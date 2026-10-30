"""IPCCH regional-aggregate ACLED converter and retained weekly store (task 10-29; prd.md R3, R24-R29, R44, R53,
R55, R56). Port of the research ``staging/ipcch-update-202610/tools/build_acled_agg.py`` conventions, item by item,
working only from the fixed tables delivered with the model combination (no geometry at runtime):

* admin1 -> polygon(s): the delivered mapping table (``acled_admin1_to_poly.csv``), which already encodes the research
  precedence (explicit override first, else centroid-in-polygon, else nearest polygon <= 25 km; cp0-semantic-followup
  S1). An admin1 of a mapped country that is absent from the table is a hard refresh failure; rows of countries outside
  the table are dropped and counted (research behaviour).
* polygon-week-type: events/fatalities summed, exposure max (also over merged admin1s and override-group copies);
  Saturday-Friday weeks labelled by their Saturday start are split into months by days (x d_m / 7); exposure is the max
  over the weeks overlapping a month.
* coverage: a polygon-month is covered iff the polygon's country is in the export regions, the month is on or after the
  country's effective coverage start AND (R56) every week overlapping the month lies inside a saved declared interval
  whose declared regions include the country's ACLED region. Event rows need not exist: a covered event-free week counts
  as zero. Uncovered -> NaN (never a partial-week sum).
* exposure (from 2015-01) and share = min(max over the polygon's ACLED units of unit exposure / population of the unit's
  area (polygon, or the whole override group), 1); population <= 0 -> NaN.
* spillover: over the DISTINCT ACLED units behind the polygon's D24 neighbours, own units excluded, covered months only;
  NaN if the polygon is uncovered or no neighbour is covered.
* model area value = sum(w * v) / sum(w) over non-NaN polygon components (weights from the delivered unit weights);
  NaN before the unit's own country coverage start.

Weekly store (one ``VersionedTable`` whose HEAD record carries every saved coverage record): a validated refresh
replaces the rows of its declared interval for its declared regions and appends its coverage record in ONE commit
(R25); a refused refresh writes nothing (R27); a saved refresh stays the keep baseline even if later steps fail (R29).
The first real refresh (no saved coverage) must make every month O-12..O complete (R44); later refreshes may end
before O and are warned (R53)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Mapping

import numpy as np
import pandas as pd
import scipy.sparse as sp

from cloud.ipcch.stores import StoreError, VersionedTable

TYPES = {"Battles": "battles", "Explosions/Remote violence": "erv", "Violence against civilians": "vac"}
T = list(TYPES.values())
GROUPS = ["events", "fatalities", "exposure", "exposure_share", "spill_events", "spill_fatalities"]
COLS = [f"acled_agg_{g}_{t}" for g in GROUPS for t in T]
EXPORT_COLUMNS = ("week", "region", "country", "admin1", "event_type", "sub_event_type", "events", "fatalities",
                  "population_exposure", "disorder_type", "centroid_latitude", "centroid_longitude")
EXPORT_KEY = ["week", "country", "admin1", "event_type", "sub_event_type"]
WEEKLY_COLUMNS = ("week", "region", "country", "admin1", "type", "events", "fatalities", "exposure")
EXPOSURE_FROM = "2015-01"
LOOKBACK_MONTHS = 12


class AcledRefreshError(StoreError):
    """An ACLED refresh failed validation; retained ACLED data are unchanged (R27)."""


@dataclass
class AcledTables:
    mapping: pd.DataFrame        # acled_country, admin1, poly_ids ("|"-joined)
    polygons: pd.DataFrame       # poly_id, iso3, pop_denominator (population table order defines polygon index)
    neighbours: pd.DataFrame     # poly_id, neighbour_poly_id (D24, directed)
    coverage: pd.DataFrame       # key (iso3 or layer_group), start_month, in_regions, acled_region
    weights: pd.DataFrame        # admin_code, poly_id, weight
    unit_iso3: pd.DataFrame      # admin_code, iso3

    @classmethod
    def from_files(cls, paths: Mapping[str, str]) -> "AcledTables":
        m = pd.read_csv(paths["mapping"], dtype=str, keep_default_na=False)
        pop = pd.read_csv(paths["population"], dtype={"poly_id": str, "iso3": str}, keep_default_na=False)
        nb = pd.read_csv(paths["neighbours"], dtype=str, keep_default_na=False)
        cov = pd.read_csv(paths["coverage_start"], dtype=str, keep_default_na=False)
        cov = cov[cov["determined"] == "True"].copy()
        cov["key"] = np.where(cov["iso3"] != "", cov["iso3"], cov["layer_group"])
        w = pd.read_csv(paths["unit_weights"], dtype={"poly_id": str}, keep_default_na=False)
        ui = pd.read_csv(paths["unit_iso3"], keep_default_na=False)
        return cls(mapping=m.loc[m["poly_ids"] != "", ["acled_country", "admin1", "poly_ids"]].reset_index(drop=True),
                   polygons=pop[["poly_id", "iso3", "pop_denominator"]].sort_values("poly_id").reset_index(drop=True),
                   neighbours=nb[["poly_id", "neighbour_poly_id"]].copy(),
                   coverage=pd.DataFrame({"key": cov["key"], "start_month": cov["effective_start_ym"],
                                          "in_regions": cov["in_f1f2_regions"] == "True",
                                          "acled_region": cov["acled_region"]}).set_index("key"),
                   weights=w[["admin_code", "poly_id", "weight"]].astype({"admin_code": str}),
                   unit_iso3=ui[["admin_code", "iso3"]].astype({"admin_code": str}))

    def required_regions(self) -> set[str]:
        return set(self.coverage.loc[self.coverage["in_regions"], "acled_region"])


# --------------------------------------------------------------------------- calendar helpers


def _ord(month: str) -> int:
    y, m = (int(x) for x in month.split("-"))
    return y * 12 + m - 1


def _label(o: int) -> str:
    return f"{o // 12:04d}-{o % 12 + 1:02d}"


def _month_bounds(month: str) -> tuple[date, date]:
    o = _ord(month)
    first = date(o // 12, o % 12 + 1, 1)
    nxt = date((o + 1) // 12, (o + 1) % 12 + 1, 1)
    return first, nxt - timedelta(days=1)


def week_overlaps(month: str) -> list[date]:
    """Saturday starts of every week overlapping ``month``."""
    first, last = _month_bounds(month)
    w = first - timedelta(days=(first.weekday() - 5) % 7)
    out = []
    while w <= last:
        out.append(w)
        w += timedelta(days=7)
    return out


def month_complete(records: list[Mapping[str, Any]], region: str, month: str) -> bool:
    """R56: every week overlapping the month lies inside a saved declared interval that declares ``region``."""
    spans = [(date.fromisoformat(r["start"]), date.fromisoformat(r["end"])) for r in records if region in r["regions"]]
    return all(any(s <= w and w + timedelta(days=6) <= e for s, e in spans) for w in week_overlaps(month))


# --------------------------------------------------------------------------- refresh validation and store


def parse_export(frame: pd.DataFrame, *, start: str, end: str, regions: list[str], tables: AcledTables) -> tuple[pd.DataFrame, dict]:
    """Validated weekly rows (WEEKLY_COLUMNS) of one manually exported regional-aggregate CSV (R24, R26, R55, R56)."""
    if list(frame.columns) != list(EXPORT_COLUMNS):
        raise AcledRefreshError(f"ACLED export header must be exactly {list(EXPORT_COLUMNS)}")
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    if s.weekday() != 5 or e.weekday() != 4 or e < s:
        raise AcledRefreshError("declared interval must run from a Saturday start to a later Friday end")
    missing = sorted(tables.required_regions() - set(regions))
    if missing:
        raise AcledRefreshError(f"declared regions do not cover the mapped regions {missing} (R56)")
    a = frame.astype(str)
    try:
        wk = pd.to_datetime(a["week"], format="%Y-%m-%d")
    except ValueError as exc:
        raise AcledRefreshError(f"unparseable week: {exc}") from exc
    if (wk.dt.dayofweek != 5).any():
        raise AcledRefreshError("export weeks must be Saturday starts")
    if ((wk < pd.Timestamp(s)) | (wk + pd.Timedelta(days=6) > pd.Timestamp(e))).any():
        raise AcledRefreshError("export rows lie outside the declared interval (R26)")
    if (~a["region"].isin(regions)).any():
        raise AcledRefreshError(f"export rows outside the declared regions: {sorted(set(a['region']) - set(regions))[:5]}")
    if a.duplicated(EXPORT_KEY).any():
        raise AcledRefreshError("duplicate export rows (week, country, admin1, event_type, sub_event_type)")
    a = a[a["event_type"].isin(TYPES)].copy()
    if (a["admin1"].str.strip() == "").any():
        raise AcledRefreshError("blank admin1 rows")
    countries = set(tables.mapping["acled_country"])
    outside = a[~a["country"].isin(countries)]
    a = a[a["country"].isin(countries)]
    known = set(zip(tables.mapping["acled_country"], tables.mapping["admin1"]))
    unmapped = sorted({k for k in zip(a["country"], a["admin1"]) if k not in known})
    if unmapped:
        raise AcledRefreshError(f"unmapped admin1 (hard refresh failure, R55/R27): {unmapped[:5]}")
    try:
        out = pd.DataFrame({"week": a["week"], "region": a["region"], "country": a["country"], "admin1": a["admin1"],
                            "type": a["event_type"].map(TYPES), "events": a["events"].astype(np.int64),
                            "fatalities": a["fatalities"].astype(np.int64),
                            "exposure": a["population_exposure"].str.replace(",", "", regex=False).astype(np.float64)})
    except ValueError as exc:
        raise AcledRefreshError(f"unparseable counts: {exc}") from exc
    if (out[["events", "fatalities"]] < 0).any().any() or not np.isfinite(out["exposure"]).all() or (out["exposure"] < 0).any():
        raise AcledRefreshError("negative or non-finite counts/exposure")
    report = {"rows": int(len(frame)), "rows_kept": int(len(out)), "rows_countries_outside_table": int(len(outside)),
              "countries_outside_table": sorted(set(outside["country"]))}
    return out.reset_index(drop=True), report


def saved_weekly(table: VersionedTable) -> tuple[pd.DataFrame, list[dict], str]:
    frame, head, generation = table.read({"week": str, "region": str, "country": str, "admin1": str, "type": str})
    if frame is None:
        return pd.DataFrame(columns=list(WEEKLY_COLUMNS)), [], generation
    return frame, list(head["record"]["coverage"]), generation


def refresh(table: VersionedTable, rows: pd.DataFrame, *, start: str, end: str, regions: list[str],
            source_ref: Mapping[str, str], feature_origin: str, tables: AcledTables) -> dict[str, Any]:
    """Replace the declared interval x regions and save its coverage record in one commit (R25/R29)."""
    old, records, generation = saved_weekly(table)
    record = {"start": start, "end": end, "regions": sorted(regions), "source": dict(source_ref)}
    new_records = records + [record]
    if not records:      # R44: initialization is an ordinary refresh covering the lookback through O
        need = [_label(o) for o in range(_ord(feature_origin) - LOOKBACK_MONTHS, _ord(feature_origin) + 1)]
        gaps = [(r, m) for r in sorted(tables.required_regions()) for m in need if not month_complete(new_records, r, m)]
        if gaps:
            raise AcledRefreshError(f"the first ACLED refresh must complete months {need[0]}..{need[-1]} for every "
                                    f"mapped region (R44); incomplete {gaps[:5]}")
    wk = old["week"]
    replaced = (wk >= start) & (wk <= end) & old["region"].isin(regions)
    frame = pd.concat([old[~replaced], rows], ignore_index=True)[list(WEEKLY_COLUMNS)]
    frame = frame.sort_values(["week", "country", "admin1", "type"], kind="mergesort").reset_index(drop=True)
    return table.commit(frame, {"coverage": new_records, "last_refresh": record, "replaced_rows": int(replaced.sum())},
                        expected_generation=generation)


def coverage_end(records: list[Mapping[str, Any]], tables: AcledTables, through: str) -> str | None:
    """Last month <= ``through`` complete for every mapped region (R53/R56); None when none is."""
    regions = sorted(tables.required_regions())
    for o in range(_ord(through), _ord(through) - 600, -1):
        m = _label(o)
        if all(month_complete(records, r, m) for r in regions):
            return m
    return None


# --------------------------------------------------------------------------- weekly -> model-area monthly series


def monthly_series(weekly: pd.DataFrame, records: list[Mapping[str, Any]], tables: AcledTables, months: list[str],
                   units: list[str]) -> pd.DataFrame:
    """(admin_code, month) x 18 columns for ``units`` and ``months`` from the saved weekly rows (module docstring)."""
    poly = tables.polygons
    P, NM = len(poly), len(months)
    pidx = pd.Series(np.arange(P), index=poly["poly_id"])
    midx = pd.Series(np.arange(NM), index=months)
    lay_iso = poly["iso3"].to_numpy()
    cov = tables.coverage
    # country-level coverage: in the export regions, on/after the start month, every overlapping week declared (R56)
    complete = {(r, m): month_complete(records, r, m) for r in set(cov["acled_region"]) for m in months}
    covered = np.zeros((P, NM), dtype=bool)
    for i, iso in enumerate(lay_iso):
        row = cov.loc[iso]
        if not row["in_regions"]:
            continue
        covered[i] = [(m >= row["start_month"]) and complete[(row["acled_region"], m)] for m in months]
    mp = tables.mapping.reset_index(drop=True)
    upolys = mp["poly_ids"].str.split("|")
    NU = len(mp)
    rows_i = np.concatenate([[int(pidx[p]) for p in ps] for ps in upolys])
    cols_i = np.repeat(np.arange(NU), upolys.map(len).to_numpy())
    Mpu = sp.csr_matrix((np.ones(len(rows_i)), (rows_i, cols_i)), shape=(P, NU))
    uid = pd.Series(np.arange(NU), index=pd.MultiIndex.from_frame(mp[["acled_country", "admin1"]]))
    # unit-week-type and polygon-week-type, then week -> month
    w = weekly.assign(uid=uid.reindex(pd.MultiIndex.from_frame(weekly[["country", "admin1"]])).to_numpy())
    uw = w.groupby(["uid", "week", "type"], as_index=False).agg(events=("events", "sum"), fatalities=("fatalities", "sum"),
                                                                exposure=("exposure", "max"))
    pe = w.assign(poly_id=w["uid"].map(dict(enumerate(upolys)))).explode("poly_id")
    pw = pe.groupby(["poly_id", "week", "type"], as_index=False).agg(events=("events", "sum"), fatalities=("fatalities", "sum"),
                                                                     exposure=("exposure", "max"))
    split = []
    for wkday in sorted(set(weekly["week"])):
        days = pd.date_range(wkday, periods=7, freq="D")
        lab = days.strftime("%Y-%m")
        for m, n in zip(*np.unique(lab, return_counts=True)):
            split.append((wkday, str(m), int(n)))
    wm = pd.DataFrame(split, columns=["week", "month", "days"])

    def to_month(frame, key):
        x = frame.merge(wm, on="week")
        x = x[x["month"].isin(set(months))]
        x = x.assign(ev=x["events"] * x["days"] / 7.0, fa=x["fatalities"] * x["days"] / 7.0)
        return x.groupby([key, "month", "type"], as_index=False).agg(ev=("ev", "sum"), fa=("fa", "sum"), ex=("exposure", "max"))

    pm, um = to_month(pw, "poly_id"), to_month(uw, "uid")
    tix = {t: k for k, t in enumerate(T)}
    EV, FA, EX = (np.zeros((P, NM, 3)) for _ in range(3))
    if len(pm):
        pi, mi, ti = pidx[pm["poly_id"]].to_numpy(), midx[pm["month"]].to_numpy(), pm["type"].map(tix).to_numpy()
        EV[pi, mi, ti], FA[pi, mi, ti], EX[pi, mi, ti] = pm["ev"], pm["fa"], pm["ex"]
    nan3 = np.broadcast_to(~covered[:, :, None], EV.shape)
    for arr in (EV, FA, EX):
        arr[nan3] = np.nan
    UEV, UFA, UEX = (np.zeros((NU, NM, 3)) for _ in range(3))
    if len(um):
        ui, umi, uti = um["uid"].astype(int).to_numpy(), midx[um["month"]].to_numpy(), um["type"].map(tix).to_numpy()
        UEV[ui, umi, uti], UFA[ui, umi, uti], UEX[ui, umi, uti] = um["ev"], um["fa"], um["ex"]
    # exposure and share (D6, D25, D27)
    pre = np.array([m < EXPOSURE_FROM for m in months])
    EX[:, pre, :] = np.nan
    popv = poly["pop_denominator"].astype(float).to_numpy()
    upop = np.asarray(Mpu.T @ popv).ravel()
    with np.errstate(divide="ignore", invalid="ignore"):
        ush = UEX / upop[:, None, None]
    raw = np.zeros((P, NM, 3))
    for p_ in range(P):
        us = Mpu.indices[Mpu.indptr[p_]:Mpu.indptr[p_ + 1]]
        if len(us):
            raw[p_] = ush[us].max(axis=0)
    raw[np.isnan(EX)] = np.nan
    raw[np.broadcast_to((popv <= 0)[:, None, None], raw.shape)] = np.nan
    SH = np.minimum(raw, 1.0)
    # spillover (D23/D24)
    A = sp.csr_matrix((np.ones(len(tables.neighbours)), (pidx[tables.neighbours["poly_id"]].to_numpy(),
                                                         pidx[tables.neighbours["neighbour_poly_id"]].to_numpy())), shape=(P, P))
    ncov = A @ covered.astype(np.float64)
    spill_ok = covered & (ncov > 0)
    reach = (A @ Mpu).tocsr()
    reach.data[:] = 1.0
    R = (reach - Mpu.multiply(reach)).tocsr()
    R.eliminate_zeros()
    ucov = covered[[int(pidx[ps[0]]) for ps in upolys], :]
    SE, SF = np.full((P, NM, 3), np.nan), np.full((P, NM, 3), np.nan)
    for k in range(3):
        SE[:, :, k] = np.where(spill_ok, R @ (UEV[:, :, k] * ucov), np.nan)
        SF[:, :, k] = np.where(spill_ok, R @ (UFA[:, :, k] * ucov), np.nan)
    stack = {"events": EV, "fatalities": FA, "exposure": EX, "exposure_share": SH, "spill_events": SE, "spill_fatalities": SF}
    # unit weights and unit coverage
    W = tables.weights[tables.weights["admin_code"].isin(set(units))]
    missing = sorted(set(units) - set(W["admin_code"]))
    if missing:
        raise StoreError(f"model areas without ACLED unit weights: {missing[:5]}")
    uidx = pd.Series(np.arange(len(units)), index=units)
    Wm = sp.csr_matrix((W["weight"].astype(float).to_numpy(), (uidx[W["admin_code"]].to_numpy(),
                                                               pidx[W["poly_id"]].to_numpy())), shape=(len(units), P))
    UV = np.full((len(units), NM, len(COLS)), np.nan)
    c = 0
    for g in GROUPS:
        for k in range(3):
            X = stack[g][:, :, k]
            ok = ~np.isnan(X)
            num, den = Wm @ np.where(ok, X, 0.0), Wm @ ok.astype(np.float64)
            with np.errstate(divide="ignore", invalid="ignore"):
                UV[:, :, c] = np.where(den > 0, num / den, np.nan)
            c += 1
    uiso = tables.unit_iso3.set_index("admin_code")["iso3"]
    ustart = np.array([cov.loc[uiso[u], "start_month"] for u in units])
    before = np.array(months)[None, :] < ustart[:, None]
    UV[np.broadcast_to(before[:, :, None], UV.shape)] = np.nan
    out = pd.DataFrame(UV.reshape(len(units) * NM, len(COLS)), columns=COLS)
    out.insert(0, "month", np.tile(months, len(units)))
    out.insert(0, "admin_code", np.repeat(units, NM))
    return out
