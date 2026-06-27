import pytest

from cloud.batch import gee_export


def test_gee_export_manifest_contains_audit_fields():
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

    for field in (
        "export_task_id",
        "export_status",
        "date_window",
        "processing_params",
        "processed_raster_generation_or_version",
        "processed_raster_checksum",
    ):
        assert field in manifest
    assert manifest["status"] == "passed"
    assert manifest["processed_raster_checksum_algorithm"] == "sha256"
    assert manifest["checksums"]["processed_raster"]["algorithm"] == "sha256"
    assert manifest["created_at_utc"] != "2026-06-26T00:00:00Z"
    assert manifest["created_at_utc"].endswith("Z")


def test_gee_export_manifest_rejects_checksum_without_sha256_prefix():
    with pytest.raises(gee_export.GEEExportError, match="sha256"):
        gee_export.build_gee_export_manifest(
            feature_month="2026-04",
            run_id="run-1",
            earth_engine_project_id="ipcch-ee",
            export_task_id="task-1",
            export_status="COMPLETED",
            processed_raster_uri="gs://bucket/runs/run-1/gee_exports/MOD13A3_EVI_2026_04_processed.tif",
            processed_raster_generation_or_version="123",
            processed_raster_checksum="md5-base64-value",
        )


def test_gee_export_manifest_rejects_short_prefixed_sha256_checksum():
    with pytest.raises(gee_export.GEEExportError, match="sha256"):
        gee_export.build_gee_export_manifest(
            feature_month="2026-04",
            run_id="run-1",
            earth_engine_project_id="ipcch-ee",
            export_task_id="task-1",
            export_status="COMPLETED",
            processed_raster_uri="gs://bucket/runs/run-1/gee_exports/MOD13A3_EVI_2026_04_processed.tif",
            processed_raster_generation_or_version="123",
            processed_raster_checksum="sha256:abc",
        )


def test_gee_export_manifest_selected_month_mismatch_fails():
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
