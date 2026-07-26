import hashlib
import json
from pathlib import Path

import pytest

import fewsnet_partitioned_rf_pipeline.local.package as package_module
from fewsnet_partitioned_rf_pipeline.local.package import (
    LOCAL_PACKAGE_FILES,
    load_local_model_package,
    write_local_model_package,
)
from fewsnet_partitioned_rf_pipeline.schemas import validate_payload
from tests.fewsnet_partitioned_rf.local_test_support import build_package_fixture


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _refresh_checksum(package_dir: Path, filename: str) -> None:
    target = package_dir / filename
    checksums_path = package_dir / "checksums.json"
    checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    checksums[filename] = hashlib.sha256(target.read_bytes()).hexdigest()
    _write_json(checksums_path, checksums)


def _rewrite_json_and_checksum(
    package_dir: Path,
    filename: str,
    payload: dict[str, object],
) -> None:
    _write_json(package_dir / filename, payload)
    _refresh_checksum(package_dir, filename)


def _forbid_joblib_load(monkeypatch) -> dict[str, bool]:
    state = {"called": False}

    def forbidden_joblib_load(path):
        state["called"] = True
        raise AssertionError(path)

    monkeypatch.setattr(package_module.joblib, "load", forbidden_joblib_load)
    return state


@pytest.fixture
def written_local_package(tmp_path):
    predictor, metadata, reports = build_package_fixture()
    package_dir = tmp_path / "0m"
    write_local_model_package(package_dir, predictor, metadata, reports)
    return package_dir, metadata


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


def test_write_rejects_approved_feature_contract_byte_drift_before_parsing(
    tmp_path,
    monkeypatch,
):
    predictor, metadata, reports = build_package_fixture()
    payload = json.loads(package_module.FEATURE_CONTRACT_PATH.read_text(encoding="utf-8"))
    drifted_contract = tmp_path / "feature_contract.json"
    drifted_contract.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    assert hashlib.sha256(drifted_contract.read_bytes()).hexdigest() != (
        "3779c6bcde70560c0e1514c563ced6e7bd559c6d352689398c3cecb93d44a67b"
    )

    called = False

    def forbidden_contract_parse(path):
        nonlocal called
        called = True
        raise AssertionError(path)

    monkeypatch.setattr(package_module, "FEATURE_CONTRACT_PATH", drifted_contract)
    monkeypatch.setattr(package_module, "load_feature_contract", forbidden_contract_parse)
    with pytest.raises(ValueError, match="approved feature contract SHA-256"):
        write_local_model_package(
            tmp_path / "package",
            predictor,
            metadata,
            reports,
        )
    assert called is False


def test_load_rejects_semantic_feature_contract_byte_drift_before_joblib_load(
    written_local_package,
    monkeypatch,
):
    package_dir, _ = written_local_package
    contract_path = package_dir / "feature_contract.json"
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    contract_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    _refresh_checksum(package_dir, "feature_contract.json")
    state = _forbid_joblib_load(monkeypatch)

    with pytest.raises(ValueError, match="approved feature contract SHA-256"):
        load_local_model_package(package_dir)
    assert state["called"] is False


@pytest.mark.parametrize(
    ("case", "expected_error"),
    (
        ("extra", "package files differ"),
        ("directory", "regular non-symlink file"),
    ),
)
def test_load_rejects_inventory_or_nonregular_member_before_joblib_load(
    written_local_package,
    monkeypatch,
    case,
    expected_error,
):
    package_dir, _ = written_local_package
    if case == "extra":
        (package_dir / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
    else:
        model_path = package_dir / "model.joblib"
        model_path.unlink()
        model_path.mkdir()
    state = _forbid_joblib_load(monkeypatch)

    with pytest.raises(ValueError, match=expected_error):
        load_local_model_package(package_dir)
    assert state["called"] is False


@pytest.mark.parametrize(
    ("case", "expected_error"),
    (
        ("fields", "checksums.json fields differ"),
        ("content", "checksum mismatch"),
    ),
)
def test_load_rejects_checksum_fields_or_content_drift_before_joblib_load(
    written_local_package,
    monkeypatch,
    case,
    expected_error,
):
    package_dir, _ = written_local_package
    if case == "fields":
        checksums_path = package_dir / "checksums.json"
        checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
        checksums.pop("training_report.json")
        _write_json(checksums_path, checksums)
    else:
        (package_dir / "training_report.json").write_text("{}\n", encoding="utf-8")
    state = _forbid_joblib_load(monkeypatch)

    with pytest.raises(ValueError, match=expected_error):
        load_local_model_package(package_dir)
    assert state["called"] is False


def test_load_rejects_manifest_schema_drift_before_joblib_load(
    written_local_package,
    monkeypatch,
):
    package_dir, _ = written_local_package
    manifest_path = package_dir / "local_model_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["runtime_backend"] = "vertex_ai"
    _rewrite_json_and_checksum(package_dir, "local_model_manifest.json", manifest)
    state = _forbid_joblib_load(monkeypatch)

    with pytest.raises(ValueError, match="local_python"):
        load_local_model_package(package_dir)
    assert state["called"] is False


def test_load_rejects_expected_identity_before_joblib_load(
    written_local_package,
    monkeypatch,
):
    package_dir, _ = written_local_package
    state = _forbid_joblib_load(monkeypatch)

    with pytest.raises(ValueError, match="expected suite version"):
        load_local_model_package(
            package_dir,
            expected_suite_version="local-202604-aaaaaaaaaaaa-bbbbbbbbbbbb",
        )
    assert state["called"] is False


def test_load_rejects_partition_asset_drift_before_joblib_load(
    written_local_package,
    monkeypatch,
):
    package_dir, _ = written_local_package
    partition_path = package_dir / "partition_map.csv"
    partition_path.write_bytes(partition_path.read_bytes() + b"\n")
    _refresh_checksum(package_dir, "partition_map.csv")
    state = _forbid_joblib_load(monkeypatch)

    with pytest.raises(ValueError, match="partition_sha256 does not match"):
        load_local_model_package(package_dir)
    assert state["called"] is False


def test_load_rejects_invalid_report_before_joblib_load(
    written_local_package,
    monkeypatch,
):
    package_dir, _ = written_local_package
    report_path = package_dir / "training_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report.pop("schema_version")
    _rewrite_json_and_checksum(package_dir, "training_report.json", report)
    state = _forbid_joblib_load(monkeypatch)

    with pytest.raises(ValueError, match="training_report fields differ"):
        load_local_model_package(package_dir)
    assert state["called"] is False


def test_load_rejects_runtime_compatibility_drift_before_joblib_load(
    written_local_package,
    monkeypatch,
):
    package_dir, _ = written_local_package
    manifest_path = package_dir / "local_model_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["dependency_versions"]["numpy"] = "0.0.0"
    _rewrite_json_and_checksum(package_dir, "local_model_manifest.json", manifest)
    state = _forbid_joblib_load(monkeypatch)

    with pytest.raises(ValueError, match="runtime dependency mismatch for numpy"):
        load_local_model_package(package_dir)
    assert state["called"] is False
