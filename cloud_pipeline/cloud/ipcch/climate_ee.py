"""Earth Engine source providers of the IPCCH climate bases, ported from the shared-folder scripts (task 10-29; R1, R13,
R34, R40, R43). Monthly raster families in this module; the table families (NDVI/EVI, SPI/SPEI) are in
``climate_tables``.

Port boundary (same algorithms, operational execution):
* The pixel-level Earth Engine graphs of ``monthly/rainfall.js`` (ANOM_Z and RAIN_CDD), ``monthly/temperature.js`` and
  ``monthly/soil_moisture.js`` are rebuilt with the Python client operation for operation (sources, unit factors,
  baselines indexed by calendar month/day, seeds, masks, temporal sums/means/counts, the CDD iterate, pixelArea-weighted
  numerator/area bands, ``reduceRegions(sum, native crs/scale, tileScale 8, maxPixelsPerRegion 1e10)``).
* The per-feature post-processing the scripts do in EE (value = num / max(area, 1e-12) when area > 0, else MISSING;
  observed days, coverage, status, QA flags) runs locally in pandas on the exported raw sums (``finalize``): the same
  arithmetic, offline-testable. MISSING (-9999) becomes NaN (legitimate per-area missingness).
* Task bookkeeping (admin blocks, resumable asset exports) is replaced by one table export per (family, source, month) to
  Cloud Storage, the pattern of the existing EVI service.
* Hard-coded run windows of the scripts (TARGET_YEAR, LAST_MONTH = 8 in 2026) are run parameters here.

Operational availability rule (the scripts have none): a provider publishes a month only when its collection covers every
day of the month (GLDAS: every 3-hourly sample). A partially published month is ``unavailable`` - never saved, because
saved months are never rewritten (R8) - and is retried by a later run (R43). Collection/metadata/export errors are
processing failures (R13).

Private inputs (admin FeatureCollections and the STAGE2A/2B/2D baselines) are configurable references; every reference is
checked read-only before any compute, and an unreadable one fails with the list of missing assets (the han-sandbox assets
are not readable by the current identity: research/cp3/climate-ee-readonly).
"""

from __future__ import annotations

import calendar as pycalendar
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol

import numpy as np
import pandas as pd

from cloud.ipcch.climate import ClimateProcessingFailure, SourceOutcome

MISSING = -9999
TILE_SCALE = 8
MAX_PIXELS_PER_REGION = 1e10
RAIN_THRESHOLD_MM = 1
FORMAL_TOLERANCE_DAYS = 0.001
GDD_BASE_C, GDD_CAP_C, EDD_CRITICAL_C = 10, 30, 30
DEFAULT_ROOT = "projects/han-sandbox-505315/assets/"

RAIN_SOURCES = {
    "chirps": {"label": "CHIRPS", "collection": "UCSB-CHC/CHIRPS/V3/DAILY_RNL", "band": "precipitation", "factor": 1},
    "persiann": {"label": "PERSIANN", "collection": "NOAA/PERSIANN-CDR", "band": "precipitation", "factor": 1},
    "era5land": {"label": "ERA5LAND", "collection": "ECMWF/ERA5_LAND/DAILY_AGGR", "band": "total_precipitation_sum", "factor": 1000}}
TEMP_SOURCES = {
    "cpc": {"label": "CPC", "collection": "NOAA/CPC/Temperature", "bands": ["tmin", "tmax"], "proj_band": "tmax"},
    "era5land": {"label": "ERA5LAND", "collection": "ECMWF/ERA5_LAND/DAILY_AGGR",
                 "bands": ["temperature_2m", "temperature_2m_min", "temperature_2m_max"], "proj_band": "temperature_2m"}}
SOIL_SOURCES = {
    "era5land": {"label": "ERA5LAND", "collection": "ECMWF/ERA5_LAND/DAILY_AGGR", "band": "volumetric_soil_water_layer_1",
                 "per_day": 1},
    "gldas21": {"label": "GLDAS21", "collection": "NASA/GLDAS/V021/NOAH/G025/T3H", "band": "SoilMoi0_10cm_inst", "per_day": 8}}
TEMP_METRICS = ("tmean_anom", "tmax_anom", "hot_days_p95", "gdd", "edd")

# family -> (script, bases served, sources)
FAMILIES = {
    "rain_anomz": ("monthly/rainfall.js", ("prcp_anom", "prcp_z"), RAIN_SOURCES),
    "rain_cdd": ("monthly/rainfall.js", ("rainy_days", "cdd"), RAIN_SOURCES),
    "temperature": ("monthly/temperature.js", TEMP_METRICS, TEMP_SOURCES),
    "soil": ("monthly/soil_moisture.js", ("sm_z",), SOIL_SOURCES)}
BASE_FAMILY = {b: f for f, (_, bases, _) in FAMILIES.items() for b in bases}


@dataclass(frozen=True)
class AssetRefs:
    """Configurable private inputs (defaults = the shared scripts' han-sandbox names)."""
    root: str = DEFAULT_ROOT
    admin_collections: tuple[str, ...] = tuple(f"IPCCH_ADMIN_STATIC_CALENDAR_CROPFRAC_V1_G{g:02d}" for g in range(25))
    rain_baseline: str = "STAGE2A_PRCP_BASELINE_1991_2020_{label}_M{mm}"
    temp_baseline: str = "STAGE2B_TEMP_BASELINE_1991_2020_{label}_M{mm}"
    soil_baseline: str = "STAGE2D_SOIL_BASELINE_2001_2020_{label}_M{mm}"

    def asset(self, name: str) -> str:
        return name if name.startswith("projects/") else self.root + name

    def admins(self) -> list[str]:
        return [self.asset(a) for a in self.admin_collections]

    def baselines(self, family: str, label: str) -> list[str]:
        template = {"rain_anomz": self.rain_baseline, "temperature": self.temp_baseline, "soil": self.soil_baseline}[family]
        return [self.asset(template.format(label=label, mm=f"{m:02d}")) for m in range(1, 13)]

    def required(self, family: str, source: str) -> list[str]:
        cfg = FAMILIES[family][2][source]
        return self.admins() + (self.baselines(family, cfg["label"]) if family != "rain_cdd" else [])


class EEBackend(Protocol):
    """The Earth Engine / Cloud Storage boundary (mocked offline)."""
    ee: Any

    def missing_assets(self, asset_ids: list[str]) -> list[str]: ...           # read-only metadata
    def image_times(self, collection: str, band: str, start: str, end: str) -> list[int]: ...   # system:time_start (ms)
    def export_table(self, collection: Any, selectors: list[str], description: str) -> str: ...  # -> result URI
    def read_table(self, uri: str) -> pd.DataFrame: ...


def month_window(month: str) -> tuple[str, str, int]:
    y, m = (int(x) for x in month.split("-"))
    days = pycalendar.monthrange(y, m)[1]
    nxt = f"{y + (m == 12):04d}-{1 if m == 12 else m + 1:02d}-01"
    return f"{y:04d}-{m:02d}-01", nxt, days


# --------------------------------------------------------------------------- shared EE helpers (rainfall.js 4)


def _empty_masked_band(ee, band, projection):
    return ee.Image.constant(0).rename(band).toDouble().setDefaultProjection(projection).selfMask()


def _baseline_collection(ee, ids):
    return ee.ImageCollection.fromImages([ee.Image(i).set("calendar_month", m) for m, i in enumerate(ids, start=1)])


def _baseline_for_month(ee, baselines, month):
    return ee.Image(baselines.filter(ee.Filter.eq("calendar_month", month)).first())


# --------------------------------------------------------------------------- monthly/rainfall.js


def rain_daily(ee, cfg, start, end):
    """rainfall.js 8: daily precipitation (mm) = band * factor, floored at 0."""
    source = ee.ImageCollection(cfg["collection"]).select(cfg["band"])

    def one(image):
        image = ee.Image(image)
        p = image.select(cfg["band"]).multiply(cfg["factor"]).max(0).rename("prcp_mm").toDouble()
        return p.copyProperties(image, ["system:time_start", "system:index"])
    return source.filterDate(start, end).map(one).sort("system:time_start")


def rain_anomz_reduction(ee, cfg, baseline_ids, start, end):
    """rainfall.js 9-11: daily anomaly vs the calendar-day normal, monthly sums/counts, z of the complete-month total,
    pixelArea-weighted numerator/area bands."""
    source = ee.ImageCollection(cfg["collection"]).select(cfg["band"])
    proj = ee.Image(source.first()).select(cfg["band"]).projection()
    baselines = _baseline_collection(ee, baseline_ids)
    start, end = ee.Date(start), ee.Date(end)
    duration = end.difference(start, "day").toInt()

    def with_anomaly(image):
        image = ee.Image(image)
        date = image.date()
        baseline = _baseline_for_month(ee, baselines, date.get("month"))
        normal = baseline.select(ee.List([ee.String("daily_normal_d").cat(date.format("dd"))])).rename("daily_normal")
        anomaly = image.select("prcp_mm").subtract(normal).rename("prcp_anom")
        return ee.Image.cat([image.select("prcp_mm"), anomaly]).toDouble().copyProperties(image, ["system:time_start", "system:index"])

    daily = rain_daily(ee, cfg, start, end).map(with_anomaly)
    seed = ee.Image.cat([_empty_masked_band(ee, "prcp_mm", proj), _empty_masked_band(ee, "prcp_anom", proj)])
    with_seed = ee.ImageCollection.fromImages([seed]).merge(daily)
    sums = with_seed.sum().rename(["prcp_total", "prcp_anom"])
    counts = with_seed.count().rename(["prcp_obs", "anom_obs"])
    month = start.get("month")
    baseline = _baseline_for_month(ee, baselines, month)
    mean, sd = baseline.select("monthly_total_mean_mm"), baseline.select("monthly_total_sd_mm")
    anomaly = sums.select("prcp_anom").updateMask(counts.select("anom_obs").gt(0)).rename("prcp_anom")
    z = (sums.select("prcp_total").subtract(mean).divide(sd.updateMask(sd.gt(0)))
         .updateMask(counts.select("prcp_obs").eq(duration)).rename("prcp_z"))
    monthly = ee.Image.cat([anomaly, z, counts.select("anom_obs").rename("anom_obs").toDouble(),
                            counts.select("prcp_obs").rename("z_obs").toDouble()]).setDefaultProjection(proj)
    area = ee.Image.pixelArea().setDefaultProjection(proj)
    a, zz = monthly.select("prcp_anom"), monthly.select("prcp_z")
    image = ee.Image.cat([
        a.multiply(area).rename("anom_num"), area.updateMask(a.mask()).rename("anom_area"),
        monthly.select("anom_obs").updateMask(a.mask()).multiply(area).rename("anom_obs_num"),
        zz.multiply(area).rename("z_num"), area.updateMask(zz.mask()).rename("z_area"),
        monthly.select("z_obs").updateMask(zz.mask()).multiply(area).rename("z_obs_num")]).toDouble().setDefaultProjection(proj)
    return image, proj


def rain_cdd_reduction(ee, cfg, baseline_ids, start, end):
    """rainfall.js 12-13: rainy days (>= 1 mm), longest consecutive dry run within the month (missing days break the
    run), observed days; pixelArea-weighted bands."""
    source = ee.ImageCollection(cfg["collection"]).select(cfg["band"])
    proj = ee.Image(source.first()).select(cfg["band"]).projection()
    daily = rain_daily(ee, cfg, start, end)

    def classify(image):
        image = ee.Image(image)
        p = image.select("prcp_mm")
        valid = p.mask().reduce(ee.Reducer.min())
        rainy = p.gte(RAIN_THRESHOLD_MM).rename("rainy_day").toDouble().updateMask(valid)
        dry = p.lt(RAIN_THRESHOLD_MM).rename("dry_day").toDouble().updateMask(valid)
        observed = ee.Image.constant(1).rename("observed_day").toDouble().setDefaultProjection(proj).updateMask(valid)
        return ee.Image.cat([rainy, dry, observed]).copyProperties(image, ["system:time_start", "system:index"])

    classified = daily.map(classify)
    sum_seed = ee.Image.constant([0, 0]).rename(["rainy_day", "observed_day"]).toDouble().setDefaultProjection(proj)
    rainy_observed = (ee.ImageCollection.fromImages([sum_seed]).merge(classified.select(["rainy_day", "observed_day"]))
                      .sum().rename(["rainy_days", "observed_days"]).toDouble())
    cdd_seed = ee.Image.constant([0, 0]).rename(["current_run", "maximum_run"]).toDouble().setDefaultProjection(proj)

    def step(image, previous):
        image, previous = ee.Image(image), ee.Image(previous)
        valid = image.select("observed_day").unmask(0).gt(0)
        dry = image.select("dry_day").unmask(0).gt(0)
        current = previous.select("current_run").add(1).where(valid.And(dry).Not(), 0).rename("current_run")
        maximum = previous.select("maximum_run").max(current).rename("maximum_run")
        return ee.Image.cat([current, maximum]).toDouble()

    state = ee.Image(classified.iterate(step, cdd_seed))
    observed = rainy_observed.select("observed_days")
    rainy = rainy_observed.select("rainy_days").updateMask(observed.gt(0))
    cdd = state.select("maximum_run").rename("cdd").updateMask(observed.gt(0))
    area = ee.Image.pixelArea().setDefaultProjection(proj)
    image = ee.Image.cat([
        rainy.multiply(area).rename("rain_num"), area.updateMask(rainy.mask()).rename("rain_area"),
        cdd.multiply(area).rename("cdd_num"), area.updateMask(cdd.mask()).rename("cdd_area"),
        observed.updateMask(observed.gt(0)).multiply(area).rename("obs_num"),
        area.updateMask(observed.gt(0)).rename("obs_area")]).toDouble().setDefaultProjection(proj)
    return image, proj


# --------------------------------------------------------------------------- monthly/temperature.js


def temperature_reduction(ee, cfg, baseline_ids, start, end):
    """temperature.js 1.3-1.5: daily metrics vs calendar-day normals/p95, monthly means (anomalies) and sums (counts,
    GDD, EDD) over valid days, pixelArea-weighted bands per metric."""
    source = ee.ImageCollection(cfg["collection"]).select(cfg["bands"])
    proj = ee.Image(source.first()).select(cfg["proj_band"]).projection()
    baselines = _baseline_collection(ee, baseline_ids)
    cpc = cfg["label"] == "CPC"

    def daily_metrics(image):
        image = ee.Image(image)
        date = image.date()
        day = ee.Number(date.get("day")).format("%02d")
        baseline = _baseline_for_month(ee, baselines, date.get("month"))
        if cpc:
            tmin, tmax = image.select("tmin"), image.select("tmax")
            tmean = tmin.add(tmax).divide(2)
        else:
            tmean = image.select("temperature_2m").subtract(273.15)
            tmin = image.select("temperature_2m_min").subtract(273.15)
            tmax = image.select("temperature_2m_max").subtract(273.15)
        tmean_normal = baseline.select(ee.List([ee.String("tmean_normal_d").cat(day)]))
        tmax_normal = baseline.select(ee.List([ee.String("tmax_normal_d").cat(day)]))
        tmax_p95 = baseline.select(ee.List([ee.String("tmax_p95_d").cat(day)]))
        out = ee.Image.cat([
            tmean.subtract(tmean_normal).rename("tmean_anom"), tmax.subtract(tmax_normal).rename("tmax_anom"),
            tmax.gt(tmax_p95).rename("hot_days_p95"),
            tmax.min(GDD_CAP_C).add(tmin.max(GDD_BASE_C)).divide(2).subtract(GDD_BASE_C).max(0).rename("gdd"),
            tmax.subtract(EDD_CRITICAL_C).max(0).rename("edd")]).toFloat()
        return out.copyProperties(image, ["system:time_start"])

    daily = source.filterDate(start, end).map(daily_metrics)
    observed = daily.select(list(TEMP_METRICS)).count().rename([f"{m}_obs" for m in TEMP_METRICS])
    means = daily.select(["tmean_anom", "tmax_anom"]).mean()
    sums = daily.select(["hot_days_p95", "gdd", "edd"]).sum()
    monthly = ee.Image.cat([means, sums, observed])
    area = ee.Image.pixelArea().setDefaultProjection(proj)
    bands = []
    for m in TEMP_METRICS:
        obs = monthly.select(f"{m}_obs")
        usable = obs.gt(0)
        value = monthly.select(m).updateMask(usable)
        bands += [value.multiply(area).rename(f"{m}_num"), area.updateMask(value.mask()).rename(f"{m}_area"),
                  obs.updateMask(usable).multiply(area).rename(f"{m}_obs_num")]
    return ee.Image.cat(bands).toDouble(), proj


# --------------------------------------------------------------------------- monthly/soil_moisture.js


def soil_reduction(ee, cfg, baseline_ids, start, end):
    """soil_moisture.js 2.3-2.4: monthly mean of all available samples, z vs the 2001-2020 calendar-month baseline
    (SD > 0 only), pixelArea-weighted bands."""
    source = ee.ImageCollection(cfg["collection"]).select(cfg["band"])
    proj = ee.Image(source.first()).select(cfg["band"]).projection()
    baselines = _baseline_collection(ee, baseline_ids)
    start, end = ee.Date(start), ee.Date(end)
    raw = source.filterDate(start, end).map(lambda img: ee.Image(img).rename("sm").toFloat())
    seed = ee.Image.constant(0).rename("sm").toFloat().setDefaultProjection(proj).selfMask()
    target = ee.ImageCollection.fromImages([seed]).merge(raw).reduce(
        ee.Reducer.mean().combine(reducer2=ee.Reducer.count(), sharedInputs=True))
    current = target.select("sm_mean")
    count = target.select("sm_count").unmask(0, False)
    baseline = _baseline_for_month(ee, baselines, start.get("month"))
    bmean, bsd = baseline.select("sm_monthly_mean"), baseline.select("sm_monthly_sd")
    z = current.subtract(bmean).divide(bsd).updateMask(count.gt(0)).updateMask(bsd.gt(0)).rename("sm_z")
    area = ee.Image.pixelArea().setDefaultProjection(proj)
    image = ee.Image.cat([
        z.multiply(area).rename("sm_z_num"), area.updateMask(z.mask()).rename("sm_z_area"),
        count.updateMask(z.mask()).multiply(area).rename("sample_count_num"),
        current.updateMask(z.mask()).multiply(area).rename("monthly_sm_mean_num")]).toDouble()
    return image, proj


REDUCTIONS: dict[str, Callable] = {"rain_anomz": rain_anomz_reduction, "rain_cdd": rain_cdd_reduction,
                                   "temperature": temperature_reduction, "soil": soil_reduction}
SUM_BANDS = {
    "rain_anomz": ["anom_num", "anom_area", "anom_obs_num", "z_num", "z_area", "z_obs_num"],
    "rain_cdd": ["rain_num", "rain_area", "cdd_num", "cdd_area", "obs_num", "obs_area"],
    "temperature": [f"{m}_{k}" for m in TEMP_METRICS for k in ("num", "area", "obs_num")],
    "soil": ["sm_z_num", "sm_z_area", "sample_count_num", "monthly_sm_mean_num"]}


def admin_collection(ee, refs: AssetRefs):
    fc = ee.FeatureCollection([])
    for asset_id in refs.admins():
        fc = fc.merge(ee.FeatureCollection(asset_id))
    return fc.sort("admin_idx")


def reduced_table(ee, family: str, source: str, month: str, refs: AssetRefs):
    """The family's reduction for one source-month over every admin: admin_code + raw band sums (no geometry)."""
    cfg = FAMILIES[family][2][source]
    start, end, _ = month_window(month)
    baseline_ids = refs.baselines(family, cfg["label"]) if family != "rain_cdd" else []
    image, proj = REDUCTIONS[family](ee, cfg, baseline_ids, start, end)
    reduced = image.reduceRegions(collection=admin_collection(ee, refs), reducer=ee.Reducer.sum(), crs=proj,
                                  scale=proj.nominalScale(), tileScale=TILE_SCALE, maxPixelsPerRegion=MAX_PIXELS_PER_REGION)
    return reduced.map(lambda f: ee.Feature(None, ee.Feature(f).toDictionary(["admin_code"] + SUM_BANDS[family])))


# --------------------------------------------------------------------------- local post-processing (the scripts' per-feature EE arithmetic)


def _ratio(num, area):
    num = pd.to_numeric(num, errors="raise").fillna(0.0).to_numpy(float)
    area = pd.to_numeric(area, errors="raise").fillna(0.0).to_numpy(float)
    present = area > 0
    return np.where(present, num / np.maximum(area, 1e-12), np.nan), present


def finalize(family: str, raw: pd.DataFrame, month: str, source: str) -> dict[str, pd.DataFrame]:
    """Per base: admin_code, value (NaN = MISSING) and the scripts' status/coverage/QA columns."""
    need = ["admin_code"] + SUM_BANDS[family]
    missing = [c for c in need if c not in raw.columns]
    if missing:
        raise ClimateProcessingFailure(f"{family} {source} {month}: export lacks columns {missing}")
    _, _, duration = month_window(month)
    if family == "soil":
        expected = duration * SOIL_SOURCES[source]["per_day"]
    codes = raw["admin_code"].astype(str)
    out = {}

    def status(present, observed, full):
        return np.where(~present, "MISSING_DATA", np.where(observed >= full - 1e-6, "COMPLETE", "PARTIAL_DATA"))

    if family == "rain_anomz":
        for base, num, area, obs in (("prcp_anom", "anom_num", "anom_area", "anom_obs_num"), ("prcp_z", "z_num", "z_area", "z_obs_num")):
            v, present = _ratio(raw[num], raw[area])
            observed = np.where(present, _ratio(raw[obs], raw[area])[0], 0.0)
            frame = pd.DataFrame({"admin_code": codes, "value": v, "status": status(present, observed, duration),
                                  "coverage": np.clip(observed / max(duration, 1), 0, 1)})
            if base == "prcp_z":
                frame["qa_abs_gt6_warning"] = (present & (np.abs(np.nan_to_num(v)) > 6)).astype(int)   # flag only, value kept
            out[base] = frame
    elif family == "rain_cdd":
        rainy, has_r = _ratio(raw["rain_num"], raw["rain_area"])
        cdd, has_c = _ratio(raw["cdd_num"], raw["cdd_area"])
        obs, has_o = _ratio(raw["obs_num"], raw["obs_area"])
        observed = np.where(has_o, obs, 0.0)
        st = np.where(~(has_r & has_c), "MISSING_DATA", np.where(observed >= duration - 1e-6, "COMPLETE", "PARTIAL_DATA"))
        upper = duration + FORMAL_TOLERANCE_DAYS
        for base, v, has in (("rainy_days", rainy, has_r), ("cdd", cdd, has_c)):
            out[base] = pd.DataFrame({"admin_code": codes, "value": v, "status": st, "coverage": np.clip(observed / max(duration, 1), 0, 1),
                                      "qa_exceeds_month_duration": (has & (np.nan_to_num(v) > upper)).astype(int),
                                      "qa_exceeds_observed_days": (has & has_o & (np.nan_to_num(v) > observed + FORMAL_TOLERANCE_DAYS)).astype(int)})
    elif family == "temperature":
        for m in TEMP_METRICS:
            v, present = _ratio(raw[f"{m}_num"], raw[f"{m}_area"])
            observed = np.where(present, _ratio(raw[f"{m}_obs_num"], raw[f"{m}_area"])[0], 0.0)
            frame = pd.DataFrame({"admin_code": codes, "value": v, "status": status(present, observed, duration),
                                  "coverage": np.clip(observed / max(duration, 1), 0, 1)})
            if m == "hot_days_p95":
                frame["qa_above_month_duration"] = (present & (np.nan_to_num(v) > duration + 1e-6)).astype(int)
            if m in ("gdd", "edd"):
                frame["qa_negative"] = (present & (np.nan_to_num(v) < 0)).astype(int)
            out[m] = frame
    elif family == "soil":
        v, present = _ratio(raw["sm_z_num"], raw["sm_z_area"])
        observed = np.where(present, _ratio(raw["sample_count_num"], raw["sm_z_area"])[0], 0.0)
        out["sm_z"] = pd.DataFrame({"admin_code": codes, "value": v, "status": status(present, observed, expected),
                                    "coverage": np.clip(observed / max(expected, 1), 0, 1),
                                    "qa_abs_gt6_warning": (present & (np.abs(np.nan_to_num(v)) > 6)).astype(int)})
    return out


# --------------------------------------------------------------------------- provider


def expected_slots(start: str, end: str, per_day: int) -> pd.DatetimeIndex:
    """Every UTC observation slot of [start, end): one per day, or every 24/per_day hours from 00:00 (GLDAS 3-hourly)."""
    return pd.date_range(pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC"), freq=f"{24 // per_day}h", inclusive="left")


def slots_present(times, start: str, end: str, per_day: int) -> tuple[int, int]:
    """(expected slots that have an image, expected slots): daily sources match by UTC day, sub-daily sources by the
    exact slot timestamp, so off-slot or duplicate stamps never count."""
    expected = expected_slots(start, end, per_day)
    stamps = pd.to_datetime(pd.Series(list(times), dtype="int64"), unit="ms", utc=True)
    have = set(stamps.dt.floor("D")) if per_day == 1 else set(stamps)
    return int(sum(slot in have for slot in expected)), len(expected)


def publication(backend: EEBackend, family: str, source: str, month: str) -> tuple[bool, str]:
    """(published, detail): every expected slot of the month (each day; GLDAS each 3-hourly UTC slot) has an image."""
    cfg = FAMILIES[family][2][source]
    start, end, _ = month_window(month)
    band = cfg.get("band") or cfg["proj_band"]
    have, need = slots_present(backend.image_times(cfg["collection"], band, start, end), start, end, cfg.get("per_day", 1))
    if have == 0:
        return False, f"{cfg['collection']}: no images for {month}"
    if have < need:
        return False, f"{cfg['collection']}: partial publication {have}/{need} for {month}"
    return True, f"{have}/{need}"


@dataclass
class MonthlyEEProvider:
    """``climate.update_monthly`` fetch for the raster families: one export per (family, source, month), cached for the
    sibling bases of the family."""
    backend: EEBackend
    refs: AssetRefs = field(default_factory=AssetRefs)
    cache: dict = field(default_factory=dict)
    log: list = field(default_factory=list)

    def fetch(self, base: str, source: str, month: str) -> SourceOutcome:
        family = BASE_FAMILY.get(base)
        if family is None or source not in FAMILIES[family][2]:
            raise ClimateProcessingFailure(f"no EE provider for {base}/{source}")
        key = (family, source, month)
        if key not in self.cache:
            self.cache[key] = self._compute(family, source, month)
        result = self.cache[key]
        if isinstance(result, str):
            return SourceOutcome(source, "unavailable", detail=result)
        frame = result[base]
        return SourceOutcome(source, "published", frame[["admin_code", "value"]].reset_index(drop=True),
                             extra={"status_counts": frame["status"].value_counts().to_dict(),
                                    "qa": {c: int(frame[c].sum()) for c in frame.columns if c.startswith("qa_")}})

    def bound(self, base: str) -> Callable[[str, str], SourceOutcome]:
        return lambda source, month: self.fetch(base, source, month)

    def _compute(self, family, source, month):
        try:
            published, detail = publication(self.backend, family, source, month)
        except Exception as exc:                                  # metadata errors are failures, never "unavailable"
            raise ClimateProcessingFailure(f"{family} {source} {month}: publication check failed: {exc}") from exc
        if not published:
            self.log.append({"family": family, "source": source, "month": month, "unavailable": detail})
            return detail
        missing = self.backend.missing_assets(self.refs.required(family, source))
        if missing:
            raise ClimateProcessingFailure(f"{family} {source}: unreadable private inputs (configure AssetRefs): {missing[:5]}"
                                           f"{' ...' if len(missing) > 5 else ''} ({len(missing)} total)")
        ee = self.backend.ee
        try:
            table = reduced_table(ee, family, source, month, self.refs)
            uri = self.backend.export_table(table, ["admin_code"] + SUM_BANDS[family],
                                            f"ipcch_{family}_{source}_{month.replace('-', '')}")
            raw = self.backend.read_table(uri)
        except ClimateProcessingFailure:
            raise
        except Exception as exc:
            raise ClimateProcessingFailure(f"{family} {source} {month}: export failed: {type(exc).__name__}: {exc}") from exc
        self.log.append({"family": family, "source": source, "month": month, "uri": uri, "rows": int(len(raw))})
        return finalize(family, raw, month, source)
