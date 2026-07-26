import pytest

from fewsnet_partitioned_rf_pipeline.local.package import (
    LOCAL_PACKAGE_FILES,
    load_local_model_package,
    write_local_model_package,
)
from fewsnet_partitioned_rf_pipeline.schemas import validate_payload
from tests.fewsnet_partitioned_rf.local_test_support import build_package_fixture


def test_local_model_package_schema_rejects_vertex_identity():
    payload = {
        "schema_version": "fewsnet-local-model-package-v1",
        "runtime_backend": "local_python",
        "suite_version": "local-202604-111111111111-222222222222",
        "feature_month": "2026-04",
        "target_month": "2026-04",
        "latest_label_month": "2026-02",
        "horizon_key": "0m",
        "horizon_months": 0,
        "source_panel": {
            "path": "/tmp/panel.csv",
            "sha256": "2" * 64,
            "size_bytes": 10,
            "row_count": 20,
        },
        "normalization_audit": {
            "path": "/tmp/panel.audit.json",
            "sha256": "3" * 64,
            "size_bytes": 11,
        },
        "feature_schema_sha256": "4" * 64,
        "partition_sha256": "5" * 64,
        "threshold": 0.51,
        "dependency_versions": {
            "python": "3.12.3",
            "numpy": "2.4.2",
            "pandas": "3.0.0",
            "scikit-learn": "1.8.0",
            "joblib": "1.5.3",
            "imbalanced-learn": "0.14.0",
        },
        "source_git_commit": "1" * 40,
        "training_target_month_range": {"start": "2023-03", "end": "2026-02"},
        "validation_target_month_range": {"start": "2025-09", "end": "2026-02"},
        "files": list(LOCAL_PACKAGE_FILES),
        "status": "validated",
        "vertex_model_resource_name": "projects/fake/models/fake",
    }
    with pytest.raises(ValueError, match="Additional properties"):
        validate_payload("local-model-package", payload)


def test_local_model_package_round_trip_validates_before_unpickling(tmp_path):
    predictor, metadata, reports = build_package_fixture()
    package_dir = tmp_path / "0m"

    manifest = write_local_model_package(
        package_dir,
        predictor,
        metadata,
        reports,
    )
    loaded = load_local_model_package(
        package_dir,
        expected_suite_version=metadata.suite_version,
        expected_source_git_commit=metadata.source_git_commit,
        expected_panel_sha256=metadata.panel_sha256,
    )

    assert tuple(sorted(path.name for path in package_dir.iterdir())) == tuple(
        sorted(LOCAL_PACKAGE_FILES)
    )
    assert manifest["runtime_backend"] == "local_python"
    assert loaded.manifest == manifest
    assert loaded.predictor.suite_version == metadata.suite_version
    assert loaded.predictor.vertex_model_resource_name == ""
    assert loaded.predictor.vertex_model_version_id == ""
    assert loaded.training_report == reports["training_report"]
    assert loaded.threshold_report == reports["threshold_report"]


def test_local_model_package_rejects_checksum_drift_before_joblib_load(
    tmp_path,
    monkeypatch,
):
    predictor, metadata, reports = build_package_fixture()
    package_dir = tmp_path / "0m"
    write_local_model_package(package_dir, predictor, metadata, reports)
    (package_dir / "training_report.json").write_text("{}\n", encoding="utf-8")

    called = False

    def forbidden_joblib_load(path):
        nonlocal called
        called = True
        raise AssertionError(path)

    monkeypatch.setattr(
        "fewsnet_partitioned_rf_pipeline.local.package.joblib.load",
        forbidden_joblib_load,
    )
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_local_model_package(package_dir)
    assert called is False


def test_local_model_package_rejects_runtime_and_source_identity_drift(tmp_path):
    predictor, metadata, reports = build_package_fixture()
    package_dir = tmp_path / "0m"
    write_local_model_package(package_dir, predictor, metadata, reports)

    with pytest.raises(ValueError, match="source Git commit"):
        load_local_model_package(
            package_dir,
            expected_source_git_commit="f" * 40,
        )
    with pytest.raises(ValueError, match="panel SHA-256"):
        load_local_model_package(
            package_dir,
            expected_panel_sha256="e" * 64,
        )
