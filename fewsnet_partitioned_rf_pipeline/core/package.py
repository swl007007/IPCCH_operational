"""Deterministic writing and defensive loading for FEWSNET model packages."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import replace
from numbers import Integral
from pathlib import Path

import joblib

from fewsnet_partitioned_rf_pipeline.config import (
    PARTITION_ASSET_PATH,
    PARTITION_ASSET_SHA256,
)
from fewsnet_partitioned_rf_pipeline.core.inference import PartitionedRFPredictor
from fewsnet_partitioned_rf_pipeline.core.partitions import PartitionMap
from fewsnet_partitioned_rf_pipeline.core.preprocessing import (
    load_feature_contract,
    write_feature_contract,
)
from fewsnet_partitioned_rf_pipeline.core.validation import (
    CLUSTER_STATE_FIELDS,
    SMOTE_RESULT_FIELDS,
    PackageValidationError,
    assert_runtime_compatible,
    runtime_dependency_versions,
    validate_container_image_identity,
    validate_horizon_training_report,
    validate_sha256,
    validate_threshold_report,
)
from fewsnet_partitioned_rf_pipeline.schemas import validate_payload


PACKAGE_FILES = (
    "model.joblib",
    "model_manifest.json",
    "feature_contract.json",
    "partition_map.csv",
    "threshold_report.json",
    "training_report.json",
    "checksums.json",
)
CONTENT_FILES = tuple(
    filename for filename in PACKAGE_FILES if filename != "checksums.json"
)
METADATA_FIELDS = {
    "suite_version",
    "snapshot_id",
    "snapshot_content_sha256",
    "target_month",
    "source_git_commit",
    "container_image_uri",
    "container_image_digest",
    "status",
}
REPORT_FIELDS = {"training_report", "threshold_report"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Mapping) -> None:
    path.write_text(
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _read_json_object(path: Path, name: str) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackageValidationError(f"{name} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise PackageValidationError(f"{name} must contain a JSON object")
    return payload


def _mapping(value: object, name: str) -> dict:
    if not isinstance(value, Mapping):
        raise PackageValidationError(f"{name} must be an object")
    return dict(value)


def _integer_keyed_mapping(value: object, name: str) -> dict[int, object]:
    mapping = _mapping(value, name)
    normalized: dict[int, object] = {}
    for cluster_id, item in mapping.items():
        if isinstance(cluster_id, bool) or not isinstance(cluster_id, Integral):
            raise PackageValidationError(f"{name} cluster IDs must be integers")
        normalized_cluster_id = int(cluster_id)
        if normalized_cluster_id in normalized:
            raise PackageValidationError(
                f"{name} contains duplicate cluster ID {normalized_cluster_id}"
            )
        normalized[normalized_cluster_id] = item
    return normalized


def _exact_fields(value: Mapping, expected: set[str], name: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise PackageValidationError(
            f"{name} fields differ; missing={missing}, extra={extra}"
        )


def _approved_partition_map() -> PartitionMap:
    try:
        return PartitionMap.load(PARTITION_ASSET_PATH, PARTITION_ASSET_SHA256)
    except (OSError, ValueError) as exc:
        raise PackageValidationError(
            f"approved partition asset failed validation: {exc}"
        ) from exc


def _validate_predictor_partition(
    predictor: PartitionedRFPredictor,
    approved_partition: PartitionMap,
) -> None:
    if predictor.partition_map != dict(approved_partition._clusters_by_admin):
        raise PackageValidationError(
            "predictor partition_map does not match the approved fixed partition"
        )


def _validate_predictor_reports(
    predictor: PartitionedRFPredictor,
    training_report: Mapping,
) -> None:
    expected_cluster_ids = {
        int(cluster_id) for cluster_id in training_report["cluster_states"]
    }
    partition_status = _integer_keyed_mapping(
        predictor.partition_status,
        "predictor.partition_status",
    )
    for cluster_id, status in partition_status.items():
        if not isinstance(status, str):
            raise PackageValidationError(
                f"predictor.partition_status.{cluster_id} must be a string"
            )
    expected_status = {
        int(cluster_id): state["status"]
        for cluster_id, state in training_report["cluster_states"].items()
    }
    if (
        set(partition_status) != expected_cluster_ids
        or partition_status != expected_status
    ):
        raise PackageValidationError(
            "predictor partition_status does not match training_report.json"
        )

    partition_models = _integer_keyed_mapping(
        predictor.partition_models,
        "predictor.partition_models",
    )
    if set(partition_models) != expected_cluster_ids:
        raise PackageValidationError(
            "predictor partition_models cluster IDs do not match training_report.json"
        )
    for cluster_id, status in expected_status.items():
        has_partition_model = partition_models[cluster_id] is not None
        if has_partition_model != (status == "partition_model"):
            raise PackageValidationError(
                "predictor partition_models model presence does not match "
                f"training_report.json for cluster {cluster_id}"
            )

    partition_metadata = _integer_keyed_mapping(
        predictor.partition_metadata,
        "predictor.partition_metadata",
    )
    if set(partition_metadata) != expected_cluster_ids:
        raise PackageValidationError(
            "predictor partition_metadata cluster IDs do not match training_report.json"
        )

    smote_metadata_fields = {
        "status": "smote_status",
        "original_class_counts": "original_class_counts",
        "resampled_class_counts": "resampled_class_counts",
        "failure_reason": "smote_failure_reason",
    }
    projected_cluster_states: dict[str, dict] = {}
    projected_smote_results: dict[str, dict] = {}
    for cluster_id in sorted(expected_cluster_ids):
        metadata = _mapping(
            partition_metadata[cluster_id],
            f"predictor.partition_metadata.{cluster_id}",
        )
        required_fields = CLUSTER_STATE_FIELDS | set(smote_metadata_fields.values())
        missing = sorted(required_fields - set(metadata))
        if missing:
            raise PackageValidationError(
                "predictor partition_metadata fields differ; "
                f"cluster={cluster_id}, missing={missing}"
            )
        projected_cluster_states[str(cluster_id)] = {
            field: metadata[field] for field in CLUSTER_STATE_FIELDS
        }
        projected_smote_results[str(cluster_id)] = {
            field: metadata[smote_metadata_fields[field]]
            for field in SMOTE_RESULT_FIELDS
        }

    projected_report = dict(training_report)
    projected_report["cluster_states"] = projected_cluster_states
    try:
        validate_horizon_training_report(projected_report)
    except PackageValidationError as exc:
        detail = str(exc).replace(
            "training_report.cluster_states.",
            "predictor.partition_metadata.",
        )
        raise PackageValidationError(
            f"predictor partition_metadata cluster_states failed validation: {detail}"
        ) from exc
    if projected_cluster_states != training_report["cluster_states"]:
        raise PackageValidationError(
            "predictor partition_metadata cluster_states do not match training_report.json"
        )

    projected_report["smote_results"] = projected_smote_results
    try:
        validate_horizon_training_report(projected_report)
    except PackageValidationError as exc:
        detail = str(exc).replace(
            "training_report.smote_results.",
            "predictor.partition_metadata.",
        )
        detail = detail.replace(".status", ".smote_status")
        detail = detail.replace(".failure_reason", ".smote_failure_reason")
        raise PackageValidationError(
            f"predictor partition_metadata smote_results failed validation: {detail}"
        ) from exc
    if projected_smote_results != training_report["smote_results"]:
        raise PackageValidationError(
            "predictor partition_metadata smote_results do not match training_report.json"
        )


def _validated_reports(
    predictor: PartitionedRFPredictor,
    reports: object,
) -> tuple[dict, dict]:
    report_mapping = _mapping(reports, "reports")
    _exact_fields(report_mapping, REPORT_FIELDS, "reports")
    training_report = validate_horizon_training_report(
        report_mapping["training_report"]
    )
    threshold_report = validate_threshold_report(
        report_mapping["threshold_report"]
    )
    if training_report["horizon_key"] != predictor.horizon_key:
        raise PackageValidationError(
            "training_report horizon_key does not match predictor"
        )
    if int(training_report["horizon_months"]) != predictor.horizon_months:
        raise PackageValidationError(
            "training_report horizon_months does not match predictor"
        )
    if (
        training_report["feature_schema_sha256"]
        != predictor.feature_contract.feature_schema_sha256
    ):
        raise PackageValidationError(
            "training_report feature schema does not match predictor"
        )
    if training_report["partition_asset_sha256"] != PARTITION_ASSET_SHA256:
        raise PackageValidationError(
            "training_report partition identity does not match approved asset"
        )
    if float(threshold_report["threshold"]) != float(predictor.threshold):
        raise PackageValidationError(
            "threshold_report threshold does not match predictor"
        )
    return training_report, threshold_report


def _manifest(
    predictor: PartitionedRFPredictor,
    metadata_value: object,
    training_report: dict,
) -> dict:
    metadata = _mapping(metadata_value, "metadata")
    _exact_fields(metadata, METADATA_FIELDS, "metadata")
    validate_container_image_identity(
        metadata["container_image_uri"],
        metadata["container_image_digest"],
    )
    manifest = {
        "schema_version": "fewsnet-model-package-v1",
        "suite_version": metadata["suite_version"],
        "snapshot_id": metadata["snapshot_id"],
        "snapshot_content_sha256": metadata["snapshot_content_sha256"],
        "horizon_key": predictor.horizon_key,
        "horizon_months": predictor.horizon_months,
        "target_month": metadata["target_month"],
        "feature_schema_sha256": predictor.feature_contract.feature_schema_sha256,
        "partition_sha256": PARTITION_ASSET_SHA256,
        "threshold": float(predictor.threshold),
        "dependency_versions": runtime_dependency_versions(),
        "source_git_commit": metadata["source_git_commit"],
        "container_image_uri": metadata["container_image_uri"],
        "container_image_digest": metadata["container_image_digest"],
        "training_target_month_range": dict(
            training_report["training_target_month_range"]
        ),
        "validation_target_month_range": dict(
            training_report["validation_target_month_range"]
        ),
        "files": list(PACKAGE_FILES),
        "status": metadata["status"],
    }
    try:
        validate_payload("model-package", manifest)
    except ValueError as exc:
        raise PackageValidationError(str(exc)) from exc
    return manifest


def write_model_package(
    output_dir: str | Path,
    predictor: PartitionedRFPredictor,
    metadata: object,
    reports: object,
) -> dict:
    """Write one exact seven-file, checksum-bound model package."""
    if not isinstance(predictor, PartitionedRFPredictor):
        raise TypeError("predictor must be a PartitionedRFPredictor")
    approved_partition = _approved_partition_map()
    _validate_predictor_partition(predictor, approved_partition)
    training_report, threshold_report = _validated_reports(predictor, reports)
    _validate_predictor_reports(predictor, training_report)
    manifest = _manifest(predictor, metadata, training_report)

    suite_version = str(manifest["suite_version"])
    if predictor.suite_version and predictor.suite_version != suite_version:
        raise PackageValidationError(
            "predictor suite_version does not match package metadata"
        )
    serialized_predictor = predictor
    if not predictor.suite_version:
        serialized_predictor = replace(predictor, suite_version=suite_version)

    package_dir = Path(output_dir)
    if package_dir.exists() and not package_dir.is_dir():
        raise PackageValidationError("output_dir must be a directory")
    if package_dir.exists() and any(package_dir.iterdir()):
        raise PackageValidationError("output_dir must be empty")
    package_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(
        serialized_predictor,
        package_dir / "model.joblib",
        compress=3,
        protocol=5,
    )
    try:
        write_feature_contract(
            serialized_predictor.feature_contract,
            package_dir / "feature_contract.json",
        )
    except ValueError as exc:
        raise PackageValidationError(f"feature contract failed validation: {exc}") from exc
    (package_dir / "partition_map.csv").write_bytes(PARTITION_ASSET_PATH.read_bytes())
    _write_json(package_dir / "threshold_report.json", threshold_report)
    _write_json(package_dir / "training_report.json", training_report)
    _write_json(package_dir / "model_manifest.json", manifest)

    checksums = {
        filename: _sha256(package_dir / filename)
        for filename in sorted(CONTENT_FILES)
    }
    _write_json(package_dir / "checksums.json", checksums)
    return manifest


def _require_package_files(package_dir: Path) -> None:
    if not package_dir.is_dir():
        raise PackageValidationError("package_dir must be an existing directory")
    actual = {path.name for path in package_dir.iterdir()}
    expected = set(PACKAGE_FILES)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise PackageValidationError(
            f"package files differ; missing={missing}, extra={extra}"
        )
    for filename in PACKAGE_FILES:
        member = package_dir / filename
        if member.is_symlink() or not member.is_file():
            raise PackageValidationError(
                f"{filename} must be a regular non-symlink file"
            )


def _verify_checksums(package_dir: Path) -> dict[str, str]:
    checksums = _read_json_object(package_dir / "checksums.json", "checksums.json")
    _exact_fields(checksums, set(CONTENT_FILES), "checksums.json")
    for filename in CONTENT_FILES:
        expected = validate_sha256(
            checksums[filename],
            f"checksums.json.{filename}",
        )
        observed = _sha256(package_dir / filename)
        if observed != expected:
            raise PackageValidationError(
                f"checksum mismatch for {filename}: expected {expected}, observed {observed}"
            )
    return {name: str(value) for name, value in checksums.items()}


def _validate_manifest_and_reports(
    package_dir: Path,
) -> tuple[dict, dict, dict, PartitionMap]:
    manifest = _read_json_object(
        package_dir / "model_manifest.json",
        "model_manifest.json",
    )
    try:
        validate_payload("model-package", manifest)
    except ValueError as exc:
        raise PackageValidationError(str(exc)) from exc
    if set(manifest["files"]) != set(PACKAGE_FILES):
        raise PackageValidationError(
            "model manifest files must list the exact seven package files"
        )
    validate_container_image_identity(
        manifest["container_image_uri"],
        manifest["container_image_digest"],
    )

    try:
        feature_contract = load_feature_contract(package_dir / "feature_contract.json")
    except (OSError, ValueError) as exc:
        raise PackageValidationError(f"feature contract failed validation: {exc}") from exc
    if feature_contract.feature_schema_sha256 != manifest["feature_schema_sha256"]:
        raise PackageValidationError(
            "feature_schema_sha256 does not match feature_contract.json"
        )

    partition_sha256 = _sha256(package_dir / "partition_map.csv")
    if partition_sha256 != manifest["partition_sha256"]:
        raise PackageValidationError(
            "partition_sha256 does not match partition_map.csv"
        )
    if partition_sha256 != PARTITION_ASSET_SHA256:
        raise PackageValidationError(
            "partition_sha256 does not match the approved fixed partition"
        )
    try:
        partition_map = PartitionMap.load(
            package_dir / "partition_map.csv",
            manifest["partition_sha256"],
        )
    except (OSError, ValueError) as exc:
        raise PackageValidationError(f"partition map failed validation: {exc}") from exc

    training_report = validate_horizon_training_report(
        _read_json_object(package_dir / "training_report.json", "training_report.json")
    )
    threshold_report = validate_threshold_report(
        _read_json_object(
            package_dir / "threshold_report.json",
            "threshold_report.json",
        )
    )
    for range_name in (
        "training_target_month_range",
        "validation_target_month_range",
    ):
        if manifest[range_name] != training_report[range_name]:
            raise PackageValidationError(
                f"manifest {range_name} does not match training_report.json"
            )
    if training_report["horizon_key"] != manifest["horizon_key"]:
        raise PackageValidationError(
            "training_report horizon_key does not match model manifest"
        )
    if int(training_report["horizon_months"]) != manifest["horizon_months"]:
        raise PackageValidationError(
            "training_report horizon_months does not match model manifest"
        )
    if training_report["feature_schema_sha256"] != manifest["feature_schema_sha256"]:
        raise PackageValidationError(
            "training_report feature identity does not match model manifest"
        )
    if training_report["partition_asset_sha256"] != manifest["partition_sha256"]:
        raise PackageValidationError(
            "training_report partition identity does not match model manifest"
        )
    if float(threshold_report["threshold"]) != float(manifest["threshold"]):
        raise PackageValidationError(
            "threshold_report threshold does not match model manifest"
        )
    return manifest, training_report, threshold_report, partition_map


def load_model_package(
    package_dir: str | Path,
    expected_image_digest: str | None = None,
    expected_source_git_commit: str | None = None,
) -> PartitionedRFPredictor:
    """Validate a package completely before unpickling its predictor."""
    package_path = Path(package_dir)
    _require_package_files(package_path)
    _verify_checksums(package_path)
    manifest, training_report, _, partition_map = _validate_manifest_and_reports(
        package_path
    )

    if (
        expected_image_digest is not None
        and manifest["container_image_digest"] != expected_image_digest
    ):
        raise PackageValidationError(
            "package image digest does not match expected image digest"
        )
    if (
        expected_source_git_commit is not None
        and manifest["source_git_commit"] != expected_source_git_commit
    ):
        raise PackageValidationError(
            "package source Git commit does not match expected source Git commit"
        )

    assert_runtime_compatible(manifest["dependency_versions"])
    try:
        predictor = joblib.load(package_path / "model.joblib")
    except Exception as exc:
        raise PackageValidationError(f"model.joblib could not be loaded: {exc}") from exc
    if not isinstance(predictor, PartitionedRFPredictor):
        raise PackageValidationError(
            "model.joblib must contain a PartitionedRFPredictor"
        )
    if predictor.horizon_key != manifest["horizon_key"]:
        raise PackageValidationError("predictor horizon_key does not match manifest")
    if predictor.horizon_months != manifest["horizon_months"]:
        raise PackageValidationError("predictor horizon_months does not match manifest")
    if predictor.suite_version != manifest["suite_version"]:
        raise PackageValidationError("predictor suite_version does not match manifest")
    if float(predictor.threshold) != float(manifest["threshold"]):
        raise PackageValidationError("predictor threshold does not match manifest")
    try:
        feature_contract = load_feature_contract(package_path / "feature_contract.json")
    except (OSError, ValueError) as exc:
        raise PackageValidationError(f"feature contract failed validation: {exc}") from exc
    if predictor.feature_contract != feature_contract:
        raise PackageValidationError(
            "predictor feature contract does not match feature_contract.json"
        )
    if predictor.partition_map != dict(partition_map._clusters_by_admin):
        raise PackageValidationError(
            "predictor partition map does not match partition_map.csv"
        )
    _validate_predictor_reports(predictor, training_report)
    return predictor
