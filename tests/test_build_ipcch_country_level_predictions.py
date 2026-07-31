import csv
import math
import subprocess
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools" / "build_ipcch_country_level_predictions.py"
SCORE_COLUMNS = tuple(
    "phase{0}_worse_score".format(phase) for phase in range(2, 6)
)


def _write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _prediction_rows(scope_months):
    target_period = {0: "2026-04", 6: "2026-10", 12: "2027-04"}[
        scope_months
    ]
    values = {
        "A1": (1.0, (0.0, 0.2, 0.4, 0.6)),
        "A2": (3.0, (1.0, 0.2, 0.8, 0.0)),
        "N1": (2.0, (0.5, 0.4, 0.3, 0.2)),
        "P1": (4.0, (0.2, 0.4, 0.6, 0.8)),
        "P2": (1.0, (0.8, 0.6, 0.4, 0.2)),
    }
    rows = []
    for row_id, (area_id, (weight, scores)) in enumerate(values.items()):
        row = {
            "area_id": area_id,
            "admin_code": area_id,
            "_row_id": row_id,
            "population_estimate": weight,
            "population_reference_period": "2026-04",
            "population_imputation_method": "observed_feature_month",
            "prediction_uncertainty": "high",
            "decision_margin": 0.01,
            "uncertainty_critical_boundary": "phase2_worse",
            "uncertainty_method": "qualitative_threshold_margin_v1",
            "feature_period": "2026-04",
            "target_period": target_period,
            "scope_months": scope_months,
            "model_package_id": "test-model",
            "source_input": "test-input.csv",
        }
        for column, score in zip(SCORE_COLUMNS, scores):
            row[column] = score
        rows.append(row)
    return rows


def _prepare_inputs(tmp_path):
    prediction_dir = tmp_path / "predictions" / "202604"
    prediction_fields = [
        "area_id",
        "admin_code",
        "_row_id",
        "population_estimate",
        "population_reference_period",
        "population_imputation_method",
        *SCORE_COLUMNS,
        "prediction_uncertainty",
        "decision_margin",
        "uncertainty_critical_boundary",
        "uncertainty_method",
        "feature_period",
        "target_period",
        "scope_months",
        "model_package_id",
        "source_input",
    ]
    for scope in (0, 6, 12):
        _write_csv(
            prediction_dir
            / "ipcch_launch_202604_scope_{0}m_predictions.csv".format(scope),
            prediction_fields,
            _prediction_rows(scope),
        )

    area_lookup = tmp_path / "country_area_id_lookup.csv"
    _write_csv(
        area_lookup,
        ["area_id", "iso3", "country", "country_code", "country_en"],
        [
            {
                "area_id": "A1",
                "iso3": "AFG",
                "country": "Afghanistan",
                "country_code": "AF",
                "country_en": "Afghanistan",
            },
            {
                "area_id": "A2",
                "iso3": "AFG",
                "country": "Afghanistan",
                "country_code": "AF",
                "country_en": "Afghanistan",
            },
            {
                "area_id": "N1",
                "iso3": "NAM",
                "country": "Namibia",
                "country_code": "",
                "country_en": "Namibia",
            },
            {
                "area_id": "P1",
                "iso3": "PSE",
                "country": "Palestinian Territory",
                "country_code": "PS",
                "country_en": "Palestine, State of",
            },
            {
                "area_id": "P2",
                "iso3": "PSE",
                "country": "Palestinian Territory",
                "country_code": "PS",
                "country_en": "Palestine, State of",
            },
        ],
    )

    country_scope = tmp_path / "country_scope.csv"
    _write_csv(
        country_scope,
        ["ISO3", "country_code", "country", "country_en"],
        [
            {
                "ISO3": "AFG",
                "country_code": "AF",
                "country": "Afghanistan",
                "country_en": "Afghanistan",
            },
            {
                "ISO3": "NAM",
                "country_code": "",
                "country": "Namibia",
                "country_en": "Namibia",
            },
            {
                "ISO3": "PSE",
                "country_code": "PS",
                "country": "Palestinian Territory",
                "country_en": "Palestine, State of",
            },
        ],
    )

    census_zip = tmp_path / "census-idb.zip"
    idb_rows = "\n".join(
        [
            "#YR|GEO_ID|POP",
            "2025|W140000WOAF|900",
            "2026|W140000WOAF|1000",
            "2026|W140000WONA|2000",
            "2026|W140000WOXG|300",
            "2026|W140000WOXW|700",
            "2026|W400000WOXG001|999999",
        ]
    )
    with zipfile.ZipFile(census_zip, "w") as archive:
        archive.writestr("idb5yr.txt", idb_rows + "\n")
        archive.writestr("readme.txt", "International Database test fixture\n")

    return prediction_dir, area_lookup, country_scope, census_zip


@pytest.fixture
def built_outputs(tmp_path):
    prediction_dir, area_lookup, country_scope, census_zip = _prepare_inputs(
        tmp_path
    )
    output_dir = tmp_path / "country-level"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--prediction-dir",
            str(prediction_dir),
            "--area-lookup",
            str(area_lookup),
            "--country-scope",
            str(country_scope),
            "--census-idb-zip",
            str(census_zip),
            "--output-dir",
            str(output_dir),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return output_dir, result


def test_census_population_uses_iso3_crosswalk_and_combines_palestinian_areas(
    built_outputs,
):
    output_dir, result = built_outputs
    assert result.returncode == 0, result.stderr or result.stdout
    population = pd.read_csv(
        output_dir / "census_idb_2026_ipcch_country_population.csv",
        keep_default_na=False,
    ).set_index("ISO3")

    assert population.loc["AFG", "referenced_population"] == 1000
    assert population.loc["NAM", "referenced_population"] == 2000
    assert population.loc["PSE", "referenced_population"] == 1000
    assert population.loc["NAM", "census_genc_codes"] == "NA"
    assert population.loc["PSE", "census_genc_codes"] == "XG;XW"
    assert set(population["population_reference_date"]) == {"2026-07-01"}


def test_country_scores_use_population_weighted_mean_and_area_dispersion(
    built_outputs,
):
    output_dir, result = built_outputs
    assert result.returncode == 0, result.stderr or result.stdout
    output = pd.read_csv(
        output_dir / "ipcch_launch_202604_scope_0m_country_predictions.csv"
    ).set_index("ISO3")
    afghanistan = output.loc["AFG"]

    assert afghanistan["referenced_population"] == 1000
    assert afghanistan["phase2_worse_score"] == pytest.approx(0.75)
    assert afghanistan[
        "phase2_worse_score_aggregation_uncertainty"
    ] == pytest.approx(math.sqrt(0.1875))
    assert afghanistan["phase3_worse_score"] == pytest.approx(0.2)
    assert afghanistan[
        "phase3_worse_score_aggregation_uncertainty"
    ] == pytest.approx(0.0)
    assert afghanistan["area_count"] == 2
    assert afghanistan["positive_weight_area_count"] == 2
    assert afghanistan["score_aggregation_method"] == (
        "population_weighted_mean_v1"
    )
    assert afghanistan["aggregation_uncertainty_method"] == (
        "population_weighted_area_score_sd_v1"
    )
    for removed_column in (
        "prediction_uncertainty",
        "decision_margin",
        "uncertainty_critical_boundary",
        "uncertainty_method",
    ):
        assert removed_column not in output.columns


def test_country_builder_writes_each_scope_and_one_combined_table(built_outputs):
    output_dir, result = built_outputs
    assert result.returncode == 0, result.stderr or result.stdout
    expected_scope_files = {
        "ipcch_launch_202604_scope_0m_country_predictions.csv",
        "ipcch_launch_202604_scope_6m_country_predictions.csv",
        "ipcch_launch_202604_scope_12m_country_predictions.csv",
    }
    assert expected_scope_files <= {path.name for path in output_dir.iterdir()}

    combined = pd.read_csv(
        output_dir / "ipcch_launch_202604_country_predictions.csv"
    )
    assert len(combined) == 9
    assert combined["scope_months"].tolist() == [0, 0, 0, 6, 6, 6, 12, 12, 12]
    assert combined.groupby("scope_months")["ISO3"].nunique().to_dict() == {
        0: 3,
        6: 3,
        12: 3,
    }
