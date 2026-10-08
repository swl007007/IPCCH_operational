import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


PROBABILITY_COLUMN = "probability_crisis"
DISPERSION_COLUMN = "probability_crisis_area_dispersion"
SCORE_AGGREGATION_METHOD = "population_weighted_mean_v1"
AREA_DISPERSION_METHOD = "population_weighted_area_score_sd_v1"
PREDICTION_NAME = re.compile(
    r"^fewsnet_partitioned_rf_(?P<run_month>\d{6})_scope_"
    r"(?P<horizon>0|6|12)m_predictions\.csv$"
)
EXPECTED_HORIZONS = (0, 6, 12)
COUNTRY_SCOPE_COLUMNS = ("ISO3", "country_code", "country", "country_en")
CENSUS_COLUMNS = (
    "ISO3",
    "country",
    "country_en",
    "referenced_population",
    "population_reference_year",
    "population_reference_date",
    "population_measure",
    "population_source",
    "population_vintage",
    "population_source_url",
    "census_genc_codes",
)
PREDICTION_COLUMNS = (
    "admin_code",
    "ISO3",
    "population",
    PROBABILITY_COLUMN,
    "predicted_crisis",
    "threshold",
    "feature_month",
    "target_month",
    "horizon_months",
    "suite_version",
    "model_artifact_path",
    "source_input",
)


class CountryAggregationError(ValueError):
    """Raised when FEWSNET country output contracts cannot be satisfied."""


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_columns(frame, columns, label):
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise CountryAggregationError(
            "{0} is missing required columns: {1}".format(
                label, ", ".join(missing)
            )
        )


def _single_value(frame, column, label):
    values = frame[column].drop_duplicates().tolist()
    if len(values) != 1:
        raise CountryAggregationError(
            "{0} must contain exactly one {1}".format(label, column)
        )
    value = values[0]
    if pd.isna(value) or not str(value).strip():
        raise CountryAggregationError(
            "{0} contains a blank {1}".format(label, column)
        )
    return value


def _atomic_write_csv(frame, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".{0}.".format(path.name),
        suffix=".tmp",
        dir=path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        frame.to_csv(temporary_path, index=False, float_format="%.17g")
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _atomic_write_json(payload, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".{0}.".format(path.name),
        suffix=".tmp",
        dir=path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        with temporary_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _read_prediction(path):
    frame = pd.read_csv(
        path,
        dtype={"admin_code": "string", "ISO3": "string"},
    )
    _require_columns(frame, PREDICTION_COLUMNS, str(path))
    if frame["admin_code"].isna().any():
        raise CountryAggregationError("prediction admin_code values cannot be blank")
    if frame["admin_code"].duplicated().any():
        raise CountryAggregationError("prediction admin_code values must be unique")
    return frame


def _finite_numeric(series, label):
    numeric = pd.to_numeric(series, errors="coerce")
    values = numeric.to_numpy(dtype="float64")
    if numeric.isna().any() or not np.isfinite(values).all():
        raise CountryAggregationError("{0} values must be finite".format(label))
    return numeric.astype("float64")


def clip_negative_probabilities(frame):
    corrected = frame.copy()
    probability = _finite_numeric(
        corrected[PROBABILITY_COLUMN], PROBABILITY_COLUMN
    )
    if (probability > 1).any():
        raise CountryAggregationError(
            "probability_crisis values cannot be greater than 1"
        )
    negative_mask = probability < 0
    clipped = probability.clip(lower=0.0)
    threshold = _finite_numeric(corrected["threshold"], "threshold")
    if (threshold < 0).any() or (threshold > 1).any():
        raise CountryAggregationError("threshold values must be within 0 and 1")
    expected_prediction = (clipped >= threshold).astype("int64")
    current_prediction = pd.to_numeric(
        corrected["predicted_crisis"], errors="coerce"
    )
    prediction_mismatch = (
        current_prediction.isna()
        | ~current_prediction.isin((0, 1))
        | current_prediction.ne(expected_prediction)
    )

    corrected[PROBABILITY_COLUMN] = clipped
    corrected["predicted_crisis"] = expected_prediction
    return corrected, {
        "negative_probability_cells_clipped": int(negative_mask.sum()),
        "predicted_crisis_cells_recomputed": int(prediction_mismatch.sum()),
        "source_file_changed": bool(
            negative_mask.any() or prediction_mismatch.any()
        ),
    }


def _prepare_country_scope(country_scope):
    _require_columns(country_scope, COUNTRY_SCOPE_COLUMNS, "country scope")
    scope = country_scope.loc[:, COUNTRY_SCOPE_COLUMNS].copy()
    for column in COUNTRY_SCOPE_COLUMNS:
        scope[column] = scope[column].astype("string").str.strip()
    for column in ("ISO3", "country", "country_en"):
        if scope[column].isna().any() or scope[column].eq("").any():
            raise CountryAggregationError(
                "country scope contains a blank {0}".format(column)
            )
    if scope["ISO3"].duplicated().any():
        raise CountryAggregationError("country scope ISO3 values must be unique")
    return scope


def _prepare_census_population(census_population):
    _require_columns(census_population, CENSUS_COLUMNS, "Census population")
    census = census_population.loc[:, CENSUS_COLUMNS].copy()
    census["ISO3"] = census["ISO3"].astype("string").str.strip()
    if census["ISO3"].isna().any() or census["ISO3"].eq("").any():
        raise CountryAggregationError("Census population contains a blank ISO3")
    if census["ISO3"].duplicated().any():
        raise CountryAggregationError("Census population ISO3 values must be unique")

    referenced_population = _finite_numeric(
        census["referenced_population"], "referenced_population"
    )
    if (referenced_population < 0).any():
        raise CountryAggregationError(
            "referenced_population values must be non-negative"
        )
    if not np.equal(referenced_population, np.floor(referenced_population)).all():
        raise CountryAggregationError(
            "referenced_population values must be whole numbers"
        )
    census["referenced_population"] = referenced_population.astype("int64")
    return census


def _prepare_population_weights(series):
    missing_text = series.astype("string").str.strip().eq("").fillna(False)
    missing = series.isna() | missing_text
    numeric = pd.to_numeric(series, errors="coerce")
    invalid = numeric.isna() & ~missing
    if invalid.any():
        raise CountryAggregationError("population contains non-numeric values")
    finite = np.isfinite(numeric.fillna(0).to_numpy(dtype="float64"))
    if not finite.all():
        raise CountryAggregationError("population contains non-finite values")
    if (numeric.dropna() < 0).any():
        raise CountryAggregationError("population weights must be non-negative")
    return numeric.astype("float64"), missing


def _weighted_mean_and_sd(values, weights):
    total_weight = float(weights.sum())
    if not math.isfinite(total_weight) or total_weight <= 0:
        raise CountryAggregationError(
            "each country must have positive population weight"
        )
    mean = float(np.average(values, weights=weights))
    variance = float(np.average((values - mean) ** 2, weights=weights))
    return mean, math.sqrt(max(variance, 0.0))


def aggregate_country_probabilities(
    predictions,
    country_scope,
    census_population,
):
    _require_columns(predictions, PREDICTION_COLUMNS, "prediction table")
    scope = _prepare_country_scope(country_scope)
    census = _prepare_census_population(census_population)

    frame = predictions.copy()
    frame["ISO3"] = frame["ISO3"].astype("string").str.strip()
    if frame["ISO3"].isna().any() or frame["ISO3"].eq("").any():
        raise CountryAggregationError("prediction ISO3 values cannot be blank")

    predicted_iso3 = set(frame["ISO3"].unique())
    missing_scope = sorted(predicted_iso3 - set(scope["ISO3"]))
    missing_census = sorted(predicted_iso3 - set(census["ISO3"]))
    if missing_scope:
        raise CountryAggregationError(
            "prediction countries are missing from country scope: {0}".format(
                ", ".join(missing_scope)
            )
        )
    if missing_census:
        raise CountryAggregationError(
            "prediction countries are missing Census population: {0}".format(
                ", ".join(missing_census)
            )
        )

    census_metadata = census.drop(columns=["country", "country_en"])
    joined = frame.merge(scope, on="ISO3", how="left", validate="many_to_one")
    joined = joined.merge(
        census_metadata,
        on="ISO3",
        how="left",
        validate="many_to_one",
        suffixes=("_area", ""),
    )

    weights, missing_weight = _prepare_population_weights(joined["population"])
    joined["_aggregation_weight"] = weights
    joined["_missing_population"] = missing_weight
    probability = _finite_numeric(
        joined[PROBABILITY_COLUMN], PROBABILITY_COLUMN
    )
    if (probability < 0).any() or (probability > 1).any():
        raise CountryAggregationError(
            "probability_crisis must be within 0 and 1 after clipping"
        )
    joined[PROBABILITY_COLUMN] = probability

    feature_month = str(
        _single_value(joined, "feature_month", "prediction table")
    ).strip()
    target_month = str(
        _single_value(joined, "target_month", "prediction table")
    ).strip()
    horizon_months = int(
        float(_single_value(joined, "horizon_months", "prediction table"))
    )
    suite_version = str(
        _single_value(joined, "suite_version", "prediction table")
    ).strip()
    model_artifact_path = str(
        _single_value(joined, "model_artifact_path", "prediction table")
    ).strip()
    source_input = str(
        _single_value(joined, "source_input", "prediction table")
    ).strip()
    area_threshold = float(
        _single_value(joined, "threshold", "prediction table")
    )

    population_fields = (
        "country_code",
        "country",
        "country_en",
        "referenced_population",
        "population_reference_year",
        "population_reference_date",
        "population_measure",
        "population_source",
        "population_vintage",
        "population_source_url",
        "census_genc_codes",
    )
    output_rows = []
    for iso3, group in joined.groupby("ISO3", sort=True):
        population_values = {
            field: _single_value(group, field, "country group")
            for field in population_fields
        }
        group_weights = group["_aggregation_weight"]
        positive = group_weights > 0
        positive_weights = group_weights.loc[positive].to_numpy(dtype="float64")
        positive_scores = group.loc[
            positive, PROBABILITY_COLUMN
        ].to_numpy(dtype="float64")
        mean, dispersion = _weighted_mean_and_sd(
            positive_scores, positive_weights
        )
        finite_population = ~group["_missing_population"]
        row = {
            "ISO3": iso3,
            **population_values,
            "feature_month": feature_month,
            "target_month": target_month,
            "horizon_months": horizon_months,
            PROBABILITY_COLUMN: mean,
            DISPERSION_COLUMN: dispersion,
            "area_count": int(len(group)),
            "finite_population_area_count": int(finite_population.sum()),
            "positive_population_area_count": int(positive.sum()),
            "zero_population_area_count": int(
                (finite_population & group_weights.eq(0)).sum()
            ),
            "missing_population_area_count": int(
                group["_missing_population"].sum()
            ),
            "area_population_weight_sum": float(positive_weights.sum()),
            "area_classification_threshold": area_threshold,
            "score_aggregation_method": SCORE_AGGREGATION_METHOD,
            "area_dispersion_method": AREA_DISPERSION_METHOD,
            "aggregation_weight_field": "population",
            "suite_version": suite_version,
            "model_artifact_path": model_artifact_path,
            "source_input": source_input,
        }
        output_rows.append(row)

    return pd.DataFrame(output_rows).sort_values("ISO3").reset_index(drop=True)


def _discover_prediction_files(prediction_dir):
    prediction_dir = Path(prediction_dir)
    matches = {}
    run_months = set()
    for path in sorted(
        prediction_dir.glob("fewsnet_partitioned_rf_*_scope_*m_predictions.csv")
    ):
        match = PREDICTION_NAME.fullmatch(path.name)
        if match is None:
            continue
        horizon = int(match.group("horizon"))
        if horizon in matches:
            raise CountryAggregationError(
                "prediction directory contains duplicate {0}m files".format(
                    horizon
                )
            )
        matches[horizon] = path
        run_months.add(match.group("run_month"))
    if set(matches) != set(EXPECTED_HORIZONS) or len(run_months) != 1:
        raise CountryAggregationError(
            "prediction directory must contain one 0m, 6m, and 12m run"
        )
    return next(iter(run_months)), matches


def build_country_level_predictions(
    prediction_dir,
    country_scope_path,
    census_population_path,
    output_dir,
):
    prediction_dir = Path(prediction_dir)
    output_dir = Path(output_dir)
    run_month, prediction_files = _discover_prediction_files(prediction_dir)
    country_scope = pd.read_csv(
        country_scope_path,
        dtype="string",
        keep_default_na=False,
    )
    census_population = pd.read_csv(
        census_population_path,
        dtype={
            "ISO3": "string",
            "country": "string",
            "country_en": "string",
            "census_genc_codes": "string",
        },
    )
    prepared_census = _prepare_census_population(census_population)

    scope_outputs = []
    combined_frames = []
    total_negative = 0
    total_prediction_recomputed = 0
    covered_iso3 = set()
    for horizon in EXPECTED_HORIZONS:
        prediction_path = prediction_files[horizon]
        frame = _read_prediction(prediction_path)
        corrected, correction = clip_negative_probabilities(frame)
        observed_horizon = int(
            float(_single_value(corrected, "horizon_months", str(prediction_path)))
        )
        if observed_horizon != horizon:
            raise CountryAggregationError(
                "{0} horizon_months does not match its filename".format(
                    prediction_path.name
                )
            )
        observed_month = str(
            _single_value(corrected, "feature_month", str(prediction_path))
        ).replace("-", "")
        if observed_month != run_month:
            raise CountryAggregationError(
                "{0} feature_month does not match its filename".format(
                    prediction_path.name
                )
            )
        if correction["source_file_changed"]:
            _atomic_write_csv(corrected, prediction_path)

        country_output = aggregate_country_probabilities(
            corrected,
            country_scope,
            prepared_census,
        )
        covered_iso3.update(country_output["ISO3"])
        output_path = output_dir / (
            "fewsnet_partitioned_rf_{0}_scope_{1}m_country_predictions.csv".format(
                run_month, horizon
            )
        )
        _atomic_write_csv(country_output, output_path)
        scope_summary = {
            "horizon_months": horizon,
            "input_path": str(prediction_path),
            "area_row_count": int(len(corrected)),
            "country_row_count": int(len(country_output)),
            "negative_probability_cells_clipped": correction[
                "negative_probability_cells_clipped"
            ],
            "predicted_crisis_cells_recomputed": correction[
                "predicted_crisis_cells_recomputed"
            ],
            "source_file_changed": correction["source_file_changed"],
            "missing_population_area_count": int(
                country_output["missing_population_area_count"].sum()
            ),
            "zero_population_area_count": int(
                country_output["zero_population_area_count"].sum()
            ),
            "output_path": str(output_path),
            "output_sha256": _sha256_file(output_path),
        }
        scope_outputs.append(scope_summary)
        combined_frames.append(country_output)
        total_negative += correction["negative_probability_cells_clipped"]
        total_prediction_recomputed += correction[
            "predicted_crisis_cells_recomputed"
        ]

    census_subset = prepared_census.loc[
        prepared_census["ISO3"].isin(covered_iso3)
    ].sort_values("ISO3").reset_index(drop=True)
    if set(census_subset["ISO3"]) != covered_iso3:
        raise CountryAggregationError(
            "Census population subset does not cover all prediction countries"
        )
    population_year = int(
        _single_value(
            census_subset,
            "population_reference_year",
            "Census population subset",
        )
    )
    population_path = output_dir / (
        "census_idb_{0}_fewsnet_country_population.csv".format(population_year)
    )
    _atomic_write_csv(census_subset, population_path)

    combined = pd.concat(combined_frames, ignore_index=True).sort_values(
        ["horizon_months", "ISO3"]
    ).reset_index(drop=True)
    combined_path = output_dir / (
        "fewsnet_partitioned_rf_{0}_country_predictions.csv".format(run_month)
    )
    _atomic_write_csv(combined, combined_path)

    summary = {
        "status": "passed",
        "run_month": run_month,
        "country_count": int(len(covered_iso3)),
        "combined_row_count": int(len(combined)),
        "negative_probability_cells_clipped": int(total_negative),
        "predicted_crisis_cells_recomputed": int(total_prediction_recomputed),
        "score_column": PROBABILITY_COLUMN,
        "score_aggregation_method": SCORE_AGGREGATION_METHOD,
        "area_dispersion_column": DISPERSION_COLUMN,
        "area_dispersion_method": AREA_DISPERSION_METHOD,
        "aggregation_weight_field": "population",
        "country_predicted_crisis_generated": False,
        "population_reference": {
            "source_table": str(census_population_path),
            "source_table_sha256": _sha256_file(census_population_path),
            "derived_table": str(population_path),
            "derived_table_sha256": _sha256_file(population_path),
        },
        "scope_outputs": scope_outputs,
        "combined_output": {
            "path": str(combined_path),
            "row_count": int(len(combined)),
            "sha256": _sha256_file(combined_path),
        },
    }
    summary_path = output_dir / "country_level_run_summary.json"
    _atomic_write_json(summary, summary_path)
    summary["summary_path"] = str(summary_path)
    return summary


def _parser():
    parser = argparse.ArgumentParser(
        description=(
            "Clip negative FEWSNET crisis probabilities and aggregate area "
            "scores to country-level population-weighted means and dispersion."
        )
    )
    parser.add_argument("--prediction-dir", required=True, type=Path)
    parser.add_argument("--country-scope", required=True, type=Path)
    parser.add_argument("--census-population", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        summary = build_country_level_predictions(
            prediction_dir=args.prediction_dir,
            country_scope_path=args.country_scope,
            census_population_path=args.census_population,
            output_dir=args.output_dir,
        )
    except (CountryAggregationError, OSError) as exc:
        print("error: {0}".format(exc), file=sys.stderr)
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
