import pandas as pd
import pytest

gpd = pytest.importorskip("geopandas")
from shapely.geometry import box  # noqa: E402

from tools import build_prepare_assets as assets  # noqa: E402


def _write(tmp_path, crs):
    frame = gpd.GeoDataFrame({"admin_code": ["0", "10"]}, geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)], crs=crs)
    path = tmp_path / "geometry.shp"
    frame.to_file(path)
    return path


def test_missing_crs_is_rejected_not_relabelled(tmp_path):
    path = _write(tmp_path, None)

    with pytest.raises(ValueError, match="no CRS"):
        assets.native_geometry(path, "ipcch")


def test_projected_geometry_is_reprojected_with_string_keys(tmp_path):
    path = _write(tmp_path, "EPSG:3857")

    frame = assets.native_geometry(path, "ipcch")

    assert frame.crs.to_epsg() == 4326 and frame["admin_code"].tolist() == ["0", "10"]
    assert frame.geometry.iloc[1].bounds[2] == pytest.approx(2 / 111319.49079327357, rel=1e-6)


def test_history_snapshot_inverts_mapping_and_bounds_months():
    panel = pd.DataFrame({"admin_code": ["0", "0", "10"], "year": [2026, 2026, 2026], "month": [3, 5, 3],
                          **{column: [1.0, 2.0, 3.0] for column in assets.MODEL_COLUMN_MAPPING["ipcch"]}})

    snapshots = assets.history_snapshots(panel, "ipcch", roster=["0", "10"], limit_month="2026-04")

    viirs = snapshots["viirs"]
    assert viirs["month"].tolist() == ["2026-03", "2026-03"]
    assert viirs["avg_rad__sum"].tolist() == [1.0, 3.0]  # nightlight_mean <- VIIRS SUM (IPCCH)
    assert viirs["avg_rad__mean"].isna().all()  # IPCCH panel carries no VIIRS mean
    with pytest.raises(ValueError, match="outside the roster"):
        assets.history_snapshots(panel, "ipcch", roster=["0"], limit_month="2026-04")
