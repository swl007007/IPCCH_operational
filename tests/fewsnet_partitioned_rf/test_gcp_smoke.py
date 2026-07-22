"""Explicitly gated live GCP smoke for the FEWSNET candidate suite."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
import re
import subprocess
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import pytest


SMOKE_ENV_VARS = (
    "FEWSNET_GCP_SMOKE_ENABLED",
    "FEWSNET_GCP_DEPLOYMENT_MANIFEST_URI",
    "FEWSNET_GCP_TEST_SNAPSHOT_MANIFEST_URI",
)
HORIZON_KEYS = ("0m", "6m", "12m")
PRODUCTION_PROJECT_ID = "food-crisis-modeling"
PRODUCTION_OBJECT_ROOT = (
    "gs://food-crisis-modeling-artifacts/fewsnet_partitioned_rf"
)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_GIT_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_GCS_BUCKET_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$"
)


def _canonical_gs_manifest_uri(
    name: str,
    value: object,
    *,
    required_suffix: str | None = None,
) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} is required")
    if value != value.strip() or any(character.isspace() for character in value):
        raise ValueError(f"{name} must be trimmed and contain no whitespace")
    parsed = urlsplit(value)
    if parsed.scheme != "gs":
        raise ValueError(f"{name} must use the gs:// scheme")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{name} must not contain a query or fragment")
    if _GCS_BUCKET_PATTERN.fullmatch(parsed.netloc) is None:
        raise ValueError(f"{name} must contain a canonical GCS bucket")
    if not parsed.path.startswith("/") or parsed.path == "/":
        raise ValueError(f"{name} must contain a nonempty object name")
    object_name = parsed.path[1:]
    segments = object_name.split("/")
    if (
        "\\" in object_name
        or any(segment in {"", ".", ".."} for segment in segments)
        or urlunsplit(parsed) != value
    ):
        raise ValueError(f"{name} must be a canonical gs://bucket/object URI")
    if required_suffix is not None and not parsed.path.endswith(required_suffix):
        raise ValueError(f"{name} must end with {required_suffix}")
    return value


def _validated_smoke_manifest_uris() -> tuple[str, str]:
    deployment_uri = _canonical_gs_manifest_uri(
        "FEWSNET_GCP_DEPLOYMENT_MANIFEST_URI",
        os.environ.get("FEWSNET_GCP_DEPLOYMENT_MANIFEST_URI"),
    )
    snapshot_uri = _canonical_gs_manifest_uri(
        "FEWSNET_GCP_TEST_SNAPSHOT_MANIFEST_URI",
        os.environ.get("FEWSNET_GCP_TEST_SNAPSHOT_MANIFEST_URI"),
        required_suffix="/source_manifest.json",
    )
    return deployment_uri, snapshot_uri


def _checked_out_source_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD^{commit}"],
            cwd=_REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("unable to resolve the checked-out Git commit") from exc
    commit = completed.stdout.strip()
    if _GIT_COMMIT_PATTERN.fullmatch(commit) is None:
        raise ValueError(
            "checked-out Git commit must be exactly 40 lowercase hex characters"
        )
    return commit


def _verified_checkout_source_commit(
    deployment_source_commit: object,
    *,
    checked_out_commit: str | None = None,
) -> str:
    if (
        not isinstance(deployment_source_commit, str)
        or _GIT_COMMIT_PATTERN.fullmatch(deployment_source_commit) is None
    ):
        raise ValueError(
            "deployment source_git_commit must be exactly 40 lowercase hex characters"
        )
    commit = (
        _checked_out_source_commit()
        if checked_out_commit is None
        else checked_out_commit
    )
    if _GIT_COMMIT_PATTERN.fullmatch(commit) is None:
        raise ValueError(
            "checked-out Git commit must be exactly 40 lowercase hex characters"
        )
    if commit != deployment_source_commit:
        raise ValueError(
            "checked-out Git commit does not equal deployment source_git_commit"
        )
    return commit


def _skip_reason() -> str:
    if os.environ.get("FEWSNET_GCP_SMOKE_ENABLED") != "1":
        return "set FEWSNET_GCP_SMOKE_ENABLED=1 to authorize the live GCP smoke"
    missing = [name for name in SMOKE_ENV_VARS if not os.environ.get(name)]
    if missing:
        return f"missing required FEWSNET GCP smoke variables: {missing}"
    try:
        _validated_smoke_manifest_uris()
    except ValueError as exc:
        return f"invalid FEWSNET GCP smoke environment: {exc}"
    return ""


_LIVE_SMOKE_SKIP_REASON = _skip_reason()


def _ref_field(ref: object, name: str) -> Any:
    if isinstance(ref, Mapping):
        return ref[name]
    return getattr(ref, name)


def _read_json_ref(store: object, ref: object) -> dict[str, Any]:
    uri = str(_ref_field(ref, "uri"))
    generation = str(_ref_field(ref, "generation"))
    data = store.read_bytes(uri, generation=generation)
    assert len(data) == int(_ref_field(ref, "size_bytes"))
    assert hashlib.sha256(data).hexdigest() == _ref_field(ref, "sha256")
    payload = json.loads(data)
    assert isinstance(payload, dict)
    return payload


def _state_name(value: object) -> str:
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name
    return str(value).rsplit(".", 1)[-1]


@pytest.mark.skipif(
    bool(_LIVE_SMOKE_SKIP_REASON),
    reason=_LIVE_SMOKE_SKIP_REASON,
)
def test_live_gcp_candidate_smoke_is_disposable_and_never_promotes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployment_manifest_uri, snapshot_manifest_uri = (
        _validated_smoke_manifest_uris()
    )
    from google.api_core.client_options import ClientOptions
    from google.api_core.exceptions import NotFound
    from google.cloud import aiplatform_v1

    from fewsnet_partitioned_rf_pipeline.cli.run_latest import (
        _default_backends,
        run_latest,
    )
    from fewsnet_partitioned_rf_pipeline.schemas import (
        validate_deployment,
        validate_payload,
    )
    from fewsnet_partitioned_rf_pipeline.vertex.storage import GCSArtifactStore

    store = GCSArtifactStore.from_default()
    deployment_ref = store.get_ref(deployment_manifest_uri)
    deployment = _read_json_ref(store, deployment_ref)
    validate_deployment(deployment)
    source_git_commit = _verified_checkout_source_commit(
        deployment["source_git_commit"]
    )
    monkeypatch.setenv("FEWSNET_SOURCE_GIT_COMMIT", source_git_commit)

    project_id = str(deployment["project_id"])
    region = str(deployment["region"])
    root_uri = str(deployment["object_store_root_uri"]).rstrip("/")
    assert project_id != PRODUCTION_PROJECT_ID, (
        "the live smoke must use a dedicated non-production GCP project"
    )
    assert not root_uri.startswith(PRODUCTION_OBJECT_ROOT), (
        "the live smoke must not use the production FEWSNET artifact root"
    )
    for name in (
        "orchestrator_service_account",
        "training_service_account",
        "batch_prediction_service_account",
    ):
        assert str(deployment[name]).endswith(
            f"@{project_id}.iam.gserviceaccount.com"
        ), f"{name} must belong to the dedicated smoke project"

    client_options = ClientOptions(
        api_endpoint=f"{region}-aiplatform.googleapis.com"
    )
    job_service = aiplatform_v1.JobServiceClient(
        client_options=client_options
    )
    model_service = aiplatform_v1.ModelServiceClient(
        client_options=client_options
    )
    endpoint_service = aiplatform_v1.EndpointServiceClient(
        client_options=client_options
    )
    parent = f"projects/{project_id}/locations/{region}"

    endpoint_names_before = {
        endpoint.name
        for endpoint in endpoint_service.list_endpoints(
            request={"parent": parent}
        )
    }
    backends = _default_backends(region)
    registry_backend = backends[1]
    alias_backend = backends[3]
    registry_backend.init(project=project_id, location=region)
    parent_models = {
        horizon_key: (
            f"{parent}/models/{deployment['parent_model_ids'][horizon_key]}"
        )
        for horizon_key in HORIZON_KEYS
    }
    production_aliases_before = {
        horizon_key: alias_backend.current_version(
            parent_models[horizon_key],
            "production",
        )
        for horizon_key in HORIZON_KEYS
    }
    current_pointer_uri = f"{root_uri}/released/current.json"

    def optional_object_state(uri: str) -> tuple[str, str, bytes] | None:
        try:
            ref = store.get_ref(uri)
        except (FileNotFoundError, NotFound):
            return None
        data = store.read_bytes(uri, generation=ref.generation)
        return (ref.generation, ref.sha256, data)

    current_pointer_before = optional_object_state(current_pointer_uri)
    result = run_latest(
        deployment,
        store,
        *backends,
        snapshot_manifest_uri=snapshot_manifest_uri,
        promote=False,
    )

    assert result["status"] == "CANDIDATE_VALIDATED"
    assert result["phase"] == "OUTPUT_VALIDATED"
    assert result["run_id"] == result["suite_version"]
    validate_payload("suite-manifest", result["suite_manifest"])

    run_manifest = _read_json_ref(store, result["run_manifest"])
    validate_payload("run-manifest", run_manifest)
    assert run_manifest["status"] == "candidate_validated"
    assert run_manifest["phase"] == "OUTPUT_VALIDATED"
    assert set(run_manifest["model_versions"]) == set(HORIZON_KEYS)
    assert set(run_manifest["batch_jobs"]) == set(HORIZON_KEYS)

    snapshot_ref = run_manifest["snapshot_ref"]
    assert snapshot_ref["uri"] == snapshot_manifest_uri
    snapshot = _read_json_ref(store, snapshot_ref)
    validate_payload("source-snapshot", snapshot)
    expected_rows = int(snapshot["area_count"])
    validation = result["validation"]
    assert validation["area_count"] == expected_rows
    assert validation["snapshot_id"] == snapshot["snapshot_id"]
    assert validation["snapshot_content_sha256"] == snapshot[
        "snapshot_content_sha256"
    ]
    assert set(validation["horizons"]) == set(HORIZON_KEYS)
    for horizon_key in HORIZON_KEYS:
        summary = validation["horizons"][horizon_key]
        assert summary["row_count"] == expected_rows
        assert sum(summary["source_counts"].values()) == expected_rows

    run_root = f"{root_uri}/runs/{result['run_id']}"
    custom_job_ref = store.get_ref(f"{run_root}/training/custom_job.json")
    custom_job_evidence = _read_json_ref(store, custom_job_ref)
    custom_job_request = custom_job_evidence["request"]["custom_job"]
    custom_job_resource = custom_job_evidence["resource"]
    operation_id = custom_job_request["labels"]["fewsnet_operation"]
    custom_jobs = list(
        job_service.list_custom_jobs(
            request={
                "parent": parent,
                "filter": (
                    f'display_name="{custom_job_request["display_name"]}" '
                    f"AND labels.fewsnet_operation={operation_id}"
                ),
            }
        )
    )
    assert len(custom_jobs) == 1
    assert custom_jobs[0].name == custom_job_resource["name"]
    assert _state_name(custom_jobs[0].state) == "JOB_STATE_SUCCEEDED"

    version_resources: set[str] = set()
    for horizon_key in HORIZON_KEYS:
        version = run_manifest["model_versions"][horizon_key]
        model = model_service.get_model(
            request={"name": version["version_resource_name"]}
        )
        observed_resource = (
            model.name
            if "@" in model.name
            else f"{model.name}@{model.version_id}"
        )
        assert observed_resource == version["version_resource_name"]
        assert str(model.version_id) == version["version_id"]
        assert model.name == version["parent_model_resource_name"]
        assert model.artifact_uri == version["artifact_uri"]
        assert model.container_spec.image_uri == deployment[
            "container_image_uri"
        ]
        assert dict(model.labels).get("lifecycle") == "candidate"
        assert version["suite_version_alias"] in set(model.version_aliases)
        assert "production" not in set(model.version_aliases)
        version_resources.add(version["version_resource_name"])
    assert len(version_resources) == 3

    expected_batch_jobs = {
        value["job_resource_name"]
        for value in run_manifest["batch_jobs"].values()
    }
    batch_run_label = hashlib.sha256(
        result["run_id"].encode("utf-8")
    ).hexdigest()[:16]
    observed_batch_jobs = list(
        job_service.list_batch_prediction_jobs(
            request={
                "parent": parent,
                "filter": f"labels.fewsnet_run={batch_run_label}",
            }
        )
    )
    assert len(observed_batch_jobs) == 3
    assert {job.name for job in observed_batch_jobs} == expected_batch_jobs
    assert all(
        _state_name(job.state) == "JOB_STATE_SUCCEEDED"
        for job in observed_batch_jobs
    )

    endpoint_names_after = {
        endpoint.name
        for endpoint in endpoint_service.list_endpoints(
            request={"parent": parent}
        )
    }
    assert endpoint_names_after == endpoint_names_before
    assert {
        horizon_key: alias_backend.current_version(
            parent_models[horizon_key],
            "production",
        )
        for horizon_key in HORIZON_KEYS
    } == production_aliases_before
    assert optional_object_state(current_pointer_uri) == current_pointer_before


_VALID_DEPLOYMENT_MANIFEST_URI = (
    "gs://dedicated-smoke-bucket/fewsnet/deployments/test.json"
)
_VALID_SNAPSHOT_MANIFEST_URI = (
    "gs://dedicated-smoke-bucket/fewsnet/inputs/snapshots/test/"
    "source_manifest.json"
)


def _set_smoke_environment(
    monkeypatch: pytest.MonkeyPatch,
    *,
    deployment_uri: str,
    snapshot_uri: str,
) -> None:
    monkeypatch.setenv("FEWSNET_GCP_SMOKE_ENABLED", "1")
    monkeypatch.setenv(
        "FEWSNET_GCP_DEPLOYMENT_MANIFEST_URI",
        deployment_uri,
    )
    monkeypatch.setenv(
        "FEWSNET_GCP_TEST_SNAPSHOT_MANIFEST_URI",
        snapshot_uri,
    )


@pytest.mark.parametrize(
    ("deployment_uri", "snapshot_uri"),
    (
        (" ", _VALID_SNAPSHOT_MANIFEST_URI),
        ("not-a-uri", _VALID_SNAPSHOT_MANIFEST_URI),
        ("gs://bucket", _VALID_SNAPSHOT_MANIFEST_URI),
        (
            f"{_VALID_DEPLOYMENT_MANIFEST_URI}?generation=1",
            _VALID_SNAPSHOT_MANIFEST_URI,
        ),
        (
            _VALID_DEPLOYMENT_MANIFEST_URI,
            "gs://dedicated-smoke-bucket/fewsnet/snapshot.json",
        ),
        (
            _VALID_DEPLOYMENT_MANIFEST_URI,
            f"{_VALID_SNAPSHOT_MANIFEST_URI}#fragment",
        ),
        (
            _VALID_DEPLOYMENT_MANIFEST_URI,
            f" {_VALID_SNAPSHOT_MANIFEST_URI}",
        ),
    ),
)
def test_smoke_gate_rejects_malformed_manifest_uris(
    monkeypatch: pytest.MonkeyPatch,
    deployment_uri: str,
    snapshot_uri: str,
) -> None:
    _set_smoke_environment(
        monkeypatch,
        deployment_uri=deployment_uri,
        snapshot_uri=snapshot_uri,
    )

    assert _skip_reason().startswith("invalid FEWSNET GCP smoke environment:")


def test_smoke_gate_accepts_canonical_manifest_uris(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_smoke_environment(
        monkeypatch,
        deployment_uri=_VALID_DEPLOYMENT_MANIFEST_URI,
        snapshot_uri=_VALID_SNAPSHOT_MANIFEST_URI,
    )

    assert _skip_reason() == ""


def test_source_commit_mismatch_fails_before_environment_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FEWSNET_SOURCE_GIT_COMMIT", raising=False)
    helper = globals().get("_verified_checkout_source_commit")
    assert callable(helper), "live smoke lacks a checkout source-commit gate"

    with pytest.raises(ValueError, match="checked-out Git commit"):
        helper("0" * 40, checked_out_commit="1" * 40)
    assert "FEWSNET_SOURCE_GIT_COMMIT" not in os.environ


def test_source_commit_match_uses_exact_checked_out_identity() -> None:
    checkout_helper = globals().get("_checked_out_source_commit")
    verify_helper = globals().get("_verified_checkout_source_commit")
    assert callable(checkout_helper)
    assert callable(verify_helper)

    checked_out_commit = checkout_helper()
    assert len(checked_out_commit) == 40
    assert checked_out_commit == checked_out_commit.lower()
    assert all(character in "0123456789abcdef" for character in checked_out_commit)
    assert verify_helper(checked_out_commit) == checked_out_commit
