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
"""

from __future__ import annotations

import calendar as pycalendar
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol

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
class TableRefs:
    root: str = DEFAULT_ROOT
    vi_baseline: str = "S2E3_VI_BASE_ADMIN_2003_2020_{label}_CMG_P{part:02d}_V3"
    vi_current: str = "S2E3_VI_CURRENT_ADMIN_{label}_Y{year}_CMG_V3"
    prcp: str = "S2C3_DROUGHT_ADMIN_PRCP_{label}_Y{a}_{b}_V3"
    et0: str = "S2C3_DROUGHT_ADMIN_ET0_FAO56_Y{a}_{b}_V3"
    et0_patch: str = "S2C3_ET0_PATCH32_Y{a}_{b}_V2"
    year_chunks: tuple[tuple[int, int], ...] = YEAR_CHUNKS

    def asset(self, name: str) -> str:
        return name if name.startswith("projects/") else self.root + name


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
            v = pd.to_numeric(table[name], errors="coerce").to_numpy(float) if name in table.columns else np.full(len(table), np.nan)
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

    def _read(self, asset):
        if asset not in self.tables:
            try:
                self.tables[asset] = self.backend.read_asset_table(asset)
            except Exception as exc:
                raise ClimateProcessingFailure(f"reading {asset} failed: {type(exc).__name__}: {exc}") from exc
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
        absent = self.backend.missing_assets(list(cur_ids.values()))
        if absent:
            return SourceOutcome(sensor, "unavailable", detail=f"current S2E3 tables not available: {absent}")
        joined = None
        for asset in base_ids:
            t = self._read(asset)
            joined = t if joined is None else pd.concat([joined, t], ignore_index=True)
        joined = joined.drop_duplicates("admin_code", keep="first").set_index("admin_code")
        for cy in years:                        # left values win on key collision (combine(..., false))
            cur = self._read(cur_ids[cy]).set_index("admin_code")
            joined = joined.join(cur[[c for c in cur.columns if c not in joined.columns]], how="left")
        need = [f"{self.index}_{p['tag']}_mean" for p in parts]
        lacking = [c for c in need if c not in joined.columns]
        if lacking:
            return SourceOutcome(sensor, "unavailable", detail=f"composites not yet in the current tables: {lacking}")
        out = monthly_vi(joined.reset_index(), sensor, self.index, y, m)
        return SourceOutcome(sensor, "published", out[["admin_code", "value"]],
                             extra={"incomplete_areas": int(out["value"].isna().sum())})


# --------------------------------------------------------------------------- monthly/spi_monthly.py


def _wide_month_matrix(frames: list[pd.DataFrame], prefix: str, months: pd.DatetimeIndex, admins: list[str]) -> np.ndarray:
    """``{prefix}_{YYYYMM}_mean`` columns of the outer-merged year-chunk tables as an admin x month matrix; absent
    month properties are NaN (normalize_monthly_table)."""
    wide = None
    for f in frames:
        f = f.assign(admin_code=f["admin_code"].astype(str)).set_index("admin_code")
        if f.index.duplicated().any():
            raise ClimateProcessingFailure(f"{prefix} table has duplicate admin_code")
        wide = f if wide is None else wide.join(f[[c for c in f.columns if c not in wide.columns]], how="outer")
    cols = [f"{prefix}_{d.year}{d.month:02d}_mean" for d in months]
    aligned = wide.reindex(admins)
    return np.column_stack([pd.to_numeric(aligned[c], errors="coerce").to_numpy(float) if c in aligned.columns
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
                try:
                    self.tables[i] = self.backend.read_asset_table(i)
                except Exception as exc:
                    raise ClimateProcessingFailure(f"reading {i} failed: {type(exc).__name__}: {exc}") from exc
            out.append(self.tables[i])
        return out

    def _compute(self, source, month):
        months = spi_spei.month_axis("1990-01", month)
        target = f"{month.replace('-', '')}"
        prcp_frames = self._read_all(self._chunks(self.refs.prcp, label=SPI_SOURCES[source]))
        et0_frames = self._read_all(self._chunks(self.refs.et0))
        patch_frames = self._read_all(self._chunks(self.refs.et0_patch))
        prcp_has = any(f"prcp_{target}_mean" in f.columns for f in prcp_frames)
        et0_has = any(f"et0_{target}_mean" in f.columns for f in et0_frames)
        prcp = _wide_month_matrix(prcp_frames, "prcp", months, self.admins)
        et0 = _wide_month_matrix(et0_frames, "et0", months, self.admins)
        et0, filled = spi_spei.apply_et0_patch(et0, _wide_month_matrix(patch_frames, "et0", months, self.admins))
        spi = spi_spei.compute_spi03_monthly(prcp, months)[:, -1] if prcp_has else None
        spei = spi_spei.compute_spei03_monthly(prcp, et0, months)[:, -1] if prcp_has and et0_has else None
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
            return SourceOutcome(source, "unavailable", detail=f"S2C3 {why} table has no {month} column")
        return SourceOutcome(source, "published", pd.DataFrame({"admin_code": self.admins, "value": r[base]}),
                             extra={"et0_patch_filled": r["et0_patch_filled"]})

    def bound(self, base: str) -> Callable[[str, str], SourceOutcome]:
        return lambda source, month: self.fetch(base, source, month)
