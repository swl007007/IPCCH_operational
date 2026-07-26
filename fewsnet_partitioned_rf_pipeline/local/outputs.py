"""Local FEWSNET prediction enrichment, validation, and CSV publication."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from jsonschema import Draft202012Validator

from fewsnet_partitioned_rf_pipeline.core.data import normalize_admin_code
from fewsnet_partitioned_rf_pipeline.core.inference import FORMAL_PREDICTION_COLUMNS
from fewsnet_partitioned_rf_pipeline.schemas import load_schema


LOCAL_PREDICTION_COLUMNS = (
    "admin_code",
    "ADMIN0",
    "ADMIN1",
    "ADMIN2",
    "ADMIN3",
    "ISO3",
    "lat",
    "lon",
    "population",
    "population_reference_period",
    "population_source",
    "probability_crisis",
    "predicted_crisis",
    "threshold",
    "cluster_id",
    "prediction_source",
    "feature_month",
    "target_month",
    "horizon_months",
    "suite_version",
    "model_artifact_path",
    "source_input",
)

_RAW_REQUIRED_COLUMNS = (
    "FEWSNET_admin_code",
    "ADMIN0",
    "ADMIN1",
    "ADMIN2",
    "ADMIN3",
    "ISO3",
    "lat",
    "lon",
    "pop",
    "date",
)
_IDENTITY_POPULATION_COLUMNS = (
    "admin_code",
    "ADMIN0",
    "ADMIN1",
    "ADMIN2",
    "ADMIN3",
    "ISO3",
    "lat",
    "lon",
    "population",
    "population_reference_period",
    "population_source",
)
_SUITE_IDENTITY_COLUMNS = (
    "admin_code",
    "ADMIN0",
    "ADMIN1",
    "ADMIN2",
    "ADMIN3",
    "ISO3",
    "lat",
    "lon",
    "population",
    "population_reference_period",
    "population_source",
    "source_input",
)
_HORIZONS = (("0m", 0), ("6m", 6), ("12m", 12))
_FALLBACK_SOURCES = (
    "pooled_unmapped",
    "pooled_small_partition",
    "pooled_single_class",
    "pooled_missing_partition_model",
)
_PREDICTION_SOURCES = ("partition_model", *_FALLBACK_SOURCES)
_LOCAL_CSV_STRING_COLUMNS = (
    "admin_code",
    "ADMIN0",
    "ADMIN1",
    "ADMIN2",
    "ADMIN3",
    "ISO3",
    "population_reference_period",
    "population_source",
    "prediction_source",
    "feature_month",
    "target_month",
    "suite_version",
    "model_artifact_path",
    "source_input",
)
_LOCAL_CSV_INTEGER_COLUMNS = (
    "predicted_crisis",
    "cluster_id",
    "horizon_months",
)
_LOCAL_CSV_FLOAT_COLUMNS = (
    "lat",
    "lon",
    "population",
    "probability_crisis",
    "threshold",
)
_LOCAL_CSV_NON_FLOAT_COLUMNS = tuple(
    column
    for column in LOCAL_PREDICTION_COLUMNS
    if column not in _LOCAL_CSV_FLOAT_COLUMNS
)
_LOCAL_CSV_NULLABLE_COLUMNS = (
    "ADMIN0",
    "ADMIN1",
    "ADMIN2",
    "ADMIN3",
    "ISO3",
    "population",
    "population_reference_period",
    "cluster_id",
)
_LOCAL_CSV_NULL_REPRESENTATION = ""
_LOCAL_CSV_DTYPES = {
    **{column: "string" for column in _LOCAL_CSV_STRING_COLUMNS},
    **{column: "Int64" for column in _LOCAL_CSV_INTEGER_COLUMNS},
    **{column: "float64" for column in _LOCAL_CSV_FLOAT_COLUMNS},
}
_LOCAL_PREDICTION_VALIDATOR = Draft202012Validator(
    load_schema("local-prediction-record")
)


@dataclass(frozen=True)
class PopulationSummary:
    raw_last_observed_count: int
    missing_raw_count: int
    missing_admin_codes: tuple[str, ...]
    reference_period_counts: dict[str, int]


def _is_missing(value: object) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _duplicate_names(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _require_dataframe(value: object, name: str) -> pd.DataFrame:
    if not isinstance(value, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas.DataFrame")
    return value


def _require_exact_columns(
    frame: pd.DataFrame,
    expected: Sequence[str],
    name: str,
) -> None:
    actual = tuple(str(column) for column in frame.columns)
    expected_columns = tuple(expected)
    if actual != expected_columns:
        raise ValueError(
            f"{name} must have exact columns in order; "
            f"expected={list(expected_columns)}, actual={list(actual)}"
        )


def _parse_month(value: object, name: str) -> pd.Period:
    if _is_missing(value) or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{name} must be a valid month")
    try:
        return pd.Period(value, freq="M")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a valid month") from exc


def _parse_panel_periods(values: pd.Series) -> pd.Series:
    blank = values.astype("string").str.strip().eq("").fillna(False)
    parsed = pd.to_datetime(values.mask(blank), errors="coerce")
    invalid = parsed.isna()
    if invalid.any():
        examples = values.loc[invalid].astype(str).head(5).tolist()
        raise ValueError(f"date contains invalid or missing values: {examples}")
    return parsed.dt.to_period("M")


def _coerce_raw_population(values: pd.Series) -> pd.Series:
    bool_values = values.map(lambda value: isinstance(value, (bool, np.bool_)))
    converted = pd.to_numeric(values, errors="coerce")
    invalid = values.notna() & (converted.isna() | bool_values)
    numeric = converted.to_numpy(dtype=np.float64, na_value=np.nan)
    invalid_finite = ~np.isnan(numeric) & ~np.isfinite(numeric)
    invalid_negative = ~np.isnan(numeric) & (numeric < 0.0)
    if invalid.any() or invalid_finite.any() or invalid_negative.any():
        raise ValueError(
            "population must contain only finite nonnegative numeric values or null"
        )
    return pd.Series(numeric, index=values.index, dtype="float64")


def build_identity_population_frame(
    panel: pd.DataFrame,
    feature_month: object,
) -> tuple[pd.DataFrame, PopulationSummary]:
    """Build canonical feature-month identity plus raw population provenance."""
    source = _require_dataframe(panel, "panel")
    column_names = tuple(str(column) for column in source.columns)
    duplicate_columns = _duplicate_names(column_names)
    if duplicate_columns:
        raise ValueError(f"panel contains duplicate columns: {duplicate_columns}")
    missing_columns = sorted(set(_RAW_REQUIRED_COLUMNS) - set(column_names))
    if missing_columns:
        raise ValueError(f"panel is missing required raw columns: {missing_columns}")

    selected_period = _parse_month(feature_month, "feature_month")
    working = source.loc[:, list(_RAW_REQUIRED_COLUMNS)].copy()
    working["_source_order"] = np.arange(len(working), dtype=np.int64)
    working["_admin_code"] = working["FEWSNET_admin_code"].map(
        normalize_admin_code
    )
    if working["_admin_code"].eq("").any():
        raise ValueError("FEWSNET_admin_code contains missing or blank values")
    working["_period"] = _parse_panel_periods(working["date"])
    working["_population"] = _coerce_raw_population(working["pop"])

    admin_codes = tuple(sorted(set(working["_admin_code"])))
    if not admin_codes:
        raise ValueError("panel must contain at least one admin code")
    feature_rows = working.loc[working["_period"] == selected_period].copy()
    feature_counts = feature_rows.groupby("_admin_code", sort=False).size().to_dict()
    invalid_feature_codes = tuple(
        code for code in admin_codes if feature_counts.get(code, 0) != 1
    )
    if invalid_feature_codes:
        raise ValueError(
            "each admin_code must have exactly one row in the requested "
            f"feature month; invalid={list(invalid_feature_codes[:10])}"
        )

    feature_rows = feature_rows.sort_values("_admin_code", kind="stable")
    available_population = working.loc[
        (working["_period"] <= selected_period)
        & working["_population"].notna()
    ].copy()
    available_population = available_population.sort_values(
        ["_admin_code", "_period", "_source_order"],
        kind="stable",
    )
    latest_population = available_population.groupby(
        "_admin_code",
        sort=False,
        as_index=False,
    ).tail(1)
    latest_by_admin = {
        row["_admin_code"]: (float(row["_population"]), str(row["_period"]))
        for _, row in latest_population.iterrows()
    }

    identity = pd.DataFrame(
        {
            "admin_code": feature_rows["_admin_code"].tolist(),
            "ADMIN0": feature_rows["ADMIN0"].tolist(),
            "ADMIN1": feature_rows["ADMIN1"].tolist(),
            "ADMIN2": feature_rows["ADMIN2"].tolist(),
            "ADMIN3": feature_rows["ADMIN3"].tolist(),
            "ISO3": feature_rows["ISO3"].tolist(),
            "lat": feature_rows["lat"].tolist(),
            "lon": feature_rows["lon"].tolist(),
        }
    )
    populations: list[float] = []
    reference_periods: list[str | None] = []
    population_sources: list[str] = []
    for admin_code in identity["admin_code"]:
        latest = latest_by_admin.get(admin_code)
        if latest is None:
            populations.append(np.nan)
            reference_periods.append(None)
            population_sources.append("missing_raw")
            continue
        population, reference_period = latest
        populations.append(population)
        reference_periods.append(reference_period)
        population_sources.append("raw_last_observed")
    identity["population"] = pd.Series(populations, dtype="float64")
    identity["population_reference_period"] = reference_periods
    identity["population_source"] = population_sources
    identity = identity.loc[:, list(_IDENTITY_POPULATION_COLUMNS)]

    missing_admin_codes = tuple(
        identity.loc[
            identity["population_source"] == "missing_raw",
            "admin_code",
        ].tolist()
    )
    raw_reference_counts = (
        identity.loc[
            identity["population_source"] == "raw_last_observed",
            "population_reference_period",
        ]
        .value_counts()
        .sort_index()
    )
    summary = PopulationSummary(
        raw_last_observed_count=int(
            (identity["population_source"] == "raw_last_observed").sum()
        ),
        missing_raw_count=int(
            (identity["population_source"] == "missing_raw").sum()
        ),
        missing_admin_codes=missing_admin_codes,
        reference_period_counts={
            str(period): int(count)
            for period, count in raw_reference_counts.items()
        },
    )
    return identity.reset_index(drop=True), summary


def _blank_vertex_field(values: pd.Series) -> bool:
    return bool(
        values.map(
            lambda value: _is_missing(value)
            or (isinstance(value, str) and not value.strip())
        ).all()
    )


def _require_nonempty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def enrich_local_predictions(
    formal_predictions: pd.DataFrame,
    identity_population: pd.DataFrame,
    *,
    model_artifact_path: str,
    source_input: str,
) -> pd.DataFrame:
    """Join local formal predictions to feature-month identity and population."""
    formal = _require_dataframe(formal_predictions, "formal_predictions")
    identity = _require_dataframe(identity_population, "identity_population")
    try:
        _require_exact_columns(
            formal,
            FORMAL_PREDICTION_COLUMNS,
            "formal_predictions",
        )
    except ValueError as exc:
        raise ValueError(
            f"exact formal prediction columns are required: {exc}"
        ) from exc
    _require_exact_columns(
        identity,
        _IDENTITY_POPULATION_COLUMNS,
        "identity_population",
    )
    if not _blank_vertex_field(formal["vertex_model_resource_name"]) or not (
        _blank_vertex_field(formal["vertex_model_version_id"])
    ):
        raise ValueError("local prediction Vertex fields must be blank")
    artifact_path = _require_nonempty_string(
        model_artifact_path,
        "model_artifact_path",
    )
    input_path = _require_nonempty_string(source_input, "source_input")

    formal_codes = formal["admin_code"].map(normalize_admin_code)
    identity_codes = identity["admin_code"].map(normalize_admin_code)
    if formal_codes.eq("").any() or identity_codes.eq("").any():
        raise ValueError("admin_code contains missing or blank values")
    if formal_codes.duplicated().any() or identity_codes.duplicated().any():
        raise ValueError("formal and identity admin_code values must be unique")
    if set(formal_codes) != set(identity_codes):
        raise ValueError("formal and identity admin_code sets must match exactly")

    formal_working = formal.copy()
    formal_working["admin_code"] = formal_codes
    formal_working["_row_order"] = np.arange(len(formal_working), dtype=np.int64)
    formal_working = formal_working.drop(
        columns=["vertex_model_resource_name", "vertex_model_version_id"]
    )
    identity_working = identity.copy()
    identity_working["admin_code"] = identity_codes
    enriched = formal_working.merge(
        identity_working,
        on="admin_code",
        how="left",
        validate="one_to_one",
        sort=False,
    )
    enriched = enriched.sort_values("_row_order", kind="stable").drop(
        columns="_row_order"
    )
    enriched["model_artifact_path"] = artifact_path
    enriched["source_input"] = input_path
    return enriched.loc[:, list(LOCAL_PREDICTION_COLUMNS)].reset_index(drop=True)


def _numeric_values(
    values: pd.Series,
    name: str,
    *,
    allow_missing: bool = False,
) -> np.ndarray:
    converted = pd.to_numeric(values, errors="coerce")
    invalid = values.notna() & converted.isna()
    numeric = converted.to_numpy(dtype=np.float64, na_value=np.nan)
    if invalid.any() or (not allow_missing and np.isnan(numeric).any()):
        raise ValueError(f"{name} must contain numeric values")
    return numeric


def _require_exact_value(values: pd.Series, expected: object, name: str) -> None:
    if values.isna().any() or not bool(values.eq(expected).all()):
        raise ValueError(f"{name} must contain one exact value: {expected}")


def _json_scalar(value: object) -> object:
    if _is_missing(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def _validate_local_prediction_record(record: dict[str, object]) -> None:
    errors = sorted(
        _LOCAL_PREDICTION_VALIDATOR.iter_errors(record),
        key=lambda error: list(error.path),
    )
    if errors:
        first = errors[0]
        path = ".".join(str(part) for part in first.path) or "<root>"
        raise ValueError(
            "local-prediction-record contract failed at "
            f"{path}: {first.message}"
        )


def validate_local_prediction_frame(
    frame: pd.DataFrame,
    *,
    expected_admin_codes: Sequence[object],
    feature_month: str,
    target_month: str,
    horizon_months: int,
    suite_version: str,
) -> dict[str, object]:
    """Validate one local prediction horizon and return deterministic metrics."""
    candidate = _require_dataframe(frame, "frame")
    _require_exact_columns(candidate, LOCAL_PREDICTION_COLUMNS, "frame")

    if isinstance(expected_admin_codes, (str, bytes)):
        raise TypeError("expected_admin_codes must be a sequence of admin codes")
    expected_codes = tuple(
        normalize_admin_code(value) for value in expected_admin_codes
    )
    if not expected_codes or any(code == "" for code in expected_codes):
        raise ValueError("expected_admin_codes must contain non-blank values")
    if len(expected_codes) != len(set(expected_codes)):
        raise ValueError("expected_admin_codes contains duplicate admin_code values")

    actual_codes = candidate["admin_code"].map(
        lambda value: value.strip() if isinstance(value, str) else str(value).strip()
    )
    normalized_codes = candidate["admin_code"].map(normalize_admin_code)
    if normalized_codes.eq("").any():
        raise ValueError("admin_code contains missing or blank values")
    if normalized_codes.duplicated().any():
        raise ValueError("frame contains duplicate admin_code values")
    if tuple(actual_codes) != expected_codes:
        raise ValueError("frame does not match expected admin_code row order")

    expected_feature_month = str(_parse_month(feature_month, "feature_month"))
    expected_target_month = str(_parse_month(target_month, "target_month"))
    if horizon_months not in {0, 6, 12}:
        raise ValueError("horizon_months must be 0, 6, or 12")
    derived_target_month = str(
        pd.Period(expected_feature_month, freq="M") + horizon_months
    )
    if expected_target_month != derived_target_month:
        raise ValueError("target_month does not match the predictive horizon")
    expected_suite = _require_nonempty_string(suite_version, "suite_version")
    _require_exact_value(
        candidate["feature_month"],
        expected_feature_month,
        "feature_month",
    )
    _require_exact_value(
        candidate["target_month"],
        expected_target_month,
        "target_month",
    )
    _require_exact_value(
        candidate["horizon_months"],
        horizon_months,
        "horizon_months",
    )
    _require_exact_value(
        candidate["suite_version"],
        expected_suite,
        "suite_version",
    )

    probabilities = _numeric_values(
        candidate["probability_crisis"],
        "probability_crisis",
    )
    if not np.isfinite(probabilities).all():
        raise ValueError("probability_crisis must contain only finite values")
    if ((probabilities < 0.0) | (probabilities > 1.0)).any():
        raise ValueError("probability_crisis must be between 0 and 1")
    thresholds = _numeric_values(candidate["threshold"], "threshold")
    if not np.isfinite(thresholds).all():
        raise ValueError("threshold must contain only finite values")
    if ((thresholds < 0.0) | (thresholds > 1.0)).any():
        raise ValueError("threshold must be between 0 and 1")
    if np.unique(thresholds).size != 1:
        raise ValueError("each prediction file must contain one constant threshold")
    threshold = float(thresholds[0])

    labels = _numeric_values(candidate["predicted_crisis"], "predicted_crisis")
    if (
        not np.isfinite(labels).all()
        or not np.equal(labels, np.floor(labels)).all()
        or not np.isin(labels, (0.0, 1.0)).all()
    ):
        raise ValueError("predicted_crisis must contain only integer 0 or 1")
    expected_labels = (probabilities >= threshold).astype(np.int8)
    if not np.array_equal(labels.astype(np.int8), expected_labels):
        raise ValueError("threshold-to-label equality is invalid")

    latitudes = _numeric_values(candidate["lat"], "lat")
    longitudes = _numeric_values(candidate["lon"], "lon")
    if not np.isfinite(latitudes).all():
        raise ValueError("latitude values must be finite")
    if not np.isfinite(longitudes).all():
        raise ValueError("longitude values must be finite")
    if ((latitudes < -90.0) | (latitudes > 90.0)).any():
        raise ValueError("latitude values must be within [-90, 90]")
    if ((longitudes < -180.0) | (longitudes > 180.0)).any():
        raise ValueError("longitude values must be within [-180, 180]")

    prediction_sources = candidate["prediction_source"].tolist()
    if any(source not in _PREDICTION_SOURCES for source in prediction_sources):
        raise ValueError("cluster/source rules require the approved source vocabulary")
    cluster_missing = candidate["cluster_id"].map(_is_missing).to_numpy(dtype=bool)
    unmapped = np.asarray(
        [source == "pooled_unmapped" for source in prediction_sources],
        dtype=bool,
    )
    if not np.array_equal(cluster_missing, unmapped):
        raise ValueError("cluster/source pairing is invalid")

    populations = _numeric_values(
        candidate["population"],
        "population",
        allow_missing=True,
    )
    populated = ~np.isnan(populations)
    if (~np.isfinite(populations[populated])).any() or (
        populations[populated] < 0.0
    ).any():
        raise ValueError("population provenance requires finite nonnegative values")
    population_sources = candidate["population_source"].tolist()
    if any(
        source not in {"raw_last_observed", "missing_raw"}
        for source in population_sources
    ):
        raise ValueError("population provenance uses an invalid source")
    reference_values = candidate["population_reference_period"].tolist()
    reference_missing = np.asarray(
        [
            _is_missing(value)
            or (isinstance(value, str) and not value.strip())
            for value in reference_values
        ],
        dtype=bool,
    )
    raw_population = np.asarray(
        [source == "raw_last_observed" for source in population_sources],
        dtype=bool,
    )
    missing_population = ~raw_population
    if (
        (raw_population & (~populated | reference_missing)).any()
        or (missing_population & (populated | ~reference_missing)).any()
    ):
        raise ValueError("population provenance pairing is invalid")
    for is_raw, reference in zip(
        raw_population,
        reference_values,
        strict=True,
    ):
        if not is_raw:
            continue
        reference_period = _parse_month(
            reference,
            "population_reference_period",
        )
        if reference_period > pd.Period(expected_feature_month, freq="M"):
            raise ValueError(
                "population provenance reference period exceeds feature_month"
            )

    for record in candidate.to_dict("records"):
        _validate_local_prediction_record(
            {name: _json_scalar(value) for name, value in record.items()},
        )

    fallback_counts = {
        source: int(sum(value == source for value in prediction_sources))
        for source in _FALLBACK_SOURCES
    }
    population_counts = {
        "raw_last_observed": int(raw_population.sum()),
        "missing_raw": int(missing_population.sum()),
    }
    return {
        "row_count": len(candidate),
        "probability_min": float(probabilities.min()),
        "probability_max": float(probabilities.max()),
        "probability_mean": float(probabilities.mean()),
        "threshold": threshold,
        "positive_label_count": int(expected_labels.sum()),
        "fallback_counts": fallback_counts,
        "population_counts": population_counts,
        "missing_admin_codes": [
            code
            for code, source in zip(
                actual_codes,
                population_sources,
                strict=True,
            )
            if source == "missing_raw"
        ],
    }


def validate_local_prediction_suite(
    predictions: Mapping[str, pd.DataFrame],
    *,
    expected_admin_codes: Sequence[object],
    feature_month: str,
    suite_version: str,
) -> dict[str, object]:
    """Validate the exact 0m/6m/12m local prediction suite."""
    if not isinstance(predictions, Mapping):
        raise TypeError("predictions must be a mapping")
    expected_keys = tuple(key for key, _ in _HORIZONS)
    if set(predictions) != set(expected_keys):
        raise ValueError(
            "predictions must contain exactly the 0m, 6m, and 12m horizons"
        )
    selected_feature_month = str(_parse_month(feature_month, "feature_month"))
    target_months = {
        key: str(pd.Period(selected_feature_month, freq="M") + months)
        for key, months in _HORIZONS
    }
    summaries: dict[str, dict[str, object]] = {}
    baseline_admin_codes: list[object] | None = None
    baseline_identity: pd.DataFrame | None = None
    for horizon_key, months in _HORIZONS:
        frame = _require_dataframe(predictions[horizon_key], horizon_key)
        if "admin_code" in frame.columns:
            admin_codes = frame["admin_code"].tolist()
            if baseline_admin_codes is not None and admin_codes != baseline_admin_codes:
                raise ValueError(
                    "all horizons must have identical admin_code row order"
                )
        summary = validate_local_prediction_frame(
            frame,
            expected_admin_codes=expected_admin_codes,
            feature_month=selected_feature_month,
            target_month=target_months[horizon_key],
            horizon_months=months,
            suite_version=suite_version,
        )
        identity = frame.loc[:, list(_SUITE_IDENTITY_COLUMNS)].reset_index(drop=True)
        if baseline_admin_codes is None:
            baseline_admin_codes = frame["admin_code"].tolist()
            baseline_identity = identity
        else:
            try:
                pd.testing.assert_frame_equal(
                    baseline_identity,
                    identity,
                    check_dtype=False,
                    check_exact=True,
                )
            except AssertionError as exc:
                raise ValueError(
                    "all horizons must have identical identity and population "
                    "provenance, coordinates, and source_input"
                ) from exc
        summaries[horizon_key] = summary
    return {
        "target_months": target_months,
        "horizon_summaries": summaries,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_local_prediction_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(
        path,
        dtype=_LOCAL_CSV_DTYPES,
        keep_default_na=False,
        na_values={
            column: [_LOCAL_CSV_NULL_REPRESENTATION]
            for column in _LOCAL_CSV_NULLABLE_COLUMNS
        },
        float_precision="round_trip",
    )


def _canonicalize_local_prediction_csv_frame(frame: pd.DataFrame) -> pd.DataFrame:
    canonical = frame.copy().reset_index(drop=True)
    for column in _LOCAL_CSV_STRING_COLUMNS:
        canonical[column] = canonical[column].astype("string")
    for column in _LOCAL_CSV_INTEGER_COLUMNS:
        canonical[column] = canonical[column].astype("Int64")
    for column in _LOCAL_CSV_FLOAT_COLUMNS:
        numeric = pd.to_numeric(canonical[column], errors="raise")
        canonical[column] = numeric.to_numpy(
            dtype=np.float64,
            na_value=np.nan,
        )
    return canonical.loc[:, list(LOCAL_PREDICTION_COLUMNS)]


def _require_local_prediction_csv_values_equal(
    actual: pd.DataFrame,
    expected: pd.DataFrame,
) -> None:
    non_float_columns = list(_LOCAL_CSV_NON_FLOAT_COLUMNS)
    if not actual.loc[:, non_float_columns].equals(
        expected.loc[:, non_float_columns]
    ):
        raise ValueError("written CSV values differ after stable readback")

    for column in _LOCAL_CSV_FLOAT_COLUMNS:
        actual_missing = actual[column].isna().to_numpy(dtype=bool)
        expected_missing = expected[column].isna().to_numpy(dtype=bool)
        if not np.array_equal(actual_missing, expected_missing):
            raise ValueError("written CSV values differ after stable readback")

        non_missing = ~actual_missing
        actual_bits = actual.loc[non_missing, column].to_numpy(
            dtype=np.float64
        ).view(np.uint64)
        expected_bits = expected.loc[non_missing, column].to_numpy(
            dtype=np.float64
        ).view(np.uint64)
        if not np.array_equal(actual_bits, expected_bits):
            raise ValueError("written CSV values differ after stable readback")


def write_local_prediction_csv(
    frame: pd.DataFrame,
    path: str | Path,
) -> dict[str, object]:
    """Write one create-only UTF-8 local prediction CSV and verify its shape."""
    candidate = _require_dataframe(frame, "frame")
    _require_exact_columns(candidate, LOCAL_PREDICTION_COLUMNS, "frame")
    output_path = Path(path)
    if output_path.exists() or output_path.is_symlink():
        raise FileExistsError(f"local prediction CSV already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    candidate.to_csv(
        output_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
        mode="x",
        na_rep=_LOCAL_CSV_NULL_REPRESENTATION,
    )
    reloaded = _read_local_prediction_csv(output_path)
    _require_exact_columns(reloaded, LOCAL_PREDICTION_COLUMNS, "written CSV")
    if len(reloaded) != len(candidate):
        raise ValueError("written CSV row count differs from the source frame")
    canonical_source = _canonicalize_local_prediction_csv_frame(candidate)
    canonical_reloaded = _canonicalize_local_prediction_csv_frame(reloaded)
    _require_local_prediction_csv_values_equal(
        canonical_reloaded,
        canonical_source,
    )
    return {
        "path": str(output_path),
        "sha256": _sha256(output_path),
        "size_bytes": output_path.stat().st_size,
        "row_count": len(reloaded),
        "columns": list(reloaded.columns),
    }
