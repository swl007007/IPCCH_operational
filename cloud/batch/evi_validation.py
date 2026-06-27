from __future__ import annotations

import pandas as pd

from cloud.common.reports import build_validation_report


class EVIValidationError(ValueError):
    """Raised when EVI output artifacts fail hard contract checks."""


def build_evi_validation_report(
    *,
    feature_month: str,
    run_id: str,
    mean_wide: pd.DataFrame,
    std_wide: pd.DataFrame,
    mean_long: pd.DataFrame,
    std_long: pd.DataFrame,
    scaffold_area_ids: list[str],
    reference_comparison: dict,
) -> dict:
    year, month = (int(part) for part in feature_month.split("-"))
    month_col = f"{year}_{month:02d}"
    _require_columns(mean_wide, ["region_id", month_col], "mean wide")
    _require_columns(std_wide, ["region_id", month_col], "std wide")
    _require_columns(mean_long, ["area_id", "year", "month", "EVI_mean"], "mean long")
    _require_columns(std_long, ["area_id", "year", "month", "EVI_std"], "std long")

    scaffold_set = set(scaffold_area_ids)
    if (
        set(mean_wide["region_id"]) != scaffold_set
        or set(std_wide["region_id"]) != scaffold_set
    ):
        raise EVIValidationError("wide output row count or area identity mismatch")
    if (
        set(mean_long["area_id"]) != scaffold_set
        or set(std_long["area_id"]) != scaffold_set
    ):
        raise EVIValidationError("long output row count or area identity mismatch")
    if len(mean_long) != len(scaffold_area_ids) or len(std_long) != len(
        scaffold_area_ids
    ):
        raise EVIValidationError("long output row count must match scaffold")
    if not ((mean_long["year"] == year) & (mean_long["month"] == month)).all():
        raise EVIValidationError("mean long selected month mismatch")
    if not ((std_long["year"] == year) & (std_long["month"] == month)).all():
        raise EVIValidationError("std long selected month mismatch")

    warning_statuses = {
        "advisory_difference",
        "malformed_reference",
        "zero_matches",
        "insufficient_pairs",
    }
    has_warning = reference_comparison.get("status") in warning_statuses
    return build_validation_report(
        report_type="evi_validation_report",
        feature_month=feature_month,
        run_id=run_id,
        status="passed_with_warnings" if has_warning else "passed",
        output_contract_status="passed",
        wide_outputs={
            "mean_rows": len(mean_wide),
            "std_rows": len(std_wide),
            "selected_month_column": month_col,
        },
        long_outputs={"row_count": len(mean_long), "std_row_count": len(std_long)},
        area_identity={
            "region_id_equals_area_id": True,
            "scaffold_area_count": len(scaffold_area_ids),
        },
        reference_comparison=reference_comparison,
        advisory_warnings=[reference_comparison] if has_warning else [],
    )


def _require_columns(frame: pd.DataFrame, columns: list[str], label: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise EVIValidationError(f"{label} missing columns: {missing}")
