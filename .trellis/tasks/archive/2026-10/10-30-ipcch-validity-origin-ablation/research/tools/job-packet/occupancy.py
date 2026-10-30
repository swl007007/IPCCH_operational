"""Read-only occupancy check before a released submission (task 10-30; task 10-28 script, task label changed): Vertex customJobs.list of active jobs with full
pagination; every active job is counted (vCPUs per machine type, every worker pool and replica). Exit 0 only if the
planned submissions keep this task at <= 2 active jobs and the region within 42 N1/E2 vCPUs.

  PYTHONDONTWRITEBYTECODE=1 $W/envs/mlflow-svc/bin/python -B occupancy.py --out RECEIPT.json --planned N
"""
import argparse, json, os, re, subprocess, sys, time
import requests

PROJECT, REGION, QUOTA, PER_JOB, TASK = "food-crisis-modeling-enso", "us-central1", 42, 16, "ipcch-validity-origin-ablation"
ACTIVE = ("JOB_STATE_QUEUED", "JOB_STATE_PENDING", "JOB_STATE_RUNNING", "JOB_STATE_CANCELLING", "JOB_STATE_UPDATING")


def vcpus(machine):
    m = re.fullmatch(r"(n1|e2)-(standard|highmem|highcpu)-(\d+)", machine or "")
    return int(m.group(3)) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--planned", type=int, required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise SystemExit(f"{a.out} exists")
    tok = subprocess.check_output(["gcloud", "auth", "print-access-token", f"--billing-project={PROJECT}", "--quiet"], text=True).strip()
    h = {"Authorization": f"Bearer {tok}", "x-goog-user-project": PROJECT}
    url = f"https://{REGION}-aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}/customJobs"
    params = {"filter": " OR ".join(f'state="{s}"' for s in ACTIVE), "pageSize": 100}
    pages, jobs = [], []
    for _ in range(5):
        r = requests.get(url, params=params, headers=h, timeout=60)
        pages.append({"status": r.status_code, "body": r.json() if r.status_code == 200 else r.text[:2000]})
        if r.status_code != 200:
            break
        jobs += r.json().get("customJobs", [])
        if not r.json().get("nextPageToken"):
            break
        params["pageToken"] = r.json()["nextPageToken"]
    complete = all(p["status"] == 200 for p in pages) and not (pages[-1]["body"] or {}).get("nextPageToken")
    rows, unknown = [], []
    for j in jobs:
        cpu = 0
        for wp in j.get("jobSpec", {}).get("workerPoolSpecs", []):
            v = vcpus(wp.get("machineSpec", {}).get("machineType"))
            if v is None:
                unknown.append(j["name"])
                continue
            cpu += v * int(wp.get("replicaCount", 1))
        rows.append({"name": j["name"], "display": j.get("displayName"), "state": j["state"], "vcpus": cpu, "task": (j.get("labels") or {}).get("task")})
    mine = sum(1 for r in rows if r["task"] == TASK)
    total = sum(r["vcpus"] for r in rows) + a.planned * PER_JOB
    ok = complete and not unknown and mine + a.planned <= 2 and total <= QUOTA
    rec = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "complete": complete, "active": rows, "unknown_machine": unknown,
           "task_active": mine, "planned": a.planned, "vcpus_after": total, "quota": QUOTA, "ok": ok, "pages": pages}
    json.dump(rec, open(a.out, "w"), indent=1)
    print(json.dumps({k: rec[k] for k in ("utc", "complete", "task_active", "planned", "vcpus_after", "ok")}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
