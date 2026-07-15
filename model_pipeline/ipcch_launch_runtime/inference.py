"""Model scoring and cumulative phase decoding for launch inference."""

import math
from typing import Mapping

import pandas as pd

from model_pipeline.ipcch_launch_runtime.population import POPULATION_OUTPUT_COLUMNS
from model_pipeline.ipcch_launch_runtime.uncertainty import (
    UncertaintyError,
    calculate_qualitative_uncertainty,
)


REQUIRED_TARGETS = (
    "phase2_worse",
    "phase3_worse",
    "phase4_worse",
    "phase5_worse",
)
SCORE_COLUMNS = tuple("{0}_score".format(target) for target in REQUIRED_TARGETS)
PRED_COLUMNS = tuple("{0}_pred".format(target) for target in REQUIRED_TARGETS)


class InferenceError(ValueError):
    """Raised when launch inference inputs or model outputs are invalid."""


def score_scope(
    *,
    monthly_rows: pd.DataFrame,
    feature_matrix: pd.DataFrame,
    models: Mapping[str, object],
    thresholds: Mapping[str, float],
    scope_months: int,
    feature_month: str,
    target_month: str,
    model_package_id: str,
    source_input: str,
    monotonicity_policy: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Score one launch scope and decode cumulative phase predictions."""
    _validate_inputs(
        monthly_rows,
        feature_matrix,
        models,
        thresholds,
        monotonicity_policy,
        feature_month,
    )

    output = _identity_frame(monthly_rows)
    applied_thresholds = {}

    for target in REQUIRED_TARGETS:
        model = models[target]
        score_column = "{0}_score".format(target)
        score = _predict_scores(model, feature_matrix, target)
        threshold = _threshold_for(target, score_column, thresholds)

        output[score_column] = score
        output["{0}_pred".format(target)] = (score >= threshold).astype("int64")
        applied_thresholds[target] = threshold

    uncertainty_fields, uncertainty_summary = calculate_qualitative_uncertainty(
        output, applied_thresholds
    )
    for column in uncertainty_fields.columns:
        output[column] = uncertainty_fields[column]

    _apply_monotonicity_policy(output, monotonicity_policy)
    output["overall_phase_pred"] = _decode_overall_phase(output)
    output["feature_period"] = str(feature_month)
    output["target_period"] = str(target_month)
    output["scope_months"] = int(scope_months)
    output["model_package_id"] = str(model_package_id)
    output["source_input"] = str(source_input)

    summary = {
        "status": "passed",
        "scope_months": int(scope_months),
        "feature_month": str(feature_month),
        "target_month": str(target_month),
        "thresholds": applied_thresholds,
        "monotonicity_policy": monotonicity_policy,
        "row_count": int(len(feature_matrix)),
        "score_columns": list(SCORE_COLUMNS),
        "pred_columns": list(PRED_COLUMNS),
        "uncertainty": uncertainty_summary,
    }
    return output, summary


def _validate_inputs(
    monthly_rows,
    feature_matrix,
    models,
    thresholds,
    monotonicity_policy,
    feature_month,
):
    if not isinstance(monthly_rows, pd.DataFrame):
        raise InferenceError("monthly_rows must be a pandas DataFrame")
    if not isinstance(feature_matrix, pd.DataFrame):
        raise InferenceError("feature_matrix must be a pandas DataFrame")
    if len(monthly_rows) != len(feature_matrix):
        raise InferenceError("monthly_rows and feature_matrix length mismatch")
    if not monthly_rows.index.equals(feature_matrix.index):
        raise InferenceError("monthly_rows and feature_matrix indexes must match")
    if not isinstance(models, Mapping):
        raise InferenceError("models must be a mapping")
    if not isinstance(thresholds, Mapping):
        raise InferenceError("thresholds must be a mapping")
    if monotonicity_policy not in ("fail", "cummax"):
        raise InferenceError("monotonicity_policy must be 'fail' or 'cummax'")

    missing_population = [
        column for column in POPULATION_OUTPUT_COLUMNS if column not in monthly_rows.columns
    ]
    if missing_population:
        raise InferenceError(
            "Missing required population column(s): {0}".format(
                ", ".join(missing_population)
            )
        )

    population = pd.to_numeric(monthly_rows["population_estimate"], errors="coerce")
    if (
        population.isna().any()
        or not population.map(_is_finite).all()
        or (population < 0).any()
    ):
        raise InferenceError("population_estimate must be finite and non-negative")

    references = pd.to_datetime(
        monthly_rows["population_reference_period"],
        format="%Y-%m",
        errors="coerce",
    )
    feature_period = pd.Timestamp(str(feature_month) + "-01")
    if references.isna().any() or (references > feature_period).any():
        raise InferenceError(
            "population_reference_period must not be later than feature_month"
        )
    expected_methods = references.map(
        lambda value: (
            "observed_feature_month"
            if value == feature_period
            else "last_observation_carried_forward"
        )
    )
    if not expected_methods.equals(monthly_rows["population_imputation_method"]):
        raise InferenceError(
            "population_imputation_method does not match reference period"
        )

    missing = [target for target in REQUIRED_TARGETS if target not in models]
    if missing:
        raise InferenceError("Missing required model(s): {0}".format(", ".join(missing)))

    for target in REQUIRED_TARGETS:
        if not hasattr(models[target], "predict"):
            raise InferenceError("Model {0} does not provide predict()".format(target))


def _identity_frame(monthly_rows):
    identity_columns = [
        column
        for column in (
            "area_id",
            "admin_code",
            "_row_id",
            *POPULATION_OUTPUT_COLUMNS,
        )
        if column in monthly_rows.columns
    ]
    return monthly_rows.loc[:, identity_columns].reset_index(drop=True).copy()


def _predict_scores(model, feature_matrix, target):
    try:
        raw_scores = model.predict(feature_matrix)
    except Exception as exc:
        raise InferenceError("Model {0} prediction failed: {1}".format(target, exc)) from exc

    try:
        series = pd.Series(raw_scores)
    except Exception as exc:
        raise InferenceError("Model {0} score output is not one-dimensional".format(target)) from exc

    if len(series) != len(feature_matrix):
        raise InferenceError(
            "Model {0} score length {1} does not match feature_matrix length {2}".format(
                target, len(series), len(feature_matrix)
            )
        )

    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.isna().any():
        raise InferenceError("Model {0} scores must be numeric and finite".format(target))
    if not numeric.map(_is_finite).all():
        raise InferenceError("Model {0} scores must be numeric and finite".format(target))
    return numeric.astype("float64").reset_index(drop=True)


def _is_finite(value):
    return math.isfinite(float(value))


def _threshold_for(target, score_column, thresholds):
    if target in thresholds:
        value = thresholds[target]
    elif score_column in thresholds:
        value = thresholds[score_column]
    elif "default" in thresholds:
        value = thresholds["default"]
    else:
        raise InferenceError(
            "Missing threshold for {0}; provide {0}, {1}, or default".format(
                target, score_column
            )
        )

    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric) or not _is_finite(numeric):
        raise InferenceError("Threshold for {0} must be numeric and finite".format(target))
    return float(numeric)


def _apply_monotonicity_policy(output, monotonicity_policy):
    if monotonicity_policy == "cummax":
        pairs = zip(reversed(PRED_COLUMNS[:-1]), reversed(PRED_COLUMNS[1:]))
        for lower_column, higher_column in pairs:
            output[lower_column] = output[[lower_column, higher_column]].max(axis=1)
        return

    violations = pd.Series(False, index=output.index)
    for lower_column, higher_column in zip(PRED_COLUMNS[:-1], PRED_COLUMNS[1:]):
        violations = violations | (
            (output[higher_column].astype("int64") > output[lower_column].astype("int64"))
        )
    if violations.any():
        raise InferenceError(
            "Non-monotonic cumulative predictions in {0} row(s)".format(
                int(violations.sum())
            )
        )


def _decode_overall_phase(output):
    phase = pd.Series(1, index=output.index, dtype="int64")
    for phase_number, pred_column in (
        (2, "phase2_worse_pred"),
        (3, "phase3_worse_pred"),
        (4, "phase4_worse_pred"),
        (5, "phase5_worse_pred"),
    ):
        phase = phase.mask(output[pred_column].astype("int64") == 1, phase_number)
    return phase
