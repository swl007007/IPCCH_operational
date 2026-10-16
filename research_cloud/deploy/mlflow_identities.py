"""Create the dedicated MLflow identities on the cloud service and apply the workspace roles, as the temporary
migration admin (user ruling 2026-10-16), through the loopback IAM proxy (``deploy.iam_proxy``).

1. The temporary admin's stored credential must log in and be an administrator (``users/current``).
2. ``ipcch-jobwriter`` (``mlflow-jobwriter``), ``ipcch-reader`` (``mlflow-reader``) and ``ipcch-assistant``
   (``mlflow-assistant-credentials``) are created with their stored credentials through ``users/create``. An existing
   user is accepted only if this task's receipt records its creation and its stored credential logs in; nothing is
   rotated.
3. ``service.workspace_roles.apply`` (the rehearsed applier, fail-closed precondition and before/after preservation
   proof) with the job writer as the only job identity and the copied principal that holds the copied Gateway endpoint
   USE as ``assistant_user`` - exactly the rehearsed invocation (``p2-service-d84dabd/wsc_check.py``).
Usernames are kept in the receipt; passwords never appear (scrubbed).

  python -m research_cloud.deploy.mlflow_identities --url http://127.0.0.1:8091 --copied-assistant-user NAME
      --receipt RECEIPT.json
"""
import argparse
import json
import sys

import requests

from research_cloud.deploy import provision_secrets as ps
from research_cloud.deploy.db_roles import secret_value
from research_cloud.service import workspace_roles as wr

IDENTITY_SECRETS = {"mlflow-jobwriter": "job", "mlflow-reader": "reader", "mlflow-assistant-credentials": "assistant"}


def cred(api, name):
    c = json.loads(secret_value(api, name))
    ps.KNOWN.discard(c["username"])              # usernames are not secret; only passwords are scrubbed
    ps.KNOWN.discard(json.dumps(c))
    ps.KNOWN.add(c["password"])
    return c["username"], c["password"]


def current(url, auth):
    r = requests.get(url + "/api/2.0/mlflow/users/current", auth=auth, timeout=60)
    return r.status_code, (r.json().get("user") if r.status_code == 200 else None)


def run(api, receipt, url, copied_assistant):
    admin = cred(api, "mlflow-temp-admin")
    status, me = current(url, admin)
    if status != 200 or not me or me.get("is_admin") is not True:
        raise ps.ProvisionError(f"temporary admin login failed or not an administrator ({status})")
    receipt.step("admin-login", user=admin[0], result="ok, is_admin")
    created = set(receipt.data.setdefault("identities_created", []))
    users = {}
    for secret, role in IDENTITY_SECRETS.items():
        user = cred(api, secret)
        users[role] = user[0]
        r = requests.get(url + "/api/2.0/mlflow/users/get", params={"username": user[0]}, auth=admin, timeout=60)
        if r.status_code == 200:
            if user[0] not in created:
                raise ps.ProvisionError(f"MLflow user {user[0]} exists but this task did not create it; refusing")
        elif r.status_code == 404:
            r = requests.post(url + "/api/2.0/mlflow/users/create", json={"username": user[0], "password": user[1]},
                              auth=admin, timeout=60)
            if r.status_code != 200:
                raise ps.ProvisionError(f"users/create {user[0]}: {r.status_code}")
            created.add(user[0])
            receipt.data["identities_created"] = sorted(created)
            receipt.step("identity-created", user=user[0], role=role)
        else:
            raise ps.ProvisionError(f"users/get {user[0]}: {r.status_code}")
        status, info = current(url, user)
        if status != 200 or info.get("is_admin") is not False:
            raise ps.ProvisionError(f"{user[0]} cannot log in with its stored credential or is an admin ({status})")
    report = wr.apply(wr.Admin(url, admin[1], admin[0]), [users["job"]], [], assistant_user=copied_assistant)
    receipt.data["workspace_roles"] = json.loads(json.dumps(report, default=list))
    receipt.step("workspace-roles", preserved=report["preserved"],
                 added={n: a["effective_added"] for n, a in report["added"].items() if a["effective_added"]})
    return {"users": users, "preserved": report["preserved"]}


def main(argv=None, api=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--copied-assistant-user", required=True)
    ap.add_argument("--receipt", required=True)
    args = ap.parse_args(argv)
    receipt = ps.Receipt(args.receipt)
    try:
        result = run(api or ps.Api(), receipt, args.url.rstrip("/"), args.copied_assistant_user)
    except ps.ProvisionError as e:
        receipt.step("stopped", error=ps.scrub(str(e)))
        print(ps.scrub(json.dumps({"status": "stopped", "error": str(e)})))
        return 1
    except Exception as e:              # noqa: BLE001 - recorded as a type plus scrubbed text (REST status lines only)
        receipt.step("stopped", error=ps.scrub(f"{type(e).__name__}: {e}")[:400])
        print(ps.scrub(json.dumps({"status": "stopped", "error": f"{type(e).__name__}: {e}"[:400]})))
        return 1
    print(ps.scrub(json.dumps({"status": "complete", **result})))
    return 0


if __name__ == "__main__":
    sys.exit(main())
