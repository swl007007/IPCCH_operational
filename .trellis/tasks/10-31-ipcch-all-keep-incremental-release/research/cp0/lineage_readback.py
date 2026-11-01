"""Task 10-31 CP2: READ-ONLY incremental lineage readback (run under guarded.sh after the monthly run).

Inputs: RUN_ID, the readback_v2 post JSON (batch generation + retained_inputs + record), the pre/post store inventories,
the ACLED pre/post fingerprints. Reads the durable EE task records
  {export_root}/ipcch_exports/<run_id>/tasks/*.json
and joins them with incremental_checks.lineage; also checks kept histories (kept_unchanged) and the ACLED interval
refresh (compare_acled), and reports GPP/nightlight/raster-climate HEAD changes. Never writes anything remote.

usage: lineage_readback.py RUN_ID POST_REAL_JSON INV_PRE INV_POST ACLED_PRE ACLED_POST EXPECTED_ACLED OUT_JSON
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
ACLED = {"start": "2026-10-17", "end": "2026-10-23", "source_sha256": "e660c7e8eb126c102145069441805bf55314914cb6297601bd5a150a87e47e8a",
         "regions": ["Caribbean", "Caucasus and Central Asia", "Central America", "East Asia", "Eastern Africa", "Europe",
                     "International Waters", "Middle Africa", "Middle East", "North America", "Northern Africa", "Oceania",
                     "South America", "South Asia", "Southeast Asia", "Southern Africa", "Western Africa"]}


def task_records(run_id):
    bucket, _, prefix = EXPORT_ROOT.removeprefix("gs://").partition("/")
    client = storage.Client()
    out = []
    for blob in client.list_blobs(bucket, prefix=f"{prefix}/ipcch_exports/{run_id}/tasks/"):
        out.append({**json.loads(blob.download_as_bytes(if_generation_match=blob.generation)),
                    "_object": f"gs://{bucket}/{blob.name}#{blob.generation}"})
    return out


def main(run_id, post_real, inv_pre, inv_post, acled_pre, acled_post, expected_acled, out):
    post = json.load(open(post_real))
    pre_t, post_t = json.load(open(inv_pre))["tables"], json.load(open(inv_post))["tables"]
    gen = post["batch"]["generation"] or {}
    production = gen.get("climate_production") or {}
    tasks = task_records(run_id)
    lin = ic.lineage(tasks, production, post_t, post["batch"]["retained_inputs"] or {}, TABLE_BASES,
                     post["actual"]["O"], run_id)
    kept = ic.kept_unchanged(pre_t, post_t, KEPT)
    a_pre, a_post, a_exp = json.load(open(acled_pre)), json.load(open(acled_post)), json.load(open(expected_acled))
    acl = ic.compare_acled(a_pre["region_week"], a_post["region_week"], ACLED["start"], ACLED["end"], ACLED["regions"],
                           a_exp["region_week"])
    last = a_post.get("last_refresh") or {}
    acled_pin = {"source_sha256": (last.get("source") or {}).get("sha256") == ACLED["source_sha256"] == a_exp["source_sha256"],
                 "interval": (last.get("start"), last.get("end")) == (ACLED["start"], ACLED["end"]),
                 "regions": sorted(last.get("regions") or []) == sorted(ACLED["regions"]),
                 "coverage_record_appended": a_post.get("coverage_records", [])[:-1] == a_pre.get("coverage_records")
                 and a_post.get("coverage_records", [None])[-1] == last}
    moved = {t: {"pre": (pre_t.get(t) or {}).get("version"), "post": (post_t.get(t) or {}).get("version"),
                 "month": ((post_t.get(t) or {}).get("record") or {}).get("month")}
             for t in RASTER_BASES + TABLE_BASES + ["history__GPP_mean", "gpp_availability_ledger",
                                                     "history__nightlight_mean", "acled_agg_weekly"]}
    checks = {**{f"lineage.{k}": v for k, v in lin["checks"].items()},
              "kept_ten_unchanged": all(kept.values()) and len(kept) == 10,
              **{f"acled.{k}": v for k, v in acl["checks"].items()},
              **{f"acled.pin.{k}": v for k, v in acled_pin.items()},
              "generic_readback_passed": bool(post.get("passed"))}
    body = {"run_id": run_id, "checks": checks, "passed": all(checks.values()), "lineage": lin, "kept": kept,
            "acled": acl, "acled_post_head": {k: a_post[k] for k in ("head_generation", "head_version", "rows", "max_week",
                                                                     "rows_inside_interval", "last_refresh")},
            "head_changes": moved, "task_records": tasks, "production": production,
            "warnings": gen.get("warnings"), "gaps": gen.get("gaps"), "coverage_end": gen.get("coverage_end"),
            "inputs": gen.get("inputs")}
    with open(out, "x") as f:
        json.dump(body, f, indent=1, sort_keys=True, default=str)
    print(json.dumps({"passed": body["passed"], "failed": sorted(k for k, v in checks.items() if not v)}, indent=1))
    return 0 if body["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:9]))
