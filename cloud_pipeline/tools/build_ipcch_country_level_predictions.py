import argparse
import hashlib
import io
import json
import math
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd


CENSUS_IDB_URL = (
    "https://www.census.gov/data-tools/demo/data/idb/dataset/idbzip.zip"
)
CENSUS_IDB_MEMBER = "idb5yr.txt"
CENSUS_IDB_RELEASE = "December 2025 release"
CENSUS_POPULATION_MEASURE = "Total mid-year population"
CENSUS_POPULATION_SOURCE = (
    "U.S. Census Bureau International Database"
)
SCORE_COLUMNS = tuple(
    "phase{0}_worse_score".format(phase) for phase in range(2, 6)
)
AREA_UNCERTAINTY_COLUMNS = (
    "prediction_uncertainty",
    "decision_margin",
    "uncertainty_critical_boundary",
    "uncertainty_method",
)
SCORE_AGGREGATION_METHOD = "population_weighted_mean_v1"
AGGREGATION_UNCERTAINTY_METHOD = (
    "population_weighted_area_score_sd_v1"
)
PREDICTION_NAME = re.compile(
    r"^ipcch_launch_(?P<run_month>\d{6})_scope_"
    r"(?P<scope>0|6|12)m_predictions\.csv$"
)
TOP_LEVEL_GEO_ID = re.compile(r"^W140000WO(?P<genc>[A-Z0-9]{2})$")
GENC_OVERRIDES = {
    "NAM": ("NA",),
    "PSE": ("XG", "XW"),
}


class CountryAggregationError(ValueError):
    """Raised when country-level output contracts cannot be satisfied."""


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
    return values[0]


def _download_census_idb(url, destination):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "IPCCH-country-aggregation/1.0"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        with Path(destination).open("wb") as output:
            shutil.copyfileobj(response, output)


def read_census_idb_population(zip_path, year=2026):
    populations = {}
    try:
        archive = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise CountryAggregationError(
            "cannot open Census IDB ZIP: {0}".format(zip_path)
        ) from exc

    with archive:
        if CENSUS_IDB_MEMBER not in archive.namelist():
            raise CountryAggregationError(
                "Census IDB ZIP is missing {0}".format(CENSUS_IDB_MEMBER)
            )
        with archive.open(CENSUS_IDB_MEMBER) as raw_handle:
            with io.TextIOWrapper(
                raw_handle, encoding="utf-8-sig", newline=""
            ) as handle:
                try:
                    header = handle.readline().rstrip("\r\n").split("|")
                except UnicodeDecodeError as exc:
                    raise CountryAggregationError(
                        "Census IDB table is not valid UTF-8 text"
                    ) from exc
                if header:
                    header[0] = header[0].lstrip("#")
                required = {"YR", "GEO_ID", "POP"}
                if not required <= set(header):
                    raise CountryAggregationError(
                        "Census IDB table is missing YR, GEO_ID, or POP"
                    )
                indexes = {name: header.index(name) for name in required}
                expected_width = len(header)
                for line_number, raw_line in enumerate(handle, start=2):
                    fields = raw_line.rstrip("\r\n").split("|")
                    if len(fields) != expected_width:
                        raise CountryAggregationError(
                            "Census IDB row {0} has an invalid width".format(
                                line_number
                            )
                        )
                    if fields[indexes["YR"]] != str(year):
                        continue
                    match = TOP_LEVEL_GEO_ID.fullmatch(
                        fields[indexes["GEO_ID"]]
                    )
                    if match is None:
                        continue
                    genc = match.group("genc")
                    try:
                        population = int(fields[indexes["POP"]])
                    except ValueError as exc:
                        raise CountryAggregationError(
                            "Census IDB population for {0} is not an integer".format(
                                genc
                            )
                        ) from exc
                    if population < 0:
                        raise CountryAggregationError(
                            "Census IDB population for {0} is negative".format(
                                genc
                            )
                        )
                    if genc in populations:
                        raise CountryAggregationError(
                            "Census IDB has duplicate country code {0}".format(genc)
                        )
                    populations[genc] = population

    if not populations:
        raise CountryAggregationError(
            "Census IDB contains no top-level country population for {0}".format(
                year
            )
        )
    return pd.DataFrame(
        [
            {"census_genc_code": code, "census_population": population}
            for code, population in sorted(populations.items())
        ]
    )


def build_census_population_reference(country_scope, idb_population, year=2026):
    _require_columns(
        country_scope,
        ("ISO3", "country_code", "country", "country_en"),
        "country scope",
    )
    _require_columns(
        idb_population,
        ("census_genc_code", "census_population"),
        "Census IDB population",
    )
    if country_scope["ISO3"].duplicated().any():
        raise CountryAggregationError("country scope ISO3 values must be unique")
    if country_scope["country"].duplicated().any():
        raise CountryAggregationError("country scope names must be unique")
    if idb_population["census_genc_code"].duplicated().any():
        raise CountryAggregationError("Census GENC codes must be unique")

    idb_by_code = idb_population.set_index("census_genc_code")
    rows = []
    for record in country_scope.to_dict("records"):
        iso3 = str(record["ISO3"]).strip()
        if not iso3:
            raise CountryAggregationError("country scope contains a blank ISO3")
        country_code = str(record["country_code"]).strip()
        genc_codes = GENC_OVERRIDES.get(iso3)
        if genc_codes is None:
            if not country_code:
                raise CountryAggregationError(
                    "country scope has no country code for {0}".format(iso3)
                )
            genc_codes = (country_code,)
        missing_codes = [
            code for code in genc_codes if code not in idb_by_code.index
        ]
        if missing_codes:
            raise CountryAggregationError(
                "Census IDB is missing {0} for {1}".format(
                    ", ".join(missing_codes), iso3
                )
            )
        referenced_population = int(
            idb_by_code.loc[list(genc_codes), "census_population"].sum()
        )
        rows.append(
            {
                "ISO3": iso3,
                "country": str(record["country"]).strip(),
                "country_en": str(record["country_en"]).strip(),
                "referenced_population": referenced_population,
                "population_reference_year": int(year),
                "population_reference_date": "{0:04d}-07-01".format(year),
                "population_measure": CENSUS_POPULATION_MEASURE,
                "population_source": CENSUS_POPULATION_SOURCE,
                "population_vintage": CENSUS_IDB_RELEASE,
                "population_source_url": CENSUS_IDB_URL,
                "census_genc_codes": ";".join(genc_codes),
            }
        )
    return pd.DataFrame(rows).sort_values("ISO3").reset_index(drop=True)


def _weighted_mean_and_sd(values, weights):
    total_weight = float(weights.sum())
    if not math.isfinite(total_weight) or total_weight <= 0:
        raise CountryAggregationError(
            "each country must have positive population weight"
        )
    mean = float(np.average(values, weights=weights))
    variance = float(np.average((values - mean) ** 2, weights=weights))
    return mean, math.sqrt(max(variance, 0.0))


def aggregate_country_scores(predictions, area_lookup, census_population):
    _require_columns(
        predictions,
        (
            "area_id",
            "population_estimate",
            *SCORE_COLUMNS,
            "feature_period",
            "target_period",
            "scope_months",
            "model_package_id",
            "source_input",
        ),
        "prediction table",
    )
    _require_columns(
        area_lookup,
        ("area_id", "country", "country_en"),
        "area lookup",
    )
    _require_columns(
        census_population,
        (
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
        ),
        "Census population reference",
    )
    if predictions["area_id"].duplicated().any():
        raise CountryAggregationError("prediction area_id values must be unique")
    if area_lookup["area_id"].duplicated().any():
        raise CountryAggregationError("area lookup area_id values must be unique")

    predictions = predictions.copy()
    area_lookup = area_lookup.copy()
    predictions["area_id"] = predictions["area_id"].astype("string")
    area_lookup["area_id"] = area_lookup["area_id"].astype("string")
    joined = predictions.merge(
        area_lookup[["area_id", "country", "country_en"]],
        on="area_id",
        how="left",
        validate="one_to_one",
    )
    if joined["country"].isna().any():
        raise CountryAggregationError(
            "prediction areas are missing from the country lookup"
        )
    joined = joined.merge(
        census_population,
        on="country",
        how="left",
        validate="many_to_one",
        suffixes=("_area", ""),
    )
    if joined["ISO3"].isna().any():
        missing = sorted(joined.loc[joined["ISO3"].isna(), "country"].unique())
        raise CountryAggregationError(
            "countries are missing Census population: {0}".format(
                ", ".join(missing)
            )
        )

    weights = pd.to_numeric(joined["population_estimate"], errors="coerce")
    if weights.isna().any() or not np.isfinite(weights).all():
        raise CountryAggregationError(
            "population_estimate weights must be finite"
        )
    if (weights < 0).any():
        raise CountryAggregationError(
            "population_estimate weights must be non-negative"
        )
    joined["_aggregation_weight"] = weights.astype("float64")
    for column in SCORE_COLUMNS:
        scores = pd.to_numeric(joined[column], errors="coerce")
        if scores.isna().any() or not np.isfinite(scores).all():
            raise CountryAggregationError(
                "{0} values must be finite".format(column)
            )
        joined[column] = scores.astype("float64")

    feature_period = _single_value(joined, "feature_period", "prediction table")
    target_period = _single_value(joined, "target_period", "prediction table")
    scope_months = int(
        _single_value(joined, "scope_months", "prediction table")
    )
    model_package_id = _single_value(
        joined, "model_package_id", "prediction table"
    )
    source_input = _single_value(joined, "source_input", "prediction table")

    output_rows = []
    for iso3, group in joined.groupby("ISO3", sort=True):
        population_fields = (
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
        population_values = {
            field: _single_value(group, field, "country group")
            for field in population_fields
        }
        group_weights = group["_aggregation_weight"].to_numpy(dtype="float64")
        row = {
            "ISO3": iso3,
            **population_values,
            "feature_period": feature_period,
            "target_period": target_period,
            "scope_months": scope_months,
            "area_count": int(len(group)),
            "positive_weight_area_count": int((group_weights > 0).sum()),
        }
        for column in SCORE_COLUMNS:
            mean, sd = _weighted_mean_and_sd(
                group[column].to_numpy(dtype="float64"), group_weights
            )
            row[column] = mean
            row["{0}_aggregation_uncertainty".format(column)] = sd
        row.update(
            {
                "score_aggregation_method": SCORE_AGGREGATION_METHOD,
                "aggregation_uncertainty_method": (
                    AGGREGATION_UNCERTAINTY_METHOD
                ),
                "aggregation_weight_field": "population_estimate",
                "model_package_id": model_package_id,
                "source_input": source_input,
            }
        )
        output_rows.append(row)

    return pd.DataFrame(output_rows).sort_values("ISO3").reset_index(drop=True)


def _load_prediction(path):
    return pd.read_csv(
        path,
        dtype={"area_id": "string", "admin_code": "string"},
    )


def build_country_level_predictions(
    prediction_dir,
    area_lookup_path,
    country_scope_path,
    census_idb_zip,
    output_dir,
    population_year=2026,
):
    prediction_dir = Path(prediction_dir)
    output_dir = Path(output_dir)
    prediction_files = []
    run_months = set()
    scopes = set()
    for path in sorted(prediction_dir.glob("ipcch_launch_*_scope_*m_predictions.csv")):
        match = PREDICTION_NAME.fullmatch(path.name)
        if match is None:
            continue
        prediction_files.append(path)
        run_months.add(match.group("run_month"))
        scopes.add(int(match.group("scope")))
    if len(run_months) != 1 or scopes != {0, 6, 12}:
        raise CountryAggregationError(
            "prediction directory must contain one 0m, 6m, and 12m run"
        )
    run_month = next(iter(run_months))

    area_lookup = pd.read_csv(
        area_lookup_path,
        dtype={"area_id": "string"},
        keep_default_na=False,
    )
    country_scope = pd.read_csv(
        country_scope_path,
        dtype="string",
        keep_default_na=False,
    )
    idb_population = read_census_idb_population(
        census_idb_zip, year=population_year
    )
    census_population = build_census_population_reference(
        country_scope, idb_population, year=population_year
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    population_path = (
        output_dir
        / "census_idb_{0}_ipcch_country_population.csv".format(population_year)
    )
    census_population.to_csv(population_path, index=False)

    outputs = []
    combined_frames = []
    for prediction_path in prediction_files:
        match = PREDICTION_NAME.fullmatch(prediction_path.name)
        scope = int(match.group("scope"))
        country_output = aggregate_country_scores(
            _load_prediction(prediction_path), area_lookup, census_population
        )
        output_path = output_dir / (
            "ipcch_launch_{0}_scope_{1}m_country_predictions.csv".format(
                run_month, scope
            )
        )
        country_output.to_csv(output_path, index=False)
        outputs.append(
            {
                "scope_months": scope,
                "path": str(output_path),
                "row_count": int(len(country_output)),
                "sha256": _sha256_file(output_path),
            }
        )
        combined_frames.append(country_output)

    combined = pd.concat(combined_frames, ignore_index=True).sort_values(
        ["scope_months", "ISO3"]
    )
    combined_path = output_dir / (
        "ipcch_launch_{0}_country_predictions.csv".format(run_month)
    )
    combined.to_csv(combined_path, index=False)
    summary = {
        "status": "passed",
        "run_month": run_month,
        "country_count": int(census_population["ISO3"].nunique()),
        "combined_row_count": int(len(combined)),
        "population_reference": {
            "year": int(population_year),
            "date": "{0:04d}-07-01".format(population_year),
            "measure": CENSUS_POPULATION_MEASURE,
            "source": CENSUS_POPULATION_SOURCE,
            "vintage": CENSUS_IDB_RELEASE,
            "url": CENSUS_IDB_URL,
            "zip_sha256": _sha256_file(census_idb_zip),
            "derived_table": str(population_path),
        },
        "score_aggregation_method": SCORE_AGGREGATION_METHOD,
        "aggregation_uncertainty_method": AGGREGATION_UNCERTAINTY_METHOD,
        "aggregation_weight_field": "population_estimate",
        "area_uncertainty_columns_removed": list(AREA_UNCERTAINTY_COLUMNS),
        "scope_outputs": sorted(outputs, key=lambda item: item["scope_months"]),
        "combined_output": {
            "path": str(combined_path),
            "row_count": int(len(combined)),
            "sha256": _sha256_file(combined_path),
        },
    }
    summary_path = output_dir / "country_level_run_summary.json"
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    summary["summary_path"] = str(summary_path)
    return summary


def _parser():
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate IPCCH area prediction scores to country level and merge "
            "U.S. Census Bureau IDB population."
        )
    )
    parser.add_argument("--prediction-dir", required=True, type=Path)
    parser.add_argument("--area-lookup", required=True, type=Path)
    parser.add_argument("--country-scope", required=True, type=Path)
    parser.add_argument("--census-idb-zip", type=Path)
    parser.add_argument("--census-idb-url", default=CENSUS_IDB_URL)
    parser.add_argument("--population-year", default=2026, type=int)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.census_idb_zip is not None:
            summary = build_country_level_predictions(
                args.prediction_dir,
                args.area_lookup,
                args.country_scope,
                args.census_idb_zip,
                args.output_dir,
                population_year=args.population_year,
            )
        else:
            with tempfile.TemporaryDirectory(prefix="ipcch-census-idb-") as tmp:
                census_zip = Path(tmp) / "idbzip.zip"
                _download_census_idb(args.census_idb_url, census_zip)
                summary = build_country_level_predictions(
                    args.prediction_dir,
                    args.area_lookup,
                    args.country_scope,
                    census_zip,
                    args.output_dir,
                    population_year=args.population_year,
                )
    except (CountryAggregationError, OSError, urllib.error.URLError) as exc:
        print("error: {0}".format(exc), file=sys.stderr)
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
