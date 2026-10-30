"""Bounded job-log verification of the three CH formal CustomJobs (task 10-28; run only under the released final packet).

For each operation, the job id is the poller's terminal record ``ledger/vertex/<op>/final.json`` (state SUCCEEDED, the
bound name equal to the submit receipt); its run id is the harvest receipt's. ONE Cloud Logging read per job, filtered to
exactly that job (the task 10-27 diagnostic command): ``gcloud logging read 'resource.type="ml_job" AND
resource.labels.job_id="<id>"' --project=food-crisis-modeling-enso --limit=2000 --format=json --order=asc``.
Checks: every entry carries that job id; fewer than 2000 entries (not truncated); no failure marker (a replica non-zero
exit, "Job failed", a Python traceback, a worker JSON line with an "error" key); the worker's MLflow "View run" line names
the run id of the harvest receipt (the entire /runs/<segment> of each such line must be exactly the 32-lowercase-hex run id). The last service message is recorded verbatim. Receipts: OUT/logs-hHH.json (raw) and
OUT/logs-check.json.

  PYTHONDONTWRITEBYTECODE=1 python3 -B job_logs.py --out NEW_DIR
"""
import argparse, json, os, re, subprocess, sys

W = "/home/swl007007/projects/food-crisis-research"
D = f"{W}/.trellis/tasks/10-28-ipcch-ch-validity-refits/research/cp4"
PROJECT, LIMIT = "food-crisis-modeling-enso", 2000


def text(e):
    return e.get("textPayload") or json.dumps(e.get("jsonPayload") or {})


def check(h, entries, job_id, run_id):
    worker = [text(e) for e in entries if e["resource"]["labels"].get("task_name") != "service"]
    service = [text(e) for e in entries if e["resource"]["labels"].get("task_name") == "service"]
    def worker_error(t):
        try:
            return isinstance(json.loads(t), dict) and "error" in json.loads(t)
        except ValueError:
            return False
    checks = {"filtered_to_job": all(e["resource"]["labels"].get("job_id") == job_id for e in entries) and bool(entries),
              "not_truncated": len(entries) < LIMIT,
              "no_nonzero_exit": not any("non-zero status" in t for t in service),
              "no_job_failed": not any(t.strip().startswith("Job failed") for t in service),
              "no_traceback": not any("Traceback (most recent call last)" in t for t in worker + service),
              "no_worker_error_json": not any(worker_error(t) for t in worker),
              # the ENTIRE /runs/<segment> path segment of each MLflow "View run" line (up to /, ?, #, whitespace or a quote):
              # at least one, and every segment is exactly the harvested 32-lowercase-hex run id (no extra suffix)
              "run_line": bool(runs := [m for t in worker if "View run" in t for m in re.findall(r"/runs/([^/?#\s\"']+)", t)])
                          and all(re.fullmatch(r"[0-9a-f]{32}", m) and m == run_id for m in runs)}
    return {"horizon": h, "job_id": job_id, "run_id": run_id, "entries": len(entries), "worker_entries": len(worker),
            "last_service_message": service[-1] if service else None, "checks": checks, "ok": all(checks.values())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out)
    res = {}
    for h in ("00", "06", "12"):
        op = f"ipcch-ch-validity-r1-formal-h{h}"
        final = json.load(open(f"{W}/ledger/vertex/{op}/final.json"))
        bound = (json.load(open(f"{W}/ledger/vertex/{op}/submit.json")).get("body") or {}).get("name")
        harvest = json.load(open(f"{D}/06-harvest-h{h}.json"))
        if final.get("state") != "JOB_STATE_SUCCEEDED" or final.get("name") != bound or not harvest.get("ok") or harvest["job"] != bound:
            res[h] = {"ok": False, "error": "job not SUCCEEDED/bound or harvest not ok; no log read"}
            continue
        job_id = bound.rsplit("/", 1)[1]
        raw = os.path.join(a.out, f"logs-h{h}.json")
        q = f'resource.type="ml_job" AND resource.labels.job_id="{job_id}"'
        with open(raw, "w") as f:
            r = subprocess.run(["gcloud", "logging", "read", q, f"--project={PROJECT}", f"--limit={LIMIT}", "--format=json", "--order=asc"],
                               stdout=f, stderr=subprocess.PIPE, text=True)
        if r.returncode:
            res[h] = {"ok": False, "rc": r.returncode, "stderr": r.stderr[-1500:]}
            continue
        res[h] = check(h, json.load(open(raw)), job_id, harvest["run_id"])
    out = {"kind": "bounded job-log verification", "reads": sum(1 for h in res.values() if "entries" in h), "horizons": res,
           "ok": len(res) == 3 and all(v.get("ok") for v in res.values())}
    json.dump(out, open(os.path.join(a.out, "logs-check.json"), "w"), indent=1)
    print(json.dumps({h: {k: v.get(k) for k in ("ok", "entries", "last_service_message")} for h, v in res.items()}, indent=1))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
