from __future__ import annotations

from dataclasses import dataclass, field
import re

from cloud.common.object_refs import is_digest_pinned_image
from cloud.common.runtime_config import RuntimeDefaults


class VertexJobConfigError(ValueError):
    """Raised when Vertex AI custom-job configuration violates the v1 contract."""


@dataclass(frozen=True)
class VertexJobConfig:
    project_id: str
    region: str
    job_id: str
    image_uri: str
    image_digest: str
    service_account: str
    staging_root_uri: str
    output_root_uri: str
    args: list[str]
    runtime: RuntimeDefaults = field(default_factory=RuntimeDefaults)


def build_vertex_custom_job_spec(config: VertexJobConfig) -> dict:
    if not is_digest_pinned_image(config.image_uri):
        raise VertexJobConfigError(
            "Vertex AI custom job image must be pinned by digest"
        )
    uri_digest = config.image_uri.rsplit("@", 1)[1]
    if uri_digest != config.image_digest:
        raise VertexJobConfigError(
            "Vertex AI custom job must use the same image digest"
        )
    if not config.service_account:
        raise VertexJobConfigError("Vertex AI custom job service account is required")
    env = _build_vertex_environment(config)
    return {
        "display_name": config.job_id,
        "job_spec": {
            "worker_pool_specs": [
                {
                    "replica_count": 1,
                    "machine_spec": {"machine_type": "n1-standard-4"},
                    "container_spec": {
                        "image_uri": config.image_uri,
                        "command": ["python3", "-m", "cloud.orchestrator.inference"],
                        "args": list(config.args),
                        "env": env,
                    },
                }
            ],
            "service_account": config.service_account,
            "base_output_directory": {"output_uri_prefix": config.output_root_uri},
            "scheduling": {
                "timeout": f"{config.runtime.vertex_ai_custom_job_timeout_seconds}s",
            },
        },
        "labels": {
            "inference_mode": "vertex_ai_custom_job",
            "ipcch_region": config.region.lower().replace("_", "-")[:63],
            "ipcch_project": config.project_id.lower().replace("_", "-")[:63],
        },
    }


def submit_vertex_custom_job(config: VertexJobConfig, *, client, parent: str):
    return client.create_custom_job(
        {
            "parent": parent,
            "custom_job": build_vertex_custom_job_spec(config),
        }
    )


def _build_vertex_environment(config: VertexJobConfig) -> list[dict[str, str]]:
    feature_month = _arg_value(config.args, "--feature-month")
    run_id = _arg_value(config.args, "--run-id")
    model_package_uri = _arg_value(config.args, "--model-package-uri")
    input_base_uri = _arg_value(config.args, "--input-base-uri")
    output_uri = _arg_value(config.args, "--output-dir") or config.output_root_uri
    return [
        {"name": "PROJECT_ID", "value": config.project_id},
        {"name": "VERTEX_AI_REGION", "value": config.region},
        {"name": "RUN_ID", "value": run_id or _run_id_from_job_id(config.job_id)},
        {"name": "FEATURE_MONTH", "value": feature_month or ""},
        {"name": "MODEL_PACKAGE_URI", "value": model_package_uri or ""},
        {"name": "INPUT_BASE_URI", "value": input_base_uri or ""},
        {"name": "INFERENCE_OUTPUT_URI", "value": output_uri},
        {"name": "IPCCH_VERTEX_OUTPUT_ROOT_URI", "value": config.output_root_uri},
    ]


def _arg_value(args: list[str], name: str) -> str | None:
    try:
        return args[args.index(name) + 1]
    except (ValueError, IndexError):
        return None


def _run_id_from_job_id(job_id: str) -> str:
    return re.sub(r"^ipcch-", "", job_id, count=1)
