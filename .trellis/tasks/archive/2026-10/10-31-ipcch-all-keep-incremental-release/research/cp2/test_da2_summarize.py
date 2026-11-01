"""Bounded self-check of da2_asset_readback.summarize (pure; no EE)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import da2_asset_readback as da  # noqa: E402


def test_omitted_vs_explicit_null_and_patch32_set():
    rows = [{"admin_code": c, "et0_202609_mean": 3.5, "days_present_202609": 30} for c in da.PATCH32_CODES]
    rows[0].pop("et0_202609_mean")                    # omitted key on one row
    rows[1]["et0_202609_mean"] = None                 # explicit null on another
    out = da.summarize(rows, "patch32")
    assert out["rows"] == 32 and out["patch32"]["equals_targets"] and not out["patch32"]["missing"]
    assert out["rows_with_omitted_keys"] == {"et0_202609_mean": 1}
    assert out["explicit_null_counts"] == {"et0_202609_mean": 1}
    assert out["value_columns"]["et0_202609_mean"]["finite"] == 30
    assert out["constants"]["days_present_202609"] == 30


def test_patch32_extra_and_float_codes():
    rows = [{"admin_code": float(c)} for c in da.PATCH32_CODES[:31]] + [{"admin_code": 1}]
    out = da.summarize(rows, "patch32")
    assert not out["patch32"]["equals_targets"] and out["patch32"]["missing"] == ["987"] and out["patch32"]["extra"] == ["1"]


def test_vi_constants_and_ranges():
    rows = [{"admin_code": "11", "evi_20260914_mean": 0.31, "composite_dates": "20260914"},
            {"admin_code": "12", "evi_20260914_mean": -0.02, "composite_dates": "20260914"}]
    out = da.summarize(rows, "vi")
    assert out["constants"]["composite_dates"] == "20260914"
    assert out["value_columns"]["evi_20260914_mean"] == {"finite": 2, "min": -0.02, "max": 0.31}
