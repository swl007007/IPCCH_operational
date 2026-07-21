from importlib import import_module
import pickle
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from fewsnet_partitioned_rf_pipeline.core.partitions import PartitionMap
from fewsnet_partitioned_rf_pipeline.core.types import FeatureContract


FORMAL_PREDICTION_COLUMNS = [
    "admin_code",
    "feature_month",
    "target_month",
    "horizon_months",
    "probability_crisis",
    "predicted_crisis",
    "threshold",
    "cluster_id",
    "prediction_source",
    "suite_version",
    "vertex_model_resource_name",
    "vertex_model_version_id",
]


def _training_module():
    return import_module("fewsnet_partitioned_rf_pipeline.core.training")


def _inference_module():
    return import_module("fewsnet_partitioned_rf_pipeline.core.inference")


def _feature_contract() -> FeatureContract:
    return FeatureContract(
        schema_version="synthetic-feature-contract-v1",
        transformation_version="synthetic-direct-alignment-v1",
        feature_columns=("signal", "auxiliary"),
        feature_dtypes=("float64", "float64"),
        required_source_columns=("signal", "auxiliary"),
        iso_mapping={},
        source_columns_sha256="a" * 64,
        feature_schema_sha256="b" * 64,
    )


def _partition_map() -> PartitionMap:
    return PartitionMap.from_frame(
        pd.DataFrame(
            {
                "admin_code": ["C0A", "C0B", "C1", "C2A", "C2B"],
                "cluster_id": [0, 0, 1, 2, 2],
            }
        )
    )


def _aligned_training_frame() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    target_months = pd.period_range("2023-03", periods=36, freq="M")
    areas = (
        ("C0A", lambda index: index % 2),
        ("C0B", lambda index: (index + 1) % 2),
        ("C1", lambda index: index % 2),
        ("C2A", lambda index: 0),
        ("C2B", lambda index: 0),
    )
    for area_index, (admin_code, target_for_index) in enumerate(areas):
        for month_index, target_month in enumerate(target_months):
            rows.append(
                {
                    "admin_code": admin_code,
                    "feature_month": target_month,
                    "target_month": target_month,
                    "fews_ipc_crisis": target_for_index(month_index),
                    "signal": float(month_index),
                    "auxiliary": float(area_index * 100 + month_index),
                }
            )
    return pd.DataFrame(reversed(rows)).reset_index(drop=True)


def _inference_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "admin_code": ["UNMAPPED", "C2A", "C1", "C0B"],
            "feature_month": ["2026-04"] * 4,
            "target_month": ["2026-04"] * 4,
            "signal": [40.0, 41.0, np.nan, 43.0],
            "auxiliary": [400.0, 401.0, 402.0, 403.0],
        },
        index=[9, 3, 7, 1],
    )


def _train_horizon():
    return _training_module().train_horizon_model(
        _aligned_training_frame(),
        _feature_contract(),
        _partition_map(),
        "0m",
    )


def _direct_partition_arrays():
    frame = _aligned_training_frame()
    clusters = _partition_map().route(frame["admin_code"]).to_numpy(dtype=object)
    return (
        frame.loc[:, ["signal", "auxiliary"]].to_numpy(dtype=float),
        frame["fews_ipc_crisis"].to_numpy(dtype=int),
        clusters,
    )


def test_smote_import_bridge_restores_sklearn_globals():
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import sklearn.ensemble as ensemble",
                    "import sklearn.utils.validation as validation",
                    "original_adaboost = ensemble.AdaBoostClassifier",
                    "had_private = hasattr(validation, '_is_pandas_df')",
                    "original_private = getattr(validation, '_is_pandas_df', None)",
                    "import fewsnet_partitioned_rf_pipeline.core.training",
                    "assert ensemble.AdaBoostClassifier is original_adaboost",
                    "assert hasattr(validation, '_is_pandas_df') is had_private",
                    "if had_private:",
                    "    assert validation._is_pandas_df is original_private",
                )
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert probe.returncode == 0, probe.stderr


def test_partition_training_records_all_states_and_is_byte_repeatable():
    training = _training_module()
    inference = _inference_module()
    X, y, cluster_ids = _direct_partition_arrays()

    first = training.train_partition_models(X, y, cluster_ids, min_samples=50)
    second = training.train_partition_models(X, y, cluster_ids, min_samples=50)

    assert first.partition_status == {
        0: "partition_model",
        1: "pooled_small_partition",
        2: "pooled_single_class",
    }
    assert first.partition_models[0] is not None
    assert first.partition_models[1] is None
    assert first.partition_models[2] is None
    assert first.partition_metadata[0]["smote_status"] == "resampled"
    assert first.partition_metadata[0]["original_class_counts"] == {
        "0": 36,
        "1": 36,
    }
    assert first.partition_metadata[0]["resampled_class_counts"] == {
        "0": 36,
        "1": 36,
    }

    X_test = np.array(
        [[4.0, 104.0], [2.0, 202.0], [3.0, 303.0], [1.0, 1.0]]
    )
    groups_test = np.array([1, 2, None, 0], dtype=object)
    first_probability = inference.predict_partition_probabilities(
        first.partition_models,
        first.pooled_model,
        X_test,
        groups_test,
    )
    second_probability = inference.predict_partition_probabilities(
        second.partition_models,
        second.pooled_model,
        X_test,
        groups_test,
    )

    assert first_probability.tobytes() == second_probability.tobytes()
    assert np.isfinite(first_probability).all()
    assert ((0.0 <= first_probability) & (first_probability <= 1.0)).all()


def test_train_horizon_model_routes_formal_rows_and_survives_pickle_round_trip():
    first = _train_horizon()
    second = _train_horizon()
    inference_frame = _inference_frame().drop(columns=["target_month"])

    predictions = first.predictor.predict_frame(inference_frame)
    repeated = second.predictor.predict_frame(inference_frame)
    restored = pickle.loads(pickle.dumps(first.predictor)).predict_frame(
        inference_frame
    )

    assert predictions.columns.tolist() == FORMAL_PREDICTION_COLUMNS
    assert predictions["admin_code"].tolist() == inference_frame[
        "admin_code"
    ].tolist()
    assert predictions["feature_month"].tolist() == ["2026-04"] * 4
    assert predictions["target_month"].tolist() == ["2026-04"] * 4
    assert predictions["horizon_months"].tolist() == [0] * 4
    assert predictions["prediction_source"].tolist() == [
        "pooled_unmapped",
        "pooled_single_class",
        "pooled_small_partition",
        "partition_model",
    ]
    assert pd.isna(predictions.loc[0, "cluster_id"])
    assert predictions.loc[1:, "cluster_id"].tolist() == [2, 1, 0]
    assert predictions["probability_crisis"].between(0.0, 1.0).all()
    np.testing.assert_array_equal(
        predictions["predicted_crisis"].to_numpy(),
        (
            predictions["probability_crisis"].to_numpy()
            >= predictions["threshold"].to_numpy()
        ).astype(int),
    )
    assert predictions["threshold"].nunique() == 1
    assert predictions["threshold"].iloc[0] == first.threshold_report["threshold"]
    assert predictions[
        [
            "suite_version",
            "vertex_model_resource_name",
            "vertex_model_version_id",
        ]
    ].eq("").all().all()
    assert predictions["probability_crisis"].to_numpy().tobytes() == repeated[
        "probability_crisis"
    ].to_numpy().tobytes()
    pd.testing.assert_frame_equal(predictions, restored)


def test_predictor_rejects_a_target_month_that_conflicts_with_its_horizon():
    predictor = _train_horizon().predictor
    conflicting = _inference_frame().assign(target_month="2026-05")

    with pytest.raises(ValueError, match="target_month.*horizon"):
        predictor.predict_frame(conflicting)


def test_predictor_uses_missing_partition_model_fallback():
    result = _train_horizon()
    result.predictor.partition_models[0] = None

    predictions = result.predictor.predict_frame(
        _inference_frame().loc[lambda frame: frame["admin_code"].eq("C0B")]
    )

    assert predictions["prediction_source"].tolist() == [
        "pooled_missing_partition_model"
    ]


def test_threshold_smote_never_sees_the_six_validation_months(monkeypatch):
    training = _training_module()
    observed_fit_arrays: list[np.ndarray] = []
    original_fit_resample = training.SMOTE.fit_resample

    def recording_fit_resample(self, X, y):
        observed_fit_arrays.append(np.asarray(X, dtype=float).copy())
        return original_fit_resample(self, X, y)

    monkeypatch.setattr(training.SMOTE, "fit_resample", recording_fit_resample)

    training.train_horizon_model(
        _aligned_training_frame(),
        _feature_contract(),
        _partition_map(),
        "0m",
    )

    assert [len(values) for values in observed_fit_arrays] == [60, 72]
    assert observed_fit_arrays[0][:, 0].max() == 29.0
    assert not np.isin(
        observed_fit_arrays[0][:, 0],
        np.arange(30.0, 36.0),
    ).any()
    assert observed_fit_arrays[1][:, 0].max() == 35.0


def test_smote_neighbor_selection_minority_skip_and_failure_metadata(monkeypatch):
    training = _training_module()

    X = np.column_stack((np.arange(50, dtype=float), np.ones(50)))
    cluster_ids = np.zeros(50, dtype=int)
    one_minority = np.zeros(50, dtype=int)
    one_minority[-1] = 1
    skipped = training.train_partition_models(
        X,
        one_minority,
        cluster_ids,
        min_samples=50,
    )
    assert skipped.partition_status[0] == "partition_model"
    assert skipped.partition_models[0] is not None
    assert skipped.partition_metadata[0]["smote_status"] == (
        "skipped_minority_lt_2"
    )

    two_minority = np.zeros(50, dtype=int)
    two_minority[-2:] = 1

    def fail_smote(self, X, y):
        raise RuntimeError("synthetic SMOTE failure")

    monkeypatch.setattr(training.SMOTE, "fit_resample", fail_smote)
    failed = training.train_partition_models(
        X,
        two_minority,
        cluster_ids,
        min_samples=50,
    )
    assert failed.partition_status[0] == "partition_model"
    assert failed.partition_models[0] is not None
    assert failed.partition_metadata[0]["smote_status"] == "failed"
    assert failed.partition_metadata[0]["smote_k_neighbors"] == 1
    assert failed.partition_metadata[0]["smote_failure_reason"] == (
        "RuntimeError: synthetic SMOTE failure"
    )
    assert failed.partition_metadata[0]["resampled_class_counts"] is None


@pytest.mark.parametrize(("label", "expected"), [(0, 0.0), (1, 1.0)])
def test_class_one_probability_handles_single_column_predict_proba(
    label,
    expected,
):
    training = _training_module()
    inference = _inference_module()
    X = np.arange(12, dtype=float).reshape(6, 2)
    y = np.full(6, label, dtype=int)
    cluster_ids = np.full(6, None, dtype=object)

    models = training.train_partition_models(
        X,
        y,
        cluster_ids,
        min_samples=50,
    )
    probability = inference.predict_partition_probabilities(
        models.partition_models,
        models.pooled_model,
        X[:2],
        np.array([None, 99], dtype=object),
    )

    np.testing.assert_array_equal(probability, np.full(2, expected))


def test_train_horizon_model_rejects_invalid_window_horizon_features_and_coverage():
    training = _training_module()
    frame = _aligned_training_frame()
    contract = _feature_contract()
    mapping = _partition_map()

    only_35_months = frame.loc[
        ~frame["target_month"].eq(pd.Period("2023-03", freq="M"))
    ]
    with pytest.raises(ValueError, match="36.*target_month"):
        training.train_horizon_model(
            only_35_months,
            contract,
            mapping,
            "0m",
        )

    with pytest.raises(ValueError, match="horizon_key"):
        training.train_horizon_model(frame, contract, mapping, "3m")

    with pytest.raises(ValueError, match="auxiliary"):
        training.train_horizon_model(
            frame.drop(columns=["auxiliary"]),
            contract,
            mapping,
            "0m",
        )

    low_coverage = PartitionMap.from_frame(
        pd.DataFrame({"admin_code": ["C0A"], "cluster_id": [0]})
    )
    with pytest.raises(ValueError, match="coverage dropped"):
        training.train_horizon_model(
            frame,
            contract,
            low_coverage,
            "0m",
        )


def test_train_horizon_model_rejects_recorded_partition_checksum_drift(
    monkeypatch,
):
    training = _training_module()
    monkeypatch.setattr(training, "PARTITION_ASSET_SHA256", "0" * 64)

    with pytest.raises(ValueError, match="partition asset SHA-256 mismatch"):
        training.train_horizon_model(
            _aligned_training_frame(),
            _feature_contract(),
            _partition_map(),
            "0m",
        )
