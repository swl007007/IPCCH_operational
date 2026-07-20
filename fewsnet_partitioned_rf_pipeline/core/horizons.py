from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral

import pandas as pd

from fewsnet_partitioned_rf_pipeline.config import (
    ADMIN_CANONICAL_COLUMN,
    HORIZON_MONTHS,
    TARGET_COLUMN,
)
from fewsnet_partitioned_rf_pipeline.core.data import normalize_admin_code


FEATURE_MONTH_COLUMN = "feature_month"
TARGET_MONTH_COLUMN = "target_month"


@dataclass(frozen=True)
class AlignmentResult:
    frame: pd.DataFrame
    dropped_rows_by_reason: dict[str, int]


def _validate_horizon(horizon_months: int) -> int:
    if (
        isinstance(horizon_months, bool)
        or not isinstance(horizon_months, Integral)
        or int(horizon_months) not in HORIZON_MONTHS
    ):
        raise ValueError("horizon_months must be one of 0, 6, and 12")
    return int(horizon_months)


def _validate_positive_integer(value: int, name: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, Integral)
        or int(value) <= 0
    ):
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def _normalize_month_values(values: pd.Series, name: str) -> pd.Series:
    parsed: list[pd.Period] = []
    invalid_examples: list[str] = []
    for value in values:
        candidate = value.strip() if isinstance(value, str) else value
        try:
            is_missing = bool(pd.isna(candidate))
        except (TypeError, ValueError):
            is_missing = False
        if is_missing or (isinstance(candidate, str) and candidate == ""):
            invalid_examples.append(str(value))
            continue
        try:
            period = pd.Period(candidate, freq="M")
        except (TypeError, ValueError):
            invalid_examples.append(str(value))
            continue
        if pd.isna(period):
            invalid_examples.append(str(value))
            continue
        parsed.append(period)

    if invalid_examples:
        raise ValueError(
            f"{name} contains invalid or missing values: "
            f"{invalid_examples[:5]}"
        )
    return pd.Series(
        pd.PeriodIndex(parsed, freq="M"),
        index=values.index,
        name=values.name,
    )


def _normalize_month_value(value: object, name: str) -> pd.Period:
    try:
        return _normalize_month_values(
            pd.Series([value], dtype="object"),
            name,
        ).iloc[0]
    except ValueError as exc:
        raise ValueError(
            f"{name} contains an invalid or missing value"
        ) from exc


def _prepare_feature_frame(
    feature_frame: pd.DataFrame,
    *,
    require_target: bool,
) -> pd.DataFrame:
    if not isinstance(feature_frame, pd.DataFrame):
        raise TypeError("feature_frame must be a pandas.DataFrame")
    required_columns = {ADMIN_CANONICAL_COLUMN, FEATURE_MONTH_COLUMN}
    if require_target:
        required_columns.add(TARGET_COLUMN)
    missing_columns = sorted(required_columns - set(feature_frame.columns))
    if missing_columns:
        raise ValueError(
            f"feature_frame is missing required columns: {missing_columns}"
        )

    working = feature_frame.copy()
    working[ADMIN_CANONICAL_COLUMN] = working[ADMIN_CANONICAL_COLUMN].map(
        normalize_admin_code
    )
    if working[ADMIN_CANONICAL_COLUMN].eq("").any():
        raise ValueError("admin_code contains missing or blank values")
    working[FEATURE_MONTH_COLUMN] = _normalize_month_values(
        working[FEATURE_MONTH_COLUMN],
        FEATURE_MONTH_COLUMN,
    )
    duplicate_keys = working.duplicated(
        [ADMIN_CANONICAL_COLUMN, FEATURE_MONTH_COLUMN],
        keep=False,
    )
    if duplicate_keys.any():
        examples = (
            working.loc[
                duplicate_keys,
                [ADMIN_CANONICAL_COLUMN, FEATURE_MONTH_COLUMN],
            ]
            .drop_duplicates()
            .head(5)
            .astype(str)
            .to_dict("records")
        )
        raise ValueError(
            "duplicate admin_code + feature_month keys are not allowed: "
            f"{examples}"
        )
    return working


def _prepare_aligned_frame(aligned: pd.DataFrame) -> pd.DataFrame:
    working = _prepare_feature_frame(aligned, require_target=True)
    if TARGET_MONTH_COLUMN not in working.columns:
        raise ValueError(
            f"aligned frame is missing required column: {TARGET_MONTH_COLUMN}"
        )
    working[TARGET_MONTH_COLUMN] = _normalize_month_values(
        working[TARGET_MONTH_COLUMN],
        TARGET_MONTH_COLUMN,
    )
    return working


def _sort_aligned_rows(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values(
        [ADMIN_CANONICAL_COLUMN, FEATURE_MONTH_COLUMN, TARGET_MONTH_COLUMN],
        kind="stable",
    ).reset_index(drop=True)


def align_horizon(
    feature_frame: pd.DataFrame,
    horizon_months: int,
) -> AlignmentResult:
    horizon = _validate_horizon(horizon_months)
    working = _prepare_feature_frame(feature_frame, require_target=True)

    target = working[
        [ADMIN_CANONICAL_COLUMN, FEATURE_MONTH_COLUMN, TARGET_COLUMN]
    ].rename(columns={FEATURE_MONTH_COLUMN: TARGET_MONTH_COLUMN})
    features = working.drop(columns=[TARGET_COLUMN])
    features[TARGET_MONTH_COLUMN] = (
        features[FEATURE_MONTH_COLUMN] + horizon
    )

    merged = features.merge(
        target,
        on=[ADMIN_CANONICAL_COLUMN, TARGET_MONTH_COLUMN],
        how="left",
        sort=False,
        validate="one_to_one",
        indicator=True,
    )
    missing_target = merged["_merge"].eq("left_only")
    null_target = merged["_merge"].eq("both") & merged[TARGET_COLUMN].isna()
    aligned = (
        merged.loc[~missing_target & ~null_target]
        .drop(columns=["_merge"])
        .sort_values(
            [ADMIN_CANONICAL_COLUMN, FEATURE_MONTH_COLUMN],
            kind="stable",
        )
        .reset_index(drop=True)
    )
    return AlignmentResult(
        frame=aligned,
        dropped_rows_by_reason={
            "missing_target_row": int(missing_target.sum()),
            "null_target_value": int(null_target.sum()),
        },
    )


def select_training_window(
    aligned: pd.DataFrame,
    latest_label_month: object,
    months: int = 36,
) -> pd.DataFrame:
    month_count = _validate_positive_integer(months, "months")
    end = _normalize_month_value(latest_label_month, "latest_label_month")
    start = end - (month_count - 1)
    working = _prepare_aligned_frame(aligned)
    selected = working.loc[
        working[TARGET_MONTH_COLUMN].between(start, end)
    ].copy()
    return _sort_aligned_rows(selected)


def split_threshold_window(
    training: pd.DataFrame,
    validation_months: int = 6,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    validation_count = _validate_positive_integer(
        validation_months,
        "validation_months",
    )
    working = _prepare_aligned_frame(training)
    target_periods = sorted(working[TARGET_MONTH_COLUMN].unique())
    minimum_period_count = validation_count + 1
    if len(target_periods) < minimum_period_count:
        raise ValueError(
            "training requires at least "
            f"{minimum_period_count} distinct target_month periods for a "
            f"{validation_count}-period validation split"
        )

    validation_periods = set(target_periods[-validation_count:])
    validation_mask = working[TARGET_MONTH_COLUMN].isin(validation_periods)
    fit = _sort_aligned_rows(working.loc[~validation_mask].copy())
    validation = _sort_aligned_rows(working.loc[validation_mask].copy())
    return fit, validation


def select_latest_inference_frame(
    feature_frame: pd.DataFrame,
    latest_feature_month: object,
    horizon_months: int,
) -> pd.DataFrame:
    horizon = _validate_horizon(horizon_months)
    latest = _normalize_month_value(
        latest_feature_month,
        "latest_feature_month",
    )
    working = _prepare_feature_frame(feature_frame, require_target=False)
    authoritative_admin_codes = set(working[ADMIN_CANONICAL_COLUMN].unique())
    selected = working.loc[
        working[FEATURE_MONTH_COLUMN].eq(latest)
    ].copy()
    selected_admin_codes = set(selected[ADMIN_CANONICAL_COLUMN].unique())
    missing_admin_codes = sorted(
        authoritative_admin_codes - selected_admin_codes
    )
    unexpected_admin_codes = sorted(
        selected_admin_codes - authoritative_admin_codes
    )
    if missing_admin_codes:
        raise ValueError(
            f"latest feature month {latest} is missing authoritative "
            f"admin_code values: {missing_admin_codes}"
        )
    if (
        unexpected_admin_codes
        or len(selected) != len(authoritative_admin_codes)
    ):
        raise ValueError(
            f"latest feature month {latest} does not match the authoritative "
            "admin_code universe; "
            f"missing={missing_admin_codes}; "
            f"unexpected={unexpected_admin_codes}; "
            f"expected_rows={len(authoritative_admin_codes)}; "
            f"actual_rows={len(selected)}"
        )

    selected[TARGET_MONTH_COLUMN] = selected[FEATURE_MONTH_COLUMN] + horizon
    return selected.sort_values(
        [ADMIN_CANONICAL_COLUMN, FEATURE_MONTH_COLUMN],
        kind="stable",
    ).reset_index(drop=True)
