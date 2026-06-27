from cloud.common import reports


def test_run_summary_report_has_required_fields():
    report = reports.build_run_summary(
        feature_month="2026-04",
        run_id="run-1",
        status="running",
        input_manifest_uri="gs://bucket/input_manifest.json",
        deployment={"provider": "gcp"},
        container_image_digest="sha256:" + "a" * 64,
    )

    required = {
        "schema_version",
        "feature_month",
        "run_id",
        "status",
        "input_manifest_uri",
        "deployment",
        "container_image_digest",
        "cloud_run_job",
        "cloud_batch_job",
        "vertex_ai_job",
        "hard_gates",
        "advisory_warnings",
        "record_only_metrics",
        "artifact_paths",
        "checksums",
        "waivers",
        "release_attempted",
        "released",
        "release_manifest_path",
        "forbidden_side_effect_check",
    }
    assert required <= report.keys()
    assert report["status"] == "running"


def test_validation_report_rejects_terminal_run_status():
    try:
        reports.build_validation_report(
            report_type="base_input_validation_report",
            feature_month="2026-04",
            run_id="run-1",
            status="released",
        )
    except reports.ReportContractError as exc:
        assert "validation report status" in str(exc)
    else:
        raise AssertionError("released must not be accepted for validation reports")


def test_evi_extraction_manifest_has_cloud_batch_fields():
    manifest = reports.build_evi_extraction_manifest(
        feature_month="2026-04",
        run_id="run-1",
        cloud_batch_job_id="job-1",
        cloud_batch_job_resource_name="projects/p/locations/us/jobs/job-1",
        worker_entrypoint="python3 -m cloud.batch.evi_worker",
        worker_container_image_uri="image@sha256:" + "a" * 64,
        worker_container_image_digest="sha256:" + "a" * 64,
        gee_export_task_id="task-1",
        source_raster_uri="gs://bucket/runs/run-1/gee_exports/MOD13A3_EVI_2026_04_processed.tif",
        source_raster_generation_or_version="123",
        geometry_uri="gs://bucket/geometry.gpkg",
        geometry_version_or_checksum="456",
        zone_count=2,
        empty_zone_count=1,
    )

    for field in (
        "gee_poll_interval_seconds",
        "gee_export_timeout_seconds",
        "batch_job_timeout_seconds",
        "retry_policy",
        "ephemeral_workspace_path",
        "output_roots",
        "artifact_paths",
        "checksums",
    ):
        assert field in manifest
    assert manifest["pixel_inclusion_rule"] == "all_touched_false_center_inside"


def test_release_manifest_status_is_current():
    manifest = reports.build_release_manifest(
        feature_month="2026-04",
        run_id="run-1",
        accepted_run_id="run-1",
        base_input_path="gs://bucket/released/202604/runs/run-1/ipcch_monthly_base_input_202604.csv",
        base_input_checksum="sha256:" + "b" * 64,
        summary_path="gs://bucket/released/202604/runs/run-1/ipcch_monthly_base_input_202604_summary.json",
        summary_checksum="sha256:" + "c" * 64,
        prediction_output_paths=[],
        prediction_output_checksums={},
    )
    assert manifest["status"] == "current"
    assert manifest["accepted_run_id"] == "run-1"
