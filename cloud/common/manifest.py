from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from cloud.common.object_refs import has_immutable_reference, is_digest_pinned_image


_LOCAL_PATH_RE = re.compile(r"^(?:[A-Za-z]:\\|/mnt/[a-z]/|/home/|/Users/|\\\\)")
_CLOUD_OR_INTERNAL_URI_RE = re.compile(
    r"^(gs://|projects/|MODIS/|ee://|container://|/app/)"
)
REQUIRED_V1_ARTIFACT_TYPES = frozenset(
    {
        "scaffold",
        "fixed_slow_area_features",
        "source_panel",
        "gee_evi_export_config",
        "geometry",
        "docker_image",
        "model_package",
        "vertex_ai_inference_config",
        "schema_contract",
        "validator",
    }
)


class ManifestValidationError(ValueError):
    """Raised when an input manifest fails schema or hard-gate validation."""


def load_manifest(
    path: str | Path,
    *,
    feature_month: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_manifest(data, feature_month=feature_month, run_id=run_id)


def validate_manifest(
    data: Mapping[str, Any],
    *,
    feature_month: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    manifest = dict(data)
    _validate_schema(manifest)
    _validate_execution_params(manifest, feature_month=feature_month, run_id=run_id)
    _validate_deployment(manifest["deployment"])
    _validate_artifacts(manifest.get("artifacts", []), manifest.get("waivers", []))
    _validate_model_package_deployment_reference(manifest)
    return manifest


def _validate_schema(data: Mapping[str, Any]) -> None:
    with (
        resources.files("cloud.schemas")
        .joinpath("input-manifest.schema.json")
        .open(encoding="utf-8") as handle
    ):
        schema = json.load(handle)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda exc: list(exc.path))
    if errors:
        raise ManifestValidationError(_format_schema_error(errors[0]))


def _format_schema_error(error: ValidationError) -> str:
    path = ".".join(str(part) for part in error.absolute_path) or "<root>"
    return f"manifest schema error at {path}: {error.message}"


def _validate_execution_params(
    manifest: Mapping[str, Any],
    *,
    feature_month: str | None,
    run_id: str | None,
) -> None:
    if feature_month is not None and manifest.get("feature_month") != feature_month:
        raise ManifestValidationError(
            "manifest feature_month must match execution parameter"
        )
    if run_id is not None and manifest.get("run_id") != run_id:
        raise ManifestValidationError("manifest run_id must match execution parameter")


def _validate_deployment(deployment: Mapping[str, Any]) -> None:
    if deployment.get("provider") != "gcp":
        raise ManifestValidationError("manifest provider must be gcp")
    if deployment.get("permission_model") != "split_least_privilege":
        raise ManifestValidationError(
            "deployment must use split least privilege service accounts"
        )

    image_uri = deployment.get("artifact_registry_image_uri", "")
    vertex_image_uri = deployment.get("vertex_ai_custom_job_container_image_uri", "")
    if not is_digest_pinned_image(image_uri) or not is_digest_pinned_image(
        vertex_image_uri
    ):
        raise ManifestValidationError(
            "runtime image references must be pinned by digest"
        )

    digest = deployment.get("vertex_ai_custom_job_container_digest", "")
    if not re.fullmatch(r"sha256:[A-Fa-f0-9]{64}", digest or ""):
        raise ManifestValidationError("vertex custom job image digest is required")
    image_digest = _image_uri_digest(image_uri)
    vertex_image_digest = _image_uri_digest(vertex_image_uri)
    if len({image_digest, vertex_image_digest, digest}) != 1:
        raise ManifestValidationError(
            "single-image runtime digest must match across Batch and Vertex"
        )

    service_accounts = [
        deployment.get("cloud_run_service_account"),
        deployment.get("cloud_batch_service_account"),
        deployment.get("vertex_ai_custom_job_service_account"),
    ]
    if (
        any(not account for account in service_accounts)
        or len(set(service_accounts)) != 3
    ):
        raise ManifestValidationError(
            "deployment must use split least privilege service accounts"
        )

    for key, value in deployment.items():
        if key.endswith("_uri") and isinstance(value, str):
            if key.endswith("image_uri"):
                continue
            _validate_runtime_uri(value, field_name=f"deployment.{key}")


def _validate_artifacts(
    artifacts: list[Mapping[str, Any]], waivers: list[Mapping[str, Any]]
) -> None:
    _validate_required_artifact_types(artifacts)
    waived_artifact_ids = {waiver.get("artifact_id") for waiver in waivers}
    for artifact in artifacts:
        uri = artifact.get("uri")
        if isinstance(uri, str):
            _validate_runtime_uri(
                uri, field_name=f"artifact {artifact.get('artifact_id')} uri"
            )
        if (
            artifact.get("required")
            and artifact.get("artifact_id") not in waived_artifact_ids
        ):
            if not has_immutable_reference(artifact):
                raise ManifestValidationError(
                    f"required artifact {artifact.get('artifact_id')} lacks immutable reference"
                )


def _validate_required_artifact_types(artifacts: list[Mapping[str, Any]]) -> None:
    by_type: dict[str, list[Mapping[str, Any]]] = {}
    for artifact in artifacts:
        artifact_type = artifact.get("artifact_type")
        if isinstance(artifact_type, str):
            by_type.setdefault(artifact_type, []).append(artifact)

    for artifact_type in sorted(REQUIRED_V1_ARTIFACT_TYPES):
        matches = by_type.get(artifact_type, [])
        if len(matches) != 1:
            raise ManifestValidationError(
                f"required artifact type {artifact_type} must appear exactly once"
            )
        if matches[0].get("required") is not True:
            raise ManifestValidationError(
                f"required artifact type {artifact_type} must be marked required"
            )


def _validate_model_package_deployment_reference(manifest: Mapping[str, Any]) -> None:
    deployment = manifest["deployment"]
    model_artifacts = [
        artifact
        for artifact in manifest.get("artifacts", [])
        if artifact.get("artifact_type") == "model_package"
    ]
    if not model_artifacts:
        raise ManifestValidationError("model package artifact is required")
    if len(model_artifacts) != 1:
        raise ManifestValidationError("exactly one model package artifact is required")
    model_artifact = model_artifacts[0]
    deployment_uri = deployment.get("vertex_ai_model_package_uri")
    artifact_uri = model_artifact.get("uri")
    if _strip_trailing_slash(deployment_uri) != _strip_trailing_slash(artifact_uri):
        raise ManifestValidationError(
            "deployment model package URI must match model package artifact URI"
        )
    deployment_ref = str(
        deployment.get("vertex_ai_model_package_checksum_or_version") or ""
    )
    artifact_refs = _model_package_immutable_refs(model_artifact)
    if deployment_ref and deployment_ref not in artifact_refs:
        raise ManifestValidationError(
            "deployment model package checksum/version must match model package artifact"
        )


def _validate_runtime_uri(value: str, *, field_name: str) -> None:
    if _LOCAL_PATH_RE.match(value):
        raise ManifestValidationError(
            f"{field_name} must not use a local workstation path"
        )
    if value.startswith("gs://") or _CLOUD_OR_INTERNAL_URI_RE.match(value):
        return
    if value.startswith("http://") or value.startswith("https://"):
        raise ManifestValidationError(f"{field_name} must use a declared cloud URI")
    raise ManifestValidationError(f"{field_name} must use a declared cloud URI")


def _image_uri_digest(value: str) -> str:
    return value.rsplit("@", 1)[1]


def _strip_trailing_slash(value: Any) -> str:
    return str(value or "").rstrip("/")


def _model_package_immutable_refs(artifact: Mapping[str, Any]) -> set[str]:
    refs = set()
    for key in ("checksum", "generation", "version_id", "model_version"):
        value = artifact.get(key)
        if value:
            text = str(value)
            refs.add(text)
            refs.add(f"{key}:{text}")
    return refs
