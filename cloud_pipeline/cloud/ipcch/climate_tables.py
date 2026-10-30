"""Table-based IPCCH climate providers (task 10-29; R1, R13, R34, R40, R43): the shared scripts that compute from
precomputed admin-level Earth Engine tables rather than rasters.

* ``monthly/ndvi_evi.js`` (sha256 d586ac49...): evi_anom per sensor (terra, aqua) = overlap-day-weighted mean of 16-day
  composite anomalies (current admin mean minus the same-slot 2003-2020 admin mean) over the calendar month, kept only at
  full coverage (>= 0.999999); a null/absent property contributes value 0 and valid 0. Terra slots start on day-of-year
  1, Aqua on 9; slot 23 ends on the next year's first slot. The script does this arithmetic in EE on the S2E3 tables; here
  the same arithmetic runs in pandas on the downloaded tables.
* ``monthly/spi_monthly.py`` (sha256 0e29ed35...): spi03/spei03 per precipitation source from the S2C3 admin monthly
  precipitation tables and the ERA5-Land FAO-56 ET0 tables (PATCH32 fills missing ET0 only), computed with the retained
  numerics of ``spi_spei``. Absent month properties are NaN, as in the script's ``normalize_monthly_table``.

Availability: a month is published by a source when the source's table(s) carry the month's properties (NDVI: every
overlapping composite of the current-year table; SPI: the month's precipitation column; SPEI additionally the month's
ET0); otherwise ``unavailable``. The producers of the S2E3/S2C3 tables are not in the shared folder: their asset
references are configurable and checked read-only; unreadable baseline/static tables fail clearly.

Tables produced by this run (task 10-30, ``TableRefs.produced``): each replaces its existing chunk/year table outright
(exactly one asset per chunk, never joined with the old one) and carries its producer's source-calendar completeness
(``ProducedTable.periods``). The seasonal scripts mask every incomplete source month in the exported chunk, so an
unpublished month is an absent/all-null column indistinguishable by its values from a published month whose polygons are
all masked: for produced chunks availability therefore comes from the declared completeness (incomplete -> unavailable
even with a column; complete -> published even if every area is masked), and missing/contradictory metadata is a
processing failure. Static/history tables keep the column-presence rule above.

PATCH32 (``S2C3_ET0_PATCH32``) covers only its buffered polygons: absent patch rows are NaN, the primary tables still need
every requested admin, and the patch fills only missing primary ET0 (``spi_spei.apply_et0_patch``).
"""

from __future__ import annotations

import calendar as pycalendar
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Protocol

import numpy as np
import pandas as pd

from cloud.ipcch import spi_spei
from cloud.ipcch.climate import ClimateProcessingFailure, SourceOutcome
from cloud.ipcch.climate_ee import DEFAULT_ROOT

FULL_COVERAGE_TOLERANCE = 0.999999
SENSOR_FIRST_DOY = {"terra": 1, "aqua": 9}
SENSOR_LABELS = {"terra": "TERRA", "aqua": "AQUA"}
SPI_SOURCES = {"chirps": "CHIRPS", "persiann": "PERSIANN", "era5land": "ERA5LAND"}
YEAR_CHUNKS = ((1990, 1995), (1996, 2001), (2002, 2007), (2008, 2013), (2014, 2019), (2020, 2026))


class TableBackend(Protocol):
    def missing_assets(self, asset_ids: list[str]) -> list[str]: ...
    def read_asset_table(self, asset_id: str) -> pd.DataFrame: ...       # FeatureCollection properties, no geometry


@dataclass(frozen=True)
class ProducedTable:
    """One table this run produced: its exact asset and the producer's source-calendar completeness per column period
    (``YYYYMM`` -> month complete, for every month of a PRCP/ET0/PATCH32 chunk; ``YYYYMMDD`` -> True, for every
    composite in a VI current-year table)."""
    asset_id: str
    periods: Mapping[str, bool]


@dataclass(frozen=True)
class TableRefs:
    root: str = DEFAULT_ROOT
    vi_baseline: str = "S2E3_VI_BASE_ADMIN_2003_2020_{label}_CMG_P{part:02d}_V3"
    vi_current: str = "S2E3_VI_CURRENT_ADMIN_{label}_Y{year}_CMG_V3"
    prcp: str = "S2C3_DROUGHT_ADMIN_PRCP_{label}_Y{a}_{b}_V3"
    et0: str = "S2C3_DROUGHT_ADMIN_ET0_FAO56_Y{a}_{b}_V3"
    et0_patch: str = "S2C3_ET0_PATCH32_Y{a}_{b}_V2"
    year_chunks: tuple[tuple[int, int], ...] = YEAR_CHUNKS
    produced: Mapping[str, ProducedTable] = field(default_factory=dict)   # existing basename -> this run's table

    def __post_init__(self):
        ids = [t.asset_id for t in self.produced.values() if isinstance(t, ProducedTable)]
        if len(set(ids)) != len(ids):
            raise ClimateProcessingFailure(f"produced tables share an asset: {sorted(ids)}")
        for name, table in self.produced.items():
            if not isinstance(table, ProducedTable):
                raise ClimateProcessingFailure(f"produced {name}: not a ProducedTable")
            kind, years, _ = self.family(name)
            if not isinstance(table.asset_id, str) or not table.asset_id.startswith("projects/") \
                    or table.asset_id == self.root + name:
                raise ClimateProcessingFailure(f"produced {name}: {table.asset_id!r} is not a new full asset id")
            _check_periods(name, kind, years, table.periods)

    def family(self, name: str) -> tuple[str, tuple[int, int], str | None]:
        """(kind, years, field prefix): ("vi", (year, year), None) for a VI current-year table (its field is the consuming
        index), ("month", chunk, "prcp"|"et0") for a PRCP or ET0/PATCH32 chunk table; other names (VI baselines,
        unknown) cannot be produced."""
        for label in SENSOR_LABELS.values():
            pattern = re.escape(self.vi_current.format(label=label, year="YEAR")).replace("YEAR", r"(\d{4})")
            m = re.fullmatch(pattern, name)
            if m:
                return "vi", (int(m[1]), int(m[1])), None
        for a, b in self.year_chunks:
            if name in [self.prcp.format(label=lab, a=a, b=b) for lab in SPI_SOURCES.values()]:
                return "month", (a, b), "prcp"
            if name in (self.et0.format(a=a, b=b), self.et0_patch.format(a=a, b=b)):
                return "month", (a, b), "et0"
        raise ClimateProcessingFailure(f"{name!r} is not a producible VI current-year or drought chunk table")

    def asset(self, name: str) -> str:
        if name in self.produced:                       # this run's table replaces the existing one (never joined)
            return self.produced[name].asset_id
        return name if name.startswith("projects/") else self.root + name

    def produced_asset(self, asset_id: str) -> tuple[str, ProducedTable] | None:
        for name, table in self.produced.items():
            if table.asset_id == asset_id:
                return name, table
        return None


def _check_periods(name: str, kind: str, years: tuple[int, int], periods: Any) -> None:
    if not isinstance(periods, Mapping) or not periods:
        raise ClimateProcessingFailure(f"produced {name}: no source-calendar completeness metadata")
    bad = [k for k, v in periods.items() if not isinstance(k, str) or not isinstance(v, bool)]
    if bad:
        raise ClimateProcessingFailure(f"produced {name}: malformed completeness entries {bad[:3]}")
    if kind == "month":                                 # the producer declares every month of the chunk
        want = {f"{y}{m:02d}" for y in range(years[0], years[1] + 1) for m in range(1, 13)}
        if set(periods) != want:
            raise ClimateProcessingFailure(f"produced {name}: completeness must declare exactly the chunk's months "
                                           f"(missing {sorted(want - set(periods))[:3]}, extra {sorted(set(periods) - want)[:3]})")
        return
    for tag, complete in periods.items():               # VI: the composites published in that year's table
        try:
            day = date(int(tag[:4]), int(tag[4:6]), int(tag[6:])) if re.fullmatch(r"\d{8}", tag) else None
        except ValueError:
            day = None
        if day is None or day.year != years[0] or complete is not True:
            raise ClimateProcessingFailure(f"produced {name}: composite entry {tag!r}={complete!r} is not a published "
                                           f"{years[0]} composite date")


def check_produced(frame: pd.DataFrame, name: str, table: ProducedTable, refs: TableRefs, index: str | None = None) -> None:
    """A produced table's schema must agree with its family and declared completeness: period fields only of the
    family's own kind (PRCP ``prcp``, ET0/PATCH32 ``et0``; VI fields of declared composites), every period field
    declared, the consumed field present for every complete month/published composite (VI: ``{index}``), and no value
    in an incomplete month (the producer masks it). Spatially masked (NaN) cells of complete periods are valid."""
    kind, _, prefix = refs.family(name)
    if kind == "vi":
        if index is None:
            raise ClimateProcessingFailure(f"produced {name}: a VI table is checked against its consuming index")
        pattern, prefix = re.compile(r"(evi|ndvi|used1km)_(\d{8})_mean"), index
    else:
        pattern = re.compile(r"(prcp|et0)_(\d{6})_mean")
    fields = {}
    for col in frame.columns:
        m = pattern.fullmatch(str(col))
        if m:
            if kind == "month" and m[1] != prefix:
                raise ClimateProcessingFailure(f"produced {name}: field {col} is not a {prefix} field")
            fields.setdefault(m[2], set()).add(m[1])
    undeclared = sorted(set(fields) - set(table.periods))
    if undeclared:
        raise ClimateProcessingFailure(f"produced {name}: columns for undeclared periods {undeclared[:3]}")
    for period, complete in table.periods.items():
        col = f"{prefix}_{period}_mean"
        if complete and col not in frame.columns:
            raise ClimateProcessingFailure(f"produced {name}: period {period} declared complete but has no {col}")
        if not complete and col in frame.columns and np.isfinite(strict_numeric(frame[col], col)).any():
            raise ClimateProcessingFailure(f"produced {name}: period {period} declared incomplete but carries values")


BASELINE_END = "2020-12"          # every fit axis spans the complete 1991-2020 baseline, whatever the target month


def input_months(first: str, last: str) -> list[str]:
    """YYYY-MM input months of the 03 indices for periods first..last: each month's 3-month accumulation reads its two
    preceding months (``spi_spei.rolling_three_month_sum``)."""
    start = (pd.Period(first, "M") - 2).strftime("%Y-%m")
    return [d.strftime("%Y-%m") for d in spi_spei.month_axis(start, last)]


def strict_numeric(values, label: str) -> np.ndarray:
    """Numeric table values; blank/null -> NaN (legitimate missingness); any other non-numeric text is a failure."""
    s = pd.Series(values)
    num = pd.to_numeric(s, errors="coerce")
    bad = num.isna() & s.notna() & (s.astype(str).str.strip() != "")
    if bad.any():
        raise ClimateProcessingFailure(f"{label}: non-numeric values {sorted(set(s[bad].astype(str)))[:3]}")
    return num.to_numpy(float)


def require_admins(table: pd.DataFrame, admins, label: str) -> None:
    absent = sorted(set(map(str, admins)) - set(table["admin_code"].astype(str)))
    if absent:
        raise ClimateProcessingFailure(f"{label}: table lacks {len(absent)} required admins {absent[:5]}")


# --------------------------------------------------------------------------- monthly/ndvi_evi.js


def observation_interval(sensor: str, year: int, slot: int) -> tuple[datetime, datetime, str]:
    """ndvi_evi.js observationInterval: nominal 16-day composite interval (UTC) and its YYYYMMDD tag."""
    first = SENSOR_FIRST_DOY[sensor]
    start = datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=first + (slot - 1) * 16 - 1)
    end = start + timedelta(days=16) if slot < 23 else datetime(year + 1, 1, 1, tzinfo=timezone.utc) + timedelta(days=first - 1)
    return start, end, start.strftime("%Y%m%d")


def month_plan(sensor: str, year: int, month: int) -> list[dict[str, Any]]:
    """ndvi_evi.js buildMonthPlan: every (calendar year in {y-1, y}, slot) interval overlapping the month, with overlap
    days; the planned days must tile the month."""
    ms = datetime(year, month, 1, tzinfo=timezone.utc)
    me = datetime(year + (month == 12), 1 if month == 12 else month + 1, 1, tzinfo=timezone.utc)
    parts = []
    for cy in (year - 1, year):
        for slot in range(1, 24):
            s, e, tag = observation_interval(sensor, cy, slot)
            days = max(0.0, (min(me, e) - max(ms, s)).total_seconds() / 86400)
            if days > 0:
                parts.append({"calendar_year": cy, "slot": slot, "days": days, "tag": tag})
    if abs(sum(p["days"] for p in parts) - (me - ms).days) > 1e-9:
        raise ClimateProcessingFailure(f"invalid monthly interval tiling {sensor} {year}-{month:02d}")
    return parts


def monthly_vi(table: pd.DataFrame, sensor: str, index: str, year: int, month: int) -> pd.DataFrame:
    """ndvi_evi.js calculateMonthlyIndex on a joined admin table (baseline + current-year properties)."""
    parts = month_plan(sensor, year, month)
    duration = pycalendar.monthrange(year, month)[1]
    weighted = np.zeros(len(table))
    covered = np.zeros(len(table))
    composites = np.zeros(len(table))
    for p in parts:
        def prop(name):
            v = strict_numeric(table[name], name) if name in table.columns else np.full(len(table), np.nan)
            ok = np.isfinite(v)
            return np.where(ok, v, 0.0), ok.astype(float)
        cur, cur_ok = prop(f"{index}_{p['tag']}_mean")
        base, base_ok = prop(f"{index}_base_s{p['slot']:02d}_mean")
        valid = cur_ok * base_ok
        valid_days = p["days"] * valid
        weighted += (cur - base) * valid_days
        covered += valid_days
        composites += valid
    coverage = np.clip(covered / max(duration, 1), 0, 1)
    complete = coverage >= FULL_COVERAGE_TOLERANCE
    mean = weighted / np.maximum(covered, 1)
    return pd.DataFrame({"admin_code": table["admin_code"].astype(str).to_numpy(), "value": np.where(complete, mean, np.nan),
                         "valid_days": covered, "coverage": coverage, "contributing_composites": composites})


@dataclass
class VegetationProvider:
    """evi_anom monthly per sensor (``climate.update_monthly`` fetch for base evi_anom)."""
    backend: TableBackend
    refs: TableRefs = field(default_factory=TableRefs)
    index: str = "evi"
    tables: dict = field(default_factory=dict)
    admins: list | None = None                     # roster: every one must be present in the joined tables

    def _read(self, asset):
        if asset not in self.tables:
            self.tables[asset] = _read_checked(self.backend, self.refs, asset, self.index)
        return self.tables[asset]

    def fetch(self, sensor: str, month: str) -> SourceOutcome:
        if sensor not in SENSOR_LABELS:
            raise ClimateProcessingFailure(f"unknown vegetation sensor {sensor}")
        y, m = (int(x) for x in month.split("-"))
        label = SENSOR_LABELS[sensor]
        base_ids = [self.refs.asset(self.refs.vi_baseline.format(label=label, part=k)) for k in range(1, 5)]
        missing = self.backend.missing_assets(base_ids)
        if missing:
            raise ClimateProcessingFailure(f"unreadable S2E3 baseline tables (configure TableRefs): {missing}")
        parts = month_plan(sensor, y, m)
        years = sorted({p["calendar_year"] for p in parts})
        cur_ids = {cy: self.refs.asset(self.refs.vi_current.format(label=label, year=cy)) for cy in years}
        absent = _absent_unproduced(self.backend, self.refs, list(cur_ids.values()))
        if absent:
            return SourceOutcome(sensor, "unavailable", detail=f"current S2E3 tables not available: {absent}")
        joined = None
        for asset in base_ids:
            t = self._read(asset)
            joined = t if joined is None else pd.concat([joined, t], ignore_index=True)
        required = self.admins if self.admins is not None else sorted(set(joined["admin_code"].astype(str)))
        require_admins(joined, required, f"S2E3 baseline {label}")
        joined = joined.drop_duplicates("admin_code", keep="first").set_index("admin_code")
        for cy in years:                        # left values win on key collision (combine(..., false))
            cur_table = self._read(cur_ids[cy])
            require_admins(cur_table, required, f"S2E3 current {label} {cy}")      # before the join: never NaN by absence
            cur = cur_table.set_index("admin_code")
            joined = joined.join(cur[[c for c in cur.columns if c not in joined.columns]], how="left")
        need = [f"{self.index}_{p['tag']}_mean" for p in parts]
        lacking = [c for c in need if c not in joined.columns]
        if lacking:
            return SourceOutcome(sensor, "unavailable", detail=f"composites not yet in the current tables: {lacking}")
        out = monthly_vi(joined.reset_index(), sensor, self.index, y, m)
        return SourceOutcome(sensor, "published", out[["admin_code", "value"]],
                             extra={"incomplete_areas": int(out["value"].isna().sum())})


# --------------------------------------------------------------------------- monthly/spi_monthly.py


def _read_checked(backend: TableBackend, refs: TableRefs, asset: str, index: str | None = None) -> pd.DataFrame:
    try:
        frame = backend.read_asset_table(asset)
    except Exception as exc:
        raise ClimateProcessingFailure(f"reading {asset} failed: {type(exc).__name__}: {exc}") from exc
    produced = refs.produced_asset(asset)
    if produced is not None:
        check_produced(frame, produced[0], produced[1], refs, index)
    return frame


def _absent_unproduced(backend: TableBackend, refs: TableRefs, ids: list[str]) -> list[str]:
    """Definitively absent ids; a table this run produced must exist (a completed export is not unavailability)."""
    absent = backend.missing_assets(ids)
    lost = [a for a in absent if refs.produced_asset(a) is not None]
    if lost:
        raise ClimateProcessingFailure(f"tables produced by this run are not readable: {lost}")
    return absent


def _wide_month_matrix(frames: list[pd.DataFrame], prefix: str, months: pd.DatetimeIndex, admins: list[str], *,
                       sparse: bool = False) -> np.ndarray:
    """``{prefix}_{YYYYMM}_mean`` columns of the outer-merged year-chunk tables as an admin x month matrix; absent
    month properties are NaN (normalize_monthly_table). ``sparse`` (PATCH32 only): the table need not cover every
    requested admin - absent rows are NaN and rows outside ``admins`` are ignored; duplicates/non-numeric still fail."""
    wide = None
    for f in frames:
        if "admin_code" not in f.columns:
            raise ClimateProcessingFailure(f"{prefix} table has no admin_code")
        if not sparse:
            require_admins(f, admins, f"{prefix} table")
        f = f.assign(admin_code=f["admin_code"].astype(str)).set_index("admin_code")
        if f.index.duplicated().any():
            raise ClimateProcessingFailure(f"{prefix} table has duplicate admin_code")
        wide = f if wide is None else wide.join(f[[c for c in f.columns if c not in wide.columns]], how="outer")
    cols = [f"{prefix}_{d.year}{d.month:02d}_mean" for d in months]
    aligned = wide.reindex(admins)
    return np.column_stack([strict_numeric(aligned[c], c) if c in aligned.columns
                            else np.full(len(admins), np.nan) for c in cols])


@dataclass
class DroughtProvider:
    """spi03/spei03 monthly per precipitation source (fetch for base spi03 or spei03)."""
    backend: TableBackend
    admins: list[str]
    refs: TableRefs = field(default_factory=TableRefs)
    tables: dict = field(default_factory=dict)
    results: dict = field(default_factory=dict)

    def _chunks(self, template, **kw):
        return [self.refs.asset(template.format(a=a, b=b, **kw)) for a, b in self.refs.year_chunks]

    def _read_all(self, ids):
        missing = self.backend.missing_assets(ids)
        if missing:
            raise ClimateProcessingFailure(f"unreadable S2C3 tables (configure TableRefs): {missing}")
        out = []
        for i in ids:
            if i not in self.tables:
                self.tables[i] = _read_checked(self.backend, self.refs, i)
            out.append(self.tables[i])
        return out

    def _month_published(self, template: str, prefix: str, month: str, frames, **kw) -> tuple[bool, bool]:
        """(produced, published) of one month of one table family: a chunk this run produced answers from its declared
        completeness; static/history chunks keep the column-presence rule."""
        token = month.replace("-", "")
        for a, b in self.refs.year_chunks:
            if a <= int(token[:4]) <= b and template.format(a=a, b=b, **kw) in self.refs.produced:
                return True, self.refs.produced[template.format(a=a, b=b, **kw)].periods[token]
        return False, any(f"{prefix}_{token}_mean" in f.columns for f in frames)

    def _window_published(self, template: str, prefix: str, window: list[str], frames, **kw) -> tuple[bool, bool]:
        """(any produced, published) over the input months an index period consumes (last = the period's own month):
        the last month by its own rule, and every produced month of the window complete. Static months keep the
        unchanged last-month-only rule."""
        states = [self._month_published(template, prefix, m, frames, **kw) for m in window]
        return any(prod for prod, _ in states), states[-1][1] and all(pub for prod, pub in states if prod)

    def _availability(self, source: str, window: list[str], prcp_frames, et0_frames, patch_frames) -> tuple[bool, bool]:
        """(precipitation, ET0) published for the input months ``window``. Static tables: PATCH32 alone can supply the
        last month's ET0 column (unchanged rule); once either ET0 family is produced, both the primary and the patch must
        be complete, so a partially filled month is never published and saved. Only the consuming source's input months
        gate availability; other months of a produced chunk (including fit-baseline months) keep the upstream masked/NaN
        missingness handled by the fits."""
        _, prcp_has = self._window_published(self.refs.prcp, "prcp", window, prcp_frames, label=SPI_SOURCES[source])
        e_prod, et0_has = self._window_published(self.refs.et0, "et0", window, et0_frames)
        p_prod, patch_has = self._window_published(self.refs.et0_patch, "et0", window, patch_frames)
        return prcp_has, (et0_has and patch_has) if (e_prod or p_prod) else (et0_has or patch_has)

    def _compute(self, source, month):
        months = spi_spei.month_axis("1990-01", max(month, BASELINE_END))     # complete baseline even for old targets
        pos = months.get_loc(pd.Timestamp(f"{month}-01"))
        prcp_frames = self._read_all(self._chunks(self.refs.prcp, label=SPI_SOURCES[source]))
        et0_frames = self._read_all(self._chunks(self.refs.et0))
        patch_frames = self._read_all(self._chunks(self.refs.et0_patch))
        prcp_has, et0_has = self._availability(source, input_months(month, month), prcp_frames, et0_frames, patch_frames)
        prcp = _wide_month_matrix(prcp_frames, "prcp", months, self.admins)
        et0 = _wide_month_matrix(et0_frames, "et0", months, self.admins)
        et0, filled = spi_spei.apply_et0_patch(et0, _wide_month_matrix(patch_frames, "et0", months, self.admins,
                                                                       sparse=True))
        spi = spi_spei.compute_spi03_monthly(prcp, months)[:, pos] if prcp_has else None
        spei = spi_spei.compute_spei03_monthly(prcp, et0, months)[:, pos] if prcp_has and et0_has else None
        return {"spi03": spi, "spei03": spei, "prcp_has": prcp_has, "et0_has": et0_has, "et0_patch_filled": filled}

    def fetch(self, base: str, source: str, month: str) -> SourceOutcome:
        if base not in ("spi03", "spei03") or source not in SPI_SOURCES:
            raise ClimateProcessingFailure(f"no drought provider for {base}/{source}")
        key = (source, month)
        if key not in self.results:
            self.results[key] = self._compute(source, month)
        r = self.results[key]
        if r[base] is None:
            why = "precipitation" if not r["prcp_has"] else "ET0"
            return SourceOutcome(source, "unavailable", detail=f"S2C3 {why} table has no published {month}")
        return SourceOutcome(source, "published", pd.DataFrame({"admin_code": self.admins, "value": r[base]}),
                             extra={"et0_patch_filled": r["et0_patch_filled"]})

    def bound(self, base: str) -> Callable[[str, str], SourceOutcome]:
        return lambda source, month: self.fetch(base, source, month)


# --------------------------------------------------------------------------- seasonal/ndvi.js


def season_vi(table: pd.DataFrame, sensor: str, index: str, windows: pd.DataFrame, season_year: int) -> pd.DataFrame:
    """ndvi.js makeSeasonRow: overlap-day-weighted anomaly of every (calendar year in {Y-1, Y}, slot) composite with the
    exact season window; value only at full coverage (>= 0.999999), otherwise MISSING (no PARTIAL_DATA)."""
    t = table.assign(admin_code=table["admin_code"].astype(str)).set_index("admin_code")
    w = windows.assign(admin_code=windows["admin_code"].astype(str)).set_index("admin_code").reindex(t.index)
    start = pd.to_datetime(w["gs_start_date"]).dt.tz_localize("UTC")
    end = pd.to_datetime(w["gs_end_date_exclusive"]).dt.tz_localize("UTC")
    duration = (end - start).dt.days.to_numpy(float)
    weighted = np.zeros(len(t)); covered = np.zeros(len(t)); composites = np.zeros(len(t))
    for cy in (season_year - 1, season_year):
        for slot in range(1, 24):
            s, e, tag = observation_interval(sensor, cy, slot)
            s, e = pd.Timestamp(s), pd.Timestamp(e)
            overlap = np.maximum(0.0, (np.minimum(end, e) - np.maximum(start, s)).dt.total_seconds().to_numpy() / 86400)

            def prop(name):
                v = strict_numeric(t[name], name) if name in t.columns else np.full(len(t), np.nan)
                ok = np.isfinite(v)
                return np.where(ok, v, 0.0), ok.astype(float)
            cur, cur_ok = prop(f"{index}_{tag}_mean")
            base, base_ok = prop(f"{index}_base_s{slot:02d}_mean")
            valid = cur_ok * base_ok
            vw = overlap * valid
            weighted += (cur - base) * vw
            covered += vw
            composites += (overlap > 0) * valid
    coverage = np.clip(covered / np.maximum(duration, 1), 0, 1)
    full = coverage >= FULL_COVERAGE_TOLERANCE
    return pd.DataFrame({"admin_code": t.index.to_numpy(), "value": np.where(full, weighted / np.maximum(covered, 1), np.nan),
                         "coverage": coverage, "status": np.where(covered == 0, "MISSING_DATA", np.where(full, "COMPLETE", "MISSING_DATA")),
                         "contributing_composites": composites})


@dataclass
class SeasonalVegetationProvider(VegetationProvider):
    """evi_anom growing-season per sensor (``climate.update_seasonal`` fetch)."""

    def fetch_season(self, sensor: str, season_year: int, season: str, windows: pd.DataFrame) -> SourceOutcome:
        label = SENSOR_LABELS[sensor]
        base_ids = [self.refs.asset(self.refs.vi_baseline.format(label=label, part=k)) for k in range(1, 5)]
        missing = self.backend.missing_assets(base_ids)
        if missing:
            raise ClimateProcessingFailure(f"unreadable S2E3 baseline tables (configure TableRefs): {missing}")
        cur_ids = {cy: self.refs.asset(self.refs.vi_current.format(label=label, year=cy)) for cy in (season_year - 1, season_year)}
        absent = _absent_unproduced(self.backend, self.refs, list(cur_ids.values()))
        if absent:
            return SourceOutcome(sensor, "unavailable", detail=f"current S2E3 tables not available: {absent}")
        base = pd.concat([self._read(a) for a in base_ids], ignore_index=True)
        required = sorted(set(windows["admin_code"].astype(str)))
        require_admins(base, required, f"S2E3 baseline {label}")
        joined = base.drop_duplicates("admin_code").set_index("admin_code")
        for cy in sorted(cur_ids):
            cur_table = self._read(cur_ids[cy])
            require_admins(cur_table, required, f"S2E3 current {label} {cy}")      # before the join
            cur = cur_table.set_index("admin_code")
            joined = joined.join(cur[[c for c in cur.columns if c not in joined.columns]], how="left")
        start = pd.to_datetime(windows["gs_start_date"]).min()
        end = pd.to_datetime(windows["gs_end_date_exclusive"]).max()
        need = [f"{self.index}_{tag}_mean" for cy in cur_ids for slot in range(1, 24)
                for s, e, tag in [observation_interval(sensor, cy, slot)]
                if pd.Timestamp(s).tz_localize(None) < end and pd.Timestamp(e).tz_localize(None) > start]
        lacking = [c for c in need if c not in joined.columns]
        if lacking:
            return SourceOutcome(sensor, "unavailable", detail=f"composites not yet in the current tables: {lacking[:3]}")
        rows = joined.reset_index()
        rows = rows[rows["admin_code"].astype(str).isin(set(windows["admin_code"].astype(str)))]
        out = season_vi(rows, sensor, self.index, windows, season_year)
        return SourceOutcome(sensor, "published", out[["admin_code", "value"]].reset_index(drop=True),
                             extra={"incomplete_areas": int(out["value"].isna().sum())})

    def bound_season(self):
        return lambda sensor, year, season, windows: self.fetch_season(sensor, year, season, windows)


# --------------------------------------------------------------------------- seasonal/spi&spei.py


@dataclass
class SeasonalDroughtProvider(DroughtProvider):
    """spi03_gs/spei03_gs per precipitation source: the seasonal script's own monthly fits (vendored) aggregated over the
    exact season plan (``spi_spei_seasonal``); never the monthly fit."""

    def fetch_season(self, base: str, source: str, season_year: int, season: str, windows: pd.DataFrame) -> SourceOutcome:
        from cloud.ipcch import spi_spei_seasonal as sss
        if base not in ("spi03", "spei03") or source not in SPI_SOURCES:
            raise ClimateProcessingFailure(f"no seasonal drought provider for {base}/{source}")
        end = (pd.to_datetime(windows["gs_end_date_exclusive"]).max() - pd.Timedelta(days=1)).strftime("%Y-%m")
        first = pd.to_datetime(windows["gs_start_date"]).min().strftime("%Y-%m")
        all_months = spi_spei.month_axis("1990-01", max(end, BASELINE_END))
        index_months = spi_spei.month_axis(first, end)
        prcp_frames = self._read_all(self._chunks(self.refs.prcp, label=SPI_SOURCES[source]))
        et0_frames = self._read_all(self._chunks(self.refs.et0))
        patch_frames = self._read_all(self._chunks(self.refs.et0_patch))
        prcp_has, et0_has = self._availability(source, input_months(first, end), prcp_frames, et0_frames, patch_frames)
        if not prcp_has:
            return SourceOutcome(source, "unavailable", detail=f"S2C3 precipitation has no published {end}")
        if base == "spei03" and not et0_has:
            return SourceOutcome(source, "unavailable", detail=f"S2C3 ET0 has no published {end}")
        codes = sorted(windows["admin_code"].astype(str))
        prcp = _wide_month_matrix(prcp_frames, "prcp", all_months, codes)
        et0 = _wide_month_matrix(et0_frames, "et0", all_months, codes)
        et0, _ = spi_spei.apply_et0_patch(et0, _wide_month_matrix(patch_frames, "et0", all_months, codes, sparse=True))
        idx = sss.monthly_indices(prcp, et0, all_months, index_months, source)
        win = windows.assign(admin_code=windows["admin_code"].astype(str), gs_calendar_valid=1).sort_values("admin_code")
        plan = sss.season_plan(win[["admin_code", "season_year", "season", "gs_calendar_valid", "gs_start_date", "gs_end_date_exclusive"]],
                               index_months, codes)
        agg = sss.aggregate(idx["spi" if base == "spi03" else "spei"], idx["spi_reason" if base == "spi03" else "spei_reason"], plan, "v")
        return SourceOutcome(source, "published", pd.DataFrame({"admin_code": plan["admin_code"], "value": agg["v"].to_numpy()}),
                             extra={"status_counts": agg["v_status"].value_counts().to_dict()})

    def bound_season(self, base):
        return lambda source, year, season, windows: self.fetch_season(base, source, year, season, windows)
