"""G6/G8: create the service's Cloud SQL users and its Secret Manager secrets without exposing any value.

Values are generated here (``secrets.token_urlsafe``) and travel only in HTTPS request bodies to the Cloud SQL Admin
API (users.insert) and the Secret Manager API (secrets.create / addVersion); they never appear on a command line, in
output, in files or in the receipt. The OAuth token comes from ``gcloud auth print-access-token`` and every request
names the target project as quota project (``x-goog-user-project``). Existing secrets or users are refused (nothing is
overwritten). Secret-level accessor grants follow cloud-deployment-plan.md. The receipt lists names, versions and
grants only.

  python -m research_cloud.deploy.provision_secrets --receipt RECEIPT.json [--dry-run]
"""
import argparse
import base64
import json
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
SA = {name: f"{name}@{PROJECT}.iam.gserviceaccount.com" for name in ("research-mlflow", "research-trainer")}
DB_USERS = ("mlflow_app", "guard_app", "research_import", "research_read")
MLFLOW_IDENTITIES = ("jobwriter", "reader", "assistant")     # basic-auth users created in the auth DB later


def token():
    return subprocess.run(["gcloud", "auth", "print-access-token", f"--billing-project={PROJECT}", "--quiet"],
                          capture_output=True, text=True, check=True).stdout.strip()


def call(method, url, body=None, tok=None):
    req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {tok}", "x-goog-user-project": PROJECT,
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def values():
    pw = {u: secrets.token_urlsafe(32) for u in DB_USERS}
    ident = {i: {"username": f"ipcch-{i}", "password": secrets.token_urlsafe(32)} for i in MLFLOW_IDENTITIES}
    sock = f"/cloudsql/{CONNECTION}"
    plan = {
        "mlflow-backend-uri": (f"postgresql://mlflow_app:{pw['mlflow_app']}@/mlflow?host={sock}", ["research-mlflow"]),
        "mlflow-auth-db-uri": (f"postgresql://mlflow_app:{pw['mlflow_app']}@/mlflow_auth?host={sock}", ["research-mlflow"]),
        "mlflow-flask-secret": (secrets.token_urlsafe(48), ["research-mlflow"]),
        "mlflow-kek-passphrase": (secrets.token_urlsafe(48), ["research-mlflow"]),
        "mlflow-assistant-credentials": (json.dumps(ident["assistant"]), ["research-mlflow"]),
        "guard-dsn": (f"host={sock} dbname=guard user=guard_app password={pw['guard_app']}", ["research-mlflow"]),
        "mlflow-jobwriter": (json.dumps(ident["jobwriter"]), ["research-trainer"]),
        "mlflow-reader": (json.dumps(ident["reader"]), []),               # operator only
        "research-import-password": (pw["research_import"], []),          # operator only (Auth Proxy import)
        "research-read-password": (pw["research_read"], []),              # operator only
    }
    return pw, plan


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--receipt", required=True)
    ap.add_argument("--dry-run", action="store_true", help="check that nothing exists yet; create nothing")
    args = ap.parse_args(argv)
    tok = token()
    sql = f"https://sqladmin.googleapis.com/v1/projects/{PROJECT}/instances/{INSTANCE}/users"
    sm = f"https://secretmanager.googleapis.com/v1/projects/{PROJECT}/secrets"
    status, existing_users = call("GET", sql, tok=tok)
    if status != 200:
        raise SystemExit(f"cannot list SQL users: {status} {existing_users.get('error', {}).get('message')}")
    clash_users = sorted({u["name"] for u in existing_users.get("items", [])} & set(DB_USERS))
    pw, plan = values()
    clash_secrets = [n for n in plan if call("GET", f"{sm}/{n}", tok=tok)[0] == 200]
    if clash_users or clash_secrets:
        raise SystemExit(f"refusing to overwrite: users {clash_users}, secrets {clash_secrets}")
    receipt = {"time_start": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "instance": CONNECTION, "users": [], "secrets": []}
    if args.dry_run:
        receipt["dry_run"] = {"users_to_create": list(DB_USERS), "secrets_to_create": list(plan)}
    else:
        for user in DB_USERS:
            status, op = call("POST", sql, {"name": user, "password": pw[user]}, tok)
            if status != 200:
                raise SystemExit(f"user {user}: {status} {op.get('error', {}).get('message')}")
            receipt["users"].append({"name": user, "operation": op.get("name")})
        for name, (value, accessors) in plan.items():
            status, sec = call("POST", f"{sm}?secretId={name}", {
                "replication": {"userManaged": {"replicas": [{"location": REGION}]}},
                "labels": {"owner": "research-migration"}}, tok)
            if status != 200:
                raise SystemExit(f"secret {name}: {status} {sec.get('error', {}).get('message')}")
            data = base64.b64encode(value.encode()).decode()
            status, ver = call("POST", f"{sm}/{name}:addVersion", {"payload": {"data": data}}, tok)
            if status != 200:
                raise SystemExit(f"secret {name} version: {status} {ver.get('error', {}).get('message')}")
            grants = []
            if accessors:
                policy = {"bindings": [{"role": "roles/secretmanager.secretAccessor",
                                        "members": [f"serviceAccount:{SA[a]}" for a in accessors]}]}
                status, pol = call("POST", f"{sm}/{name}:setIamPolicy", {"policy": policy}, tok)
                if status != 200:
                    raise SystemExit(f"secret {name} policy: {status} {pol.get('error', {}).get('message')}")
                grants = accessors
            receipt["secrets"].append({"name": name, "version": ver.get("name", "").rsplit("/", 1)[-1],
                                       "replication": REGION, "accessors": grants})
        del pw, plan
    receipt["time_end"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with open(args.receipt, "w") as f:
        json.dump(receipt, f, indent=1)
    print(json.dumps({"users": len(receipt["users"]), "secrets": len(receipt["secrets"]),
                      "dry_run": args.dry_run}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
