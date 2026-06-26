"""Monthly production input validation for pure inference.

Documented null tokens are normalized to ``pandas.NA`` before validation:
empty string, whitespace-only strings, ``NA``, ``N/A``, ``NULL``, ``null``,
``NaN``, ``nan``, ``None``, and ``#N/A``.
"""

import re

import pandas as pd


NULL_TOKENS = frozenset(["", "NA", "N/A", "NULL", "null", "NaN", "nan", "None", "#N/A"])
FEATURE_MONTH_PATTERN = re.compile(r"^(\d{4})-?(\d{2})$")


class InputContractError(ValueError):
    """Raised when a monthly production input violates the runtime contract."""


def validate_monthly_input(input_df, feature_month):
    """Validate one monthly production inference input.

    Parameters
    ----------
    input_df : pandas.DataFrame
        Monthly feature input with ``year``/``month`` plus ``area_id`` or
        ``admin_code``.
    feature_month : str
        CLI feature month argument in ``YYYY-MM`` or ``YYYYMM`` form.

    Returns
    -------
    tuple[pandas.DataFrame, dict]
        Validated DataFrame and a machine-readable report.
    """
    if not isinstance(input_df, pd.DataFrame):
        raise InputContractError("Input must be a pandas DataFrame")

    expected_year, expected_month = _parse_feature_month(feature_month)
    input_columns = list(input_df.columns)
    if "_row_id" in input_columns:
        raise InputContractError("_row_id is reserved for runtime row identity")

    df = _normalize_null_tokens(input_df.copy())
    df.insert(0, "_row_id", range(len(df)))

    _require_columns(df, ["year", "month"])
    _validate_feature_month(df, expected_year, expected_month)
    _validate_and_prepare_ids(df)

    report = _build_report(df, input_columns, expected_year, expected_month)
    return df, report


def _parse_feature_month(feature_month):
    value = str(feature_month)
    match = FEATURE_MONTH_PATTERN.match(value)
    if not match:
        raise InputContractError("feature_month must use YYYY-MM or YYYYMM format")
    year = int(match.group(1))
    month = int(match.group(2))
    if month < 1 or month > 12:
        raise InputContractError("feature_month month must be between 01 and 12")
    return year, month


def _normalize_null_tokens(df):
    def normalize(value):
        if isinstance(value, str) and value.strip() in NULL_TOKENS:
            return pd.NA
        return value

    return df.apply(lambda column: column.map(normalize))


def _require_columns(df, columns):
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise InputContractError("Missing required column(s): {0}".format(", ".join(missing)))


def _validate_feature_month(df, expected_year, expected_month):
    years = _integer_series(df["year"], "year")
    months = _integer_series(df["month"], "month")
    if ((months < 1) | (months > 12)).any():
        raise InputContractError("month must be between 1 and 12")

    unique_months = set(zip(years.tolist(), months.tolist()))

    if len(unique_months) != 1:
        raise InputContractError("Input must contain exactly one feature month")

    actual_year, actual_month = next(iter(unique_months))
    if (actual_year, actual_month) != (expected_year, expected_month):
        raise InputContractError(
            "feature_month {0:04d}-{1:02d} does not match input {2:04d}-{3:02d}".format(
                expected_year, expected_month, actual_year, actual_month
            )
        )

    df["year"] = years
    df["month"] = months


def _integer_series(series, column_name):
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.isna().any():
        raise InputContractError("{0} must be nonmissing integers".format(column_name))
    if not (numeric % 1 == 0).all():
        raise InputContractError("{0} must be nonmissing integers".format(column_name))
    return numeric.astype("int64")


def _validate_and_prepare_ids(df):
    has_area_id = "area_id" in df.columns
    has_admin_code = "admin_code" in df.columns
    if not has_area_id and not has_admin_code:
        raise InputContractError("Input must contain area_id or admin_code")

    if has_area_id:
        df["area_id"] = _string_key_series(df["area_id"], "area_id")
    if has_admin_code:
        df["admin_code"] = _string_key_series(df["admin_code"], "admin_code")

    if has_area_id and has_admin_code:
        mismatch = df["area_id"] != df["admin_code"]
        if mismatch.any():
            raise InputContractError("area_id/admin_code mismatch in input rows")
    elif has_admin_code:
        df["area_id"] = df["admin_code"]

    if df["area_id"].duplicated().any():
        duplicate_ids = sorted(df.loc[df["area_id"].duplicated(keep=False), "area_id"].unique())
        raise InputContractError(
            "Duplicate area_id values for feature month: {0}".format(", ".join(duplicate_ids))
        )


def _string_key_series(series, column_name):
    if series.isna().any():
        raise InputContractError("{0} must be nonmissing".format(column_name))
    return series.map(lambda value: str(value).strip())


def _build_report(df, input_columns, expected_year, expected_month):
    null_counts = {
        column: int(count)
        for column, count in df.isna().sum().items()
        if int(count) > 0
    }
    return {
        "status": "passed",
        "feature_month": "{0:04d}-{1:02d}".format(expected_year, expected_month),
        "row_count": int(len(df)),
        "unique_area_count": int(df["area_id"].nunique(dropna=True)),
        "input_columns": input_columns,
        "coverage": {
            "area_id_nonmissing": int(df["area_id"].notna().sum()),
            "area_id_missing": int(df["area_id"].isna().sum()),
            "null_counts": null_counts,
        },
    }
