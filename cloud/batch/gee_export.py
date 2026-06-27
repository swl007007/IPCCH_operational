from __future__ import annotations

from datetime import date
from datetime import datetime
from datetime import timezone
import re


class GEEExportError(ValueError):
    """Raised when GEE export metadata violates the selected-month contract."""


def build_gee_export_manifest(
    *,
    feature_month: str,
    run_id: str,
    earth_engine_project_id: str,
    export_task_id: str,
    export_status: str,
    processed_raster_uri: str,
    processed_raster_generation_or_version: str,
    processed_raster_checksum: str | None,
    status: str = "passed",
) -> dict:
    year, month = (int(part) for part in feature_month.split("-"))
    expected_token = f"{year}_{month:02d}"
    if expected_token not in processed_raster_uri:
        raise GEEExportError("processed raster URI must match selected month")
    processed_raster_checksum = _normalize_sha256_checksum(processed_raster_checksum)
    checksum_algorithm = "sha256" if processed_raster_checksum else None
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    return {
        "schema_version": "ipcch-monthly-e2e-report-v1",
        "feature_month": feature_month,
        "run_id": run_id,
        "earth_engine_project_id": earth_engine_project_id,
        "earth_engine_collection": "MODIS/061/MOD13A3",
        "band": "EVI",
        "date_window": {"start": f"{feature_month}-01", "end": next_month.isoformat()},
        "processing_params": {
            "source_scale": "raw_scaled_integer",
            "selected_band": "EVI",
        },
        "export_task_id": export_task_id,
        "export_status": export_status,
        "processed_raster_uri": processed_raster_uri,
        "processed_raster_generation_or_version": processed_raster_generation_or_version,
        "processed_raster_checksum": processed_raster_checksum,
        "processed_raster_checksum_algorithm": checksum_algorithm,
        "created_at_utc": _utc_now(),
        "status": status,
        "artifact_paths": {"processed_raster_uri": processed_raster_uri},
        "checksums": {
            "processed_raster": {
                "checksum": processed_raster_checksum,
                "algorithm": checksum_algorithm,
            }
        },
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_sha256_checksum(checksum: str | None) -> str | None:
    if checksum is None:
        return None
    if re.fullmatch(r"[A-Fa-f0-9]{64}", checksum):
        return "sha256:" + checksum.lower()
    prefixed = re.fullmatch(r"sha256:([A-Fa-f0-9]{64})", checksum)
    if prefixed:
        return "sha256:" + prefixed.group(1).lower()
    raise GEEExportError("processed raster checksum must be sha256")
