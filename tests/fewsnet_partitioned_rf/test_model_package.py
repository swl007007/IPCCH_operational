from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from sklearn.ensemble import RandomForestClassifier

from fewsnet_partitioned_rf_pipeline.config import (
    FEATURE_CONTRACT_PATH,
    PARTITION_ASSET_PATH,
    PARTITION_ASSET_SHA256,
)
from fewsnet_partitioned_rf_pipeline.core.inference import PartitionedRFPredictor
from fewsnet_partitioned_rf_pipeline.core.package import (
    load_model_package,
    write_model_package,
)
from fewsnet_partitioned_rf_pipeline.core.partitions import PartitionMap
from fewsnet_partitioned_rf_pipeline.core.preprocessing import (
    MaxPlusImputer,
    load_feature_contract,
)
from fewsnet_partitioned_rf_pipeline.core.validation import (
    PackageValidationError,
    runtime_dependency_versions,
)
from fewsnet_partitioned_rf_pipeline.schemas import validate_payload


PACKAGE_FILES = {
    "model.joblib",
    "model_manifest.json",
    "feature_contract.json",
    "partition_map.csv",
    "threshold_report.json",
    "training_report.json",
    "checksums.json",
}
CHECKSUMMED_FILES = PACKAGE_FILES - {"checksums.json"}
SHA256_A = "a" * 64
SHA256_B = "b" * 64
SOURCE_COMMIT = "1" * 40
IMAGE_DIGEST = f"sha256:{SHA256_A}"
IMAGE_URI = f"us-central1-docker.pkg.dev/project/repo/fewsnet@{IMAGE_DIGEST}"


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


def _rewrite_model_and_checksum(
    package_dir: Path,
    predictor: PartitionedRFPredictor,
) -> None:
    model_path = package_dir / "model.joblib"
    joblib.dump(predictor, model_path, compress=3, protocol=5)
    checksums_path = package_dir / "checksums.json"
    checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    checksums["model.joblib"] = hashlib.sha256(model_path.read_bytes()).hexdigest()
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
    mapped_admins = list(predictor.partition_map)[:2]
    inference_frame = pd.DataFrame(
        {
            "admin_code": [mapped_admins[0], mapped_admins[1], "UNMAPPED"],
            "feature_month": ["2026-04"] * 3,
            **{
                feature_name: [0.25, 1.25, 2.25]
                for feature_name in feature_contract.feature_columns
            },
        }
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
    return predictor, inference_frame, metadata, reports


@pytest.fixture
def package_dir(tmp_path, model_inputs) -> Path:
    predictor, _, metadata, reports = model_inputs
    output_dir = tmp_path / "model-package"
    write_model_package(
        output_dir,
        predictor,
        copy.deepcopy(metadata),
        copy.deepcopy(reports),
    )
    return output_dir


def test_model_package_round_trip_is_exact_and_vertex_compatible(
    package_dir,
    model_inputs,
):
    predictor, inference_frame, metadata, reports = model_inputs
    manifest = json.loads(
        (package_dir / "model_manifest.json").read_text(encoding="utf-8")
    )
    checksums = json.loads(
        (package_dir / "checksums.json").read_text(encoding="utf-8")
    )

    assert {path.name for path in package_dir.iterdir()} == PACKAGE_FILES
    assert set(manifest["files"]) == PACKAGE_FILES
    assert set(checksums) == CHECKSUMMED_FILES
    assert manifest["dependency_versions"] == runtime_dependency_versions()
    assert manifest["container_image_uri"] == metadata["container_image_uri"]
    assert manifest["container_image_digest"] == metadata["container_image_digest"]
    assert manifest["training_target_month_range"] == reports["training_report"][
        "training_target_month_range"
    ]
    assert manifest["validation_target_month_range"] == reports[
        "training_report"
    ]["validation_target_month_range"]
    validate_payload("model-package", manifest)

    loaded = load_model_package(
        package_dir,
        expected_image_digest=IMAGE_DIGEST,
        expected_source_git_commit=SOURCE_COMMIT,
    )
    assert isinstance(loaded, PartitionedRFPredictor)
    assert_frame_equal(
        loaded.predict_frame(inference_frame),
        predictor.predict_frame(inference_frame),
        check_exact=True,
    )


@pytest.mark.parametrize(
    "field",
    (
        "container_image_uri",
        "training_target_month_range",
        "validation_target_month_range",
    ),
)
def test_model_package_schema_requires_design_manifest_fields(
    package_dir,
    field,
):
    manifest = json.loads(
        (package_dir / "model_manifest.json").read_text(encoding="utf-8")
    )
    manifest.pop(field)

    with pytest.raises(ValueError, match=field):
        validate_payload("model-package", manifest)


def test_write_rejects_image_uri_digest_mismatch(tmp_path, model_inputs):
    predictor, _, metadata, reports = model_inputs
    mismatched = copy.deepcopy(metadata)
    mismatched["container_image_uri"] = (
        "us-central1-docker.pkg.dev/project/repo/fewsnet@sha256:" + SHA256_B
    )

    with pytest.raises(PackageValidationError, match="container_image_uri"):
        write_model_package(
            tmp_path / "bad-package",
            predictor,
            mismatched,
            copy.deepcopy(reports),
        )


def test_load_rejects_image_uri_digest_mismatch_before_unpickling(
    package_dir,
    monkeypatch,
):
    manifest = json.loads(
        (package_dir / "model_manifest.json").read_text(encoding="utf-8")
    )
    manifest["container_image_uri"] = (
        "us-central1-docker.pkg.dev/project/repo/fewsnet@sha256:" + SHA256_B
    )
    _rewrite_json_and_checksum(package_dir, "model_manifest.json", manifest)

    def fail_if_unpickled(*_args, **_kwargs):
        raise AssertionError("joblib.load must not run before manifest validation")

    monkeypatch.setattr(
        "fewsnet_partitioned_rf_pipeline.core.package.joblib.load",
        fail_if_unpickled,
    )
    with pytest.raises(PackageValidationError, match="container_image_uri"):
        load_model_package(package_dir)


def test_load_rejects_manifest_report_range_mismatch_before_unpickling(
    package_dir,
    monkeypatch,
):
    training_report = json.loads(
        (package_dir / "training_report.json").read_text(encoding="utf-8")
    )
    training_report["validation_target_month_range"]["start"] = "2025-10"
    _rewrite_json_and_checksum(
        package_dir,
        "training_report.json",
        training_report,
    )

    def fail_if_unpickled(*_args, **_kwargs):
        raise AssertionError("joblib.load must not run before report validation")

    monkeypatch.setattr(
        "fewsnet_partitioned_rf_pipeline.core.package.joblib.load",
        fail_if_unpickled,
    )
    with pytest.raises(PackageValidationError, match="validation_target_month_range"):
        load_model_package(package_dir)


def _assert_training_report_rejected_before_unpickling(
    package_dir: Path,
    monkeypatch,
    training_report: dict,
    match: str,
) -> None:
    _rewrite_json_and_checksum(
        package_dir,
        "training_report.json",
        training_report,
    )

    def fail_if_unpickled(*_args, **_kwargs):
        raise AssertionError("joblib.load must not run before report validation")

    monkeypatch.setattr(
        "fewsnet_partitioned_rf_pipeline.core.package.joblib.load",
        fail_if_unpickled,
    )
    with pytest.raises(PackageValidationError, match=match):
        load_model_package(package_dir)


def test_load_rejects_training_report_extra_field_before_unpickling(
    package_dir,
    monkeypatch,
):
    training_report = json.loads(
        (package_dir / "training_report.json").read_text(encoding="utf-8")
    )
    training_report["unexpected"] = True

    _assert_training_report_rejected_before_unpickling(
        package_dir,
        monkeypatch,
        training_report,
        "training_report fields differ",
    )


def test_load_rejects_string_cluster_state_before_unpickling(
    package_dir,
    monkeypatch,
):
    training_report = json.loads(
        (package_dir / "training_report.json").read_text(encoding="utf-8")
    )
    training_report["cluster_states"]["0"] = "not an object"

    _assert_training_report_rejected_before_unpickling(
        package_dir,
        monkeypatch,
        training_report,
        r"training_report\.cluster_states\.0 must be an object",
    )


def test_load_rejects_malformed_smote_result_before_unpickling(
    package_dir,
    monkeypatch,
):
    training_report = json.loads(
        (package_dir / "training_report.json").read_text(encoding="utf-8")
    )
    training_report["smote_results"]["0"]["original_class_counts"]["1"] = "2"

    _assert_training_report_rejected_before_unpickling(
        package_dir,
        monkeypatch,
        training_report,
        r"training_report\.smote_results\.0\.original_class_counts\.1",
    )


@pytest.mark.parametrize(
    ("section", "field"),
    (
        ("cluster_states", "status"),
        ("cluster_states", "smote_status"),
        ("smote_results", "status"),
    ),
)
def test_load_rejects_non_string_training_report_status_before_unpickling(
    package_dir,
    monkeypatch,
    section,
    field,
):
    training_report = json.loads(
        (package_dir / "training_report.json").read_text(encoding="utf-8")
    )
    training_report[section]["0"][field] = []

    _assert_training_report_rejected_before_unpickling(
        package_dir,
        monkeypatch,
        training_report,
        rf"training_report\.{section}\.0\.{field}",
    )


@pytest.mark.parametrize(
    ("mismatch", "match"),
    (
        ("partition_status", "predictor partition_status"),
        ("cluster_states", "predictor partition_metadata cluster_states"),
        ("smote_results", "predictor partition_metadata smote_results"),
    ),
)
def test_load_rejects_predictor_report_mismatch_after_unpickling(
    package_dir,
    mismatch,
    match,
):
    predictor = joblib.load(package_dir / "model.joblib")
    if mismatch == "partition_status":
        predictor.partition_status[0] = "pooled_single_class"
    elif mismatch == "cluster_states":
        predictor.partition_metadata[0]["sample_count"] = 5
    else:
        predictor.partition_metadata[0]["smote_failure_reason"] = "unexpected"
    _rewrite_model_and_checksum(package_dir, predictor)

    with pytest.raises(PackageValidationError, match=match):
        load_model_package(package_dir)


@pytest.mark.parametrize("operation", ("write", "load"))
@pytest.mark.parametrize(
    ("mismatch", "match"),
    (
        ("pooled_has_model", "predictor partition_models model presence"),
        ("missing_key", "predictor partition_models cluster IDs"),
        ("extra_key", "predictor partition_models cluster IDs"),
    ),
)
def test_package_rejects_partition_model_routing_evidence_mismatch(
    tmp_path,
    package_dir,
    model_inputs,
    operation,
    mismatch,
    match,
):
    predictor = joblib.load(package_dir / "model.joblib")
    if mismatch == "pooled_has_model":
        predictor.partition_models[0] = predictor.pooled_model
    elif mismatch == "missing_key":
        predictor.partition_models.pop(0)
    else:
        predictor.partition_models[99] = None

    output_dir = tmp_path / f"bad-routing-{mismatch}"
    with pytest.raises(PackageValidationError, match=match):
        if operation == "write":
            _, _, metadata, reports = model_inputs
            write_model_package(
                output_dir,
                predictor,
                copy.deepcopy(metadata),
                copy.deepcopy(reports),
            )
        else:
            _rewrite_model_and_checksum(package_dir, predictor)
            load_model_package(package_dir)
    if operation == "write":
        assert not output_dir.exists()


@pytest.mark.parametrize("operation", ("write", "load"))
@pytest.mark.parametrize("value_count", (1, 2))
@pytest.mark.parametrize(
    ("location", "match"),
    (
        ("partition_status", r"predictor\.partition_status\.0"),
        ("partition_metadata", r"predictor\.partition_metadata\.0\.status"),
    ),
)
def test_package_rejects_non_scalar_predictor_report_values(
    tmp_path,
    package_dir,
    model_inputs,
    operation,
    value_count,
    location,
    match,
):
    predictor = joblib.load(package_dir / "model.joblib")
    value = np.asarray(["pooled_small_partition"] * value_count, dtype=object)
    if location == "partition_status":
        predictor.partition_status[0] = value
    else:
        predictor.partition_metadata[0]["status"] = value

    output_dir = tmp_path / f"bad-{location}-{value_count}"
    with pytest.raises(PackageValidationError, match=match):
        if operation == "write":
            _, _, metadata, reports = model_inputs
            write_model_package(
                output_dir,
                predictor,
                copy.deepcopy(metadata),
                copy.deepcopy(reports),
            )
        else:
            _rewrite_model_and_checksum(package_dir, predictor)
            load_model_package(package_dir)
    if operation == "write":
        assert not output_dir.exists()


@pytest.mark.parametrize("operation", ("write", "load"))
@pytest.mark.parametrize(
    "mapping_name",
    ("partition_status", "partition_models", "partition_metadata"),
)
def test_package_rejects_non_integer_predictor_cluster_keys(
    tmp_path,
    package_dir,
    model_inputs,
    operation,
    mapping_name,
):
    predictor = joblib.load(package_dir / "model.joblib")
    cluster_mapping = getattr(predictor, mapping_name)
    value = cluster_mapping.pop(0)
    cluster_mapping[0.0] = value

    output_dir = tmp_path / f"bad-key-{mapping_name}"
    with pytest.raises(
        PackageValidationError,
        match=rf"predictor\.{mapping_name} cluster IDs must be integers",
    ):
        if operation == "write":
            _, _, metadata, reports = model_inputs
            write_model_package(
                output_dir,
                predictor,
                copy.deepcopy(metadata),
                copy.deepcopy(reports),
            )
        else:
            _rewrite_model_and_checksum(package_dir, predictor)
            load_model_package(package_dir)
    if operation == "write":
        assert not output_dir.exists()


def test_load_rejects_threshold_report_tamper_before_unpickling(
    package_dir,
    monkeypatch,
):
    threshold_report_path = package_dir / "threshold_report.json"
    threshold_report = json.loads(threshold_report_path.read_text(encoding="utf-8"))
    threshold_report["threshold"] = 0.7
    _write_json(threshold_report_path, threshold_report)

    def fail_if_unpickled(*_args, **_kwargs):
        raise AssertionError("joblib.load must not run before checksum validation")

    monkeypatch.setattr(
        "fewsnet_partitioned_rf_pipeline.core.package.joblib.load",
        fail_if_unpickled,
    )
    with pytest.raises(PackageValidationError, match="threshold_report.json"):
        load_model_package(package_dir)


def test_runtime_drift_is_rejected_before_unpickling(package_dir, monkeypatch):
    import fewsnet_partitioned_rf_pipeline.core.validation as package_validation

    observed = runtime_dependency_versions()
    observed["python"] = "0.0"
    monkeypatch.setattr(
        package_validation,
        "runtime_dependency_versions",
        lambda: observed,
    )

    def fail_if_unpickled(*_args, **_kwargs):
        raise AssertionError("joblib.load must not run under runtime drift")

    monkeypatch.setattr(
        "fewsnet_partitioned_rf_pipeline.core.package.joblib.load",
        fail_if_unpickled,
    )
    with pytest.raises(PackageValidationError, match="runtime dependency mismatch"):
        load_model_package(package_dir)


@pytest.mark.parametrize("operation", ("write", "load"))
def test_missing_runtime_dependency_fails_closed(
    tmp_path,
    package_dir,
    model_inputs,
    monkeypatch,
    operation,
):
    import fewsnet_partitioned_rf_pipeline.core.validation as package_validation

    installed_version = package_validation.metadata.version

    def version_with_missing_dependency(name):
        if name == "imbalanced-learn":
            raise package_validation.metadata.PackageNotFoundError(name)
        return installed_version(name)

    monkeypatch.setattr(
        package_validation.metadata,
        "version",
        version_with_missing_dependency,
    )

    if operation == "write":
        predictor, _, metadata, reports = model_inputs
        action = lambda: write_model_package(
            tmp_path / "missing-dependency-package",
            predictor,
            copy.deepcopy(metadata),
            copy.deepcopy(reports),
        )
    else:
        action = lambda: load_model_package(package_dir)

    with pytest.raises(
        PackageValidationError,
        match="required runtime dependency imbalanced-learn is not installed",
    ):
        action()


def test_load_requires_every_package_file(package_dir):
    (package_dir / "training_report.json").unlink()

    with pytest.raises(PackageValidationError, match="training_report.json"):
        load_model_package(package_dir)


@pytest.mark.parametrize("member_type", ("directory", "symlink"))
def test_load_rejects_non_regular_package_member_before_hashing(
    package_dir,
    monkeypatch,
    member_type,
):
    member = package_dir / "training_report.json"
    if member_type == "directory":
        member.unlink()
        member.mkdir()
    else:
        target = package_dir.parent / "training-report-target.json"
        target.write_bytes(member.read_bytes())
        member.unlink()
        try:
            member.symlink_to(target)
        except OSError as exc:
            pytest.skip(f"symlink creation unavailable: {exc}")

    def fail_if_hashed(*_args, **_kwargs):
        raise AssertionError("package members must be type-checked before hashing")

    monkeypatch.setattr(
        "fewsnet_partitioned_rf_pipeline.core.package._sha256",
        fail_if_hashed,
    )
    with pytest.raises(
        PackageValidationError,
        match="training_report.json must be a regular non-symlink file",
    ):
        load_model_package(package_dir)


def test_load_rejects_non_predictor_joblib(package_dir):
    model_path = package_dir / "model.joblib"
    joblib.dump({"not": "a predictor"}, model_path, compress=3, protocol=5)
    checksums = json.loads(
        (package_dir / "checksums.json").read_text(encoding="utf-8")
    )
    checksums["model.joblib"] = hashlib.sha256(model_path.read_bytes()).hexdigest()
    _write_json(package_dir / "checksums.json", checksums)

    with pytest.raises(PackageValidationError, match="PartitionedRFPredictor"):
        load_model_package(package_dir)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    (
        ("feature_schema_sha256", "c" * 64, "feature_schema_sha256"),
        ("partition_sha256", "c" * 64, "partition_sha256"),
    ),
)
def test_load_rejects_manifest_feature_or_partition_identity_drift(
    package_dir,
    field,
    value,
    match,
):
    manifest = json.loads(
        (package_dir / "model_manifest.json").read_text(encoding="utf-8")
    )
    manifest[field] = value
    _rewrite_json_and_checksum(package_dir, "model_manifest.json", manifest)

    with pytest.raises(PackageValidationError, match=match):
        load_model_package(package_dir)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    (
        ({"expected_image_digest": f"sha256:{SHA256_B}"}, "image digest"),
        ({"expected_source_git_commit": "2" * 40}, "source Git commit"),
    ),
)
def test_load_rejects_optional_runtime_pins(package_dir, kwargs, match):
    with pytest.raises(PackageValidationError, match=match):
        load_model_package(package_dir, **kwargs)


@pytest.mark.parametrize(
    ("report_name", "field", "value", "match"),
    (
        ("training_report", "horizon_key", "6m", "horizon_key"),
        ("training_report", "horizon_months", 6, "horizon_months"),
        ("training_report", "feature_schema_sha256", "c" * 64, "feature"),
        ("training_report", "partition_asset_sha256", "c" * 64, "partition"),
        ("threshold_report", "threshold", 0.7, "threshold"),
    ),
)
def test_write_rejects_report_identity_mismatch(
    tmp_path,
    model_inputs,
    report_name,
    field,
    value,
    match,
):
    predictor, _, metadata, reports = model_inputs
    mismatched_reports = copy.deepcopy(reports)
    mismatched_reports[report_name][field] = value

    with pytest.raises(PackageValidationError, match=match):
        write_model_package(
            tmp_path / f"bad-{report_name}-{field}",
            predictor,
            copy.deepcopy(metadata),
            mismatched_reports,
        )


def test_load_rejects_threshold_identity_mismatch_with_updated_checksum(package_dir):
    threshold_report = json.loads(
        (package_dir / "threshold_report.json").read_text(encoding="utf-8")
    )
    threshold_report["threshold"] = 0.7
    _rewrite_json_and_checksum(
        package_dir,
        "threshold_report.json",
        threshold_report,
    )

    with pytest.raises(PackageValidationError, match="threshold"):
        load_model_package(package_dir)
