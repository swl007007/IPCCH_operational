"""Task 10-29: IPCCH feature assembly contract on synthetic retained inputs (order, R58 year dummies, R62 history bound,
R32 roster, origin alignment, missing families stay NaN). Bit parity with the research matrices is evidenced separately
(research/cp3/assembly-parity)."""

import json
import os

import numpy as np
import pandas as pd
import pytest

from cloud.ipcch import assembly as asm
from cloud.ipcch.vendor import ipcch_compact as cp
from cloud.ipcch.vendor import ipcch_validity_feature_blocks as vb

ORDER = tuple(json.load(open(os.path.join(os.path.dirname(__file__), "..", "fixtures", "ipcch_climate", "feature_order_527.json"))))
ROSTER = (11, 12, 13)
MONTHS = [f"{y}-{m:02d}" for y in range(2015, 2027) for m in range(1, 13)]


def series(seed, months=MONTHS, areas=ROSTER):
    rng = np.random.default_rng(seed)
    return pd.DataFrame([{"admin_code": a, "month": m, "value": float(rng.normal())} for a in areas for m in months])


def inputs(**over):
    rng = np.random.default_rng(0)
    static_names = list(ORDER[:29])
    ae_names = [c for c in ORDER if c.startswith(("ae2017_mean_A", "ae2017_sd_A"))]
    windows = pd.DataFrame([{"admin_code": a, "season_year": y, "season": s,
                             "gs_start_date": f"{y}-{'03' if s == 's1' else '08'}-01", "gs_end_date_exclusive": f"{y}-{'07' if s == 's1' else '11'}-01"}
                            for a in ROSTER for y in range(2015, 2028) for s in ("s1", "s2")])
    acled = pd.DataFrame([{"admin_code": a, "month": m, **{s: float(rng.integers(0, 5)) for s in vb.ACLED_AGG_SOURCES}}
                          for a in ROSTER for m in MONTHS])
    kw = dict(
        climate_monthly={b: series(i) for i, b in enumerate(cp.CLIMATE_BASES)},
        climate_seasonal={b: windows[["admin_code", "season_year", "season"]].assign(value=rng.normal(size=len(windows)))
                          for b in cp.CLIMATE_BASES},
        season_windows=windows, interim={f: series(50 + i) for i, f in enumerate(asm.INTERIM_FAMILIES)}, acled=acled,
        idp_national=pd.DataFrame({"iso3": ["AAA", "AAA"], "report_month": ["2025-06", "2026-09"], "stock": [100.0, 200.0]}),
        idp_local=series(90), snapshot=pd.DataFrame({"area_id": [11, 11, 11, 12], "report_month": ["2025-06", "2026-02", "2026-12", "2026-01"],
                                                     "phase": [2, 3, 4, 1], "availability_month": ["2025-06", "2026-02", "2026-12", "2026-01"],
                                                     "preparation_cutoff": "2026-12"}),
        static29=pd.DataFrame({"admin_code": list(ROSTER), **{c: [1.0, 2.0, np.nan] for c in static_names}}),
        descriptors=pd.DataFrame({"admin_code": list(ROSTER), **{c: [0.1, 0.2, 0.3] for c in ae_names}}),
        identity=pd.DataFrame({"admin_code": list(ROSTER), "iso3": ["AAA", "AAA", None], "lat": [1.0, 2.0, 3.0], "lon": [4.0, 5.0, 6.0]}),
        roster=ROSTER, order=ORDER)
    kw.update(over)
    return asm.AssemblyInputs(**kw)


def ords(month):
    y, m = (int(x) for x in month.split("-"))
    return y * 12 + m - 1


def test_order_dummies_history_and_alignment():
    target = ords("2027-01")
    X, ledger = asm.assemble(inputs(), 2, list(ROSTER), [target] * 3)
    assert list(X.columns) == list(ORDER) and X.shape == (3, 527)
    assert X[[f"year_{y}" for y in range(2014, 2027)]].to_numpy().sum() == 0          # 2027 target: all-zero (R58)
    assert X["month_1"].tolist() == [1.0, 1.0, 1.0] and X["lat"].tolist() == [1.0, 2.0, 3.0]
    # O = 2026-11: area 11 latest reports <= O are 2026-02 (3) then 2025-06 (2); the 2026-12 report is after O (R62)
    assert X.loc[0, "overall_phase_history_1"] == 3.0 and X.loc[0, "overall_phase_history_2"] == 2.0
    assert np.isnan(X.loc[0, "overall_phase_history_3"]) and np.isnan(X.loc[2, "overall_phase_history_1"])
    assert X.loc[0, "idp_admin0_latest_stock"] == 200.0 and X.loc[0, "idp_admin0_latest_age_months"] == 2.0
    assert np.isnan(X.loc[2, "idp_admin0_latest_stock"])                               # no ISO3 -> missing
    assert ledger["origin_ord"].tolist() == [target - 2] * 3 and ledger["acled_cutoff_ord"].tolist() == [target - 3] * 3
    # O = 2026-11 is past the series end (2026-12 is the last month) -> value at origin exists; GPP absent family -> NaN
    X2, _ = asm.assemble(inputs(interim={f: series(1) for f in asm.INTERIM_FAMILIES if f != "GPP_mean"}), 2, list(ROSTER), [target] * 3)
    assert X2["GPP_mean__value_at_origin"].isna().all() and X2.filter(like="GPP_mean__").isna().all().all()


def test_contract_failures():
    with pytest.raises(asm.AssemblyError, match="unknown modeled-area"):
        asm.assemble(inputs(), 8, [11, 99], [ords("2026-10")] * 2)
    with pytest.raises(asm.AssemblyError, match="duplicate"):
        asm.assemble(inputs(), 8, [11, 11], [ords("2026-10")] * 2)
    with pytest.raises(asm.AssemblyError, match="package order"):
        asm.assemble(inputs(order=ORDER[:-1]), 14, [11], [ords("2026-10")])
    bad = inputs().snapshot.assign(phase=[2, 3, 6, 1])
    with pytest.raises(asm.AssemblyError, match="phases"):
        asm.assemble(inputs(snapshot=bad), 2, [11], [ords("2026-10")])



def test_empty_optional_sources_give_missing_features_and_strict_identifiers():
    empty = pd.DataFrame({"admin_code": pd.Series(dtype="int64"), "month": pd.Series(dtype=str), "value": pd.Series(dtype=float)})
    X, _ = asm.assemble(inputs(idp_local=empty), 2, list(ROSTER), [ords("2026-10")] * 3)
    assert X[list(vb.IDP_LOCAL_FEATURES)].isna().all().all()                       # missing, not a block (R65)
    no_acled = inputs().acled.iloc[0:0]
    X, _ = asm.assemble(inputs(acled=no_acled), 2, list(ROSTER), [ords("2026-10")] * 3)
    assert X[list(vb.ACLED_AGG_FEATURES)].isna().all().all()
    dup = pd.DataFrame({"iso3": ["AAA", "AAA"], "report_month": ["2025-06", "2025-06"], "stock": [1.0, 2.0]})
    with pytest.raises(asm.AssemblyError, match="duplicate"):
        asm.assemble(inputs(idp_national=dup), 2, [11], [ords("2026-10")])
    for admin, target, h, msg in (([11.9], [ords("2026-10")], 2, "admin_code"), ([11], [ords("2026-10") + 0.5], 2, "target"),
                                  ([11], [ords("2026-10")], 2.5, "horizon"), ([11], [ords("2026-10")], 6, "2, 8 or 14")):
        with pytest.raises(asm.AssemblyError, match=msg):
            asm.assemble(inputs(), h, admin, target)
