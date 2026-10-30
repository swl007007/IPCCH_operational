"""Task 10-29: seasonal EE providers (rainfall paint calendar, per-feature temperature and soil moisture) - offline graph
construction with the real client, local post-processing, provider outcomes and seasonal saves via a mocked boundary."""

import json

import numpy as np
import pandas as pd
import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import climate as cl
from cloud.ipcch import climate_ee_seasonal as cs
from cloud.ipcch.climate_ee import AssetRefs
from cloud.ipcch.stores import StoreRoot, VersionedTable
from tests.cloud.ee_offline import offline_ee

CODES = ["1", "2"]


def ser(obj):
    ee = offline_ee()
    return json.dumps(json.loads(ee.serializer.toJSON(obj)))


@pytest.mark.parametrize("family", ["gs_rain_anomz", "gs_rain_cdd"])
@pytest.mark.parametrize("source", ["chirps", "persiann", "era5land"])
def test_rainfall_graph(family, source):
    ee = offline_ee()
    table, cols, roots = cs.rain_seasonal_table(ee, family, source, 2026, ("2025-10-01", "2026-09-01"), AssetRefs(), CODES)
    g = ser(table)
    assert "Image.paint" in g and "Image.reduceRegions" in g and "s1_calendar_valid_num" in g and "Filter.listContains" in g
    assert f'"tileScale": {{"constantValue": {8 if "anomz" in family else 16}}}' in g
    if family == "gs_rain_anomz":
        assert roots == [f"prcp_anom_gs_{source}", f"prcp_z_gs_{source}"] and "daily_normal_d" in g and "monthly_total_sd_mm" in g
    else:
        assert roots == [f"rainy_days_gs_{source}", f"cdd_gs_{source}"] and "Image.arrayAccum" in g and "Image.arrayReduce" in g


@pytest.mark.parametrize("source", ["cpc", "era5land"])
def test_temperature_and_soil_graphs(source):
    ee = offline_ee()
    table, cols = cs.temperature_seasonal_table(ee, source, "s1", 2026, "2026-09-01", AssetRefs(), CODES)
    g = ser(table)
    assert "Image.reduceRegion" in g and "Date.advance" in g and "tmax_p95_d" in g and "Collection.map" in g
    soil_src = "gldas21" if source == "cpc" else "era5land"
    table, cols = cs.soil_seasonal_table(ee, soil_src, "s2", 2026, "2026-09-01", AssetRefs(), CODES)
    g = ser(table)
    assert "month_start_millis" in g and "sm_monthly_sd" in g and "Geometry.area" in g and "Reducer.combine" in g


def test_finalize_rules():
    raw = pd.DataFrame({"admin_code": ["1", "2", "3"], "s1_calendar_valid_num": [1, 1, 0]})
    for root in ("prcp_anom_gs_chirps", "prcp_z_gs_chirps"):
        raw[f"s1_{root}_area_sum"] = [10.0, 0.0, 5.0]
        raw[f"s1_{root}_valid_area"] = [2.0, 0.0, 1.0]
        raw[f"s1_{root}_coverage_fraction_area_sum"] = [4.0, 2.0, 1.0]
        raw[f"s1_{root}_coverage_fraction_valid_area"] = [4.0, 4.0, 1.0]
    out = cs.finalize_rain(raw, ["prcp_anom_gs_chirps", "prcp_z_gs_chirps"], "s1")["prcp_z"]
    assert out["value"].tolist()[0] == 5.0 and np.isnan(out["value"].tolist()[1]) and np.isnan(out["value"].tolist()[2])
    assert out["status"].tolist() == ["COMPLETE", "MISSING_DATA", "INVALID_CALENDAR"]
    t = pd.DataFrame({"admin_code": ["1"], "calendar_valid": [1], "duration": [100],
                      **{f"{m}_{k}": [v] for m in ("tmean_anom", "tmax_anom", "hot_days_p95", "gdd", "edd")
                         for k, v in (("num", 6.0), ("area", 2.0), ("obs", 120.0))}})
    tt = cs.finalize_temperature(t)
    assert tt["gdd"]["value"].tolist() == [3.0] and tt["gdd"]["status"].tolist() == ["PARTIAL_DATA"]   # 60 of 100 days
    s = pd.DataFrame({"admin_code": ["1"], "calendar_valid": [1], "duration": [90], "geometry_area": [1e8], "z_area": [14.0],
                      "area": [2.0], "days_area": [180.0], "incomplete_area": [0.0], "excess_area": [0.0]})
    ss = cs.finalize_soil(s)["sm_z"]
    assert ss["value"].tolist() == [7.0] and ss["status"].tolist() == ["COMPLETE"] and ss["qa_abs_gt6_warning"].tolist() == [1]


class Backend:
    def __init__(self, cover_to="2026-09-01", missing=()):
        self.ee, self.cover_to, self.missing, self.exports = offline_ee(), pd.Timestamp(cover_to, tz="UTC"), missing, []

    def missing_assets(self, ids):
        return [i for i in ids if any(m in i for m in self.missing)]

    def image_times(self, collection, band, start, end):
        freq = "3h" if "GLDAS" in collection else "D"               # GLDAS publishes 8 samples a day
        days = pd.date_range(pd.Timestamp(start, tz="UTC"), min(self.cover_to, pd.Timestamp(end, tz="UTC")), freq=freq, inclusive="left")
        return [int(d.value // 10**6) for d in days]

    def export_table(self, collection, selectors, description):
        self.exports.append(description)
        self.cols = selectors
        return f"gs://x/{description}.csv"

    def read_table(self, uri):
        frame = pd.DataFrame({c: [1.0, 1.0] for c in self.cols})
        frame["admin_code"] = CODES
        for c in self.cols:
            if c.endswith("calendar_valid_num") or c == "calendar_valid":
                frame[c] = 1
        return frame


def test_provider_and_seasonal_saves(tmp_path):
    windows = pd.DataFrame({"admin_code": CODES, "season_year": [2026, 2026], "season": ["s1", "s1"],
                            "gs_start_date": ["2026-03-01", "2026-03-10"], "gs_end_date_exclusive": ["2026-07-01", "2026-08-01"]})
    late = cs.SeasonalEEProvider(Backend(cover_to="2026-07-20"))
    assert late.fetch("gdd", "cpc", 2026, "s1", windows).status == "unavailable"
    with pytest.raises(cl.ClimateProcessingFailure, match="unreadable private inputs"):
        cs.SeasonalEEProvider(Backend(missing=["STAGE2D"])).fetch("sm_z", "gldas21", 2026, "s1", windows)
    provider = cs.SeasonalEEProvider(Backend())
    table = VersionedTable(LocalObjectStore(tmp_path), StoreRoot("real", "gs://b/ipcch-v2/real"), cl.table_name("prcp_z", cl.SEASONAL))
    rep = cl.update_seasonal(table, "prcp_z", origin="2026-07", roster=CODES, windows=windows, fetch=provider.bound("prcp_z"))
    assert rep["saved"] == ["2026-s1"]
    frame, _ = cl.read_seasonal(table)
    assert frame["admin_code"].tolist() == ["1", "2"] and frame["n_sources"].tolist() == [3, 3]
    assert len(provider.backend.exports) == 3                       # one export per source; prcp_anom would reuse them
