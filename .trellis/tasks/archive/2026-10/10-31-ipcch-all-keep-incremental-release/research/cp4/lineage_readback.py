"""Task 10-31 CP2: READ-ONLY incremental lineage readback (run under guarded.sh after the monthly run).

Inputs: RUN_ID, the readback_v2 post JSON (batch generation + retained_inputs + record), the pre/post store inventories. Reads the durable EE task records
  {export_root}/ipcch_exports/<run_id>/tasks/*.json
and joins them with incremental_checks.lineage; also checks the eleven kept histories (kept_unchanged), and reports GPP/nightlight/raster-climate HEAD changes. Never writes anything remote.

usage: lineage_readback.py RUN_ID POST_REAL_JSON INV_PRE INV_POST OUT_JSON\n(D5 recovery copy: all eleven manual inputs kept, including ACLED v2; the first attempt's ACLED refresh evidence\nstays in cp2/failure-source-checks.json)
"""

import json
import sys
from pathlib import Path

from google.cloud import storage

sys.path.insert(0, str(Path(__file__).parent))
import incremental_checks as ic  # noqa: E402

EXPORT_ROOT = "gs://food-crisis-test-ipcch-data/ipcch-v2/exports"
TABLE_BASES = ["history__climate_month_evi_anom", "history__climate_month_spi03", "history__climate_month_spei03"]
RASTER_BASES = [f"history__climate_month_{b}" for b in ("prcp_anom", "prcp_z", "rainy_days", "cdd", "tmean_anom",
                                                        "tmax_anom", "hot_days_p95", "gdd", "edd", "sm_z")]
KEPT = ["history__WFP_Price", "history__history_snapshot", "history__nino34_anom",
        "history__bbg_staple_food__composite_mean", "history__bbg_oilgas__composite_mean",
        "history__bbg_soybean_oil__composite_mean", "history__bbg_global_food__composite_mean",
        "history__food_price_index_WB", "history__idp_national", "history__idp_local"]
KEPT = KEPT + ["acled_agg_weekly"]          # D5 all-eleven-keep: ACLED v2 is a kept history for this run


def task_records(run_id):
    bucket, _, prefix = EXPORT_ROOT.removeprefix("gs://").partition("/")
    client = storage.Client()
    out = []
    for blob in client.list_blobs(bucket, prefix=f"{prefix}/ipcch_exports/{run_id}/tasks/"):
        out.append({**json.loads(blob.download_as_bytes(if_generation_match=blob.generation)),
                    "_object": f"gs://{bucket}/{blob.name}#{blob.generation}"})
    return out


def main(run_id, post_real, inv_pre, inv_post, out):
    post = json.load(open(post_real))
    pre_t, post_t = json.load(open(inv_pre))["tables"], json.load(open(inv_post))["tables"]
    gen = post["batch"]["generation"] or {}
    production = gen.get("climate_production") or {}
    tasks = task_records(run_id)
    lin = ic.lineage(tasks, production, post_t, post["batch"]["retained_inputs"] or {}, TABLE_BASES,
                     post["actual"]["O"], run_id)
    kept = ic.kept_unchanged(pre_t, post_t, KEPT)
    moved = {t: {"pre": (pre_t.get(t) or {}).get("version"), "post": (post_t.get(t) or {}).get("version"),
                 "month": ((post_t.get(t) or {}).get("record") or {}).get("month")}
             for t in RASTER_BASES + TABLE_BASES + ["history__GPP_mean", "gpp_availability_ledger",
                                                     "history__nightlight_mean", "acled_agg_weekly"]}
    checks = {**{f"lineage.{k}": v for k, v in lin["checks"].items()},
              "kept_eleven_unchanged": all(kept.values()) and len(kept) == 11,
              "generic_readback_passed": bool(post.get("passed"))}
    body = {"run_id": run_id, "checks": checks, "passed": all(checks.values()), "lineage": lin, "kept": kept,
            "head_changes": moved, "task_records": tasks, "production": production,
            "warnings": gen.get("warnings"), "gaps": gen.get("gaps"), "coverage_end": gen.get("coverage_end"),
            "inputs": gen.get("inputs")}
    with open(out, "x") as f:
        json.dump(body, f, indent=1, sort_keys=True, default=str)
    print(json.dumps({"passed": body["passed"], "failed": sorted(k for k, v in checks.items() if not v)}, indent=1))
    return 0 if body["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:6]))
