"""Staging access checks for the IAM-protected Cloud Run revision (no MLflow credentials needed).

The staging service runs with ``--no-allow-unauthenticated``: Cloud Run IAM admits only callers with ``run.invoker``.
To reach MLflow's own Basic-auth layer, the operator's Google identity token goes in ``X-Serverless-Authorization``
(Cloud Run then leaves ``Authorization`` to the container). The token comes from ``gcloud auth print-identity-token``
and is never printed or written. Checks (expected vs observed, with the origin of each refusal):

A. no identity token: refused by Cloud Run IAM (403, no MLflow ``WWW-Authenticate: Basic`` challenge);
B. identity token, no Basic credentials: content-free ``/health`` 200; every content route of the local rehearsal
   (tracking, registry, proxied artifacts incl. a real copied artifact, Gateway, assistant config, user creation)
   401 with MLflow's Basic challenge;
C. identity token, wrong Basic credentials (random user/password): 401;
D. the service's legacy ``*.a.run.app`` host (not in ``IPCCH_ALLOWED_HOSTS``) with the identity token: content routes
   refused by MLflow's host check; ``/health`` (content-free) and ``/version`` are exempt from that check in MLflow 3.17,
   and ``/version`` still needs Basic auth. Observed upstream: the proxied artifact routes (FastAPI artifact router)
   are outside the Flask host check, so on that host they get MLflow's Basic challenge (401) instead of 403.

Principal-positive rows (owner, reader, job writer, assistant) need MLflow identities and run separately.

  python -m research_cloud.deploy.staging_access --url URL --legacy-url URL --artifact REL --run-id ID --out REPORT.json
"""
import argparse
import json
import secrets
import subprocess
import sys
import time

import requests

CONTENT = ("/api/2.0/mlflow/experiments/search?max_results=5", "/api/2.0/mlflow/registered-models/search",
           "/api/2.0/mlflow-artifacts/artifacts", "/ajax-api/2.0/mlflow/gateway/endpoints/list",
           "/ajax-api/3.0/mlflow/assistant/config")


def identity_token():
    return subprocess.run(["gcloud", "auth", "print-identity-token", "--quiet"], capture_output=True, text=True,
                          check=True).stdout.strip()


class Checks:
    def __init__(self, token):
        self.token, self.results = token, []

    def call(self, row, base, method, path, expect, *, iam=True, auth=None, json_body=None, note=""):
        headers = {"X-Serverless-Authorization": f"Bearer {self.token}"} if iam else {}
        r = requests.request(method, base.rstrip("/") + path, headers=headers, auth=auth, json=json_body, timeout=120,
                             allow_redirects=False)
        challenge = r.headers.get("WWW-Authenticate", "")
        ok = r.status_code in (expect if isinstance(expect, tuple) else (expect,))
        self.results.append({"row": row, "method": method, "path": path.split("?")[0], "iam_token": iam,
                             "basic": "none" if auth is None else "wrong", "expected": expect,
                             "observed": r.status_code, "basic_challenge": challenge.lower().startswith("basic"),
                             "ok": ok, "note": note})
        return r


def run(url, legacy_url, artifact, run_id, token):
    c = Checks(token)
    c.call("A", url, "GET", "/health", 403, iam=False, note="Cloud Run IAM, no identity token")
    c.call("A", url, "GET", CONTENT[0], 403, iam=False, note="Cloud Run IAM, no identity token")
    c.call("B", url, "GET", "/health", 200, note="content-free health")
    for path in CONTENT:
        c.call("B", url, "GET", path, 401, note="content route without Basic credentials")
    c.call("B", url, "GET", f"/api/2.0/mlflow-artifacts/artifacts/{artifact}", 401, note="real copied artifact")
    c.call("B", url, "GET", f"/get-artifact?path={artifact.split('/artifacts/', 1)[-1]}&run_id={run_id}", 401,
           note="UI artifact route")
    c.call("B", url, "POST", "/gateway/mlflow/v1/chat/completions", 401,
           json_body={"model": "x", "messages": [{"role": "user", "content": "hi"}]}, note="Gateway")
    c.call("B", url, "POST", "/api/2.0/mlflow/users/create", 401,
           json_body={"username": "x", "password": "y" * 12}, note="user creation")
    wrong = (f"nobody-{secrets.token_hex(4)}", secrets.token_urlsafe(16))
    c.call("C", url, "GET", CONTENT[0], 401, auth=wrong, note="wrong Basic credentials")
    c.call("C", url, "GET", f"/api/2.0/mlflow-artifacts/artifacts/{artifact}", 401, auth=wrong,
           note="wrong Basic credentials, real artifact")
    c.call("B", url, "GET", "/version", 401, note="version is Basic-auth protected")
    # MLflow 3.17 exempts /health and /version from the host check (security_utils.HEALTH_ENDPOINTS); /version stays
    # behind Basic auth; every other route on a host outside the allowed list is refused by the host check
    c.call("D", legacy_url, "GET", "/health", 200, note="health is host-check exempt (pinned MLflow behaviour)")
    c.call("D", legacy_url, "GET", "/version", 401, note="host-check exempt, still Basic-auth protected")
    r = c.call("D", legacy_url, "GET", CONTENT[0], (400, 403), note="legacy host not in the allowed hosts")
    c.results[-1]["refused_by_mlflow_host_check"] = "host" in r.text.lower()
    # observed upstream property (MLflow 3.17): the host check is a Flask before_request hook, and the proxied
    # artifact routes are served by the FastAPI artifact router, outside it - they are reached on any host, and Basic
    # auth still refuses them (DNS-rebinding protection absent there; content authorization present)
    c.call("D", legacy_url, "GET", f"/api/2.0/mlflow-artifacts/artifacts/{artifact}", 401,
           note="UPSTREAM: artifact router outside the Flask host check; Basic auth still required")
    c.results[-1]["upstream_finding"] = "artifact router not host-checked"
    return c.results


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--legacy-url", required=True)
    ap.add_argument("--artifact", required=True, help="artifact path relative to the artifact root")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    results = run(args.url, args.legacy_url, args.artifact, args.run_id, identity_token())
    report = {"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "url": args.url, "legacy_url": args.legacy_url,
              "checks": len(results), "passed": sum(r["ok"] for r in results), "results": results}
    with open(args.out, "w") as f:
        json.dump(report, f, indent=1)
    for r in results:
        print(f"{r['row']} {'ok ' if r['ok'] else 'BAD'} {r['method']} {r['path']} expected {r['expected']} "
              f"observed {r['observed']} basic-challenge={r['basic_challenge']}")
    print(f"{report['passed']}/{report['checks']}")
    return 0 if report["passed"] == report["checks"] else 1


if __name__ == "__main__":
    sys.exit(main())
