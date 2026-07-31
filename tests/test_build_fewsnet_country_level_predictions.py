import csv
import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools" / "build_fewsnet_country_level_predictions.py"


def _load_builder_module():
    spec = importlib.util.spec_from_file_location(
        "build_fewsnet_country_level_predictions", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _prediction_rows(scope):
    target_month = {0: "2026-04", 6: "2026-10", 12: "2027-04"}[scope]
    values = [
        ("A1", "AFG", "Afghanistan", "1", -0.2, "raw_last_observed"),
        ("A2", "AFG", "Afghanistan", "3", 0.8, "raw_last_observed"),
        ("A3", "AFG", "Afghanistan", "", 0.4, "missing_raw"),
        ("A4", "AFG", "Afghanistan", "0", 0.9, "raw_last_observed"),
        ("B1", "BDI", "Burundi", "2", 0.5, "raw_last_observed"),
    ]
    rows = []
    for admin_code, iso3, country, population, probability, population_source in values:
        rows.append(
            {
                "admin_code": admin_code,
                "ADMIN0": country,
                "ADMIN1": "region",
                "ADMIN2": "district",
                "ADMIN3": "",
                "ISO3": iso3,
                "lat": "1.0",
                "lon": "2.0",
                "population": population,
                "population_reference_period": "2024-10" if population else "",
                "population_source": population_source,
                "probability_crisis": probability,
                "predicted_crisis": (
                    1 if admin_code == "A1" else int(probability >= 0.5)
                ),
                "threshold": 0.5,
                "cluster_id": "1",
                "prediction_source": "partition_model",
                "feature_month": "2026-04",
                "target_month": target_month,
                "horizon_months": scope,
                "suite_version": "test-suite",
                "model_artifact_path": "model/test/{0}m".format(scope),
                "source_input": "test-panel.csv",
            }
        )
    return rows


@pytest.fixture
def built_outputs(tmp_path):
    prediction_dir = tmp_path / "predictions" / "202604"
    fields = [
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
    ]
    for scope in (0, 6, 12):
        _write_csv(
            prediction_dir
            / "fewsnet_partitioned_rf_202604_scope_{0}m_predictions.csv".format(scope),
            fields,
            _prediction_rows(scope),
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
                "ISO3": "BDI",
                "country_code": "BI",
                "country": "Burundi",
                "country_en": "Burundi",
            },
            {
                "ISO3": "NAM",
                "country_code": "",
                "country": "Namibia",
                "country_en": "Namibia",
            },
        ],
    )
    census = tmp_path / "census_population.csv"
    population_fields = [
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
    ]
    _write_csv(
        census,
        population_fields,
        [
            {
                "ISO3": "AFG",
                "country": "Afghanistan",
                "country_en": "Afghanistan",
                "referenced_population": 1000,
                "population_reference_year": 2026,
                "population_reference_date": "2026-07-01",
                "population_measure": "Total mid-year population",
                "population_source": "U.S. Census Bureau International Database",
                "population_vintage": "December 2025 release",
                "population_source_url": "https://example.test/census.zip",
                "census_genc_codes": "AF",
            },
            {
                "ISO3": "BDI",
                "country": "Burundi",
                "country_en": "Burundi",
                "referenced_population": 2000,
                "population_reference_year": 2026,
                "population_reference_date": "2026-07-01",
                "population_measure": "Total mid-year population",
                "population_source": "U.S. Census Bureau International Database",
                "population_vintage": "December 2025 release",
                "population_source_url": "https://example.test/census.zip",
                "census_genc_codes": "BI",
            },
        ],
    )

    output_dir = prediction_dir / "country_level"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--prediction-dir",
            str(prediction_dir),
            "--country-scope",
            str(country_scope),
            "--census-population",
            str(census),
            "--output-dir",
            str(output_dir),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return prediction_dir, output_dir, result


def test_negative_area_probabilities_are_clipped_and_predictions_stay_consistent(
    built_outputs,
):
    prediction_dir, output_dir, result = built_outputs
    assert result.returncode == 0, result.stderr or result.stdout
    corrected = pd.read_csv(
        prediction_dir / "fewsnet_partitioned_rf_202604_scope_0m_predictions.csv",
        dtype={"admin_code": "string"},
    ).set_index("admin_code")
    assert corrected.loc["A1", "probability_crisis"] == 0.0
    assert corrected.loc["A2", "probability_crisis"] == 0.8
    assert corrected.loc["A1", "predicted_crisis"] == 0
    assert corrected.loc["A4", "predicted_crisis"] == 1
    summary = json.loads(
        (output_dir / "country_level_run_summary.json").read_text(encoding="utf-8")
    )
    assert summary["negative_probability_cells_clipped"] == 3
    assert summary["predicted_crisis_cells_recomputed"] == 3


def test_area_threshold_must_be_within_probability_range():
    builder = _load_builder_module()
    frame = pd.DataFrame(
        {
            "probability_crisis": [0.2],
            "predicted_crisis": [0],
            "threshold": [1.2],
        }
    )
    with pytest.raises(builder.CountryAggregationError, match="threshold"):
        builder.clip_negative_probabilities(frame)


def test_country_probability_uses_positive_population_and_area_dispersion(
    built_outputs,
):
    prediction_dir, output_dir, result = built_outputs
    assert result.returncode == 0, result.stderr or result.stdout
    country = pd.read_csv(
        output_dir
        / "fewsnet_partitioned_rf_202604_scope_0m_country_predictions.csv"
    ).set_index("ISO3")
    afghanistan = country.loc["AFG"]
    assert afghanistan["referenced_population"] == 1000
    assert afghanistan["probability_crisis"] == pytest.approx(0.6)
    assert afghanistan["probability_crisis_area_dispersion"] == pytest.approx(
        math.sqrt(0.12)
    )
    assert afghanistan["area_count"] == 4
    assert afghanistan["finite_population_area_count"] == 3
    assert afghanistan["positive_population_area_count"] == 2
    assert afghanistan["zero_population_area_count"] == 1
    assert afghanistan["missing_population_area_count"] == 1
    assert afghanistan["area_population_weight_sum"] == pytest.approx(4.0)
    assert "country_predicted_crisis" not in country.columns


def test_builder_writes_three_scopes_combined_and_census_subset(built_outputs):
    prediction_dir, output_dir, result = built_outputs
    assert result.returncode == 0, result.stderr or result.stdout
    expected_scope_files = {
        "fewsnet_partitioned_rf_202604_scope_0m_country_predictions.csv",
        "fewsnet_partitioned_rf_202604_scope_6m_country_predictions.csv",
        "fewsnet_partitioned_rf_202604_scope_12m_country_predictions.csv",
    }
    assert expected_scope_files <= {path.name for path in output_dir.iterdir()}
    population = pd.read_csv(
        output_dir / "census_idb_2026_fewsnet_country_population.csv"
    )
    assert population["ISO3"].tolist() == ["AFG", "BDI"]
    combined = pd.read_csv(
        output_dir / "fewsnet_partitioned_rf_202604_country_predictions.csv"
    )
    assert len(combined) == 6
    assert combined["horizon_months"].tolist() == [0, 0, 6, 6, 12, 12]
    assert set(combined["score_aggregation_method"]) == {
        "population_weighted_mean_v1"
    }
    assert set(combined["area_dispersion_method"]) == {
        "population_weighted_area_score_sd_v1"
    }
    assert set(combined["aggregation_weight_field"]) == {"population"}
