"""Explicitly gated live GCP smoke for the FEWSNET candidate suite."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from typing import Any

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


def _skip_reason() -> str:
    if os.environ.get("FEWSNET_GCP_SMOKE_ENABLED") != "1":
        return "set FEWSNET_GCP_SMOKE_ENABLED=1 to authorize the live GCP smoke"
    missing = [name for name in SMOKE_ENV_VARS if not os.environ.get(name)]
    if missing:
        return f"missing required FEWSNET GCP smoke variables: {missing}"
    return ""


pytestmark = pytest.mark.skipif(bool(_skip_reason()), reason=_skip_reason())


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


def test_live_gcp_candidate_smoke_is_disposable_and_never_promotes() -> None:
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

    deployment_manifest_uri = os.environ[
        "FEWSNET_GCP_DEPLOYMENT_MANIFEST_URI"
    ]
    snapshot_manifest_uri = os.environ[
        "FEWSNET_GCP_TEST_SNAPSHOT_MANIFEST_URI"
    ]
    store = GCSArtifactStore.from_default()
    deployment_ref = store.get_ref(deployment_manifest_uri)
    deployment = _read_json_ref(store, deployment_ref)
    validate_deployment(deployment)

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
