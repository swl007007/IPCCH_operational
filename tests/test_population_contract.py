import math

import pandas as pd
import pytest

from model_pipeline.ipcch_launch_runtime.population import (
    PopulationContractError,
    validate_population_contract,
)


def _population_frame(**overrides):
    frame = pd.DataFrame(
        {
            "population_estimate": [100.0],
            "population_reference_period": ["2026-04"],
            "population_imputation_method": ["observed_feature_month"],
        }
    )
    for column, value in overrides.items():
        frame[column] = [value]
    return frame


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"population_estimate": -1.0}, "finite and non-negative"),
        ({"population_estimate": math.inf}, "finite and non-negative"),
        (
            {"population_reference_period": "2026-05"},
            "must not be later",
        ),
        (
            {"population_imputation_method": "nearest_past"},
            "does not match reference period",
        ),
    ],
)
def test_population_contract_rejects_invalid_semantics(overrides, message):
    with pytest.raises(PopulationContractError, match=message):
        validate_population_contract(
            _population_frame(**overrides), feature_month="2026-04"
        )


def test_population_contract_returns_both_method_counts_even_when_one_is_zero():
    summary = validate_population_contract(
        _population_frame(), feature_month="2026-04"
    )

    assert summary == {
        "observed_feature_month": 1,
        "last_observation_carried_forward": 0,
    }
