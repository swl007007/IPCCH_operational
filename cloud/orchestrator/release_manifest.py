from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = "ipcch-monthly-e2e-release-v1"


def build_current_release_manifest(
    *,
    feature_month: str,
    run_id: str,
    accepted_run_id: str,
    container_image_digest: str,
    model_package: dict[str, Any],
    validation_status: dict[str, str],
    copied_artifacts: list[dict[str, Any]],
    referenced_artifacts: list[dict[str, Any]],
    **extra: Any,
) -> dict[str, Any]:
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "feature_month": feature_month,
        "run_id": run_id,
        "accepted_run_id": accepted_run_id,
        "status": "current",
        "container_image_digest": container_image_digest,
        "model_package": model_package,
        "validation_status": validation_status,
        "release_timestamp_utc": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "released_copied_artifacts": copied_artifacts,
        "released_referenced_artifacts": referenced_artifacts,
    }
    manifest.update(extra)
    return manifest
