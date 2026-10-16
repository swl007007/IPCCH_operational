"""G6/G8 phase 1: task-owned credentials in Secret Manager, then the single Cloud SQL admin user (resumable).

Order (each step recorded in an incremental, sanitized receipt that is rewritten after every step, also on failure):

1. **Credentials first.** Every credential is a Secret Manager secret labelled as owned by this task, created with a
   generated value *before* anything uses it. A secret that already exists is resumed only if it carries the task
   label (its latest version is read back and reused - never rotated); any other existing secret is refused.
   Preflight: only HTTP 404 means absent; 403/5xx/transport errors stop the run (no "successful" dry run).
2. **One admin user** ``research_admin`` through the Cloud SQL Admin API (``users.insert``; such users join
   ``cloudsqlsuperuser``). Its operation is polled to ``DONE`` and its ``error`` inspected; a local wait timeout is
   recorded as ``unknown`` (not failure) and the next run resumes polling that exact operation. An existing
   ``research_admin`` is accepted only when this task's receipt holds its insert operation.
   The application and read roles are NOT created here: ``db_roles.py`` creates them as ``research_admin`` with
   ``CREATE ROLE ... LOGIN`` (never members of ``cloudsqlsuperuser``) and verifies their attributes.
3. **Dependent secrets** (connection URIs/DSN) composed from the stored passwords; an existing task-owned dependent
   secret must equal the composed value (no rotation).
4. **Secret-level accessor bindings** set exactly as in cloud-deployment-plan.md.

Values travel only in HTTPS request/response bodies; they are never printed, logged, put on a command line or written
to the receipt. Provider errors are reduced to status/reason codes (no remote free text), and every known credential
value is scrubbed from the receipt and output before they are written.

Resume rules for the admin insert: every known operation is re-polled (also when recorded DONE) and its errors
inspected; a failed insert with no user allows a new insert, a user present despite a failed insert is refused; a user
present without any recorded operation (a lost acknowledgement) is accepted only from provider state - exactly one
error-free CREATE_USER operation on the instance since the admin secret was created - and its stored credential must
then pass an actual login in db_roles.py.

  python -m research_cloud.deploy.provision_secrets --receipt RECEIPT.json [--dry-run]
"""
import argparse
import base64
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request

PROJECT = "food-crisis-modeling-enso"
REGION = "us-central1"
INSTANCE = "research-pg"
CONNECTION = f"{PROJECT}:{REGION}:{INSTANCE}"
LABELS = {"owner": "research-migration", "task": "gcp-research-modeling-migration"}
SA = {name: f"{name}@{PROJECT}.iam.gserviceaccount.com" for name in ("research-mlflow", "research-trainer")}
ADMIN = "research_admin"
PASSWORDS = {"sql-research-admin": [], "sql-mlflow-app": [], "sql-guard-app": [],
             "sql-research-import": [], "sql-research-read": []}             # operator-only
GENERATED = {"mlflow-flask-secret": ["research-mlflow"], "mlflow-kek-passphrase": ["research-mlflow"]}
IDENTITIES = {"mlflow-assistant-credentials": ("ipcch-assistant", ["research-mlflow"]),
              "mlflow-jobwriter": ("ipcch-jobwriter", ["research-trainer"]),
              "mlflow-reader": ("ipcch-reader", [])}
SOCKET = f"/cloudsql/{CONNECTION}"
# the driver is explicit: SQLAlchemy 2.1 maps a bare postgresql:// to psycopg (v3), and the service image ships psycopg2
DRIVER = "postgresql+psycopg2"
DEPENDENT = {
    "mlflow-backend-uri": (lambda pw: f"{DRIVER}://mlflow_app:{pw['sql-mlflow-app']}@/mlflow?host={SOCKET}", ["research-mlflow"]),
    "mlflow-auth-db-uri": (lambda pw: f"{DRIVER}://mlflow_app:{pw['sql-mlflow-app']}@/mlflow_auth?host={SOCKET}", ["research-mlflow"]),
    "guard-dsn": (lambda pw: f"host={SOCKET} dbname=guard user=guard_app password={pw['sql-guard-app']}", ["research-mlflow"]),
}


class ProvisionError(Exception):
    pass


class Api:
    """Minimal REST client; tests replace it with a fake."""

    def __init__(self, token=None):
        self.token = token or subprocess.run(["gcloud", "auth", "print-access-token", f"--billing-project={PROJECT}", "--quiet"],
                                             capture_output=True, text=True, check=True).stdout.strip()

    def call(self, method, url, body=None):
        req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {self.token}", "x-goog-user-project": PROJECT,
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")
        except (urllib.error.URLError, OSError) as e:
            return None, {"error": {"message": f"transport: {type(e).__name__}"}}


SM = f"https://secretmanager.googleapis.com/v1/projects/{PROJECT}/secrets"
SQL = f"https://sqladmin.googleapis.com/v1/projects/{PROJECT}"


def message(body):
    """Provider error as codes only (status and reasons); remote free text never enters receipts or output."""
    err = (body or {}).get("error", {}) or {}
    reasons = sorted({str(e.get("reason")) for e in err.get("errors", []) if e.get("reason")}
                     | {str(d.get("reason")) for d in err.get("details", []) if isinstance(d, dict) and d.get("reason")})
    return f"[{err.get('status') or 'no-status'}{' ' + ','.join(reasons) if reasons else ''}]"


KNOWN = set()     # every credential value seen in this process (generated or read back)


def remember(value):
    KNOWN.add(value)
    if value.startswith("{"):
        try:
            KNOWN.update(str(v) for v in json.loads(value).values())
        except ValueError:
            pass
    return value


def scrub(text):
    for value in sorted((v for v in KNOWN if len(v) >= 8), key=len, reverse=True):
        text = text.replace(value, "[redacted]")
    return text


class Receipt:
    def __init__(self, path):
        self.path = path
        self.data = json.load(open(path)) if os.path.exists(path) else {"secrets": {}, "sql_ops": {}, "steps": []}

    def step(self, what, **fields):
        self.data["steps"].append({"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "step": what, **fields})
        self.save()

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            f.write(scrub(json.dumps(self.data, indent=1)))      # defence in depth: no known credential persists
        os.replace(tmp, self.path)


def secret_state(api, name):
    """'absent' (404 only), ('task', latest value) for a task-owned secret, or raise."""
    status, body = api.call("GET", f"{SM}/{name}")
    if status == 404:
        return "absent", None
    if status != 200:
        raise ProvisionError(f"secret {name}: preflight returned {status} {message(body)}")
    if any(body.get("labels", {}).get(k) != v for k, v in LABELS.items()):
        raise ProvisionError(f"secret {name} exists but is not owned by this task; refusing")
    status, ver = api.call("GET", f"{SM}/{name}/versions/latest:access")
    if status == 404:                                        # created by this task, version write never landed
        return "task-empty", None
    if status != 200:
        raise ProvisionError(f"secret {name}: cannot read its task-owned version ({status} {message(ver)})")
    return "task", remember(base64.b64decode(ver["payload"]["data"]).decode())


def ensure_secret(api, receipt, name, make_value, accessors, must_equal=None):
    """The secret's value: resumed (task-owned, never rotated) or created with ``make_value()``."""
    state, value = secret_state(api, name)
    if state == "task":
        if must_equal is not None and value != must_equal:
            raise ProvisionError(f"secret {name} holds a different value than composed; refusing to rotate it")
        receipt.data["secrets"].setdefault(name, {})["resumed"] = True
    else:
        value = remember(make_value() if must_equal is None else must_equal)
        if state == "absent":
            status, body = api.call("POST", f"{SM}?secretId={name}", {
                "replication": {"userManaged": {"replicas": [{"location": REGION}]}}, "labels": LABELS})
            if status != 200:
                raise ProvisionError(f"secret {name}: create returned {status} {message(body)}")
        status, ver = api.call("POST", f"{SM}/{name}:addVersion",
                               {"payload": {"data": base64.b64encode(value.encode()).decode()}})
        if status != 200:
            raise ProvisionError(f"secret {name}: addVersion returned {status} {message(ver)}")
        receipt.data["secrets"][name] = {"version": ver.get("name", "").rsplit("/", 1)[-1], "replication": REGION}
    policy = {"bindings": [{"role": "roles/secretmanager.secretAccessor",
                            "members": [f"serviceAccount:{SA[a]}" for a in accessors]}]} if accessors else {}
    status, body = api.call("POST", f"{SM}/{name}:setIamPolicy", {"policy": policy})
    if status != 200:
        raise ProvisionError(f"secret {name}: setIamPolicy returned {status} {message(body)}")
    receipt.data["secrets"][name]["accessors"] = accessors
    receipt.step("secret", name=name, resumed=state == "task")
    return value


POLL_WAIT_S, POLL_EVERY_S = 600, 5


def poll(api, receipt, op_name, wait_s=None, every_s=None, sleep=None):
    """Poll a Cloud SQL operation to DONE; record 'unknown' (not failure) on a local wait timeout."""
    wait_s, every_s, sleep = wait_s or POLL_WAIT_S, every_s or POLL_EVERY_S, sleep or time.sleep
    deadline = time.monotonic() + wait_s
    while True:
        status, op = api.call("GET", f"{SQL}/operations/{op_name}")
        if status != 200:
            receipt.data["sql_ops"][op_name]["status"] = "unknown"
            receipt.step("sql-op-poll", operation=op_name, status="unknown", http=status)
            raise ProvisionError(f"operation {op_name}: poll returned {status}; state unknown, rerun to resume")
        receipt.data["sql_ops"][op_name]["status"] = op.get("status")
        if op.get("status") == "DONE":
            errors = op.get("error", {}).get("errors", [])
            receipt.data["sql_ops"][op_name]["errors"] = [e.get("code") for e in errors]
            receipt.step("sql-op-done", operation=op_name, errors=[e.get("code") for e in errors])
            if errors:
                raise ProvisionError(f"operation {op_name} finished with errors {[e.get('code') for e in errors]}")
            return op
        if time.monotonic() >= deadline:
            receipt.data["sql_ops"][op_name]["status"] = "unknown"
            receipt.step("sql-op-wait-timeout", operation=op_name, status="unknown")
            raise ProvisionError(f"operation {op_name} not DONE within the local wait; state unknown, rerun to resume")
        sleep(every_s)


def recovered_insert(api, receipt):
    """A lost users.insert acknowledgement, recovered from provider state: exactly one error-free CREATE_USER operation
    on the instance since the admin credential's secret was created. The stored credential itself is then proven by
    an actual login in db_roles.py (recorded as pending here)."""
    status, sec = api.call("GET", f"{SM}/sql-research-admin")
    if status != 200 or not sec.get("createTime"):
        return None
    status, ops = api.call("GET", f"{SQL}/operations?instance={INSTANCE}")
    if status != 200:
        raise ProvisionError(f"cannot list instance operations: {status} {message(ops)}")
    created = [o for o in ops.get("items", []) if o.get("operationType") == "CREATE_USER" and o.get("status") == "DONE"
               and not o.get("error") and o.get("insertTime", "") >= sec["createTime"]]
    return created[0] if len(created) == 1 else None


def ensure_admin(api, receipt, password):
    known = [n for n, o in receipt.data["sql_ops"].items() if o.get("kind") == "insert-user" and o.get("user") == ADMIN]
    succeeded = []
    for op_name in known:                    # every known insert is re-polled and its errors inspected, even if DONE
        try:
            poll(api, receipt, op_name)
            succeeded.append(op_name)
        except ProvisionError as e:
            if receipt.data["sql_ops"][op_name].get("status") != "DONE":
                raise                        # still unknown: never start another insert meanwhile
            receipt.data["sql_ops"][op_name]["failed"] = True
            receipt.step("sql-op-failed", operation=op_name, detail=str(e))
    status, users = api.call("GET", f"{SQL}/instances/{INSTANCE}/users")
    if status != 200:
        raise ProvisionError(f"cannot list SQL users: {status} {message(users)}")
    if ADMIN in {u["name"] for u in users.get("items", [])}:
        if succeeded:
            receipt.step("sql-admin", user=ADMIN, state="present (this task's operation)")
            return
        if known:
            raise ProvisionError(f"{ADMIN} exists although this task's insert failed; refusing")
        op = recovered_insert(api, receipt)
        if op is None:
            raise ProvisionError(f"{ADMIN} exists without a recorded or recoverable insert of this task; refusing")
        receipt.data["sql_ops"][op["name"]] = {"kind": "insert-user", "user": ADMIN, "status": "DONE",
                                               "recovered_from": "instance operation list (CREATE_USER)",
                                               "credential": "pending login proof in db_roles"}
        receipt.step("sql-admin", user=ADMIN, state="recovered lost acknowledgement", operation=op["name"])
        return
    status, op = api.call("POST", f"{SQL}/instances/{INSTANCE}/users", {"name": ADMIN, "password": password})
    if status != 200:
        raise ProvisionError(f"{ADMIN}: insert returned {status} {message(op)}")
    receipt.data["sql_ops"][op["name"]] = {"kind": "insert-user", "user": ADMIN, "status": op.get("status")}
    receipt.step("sql-op-started", operation=op["name"], user=ADMIN)
    poll(api, receipt, op["name"])


def run(api, receipt, dry_run=False):
    names = list(PASSWORDS) + list(GENERATED) + list(IDENTITIES) + list(DEPENDENT)
    states = {n: secret_state(api, n)[0] for n in names}           # raises on anything but 200/404
    receipt.step("preflight", states=states)
    if dry_run:
        return states
    pw = {name: ensure_secret(api, receipt, name, lambda: secrets.token_urlsafe(32), accessors)
          for name, accessors in PASSWORDS.items()}
    for name, accessors in GENERATED.items():
        ensure_secret(api, receipt, name, lambda: secrets.token_urlsafe(48), accessors)
    for name, (user, accessors) in IDENTITIES.items():
        ensure_secret(api, receipt, name, lambda u=user: json.dumps({"username": u, "password": secrets.token_urlsafe(32)}),
                      accessors)
    ensure_admin(api, receipt, pw["sql-research-admin"])
    for name, (compose, accessors) in DEPENDENT.items():
        ensure_secret(api, receipt, name, None, accessors, must_equal=compose(pw))
    receipt.step("complete")
    return states


def main(argv=None, api=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--receipt", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    receipt = Receipt(args.receipt)
    try:
        states = run(api or Api(), receipt, args.dry_run)
    except ProvisionError as e:
        receipt.step("stopped", error=scrub(str(e)))
        print(scrub(json.dumps({"status": "stopped", "error": str(e)})))
        return 1
    print(json.dumps({"status": "dry-run" if args.dry_run else "complete", "secrets": len(receipt.data["secrets"]),
                      "absent_before": sum(s == "absent" for s in states.values())}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
