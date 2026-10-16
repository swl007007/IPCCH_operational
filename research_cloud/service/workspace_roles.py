"""Workspace-mode role layout for the IPCCH service, applied through the admin REST API (idempotent).

Why: with workspaces disabled, MLflow 3.17 lets any authenticated user create experiments, registered models and
Gateway secrets/definitions/endpoints (creation is only vetoed by an explicit DENY, and a wildcard DENY also blocks
reads). With workspaces enabled, creation requires a workspace-wide USE grant, while a role's READ on a type's
wildcard confers reads. That is the native way to keep invited readers and the assistant read-only.

What changes (explicit; everything else is copied verbatim and compared before/after):
* every existing user, role, role permission and assignment is kept unchanged;
* ``ipcch-readers`` (workspace ``default``): READ on experiment/registered_model/prompt ``*``. Assigned to every
  non-admin user that holds no workspace-wide grant, preserving the read access they had through
  ``default_permission = READ``; what they lose is creating new top-level resources;
* ``ipcch-job-writers``: workspace USE (create experiments and write runs in experiments they create) plus EDIT on
  each listed existing experiment the training jobs write to. Assigned only to the named job identities.

  python -m research_cloud.service.workspace_roles --url URL --job-user NAME [--job-user ...]
      [--job-experiment ID ...] --report REPORT.json      (admin password from MLFLOW_AUTH_ADMIN_PASSWORD)
"""
import argparse
import json
import os

import requests

READ_TYPES = ("experiment", "registered_model", "prompt")
WORKSPACE = "default"


class Admin:
    def __init__(self, url, password, username="admin"):
        self.url, self.auth = url.rstrip("/"), (username, password)

    def __call__(self, method, path, body=None, params=None):
        r = requests.request(method, self.url + path, json=body, params=params, auth=self.auth, timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"{method} {path}: {r.status_code} {r.text[:200]}")
        return r.json()


def grants(api):
    """{username: sorted [(role, resource_type, pattern, permission)]} from the live auth store."""
    roles = {}
    for role in api("GET", "/api/3.0/mlflow/roles/list", params={"workspace": WORKSPACE}).get("roles", []):
        perms = api("GET", "/api/3.0/mlflow/roles/permissions/list", params={"role_id": role["id"]}).get("role_permissions", [])
        roles[role["id"]] = (role["name"], [(p["resource_type"], p["resource_pattern"], p["permission"]) for p in perms])
    out = {}
    for user in api("GET", "/api/2.0/mlflow/users/list").get("users", []):
        rows = []
        for role in api("GET", "/api/3.0/mlflow/users/roles/list", params={"username": user["username"]}).get("roles", []):
            name, perms = roles.get(role["id"], (role.get("name"), []))
            rows += [(name, *p) for p in perms]
        out[user["username"]] = {"is_admin": user.get("is_admin", False), "grants": sorted(rows)}
    return out


def ensure_role(api, name, permissions):
    existing = {r["name"]: r for r in api("GET", "/api/3.0/mlflow/roles/list", params={"workspace": WORKSPACE}).get("roles", [])}
    role = existing.get(name) or api("POST", "/api/3.0/mlflow/roles/create", {"name": name, "workspace": WORKSPACE})["role"]
    have = {(p["resource_type"], p["resource_pattern"], p["permission"])
            for p in api("GET", "/api/3.0/mlflow/roles/permissions/list", params={"role_id": role["id"]}).get("role_permissions", [])}
    for rt, pattern, perm in permissions:
        if (rt, pattern, perm) not in have:
            api("POST", "/api/3.0/mlflow/roles/permissions/add",
                {"role_id": role["id"], "resource_type": rt, "resource_pattern": pattern, "permission": perm})
    return role["id"]


def assign(api, username, role_id):
    held = {r["id"] for r in api("GET", "/api/3.0/mlflow/users/roles/list", params={"username": username}).get("roles", [])}
    if role_id not in held:
        api("POST", "/api/3.0/mlflow/roles/assign", {"username": username, "role_id": role_id})


def apply(api, job_users, job_experiments):
    before = grants(api)
    readers = ensure_role(api, "ipcch-readers", [(t, "*", "READ") for t in READ_TYPES])
    writers = ensure_role(api, "ipcch-job-writers", [("workspace", "*", "USE")]
                          + [("experiment", str(e), "EDIT") for e in job_experiments])
    for name, info in before.items():
        if info["is_admin"] or name in job_users:
            continue
        if not any(g[1] == "workspace" for g in info["grants"]):
            assign(api, name, readers)
    for name in job_users:
        assign(api, name, writers)
    after = grants(api)
    diff = {}
    for name in sorted(set(before) | set(after)):
        b, a = set(map(tuple, before.get(name, {}).get("grants", []))), set(map(tuple, after.get(name, {}).get("grants", [])))
        diff[name] = {"copied_unchanged": sorted(b & a), "added": sorted(a - b), "removed": sorted(b - a)}
    if any(d["removed"] for d in diff.values()):
        raise RuntimeError("a copied grant disappeared")
    return {"before": before, "after": after, "diff": diff}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--job-user", action="append", default=[])
    ap.add_argument("--job-experiment", action="append", default=[])
    ap.add_argument("--report", required=True)
    ap.add_argument("--redact-usernames", action="store_true", help="replace usernames by stable labels in the report")
    args = ap.parse_args()
    report = apply(Admin(args.url, os.environ["MLFLOW_AUTH_ADMIN_PASSWORD"]), args.job_user, args.job_experiment)
    if args.redact_usernames:
        labels = {n: f"user-{i}" for i, n in enumerate(sorted(report["before"] | report["after"]), 1)}
        report = {k: {labels[n]: v for n, v in report[k].items()} for k in report}
    json.dump(report, open(args.report, "w"), indent=1, default=list)
    print(json.dumps({n: {k: len(v) for k, v in d.items()} for n, d in report["diff"].items()}))


if __name__ == "__main__":
    main()
