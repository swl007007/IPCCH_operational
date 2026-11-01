"""Tiny self-checks of the CP5 helper corrections (pure functions; no I/O)."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
import da2_asset_readback as da  # noqa: E402
import da2_witness as dw  # noqa: E402
import witness_readback as wr  # noqa: E402


def frame(rows):
    return pd.DataFrame(rows, columns=["admin_code", "month", "value"]).astype(str)


OLD = [("1", "2026-08", "0.5"), ("2", "2026-08", "0.6")]


def test_climate_keys_exact_roster_x_O():
    ok = wr.compare_keys(frame(OLD), frame(OLD + [("1", "2026-09", "0.1"), ("2", "2026-09", "")]), ["1", "2"], "2026-09")
    assert ok["passed"] and ok["new_rows"] == 2 and ok["new_value_blank"] == 1
    one = wr.compare_keys(frame(OLD), frame(OLD + [("1", "2026-09", "0.1")]), ["1", "2"], "2026-09")
    assert not one["passed"] and one["roster_missing"] == 1          # one admin only is NOT enough
    dup = wr.compare_keys(frame(OLD + [OLD[0]]), frame(OLD), ["1", "2"], "2026-09")
    assert not dup["passed"] and not dup["pre_keys_unique"]
    changed = wr.compare_keys(frame(OLD), frame([("1", "2026-08", "0.9"), OLD[1], ("1", "2026-09", "0"), ("2", "2026-09", "0")]),
                              ["1", "2"], "2026-09")
    assert not changed["passed"] and changed["old_values_changed"] == 1


def test_expected_fields_wholly_omitted_is_reported():
    rows = [{"admin_code": 1, "et0_202609_mean": 3.0}, {"admin_code": 2, "et0_202609_mean": None}]
    out = da.summarize(rows, "drought", ["et0_202609_mean", "days_present_202609"])
    assert out["expected_fields"]["days_present_202609"]["status"] == "wholly_omitted"
    assert out["expected_fields"]["et0_202609_mean"] == {"rows": 2, "omitted": 0, "explicit_null": 1, "finite": 1,
                                                         "other": 0, "status": "partial"}
    assert da.summarize(rows, "drought")["expected_fields_note"].startswith("no declared")


def test_patch32_counts_accompany_exact_set():
    rows = [{"admin_code": c} for c in da.PATCH32_CODES] + [{"admin_code": da.PATCH32_CODES[0]}]
    p = da.summarize(rows, "patch32")["patch32"]
    assert p["rows"] == 33 and p["distinct"] == 32 and p["duplicates"] == 1 and not p["equals_targets"]


def test_patch_fill_rule_and_preservation():
    prim = {"76": {"et0_202609_mean": None}, "77": {"et0_202609_mean": 2.0}, "983": {}}
    patch = {"76": {"et0_202609_mean": 3.0}, "77": {"et0_202609_mean": 9.0}, "983": {"et0_202609_mean": True}}
    f = {x["admin_code"]: x for x in dw.patch_fill(prim, patch, ["76", "77", "983"], ["202609"])}
    assert f["76"]["filled"] and f["76"]["selected"] == 3.0
    assert not f["77"]["filled"] and f["77"]["selected"] == 2.0 and f["77"]["finite_primary_preserved"]
    assert not f["983"]["filled"] and not f["983"]["primary_key_present"]       # bool patch is not finite numeric


def test_vi_compare_pending_and_tolerance():
    assert dw.vi_compare({}, {}) == {"status": "unobserved_pending_D2", "passed": None, "per_admin": {}}
    assert dw.vi_compare({"1": 0.25}, {"1": 0.25})["passed"]
    assert not dw.vi_compare({"1": 0.25}, {"1": 0.26})["passed"]
    assert not dw.vi_compare({}, {"1": 0.25})["passed"]                          # missing recompute fails


def test_expected_fields_drought_and_vi():
    f = dw.expected_fields("drought", "projects/p/assets/S2C3_DROUGHT_ADMIN_ET0_FAO56_Y2020_2026_V3__M202611_x_1", [], "2026-09")
    assert f[0] == "et0_202001_mean" and "et0_202609_mean" in f and "et0_202610_mean" not in f and "days_present_202609" in f
    assert dw.expected_fields("vi", "a", [{"composite_dates": "20260914,20260930"}], "2026-09") == ["evi_20260914_mean", "evi_20260930_mean"]


def _links_world(tmp_path, retained, corrupt_delivery=False):
    import hashlib, json
    req = {t: {"generation": "7", "version": 2, "sha256": f"s-{t}"} for t in retained}
    post_t = {t: {"head_generation": "7", "version": 2, "content_sha256": f"s-{t}"} for t in wr.REQUIRED_RETAINED}
    bman = json.dumps({"batch_id": "B1", "retained_inputs": req, "feature_provenance": {"sha256": "fp"}}).encode()
    dman = json.dumps({"files": [{"path": "ipcch/reports/ipcch_feature_fill_audit.csv", "sha256": "fp"}]}).encode()
    blobs = {("gs://x/batch.json", "1"): bman, ("gs://x/delivery.json", "2"): dman}
    post = {"passed": True, "batch": {"batch_id": "B1", "manifest_ref": {"uri": "gs://x/batch.json", "generation": "1",
                                                                       "sha256": hashlib.sha256(bman).hexdigest()}},
            "record": {"delivery": {"manifest": {"uri": "gs://x/delivery.json", "generation": "2",
                                                 "sha256": "0" * 64 if corrupt_delivery else hashlib.sha256(dman).hexdigest()}}}}
    (tmp_path / "post.json").write_text(json.dumps(post))
    (tmp_path / "inv.json").write_text(json.dumps({"tables": post_t}))
    return blobs


def _run_links(tmp_path, monkeypatch, blobs, name):
    import json
    monkeypatch.setattr(wr.storage, "Client", lambda *a, **k: None)
    monkeypatch.setattr(wr, "_bytes", lambda client, uri, generation=None: blobs[(uri, generation)])
    code = wr.links(str(tmp_path / "post.json"), str(tmp_path / "inv.json"), str(tmp_path / name))
    return code, json.loads((tmp_path / name).read_text())


def test_links_integration_required_refs_and_manifest_sha(tmp_path, monkeypatch):
    code, body = _run_links(tmp_path, monkeypatch, _links_world(tmp_path, wr.REQUIRED_RETAINED), "ok.json")
    assert code == 0 and body["passed"]
    code, body = _run_links(tmp_path, monkeypatch, _links_world(tmp_path, []), "empty.json")
    assert code == 1 and not body["checks"]["retained_nonempty"] and not body["checks"]["retained_all_equal_post_heads"]
    code, body = _run_links(tmp_path, monkeypatch, _links_world(tmp_path, wr.REQUIRED_RETAINED[:-1]), "missing.json")
    assert code == 1 and body["missing_required"] == [wr.REQUIRED_RETAINED[-1]]
    code, body = _run_links(tmp_path, monkeypatch, _links_world(tmp_path, wr.REQUIRED_RETAINED, corrupt_delivery=True), "bad.json")
    assert code == 1 and not body["checks"]["delivery_manifest_sha_ok"]
