"""Task 10-29 IPCCH climate ensemble core (R8, R13, R32, R33, R34, R40, R41, R43) on tiny synthetic stores."""

import numpy as np
import pandas as pd
import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import climate as cl
from cloud.ipcch.stores import StoreError, StoreRoot, VersionedTable

ROSTER = ["1", "2", "3"]


def store(tmp_path, base, temporal=cl.MONTHLY):
    return VersionedTable(LocalObjectStore(tmp_path), StoreRoot("real", "gs://b/ipcch-v2/real"), cl.table_name(base, temporal))


def pub(source, values, codes=ROSTER):
    return cl.SourceOutcome(source, "published", pd.DataFrame({"admin_code": list(codes), "value": values}))


def seed(table, months):
    rows = pd.DataFrame([{"admin_code": a, "month": m, "value": 0.0, "n_sources": 1, "ens_sd": np.nan, "method_id": "accepted"}
                         for m in months for a in ROSTER])
    table.commit(rows, {"action": "initialise"}, expected_generation="0")


def test_ensemble_rule():
    e = cl.ensemble({"a": pd.Series([1.0, 2.0, np.nan, np.nan], index=list("wxyz")),
                     "b": pd.Series([3.0, np.nan, np.nan, 5.0], index=list("wxyz")),
                     "c": pd.Series([5.0, np.nan, np.nan, np.nan], index=list("wxyz"))}).set_index("admin_code")
    assert e.loc["w", "value"] == 3.0 and e.loc["w", "n_sources"] == 3
    assert e.loc["w", "ens_sd"] == pytest.approx(np.std([1.0, 3.0, 5.0]))     # population SD, ddof 0
    assert e.loc["x", "value"] == 2.0 and e.loc["x", "n_sources"] == 1 and np.isnan(e.loc["x", "ens_sd"])  # single source
    assert np.isnan(e.loc["y", "value"]) and e.loc["y", "n_sources"] == 0      # never zero-filled
    assert e.loc["z", "value"] == 5.0


def test_monthly_lookback_gaps_persistence_and_origin_block(tmp_path):
    t = store(tmp_path, "sm_z")
    seed(t, ["2026-03", "2026-04"])
    calls = []

    def fetch(src, month):
        calls.append((src, month))
        if month == "2026-05":
            return cl.SourceOutcome(src, "unavailable", detail="not published")       # lookback gap (R43)
        if src == "gldas21":
            return cl.SourceOutcome(src, "unavailable", detail="lag")                 # one provider late (R34)
        return pub(src, [1.0, np.nan, 3.0])

    rep = cl.update_monthly(t, "sm_z", origin="2026-06", roster=ROSTER, fetch=fetch)
    assert rep["saved"] == ["2026-06"] and set(rep["gaps"]) == {"2026-05"}
    frame, _ = cl.read_monthly(t)
    june = frame[frame["month"] == "2026-06"].set_index("admin_code")
    assert june["value"].tolist()[0] == 1.0 and np.isnan(june.loc["2", "value"])       # per-area NaN retained
    assert june["n_sources"].tolist() == [1, 0, 1] and june["ens_sd"].isna().all()
    assert set(june["method_id"]) == {cl.method_id("sm_z", cl.MONTHLY)}
    # a later run retries only the unsaved gap; the late provider never rewrites the saved June (R8)
    calls.clear()
    rep2 = cl.update_monthly(t, "sm_z", origin="2026-06", roster=ROSTER, fetch=lambda s, m: pub(s, [9.0, 9.0, 9.0]))
    assert rep2["saved"] == ["2026-05"]
    frame, _ = cl.read_monthly(t)
    assert frame.loc[frame["month"] == "2026-06", "value"].tolist()[0] == 1.0
    # no source for O blocks (R13); earlier months already saved stay saved (R41)
    with pytest.raises(cl.ClimateSourceMissing):
        cl.update_monthly(t, "sm_z", origin="2026-08",
                          roster=ROSTER, fetch=lambda s, m: pub(s, [2.0, 2.0, 2.0]) if m == "2026-07"
                          else cl.SourceOutcome(s, "unavailable"))
    assert "2026-07" in set(cl.read_monthly(t)[0]["month"])


def test_failures_are_never_unavailability(tmp_path):
    t = store(tmp_path, "gdd")
    seed(t, ["2026-03"])
    head = t.head()
    bad = {
        "missing roster area": lambda s, m: pub(s, [1.0, 2.0], codes=["1", "2"]),
        "duplicate": lambda s, m: pub(s, [1.0, 2.0, 3.0, 4.0], codes=["1", "2", "3", "3"]),
        "infinite": lambda s, m: pub(s, [1.0, np.inf, 3.0]),
        "status": lambda s, m: cl.SourceOutcome(s, "error"),
        "source set": lambda s, m: pub("cpc", [1.0, 2.0, 3.0]),
    }
    for name, fetch in bad.items():
        with pytest.raises(cl.ClimateProcessingFailure):
            cl.update_monthly(t, "gdd", origin="2026-04", roster=ROSTER, fetch=fetch)
    assert t.head() == head                                                   # nothing saved by a failed month


def test_out_of_roster_areas_dropped_and_counted(tmp_path):
    t = store(tmp_path, "edd")
    seed(t, ["2026-03"])
    fetch = lambda s, m: pub(s, [1.0, 2.0, 3.0, 4.0], codes=["1", "2", "3", "6227"])
    head = t.head()
    with pytest.raises(cl.ClimateProcessingFailure, match=r"unknown modeled-area identifiers \['6227'\]"):
        cl.update_monthly(t, "edd", origin="2026-04", roster=ROSTER, fetch=fetch)          # undeclared extra (R32)
    assert t.head() == head
    rep = cl.update_monthly(t, "edd", origin="2026-04", roster=ROSTER, fetch=fetch, declared_extra=["6227"])
    assert rep["months"]["2026-04"]["dropped_out_of_roster"] == {"cpc": 1, "era5land": 1}
    assert set(cl.read_monthly(t)[0]["admin_code"]) == set(ROSTER)


def test_empty_history_and_noncanonical_months_refused(tmp_path):
    with pytest.raises(StoreError, match="accepted climate history"):
        cl.update_monthly(store(tmp_path, "cdd"), "cdd", origin="2026-04", roster=ROSTER, fetch=None)
    t = store(tmp_path, "rainy_days")
    seed(t, ["2026-03"])
    with pytest.raises(StoreError, match="canonical"):
        cl.update_monthly(t, "rainy_days", origin="2026-4", roster=ROSTER, fetch=None)


def test_seasons_only_when_complete_and_never_rewritten(tmp_path):
    t = store(tmp_path, "prcp_z", cl.SEASONAL)
    windows = pd.DataFrame({"admin_code": ["1", "2", "3"], "season_year": [2026, 2026, 2026], "season": ["s1", "s1", "s1"],
                            "gs_start_date": ["2026-03-01", "2026-03-01", "2026-04-01"],
                            "gs_end_date_exclusive": ["2026-07-01", "2026-07-01", "2026-08-01"]})
    seen = []

    def fetch(src, year, season, win):
        seen.append(list(win["admin_code"]))
        return pub(src, [1.0] * len(win), codes=list(win["admin_code"]))

    rep = cl.update_seasonal(t, "prcp_z", origin="2026-06", roster=ROSTER, windows=windows, fetch=fetch)
    assert rep["saved"] == ["2026-s1"] and seen[0] == ["1", "2"]               # area 3 still in season: not saved
    cl.update_seasonal(t, "prcp_z", origin="2026-07", roster=ROSTER, windows=windows, fetch=fetch)
    assert seen[-1] == ["3"]                                                   # only the newly completed area
    frame, _ = cl.read_seasonal(t)
    assert sorted(frame["admin_code"]) == ROSTER and frame["n_sources"].eq(3).all()
    assert cl.update_seasonal(t, "prcp_z", origin="2026-09", roster=ROSTER, windows=windows, fetch=fetch)["saved"] == []
    for bad in ("2026-02-31", "2026-13-01"):
        with pytest.raises(StoreError, match="real YYYY-MM-DD"):
            cl.completed_windows(windows.assign(gs_end_date_exclusive=bad), "2026-09")
    with pytest.raises(StoreError, match="unknown modeled areas"):
        cl.update_seasonal(t, "prcp_z", origin="2026-09", roster=["1"], windows=windows, fetch=fetch)


def test_method_ids_bind_scripts():
    assert cl.method_ids("spei03", cl.MONTHLY)["spei_fit"] == cl.SPEI_FIT_MONTHLY
    assert cl.method_ids("spei03", cl.SEASONAL)["spei_fit"] == cl.SPEI_FIT_SEASONAL != cl.SPEI_FIT_MONTHLY
    assert "season_aggregation" in cl.method_ids("spi03", cl.SEASONAL)
    assert cl.method_ids("evi_anom", cl.MONTHLY)["script"] == "monthly/ndvi_evi.js"
    assert cl.method_ids("evi_anom", cl.SEASONAL)["script"] == "seasonal/ndvi.js"
    assert cl.method_id("prcp_anom", cl.SEASONAL).startswith("seasonal/rainfall.js@73ba8ddbfbd6|")
    assert set(cl.BASES) == {"prcp_anom", "prcp_z", "rainy_days", "cdd", "tmean_anom", "tmax_anom", "hot_days_p95", "gdd",
                             "edd", "sm_z", "spi03", "spei03", "evi_anom"}


def test_seasonal_outputs_over_all_admins_keep_only_window_areas_and_refuse_unknown_ids(tmp_path):
    windows = pd.DataFrame({"admin_code": ["1", "2"], "season_year": [2026, 2026], "season": ["s1", "s1"],
                            "gs_start_date": ["2026-03-01", "2026-03-01"], "gs_end_date_exclusive": ["2026-07-01", "2026-07-01"]})
    everything = lambda src, year, season, win: pub(src, [1.0, 2.0, 3.0, 4.0], codes=["1", "2", "3", "6227"])
    t = store(tmp_path, "prcp_z", cl.SEASONAL)
    with pytest.raises(cl.ClimateProcessingFailure, match=r"unknown modeled-area identifiers \['6227'\]"):
        cl.update_seasonal(t, "prcp_z", origin="2026-06", roster=ROSTER, windows=windows, fetch=everything)
    assert t.head()[0] is None
    rep = cl.update_seasonal(t, "prcp_z", origin="2026-06", roster=ROSTER, windows=windows, fetch=everything,
                             declared_extra=["6227"])
    assert rep["saved"] == ["2026-s1"]
    assert sorted(cl.read_seasonal(t)[0]["admin_code"]) == ["1", "2"]      # roster area 3 (no window) and 6227 dropped
