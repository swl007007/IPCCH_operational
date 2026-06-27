import copy
import json
from pathlib import Path

import pytest

from cloud.common import manifest


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "cloud"
REQUIRED_ARTIFACT_TYPES = (
    "scaffold",
    "fixed_slow_area_features",
    "source_panel",
    "gee_evi_export_config",
    "geometry",
    "docker_image",
    "model_package",
    "vertex_ai_inference_config",
    "schema_contract",
    "validator",
)


def _load_fixture(name):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_valid_manifest_fixture_loads_and_matches_execution_parameters():
    loaded = manifest.load_manifest(
        FIXTURE_DIR / "input_manifest_202604_valid.json",
        feature_month="2026-04",
        run_id="run-202604-valid",
    )

    assert loaded["feature_month"] == "2026-04"
    assert loaded["run_id"] == "run-202604-valid"
    assert loaded["deployment"]["provider"] == "gcp"


def test_required_artifact_missing_immutable_reference_fails():
    data = _load_fixture("input_manifest_202604_valid.json")
    data["artifacts"][0].pop("generation")

    with pytest.raises(manifest.ManifestValidationError, match="immutable reference"):
        manifest.validate_manifest(data)


@pytest.mark.parametrize("artifact_type", REQUIRED_ARTIFACT_TYPES)
def test_required_v1_artifact_type_must_be_present_exactly_once(artifact_type):
    data = _load_fixture("input_manifest_202604_valid.json")
    data["artifacts"] = [
        artifact
        for artifact in data["artifacts"]
        if artifact["artifact_type"] != artifact_type
    ]

    with pytest.raises(manifest.ManifestValidationError, match=artifact_type):
        manifest.validate_manifest(data)

    data = _load_fixture("input_manifest_202604_valid.json")
    original = next(
        artifact
        for artifact in data["artifacts"]
        if artifact["artifact_type"] == artifact_type
    )
    duplicate = copy.deepcopy(original)
    duplicate["artifact_id"] = duplicate["artifact_id"] + "-duplicate"
    data["artifacts"].append(duplicate)

    with pytest.raises(manifest.ManifestValidationError, match=artifact_type):
        manifest.validate_manifest(data)


def test_local_workstation_uri_fails():
    data = _load_fixture("input_manifest_202604_valid.json")
    data["artifacts"][0]["uri"] = "/mnt/c/local/ipcch_scaffold_202604.csv"

    with pytest.raises(manifest.ManifestValidationError, match="local workstation"):
        manifest.validate_manifest(data)


def test_unsupported_artifact_uri_scheme_fails():
    data = _load_fixture("input_manifest_202604_valid.json")
    data["artifacts"][0]["uri"] = "s3://other-bucket/ipcch_scaffold_202604.csv"

    with pytest.raises(manifest.ManifestValidationError, match="cloud URI"):
        manifest.validate_manifest(data)


def test_relative_artifact_uri_fails():
    data = _load_fixture("input_manifest_202604_valid.json")
    data["artifacts"][0]["uri"] = "inputs/ipcch_scaffold_202604.csv"

    with pytest.raises(manifest.ManifestValidationError, match="cloud URI"):
        manifest.validate_manifest(data)


def test_non_gcp_provider_fails():
    data = _load_fixture("input_manifest_202604_valid.json")
    data["deployment"]["provider"] = "aws"

    with pytest.raises(manifest.ManifestValidationError, match="provider"):
        manifest.validate_manifest(data)


def test_tag_only_runtime_image_fails():
    data = _load_fixture("input_manifest_202604_valid.json")
    data["deployment"]["artifact_registry_image_uri"] = (
        "us-central1-docker.pkg.dev/ipcch-test/runtime/ipcch:latest"
    )

    with pytest.raises(manifest.ManifestValidationError, match="digest|sha256"):
        manifest.validate_manifest(data)


def test_runtime_images_must_use_same_single_image_digest():
    data = _load_fixture("input_manifest_202604_valid.json")
    data["deployment"]["vertex_ai_custom_job_container_image_uri"] = (
        "us-central1-docker.pkg.dev/ipcch-test/runtime/ipcch@sha256:" + "b" * 64
    )
    data["deployment"]["vertex_ai_custom_job_container_digest"] = "sha256:" + "b" * 64

    with pytest.raises(manifest.ManifestValidationError, match="single-image"):
        manifest.validate_manifest(data)


def test_shared_service_accounts_fail_split_least_privilege_gate():
    data = _load_fixture("input_manifest_202604_valid.json")
    shared = "shared@ipcch-test.iam.gserviceaccount.com"
    data["deployment"]["cloud_run_service_account"] = shared
    data["deployment"]["cloud_batch_service_account"] = shared

    with pytest.raises(manifest.ManifestValidationError, match="split least privilege"):
        manifest.validate_manifest(data)


def test_feature_month_and_run_id_must_match_execution_parameters():
    data = copy.deepcopy(_load_fixture("input_manifest_202604_valid.json"))

    with pytest.raises(manifest.ManifestValidationError, match="feature_month"):
        manifest.validate_manifest(data, feature_month="2026-05")

    with pytest.raises(manifest.ManifestValidationError, match="run_id"):
        manifest.validate_manifest(data, run_id="different-run")


def test_deployment_model_package_must_match_model_package_artifact():
    data = _load_fixture("input_manifest_202604_valid.json")
    model_artifact = next(
        artifact
        for artifact in data["artifacts"]
        if artifact["artifact_type"] == "model_package"
    )
    model_artifact["uri"] = "gs://ipcch-test/model-packages/validated/"
    model_artifact["checksum"] = "a" * 64
    model_artifact["checksum_algorithm"] = "sha256"
    data["deployment"]["vertex_ai_model_package_uri"] = (
        "gs://ipcch-test/model-packages/unvalidated/"
    )
    data["deployment"]["vertex_ai_model_package_checksum_or_version"] = "b" * 64

    with pytest.raises(manifest.ManifestValidationError, match="model package"):
        manifest.validate_manifest(data)
