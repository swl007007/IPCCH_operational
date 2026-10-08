from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = "ipcch-monthly-e2e-report-v1"
RUN_STATUSES = {"running", "failed", "released", "release_failed", "release_conflict"}
VALIDATION_STATUSES = {"passed", "failed", "passed_with_warnings"}
RELEASE_MANIFEST_STATUSES = {"current"}


class ReportContractError(ValueError):
    """Raised when a report builder receives fields outside the report contract."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _common_report(
    *,
    feature_month: str,
    run_id: str,
    status: str,
    allowed_statuses: set[str],
    **extra: Any,
) -> dict[str, Any]:
    if status not in allowed_statuses:
        raise ReportContractError(f"invalid report status: {status}")
    report = {
        "schema_version": SCHEMA_VERSION,
        "feature_month": feature_month,
        "run_id": run_id,
        "status": status,
        "hard_gates": [],
        "advisory_warnings": [],
        "record_only_metrics": {},
        "artifact_paths": {},
        "checksums": {},
    }
    report.update(extra)
    return report


def build_run_summary(
    *,
    feature_month: str,
    run_id: str,
    status: str,
    input_manifest_uri: str,
    deployment: dict[str, Any],
    container_image_digest: str,
    **extra: Any,
) -> dict[str, Any]:
    report = _common_report(
        feature_month=feature_month,
        run_id=run_id,
        status=status,
        allowed_statuses=RUN_STATUSES,
        input_manifest_uri=input_manifest_uri,
        deployment=deployment,
        container_image_digest=container_image_digest,
        cloud_run_job={},
        cloud_batch_job={},
        vertex_ai_job={},
        waivers=[],
        release_attempted=False,
        released=False,
        release_manifest_path=None,
        forbidden_side_effect_check={},
    )
    report.update(extra)
    return report


def build_validation_report(
    *,
    report_type: str,
    feature_month: str,
    run_id: str,
    status: str,
    **extra: Any,
) -> dict[str, Any]:
    if status not in VALIDATION_STATUSES:
        raise ReportContractError(f"validation report status is not allowed: {status}")
    report = _common_report(
        feature_month=feature_month,
        run_id=run_id,
        status=status,
        allowed_statuses=VALIDATION_STATUSES,
        report_type=report_type,
    )
    report.update(extra)
    return report


def build_evi_extraction_manifest(
    *,
    feature_month: str,
    run_id: str,
    cloud_batch_job_id: str,
    cloud_batch_job_resource_name: str,
    worker_entrypoint: str,
    worker_container_image_uri: str,
    worker_container_image_digest: str,
    gee_export_task_id: str,
    source_raster_uri: str,
    source_raster_generation_or_version: str,
    geometry_uri: str,
    geometry_version_or_checksum: str,
    zone_count: int,
    empty_zone_count: int,
    status: str = "passed",
    **extra: Any,
) -> dict[str, Any]:
    report = _common_report(
        feature_month=feature_month,
        run_id=run_id,
        status=status,
        allowed_statuses={"passed", "failed"},
        worker_type="cloud_batch",
        cloud_batch_job_id=cloud_batch_job_id,
        cloud_batch_job_resource_name=cloud_batch_job_resource_name,
        worker_entrypoint=worker_entrypoint,
        worker_container_image_uri=worker_container_image_uri,
        worker_container_image_digest=worker_container_image_digest,
        gee_export_task_id=gee_export_task_id,
        gee_poll_interval_seconds=60,
        gee_export_timeout_seconds=21600,
        batch_job_timeout_seconds=28800,
        retry_policy={"max_retries": 2},
        ephemeral_workspace_path="/tmp/ipcch-cloud-worker",
        output_roots={},
        source_raster_uri=source_raster_uri,
        source_raster_generation_or_version=source_raster_generation_or_version,
        geometry_uri=geometry_uri,
        geometry_version_or_checksum=geometry_version_or_checksum,
        rasterio_version=None,
        gdal_version=None,
        pixel_inclusion_rule="all_touched_false_center_inside",
        nodata_rule="ignore_nodata_and_emit_empty_zone_nulls",
        zone_count=zone_count,
        empty_zone_count=empty_zone_count,
        log_uri=None,
    )
    report.update(extra)
    return report


def build_release_manifest(
    *,
    feature_month: str,
    run_id: str,
    accepted_run_id: str,
    base_input_path: str,
    base_input_checksum: str,
    summary_path: str,
    summary_checksum: str,
    prediction_output_paths: list[str],
    prediction_output_checksums: dict[str, str],
    status: str = "current",
    **extra: Any,
) -> dict[str, Any]:
    if status not in RELEASE_MANIFEST_STATUSES:
        raise ReportContractError(f"release manifest status is not allowed: {status}")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "feature_month": feature_month,
        "run_id": run_id,
        "accepted_run_id": accepted_run_id,
        "status": status,
        "base_input_path": base_input_path,
        "base_input_checksum": base_input_checksum,
        "summary_path": summary_path,
        "summary_checksum": summary_checksum,
        "prediction_output_paths": prediction_output_paths,
        "prediction_output_checksums": prediction_output_checksums,
        "release_timestamp_utc": _utc_now(),
        "released_copied_artifacts": [],
        "released_referenced_artifacts": [],
        "artifact_paths": {},
        "checksums": {},
    }
    manifest.update(extra)
    return manifest
