from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from fewsnet_partitioned_rf_pipeline.config import (
    ADMIN_CANONICAL_COLUMN,
    ADMIN_SOURCE_COLUMN,
    TARGET_COLUMN,
)
from fewsnet_partitioned_rf_pipeline.core.data import normalize_admin_code
from fewsnet_partitioned_rf_pipeline.core.types import FeatureContract


DROP_SOURCE_COLUMNS = {
    "unit_name",
    "ADMIN0",
    "ADMIN1",
    "ADMIN2",
    "ADMIN3",
    "ISO3",
    "fews_ipc_adjusted",
    "fews_proj_med_adjusted",
    "fews_proj_near",
    "fews_proj_near_ha",
    "fews_proj_med",
    "fews_proj_med_ha",
}

SCHEMA_VERSION = "fewsnet-feature-contract-v1"
TRANSFORMATION_VERSION = "stage3-direct-alignment-v1"
DATE_SOURCE_COLUMN = "date"
FEATURE_MONTH_COLUMN = "feature_month"
ISO_SOURCE_COLUMN = "ISO"
IPC_SOURCE_COLUMN = "fews_ipc"
YEAR_COLUMN = "years"
FEATURE_DTYPE = "float64"

TARGET_LAG_MONTHS = (4, 8, 12)
WFP_ROLLING_WINDOWS = (4, 12)
EVI_LAG_MONTHS = tuple(range(1, 13))

REFERENCE_REQUIRED_FEATURES = {
    ADMIN_SOURCE_COLUMN,
    "lat",
    "lon",
    "month",
    "fews_ha",
    "fews_ipc_crisis_lag_4",
    "fews_ipc_lag_12",
    "WFP_Price_m4",
    "WFP_Price_m12",
    "nightlight_m12",
    "EVI_l12",
}
REFERENCE_EXCLUDED_FEATURES = {
    TARGET_COLUMN,
    IPC_SOURCE_COLUMN,
    "fews_proj_med",
}

CORE_REQUIRED_SOURCE_COLUMNS = {
    ADMIN_SOURCE_COLUMN,
    ISO_SOURCE_COLUMN,
    "lat",
    "lon",
    "month",
    "fews_ha",
    "WFP_Price",
    "nightlight",
    "EVI",
    IPC_SOURCE_COLUMN,
    TARGET_COLUMN,
    DATE_SOURCE_COLUMN,
}
NON_FEATURE_SOURCE_COLUMNS = {
    ISO_SOURCE_COLUMN,
    DATE_SOURCE_COLUMN,
    TARGET_COLUMN,
    IPC_SOURCE_COLUMN,
}
REFERENCE_GROUP_COLUMNS = {
    "AEZ_group",
    "ISO_encoded",
    "AEZ_country_group",
}

YEAR_FEATURE_RE = re.compile(r"^year_(-?\d+)$")
MONTH_FEATURE_RE = re.compile(r"^month_(\d+)$")


def _canonical_json_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_columns_sha256(columns: Sequence[str]) -> str:
    return _canonical_json_sha256(list(columns))


def _feature_schema_sha256(
    columns: Sequence[str], dtypes: Sequence[str]
) -> str:
    return _canonical_json_sha256(
        [[name, dtype] for name, dtype in zip(columns, dtypes, strict=True)]
    )


def _duplicates(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    duplicate_names: set[str] = set()
    for value in values:
        if value in seen:
            duplicate_names.add(value)
        seen.add(value)
    return sorted(duplicate_names)


def _normalize_iso(value: object) -> str:
    if pd.isna(value):
        raise ValueError("ISO contains a missing value")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("ISO contains a blank value")
    return normalized


def _parse_feature_months(values: pd.Series) -> pd.Series:
    blank = values.astype("string").str.strip().eq("")
    parsed = pd.to_datetime(values.mask(blank), errors="coerce")
    invalid = parsed.isna()
    if invalid.any():
        examples = values.loc[invalid].astype(str).head(5).tolist()
        raise ValueError(f"date contains invalid or missing values: {examples}")
    return parsed.dt.to_period("M")


def _coerce_numeric(values: pd.Series, name: str) -> pd.Series:
    normalized = values.copy()
    if pd.api.types.is_object_dtype(normalized.dtype) or pd.api.types.is_string_dtype(
        normalized.dtype
    ):
        normalized = normalized.replace(r"^\s*$", np.nan, regex=True)
    converted = pd.to_numeric(normalized, errors="coerce")
    invalid = normalized.notna() & converted.isna()
    if invalid.any():
        examples = normalized.loc[invalid].astype(str).head(5).tolist()
        raise ValueError(
            f"predictor {name!r} contains non-coercible values: {examples}"
        )
    return converted.astype(FEATURE_DTYPE)


def _normalize_aez(values: pd.Series, name: str) -> pd.Series:
    normalized = values.copy()
    string_values = normalized.astype("string").str.strip().str.lower()
    true_mask = string_values.eq("true").fillna(False)
    false_mask = string_values.eq("false").fillna(False)
    normalized = normalized.mask(true_mask, 1.0).mask(false_mask, 0.0)
    return _coerce_numeric(normalized, name)


def _derived_feature_columns(
    years: Sequence[int], months: Sequence[int]
) -> tuple[str, ...]:
    return (
        YEAR_COLUMN,
        *(f"fews_ipc_crisis_lag_{lag}" for lag in TARGET_LAG_MONTHS),
        *(f"fews_ipc_lag_{lag}" for lag in TARGET_LAG_MONTHS),
        *(f"year_{year}" for year in sorted(years)),
        *(f"month_{month}" for month in sorted(months)),
        *(f"WFP_Price_m{window}" for window in WFP_ROLLING_WINDOWS),
        "nightlight_m12",
        *(f"EVI_l{lag}" for lag in EVI_LAG_MONTHS),
    )


def _expected_feature_columns(
    required_source_columns: Sequence[str],
    years: Sequence[int],
    months: Sequence[int],
) -> tuple[str, ...]:
    base_features = tuple(
        name
        for name in required_source_columns
        if name not in NON_FEATURE_SOURCE_COLUMNS
        and name not in REFERENCE_GROUP_COLUMNS
    )
    return base_features + _derived_feature_columns(years, months)


def _contract_categories(contract: FeatureContract) -> tuple[tuple[int, ...], tuple[int, ...]]:
    years: list[int] = []
    months: list[int] = []
    for name in contract.feature_columns:
        if match := YEAR_FEATURE_RE.fullmatch(name):
            years.append(int(match.group(1)))
        elif match := MONTH_FEATURE_RE.fullmatch(name):
            month = int(match.group(1))
            if not 1 <= month <= 12:
                raise ValueError(f"invalid month dummy in feature contract: {name}")
            months.append(month)
    if years != sorted(years) or len(years) != len(set(years)):
        raise ValueError("year dummy columns in feature contract are not sorted and unique")
    if months != sorted(months) or len(months) != len(set(months)):
        raise ValueError("month dummy columns in feature contract are not sorted and unique")
    if not years or not months:
        raise ValueError("feature contract must contain year and month dummy columns")
    return tuple(years), tuple(months)


def _validate_contract(contract: FeatureContract) -> tuple[tuple[int, ...], tuple[int, ...]]:
    if contract.schema_version != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported feature contract schema_version: {contract.schema_version}"
        )
    if contract.transformation_version != TRANSFORMATION_VERSION:
        raise ValueError(
            "unsupported feature contract transformation_version: "
            f"{contract.transformation_version}"
        )

    duplicate_features = _duplicates(contract.feature_columns)
    if duplicate_features:
        raise ValueError(
            "duplicate feature names in contract.feature_columns: "
            f"{duplicate_features}"
        )
    duplicate_sources = _duplicates(contract.required_source_columns)
    if duplicate_sources:
        raise ValueError(
            "duplicate names in contract.required_source_columns: "
            f"{duplicate_sources}"
        )
    if len(contract.feature_columns) != len(contract.feature_dtypes):
        raise ValueError("feature_columns and feature_dtypes lengths differ")
    unsupported_dtypes = sorted(set(contract.feature_dtypes) - {FEATURE_DTYPE})
    if unsupported_dtypes:
        raise ValueError(
            f"feature contract contains unsupported dtypes: {unsupported_dtypes}"
        )

    missing_sources = sorted(
        CORE_REQUIRED_SOURCE_COLUMNS - set(contract.required_source_columns)
    )
    if missing_sources:
        raise ValueError(
            f"feature contract is missing required raw names: {missing_sources}"
        )
    dropped_sources = sorted(
        set(contract.required_source_columns) & DROP_SOURCE_COLUMNS
    )
    if dropped_sources:
        raise ValueError(
            f"feature contract declares dropped raw names: {dropped_sources}"
        )

    years, months = _contract_categories(contract)
    expected_features = _expected_feature_columns(
        contract.required_source_columns,
        years,
        months,
    )
    if tuple(contract.feature_columns) != expected_features:
        expected_set = set(expected_features)
        actual_set = set(contract.feature_columns)
        raise ValueError(
            "feature contract names do not match deterministic Stage 3 schema; "
            f"unknown={sorted(actual_set - expected_set)}; "
            f"missing={sorted(expected_set - actual_set)}"
        )

    expected_source_sha = _source_columns_sha256(contract.required_source_columns)
    if contract.source_columns_sha256 != expected_source_sha:
        raise ValueError(
            "source column checksum mismatch: "
            f"expected {expected_source_sha}, got {contract.source_columns_sha256}"
        )
    expected_feature_sha = _feature_schema_sha256(
        contract.feature_columns,
        contract.feature_dtypes,
    )
    if contract.feature_schema_sha256 != expected_feature_sha:
        raise ValueError(
            "feature schema checksum mismatch: "
            f"expected {expected_feature_sha}, got {contract.feature_schema_sha256}"
        )

    sorted_iso_keys = sorted(contract.iso_mapping)
    expected_iso_mapping = {
        iso: index for index, iso in enumerate(sorted_iso_keys)
    }
    if contract.iso_mapping != expected_iso_mapping:
        raise ValueError("feature contract ISO mapping is not sorted and contiguous")
    return years, months


def add_calendar_lag(
    frame: pd.DataFrame,
    value_column: str,
    months: int,
    output_column: str,
) -> pd.DataFrame:
    right = frame[[ADMIN_CANONICAL_COLUMN, FEATURE_MONTH_COLUMN, value_column]].copy()
    right[FEATURE_MONTH_COLUMN] = right[FEATURE_MONTH_COLUMN] + months
    right = right.rename(columns={value_column: output_column})
    return frame.merge(
        right,
        on=[ADMIN_CANONICAL_COLUMN, FEATURE_MONTH_COLUMN],
        how="left",
        validate="one_to_one",
        sort=False,
    )


def _add_calendar_rolling_sum(
    frame: pd.DataFrame,
    value_column: str,
    window: int,
    output_column: str,
) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for admin_code, group in frame.groupby(ADMIN_CANONICAL_COLUMN, sort=True):
        values = group.set_index(FEATURE_MONTH_COLUMN)[value_column].sort_index()
        complete_index = pd.period_range(
            values.index.min(),
            values.index.max(),
            freq="M",
        )
        complete_values = values.reindex(complete_index)
        rolled = complete_values.shift(1).rolling(
            window=window,
            min_periods=window,
        ).sum()
        parts.append(
            pd.DataFrame(
                {
                    ADMIN_CANONICAL_COLUMN: admin_code,
                    FEATURE_MONTH_COLUMN: complete_index,
                    output_column: rolled.to_numpy(),
                }
            )
        )
    right = pd.concat(parts, ignore_index=True)
    return frame.merge(
        right,
        on=[ADMIN_CANONICAL_COLUMN, FEATURE_MONTH_COLUMN],
        how="left",
        validate="one_to_one",
        sort=False,
    )


class Stage3FeatureBuilder:
    """Build and enforce the frozen, horizon-neutral Stage 3 feature frame."""

    def fit(self, panel: pd.DataFrame) -> FeatureContract:
        if not isinstance(panel, pd.DataFrame):
            raise TypeError("panel must be a pandas.DataFrame")
        duplicate_columns = _duplicates(tuple(str(name) for name in panel.columns))
        if duplicate_columns:
            raise ValueError(f"panel contains duplicate column names: {duplicate_columns}")

        source_columns = tuple(
            str(name) for name in panel.columns if str(name) not in DROP_SOURCE_COLUMNS
        )
        missing_sources = sorted(CORE_REQUIRED_SOURCE_COLUMNS - set(source_columns))
        if missing_sources:
            raise ValueError(f"panel is missing required raw inputs: {missing_sources}")

        iso_values = sorted({_normalize_iso(value) for value in panel[ISO_SOURCE_COLUMN]})
        if not iso_values:
            raise ValueError("panel does not contain any ISO values")
        iso_mapping = {iso: index for index, iso in enumerate(iso_values)}

        feature_months = _parse_feature_months(panel[DATE_SOURCE_COLUMN])
        years = tuple(sorted({int(value) for value in feature_months.dt.year}))
        months = tuple(sorted({int(value) for value in feature_months.dt.month}))

        reserved_names = set(
            _derived_feature_columns(years, months)
        ) | REFERENCE_GROUP_COLUMNS
        collisions = sorted(set(source_columns) & reserved_names)
        if collisions:
            raise ValueError(
                f"raw source columns collide with derived Stage 3 names: {collisions}"
            )

        feature_columns = _expected_feature_columns(source_columns, years, months)
        feature_dtypes = (FEATURE_DTYPE,) * len(feature_columns)
        contract = FeatureContract(
            schema_version=SCHEMA_VERSION,
            transformation_version=TRANSFORMATION_VERSION,
            feature_columns=feature_columns,
            feature_dtypes=feature_dtypes,
            required_source_columns=source_columns,
            iso_mapping=iso_mapping,
            source_columns_sha256=_source_columns_sha256(source_columns),
            feature_schema_sha256=_feature_schema_sha256(
                feature_columns,
                feature_dtypes,
            ),
        )
        _validate_contract(contract)
        return contract

    def transform(
        self,
        panel: pd.DataFrame,
        contract: FeatureContract,
    ) -> pd.DataFrame:
        if not isinstance(panel, pd.DataFrame):
            raise TypeError("panel must be a pandas.DataFrame")
        allowed_years, allowed_months = _validate_contract(contract)

        duplicate_columns = _duplicates(tuple(str(name) for name in panel.columns))
        if duplicate_columns:
            raise ValueError(f"panel contains duplicate column names: {duplicate_columns}")
        missing_raw = sorted(set(contract.required_source_columns) - set(panel.columns))
        if missing_raw:
            raise ValueError(f"panel is missing required raw inputs: {missing_raw}")

        working = panel.loc[:, list(contract.required_source_columns)].copy()
        working.insert(0, "_row_order", np.arange(len(working), dtype=np.int64))
        working[ADMIN_CANONICAL_COLUMN] = working[ADMIN_SOURCE_COLUMN].map(
            normalize_admin_code
        )
        working[FEATURE_MONTH_COLUMN] = _parse_feature_months(
            working[DATE_SOURCE_COLUMN]
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

        iso_values = working[ISO_SOURCE_COLUMN].map(_normalize_iso)
        unseen_iso = sorted(set(iso_values) - set(contract.iso_mapping))
        if unseen_iso:
            raise ValueError(f"unseen ISO values: {unseen_iso}")
        working["ISO_encoded"] = iso_values.map(contract.iso_mapping).astype(
            FEATURE_DTYPE
        )

        panel_years = {int(value) for value in working[FEATURE_MONTH_COLUMN].dt.year}
        unseen_years = sorted(panel_years - set(allowed_years))
        if unseen_years:
            raise ValueError(f"unseen year dummy categories: {unseen_years}")
        panel_months = {
            int(value) for value in working[FEATURE_MONTH_COLUMN].dt.month
        }
        unseen_months = sorted(panel_months - set(allowed_months))
        if unseen_months:
            raise ValueError(f"unseen month dummy categories: {unseen_months}")

        base_feature_columns = [
            name
            for name in contract.required_source_columns
            if name not in NON_FEATURE_SOURCE_COLUMNS
            and name not in REFERENCE_GROUP_COLUMNS
        ]
        aez_columns = [name for name in base_feature_columns if name.startswith("AEZ_")]
        numeric_columns: dict[str, pd.Series] = {}
        for name in base_feature_columns:
            if name in aez_columns:
                numeric_columns[name] = _normalize_aez(working[name], name)
            else:
                numeric_columns[name] = _coerce_numeric(working[name], name)
        numeric_columns[TARGET_COLUMN] = _coerce_numeric(
            working[TARGET_COLUMN], TARGET_COLUMN
        )
        numeric_columns[IPC_SOURCE_COLUMN] = _coerce_numeric(
            working[IPC_SOURCE_COLUMN], IPC_SOURCE_COLUMN
        )
        working = pd.concat(
            [
                working.drop(columns=list(numeric_columns)),
                pd.DataFrame(numeric_columns, index=working.index),
            ],
            axis=1,
        )

        calendar_features: dict[str, pd.Series] = {
            YEAR_COLUMN: working[FEATURE_MONTH_COLUMN].dt.year.astype(FEATURE_DTYPE)
        }
        for year in allowed_years:
            calendar_features[f"year_{year}"] = (
                working[FEATURE_MONTH_COLUMN].dt.year == year
            ).astype(FEATURE_DTYPE)
        for month in allowed_months:
            calendar_features[f"month_{month}"] = (
                working[FEATURE_MONTH_COLUMN].dt.month == month
            ).astype(FEATURE_DTYPE)
        working = pd.concat(
            [working, pd.DataFrame(calendar_features, index=working.index)],
            axis=1,
        )

        for lag in TARGET_LAG_MONTHS:
            working = add_calendar_lag(
                working,
                TARGET_COLUMN,
                lag,
                f"fews_ipc_crisis_lag_{lag}",
            )
        for lag in TARGET_LAG_MONTHS:
            working = add_calendar_lag(
                working,
                IPC_SOURCE_COLUMN,
                lag,
                f"fews_ipc_lag_{lag}",
            )

        for window in WFP_ROLLING_WINDOWS:
            working = _add_calendar_rolling_sum(
                working,
                "WFP_Price",
                window,
                f"WFP_Price_m{window}",
            )
        working = _add_calendar_rolling_sum(
            working,
            "nightlight",
            12,
            "nightlight_m12",
        )
        for lag in EVI_LAG_MONTHS:
            working = add_calendar_lag(
                working,
                "EVI",
                lag,
                f"EVI_l{lag}",
            )

        if aez_columns:
            aez_group = working.groupby(
                aez_columns,
                dropna=False,
                sort=True,
            ).ngroup()
            aez_country_group = pd.DataFrame(
                {
                    "AEZ_group": aez_group,
                    "ISO_encoded": working["ISO_encoded"],
                },
                index=working.index,
            ).groupby(
                ["AEZ_group", "ISO_encoded"],
                dropna=False,
                sort=True,
            ).ngroup()
        else:
            aez_group = pd.Series(0, index=working.index)
            aez_country_group = pd.Series(0, index=working.index)
        working = pd.concat(
            [
                working,
                pd.DataFrame(
                    {
                        "AEZ_group": aez_group,
                        "AEZ_country_group": aez_country_group,
                    },
                    index=working.index,
                ),
            ],
            axis=1,
        )

        missing_generated = sorted(set(contract.feature_columns) - set(working.columns))
        if missing_generated:
            raise ValueError(
                f"frozen contract features could not be generated: {missing_generated}"
            )
        predictors = pd.DataFrame(
            {
                name: _coerce_numeric(working[name], name)
                for name in contract.feature_columns
            },
            index=working.index,
        )
        predictors = predictors.replace([np.inf, -np.inf], np.nan)

        identity = working.loc[
            :, ["_row_order", ADMIN_CANONICAL_COLUMN, FEATURE_MONTH_COLUMN, TARGET_COLUMN]
        ].copy()
        result = pd.concat(
            [identity.reset_index(drop=True), predictors.reset_index(drop=True)],
            axis=1,
        )
        result = result.sort_values("_row_order", kind="stable").drop(
            columns=["_row_order"]
        )
        return result.reset_index(drop=True)


class MaxPlusImputer:
    """Impute missing numeric values from per-column fit-slice maxima."""

    def __init__(self, multiplier: float = 100.0) -> None:
        self.multiplier = multiplier

    @staticmethod
    def _as_float64_2d(X: object) -> np.ndarray:
        try:
            array = np.asarray(X, dtype=np.float64)
        except (TypeError, ValueError) as exc:
            raise ValueError("X must be a 2-D numeric array") from exc
        if array.ndim != 2:
            raise ValueError("X must be a 2-D numeric array")
        return array.copy()

    def fit(self, X: object, y: object | None = None) -> MaxPlusImputer:
        del y
        fit_values = self._as_float64_2d(X)
        fit_values[np.isinf(fit_values)] = np.nan

        feature_count = fit_values.shape[1]
        feature_mins = np.full(feature_count, np.nan, dtype=np.float64)
        feature_maxs = np.full(feature_count, np.nan, dtype=np.float64)
        impute_values = np.zeros(feature_count, dtype=np.float64)
        multiplier = float(self.multiplier)

        for index in range(feature_count):
            finite_values = fit_values[~np.isnan(fit_values[:, index]), index]
            if finite_values.size == 0:
                continue
            minimum = float(np.min(finite_values))
            maximum = float(np.max(finite_values))
            feature_mins[index] = minimum
            feature_maxs[index] = maximum
            impute_values[index] = (
                multiplier if maximum == 0.0 else maximum * multiplier
            )

        self.n_features_in_ = feature_count
        self.feature_mins_ = feature_mins
        self.feature_maxs_ = feature_maxs
        self.impute_values_ = impute_values
        return self

    def transform(self, X: object) -> np.ndarray:
        if not hasattr(self, "n_features_in_"):
            raise RuntimeError("MaxPlusImputer must be fitted before transform")

        transformed = self._as_float64_2d(X)
        if transformed.shape[1] != self.n_features_in_:
            raise ValueError(
                "feature count differs from fitted data: "
                f"expected {self.n_features_in_}, got {transformed.shape[1]}"
            )
        transformed[np.isinf(transformed)] = np.nan
        return np.where(
            np.isnan(transformed),
            self.impute_values_,
            transformed,
        ).astype(np.float64, copy=False)

    def fit_transform(
        self,
        X: object,
        y: object | None = None,
    ) -> np.ndarray:
        return self.fit(X, y).transform(X)


def feature_contract_to_payload(contract: FeatureContract) -> dict[str, object]:
    return asdict(contract)


def feature_contract_from_payload(payload: dict[str, object]) -> FeatureContract:
    contract = FeatureContract(
        schema_version=str(payload["schema_version"]),
        transformation_version=str(payload["transformation_version"]),
        feature_columns=tuple(str(value) for value in payload["feature_columns"]),
        feature_dtypes=tuple(str(value) for value in payload["feature_dtypes"]),
        required_source_columns=tuple(
            str(value) for value in payload["required_source_columns"]
        ),
        iso_mapping={
            str(name): int(value)
            for name, value in dict(payload["iso_mapping"]).items()
        },
        source_columns_sha256=str(payload["source_columns_sha256"]),
        feature_schema_sha256=str(payload["feature_schema_sha256"]),
    )
    _validate_contract(contract)
    return contract


def load_feature_contract(path: str | Path) -> FeatureContract:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("feature contract JSON must contain an object")
    return feature_contract_from_payload(payload)


def write_feature_contract(contract: FeatureContract, path: str | Path) -> None:
    _validate_contract(contract)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            feature_contract_to_payload(contract),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _repeat_to_length(values: Sequence[object], length: int) -> list[object]:
    if not values:
        return [np.nan] * length
    return [values[index % len(values)] for index in range(length)]


def _read_contract_generation_frame(panel_path: Path) -> pd.DataFrame:
    header = pd.read_csv(panel_path, nrows=0, keep_default_na=False)
    columns = [str(name) for name in header.columns]
    missing = sorted({ISO_SOURCE_COLUMN, DATE_SOURCE_COLUMN} - set(columns))
    if missing:
        raise ValueError(f"panel is missing contract-generation columns: {missing}")

    iso_values: set[str] = set()
    feature_months: set[pd.Period] = set()
    for chunk in pd.read_csv(
        panel_path,
        usecols=[ISO_SOURCE_COLUMN, DATE_SOURCE_COLUMN],
        keep_default_na=False,
        chunksize=100_000,
    ):
        iso_values.update(_normalize_iso(value) for value in chunk[ISO_SOURCE_COLUMN])
        feature_months.update(_parse_feature_months(chunk[DATE_SOURCE_COLUMN]))

    ordered_isos = sorted(iso_values)
    ordered_months = sorted(feature_months)
    row_count = max(len(ordered_isos), len(ordered_months), 1)
    data = {name: [np.nan] * row_count for name in columns}
    data[ISO_SOURCE_COLUMN] = _repeat_to_length(ordered_isos, row_count)
    data[DATE_SOURCE_COLUMN] = _repeat_to_length(
        [value.start_time for value in ordered_months],
        row_count,
    )
    return pd.DataFrame(data, columns=columns)


def _verify_reference_identity(contract: FeatureContract) -> None:
    missing = sorted(REFERENCE_REQUIRED_FEATURES - set(contract.feature_columns))
    present_excluded = sorted(
        REFERENCE_EXCLUDED_FEATURES & set(contract.feature_columns)
    )
    if missing or present_excluded:
        raise ValueError(
            "generated contract failed approved reference identity checks; "
            f"missing={missing}; excluded_present={present_excluded}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the frozen FEWSNET Stage 3 feature contract"
    )
    parser.add_argument("--panel", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    panel = _read_contract_generation_frame(args.panel)
    contract = Stage3FeatureBuilder().fit(panel)
    _verify_reference_identity(contract)
    print(f"feature_count={len(contract.feature_columns)}")
    print("required_feature_checks=passed")
    print("excluded_feature_checks=passed")
    write_feature_contract(contract, args.output)
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
