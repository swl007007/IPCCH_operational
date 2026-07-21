"""Training for pooled and fixed-partition FEWSNET Random Forest models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import inspect
from numbers import Integral
from typing import Iterable

import numpy as np
import pandas as pd
import sklearn.ensemble
import sklearn.utils.validation
from sklearn.ensemble import RandomForestClassifier
from sklearn.utils._dataframe import is_pandas_df

from fewsnet_partitioned_rf_pipeline.config import (
    ADMIN_CANONICAL_COLUMN,
    HORIZON_KEYS,
    PARTITION_ASSET_PATH,
    PARTITION_ASSET_SHA256,
    PARTITION_MIN_SAMPLES,
    RF_PARAMS,
    SMOTE_MAX_NEIGHBORS,
    TARGET_COLUMN,
    THRESHOLD_VALIDATION_MONTHS,
    TRAIN_WINDOW_MONTHS,
)
from fewsnet_partitioned_rf_pipeline.core.horizons import (
    FEATURE_MONTH_COLUMN,
    TARGET_MONTH_COLUMN,
    split_threshold_window,
)
from fewsnet_partitioned_rf_pipeline.core.inference import (
    PartitionedRFPredictor,
    _normalize_cluster_ids,
    predict_partition_probabilities,
)
from fewsnet_partitioned_rf_pipeline.core.partitions import PartitionMap
from fewsnet_partitioned_rf_pipeline.core.preprocessing import MaxPlusImputer
from fewsnet_partitioned_rf_pipeline.core.thresholds import (
    select_max_f1_threshold,
)
from fewsnet_partitioned_rf_pipeline.core.types import (
    FeatureContract,
    PartitionStatus,
)


def _load_smote_type():
    """Import the pinned imbalanced-learn against sklearn 1.8 compatibly."""
    validation_module = sklearn.utils.validation
    had_private_dataframe_helper = hasattr(
        validation_module,
        "_is_pandas_df",
    )
    if not had_private_dataframe_helper:
        validation_module._is_pandas_df = is_pandas_df

    original_adaboost = sklearn.ensemble.AdaBoostClassifier
    needs_algorithm_bridge = "algorithm" not in inspect.signature(
        original_adaboost
    ).parameters
    if needs_algorithm_bridge:

        class CompatAdaBoostClassifier(original_adaboost):
            def __init__(
                self,
                estimator=None,
                *,
                n_estimators=50,
                learning_rate=1.0,
                algorithm=None,
                random_state=None,
            ):
                self.algorithm = algorithm
                super().__init__(
                    estimator=estimator,
                    n_estimators=n_estimators,
                    learning_rate=learning_rate,
                    random_state=random_state,
                )

        sklearn.ensemble.AdaBoostClassifier = CompatAdaBoostClassifier

    try:
        from imblearn.over_sampling import SMOTE as smote_type
    finally:
        if needs_algorithm_bridge:
            sklearn.ensemble.AdaBoostClassifier = original_adaboost
        if not had_private_dataframe_helper:
            del validation_module._is_pandas_df
    return smote_type


SMOTE = _load_smote_type()


@dataclass(frozen=True)
class PartitionModels:
    pooled_model: RandomForestClassifier
    partition_models: dict[int, RandomForestClassifier | None]
    partition_status: dict[int, PartitionStatus]
    partition_metadata: dict[int, dict]


@dataclass(frozen=True)
class HorizonTrainingResult:
    predictor: PartitionedRFPredictor
    training_report: dict
    threshold_report: dict


def _as_training_matrix(X: object) -> np.ndarray:
    try:
        matrix = np.asarray(X, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("X must be a 2-D numeric array") from exc
    if matrix.ndim != 2:
        raise ValueError("X must be a 2-D numeric array")
    if len(matrix) == 0:
        raise ValueError("X must contain at least one training row")
    if not np.isfinite(matrix).all():
        raise ValueError("X must contain only finite values after imputation")
    return matrix


def _as_binary_target(y: object, *, expected_rows: int) -> np.ndarray:
    try:
        values = np.asarray(y, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("y must contain binary numeric values") from exc
    if values.ndim != 1:
        raise ValueError("y must be one-dimensional")
    if len(values) != expected_rows:
        raise ValueError("y must have one value per X row")
    if not np.isfinite(values).all() or not np.isin(values, [0.0, 1.0]).all():
        raise ValueError("y must contain only binary 0/1 values")
    return values.astype(np.int8)


def _validate_min_samples(min_samples: int) -> int:
    if (
        isinstance(min_samples, bool)
        or not isinstance(min_samples, Integral)
        or int(min_samples) <= 0
    ):
        raise ValueError("min_samples must be a positive integer")
    return int(min_samples)


def _class_counts(y: np.ndarray) -> dict[str, int]:
    counts = np.bincount(y.astype(int), minlength=2)
    return {"0": int(counts[0]), "1": int(counts[1])}


def _partition_metadata(
    *,
    status: PartitionStatus,
    sample_count: int,
    class_counts: dict[str, int],
    smote_status: str,
    fallback_reason: str | None,
    original_class_counts: dict[str, int] | None = None,
    resampled_class_counts: dict[str, int] | None = None,
    smote_k_neighbors: int | None = None,
    smote_failure_reason: str | None = None,
) -> dict[str, object]:
    return {
        "status": status,
        "sample_count": sample_count,
        "class_counts": class_counts,
        "smote_status": smote_status,
        "fallback_reason": fallback_reason,
        "original_class_counts": original_class_counts or class_counts,
        "resampled_class_counts": resampled_class_counts,
        "smote_k_neighbors": smote_k_neighbors,
        "smote_failure_reason": smote_failure_reason,
    }


def train_partition_models(
    X: object,
    y: object,
    cluster_ids: object,
    min_samples: int = PARTITION_MIN_SAMPLES,
) -> PartitionModels:
    """Fit one pooled RF and every eligible cluster-specific RF."""
    matrix = _as_training_matrix(X)
    target = _as_binary_target(y, expected_rows=len(matrix))
    normalized_clusters = _normalize_cluster_ids(
        cluster_ids,
        expected_rows=len(matrix),
    )
    minimum = _validate_min_samples(min_samples)

    pooled_model = RandomForestClassifier(**RF_PARAMS)
    pooled_model.fit(matrix, target)

    partition_models: dict[int, RandomForestClassifier | None] = {}
    partition_status: dict[int, PartitionStatus] = {}
    partition_metadata: dict[int, dict] = {}

    mapped_cluster_ids = sorted(
        {
            int(cluster_id)
            for cluster_id in normalized_clusters
            if cluster_id is not None
        }
    )
    for cluster_id in mapped_cluster_ids:
        mask = np.fromiter(
            (value == cluster_id for value in normalized_clusters),
            dtype=bool,
            count=len(normalized_clusters),
        )
        X_partition = matrix[mask]
        y_partition = target[mask]
        sample_count = len(y_partition)
        class_counts = _class_counts(y_partition)

        if sample_count < minimum:
            status: PartitionStatus = "pooled_small_partition"
            partition_models[cluster_id] = None
            partition_status[cluster_id] = status
            partition_metadata[cluster_id] = _partition_metadata(
                status=status,
                sample_count=sample_count,
                class_counts=class_counts,
                smote_status="not_applicable_small_partition",
                fallback_reason=f"sample_count_lt_{minimum}",
            )
            continue

        if np.count_nonzero(np.asarray(list(class_counts.values()))) == 1:
            status = "pooled_single_class"
            partition_models[cluster_id] = None
            partition_status[cluster_id] = status
            partition_metadata[cluster_id] = _partition_metadata(
                status=status,
                sample_count=sample_count,
                class_counts=class_counts,
                smote_status="not_applicable_single_class",
                fallback_reason="single_class_partition",
            )
            continue

        train_X = X_partition
        train_y = y_partition
        minority_count = int(
            np.bincount(y_partition.astype(int), minlength=2).min()
        )
        smote_status = "skipped_minority_lt_2"
        resampled_counts: dict[str, int] | None = None
        smote_k_neighbors: int | None = None
        smote_failure_reason: str | None = None
        if minority_count >= 2:
            smote_k_neighbors = min(
                SMOTE_MAX_NEIGHBORS,
                minority_count - 1,
            )
            try:
                train_X, train_y = SMOTE(
                    random_state=RF_PARAMS["random_state"],
                    k_neighbors=smote_k_neighbors,
                ).fit_resample(X_partition, y_partition)
                train_X = np.asarray(train_X, dtype=np.float64)
                train_y = np.asarray(train_y, dtype=np.int8)
                resampled_counts = _class_counts(train_y)
                smote_status = "resampled"
            except Exception as exc:  # imbalanced-learn failure must be non-fatal
                train_X = X_partition
                train_y = y_partition
                smote_status = "failed"
                smote_failure_reason = f"{type(exc).__name__}: {exc}"

        model = RandomForestClassifier(**RF_PARAMS)
        model.fit(train_X, train_y)
        status = "partition_model"
        partition_models[cluster_id] = model
        partition_status[cluster_id] = status
        partition_metadata[cluster_id] = _partition_metadata(
            status=status,
            sample_count=sample_count,
            class_counts=class_counts,
            smote_status=smote_status,
            fallback_reason=None,
            original_class_counts=class_counts,
            resampled_class_counts=resampled_counts,
            smote_k_neighbors=smote_k_neighbors,
            smote_failure_reason=smote_failure_reason,
        )

    return PartitionModels(
        pooled_model=pooled_model,
        partition_models=partition_models,
        partition_status=partition_status,
        partition_metadata=partition_metadata,
    )


def _with_expected_clusters(
    models: PartitionModels,
    expected_cluster_ids: Iterable[int],
    *,
    min_samples: int,
) -> PartitionModels:
    partition_models = dict(models.partition_models)
    partition_status = dict(models.partition_status)
    partition_metadata = dict(models.partition_metadata)
    for cluster_id in sorted({int(value) for value in expected_cluster_ids}):
        if cluster_id in partition_status:
            continue
        status: PartitionStatus = "pooled_small_partition"
        class_counts = {"0": 0, "1": 0}
        partition_models[cluster_id] = None
        partition_status[cluster_id] = status
        partition_metadata[cluster_id] = _partition_metadata(
            status=status,
            sample_count=0,
            class_counts=class_counts,
            smote_status="not_applicable_small_partition",
            fallback_reason=f"sample_count_lt_{min_samples}",
        )
    return PartitionModels(
        pooled_model=models.pooled_model,
        partition_models=partition_models,
        partition_status=partition_status,
        partition_metadata=partition_metadata,
    )


def _assert_partition_asset_identity() -> None:
    actual_sha256 = hashlib.sha256(PARTITION_ASSET_PATH.read_bytes()).hexdigest()
    if actual_sha256 != PARTITION_ASSET_SHA256:
        raise ValueError(
            "partition asset SHA-256 mismatch: "
            f"expected {PARTITION_ASSET_SHA256}, got {actual_sha256}"
        )


def _validate_horizon_key(horizon_key: str) -> int:
    months_by_key = {key: months for months, key in HORIZON_KEYS.items()}
    if horizon_key not in months_by_key:
        raise ValueError(
            "horizon_key must be one of "
            + ", ".join(months_by_key)
        )
    return months_by_key[horizon_key]


def _validate_exact_training_window(
    training: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    fit, validation = split_threshold_window(
        training,
        validation_months=THRESHOLD_VALIDATION_MONTHS,
    )
    combined = pd.concat([fit, validation], ignore_index=True)
    target_periods = sorted(combined[TARGET_MONTH_COLUMN].unique())
    if len(target_periods) != TRAIN_WINDOW_MONTHS:
        raise ValueError(
            "training frame must contain exactly one inclusive "
            f"{TRAIN_WINDOW_MONTHS}-target_month window"
        )
    expected_periods = list(
        pd.period_range(
            target_periods[0],
            periods=TRAIN_WINDOW_MONTHS,
            freq="M",
        )
    )
    if target_periods != expected_periods:
        raise ValueError(
            "training frame must contain one contiguous inclusive "
            f"{TRAIN_WINDOW_MONTHS}-target_month window"
        )
    return fit, validation, combined


def _month_range(frame: pd.DataFrame) -> dict[str, str]:
    return {
        "start": str(frame[TARGET_MONTH_COLUMN].min()),
        "end": str(frame[TARGET_MONTH_COLUMN].max()),
    }


def _fallback_counts(
    statuses: dict[int, PartitionStatus],
) -> dict[str, int]:
    fallback_states = (
        "pooled_unmapped",
        "pooled_small_partition",
        "pooled_single_class",
        "pooled_missing_partition_model",
    )
    return {
        state: sum(status == state for status in statuses.values())
        for state in fallback_states
    }


def train_horizon_model(
    aligned_frame: pd.DataFrame,
    feature_contract: FeatureContract,
    partition_map: PartitionMap,
    horizon_key: str,
) -> HorizonTrainingResult:
    """Select a threshold on 30 months and refit the final 36-month model."""
    horizon_months = _validate_horizon_key(horizon_key)
    _assert_partition_asset_identity()
    if not isinstance(aligned_frame, pd.DataFrame):
        raise TypeError("aligned_frame must be a pandas.DataFrame")
    if not isinstance(feature_contract, FeatureContract):
        raise TypeError("feature_contract must be a FeatureContract")
    if not isinstance(partition_map, PartitionMap):
        raise TypeError("partition_map must be a PartitionMap")

    feature_columns = tuple(feature_contract.feature_columns)
    if not feature_columns or len(feature_columns) != len(set(feature_columns)):
        raise ValueError("feature_contract must contain unique feature names")
    required_columns = {
        ADMIN_CANONICAL_COLUMN,
        FEATURE_MONTH_COLUMN,
        TARGET_MONTH_COLUMN,
        TARGET_COLUMN,
        *feature_columns,
    }
    missing_columns = sorted(required_columns - set(aligned_frame.columns))
    if missing_columns:
        raise ValueError(
            f"aligned_frame is missing required columns: {missing_columns}"
        )

    fit, validation, training = _validate_exact_training_window(aligned_frame)
    misaligned = training[TARGET_MONTH_COLUMN].ne(
        training[FEATURE_MONTH_COLUMN] + horizon_months
    )
    if misaligned.any():
        raise ValueError(
            "aligned_frame feature_month and target_month do not match "
            f"horizon_key {horizon_key}"
        )
    coverage_pct = partition_map.assert_release_coverage(
        training[ADMIN_CANONICAL_COLUMN]
    )

    fit_X_raw = fit.loc[:, list(feature_columns)].to_numpy()
    fit_y = _as_binary_target(fit[TARGET_COLUMN], expected_rows=len(fit))
    fit_clusters = partition_map.route(fit[ADMIN_CANONICAL_COLUMN]).to_numpy(
        dtype=object
    )
    temporary_imputer = MaxPlusImputer(multiplier=100.0)
    fit_X = temporary_imputer.fit_transform(fit_X_raw)
    temporary_models = train_partition_models(
        fit_X,
        fit_y,
        fit_clusters,
        min_samples=PARTITION_MIN_SAMPLES,
    )

    validation_X = temporary_imputer.transform(
        validation.loc[:, list(feature_columns)].to_numpy()
    )
    validation_y = _as_binary_target(
        validation[TARGET_COLUMN],
        expected_rows=len(validation),
    )
    validation_clusters = partition_map.route(
        validation[ADMIN_CANONICAL_COLUMN]
    ).to_numpy(dtype=object)
    validation_probability = predict_partition_probabilities(
        temporary_models.partition_models,
        temporary_models.pooled_model,
        validation_X,
        validation_clusters,
    )
    threshold_result = select_max_f1_threshold(
        validation_y,
        validation_probability,
    )

    final_X_raw = training.loc[:, list(feature_columns)].to_numpy()
    final_y = _as_binary_target(
        training[TARGET_COLUMN],
        expected_rows=len(training),
    )
    final_clusters = partition_map.route(
        training[ADMIN_CANONICAL_COLUMN]
    ).to_numpy(dtype=object)
    final_imputer = MaxPlusImputer(multiplier=100.0)
    final_X = final_imputer.fit_transform(final_X_raw)
    final_models = train_partition_models(
        final_X,
        final_y,
        final_clusters,
        min_samples=PARTITION_MIN_SAMPLES,
    )
    final_models = _with_expected_clusters(
        final_models,
        partition_map.cluster_ids,
        min_samples=PARTITION_MIN_SAMPLES,
    )

    predictor = PartitionedRFPredictor(
        imputer=final_imputer,
        pooled_model=final_models.pooled_model,
        partition_models=final_models.partition_models,
        partition_status=final_models.partition_status,
        partition_metadata=final_models.partition_metadata,
        partition_map=dict(partition_map._clusters_by_admin),
        feature_contract=feature_contract,
        threshold=threshold_result.threshold,
        horizon_key=horizon_key,
        horizon_months=horizon_months,
    )

    cluster_states = {
        str(cluster_id): {
            "status": metadata["status"],
            "sample_count": metadata["sample_count"],
            "class_counts": metadata["class_counts"],
            "smote_status": metadata["smote_status"],
            "fallback_reason": metadata["fallback_reason"],
        }
        for cluster_id, metadata in final_models.partition_metadata.items()
    }
    smote_results = {
        str(cluster_id): {
            "status": metadata["smote_status"],
            "original_class_counts": metadata["original_class_counts"],
            "resampled_class_counts": metadata["resampled_class_counts"],
            "failure_reason": metadata["smote_failure_reason"],
        }
        for cluster_id, metadata in final_models.partition_metadata.items()
    }
    training_report = {
        "schema_version": "fewsnet-horizon-training-report-v1",
        "horizon_key": horizon_key,
        "horizon_months": horizon_months,
        "feature_schema_sha256": feature_contract.feature_schema_sha256,
        "partition_asset_sha256": PARTITION_ASSET_SHA256,
        "partition_coverage_pct": coverage_pct,
        "training_target_month_range": _month_range(training),
        "fit_target_month_range": _month_range(fit),
        "validation_target_month_range": _month_range(validation),
        "sample_count": len(training),
        "fit_sample_count": len(fit),
        "validation_sample_count": len(validation),
        "pooled_class_counts": _class_counts(final_y),
        "cluster_states": cluster_states,
        "smote_results": smote_results,
        "fallback_counts": _fallback_counts(final_models.partition_status),
    }
    return HorizonTrainingResult(
        predictor=predictor,
        training_report=training_report,
        threshold_report=asdict(threshold_result),
    )
