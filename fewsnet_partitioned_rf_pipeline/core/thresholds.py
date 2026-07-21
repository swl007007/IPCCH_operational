from __future__ import annotations

import numpy as np
from sklearn.metrics import f1_score, precision_score, recall_score

from fewsnet_partitioned_rf_pipeline.config import THRESHOLD_GRID
from fewsnet_partitioned_rf_pipeline.core.types import ThresholdResult


def _fallback(
    reason: str,
    *,
    support: int,
    positive_cases: int,
) -> ThresholdResult:
    return ThresholdResult(
        threshold=0.50,
        precision=None,
        recall=None,
        f1=None,
        support=support,
        positive_cases=positive_cases,
        fallback_reason=reason,
    )


def select_max_f1_threshold(
    y_true: object,
    y_probability: object,
) -> ThresholdResult:
    true_values = np.asarray(y_true)
    probability_values = np.asarray(y_probability, dtype=np.float64)
    if true_values.ndim != 1 or probability_values.ndim != 1:
        raise ValueError("y_true and y_probability must be one-dimensional")
    if true_values.shape != probability_values.shape:
        raise ValueError("y_true and y_probability must have the same shape")

    finite_probability = np.isfinite(probability_values)
    finite_true = true_values[finite_probability]
    finite_probability_values = probability_values[finite_probability]
    support = int(finite_probability_values.size)
    positive_cases = int(np.count_nonzero(finite_true == 1))

    if support == 0:
        return _fallback(
            "no_validation_observations",
            support=support,
            positive_cases=positive_cases,
        )
    if positive_cases == 0:
        return _fallback(
            "no_validation_positive_cases",
            support=support,
            positive_cases=positive_cases,
        )

    results: list[ThresholdResult] = []
    for threshold in THRESHOLD_GRID:
        predicted = (finite_probability_values >= threshold).astype(np.int8)
        precision = float(
            precision_score(finite_true, predicted, zero_division=0)
        )
        recall = float(recall_score(finite_true, predicted, zero_division=0))
        f1 = float(f1_score(finite_true, predicted, zero_division=0))
        if np.isfinite(f1):
            results.append(
                ThresholdResult(
                    threshold=threshold,
                    precision=precision,
                    recall=recall,
                    f1=f1,
                    support=support,
                    positive_cases=positive_cases,
                    fallback_reason=None,
                )
            )

    if not results:
        return _fallback(
            "no_finite_validation_f1",
            support=support,
            positive_cases=positive_cases,
        )
    return max(results, key=lambda row: (row.f1, row.threshold))
