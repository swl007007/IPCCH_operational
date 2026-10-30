"""Origin-ablation job packet step (ledger write; run only after release): reserve the job-phase platform line and the three FORMAL
CustomJobs of task 10-30 in the shared ledger, month 2026-10, exactly as ``reservations.json`` "platform" + "training"
(sha256 given at release). Prechecks all four first: none may exist, the released build line must exist, each pool's
committed + new must stay within its cap, and build + platform + training stay within the task cap. Adapted from the task
10-28 ``reserve_job.py`` (only these task constants differ). No earlier task line is required, reused or counted except
this task's own build line.

  cd $W/control-plane-origin-ablation && IPCCH_ORIGIN_JOB_RESERVE_CONFIRM=r1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. $W/envs/mlflow-svc/bin/python -B reserve_job.py --plan-sha256 SHA --out RECEIPT.json
"""
import argparse, hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = "/home/swl007007/projects/food-crisis-research/ledger/spend.sqlite"
TASK_TRAINING_MAX, TASK_PLATFORM_MAX, TASK_CAP = 5.73, 0.90, 7.00
BUILD_OP, PLATFORM_OP = "ipcch-origin-ablation-r1-build", "ipcch-origin-ablation-r1-platform"


def main():
    from research_cloud.cost import ledger as L
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--plan-sha256", required=True)
    ap.add_argument("--ledger", default=LEDGER)
    a = ap.parse_args()
    if os.environ.get("IPCCH_ORIGIN_JOB_RESERVE_CONFIRM") != "r1" or os.path.exists(a.out):
        raise SystemExit("needs IPCCH_ORIGIN_JOB_RESERVE_CONFIRM=r1 and a new receipt path")
    raw = open(os.path.join(HERE, "reservations.json"), "rb").read()
    if hashlib.sha256(raw).hexdigest() != a.plan_sha256:
        raise SystemExit("reservations.json differs from the released plan")
    plan = json.loads(raw)
    training, platform = plan["training"], plan["platform"]
    if len(training) != 3 or any(not e["operation"].startswith("ipcch-origin-ablation-r1-formal-h") for e in training) \
            or sum(e["usd"] for e in training) > TASK_TRAINING_MAX:
        raise SystemExit("the plan must hold exactly the three formal operations within the task training cap")
    if len(platform) != 1 or platform[0]["operation"] != PLATFORM_OP or platform[0]["usd"] > TASK_PLATFORM_MAX:
        raise SystemExit("the plan must hold exactly the job-phase platform line within its task cap")
    entries = platform + training
    conn = L.connect(a.ledger)
    before = L.summary(conn, plan["month"])
    build = conn.execute("SELECT reserved_usd FROM operations WHERE operation_id = ?", (BUILD_OP,)).fetchone()
    if not build:
        raise SystemExit(f"{BUILD_OP} is not in the ledger; nothing reserved")
    if build[0] + sum(e["usd"] for e in entries) > TASK_CAP + 1e-9:
        raise SystemExit("the task cap would be exceeded; nothing reserved")
    for e in entries:
        if conn.execute("SELECT 1 FROM operations WHERE operation_id = ?", (e["operation"],)).fetchone():
            raise SystemExit(f"{e['operation']} already exists; nothing reserved")
    for pool, new in (("training", training), ("platform", platform)):
        if before[pool]["committed_usd"] + sum(e["usd"] for e in new) > before[pool]["cap_usd"] + 1e-9:
            raise SystemExit(f"{pool} pool cap would be exceeded; nothing reserved")
    done = []
    for e in entries:
        L.reserve(conn, e["pool"], e["month"], e["operation"], e["usd"], e["detail"])
        row = conn.execute("SELECT operation_id, pool, month, reserved_usd, status FROM operations WHERE operation_id = ?", (e["operation"],)).fetchone()
        done.append(dict(zip(("operation_id", "pool", "month", "reserved_usd", "status"), row)))
    json.dump({"plan_sha256": a.plan_sha256, "ledger": os.path.abspath(a.ledger), "before": before,
               "after": L.summary(conn, plan["month"]), "reserved": done}, open(a.out, "w"), indent=1)
    print(json.dumps({"reserved": [d["operation_id"] for d in done]}))


if __name__ == "__main__":
    sys.exit(main())
