"""Temporary migration admin for the cloud MLflow auth store (user ruling 2026-10-16: create, use for the in-scope
admin steps, remove after acceptance; the owner's personal account and password are never read or changed).

``create``: the credential is generated into this task's Secret Manager secret ``mlflow-temp-admin`` (task labels,
no accessor bindings: operator only; resumed, never rotated) and the user is created directly in the ``mlflow_auth``
database as ``mlflow_app`` through the Auth Proxy, with MLflow 3.17's own auth store (its password hashing). An
existing user of that name is accepted only when this task's receipt records its creation. ``remove``: the user is
deleted through the same store and its secret versions are disabled and destroyed. Both record a before/after user
snapshot (username, is_admin) and the diff: exactly the temporary admin is added/removed, every other user unchanged.
No credential is printed or receipted (scrubbed receipt as in ``provision_secrets``).

  python -m research_cloud.deploy.temp_admin create|remove --port 5433 --receipt RECEIPT.json
"""
import argparse
import json
import secrets
import sys

from research_cloud.deploy.db_roles import secret_value
from research_cloud.deploy.provision_secrets import (SM, Api, ProvisionError, Receipt, ensure_secret, message,
                                                     remember, scrub)

USERNAME = "ipcch-migration-admin"
SECRET = "mlflow-temp-admin"


def store(api, port):
    from mlflow.server.auth.sqlalchemy_store import SqlAlchemyStore
    password = secret_value(api, "sql-mlflow-app")
    s = SqlAlchemyStore()
    s.init_db(f"postgresql+psycopg2://mlflow_app:{password}@127.0.0.1:{port}/mlflow_auth?sslmode=disable")
    return s


def users(s):
    return {u.username: bool(u.is_admin) for u in s.list_users()}


def create(api, receipt, port):
    cred = json.loads(ensure_secret(api, receipt, SECRET,
                                    lambda: json.dumps({"username": USERNAME, "password": secrets.token_urlsafe(32)}), []))
    remember(cred["password"])
    s = store(api, port)
    before = users(s)
    if USERNAME in before:
        if not receipt.data.get("temp_admin_created"):
            raise ProvisionError(f"{USERNAME} exists but this task did not create it; refusing")
        if not s.authenticate_user(USERNAME, cred["password"]):
            raise ProvisionError(f"{USERNAME} exists but its stored credential does not authenticate; refusing")
    else:
        s.create_user(USERNAME, cred["password"], is_admin=True)
        receipt.data["temp_admin_created"] = True
    after = users(s)
    diff = check(before, after, added=USERNAME)
    receipt.data["create"] = {"before": before, "after": after, "diff": diff,
                              "authenticates": s.authenticate_user(USERNAME, cred["password"])}
    receipt.step("temp-admin-created", user=USERNAME, diff=diff)
    return receipt.data["create"]


def remove(api, receipt, port):
    s = store(api, port)
    before = users(s)
    if USERNAME in before:
        s.delete_user(USERNAME)
    after = users(s)
    diff = check(before, after, removed=USERNAME)
    status, body = api.call("GET", f"{SM}/{SECRET}/versions")
    if status != 200:
        raise ProvisionError(f"secret {SECRET}: list versions returned {status} {message(body)}")
    destroyed = []
    for v in body.get("versions", []):
        if v.get("state") != "DESTROYED":
            status, out = api.call("POST", f"https://secretmanager.googleapis.com/v1/{v['name']}:destroy", {})
            if status != 200:
                raise ProvisionError(f"secret {SECRET}: destroy returned {status} {message(out)}")
            destroyed.append(v["name"].rsplit("/", 1)[-1])
    receipt.data["remove"] = {"before": before, "after": after, "diff": diff, "secret_versions_destroyed": destroyed}
    receipt.step("temp-admin-removed", user=USERNAME, diff=diff, secret_versions_destroyed=destroyed)
    return receipt.data["remove"]


def check(before, after, added=None, removed=None):
    """The only change is the temporary admin (added as admin, or removed); any other difference refuses."""
    others_b = {u: a for u, a in before.items() if u != USERNAME}
    others_a = {u: a for u, a in after.items() if u != USERNAME}
    if others_b != others_a:
        raise ProvisionError("users other than the temporary admin changed; refusing")
    if added and after.get(added) is not True:
        raise ProvisionError(f"{added} is not present as an admin after create")
    if removed and removed in after:
        raise ProvisionError(f"{removed} is still present after remove")
    return {"added": [added] if added and added not in before else [], "removed": [removed] if removed and removed in before else [],
            "others_unchanged": len(others_a)}


def main(argv=None, api=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("create", "remove"))
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--receipt", required=True)
    args = ap.parse_args(argv)
    receipt = Receipt(args.receipt)
    api = api or Api()
    try:
        result = (create if args.action == "create" else remove)(api, receipt, args.port)
    except ProvisionError as e:
        receipt.step("stopped", error=scrub(str(e)))
        print(scrub(json.dumps({"status": "stopped", "error": str(e)})))
        return 1
    except Exception as e:              # noqa: BLE001 - driver/store errors as a type only
        receipt.step("stopped", error=type(e).__name__)
        print(json.dumps({"status": "stopped", "error": type(e).__name__}))
        return 1
    print(scrub(json.dumps({"status": "complete", "action": args.action, "diff": result["diff"]})))
    return 0


if __name__ == "__main__":
    sys.exit(main())
