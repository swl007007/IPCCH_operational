"""Principal-positive access matrix on the cloud MLflow service (staging: through the loopback IAM proxy).

Principals are the real cloud identities (credentials read in-process from this task's secrets, never printed):
the temporary migration admin, ``ipcch-reader``, ``ipcch-assistant`` (read-only) and ``ipcch-jobwriter``. The owner's
personal account is not used (the user performs their own login). Each row records expected vs observed status.

* job writer (first): create (or reuse) the acceptance experiment, create a run in it, log a metric, upload and read
  back an artifact through the proxied artifact route - 200; create a run in a copied experiment, create a user - 403.
* reader / assistant: search experiments and runs, read a copied run, download a copied artifact through the proxied
  artifact route (bytes must equal the frozen r1 manifest sha256) - 200; create an experiment / registered model /
  Gateway secret, a user, self-escalate to admin - 403; and the denied write/delete probes (create a run, tag a run,
  delete the experiment) target the acceptance-only experiment and run, never historical copied data.
* temporary admin: list users - 200 (skipped with ``--without-admin``, which never reads its secret).
Writes go only to the acceptance experiment ``cloud-acceptance-access-matrix`` (created by the job writer).

  python -m research_cloud.deploy.cloud_access --url http://127.0.0.1:8091 --artifact REL --artifact-sha256 SHA
      --copied-experiment ID --copied-run ID --out REPORT.json
"""
import argparse
import hashlib
import json
import sys
import time

import requests

from research_cloud.deploy import provision_secrets as ps
from research_cloud.deploy.mlflow_identities import cred

EXPERIMENT = "cloud-acceptance-access-matrix"


class Matrix:
    def __init__(self, url):
        self.url, self.rows = url, []

    def call(self, who, auth, method, path, expect, *, body=None, params=None, data=None, note=""):
        r = requests.request(method, self.url + path, json=body, params=params, data=data, auth=auth, timeout=300)
        self.rows.append({"principal": who, "method": method, "path": path, "expected": expect,
                          "observed": r.status_code, "ok": r.status_code == expect, "note": note})
        return r


def run(api, url, artifact, artifact_sha, exp_id, run_id, with_admin=True):
    m = Matrix(url)
    names = [("reader", "mlflow-reader"), ("assistant", "mlflow-assistant-credentials"), ("job", "mlflow-jobwriter")]
    ids = {k: cred(api, s) for k, s in ([("admin", "mlflow-temp-admin")] if with_admin else []) + names}
    if with_admin:      # after the temporary admin is removed, the matrix runs without it (no secret read)
        m.call("admin", ids["admin"], "GET", "/api/2.0/mlflow/users/list", 200)
    # the job writer first: the acceptance experiment/run are the targets of every denied write/delete probe below
    j = ids["job"]
    r = requests.get(url + "/api/2.0/mlflow/experiments/get-by-name", params={"experiment_name": EXPERIMENT}, auth=j, timeout=60)
    if r.status_code == 200:
        own = r.json()["experiment"]["experiment_id"]
        m.rows.append({"principal": "job", "method": "GET", "path": "/api/2.0/mlflow/experiments/get-by-name",
                       "expected": 200, "observed": 200, "ok": True, "note": "acceptance experiment exists (rerun)"})
    else:
        r = m.call("job", j, "POST", "/api/2.0/mlflow/experiments/create", 200, body={"name": EXPERIMENT})
        own = r.json()["experiment_id"]
    r = m.call("job", j, "POST", "/api/2.0/mlflow/runs/create", 200,
               body={"experiment_id": own, "run_name": f"access-matrix-{time.strftime('%Y%m%dT%H%M%S')}"})
    new_run = r.json()["run"]["info"]
    m.call("job", j, "POST", "/api/2.0/mlflow/runs/log-metric", 200,
           body={"run_id": new_run["run_id"], "key": "acceptance", "value": 1.0, "timestamp": int(time.time() * 1000)})
    payload = b"cloud access matrix artifact\n"
    path = new_run["artifact_uri"].split("mlflow-artifacts:/", 1)[-1].lstrip("/") + "/probe.txt"
    m.call("job", j, "PUT", f"/api/2.0/mlflow-artifacts/artifacts/{path}", 200, data=payload, note="proxied upload")
    r = m.call("job", j, "GET", f"/api/2.0/mlflow-artifacts/artifacts/{path}", 200, note="read back own artifact")
    m.rows[-1]["bytes_equal"] = r.content == payload
    m.rows[-1]["ok"] &= m.rows[-1]["bytes_equal"]
    m.call("job", j, "POST", "/api/2.0/mlflow/runs/create", 403, body={"experiment_id": exp_id},
           note="copied experiment (no write grant)")
    m.call("job", j, "POST", "/api/2.0/mlflow/users/create", 403, body={"username": "denied-job", "password": "p" * 16})
    for who in ("reader", "assistant"):
        a = ids[who]
        r = m.call(who, a, "GET", "/api/2.0/mlflow/experiments/search", 200, params={"max_results": 100})
        m.rows[-1]["experiments_visible"] = len(r.json().get("experiments", [])) if r.ok else None
        m.call(who, a, "POST", "/api/2.0/mlflow/runs/search", 200, body={"experiment_ids": [exp_id], "max_results": 5})
        m.call(who, a, "GET", "/api/2.0/mlflow/runs/get", 200, params={"run_id": run_id})
        r = m.call(who, a, "GET", f"/api/2.0/mlflow-artifacts/artifacts/{artifact}", 200, note="copied artifact")
        m.rows[-1]["sha256_equal_r1"] = r.ok and hashlib.sha256(r.content).hexdigest() == artifact_sha
        m.rows[-1]["ok"] &= m.rows[-1]["sha256_equal_r1"]
        m.call(who, a, "POST", "/api/2.0/mlflow/experiments/create", 403, body={"name": f"denied-{who}-{time.time():.0f}"})
        # denied write/delete probes target the acceptance-only experiment and run (same copied-role READ policy)
        m.call(who, a, "POST", "/api/2.0/mlflow/runs/create", 403, body={"experiment_id": own}, note="acceptance experiment")
        m.call(who, a, "POST", "/api/2.0/mlflow/runs/set-tag", 403, body={"run_id": new_run["run_id"], "key": "x", "value": "y"},
               note="acceptance run")
        m.call(who, a, "POST", "/api/2.0/mlflow/experiments/delete", 403, body={"experiment_id": own}, note="acceptance experiment")
        m.call(who, a, "POST", "/api/2.0/mlflow/registered-models/create", 403, body={"name": f"denied-{who}"})
        m.call(who, a, "POST", "/api/3.0/mlflow/gateway/secrets/create", 403,
               body={"secret_name": f"denied-{who}", "secret_value": {"api_key": "x"}, "provider": "openai"})
        m.call(who, a, "POST", "/api/2.0/mlflow/users/create", 403, body={"username": f"denied-{who}", "password": "p" * 16})
        m.call(who, a, "PATCH", "/api/2.0/mlflow/users/update-admin", 403, body={"username": a[0], "is_admin": True})
    return m.rows, {"acceptance_experiment": own, "acceptance_run": new_run["run_id"], "artifact_path": path}


def main(argv=None, api=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--artifact-sha256", required=True)
    ap.add_argument("--copied-experiment", required=True)
    ap.add_argument("--copied-run", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--without-admin", action="store_true", help="post-removal: never reads mlflow-temp-admin")
    args = ap.parse_args(argv)
    rows, created = run(api or ps.Api(), args.url.rstrip("/"), args.artifact, args.artifact_sha256,
                        args.copied_experiment, args.copied_run, with_admin=not args.without_admin)
    report = {"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "url": args.url,
              "transport": "loopback IAM proxy (deploy.iam_proxy)" if args.url.startswith("http://127.0.0.1") else "direct HTTPS",
              "rows": rows, "passed": sum(r["ok"] for r in rows), "total": len(rows), **created}
    with open(args.out, "w") as f:
        f.write(ps.scrub(json.dumps(report, indent=1)))
    for r in rows:
        print(f"{'ok ' if r['ok'] else 'BAD'} {r['principal']:9} {r['method']:5} {r['path']} {r['expected']} -> {r['observed']}")
    print(f"{report['passed']}/{report['total']}")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
