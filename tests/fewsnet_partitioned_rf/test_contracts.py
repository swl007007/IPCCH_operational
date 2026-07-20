import copy
import json
from pathlib import Path

import pytest

from fewsnet_partitioned_rf_pipeline.core.types import ObjectRef, RunPhase
from fewsnet_partitioned_rf_pipeline.schemas import validate_deployment, validate_payload


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/fewsnet_partitioned_rf"
HORIZONS = {"0m": 0, "6m": 6, "12m": 12}
SHA256 = "a" * 64


def _object_ref(name: str) -> dict:
    return {
        "uri": f"gs://bucket/{name}",
        "generation": "1",
        "sha256": SHA256,
        "size_bytes": 1,
    }


def _registered_model(horizon_key: str) -> dict:
    return {
        "horizon_key": horizon_key,
        "parent_model_resource_name": (
            f"projects/food-crisis-modeling/locations/us-central1/models/{horizon_key}"
        ),
        "version_resource_name": (
            "projects/food-crisis-modeling/locations/us-central1/models/"
            f"{horizon_key}@1"
        ),
        "version_id": "1",
        "suite_version_alias": "suite-v1",
        "artifact_uri": f"gs://bucket/models/{horizon_key}",
    }


def _batch_job(horizon_key: str) -> dict:
    return {
        "horizon_key": horizon_key,
        "job_resource_name": (
            "projects/food-crisis-modeling/locations/us-central1/"
            f"batchPredictionJobs/{horizon_key}"
        ),
        "model_version_resource_name": (
            "projects/food-crisis-modeling/locations/us-central1/models/"
            f"{horizon_key}@1"
        ),
        "input_uri": f"gs://bucket/batch/{horizon_key}/input.jsonl",
        "destination_prefix": f"gs://bucket/batch/{horizon_key}/raw",
        "gcs_output_directory": f"gs://bucket/batch/{horizon_key}/output",
    }


def _run_manifest(
    *, phase: str = "OUTPUT_VALIDATED", status: str = "candidate_validated"
) -> dict:
    return {
        "schema_version": "fewsnet-run-manifest-v1",
        "run_id": "run-1",
        "suite_version": "suite-v1",
        "phase": phase,
        "status": status,
        "snapshot_ref": {
            **_object_ref("snapshots/source_manifest.json"),
            "snapshot_id": "snapshot-v1",
            "snapshot_content_sha256": SHA256,
        },
        "model_versions": {
            horizon_key: _registered_model(horizon_key)
            for horizon_key in HORIZONS
        },
        "batch_jobs": {
            horizon_key: _batch_job(horizon_key) for horizon_key in HORIZONS
        },
        "hard_gates": {"output_rows_complete": True},
        "timestamps": {"updated_at_utc": "2026-07-20T00:00:00Z"},
        "retry_attempts": [],
    }


def _training_report() -> dict:
    threshold = {
        "threshold": 0.5,
        "precision": 0.8,
        "recall": 0.7,
        "f1": 0.75,
        "support": 20,
        "positive_cases": 8,
        "fallback_reason": None,
    }
    cluster_state = {
        "status": "partition_model",
        "sample_count": 50,
        "class_counts": {"0": 25, "1": 25},
        "smote_status": "succeeded",
        "fallback_reason": None,
    }
    smote_result = {
        "status": "succeeded",
        "original_class_counts": {"0": 25, "1": 25},
        "resampled_class_counts": {"0": 25, "1": 25},
        "failure_reason": None,
    }
    fallback_counts = {
        "pooled_unmapped": 0,
        "pooled_small_partition": 0,
        "pooled_single_class": 0,
        "pooled_missing_partition_model": 0,
    }
    return {
        "schema_version": "fewsnet-training-report-v1",
        "suite_version": "suite-v1",
        "training_target_month_range": {"start": "2023-05", "end": "2026-04"},
        "validation_target_month_range": {
            "start": "2025-11",
            "end": "2026-04",
        },
        "horizon_thresholds": {
            horizon_key: copy.deepcopy(threshold) for horizon_key in HORIZONS
        },
        "cluster_states": {
            horizon_key: {
                str(cluster_id): copy.deepcopy(cluster_state)
                for cluster_id in range(17)
            }
            for horizon_key in HORIZONS
        },
        "smote_results": {
            horizon_key: {
                str(cluster_id): copy.deepcopy(smote_result)
                for cluster_id in range(17)
            }
            for horizon_key in HORIZONS
        },
        "fallback_counts": {
            horizon_key: copy.deepcopy(fallback_counts) for horizon_key in HORIZONS
        },
    }


def _model_package(horizon_key: str = "0m") -> dict:
    return {
        "schema_version": "fewsnet-model-package-v1",
        "suite_version": "suite-v1",
        "snapshot_id": "snapshot-v1",
        "snapshot_content_sha256": SHA256,
        "horizon_key": horizon_key,
        "horizon_months": HORIZONS[horizon_key],
        "target_month": "2026-04",
        "feature_schema_sha256": SHA256,
        "partition_sha256": SHA256,
        "threshold": 0.5,
        "dependency_versions": {
            "python": "3.12",
            "numpy": "2.4.2",
            "pandas": "3.0.0",
            "scikit-learn": "1.8.0",
            "joblib": "1.5.3",
            "imbalanced-learn": "0.14.0",
        },
        "source_git_commit": "1" * 40,
        "container_image_digest": "sha256:" + SHA256,
        "files": ["model.joblib"],
        "status": "validated",
    }


def _suite_manifest() -> dict:
    return {
        "schema_version": "fewsnet-suite-manifest-v1",
        "suite_version": "suite-v1",
        "feature_month": "2026-04",
        "source_git_commit": "1" * 40,
        "snapshot_ref": {
            "manifest": _object_ref("snapshots/source_manifest.json"),
            "snapshot_id": "snapshot-v1",
            "snapshot_content_sha256": SHA256,
        },
        "container_image": {
            "uri": "registry/image@sha256:" + SHA256,
            "digest": "sha256:" + SHA256,
        },
        "partition": {
            "uri": "fewsnet_partitioned_rf_pipeline/assets/partitions/map.csv",
            "sha256": SHA256,
        },
        "model_versions": {
            horizon_key: _registered_model(horizon_key)
            for horizon_key in HORIZONS
        },
        "predictions": {
            horizon_key: _object_ref(f"predictions/{horizon_key}.csv")
            for horizon_key in HORIZONS
        },
        "alias_state": {
            horizon_key: {
                "alias": "production",
                "version_resource_name": f"models/{horizon_key}@1",
            }
            for horizon_key in HORIZONS
        },
        "released_at_utc": "2026-07-20T00:00:00Z",
    }


def test_source_snapshot_fixture_validates():
    payload = json.loads((FIXTURES / "source_snapshot_valid.json").read_text())
    validate_payload("source-snapshot", payload)


def test_source_snapshot_requires_immutable_object_generation():
    payload = json.loads((FIXTURES / "source_snapshot_valid.json").read_text())
    payload["panel"].pop("generation")
    with pytest.raises(ValueError, match="generation"):
        validate_payload("source-snapshot", payload)


def test_shared_types_freeze_object_identity_and_run_phases():
    ref = ObjectRef("gs://bucket/object", "7", "a" * 64, 12)
    assert ref.generation == "7"
    assert RunPhase.RELEASED.value == "RELEASED"


def test_deployment_requires_digest_pinned_image_and_matching_digest():
    payload = json.loads((FIXTURES / "deployment_valid.json").read_text())
    validate_deployment(payload)
    payload["container_image_digest"] = "sha256:" + "b" * 64
    with pytest.raises(ValueError, match="container_image_digest"):
        validate_deployment(payload)


def test_candidate_validated_run_manifest_accepts_complete_output_evidence():
    validate_payload("run-manifest", _run_manifest())


def test_early_run_manifest_allows_incomplete_model_and_batch_maps():
    payload = _run_manifest(phase="DISCOVERED", status="running")
    payload["model_versions"] = {}
    payload["batch_jobs"] = {}
    validate_payload("run-manifest", payload)


def test_candidate_validated_run_manifest_requires_output_validated_phase():
    payload = _run_manifest(phase="TRAINING")
    with pytest.raises(ValueError, match="OUTPUT_VALIDATED"):
        validate_payload("run-manifest", payload)


@pytest.mark.parametrize("field", ["model_versions", "batch_jobs"])
def test_candidate_validated_run_manifest_requires_all_horizon_evidence(field):
    payload = _run_manifest()
    payload[field].pop("12m")
    with pytest.raises(ValueError, match="12m"):
        validate_payload("run-manifest", payload)


def test_training_report_accepts_exact_seventeen_cluster_entries_per_horizon():
    validate_payload("training-report", _training_report())


@pytest.mark.parametrize("field", ["cluster_states", "smote_results"])
def test_training_report_rejects_missing_fixed_cluster(field):
    payload = _training_report()
    payload[field]["0m"].pop("16")
    with pytest.raises(ValueError, match="16"):
        validate_payload("training-report", payload)


@pytest.mark.parametrize("field", ["cluster_states", "smote_results"])
def test_training_report_rejects_empty_fixed_cluster_evidence(field):
    payload = _training_report()
    payload[field]["0m"] = {}
    with pytest.raises(ValueError, match="0"):
        validate_payload("training-report", payload)


@pytest.mark.parametrize(
    ("schema_name", "payload", "field"),
    [
        (
            "source-snapshot",
            json.loads((FIXTURES / "source_snapshot_valid.json").read_text()),
            "created_at_utc",
        ),
        ("suite-manifest", _suite_manifest(), "released_at_utc"),
    ],
)
def test_contracts_reject_invalid_date_time_values(schema_name, payload, field):
    payload[field] = "not-a-date"
    with pytest.raises(ValueError, match="date-time"):
        validate_payload(schema_name, payload)


@pytest.mark.parametrize("horizon_key", HORIZONS)
def test_model_package_accepts_matching_horizon_identity(horizon_key):
    validate_payload("model-package", _model_package(horizon_key))


@pytest.mark.parametrize(
    ("horizon_key", "horizon_months"),
    [("0m", 6), ("6m", 12), ("12m", 0)],
)
def test_model_package_rejects_contradictory_horizon_identity(
    horizon_key, horizon_months
):
    payload = _model_package(horizon_key)
    payload["horizon_months"] = horizon_months
    with pytest.raises(ValueError, match="horizon_months"):
        validate_payload("model-package", payload)


@pytest.mark.parametrize("field", ["model_versions", "batch_jobs"])
def test_run_manifest_rejects_horizon_identity_mismatched_to_map_key(field):
    payload = _run_manifest()
    payload[field]["0m"]["horizon_key"] = "6m"
    with pytest.raises(ValueError, match="horizon_key"):
        validate_payload("run-manifest", payload)


def test_suite_manifest_rejects_horizon_identity_mismatched_to_map_key():
    payload = _suite_manifest()
    payload["model_versions"]["0m"]["horizon_key"] = "12m"
    with pytest.raises(ValueError, match="horizon_key"):
        validate_payload("suite-manifest", payload)
