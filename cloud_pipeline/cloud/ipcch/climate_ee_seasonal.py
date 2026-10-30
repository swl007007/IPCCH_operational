"""Growing-season Earth Engine providers ported from the shared seasonal scripts (task 10-29; R1, R33, R34, R40).

The three raster scripts use different EE structures and are ported as such (spec: research/cp3/climate-script-specs.md):

* ``seasonal/rainfall.js`` (prcp_anom, prcp_z, rainy_days, cdd): the admin calendars are PAINTED into rasters (all
  admins in admin_idx order, as the script does, so overlapping polygons keep the script's paint order); relative day
  numbers from Jan 1 of the season year (cross-year starts from the previous year, no Feb-29 clamp: offset arithmetic);
  daily values masked by "active on date"; ``finishDailySum`` (full pixel coverage >= 0.999999 required); CDD with the
  script's array accumulation (latest reset day, run = day - reset, max); prcp_z = complete-month total z weighted by
  calendar-overlap days. One ``reduceRegions`` (tileScale 8 for ANOM_Z, 16 for RAIN_CDD, maxPixelsPerRegion 1e9).
* ``seasonal/temperature.js``: per feature (``FeatureCollection.map``), exact vector calendar with the ``use_Feb28``
  clamp, the feature's own date filter, the monthly script's daily metrics, means for anomalies / sums otherwise, any
  valid day (no coverage threshold), ``reduceRegion`` over the feature geometry.
* ``seasonal/soil_moisture.js``: per feature, monthly z (all samples of the month averaged, baseline SD > 0) for the 24
  months of (season_year-1, season_year), weighted by the feature's calendar-overlap days; pixel z = sum(numerator) /
  supported days; ``reduceRegion``. The script's monthly cache images are an optimisation and are computed on the fly.

The scripts' hard run windows (season years 2015-2021, data end 2022-01-01) are run parameters: ``data_end`` is the first
day after the feature origin, and only completed seasons are requested (R33). Per-feature/per-season arithmetic after the
reduction runs locally (``finalize_*``). Availability: a source publishes a season once its collection has published
through the last day of the requested windows (GLDAS: through that day's 21:00 UTC slot); gaps inside a season follow
each script's own available-observation semantics (temperature/soil: any valid observation; rainfall: full pixel
coverage), and dates outside the season never matter. Rainfall date bounds come from the FULL season calendar (all
admins, both seasons of the season year, as the script paints them) and data reads are clamped at the run's data end
(first day after the feature origin).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from cloud.ipcch.climate import ClimateProcessingFailure, SourceOutcome
from cloud.ipcch.climate_ee import (MISSING, RAIN_SOURCES, RAIN_THRESHOLD_MM, SOIL_SOURCES, TEMP_METRICS, TEMP_SOURCES,
                                    TILE_SCALE, AssetRefs, EEBackend, _baseline_collection, _baseline_for_month,
                                    admin_collection)

COVERAGE_USABLE = 0.999999
RAIN_TILE = {"anomz": 8, "cdd": 16}
RAIN_MAX_PIXELS = 1e9
SEASON_MAX_PIXELS = 1e10
GS_FAMILIES = {
    "gs_rain_anomz": ("seasonal/rainfall.js", ("prcp_anom", "prcp_z"), RAIN_SOURCES),
    "gs_rain_cdd": ("seasonal/rainfall.js", ("rainy_days", "cdd"), RAIN_SOURCES),
    "gs_temperature": ("seasonal/temperature.js", TEMP_METRICS, TEMP_SOURCES),
    "gs_soil": ("seasonal/soil_moisture.js", ("sm_z",), SOIL_SOURCES)}
GS_BASE_FAMILY = {b: f for f, (_, bases, _) in GS_FAMILIES.items() for b in bases}


def _days_before_month(year: int, month: int) -> int:
    return (date(year, month, 1) - date(year, 1, 1)).days


def _days_in_year(year: int) -> int:
    return (date(year + 1, 1, 1) - date(year, 1, 1)).days


def _rel(d: date, year: int) -> int:
    return (d - date(year, 1, 1)).days


def requested_admins(ee, refs: AssetRefs, codes: list[str]):
    return admin_collection(ee, refs).filter(ee.Filter.inList("admin_code", ee.List(codes)))


# --------------------------------------------------------------------------- seasonal/rainfall.js


def _rain_calendar(ee, painted, season, year, projection):
    """calendarImages: painted calendar rasters (relative days from Jan 1 of ``year``)."""
    def prop(name):
        return ee.Image(0).toFloat().paint(painted, name).setDefaultProjection(projection)

    def offset(month_img, day_img, y):
        out = ee.Image(0).toFloat().setDefaultProjection(projection)
        for m in range(1, 13):
            out = out.where(month_img.eq(m), day_img.subtract(1).add(_days_before_month(y, m)))
        return out

    valid = prop(f"{season}_calendar_valid_num").eq(1)
    sos_m, sos_d = prop(f"{season}_sos_month"), prop(f"{season}_sos_day")
    eos_m, eos_d = prop(f"{season}_eos_month"), prop(f"{season}_eos_day")
    cross = prop(f"{season}_cross_year").eq(1)
    same = offset(sos_m, sos_d, year)
    previous = offset(sos_m, sos_d, year - 1).subtract(_days_in_year(year - 1))
    start = same.where(cross, previous)
    end = offset(eos_m, eos_d, year).add(1)
    duration = end.subtract(start)
    valid = valid.And(duration.gt(0)).And(duration.lte(367))
    return {"valid": valid, "start": start, "end": end, "duration": duration}


def _active(cal, rel_day):
    return cal["valid"].And(cal["start"].lte(rel_day)).And(cal["end"].gt(rel_day))


def _overlap(ee, cal, a, b):
    return (cal["end"].min(ee.Image.constant(b)).subtract(cal["start"].max(ee.Image.constant(a))).max(0)
            .updateMask(cal["valid"]).toFloat())


def rain_seasonal_image(ee, family: str, source: str, year: int, bounds: tuple[str, str], refs: AssetRefs):
    """The script's metric image for one RUN_YEAR: bands {s}_{root} and {s}_{root}_coverage_fraction, s in s1/s2."""
    cfg = RAIN_SOURCES[source]
    key = source
    projection = ee.Image(ee.ImageCollection(cfg["collection"]).select(cfg["band"]).first()).projection()
    painted = admin_collection(ee, refs).map(lambda f: ee.Feature(f).set({
        "s1_calendar_valid_num": ee.Number(ee.Algorithms.If(ee.Feature(f).get("s1_calendar_valid"), 1, 0)),
        "s2_calendar_valid_num": ee.Number(ee.Algorithms.If(ee.Feature(f).get("s2_calendar_valid"), 1, 0))}))
    raw = (ee.ImageCollection(cfg["collection"]).filterDate(bounds[0], bounds[1]).select(cfg["band"])
           .map(lambda img: ee.Image(img).multiply(cfg["factor"]).max(0).rename("prcp_mm").toFloat()
                .copyProperties(img, ["system:time_start"])).sort("system:time_start"))
    origin = ee.Date.fromYMD(year, 1, 1)
    cals = {s: _rain_calendar(ee, painted, s, year, projection) for s in ("s1", "s2")}

    def seed(band):
        return ee.Image.constant(0).rename(band).toFloat().setDefaultProjection(projection).selfMask()

    def finish(prepared, season, cal, name):
        vb = f"{season}_value"
        with_seed = prepared.merge(ee.ImageCollection([seed(vb)]))
        valid_days = with_seed.select(vb).count()
        coverage = valid_days.divide(cal["duration"]).clamp(0, 1).unmask(0).updateMask(cal["valid"]).toFloat()
        usable = coverage.gte(COVERAGE_USABLE).And(cal["valid"])
        value = with_seed.select(vb).sum().updateMask(usable).updateMask(cal["valid"])
        return [value.rename(name), coverage.rename(name + "_coverage_fraction")]

    def per_day(fn):
        def wrapped(image):
            image = ee.Image(image)
            rel = image.date().difference(origin, "day").floor()
            v = fn(image)
            return ee.Image.cat([v.updateMask(_active(cals["s1"], rel)).rename("s1_value"),
                                 v.updateMask(_active(cals["s2"], rel)).rename("s2_value")]).toFloat() \
                .copyProperties(image, ["system:time_start"])
        return wrapped

    bands = []
    if family == "gs_rain_anomz":
        baselines = _baseline_collection(ee, refs.baselines("rain_anomz", cfg["label"]))

        def anomaly(image):
            d = image.date()
            normal = _baseline_for_month(ee, baselines, ee.Number(d.get("month"))).select(
                ee.List([ee.String("daily_normal_d").cat(ee.Number(d.get("day")).format("%02d"))])).rename("daily_normal")
            return image.select("prcp_mm").subtract(normal)

        prepared = raw.map(per_day(anomaly))
        root = f"prcp_anom_gs_{key}"
        for s in ("s1", "s2"):
            bands += finish(prepared, s, cals[s], f"{s}_{root}")
        zroot = f"prcp_z_gs_{key}"
        num = {"s1": [], "s2": []}
        den = {"s1": [], "s2": []}
        for cy in (year - 1, year):
            for m in range(1, 13):
                ms = ee.Date.fromYMD(cy, m, 1)
                me = ms.advance(1, "month")
                rs = _rel(date(cy, m, 1), year)
                re_ = _rel(date(cy + (m == 12), 1 if m == 12 else m + 1, 1), year)
                sub = raw.filterDate(ms, me).merge(ee.ImageCollection([seed("prcp_mm")]))
                complete = sub.select("prcp_mm").count().eq(me.difference(ms, "day"))
                total = sub.select("prcp_mm").sum()
                base = _baseline_for_month(ee, baselines, m)
                sd = base.select("monthly_total_sd_mm")
                z = total.subtract(base.select("monthly_total_mean_mm")).divide(sd).updateMask(sd.gt(0)).updateMask(complete)
                for s in ("s1", "s2"):
                    w = _overlap(ee, cals[s], rs, re_).updateMask(z.mask()).unmask(0)
                    num[s].append(z.unmask(0).multiply(w))
                    den[s].append(w)
        for s in ("s1", "s2"):
            d = ee.ImageCollection.fromImages(den[s]).sum()
            cov = d.divide(cals[s]["duration"]).clamp(0, 1).unmask(0).updateMask(cals[s]["valid"]).toFloat()
            usable = cov.gte(COVERAGE_USABLE).And(cals[s]["valid"])
            zz = ee.ImageCollection.fromImages(num[s]).sum().divide(d).updateMask(usable).updateMask(cals[s]["valid"])
            bands += [zz.rename(f"{s}_{zroot}"), cov.rename(f"{s}_{zroot}_coverage_fraction")]
        roots = [root, zroot]
    else:
        prepared = raw.map(per_day(lambda image: image.select("prcp_mm").gte(RAIN_THRESHOLD_MM).toFloat()))
        root = f"rainy_days_gs_{key}"
        for s in ("s1", "s2"):
            bands += finish(prepared, s, cals[s], f"{s}_{root}")
        croot = f"cdd_gs_{key}"
        for s in ("s1", "s2"):
            cal = cals[s]

            def seq(image, cal=cal):
                image = ee.Image(image)
                rel = image.date().difference(origin, "day").floor()
                day_img = ee.Image.constant(rel).rename("day").toInt16().setDefaultProjection(projection)
                active = _active(cal, rel)
                observed = image.select("prcp_mm").mask().gt(0).And(active).rename("observed").toInt16()
                dry = (image.select("prcp_mm").lt(RAIN_THRESHOLD_MM).unmask(0).And(active).And(observed.eq(1))
                       .rename("dry").toInt16())
                reset = cal["start"].subtract(1).toInt16().where(dry.Not(), day_img).rename("reset_day")
                return ee.Image.cat([dry, observed, day_img, reset]).toInt16().copyProperties(image, ["system:time_start"])

            sequence = raw.map(seq).sort("system:time_start")
            latest = sequence.select("reset_day").toArray().arrayAccum(0, ee.Reducer.max())
            run = sequence.select("day").toArray().subtract(latest).multiply(sequence.select("dry").toArray())
            maximum = run.arrayReduce(ee.Reducer.max(), [0]).arrayGet([0, 0])
            observed_days = sequence.select("observed").sum()
            cov = observed_days.divide(cal["duration"]).clamp(0, 1).unmask(0).updateMask(cal["valid"]).toFloat()
            usable = cov.gte(COVERAGE_USABLE).And(cal["valid"])
            bands += [maximum.updateMask(usable).updateMask(cal["valid"]).rename(f"{s}_{croot}"),
                      cov.rename(f"{s}_{croot}_coverage_fraction")]
        roots = [root, croot]
    return ee.Image.cat(bands).toFloat(), roots, projection


def rain_seasonal_table(ee, family, source, year, bounds, refs, codes):
    image, roots, projection = rain_seasonal_image(ee, family, source, year, bounds, refs)
    names = [f"{s}_{r}{suffix}" for s in ("s1", "s2") for r in roots for suffix in ("", "_coverage_fraction")]
    selected = image.select(names)
    area = ee.Image.pixelArea().setDefaultProjection(projection)
    reduction = ee.Image.cat([selected.multiply(area).rename([n + "_area_sum" for n in names]),
                              selected.mask().multiply(area).rename([n + "_valid_area" for n in names])]).toDouble()
    admins = requested_admins(ee, refs, codes).map(lambda f: ee.Feature(f).set({
        "s1_calendar_valid_num": ee.Number(ee.Algorithms.If(ee.Feature(f).get("s1_calendar_valid"), 1, 0)),
        "s2_calendar_valid_num": ee.Number(ee.Algorithms.If(ee.Feature(f).get("s2_calendar_valid"), 1, 0))}))
    reduced = reduction.reduceRegions(collection=admins, reducer=ee.Reducer.sum(), crs=projection,
                                      scale=projection.nominalScale(), tileScale=RAIN_TILE["anomz" if "anomz" in family else "cdd"],
                                      maxPixelsPerRegion=RAIN_MAX_PIXELS)
    cols = ["admin_code", "s1_calendar_valid_num", "s2_calendar_valid_num"] + [n + k for n in names for k in ("_area_sum", "_valid_area")]
    return reduced.map(lambda f: ee.Feature(None, ee.Feature(f).toDictionary(cols))), cols, roots


def finalize_rain(raw: pd.DataFrame, roots: list[str], season: str) -> dict[str, pd.DataFrame]:
    """makeSeasonRows arithmetic: value = area_sum / valid_area (no 1e-12 guard) when the calendar is valid and the
    valid area > 0; coverage likewise (clamped); status INVALID_CALENDAR / MISSING_DATA / COMPLETE / PARTIAL_DATA."""
    valid = pd.to_numeric(raw[f"{season}_calendar_valid_num"], errors="coerce").fillna(0).to_numpy() == 1
    out = {}
    for root in roots:
        b = f"{season}_{root}"
        va = pd.to_numeric(raw[b + "_valid_area"], errors="coerce").to_numpy(float)
        has = np.isfinite(va) & (va > 0)
        with np.errstate(invalid="ignore", divide="ignore"):
            value = np.where(valid & has, pd.to_numeric(raw[b + "_area_sum"], errors="coerce").to_numpy(float) / va, np.nan)
        cva = pd.to_numeric(raw[b + "_coverage_fraction_valid_area"], errors="coerce").to_numpy(float)
        has_c = np.isfinite(cva) & (cva > 0)
        with np.errstate(invalid="ignore", divide="ignore"):
            cov = np.where(valid & has_c, np.clip(pd.to_numeric(raw[b + "_coverage_fraction_area_sum"], errors="coerce").to_numpy(float) / cva, 0, 1), np.nan)
        status = np.where(~valid, "INVALID_CALENDAR", np.where(~has, "MISSING_DATA", np.where(cov >= COVERAGE_USABLE, "COMPLETE", "PARTIAL_DATA")))
        base = root.split("_gs_")[0]
        out[base] = pd.DataFrame({"admin_code": raw["admin_code"].astype(str).to_numpy(), "value": value, "coverage": cov, "status": status})
    return out


# --------------------------------------------------------------------------- seasonal/temperature.js and soil_moisture.js (per feature)


def calendar_date(ee, y, m, d):
    """calendarDate: day clamped to the month's last day (use_Feb28)."""
    y, m, d = ee.Number(y).toInt(), ee.Number(m).toInt(), ee.Number(d).toInt()
    first = ee.Date.fromYMD(y, m, 1)
    last = ee.Number(first.advance(1, "month").advance(-1, "day").get("day"))
    return first.advance(d.min(last).subtract(1), "day")


def _number(ee, value, fallback):
    return ee.Number(ee.Algorithms.If(ee.Algorithms.IsEqual(value, None), fallback, value))


def admin_calendar(ee, feature, season, season_year, data_end):
    f = ee.Feature(feature)
    sy = ee.Number(season_year).toInt()
    cross = _number(ee, f.get(f"{season}_cross_year"), 0).toInt()
    start = calendar_date(ee, sy.subtract(cross), _number(ee, f.get(f"{season}_sos_month"), 1), _number(ee, f.get(f"{season}_sos_day"), 1))
    end_incl = calendar_date(ee, sy, _number(ee, f.get(f"{season}_eos_month"), 1), _number(ee, f.get(f"{season}_eos_day"), 1))
    end_excl = end_incl.advance(1, "day")
    duration = end_excl.difference(start, "day").toInt()
    valid = _number(ee, f.get(f"{season}_calendar_valid"), 0).eq(1).And(duration.gt(0))
    permitted = ee.Date(ee.Number(end_excl.millis()).min(ee.Date(data_end).millis()))
    return {"start": start, "end_exclusive": end_excl, "duration": duration, "valid": valid, "permitted_end": permitted,
            "has_time": permitted.millis().gt(start.millis())}


def temperature_seasonal_table(ee, source, season, season_year, data_end, refs, codes):
    cfg = TEMP_SOURCES[source]
    src = ee.ImageCollection(cfg["collection"]).select(cfg["bands"])
    proj = ee.Image(src.first()).select(cfg["proj_band"]).projection()
    baselines = _baseline_collection(ee, refs.baselines("temperature", cfg["label"]))
    cpc = cfg["label"] == "CPC"

    def daily_metrics(image):
        image = ee.Image(image)
        d = image.date()
        day = ee.Number(d.get("day")).format("%02d")
        base = _baseline_for_month(ee, baselines, d.get("month"))
        if cpc:
            tmin, tmax = image.select("tmin"), image.select("tmax")
            tmean = tmin.add(tmax).divide(2)
        else:
            tmean = image.select("temperature_2m").subtract(273.15)
            tmin = image.select("temperature_2m_min").subtract(273.15)
            tmax = image.select("temperature_2m_max").subtract(273.15)
        sel = lambda p: base.select(ee.List([ee.String(p).cat(day)]))
        return ee.Image.cat([tmean.subtract(sel("tmean_normal_d")).rename("tmean_anom"),
                             tmax.subtract(sel("tmax_normal_d")).rename("tmax_anom"),
                             tmax.gt(sel("tmax_p95_d")).rename("hot_days_p95"),
                             tmax.min(30).add(tmin.max(10)).divide(2).subtract(10).max(0).rename("gdd"),
                             tmax.subtract(30).max(0).rename("edd")]).toFloat().copyProperties(image, ["system:time_start"])

    def calculate(feature):
        feature = ee.Feature(feature)
        cal = admin_calendar(ee, feature, season, season_year, data_end)
        raw = (src.filter(ee.Filter.gte("system:time_start", cal["start"].millis()))
               .filter(ee.Filter.lt("system:time_start", cal["permitted_end"].millis())))
        seed = ee.Image.constant([0, 0, 0, 0, 0]).rename(list(TEMP_METRICS)).toFloat().setDefaultProjection(proj).selfMask()
        daily = ee.ImageCollection.fromImages([seed]).merge(raw.map(daily_metrics))
        totals, counts = daily.select(list(TEMP_METRICS)).sum(), daily.select(list(TEMP_METRICS)).count()
        area = ee.Image.pixelArea().setDefaultProjection(proj)
        window = ee.Image.constant(cal["valid"].And(cal["has_time"]))
        bands = []
        for m in TEMP_METRICS:
            observed = counts.select(m)
            usable = observed.gt(0).And(window)
            value = totals.select(m)
            if m in ("tmean_anom", "tmax_anom"):
                value = value.divide(observed.max(1))
            value = value.updateMask(usable)
            bands += [value.multiply(area).rename(f"{m}_num"), area.updateMask(value.mask()).rename(f"{m}_area"),
                      observed.updateMask(usable).multiply(area).rename(f"{m}_obs")]
        stats = ee.Image.cat(bands).toDouble().reduceRegion(reducer=ee.Reducer.sum(), geometry=feature.geometry(), crs=proj,
                                                            scale=proj.nominalScale(), maxPixels=SEASON_MAX_PIXELS, tileScale=TILE_SCALE)
        return ee.Feature(None, stats).set({"admin_code": feature.get("admin_code"), "calendar_valid": cal["valid"],
                                            "duration": cal["duration"]})

    cols = ["admin_code", "calendar_valid", "duration"] + [f"{m}_{k}" for m in TEMP_METRICS for k in ("num", "area", "obs")]
    return requested_admins(ee, refs, codes).map(calculate), cols


def finalize_temperature(raw: pd.DataFrame) -> dict[str, pd.DataFrame]:
    valid = pd.to_numeric(raw["calendar_valid"], errors="coerce").fillna(0).to_numpy() == 1
    duration = pd.to_numeric(raw["duration"], errors="coerce").to_numpy(float)
    out = {}
    for m in TEMP_METRICS:
        a = pd.to_numeric(raw[f"{m}_area"], errors="coerce").fillna(0).to_numpy(float)
        present = a > 0
        value = np.where(present, pd.to_numeric(raw[f"{m}_num"], errors="coerce").fillna(0).to_numpy(float) / np.maximum(a, 1e-12), np.nan)
        observed = np.where(present, pd.to_numeric(raw[f"{m}_obs"], errors="coerce").fillna(0).to_numpy(float) / np.maximum(a, 1e-12), 0.0)
        status = np.where(~valid, "INVALID_CALENDAR", np.where(~present, "MISSING_DATA",
                                                               np.where(observed >= duration - 1e-6, "COMPLETE", "PARTIAL_DATA")))
        out[m] = pd.DataFrame({"admin_code": raw["admin_code"].astype(str).to_numpy(), "value": np.where(valid, value, np.nan),
                               "coverage": np.clip(observed / np.maximum(duration, 1), 0, 1), "status": status})
    return out


def soil_seasonal_table(ee, source, season, season_year, data_end, refs, codes):
    cfg = SOIL_SOURCES[source]
    src = ee.ImageCollection(cfg["collection"]).select(cfg["band"])
    proj = ee.Image(src.first()).projection()
    baselines = refs.baselines("soil", cfg["label"])
    images = []
    for y in (season_year - 1, season_year):
        for m in range(1, 13):
            s, e = date(y, m, 1), date(y + (m == 12), 1 if m == 12 else m + 1, 1)
            seed = ee.Image.constant(0).rename("sm").toFloat().setDefaultProjection(proj).selfMask()
            raw = src.filterDate(s.isoformat(), e.isoformat()).map(lambda img: ee.Image(img).select([0]).rename("sm").toFloat())
            red = ee.ImageCollection.fromImages([seed]).merge(raw).reduce(ee.Reducer.mean().combine(reducer2=ee.Reducer.count(), sharedInputs=True))
            count = red.select("sm_count").unmask(0, False)
            base = ee.Image(baselines[m - 1])
            sd = base.select("sm_monthly_sd")
            z = red.select("sm_mean").subtract(base.select("sm_monthly_mean")).divide(sd.updateMask(sd.gt(0))).updateMask(count.gt(0))
            support = z.mask().gt(0).unmask(0, False)
            expected = (e - s).days * cfg["per_day"]
            img = ee.Image.cat([z.unmask(0, False).multiply(support).rename("numerator"), support.rename("days"),
                                count.lt(expected).multiply(support).rename("incomplete"),
                                count.gt(expected).multiply(support).rename("excess")]).toDouble().setDefaultProjection(proj)
            ms = int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp() * 1000)
            me = int(datetime(e.year, e.month, 1, tzinfo=timezone.utc).timestamp() * 1000)
            images.append(img.set({"month_start_millis": ms, "month_end_millis": me}))
    monthly = ee.ImageCollection.fromImages(images)
    area_img = ee.Image.pixelArea().setDefaultProjection(proj)
    bands = ["numerator", "days", "incomplete", "excess"]

    def calculate(feature):
        feature = ee.Feature(feature)
        cal = admin_calendar(ee, feature, season, season_year, data_end)
        has_time = cal["valid"].And(cal["has_time"])

        def weight(image):
            image = ee.Image(image)
            o_start = ee.Number(cal["start"].millis()).max(ee.Number(image.get("month_start_millis")))
            o_end = ee.Number(cal["permitted_end"].millis()).min(ee.Number(image.get("month_end_millis")))
            days = ee.Number(ee.Algorithms.If(has_time, o_end.subtract(o_start).max(0).divide(86400000), 0))
            return image.select(bands).multiply(days)

        zero = ee.Image.constant([0, 0, 0, 0]).rename(bands).toDouble().setDefaultProjection(proj)
        sums = ee.ImageCollection.fromImages([zero]).merge(monthly.map(weight)).sum()
        supported = sums.select("days")
        pixel_z = sums.select("numerator").divide(supported.max(1))
        valid_area = area_img.updateMask(supported.gt(0))
        stack = ee.Image.cat([pixel_z.multiply(valid_area).rename("z_area"), valid_area.rename("area"),
                              supported.multiply(valid_area).rename("days_area"),
                              sums.select("incomplete").multiply(valid_area).rename("incomplete_area"),
                              sums.select("excess").multiply(valid_area).rename("excess_area")]).toDouble()
        stats = stack.reduceRegion(reducer=ee.Reducer.sum(), geometry=feature.geometry(), crs=proj, scale=proj.nominalScale(),
                                   maxPixels=SEASON_MAX_PIXELS, tileScale=TILE_SCALE)
        return ee.Feature(None, stats).set({"admin_code": feature.get("admin_code"), "calendar_valid": cal["valid"],
                                            "duration": cal["duration"], "geometry_area": feature.geometry().area(100)})

    cols = ["admin_code", "calendar_valid", "duration", "geometry_area", "z_area", "area", "days_area", "incomplete_area", "excess_area"]
    return requested_admins(ee, refs, codes).map(calculate), cols


def finalize_soil(raw: pd.DataFrame) -> dict[str, pd.DataFrame]:
    g = lambda c: pd.to_numeric(raw[c], errors="coerce").fillna(0).to_numpy(float)
    valid = g("calendar_valid") == 1
    area, duration = g("area"), g("duration")
    safe = np.where(area > 0, area, 1.0)
    value = np.where(area > 0, g("z_area") / safe, np.nan)
    support, incomplete = g("days_area") / safe, g("incomplete_area") / safe
    status = np.where(~valid, "INVALID_CALENDAR", np.where(g("geometry_area") <= 0, "INVALID_GEOMETRY", np.where(area <= 0, "MISSING_DATA",
                      np.where((support >= duration - 1e-6) & (incomplete <= 1e-6), "COMPLETE", "PARTIAL_DATA"))))
    return {"sm_z": pd.DataFrame({"admin_code": raw["admin_code"].astype(str).to_numpy(), "value": np.where(valid, value, np.nan),
                                  "coverage": np.where(valid, np.clip(support / np.maximum(duration, 1), 0, 1), np.nan), "status": status,
                                  "qa_abs_gt6_warning": ((area > 0) & (np.abs(np.nan_to_num(value)) > 6)).astype(int)})}


# --------------------------------------------------------------------------- provider


def window_bounds(windows: pd.DataFrame) -> tuple[str, str]:
    """[first day of the month of the earliest start, first day of the month after the latest inclusive end)."""
    s = pd.to_datetime(windows["gs_start_date"]).min()
    e = pd.to_datetime(windows["gs_end_date_exclusive"]).max() - pd.Timedelta(days=1)
    nxt = (e + pd.offsets.MonthBegin(1)).normalize()
    return s.strftime("%Y-%m-01"), nxt.strftime("%Y-%m-%d")


@dataclass
class SeasonalEEProvider:
    """``climate.update_seasonal`` fetch for the raster seasonal families; one export per (family, source, season_year,
    season, requested areas)."""
    backend: EEBackend
    data_end: str                                    # first day after the run's feature origin: no data read beyond it
    calendar_windows: pd.DataFrame                   # every admin's s1/s2 windows (rainfall paints all of them)
    refs: AssetRefs = field(default_factory=AssetRefs)
    cache: dict = field(default_factory=dict)

    def fetch(self, base: str, source: str, season_year: int, season: str, windows: pd.DataFrame) -> SourceOutcome:
        family = GS_BASE_FAMILY.get(base)
        if family is None or source not in GS_FAMILIES[family][2]:
            raise ClimateProcessingFailure(f"no seasonal EE provider for {base}/{source}")
        codes = sorted(windows["admin_code"].astype(str))
        key = (family, source, int(season_year), season, tuple(codes))
        if key not in self.cache:
            self.cache[key] = self._compute(family, source, int(season_year), season, windows, codes)
        r = self.cache[key]
        if isinstance(r, str):
            return SourceOutcome(source, "unavailable", detail=r)
        frame = r[base]
        return SourceOutcome(source, "published", frame[["admin_code", "value"]].reset_index(drop=True),
                             extra={"status_counts": frame["status"].value_counts().to_dict()})

    def bound(self, base):
        return lambda source, year, season, windows: self.fetch(base, source, year, season, windows)

    def _compute(self, family, source, year, season, windows, codes):
        cfg = GS_FAMILIES[family][2][source]
        start = pd.to_datetime(windows["gs_start_date"]).min().strftime("%Y-%m-%d")
        last_day = pd.to_datetime(windows["gs_end_date_exclusive"]).max() - pd.Timedelta(days=1)
        if last_day >= pd.Timestamp(self.data_end):
            raise ClimateProcessingFailure(f"{family} {year}-{season}: requested window ends after the run data end {self.data_end}")
        band = cfg.get("band") or cfg["proj_band"]
        try:
            times = self.backend.image_times(cfg["collection"], band, start, self.data_end)
        except Exception as exc:
            raise ClimateProcessingFailure(f"{family} {source} {year}-{season}: publication check failed: {exc}") from exc
        per_day = cfg.get("per_day", 1)
        need = pd.Timestamp(last_day, tz="UTC") + pd.Timedelta(hours=24 - 24 // per_day if per_day > 1 else 0)
        latest = pd.to_datetime(max(times), unit="ms", utc=True) if len(times) else None
        if latest is None or latest < need:
            return f"{cfg['collection']}: published through {latest}, season needs {need}"
        fam_key = {"gs_rain_anomz": "rain_anomz", "gs_rain_cdd": "rain_cdd", "gs_temperature": "temperature", "gs_soil": "soil"}[family]
        missing = self.backend.missing_assets(self.refs.required(fam_key, source))
        if missing:
            raise ClimateProcessingFailure(f"{family} {source}: unreadable private inputs (configure AssetRefs): {missing[:5]} ({len(missing)} total)")
        ee = self.backend.ee
        data_end = self.data_end
        try:
            if family in ("gs_rain_anomz", "gs_rain_cdd"):
                cal = self.calendar_windows
                yw = cal[cal["season_year"].astype(int) == year].dropna(subset=["gs_start_date", "gs_end_date_exclusive"])
                if yw.empty:
                    raise ClimateProcessingFailure(f"no calendar windows for season year {year}")
                lo, hi = window_bounds(yw)                           # full both-season calendar bounds (script)
                table, cols, roots = rain_seasonal_table(ee, family, source, year, (lo, min(hi, data_end)), self.refs, codes)
            elif family == "gs_temperature":
                table, cols = temperature_seasonal_table(ee, source, season, year, data_end, self.refs, codes)
            else:
                table, cols = soil_seasonal_table(ee, source, season, year, data_end, self.refs, codes)
            uri = self.backend.export_table(table, cols, f"ipcch_{family}_{source}_{year}_{season}")
            raw = self.backend.read_table(uri)
        except ClimateProcessingFailure:
            raise
        except Exception as exc:
            raise ClimateProcessingFailure(f"{family} {source} {year}-{season}: export failed: {type(exc).__name__}: {exc}") from exc
        lacking = [c for c in cols if c not in raw.columns]
        if lacking:
            raise ClimateProcessingFailure(f"{family} {source} {year}-{season}: export lacks {lacking[:5]}")
        if family in ("gs_rain_anomz", "gs_rain_cdd"):
            return finalize_rain(raw, roots, season)
        return finalize_temperature(raw) if family == "gs_temperature" else finalize_soil(raw)
