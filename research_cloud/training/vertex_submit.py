"""Submit a prepared Vertex AI CustomJob / HyperparameterTuningJob spec and follow it to a terminal state.

The ledger operation must already be reserved (training pool). ``submit`` POSTs the spec to the regional endpoint
(project pinned, operator credentials with the target as quota project), attaches the returned job name to the
reservation and saves the response; ``poll`` reads the job until a terminal state (SUCCEEDED / FAILED / CANCELLED /
EXPIRED), recording each observed state on the ledger operation. The reservation is never released here: it stays
held until terminal status is observed and actual cost is settled separately from billing.

  python -m research_cloud.training.vertex_submit submit --spec SPEC.json --kind custom|hpt --operation ID --out DIR
  python -m research_cloud.training.vertex_submit poll --job NAME --operation ID --out DIR [--every 30]
"""
import argparse
import json
import os
import subprocess
import sys
import time

import requests

PROJECT, REGION = "food-crisis-modeling-enso", "us-central1"
BASE = f"https://{REGION}-aiplatform.googleapis.com/v1"
TERMINAL = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}
LEDGER = "/home/swl007007/projects/food-crisis-research/ledger/spend.sqlite"


def headers():
    token = subprocess.run(["gcloud", "auth", "print-access-token", f"--billing-project={PROJECT}", "--quiet"],
                           capture_output=True, text=True, check=True).stdout.strip()
    return {"Authorization": f"Bearer {token}", "x-goog-user-project": PROJECT, "Content-Type": "application/json"}


def submit(spec_path, kind, operation, out):
    from research_cloud.cost import ledger as L
    conn = L.connect(LEDGER)
    status, resource, _ = L._get(conn, operation)
    pool = conn.execute("SELECT pool FROM operations WHERE operation_id = ?", (operation,)).fetchone()[0]
    if status != "reserved" or pool != "training" or resource:
        raise SystemExit(f"{operation}: not an open, unattached training reservation (status {status}, pool {pool})")
    collection = {"custom": "customJobs", "hpt": "hyperparameterTuningJobs"}[kind]
    body = json.load(open(spec_path))
    r = requests.post(f"{BASE}/projects/{PROJECT}/locations/{REGION}/{collection}", headers=headers(), json=body, timeout=120)
    json.dump({"status": r.status_code, "body": r.json() if r.content else None}, open(os.path.join(out, "submit.json"), "w"), indent=1)
    if r.status_code != 200:
        raise SystemExit(f"submit returned {r.status_code}")
    name = r.json()["name"]
    L.attach(conn, operation, name)
    print(json.dumps({"job": name, "state": r.json().get("state")}))
    return name


def poll(name, operation, out, every=30):
    from research_cloud.cost import ledger as L
    conn = L.connect(LEDGER)
    last = None
    while True:
        r = requests.get(f"{BASE}/{name}", headers=headers(), timeout=60)
        job = r.json()
        state = job.get("state")
        if state != last:
            L.observe(conn, operation, state, f"GET {name}")
            print(json.dumps({"time": time.strftime("%H:%M:%S"), "state": state}), flush=True)
            last = state
        if state in TERMINAL:
            json.dump(job, open(os.path.join(out, "final.json"), "w"), indent=1)
            return 0 if state == "JOB_STATE_SUCCEEDED" else 1
        time.sleep(every)


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("submit")
    s.add_argument("--spec", required=True)
    s.add_argument("--kind", choices=("custom", "hpt"), required=True)
    s.add_argument("--operation", required=True)
    s.add_argument("--out", required=True)
    p = sub.add_parser("poll")
    p.add_argument("--job", required=True)
    p.add_argument("--operation", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--every", type=int, default=30)
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    if args.cmd == "submit":
        submit(args.spec, args.kind, args.operation, args.out)
        return 0
    return poll(args.job, args.operation, args.out, args.every)


if __name__ == "__main__":
    sys.exit(main())
