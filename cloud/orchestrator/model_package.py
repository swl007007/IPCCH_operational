from __future__ import annotations

from typing import Any, Mapping

from cloud.common.object_refs import has_immutable_reference


REQUIRED_MODEL_PACKAGE_MANIFEST_FIELDS = (
    "schema_version",
    "model_package_id",
    "model_version",
    "created_at_utc",
    "source_git_commit",
    "weights_files",
    "weights_checksums",
    "inference_entrypoint",
    "inference_code_version",
    "dependency_manifest",
    "expected_input_schema",
    "expected_output_schema",
    "local_validation_status",
    "local_validation_artifact_reference",
    "status",
)


class ModelPackageValidationError(ValueError):
    """Raised when an immutable model package contract is not satisfied."""


def validate_model_package(
    package: Mapping[str, Any],
    *,
    expected_input_schema: str,
    expected_output_schema: str,
    base_input_columns: list[str] | None = None,
) -> dict:
    if not package.get("uri"):
        raise ModelPackageValidationError("model package URI is required")
    if not has_immutable_reference(package):
        raise ModelPackageValidationError(
            "model package requires an immutable reference"
        )
    manifest = package.get("manifest")
    if not isinstance(manifest, Mapping):
        raise ModelPackageValidationError("model package manifest is required")
    _validate_required_manifest_fields(manifest)
    if manifest.get("expected_input_schema") != expected_input_schema:
        raise ModelPackageValidationError(
            "model package expected_input_schema mismatch"
        )
    if manifest.get("expected_output_schema") != expected_output_schema:
        raise ModelPackageValidationError(
            "model package expected_output_schema mismatch"
        )
    model_package_id = str(manifest.get("model_package_id") or "").strip()
    if not model_package_id:
        raise ModelPackageValidationError(
            "model package manifest model_package_id is required"
        )
    required_feature_columns = list(package.get("required_feature_columns") or [])
    if base_input_columns is not None and required_feature_columns:
        missing = sorted(set(required_feature_columns) - set(base_input_columns))
        if missing:
            raise ModelPackageValidationError(
                f"base input missing model feature columns: {missing}"
            )
    return {
        "status": "passed",
        "model_package_uri": package["uri"],
        "model_package_id": model_package_id,
        "expected_input_schema": expected_input_schema,
        "expected_output_schema": expected_output_schema,
        "required_feature_columns": required_feature_columns,
        "immutable_reference": {
            key: package[key]
            for key in (
                "checksum",
                "checksum_algorithm",
                "generation",
                "version_id",
                "model_version",
            )
            if key in package
        },
    }


def _validate_required_manifest_fields(manifest: Mapping[str, Any]) -> None:
    for field in REQUIRED_MODEL_PACKAGE_MANIFEST_FIELDS:
        if field not in manifest:
            raise ModelPackageValidationError(
                f"model package manifest {field} is required"
            )
        value = manifest[field]
        if isinstance(value, str):
            if not value.strip():
                raise ModelPackageValidationError(
                    f"model package manifest {field} is required"
                )
        elif isinstance(value, (list, tuple, set, dict)):
            if not value:
                raise ModelPackageValidationError(
                    f"model package manifest {field} is required"
                )
        elif value is None:
            raise ModelPackageValidationError(
                f"model package manifest {field} is required"
            )
