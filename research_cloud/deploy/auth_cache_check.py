"""Live check of the MLflow credential cache's invalidation on the cloud service (temporary admin; a throwaway user).

A throwaway non-admin user is created, its credential is warmed into the cache, and each change made through the admin
routes must take effect on the very next request (no TTL wait):
1. password change: the old password -> 401 immediately, the new one -> 200;
2. promotion to admin: an admin-only call (``users/list``) -> 200; demotion: the same call -> 403 immediately;
3. a READ write probe (create experiment) stays 403 throughout as a non-admin;
4. deletion: the warmed credential -> 401 immediately.
The throwaway user is deleted at the end (also on failure). No personal account or stored hash is touched.

  python -m research_cloud.deploy.auth_cache_check --url URL --out REPORT.json
"""
import argparse
import json
import secrets
import sys
import time

import requests

from research_cloud.deploy import provision_secrets as ps
from research_cloud.deploy.mlflow_identities import cred


def main(argv=None, api=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    url = args.url.rstrip("/")
    admin = cred(api or ps.Api(), "mlflow-temp-admin")
    user, pw1, pw2 = f"cache-probe-{secrets.token_hex(4)}", secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    ps.KNOWN.update({pw1, pw2})
    rows = []

    def call(step, method, path, auth, expect, body=None, params=None):
        r = requests.request(method, url + path, json=body, params=params, auth=auth, timeout=60)
        rows.append({"step": step, "method": method, "path": path, "expected": expect, "observed": r.status_code,
                     "ok": r.status_code == expect})
        return r

    try:
        call("create", "POST", "/api/2.0/mlflow/users/create", admin, 200, {"username": user, "password": pw1})
        for _ in range(3):
            call("warm", "GET", "/api/2.0/mlflow/users/current", (user, pw1), 200)
        call("read-write-denied", "POST", "/api/2.0/mlflow/experiments/create", (user, pw1), 403, {"name": f"denied-{user}"})
        call("password-change", "PATCH", "/api/2.0/mlflow/users/update-password", admin, 200, {"username": user, "password": pw2})
        call("old-password-immediately-denied", "GET", "/api/2.0/mlflow/users/current", (user, pw1), 401)
        call("new-password", "GET", "/api/2.0/mlflow/users/current", (user, pw2), 200)
        call("non-admin-users-list", "GET", "/api/2.0/mlflow/users/list", (user, pw2), 403)
        call("promote", "PATCH", "/api/2.0/mlflow/users/update-admin", admin, 200, {"username": user, "is_admin": True})
        call("admin-users-list", "GET", "/api/2.0/mlflow/users/list", (user, pw2), 200)
        call("demote", "PATCH", "/api/2.0/mlflow/users/update-admin", admin, 200, {"username": user, "is_admin": False})
        call("demoted-immediately-denied", "GET", "/api/2.0/mlflow/users/list", (user, pw2), 403)
        call("read-write-still-denied", "POST", "/api/2.0/mlflow/experiments/create", (user, pw2), 403, {"name": f"denied-{user}"})
        for _ in range(2):
            call("rewarm", "GET", "/api/2.0/mlflow/users/current", (user, pw2), 200)
        call("delete", "DELETE", "/api/2.0/mlflow/users/delete", admin, 200, {"username": user})
        call("deleted-immediately-denied", "GET", "/api/2.0/mlflow/users/current", (user, pw2), 401)
    finally:
        r = requests.get(url + "/api/2.0/mlflow/users/get", params={"username": user}, auth=admin, timeout=60)
        if r.status_code == 200:
            requests.delete(url + "/api/2.0/mlflow/users/delete", json={"username": user}, auth=admin, timeout=60)
    report = {"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "url": url, "probe_user": user, "rows": rows,
              "passed": sum(r["ok"] for r in rows), "total": len(rows)}
    with open(args.out, "w") as f:
        f.write(ps.scrub(json.dumps(report, indent=1)))
    for r in rows:
        print(f"{'ok ' if r['ok'] else 'BAD'} {r['step']:32} {r['method']:6} {r['path']} {r['expected']} -> {r['observed']}")
    print(f"{report['passed']}/{report['total']}")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
