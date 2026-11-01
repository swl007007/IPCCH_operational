"""Bounded self-check of incremental_checks.py (tiny in-memory fixtures; no I/O, no polling)."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import incremental_checks as ic  # noqa: E402


def frame(rows):
    return pd.DataFrame(rows, columns=list(ic.WEEKLY_COLUMNS))


OLD = [("2026-10-10", "Eastern Africa", "Kenya", "Nairobi", "Battles", 1, 0, 1.0),
       ("2026-10-10", "Middle Africa", "Chad", "Lac", "Riots", 2, 1, 1.0)]
NEW = [("2026-10-17", "Eastern Africa", "Kenya", "Nairobi", "Battles", 3, 0, 1.0),
       ("2026-10-17", "Oceania", "Fiji", "Central", "Protests", 1, 0, 1.0)]
REG = ["Eastern Africa", "Middle Africa", "Oceania"]
S, E = "2026-10-17", "2026-10-23"


def test_acled_interval_equal_to_pinned_export_passes():
    out = ic.compare_acled(ic.fingerprint(frame(OLD)), ic.fingerprint(frame(OLD + NEW)), S, E, REG, ic.fingerprint(frame(NEW)))
    assert out["passed"] and out["interval_rows"] == 2


def test_acled_same_count_wrong_value_fails():
    wrong = [NEW[0][:5] + (4, 0, 1.0), NEW[1]]                       # same rows/keys, one value differs
    out = ic.compare_acled(ic.fingerprint(frame(OLD)), ic.fingerprint(frame(OLD + wrong)), S, E, REG, ic.fingerprint(frame(NEW)))
    assert not out["checks"]["interval_equals_pinned_export"] and out["interval_mismatch"] == ["Eastern Africa|2026-10-17"]


def test_acled_changed_old_week_or_late_week_fails():
    pre = ic.fingerprint(frame(OLD))
    edited = [OLD[0][:5] + (9, 0, 1.0), OLD[1]]
    out = ic.compare_acled(pre, ic.fingerprint(frame(edited + NEW)), S, E, REG, ic.fingerprint(frame(NEW)))
    assert not out["checks"]["outside_preserved"] and out["lost_or_changed_outside"] == ["Eastern Africa|2026-10-10"]
    late = [("2026-10-24",) + NEW[0][1:]]
    out = ic.compare_acled(pre, ic.fingerprint(frame(OLD + NEW + late)), S, E, REG, ic.fingerprint(frame(NEW)))
    assert not out["checks"]["no_new_keys_outside"]


def test_fingerprint_is_order_independent():
    assert ic.fingerprint(frame(OLD + NEW)) == ic.fingerprint(frame(list(reversed(OLD + NEW))))


def head(gen, ver, sha, record=None):
    return {"head_generation": gen, "version": ver, "content_sha256": sha, "record": record or {}}


RUN = "ipcch-real-x"
J1, J2 = "S2C3_DROUGHT_ADMIN_PRCP_CHIRPS_Y2020_2026_V3", "S2C3_DROUGHT_ADMIN_PRCP_PERSIANN_Y2020_2026_V3"


def world():
    tasks = [{"run_id": RUN, "kind": "table_to_asset", "asset_id": "A1", "task_id": "T1", "state": "completed"},
             {"run_id": RUN, "kind": "table_to_asset", "asset_id": "A2", "task_id": "T2", "state": "completed"}]
    prod = {"run_id": RUN, "demand": {"monthly": {"spi03": ["2026-09"]}, "seasonal": {"spi03": []}}, "jobs": [J1, J2],
            "receipts": [{"table": J1, "asset_id": "A1", "task_id": "T1", "state": "completed", "rows": 6226},
                         {"table": J2, "asset_id": "A2", "task_id": "T2", "state": "completed", "rows": 6226}]}
    post = {"m_spi03": head("9", 2, "s9", {"month": "2026-09", "published": ["chirps", "persiann"],
                                           "produced_tables": {"chirps": ["A1"], "persiann": ["A2"]}})}
    ret = {"m_spi03": {"generation": "9", "version": 2, "sha256": "s9"}}
    return tasks, prod, post, ret


def run(tasks, prod, post, ret):
    return ic.lineage(tasks, prod, post, ret, ["m_spi03"], "2026-09", RUN)


def test_lineage_passes_on_a_linked_chain_with_all_assets_consumed():
    out = run(*world())
    assert out["passed"] and out["all_assets_consumed"], out["checks"]


def test_lineage_fails_each_broken_link():
    tasks, prod, post, ret = world()
    assert not run(tasks[:1], prod, post, ret)["checks"]["receipts_join_completed_task_records"]
    assert not run(tasks, {**prod, "jobs": [J1, "OTHER"]}, post, ret)["checks"]["receipt_tables_equal_jobs"]
    assert not run(tasks, {**prod, "run_id": "other"}, post, ret)["checks"]["bound_to_run"]
    dup = tasks + [{"run_id": RUN, "kind": "table_to_asset", "asset_id": "A1", "task_id": "T9", "state": "completed"}]
    assert not run(dup, prod, post, ret)["checks"]["no_duplicate_task_or_destination"]
    stale = {"m_spi03": {"generation": "8", "version": 1, "sha256": "s8"}}
    assert not run(tasks, prod, post, stale)["checks"]["batch_retained_inputs_equal_post_heads"]
    empty = {**prod, "demand": {"monthly": {"spi03": []}, "seasonal": {}}, "jobs": [], "receipts": []}
    assert not run(tasks, empty, post, ret)["checks"]["demand_nonempty"]
    wrong = {"m_spi03": head("9", 2, "s9", {"month": "2026-08", "published": ["chirps"], "produced_tables": {"chirps": ["A1", "A2"]}})}
    assert not run(tasks, prod, wrong, ret)["checks"]["each_table_base_appends_O_from_this_run"]


def test_unconsumed_asset_needs_explicit_unavailable_disposition():
    tasks, prod, post, ret = world()
    rec = {"month": "2026-09", "published": ["chirps"], "produced_tables": {"chirps": ["A1"]}}
    unexplained = run(tasks, prod, {"m_spi03": head("9", 2, "s9", rec)}, ret)
    assert not unexplained["checks"]["unconsumed_assets_explained"] and not unexplained["passed"]
    rec2 = {**rec, "unavailable": {"persiann": "collection incomplete for 2026-09"}}
    explained = run(tasks, prod, {"m_spi03": head("9", 2, "s9", rec2)}, ret)
    assert explained["passed"] and not explained["all_assets_consumed"]
    assert explained["unconsumed_dispositions"]["A2"]["unavailable_evidence"] == {"m_spi03": "collection incomplete for 2026-09"}


def test_kept_unchanged():
    a = {"t": head("1", 1, "x")}
    assert ic.kept_unchanged(a, {"t": head("1", 1, "x")}, ["t"]) == {"t": True}
    assert ic.kept_unchanged(a, {"t": head("2", 2, "y")}, ["t"]) == {"t": False}


def test_mixed_records_join_only_asset_exports():
    tasks, prod, post, ret = world()
    raster = [{"run_id": RUN, "description": "prcp_chirps_202609", "prefix": "gs://x/ipcch_exports/r/", "selectors": ["a"],
               "task_id": "R1", "state": "completed"},
              {"run_id": RUN, "description": "sm_gldas_202609", "prefix": "gs://x/", "selectors": [], "task_id": "R2",
               "state": "reserved"}]
    out = run(tasks + raster, prod, post, ret)
    assert out["passed"] and out["asset_task_records"] == 2
    assert out["other_task_records"] == {"count": 2, "states": ["completed", "reserved"], "not_completed": ["sm_gldas_202609"]}
    foreign = raster[:1] + [dict(raster[1], run_id="other")]
    assert not run(tasks + foreign, prod, post, ret)["checks"]["bound_to_run"]
