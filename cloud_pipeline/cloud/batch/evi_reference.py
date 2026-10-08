from __future__ import annotations

import pandas as pd


_KEY_COLUMNS = ["area_id", "year", "month"]


def compare_evi_reference(
    observed: pd.DataFrame | None,
    reference: pd.DataFrame | None,
    *,
    value_column: str = "EVI_mean",
) -> dict:
    if observed is None or reference is None:
        return {"status": "not_provided"}
    required = set(_KEY_COLUMNS + [value_column])
    if not required <= set(observed.columns) or not required <= set(reference.columns):
        return {"status": "malformed_reference", "severity": "warning"}
    merged = observed[_KEY_COLUMNS + [value_column]].merge(
        reference[_KEY_COLUMNS + [value_column]],
        on=_KEY_COLUMNS,
        how="inner",
        suffixes=("_observed", "_reference"),
    )
    if merged.empty:
        return {
            "status": "zero_matches",
            "severity": "warning",
            "matched_observations": 0,
        }
    observed_col = f"{value_column}_observed"
    reference_col = f"{value_column}_reference"
    diffs = (merged[observed_col] - merged[reference_col]).abs()
    if len(merged) < 2:
        return {
            "status": "insufficient_pairs",
            "severity": "warning",
            "matched_observations": len(merged),
            "max_abs_diff": float(diffs.max()),
        }
    correlation = merged[observed_col].corr(merged[reference_col])
    return {
        "status": "advisory_difference" if float(diffs.max()) > 0 else "matched",
        "severity": "warning" if float(diffs.max()) > 0 else "none",
        "matched_observations": len(merged),
        "max_abs_diff": float(diffs.max()),
        "correlation": None if pd.isna(correlation) else float(correlation),
    }
