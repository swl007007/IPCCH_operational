from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from importlib import import_module
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from fewsnet_partitioned_rf_pipeline.core.horizons import (
    select_latest_inference_frame,
)
from fewsnet_partitioned_rf_pipeline.core.inference import (
    FORMAL_PREDICTION_COLUMNS,
)
from fewsnet_partitioned_rf_pipeline.core.types import (
    BatchJobRef,
    FeatureContract,
    RegisteredModelVersion,
)
from fewsnet_partitioned_rf_pipeline.schemas import validate_payload
from fewsnet_partitioned_rf_pipeline.vertex.storage import LocalArtifactStore


FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures/fewsnet_partitioned_rf"
RAW_OUTPUT_FIXTURE = FIXTURE_ROOT / "vertex_batch_output.jsonl"
SUITE_VERSION = "fewsnet-prf-202604-test"
RUN_ROOT_URI = "gs://bucket/fewsnet_partitioned_rf/runs/run-001"
SUITE_ROOT_URI = f"gs://bucket/fewsnet_partitioned_rf/suites/{SUITE_VERSION}"
JOB_NAME = (
    "projects/food-crisis-modeling/locations/us-central1/"
    "batchPredictionJobs/123456789"
)
OUTPUT_DIRECTORY = f"{RUN_ROOT_URI}/batch_prediction/6m/raw/job-123456789"


def _batch_module():
    return import_module(
        "fewsnet_partitioned_rf_pipeline.vertex.batch_prediction"
    )


def _cli_module():
    return import_module("fewsnet_partitioned_rf_pipeline.cli.infer")


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


def _latest_input_frame() -> pd.DataFrame:
    feature_frame = pd.DataFrame(
        {
            "admin_code": ["B", "A", "B", "A"],
            "feature_month": ["2026-03", "2026-03", "2026-04", "2026-04"],
            "signal": [30.0, 10.0, 3.5, 1.5],
            "auxiliary": [40.0, 20.0, 4.5, 2.5],
        }
    )
    latest = select_latest_inference_frame(
        feature_frame,
        "2026-04",
        6,
    )
    return latest.iloc[::-1].reset_index(drop=True)


def _model_ref() -> RegisteredModelVersion:
    parent = (
        "projects/food-crisis-modeling/locations/us-central1/models/"
        "fewsnet-partitioned-rf-6m"
    )
    return RegisteredModelVersion(
        horizon_key="6m",
        parent_model_resource_name=parent,
        version_resource_name=f"{parent}@17",
        version_id="17",
        suite_version_alias="fewsnet-prf-202604-test",
        artifact_uri=f"{SUITE_ROOT_URI}/models/6m",
    )


def _deployment() -> dict[str, object]:
    return {
        "schema_version": "fewsnet-deployment-v1",
        "project_id": "food-crisis-modeling",
        "region": "us-central1",
        "object_store_root_uri": "gs://bucket/fewsnet_partitioned_rf",
        "orchestrator_service_account": (
            "fewsnet-orchestrator@food-crisis-modeling.iam.gserviceaccount.com"
        ),
        "training_service_account": (
            "fewsnet-training@food-crisis-modeling.iam.gserviceaccount.com"
        ),
        "batch_prediction_service_account": (
            "fewsnet-batch@food-crisis-modeling.iam.gserviceaccount.com"
        ),
        "container_image_uri": (
            "us-central1-docker.pkg.dev/food-crisis-modeling/fewsnet/model@"
            f"sha256:{'a' * 64}"
        ),
        "container_image_digest": f"sha256:{'a' * 64}",
        "source_git_commit": "1" * 40,
        "parent_model_ids": {
            "0m": "fewsnet-partitioned-rf-0m",
            "6m": "fewsnet-partitioned-rf-6m",
            "12m": "fewsnet-partitioned-rf-12m",
        },
        "training_machine_type": "n2-highmem-8",
        "batch_machine_type": "n2-standard-8",
        "training_timeout_seconds": 21600,
        "batch_timeout_seconds": 7200,
        "max_retries": 3,
    }


def _submission_config(model_ref: RegisteredModelVersion | None = None) -> dict:
    return {
        "deployment": _deployment(),
        "run_id": "run-001",
        "horizon_key": "6m",
        "model_ref": model_ref or _model_ref(),
        "job_display_name": "fewsnet-batch-run-001-6m",
        "labels": {
            "fewsnet_mode": "batch-prediction",
            "fewsnet_run": "run-001",
            "fewsnet_horizon": "6m",
        },
    }


@dataclass
class FakeSubmittedBatchJob:
    resource_name: str
    display_name: str
    gca_resource: dict[str, object]


class FakeBatchPredictionJobBoundary:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    def submit(self, **kwargs):
        self.calls.append(dict(kwargs))
        return FakeSubmittedBatchJob(
            resource_name=JOB_NAME,
            display_name=str(kwargs["job_display_name"]),
            gca_resource=_job_resource("JOB_STATE_QUEUED"),
        )


class FakeBatchSDK:
    def __init__(self):
        self.BatchPredictionJob = FakeBatchPredictionJobBoundary()


class FakeJobService:
    def __init__(self, resources):
        self.resources = iter(resources)
        self.events: list[tuple[str, str]] = []

    def get_batch_prediction_job(self, *, name: str):
        self.events.append(("get", name))
        return next(self.resources)

    def cancel_batch_prediction_job(self, *, name: str):
        self.events.append(("cancel", name))
        return {"name": name, "cancel_requested": True}


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class RecordingLocalArtifactStore(LocalArtifactStore):
    def __init__(self, root: Path):
        super().__init__(root)
        self.events: list[tuple[str, str, bytes]] = []

    def put_bytes(self, uri, data, *, if_generation_match=None):
        self.events.append(("put_bytes", uri, data))
        return super().put_bytes(
            uri,
            data,
            if_generation_match=if_generation_match,
        )


def _job_resource(
    state: str,
    *,
    name: str = JOB_NAME,
    output_directory: str | None = None,
    error: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "name": name,
        "display_name": "fewsnet-batch-run-001-6m",
        "model": _model_ref().version_resource_name,
        "state": state,
        "input_config": {
            "instances_format": "jsonl",
            "gcs_source": {"uris": [f"{RUN_ROOT_URI}/batch_prediction/6m/input.jsonl"]},
        },
        "output_config": {
            "predictions_format": "jsonl",
            "gcs_destination": {
                "output_uri_prefix": (
                    f"{RUN_ROOT_URI}/batch_prediction/6m/raw"
                )
            },
        },
        "dedicated_resources": {
            "machine_spec": {"machine_type": "n2-standard-8"},
            "starting_replica_count": 1,
            "max_replica_count": 1,
        },
        "service_account": (
            "fewsnet-batch@food-crisis-modeling.iam.gserviceaccount.com"
        ),
        "manual_batch_tuning_parameters": {"batch_size": 64},
        "generate_explanation": False,
        "labels": {
            "fewsnet_mode": "batch-prediction",
            "fewsnet_run": "run-001",
            "fewsnet_horizon": "6m",
        },
        "create_time": "2026-07-21T12:00:00Z",
        "start_time": "2026-07-21T12:01:00Z",
        "end_time": (
            "2026-07-21T12:02:00Z"
            if state.startswith("JOB_STATE_SUCCEEDED")
            or state in {"JOB_STATE_FAILED", "JOB_STATE_CANCELLED"}
            else None
        ),
        "update_time": "2026-07-21T12:01:30Z",
        "error": error or {},
        "partial_failures": [],
        "output_info": (
            {"gcs_output_directory": output_directory}
            if output_directory is not None
            else {}
        ),
    }


def _job_ref() -> BatchJobRef:
    return BatchJobRef(
        horizon_key="6m",
        job_resource_name=JOB_NAME,
        model_version_resource_name=_model_ref().version_resource_name,
        input_uri=f"{RUN_ROOT_URI}/batch_prediction/6m/input.jsonl",
        destination_prefix=f"{RUN_ROOT_URI}/batch_prediction/6m/raw",
    )


def _json_record(record: pd.Series) -> dict[str, object]:
    payload = record.to_dict()
    if pd.isna(payload["cluster_id"]):
        payload["cluster_id"] = None
    payload["horizon_months"] = int(payload["horizon_months"])
    payload["predicted_crisis"] = int(payload["predicted_crisis"])
    if payload["cluster_id"] is not None:
        payload["cluster_id"] = int(payload["cluster_id"])
    return payload


def test_batch_prediction_module_exposes_task_16_interfaces():
    module = _batch_module()

    assert callable(module.write_batch_input_jsonl)
    assert callable(module.submit_batch_prediction)
    assert callable(module.wait_batch_prediction)
    assert callable(module.normalize_batch_output)
    assert callable(_cli_module().normalize_and_publish_batch_output)


def test_write_batch_input_jsonl_emits_one_ordered_horizon_neutral_instance_per_area(
    tmp_path,
):
    output_path = tmp_path / "input.jsonl"

    _batch_module().write_batch_input_jsonl(
        _latest_input_frame(),
        _feature_contract(),
        output_path,
    )

    lines = output_path.read_text(encoding="utf-8").splitlines()
    instances = [json.loads(line) for line in lines]
    assert len(instances) == 2
    assert [list(instance) for instance in instances] == [
        ["admin_code", "feature_month", "signal", "auxiliary"],
        ["admin_code", "feature_month", "signal", "auxiliary"],
    ]
    assert [instance["admin_code"] for instance in instances] == ["B", "A"]
    assert [instance["feature_month"] for instance in instances] == [
        "2026-04",
        "2026-04",
    ]
    assert instances[0]["signal"] == 3.5
    assert instances[1]["auxiliary"] == 2.5
    assert all("horizon_months" not in instance for instance in instances)
    assert all("target_month" not in instance for instance in instances)


def test_write_batch_input_jsonl_serializes_missing_numeric_features_as_json_null(
    tmp_path,
):
    frame = _latest_input_frame()
    frame.loc[0, "signal"] = np.nan

    _batch_module().write_batch_input_jsonl(
        frame,
        _feature_contract(),
        tmp_path / "input.jsonl",
    )

    first = json.loads((tmp_path / "input.jsonl").read_text().splitlines()[0])
    assert first["signal"] is None


@pytest.mark.parametrize("invalid_value", ["3.5", True, np.inf, -np.inf])
def test_write_batch_input_jsonl_rejects_non_float64_values_before_replacing_output(
    tmp_path,
    invalid_value,
):
    output_path = tmp_path / "input.jsonl"
    output_path.write_bytes(b"preserve-existing-bytes\n")
    frame = _latest_input_frame()
    frame["signal"] = frame["signal"].astype(object)
    frame.at[0, "signal"] = invalid_value

    with pytest.raises(ValueError):
        _batch_module().write_batch_input_jsonl(
            frame,
            _feature_contract(),
            output_path,
        )

    assert output_path.read_bytes() == b"preserve-existing-bytes\n"


def test_write_batch_input_jsonl_enforces_declared_dtype_and_emits_native_float(
    tmp_path,
):
    batch = _batch_module()
    invalid_contract = replace(
        _feature_contract(),
        feature_dtypes=("int64", "float64"),
    )
    output_path = tmp_path / "input.jsonl"

    with pytest.raises(ValueError, match="float64"):
        batch.write_batch_input_jsonl(
            _latest_input_frame(),
            invalid_contract,
            output_path,
        )
    assert not output_path.exists()

    frame = _latest_input_frame()
    frame["signal"] = frame["signal"].astype(object)
    frame.at[0, "signal"] = np.int64(3)
    batch.write_batch_input_jsonl(frame, _feature_contract(), output_path)
    first = json.loads(output_path.read_text().splitlines()[0])
    assert type(first["signal"]) is float
    assert first["signal"] == 3.0


def test_submit_batch_prediction_uses_async_exact_version_sdk_contract():
    batch = _batch_module()
    sdk = FakeBatchSDK()
    backend = batch.VertexBatchBackend(sdk=sdk, job_service=FakeJobService([]))

    job_ref = batch.submit_batch_prediction(_submission_config(), backend)

    assert job_ref == _job_ref()
    assert sdk.BatchPredictionJob.calls == [
        {
            "job_display_name": "fewsnet-batch-run-001-6m",
            "model_name": _model_ref().version_resource_name,
            "instances_format": "jsonl",
            "predictions_format": "jsonl",
            "gcs_source": f"{RUN_ROOT_URI}/batch_prediction/6m/input.jsonl",
            "gcs_destination_prefix": f"{RUN_ROOT_URI}/batch_prediction/6m/raw",
            "machine_type": "n2-standard-8",
            "starting_replica_count": 1,
            "max_replica_count": 1,
            "service_account": (
                "fewsnet-batch@food-crisis-modeling.iam.gserviceaccount.com"
            ),
            "labels": {
                "fewsnet_mode": "batch-prediction",
                "fewsnet_run": "run-001",
                "fewsnet_horizon": "6m",
            },
            "project": "food-crisis-modeling",
            "location": "us-central1",
        }
    ]


@pytest.mark.parametrize(
    "model_ref",
    [
        replace(_model_ref(), version_id="candidate"),
        replace(
            _model_ref(),
            version_resource_name=_model_ref().parent_model_resource_name,
        ),
        replace(
            _model_ref(),
            version_resource_name=(
                f"{_model_ref().parent_model_resource_name}@18"
            ),
        ),
    ],
)
def test_submit_batch_prediction_rejects_non_numeric_or_inexact_model_versions(
    model_ref,
):
    batch = _batch_module()
    sdk = FakeBatchSDK()
    backend = batch.VertexBatchBackend(sdk=sdk, job_service=FakeJobService([]))

    with pytest.raises(ValueError, match="version"):
        batch.submit_batch_prediction(_submission_config(model_ref), backend)

    assert sdk.BatchPredictionJob.calls == []


@pytest.mark.parametrize(
    "wrong_parent",
    [
        (
            "projects/wrong-project/locations/us-central1/models/"
            "fewsnet-partitioned-rf-6m"
        ),
        (
            "projects/food-crisis-modeling/locations/europe-west1/models/"
            "fewsnet-partitioned-rf-6m"
        ),
        (
            "projects/food-crisis-modeling/locations/us-central1/models/"
            "fewsnet-partitioned-rf-12m"
        ),
    ],
    ids=["wrong-project", "wrong-region", "wrong-stable-parent"],
)
def test_submit_batch_prediction_binds_model_parent_to_deployment(
    wrong_parent,
):
    batch = _batch_module()
    model_ref = replace(
        _model_ref(),
        parent_model_resource_name=wrong_parent,
        version_resource_name=f"{wrong_parent}@17",
    )
    sdk = FakeBatchSDK()
    backend = batch.VertexBatchBackend(sdk=sdk, job_service=FakeJobService([]))

    with pytest.raises(ValueError, match="parent"):
        batch.submit_batch_prediction(_submission_config(model_ref), backend)

    assert sdk.BatchPredictionJob.calls == []


def test_wait_batch_prediction_polls_exact_name_and_records_success_output():
    batch = _batch_module()
    service = FakeJobService(
        [
            _job_resource("JOB_STATE_QUEUED"),
            _job_resource("JOB_STATE_RUNNING"),
            _job_resource(
                "JOB_STATE_SUCCEEDED",
                output_directory=OUTPUT_DIRECTORY,
            ),
        ]
    )
    backend = batch.VertexBatchBackend(sdk=FakeBatchSDK(), job_service=service)
    clock = FakeClock()

    terminal = batch.wait_batch_prediction(
        _job_ref(),
        10,
        backend,
        poll_interval_seconds=1,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    assert terminal == replace(
        _job_ref(),
        gcs_output_directory=OUTPUT_DIRECTORY,
    )
    assert service.events == [("get", JOB_NAME)] * 3


def test_wait_batch_prediction_accepts_success_returned_on_deadline_without_cancel():
    batch = _batch_module()
    service = FakeJobService(
        [
            _job_resource("JOB_STATE_QUEUED"),
            _job_resource("JOB_STATE_RUNNING"),
            _job_resource(
                "JOB_STATE_SUCCEEDED",
                output_directory=OUTPUT_DIRECTORY,
            ),
        ]
    )
    backend = batch.VertexBatchBackend(sdk=FakeBatchSDK(), job_service=service)
    clock = FakeClock()

    terminal = batch.wait_batch_prediction(
        _job_ref(),
        2,
        backend,
        poll_interval_seconds=1,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    assert terminal == replace(
        _job_ref(),
        gcs_output_directory=OUTPUT_DIRECTORY,
    )
    assert service.events == [("get", JOB_NAME)] * 3


def test_wait_batch_prediction_timeout_cancels_exact_name_then_waits_for_terminal():
    batch = _batch_module()
    service = FakeJobService(
        [
            _job_resource("JOB_STATE_QUEUED"),
            _job_resource("JOB_STATE_RUNNING"),
            _job_resource("JOB_STATE_CANCELLING"),
            _job_resource("JOB_STATE_CANCELLED"),
        ]
    )
    backend = batch.VertexBatchBackend(sdk=FakeBatchSDK(), job_service=service)
    clock = FakeClock()

    with pytest.raises(batch.BatchPredictionTimeoutError) as caught:
        batch.wait_batch_prediction(
            _job_ref(),
            2,
            backend,
            poll_interval_seconds=1,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )

    assert caught.value.job_ref == _job_ref()
    assert [event for event in service.events if event[0] == "cancel"] == [
        ("cancel", JOB_NAME)
    ]
    cancel_index = service.events.index(("cancel", JOB_NAME))
    assert ("get", JOB_NAME) in service.events[cancel_index + 1 :]


def test_wait_batch_prediction_surfaces_complete_failed_job_response():
    batch = _batch_module()
    failed = _job_resource(
        "JOB_STATE_FAILED",
        error={
            "code": 13,
            "message": "prediction worker failed",
            "details": [{"reason": "CONTAINER_EXIT"}],
        },
    )
    backend = batch.VertexBatchBackend(
        sdk=FakeBatchSDK(),
        job_service=FakeJobService([failed]),
    )

    with pytest.raises(batch.BatchPredictionJobError) as caught:
        batch.wait_batch_prediction(_job_ref(), 10, backend)

    assert caught.value.resource == failed


def test_normalize_batch_output_restores_input_order_and_sets_exact_identity():
    predictions = _batch_module().normalize_batch_output(
        [RAW_OUTPUT_FIXTURE],
        _latest_input_frame(),
        _model_ref(),
        SUITE_VERSION,
    )

    assert predictions.columns.tolist() == list(FORMAL_PREDICTION_COLUMNS)
    assert predictions["admin_code"].tolist() == ["B", "A"]
    assert predictions["feature_month"].tolist() == ["2026-04", "2026-04"]
    assert predictions["target_month"].tolist() == ["2026-10", "2026-10"]
    assert predictions["horizon_months"].tolist() == [6, 6]
    assert predictions["probability_crisis"].tolist() == [0.2, 0.8]
    assert predictions["suite_version"].tolist() == [SUITE_VERSION] * 2
    assert predictions["vertex_model_resource_name"].tolist() == [
        _model_ref().version_resource_name,
    ] * 2
    assert predictions["vertex_model_version_id"].tolist() == ["17", "17"]
    for _, record in predictions.iterrows():
        validate_payload("prediction-record", _json_record(record))


@pytest.mark.parametrize(
    "mutation",
    [
        "feature-value-drift",
        "feature-type-drift",
        "horizon-leak",
        "target-leak",
        "extra-field",
    ],
)
def test_normalize_batch_output_requires_exact_echoed_input_instance(
    tmp_path,
    mutation,
):
    lines = RAW_OUTPUT_FIXTURE.read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[0])
    if mutation == "feature-value-drift":
        payload["instance"]["signal"] = 99.0
    elif mutation == "feature-type-drift":
        payload["instance"]["signal"] = "1.5"
    elif mutation == "horizon-leak":
        payload["instance"]["horizon_months"] = 6
    elif mutation == "target-leak":
        payload["instance"]["target_month"] = "2026-10"
    elif mutation == "extra-field":
        payload["instance"]["unexpected"] = "leak"
    else:
        raise AssertionError(mutation)
    lines[0] = json.dumps(payload, separators=(",", ":"))
    raw_path = tmp_path / "predictions_0001.jsonl"
    raw_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    input_frame = _latest_input_frame()
    input_frame["fews_ipc_crisis"] = [0, 1]

    with pytest.raises(ValueError, match="instance"):
        _batch_module().normalize_batch_output(
            [raw_path],
            input_frame,
            _model_ref(),
            SUITE_VERSION,
        )


@pytest.mark.parametrize(
    ("model_ref", "message"),
    [
        (
            replace(
                _model_ref(),
                suite_version_alias="fewsnet-prf-202604-other",
            ),
            "suite",
        ),
        (
            replace(
                _model_ref(),
                artifact_uri=(
                    "gs://bucket/fewsnet_partitioned_rf/suites/"
                    "fewsnet-prf-202604-other/models/6m"
                ),
            ),
            "artifact",
        ),
        (
            replace(
                _model_ref(),
                artifact_uri=f"{SUITE_ROOT_URI}/models/12m",
            ),
            "artifact",
        ),
    ],
    ids=["wrong-alias", "wrong-artifact-suite", "wrong-artifact-horizon"],
)
def test_normalize_batch_output_binds_model_to_suite_and_horizon(
    model_ref,
    message,
):
    with pytest.raises(ValueError, match=message):
        _batch_module().normalize_batch_output(
            [RAW_OUTPUT_FIXTURE],
            _latest_input_frame(),
            model_ref,
            SUITE_VERSION,
        )


@pytest.mark.parametrize("drift", ["whitespace", "leading-zero"])
def test_normalize_batch_output_rejects_lossy_prediction_admin_identity(
    tmp_path,
    drift,
):
    payloads = [
        json.loads(line)
        for line in RAW_OUTPUT_FIXTURE.read_text(encoding="utf-8").splitlines()
    ]
    input_frame = _latest_input_frame()
    if drift == "whitespace":
        payloads[0]["prediction"]["admin_code"] = " A "
    elif drift == "leading-zero":
        replacements = {"A": "1", "B": "2"}
        input_frame["admin_code"] = input_frame["admin_code"].map(replacements)
        for payload in payloads:
            canonical = replacements[payload["instance"]["admin_code"]]
            payload["instance"]["admin_code"] = canonical
            payload["prediction"]["admin_code"] = canonical
        payloads[0]["prediction"]["admin_code"] = "001"
    else:
        raise AssertionError(drift)
    raw_path = tmp_path / "predictions_0001.jsonl"
    raw_path.write_text(
        "\n".join(
            json.dumps(payload, separators=(",", ":"))
            for payload in payloads
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="admin_code"):
        _batch_module().normalize_batch_output(
            [raw_path],
            input_frame,
            _model_ref(),
            SUITE_VERSION,
        )


def _mutated_raw_file(tmp_path: Path, mutation: str) -> list[Path]:
    lines = RAW_OUTPUT_FIXTURE.read_text(encoding="utf-8").splitlines()
    if mutation == "error_file":
        path = tmp_path / "errors_0001.jsonl"
        path.write_text(
            json.dumps({"error": {"code": 400, "message": "bad instance"}})
            + "\n",
            encoding="utf-8",
        )
        return [path]
    if mutation == "line_error":
        payload = json.loads(lines[0])
        payload["error"] = {"code": 400, "message": "bad instance"}
        path = tmp_path / "predictions_0001.jsonl"
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        return [path]
    if mutation == "malformed":
        path = tmp_path / "predictions_0001.jsonl"
        path.write_text("{not-json}\n", encoding="utf-8")
        return [path]
    if mutation == "duplicate":
        lines.append(lines[0])
    elif mutation == "missing":
        lines = lines[:1]
    else:
        payload = json.loads(lines[0])
        if mutation == "instance_identity":
            payload["instance"]["admin_code"] = "NOT-IN-INPUT"
        elif mutation == "prediction_identity":
            payload["prediction"]["admin_code"] = "B"
        elif mutation == "schema":
            payload["prediction"]["probability_crisis"] = 1.2
        elif mutation == "suite_identity":
            payload["prediction"]["suite_version"] = "wrong-suite"
        else:
            raise AssertionError(mutation)
        lines[0] = json.dumps(payload, separators=(",", ":"))
    path = tmp_path / "predictions_0001.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [path]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("error_file", "error"),
        ("line_error", "error"),
        ("malformed", "JSON"),
        ("duplicate", "duplicate"),
        ("missing", "missing"),
        ("instance_identity", "input"),
        ("prediction_identity", "identity"),
        ("schema", "prediction-record"),
        ("suite_identity", "suite"),
    ],
)
def test_normalize_batch_output_rejects_any_incomplete_or_inconsistent_output(
    tmp_path,
    mutation,
    message,
):
    with pytest.raises(ValueError, match=message):
        _batch_module().normalize_batch_output(
            _mutated_raw_file(tmp_path, mutation),
            _latest_input_frame(),
            _model_ref(),
            SUITE_VERSION,
        )


def test_normalize_and_publish_batch_output_writes_one_canonical_csv_to_both_uris(
    tmp_path,
):
    store = RecordingLocalArtifactStore(tmp_path / "store")
    run_uri = f"{RUN_ROOT_URI}/predictions/6m.csv"
    suite_uri = f"{SUITE_ROOT_URI}/predictions/6m.csv"

    predictions = _cli_module().normalize_and_publish_batch_output(
        raw_paths=[RAW_OUTPUT_FIXTURE],
        input_frame=_latest_input_frame(),
        model_ref=_model_ref(),
        suite_version=SUITE_VERSION,
        run_csv_uri=run_uri,
        suite_csv_uri=suite_uri,
        store=store,
    )

    assert predictions["admin_code"].tolist() == ["B", "A"]
    assert store.events == [
        ("put_bytes", run_uri, store.events[0][2]),
        ("put_bytes", suite_uri, store.events[0][2]),
    ]
    assert store.read_bytes(run_uri) == store.read_bytes(suite_uri)
    csv = pd.read_csv(io.BytesIO(store.read_bytes(run_uri)))
    assert csv.columns.tolist() == list(FORMAL_PREDICTION_COLUMNS)
    assert csv["admin_code"].tolist() == ["B", "A"]


def test_normalize_and_publish_rejects_run_uri_outside_suite_publication_root(
    tmp_path,
):
    store = RecordingLocalArtifactStore(tmp_path / "store")

    with pytest.raises(ValueError, match="run_csv_uri"):
        _cli_module().normalize_and_publish_batch_output(
            raw_paths=[RAW_OUTPUT_FIXTURE],
            input_frame=_latest_input_frame(),
            model_ref=_model_ref(),
            suite_version=SUITE_VERSION,
            run_csv_uri=(
                "gs://wrong-bucket/unrelated/runs/run-001/predictions/6m.csv"
            ),
            suite_csv_uri=f"{SUITE_ROOT_URI}/predictions/6m.csv",
            store=store,
        )

    assert store.events == []


def test_normalize_and_publish_rejects_empty_run_id_before_writes(tmp_path):
    store = RecordingLocalArtifactStore(tmp_path / "store")

    with pytest.raises(ValueError, match="run_csv_uri"):
        _cli_module().normalize_and_publish_batch_output(
            raw_paths=[RAW_OUTPUT_FIXTURE],
            input_frame=_latest_input_frame(),
            model_ref=_model_ref(),
            suite_version=SUITE_VERSION,
            run_csv_uri=(
                "gs://bucket/fewsnet_partitioned_rf/runs//predictions/6m.csv"
            ),
            suite_csv_uri=f"{SUITE_ROOT_URI}/predictions/6m.csv",
            store=store,
        )

    assert store.events == []


def test_normalize_and_publish_rejects_nested_run_id_segments_before_writes(
    tmp_path,
):
    store = RecordingLocalArtifactStore(tmp_path / "store")

    with pytest.raises(ValueError, match="run_csv_uri"):
        _cli_module().normalize_and_publish_batch_output(
            raw_paths=[RAW_OUTPUT_FIXTURE],
            input_frame=_latest_input_frame(),
            model_ref=_model_ref(),
            suite_version=SUITE_VERSION,
            run_csv_uri=(
                "gs://bucket/fewsnet_partitioned_rf/runs/"
                "run-001/run-002/predictions/6m.csv"
            ),
            suite_csv_uri=f"{SUITE_ROOT_URI}/predictions/6m.csv",
            store=store,
        )

    assert store.events == []


def test_normalize_and_publish_binds_artifact_to_exact_suite_uri_before_writes(
    tmp_path,
):
    store = RecordingLocalArtifactStore(tmp_path / "store")
    model_ref = replace(
        _model_ref(),
        artifact_uri=(
            "gs://other-bucket/fewsnet_partitioned_rf/suites/"
            f"{SUITE_VERSION}/models/6m"
        ),
    )

    with pytest.raises(ValueError, match="artifact"):
        _cli_module().normalize_and_publish_batch_output(
            raw_paths=[RAW_OUTPUT_FIXTURE],
            input_frame=_latest_input_frame(),
            model_ref=model_ref,
            suite_version=SUITE_VERSION,
            run_csv_uri=f"{RUN_ROOT_URI}/predictions/6m.csv",
            suite_csv_uri=f"{SUITE_ROOT_URI}/predictions/6m.csv",
            store=store,
        )

    assert store.events == []


def test_normalized_cluster_id_remains_nullable_integer_in_frame_and_csv(tmp_path):
    predictions = _batch_module().normalize_batch_output(
        [RAW_OUTPUT_FIXTURE],
        _latest_input_frame(),
        _model_ref(),
        SUITE_VERSION,
    )

    assert str(predictions["cluster_id"].dtype) == "Int64"
    records = predictions.astype(object).where(predictions.notna(), None)
    for record in records.to_dict(orient="records"):
        validate_payload("prediction-record", record)

    store = RecordingLocalArtifactStore(tmp_path / "store")
    run_uri = f"{RUN_ROOT_URI}/predictions/6m.csv"
    _cli_module().normalize_and_publish_batch_output(
        raw_paths=[RAW_OUTPUT_FIXTURE],
        input_frame=_latest_input_frame(),
        model_ref=_model_ref(),
        suite_version=SUITE_VERSION,
        run_csv_uri=run_uri,
        suite_csv_uri=f"{SUITE_ROOT_URI}/predictions/6m.csv",
        store=store,
    )
    rows = list(
        csv.reader(io.StringIO(store.read_bytes(run_uri).decode("utf-8")))
    )
    cluster_index = rows[0].index("cluster_id")
    assert rows[1][cluster_index] == ""
    assert rows[2][cluster_index] == "3"


def test_normalize_and_publish_batch_output_writes_nothing_when_any_gate_fails(
    tmp_path,
):
    store = RecordingLocalArtifactStore(tmp_path / "store")

    with pytest.raises(ValueError, match="JSON"):
        _cli_module().normalize_and_publish_batch_output(
            raw_paths=_mutated_raw_file(tmp_path, "malformed"),
            input_frame=_latest_input_frame(),
            model_ref=_model_ref(),
            suite_version=SUITE_VERSION,
            run_csv_uri=f"{RUN_ROOT_URI}/predictions/6m.csv",
            suite_csv_uri=f"{SUITE_ROOT_URI}/predictions/6m.csv",
            store=store,
        )

    assert store.events == []
