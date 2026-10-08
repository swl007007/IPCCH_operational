import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from cloud.batch import evi_outputs, evi_service, evi_worker, gee_export
from cloud.common.object_store import LocalObjectStore
from cloud.orchestrator import batch_client


class FakeBatchClient:
    def __init__(self):
        self.requests = []

    def create_job(self, request):
        self.requests.append(request)
        return {"name": f"{request['parent']}/jobs/{request['job_id']}"}


class FakeEVIService:
    def __init__(self):
        self.calls = []

    def export_processed_raster(
        self, *, feature_month, run_id, manifest, run_prefix_uri
    ):
        self.calls.append(("export", feature_month, run_id, run_prefix_uri))
        return {
            "earth_engine_project_id": manifest["deployment"][
                "earth_engine_project_id"
            ],
            "export_task_id": "task-1",
            "export_status": "COMPLETED",
            "processed_raster_uri": run_prefix_uri
            + "gee_exports/MOD13A3_EVI_2026_04_processed.tif",
            "processed_raster_generation_or_version": "123",
            "processed_raster_checksum": "sha256:" + "a" * 64,
        }

    def extract_zonal_stats(self, *, feature_month, run_id, manifest, raster_uri):
        self.calls.append(("extract", raster_uri))
        return {
            "mean_wide_csv": "region_id,2026_04\nA,1.5\n",
            "std_wide_csv": "region_id,2026_04\nA,0.2\n",
            "scaffold_area_ids": ["A"],
            "cloud_batch_job_id": "batch-job-1",
            "cloud_batch_job_resource_name": "projects/p/locations/us/jobs/batch-job-1",
            "geometry_uri": "gs://bucket/geometry.gpkg",
            "geometry_version_or_checksum": "1",
            "zone_count": 1,
            "empty_zone_count": 0,
        }


def _valid_manifest():
    return json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "fixtures"
            / "cloud"
            / "input_manifest_202604_valid.json"
        ).read_text(encoding="utf-8")
    )


def test_batch_worker_writes_gee_evi_outputs_and_reports(tmp_path):
    store = LocalObjectStore(tmp_path)

    result = evi_worker.run_fake_evi_worker(
        store=store,
        feature_month="2026-04",
        run_id="run-1",
        run_prefix_uri="gs://bucket/monthly/runs/run-1/",
        zones=[
            {"area_id": "A", "values": [1000, 3000]},
            {"area_id": "B", "values": []},
        ],
    )

    assert result["status"] == "passed"
    expected_paths = {
        "gs://bucket/monthly/runs/run-1/gee_exports/gee_export_manifest.json",
        "gs://bucket/monthly/runs/run-1/evi/EVI_mean_extraction_results.csv",
        "gs://bucket/monthly/runs/run-1/evi/EVI_std_extraction_results.csv",
        "gs://bucket/monthly/runs/run-1/evi/EVI_mean_monthly_long.csv",
        "gs://bucket/monthly/runs/run-1/evi/EVI_std_monthly_long.csv",
        "gs://bucket/monthly/runs/run-1/evi/evi_extraction_manifest.json",
        "gs://bucket/monthly/runs/run-1/evi/evi_validation_report.json",
    }
    assert expected_paths <= set(store.list("gs://bucket/monthly/runs/run-1/"))
    gee_manifest = json.loads(
        store.read_text(
            "gs://bucket/monthly/runs/run-1/gee_exports/gee_export_manifest.json"
        )
    )
    assert gee_manifest["band"] == "EVI"
    assert gee_manifest["date_window"] == {"start": "2026-04-01", "end": "2026-05-01"}


def test_batch_worker_cli_returns_zero_and_writes_outputs(tmp_path):
    store = LocalObjectStore(tmp_path)
    exit_code = evi_worker.run_worker_cli(
        [
            "--feature-month",
            "2026-04",
            "--run-id",
            "run-1",
            "--run-prefix-uri",
            "gs://bucket/monthly/runs/run-1/",
            "--zones-json",
            '[{"area_id": "A", "values": [1000, 3000]}]',
        ],
        store=store,
    )

    assert exit_code == 0
    assert (
        "gs://bucket/monthly/runs/run-1/evi/evi_validation_report.json"
        in store.list("gs://bucket/monthly/runs/run-1/")
    )


def test_batch_worker_cli_returns_nonzero_on_hard_gate(tmp_path):
    store = LocalObjectStore(tmp_path)
    exit_code = evi_worker.run_worker_cli(
        [
            "--feature-month",
            "2026-04",
            "--run-id",
            "run-1",
            "--run-prefix-uri",
            "gs://bucket/monthly/runs/run-1/",
            "--zones-json",
            '[{"area_id": "A", "region_id": "R-A", "values": [1]}]',
        ],
        store=store,
    )

    assert exit_code == 1
    assert "gs://bucket/monthly/runs/run-1/evi/evi_worker_error.json" in store.list(
        "gs://bucket/monthly/runs/run-1/"
    )


def test_batch_worker_cli_uses_manifest_backed_production_evi_service(tmp_path):
    store = LocalObjectStore(tmp_path)
    service = FakeEVIService()
    manifest = _valid_manifest()
    manifest["deployment"]["gee_poll_interval_seconds"] = 7
    manifest["deployment"]["gee_export_timeout_seconds"] = 123
    manifest["deployment"]["batch_job_timeout_seconds"] = 456
    manifest["deployment"]["retry_policy"] = {"max_retries": 1}
    manifest_uri = "gs://bucket/manifests/input.json"
    store.write_text(manifest_uri, json.dumps(manifest))

    exit_code = evi_worker.run_worker_cli(
        [
            "--feature-month",
            "2026-04",
            "--run-id",
            "run-202604-valid",
            "--run-prefix-uri",
            "gs://bucket/monthly/runs/run-202604-valid/",
            "--run-root-uri",
            "gs://bucket/monthly/runs/run-202604-valid/",
            "--gee-export-root-uri",
            "gs://bucket/monthly/runs/run-202604-valid/gee_exports/",
            "--evi-output-root-uri",
            "gs://bucket/monthly/runs/run-202604-valid/evi/",
            "--logs-root-uri",
            "gs://bucket/monthly/runs/run-202604-valid/logs/",
            "--input-manifest-uri",
            manifest_uri,
        ],
        store=store,
        evi_service=service,
    )

    run_prefix = "gs://bucket/monthly/runs/run-202604-valid/"
    assert exit_code == 0
    assert service.calls == [
        ("export", "2026-04", "run-202604-valid", run_prefix),
        ("extract", run_prefix + "gee_exports/MOD13A3_EVI_2026_04_processed.tif"),
    ]
    assert set(store.list(run_prefix)) >= {
        run_prefix + "gee_exports/gee_export_manifest.json",
        run_prefix + "evi/EVI_mean_extraction_results.csv",
        run_prefix + "evi/EVI_std_extraction_results.csv",
        run_prefix + "evi/EVI_mean_monthly_long.csv",
        run_prefix + "evi/EVI_std_monthly_long.csv",
        run_prefix + "evi/evi_extraction_manifest.json",
        run_prefix + "evi/evi_validation_report.json",
    }
    extraction_manifest = json.loads(
        store.read_text(run_prefix + "evi/evi_extraction_manifest.json")
    )
    assert extraction_manifest["gee_poll_interval_seconds"] == 7
    assert extraction_manifest["gee_export_timeout_seconds"] == 123
    assert extraction_manifest["batch_job_timeout_seconds"] == 456
    assert extraction_manifest["retry_policy"] == {"max_retries": 1}
    assert extraction_manifest["output_roots"] == {
        "run_root_uri": run_prefix,
        "gee_export_root_uri": run_prefix + "gee_exports/",
        "evi_output_root_uri": run_prefix + "evi/",
        "logs_root_uri": run_prefix + "logs/",
    }


def test_batch_worker_cli_accepts_execution_contract_root_args(tmp_path):
    store = LocalObjectStore(tmp_path)
    service = FakeEVIService()
    manifest_uri = "gs://bucket/manifests/input.json"
    store.write_text(manifest_uri, json.dumps(_valid_manifest()))

    exit_code = evi_worker.run_worker_cli(
        [
            "--feature-month",
            "2026-04",
            "--run-id",
            "run-202604-valid",
            "--input-manifest-uri",
            manifest_uri,
            "--run-root-uri",
            "gs://bucket/monthly/runs/run-202604-valid/",
            "--gee-export-root-uri",
            "gs://bucket/monthly/runs/run-202604-valid/gee_exports/",
            "--evi-output-root-uri",
            "gs://bucket/monthly/runs/run-202604-valid/evi/",
            "--logs-root-uri",
            "gs://bucket/monthly/runs/run-202604-valid/logs/",
        ],
        store=store,
        evi_service=service,
    )

    assert exit_code == 0
    report = json.loads(
        store.read_text(
            "gs://bucket/monthly/runs/run-202604-valid/evi/evi_validation_report.json"
        )
    )
    assert report["reference_comparison"] == {"status": "not_provided"}


def test_batch_worker_cli_uses_reference_sample_uri_for_evi_comparison(tmp_path):
    store = LocalObjectStore(tmp_path)
    service = FakeEVIService()
    manifest_uri = "gs://bucket/manifests/input.json"
    reference_uri = "gs://bucket/reference/evi_reference.csv"
    store.write_text(manifest_uri, json.dumps(_valid_manifest()))
    store.write_text(reference_uri, "area_id,year,month,EVI_mean\nA,2026,4,1.5\n")

    exit_code = evi_worker.run_worker_cli(
        [
            "--feature-month",
            "2026-04",
            "--run-id",
            "run-202604-valid",
            "--input-manifest-uri",
            manifest_uri,
            "--run-root-uri",
            "gs://bucket/monthly/runs/run-202604-valid/",
            "--reference-sample-uri",
            reference_uri,
        ],
        store=store,
        evi_service=service,
    )

    assert exit_code == 0
    report = json.loads(
        store.read_text(
            "gs://bucket/monthly/runs/run-202604-valid/evi/evi_validation_report.json"
        )
    )
    assert report["reference_comparison"]["status"] == "insufficient_pairs"


def test_batch_worker_cli_builds_default_manifest_backed_evi_service(
    tmp_path, monkeypatch
):
    store = LocalObjectStore(tmp_path)
    service = FakeEVIService()
    manifest_uri = "gs://bucket/manifests/input.json"
    store.write_text(manifest_uri, json.dumps(_valid_manifest()))
    monkeypatch.setattr(evi_worker, "build_default_evi_service", lambda: service)

    exit_code = evi_worker.run_worker_cli(
        [
            "--feature-month",
            "2026-04",
            "--run-id",
            "run-202604-valid",
            "--run-prefix-uri",
            "gs://bucket/monthly/runs/run-202604-valid/",
            "--input-manifest-uri",
            manifest_uri,
        ],
        store=store,
    )

    assert exit_code == 0
    assert service.calls[0] == (
        "export",
        "2026-04",
        "run-202604-valid",
        "gs://bucket/monthly/runs/run-202604-valid/",
    )


def test_batch_submitter_builds_digest_pinned_job_spec_with_runtime_defaults():
    config = batch_client.BatchJobConfig(
        job_name_prefix="ipcch-evi",
        image_uri="us/pkg/ipcch@sha256:" + "a" * 64,
        service_account="batch@project.iam.gserviceaccount.com",
        run_id="run-1",
        feature_month="2026-04",
        worker_args=["--run-id", "run-1"],
    )

    spec = batch_client.build_batch_job_spec(config)

    task_spec = spec["task_groups"][0]["task_spec"]
    container = task_spec["runnables"][0]["container"]
    assert container["image_uri"].endswith("@sha256:" + "a" * 64)
    assert container["entrypoint"] == "python3"
    assert container["commands"] == [
        "-m",
        "cloud.batch.evi_worker",
        "--run-id",
        "run-1",
    ]
    assert "options" not in container
    assert "service_account" not in task_spec
    assert spec["allocation_policy"]["service_account"]["email"] == (
        "batch@project.iam.gserviceaccount.com"
    )
    assert task_spec["max_run_duration"] == "28800s"
    assert task_spec["max_retry_count"] == 2
    assert spec["logs_policy"]["destination"] == "CLOUD_LOGGING"


def test_batch_submitter_job_payload_contains_only_job_fields():
    config = batch_client.BatchJobConfig(
        job_name_prefix="ipcch-evi",
        image_uri="us/pkg/ipcch@sha256:" + "a" * 64,
        service_account="batch@project.iam.gserviceaccount.com",
        run_id="run-1",
        feature_month="2026-04",
        worker_args=["--run-id", "run-1"],
    )

    request = batch_client.build_batch_create_job_request(
        config, parent="projects/ipcch/locations/us-central1"
    )

    assert request["job_id"] == "ipcch-evi-run-1"
    assert "job_id" not in request["job"]
    assert "feature_month" not in request["job"]
    assert "name" not in request["job"]
    assert request["job"]["labels"]["ipcch_feature_month"] == "202604"


def test_batch_submitter_sanitizes_job_id_without_changing_run_label():
    config = batch_client.BatchJobConfig(
        job_name_prefix="ipcch-evi",
        image_uri="us/pkg/ipcch@sha256:" + "a" * 64,
        service_account="batch@project.iam.gserviceaccount.com",
        run_id="Run_2026.04_" + "X" * 80,
        feature_month="2026-04",
        worker_args=["--run-id", "Run_2026.04_" + "X" * 80],
    )

    request = batch_client.build_batch_create_job_request(
        config, parent="projects/ipcch/locations/us-central1"
    )

    assert request["job_id"].startswith("ipcch-evi-run-2026-04-")
    assert request["job_id"] == request["job_id"].lower()
    assert "_" not in request["job_id"]
    assert "." not in request["job_id"]
    assert len(request["job_id"]) <= 63
    assert request["job"]["labels"]["ipcch_run_id"].startswith("run-2026-04-")


def test_batch_submitter_bounds_job_id_with_overlong_prefix():
    config = batch_client.BatchJobConfig(
        job_name_prefix="ipcch-evi-" + "x" * 120,
        image_uri="us/pkg/ipcch@sha256:" + "a" * 64,
        service_account="batch@project.iam.gserviceaccount.com",
        run_id="run-1",
        feature_month="2026-04",
        worker_args=["--run-id", "run-1"],
    )

    request = batch_client.build_batch_create_job_request(
        config, parent="projects/ipcch/locations/us-central1"
    )

    assert len(request["job_id"]) <= 63
    assert request["job_id"] == request["job_id"].lower()
    assert request["job_id"].startswith("ipcch-evi-")


def test_batch_submitter_job_spec_uses_python_client_field_names():
    config = batch_client.BatchJobConfig(
        job_name_prefix="ipcch-evi",
        image_uri="us/pkg/ipcch@sha256:" + "a" * 64,
        service_account="batch@project.iam.gserviceaccount.com",
        run_id="run-1",
        feature_month="2026-04",
        worker_args=["--run-id", "run-1"],
    )

    spec = batch_client.build_batch_job_spec(config)

    assert "taskGroups" not in spec
    assert "allocationPolicy" not in spec
    assert "logsPolicy" not in spec
    assert (
        "imageUri"
        not in spec["task_groups"][0]["task_spec"]["runnables"][0]["container"]
    )


def test_batch_submitter_rejects_tag_only_image():
    config = batch_client.BatchJobConfig(
        job_name_prefix="ipcch-evi",
        image_uri="us/pkg/ipcch:latest",
        service_account="batch@project.iam.gserviceaccount.com",
        run_id="run-1",
        feature_month="2026-04",
        worker_args=[],
    )

    with pytest.raises(batch_client.BatchJobConfigError, match="digest"):
        batch_client.build_batch_job_spec(config)


def test_batch_submitter_calls_cloud_batch_client_with_job_request():
    fake_client = FakeBatchClient()
    config = batch_client.BatchJobConfig(
        job_name_prefix="ipcch-evi",
        image_uri="us/pkg/ipcch@sha256:" + "a" * 64,
        service_account="batch@project.iam.gserviceaccount.com",
        run_id="run-1",
        feature_month="2026-04",
        worker_args=["--run-id", "run-1"],
    )

    response = batch_client.submit_batch_job(
        config,
        client=fake_client,
        parent="projects/ipcch/locations/us-central1",
    )

    assert response == {
        "name": "projects/ipcch/locations/us-central1/jobs/ipcch-evi-run-1"
    }
    assert fake_client.requests == [
        {
            "parent": "projects/ipcch/locations/us-central1",
            "job_id": "ipcch-evi-run-1",
            "job": batch_client.build_batch_job_spec(config),
        }
    ]


def test_default_evi_service_is_in_repo_production_service(monkeypatch):
    service = evi_worker.build_default_evi_service()

    assert isinstance(service, evi_service.EarthEngineRasterioEVIService)


def test_in_repo_evi_service_uses_ee_and_rasterio_adapters(tmp_path):
    store = LocalObjectStore(tmp_path)
    manifest = _valid_manifest()
    run_prefix = "gs://bucket/monthly/runs/run-202604-valid/"
    calls = []

    class FakeEEAdapter:
        def export_processed_raster(self, **kwargs):
            calls.append(("ee", kwargs["feature_month"], kwargs["run_prefix_uri"]))
            return {
                "earth_engine_project_id": "ipcch-ee",
                "export_task_id": "task-1",
                "export_status": "COMPLETED",
                "processed_raster_uri": run_prefix
                + "gee_exports/MOD13A3_EVI_2026_04_processed.tif",
                "processed_raster_generation_or_version": "42",
                "processed_raster_checksum": "sha256:" + "a" * 64,
            }

    class FakeRasterioAdapter:
        def extract_zonal_stats(self, **kwargs):
            calls.append(("rasterio", kwargs["raster_uri"]))
            return {
                "mean_wide_csv": "region_id,2026_04\nA,1.5\n",
                "std_wide_csv": "region_id,2026_04\nA,0.2\n",
                "scaffold_area_ids": ["A"],
                "cloud_batch_job_id": "batch-job-1",
                "cloud_batch_job_resource_name": "projects/p/locations/us/jobs/batch-job-1",
                "geometry_uri": "gs://bucket/geometry.gpkg",
                "geometry_version_or_checksum": "1",
                "zone_count": 1,
                "empty_zone_count": 0,
            }

    service = evi_service.EarthEngineRasterioEVIService(
        store=store,
        ee_adapter=FakeEEAdapter(),
        rasterio_adapter=FakeRasterioAdapter(),
    )

    export = service.export_processed_raster(
        feature_month="2026-04",
        run_id="run-202604-valid",
        manifest=manifest,
        run_prefix_uri=run_prefix,
    )
    extraction = service.extract_zonal_stats(
        feature_month="2026-04",
        run_id="run-202604-valid",
        manifest=manifest,
        raster_uri=export["processed_raster_uri"],
    )

    assert export["processed_raster_generation_or_version"] == "42"
    assert extraction["zone_count"] == 1
    assert calls == [
        ("ee", "2026-04", run_prefix),
        ("rasterio", run_prefix + "gee_exports/MOD13A3_EVI_2026_04_processed.tif"),
    ]


def test_ee_export_adapter_uses_manifest_evi_config_and_export_region(
    tmp_path, monkeypatch
):
    store = LocalObjectStore(tmp_path)
    manifest = _valid_manifest()
    evi_config = next(
        artifact
        for artifact in manifest["artifacts"]
        if artifact["artifact_type"] == "gee_evi_export_config"
    )
    evi_config["processing_params"] = {
        "export_region": {"type": "Polygon", "coordinates": []},
        "scale": 500,
    }
    calls = {}

    class FakeImageCollection:
        def __init__(self, collection):
            calls["collection"] = collection

        def filterDate(self, start, end):
            calls["date_window"] = {"start": start, "end": end}
            return self

        def select(self, band):
            calls["band"] = band
            return self

        def first(self):
            return "image"

    class FakeTask:
        id = "task-1"

        def start(self):
            calls["started"] = True
            store.write_text(
                "gs://bucket/monthly/runs/run-1/gee_exports/MOD13A3_EVI_2026_04_processed.tif",
                "fake-raster",
            )

        def status(self):
            return {"state": "COMPLETED", "id": "task-1"}

    def to_cloud_storage(**kwargs):
        calls["export_kwargs"] = kwargs
        return FakeTask()

    fake_ee = SimpleNamespace(
        Initialize=lambda project: calls.setdefault("project", project),
        ImageCollection=FakeImageCollection,
        batch=SimpleNamespace(
            Export=SimpleNamespace(
                image=SimpleNamespace(toCloudStorage=to_cloud_storage)
            )
        ),
    )
    monkeypatch.setitem(sys.modules, "ee", fake_ee)

    adapter = evi_service.EarthEngineEVIExportAdapter(store=store)
    result = adapter.export_processed_raster(
        feature_month="2026-04",
        run_id="run-1",
        manifest=manifest,
        run_prefix_uri="gs://bucket/monthly/runs/run-1/",
    )

    assert result["export_task_id"] == "task-1"
    assert calls["collection"] == "MODIS/061/MOD13A3"
    assert calls["band"] == "EVI"
    assert calls["date_window"] == {"start": "2026-04-01", "end": "2026-05-01"}
    assert (
        calls["export_kwargs"]["region"]
        == evi_config["processing_params"]["export_region"]
    )
    assert calls["export_kwargs"]["scale"] == 500


def test_rasterio_adapter_drives_rows_from_scaffold_and_rejects_duplicate_geometry_ids(
    tmp_path, monkeypatch
):
    store = LocalObjectStore(tmp_path)
    manifest = _valid_manifest()
    scaffold_uri = next(
        artifact
        for artifact in manifest["artifacts"]
        if artifact["artifact_type"] == "scaffold"
    )["uri"]
    geometry_uri = next(
        artifact
        for artifact in manifest["artifacts"]
        if artifact["artifact_type"] == "geometry"
    )["uri"]
    store.write_text(scaffold_uri, "area_id,year,month\nA,2026,4\nB,2026,4\n")
    store.write_text(
        geometry_uri,
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "properties": {"area_id": "A"}, "geometry": {}},
                    {"type": "Feature", "properties": {"area_id": "A"}, "geometry": {}},
                ],
            }
        ),
    )
    monkeypatch.setitem(sys.modules, "rasterio", SimpleNamespace(open=lambda uri: None))
    monkeypatch.setitem(
        sys.modules,
        "rasterio.mask",
        SimpleNamespace(mask=lambda *args, **kwargs: None),
    )

    adapter = evi_service.RasterioZonalStatsAdapter(store=store)

    with pytest.raises(evi_service.EVIServiceError, match="duplicate"):
        adapter.extract_zonal_stats(
            feature_month="2026-04",
            run_id="run-1",
            manifest=manifest,
            raster_uri="gs://bucket/raster.tif",
        )


def test_gee_export_manifest_builder_records_selected_month_and_raster_reference():
    manifest = gee_export.build_gee_export_manifest(
        feature_month="2026-04",
        run_id="run-1",
        earth_engine_project_id="ipcch-ee",
        export_task_id="task-1",
        export_status="COMPLETED",
        processed_raster_uri="gs://bucket/runs/run-1/gee_exports/MOD13A3_EVI_2026_04_processed.tif",
        processed_raster_generation_or_version="123",
        processed_raster_checksum="sha256:" + "a" * 64,
    )

    assert manifest["earth_engine_collection"] == "MODIS/061/MOD13A3"
    assert manifest["band"] == "EVI"
    assert manifest["date_window"] == {"start": "2026-04-01", "end": "2026-05-01"}
    assert manifest["processed_raster_generation_or_version"] == "123"


def test_gee_export_manifest_rejects_selected_month_mismatch():
    with pytest.raises(gee_export.GEEExportError, match="selected month"):
        gee_export.build_gee_export_manifest(
            feature_month="2026-04",
            run_id="run-1",
            earth_engine_project_id="ipcch-ee",
            export_task_id="task-1",
            export_status="COMPLETED",
            processed_raster_uri="gs://bucket/runs/run-1/gee_exports/MOD13A3_EVI_2026_05_processed.tif",
            processed_raster_generation_or_version="123",
            processed_raster_checksum="sha256:" + "a" * 64,
        )


def test_evi_outputs_writer_returns_selected_month_mean_and_std_long_tables():
    outputs = evi_outputs.write_selected_month_long_outputs(
        mean_wide_csv="region_id,2026_04\nA,1.5\nB,\n",
        std_wide_csv="region_id,2026_04\nA,0.2\nB,\n",
        feature_month="2026-04",
        scaffold_area_ids=["A", "B"],
    )

    assert (
        outputs["EVI_mean_monthly_long.csv"].splitlines()[0]
        == "area_id,year,month,EVI_mean"
    )
    assert (
        outputs["EVI_std_monthly_long.csv"].splitlines()[0]
        == "area_id,year,month,EVI_std"
    )
    assert "A,2026,4,1.5" in outputs["EVI_mean_monthly_long.csv"]
