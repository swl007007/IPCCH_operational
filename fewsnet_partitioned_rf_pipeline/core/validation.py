"""Validation helpers for immutable FEWSNET model packages."""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass
from importlib import metadata
from numbers import Integral, Real
from typing import Any, Mapping

import pandas as pd

from fewsnet_partitioned_rf_pipeline.config import (
    HORIZON_KEYS,
    PARTITION_ASSET_SHA256,
)
from fewsnet_partitioned_rf_pipeline.core.data import normalize_admin_code
from fewsnet_partitioned_rf_pipeline.core.inference import (
    FORMAL_PREDICTION_COLUMNS,
)
from fewsnet_partitioned_rf_pipeline.core.partitions import PartitionMap
from fewsnet_partitioned_rf_pipeline.core.types import (
    ObjectRef,
    RegisteredModelVersion,
    SnapshotManifest,
)
from fewsnet_partitioned_rf_pipeline.schemas import validate_payload


RUNTIME_DEPENDENCIES = (
    "python",
    "numpy",
    "pandas",
    "scikit-learn",
    "joblib",
    "imbalanced-learn",
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MONTH_PATTERN = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")
EXPECTED_CLUSTER_KEYS = {str(cluster_id) for cluster_id in range(17)}
FALLBACK_COUNT_KEYS = {
    "pooled_unmapped",
    "pooled_small_partition",
    "pooled_single_class",
    "pooled_missing_partition_model",
}
CLUSTER_STATE_FIELDS = {
    "status",
    "sample_count",
    "class_counts",
    "smote_status",
    "fallback_reason",
}
SMOTE_RESULT_FIELDS = {
    "status",
    "original_class_counts",
    "resampled_class_counts",
    "failure_reason",
}
CLUSTER_STATUSES = {
    "partition_model",
    "pooled_small_partition",
    "pooled_single_class",
}
SMOTE_STATUSES = {
    "not_applicable_small_partition",
    "not_applicable_single_class",
    "skipped_minority_lt_2",
    "resampled",
    "failed",
}
PREDICTION_SOURCES = (
    "partition_model",
    "pooled_unmapped",
    "pooled_small_partition",
    "pooled_single_class",
    "pooled_missing_partition_model",
)
HORIZON_ORDER = tuple(HORIZON_KEYS[months] for months in sorted(HORIZON_KEYS))
HORIZON_MONTHS_BY_KEY = {
    horizon_key: months for months, horizon_key in HORIZON_KEYS.items()
}
OBJECT_URI_PATTERN = re.compile(r"^gs://[^/]+/.+")


@dataclass(frozen=True)
class PredictionSuiteEntry:
    """Validation carrier for one formal horizon output and its provenance."""

    frame: pd.DataFrame
    batch_input: ObjectRef
    batch_snapshot_content_sha256: str
    package_manifest: Mapping[str, Any]


class PackageValidationError(ValueError):
    """Raised when an immutable model package fails validation."""


def runtime_dependency_versions() -> dict[str, str]:
    """Return the exact runtime versions that govern joblib compatibility."""
    versions = {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
    }
    for name in RUNTIME_DEPENDENCIES[1:]:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError as exc:
            raise PackageValidationError(
                f"required runtime dependency {name} is not installed"
            ) from exc
    return versions


def assert_runtime_compatible(expected: dict[str, str]) -> None:
    observed = runtime_dependency_versions()
    for name in RUNTIME_DEPENDENCIES:
        if observed[name] != expected[name]:
            raise PackageValidationError(
                f"runtime dependency mismatch for {name}: "
                f"expected {expected[name]}, observed {observed[name]}"
            )


def validate_container_image_identity(uri: object, digest: object) -> None:
    if not isinstance(uri, str) or not isinstance(digest, str):
        raise PackageValidationError(
            "container_image_uri and container_image_digest must be strings"
        )
    if not uri.endswith(f"@{digest}"):
        raise PackageValidationError(
            "container_image_uri must end with @container_image_digest"
        )


def validate_sha256(value: object, name: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise PackageValidationError(f"{name} must be a lowercase SHA-256 hex digest")
    return value


def validate_month_range(value: object, name: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"start", "end"}:
        raise PackageValidationError(f"{name} must contain exactly start and end")
    start = value["start"]
    end = value["end"]
    if (
        not isinstance(start, str)
        or MONTH_PATTERN.fullmatch(start) is None
        or not isinstance(end, str)
        or MONTH_PATTERN.fullmatch(end) is None
    ):
        raise PackageValidationError(f"{name} must contain YYYY-MM values")
    if start > end:
        raise PackageValidationError(f"{name} start must not be after end")
    return {"start": start, "end": end}


def _mapping(value: object, name: str) -> Mapping:
    if not isinstance(value, Mapping):
        raise PackageValidationError(f"{name} must be an object")
    return value


def _nonnegative_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or int(value) < 0:
        raise PackageValidationError(f"{name} must be a non-negative integer")
    return int(value)


def _exact_fields(value: Mapping, expected: set[str], name: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise PackageValidationError(
            f"{name} fields differ; missing={missing}, extra={extra}"
        )


def _nullable_string(value: object, name: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise PackageValidationError(f"{name} must be a string or null")
    return value


def _binary_class_counts(value: object, name: str) -> dict[str, int]:
    counts = _mapping(value, name)
    _exact_fields(counts, {"0", "1"}, name)
    return {
        class_name: _nonnegative_integer(
            counts[class_name],
            f"{name}.{class_name}",
        )
        for class_name in ("0", "1")
    }


def _validate_cluster_state(value: object, name: str) -> dict:
    state = _mapping(value, name)
    _exact_fields(state, CLUSTER_STATE_FIELDS, name)
    status = state["status"]
    if not isinstance(status, str) or status not in CLUSTER_STATUSES:
        raise PackageValidationError(
            f"{name}.status must be one of {sorted(CLUSTER_STATUSES)}"
        )
    sample_count = _nonnegative_integer(
        state["sample_count"],
        f"{name}.sample_count",
    )
    class_counts = _binary_class_counts(
        state["class_counts"],
        f"{name}.class_counts",
    )
    if sum(class_counts.values()) != sample_count:
        raise PackageValidationError(
            f"{name}.class_counts must sum to sample_count"
        )
    smote_status = state["smote_status"]
    if not isinstance(smote_status, str) or smote_status not in SMOTE_STATUSES:
        raise PackageValidationError(
            f"{name}.smote_status must be one of {sorted(SMOTE_STATUSES)}"
        )
    fallback_reason = _nullable_string(
        state["fallback_reason"],
        f"{name}.fallback_reason",
    )

    expected_smote_statuses = {
        "partition_model": {"skipped_minority_lt_2", "resampled", "failed"},
        "pooled_small_partition": {"not_applicable_small_partition"},
        "pooled_single_class": {"not_applicable_single_class"},
    }
    if smote_status not in expected_smote_statuses[status]:
        raise PackageValidationError(
            f"{name}.status and smote_status are inconsistent"
        )
    if status == "partition_model" and fallback_reason is not None:
        raise PackageValidationError(
            f"{name}.fallback_reason must be null for partition_model"
        )
    if status != "partition_model" and fallback_reason is None:
        raise PackageValidationError(
            f"{name}.fallback_reason must describe the pooled fallback"
        )
    if (
        status == "pooled_single_class"
        and sum(count > 0 for count in class_counts.values()) != 1
    ):
        raise PackageValidationError(
            f"{name}.class_counts must contain exactly one observed class"
        )
    if status == "partition_model" and not all(
        count > 0 for count in class_counts.values()
    ):
        raise PackageValidationError(
            f"{name}.class_counts must contain both classes for partition_model"
        )
    return dict(state)


def _validate_smote_result(
    value: object,
    name: str,
    cluster_state: Mapping,
) -> dict:
    result = _mapping(value, name)
    _exact_fields(result, SMOTE_RESULT_FIELDS, name)
    status = result["status"]
    if not isinstance(status, str) or status not in SMOTE_STATUSES:
        raise PackageValidationError(
            f"{name}.status must be one of {sorted(SMOTE_STATUSES)}"
        )
    original_counts = _binary_class_counts(
        result["original_class_counts"],
        f"{name}.original_class_counts",
    )
    resampled_value = result["resampled_class_counts"]
    resampled_counts = (
        None
        if resampled_value is None
        else _binary_class_counts(
            resampled_value,
            f"{name}.resampled_class_counts",
        )
    )
    failure_reason = _nullable_string(
        result["failure_reason"],
        f"{name}.failure_reason",
    )

    if status != cluster_state["smote_status"]:
        raise PackageValidationError(
            f"{name}.status does not match cluster state smote_status"
        )
    if original_counts != cluster_state["class_counts"]:
        raise PackageValidationError(
            f"{name}.original_class_counts do not match cluster state class_counts"
        )
    if sum(original_counts.values()) != cluster_state["sample_count"]:
        raise PackageValidationError(
            f"{name}.original_class_counts must sum to cluster sample_count"
        )
    if status == "resampled":
        if resampled_counts is None:
            raise PackageValidationError(
                f"{name}.resampled_class_counts must be present after resampling"
            )
        if any(
            resampled_counts[class_name] < original_counts[class_name]
            for class_name in ("0", "1")
        ):
            raise PackageValidationError(
                f"{name}.resampled_class_counts must not decrease a class count"
            )
        if failure_reason is not None:
            raise PackageValidationError(
                f"{name}.failure_reason must be null after resampling"
            )
    elif resampled_counts is not None:
        raise PackageValidationError(
            f"{name}.resampled_class_counts must be null when SMOTE was not applied"
        )
    if status == "failed" and failure_reason is None:
        raise PackageValidationError(
            f"{name}.failure_reason must describe the SMOTE failure"
        )
    if status != "failed" and failure_reason is not None:
        raise PackageValidationError(
            f"{name}.failure_reason must be null unless SMOTE failed"
        )
    if status == "skipped_minority_lt_2" and min(original_counts.values()) >= 2:
        raise PackageValidationError(
            f"{name}.original_class_counts are inconsistent with skipped_minority_lt_2"
        )
    return dict(result)


def _bounded_metric(value: object, name: str, *, nullable: bool) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise PackageValidationError(f"{name} must be a number between 0 and 1")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise PackageValidationError(f"{name} must be a number between 0 and 1")
    return number


def validate_threshold_report(value: object) -> dict:
    report = _mapping(value, "threshold_report")
    required = {
        "threshold",
        "precision",
        "recall",
        "f1",
        "support",
        "positive_cases",
        "fallback_reason",
    }
    if set(report) != required:
        missing = sorted(required - set(report))
        extra = sorted(set(report) - required)
        raise PackageValidationError(
            f"threshold_report fields differ; missing={missing}, extra={extra}"
        )
    _bounded_metric(report["threshold"], "threshold_report.threshold", nullable=False)
    for name in ("precision", "recall", "f1"):
        _bounded_metric(report[name], f"threshold_report.{name}", nullable=True)
    support = _nonnegative_integer(report["support"], "threshold_report.support")
    positive_cases = _nonnegative_integer(
        report["positive_cases"],
        "threshold_report.positive_cases",
    )
    if positive_cases > support:
        raise PackageValidationError(
            "threshold_report.positive_cases must not exceed support"
        )
    fallback_reason = report["fallback_reason"]
    if fallback_reason is not None and not isinstance(fallback_reason, str):
        raise PackageValidationError(
            "threshold_report.fallback_reason must be a string or null"
        )
    return dict(report)


def validate_horizon_training_report(value: object) -> dict:
    report = _mapping(value, "training_report")
    required = {
        "schema_version",
        "horizon_key",
        "horizon_months",
        "feature_schema_sha256",
        "partition_asset_sha256",
        "partition_coverage_pct",
        "training_target_month_range",
        "fit_target_month_range",
        "validation_target_month_range",
        "sample_count",
        "fit_sample_count",
        "validation_sample_count",
        "pooled_class_counts",
        "cluster_states",
        "smote_results",
        "fallback_counts",
    }
    _exact_fields(report, required, "training_report")
    if report["schema_version"] != "fewsnet-horizon-training-report-v1":
        raise PackageValidationError(
            "training_report schema_version must be fewsnet-horizon-training-report-v1"
        )
    horizon_months = report["horizon_months"]
    if (
        isinstance(horizon_months, bool)
        or not isinstance(horizon_months, Integral)
        or HORIZON_KEYS.get(int(horizon_months)) != report["horizon_key"]
    ):
        raise PackageValidationError(
            "training_report horizon_key and horizon_months do not match"
        )
    validate_sha256(
        report["feature_schema_sha256"],
        "training_report.feature_schema_sha256",
    )
    validate_sha256(
        report["partition_asset_sha256"],
        "training_report.partition_asset_sha256",
    )
    coverage = report["partition_coverage_pct"]
    if isinstance(coverage, bool) or not isinstance(coverage, Real):
        raise PackageValidationError(
            "training_report.partition_coverage_pct must be between 0 and 100"
        )
    coverage_number = float(coverage)
    if not math.isfinite(coverage_number) or not 0.0 <= coverage_number <= 100.0:
        raise PackageValidationError(
            "training_report.partition_coverage_pct must be between 0 and 100"
        )
    for name in (
        "training_target_month_range",
        "fit_target_month_range",
        "validation_target_month_range",
    ):
        validate_month_range(report[name], f"training_report.{name}")
    sample_count = _nonnegative_integer(
        report["sample_count"],
        "training_report.sample_count",
    )
    fit_count = _nonnegative_integer(
        report["fit_sample_count"],
        "training_report.fit_sample_count",
    )
    validation_count = _nonnegative_integer(
        report["validation_sample_count"],
        "training_report.validation_sample_count",
    )
    if fit_count + validation_count != sample_count:
        raise PackageValidationError(
            "training_report fit and validation counts must sum to sample_count"
        )
    pooled_counts = _binary_class_counts(
        report["pooled_class_counts"],
        "training_report.pooled_class_counts",
    )
    if sum(pooled_counts.values()) != sample_count:
        raise PackageValidationError(
            "training_report pooled class counts must sum to sample_count"
        )
    cluster_states = _mapping(
        report["cluster_states"],
        "training_report.cluster_states",
    )
    if set(cluster_states) != EXPECTED_CLUSTER_KEYS:
        raise PackageValidationError(
            "training_report.cluster_states must contain clusters 0 through 16"
        )
    validated_cluster_states = {
        cluster_id: _validate_cluster_state(
            cluster_states[cluster_id],
            f"training_report.cluster_states.{cluster_id}",
        )
        for cluster_id in sorted(EXPECTED_CLUSTER_KEYS, key=int)
    }
    smote_results = _mapping(
        report["smote_results"],
        "training_report.smote_results",
    )
    if set(smote_results) != EXPECTED_CLUSTER_KEYS:
        raise PackageValidationError(
            "training_report.smote_results must contain clusters 0 through 16"
        )
    for cluster_id in sorted(EXPECTED_CLUSTER_KEYS, key=int):
        _validate_smote_result(
            smote_results[cluster_id],
            f"training_report.smote_results.{cluster_id}",
            validated_cluster_states[cluster_id],
        )
    fallback_counts = _mapping(
        report["fallback_counts"],
        "training_report.fallback_counts",
    )
    if set(fallback_counts) != FALLBACK_COUNT_KEYS:
        raise PackageValidationError(
            "training_report.fallback_counts has invalid fields"
        )
    for name, count in fallback_counts.items():
        _nonnegative_integer(count, f"training_report.fallback_counts.{name}")
    expected_fallback_counts = {
        "pooled_unmapped": 0,
        "pooled_small_partition": sum(
            state["status"] == "pooled_small_partition"
            for state in validated_cluster_states.values()
        ),
        "pooled_single_class": sum(
            state["status"] == "pooled_single_class"
            for state in validated_cluster_states.values()
        ),
        "pooled_missing_partition_model": 0,
    }
    if dict(fallback_counts) != expected_fallback_counts:
        raise PackageValidationError(
            "training_report.fallback_counts do not match cluster_states"
        )
    return dict(report)


def validate_prediction_suite(
    predictions: Mapping[str, PredictionSuiteEntry],
    snapshot: SnapshotManifest,
    registered_versions: Mapping[str, RegisteredModelVersion],
) -> dict[str, Any]:
    """Validate one exact, provenance-bound prediction frame per horizon."""
    if not isinstance(predictions, Mapping):
        raise TypeError("predictions must be a mapping")
    if not isinstance(snapshot, SnapshotManifest):
        raise TypeError("snapshot must be a SnapshotManifest")
    if not isinstance(registered_versions, Mapping):
        raise TypeError("registered_versions must be a mapping")
    _require_horizon_keys(predictions, "predictions")
    _require_horizon_keys(registered_versions, "registered_versions")
    validate_sha256(
        snapshot.snapshot_content_sha256,
        "snapshot.snapshot_content_sha256",
    )
    if snapshot.area_count <= 0:
        raise ValueError("snapshot.area_count must be positive")
    if MONTH_PATTERN.fullmatch(snapshot.latest_feature_month) is None:
        raise ValueError("snapshot.latest_feature_month must be YYYY-MM")

    suite_version: str | None = None
    authoritative_admin_universe: set[str] | None = None
    horizon_summaries: dict[str, dict[str, Any]] = {}
    for horizon_key in HORIZON_ORDER:
        entry = predictions[horizon_key]
        if not isinstance(entry, PredictionSuiteEntry):
            raise TypeError(
                "predictions entries must be PredictionSuiteEntry instances"
            )
        version = registered_versions[horizon_key]
        _validate_registered_version(version, horizon_key)
        _validate_object_ref(
            entry.batch_input,
            f"predictions.{horizon_key}.batch_input",
        )
        validate_sha256(
            entry.batch_snapshot_content_sha256,
            f"predictions.{horizon_key}.batch_snapshot_content_sha256",
        )
        if (
            entry.batch_snapshot_content_sha256
            != snapshot.snapshot_content_sha256
        ):
            raise ValueError(
                f"{horizon_key} Batch input snapshot digest does not match "
                "the selected snapshot"
            )
        package = _validate_suite_package(
            entry.package_manifest,
            snapshot=snapshot,
            version=version,
            horizon_key=horizon_key,
        )
        frame_summary = _validate_prediction_frame(
            entry.frame,
            snapshot=snapshot,
            version=version,
            package=package,
            horizon_key=horizon_key,
        )
        frame_suite_version = frame_summary.pop("suite_version")
        admin_universe = frame_summary.pop("admin_universe")
        if suite_version is None:
            suite_version = frame_suite_version
        elif frame_suite_version != suite_version:
            raise ValueError("prediction suite_version differs across horizons")
        if authoritative_admin_universe is None:
            authoritative_admin_universe = admin_universe
        elif admin_universe != authoritative_admin_universe:
            raise ValueError("prediction admin universe differs across horizons")
        horizon_summaries[horizon_key] = frame_summary

    if suite_version is None:
        raise ValueError("prediction suite is empty")
    return {
        "suite_version": suite_version,
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_content_sha256": snapshot.snapshot_content_sha256,
        "feature_month": snapshot.latest_feature_month,
        "area_count": snapshot.area_count,
        "horizons": horizon_summaries,
    }


def _require_horizon_keys(value: Mapping, name: str) -> None:
    expected = set(HORIZON_ORDER)
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(
            f"{name} horizon keys differ; missing={missing}, extra={extra}"
        )


def _validate_registered_version(
    version: object,
    horizon_key: str,
) -> None:
    if not isinstance(version, RegisteredModelVersion):
        raise TypeError(
            "registered_versions must contain RegisteredModelVersion instances"
        )
    if version.horizon_key != horizon_key:
        raise ValueError("registered model version horizon does not match its key")
    if not version.parent_model_resource_name:
        raise ValueError("registered model parent resource is required")
    if not version.version_id.isdigit():
        raise ValueError("registered model version ID must be numeric")
    expected_resource = (
        f"{version.parent_model_resource_name}@{version.version_id}"
    )
    if version.version_resource_name != expected_resource:
        raise ValueError(
            "registered model version resource must use the exact numeric version"
        )


def _validate_object_ref(value: object, name: str) -> None:
    if not isinstance(value, ObjectRef):
        raise TypeError(f"{name} must be an ObjectRef")
    if OBJECT_URI_PATTERN.fullmatch(value.uri) is None:
        raise ValueError(f"{name}.uri must be a gs://bucket/object URI")
    if not value.generation.isdigit():
        raise ValueError(f"{name} must contain a numeric generation")
    if int(value.generation) <= 0:
        raise ValueError(f"{name} generation must be positive")
    validate_sha256(value.sha256, f"{name}.sha256")
    if (
        isinstance(value.size_bytes, bool)
        or not isinstance(value.size_bytes, Integral)
        or int(value.size_bytes) < 0
    ):
        raise ValueError(f"{name} must contain a non-negative size")


def _validate_suite_package(
    value: object,
    *,
    snapshot: SnapshotManifest,
    version: RegisteredModelVersion,
    horizon_key: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("package_manifest must be a mapping")
    package = dict(value)
    try:
        validate_payload("model-package", package)
    except ValueError as exc:
        raise ValueError(f"{horizon_key} package manifest is invalid: {exc}") from exc
    if package["status"] != "validated":
        raise ValueError(f"{horizon_key} package manifest must be validated")
    if package["snapshot_id"] != snapshot.snapshot_id:
        raise ValueError(f"{horizon_key} package snapshot ID does not match")
    if package["snapshot_content_sha256"] != snapshot.snapshot_content_sha256:
        raise ValueError(f"{horizon_key} package snapshot digest does not match")
    if package["horizon_key"] != horizon_key:
        raise ValueError(f"{horizon_key} package horizon key does not match")
    expected_months = HORIZON_MONTHS_BY_KEY[horizon_key]
    if package["horizon_months"] != expected_months:
        raise ValueError(f"{horizon_key} package horizon months do not match")
    expected_target = str(
        pd.Period(snapshot.latest_feature_month, freq="M") + expected_months
    )
    if package["target_month"] != expected_target:
        raise ValueError(f"{horizon_key} package target month does not match")
    if package["partition_sha256"] != PARTITION_ASSET_SHA256:
        raise ValueError(f"{horizon_key} package partition identity does not match")
    expected_artifact_suffix = (
        f"/suites/{package['suite_version']}/models/{horizon_key}"
    )
    if not version.artifact_uri.endswith(expected_artifact_suffix):
        raise ValueError(
            f"{horizon_key} registered model artifact URI does not match the package"
        )
    return package


def _validate_prediction_frame(
    frame: object,
    *,
    snapshot: SnapshotManifest,
    version: RegisteredModelVersion,
    package: Mapping[str, Any],
    horizon_key: str,
) -> dict[str, Any]:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{horizon_key} prediction frame must be a DataFrame")
    columns = [str(column) for column in frame.columns]
    duplicate_columns = sorted(
        {column for column in columns if columns.count(column) > 1}
    )
    if duplicate_columns:
        raise ValueError(
            f"{horizon_key} prediction frame has duplicate columns: "
            f"{duplicate_columns}"
        )
    if tuple(columns) != FORMAL_PREDICTION_COLUMNS:
        raise ValueError(
            f"{horizon_key} prediction frame must use the formal prediction columns"
        )
    if len(frame) != snapshot.area_count:
        raise ValueError(
            f"{horizon_key} prediction row count must equal snapshot.area_count"
        )

    admin_codes = frame["admin_code"].map(normalize_admin_code)
    if admin_codes.eq("").any():
        raise ValueError(f"{horizon_key} prediction admin_code is blank")
    if admin_codes.duplicated(keep=False).any():
        raise ValueError(f"{horizon_key} prediction contains duplicate admin_code")
    admin_universe = set(admin_codes.tolist())
    if len(admin_universe) != snapshot.area_count:
        raise ValueError(
            f"{horizon_key} prediction admin universe does not match "
            "snapshot area count"
        )

    feature_months = _prediction_months(
        frame["feature_month"],
        f"{horizon_key}.feature_month",
    )
    if set(feature_months) != {snapshot.latest_feature_month}:
        raise ValueError(
            f"{horizon_key} feature_month must equal the selected snapshot month"
        )
    expected_months = HORIZON_MONTHS_BY_KEY[horizon_key]
    horizon_months = _integral_values(
        frame["horizon_months"],
        f"{horizon_key}.horizon_months",
    )
    if set(horizon_months) != {expected_months}:
        raise ValueError(f"{horizon_key} horizon_months does not match its key")
    expected_target = str(
        pd.Period(snapshot.latest_feature_month, freq="M") + expected_months
    )
    target_months = _prediction_months(
        frame["target_month"],
        f"{horizon_key}.target_month",
    )
    if set(target_months) != {expected_target}:
        raise ValueError(
            f"{horizon_key} target_month must equal feature_month plus horizon"
        )

    probabilities = _bounded_prediction_numbers(
        frame["probability_crisis"],
        f"{horizon_key}.probability_crisis",
    )
    thresholds = _bounded_prediction_numbers(
        frame["threshold"],
        f"{horizon_key}.threshold",
    )
    classes = _binary_prediction_classes(
        frame["predicted_crisis"],
        f"{horizon_key}.predicted_crisis",
    )
    expected_classes = [
        int(probability >= threshold)
        for probability, threshold in zip(
            probabilities,
            thresholds,
            strict=True,
        )
    ]
    if classes != expected_classes:
        raise ValueError(
            f"{horizon_key} predicted class must equal probability >= threshold"
        )
    if set(thresholds) != {float(package["threshold"])}:
        raise ValueError(f"{horizon_key} threshold does not match package")

    cluster_ids = _prediction_cluster_ids(
        frame["cluster_id"],
        horizon_key,
    )
    sources = frame["prediction_source"].tolist()
    if any(source not in PREDICTION_SOURCES for source in sources):
        raise ValueError(f"{horizon_key} prediction_source is invalid")
    for cluster_id, source in zip(cluster_ids, sources, strict=True):
        if (cluster_id is None) != (source == "pooled_unmapped"):
            raise ValueError(f"{horizon_key} prediction route/source pair is invalid")

    mapped_rows = [
        (admin_code, cluster_id)
        for admin_code, cluster_id in zip(
            admin_codes,
            cluster_ids,
            strict=True,
        )
        if cluster_id is not None
    ]
    mapped_frame = pd.DataFrame(
        mapped_rows,
        columns=["admin_code", "cluster_id"],
    )
    coverage = PartitionMap.from_frame(mapped_frame).assert_release_coverage(
        admin_codes
    )

    suite_versions = frame["suite_version"].tolist()
    if any(
        not isinstance(value, str) or not value
        for value in suite_versions
    ) or set(suite_versions) != {package["suite_version"]}:
        raise ValueError(f"{horizon_key} suite_version does not match package")
    resources = frame["vertex_model_resource_name"].tolist()
    version_ids = frame["vertex_model_version_id"].tolist()
    if set(resources) != {version.version_resource_name} or set(version_ids) != {
        version.version_id
    }:
        raise ValueError(
            f"{horizon_key} formal output does not match registered model version"
        )

    source_counts = {
        source: int(sum(value == source for value in sources))
        for source in PREDICTION_SOURCES
    }
    if sum(source_counts.values()) != snapshot.area_count:
        raise ValueError(f"{horizon_key} fallback totals do not reconcile")
    return {
        "suite_version": package["suite_version"],
        "admin_universe": admin_universe,
        "row_count": len(frame),
        "partition_coverage_pct": coverage,
        "source_counts": source_counts,
    }


def _prediction_months(values: pd.Series, name: str) -> list[str]:
    months: list[str] = []
    for value in values:
        if not isinstance(value, str) or MONTH_PATTERN.fullmatch(value) is None:
            raise ValueError(f"{name} must contain YYYY-MM strings")
        months.append(value)
    return months


def _integral_values(values: pd.Series, name: str) -> list[int]:
    result: list[int] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise ValueError(f"{name} must contain integers")
        result.append(int(value))
    return result


def _bounded_prediction_numbers(values: pd.Series, name: str) -> list[float]:
    result: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{name} must contain numbers between 0 and 1")
        number = float(value)
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            raise ValueError(f"{name} must contain numbers between 0 and 1")
        result.append(number)
    return result


def _binary_prediction_classes(values: pd.Series, name: str) -> list[int]:
    result = _integral_values(values, name)
    if any(value not in {0, 1} for value in result):
        raise ValueError(f"{name} must contain only 0 or 1")
    return result


def _prediction_cluster_ids(
    values: pd.Series,
    horizon_key: str,
) -> list[int | None]:
    result: list[int | None] = []
    for value in values:
        if value is None or pd.isna(value):
            result.append(None)
            continue
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise ValueError(f"{horizon_key} cluster_id must be integer or null")
        cluster_id = int(value)
        if not 0 <= cluster_id <= 16:
            raise ValueError(f"{horizon_key} cluster_id must be between 0 and 16")
        result.append(cluster_id)
    return result
