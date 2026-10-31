"""Automatic production of the IPCCH climate input tables (task 10-30; R2, R8, R10): the two seasonal producer scripts
ported to the Python Earth Engine client and run inside the monthly flow, so no table ID is edited by hand.

* ``seasonal/01_vi_prcp_et0_update.js`` (sha256 b0d64ac0...): S2E3 VI current-year tables (MOD13C1/MYD13C1, SummaryQA <=
  1 and Pixel_1km > 0, no additional VI scaling) and the S2C3 drought chunks: monthly precipitation (CHIRPS, PERSIANN,
  ERA5-Land x 1000; daily values floored at 0, summed) and ERA5-Land FAO-56 Penman-Monteith ET0 (daily, floored at 0,
  summed), each month masked unless the source has every day of the month. Original admin polygons.
* ``seasonal/02_et0_patch32_update.js`` (sha256 841ae7f8...): the same monthly ET0 reduced over the 32 PATCH32 admins'
  original polygons buffered by 30 km (maxError 100); the 32 distinct targets are checked before submission.

Port boundary: the graphs are rebuilt operation for operation (sources, bands, QA, unit factors, daily FAO-56 arithmetic,
masks, mean+stdDev+count reducer, native projection/scale, tileScale 8, maxPixelsPerRegion 1e9, centroid(100) compact
geometry, per-row properties). The shared formulas exist once here (``daily_fao56_et0``, ``monthly_et0``,
``stats_reducer``) and serve both scripts; the Code Editor bookkeeping is replaced by:

* demand planning from the retained stores (the same scheduling ``climate.update_monthly``/``update_seasonal`` use):
  only unsaved months/seasons of evi_anom, spi03 and spei03 need tables; already-retained periods produce nothing;
* required tables: the VI years each demanded period reads (a January Aqua month also reads the prior year's composite),
  and every drought chunk from 2020 on that holds a demanded input month (rolling 3-month window, seasonal spans);
  historical chunks (1990-2019) and the VI baselines are static inputs and are never produced. Chunks after 2026 follow
  ``climate_tables.year_chunks`` (6-year blocks from 2027), the same function the reader uses;
* immutable output IDs ``{output_root}{existing basename}__{version}``, version from the execution month and the run ID
  (a new run on the same day gets new IDs; an existing ID is never reused);
* one Asset export per table per run, all submitted before any wait (``EETransport`` reservation/task-id/bounded-wait/
  cancel machinery); any failure cancels the others and blocks - old assets are never substituted;
* source-calendar completeness evaluated in the SAME export graph as the masks: ``days_present_YYYYMM`` per chunk month
  and ``composite_dates`` per VI year are written as table properties, read back from the completed asset and turned
  into ``climate_tables.ProducedTable`` periods; schema, units, identity properties and PATCH32 IDs are validated before
  the asset is exposed to the consumers (``TableRefs.produced``).

The scripts' date-only ``_UPDATE_YYYYMMDD`` tag, fixed 2026 years and manual Tasks-panel start are not ported.
"""

from __future__ import annotations

import calendar as pycalendar
import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd

from cloud.ipcch import climate as cl
from cloud.ipcch import climate_tables as ct
from cloud.ipcch.climate import ClimateProcessingFailure
from cloud.ipcch.climate_ee import RAIN_SOURCES, AssetRefs

SCRIPTS = {"seasonal/01_vi_prcp_et0_update.js": "b0d64ac063e75d64d1f3ac4e17d79250b890a789f12acdecc0562ba0231c3549",
           "seasonal/02_et0_patch32_update.js": "841ae7f838c8c7457928e95df860980b28857ec83bf6b9b92cb604fdd3ed7e47"}
PRODUCER_VERSION = "ipcch-table-producers-v1"
TILE_SCALE = 8
MAX_PIXELS_PER_REGION = 1e9
VI_MAX_SUMMARY_QA = 1
VI_SOURCES = {"terra": {"label": "TERRA", "collection": "MODIS/061/MOD13C1"},
              "aqua": {"label": "AQUA", "collection": "MODIS/061/MYD13C1"}}
PRECIP_SOURCES = {s: RAIN_SOURCES[s] for s in ct.SPI_SOURCES}   # same IDs, bands and unit factors as 01's PRECIP_SOURCES
ERA5_DAILY_ID = "ECMWF/ERA5_LAND/DAILY_AGGR"
ERA5_ET0_BANDS = ["temperature_2m", "temperature_2m_min", "temperature_2m_max", "dewpoint_temperature_2m",
                  "u_component_of_wind_10m", "v_component_of_wind_10m", "surface_pressure",
                  "surface_net_solar_radiation_sum", "surface_net_thermal_radiation_sum"]
ET0_SOURCE = "ERA5LAND_FAO56_PM_ET0"
ET0_METHOD = "FAO56_PENMAN_MONTEITH_DAILY_THEN_MONTHLY_SUM"
PATCH32_CODES = (101183, 101191, 101194, 101275, 2107, 2108, 3422, 3423, 3427, 3428, 3429, 3430, 3431, 3432, 3433, 4073,
                 4267, 4269, 4270, 4353, 4783, 4784, 4785, 4786, 4787, 76, 77, 983, 984, 985, 986, 987)
PATCH32_BUFFER_M = 30000
FIRST_PRODUCED_CHUNK = 2020                       # 1990-2019 chunks are completed history (never produced)
TABLE_BASES = ("evi_anom", "spi03", "spei03")


# --------------------------------------------------------------------------- shared graph helpers


def stats_reducer(ee):
    """mean, spatial stdDev and valid-pixel count of every band (ADMIN_STATS_REDUCER of both scripts)."""
    return ee.Reducer.mean().combine(reducer2=ee.Reducer.stdDev(), sharedInputs=True) \
        .combine(reducer2=ee.Reducer.count(), sharedInputs=True)


def empty_image(ee):
    return ee.Image(0).select([])


def merged_admins(ee, inputs: AssetRefs):
    fc = ee.FeatureCollection([])
    for asset_id in inputs.admins():
        fc = fc.merge(ee.FeatureCollection(asset_id))
    return fc


def admin_features(ee, inputs: AssetRefs):
    """01 section 2: original polygon geometry, admin_code and admin_area_km2 (area maxError 1)."""
    def one(feature):
        feature = ee.Feature(feature)
        return ee.Feature(feature.geometry()).copyProperties(feature, ["admin_code"]) \
            .set("admin_area_km2", feature.geometry().area(1).divide(1e6))
    return merged_admins(ee, inputs).map(one)


def patch32_targets(ee, inputs: AssetRefs):
    """02 section 3: the 32 targets, admin_code stored as number or string, distinct by admin_code."""
    allf = merged_admins(ee, inputs)
    numeric = allf.filter(ee.Filter.inList("admin_code", list(PATCH32_CODES)))
    text = allf.filter(ee.Filter.inList("admin_code", [str(c) for c in PATCH32_CODES]))
    return numeric.merge(text).distinct(["admin_code"])


def buffered_patch32(ee, targets):
    """02 section 3: original polygon buffered by 30 km (maxError 100) plus the fallback properties."""
    def one(feature):
        feature = ee.Feature(feature)
        return ee.Feature(feature.geometry().buffer(PATCH32_BUFFER_M, 100)).copyProperties(feature, ["admin_code"]).set({
            "original_admin_area_km2": feature.geometry().area(100).divide(1e6), "et0_spatial_fallback": 1,
            "fallback_method": "BUFFERED_ERA5LAND_MEAN", "fallback_buffer_m": PATCH32_BUFFER_M})
    return targets.map(one)


def reduce_to_points(ee, image, collection, projection, scale):
    """reduceRegions with the shared reducer, then each polygon replaced by its centroid(100) (EE table assets cannot
    hold null geometry)."""
    reduced = ee.Image(image).reduceRegions(collection=ee.FeatureCollection(collection), reducer=stats_reducer(ee),
                                            crs=projection, scale=scale, tileScale=TILE_SCALE,
                                            maxPixelsPerRegion=MAX_PIXELS_PER_REGION)
    return reduced.map(lambda f: ee.Feature(ee.Feature(f).geometry().centroid(100), ee.Feature(f).toDictionary()))


def month_range(ee, year: int, month: int):
    start = ee.Date.fromYMD(year, month, 1)
    end = start.advance(1, "month")
    return start, end, end.difference(start, "day").toInt()


def _grid_band(ee, name, projection):
    return ee.Image.constant(1).rename(name).setDefaultProjection(projection).toFloat()


def _with_days_present(ee, table, days: Mapping[str, Any]):
    """The completeness evidence of the same graph as the masks: ``days_present_YYYYMM`` on every row."""
    props = ee.Dictionary({f"days_present_{tag}": n for tag, n in days.items()})
    return table.map(lambda f: ee.Feature(f).set(props))


# --------------------------------------------------------------------------- VI (01 section 3)


def prepare_vi(ee, image):
    image = ee.Image(image)
    valid = image.select("SummaryQA").lte(VI_MAX_SUMMARY_QA).And(image.select("Pixel_1km").gt(0))
    return ee.Image(image.select(["NDVI", "EVI", "Pixel_1km"], ["ndvi", "evi", "used_1km"]).updateMask(valid).toFloat()
                    .copyProperties(image, ["system:time_start", "system:index"]))


def vi_year(ee, sensor: str, year: int):
    """(stack of every published 16-day composite of the year renamed {ndvi,evi,used1km}_YYYYMMDD + cmg_grid_total,
    composite dates of the same collection, NDVI projection)."""
    cfg = VI_SOURCES[sensor]
    start = ee.Date.fromYMD(year, 1, 1)
    images = ee.ImageCollection(cfg["collection"]).filterDate(start, start.advance(1, "year")).sort("system:time_start")

    def step(image, accumulator):
        image = ee.Image(image)
        tag = ee.Date(image.get("system:time_start")).format("YYYYMMdd")
        renamed = image.rename(ee.List([ee.String("ndvi_").cat(tag), ee.String("evi_").cat(tag),
                                        ee.String("used1km_").cat(tag)]))
        return ee.Image(accumulator).addBands(renamed)
    stack = ee.Image(images.map(lambda i: prepare_vi(ee, i)).iterate(step, empty_image(ee)))
    projection = ee.ImageCollection(cfg["collection"]).first().select("NDVI").projection()
    dates = images.aggregate_array("system:time_start").map(lambda t: ee.Date(t).format("YYYYMMdd")).join(",")
    return stack.addBands(_grid_band(ee, "cmg_grid_total", projection)), dates, projection


def vi_table(ee, sensor: str, year: int, admins):
    stack, dates, projection = vi_year(ee, sensor, year)
    cfg = VI_SOURCES[sensor]
    props = {"sensor": cfg["label"], "product": cfg["collection"], "observation_year": year,
             "temporal_resolution": "16_day", "spatial_product": "CMG_0P05_DEG"}
    table = reduce_to_points(ee, stack, admins, projection, projection.nominalScale())
    return table.map(lambda f: ee.Feature(f).set(props).set("composite_dates", dates))


# --------------------------------------------------------------------------- drought precipitation (01 section 4)


def monthly_precipitation(ee, source: str, year: int, month: int):
    """(prcp_YYYYMM band, days present): daily band x unit factor floored at 0, summed; the whole month masked unless
    every day is present."""
    cfg = PRECIP_SOURCES[source]
    start, end, expected = month_range(ee, year, month)
    daily = ee.ImageCollection(cfg["collection"]).filterDate(start, end).select(cfg["band"]) \
        .map(lambda i: ee.Image(i).multiply(cfg["factor"]).max(0).rename("prcp_mm").toFloat())
    present = daily.size()
    template = ee.Image(ee.ImageCollection(cfg["collection"]).select(cfg["band"]).first()).multiply(0) \
        .rename("prcp_mm").updateMask(ee.Image.constant(0)).toFloat()
    complete = present.eq(expected)
    monthly = ee.Image(ee.Algorithms.If(present.gt(0), daily.sum(), template)).updateMask(ee.Image.constant(complete))
    return monthly.rename(f"prcp_{year}{month:02d}").set({"year": year, "month": month, "days_present": present,
                                                         "days_expected": expected, "month_complete": complete}), present


def precipitation_table(ee, source: str, a: int, b: int, admins):
    cfg = PRECIP_SOURCES[source]
    stack, days = empty_image(ee), {}
    for y in range(a, b + 1):
        for m in range(1, 13):
            band, days[f"{y}{m:02d}"] = monthly_precipitation(ee, source, y, m)
            stack = stack.addBands(band)
    projection = ee.ImageCollection(cfg["collection"]).first().select(cfg["band"]).projection()
    stack = stack.addBands(_grid_band(ee, "source_grid_total", projection))
    props = {"source": ct.SPI_SOURCES[source], "product": cfg["collection"], "chunk_start_year": a, "chunk_end_year": b,
             "temporal_resolution": "monthly_total", "unit": "mm_month"}
    table = reduce_to_points(ee, stack, admins, projection, projection.nominalScale())
    return _with_days_present(ee, table.map(lambda f: ee.Feature(f).set(props)), days)


# --------------------------------------------------------------------------- ERA5-Land FAO-56 ET0 (01 section 5 / 02 sections 5-9)


def saturation_vapor_pressure(ee, temp_c):
    temp_c = ee.Image(temp_c)
    return temp_c.multiply(17.27).divide(temp_c.add(237.3)).exp().multiply(0.6108)


WIND_2M_FACTOR = 4.87 / math.log(67.8 * 10 - 5.42)        # 10 m -> 2 m (client-side constant, as in both scripts)


def daily_fao56_et0(ee, image):
    """calculateDailyFao56Et0 (identical in both scripts): FAO-56 Penman-Monteith reference ET (mm/day) from ERA5-Land
    daily aggregates; soil heat flux 0; floored at 0."""
    image = ee.Image(image)
    t_mean = image.select("temperature_2m").subtract(273.15)
    t_min = image.select("temperature_2m_min").subtract(273.15)
    t_max = image.select("temperature_2m_max").subtract(273.15)
    dewpoint = image.select("dewpoint_temperature_2m").subtract(273.15)
    es = saturation_vapor_pressure(ee, t_min).add(saturation_vapor_pressure(ee, t_max)).divide(2)
    ea = saturation_vapor_pressure(ee, dewpoint)
    vpd = es.subtract(ea).max(0)
    slope = saturation_vapor_pressure(ee, t_mean).multiply(4098).divide(t_mean.add(237.3).pow(2))
    psychrometric = image.select("surface_pressure").divide(1000).multiply(0.000665)
    wind10m = image.select("u_component_of_wind_10m").pow(2).add(image.select("v_component_of_wind_10m").pow(2)).sqrt()
    wind2m = wind10m.multiply(WIND_2M_FACTOR)
    net_radiation = image.select("surface_net_solar_radiation_sum").add(
        image.select("surface_net_thermal_radiation_sum")).divide(1e6)
    radiation_term = slope.multiply(net_radiation).multiply(0.408)
    aerodynamic_term = psychrometric.multiply(900).divide(t_mean.add(273)).multiply(wind2m).multiply(vpd)
    denominator = slope.add(psychrometric.multiply(wind2m.multiply(0.34).add(1)))
    et0 = radiation_term.add(aerodynamic_term).divide(denominator).max(0).rename("et0_mm_day").toFloat()
    return ee.Image(et0.copyProperties(image, ["system:time_start", "system:index"]))


def monthly_et0(ee, year: int, month: int, *, cast: bool = False):
    """(et0_YYYYMM band, days present): daily FAO-56 ET0 summed over the month, masked unless every day is present.
    ``cast``: 02 (PATCH32) ends its monthlyEt0Image with ``.toFloat()``; 01 does not."""
    start, end, expected = month_range(ee, year, month)
    raw = ee.ImageCollection(ERA5_DAILY_ID).filterDate(start, end).select(ERA5_ET0_BANDS)
    present = raw.size()
    template = ee.Image(daily_fao56_et0(ee, ee.Image(ee.ImageCollection(ERA5_DAILY_ID).select(ERA5_ET0_BANDS).first()))) \
        .multiply(0).updateMask(ee.Image.constant(0)).rename("et0_mm_day")
    complete = present.eq(expected)
    monthly = ee.Image(ee.Algorithms.If(present.gt(0), raw.map(lambda i: daily_fao56_et0(ee, i)).sum(), template)) \
        .updateMask(ee.Image.constant(complete))
    if cast:
        return monthly.rename(f"et0_{year}{month:02d}").toFloat(), present
    return monthly.rename(f"et0_{year}{month:02d}").set({"year": year, "month": month, "days_present": present,
                                                        "days_expected": expected, "month_complete": complete}), present


def et0_chunk(ee, a: int, b: int, *, patch: bool = False):
    stack, days = empty_image(ee), {}
    for y in range(a, b + 1):
        for m in range(1, 13):
            band, days[f"{y}{m:02d}"] = monthly_et0(ee, y, m, cast=patch)
            stack = stack.addBands(band)
    projection = ee.ImageCollection(ERA5_DAILY_ID).first().select("temperature_2m").projection()
    return stack.addBands(_grid_band(ee, "source_grid_total", projection)), days, projection


def _et0_props(a, b):
    return {"source": ET0_SOURCE, "product": ERA5_DAILY_ID, "chunk_start_year": a, "chunk_end_year": b,
            "temporal_resolution": "monthly_total", "unit": "mm_month", "et0_method": ET0_METHOD}


def et0_table(ee, a: int, b: int, admins):
    stack, days, projection = et0_chunk(ee, a, b)
    table = reduce_to_points(ee, stack, admins, projection, projection.nominalScale())
    return _with_days_present(ee, table.map(lambda f: ee.Feature(f).set(_et0_props(a, b))), days)


def patch32_table(ee, a: int, b: int, buffered):
    stack, days, projection = et0_chunk(ee, a, b, patch=True)
    props = {**_et0_props(a, b), "et0_spatial_fallback": 1, "fallback_method": "BUFFERED_ERA5LAND_MEAN",
             "fallback_buffer_m": PATCH32_BUFFER_M, "patch_version": "V2"}
    table = reduce_to_points(ee, stack, buffered, projection, projection.nominalScale())
    return _with_days_present(ee, table.map(lambda f: ee.Feature(f).set(props)), days)


# --------------------------------------------------------------------------- planning


@dataclass(frozen=True)
class TableJob:
    name: str                     # existing basename (the consumer's TableRefs key)
    kind: str                     # vi | prcp | et0 | patch32
    key: str | None               # sensor or precipitation source
    years: tuple[int, int]

    @property
    def script(self) -> str:
        return "seasonal/02_et0_patch32_update.js" if self.kind == "patch32" else "seasonal/01_vi_prcp_et0_update.js"


def demand(tables: Callable[[str, str], Any], *, origin: str, windows: pd.DataFrame) -> dict[str, Any]:
    """The unsaved periods of the table-based bases, by the same scheduling the climate update applies."""
    out: dict[str, Any] = {"monthly": {}, "seasonal": {}}
    for base in TABLE_BASES:
        frame, _ = cl.read_monthly(tables(base, cl.MONTHLY))
        out["monthly"][base] = cl.months_to_update(set(frame["month"]), origin)
        groups = []
        for (year, season), win in cl.pending_seasons(tables(base, cl.SEASONAL), windows, origin).groupby(
                ["season_year", "season"], sort=True):
            groups.append({"season_year": int(year), "season": season, "span": list(ct.season_span(win))})
        out["seasonal"][base] = groups
    return out


def required_tables(need: Mapping[str, Any], refs: ct.TableRefs) -> list[TableJob]:
    """Every table the demanded periods read that is not completed static history (see module docstring)."""
    vi: set[tuple[str, int]] = set()
    for month in need["monthly"]["evi_anom"]:
        y, m = (int(x) for x in month.split("-"))
        vi |= {(s, p["calendar_year"]) for s in VI_SOURCES for p in ct.month_plan(s, y, m)}
    for g in need["seasonal"]["evi_anom"]:
        vi |= {(s, y) for s in VI_SOURCES for y in (g["season_year"] - 1, g["season_year"])}
    months: set[str] = set()
    for base in ("spi03", "spei03"):
        for month in need["monthly"][base]:
            months.update(ct.input_months(month, month))
        for g in need["seasonal"][base]:
            months.update(ct.input_months(*g["span"]))
    chunks = sorted({(a, b) for month in months for a, b in refs.year_chunks
                     if a <= int(month[:4]) <= b and a >= FIRST_PRODUCED_CHUNK})
    missing = sorted(m for m in months if int(m[:4]) >= FIRST_PRODUCED_CHUNK
                     and not any(a <= int(m[:4]) <= b for a, b in refs.year_chunks))
    if missing:
        raise ClimateProcessingFailure(f"demanded drought input months {missing[:3]} lie beyond the reader's chunks "
                                       f"{refs.year_chunks[-1]}")
    jobs = [TableJob(refs.vi_current.format(label=VI_SOURCES[s]["label"], year=y), "vi", s, (y, y)) for s, y in sorted(vi)]
    for a, b in chunks:
        jobs += [TableJob(refs.prcp.format(label=lab, a=a, b=b), "prcp", s, (a, b)) for s, lab in ct.SPI_SOURCES.items()]
        jobs += [TableJob(refs.et0.format(a=a, b=b), "et0", None, (a, b)),
                 TableJob(refs.et0_patch.format(a=a, b=b), "patch32", None, (a, b))]
    return jobs


def output_version(run_id: str, execution_month: str) -> str:
    """Immutable per-run version: execution month + run ID (asset-safe) + an 8-hex digest of the exact run ID."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", run_id)
    return f"M{execution_month.replace('-', '')}_{safe}_{hashlib.sha256(run_id.encode()).hexdigest()[:8]}"


# --------------------------------------------------------------------------- readback validation


def _constant(frame: pd.DataFrame, column: str, label: str):
    if column not in frame.columns:
        raise ClimateProcessingFailure(f"{label}: produced table lacks {column}")
    values = frame[column].dropna().astype(str).unique()
    if len(values) != 1 or frame[column].isna().any():
        raise ClimateProcessingFailure(f"{label}: {column} must be one value on every row, got {list(values)[:3]}")
    return values[0]


def readback(job: TableJob, frame: pd.DataFrame) -> dict[str, bool]:
    """Validate a completed asset's identity properties, units and admin codes; return its declared completeness."""
    label = job.name
    if frame.empty or frame["admin_code"].isna().any() or frame["admin_code"].duplicated().any():
        raise ClimateProcessingFailure(f"{label}: produced table has no rows or missing/duplicate admin_code")
    if job.kind == "vi":
        cfg = VI_SOURCES[job.key]
        expect = {"sensor": cfg["label"], "product": cfg["collection"], "observation_year": str(job.years[0]),
                  "temporal_resolution": "16_day", "spatial_product": "CMG_0P05_DEG"}
    else:
        a, b = job.years
        expect = {"chunk_start_year": str(a), "chunk_end_year": str(b), "temporal_resolution": "monthly_total",
                  "unit": "mm_month"}
        expect.update({"source": ct.SPI_SOURCES[job.key], "product": PRECIP_SOURCES[job.key]["collection"]}
                      if job.kind == "prcp" else {"source": ET0_SOURCE, "product": ERA5_DAILY_ID, "et0_method": ET0_METHOD})
        if job.kind == "patch32":
            expect.update({"et0_spatial_fallback": "1", "fallback_method": "BUFFERED_ERA5LAND_MEAN",
                           "fallback_buffer_m": str(PATCH32_BUFFER_M), "patch_version": "V2"})
    for column, value in expect.items():
        got = _constant(frame, column, label)
        if got != value and not (_number(got) is not None and _number(got) == _number(value)):
            raise ClimateProcessingFailure(f"{label}: {column} is {got!r}, expected {value!r}")
    if job.kind == "patch32" and set(frame["admin_code"].astype(str)) != {str(c) for c in PATCH32_CODES}:
        raise ClimateProcessingFailure(f"{label}: PATCH32 admin codes differ from the 32 targets")
    means = re.compile(r"(?:evi|ndvi|used1km)_\d{8}_mean" if job.kind == "vi" else r"(?:prcp|et0)_\d{6}_mean")
    for column in [c for c in frame.columns if means.fullmatch(str(c))]:
        values = ct.strict_numeric(frame[column], f"{label} {column}")      # non-numeric text fails; null = masked
        if np.isinf(values).any():
            raise ClimateProcessingFailure(f"{label}: {column} has infinite values")
    if job.kind == "vi":
        listed = _constant(frame, "composite_dates", label)    # absent, null or mixed metadata fails here
        if listed == "":
            return {}                                          # explicit empty listing: no published composite yet
        dates = listed.split(",")
        if any(not re.fullmatch(r"\d{8}", d) for d in dates) or len(set(dates)) != len(dates):
            raise ClimateProcessingFailure(f"{label}: malformed composite_dates {dates[:3]}")
        return {tag: True for tag in dates}
    periods = {}
    for y in range(job.years[0], job.years[1] + 1):
        for m in range(1, 13):
            present = _number(_constant(frame, f"days_present_{y}{m:02d}", label))
            if present is None or present < 0 or present != int(present):
                raise ClimateProcessingFailure(f"{label}: days_present_{y}{m:02d} is not a day count")
            periods[f"{y}{m:02d}"] = int(present) == pycalendar.monthrange(y, m)[1]
    return periods


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- production


@dataclass
class Production:
    """This run's produced tables (``TableRefs.produced``), their read-back frames (handed to the consumers so they are
    not read twice) and the receipts linking run, producer, task, asset and periods."""
    produced: dict[str, ct.ProducedTable] = field(default_factory=dict)
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    report: dict[str, Any] = field(default_factory=dict)


@dataclass
class TableProducer:
    transport: Any                     # ee_transport.EETransport (submit/wait/cancel asset exports, read_asset_table)
    inputs: AssetRefs                  # shared input polygons (han-sandbox by default)
    output_root: str                   # writable EE asset root, e.g. projects/feisty-flames-511718-d4/assets/
    run_id: str
    execution_month: str

    def __post_init__(self):
        if not re.fullmatch(r"projects/[^/]+/assets/(?:[^/]+/)*", self.output_root or ""):
            raise ClimateProcessingFailure(f"producer output root {self.output_root!r} must be projects/<p>/assets/.../")
        if self.output_root.startswith(self.inputs.root):
            raise ClimateProcessingFailure("producer output root must not be the shared read-only input root")

    def asset_id(self, job: TableJob) -> str:
        return f"{self.output_root}{job.name}__{output_version(self.run_id, self.execution_month)}"

    def graph(self, ee, job: TableJob, admins, buffered):
        a, b = job.years
        if job.kind == "vi":
            return vi_table(ee, job.key, a, admins)
        if job.kind == "prcp":
            return precipitation_table(ee, job.key, a, b, admins)
        return et0_table(ee, a, b, admins) if job.kind == "et0" else patch32_table(ee, a, b, buffered)

    def run(self, tables: Callable[[str, str], Any], *, origin: str, windows: pd.DataFrame) -> Production:
        refs = ct.TableRefs(year_chunks=ct.year_chunks(int(origin[:4])))
        need = demand(tables, origin=origin, windows=windows)
        jobs = required_tables(need, refs)
        report: dict[str, Any] = {"producer_version": PRODUCER_VERSION, "scripts": dict(SCRIPTS), "run_id": self.run_id,
                                  "version": output_version(self.run_id, self.execution_month), "demand": need,
                                  "jobs": [j.name for j in jobs], "receipts": []}
        if not jobs:
            report["skipped"] = "every evi_anom/spi03/spei03 period through O is already retained; nothing produced"
            return Production(report=report)
        ee = self.transport.ee
        absent = self.transport.missing_assets(self.inputs.admins())
        if absent:
            raise ClimateProcessingFailure(f"unreadable producer input polygons (configure the input root): {absent}")
        admins = admin_features(ee, self.inputs)
        targets = patch32_targets(ee, self.inputs)
        if any(j.kind == "patch32" for j in jobs):
            count = self.transport.evaluate(ee.Dictionary({"rows": targets.size(),
                                                           "unique_codes": targets.aggregate_count_distinct("admin_code")}))
            if not isinstance(count, Mapping) or count.get("rows") != 32 or count.get("unique_codes") != 32:
                raise ClimateProcessingFailure(f"PATCH32 target selection must have 32 rows and distinct codes: {count}")
        ids = {j.name: self.asset_id(j) for j in jobs}
        reused = [i for i in ids.values() if i not in self.transport.missing_assets([i])]
        if reused:
            raise ClimateProcessingFailure(f"output assets already exist (never reused): {reused}")
        handles = []
        try:
            for job in jobs:                                   # submit everything before waiting (one task per table)
                handles.append((job, self.transport.submit_asset_export(
                    self.graph(ee, job, admins, buffered_patch32(ee, targets)), ids[job.name], job.name)))
            receipts = [(job, self.transport.wait_asset_export(handle)) for job, handle in handles]
        except BaseException:
            report["cancelled"] = [self.transport.cancel_asset_export(h) for _, h in handles]
            raise
        production = Production(report=report)
        for job, receipt in receipts:
            frame = self.transport.read_asset_table(ids[job.name])
            table = ct.ProducedTable(ids[job.name], readback(job, frame))
            refs_one = ct.TableRefs(year_chunks=refs.year_chunks, produced={job.name: table})
            ct.check_produced(frame, job.name, table, refs_one, "evi" if job.kind == "vi" else None)
            production.produced[job.name] = table
            production.frames[ids[job.name]] = frame
            complete = sorted(k for k, ok in table.periods.items() if ok)
            report["receipts"].append({"table": job.name, "asset_id": ids[job.name], "script": job.script,
                                       "script_sha256": SCRIPTS[job.script], "task_id": receipt.get("task_id"),
                                       "state": receipt.get("state"), "rows": int(len(frame)),
                                       "complete_periods": len(complete), "last_complete": complete[-1] if complete else None})
        return production
