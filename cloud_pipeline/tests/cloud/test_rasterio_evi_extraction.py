import pandas as pd
import pytest
import sys
from types import SimpleNamespace

from cloud.batch import evi_extract
from cloud.batch import evi_service
from cloud.common.object_store import LocalObjectStore


def test_compute_zone_stats_preserves_empty_zones_and_center_rule():
    zones = [
        {"area_id": "A", "values": [1000, 3000]},
        {"area_id": "B", "values": []},
    ]

    results = evi_extract.compute_evi_zone_stats(
        zones, pixel_inclusion_rule="all_touched_false_center_inside"
    )

    assert results == [
        {"region_id": "A", "EVI_mean": 2000.0, "EVI_std": 1000.0},
        {"region_id": "B", "EVI_mean": None, "EVI_std": None},
    ]


def test_compute_zone_stats_rejects_region_area_mismatch():
    zones = [{"area_id": "A", "region_id": "R-A", "values": [1]}]

    try:
        evi_extract.compute_evi_zone_stats(
            zones, pixel_inclusion_rule="all_touched_false_center_inside"
        )
    except evi_extract.EVIExtractionError as exc:
        assert "region_id must equal area_id" in str(exc)
    else:
        raise AssertionError("region_id != area_id must fail")


def test_long_outputs_contain_selected_month_and_scaffold_row_count():
    wide = pd.DataFrame(
        [
            {"region_id": "A", "2026_04": 2000.0},
            {"region_id": "B", "2026_04": None},
        ]
    )

    long = evi_extract.wide_month_to_long(
        wide,
        feature_name="EVI_mean",
        feature_month="2026-04",
        scaffold_area_ids=["A", "B"],
    )

    assert list(long.columns) == ["area_id", "year", "month", "EVI_mean"]
    assert len(long) == 2
    assert set(long["area_id"]) == {"A", "B"}
    assert set(long["year"]) == {2026}
    assert set(long["month"]) == {4}


def test_rasterio_adapter_preserves_non_overlapping_zone_as_empty_row(
    tmp_path, monkeypatch
):
    store = LocalObjectStore(tmp_path)
    scaffold_uri = "gs://bucket/scaffold.csv"
    geometry_uri = "gs://bucket/geometry.geojson"
    store.write_text(scaffold_uri, "area_id,year,month\nA,2026,4\nB,2026,4\n")
    store.write_text(
        geometry_uri,
        """
{
  "type": "FeatureCollection",
  "features": [
    {"type": "Feature", "properties": {"area_id": "A"}, "geometry": {"type": "Polygon", "coordinates": []}},
    {"type": "Feature", "properties": {"area_id": "B"}, "geometry": {"type": "Polygon", "coordinates": []}}
  ]
}
""",
    )
    manifest = {
        "artifacts": [
            {"artifact_type": "scaffold", "uri": scaffold_uri},
            {"artifact_type": "geometry", "uri": geometry_uri, "generation": "1"},
        ]
    }

    class FakeDataset:
        crs = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FakeMaskedData:
        def __getitem__(self, index):
            return SimpleNamespace(compressed=lambda: [1000.0, 3000.0])

    def fake_mask(dataset, shapes, **kwargs):
        if fake_mask.calls == 0:
            fake_mask.calls += 1
            return FakeMaskedData(), None
        raise ValueError("Input shapes do not overlap raster")

    fake_mask.calls = 0
    monkeypatch.setitem(
        sys.modules,
        "rasterio",
        SimpleNamespace(open=lambda uri: FakeDataset()),
    )
    monkeypatch.setitem(
        sys.modules,
        "rasterio.mask",
        SimpleNamespace(mask=fake_mask),
    )

    result = evi_service.RasterioZonalStatsAdapter(store=store).extract_zonal_stats(
        feature_month="2026-04",
        run_id="run-1",
        manifest=manifest,
        raster_uri="gs://bucket/raster.tif",
    )

    mean = pd.read_csv(pd.io.common.StringIO(result["mean_wide_csv"]))
    assert result["empty_zone_count"] == 1
    assert list(mean["region_id"]) == ["A", "B"]
    assert pd.isna(mean.loc[mean["region_id"] == "B", "2026_04"]).all()


def test_gee_export_adapter_requires_immutable_raster_reference(tmp_path, monkeypatch):
    class FakeTask:
        id = "task-1"

        def start(self):
            return None

        def status(self):
            return {"state": "COMPLETED", "id": self.id}

    class FakeExportImage:
        @staticmethod
        def toCloudStorage(**kwargs):
            return FakeTask()

    fake_ee = SimpleNamespace(
        Initialize=lambda project: None,
        ImageCollection=lambda collection: SimpleNamespace(
            filterDate=lambda start, end: SimpleNamespace(
                select=lambda band: SimpleNamespace(first=lambda: "image")
            )
        ),
        batch=SimpleNamespace(Export=SimpleNamespace(image=FakeExportImage)),
    )
    monkeypatch.setitem(sys.modules, "ee", fake_ee)
    manifest = {
        "deployment": {
            "earth_engine_project_id": "ipcch-ee",
            "gee_poll_interval_seconds": 1,
            "gee_export_timeout_seconds": 1,
        },
        "artifacts": [
            {
                "artifact_type": "gee_evi_export_config",
                "earth_engine_collection": "MODIS/061/MOD13A3",
                "band": "EVI",
                "processing_params": {},
            }
        ],
    }

    with pytest.raises(evi_service.EVIServiceError, match="immutable"):
        evi_service.EarthEngineEVIExportAdapter(
            store=LocalObjectStore(tmp_path)
        ).export_processed_raster(
            feature_month="2026-04",
            run_id="run-1",
            manifest=manifest,
            run_prefix_uri="gs://bucket/runs/run-1/",
        )
