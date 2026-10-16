"""Workspace-role check on a disposable copy of the r1-copied stores (local rehearsal; usernames redacted in output)."""
import json, secrets, sys, requests
from research_cloud.service import workspace_roles as wr
D = sys.argv[1]; U = "http://127.0.0.1:55502"; H = {"X-Forwarded-For": "203.0.113.7"}
creds = json.load(open(f"{D}/wsc-creds.json")); admin = tuple(creds["admin"]); asst = tuple(creds["user-2"])
res = []
def call(phase, who, auth, m, path, expect, body=None, params=None):
    r = requests.request(m, U + path, json=body, params=params, auth=auth, headers=H, timeout=60)
    res.append({"phase": phase, "principal": who, "call": f"{m} {path}", "expected": expect, "observed": r.status_code, "ok": r.status_code == expect})
    return r
api = wr.Admin(U, admin[1], admin[0])
me = call("before", "copied-nonadmin", asst, "GET", "/api/2.0/mlflow/users/current", 200).json()["user"]
res[-1]["ok"] &= me["is_admin"] is False
call("before", "copied-nonadmin", asst, "GET", "/api/2.0/mlflow/experiments/get", 403, params={"experiment_id": "1"})
job = ("jobwriter-" + secrets.token_hex(3), secrets.token_urlsafe(18))
call("setup", "admin", admin, "POST", "/api/2.0/mlflow/users/create", 200, body={"username": job[0], "password": job[1]})
report = wr.apply(api, [job[0]], ["1"], assistant_user=asst[0])
for path, params in (("/api/2.0/mlflow/experiments/get", {"experiment_id": "1"}), ("/api/2.0/mlflow/experiments/search", {"max_results": 50})):
    call("after", "copied-nonadmin", asst, "GET", path, 200, params=params)
n_exp = len(requests.get(U + "/api/2.0/mlflow/experiments/search", params={"max_results": 50}, auth=asst, headers=H).json().get("experiments", []))
for path, body in (("/api/2.0/mlflow/experiments/create", {"name": "x-" + secrets.token_hex(2)}),
                   ("/api/2.0/mlflow/registered-models/create", {"name": "x-" + secrets.token_hex(2)}),
                   ("/api/3.0/mlflow/gateway/secrets/create", {"secret_name": "x" + secrets.token_hex(2), "secret_value": {"api_key": "x"}, "provider": "vertex_ai"}),
                   ("/api/2.0/mlflow/runs/create", {"experiment_id": "1"})):
    call("after", "copied-nonadmin", asst, "POST", path, 403, body=body)
for eid in [e["endpoint_id"] for e in api("GET", "/api/3.0/mlflow/gateway/endpoints/list").get("endpoints", [])]:
    r = call("after", "admin", admin, "GET", "/api/3.0/mlflow/users/permissions/get", 200,
             params={"username": asst[0], "resource_type": "gateway_endpoint", "resource_id": eid})
    res[-1]["detail"] = r.json()
new = call("after", "new-job-writer", job, "POST", "/api/2.0/mlflow/experiments/create", 200, body={"name": "job-" + secrets.token_hex(2)}).json().get("experiment_id")
call("after", "new-job-writer", job, "POST", "/api/2.0/mlflow/runs/create", 200, body={"experiment_id": new})
call("after", "new-job-writer", job, "POST", "/api/2.0/mlflow/runs/create", 200, body={"experiment_id": "1"})
call("after", "new-job-writer", job, "POST", "/api/2.0/mlflow/runs/create", 403, body={"experiment_id": "2"})
call("after", "new-job-writer", job, "POST", "/api/2.0/mlflow/experiments/delete", 403, body={"experiment_id": "1"})
call("after", "admin", admin, "POST", "/api/2.0/mlflow/runs/create", 200, body={"experiment_id": "2"})
out = {"store": "disposable copy of the r1-copied tracking/auth stores (wsc_*), workspaces enabled",
       "visible_experiments_to_copied_nonadmin": n_exp,
       "role_report": wr.redact(report, {admin[0]: "admin", asst[0]: "copied-nonadmin", job[0]: "new-job-writer"}),
       "checks": res, "passed": sum(r["ok"] for r in res), "total": len(res)}
json.dump(out, open(f"{D}/workspace-roles-wsc.json", "w"), indent=1, default=list)
print(json.dumps(report["preserved"]), "visible", n_exp, f"{out['passed']}/{out['total']}")
sys.exit(0 if out["passed"] == out["total"] and n_exp == 6 else 1)
