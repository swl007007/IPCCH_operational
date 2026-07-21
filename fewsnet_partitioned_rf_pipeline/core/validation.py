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
        except metadata.PackageNotFoundError:
            versions[name] = "not-installed"
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
    missing = sorted(required - set(report))
    if missing:
        raise PackageValidationError(f"training_report is missing fields: {missing}")
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
    pooled_counts = _mapping(
        report["pooled_class_counts"],
        "training_report.pooled_class_counts",
    )
    if set(pooled_counts) != {"0", "1"}:
        raise PackageValidationError(
            "training_report.pooled_class_counts must contain 0 and 1"
        )
    pooled_total = sum(
        _nonnegative_integer(
            pooled_counts[class_name],
            f"training_report.pooled_class_counts.{class_name}",
        )
        for class_name in ("0", "1")
    )
    if pooled_total != sample_count:
        raise PackageValidationError(
            "training_report pooled class counts must sum to sample_count"
        )
    for name in ("cluster_states", "smote_results"):
        values = _mapping(report[name], f"training_report.{name}")
        if set(values) != EXPECTED_CLUSTER_KEYS:
            raise PackageValidationError(
                f"training_report.{name} must contain clusters 0 through 16"
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
    return dict(report)
