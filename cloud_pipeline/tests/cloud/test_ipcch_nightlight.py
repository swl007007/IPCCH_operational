"""Task 10-29: IPCCH nightlight_mean append through the existing VIIRS contract (avg_rad__sum on the roster geometry)."""

import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin

from cloud.batch import remote_sources as rs
from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import nightlight as nl
from cloud.ipcch import retained
from cloud.ipcch.stores import StoreError, StoreRoot, VersionedTable
from cloud.orchestrator.prepare import AcquiredRaster
from tests.cloud.test_ipcch_gpp import GEOMS

ROSTER = ["1", "2", "3", "4"]
DATA = np.array([[1.5, 2.0, 0.5, 9.0], [0.0, 0.25, -9999, -9999], [1.0, 1.0, 1.0, 1.0], [3.0, 3.0, 3.0, 3.0]], "float32")


class FakeAcquirer:
    def __init__(self, tmp, published, fail=None):
        self.tmp, self.published, self.fail = tmp, published, fail
        self.started, self.acquired, self.cancelled = [], [], 0

    def published_months(self, family, *, start_month, end_month):
        assert family == "viirs"
        return {m: f"NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG/{m.replace('-', '')}01" for m in self.published
                if start_month <= m <= end_month}

    def start_exports(self, family, months, *, prepare_id):
        self.started.append(sorted(months))

    def acquire(self, family, month, *, provider_id, prepare_id, workdir):
        if self.fail == month:
            raise rs.SourceRetrievalError("Earth Engine export failed")
        self.acquired.append(month)
        path = str(self.tmp / f"v{month}.tif")
        with rasterio.open(path, "w", driver="GTiff", width=4, height=4, count=1, dtype="float32", crs="EPSG:4326",
                           transform=from_origin(0, 4, 1, 1), nodata=-9999) as ds:
            ds.write(DATA, 1)
        return AcquiredRaster(path, {"uri": f"gs://x/{month}"})

    def cancel_started(self):
        self.cancelled += 1
        return ["T"]


def seeded(tmp_path):
    store, root = LocalObjectStore(tmp_path / "s"), StoreRoot("real", "gs://b/ipcch-v2/real")
    t = VersionedTable(store, root, nl.HISTORY_TABLE)
    t.commit(pd.DataFrame([{"admin_code": a, "month": "2026-06", "value": 1.0, "method_id": "delivered"} for a in ROSTER]),
             {"action": "initialise"}, expected_generation="0")
    return store, root, t


def test_appends_viirs_sum_on_roster_and_records_gaps(tmp_path):
    store, root, t = seeded(tmp_path)
    acq = FakeAcquirer(tmp_path, published=["2026-07"])
    rep = nl.update_nightlight(store, root, origin="2026-08", roster=ROSTER, geometries={k: GEOMS[k] for k in ROSTER},
                               acquirer=acq, run_id="r1", workdir=tmp_path)
    assert rep["saved"] == ["2026-07"] and rep["gaps"] == ["2026-08"] and acq.started == [["2026-07"]]
    jul = retained.read_series(t)[0].query("month == '2026-07'").set_index("admin_code")["value"]
    assert jul["1"] == 4.0 and jul["2"] == 0.25 and jul["4"] == 4.0          # zonal SUM of valid cells (nodata ignored)
    assert np.isnan(jul["3"]) and rep["pixel_missing"]["2026-07"] == 1       # all-nodata zone -> NaN
    assert rep["method_id"].endswith("avg_rad__sum|cell-centre") and rep["coverage_end"] == "2026-07"
    rep2 = nl.update_nightlight(store, root, origin="2026-08", roster=ROSTER, geometries={k: GEOMS[k] for k in ROSTER},
                                acquirer=FakeAcquirer(tmp_path, published=["2026-08"]), run_id="r2", workdir=tmp_path)
    assert rep2["candidates"] == ["2026-08"] and rep2["saved"] == ["2026-08"]          # saved months never refetched


def test_retrieval_failure_blocks_after_saved_months_and_cancels(tmp_path):
    store, root, t = seeded(tmp_path)
    acq = FakeAcquirer(tmp_path, published=["2026-07", "2026-08"], fail="2026-08")
    with pytest.raises(nl.NightlightProcessingFailure) as info:
        nl.update_nightlight(store, root, origin="2026-08", roster=ROSTER, geometries={k: GEOMS[k] for k in ROSTER},
                             acquirer=acq, run_id="r1", workdir=tmp_path)
    assert info.value.nightlight_report["saved"] == ["2026-07"] and acq.cancelled == 1
    assert "2026-08" not in set(retained.read_series(t)[0]["month"])


def test_geometries_must_be_the_roster(tmp_path):
    store, root, _ = seeded(tmp_path)
    with pytest.raises(StoreError, match="exactly the roster"):
        nl.update_nightlight(store, root, origin="2026-07", roster=ROSTER, geometries={"1": GEOMS["1"]},
                             acquirer=None, run_id="r", workdir=tmp_path)
