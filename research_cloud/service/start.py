"""Container entry point for the IPCCH MLflow service: MLflow 3.17.0, basic-auth, uvicorn, one worker.

Start-up refuses to serve unless the base contract holds:
* MLflow 3.17.0; PostgreSQL tracking and auth stores; ``MLFLOW_BASIC_AUTH_FAIL_CLOSED=true``.
* Stable Flask secret and Gateway KEK from the environment (Secret Manager), never generated per revision.
* ``MLFLOW_GATEWAY_ALLOWED_PROVIDERS`` is pinned to ``vertex_ai`` in every mode (any other value is refused): the egress
  hook wraps only the Gateway's aiohttp choke point, and providers with their own SDK clients would bypass it.
* Workspaces are enabled (``MLFLOW_ENABLE_WORKSPACES=true``): creating experiments, registered models and Gateway
  resources then needs a workspace-wide USE grant, so READ principals stay read-only (``workspace_roles.py``).
* Server job execution is forced off (``MLFLOW_SERVER_ENABLE_JOB_EXECUTION=false``; SQL trace rollups, which need it,
  are refused): job workers can call LLM providers outside the Gateway (e.g. LiteLLM judges on the service's ADC),
  which would bypass the spend guard, and this research service does not use them.

The assistant is armed only if it was requested (``IPCCH_ASSISTANT_ENABLE=1``) and every prerequisite holds:
* complete dedicated read-only credentials (``MLFLOW_TRACKING_USERNAME`` / ``_PASSWORD``);
* ``MLFLOW_GATEWAY_ALLOWED_PROVIDERS=vertex_ai`` and a Gateway endpoint name;
* a valid guard config whose ledger is reachable.

Otherwise it runs in ``deny`` mode: the remote assistant stays off (``MLFLOW_ENABLE_REMOTE_ASSISTANT=false``), the
assistant config selects no provider, and every Gateway provider egress is refused by the hook. Either way a fresh
interpreter must show the service hook loaded in the chosen mode (and, when armed, every assistant patch marker)
before the server starts; ``site`` would otherwise ignore a failing ``.pth`` line. The assistant self-calls the
server on ``127.0.0.1:$PORT``. Nothing secret is printed.

  python -m research_cloud.service.start
"""
import configparser
import json
import os
import subprocess
import sys
from pathlib import Path

BASE_ENV = ("PORT", "MLFLOW_BACKEND_STORE_URI", "MLFLOW_ARTIFACTS_DESTINATION", "IPCCH_AUTH_DATABASE_URI",
            "MLFLOW_FLASK_SERVER_SECRET_KEY", "MLFLOW_CRYPTO_KEK_PASSPHRASE", "IPCCH_ALLOWED_HOSTS")
EXIT_REFUSED = 78
PROBE = ("import json, sys; m = sys.modules.get('research_cloud.service.hook'); "
         "print(json.dumps(getattr(m, 'STATE', None)))")


class StartupRefused(Exception):
    pass


def check_base(env):
    from importlib.metadata import version

    missing = [k for k in BASE_ENV if not env.get(k, "").strip()]
    if missing:
        raise StartupRefused(f"missing required settings {missing}")
    if version("mlflow") != "3.17.0":
        raise StartupRefused(f"mlflow {version('mlflow')} is not the pinned 3.17.0")
    if env.get("MLFLOW_BASIC_AUTH_FAIL_CLOSED", "").lower() != "true":
        raise StartupRefused("MLFLOW_BASIC_AUTH_FAIL_CLOSED must be true")
    for k in ("MLFLOW_BACKEND_STORE_URI", "IPCCH_AUTH_DATABASE_URI"):
        if not env[k].startswith("postgresql"):
            raise StartupRefused(f"{k} must be a PostgreSQL URI")
    if env.get("IPCCH_REHEARSAL_FAKE_VERTEX") and env.get("K_SERVICE"):
        raise StartupRefused("the rehearsal fake upstream cannot run on Cloud Run")
    if env.get("MLFLOW_GATEWAY_ALLOWED_PROVIDERS", "vertex_ai") != "vertex_ai":
        raise StartupRefused("MLFLOW_GATEWAY_ALLOWED_PROVIDERS may only be vertex_ai")
    if env.get("MLFLOW_SQL_TRACE_ROLLUPS_ENABLED", "").lower() in ("1", "true"):
        raise StartupRefused("SQL trace rollups need server job execution, which this service keeps off")
    if not env["PORT"].isdigit():
        raise StartupRefused("PORT must be an integer")


def write_auth_config(env, path):
    """Auth ini from the environment; default READ for authenticated users as in the source service."""
    cfg = configparser.ConfigParser()
    cfg["mlflow"] = {"default_permission": "READ", "database_uri": env["IPCCH_AUTH_DATABASE_URI"],
                     "admin_username": env.get("IPCCH_ADMIN_USERNAME", "admin"),
                     "authorization_function": "mlflow.server.auth:authenticate_request_basic_auth",
                     "grant_default_workspace_access": "false"}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        cfg.write(f)


def assistant_mode(env):
    """('armed', []) or ('deny', reasons)."""
    if env.get("IPCCH_ASSISTANT_ENABLE") != "1":
        return "deny", ["assistant not requested"]
    from research_cloud.service import guard

    reasons = []
    if not (env.get("MLFLOW_TRACKING_USERNAME") and env.get("MLFLOW_TRACKING_PASSWORD")):
        reasons.append("assistant read-only credentials incomplete")
    if env.get("MLFLOW_GATEWAY_ALLOWED_PROVIDERS") != "vertex_ai":
        reasons.append("MLFLOW_GATEWAY_ALLOWED_PROVIDERS must be exactly vertex_ai")
    if not env.get("IPCCH_ASSISTANT_ENDPOINT"):
        reasons.append("IPCCH_ASSISTANT_ENDPOINT (Gateway endpoint name) missing")
    try:
        saved = dict(os.environ)
        os.environ.update(env)   # load_config reads the ledger DSN variable from the environment
        try:
            cfg = guard.load_config(env.get("IPCCH_ASSISTANT_GUARD_CONFIG") or "")
            guard.Ledger(cfg).ensure_schema()
        finally:
            os.environ.clear()
            os.environ.update(saved)
    except Exception as e:
        reasons.append(f"spend guard unavailable ({type(e).__name__})")
    return ("deny", reasons) if reasons else ("armed", [])


def write_assistant_config(mode, env, home):
    """Deterministic ~/.mlflow/assistant/config.json: the Gateway provider only, no file edits, or nothing."""
    providers = {}
    if mode == "armed":
        providers["mlflow_gateway"] = {"model": env["IPCCH_ASSISTANT_ENDPOINT"], "selected": True,
                                       "permissions": {"allow_edit_files": False, "allow_read_docs": False,
                                                       "full_access": False}}
    path = Path(home) / ".mlflow" / "assistant" / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"projects": {}, "providers": providers}, indent=2))
    return path


def verify_hook(env, mode):
    out = subprocess.run([sys.executable, "-c", PROBE], env=env, capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise StartupRefused(f"service hook failed in a fresh interpreter (exit {out.returncode}): {out.stderr.strip()[-300:]}")
    state = json.loads(out.stdout.strip().splitlines()[-1]) if out.stdout.strip() else None
    if not state or state.get("mode") != mode:
        raise StartupRefused(f"service hook not active in mode {mode}: {state}")
    if mode == "armed" and not (state.get("markers") and all(state["markers"].values())):
        raise StartupRefused(f"assistant patch markers incomplete: {state.get('markers')}")
    return state


def prepare(env):
    """Validate and build the server environment and argv. Raises StartupRefused."""
    check_base(env)
    env = dict(env)
    port = env["PORT"]
    auth_ini = Path(env.get("IPCCH_RUNTIME_DIR", "/tmp/ipcch-mlflow")) / "basic_auth.ini"
    write_auth_config(env, auth_ini)
    mode, reasons = assistant_mode(env)
    env.update(MLFLOW_AUTH_CONFIG_PATH=str(auth_ini), MLFLOW_DISABLE_AGENT_HINT="1", IPCCH_SERVICE_HOOK="1",
               IPCCH_ASSISTANT_MODE=mode, IPCCH_ASSISTANT_SELF_URL=f"http://127.0.0.1:{port}",
               MLFLOW_ENABLE_REMOTE_ASSISTANT="true" if mode == "armed" else "false",
               MLFLOW_ENABLE_ASSISTANT_SANDBOX="false", MLFLOW_SERVER_ENABLE_JOB_EXECUTION="false",
               # pinned in both modes: providers with their own SDK clients (Bedrock, LiteLLM) bypass the egress hook
               MLFLOW_GATEWAY_ALLOWED_PROVIDERS="vertex_ai", MLFLOW_ENABLE_WORKSPACES="true")
    write_assistant_config(mode, env, env.get("HOME", str(Path.home())))
    state = verify_hook(env, mode)
    argv = ["mlflow", "server", "--app-name", "basic-auth", "--host", "0.0.0.0", "--port", port, "--workers", "1",
            "--backend-store-uri", env["MLFLOW_BACKEND_STORE_URI"],
            "--artifacts-destination", env["MLFLOW_ARTIFACTS_DESTINATION"], "--serve-artifacts",
            "--allowed-hosts", env["IPCCH_ALLOWED_HOSTS"]]
    status = {"assistant_mode": mode, "assistant_refusals": reasons, "hook": state, "port": port}
    return env, argv, status


def main():
    try:
        env, argv, status = prepare(dict(os.environ))
    except StartupRefused as e:
        print(json.dumps({"startup": "refused", "reason": str(e)}), flush=True)
        sys.exit(EXIT_REFUSED)
    print(json.dumps({"startup": "ok", **status}), flush=True)
    os.execvpe(argv[0], argv, env)


if __name__ == "__main__":
    main()
