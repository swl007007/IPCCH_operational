"""IPCCH climate ensembles over the shared-folder source algorithms (task 10-29; R1, R8, R13, R33, R34, R40, R41, R43).

* 13 model bases, each with the delivered per-source columns (``{base}_month_{src}`` / ``{base}_gs_{src}``); only the
  ensemble mean enters the model. Ensemble (R34, the shared SPI/SPEI ``add_dynamic_ensemble`` rule): equal weights over
  the sources with a finite value for that area, ``n_sources`` = that count, between-source SD = population SD (ddof 0)
  only when n >= 2, else missing; one source -> mean = that source; no source -> missing. Never zero-filled.
* A provider answers one (base, source, period) with a ``SourceOutcome``: ``published`` values (NaN = legitimate per-area
  missingness, e.g. masks/no valid pixels) or ``unavailable`` (the provider definitively does not publish the period yet).
  Anything else (authentication, download, computation, malformed tables, non-finite values, missing roster areas) is a
  ``ClimateProcessingFailure`` and blocks; it is never reclassified as unavailability.
* Monthly update (R43): every month from the first saved month through O that is not saved yet is attempted, oldest first.
  Each indicator-month that has at least one published source is saved immediately (R41) and never rewritten (R8),
  including when another provider arrives later. A month with no published source stays unsaved and is a recorded
  source-level gap, except O itself: no source for O blocks real generation (R13, ``ClimateSourceMissing``).
* Seasons (R33): only seasons whose exclusive end is on or before the first day of O+1 are complete and eligible; partial
  seasons are never saved. Saved seasons are never rewritten.
* Fixed roster (R32): published tables must cover every package-roster area exactly once; out-of-roster admins the
  fixed geography declares (the 6,227th admin of the shared GEE assets, ``declared_extra``) are dropped and counted,
  never required; any other identifier is unknown and fails.
* Method identifiers (R40) bind each base to the ported shared script (path + sha256) and the spatial, outlier, SPEI-fit
  and ensemble methods; the compact ``method_id`` is stored on every saved row.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Iterable, Mapping

import numpy as np
import pandas as pd

from cloud.ipcch.stores import StoreError, VersionedTable

_MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")
_DAY = re.compile(r"\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])")

PRCP = ("chirps", "persiann", "era5land")
TEMP = ("cpc", "era5land")
SOIL = ("era5land", "gldas21")
VEG = ("terra", "aqua")
SOURCES: dict[str, tuple[str, ...]] = {
    "prcp_anom": PRCP, "prcp_z": PRCP, "rainy_days": PRCP, "cdd": PRCP,
    "tmean_anom": TEMP, "tmax_anom": TEMP, "hot_days_p95": TEMP, "gdd": TEMP, "edd": TEMP,
    "sm_z": SOIL, "spi03": PRCP, "spei03": PRCP, "evi_anom": VEG}
BASES = tuple(SOURCES)

# Shared-folder scripts the provider algorithms are ported from (IPCCH_shared_folder, sha256 at port time).
SCRIPTS: dict[str, str] = {
    "monthly/rainfall.js": "08b72faa9c852feea4d0b4b518cd9537d0af0508e804bb4bd2e43002e2938162",
    "monthly/temperature.js": "ed917c0adbc53c1313335ce25c92815e8237696a3e155efc4cecb514c10992b6",
    "monthly/soil_moisture.js": "58cfd1ca9311115657ea3b3eabf518bcbd58b61e0d5b8b6395e64f4b1de7e819",
    "monthly/ndvi_evi.js": "d586ac495e3d1779b59362d3af800bf027b7fac492432d87145994a214dd5463",
    "monthly/spi_monthly.py": "0e29ed359915840825d5d35a0ecf962639d2218c27744af012e367a8b7d854c5",
    "seasonal/rainfall.js": "73ba8ddbfbd62b0b0518bc514b5e3ebbdb07b071ca9c0bac15ecb1dc8c01e0b8",
    "seasonal/temperature.js": "3ff82a634ba92ee52dea9022958abe0cf999640ac200fa1c11a290c02f081a24",
    "seasonal/soil_moisture.js": "f701cf2b184299cf53eaa20684bf75d99acef375cf0bd4b776604e651b2ba69b",
    "seasonal/ndvi.js": "4fd5ee58dd5b86b37fc1e85fc194019f684cac29bd25cac46b24cfbd27d494c7",
    "seasonal/spi&spei.py": "fbc559792896f5dc251aceb1ad83926c0cbdf2107c713aeb14701359dea690a7"}
_FAMILY = {"prcp_anom": "rainfall", "prcp_z": "rainfall", "rainy_days": "rainfall", "cdd": "rainfall",
           "tmean_anom": "temperature", "tmax_anom": "temperature", "hot_days_p95": "temperature", "gdd": "temperature",
           "edd": "temperature", "sm_z": "soil_moisture", "evi_anom": "ndvi"}
WEIGHTING = "PIXEL_METRIC_THEN_PIXELAREA_WEIGHTED_ADMIN_MEAN"
OUTLIER = "ABS_Z_GT6_WARNING_ONLY_VALUE_KEPT"
# The two shared scripts print the same SPEI label but fit differently (monthly: plotting-position PWMs; seasonal: unbiased
# PWMs, k = -tau3, strict GLO probability); identifiers name script and function so they are never conflated (R40).
SPEI_FIT_MONTHLY = "SPEI_UBPWM_GLO_STRICT_SUPPORT_V3@monthly/spi_monthly.py:compute_spei03_monthly"
SPEI_FIT_SEASONAL = "SPEI_UBPWM_GLO_STRICT_SUPPORT_V3@seasonal/spi&spei.py:fit_glo_ubpwm+glo_probability_strict"
SEASONAL_INDEX_AGGREGATION = "MONTHLY_INDEX_EXACT_OVERLAP_DAY_WEIGHTED_MEAN|FULL_COVERAGE_0.999999|USE_FEB28"
ENSEMBLE = "EQUAL_WEIGHT_VALID_SOURCES_POPSD_DDOF0_MIN2_V1"
MONTHLY, SEASONAL = "month", "gs"

MONTH_COLUMNS = ("admin_code", "month", "value", "n_sources", "ens_sd", "method_id")
GS_KEY = ("admin_code", "season_year", "season")
GS_COLUMNS = GS_KEY + ("gs_start_date", "gs_end_date_exclusive", "value", "n_sources", "ens_sd", "method_id")


class ClimateProcessingFailure(RuntimeError):
    """A provider/computation failure: blocks the affected generation; never treated as unavailability (R13/R34)."""


class ClimateSourceMissing(RuntimeError):
    """No source publishes a required base for the feature origin O: real generation stops (R13)."""


def script_for(base: str, temporal: str) -> str:
    if base not in SOURCES or temporal not in (MONTHLY, SEASONAL):
        raise ValueError(f"unknown climate base/temporal {base!r}/{temporal!r}")
    if base in ("spi03", "spei03"):
        return "monthly/spi_monthly.py" if temporal == MONTHLY else "seasonal/spi&spei.py"
    if temporal == MONTHLY and base == "evi_anom":
        return "monthly/ndvi_evi.js"
    return f"{'monthly' if temporal == MONTHLY else 'seasonal'}/{_FAMILY[base]}.js"


def method_ids(base: str, temporal: str) -> dict[str, str]:
    """R40 identifiers recorded in batch metadata."""
    script = script_for(base, temporal)
    ids = {"script": script, "script_sha256": SCRIPTS[script], "spatial_weighting": WEIGHTING, "outlier": OUTLIER,
           "ensemble": ENSEMBLE}
    if base == "spei03":
        ids["spei_fit"] = SPEI_FIT_MONTHLY if temporal == MONTHLY else SPEI_FIT_SEASONAL
    if base in ("spi03", "spei03") and temporal == SEASONAL:
        ids["season_aggregation"] = SEASONAL_INDEX_AGGREGATION
    return ids


def method_id(base: str, temporal: str) -> str:
    """Compact identifier stored on every saved row."""
    script = script_for(base, temporal)
    return f"{script}@{SCRIPTS[script][:12]}|{ENSEMBLE}"


def table_name(base: str, temporal: str) -> str:
    """The retained table of one base: the same name the initialiser gives the accepted bundle file
    ``history/climate_{temporal}_{base}.csv`` (``initial.table_name``), so updates append to the accepted history."""
    script_for(base, temporal)
    return f"history__climate_{temporal}_{base}"


# --------------------------------------------------------------------------- provider outcomes and the ensemble


@dataclass(frozen=True)
class SourceOutcome:
    source: str
    status: str                                  # "published" | "unavailable"
    values: pd.DataFrame | None = None           # published: admin_code, value
    detail: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def roster_values(outcome: SourceOutcome, roster: Iterable[str], label: str, known: Iterable[str] = ()) -> tuple[pd.Series, int]:
    """(values indexed by the full roster, dropped rows) of one published outcome; malformed -> failure. Rows outside
    ``roster`` are dropped only for ``known`` areas (other roster areas of a season, declared fixed-source extras such as
    the 6,227th GEE admin); any other identifier is unknown and fails (R32)."""
    roster = list(roster)
    v = outcome.values
    if not isinstance(v, pd.DataFrame) or list(v.columns) != ["admin_code", "value"]:
        raise ClimateProcessingFailure(f"{label}: published values need exactly admin_code, value")
    codes = v["admin_code"].astype(str)
    try:
        vals = pd.to_numeric(v["value"], errors="raise").astype("float64")
    except (TypeError, ValueError) as exc:
        raise ClimateProcessingFailure(f"{label}: non-numeric values ({exc})") from exc
    if np.isinf(vals.to_numpy()).any():
        raise ClimateProcessingFailure(f"{label}: infinite values")
    if codes.duplicated().any():
        raise ClimateProcessingFailure(f"{label}: duplicate admin_code {sorted(set(codes[codes.duplicated()]))[:5]}")
    keep = codes.isin(roster)
    unknown = sorted(set(codes[~keep]) - set(map(str, known)))
    if unknown:
        raise ClimateProcessingFailure(f"{label}: unknown modeled-area identifiers {unknown[:5]} (R32)")
    missing = sorted(set(roster) - set(codes))
    if missing:
        raise ClimateProcessingFailure(f"{label}: published table lacks {len(missing)} roster areas {missing[:5]}")
    s = pd.Series(vals[keep].to_numpy(), index=codes[keep].to_numpy())
    return s.reindex(roster), int((~keep).sum())


def ensemble(per_source: Mapping[str, pd.Series]) -> pd.DataFrame:
    """Per area: ``value`` = equal-weight mean of finite sources, ``n_sources``, ``ens_sd`` (ddof 0, n >= 2 only)."""
    if not per_source:
        raise ValueError("ensemble needs at least one published source")
    frame = pd.DataFrame(dict(per_source))
    x = frame.to_numpy(dtype="float64")
    finite = np.isfinite(x)
    n = finite.sum(axis=1)
    total = np.where(finite, x, 0.0).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(n > 0, total / np.maximum(n, 1), np.nan)
        dev = np.where(finite, x - mean[:, None], 0.0)
        sd = np.where(n >= 2, np.sqrt((dev ** 2).sum(axis=1) / np.maximum(n, 1)), np.nan)
    return pd.DataFrame({"admin_code": frame.index.astype(str), "value": mean, "n_sources": n.astype("int64"),
                         "ens_sd": sd})


def _collect(base: str, temporal: str, period: str, outcomes: list[SourceOutcome], roster: list[str],
             known: Iterable[str] = ()) -> tuple[dict[str, pd.Series], dict[str, Any]]:
    expected = SOURCES[base]
    got = [o.source for o in outcomes]
    if sorted(got) != sorted(expected):
        raise ClimateProcessingFailure(f"{base} {period}: outcomes for {got}, expected exactly {list(expected)}")
    published, report = {}, {"published": [], "unavailable": {}, "dropped_out_of_roster": {}}
    for o in outcomes:
        label = f"{table_name(base, temporal)} {period} {o.source}"
        if o.status == "published":
            published[o.source], dropped = roster_values(o, roster, label, known)
            report["published"].append(o.source)
            report["dropped_out_of_roster"][o.source] = dropped
            if o.extra.get("produced_tables"):            # this run's producer assets behind the saved value (R10)
                report.setdefault("produced_tables", {})[o.source] = list(o.extra["produced_tables"])
        elif o.status == "unavailable":
            if o.values is not None:
                raise ClimateProcessingFailure(f"{label}: an unavailable outcome carries values")
            report["unavailable"][o.source] = o.detail
        else:
            raise ClimateProcessingFailure(f"{label}: outcome status {o.status!r} is neither published nor unavailable")
    return published, report


# --------------------------------------------------------------------------- calendar helpers


def _months(values: Iterable[Any], what: str) -> None:
    bad = sorted({repr(v) for v in values if not isinstance(v, str) or _MONTH.fullmatch(v) is None})
    if bad:
        raise StoreError(f"{what} must be canonical YYYY-MM months: {bad[:5]}")


def _ord(month: str) -> int:
    y, m = (int(x) for x in month.split("-"))
    return y * 12 + m - 1


def _label(o: int) -> str:
    return f"{o // 12:04d}-{o % 12 + 1:02d}"


def first_day_after(month: str) -> str:
    """First day of the month after ``month`` (season completeness bound, R33)."""
    o = _ord(month) + 1
    return date(o // 12, o % 12 + 1, 1).isoformat()


# --------------------------------------------------------------------------- monthly store


def _read(table: VersionedTable, columns: tuple[str, ...], dtypes: Mapping[str, Any]) -> tuple[pd.DataFrame, str]:
    frame, _, generation = table.read(dtypes)
    if frame is None:
        frame = pd.DataFrame({c: pd.Series(dtype="object") for c in columns})
    elif list(frame.columns) != list(columns):
        raise StoreError(f"{table.table}: columns {list(frame.columns)} != {list(columns)}")
    return frame, generation


def read_monthly(table: VersionedTable) -> tuple[pd.DataFrame, str]:
    return _read(table, MONTH_COLUMNS, {"admin_code": str, "month": str, "method_id": str})


def months_to_update(saved: Iterable[str], origin: str) -> list[str]:
    """R43: every month from the first saved month through O that is not saved yet, oldest first."""
    saved = set(saved)
    _months(saved | {origin}, "months")
    if not saved:
        raise StoreError("no accepted climate history: the retained store must be initialised from the accepted "
                         "delivered history (R45) before incremental updates")
    first = min(saved)
    return [_label(o) for o in range(_ord(first), _ord(origin) + 1) if _label(o) not in saved]


def _append(table: VersionedTable, frame: pd.DataFrame, rows: pd.DataFrame, keys: list[str], generation: str,
            record: Mapping[str, Any]) -> dict[str, Any]:
    clash = frame.merge(rows[keys], on=keys, how="inner")
    if len(clash):
        raise StoreError(f"{table.table}: saved values are never rewritten (R8): {clash[keys].head(5).to_dict('records')}")
    out = pd.concat([frame, rows], ignore_index=True)[list(frame.columns)]
    return table.commit(out.sort_values(keys[::-1], kind="mergesort").reset_index(drop=True), record,
                        expected_generation=generation)


Fetch = Callable[[str, str], SourceOutcome]          # (source, period) -> outcome


def update_monthly(table: VersionedTable, base: str, *, origin: str, roster: Iterable[str], fetch: Fetch,
                   declared_extra: Iterable[str] = ()) -> dict[str, Any]:
    """Attempt every unsaved month through O (oldest first); save each with >= 1 published source immediately.
    ``declared_extra``: out-of-roster admins the fixed geography declares (dropped and counted; others fail, R32)."""
    roster = sorted({str(a) for a in roster})
    extra = sorted({str(a) for a in declared_extra})
    if table.table != table_name(base, MONTHLY):
        raise StoreError(f"{table.table} is not the {base} monthly store")
    frame, _ = read_monthly(table)
    report: dict[str, Any] = {"base": base, "origin": origin, "method": method_ids(base, MONTHLY), "saved": [], "gaps": {},
                              "months": {}}
    try:
        _monthly_loop(table, base, frame, origin, roster, fetch, report, extra)
    except (ClimateProcessingFailure, ClimateSourceMissing) as exc:
        exc.climate_report = report           # months already saved in THIS base stay saved and are reported (R41)
        raise
    frame, _ = read_monthly(table)
    report["coverage_end"] = max(frame["month"]) if len(frame) else None
    return report


def _monthly_loop(table, base, frame, origin, roster, fetch, report, extra=()):
    for month in months_to_update(set(frame["month"]), origin):
        outcomes = [fetch(src, month) for src in SOURCES[base]]
        published, info = _collect(base, MONTHLY, month, outcomes, roster, extra)
        if not published:
            if month == origin:
                raise ClimateSourceMissing(f"{base}: no source publishes the feature origin {origin} "
                                           f"({info['unavailable']}); real generation stops (R13)")
            report["gaps"][month] = info["unavailable"]           # source-level gap, distinct from per-area NaN (R43)
            continue
        ens = ensemble(published)
        rows = ens.assign(month=month, method_id=method_id(base, MONTHLY))[list(MONTH_COLUMNS)]
        frame, generation = read_monthly(table)
        _append(table, frame, rows, ["admin_code", "month"], generation,
                {"action": "append", "base": base, "month": month, "method_id": method_id(base, MONTHLY), **info})
        report["saved"].append(month)
        report["months"][month] = {**info, "areas_missing": int(ens["value"].isna().sum()),
                                   "n_sources_counts": {int(k): int(v) for k, v in ens["n_sources"].value_counts().items()}}


# --------------------------------------------------------------------------- growing seasons (R33)


def read_seasonal(table: VersionedTable) -> tuple[pd.DataFrame, str]:
    frame, generation = _read(table, GS_COLUMNS, {"admin_code": str, "season": str, "gs_start_date": str,
                                                  "gs_end_date_exclusive": str, "method_id": str})
    if len(frame):
        frame["season_year"] = frame["season_year"].astype("int64")
    return frame, generation


def _real_day(value: Any) -> bool:
    if not isinstance(value, str) or _DAY.fullmatch(value) is None:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def completed_windows(windows: pd.DataFrame, origin: str) -> pd.DataFrame:
    """Season windows (admin_code, season_year, season, gs_start_date, gs_end_date_exclusive) complete by the end of O."""
    need = ["admin_code", "season_year", "season", "gs_start_date", "gs_end_date_exclusive"]
    if list(windows.columns) != need:
        raise StoreError(f"season windows need exactly {need}")
    w = windows.assign(admin_code=windows["admin_code"].astype(str), season_year=windows["season_year"].astype("int64"))
    for c in ("gs_start_date", "gs_end_date_exclusive"):
        bad = [v for v in w[c] if not _real_day(v)]
        if bad:
            raise StoreError(f"season windows: {c} must be real YYYY-MM-DD dates, got {bad[:3]}")
    if (w["gs_end_date_exclusive"] <= w["gs_start_date"]).any():
        raise StoreError("season windows must end after they start")
    if w.duplicated(list(GS_KEY)).any():
        raise StoreError("duplicate season windows")
    _months([origin], "origin")
    return w[w["gs_end_date_exclusive"] <= first_day_after(origin)].reset_index(drop=True)


def pending_seasons(table: VersionedTable, windows: pd.DataFrame, origin: str) -> pd.DataFrame:
    """The completed season windows whose (area, season_year, season) is not saved yet (R33/R8)."""
    done = completed_windows(windows, origin)
    frame, _ = read_seasonal(table)
    saved = set(map(tuple, frame[list(GS_KEY)].astype({"season_year": "int64"}).itertuples(index=False)))
    return done[[(a, int(y), s) not in saved for a, y, s in done[list(GS_KEY)].itertuples(index=False)]]


GsFetch = Callable[[str, int, str, pd.DataFrame], SourceOutcome]   # (source, season_year, season, windows) -> outcome


def update_seasonal(table: VersionedTable, base: str, *, origin: str, roster: Iterable[str], windows: pd.DataFrame,
                    fetch: GsFetch, declared_extra: Iterable[str] = ()) -> dict[str, Any]:
    """Save every completed, unsaved (season_year, season) once, over the areas whose window completed (R33/R41/R8)."""
    roster = sorted({str(a) for a in roster})
    known = sorted(set(roster) | {str(a) for a in declared_extra})
    if table.table != table_name(base, SEASONAL):
        raise StoreError(f"{table.table} is not the {base} seasonal store")
    unknown = sorted(set(completed_windows(windows, origin)["admin_code"]) - set(roster))
    if unknown:
        raise StoreError(f"season windows for unknown modeled areas {unknown[:5]} (R32)")
    todo = pending_seasons(table, windows, origin)
    report: dict[str, Any] = {"base": base, "origin": origin, "method": method_ids(base, SEASONAL), "saved": [], "gaps": {}}
    try:
        _seasonal_loop(table, base, todo, fetch, report, known)
    except ClimateProcessingFailure as exc:
        exc.climate_report = report
        raise
    return report


def _seasonal_loop(table, base, todo, fetch, report, known=()):
    for (year, season), win in todo.groupby(["season_year", "season"], sort=True):
        areas = sorted(win["admin_code"])
        win = win.sort_values("admin_code").reset_index(drop=True)
        outcomes = [fetch(src, int(year), season, win) for src in SOURCES[base]]
        published, info = _collect(base, SEASONAL, f"{year}-{season}", outcomes, areas, known)
        if not published:
            report["gaps"][f"{year}-{season}"] = info["unavailable"]
            continue
        ens = ensemble(published).merge(win, on="admin_code")
        rows = ens.assign(method_id=method_id(base, SEASONAL))[list(GS_COLUMNS)]
        frame, generation = read_seasonal(table)
        _append(table, frame, rows, list(GS_KEY), generation,
                {"action": "append", "base": base, "season_year": int(year), "season": season,
                 "method_id": method_id(base, SEASONAL), **info})
        report["saved"].append(f"{year}-{season}")
