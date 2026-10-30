"""Task 10-29: the seasonal SPI/SPEI port (vendored originals + ported exact season plan) equals the shared-folder
seasonal/spi&spei.py, and differs from the monthly script's SPEI (separate method)."""

import importlib.util
import json
import os

import numpy as np
import pandas as pd
import pytest

from cloud.ipcch import spi_spei as monthly
from cloud.ipcch import spi_spei_seasonal as ss

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fixtures", "ipcch_climate")
SHARED = os.environ.get("IPCCH_SHARED_SPI_SEASONAL",
                        "/mnt/c/users/swl00/ifpri dropbox/weilun shi/IPCCH_shared_folder/seasonal/spi&spei.py")
ALL = pd.date_range("1990-01-01", "2021-12-01", freq="MS")
IDX = pd.date_range("2014-01-01", "2021-12-01", freq="MS")


def _maker():
    spec = importlib.util.spec_from_file_location("make_seasonal", os.path.join(FIX, "make_seasonal_golden.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _port(prcp, et0, cal):
    m = ss.monthly_indices(prcp, et0, ALL, IDX, "chirps")
    windows = ss.windows_from_calendar(cal, range(2015, 2022))
    plan = ss.season_plan(windows, IDX, list(cal["admin_code"].astype(str)))
    agg = pd.concat([ss.aggregate(m["spi"], m["spi_reason"], plan, "spi03_gs_chirps"),
                     ss.aggregate(m["spei"], m["spei_reason"], plan, "spei03_gs_chirps")], axis=1)
    return m, plan, agg


def test_port_equals_golden_from_original():
    g = np.load(os.path.join(FIX, "ipcch_seasonal_golden.npz"))
    want = pd.read_csv(os.path.join(FIX, "ipcch_seasonal_golden.csv"), dtype={"admin_code": str}, float_precision="round_trip")
    cal = pd.read_csv(os.path.join(FIX, "ipcch_seasonal_calendar_fixture.csv"), dtype=str, keep_default_na=False)
    m, plan, agg = _port(g["prcp"], g["et0"], cal)
    for k in ("spi", "spi_reason", "spei", "spei_reason"):
        np.testing.assert_array_equal(m[k], g[k])
    for c in ("admin_code", "season_year", "season", "gs_calendar_valid", "_admin_position"):
        assert plan[c].astype(str).tolist() == want[c].astype(str).tolist(), c
    for c in ("gs_start_date", "gs_end_date_exclusive"):
        assert plan[c].fillna("").tolist() == want[c].fillna("").tolist(), c
    np.testing.assert_array_equal(plan["gs_duration_recalculated_days"].to_numpy(float), want["gs_duration_recalculated_days"].to_numpy(float))
    assert plan["_month_positions"].map(list).tolist() == want["_month_positions"].map(json.loads).tolist()
    assert plan["_overlap_days"].map(list).tolist() == want["_overlap_days"].map(json.loads).tolist()
    for c in agg.columns:
        if not pd.api.types.is_numeric_dtype(want[c]):
            assert agg[c].fillna("").astype(str).tolist() == want[c].fillna("").astype(str).tolist(), c
        else:
            np.testing.assert_array_equal(agg[c].to_numpy(float), want[c].to_numpy(float), err_msg=c)
    assert (agg["spei03_gs_chirps_status"] == "COMPLETE").sum() > 20 and (plan["gs_calendar_valid"] == 0).sum() > 0


@pytest.mark.skipif(not os.path.exists(SHARED), reason="shared-folder script not mounted; golden still checked")
def test_vendored_text_and_live_differential():
    mk = _maker()
    import subprocess, sys
    tool = os.path.join(os.path.dirname(__file__), "..", "..", "tools", "vendor_ipcch_seasonal_spi_spei.py")
    spec = importlib.util.spec_from_file_location("vendor_tool", tool)
    vt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vt)
    assert all(p in ss._TEXT for p in vt.extract(SHARED))                    # vendored bytes == original functions
    cal = mk.calendar_fixture()
    for seed in (5, 6):
        prcp, et0 = mk.inputs(seed, len(cal))
        ns = mk.original(SHARED, len(cal), cal)
        m, plan, agg = _port(prcp, et0, cal.astype(str))
        o_spei, o_r, _ = ns["compute_spei03"](prcp, et0, "chirps")
        np.testing.assert_array_equal(m["spei"], o_spei)
        np.testing.assert_array_equal(m["spei_reason"], o_r)
        o_agg = ns["aggregate_gs"](o_spei, o_r, "x")
        np.testing.assert_array_equal(ss.aggregate(m["spei"], m["spei_reason"], plan, "x")["x"].to_numpy(), o_agg["x"].to_numpy())


def test_seasonal_spei_is_not_the_monthly_spei():
    g = np.load(os.path.join(FIX, "ipcch_seasonal_golden.npz"))
    mon = monthly.compute_spei03_monthly(g["prcp"], g["et0"], ALL)[:, ALL.get_indexer(IDX)]
    sea = g["spei"]
    both = np.isfinite(mon) & np.isfinite(sea)
    assert both.sum() > 100 and not np.allclose(mon[both], sea[both])     # different fits: never conflated (R40)
    from cloud.ipcch import climate as cl
    assert ss.SPEI_FIT == cl.SPEI_FIT_SEASONAL != cl.SPEI_FIT_MONTHLY


def test_boundaries():
    with pytest.raises(ValueError, match="identical"):
        ss.monthly_indices(np.ones((2, len(ALL))), np.ones((1, len(ALL))), ALL, IDX, "chirps")
    with pytest.raises(ValueError, match="1991-2020"):
        short = pd.date_range("2000-01-01", "2021-12-01", freq="MS")
        ss.monthly_indices(np.ones((1, len(short))), np.ones((1, len(short))), short, IDX, "chirps")
    with pytest.raises(RuntimeError, match="unavailable"):
        w = pd.DataFrame([{"admin_code": "1", "season_year": 2022, "season": "s1", "gs_calendar_valid": 1,
                           "gs_start_date": "2021-11-01", "gs_end_date_exclusive": "2022-03-01"}])
        ss.season_plan(w, IDX, ["1"])
    bad = pd.DataFrame([{"admin_code": "1", "s1_calendar_valid": "1", "s1_cross_year": "0", "s1_sos_month": "", "s1_sos_day": "1",
                         "s1_eos_month": "5", "s1_eos_day": "1", "s2_calendar_valid": "0"}])
    with pytest.raises(ValueError, match="missing month/day"):
        ss.windows_from_calendar(bad, [2020])
    leap = pd.DataFrame([{"admin_code": "1", "s1_calendar_valid": "1", "s1_cross_year": "0", "s1_sos_month": "2", "s1_sos_day": "29",
                          "s1_eos_month": "5", "s1_eos_day": "1", "s2_calendar_valid": "0"}])
    w = ss.windows_from_calendar(leap, [2019, 2020])
    assert w.loc[w.season == "s1", "gs_start_date"].tolist() == ["2019-02-28", "2020-02-29"]     # USE_FEB28 only
