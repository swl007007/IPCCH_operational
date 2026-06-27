from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re

from cloud.common.object_refs import is_digest_pinned_image
from cloud.common.runtime_config import RuntimeDefaults


class BatchJobConfigError(ValueError):
    """Raised when the Cloud Batch job configuration violates the v1 contract."""


@dataclass(frozen=True)
class BatchJobConfig:
    job_name_prefix: str
    image_uri: str
    service_account: str
    run_id: str
    feature_month: str
    worker_args: list[str]
    runtime: RuntimeDefaults = field(default_factory=RuntimeDefaults)


def build_batch_job_spec(config: BatchJobConfig) -> dict:
    if not is_digest_pinned_image(config.image_uri):
        raise BatchJobConfigError("Cloud Batch worker image must be pinned by digest")
    if not config.service_account:
        raise BatchJobConfigError("Cloud Batch service account is required")
    return {
        "task_groups": [
            {
                "task_spec": {
                    "runnables": [
                        {
                            "container": {
                                "image_uri": config.image_uri,
                                "entrypoint": "python3",
                                "commands": [
                                    "-m",
                                    "cloud.batch.evi_worker",
                                    *config.worker_args,
                                ],
                            }
                        }
                    ],
                    "max_run_duration": f"{config.runtime.batch_job_timeout_seconds}s",
                    "max_retry_count": config.runtime.max_retries,
                },
                "task_count": 1,
                "parallelism": 1,
            }
        ],
        "allocation_policy": {
            "service_account": {"email": config.service_account},
        },
        "logs_policy": {"destination": "CLOUD_LOGGING"},
        "labels": {
            "ipcch_feature_month": config.feature_month.replace("-", ""),
            "ipcch_run_id": _sanitize_label_value(config.run_id),
        },
    }


def build_batch_job_id(config: BatchJobConfig) -> str:
    prefix = _bounded_job_prefix(_sanitize_job_id_part(config.job_name_prefix))
    run_part = _sanitize_job_id_part(config.run_id) or "run"
    job_id = f"{prefix}-{run_part}"
    if len(job_id) <= 63:
        return job_id
    digest = hashlib.sha1(config.run_id.encode("utf-8")).hexdigest()[:8]
    available = 63 - len(prefix) - len(digest) - 2
    return f"{prefix}-{run_part[:available].rstrip('-')}-{digest}"


def build_batch_create_job_request(config: BatchJobConfig, *, parent: str) -> dict:
    return {
        "parent": parent,
        "job_id": build_batch_job_id(config),
        "job": build_batch_job_spec(config),
    }


def submit_batch_job(config: BatchJobConfig, *, client, parent: str):
    return client.create_job(build_batch_create_job_request(config, parent=parent))


def _sanitize_job_id_part(value: str) -> str:
    sanitized = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    sanitized = re.sub(r"-+", "-", sanitized)
    if sanitized and not sanitized[0].isalpha():
        sanitized = "x-" + sanitized
    return sanitized


def _sanitize_label_value(value: str) -> str:
    sanitized = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    sanitized = re.sub(r"-+", "-", sanitized)
    return sanitized[:63]


def _bounded_job_prefix(prefix: str) -> str:
    prefix = prefix or "ipcch-evi"
    max_prefix_length = 63 - 1 - 8 - 1
    return prefix[:max_prefix_length].rstrip("-") or "ipcch-evi"
