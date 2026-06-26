"""Runtime feature matrix construction from packaged launch contracts."""

from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd


class FeatureContractError(ValueError):
    """Raised when a packaged feature contract cannot build a model matrix."""


def apply_feature_contract(
    monthly_input: pd.DataFrame,
    contract: pd.DataFrame,
    feature_columns: Sequence[str],
    *,
    package_root: Path,
    metadata: Mapping[str, object],
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Build a model feature matrix in the exact packaged feature order."""
    if not isinstance(monthly_input, pd.DataFrame):
        raise FeatureContractError("monthly_input must be a pandas DataFrame")
    if not isinstance(contract, pd.DataFrame):
        raise FeatureContractError("contract must be a pandas DataFrame")
    if isinstance(feature_columns, (str, bytes)) or not isinstance(
        feature_columns, Sequence
    ):
        raise FeatureContractError("feature_columns must be a sequence of feature names")
    if not isinstance(metadata, Mapping):
        raise FeatureContractError("metadata must be a mapping")

    package_root = Path(package_root)
    requested_features = [str(feature) for feature in feature_columns]
    if len(requested_features) != len(set(requested_features)):
        raise FeatureContractError("feature_columns contains duplicate feature names")

    contract = contract.copy()
    feature_name_column = _require_contract_column(
        contract, ["model_feature", "feature", "feature_name", "feature_column"]
    )
    category_column = _require_contract_column(contract, ["category", "feature_category"])
    source_column = _optional_contract_column(
        contract, ["source_column", "input_column", "lookup_column"]
    )
    dtype_column = _optional_contract_column(
        contract, ["dtype", "declared_dtype", "feature_dtype"]
    )
    required_column = _optional_contract_column(
        contract, ["required_in_input", "required"]
    )
    lookup_asset_column = _optional_contract_column(contract, ["lookup_asset"])
    tolerance_column = _optional_contract_column(
        contract, ["missing_tolerance", "missing_rate_tolerance"]
    )
    fill_key_column = _optional_contract_column(
        contract, ["fill_value_or_stat_key", "imputation_stat_key", "stat_key"]
    )
    supported_column = _optional_contract_column(contract, ["supported"])
    status_column = _optional_contract_column(contract, ["status"])

    contract["_feature_name"] = contract[feature_name_column].map(_clean_string)
    if contract["_feature_name"].isna().any() or (contract["_feature_name"] == "").any():
        raise FeatureContractError("Contract feature names must be nonmissing")

    duplicate_names = sorted(
        contract.loc[contract["_feature_name"].duplicated(keep=False), "_feature_name"]
        .dropna()
        .unique()
        .tolist()
    )
    if duplicate_names:
        raise FeatureContractError(
            "Duplicate contract feature row(s): {0}".format(", ".join(duplicate_names))
        )

    contract_by_feature = contract.set_index("_feature_name", drop=False)
    missing_features = [
        feature for feature in requested_features if feature not in contract_by_feature.index
    ]
    if missing_features:
        raise FeatureContractError(
            "Missing model feature(s) in contract: {0}".format(
                ", ".join(missing_features)
            )
        )

    ignored_contract_features = sorted(
        feature
        for feature in contract_by_feature.index.tolist()
        if feature not in set(requested_features)
    )

    matrix_columns = {}
    filled_features = []
    feature_details = {}
    warnings = []
    lookup_cache = {}

    for feature_name in requested_features:
        row = contract_by_feature.loc[feature_name]
        category = _normalize_category(row[category_column])
        if _is_feature_excluded(row, supported_column, status_column, category):
            raise FeatureContractError(
                "Model feature {0} is unsupported or excluded".format(feature_name)
            )

        dtype = _clean_string(row[dtype_column]) if dtype_column else "float"
        if not dtype:
            dtype = "float"
        source = _clean_string(row[source_column]) if source_column else ""
        required_in_input = _required_in_input(row, required_column, category)
        tolerance = _missing_tolerance(row, tolerance_column)

        series, fill_method, filled, pre_fill_missing_rate = _construct_feature(
            monthly_input=monthly_input,
            row=row,
            feature_name=feature_name,
            category=category,
            source_column=source,
            required_in_input=required_in_input,
            package_root=package_root,
            metadata=metadata,
            lookup_asset_column=lookup_asset_column,
            fill_key_column=fill_key_column,
            lookup_cache=lookup_cache,
        )

        coerced = _coerce_dtype(series, dtype, feature_name)
        missing_rate = _missing_rate(coerced)
        if missing_rate > tolerance:
            raise FeatureContractError(
                "Feature {0} missing rate {1:.6f} exceeds tolerance {2:.6f}".format(
                    feature_name, missing_rate, tolerance
                )
            )

        matrix_columns[feature_name] = coerced
        if filled:
            filled_features.append(feature_name)
        feature_details[feature_name] = {
            "category": category,
            "source_column": source,
            "dtype": dtype,
            "required_in_input": bool(required_in_input),
            "missing_tolerance": float(tolerance),
            "pre_fill_missing_rate": float(pre_fill_missing_rate),
            "post_fill_missing_rate": float(missing_rate),
            "missing_rate": float(missing_rate),
            "fill_method": fill_method,
            "filled": bool(filled),
        }

    matrix = pd.DataFrame(matrix_columns, index=monthly_input.index)
    report = {
        "status": "passed",
        "feature_count": len(requested_features),
        "filled_features": filled_features,
        "ignored_contract_features": ignored_contract_features,
        "warnings": warnings,
        "features": feature_details,
    }
    return matrix.loc[:, requested_features], report


def _construct_feature(
    *,
    monthly_input,
    row,
    feature_name,
    category,
    source_column,
    required_in_input,
    package_root,
    metadata,
    lookup_asset_column,
    fill_key_column,
    lookup_cache,
):
    if category == "required":
        if not source_column:
            raise FeatureContractError("Feature {0} missing source column".format(feature_name))
        if required_in_input and source_column not in monthly_input.columns:
            raise FeatureContractError(
                "Required source column {0} missing for feature {1}".format(
                    source_column, feature_name
                )
            )
        if source_column not in monthly_input.columns:
            series = pd.Series(pd.NA, index=monthly_input.index)
            return series, "none", False, _missing_rate(series)
        series = monthly_input[source_column].copy()
        return series, "none", False, _missing_rate(series)

    if category in ("static_join", "carry_forward"):
        fill_method = "carry forward" if category == "carry_forward" else "static_join"
        series = _lookup_series(
            monthly_input=monthly_input,
            row=row,
            feature_name=feature_name,
            source_column=source_column,
            package_root=package_root,
            lookup_asset_column=lookup_asset_column,
            lookup_cache=lookup_cache,
        )
        return series, fill_method, True, _missing_rate(series)

    if category == "median_impute":
        return _median_impute_series(
            monthly_input=monthly_input,
            row=row,
            feature_name=feature_name,
            source_column=source_column,
            required_in_input=required_in_input,
            metadata=metadata,
            fill_key_column=fill_key_column,
        )

    if category == "derived":
        raise FeatureContractError(
            "Derived feature {0} is not supported by this runtime".format(feature_name)
        )

    raise FeatureContractError(
        "Feature {0} has unsupported category {1}".format(feature_name, category)
    )


def _lookup_series(
    *,
    monthly_input,
    row,
    feature_name,
    source_column,
    package_root,
    lookup_asset_column,
    lookup_cache,
):
    if "area_id" not in monthly_input.columns:
        raise FeatureContractError(
            "area_id is required in monthly_input for lookup feature {0}".format(
                feature_name
            )
        )
    if not source_column:
        raise FeatureContractError(
            "Lookup feature {0} missing source column".format(feature_name)
        )
    lookup_asset = _clean_string(row[lookup_asset_column]) if lookup_asset_column else ""
    if not lookup_asset:
        raise FeatureContractError(
            "Lookup feature {0} missing lookup_asset".format(feature_name)
        )

    lookup_path = _package_relative_path(package_root, lookup_asset)
    if lookup_path in lookup_cache:
        lookup = lookup_cache[lookup_path]
    else:
        try:
            lookup = pd.read_csv(lookup_path, dtype={"area_id": "string"})
        except FileNotFoundError as exc:
            raise FeatureContractError(
                "Lookup asset not found for feature {0}: {1}".format(
                    feature_name, lookup_asset
                )
            ) from exc
        if "area_id" not in lookup.columns:
            raise FeatureContractError(
                "Lookup asset {0} missing column area_id for feature {1}".format(
                    lookup_asset, feature_name
                )
            )
        lookup["area_id"] = lookup["area_id"].map(lambda value: str(value).strip())
        if lookup["area_id"].duplicated().any():
            duplicates = sorted(
                lookup.loc[lookup["area_id"].duplicated(keep=False), "area_id"]
                .dropna()
                .unique()
                .tolist()
            )
            raise FeatureContractError(
                "Lookup asset {0} has duplicate area_id values: {1}".format(
                    lookup_asset, ", ".join(duplicates)
                )
            )
        lookup_cache[lookup_path] = lookup

    if source_column not in lookup.columns:
        raise FeatureContractError(
            "Lookup asset {0} missing column {1} for feature {2}".format(
                lookup_asset, source_column, feature_name
            )
        )

    area_ids = monthly_input["area_id"].map(lambda value: str(value).strip())
    joined = area_ids.map(lookup.set_index("area_id")[source_column])
    joined.index = monthly_input.index
    return joined


def _median_impute_series(
    *,
    monthly_input,
    row,
    feature_name,
    source_column,
    required_in_input,
    metadata,
    fill_key_column,
):
    fill_key = _clean_string(row[fill_key_column]) if fill_key_column else ""
    if not fill_key:
        raise FeatureContractError(
            "Median impute feature {0} missing fill_value_or_stat_key".format(
                feature_name
            )
        )
    stats = metadata.get("imputation_statistics")
    if not isinstance(stats, Mapping) or fill_key not in stats:
        raise FeatureContractError(
            "Missing imputation statistic {0} for feature {1}".format(
                fill_key, feature_name
            )
        )

    if source_column in monthly_input.columns:
        source = monthly_input[source_column].copy()
    elif required_in_input:
        raise FeatureContractError(
            "Required source column {0} missing for feature {1}".format(
                source_column, feature_name
            )
        )
    else:
        source = pd.Series(pd.NA, index=monthly_input.index)

    pre_fill_missing_rate = _missing_rate(source)
    filled = bool(source.isna().any())
    return source.fillna(stats[fill_key]), "median_impute", filled, pre_fill_missing_rate


def _coerce_dtype(series, dtype, feature_name):
    dtype_key = str(dtype).strip().lower().replace("_", "")
    if dtype_key in ("float", "float64", "double", "numeric"):
        return _numeric_series(series, feature_name).astype("float64")
    if dtype_key in ("integer", "int", "int64"):
        numeric = _numeric_series(series, feature_name)
        nonmissing = numeric.dropna()
        if not (nonmissing % 1 == 0).all():
            raise FeatureContractError(
                "Feature {0} cannot be coerced to integer".format(feature_name)
            )
        if numeric.isna().any():
            return numeric.astype("Int64")
        return numeric.astype("int64")
    if dtype_key in ("boolean", "bool"):
        return series.map(lambda value: _coerce_boolean(value, feature_name)).astype(
            "boolean"
        )
    if dtype_key in ("string", "str"):
        return series.map(lambda value: pd.NA if pd.isna(value) else str(value)).astype(
            "string"
        )
    if dtype_key in ("categorical", "category"):
        values = series.map(lambda value: pd.NA if pd.isna(value) else str(value))
        return values.astype("category")
    raise FeatureContractError(
        "Feature {0} has unsupported dtype {1}".format(feature_name, dtype)
    )


def _numeric_series(series, feature_name):
    numeric = pd.to_numeric(series, errors="coerce")
    invalid_mask = series.notna() & numeric.isna()
    if invalid_mask.any():
        invalid_values = [
            str(value)
            for value in series.loc[invalid_mask].drop_duplicates().head(5).tolist()
        ]
        raise FeatureContractError(
            "Feature {0} has invalid numeric value(s): {1}".format(
                feature_name, ", ".join(invalid_values)
            )
        )
    return numeric


def _coerce_boolean(value, feature_name):
    if pd.isna(value):
        return pd.NA
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("true", "t", "yes", "y", "1"):
            return True
        if normalized in ("false", "f", "no", "n", "0"):
            return False
    raise FeatureContractError(
        "Feature {0} cannot be coerced to boolean".format(feature_name)
    )


def _package_relative_path(package_root, lookup_asset):
    root = Path(package_root).resolve()
    path = (root / lookup_asset).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise FeatureContractError(
            "lookup_asset must be package-relative: {0}".format(lookup_asset)
        ) from exc
    return path


def _require_contract_column(contract, candidates):
    column = _optional_contract_column(contract, candidates)
    if column is None:
        raise FeatureContractError(
            "Contract missing required column; expected one of {0}".format(
                ", ".join(candidates)
            )
        )
    return column


def _optional_contract_column(contract, candidates):
    for column in candidates:
        if column in contract.columns:
            return column
    return None


def _clean_string(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_category(value):
    category = _clean_string(value).lower().replace("-", "_").replace(" ", "_")
    if category == "carryforward":
        return "carry_forward"
    if category in ("median", "medianimpute"):
        return "median_impute"
    return category


def _required_in_input(row, required_column, category):
    if category == "required":
        return True
    if required_column is None:
        return False
    value = row[required_column]
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes", "y")


def _missing_tolerance(row, tolerance_column):
    if tolerance_column is None or pd.isna(row[tolerance_column]) or row[tolerance_column] == "":
        return 0.0
    try:
        tolerance = float(row[tolerance_column])
    except (TypeError, ValueError) as exc:
        raise FeatureContractError("missing_tolerance must be numeric") from exc
    if tolerance < 0 or tolerance > 1:
        raise FeatureContractError("missing_tolerance must be between 0 and 1")
    return tolerance


def _is_feature_excluded(row, supported_column, status_column, category):
    if category in ("unsupported", "excluded"):
        return True
    if supported_column is not None and not _truthy(row[supported_column]):
        return True
    if status_column is not None:
        status = _clean_string(row[status_column]).lower()
        if status in ("unsupported", "excluded"):
            return True
    return False


def _truthy(value):
    if pd.isna(value):
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in ("false", "0", "no", "n", "excluded")


def _missing_rate(series):
    if len(series) == 0:
        return 0.0
    return float(series.isna().mean())
