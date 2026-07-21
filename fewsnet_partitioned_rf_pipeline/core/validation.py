"""Validation helpers for immutable FEWSNET model packages."""

from __future__ import annotations

import math
import re
import sys
from importlib import metadata
from numbers import Integral, Real
from typing import Mapping

from fewsnet_partitioned_rf_pipeline.config import HORIZON_KEYS


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
