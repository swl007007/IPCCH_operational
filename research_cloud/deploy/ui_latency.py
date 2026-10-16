"""Warm, browser-shaped latency probe of the cloud MLflow UI's data calls (read-only; temporary admin credentials).

Each call is sent the way the bundled UI sends it (``/ajax-api``, exact service ``Origin``, ``Accept-Encoding: gzip``,
``runs/search`` with ``max_results`` 100, ``logged-models/search`` without ``max_results``), ``--repeat`` times in a
row after one discarded warm-up, and records per call: HTTP status, time to first byte (response headers), total time,
transferred and decoded bytes and the ``Content-Encoding``. Nothing is written to the service.

  python -m research_cloud.deploy.ui_latency --url URL --experiments 1 2 3 4 --run-id ID --repeat 3 --out REPORT.json
"""
import argparse
import json
import statistics
import sys
import time

import requests

from research_cloud.deploy import provision_secrets as ps
from research_cloud.deploy.mlflow_identities import cred


def calls(experiments, run_id):
    out = [("POST", "/ajax-api/2.0/mlflow/experiments/search", {"max_results": 25}, None)]
    for e in experiments:
        out += [("GET", "/ajax-api/2.0/mlflow/experiments/get", None, {"experiment_id": e}),
                ("POST", "/ajax-api/2.0/mlflow/runs/search", {"experiment_ids": [e], "max_results": 100,
                                                               "order_by": ["attributes.start_time DESC"]}, None),
                ("POST", "/ajax-api/2.0/mlflow/logged-models/search",
                 {"experiment_ids": [e], "order_by": [{"field_name": "creation_time", "ascending": False}]}, None),
                ("POST", "/ajax-api/2.0/mlflow/experiments/search-datasets", {"experiment_ids": [e]}, None)]
    out.append(("GET", "/ajax-api/2.0/mlflow/runs/get", None, {"run_id": run_id}))
    return out


def one(session, url, auth, method, path, body, params):
    t0 = time.perf_counter()
    r = session.request(method, url + path, json=body, params=params, auth=auth, stream=True, timeout=300,
                        headers={"Origin": url, "Accept-Encoding": "gzip"})
    ttfb = time.perf_counter() - t0
    raw = r.raw.read(decode_content=False)
    total = time.perf_counter() - t0
    return {"status": r.status_code, "ttfb_s": round(ttfb, 3), "total_s": round(total, 3), "wire_bytes": len(raw),
            "content_encoding": r.headers.get("Content-Encoding"), "content_type": r.headers.get("Content-Type")}


def main(argv=None, api=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--experiments", nargs="+", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    auth = cred(api or ps.Api(), "mlflow-temp-admin")
    session = requests.Session()
    url = args.url.rstrip("/")
    rows = []
    for method, path, body, params in calls(args.experiments, args.run_id):
        one(session, url, auth, method, path, body, params)                       # warm-up, discarded
        samples = [one(session, url, auth, method, path, body, params) for _ in range(args.repeat)]
        rows.append({"method": method, "path": path, "experiment": (body or params or {}).get("experiment_ids",
                     [(params or {}).get("experiment_id")])[0] if (body or params) else None, "samples": samples,
                     "median_ttfb_s": statistics.median(s["ttfb_s"] for s in samples),
                     "median_total_s": statistics.median(s["total_s"] for s in samples)})
        last = samples[-1]
        print(f"{method:4} {path:48} exp={rows[-1]['experiment']!s:4} status={last['status']} "
              f"ttfb~{rows[-1]['median_ttfb_s']:.2f}s total~{rows[-1]['median_total_s']:.2f}s "
              f"wire={last['wire_bytes']} enc={last['content_encoding']}", flush=True)
    with open(args.out, "w") as f:
        json.dump({"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "url": url, "rows": rows}, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
