"""Task 10-29: EE raster providers ported from the shared monthly scripts - offline graph construction with the real
client, local post-processing of exported sums, provider outcomes and retained saves through a mocked EE boundary."""

import json

import numpy as np
import pandas as pd
import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import climate as cl
from cloud.ipcch import climate_ee as ce
from cloud.ipcch.stores import StoreRoot, VersionedTable
from tests.cloud.ee_offline import offline_ee

ROSTER = ["1", "2", "3"]


def graph(family, source, month="2026-08"):
    ee = offline_ee()
    return json.dumps(json.loads(ee.serializer.toJSON(ce.reduced_table(ee, family, source, month, ce.AssetRefs()))))


@pytest.mark.parametrize("family,source", [(f, s) for f, (_, _, srcs) in ce.FAMILIES.items() for s in srcs])
def test_graphs_build_offline_with_the_ported_operations(family, source):
    g = graph(family, source)
    cfg = ce.FAMILIES[family][2][source]
    assert cfg["collection"] in g and "Image.reduceRegions" in g and "Reducer.sum" in g and "Image.pixelArea" in g
    assert '"tileScale": {"constantValue": 8}' in g and "maxPixelsPerRegion" in g
    assert "IPCCH_ADMIN_STATIC_CALENDAR_CROPFRAC_V1_G24" in g and '"constantValue": "2026-08-01"' in g
    if family != "rain_cdd":
        assert all(i in g for i in ce.AssetRefs().baselines(family, cfg["label"]))
    for band in ce.SUM_BANDS[family]:
        assert f'"{band}"' in g


def test_family_specific_operations():
    era = graph("rain_anomz", "era5land")
    assert '"constantValue": 1000' in era and "daily_normal_d" in era and "monthly_total_sd_mm" in era
    cdd = graph("rain_cdd", "chirps")
    assert "ImageCollection.iterate" in cdd or "Collection.iterate" in cdd
    assert "Image.gte" in cdd and "Image.lt" in cdd and "Image.where" in cdd
    t = graph("temperature", "era5land")
    assert '"constantValue": 273.15' in t and "tmax_p95_d" in t and "tmean_normal_d" in t
    assert '"constantValue": 30' in t and '"constantValue": 10' in t
    s = graph("soil", "gldas21")
    assert "Reducer.combine" in s and "sm_monthly_sd" in s and "STAGE2D_SOIL_BASELINE_2001_2020_GLDAS21_M01" in s


def test_finalize_matches_the_scripts_arithmetic():
    raw = pd.DataFrame({"admin_code": ["1", "2", "3"], "z_num": [12.0, 0.0, 70.0], "z_area": [4.0, 0.0, 10.0],
                        "z_obs_num": [124.0, 0.0, 310.0], "anom_num": [8.0, 0.0, 5.0], "anom_area": [4.0, 0.0, 10.0],
                        "anom_obs_num": [100.0, 0.0, 310.0]})
    out = ce.finalize("rain_anomz", raw, "2026-08", "chirps")
    z = out["prcp_z"].set_index("admin_code")
    assert z.loc["1", "value"] == 3.0 and np.isnan(z.loc["2", "value"]) and z.loc["3", "value"] == 7.0
    assert z["status"].tolist() == ["COMPLETE", "MISSING_DATA", "COMPLETE"]       # 31 observed days of 31
    assert z["qa_abs_gt6_warning"].tolist() == [0, 0, 1]                           # warning only, value kept (R40)
    a = out["prcp_anom"].set_index("admin_code")
    assert a.loc["1", "status"] == "PARTIAL_DATA" and a.loc["1", "value"] == 2.0
    soil = ce.finalize("soil", pd.DataFrame({"admin_code": ["1"], "sm_z_num": [6.0], "sm_z_area": [2.0],
                                             "sample_count_num": [2.0 * 240], "monthly_sm_mean_num": [0.5]}),
                       "2026-08", "gldas21")["sm_z"]
    assert soil["value"].tolist() == [3.0] and soil["status"].tolist() == ["PARTIAL_DATA"]   # 240 of 31*8 samples
    with pytest.raises(cl.ClimateProcessingFailure, match="lacks columns"):
        ce.finalize("temperature", raw, "2026-08", "cpc")


class FakeBackend:
    def __init__(self, days=31, per_day=1, missing=(), fail_export=False, rows=None):
        self.ee = offline_ee()
        self.days, self.per_day, self.missing, self.fail_export = days, per_day, list(missing), fail_export
        self.rows = rows
        self.exports = []

    def missing_assets(self, ids):
        return [i for i in ids if any(m in i for m in self.missing)]

    def image_times(self, collection, band, start, end):
        t0 = pd.Timestamp(start, tz="UTC")
        return [int((t0 + pd.Timedelta(hours=3 * k if self.per_day > 1 else 24 * k)).value // 10**6)
                for k in range(self.days * self.per_day)]

    def export_table(self, collection, selectors, description):
        if self.fail_export:
            raise RuntimeError("task FAILED: computation timed out")
        self.exports.append((description, selectors, len(self.ee.serializer.toJSON(collection))))
        return f"gs://exports/{description}.csv"

    def read_table(self, uri):
        family = "rain_anomz" if "anomz" in uri else "rain_cdd" if "cdd" in uri else "temperature" if "temperature" in uri else "soil"
        frame = pd.DataFrame({"admin_code": ROSTER + ["6227"]})
        for b in ce.SUM_BANDS[family]:
            frame[b] = 1.0 if b.endswith(("area", "obs_num")) else 2.0
        return frame


def test_provider_outcomes_and_failures():
    p = ce.MonthlyEEProvider(FakeBackend(days=0))
    assert p.fetch("prcp_z", "chirps", "2026-08").status == "unavailable"
    p = ce.MonthlyEEProvider(FakeBackend(days=20))
    o = p.fetch("gdd", "cpc", "2026-08")
    assert o.status == "unavailable" and "partial publication 20/31" in o.detail       # never frozen partially (R8)
    with pytest.raises(cl.ClimateProcessingFailure, match="unreadable private inputs"):
        ce.MonthlyEEProvider(FakeBackend(missing=["STAGE2B"])).fetch("gdd", "cpc", "2026-08")
    with pytest.raises(cl.ClimateProcessingFailure, match="export failed"):
        ce.MonthlyEEProvider(FakeBackend(fail_export=True)).fetch("sm_z", "era5land", "2026-08")
    hourly = FakeBackend(days=31, per_day=8)                   # 248 consecutive HOURLY stamps (< 11 days): not 3-hourly
    hourly.image_times = lambda c, b, s, e: [int((pd.Timestamp(s, tz="UTC") + pd.Timedelta(hours=k)).value // 10**6) for k in range(248)]
    assert ce.MonthlyEEProvider(hourly).fetch("sm_z", "gldas21", "2026-08").status == "unavailable"
    assert ce.slots_present([], "2026-08-01", "2026-09-01", 8) == (0, 248)
    gl = ce.MonthlyEEProvider(FakeBackend(days=31, per_day=8))
    assert gl.fetch("sm_z", "gldas21", "2026-08").status == "published"
    with pytest.raises(cl.ClimateProcessingFailure, match="no EE provider"):
        gl.fetch("spi03", "chirps", "2026-08")


def test_provider_drives_retained_saves(tmp_path):
    backend = FakeBackend()
    provider = ce.MonthlyEEProvider(backend)
    table = VersionedTable(LocalObjectStore(tmp_path), StoreRoot("real", "gs://b/ipcch-v2/real"), cl.table_name("prcp_anom", cl.MONTHLY))
    seed = pd.DataFrame([{"admin_code": a, "month": "2026-07", "value": 0.0, "n_sources": 3, "ens_sd": 0.0, "method_id": "accepted"}
                         for a in ROSTER])
    table.commit(seed, {"action": "initialise"}, expected_generation="0")
    rep = cl.update_monthly(table, "prcp_anom", origin="2026-08", roster=ROSTER, fetch=provider.bound("prcp_anom"))
    assert rep["saved"] == ["2026-08"] and rep["months"]["2026-08"]["dropped_out_of_roster"]["chirps"] == 1
    frame, _ = cl.read_monthly(table)
    aug = frame[frame["month"] == "2026-08"]
    assert aug["value"].tolist() == [2.0, 2.0, 2.0] and aug["n_sources"].tolist() == [3, 3, 3]
    # the sibling base reuses the same three exports (one per source)
    provider.fetch("prcp_z", "persiann", "2026-08")
    assert len(backend.exports) == 3
