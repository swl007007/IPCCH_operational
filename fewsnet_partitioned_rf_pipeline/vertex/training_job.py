"""Thin Vertex Custom Job boundary for FEWSNET suite training."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
import re
import time
from typing import Any, Callable, Protocol

from fewsnet_partitioned_rf_pipeline.vertex.storage import (
    ArtifactStore,
    put_immutable_or_verify,
)


_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_OPERATION_LABEL = "fewsnet_operation"
_TERMINAL_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
}
_CANCEL_TERMINAL_STATES = {
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
}


@dataclass(frozen=True)
class TrainingCustomJobConfig:
    project_id: str
    region: str
    run_id: str
    job_id: str
    snapshot_manifest_uri: str
    suite_version: str
    run_root_uri: str
    model_root_uri: str
    container_image_uri: str
    container_image_digest: str
    source_git_commit: str
    training_service_account: str
    training_machine_type: str = "n2-highmem-8"
    training_timeout_seconds: int = 21600


class TrainingJobBackend(Protocol):
    """Minimal backend used by Task 13; orchestration remains in Task 18."""

    def submit(self, request: dict[str, Any]) -> object: ...

    def get(self, job_name: str) -> object: ...

    def cancel(self, job_name: str) -> object: ...


class TrainingJobTimeoutError(TimeoutError):
    """Raised only after a timed-out job reaches cancelled or failed state."""

    def __init__(self, job_name: str, resource: dict[str, Any]) -> None:
        super().__init__(
            "FEWSNET training Custom Job exceeded its timeout and reached "
            f"{resource.get('state', '<unknown>')}: {job_name}"
        )
        self.job_name = job_name
        self.resource = resource


def build_training_custom_job_spec(config: TrainingCustomJobConfig) -> dict:
    """Build one digest-pinned worker request for the three-horizon trainer."""
    _validate_config(config)
    training_output_uri = f"{config.run_root_uri.rstrip('/')}/training"
    args = [
        "--snapshot-manifest-uri",
        config.snapshot_manifest_uri,
        "--suite-version",
        config.suite_version,
        "--run-root-uri",
        config.run_root_uri,
        "--model-root-uri",
        config.model_root_uri,
        "--container-image-uri",
        config.container_image_uri,
        "--container-image-digest",
        config.container_image_digest,
        "--source-git-commit",
        config.source_git_commit,
    ]
    environment = [
        {"name": "PROJECT_ID", "value": config.project_id},
        {"name": "VERTEX_AI_REGION", "value": config.region},
        {"name": "RUN_ID", "value": config.run_id},
        {"name": "SUITE_VERSION", "value": config.suite_version},
        {"name": "TRAINING_OUTPUT_URI", "value": training_output_uri},
    ]
    return {
        "display_name": config.job_id,
        "job_spec": {
            "worker_pool_specs": [
                {
                    "replica_count": 1,
                    "machine_spec": {
                        "machine_type": config.training_machine_type,
                    },
                    "container_spec": {
                        "image_uri": config.container_image_uri,
                        "command": [
                            "python3",
                            "-m",
                            "fewsnet_partitioned_rf_pipeline.cli.train",
                        ],
                        "args": args,
                        "env": environment,
                    },
                }
            ],
            "service_account": config.training_service_account,
            "base_output_directory": {
                "output_uri_prefix": training_output_uri,
            },
            "scheduling": {
                "timeout": f"{config.training_timeout_seconds}s",
            },
        },
        "labels": {
            "fewsnet_mode": "training",
            "fewsnet_region": _label_value(config.region),
            "fewsnet_run": _label_value(config.run_id),
        },
    }


def submit_and_persist_training_custom_job(
    config: TrainingCustomJobConfig,
    *,
    backend: TrainingJobBackend,
    store: ArtifactStore,
) -> dict[str, Any]:
    """Submit one job and persist its normalized request/resource before polling."""
    custom_job = build_training_custom_job_spec(config)
    request = {
        "parent": (
            f"projects/{config.project_id}/locations/{config.region}"
        ),
        "custom_job": custom_job,
    }
    custom_job["labels"][_OPERATION_LABEL] = _operation_identity(request)
    resource = _normalize_mapping(backend.submit(request), "submitted resource")
    name = resource.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("submitted Custom Job resource must contain a name")

    evidence = {
        "schema_version": "fewsnet-training-custom-job-v1",
        "request": request,
        "resource": resource,
    }
    evidence_bytes = json.dumps(
        evidence,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    put_immutable_or_verify(
        store,
        f"{config.run_root_uri.rstrip('/')}/training/custom_job.json",
        evidence_bytes,
    )
    return resource


def _operation_identity(request: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            request,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:63]


def wait_for_training_custom_job(
    job_name: str,
    *,
    backend: TrainingJobBackend,
    training_timeout_seconds: int,
    poll_interval_seconds: float = 30.0,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Wait for a terminal job, cancelling the exact resource on timeout."""
    if not isinstance(job_name, str) or not job_name:
        raise ValueError("job_name is required")
    if (
        isinstance(training_timeout_seconds, bool)
        or not isinstance(training_timeout_seconds, int)
        or training_timeout_seconds <= 0
    ):
        raise ValueError("training_timeout_seconds must be a positive integer")
    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be positive")

    started_at = monotonic()
    cancellation_requested = False
    while True:
        resource = _normalize_mapping(backend.get(job_name), "Custom Job resource")
        resource_name = resource.get("name")
        if resource_name != job_name:
            raise ValueError(
                "Custom Job backend returned a different resource name: "
                f"expected {job_name}, got {resource_name}"
            )
        state = _state_name(resource.get("state"))
        resource["state"] = state

        if cancellation_requested:
            if state in _CANCEL_TERMINAL_STATES:
                raise TrainingJobTimeoutError(job_name, resource)
            if state in _TERMINAL_STATES:
                raise RuntimeError(
                    "timed-out Custom Job reached an unexpected terminal state: "
                    f"{state}"
                )
        elif state in _TERMINAL_STATES:
            return resource
        if (
            not cancellation_requested
            and monotonic() - started_at >= training_timeout_seconds
        ):
            backend.cancel(job_name)
            cancellation_requested = True
        sleep(poll_interval_seconds)


def _validate_config(config: TrainingCustomJobConfig) -> None:
    if not isinstance(config, TrainingCustomJobConfig):
        raise TypeError("config must be a TrainingCustomJobConfig")
    required_strings = {
        "project_id": config.project_id,
        "region": config.region,
        "run_id": config.run_id,
        "job_id": config.job_id,
        "snapshot_manifest_uri": config.snapshot_manifest_uri,
        "suite_version": config.suite_version,
        "run_root_uri": config.run_root_uri,
        "model_root_uri": config.model_root_uri,
        "training_service_account": config.training_service_account,
        "training_machine_type": config.training_machine_type,
    }
    missing = sorted(
        name
        for name, value in required_strings.items()
        if not isinstance(value, str) or not value.strip()
    )
    if missing:
        raise ValueError(f"training Custom Job fields are required: {missing}")
    for name, uri in (
        ("snapshot_manifest_uri", config.snapshot_manifest_uri),
        ("run_root_uri", config.run_root_uri),
        ("model_root_uri", config.model_root_uri),
    ):
        if not uri.startswith("gs://"):
            raise ValueError(f"{name} must be a gs:// URI")
    if _DIGEST_PATTERN.fullmatch(config.container_image_digest) is None:
        raise ValueError("container image digest must be sha256:<64 lowercase hex>")
    if not config.container_image_uri.endswith(
        f"@{config.container_image_digest}"
    ):
        raise ValueError(
            "container image URI must be digest-pinned with the exact digest"
        )
    if _COMMIT_PATTERN.fullmatch(config.source_git_commit) is None:
        raise ValueError("source_git_commit must be 40 lowercase hexadecimal characters")
    if (
        isinstance(config.training_timeout_seconds, bool)
        or not isinstance(config.training_timeout_seconds, int)
        or config.training_timeout_seconds <= 0
    ):
        raise ValueError("training_timeout_seconds must be a positive integer")


def _normalize_mapping(value: object, name: str) -> dict[str, Any]:
    normalized = _normalize_json(value)
    if not isinstance(normalized, dict):
        raise ValueError(f"{name} must normalize to a JSON object")
    return normalized


def _normalize_json(value: object) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_json(item)
            for key, item in value.items()
        }
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize_json(asdict(value))
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    to_dict = getattr(type(value), "to_dict", None)
    if callable(to_dict):
        try:
            return _normalize_json(
                to_dict(value, use_integers_for_enums=False)
            )
        except TypeError:
            return _normalize_json(to_dict(value))
    raise ValueError(
        f"value is not JSON-normalizable: {type(value).__name__}"
    )


def _state_name(value: object) -> str:
    if isinstance(value, str) and value:
        return value.rsplit(".", 1)[-1]
    enum_name = getattr(value, "name", None)
    if isinstance(enum_name, str) and enum_name:
        return enum_name
    raise ValueError("Custom Job resource must contain a named state")


def _label_value(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]", "-", value.lower())
    normalized = normalized.strip("-_")
    return normalized[:63] or "unknown"
