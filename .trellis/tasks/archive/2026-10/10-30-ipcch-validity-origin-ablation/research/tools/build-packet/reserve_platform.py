"""Origin-ablation build packet step 1 (ledger write; run only after release): reserve the task 10-30 build platform line in the shared
ledger, month 2026-10, exactly as ``reservation-platform.json`` (sha256 pinned at release). Prechecks: the operation must not
exist and the platform pool's committed + 0.19 must stay within its cap. No earlier task line is required, reused or counted. Receipt with
readback.

  cd $W/control-plane-origin-ablation && IPCCH_ORIGIN_PLATFORM_RESERVE_CONFIRM=r1 PYTHONPATH=. $W/envs/mlflow-svc/bin/python -B \
    $W/staging/ipcch-origin-ablation-20261030/build-packet/reserve_platform.py --plan-sha256 SHA --out RECEIPT.json
"""
import argparse, hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLAN = os.path.join(HERE, "reservation-platform.json")
LEDGER = "/home/swl007007/projects/food-crisis-research/ledger/spend.sqlite"


def main():
    from research_cloud.cost import ledger as L
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--plan-sha256", required=True)
    ap.add_argument("--ledger", default=LEDGER)
    a = ap.parse_args()
    if os.environ.get("IPCCH_ORIGIN_PLATFORM_RESERVE_CONFIRM") != "r1" or os.path.exists(a.out):
        raise SystemExit("needs IPCCH_ORIGIN_PLATFORM_RESERVE_CONFIRM=r1 and a new receipt path")
    raw = open(PLAN, "rb").read()
    if hashlib.sha256(raw).hexdigest() != a.plan_sha256:
        raise SystemExit("reservation-platform.json differs from the released plan")
    plan = json.loads(raw)
    entries = plan["platform"]
    if len(entries) != 1 or entries[0]["operation"] != "ipcch-origin-ablation-r1-build" or entries[0]["usd"] > plan["task_cap"]["platform_usd_max"]:
        raise SystemExit("the origin-ablation build packet reserves exactly the build line within the task cap")
    conn = L.connect(a.ledger)
    before = L.summary(conn, plan["month"])
    e = entries[0]
    if conn.execute("SELECT 1 FROM operations WHERE operation_id = ?", (e["operation"],)).fetchone():
        raise SystemExit(f"{e['operation']} already exists; nothing reserved")
    if before["platform"]["committed_usd"] + e["usd"] > before["platform"]["cap_usd"] + 1e-9:
        raise SystemExit("platform pool cap would be exceeded; nothing reserved")
    L.reserve(conn, e["pool"], e["month"], e["operation"], e["usd"], e["detail"])
    row = conn.execute("SELECT operation_id, pool, month, reserved_usd, status FROM operations WHERE operation_id = ?",
                       (e["operation"],)).fetchone()
    receipt = {"plan_sha256": a.plan_sha256, "ledger": os.path.abspath(a.ledger), "before": before,
               "after": L.summary(conn, plan["month"]), "reserved": dict(zip(("operation_id", "pool", "month", "reserved_usd", "status"), row))}
    json.dump(receipt, open(a.out, "w"), indent=1)
    print(json.dumps({k: receipt["after"][k]["committed_usd"] for k in ("platform", "training")}))


if __name__ == "__main__":
    sys.exit(main())
