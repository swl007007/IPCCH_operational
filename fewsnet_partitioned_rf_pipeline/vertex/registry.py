"""Narrow Vertex Model Registry boundary for FEWSNET candidate versions."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
import hashlib
import json
import re
from typing import Any

from google.api_core.exceptions import NotFound
from google.cloud import aiplatform

from fewsnet_partitioned_rf_pipeline.config import PARENT_MODEL_IDS
from fewsnet_partitioned_rf_pipeline.core import RegisteredModelVersion
from fewsnet_partitioned_rf_pipeline.vertex.storage import (
    ArtifactStore,
    put_immutable_or_verify,
)


_ALIAS_INVALID_PATTERN = re.compile(r"[^a-z0-9-]")
_REPEATED_HYPHEN_PATTERN = re.compile(r"-+")
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_ALIAS_MAX_LENGTH = 128
_LABEL_VALUE_MAX_LENGTH = 63
_LABEL_HASH_LENGTH = 12
_RESERVED_LABEL_KEYS = ("horizon", "suite", "lifecycle")


def suite_version_alias(suite_version: str) -> str:
    """Project one immutable suite identity into a Vertex version alias."""
    if not isinstance(suite_version, str):
        raise ValueError("suite version alias source must be a string")
    alias = _ALIAS_INVALID_PATTERN.sub("-", suite_version.lower())
    alias = _REPEATED_HYPHEN_PATTERN.sub("-", alias).strip("-")
    if not alias:
        raise ValueError("suite version alias must not be empty")
    if not alias[0].isalpha():
        alias = f"v-{alias}"
    if len(alias) > _ALIAS_MAX_LENGTH:
        raise ValueError(
            "suite version alias must be at most "
            f"{_ALIAS_MAX_LENGTH} characters"
        )
    return alias


def resolve_parent_model(
    *,
    project_id: str,
    region: str,
    horizon_key: str,
    sdk: Any = aiplatform,
) -> str | None:
    """Return the deterministic stable parent resource, or None if absent."""
    parent_resource_name, registry = _resolve_parent_registry(
        project_id=project_id,
        region=region,
        horizon_key=horizon_key,
        sdk=sdk,
    )
    return parent_resource_name if registry is not None else None


def register_candidate_version(
    *,
    project_id: str,
    region: str,
    run_root_uri: str,
    suite_version: str,
    horizon_key: str,
    artifact_uri: str,
    image_uri: str,
    image_digest: str,
    source_git_commit: str,
    version_description: str,
    labels: Mapping[str, str],
    store: ArtifactStore,
    update_run_manifest: Callable[[RegisteredModelVersion], None],
    sdk: Any = aiplatform,
) -> RegisteredModelVersion:
    """Register or exactly reuse one immutable candidate Model Version."""
    _validate_registration_inputs(
        project_id=project_id,
        region=region,
        run_root_uri=run_root_uri,
        horizon_key=horizon_key,
        artifact_uri=artifact_uri,
        image_uri=image_uri,
        image_digest=image_digest,
        source_git_commit=source_git_commit,
        version_description=version_description,
        labels=labels,
        update_run_manifest=update_run_manifest,
    )
    suite_alias = suite_version_alias(suite_version)
    suite_label = _suite_label_value(suite_alias)
    candidate_labels = _candidate_labels(
        labels,
        horizon_key=horizon_key,
        suite_label=suite_label,
    )
    parent_resource_name, registry = _resolve_parent_registry(
        project_id=project_id,
        region=region,
        horizon_key=horizon_key,
        sdk=sdk,
    )

    existing_model = None
    if registry is not None:
        try:
            version_info = registry.get_version_info(suite_alias)
        except NotFound:
            pass
        else:
            if version_info.model_resource_name != parent_resource_name:
                raise ValueError(
                    "existing suite alias resolved to a different parent model"
                )
            version_aliases = getattr(version_info, "version_aliases", ())
            if "production" in (version_aliases or ()):
                raise ValueError(
                    "existing candidate must not have the production alias"
                )
            existing_model = sdk.Model(
                model_name=version_info.model_resource_name,
                version=str(version_info.version_id),
            )

    if existing_model is not None:
        _validate_existing_candidate(
            existing_model,
            artifact_uri=artifact_uri,
            image_uri=image_uri,
            image_digest=image_digest,
            source_git_commit=source_git_commit,
            horizon_key=horizon_key,
            suite_label=suite_label,
        )
        existing_labels = _model_labels(existing_model)
        registered = _registered_model_version(
            existing_model,
            horizon_key=horizon_key,
            suite_alias=suite_alias,
            artifact_uri=artifact_uri,
            expected_parent_resource_name=parent_resource_name,
        )
        if existing_labels["lifecycle"] == "abandoned":
            registry.update_version(
                version=registered.version_id,
                labels={**existing_labels, "lifecycle": "candidate"}
            )
    else:
        uploaded = sdk.Model.upload(
            display_name=PARENT_MODEL_IDS[horizon_key],
            artifact_uri=artifact_uri,
            serving_container_image_uri=image_uri,
            serving_container_predict_route="/predict",
            serving_container_health_route="/health",
            serving_container_ports=[8080],
            serving_container_environment_variables={
                "FEWSNET_CONTAINER_IMAGE_DIGEST": image_digest,
                "FEWSNET_SOURCE_GIT_COMMIT": source_git_commit,
            },
            labels=candidate_labels,
            parent_model=(
                parent_resource_name if registry is not None else None
            ),
            model_id=(
                None if registry is not None else PARENT_MODEL_IDS[horizon_key]
            ),
            is_default_version=registry is None,
            version_aliases=[suite_alias],
            version_description=version_description,
            sync=True,
        )
        registered = _registered_model_version(
            uploaded,
            horizon_key=horizon_key,
            suite_alias=suite_alias,
            artifact_uri=artifact_uri,
            expected_parent_resource_name=parent_resource_name,
        )

    evidence_uri = (
        f"{run_root_uri.rstrip('/')}/registry/{horizon_key}.json"
    )
    put_immutable_or_verify(
        store,
        evidence_uri,
        json.dumps(
            asdict(registered),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
    )
    update_run_manifest(registered)
    return registered


def mark_registered_versions_abandoned(
    versions: Sequence[RegisteredModelVersion],
    *,
    project_id: str,
    region: str,
    sdk: Any = aiplatform,
) -> None:
    """Retain candidate versions while merging an abandoned lifecycle label."""
    _required_string("project_id", project_id)
    _required_string("region", region)
    sdk.init(project=project_id, location=region)
    for version in versions:
        if not isinstance(version, RegisteredModelVersion):
            raise TypeError(
                "versions must contain RegisteredModelVersion instances"
            )
        model = sdk.Model(
            model_name=version.parent_model_resource_name,
            version=version.version_id,
        )
        _validate_loaded_model_identity(model, version)
        registry = sdk.ModelRegistry(version.parent_model_resource_name)
        registry.update_version(
            version=version.version_id,
            labels={**_model_labels(model), "lifecycle": "abandoned"}
        )


def _resolve_parent_registry(
    *,
    project_id: str,
    region: str,
    horizon_key: str,
    sdk: Any,
) -> tuple[str, object | None]:
    _required_string("project_id", project_id)
    _required_string("region", region)
    if horizon_key not in PARENT_MODEL_IDS:
        raise ValueError(f"unsupported horizon_key: {horizon_key}")
    sdk.init(project=project_id, location=region)
    parent_resource_name = (
        f"projects/{project_id}/locations/{region}/models/"
        f"{PARENT_MODEL_IDS[horizon_key]}"
    )
    registry = sdk.ModelRegistry(parent_resource_name)
    try:
        registry.list_versions()
    except NotFound:
        return parent_resource_name, None
    return parent_resource_name, registry


def _suite_label_value(suite_alias: str) -> str:
    if len(suite_alias) <= _LABEL_VALUE_MAX_LENGTH:
        return suite_alias
    suffix = hashlib.sha256(suite_alias.encode("utf-8")).hexdigest()[
        :_LABEL_HASH_LENGTH
    ]
    prefix_length = (
        _LABEL_VALUE_MAX_LENGTH - _LABEL_HASH_LENGTH - 1
    )
    prefix = suite_alias[:prefix_length].rstrip("-")
    return f"{prefix}-{suffix}"


def _candidate_labels(
    labels: Mapping[str, str],
    *,
    horizon_key: str,
    suite_label: str,
) -> dict[str, str]:
    candidate_identity = {
        "horizon": horizon_key,
        "suite": suite_label,
        "lifecycle": "candidate",
    }
    normalized = dict(labels)
    for key in _RESERVED_LABEL_KEYS:
        if key in normalized and normalized[key] != candidate_identity[key]:
            raise ValueError(
                f"{key} label cannot override the candidate identity"
            )
    normalized.update(candidate_identity)
    return normalized


def _validate_existing_candidate(
    model: object,
    *,
    artifact_uri: str,
    image_uri: str,
    image_digest: str,
    source_git_commit: str,
    horizon_key: str,
    suite_label: str,
) -> None:
    if getattr(model, "uri", None) != artifact_uri:
        raise ValueError("existing candidate artifact URI does not match")
    gca_resource = getattr(model, "gca_resource", None)
    container_spec = getattr(gca_resource, "container_spec", None)
    if getattr(container_spec, "image_uri", None) != image_uri:
        raise ValueError("existing candidate image URI does not match")
    environment = _container_environment(container_spec)
    if environment.get("FEWSNET_CONTAINER_IMAGE_DIGEST") != image_digest:
        raise ValueError("existing candidate image digest does not match")
    if environment.get("FEWSNET_SOURCE_GIT_COMMIT") != source_git_commit:
        raise ValueError("existing candidate source Git commit does not match")
    labels = _model_labels(model)
    if labels.get("horizon") != horizon_key:
        raise ValueError("existing candidate horizon label does not match")
    if labels.get("suite") != suite_label:
        raise ValueError("existing candidate suite label does not match")
    if labels.get("lifecycle") not in {"candidate", "abandoned"}:
        raise ValueError(
            "existing candidate lifecycle must be candidate or abandoned"
        )


def _container_environment(container_spec: object) -> dict[str, str]:
    environment: dict[str, str] = {}
    for item in getattr(container_spec, "env", ()):
        name = getattr(item, "name", None)
        value = getattr(item, "value", None)
        if isinstance(name, str) and isinstance(value, str):
            environment[name] = value
    return environment


def _model_labels(model: object) -> dict[str, str]:
    labels = getattr(model, "labels", None)
    if not isinstance(labels, Mapping):
        raise ValueError("Vertex Model labels must be a mapping")
    normalized = dict(labels)
    if not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in normalized.items()
    ):
        raise ValueError("Vertex Model labels must contain string pairs")
    return normalized


def _registered_model_version(
    model: object,
    *,
    horizon_key: str,
    suite_alias: str,
    artifact_uri: str,
    expected_parent_resource_name: str,
) -> RegisteredModelVersion:
    parent_resource_name = getattr(model, "resource_name", None)
    version_resource_name = getattr(model, "versioned_resource_name", None)
    version_id = str(getattr(model, "version_id", ""))
    if parent_resource_name != expected_parent_resource_name:
        raise ValueError("Vertex returned an unexpected parent model resource")
    if not version_id.isdigit():
        raise ValueError("Vertex returned a non-numeric model version ID")
    if version_resource_name != f"{parent_resource_name}@{version_id}":
        raise ValueError("Vertex returned an inconsistent version resource name")
    return RegisteredModelVersion(
        horizon_key=horizon_key,
        parent_model_resource_name=parent_resource_name,
        version_resource_name=version_resource_name,
        version_id=version_id,
        suite_version_alias=suite_alias,
        artifact_uri=artifact_uri,
    )


def _validate_loaded_model_identity(
    model: object,
    version: RegisteredModelVersion,
) -> None:
    if getattr(model, "resource_name", None) != (
        version.parent_model_resource_name
    ):
        raise ValueError("loaded model parent identity does not match")
    if str(getattr(model, "version_id", "")) != version.version_id:
        raise ValueError("loaded model version identity does not match")
    if getattr(model, "versioned_resource_name", None) != (
        version.version_resource_name
    ):
        raise ValueError("loaded model resource identity does not match")


def _validate_registration_inputs(
    *,
    project_id: str,
    region: str,
    run_root_uri: str,
    horizon_key: str,
    artifact_uri: str,
    image_uri: str,
    image_digest: str,
    source_git_commit: str,
    version_description: str,
    labels: Mapping[str, str],
    update_run_manifest: Callable[[RegisteredModelVersion], None],
) -> None:
    _required_string("project_id", project_id)
    _required_string("region", region)
    _required_string("run_root_uri", run_root_uri)
    _required_string("artifact_uri", artifact_uri)
    _required_string("image_uri", image_uri)
    _required_string("version_description", version_description)
    if horizon_key not in PARENT_MODEL_IDS:
        raise ValueError(f"unsupported horizon_key: {horizon_key}")
    if not run_root_uri.startswith("gs://"):
        raise ValueError("run_root_uri must be a gs:// URI")
    if not artifact_uri.startswith("gs://"):
        raise ValueError("artifact_uri must be a gs:// URI")
    if _DIGEST_PATTERN.fullmatch(image_digest) is None:
        raise ValueError("image_digest must be sha256:<64 lowercase hex>")
    if not image_uri.endswith(f"@{image_digest}"):
        raise ValueError("image_uri must be pinned to the exact image_digest")
    if _COMMIT_PATTERN.fullmatch(source_git_commit) is None:
        raise ValueError(
            "source_git_commit must be 40 lowercase hexadecimal characters"
        )
    if not isinstance(labels, Mapping):
        raise TypeError("labels must be a mapping")
    if not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in labels.items()
    ):
        raise ValueError("labels must contain string pairs")
    if not callable(update_run_manifest):
        raise TypeError("update_run_manifest must be callable")


def _required_string(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value
