from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import math
from types import SimpleNamespace
from tempfile import NamedTemporaryFile

import pandas as pd

from cloud.common.reports import build_validation_report
from cloud.orchestrator.assembly import _normalize_identifier
from model_pipeline.ipcch_launch_runtime.population import POPULATION_OUTPUT_COLUMNS
from tools.validate_ipcch_schema import validate as validate_ipcch_schema


class BaseInputValidationError(ValueError):
    """Raised when assembled base input fails a hard gate."""


def validate_base_input(
    *,
    base_input: pd.DataFrame,
    scaffold: pd.DataFrame,
    feature_month: str,
) -> dict:
    key = ["area_id", "year", "month"]
    year, month = (int(part) for part in feature_month.split("-"))
    base_input = _normalize_area_id(base_input)
    scaffold = _normalize_area_id(scaffold)
    for frame_name, frame in (("base input", base_input), ("scaffold", scaffold)):
        missing = [column for column in key if column not in frame.columns]
        if missing:
            raise BaseInputValidationError(
                f"{frame_name} missing key columns: {missing}"
            )
        blank_counts = _blank_key_counts(frame, key)
        if any(count for count in blank_counts.values()):
            raise BaseInputValidationError(
                f"{frame_name} contains blank required keys: {blank_counts}"
            )
    if not ((base_input["year"] == year) & (base_input["month"] == month)).all():
        raise BaseInputValidationError("base input selected month mismatch")
    base_keys = set(map(tuple, base_input[key].itertuples(index=False, name=None)))
    scaffold_keys = set(map(tuple, scaffold[key].itertuples(index=False, name=None)))
    if base_keys != scaffold_keys:
        raise BaseInputValidationError("base input row universe must match scaffold")
    duplicate_key_count = int(base_input.duplicated(key).sum())
    if duplicate_key_count:
        raise BaseInputValidationError("base input contains duplicate keys")
    population_selection = _validate_population_output(base_input, feature_month)
    schema_result = _validate_model_input_forecast_schema(base_input)
    return build_validation_report(
        report_type="base_input_validation_report",
        feature_month=feature_month,
        run_id="local-base-input-validation",
        status="passed",
        scaffold_row_count=len(scaffold),
        base_input_row_count=len(base_input),
        row_universe_match=True,
        key_columns=key,
        duplicate_key_count=0,
        missing_key_counts={
            column: int(base_input[column].isna().sum()) for column in key
        },
        schema_result=schema_result,
        population_selection=population_selection,
        join_coverage={},
        missingness={},
    )


def _validate_population_output(base_input: pd.DataFrame, feature_month: str) -> dict:
    required = list(POPULATION_OUTPUT_COLUMNS)
    missing = [column for column in required if column not in base_input.columns]
    if missing:
        raise BaseInputValidationError(
            f"base input missing population output columns: {missing}"
        )
    values = pd.to_numeric(base_input["population_estimate"], errors="coerce")
    if values.isna().any() or not values.map(math.isfinite).all() or (values < 0).any():
        raise BaseInputValidationError(
            "population_estimate must be finite and non-negative"
        )
    references = pd.to_datetime(
        base_input["population_reference_period"], format="%Y-%m", errors="coerce"
    )
    feature_period = pd.Timestamp(feature_month + "-01")
    if references.isna().any() or (references > feature_period).any():
        raise BaseInputValidationError(
            "population_reference_period must not be later than feature_month"
        )
    expected_methods = references.map(
        lambda value: (
            "observed_feature_month"
            if value == feature_period
            else "last_observation_carried_forward"
        )
    )
    if not base_input.empty and not expected_methods.equals(
        base_input["population_imputation_method"]
    ):
        raise BaseInputValidationError(
            "population_imputation_method does not match reference period"
        )
    return {
        "observed_feature_month_rows": int(
            (expected_methods == "observed_feature_month").sum()
        ),
        "last_observation_carried_forward_rows": int(
            (expected_methods == "last_observation_carried_forward").sum()
        ),
    }


def _normalize_area_id(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "area_id" not in result.columns and "admin_code" in result.columns:
        result["area_id"] = result["admin_code"].map(_normalize_identifier)
    elif "area_id" not in result.columns:
        return result
    result["area_id"] = result["area_id"].map(_normalize_identifier)
    if "admin_code" in result.columns:
        normalized_admin = result["admin_code"].map(_normalize_identifier)
        if not (result["area_id"].fillna("") == normalized_admin.fillna("")).all():
            raise BaseInputValidationError(
                "area_id must equal normalized admin_code when both exist"
            )
    return result


def _validate_model_input_forecast_schema(base_input: pd.DataFrame) -> dict:
    with NamedTemporaryFile(
        mode="w", suffix=".csv", encoding="utf-8", newline="", delete=True
    ) as handle:
        base_input.to_csv(handle.name, index=False)
        args = SimpleNamespace(
            csv=handle.name,
            mode="model-input-forecast",
            max_duplicate_examples=5,
        )
        output = StringIO()
        with redirect_stdout(output):
            exit_code = validate_ipcch_schema(args)
    status = "passed" if exit_code == 0 else "failed"
    result = {
        "mode": "model-input-forecast",
        "status": status,
        "output": output.getvalue().strip(),
    }
    if exit_code != 0:
        raise BaseInputValidationError(f"schema validation failed: {result['output']}")
    return result


def _blank_key_counts(frame: pd.DataFrame, key_columns: list[str]) -> dict[str, int]:
    counts = {}
    for column in key_columns:
        series = frame[column]
        blank_strings = series.astype(str).str.strip().eq("")
        counts[column] = int(series.isna().sum() + blank_strings.sum())
    return counts
