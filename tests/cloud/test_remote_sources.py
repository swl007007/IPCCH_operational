import math
from datetime import datetime, timezone

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin  # noqa: E402

from cloud.batch import remote_sources as rs  # noqa: E402


NODATA = -9999.0


def _square(x0, y0, size):
    return {"type": "Polygon", "coordinates": [[(x0, y0), (x0 + size, y0), (x0 + size, y0 + size),
                                                (x0, y0 + size), (x0, y0)]]}


def _collection(**polygons):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"admin_code": key}, "geometry": geometry}
        for key, geometry in polygons.items()
    ]}


def _write_raster(path, bands, *, descriptions=None, crs="EPSG:4326", origin=(0.0, 4.0)):
    array = np.asarray(bands, dtype="float32")
    if array.ndim == 2:
        array = array[None]
    profile = {"driver": "GTiff", "width": array.shape[2], "height": array.shape[1], "count": array.shape[0],
               "dtype": "float32", "transform": from_origin(origin[0], origin[1], 1, 1), "nodata": NODATA}
    if crs:
        profile["crs"] = crs
    with rasterio.open(path, "w", **profile) as dataset:
        dataset.write(array)
        for index, description in enumerate(descriptions or [], start=1):
            dataset.set_band_description(index, description)
    return str(path)


GRID = np.arange(16, dtype="float32").reshape(4, 4)  # rows top->bottom: 0..3, 4..7, 8..11, 12..15


def _geometries():
    # "0": top-left 2x2 cells {0,1,4,5} with cell 0 nodata; "00": bottom-right 2x2 {10,11,14,15};
    # "7": outside the raster.
    collection = _collection(**{"0": _square(0, 2, 2), "00": _square(2, 0, 2), "7": _square(50, 50, 1)})
    return rs.native_geometries(collection, roster=["0", "00", "7"])


def test_evi_mean_and_population_std_ignore_nodata_and_keep_string_keys(tmp_path):
    grid = GRID.copy()
    grid[0, 0] = NODATA
    path = _write_raster(tmp_path / "evi.tif", grid)

    stats = rs.zonal_statistics(path, _geometries(), family="evi", month="2026-09").set_index("admin_code")

    assert list(stats.index) == ["0", "00", "7"]
    assert stats.loc["0", "EVI__mean"] == pytest.approx(np.mean([1, 4, 5]))
    assert stats.loc["0", "EVI__std"] == pytest.approx(np.std([1, 4, 5], ddof=0))
    assert stats.loc["00", "EVI__mean"] == pytest.approx(np.mean([10, 11, 14, 15]))
    assert math.isnan(stats.loc["7", "EVI__mean"]) and math.isnan(stats.loc["7", "EVI__std"])
    assert (stats["month"] == "2026-09").all()


def test_cell_centre_rule_excludes_partially_covered_cells(tmp_path):
    path = _write_raster(tmp_path / "evi.tif", GRID)
    # Covers cell (row 0, col 0) centre only; touches its neighbours' edges.
    geometries = rs.native_geometries(_collection(a=_square(0.2, 3.2, 0.6)), roster=["a"])

    stats = rs.zonal_statistics(path, geometries, family="evi", month="2026-09")

    assert stats.loc[0, "EVI__mean"] == 0.0


def test_viirs_emits_sum_std_and_mean(tmp_path):
    path = _write_raster(tmp_path / "viirs.tif", GRID)

    stats = rs.zonal_statistics(path, _geometries(), family="viirs", month="2026-09").set_index("admin_code")

    values = [10, 11, 14, 15]
    assert stats.loc["00", "avg_rad__sum"] == pytest.approx(sum(values))
    assert stats.loc["00", "avg_rad__mean"] == pytest.approx(np.mean(values))
    assert stats.loc["00", "avg_rad__std"] == pytest.approx(np.std(values))
    assert rs.MODEL_COLUMN_MAPPING["fewsnet"]["nightlight"] == "avg_rad__mean"
    assert rs.MODEL_COLUMN_MAPPING["ipcch"]["nightlight_mean"] == "avg_rad__sum"
    assert rs.MODEL_COLUMN_MAPPING["ipcch"]["GPP_std"] == "GPP_SD__mean"


def test_fldas_bands_are_identified_by_name_not_position(tmp_path):
    names = list(reversed(rs.FLDAS_BANDS))  # stored in reverse order
    bands = [GRID + 100 * index for index in range(len(names))]
    path = _write_raster(tmp_path / "fldas.tif", bands, descriptions=names)

    stats = rs.zonal_statistics(path, _geometries(), family="fldas", month="2026-09").set_index("admin_code")

    position = names.index("Rainf_f_tavg")
    assert stats.loc["00", "Rainf_f_tavg__mean"] == pytest.approx(np.mean([10, 11, 14, 15]) + 100 * position)
    assert {f"{band}__std" for band in rs.FLDAS_BANDS} <= set(stats.columns)


def test_multiband_without_names_or_wrong_names_is_rejected(tmp_path):
    bands = [GRID] * len(rs.FLDAS_BANDS)
    unnamed = _write_raster(tmp_path / "unnamed.tif", bands)
    wrong = _write_raster(tmp_path / "wrong.tif", bands, descriptions=[f"b{i}" for i in range(len(bands))])

    with pytest.raises(rs.ExtractionError, match="band identity unavailable"):
        rs.zonal_statistics(unnamed, _geometries(), family="fldas", month="2026-09")
    with pytest.raises(rs.ExtractionError, match="do not match the contract"):
        rs.zonal_statistics(wrong, _geometries(), family="fldas", month="2026-09")


def test_stamp_band_names_binds_explicit_selection_order(tmp_path):
    bands = [GRID + index for index in range(len(rs.FLDAS_BANDS))]
    path = _write_raster(tmp_path / "export.tif", bands)

    assert rs.stamp_band_names(path, rs.FLDAS_BANDS) == "explicit_export_selection_order"
    assert rs.stamp_band_names(path, rs.FLDAS_BANDS) == "raster_band_descriptions"
    with rasterio.open(path) as dataset:
        assert dataset.descriptions == rs.FLDAS_BANDS
    with pytest.raises(rs.ExtractionError, match="differ from the export selection"):
        rs.stamp_band_names(path, tuple(reversed(rs.FLDAS_BANDS)))
    with pytest.raises(rs.ExtractionError, match="export selected"):
        rs.stamp_band_names(path, rs.FLDAS_BANDS[:3])


def test_raster_without_crs_is_rejected(tmp_path):
    path = _write_raster(tmp_path / "nocrs.tif", GRID, crs=None)

    with pytest.raises(rs.ExtractionError, match="no CRS"):
        rs.zonal_statistics(path, _geometries(), family="evi", month="2026-09")


def test_mosaic_preserves_values_and_band_names(tmp_path):
    names = list(rs.FLDAS_BANDS)
    full = [GRID + index for index in range(len(names))]
    whole = _write_raster(tmp_path / "whole.tif", full, descriptions=names)
    left = _write_raster(tmp_path / "left.tif", [band[:, :2] for band in full], descriptions=names)
    right = _write_raster(tmp_path / "right.tif", [band[:, 2:] for band in full], descriptions=names,
                          origin=(2.0, 4.0))

    mosaic = rs.mosaic_shards([left, right], str(tmp_path / "mosaic.tif"))

    with rasterio.open(mosaic) as dataset:
        assert dataset.descriptions == rs.FLDAS_BANDS
    a = rs.zonal_statistics(whole, _geometries(), family="fldas", month="2026-09")
    b = rs.zonal_statistics(mosaic, _geometries(), family="fldas", month="2026-09")
    np.testing.assert_array_equal(a.drop(columns=["admin_code", "month"]).to_numpy(),
                                  b.drop(columns=["admin_code", "month"]).to_numpy())


@pytest.mark.parametrize(
    ("collection", "roster", "message"),
    [
        (_collection(**{"0": _square(0, 0, 1)}) | {"features": [
            {"type": "Feature", "properties": {"admin_code": 0}, "geometry": _square(0, 0, 1)}]}, ["0"], "non-empty string"),
        ({"features": [{"properties": {"admin_code": "1"}, "geometry": _square(0, 0, 1)}] * 2}, ["1"], "duplicate"),
        (_collection(**{"1": _square(0, 0, 1)}), ["1", "2"], "must equal the roster"),
        ({"features": [{"properties": {"fid": 0}, "geometry": _square(0, 0, 1)}]}, ["0"], "non-empty string"),
    ],
)
def test_native_geometries_require_explicit_string_admin_code(collection, roster, message):
    with pytest.raises(rs.ExtractionError, match=message):
        rs.native_geometries(collection, roster=roster)


def test_latest_completed_month_excludes_unfinished_and_future_months():
    published = ["2026-07", "2026-08", "2026-09", "2026-10"]
    early_october = datetime(2026, 10, 5, tzinfo=timezone.utc)

    assert rs.latest_completed_month(published, origin_month="2026-10", cutoff_utc=early_october) == "2026-09"
    assert rs.latest_completed_month(published, origin_month="2026-10",
                                     cutoff_utc=datetime(2026, 11, 2, tzinfo=timezone.utc)) == "2026-10"
    assert rs.latest_completed_month(published, origin_month="2026-08", cutoff_utc=early_october) == "2026-08"
    assert rs.latest_completed_month([], origin_month="2026-10", cutoff_utc=early_october) is None
    with pytest.raises(ValueError, match="timezone-aware"):
        rs.latest_completed_month(published, origin_month="2026-10", cutoff_utc=datetime(2026, 10, 5))


def _ms(year, month):
    return int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp() * 1000)


def test_gee_discovery_binds_exact_image_ids_and_fails_loudly():
    collection = "MODIS/061/MOD13A3"
    listing = [(_ms(2026, 8), f"{collection}/2026_08_01"), (_ms(2026, 9), f"{collection}/2026_09_01")]

    found = rs.gee_published_months(lambda *args: listing, collection, start_month="2026-08", end_month="2026-10")

    assert found == {"2026-08": f"{collection}/2026_08_01", "2026-09": f"{collection}/2026_09_01"}

    def broken(*args):
        raise PermissionError("403 Earth Engine not authorized")

    failures = [
        (broken, "availability query failed"),
        (lambda *a: listing + [(_ms(2026, 9), f"{collection}/2026_09_15")], "multiple images"),
        (lambda *a: [("2026-09", f"{collection}/x")], "malformed"),
        (lambda *a: [(_ms(2026, 9), "OTHER/collection/x")], "malformed"),
    ]
    for lister, message in failures:
        with pytest.raises(rs.SourceRetrievalError, match=message):
            rs.gee_published_months(lister, collection, start_month="2026-08", end_month="2026-10")


def test_http_discovery_distinguishes_lag_from_failure():
    template = rs.SOURCE_CONTRACTS["gosif_mean"].export["url"]
    statuses = {"2026-07": 200, "2026-08": 200, "2026-09": 404}

    def head(url):
        name = url.rsplit("/", 1)[1]  # GOSIF_GPP_2026.M08_Mean.tif.gz
        return statuses[f"{name[10:14]}-{name[16:18]}"]

    found = rs.http_published_months(head, template, ["2026-07", "2026-08", "2026-09"])

    assert list(found) == ["2026-07", "2026-08"]
    assert found["2026-08"].endswith("/Mean/GOSIF_GPP_2026.M08_Mean.tif.gz")
    with pytest.raises(rs.SourceRetrievalError, match="HTTP 503"):
        rs.http_published_months(lambda url: 503, template, ["2026-09"])

    def timeout(url):
        raise TimeoutError("read timed out")

    with pytest.raises(rs.SourceRetrievalError, match="request failed"):
        rs.http_published_months(timeout, template, ["2026-09"])


def test_gee_export_spec_follows_current_scripts():
    fldas = rs.gee_export_spec("fldas", "2026-09")
    viirs = rs.gee_export_spec("viirs", "2026-12")
    evi = rs.gee_export_spec("evi", "2026-09")

    assert fldas["bands"] == list(rs.FLDAS_BANDS) and len(fldas["bands"]) == 28
    assert fldas["crs_transform"] == (0.1, 0, -180, 0, -0.1, 90)
    assert (viirs["start"], viirs["end"], viirs["resample"]) == ("2026-12-01", "2027-01-01", "bilinear")
    assert viirs["crs_transform"][0] == pytest.approx(0.0041666667 * 8)
    assert (evi["bands"], evi["scale"], evi["region"]) == (["EVI"], 1000, (-180, -60, 180, 80))
    with pytest.raises(ValueError, match="not an Earth Engine source"):
        rs.gee_export_spec("gosif_mean", "2026-09")


def _shard(path, x0, values, *, mask=None, nodata=None):
    profile = {"driver": "GTiff", "width": len(values), "height": 1, "count": 1, "dtype": "float32",
               "crs": "EPSG:4326", "transform": from_origin(x0, 1, 1, 1)}
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as dataset:
        dataset.write(np.array([[values]], dtype="float32"))
        if mask is not None:
            dataset.write_mask(np.array([mask], dtype="uint8"))
    return str(path)


@pytest.mark.parametrize("encoding", ["internal_mask", "nodata_value"])
def test_mosaic_preserves_invalid_cells_from_shard_masks(tmp_path, encoding):
    if encoding == "internal_mask":
        first = _shard(tmp_path / "a.tif", 0, [10, 20], mask=[255, 0])  # nodata=None, second cell masked
    else:
        first = _shard(tmp_path / "a.tif", 0, [10, -1], nodata=-1)
    second = _shard(tmp_path / "b.tif", 2, [10, 20])

    mosaic = rs.mosaic_shards([first, second], str(tmp_path / "m.tif"))

    with rasterio.open(mosaic) as dataset:
        assert dataset.read(1, masked=True).mask.tolist() == [[False, True, False, False]]
    geometries = rs.native_geometries(_collection(a={"type": "Polygon", "coordinates": [[(0, 0), (4, 0), (4, 1),
                                                                                         (0, 1), (0, 0)]]}),
                                      roster=["a"])
    stats = rs.zonal_statistics(mosaic, geometries, family="evi", month="2026-09")
    assert stats.loc[0, "EVI__mean"] == pytest.approx(40 / 3)


def test_mosaic_keeps_valid_zero_and_masks_only_invalid_pixel(tmp_path):
    # nodata=None everywhere: a valid 0 must stay valid; only the internally masked cell is invalid.
    first = _shard(tmp_path / "a.tif", 0, [0, 10], mask=[255, 0])
    second = _shard(tmp_path / "b.tif", 2, [0, 30])

    mosaic = rs.mosaic_shards([first, second], str(tmp_path / "m.tif"))

    with rasterio.open(mosaic) as dataset:
        band = dataset.read(1, masked=True)
    assert band.mask.tolist() == [[False, True, False, False]]
    assert band.compressed().tolist() == [0.0, 0.0, 30.0]
    geometries = rs.native_geometries(_collection(a={"type": "Polygon", "coordinates": [[(0, 0), (4, 0), (4, 1),
                                                                                         (0, 1), (0, 0)]]}),
                                      roster=["a"])
    stats = rs.zonal_statistics(mosaic, geometries, family="evi", month="2026-09")
    assert stats.loc[0, "EVI__mean"] == pytest.approx(10.0)
    assert stats.loc[0, "EVI__std"] == pytest.approx(np.std([0.0, 0.0, 30.0]))
