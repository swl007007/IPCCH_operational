"""Task 10-29: IPCCH GOSIF-GPP v3 append must match the delivered research GPP_mean units and missingness (fills
65534/65535 masked before the mean, x0.01, true zeros kept, all-fill -> NaN), with the shared/legacy FEWS NET raw
zonal statistics unchanged; ledger + fill-only-unpublished (R9/R49/R54)."""

import math

import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin

from cloud.batch import remote_sources as rs
from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import gpp, retained
from cloud.ipcch.stores import StoreError, StoreRoot, VersionedTable
from cloud.orchestrator.prepare import AcquiredRaster

# 4x4 cells of 1 degree, origin (0, 4); polygons are whole cells (cell centres inside)
GRID = (4, 4, (1.0, 0.0, 0.0, 0.0, -1.0, 4.0))
RASTER = np.array([[10, 20, 65535, 7],
                   [0, 0, 65534, 65535],
                   [65534, 65535, 5, 0],
                   [3, 65535, 9, 11]], dtype="uint16")


def cell_box(x0, y0, x1, y1):
    return {"type": "Polygon", "coordinates": [[(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]]}


# A: row0 cols0-2 -> 10, 20, 65535 ; B: row1 cols0-1 -> 0, 0 ; C: row1 col2-3 -> 65534, 65535 (all fill)
# D: row2 cols 0-3 -> 65534, 65535, 5, 0 ; E: outside the raster
GEOMS = {"1": cell_box(0, 3, 3, 4), "2": cell_box(0, 2, 2, 3), "3": cell_box(2, 2, 4, 3), "4": cell_box(0, 1, 4, 2),
         "5": cell_box(10, 10, 11, 11)}


def write_raster(path, data=RASTER, band_name=None, dtype="uint16"):
    with rasterio.open(path, "w", driver="GTiff", width=4, height=4, count=1, dtype=dtype, crs="EPSG:4326",
                       transform=from_origin(0, 4, 1, 1), nodata=None) as ds:
        ds.write(data.astype(dtype), 1)
        if band_name:
            ds.set_band_description(1, band_name)
    return str(path)


def research(x):
    """extract_gpp_v3.py:123-133 verbatim arithmetic for one polygon's member cells."""
    x = np.asarray(x)
    valid = ~((x == 65535) | (x == 65534))
    s_ = np.where(valid, x, 0).astype(np.float64).sum()
    nv = int(valid.sum())
    return s_ / max(nv, 1) * gpp.SCALE if nv > 0 else np.nan


def test_research_equivalent_mean_and_no_fill_contamination(tmp_path):
    out = gpp.zonal_gpp_mean(write_raster(tmp_path / "g.tif"), GEOMS, grid=GRID).set_index("admin_code")
    expect = {"1": research([10, 20, 65535]), "2": research([0, 0]), "3": research([65534, 65535]),
              "4": research([65534, 65535, 5, 0])}
    for k, v in expect.items():
        assert (math.isnan(v) and math.isnan(out.loc[k, "value"])) or out.loc[k, "value"] == v      # bit-equal
    assert out.loc["1", "value"] == pytest.approx(0.15) and out.loc["2", "value"] == 0.0              # true zeros kept
    assert math.isnan(out.loc["3", "value"]) and out.loc["3", "n_fill"] == 2                          # all fill -> NaN
    assert out.loc["4", "value"] == pytest.approx(0.025) and out.loc["4", "n_zero"] == 1
    assert math.isnan(out.loc["5", "value"]) and out.loc["5", "n_valid"] == 0                          # no member cell
    assert out["value"].max() < 1                                                                      # never raw scale


def test_shared_legacy_zonal_statistics_unchanged(tmp_path):
    """The FEWS NET / legacy contract keeps its raw unscaled statistics (fill codes count as data there)."""
    path = write_raster(tmp_path / "legacy.tif", band_name="GPP_Mean")
    legacy = rs.zonal_statistics(path, {k: GEOMS[k] for k in ("1", "2", "3")}, family="gosif_mean", month="2026-01")
    assert legacy["GPP_Mean__mean"].tolist() == [np.mean([10, 20, 65535]), 0.0, np.mean([65534, 65535])]
    assert rs.MODEL_COLUMN_MAPPING["fewsnet"]["gpp_mean"] == "GPP_Mean__mean"
    assert "No unit scaling is applied" in " ".join(rs.__doc__.split())


def test_grid_and_encoding_are_enforced(tmp_path):
    with pytest.raises(retained.GppProcessingFailure, match="not the GOSIF v3"):
        gpp.zonal_gpp_mean(write_raster(tmp_path / "g.tif"), GEOMS)                    # the 4x4 test grid != provider grid
    with pytest.raises(retained.GppProcessingFailure, match="not the GOSIF v3"):
        gpp.zonal_gpp_mean(write_raster(tmp_path / "f.tif", RASTER.astype("float32"), dtype="float32"), GEOMS, grid=GRID)


class FakeAcquirer:
    def __init__(self, tmp_path, statuses):
        self.tmp, self.statuses, self.downloads = tmp_path, statuses, []

    def _head(self, url):
        s = self.statuses[url.rsplit("GOSIF_GPP_", 1)[1][:8].replace(".M", "-")]
        if isinstance(s, Exception):
            raise s
        return s

    def _acquire_http(self, family, month, provider_id, prepare_id, workdir):
        assert family == "gosif_mean" and provider_id == rs.gosif_url(rs.SOURCE_CONTRACTS[family].export["url"], month)
        self.downloads.append(month)
        return AcquiredRaster(write_raster(self.tmp / f"{month}.tif"), {"uri": f"gs://r/{month}", "generation": "1", "sha256": "f" * 64})


def seeded(tmp_path):
    store, root = LocalObjectStore(tmp_path / "store"), StoreRoot("real", "gs://b/ipcch-v2/real")
    hist = VersionedTable(store, root, gpp.HISTORY_TABLE)
    hist.commit(pd.DataFrame([{"admin_code": a, "month": "2025-12", "value": 80.5, "method_id": "delivered"} for a in "1234"]),
                {"action": "initialise"}, expected_generation="0")
    return store, root, hist


def test_update_ledger_published_unpublished_and_fill_only_unpublished(tmp_path):
    store, root, hist = seeded(tmp_path)
    roster = ["1", "2", "3", "4"]
    geoms = {k: GEOMS[k] for k in roster}
    acq = FakeAcquirer(tmp_path, {"2026-01": 200, "2026-02": 200, "2026-03": 404, "2026-04": 404})
    rep = gpp.update_gpp(store, root, origin="2026-04", roster=roster, geometries=geoms, acquirer=acq, run_id="r1",
                         workdir=tmp_path, checked_at="2026-06-30", grid=GRID)
    assert rep["saved"] == ["2026-01", "2026-02"] and rep["unpublished"] == ["2026-03", "2026-04"]
    assert rep["pixel_missing"]["2026-01"] == 1 and rep["coverage_end"] == "2026-02"
    frame, _ = retained.read_series(hist)
    jan = frame[frame["month"] == "2026-01"].set_index("admin_code")
    assert jan.loc["1", "value"] == research([10, 20, 65535]) and math.isnan(jan.loc["3", "value"])   # NaN = pixel missing
    assert set(jan["method_id"]) == {gpp.METHOD_ID}
    assert "2026-03" not in set(frame["month"])                                                    # unpublished: absent
    led = retained.latest_gpp_status(VersionedTable(store, root, gpp.LEDGER_TABLE))
    assert led == {"2026-01": "published", "2026-02": "published", "2026-03": "unpublished", "2026-04": "unpublished"}
    # next run: 2026-03 published late -> filled; saved months never re-downloaded or rewritten
    acq2 = FakeAcquirer(tmp_path, {"2026-03": 200, "2026-04": 404, "2026-05": 404})
    rep2 = gpp.update_gpp(store, root, origin="2026-05", roster=roster, geometries=geoms, acquirer=acq2, run_id="r2",
                          workdir=tmp_path, checked_at="2026-07-31", grid=GRID)
    assert acq2.downloads == ["2026-03"] and rep2["saved"] == ["2026-03"] and rep2["unpublished"] == ["2026-04", "2026-05"]
    assert retained.read_series(hist)[0].query("month == '2026-01'")["value"].tolist()[0] == research([10, 20, 65535])


@pytest.mark.parametrize("status", [503, TimeoutError("read timed out")])
def test_non_definitive_outcomes_block_after_saved_months(tmp_path, status):
    store, root, hist = seeded(tmp_path)
    roster = ["1", "2", "3", "4"]
    acq = FakeAcquirer(tmp_path, {"2026-01": 200, "2026-02": status})
    with pytest.raises(retained.GppProcessingFailure) as info:
        gpp.update_gpp(store, root, origin="2026-02", roster=roster, geometries={k: GEOMS[k] for k in roster},
                       acquirer=acq, run_id="r1", workdir=tmp_path, checked_at="2026-04-30", grid=GRID)
    assert info.value.gpp_report["saved"] == ["2026-01"]                                           # R41-style progress
    assert "2026-02" not in retained.latest_gpp_status(VersionedTable(store, root, gpp.LEDGER_TABLE))  # not unpublished


def test_geometries_must_be_the_roster(tmp_path):
    store, root, _ = seeded(tmp_path)
    with pytest.raises(StoreError, match="exactly the roster"):
        gpp.update_gpp(store, root, origin="2026-01", roster=["1", "2"], geometries={"2": GEOMS["2"], "1": GEOMS["1"]},
                       acquirer=None, run_id="r", workdir=tmp_path, checked_at="2026-03-31", grid=GRID)
