"""Full-history (all eligible rows, fixed threshold, no evaluation) FEWSNET fit path.

No estimator is fitted here: the partition-model primitive is replaced by a recorder
that returns the already-fitted April bootstrap models (serialization fixture only),
and any real RandomForestClassifier.fit or SMOTE.fit_resample call fails the test.
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier

from fewsnet_partitioned_rf_pipeline.config import (
    FEATURE_CONTRACT_PATH,
    FULL_DATA_PACKAGE_SCHEMA,
    PARTITION_ASSET_PATH,
    PARTITION_ASSET_SHA256,
    PARTITION_MIN_SAMPLES,
    TARGET_COLUMN,
)
from fewsnet_partitioned_rf_pipeline.core import training
from fewsnet_partitioned_rf_pipeline.core.horizons import (
    FEATURE_MONTH_COLUMN,
    TARGET_MONTH_COLUMN,
    align_horizon,
)
from fewsnet_partitioned_rf_pipeline.core.partitions import PartitionMap
from fewsnet_partitioned_rf_pipeline.core.preprocessing import (
    MaxPlusImputer,
    load_feature_contract,
)
from fewsnet_partitioned_rf_pipeline.core.validation import (
    PackageValidationError,
    validate_horizon_training_report,
    validate_threshold_report,
)
from fewsnet_partitioned_rf_pipeline.local.package import (
    LocalPackageMetadata,
    load_local_model_package,
    write_local_model_package,
)


RUNTIME_ROOT = Path(__file__).resolve().parents[2]
LEGACY_PACKAGE = RUNTIME_ROOT / "bootstrap/models/fewsnet/0m"
CONTRACT = load_feature_contract(FEATURE_CONTRACT_PATH)
PARTITIONS = PartitionMap.load(PARTITION_ASSET_PATH, PARTITION_ASSET_SHA256)
needs_legacy = pytest.mark.skipif(
    not LEGACY_PACKAGE.is_dir(), reason="bootstrap package not present"
)


@pytest.fixture(autouse=True)
def no_real_estimator_fit(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("estimator fitting is out of scope for unit checks")

    monkeypatch.setattr(RandomForestClassifier, "fit", forbidden)
    monkeypatch.setattr(training.SMOTE, "fit_resample", forbidden)


@pytest.fixture(scope="module")
def legacy_predictor():
    if not LEGACY_PACKAGE.is_dir():
        pytest.skip("bootstrap package not present")
    return joblib.load(LEGACY_PACKAGE / "model.joblib")


@pytest.fixture
def recorded_fit(monkeypatch, legacy_predictor):
    """Record exact fit-primitive inputs; return the already-fitted April models."""
    calls = []

    def record(X, y, cluster_ids, min_samples):
        calls.append({"X": np.array(X), "y": np.array(y),
                      "clusters": list(cluster_ids), "min_samples": min_samples})
        return training.PartitionModels(
            pooled_model=legacy_predictor.pooled_model,
            partition_models=dict(legacy_predictor.partition_models),
            partition_status=dict(legacy_predictor.partition_status),
            partition_metadata=dict(legacy_predictor.partition_metadata),
        )

    monkeypatch.setattr(training, "train_partition_models", record)
    return calls


def _mapped_codes(count):
    return sorted(PARTITIONS._clusters_by_admin, key=int)[:count]


def _feature_frame(codes, months, target):
    """Rows for every (code, month); target(code_index, month_index) may return NaN."""
    rng = np.random.default_rng(7)
    rows = [{"admin_code": code, FEATURE_MONTH_COLUMN: pd.Period(month, "M"),
             TARGET_COLUMN: target(code_index, month_index)}
            for code_index, code in enumerate(codes)
            for month_index, month in enumerate(months)]
    frame = pd.DataFrame(rows)
    features = rng.normal(size=(len(frame), len(CONTRACT.feature_columns)))
    features[::5, 3] = np.nan  # some missing predictors reach the saved imputer
    return pd.concat([frame, pd.DataFrame(features, columns=list(CONTRACT.feature_columns))], axis=1)


def _aligned(horizon=6, months=60, end="2026-06"):
    """Aligned rows spanning ``months`` target months that end at ``end``."""
    codes = _mapped_codes(12)
    first = pd.Period(end, "M") - (months - 1) - horizon
    periods = [str(first + offset) for offset in range(months + horizon)]
    frame = _feature_frame(codes, periods, lambda c, m: float((c + m) % 3 == 0))
    return align_horizon(frame, horizon).frame


def _fit(aligned, horizon_key="6m", threshold=0.41):
    return training.train_full_history_model(
        aligned, CONTRACT, PARTITIONS, horizon_key,
        threshold=threshold, threshold_source="fixed-test-source",
    )


def test_missing_labels_stay_excluded_not_zero():
    codes = _mapped_codes(3)
    months = ["2026-02", "2026-03", "2026-06"]
    labels = {("2026-02", 0): 1.0, ("2026-06", 0): np.nan, ("2026-06", 1): 0.0}
    frame = _feature_frame(codes, months, lambda c, m: labels.get((months[m], c), np.nan))
    result = align_horizon(frame, 0)
    kept = set(zip(result.frame["admin_code"], result.frame[TARGET_MONTH_COLUMN].astype(str)))
    assert kept == {(codes[0], "2026-02"), (codes[1], "2026-06")}
    assert result.dropped_rows_by_reason == {"missing_target_row": 0, "null_target_value": 7}
    assert not result.frame[TARGET_COLUMN].isna().any()


@needs_legacy
def test_every_eligible_row_reaches_the_fit_primitive_once(monkeypatch, recorded_fit):
    def forbidden(*args, **kwargs):
        raise AssertionError("threshold search or temporal split must not run")

    monkeypatch.setattr(training, "select_max_f1_threshold", forbidden)
    monkeypatch.setattr(training, "split_threshold_window", forbidden)
    aligned = _aligned(months=60)
    assert aligned[TARGET_MONTH_COLUMN].nunique() == 60  # beyond the legacy 36-period cap
    result = _fit(aligned)

    assert len(recorded_fit) == 1
    call = recorded_fit[0]
    raw = aligned.loc[:, list(CONTRACT.feature_columns)].to_numpy()
    np.testing.assert_array_equal(call["X"], MaxPlusImputer(multiplier=100.0).fit_transform(raw))
    np.testing.assert_array_equal(call["y"], aligned[TARGET_COLUMN].to_numpy(dtype=np.int8))
    assert call["clusters"] == list(PARTITIONS.route(aligned["admin_code"]))
    assert call["min_samples"] == PARTITION_MIN_SAMPLES

    report = validate_horizon_training_report(result.training_report)
    assert report["sample_count"] == len(aligned)
    assert report["training_target_month_range"] == {
        "start": str(aligned[TARGET_MONTH_COLUMN].min()), "end": "2026-06"}
    assert report["fit_mode"] == "all_eligible_history" and report["evaluation"] == "none"
    assert not {"fit_target_month_range", "fit_sample_count", "validation_target_month_range",
                "validation_sample_count"} & set(report)


@needs_legacy
@pytest.mark.parametrize("horizon_key,threshold", [("0m", 0.48), ("6m", 0.41), ("12m", 0.45)])
def test_fixed_threshold_is_routed_without_search(monkeypatch, recorded_fit, horizon_key, threshold):
    monkeypatch.setattr(training, "select_max_f1_threshold",
                        lambda *a, **k: pytest.fail("threshold search must not run"))
    horizon = int(horizon_key[:-1])
    result = _fit(_aligned(horizon=horizon, months=8), horizon_key, threshold)
    assert result.predictor.threshold == threshold
    assert validate_threshold_report(result.threshold_report) == {
        "schema_version": "fewsnet-fixed-threshold-report-v1", "threshold": threshold,
        "selection": "fixed_operational_threshold_no_search", "source": "fixed-test-source"}


def test_rejects_misaligned_or_missing_targets_before_fitting():
    aligned = _aligned(months=8)
    shifted = aligned.copy()
    shifted[TARGET_MONTH_COLUMN] = shifted[TARGET_MONTH_COLUMN] + 1
    with pytest.raises(ValueError, match="do not match"):
        _fit(shifted)
    unlabeled = aligned.copy()
    unlabeled.loc[0, TARGET_COLUMN] = np.nan
    with pytest.raises(ValueError, match="binary"):
        _fit(unlabeled)


def _metadata(suite, panel_sha="b" * 64):
    return LocalPackageMetadata(
        suite_version=suite, feature_month="2026-10", target_month="2027-04",
        latest_label_month="2026-06", source_git_commit="a" * 40,
        panel_path="/data/panel.csv", panel_sha256=panel_sha, panel_size_bytes=10,
        panel_row_count=5, normalization_audit_path="/data/audit.json",
        normalization_audit_sha256="c" * 64, normalization_audit_size_bytes=3,
    )


def _write(path, result, suite):
    return write_local_model_package(path, result.predictor, _metadata(suite),
                                     {"training_report": result.training_report,
                                      "threshold_report": result.threshold_report})


@needs_legacy
def test_full_data_package_round_trip_and_tamper_rejection(tmp_path, recorded_fit):
    result = _fit(_aligned(months=8))
    suite = f"full-202610-{'a' * 12}-{'b' * 12}"
    _write(tmp_path / "6m", result, suite)
    loaded = load_local_model_package(tmp_path / "6m", expected_suite_version=suite)
    assert loaded.manifest["schema_version"] == FULL_DATA_PACKAGE_SCHEMA
    assert loaded.manifest["fit_mode"] == "all_eligible_history_no_evaluation"
    assert "validation_target_month_range" not in loaded.manifest
    assert loaded.predictor.threshold == 0.41

    manifest_path = tmp_path / "6m/local_model_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["validation_target_month_range"] = {"start": "2026-01", "end": "2026-06"}
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(PackageValidationError):
        load_local_model_package(tmp_path / "6m")


@needs_legacy
def test_full_data_package_rejects_legacy_suite_prefix(tmp_path, recorded_fit):
    result = _fit(_aligned(months=8))
    with pytest.raises(PackageValidationError):
        _write(tmp_path / "6m", result, f"local-202610-{'a' * 12}-{'b' * 12}")


@needs_legacy
def test_legacy_april_package_still_loads_and_validates():
    loaded = load_local_model_package(LEGACY_PACKAGE)
    assert loaded.manifest["schema_version"] == "fewsnet-local-model-package-v1"
    assert loaded.training_report["schema_version"] == "fewsnet-horizon-training-report-v1"
    assert loaded.training_report["validation_target_month_range"] == {"start": "2023-10", "end": "2026-02"}
    assert "schema_version" not in loaded.threshold_report
    assert loaded.predictor.threshold == 0.48


@needs_legacy
def test_full_data_report_requires_declared_no_evaluation(recorded_fit):
    result = _fit(_aligned(months=8))
    report = dict(result.training_report)
    report["evaluation"] = "holdout"
    with pytest.raises(PackageValidationError):
        validate_horizon_training_report(report)
    undeclared = dict(result.training_report)
    del undeclared["fit_mode"]
    with pytest.raises(PackageValidationError):
        validate_horizon_training_report(undeclared)
