from __future__ import annotations

import copy
import hashlib
import importlib
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sklearn.ensemble import RandomForestClassifier

from fewsnet_partitioned_rf_pipeline.config import (
    FEATURE_CONTRACT_PATH,
    PARTITION_ASSET_PATH,
    PARTITION_ASSET_SHA256,
)
from fewsnet_partitioned_rf_pipeline.core.inference import PartitionedRFPredictor
from fewsnet_partitioned_rf_pipeline.core.package import (
    PACKAGE_FILES,
    write_model_package,
)
from fewsnet_partitioned_rf_pipeline.core.partitions import PartitionMap
from fewsnet_partitioned_rf_pipeline.core.preprocessing import (
    MaxPlusImputer,
    load_feature_contract,
)
from fewsnet_partitioned_rf_pipeline.vertex.storage import LocalArtifactStore


SHA256_A = "a" * 64
SHA256_B = "b" * 64
SOURCE_COMMIT = "1" * 40
IMAGE_DIGEST = f"sha256:{SHA256_A}"
IMAGE_URI = f"us-central1-docker.pkg.dev/project/repo/fewsnet@{IMAGE_DIGEST}"
ARTIFACT_URI = "gs://test-models/suite-v1/models/0m"


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _rewrite_json_and_checksum(
    package_dir: Path,
    filename: str,
    payload: dict,
) -> None:
    target = package_dir / filename
    _write_json(target, payload)
    checksums_path = package_dir / "checksums.json"
    checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    checksums[filename] = hashlib.sha256(target.read_bytes()).hexdigest()
    _write_json(checksums_path, checksums)


def _cluster_state() -> dict:
    return {
        "status": "pooled_small_partition",
        "sample_count": 4,
        "class_counts": {"0": 2, "1": 2},
        "smote_status": "not_applicable_small_partition",
        "fallback_reason": "sample_count_lt_50",
    }


def _smote_result() -> dict:
    return {
        "status": "not_applicable_small_partition",
        "original_class_counts": {"0": 2, "1": 2},
        "resampled_class_counts": None,
        "failure_reason": None,
    }


def _partition_metadata() -> dict:
    cluster_state = _cluster_state()
    smote_result = _smote_result()
    return {
        **cluster_state,
        "original_class_counts": smote_result["original_class_counts"],
        "resampled_class_counts": smote_result["resampled_class_counts"],
        "smote_k_neighbors": None,
        "smote_failure_reason": smote_result["failure_reason"],
    }


@pytest.fixture(scope="module")
def model_inputs():
    feature_contract = load_feature_contract(FEATURE_CONTRACT_PATH)
    partition_map = PartitionMap.load(
        PARTITION_ASSET_PATH,
        PARTITION_ASSET_SHA256,
    )
    feature_count = len(feature_contract.feature_columns)
    matrix = np.vstack(
        [
            np.zeros(feature_count),
            np.ones(feature_count),
            np.full(feature_count, 2.0),
            np.full(feature_count, 3.0),
        ]
    )
    target = np.asarray([0, 1, 0, 1], dtype=np.int8)
    imputer = MaxPlusImputer(multiplier=100.0).fit(matrix)
    pooled_model = RandomForestClassifier(
        n_estimators=8,
        random_state=5,
        n_jobs=1,
    ).fit(matrix, target)
    cluster_ids = partition_map.cluster_ids
    predictor = PartitionedRFPredictor(
        imputer=imputer,
        pooled_model=pooled_model,
        partition_models={cluster_id: None for cluster_id in cluster_ids},
        partition_status={
            cluster_id: "pooled_small_partition" for cluster_id in cluster_ids
        },
        partition_metadata={
            cluster_id: _partition_metadata() for cluster_id in cluster_ids
        },
        partition_map=dict(partition_map._clusters_by_admin),
        feature_contract=feature_contract,
        threshold=0.5,
        horizon_key="0m",
        horizon_months=0,
        suite_version="suite-v1",
    )
    threshold_report = {
        "threshold": 0.5,
        "precision": 0.75,
        "recall": 0.6,
        "f1": 2 * 0.75 * 0.6 / (0.75 + 0.6),
        "support": 20,
        "positive_cases": 8,
        "fallback_reason": None,
    }
    training_report = {
        "schema_version": "fewsnet-horizon-training-report-v1",
        "horizon_key": "0m",
        "horizon_months": 0,
        "feature_schema_sha256": feature_contract.feature_schema_sha256,
        "partition_asset_sha256": PARTITION_ASSET_SHA256,
        "partition_coverage_pct": 100.0,
        "training_target_month_range": {
            "start": "2023-05",
            "end": "2026-04",
        },
        "fit_target_month_range": {
            "start": "2023-05",
            "end": "2025-10",
        },
        "validation_target_month_range": {
            "start": "2025-11",
            "end": "2026-04",
        },
        "sample_count": 100,
        "fit_sample_count": 80,
        "validation_sample_count": 20,
        "pooled_class_counts": {"0": 50, "1": 50},
        "cluster_states": {
            str(cluster_id): _cluster_state() for cluster_id in cluster_ids
        },
        "smote_results": {
            str(cluster_id): _smote_result() for cluster_id in cluster_ids
        },
        "fallback_counts": {
            "pooled_unmapped": 0,
            "pooled_small_partition": len(cluster_ids),
            "pooled_single_class": 0,
            "pooled_missing_partition_model": 0,
        },
    }
    metadata = {
        "suite_version": "suite-v1",
        "snapshot_id": "snapshot-v1",
        "snapshot_content_sha256": SHA256_B,
        "target_month": "2026-04",
        "source_git_commit": SOURCE_COMMIT,
        "container_image_uri": IMAGE_URI,
        "container_image_digest": IMAGE_DIGEST,
        "status": "validated",
    }
    reports = {
        "training_report": training_report,
        "threshold_report": threshold_report,
    }
    return predictor, metadata, reports


def _write_package(tmp_path: Path, model_inputs) -> Path:
    predictor, metadata, reports = model_inputs
    package_dir = tmp_path / "model-package"
    write_model_package(
        package_dir,
        predictor,
        copy.deepcopy(metadata),
        copy.deepcopy(reports),
    )
    return package_dir


def _upload_package(
    package_dir: Path,
    store: LocalArtifactStore,
    *,
    excluded: set[str] | None = None,
) -> None:
    excluded = excluded or set()
    for filename in PACKAGE_FILES:
        if filename not in excluded:
            store.upload_file(
                package_dir / filename,
                f"{ARTIFACT_URI}/{filename}",
            )


def _environment(**overrides: str) -> dict[str, str]:
    environment = {
        "AIP_HTTP_PORT": "9090",
        "AIP_HEALTH_ROUTE": "/ready",
        "AIP_PREDICT_ROUTE": "/infer",
        "AIP_STORAGE_URI": ARTIFACT_URI,
        "FEWSNET_CONTAINER_IMAGE_DIGEST": IMAGE_DIGEST,
        "FEWSNET_SOURCE_GIT_COMMIT": SOURCE_COMMIT,
    }
    environment.update(overrides)
    return environment


def _create_client(
    environment: dict[str, str],
    store: LocalArtifactStore,
) -> TestClient:
    module = importlib.import_module(
        "fewsnet_partitioned_rf_pipeline.vertex.predictor_server"
    )
    return TestClient(module.create_app(environ=environment, store=store))


def _instances(model_inputs) -> list[dict]:
    predictor, _, _ = model_inputs
    mapped_admins = list(predictor.partition_map)[:2]
    return [
        {
            "admin_code": mapped_admins[1],
            "feature_month": "2026-04",
            **{
                feature_name: 1.25
                for feature_name in predictor.feature_contract.feature_columns
            },
        },
        {
            "admin_code": "UNMAPPED",
            "feature_month": "2026-04",
            **{
                feature_name: 2.25
                for feature_name in predictor.feature_contract.feature_columns
            },
        },
        {
            "admin_code": mapped_admins[0],
            "feature_month": "2026-04",
            **{
                feature_name: 0.25
                for feature_name in predictor.feature_contract.feature_columns
            },
        },
    ]


def test_missing_environment_creates_unhealthy_app_without_raising(tmp_path):
    client = _create_client({}, LocalArtifactStore(tmp_path / "store"))

    assert client.get("/health").status_code == 503
    assert client.post("/predict", json={"instances": []}).status_code == 503


@pytest.mark.parametrize(
    "failure_kind",
    [
        "missing-package-file",
        "checksum-mismatch",
        "dependency-mismatch",
        "image-digest-mismatch",
        "source-commit-mismatch",
    ],
)
def test_health_returns_503_after_package_load_failure(
    tmp_path,
    model_inputs,
    failure_kind,
):
    package_dir = _write_package(tmp_path, model_inputs)
    excluded: set[str] = set()
    environment = _environment()
    if failure_kind == "missing-package-file":
        excluded.add("training_report.json")
    elif failure_kind == "checksum-mismatch":
        (package_dir / "feature_contract.json").write_text(
            "{}\n",
            encoding="utf-8",
        )
    elif failure_kind == "dependency-mismatch":
        manifest_path = package_dir / "model_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["dependency_versions"]["numpy"] = "0.0.0"
        _rewrite_json_and_checksum(package_dir, manifest_path.name, manifest)
    elif failure_kind == "image-digest-mismatch":
        environment["FEWSNET_CONTAINER_IMAGE_DIGEST"] = f"sha256:{'c' * 64}"
    elif failure_kind == "source-commit-mismatch":
        environment["FEWSNET_SOURCE_GIT_COMMIT"] = "2" * 40

    store = LocalArtifactStore(tmp_path / "store")
    _upload_package(package_dir, store, excluded=excluded)
    client = _create_client(environment, store)

    assert client.get("/ready").status_code == 503
    assert client.post("/infer", json={"instances": []}).status_code == 503


def test_successful_load_is_healthy_and_prediction_preserves_instance_order(
    tmp_path,
    model_inputs,
):
    package_dir = _write_package(tmp_path, model_inputs)
    store = LocalArtifactStore(tmp_path / "store")
    _upload_package(package_dir, store)
    client = _create_client(_environment(), store)
    instances = _instances(model_inputs)

    assert client.get("/ready").status_code == 200
    response = client.post("/infer", json={"instances": instances})

    assert response.status_code == 200
    predictions = response.json()["predictions"]
    assert [row["admin_code"] for row in predictions] == [
        row["admin_code"] for row in instances
    ]
    assert all(row["horizon_months"] == 0 for row in predictions)


def test_predict_rejects_missing_model_feature(tmp_path, model_inputs):
    package_dir = _write_package(tmp_path, model_inputs)
    store = LocalArtifactStore(tmp_path / "store")
    _upload_package(package_dir, store)
    instances = _instances(model_inputs)
    predictor, _, _ = model_inputs
    instances[1].pop(predictor.feature_contract.feature_columns[0])

    response = _create_client(_environment(), store).post(
        "/infer",
        json={"instances": instances},
    )

    assert response.status_code == 400


@pytest.mark.parametrize(
    "payload",
    [
        {"horizon_months": 0},
        {"horizon": "0m"},
    ],
)
def test_predict_rejects_request_level_horizon(
    tmp_path,
    model_inputs,
    payload,
):
    package_dir = _write_package(tmp_path, model_inputs)
    store = LocalArtifactStore(tmp_path / "store")
    _upload_package(package_dir, store)
    payload = {**payload, "instances": _instances(model_inputs)}

    response = _create_client(_environment(), store).post(
        "/infer",
        json=payload,
    )

    assert response.status_code == 400


def test_predict_rejects_undeclared_instance_feature(tmp_path, model_inputs):
    package_dir = _write_package(tmp_path, model_inputs)
    store = LocalArtifactStore(tmp_path / "store")
    _upload_package(package_dir, store)
    instances = _instances(model_inputs)
    instances[0]["undeclared_feature"] = 1.0

    response = _create_client(_environment(), store).post(
        "/infer",
        json={"instances": instances},
    )

    assert response.status_code == 400
