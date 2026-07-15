import pandas as pd
import pytest

from model_pipeline.ipcch_launch_runtime.uncertainty import (
    UNCERTAINTY_METHOD,
    calculate_qualitative_uncertainty,
)


def test_uncertainty_labels_use_approved_boundaries_and_fixed_tie_order():
    scores = pd.DataFrame(
        {
            "phase2_worse_score": [0.21, 0.25, 0.30],
            "phase3_worse_score": [0.80, 0.80, 0.80],
            "phase4_worse_score": [0.80, 0.80, 0.80],
            "phase5_worse_score": [0.80, 0.80, 0.80],
        }
    )
    thresholds = {
        "phase2_worse": 0.20,
        "phase3_worse": 0.20,
        "phase4_worse": 0.20,
        "phase5_worse": 0.20,
    }

    fields, summary = calculate_qualitative_uncertainty(scores, thresholds)

    assert fields["prediction_uncertainty"].tolist() == ["high", "medium", "low"]
    assert fields["decision_margin"].tolist() == pytest.approx([0.01, 0.05, 0.10])
    assert fields["uncertainty_critical_boundary"].tolist() == [
        "phase2_worse",
        "phase2_worse",
        "phase2_worse",
    ]
    assert set(fields["uncertainty_method"]) == {UNCERTAINTY_METHOD}
    assert summary["label_counts"] == {"high": 1, "medium": 1, "low": 1}


def test_uncertainty_uses_each_target_threshold_and_phase_order_for_ties():
    scores = pd.DataFrame(
        {
            "phase2_worse_score": [0.40],
            "phase3_worse_score": [0.35],
            "phase4_worse_score": [0.90],
            "phase5_worse_score": [0.90],
        }
    )
    thresholds = {
        "phase2_worse": 0.45,
        "phase3_worse": 0.30,
        "phase4_worse": 0.20,
        "phase5_worse": 0.20,
    }

    fields, _ = calculate_qualitative_uncertainty(scores, thresholds)

    assert fields.loc[0, "decision_margin"] == pytest.approx(0.05)
    assert fields.loc[0, "uncertainty_critical_boundary"] == "phase2_worse"
