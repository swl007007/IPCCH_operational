"""Truthful writing and defensive loading for local FEWSNET model packages."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from numbers import Integral
from pathlib import Path

import joblib

from fewsnet_partitioned_rf_pipeline.config import (
    FEATURE_CONTRACT_PATH,
    PARTITION_ASSET_PATH,
    PARTITION_ASSET_SHA256,
)
from fewsnet_partitioned_rf_pipeline.core.inference import PartitionedRFPredictor
from fewsnet_partitioned_rf_pipeline.core.partitions import PartitionMap
from fewsnet_partitioned_rf_pipeline.core.preprocessing import load_feature_contract
from fewsnet_partitioned_rf_pipeline.core.validation import (
    CLUSTER_STATE_FIELDS,
    SMOTE_RESULT_FIELDS,
    PackageValidationError,
    assert_runtime_compatible,
    runtime_dependency_versions,
    validate_horizon_training_report,
    validate_sha256,
    validate_threshold_report,
)
from fewsnet_partitioned_rf_pipeline.schemas import validate_payload


LOCAL_PACKAGE_FILES = (
    "model.joblib",
    "feature_contract.json",
    "partition_map.csv",
    "threshold_report.json",
    "training_report.json",
    "local_model_manifest.json",
    "checksums.json",
)
_CONTENT_FILES = tuple(
    filename for filename in LOCAL_PACKAGE_FILES if filename != "checksums.json"
)
_REPORT_FIELDS = {"training_report", "threshold_report"}


@dataclass(frozen=True)
class LocalPackageMetadata:
    suite_version: str
    feature_month: str
    target_month: str
    latest_label_month: str
    source_git_commit: str
    panel_path: str
    panel_sha256: str
    panel_size_bytes: int
    panel_row_count: int
    normalization_audit_path: str
    normalization_audit_sha256: str
    normalization_audit_size_bytes: int


@dataclass(frozen=True)
class LoadedLocalModelPackage:
    predictor: PartitionedRFPredictor
    manifest: dict[str, object]
    training_report: dict[str, object]
    threshold_report: dict[str, object]
    checksums: dict[str, str]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _read_json_object(path: Path, name: str) -> dict[str, object]:
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


def _exact_fields(value: Mapping, expected: set[str], name: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise PackageValidationError(
            f"{name} fields differ; missing={missing}, extra={extra}"
        )


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


def _approved_partition_map() -> PartitionMap:
    try:
        return PartitionMap.load(PARTITION_ASSET_PATH, PARTITION_ASSET_SHA256)
    except (OSError, ValueError) as exc:
        raise PackageValidationError(
            f"approved partition asset failed validation: {exc}"
        ) from exc


def _approved_feature_contract():
    try:
        return load_feature_contract(FEATURE_CONTRACT_PATH)
    except (OSError, ValueError) as exc:
        raise PackageValidationError(
            f"approved feature contract failed validation: {exc}"
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
            "predictor partition_metadata cluster_states failed validation: "
            f"{detail}"
        ) from exc
    if projected_cluster_states != training_report["cluster_states"]:
        raise PackageValidationError(
            "predictor partition_metadata cluster_states do not match "
            "training_report.json"
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
            "predictor partition_metadata smote_results failed validation: "
            f"{detail}"
        ) from exc
    if projected_smote_results != training_report["smote_results"]:
        raise PackageValidationError(
            "predictor partition_metadata smote_results do not match "
            "training_report.json"
        )


def _validated_reports(
    predictor: PartitionedRFPredictor,
    reports: object,
) -> tuple[dict[str, object], dict[str, object]]:
    report_mapping = _mapping(reports, "reports")
    _exact_fields(report_mapping, _REPORT_FIELDS, "reports")
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


def _shift_month(month: str, months: int) -> str:
    year = int(month[:4])
    month_number = int(month[5:7])
    absolute_month = year * 12 + month_number - 1 + months
    shifted_year, shifted_zero_based_month = divmod(absolute_month, 12)
    return f"{shifted_year:04d}-{shifted_zero_based_month + 1:02d}"


def _expected_suite_version(manifest: Mapping[str, object]) -> str:
    feature_month = str(manifest["feature_month"])
    source_git_commit = str(manifest["source_git_commit"])
    panel_sha256 = str(manifest["source_panel"]["sha256"])
    return (
        f"local-{feature_month.replace('-', '')}-"
        f"{source_git_commit[:12]}-{panel_sha256[:12]}"
    )


def _validate_manifest_identities(manifest: Mapping[str, object]) -> None:
    if manifest["suite_version"] != _expected_suite_version(manifest):
        raise PackageValidationError(
            "local package suite version does not match feature month, "
            "source Git commit, and panel SHA-256"
        )
    expected_target_month = _shift_month(
        str(manifest["feature_month"]),
        int(manifest["horizon_months"]),
    )
    if manifest["target_month"] != expected_target_month:
        raise PackageValidationError(
            "local package target_month does not match feature_month and horizon"
        )
    latest_label_month = manifest["latest_label_month"]
    for range_name in (
        "training_target_month_range",
        "validation_target_month_range",
    ):
        if manifest[range_name]["end"] != latest_label_month:
            raise PackageValidationError(
                f"local package {range_name} must end at latest_label_month"
            )


def _manifest(
    predictor: PartitionedRFPredictor,
    metadata: LocalPackageMetadata,
    training_report: Mapping,
) -> dict[str, object]:
    manifest: dict[str, object] = {
        "schema_version": "fewsnet-local-model-package-v1",
        "runtime_backend": "local_python",
        "suite_version": metadata.suite_version,
        "feature_month": metadata.feature_month,
        "target_month": metadata.target_month,
        "latest_label_month": metadata.latest_label_month,
        "horizon_key": predictor.horizon_key,
        "horizon_months": predictor.horizon_months,
        "source_panel": {
            "path": metadata.panel_path,
            "sha256": metadata.panel_sha256,
            "size_bytes": metadata.panel_size_bytes,
            "row_count": metadata.panel_row_count,
        },
        "normalization_audit": {
            "path": metadata.normalization_audit_path,
            "sha256": metadata.normalization_audit_sha256,
            "size_bytes": metadata.normalization_audit_size_bytes,
        },
        "feature_schema_sha256": predictor.feature_contract.feature_schema_sha256,
        "partition_sha256": PARTITION_ASSET_SHA256,
        "threshold": float(predictor.threshold),
        "dependency_versions": runtime_dependency_versions(),
        "source_git_commit": metadata.source_git_commit,
        "training_target_month_range": dict(
            training_report["training_target_month_range"]
        ),
        "validation_target_month_range": dict(
            training_report["validation_target_month_range"]
        ),
        "files": list(LOCAL_PACKAGE_FILES),
        "status": "validated",
    }
    try:
        validate_payload("local-model-package", manifest)
    except ValueError as exc:
        raise PackageValidationError(str(exc)) from exc
    _validate_manifest_identities(manifest)
    return manifest


def write_local_model_package(
    output_dir: str | Path,
    predictor: PartitionedRFPredictor,
    metadata: LocalPackageMetadata,
    reports: object,
) -> dict[str, object]:
    """Write one exact seven-file package for the local Python runtime."""
    if not isinstance(predictor, PartitionedRFPredictor):
        raise TypeError("predictor must be a PartitionedRFPredictor")
    if not isinstance(metadata, LocalPackageMetadata):
        raise TypeError("metadata must be a LocalPackageMetadata")
    if (
        predictor.vertex_model_resource_name != ""
        or predictor.vertex_model_version_id != ""
    ):
        raise PackageValidationError(
            "local predictor Vertex identity fields must be blank"
        )

    approved_feature_contract = _approved_feature_contract()
    if predictor.feature_contract != approved_feature_contract:
        raise PackageValidationError(
            "predictor feature contract does not match the approved frozen contract"
        )
    approved_partition = _approved_partition_map()
    _validate_predictor_partition(predictor, approved_partition)
    training_report, threshold_report = _validated_reports(predictor, reports)
    _validate_predictor_reports(predictor, training_report)
    manifest = _manifest(predictor, metadata, training_report)

    suite_version = str(manifest["suite_version"])
    if predictor.suite_version and predictor.suite_version != suite_version:
        raise PackageValidationError(
            "predictor suite_version does not match local package metadata"
        )
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
    (package_dir / "feature_contract.json").write_bytes(
        FEATURE_CONTRACT_PATH.read_bytes()
    )
    (package_dir / "partition_map.csv").write_bytes(PARTITION_ASSET_PATH.read_bytes())
    _write_json(package_dir / "threshold_report.json", threshold_report)
    _write_json(package_dir / "training_report.json", training_report)
    _write_json(package_dir / "local_model_manifest.json", manifest)

    checksums = {
        filename: _sha256(package_dir / filename)
        for filename in sorted(_CONTENT_FILES)
    }
    _write_json(package_dir / "checksums.json", checksums)
    return manifest


def _require_package_files(package_dir: Path) -> None:
    if not package_dir.is_dir():
        raise PackageValidationError("package_dir must be an existing directory")
    actual = {path.name for path in package_dir.iterdir()}
    expected = set(LOCAL_PACKAGE_FILES)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise PackageValidationError(
            f"package files differ; missing={missing}, extra={extra}"
        )
    for filename in LOCAL_PACKAGE_FILES:
        member = package_dir / filename
        if member.is_symlink() or not member.is_file():
            raise PackageValidationError(
                f"{filename} must be a regular non-symlink file"
            )


def _verify_checksums(package_dir: Path) -> dict[str, str]:
    checksums = _read_json_object(package_dir / "checksums.json", "checksums.json")
    _exact_fields(checksums, set(_CONTENT_FILES), "checksums.json")
    for filename in _CONTENT_FILES:
        expected = validate_sha256(
            checksums[filename],
            f"checksums.json.{filename}",
        )
        observed = _sha256(package_dir / filename)
        if observed != expected:
            raise PackageValidationError(
                f"checksum mismatch for {filename}: "
                f"expected {expected}, observed {observed}"
            )
    return {name: str(value) for name, value in checksums.items()}


def _read_and_validate_manifest(package_dir: Path) -> dict[str, object]:
    manifest = _read_json_object(
        package_dir / "local_model_manifest.json",
        "local_model_manifest.json",
    )
    try:
        validate_payload("local-model-package", manifest)
    except ValueError as exc:
        raise PackageValidationError(str(exc)) from exc
    if set(manifest["files"]) != set(LOCAL_PACKAGE_FILES):
        raise PackageValidationError(
            "local model manifest files must list the exact seven package files"
        )
    _validate_manifest_identities(manifest)
    return manifest


def _validate_expected_identities(
    manifest: Mapping[str, object],
    *,
    expected_suite_version: str | None,
    expected_source_git_commit: str | None,
    expected_panel_sha256: str | None,
) -> None:
    if (
        expected_suite_version is not None
        and manifest["suite_version"] != expected_suite_version
    ):
        raise PackageValidationError(
            "local package suite version does not match expected suite version"
        )
    if (
        expected_source_git_commit is not None
        and manifest["source_git_commit"] != expected_source_git_commit
    ):
        raise PackageValidationError(
            "local package source Git commit does not match expected source Git commit"
        )
    if (
        expected_panel_sha256 is not None
        and manifest["source_panel"]["sha256"] != expected_panel_sha256
    ):
        raise PackageValidationError(
            "local package panel SHA-256 does not match expected panel SHA-256"
        )


def _validate_contract_partition_and_reports(
    package_dir: Path,
    manifest: Mapping[str, object],
) -> tuple[object, PartitionMap, dict[str, object], dict[str, object]]:
    try:
        feature_contract = load_feature_contract(package_dir / "feature_contract.json")
    except (OSError, ValueError) as exc:
        raise PackageValidationError(f"feature contract failed validation: {exc}") from exc
    if feature_contract.feature_schema_sha256 != manifest["feature_schema_sha256"]:
        raise PackageValidationError(
            "feature_schema_sha256 does not match feature_contract.json"
        )
    if feature_contract != _approved_feature_contract():
        raise PackageValidationError(
            "feature_contract.json does not match the approved frozen contract"
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
            str(manifest["partition_sha256"]),
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
            "training_report horizon_key does not match local model manifest"
        )
    if int(training_report["horizon_months"]) != manifest["horizon_months"]:
        raise PackageValidationError(
            "training_report horizon_months does not match local model manifest"
        )
    if training_report["feature_schema_sha256"] != manifest["feature_schema_sha256"]:
        raise PackageValidationError(
            "training_report feature identity does not match local model manifest"
        )
    if training_report["partition_asset_sha256"] != manifest["partition_sha256"]:
        raise PackageValidationError(
            "training_report partition identity does not match local model manifest"
        )
    if float(threshold_report["threshold"]) != float(manifest["threshold"]):
        raise PackageValidationError(
            "threshold_report threshold does not match local model manifest"
        )
    return feature_contract, partition_map, training_report, threshold_report


def load_local_model_package(
    package_dir: str | Path,
    *,
    expected_suite_version: str | None = None,
    expected_source_git_commit: str | None = None,
    expected_panel_sha256: str | None = None,
) -> LoadedLocalModelPackage:
    """Validate a local package completely before unpickling its predictor."""
    package_path = Path(package_dir)
    _require_package_files(package_path)
    checksums = _verify_checksums(package_path)
    manifest = _read_and_validate_manifest(package_path)
    _validate_expected_identities(
        manifest,
        expected_suite_version=expected_suite_version,
        expected_source_git_commit=expected_source_git_commit,
        expected_panel_sha256=expected_panel_sha256,
    )
    (
        feature_contract,
        partition_map,
        training_report,
        threshold_report,
    ) = _validate_contract_partition_and_reports(package_path, manifest)

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
    if predictor.feature_contract != feature_contract:
        raise PackageValidationError(
            "predictor feature contract does not match feature_contract.json"
        )
    if predictor.partition_map != dict(partition_map._clusters_by_admin):
        raise PackageValidationError(
            "predictor partition map does not match partition_map.csv"
        )
    _validate_predictor_reports(predictor, training_report)
    if (
        predictor.vertex_model_resource_name != ""
        or predictor.vertex_model_version_id != ""
    ):
        raise PackageValidationError(
            "local predictor Vertex identity fields must be blank"
        )
    return LoadedLocalModelPackage(
        predictor=predictor,
        manifest=manifest,
        training_report=training_report,
        threshold_report=threshold_report,
        checksums=checksums,
    )
