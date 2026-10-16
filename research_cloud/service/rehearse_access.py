"""HTTP access rehearsal for the IPCCH MLflow service (local, disposable stores; no provider call).

Creates throwaway users through the admin API, then checks each principal against the routes the design names:
tracking, artifacts (proxied), Gateway, assistant and user administration. "remote" requests carry
X-Forwarded-For from a documentation address, which uvicorn (trusting 127.0.0.1) turns into a non-loopback client,
as every Cloud Run client will be. Prints and writes a report of expected vs observed status; secrets never appear.

  python -m research_cloud.service.rehearse_access --url http://127.0.0.1:55500 --mode deny|armed --out REPORT.json
      [--state STATE.json]          # keep the throwaway credentials (mode 600) for a restart check
  python -m research_cloud.service.rehearse_access --url ... --verify-restart STATE.json --out REPORT.json
  (admin password from MLFLOW_AUTH_ADMIN_PASSWORD)

The Gateway check creates an OpenAI-type endpoint with a fake key and an unroutable api_base: in deny mode the
service hook must refuse the egress (503, guard message) before any connection; in armed mode the native provider
allowlist (vertex_ai only) must refuse it. Neither reaches a network.
"""
import argparse
import json
import os
import secrets

import requests

REMOTE = {"X-Forwarded-For": "203.0.113.7"}


class Rehearsal:
    def __init__(self, url):
        self.url, self.results, self.auth = url.rstrip("/"), [], {}

    def call(self, who, method, path, expect, *, json_body=None, data=None, remote=True, note=""):
        headers = dict(REMOTE) if remote else {}
        auth = self.auth.get(who)
        r = requests.request(method, self.url + path, json=json_body, data=data, headers=headers, auth=auth, timeout=60)
        ok = r.status_code in (expect if isinstance(expect, tuple) else (expect,))
        self.results.append({"principal": who, "method": method, "path": path.split("?")[0], "remote": remote,
                             "expected": expect, "observed": r.status_code, "ok": ok, "note": note})
        return r

    def setup(self, *args, **kwargs):
        """A call the rehearsal depends on; stop rather than report later results against a broken setup."""
        r = self.call(*args, **kwargs)
        if not self.results[-1]["ok"]:
            raise SystemExit(f"setup step failed: {self.results[-1]}")
        return r

    def user(self, role, suffix):
        name, password = f"{role}-{suffix}", secrets.token_urlsafe(18)
        self.setup("admin", "POST", "/api/2.0/mlflow/users/create", 200, json_body={"username": name, "password": password},
                   note="admin creates user")
        self.auth[role] = (name, password)


def run(url, mode):
    t = Rehearsal(url)
    t.auth["admin"] = ("admin", os.environ["MLFLOW_AUTH_ADMIN_PASSWORD"])
    t.call("anonymous", "GET", "/health", 200, note="content-free health")
    for path in ("/api/2.0/mlflow/experiments/search?max_results=5", "/api/2.0/mlflow/registered-models/search",
                 "/api/2.0/mlflow-artifacts/artifacts", "/ajax-api/2.0/mlflow/gateway/endpoints/list",
                 "/ajax-api/3.0/mlflow/assistant/config"):
        t.call("anonymous", "GET", path, 401, note="anonymous content route")
    t.call("anonymous", "POST", "/gateway/mlflow/v1/chat/completions", 401,
           json_body={"model": "x", "messages": [{"role": "user", "content": "hi"}]}, note="anonymous gateway")
    t.call("anonymous", "POST", "/api/2.0/mlflow/users/create", 401, json_body={"username": "x", "password": "y" * 12})

    suffix = secrets.token_hex(3)
    for role in ("reader", "jobwriter", "assistant"):
        t.user(role, suffix)
    exp = t.setup("admin", "POST", "/api/2.0/mlflow/experiments/create", 200,
                 json_body={"name": f"rehearsal-{secrets.token_hex(3)}"}).json()["experiment_id"]
    t.setup("admin", "POST", "/api/3.0/mlflow/users/permissions/grant", 200,
            json_body={"username": t.auth["jobwriter"][0], "resource_type": "experiment", "resource_id": exp, "permission": "EDIT"},
           note="job writer EDIT on the experiment")

    run_id = t.setup("jobwriter", "POST", "/api/2.0/mlflow/runs/create", 200,
                    json_body={"experiment_id": exp}).json()["run"]["info"]["run_id"]
    t.call("jobwriter", "POST", "/api/2.0/mlflow/runs/log-metric", 200,
           json_body={"run_id": run_id, "key": "m", "value": 1.0, "timestamp": 0, "step": 0})
    art = f"/api/2.0/mlflow-artifacts/artifacts/{exp}/{run_id}/artifacts/probe.txt"
    t.call("jobwriter", "PUT", art, 200, data=b"rehearsal artifact", note="job writer uploads via artifact proxy")

    for who in ("reader", "assistant"):
        t.call(who, "GET", f"/api/2.0/mlflow/runs/get?run_id={run_id}", 200, note="default READ")
        t.call(who, "GET", art, 200, note="READ downloads artifact")
        t.call(who, "POST", "/api/2.0/mlflow/runs/create", 403, json_body={"experiment_id": exp}, note="READ cannot write")
        t.call(who, "POST", "/api/2.0/mlflow/runs/log-metric", 403,
               json_body={"run_id": run_id, "key": "m", "value": 2.0, "timestamp": 0, "step": 1})
        t.call(who, "PUT", art.replace("probe", "overwrite"), 403, data=b"x", note="READ cannot upload")
        t.call(who, "POST", "/api/2.0/mlflow/experiments/delete", 403, json_body={"experiment_id": exp})
        t.call(who, "POST", "/api/2.0/mlflow/users/create", 403, json_body={"username": f"{who}-{suffix}-2", "password": "p" * 16})
        t.call(who, "POST", "/api/2.0/mlflow/users/update-admin", 403, json_body={"username": t.auth[who][0], "is_admin": True},
               note="no self-escalation")
    t.call("jobwriter", "POST", "/api/2.0/mlflow/experiments/delete", 403, json_body={"experiment_id": exp},
           note="EDIT is not MANAGE")

    # assistant routes: config writes and skills install stay loopback-only; chat follows the mode
    t.call("admin", "PUT", "/ajax-api/3.0/mlflow/assistant/config", 403, json_body={"providers": {}},
           note="remote config write refused even for admin")
    t.call("admin", "PUT", "/ajax-api/3.0/mlflow/assistant/config", (200, 403, 422), json_body={"providers": {}},
           remote=False, note="loopback config write (observational)")
    msg = {"message": "list experiments", "context": {}}
    t.call("assistant", "POST", "/ajax-api/3.0/mlflow/assistant/message", 403 if mode == "deny" else (200, 400, 422),
           json_body=msg, note=f"remote assistant chat in {mode} mode")
    gateway_egress(t, mode)
    return t, {"experiment_id": exp, "run_id": run_id, "artifact": art, "auth": t.auth}


def gateway_egress(t, mode):
    from mlflow.entities.gateway_endpoint import GatewayEndpointModelConfig, GatewayModelLinkageType
    from mlflow.store.tracking.rest_store import RestStore
    from mlflow.utils.rest_utils import MlflowHostCreds

    user, password = t.auth["admin"]
    store = RestStore(lambda: MlflowHostCreds(t.url, username=user, password=password))
    tag = secrets.token_hex(3)
    try:
        secret = store.create_gateway_secret(f"rehearsal-{tag}", {"api_key": "rehearsal-not-a-key"}, provider="openai",
                                              auth_config={"api_base": "https://example.com:9/v1"})
        model = store.create_gateway_model_definition(f"rehearsal-{tag}", secret.secret_id, "openai", "gpt-rehearsal")
        store.create_gateway_endpoint(f"rehearsal-{tag}", [GatewayEndpointModelConfig(
            model_definition_id=model.model_definition_id, linkage_type=GatewayModelLinkageType.PRIMARY, weight=1.0)])
    except Exception as e:   # armed mode: the provider allowlist may refuse at creation
        t.results.append({"principal": "admin", "method": "POST", "path": "gateway endpoint create (openai)",
                          "remote": False, "expected": "refused in armed mode" if mode == "armed" else "created",
                          "observed": type(e).__name__, "ok": mode == "armed", "note": str(e)[:200]})
        return
    r = t.call("admin", "POST", "/gateway/mlflow/v1/chat/completions", 503 if mode == "deny" else (400, 403, 404, 500, 503),
               json_body={"model": f"rehearsal-{tag}", "messages": [{"role": "user", "content": "hi"}]},
               note=f"provider egress in {mode} mode")
    t.results[-1]["note"] += f"; response {r.text[:160]!r}"
    if mode == "armed":   # must be the native allowlist refusal, not an upstream attempt
        native = "not allowed" in r.text
        t.results[-1].update(ok=t.results[-1]["ok"] and native)
    if mode == "deny":
        guarded = "disabled on this server" in r.text
        t.results[-1].update(ok=t.results[-1]["ok"] and guarded, note=t.results[-1]["note"] + f"; guard message {guarded}")


def verify_restart(url, state):
    """After a server restart: the same principals keep exactly their roles (PostgreSQL-backed auth)."""
    t = Rehearsal(url)
    t.auth = {k: tuple(v) for k, v in state["auth"].items()}
    t.call("jobwriter", "POST", "/api/2.0/mlflow/runs/log-metric", 200,
           json_body={"run_id": state["run_id"], "key": "m", "value": 3.0, "timestamp": 0, "step": 2})
    t.call("jobwriter", "POST", "/api/2.0/mlflow/experiments/delete", 403, json_body={"experiment_id": state["experiment_id"]})
    for who in ("reader", "assistant"):
        t.call(who, "GET", state["artifact"], 200)
        t.call(who, "POST", "/api/2.0/mlflow/runs/create", 403, json_body={"experiment_id": state["experiment_id"]})
    t.call("anonymous", "GET", state["artifact"], 401)
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--mode", choices=("deny", "armed"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--state")
    ap.add_argument("--verify-restart")
    args = ap.parse_args()
    if args.verify_restart:
        t = verify_restart(args.url, json.load(open(args.verify_restart)))
    else:
        t, state = run(args.url, args.mode)
        if args.state:
            fd = os.open(args.state, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump({k: v for k, v in state.items() if k != "auth"} | {"auth": {k: list(v) for k, v in state["auth"].items()
                                                                                  if k != "admin"}}, f)
    results = t.results
    json.dump({"mode": args.mode or "verify-restart", "passed": sum(r["ok"] for r in results), "total": len(results),
               "results": results}, open(args.out, "w"), indent=1)
    for r in results:
        if not r["ok"]:
            print("MISMATCH", r)
    print(f"{sum(r['ok'] for r in results)}/{len(results)} as expected")


if __name__ == "__main__":
    main()
