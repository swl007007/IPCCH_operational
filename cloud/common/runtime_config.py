from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class RuntimeDefaults:
    gee_poll_interval_seconds: int = 60
    gee_export_timeout_seconds: int = 21600
    batch_job_timeout_seconds: int = 28800
    vertex_ai_custom_job_timeout_seconds: int = 7200
    max_retries: int = 2


def resolve_runtime_config(deployment: Mapping[str, Any]) -> RuntimeDefaults:
    retry_policy = deployment.get("retry_policy") or {}
    return RuntimeDefaults(
        gee_poll_interval_seconds=int(deployment.get("gee_poll_interval_seconds", 60)),
        gee_export_timeout_seconds=int(
            deployment.get("gee_export_timeout_seconds", 21600)
        ),
        batch_job_timeout_seconds=int(
            deployment.get("batch_job_timeout_seconds", 28800)
        ),
        vertex_ai_custom_job_timeout_seconds=int(
            deployment.get("vertex_ai_custom_job_timeout_seconds", 7200)
        ),
        max_retries=int(retry_policy.get("max_retries", 2)),
    )
