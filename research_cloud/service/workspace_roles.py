"""Workspace-mode role layout for the IPCCH service, applied through the admin REST API (idempotent).

Why: with workspaces disabled, MLflow 3.17 lets any authenticated user create experiments, registered models and
Gateway secrets/definitions/endpoints (creation is only vetoed by an explicit DENY, and a wildcard DENY also blocks
reads). With workspaces enabled, creation requires a workspace-wide USE grant, while a role's READ on a type's
wildcard confers reads. That is the native way to keep invited readers and the assistant read-only.

Precondition (fail-closed, before any change): managed roles hold exactly their contract; ordinary readers and the
service assistant identity are non-admin and hold nothing beyond READ (the assistant: plus Gateway endpoint USE);
job identities exist and are non-admin. Conflicts are reported; nothing is revoked and no exception is invented.

What changes (explicit; every copied user, role, permission row and assignment is snapshotted by key and must be
unchanged afterwards):
* every existing user, role, role permission and assignment is kept unchanged;
* ``ipcch-readers`` (workspace ``default``): READ on experiment/registered_model/prompt ``*``. Assigned to every
  non-admin, non-job user (the precondition guarantees they hold nothing beyond READ), preserving the read access they had through
  ``default_permission = READ``; what they lose is creating new top-level resources;
* ``ipcch-job-writers``: workspace USE (create experiments and write runs in experiments they create) plus EDIT on
  each listed existing experiment the training jobs write to. Assigned only to the named job identities.

  python -m research_cloud.service.workspace_roles --url URL --job-user NAME [--job-user ...]
      [--job-experiment ID ...] [--assistant-user NAME] --report REPORT.json [--redact-usernames]
      (admin password from MLFLOW_AUTH_ADMIN_PASSWORD; roles are read in workspace "default" only)
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


def snapshot(api):
    """Keyed auth snapshot: every user (admin flag) with every assigned role (id, name, workspace, permission rows),
    including roles without permissions; plus every role in the workspace with its rows and assignees."""
    roles = {}
    for role in api("GET", "/api/3.0/mlflow/roles/list", params={"workspace": WORKSPACE}).get("roles", []):
        perms = api("GET", "/api/3.0/mlflow/roles/permissions/list", params={"role_id": role["id"]}).get("role_permissions", [])
        roles[role["id"]] = {"name": role["name"], "workspace": role.get("workspace"), "assignees": [],
                             "permissions": sorted((p["resource_type"], p["resource_pattern"], p["permission"]) for p in perms)}
    users = {}
    for user in api("GET", "/api/2.0/mlflow/users/list").get("users", []):
        held = api("GET", "/api/3.0/mlflow/users/roles/list", params={"username": user["username"]}).get("roles", [])
        users[user["username"]] = {"is_admin": bool(user.get("is_admin")), "role_ids": sorted(r["id"] for r in held)}
        for r in held:
            if r["id"] in roles:
                roles[r["id"]]["assignees"].append(user["username"])
    return {"users": users, "roles": roles}


def effective(snap, username):
    return sorted({tuple(p) for rid in snap["users"][username]["role_ids"] for p in snap["roles"].get(rid, {}).get("permissions", [])})


def conflicts(snap, job_users, assistant_user, job_experiments):
    """Fail-closed precondition: the copied store must already fit the intended contract before anything is added.
    Nothing is revoked and no exception is invented; every conflict is reported."""
    out = []
    intended = {"ipcch-readers": {(t, "*", "READ") for t in READ_TYPES},
                "ipcch-job-writers": {("workspace", "*", "USE")} | {("experiment", str(e), "EDIT") for e in job_experiments}}
    for rid, role in snap["roles"].items():
        if role["name"] in intended and set(map(tuple, role["permissions"])) - intended[role["name"]]:
            out.append(f"managed role {role['name']} holds grants outside its contract: "
                       f"{sorted(set(map(tuple, role['permissions'])) - intended[role['name']])}")
        if role["name"] == "ipcch-job-writers" and set(role["assignees"]) - set(job_users):
            out.append(f"ipcch-job-writers is assigned to users outside the job identities ({len(set(role['assignees']) - set(job_users))})")
    for name in job_users:
        if name not in snap["users"]:
            out.append("a named job identity does not exist")
        elif snap["users"][name]["is_admin"]:
            out.append("a named job identity is an administrator")
    if assistant_user is not None and assistant_user in job_users:
        out.append("the service assistant identity is also declared a job identity; it must stay read-only")
    if assistant_user is not None:
        if assistant_user not in snap["users"]:
            out.append("the service assistant identity does not exist")
        elif snap["users"][assistant_user]["is_admin"]:
            out.append("the service assistant identity is an administrator")
    for name, info in snap["users"].items():
        if info["is_admin"] or name in job_users:
            continue
        allowed_use = {("gateway_endpoint", "USE")} if name == assistant_user else set()
        for rt, pattern, perm in effective(snap, name):
            if perm == "READ" or (rt, perm) in allowed_use:
                continue
            who = "the service assistant identity" if name == assistant_user else "an ordinary reader"
            out.append(f"{who} holds {perm} on {rt}:{pattern}; read-only contract would not hold")
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


def apply(api, job_users, job_experiments, assistant_user=None):
    before = snapshot(api)
    problems = conflicts(before, job_users, assistant_user, job_experiments)
    if problems:
        raise RuntimeError("workspace role precondition failed (no change made): " + "; ".join(problems))
    readers = ensure_role(api, "ipcch-readers", [(t, "*", "READ") for t in READ_TYPES])
    writers = ensure_role(api, "ipcch-job-writers", [("workspace", "*", "USE")]
                          + [("experiment", str(e), "EDIT") for e in job_experiments])
    for name, info in before["users"].items():   # the precondition already refused any non-READ reader grant
        if not info["is_admin"] and name not in job_users:
            assign(api, name, readers)
    for name in job_users:
        assign(api, name, writers)
    after = snapshot(api)
    preserved = {
        "users": all(n in after["users"] and after["users"][n]["is_admin"] == u["is_admin"]
                     and set(u["role_ids"]) <= set(after["users"][n]["role_ids"]) for n, u in before["users"].items()),
        "roles": all(rid in after["roles"] and after["roles"][rid]["name"] == r["name"]
                     and after["roles"][rid]["permissions"] == r["permissions"]
                     and set(r["assignees"]) <= set(after["roles"][rid]["assignees"])
                     for rid, r in before["roles"].items() if r["name"] not in ("ipcch-readers", "ipcch-job-writers")),
    }
    if not all(preserved.values()):
        raise RuntimeError(f"a copied user, role, role permission or assignment changed: {preserved}")
    added = {n: {"role_ids": sorted(set(after["users"][n]["role_ids"]) - set(before["users"].get(n, {}).get("role_ids", []))),
                 "effective_added": sorted(set(effective(after, n)) - set(effective(before, n)) if n in before["users"]
                                           else set(effective(after, n)))}
             for n in after["users"]}
    return {"before": before, "after": after, "preserved": preserved, "added": added,
            "scope": "users, workspace roles, role permission rows and assignments read through the admin REST API; "
                     "legacy per-resource tables are covered by the full-store copier's table comparison"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--job-user", action="append", default=[])
    ap.add_argument("--job-experiment", action="append", default=[])
    ap.add_argument("--assistant-user", help="the service's assistant identity (MLFLOW_TRACKING_USERNAME)")
    ap.add_argument("--report", required=True)
    ap.add_argument("--redact-usernames", action="store_true", help="replace usernames by stable labels in the report")
    args = ap.parse_args()
    report = apply(Admin(args.url, os.environ["MLFLOW_AUTH_ADMIN_PASSWORD"]), args.job_user, args.job_experiment,
                   args.assistant_user)
    if args.redact_usernames:
        report = redact(report)
    json.dump(report, open(args.report, "w"), indent=1, default=list)
    print(json.dumps({"preserved": report["preserved"], "added": report["added"]}, default=list))


def redact(report, labels=None):
    names = sorted(report["after"]["users"])
    labels = labels or {n: f"user-{i}" for i, n in enumerate(names, 1)}
    text = json.dumps(report, default=list)
    for n in sorted(labels, key=len, reverse=True):
        text = text.replace(json.dumps(n), json.dumps(labels[n]))
    return json.loads(text)


if __name__ == "__main__":
    main()
