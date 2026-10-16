"""Submit a prepared Vertex AI CustomJob / HyperparameterTuningJob spec under a held ledger reservation, and follow it.

Admission is idempotent and fail-closed (the cost/concurrency contract, not a general SDK):

* ``submit``: the spec must stay within its reservation (machine, one replica, timeout, boot disk, serial trial
  count, ``disableRetries``). Before any provider call the reservation is **claimed** atomically (ledger ``attach`` of a marker
  ``claim:<id>:<spec sha256>``; a repeated or concurrent submit for the same operation is refused there). The claim is
  written to ``claim.json``, the request carries it as the job label ``ipcch-claim``, then the spec is POSTed once.
  HTTP 200: the returned job name is **bound** to the reservation (ledger ``bind``). Anything else - a non-200, a
  timeout, a lost acknowledgement - leaves the claim held with the outcome recorded; nothing is retried.
* ``reconcile``: for a held claim, list the jobs labelled with it. Exactly one: bind it. More than one: refuse. None:
  the claim stays held - a list result (eventually consistent) cannot prove the job was never created, so the
  reservation is never released from here.
* ``poll``: read the bound job until a terminal state; every read must be HTTP 200 and return exactly the bound name
  before its state is recorded on the ledger. The reservation is never released here.

  python -m research_cloud.training.vertex_submit submit --spec SPEC.json --kind custom|hpt --operation ID --out DIR
  python -m research_cloud.training.vertex_submit reconcile --kind custom|hpt --operation ID --out DIR
  python -m research_cloud.training.vertex_submit poll --kind custom|hpt --operation ID --out DIR [--every 30]
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid

import requests

ENTRY = "/usr/local/bin/train-entry"   # the only command allowed before the per-trial cap

PROJECT, REGION = "food-crisis-modeling-enso", "us-central1"
BASE = f"https://{REGION}-aiplatform.googleapis.com/v1"
PARENT = f"projects/{PROJECT}/locations/{REGION}"
COLLECTION = {"custom": "customJobs", "hpt": "hyperparameterTuningJobs"}
TERMINAL = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}
LEDGER = "/home/swl007007/projects/food-crisis-research/ledger/spend.sqlite"


def headers():
    token = subprocess.run(["gcloud", "auth", "print-access-token", f"--billing-project={PROJECT}", "--quiet"],
                           capture_output=True, text=True, check=True).stdout.strip()
    return {"Authorization": f"Bearer {token}", "x-goog-user-project": PROJECT, "Content-Type": "application/json"}


def save(out, name, value):
    with open(os.path.join(out, name), "w") as f:
        json.dump(value, f, indent=1)


def current(conn, operation):
    from research_cloud.cost import ledger as L
    status, resource, state = L._get(conn, operation)
    pool = conn.execute("SELECT pool FROM operations WHERE operation_id = ?", (operation,)).fetchone()[0]
    return status, resource, state, pool


def reservation_detail(conn, operation):
    raw = conn.execute("SELECT detail FROM operations WHERE operation_id = ?", (operation,)).fetchone()[0]
    detail = json.loads(raw) if raw else {}
    return json.loads(detail) if isinstance(detail, str) else detail       # stored as a JSON-encoded string


def within_reservation(body, kind, detail):
    """The spec may not ask for more than was reserved: machine, one replica, per-trial timeout, boot disk, trial
    count (HPT serial), and no automatic retries. Returns the list of mismatches."""
    job = body["trialJobSpec"] if kind == "hpt" else body["jobSpec"]
    pools = job.get("workerPoolSpecs", [])
    out = []
    if len(pools) != 1 or str(pools[0].get("replicaCount")) != "1":
        out.append("exactly one worker pool with one replica")
    elif pools[0]["machineSpec"].get("machineType") != detail.get("machine") or pools[0]["machineSpec"].get("acceleratorCount"):
        out.append(f"machine {pools[0]['machineSpec']} is not the reserved {detail.get('machine')}")
    elif int((pools[0].get("diskSpec") or {}).get("bootDiskSizeGb", 100)) > int(detail.get("boot_disk_gib", 0)):
        out.append("boot disk larger than reserved")
    sched = job.get("scheduling", {})
    if kind == "hpt":
        # the parent deadline covers the serial study; each trial is capped by the timeout wrapper at its command prefix
        want = int(body.get("maxTrialCount", 1)) * (int(detail.get("timeout_s", -1)) + int(detail.get("overhead_s", -1)))
        if sched.get("timeout") != f"{want}s":
            out.append(f"HPT timeout {sched.get('timeout')} is not trials x (timeout + overhead) = {want}s")
        from research_cloud.training.cloud_job import cap_command
        cap = cap_command(int(detail.get("timeout_s", -1)))
        cmd = pools[0].get("containerSpec", {}).get("command", []) if pools else []
        rest = cmd[1:] if cmd[:1] == [ENTRY] else cmd                # optional root-start entry, then cap, then python
        if rest[:len(cap) + 1] != cap + ["python"]:
            out.append(f"HPT trial command must start [{ENTRY}] {' '.join(cap)} python (the per-trial cap)")
    elif sched.get("timeout") != f"{int(detail.get('timeout_s', -1))}s":
        out.append(f"timeout {sched.get('timeout')} is not the reserved {detail.get('timeout_s')}s")
    if sched.get("disableRetries") is not True:
        out.append("disableRetries must be true")
    trials = int(body.get("maxTrialCount", 1)) if kind == "hpt" else 1
    if trials > int(detail.get("trials", 0)) or (kind == "hpt" and int(body.get("parallelTrialCount", 0)) != 1):
        out.append(f"{trials} trials (parallel {body.get('parallelTrialCount')}) exceed the reserved {detail.get('trials')} serial")
    return out


def submit(conn, spec_path, kind, operation, out):
    from research_cloud.cost import ledger as L
    status, resource, _, pool = current(conn, operation)
    if status != "reserved" or pool != "training" or resource:
        raise SystemExit(f"{operation}: not an open, unclaimed training reservation (status {status}, resource {resource})")
    raw = open(spec_path, "rb").read()
    spec_sha = hashlib.sha256(raw).hexdigest()
    problems = within_reservation(json.loads(raw), kind, reservation_detail(conn, operation))
    if problems:
        raise SystemExit(f"{operation}: spec exceeds its reservation: {problems}")
    claim_id = uuid.uuid4().hex[:20]
    marker = f"claim:{claim_id}:{spec_sha}"
    L.attach(conn, operation, marker)                 # atomic: a second submit for this operation fails here
    body = json.loads(raw)
    body["labels"] = {**body.get("labels", {}), "ipcch-claim": claim_id}
    save(out, "claim.json", {"operation": operation, "claim": marker, "spec": os.path.abspath(spec_path),
                             "spec_sha256": spec_sha, "time": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    try:
        r = requests.post(f"{BASE}/{PARENT}/{COLLECTION[kind]}", headers=headers(), json=body, timeout=120)
    except Exception as e:                            # noqa: BLE001 - ambiguous: the job may or may not exist
        save(out, "submit.json", {"outcome": "ambiguous", "error": type(e).__name__})
        print(json.dumps({"outcome": "ambiguous (claim held; run reconcile)", "claim": claim_id}))
        return 2
    save(out, "submit.json", {"status": r.status_code, "body": r.json() if r.content else None})
    if r.status_code != 200:
        print(json.dumps({"outcome": f"HTTP {r.status_code} (claim held; run reconcile)", "claim": claim_id}))
        return 1
    L.bind(conn, operation, marker, r.json()["name"])
    print(json.dumps({"job": r.json()["name"], "state": r.json().get("state"), "claim": claim_id}))
    return 0


def reconcile(conn, kind, operation, out):
    from research_cloud.cost import ledger as L
    status, marker, _, _ = current(conn, operation)
    if status != "reserved" or not marker or not marker.startswith("claim:"):
        raise SystemExit(f"{operation}: no held claim to reconcile (status {status}, resource {marker})")
    claim_id = marker.split(":")[1]
    query = f'labels.ipcch-claim="{claim_id}"'
    r = requests.get(f"{BASE}/{PARENT}/{COLLECTION[kind]}", headers=headers(), params={"filter": query}, timeout=60)
    if r.status_code != 200:
        raise SystemExit(f"lookup returned {r.status_code}; claim stays held")
    jobs = r.json().get(COLLECTION[kind], [])
    lookup = {"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "collection": COLLECTION[kind], "filter": query,
              "found": [j["name"] for j in jobs]}
    save(out, "reconcile.json", lookup)
    if len(jobs) == 1:
        L.bind(conn, operation, marker, jobs[0]["name"])
        print(json.dumps({"bound": jobs[0]["name"]}))
        return 0
    if len(jobs) > 1:
        raise SystemExit(f"{len(jobs)} jobs carry claim {claim_id}; refusing")
    print(json.dumps({"not_found_yet": lookup, "claim": "held (no release from a list lookup)"}))
    return 1


def poll(conn, kind, operation, out, every=30, sleep=time.sleep):
    from research_cloud.cost import ledger as L
    status, name, _, _ = current(conn, operation)
    if status != "reserved" or not name or name.startswith("claim:"):
        raise SystemExit(f"{operation}: no bound job to poll (status {status}, resource {name})")
    if f"/{COLLECTION[kind]}/" not in name:
        raise SystemExit(f"{operation}: bound resource {name} is not a {COLLECTION[kind]} job")
    last = None
    while True:
        r = requests.get(f"{BASE}/{name}", headers=headers(), timeout=60)
        if r.status_code != 200:
            raise SystemExit(f"GET {name} returned {r.status_code}; nothing recorded")
        job = r.json()
        if job.get("name") != name:
            raise SystemExit(f"GET returned job {job.get('name')}, not the bound {name}; nothing recorded")
        state = job.get("state")
        if state != last:
            L.observe(conn, operation, state, f"GET {name}")
            print(json.dumps({"time": time.strftime("%H:%M:%S"), "state": state}), flush=True)
            last = state
        if state in TERMINAL:
            save(out, "final.json", job)
            return 0 if state == "JOB_STATE_SUCCEEDED" else 1
        sleep(every)


def main(argv=None, conn=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for cmd in ("submit", "reconcile", "poll"):
        p = sub.add_parser(cmd)
        p.add_argument("--kind", choices=tuple(COLLECTION), required=True)
        p.add_argument("--operation", required=True)
        p.add_argument("--out", required=True)
        if cmd == "submit":
            p.add_argument("--spec", required=True)
        if cmd == "poll":
            p.add_argument("--every", type=int, default=30)
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    if conn is None:
        from research_cloud.cost import ledger as L
        conn = L.connect(LEDGER)
    if args.cmd == "submit":
        return submit(conn, args.spec, args.kind, args.operation, args.out)
    if args.cmd == "reconcile":
        return reconcile(conn, args.kind, args.operation, args.out)
    return poll(conn, args.kind, args.operation, args.out, args.every)


if __name__ == "__main__":
    sys.exit(main())
