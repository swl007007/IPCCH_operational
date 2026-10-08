import pandas as pd
import pytest

from cloud.batch import evi_reference


def test_absent_reference_sample_is_not_provided():
    assert evi_reference.compare_evi_reference(None, None) == {"status": "not_provided"}


def test_malformed_optional_reference_is_advisory_warning():
    observed = pd.DataFrame(
        {"area_id": ["A"], "year": [2026], "month": [4], "EVI_mean": [1.0]}
    )
    reference = pd.DataFrame({"bad_key": ["A"], "EVI_mean": [1.0]})

    result = evi_reference.compare_evi_reference(observed, reference)

    assert result["status"] == "malformed_reference"
    assert result["severity"] == "warning"


def test_zero_matched_observations_is_advisory_warning():
    observed = pd.DataFrame(
        {"area_id": ["A"], "year": [2026], "month": [4], "EVI_mean": [1.0]}
    )
    reference = pd.DataFrame(
        {"area_id": ["B"], "year": [2026], "month": [4], "EVI_mean": [1.0]}
    )

    result = evi_reference.compare_evi_reference(observed, reference)

    assert result["status"] == "zero_matches"
    assert result["severity"] == "warning"


def test_insufficient_correlation_pairs_is_advisory_warning():
    observed = pd.DataFrame(
        {"area_id": ["A"], "year": [2026], "month": [4], "EVI_mean": [1.0]}
    )
    reference = pd.DataFrame(
        {"area_id": ["A"], "year": [2026], "month": [4], "EVI_mean": [1.2]}
    )

    result = evi_reference.compare_evi_reference(observed, reference)

    assert result["status"] == "insufficient_pairs"
    assert result["matched_observations"] == 1


def test_numeric_differences_are_advisory_not_hard_failures():
    observed = pd.DataFrame(
        {
            "area_id": ["A", "B"],
            "year": [2026, 2026],
            "month": [4, 4],
            "EVI_mean": [1.0, 2.0],
        }
    )
    reference = pd.DataFrame(
        {
            "area_id": ["A", "B"],
            "year": [2026, 2026],
            "month": [4, 4],
            "EVI_mean": [1.1, 1.9],
        }
    )

    result = evi_reference.compare_evi_reference(observed, reference)

    assert result["status"] == "advisory_difference"
    assert result["severity"] == "warning"
    assert result["matched_observations"] == 2
    assert result["max_abs_diff"] == pytest.approx(0.1)
