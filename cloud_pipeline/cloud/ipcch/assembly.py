"""IPCCH H2/H8/H14 feature assembly from the retained inputs (task 10-29; R13, R32, R58, R59, R62, R64, R65).

The arithmetic is the research recipe that built the final matrices, vendored verbatim (``vendor/ipcch_compact.py``,
``vendor/ipcch_validity_feature_blocks.py``): ordinary/same-month-z/stress stems of the interim and climate grids at the
origin O = T - H, the latest two completed growing seasons (end exclusive <= first day of O+1) with the major-season flag,
static29, national IDP (latest report <= O), the 114 aggregated-ACLED columns at A = O - 1, local IDP windows at O and
the 128 AlphaEarth descriptors. Operational differences, each required by the specification:

* identifiers (R58): lat/lon are the fixed per-area coordinates of the handoff identity table; month dummies of the
  target month; year dummies year_2014..year_2026 are all zero for 2027+ targets (training raised outside 2014-2026);
* reported-phase history (R62): the latest three reports with report month <= O from the accepted snapshot, with no
  training-context family exclusions;
* GPP (R9/R57): whatever the retained GPP history holds (published months); the provider-log filter is a training-time
  simulation only;
* fixed roster (R32): every key's area must be a roster area; the caller passes the full roster for real batches.

``assemble`` returns the model-ordered matrix (the package's feature order, verified) and a per-row ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd

from cloud.ipcch.vendor import ipcch_compact as cp
from cloud.ipcch.vendor import ipcch_validity_feature_blocks as vb

INTERIM_FAMILIES = ("GPP_mean", "nightlight_mean", "WFP_Price", "food_price_index_WB", "nino34_anom",
                    "bbg_staple_food__composite_mean", "bbg_oilgas__composite_mean", "bbg_soybean_oil__composite_mean",
                    "bbg_global_food__composite_mean")
ABSENT_INTERIM = ("event_count_violence", "sum_fatalities_violence")   # compact conflict columns, dropped in this arm
FIRST_YEAR_DUMMY, LAST_YEAR_DUMMY = 2014, 2026


class AssemblyError(RuntimeError):
    pass


@dataclass
class AssemblyInputs:
    """Long retained frames (admin_code as int, month as YYYY-MM) and fixed assets."""
    climate_monthly: Mapping[str, pd.DataFrame]      # base -> admin_code, month, value
    climate_seasonal: Mapping[str, pd.DataFrame]     # base -> admin_code, season_year, season, value
    season_windows: pd.DataFrame                     # admin_code, season_year, season, gs_start_date, gs_end_date_exclusive
    interim: Mapping[str, pd.DataFrame]              # family -> admin_code, month, value
    acled: pd.DataFrame                              # admin_code, month + the 18 acled_agg_* series
    idp_national: pd.DataFrame                       # iso3, report_month, stock
    idp_local: pd.DataFrame                          # admin_code, month, value
    snapshot: pd.DataFrame                           # area_id, report_month, phase, ...
    static29: pd.DataFrame                           # admin_code + the 29 static columns (frozen order)
    descriptors: pd.DataFrame                        # admin_code + 128 AlphaEarth columns
    identity: pd.DataFrame                           # admin_code, iso3, lat, lon
    roster: tuple[int, ...]
    order: tuple[str, ...]                           # the package feature order (527)


def _ord(month) -> np.ndarray:
    s = pd.Series(month, dtype=str)
    if not s.str.fullmatch(r"\d{4}-(0[1-9]|1[0-2])").all():
        raise AssemblyError(f"months must be YYYY-MM: {sorted(set(s[~s.str.fullmatch(r'\d{4}-(0[1-9]|1[0-2])')]))[:3]}")
    return s.str[:4].astype(np.int64).to_numpy() * 12 + s.str[5:7].astype(np.int64).to_numpy() - 1


def integral(values, label: str) -> np.ndarray:
    """int64 identifiers/ordinals; non-integral, non-finite or non-numeric values fail instead of being truncated."""
    arr = np.asarray(values)
    try:
        f = arr.astype(np.float64)
    except (TypeError, ValueError) as exc:
        raise AssemblyError(f"{label} must be integers") from exc
    if arr.size and (not np.isfinite(f).all() or (f != np.round(f)).any()):
        raise AssemblyError(f"{label} must be integral, got {sorted(set(f[(~np.isfinite(f)) | (f != np.round(f))].tolist()))[:3]}")
    return f.astype(np.int64)


def validate_idp_national(frame: pd.DataFrame) -> pd.DataFrame:
    """National IDP observations (iso3, report_month, stock): one report per country-month, non-negative finite stock."""
    if list(frame.columns) != ["iso3", "report_month", "stock"]:
        raise AssemblyError(f"idp_national columns must be exactly iso3, report_month, stock: {list(frame.columns)}")
    dup = frame.duplicated(["iso3", "report_month"], keep=False)
    if dup.any():
        raise AssemblyError(f"idp_national has duplicate (iso3, report_month) {frame.loc[dup, ['iso3', 'report_month']].head(3).to_dict('records')}")
    stock = pd.to_numeric(frame["stock"], errors="raise").to_numpy(float)
    if not np.isfinite(stock).all() or (stock < 0).any():
        raise AssemblyError("idp_national stock must be finite and non-negative")
    _ord(frame["report_month"])
    return frame


def grid(frames: Mapping[str, pd.DataFrame], variables, roster) -> "cp.Grid":
    """Area x month grid over the union of the frames' areas and months (absent cells NaN, as the research grids). An
    optional source with no saved rows yields an all-NaN grid over the roster: its features are missing, never a block
    (R65)."""
    parts = []
    for v in variables:
        f = frames.get(v)
        if f is None:
            continue
        if f.duplicated(["admin_code", "month"]).any():
            raise AssemblyError(f"{v}: duplicate (admin_code, month)")
        parts.append(pd.DataFrame({"area": integral(f["admin_code"], f"{v}.admin_code"), "ord": _ord(f["month"]), "v": v,
                                   "x": pd.to_numeric(f["value"], errors="raise").to_numpy(float)}))
    long = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame({"area": [], "ord": [], "v": [], "x": []})
    if long.empty:
        return cp.Grid(np.asarray(sorted(roster), dtype=np.int64), 0, 1,
                       {v: np.full((len(roster), 1), np.nan) for v in variables})
    if np.isinf(long["x"]).any():
        raise AssemblyError("infinite source values")
    area_ids = np.sort(long["area"].unique())
    first, last = int(long["ord"].min()), int(long["ord"].max())
    values = {}
    for v in variables:
        arr = np.full((len(area_ids), last - first + 1), np.nan)
        sub = long[long["v"] == v]
        arr[np.searchsorted(area_ids, sub["area"].to_numpy()), sub["ord"].to_numpy() - first] = sub["x"].to_numpy()
        values[v] = arr
    return cp.Grid(area_ids, first, last - first + 1, values)


def identifiers(admin: np.ndarray, target: np.ndarray, identity: pd.DataFrame) -> pd.DataFrame:
    """compact.identifier_block with fixed coordinates and R58 year dummies (all zero for 2027+)."""
    ident = identity.assign(admin_code=identity["admin_code"].astype(np.int64)).set_index("admin_code")
    ll = ident[["lat", "lon"]].reindex(admin)
    if ll.isna().any().any():
        raise AssemblyError(f"missing coordinates for {int(ll.isna().any(axis=1).sum())} rows")
    years, months = target // 12, target % 12 + 1
    if years.min() < FIRST_YEAR_DUMMY:
        raise AssemblyError("target year before the first identifier year 2014")
    out = {"lat": ll["lat"].to_numpy(float), "lon": ll["lon"].to_numpy(float)}
    for m in range(1, 13):
        out[f"month_{m}"] = (months == m).astype(float)
    for y in range(FIRST_YEAR_DUMMY, LAST_YEAR_DUMMY + 1):
        out[f"year_{y}"] = (years == y).astype(float)          # 2027+ targets: every year dummy is 0 (R58)
    block = pd.DataFrame(out)
    if list(block.columns) != list(cp.IDENTIFIER_FEATURES):
        raise AssemblyError("identifier order")
    return block


def history_observations(snapshot: pd.DataFrame) -> pd.DataFrame:
    """R62 snapshot -> the research observation frame (admin_code, month_ord, reported_phase, family=-1), sorted."""
    phase = pd.to_numeric(snapshot["phase"], errors="raise")
    if not phase.isin([1, 2, 3, 4, 5]).all():
        raise AssemblyError("snapshot phases must be 1-5")
    obs = pd.DataFrame({"admin_code": snapshot["area_id"].astype(np.int64).to_numpy(), "month_ord": _ord(snapshot["report_month"]),
                        "reported_phase": phase.astype(float).to_numpy(), "family": -1})
    if obs.duplicated(["admin_code", "month_ord"]).any():
        raise AssemblyError("snapshot has duplicate area/report months")
    return obs.sort_values(["admin_code", "month_ord"], kind="mergesort").reset_index(drop=True)


def seasons_frame(inputs: AssemblyInputs) -> pd.DataFrame:
    """Every season window with the 13 saved seasonal ensembles (NaN for seasons not saved)."""
    w = inputs.season_windows.assign(admin_code=inputs.season_windows["admin_code"].astype(np.int64),
                                     season_year=inputs.season_windows["season_year"].astype(np.int64))
    key = ["admin_code", "season_year", "season"]
    for base in cp.CLIMATE_BASES:
        f = inputs.climate_seasonal.get(base)
        col = f"{base}_gs_ensmean"
        if f is None:
            w[col] = np.nan
            continue
        f = f.assign(admin_code=f["admin_code"].astype(np.int64), season_year=f["season_year"].astype(np.int64))
        w = w.merge(f[key + ["value"]].rename(columns={"value": col}), on=key, how="left", validate="one_to_one")
    return w


def assemble(inputs: AssemblyInputs, horizon: int, admin, target) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Model-ordered features for keys (admin_code, target month ordinal) at origin O = T - H."""
    h = int(integral([horizon], "horizon")[0])
    if h not in (2, 8, 14):
        raise AssemblyError(f"horizon must be 2, 8 or 14, got {h}")
    admin = integral(admin, "admin_code")
    target = integral(target, "target month ordinal")
    if admin.shape != target.shape:
        raise AssemblyError("admin and target lengths differ")
    unknown = sorted(set(admin) - set(inputs.roster))
    if unknown:
        raise AssemblyError(f"unknown modeled-area identifiers {unknown[:5]} (fixed roster, R32)")
    keys = pd.DataFrame({"area_id": admin, "year": target // 12, "month": target % 12 + 1})
    if keys.duplicated().any():
        raise AssemblyError("duplicate (area, target) keys")
    origin = target - h
    roster = inputs.roster
    interim = grid(inputs.interim, INTERIM_FAMILIES, roster)
    for c in ABSENT_INTERIM:            # dropped from this arm; present as NaN so the vendored recipe runs unchanged
        interim.values[c] = np.full((len(interim.area_ids), interim.n_months), np.nan)
    interim.values = {s: interim.values[s] for s in cp.INTERIM_SOURCES}
    climate = grid({f"{b}_month_ensmean": inputs.climate_monthly[b] for b in cp.CLIMATE_BASES}, cp.CLIMATE_SOURCES, roster)
    monthly = cp.monthly_block(interim, climate, keys, [h])[h]
    season, season_ledger = cp.completed_seasons(seasons_frame(inputs), admin, origin)
    cp.assert_season_ledger(season, season_ledger, origin)
    ident = identifiers(admin, target, inputs.identity)
    static = inputs.static29.assign(admin_code=inputs.static29["admin_code"].astype(np.int64)).set_index("admin_code")
    static = static.reindex(admin).reset_index(drop=True)
    obs = history_observations(inputs.snapshot)
    hist, hist_src, _ = vb.history_block(admin, target, h, obs)
    history = pd.DataFrame(hist, columns=list(vb.HISTORY_FEATURES))
    iso3 = inputs.identity.assign(admin_code=inputs.identity["admin_code"].astype(np.int64)).set_index("admin_code")["iso3"]
    nat = validate_idp_national(inputs.idp_national)
    idp_obs = pd.DataFrame({"iso3": nat["iso3"].astype(str).to_numpy(), "report_ord": _ord(nat["report_month"]),
                            "stock": pd.to_numeric(nat["stock"], errors="raise").to_numpy(float)}
                           ).sort_values(["iso3", "report_ord"], kind="mergesort").reset_index(drop=True)
    idp, idp_report = vb.idp_block(idp_obs, iso3.reindex(admin).to_numpy(dtype=object), origin)
    frame = pd.concat([static, monthly, season, ident, history, idp], axis=1).drop(columns=list(vb.OLD_ACLED_FEATURES))
    ae = inputs.descriptors.assign(admin_code=inputs.descriptors["admin_code"].astype(np.int64)).set_index("admin_code").reindex(admin)
    acled = grid({s: inputs.acled[["admin_code", "month", s]].rename(columns={s: "value"}) for s in vb.ACLED_AGG_SOURCES},
                 vb.ACLED_AGG_SOURCES, roster)
    acled_block, acled_cutoff = vb.acled_agg_block(acled, admin, origin)
    local = grid({vb.IDP_LOCAL_VALUE: inputs.idp_local}, (vb.IDP_LOCAL_VALUE,), roster)
    local_block, _ = vb.idp_local_block(local, admin, origin)
    X = pd.concat([frame.reset_index(drop=True), ae.reset_index(drop=True),
                   acled_block[list(vb.ACLED_AGG_FEATURES)].reset_index(drop=True),
                   local_block[list(vb.IDP_LOCAL_FEATURES)].reset_index(drop=True)], axis=1)
    if list(X.columns) != list(inputs.order):
        diff = [(i, a, b) for i, (a, b) in enumerate(zip(X.columns, inputs.order)) if a != b][:3]
        raise AssemblyError(f"assembled order differs from the package order ({len(X.columns)} vs {len(inputs.order)}): {diff}")
    if np.isinf(X.to_numpy(float)).any():
        raise AssemblyError("infinite feature values")
    ledger = pd.DataFrame({"admin_code": admin, "target_ord": target, "origin_ord": origin, "horizon": h,
                           "acled_cutoff_ord": acled_cutoff, "idp_report_ord": idp_report,
                           "history_1_source_ord": hist_src[:, 0],
                           "season_cutoff_date": season_ledger["season_cutoff_date"].to_numpy()})
    return X, ledger
