import json
from pathlib import Path

import numpy as np

from fewsnet_partitioned_rf_pipeline.core.inference import (
    predict_partition_probabilities,
)
from fewsnet_partitioned_rf_pipeline.core.training import train_partition_models


def test_partition_training_matches_frozen_reference_fixture():
    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures/fewsnet_partitioned_rf/stage3_reference_parity.json"
    )
    payload = json.loads(fixture.read_text())
    models = train_partition_models(
        np.asarray(payload["X_train"], dtype=float),
        np.asarray(payload["y_train"], dtype=int),
        np.asarray(payload["groups_train"], dtype=int),
        min_samples=int(payload["min_samples"]),
    )
    probability = predict_partition_probabilities(
        models.partition_models,
        models.pooled_model,
        np.asarray(payload["X_test"], dtype=float),
        np.asarray(payload["groups_test"], dtype=int),
    )
    assert np.allclose(
        probability,
        payload["expected_probability"],
        atol=1e-12,
    )
    assert models.partition_status == {
        int(key): value
        for key, value in payload["expected_partition_status"].items()
    }
    assert (probability >= payload["threshold"]).astype(int).tolist() == payload[
        "expected_class"
    ]
