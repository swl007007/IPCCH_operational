"""Local inference for the FEWSNET fixed-partition Random Forest suite."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from fewsnet_partitioned_rf_pipeline.config import (
    ADMIN_CANONICAL_COLUMN,
    HORIZON_KEYS,
)
from fewsnet_partitioned_rf_pipeline.core.data import normalize_admin_code
from fewsnet_partitioned_rf_pipeline.core.preprocessing import MaxPlusImputer
from fewsnet_partitioned_rf_pipeline.core.types import (
    FeatureContract,
    PartitionStatus,
)


FEATURE_MONTH_COLUMN = "feature_month"
TARGET_MONTH_COLUMN = "target_month"
FORMAL_PREDICTION_COLUMNS = (
    ADMIN_CANONICAL_COLUMN,
    FEATURE_MONTH_COLUMN,
    TARGET_MONTH_COLUMN,
    "horizon_months",
    "probability_crisis",
    "predicted_crisis",
    "threshold",
    "cluster_id",
    "prediction_source",
    "suite_version",
    "vertex_model_resource_name",
    "vertex_model_version_id",
)


def _as_prediction_matrix(X: object) -> np.ndarray:
    try:
        matrix = np.asarray(X, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("X must be a 2-D numeric array") from exc
    if matrix.ndim != 2:
        raise ValueError("X must be a 2-D numeric array")
    return matrix


def _cluster_id_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        raise ValueError("cluster_ids must contain integers or missing values")
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError(
            "cluster_ids must contain integers or missing values"
        ) from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError("cluster_ids must contain integers or missing values")
    return int(number)


def _normalize_cluster_ids(
    cluster_ids: object,
    *,
    expected_rows: int,
) -> np.ndarray:
    values = np.asarray(cluster_ids, dtype=object)
    if values.ndim != 1:
        raise ValueError("cluster_ids must be one-dimensional")
    if len(values) != expected_rows:
        raise ValueError("cluster_ids must have one value per X row")
    return np.asarray(
        [_cluster_id_or_none(value) for value in values],
        dtype=object,
    )


def _class_one_probability(
    model: RandomForestClassifier,
    X: np.ndarray,
) -> np.ndarray:
    probabilities = np.asarray(model.predict_proba(X), dtype=np.float64)
    if probabilities.ndim != 2 or probabilities.shape[0] != len(X):
        raise ValueError("predict_proba returned an invalid probability matrix")
    classes = np.asarray(model.classes_)
    class_one_columns = np.flatnonzero(classes == 1)
    if class_one_columns.size == 0:
        return np.zeros(len(X), dtype=np.float64)
    if class_one_columns.size != 1:
        raise ValueError("model classes contain duplicate class-1 entries")
    return probabilities[:, int(class_one_columns[0])]


def predict_partition_probabilities(
    partition_models: Mapping[int, RandomForestClassifier | None],
    pooled_model: RandomForestClassifier,
    X: object,
    cluster_ids: object,
) -> np.ndarray:
    """Route rows to partition models with pooled fallback, preserving order."""
    matrix = _as_prediction_matrix(X)
    normalized_clusters = _normalize_cluster_ids(
        cluster_ids,
        expected_rows=len(matrix),
    )
    normalized_models = {
        _cluster_id_or_none(cluster_id): model
        for cluster_id, model in partition_models.items()
    }
    if None in normalized_models:
        raise ValueError("partition_models keys must be integer cluster IDs")

    result = np.empty(len(matrix), dtype=np.float64)
    unmapped_mask = np.fromiter(
        (cluster_id is None for cluster_id in normalized_clusters),
        dtype=bool,
        count=len(normalized_clusters),
    )
    if unmapped_mask.any():
        result[unmapped_mask] = _class_one_probability(
            pooled_model,
            matrix[unmapped_mask],
        )

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
        model = normalized_models.get(cluster_id) or pooled_model
        result[mask] = _class_one_probability(model, matrix[mask])
    return result


def _format_months(values: pd.Series, name: str) -> list[str]:
    formatted: list[str] = []
    invalid: list[str] = []
    for value in values:
        candidate = value.strip() if isinstance(value, str) else value
        try:
            missing = bool(pd.isna(candidate))
        except (TypeError, ValueError):
            missing = False
        if missing or (isinstance(candidate, str) and candidate == ""):
            invalid.append(str(value))
            continue
        try:
            formatted.append(str(pd.Period(candidate, freq="M")))
        except (TypeError, ValueError):
            invalid.append(str(value))
    if invalid:
        raise ValueError(f"{name} contains invalid or missing values: {invalid[:5]}")
    return formatted


@dataclass(frozen=True)
class PartitionedRFPredictor:
    """Serializable composite predictor with fixed partition routing."""

    imputer: MaxPlusImputer
    pooled_model: RandomForestClassifier
    partition_models: dict[int, RandomForestClassifier | None]
    partition_status: dict[int, PartitionStatus]
    partition_metadata: dict[int, dict]
    partition_map: dict[str, int]
    feature_contract: FeatureContract
    threshold: float
    horizon_key: str
    horizon_months: int
    suite_version: str = ""
    vertex_model_resource_name: str = ""
    vertex_model_version_id: str = ""

    def __post_init__(self) -> None:
        expected_key = HORIZON_KEYS.get(self.horizon_months)
        if expected_key is None or self.horizon_key != expected_key:
            raise ValueError("horizon_key and horizon_months do not match")
        threshold = float(self.threshold)
        if not np.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be finite and between 0 and 1")
        feature_columns = tuple(self.feature_contract.feature_columns)
        if not feature_columns or len(feature_columns) != len(set(feature_columns)):
            raise ValueError("feature contract must contain unique feature names")

    def predict_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Return the exact formal local prediction record columns."""
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("frame must be a pandas.DataFrame")
        column_names = [str(name) for name in frame.columns]
        duplicate_names = sorted(
            {name for name in column_names if column_names.count(name) > 1}
        )
        if duplicate_names:
            raise ValueError(f"frame contains duplicate columns: {duplicate_names}")

        feature_columns = tuple(self.feature_contract.feature_columns)
        required_columns = {
            ADMIN_CANONICAL_COLUMN,
            FEATURE_MONTH_COLUMN,
            *feature_columns,
        }
        missing_columns = sorted(required_columns - set(frame.columns))
        if missing_columns:
            raise ValueError(f"frame is missing required columns: {missing_columns}")

        admin_codes = frame[ADMIN_CANONICAL_COLUMN].map(normalize_admin_code)
        if admin_codes.eq("").any():
            raise ValueError("admin_code contains missing or blank values")
        feature_months = _format_months(
            frame[FEATURE_MONTH_COLUMN],
            FEATURE_MONTH_COLUMN,
        )
        expected_target_months = [
            str(pd.Period(month, freq="M") + self.horizon_months)
            for month in feature_months
        ]
        if TARGET_MONTH_COLUMN in frame.columns:
            target_months = _format_months(
                frame[TARGET_MONTH_COLUMN],
                TARGET_MONTH_COLUMN,
            )
            if target_months != expected_target_months:
                raise ValueError(
                    "target_month values do not match the predictor horizon"
                )
        else:
            target_months = expected_target_months

        matrix = self.imputer.transform(
            frame.loc[:, list(feature_columns)].to_numpy()
        )
        cluster_values = np.asarray(
            [self.partition_map.get(admin_code) for admin_code in admin_codes],
            dtype=object,
        )
        probabilities = predict_partition_probabilities(
            self.partition_models,
            self.pooled_model,
            matrix,
            cluster_values,
        )

        sources: list[PartitionStatus] = []
        for cluster_id in cluster_values:
            if cluster_id is None:
                sources.append("pooled_unmapped")
                continue
            model = self.partition_models.get(int(cluster_id))
            if model is not None:
                sources.append("partition_model")
                continue
            status = self.partition_status.get(int(cluster_id))
            if status in {"pooled_small_partition", "pooled_single_class"}:
                sources.append(status)
            else:
                sources.append("pooled_missing_partition_model")

        predicted = (probabilities >= float(self.threshold)).astype(np.int8)
        output = pd.DataFrame(
            {
                ADMIN_CANONICAL_COLUMN: admin_codes.tolist(),
                FEATURE_MONTH_COLUMN: feature_months,
                TARGET_MONTH_COLUMN: target_months,
                "horizon_months": self.horizon_months,
                "probability_crisis": probabilities,
                "predicted_crisis": predicted,
                "threshold": float(self.threshold),
                "cluster_id": pd.array(cluster_values, dtype="Int64"),
                "prediction_source": sources,
                "suite_version": self.suite_version,
                "vertex_model_resource_name": self.vertex_model_resource_name,
                "vertex_model_version_id": self.vertex_model_version_id,
            }
        )
        return output.loc[:, list(FORMAL_PREDICTION_COLUMNS)]
