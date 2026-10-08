import pytest

from model_pipeline.ipcch_launch_runtime.population import (
    PopulationSelectionError,
    PopulationSnapshotBuilder,
)


def test_population_snapshot_uses_current_then_latest_prior_without_future_leakage():
    builder = PopulationSnapshotBuilder(feature_year=2026, feature_month=4)
    builder.add("A", 2026, 4, 120.0)
    builder.add("A", 2026, 5, 999.0)
    builder.add("B", 2025, 9, 80.0)
    builder.add("B", 2026, 5, 900.0)

    snapshot, summary = builder.build(["A", "B"])

    assert snapshot["A"] == {
        "population_estimate": 120.0,
        "population_reference_period": "2026-04",
        "population_imputation_method": "observed_feature_month",
    }
    assert snapshot["B"] == {
        "population_estimate": 80.0,
        "population_reference_period": "2025-09",
        "population_imputation_method": "last_observation_carried_forward",
    }
    assert summary == {
        "observed_feature_month_rows": 1,
        "last_observation_carried_forward_rows": 1,
        "missing_area_count": 0,
    }


def test_population_snapshot_rejects_area_without_current_or_prior_population():
    builder = PopulationSnapshotBuilder(feature_year=2026, feature_month=4)
    builder.add("A", 2026, 5, 100.0)

    with pytest.raises(PopulationSelectionError, match="no current or prior population"):
        builder.build(["A"])


@pytest.mark.parametrize("value", [-1, float("inf"), "not-a-number"])
def test_population_snapshot_rejects_invalid_candidate_population(value):
    builder = PopulationSnapshotBuilder(feature_year=2026, feature_month=4)

    with pytest.raises(PopulationSelectionError, match="finite and non-negative"):
        builder.add("A", 2026, 4, value)


def test_population_snapshot_rejects_conflicting_values_for_same_area_period():
    builder = PopulationSnapshotBuilder(feature_year=2026, feature_month=4)
    builder.add("A", 2026, 4, 100.0)

    with pytest.raises(PopulationSelectionError, match="conflicting population"):
        builder.add("A", 2026, 4, 101.0)
