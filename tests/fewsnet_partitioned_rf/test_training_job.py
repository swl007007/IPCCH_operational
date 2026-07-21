from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from google.api_core.exceptions import ServiceUnavailable
from shapely.geometry import Point

from fewsnet_partitioned_rf_pipeline.cli.run_latest import (
    _VertexTrainingBackend,
    retry_transient,
)
from fewsnet_partitioned_rf_pipeline.cli.train import (
    TrainingWorkerConfig,
    run_training_worker,
)
from fewsnet_partitioned_rf_pipeline.config import FEATURE_CONTRACT_PATH
from fewsnet_partitioned_rf_pipeline.schemas import validate_payload
from fewsnet_partitioned_rf_pipeline.vertex.storage import (
    LocalArtifactStore,
    put_immutable_or_verify,
    upload_file_immutable_or_verify,
)
from fewsnet_partitioned_rf_pipeline.vertex.training_job import (
    TrainingCustomJobConfig,
    TrainingJobTimeoutError,
    build_training_custom_job_spec,
    submit_and_persist_training_custom_job,
    wait_for_training_custom_job,
)


SHA256_A = "a" * 64
IMAGE_DIGEST = f"sha256:{SHA256_A}"
IMAGE_URI = (
    "us-central1-docker.pkg.dev/project/fewsnet/trainer"
    f"@{IMAGE_DIGEST}"
)
SOURCE_COMMIT = "1" * 40
SUITE_VERSION = "fewsnet-prf-202412-test"
RUN_ROOT_URI = "gs://bucket/runs/run-001"
MODEL_ROOT_URI = f"gs://bucket/suites/{SUITE_VERSION}/models"


class RecordingLocalArtifactStore(LocalArtifactStore):
    def __init__(self, root: Path):
        super().__init__(root)
        self.events: list[tuple[str, str]] = []

    def put_bytes(self, uri, data, *, if_generation_match=None):
        self.events.append(("put_bytes", uri))
        return super().put_bytes(
            uri,
            data,
            if_generation_match=if_generation_match,
        )

    def upload_file(self, path, uri, *, if_generation_match=None):
        self.events.append(("upload_file", uri))
        return super().upload_file(
            path,
            uri,
            if_generation_match=if_generation_match,
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _panel_file_payload(path: Path, *, rows: int, columns: int) -> dict:
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
        "row_count": rows,
        "column_count": columns,
    }


def _write_panel(path: Path) -> pd.DataFrame:
    contract = json.loads(FEATURE_CONTRACT_PATH.read_text(encoding="utf-8"))
    source_columns = list(contract["required_source_columns"])
    periods = pd.period_range("2020-01", "2024-12", freq="M")
    rows: list[dict[str, object]] = []
    for admin_code, latitude, longitude in (
        ("0", 9.551002, 29.130297),
        ("1", 9.786447, 28.414507),
    ):
        for index, period in enumerate(periods):
            row = {
                name: float((column_index % 11) + 1) + index / 1000
                for column_index, name in enumerate(source_columns)
            }
            crisis = (index + int(admin_code)) % 2
            row.update(
                {
                    "FEWSNET_admin_code": admin_code,
                    "ISO": "SS",
                    "lat": latitude,
                    "lon": longitude,
                    "month": period.month,
                    "fews_ipc": 2 + crisis,
                    "fews_ipc_crisis": crisis,
                    "date": period.to_timestamp().strftime("%Y-%m-%d"),
                }
            )
            rows.append(row)
    panel = pd.DataFrame(rows, columns=source_columns)
    panel.to_csv(path, index=False, lineterminator="\n")
    return panel


def _seed_snapshot(
    tmp_path: Path,
    store: RecordingLocalArtifactStore,
) -> tuple[str, str]:
    panel_path = tmp_path / "assembled_fewsnet.normalized.csv"
    audit_path = tmp_path / "panel_normalization_audit.json"
    boundaries_path = tmp_path / "admin_boundaries.parquet"
    admin_universe_path = tmp_path / "admin_universe.csv"
    panel = _write_panel(panel_path)
    latest_month = "2024-12"

    panel_file = _panel_file_payload(
        panel_path,
        rows=len(panel),
        columns=len(panel.columns),
    )
    audit = {
        "schema_version": "fewsnet-panel-normalization-v1",
        "normalization_version": "deduplicate-before-global-rolling-zscore-v1",
        "source_panel": dict(panel_file),
        "output_panel": dict(panel_file),
        "key_columns": ["FEWSNET_admin_code", "feature_month"],
        "sort_columns": ["FEWSNET_admin_code", "date", "source_row_number"],
        "comparison_excluded_columns": ["Tair_zscore", "Rainf_zscore"],
        "climate_derivation": {
            "Tair_f_tavg_mean": "Tair_zscore",
            "Rainf_f_tavg_mean": "Rainf_zscore",
            "rolling_order": "global_after_stable_admin_date_sort",
            "window": 12,
            "minimum_periods": 1,
            "grouping_column": "FEWSNET_admin_code",
            "std_ddof": 1,
        },
        "latest_feature_month": latest_month,
        "latest_label_month": latest_month,
        "duplicate_group_count": 0,
        "duplicate_row_count": 0,
        "removed_row_count": 0,
        "conflict_group_count": 0,
        "duplicate_groups": [],
    }
    audit_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    boundaries = gpd.GeoDataFrame(
        {"admin_code": ["0", "1"]},
        geometry=[Point(29.130297, 9.551002), Point(28.414507, 9.786447)],
        crs="EPSG:4326",
    )
    boundaries.to_parquet(boundaries_path, index=False)
    pd.DataFrame({"admin_code": ["0", "1"]}).to_csv(
        admin_universe_path,
        index=False,
        lineterminator="\n",
    )

    snapshot_root = "gs://bucket/inputs/snapshots/fewsnet-test"
    panel_ref = upload_file_immutable_or_verify(
        store,
        panel_path,
        f"{snapshot_root}/assembled_fewsnet.normalized.csv",
    )
    audit_ref = upload_file_immutable_or_verify(
        store,
        audit_path,
        f"{snapshot_root}/panel_normalization_audit.json",
    )
    boundaries_ref = upload_file_immutable_or_verify(
        store,
        boundaries_path,
        f"{snapshot_root}/admin_boundaries.parquet",
    )
    admin_universe_ref = upload_file_immutable_or_verify(
        store,
        admin_universe_path,
        f"{snapshot_root}/admin_universe.csv",
    )
    admin_code_mapping = {
        "panel": "FEWSNET_admin_code",
        "boundaries": "admin_code",
        "canonical": "admin_code",
    }
    identity = {
        "schema_version": "fewsnet-source-snapshot-v2",
        "panel_sha256": panel_ref.sha256,
        "normalization_audit_sha256": audit_ref.sha256,
        "normalization_version": audit["normalization_version"],
        "boundaries_sha256": boundaries_ref.sha256,
        "admin_universe_sha256": admin_universe_ref.sha256,
        "row_count": len(panel),
        "area_count": 2,
        "spatial_feature_count": 2,
        "crs": "EPSG:4326",
        "latest_feature_month": latest_month,
        "latest_label_month": latest_month,
        "admin_code_mapping": admin_code_mapping,
    }
    snapshot_content_sha256 = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    manifest = {
        "schema_version": "fewsnet-source-snapshot-v2",
        "snapshot_id": f"fewsnet-202412-{snapshot_content_sha256[:8]}",
        "created_at_utc": "2026-07-21T00:00:00Z",
        "snapshot_content_sha256": snapshot_content_sha256,
        "panel": panel_ref.__dict__,
        "normalization_audit": audit_ref.__dict__,
        "boundaries": boundaries_ref.__dict__,
        "admin_universe": admin_universe_ref.__dict__,
        "row_count": len(panel),
        "area_count": 2,
        "spatial_feature_count": 2,
        "crs": "EPSG:4326",
        "latest_feature_month": latest_month,
        "latest_label_month": latest_month,
        "source_identity": {
            "panel_bootstrap_path": str(panel_path),
            "boundaries_bootstrap_path": str(boundaries_path),
            "panel_source_type": "synthetic_normalized_csv",
            "boundaries_source_type": "synthetic_geoparquet",
        },
        "admin_code_mapping": admin_code_mapping,
    }
    validate_payload("source-snapshot", manifest)
    manifest_uri = f"{snapshot_root}/source_manifest.json"
    put_immutable_or_verify(
        store,
        manifest_uri,
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(),
    )
    return manifest_uri, snapshot_content_sha256


def _worker_config(snapshot_manifest_uri: str) -> TrainingWorkerConfig:
    return TrainingWorkerConfig(
        snapshot_manifest_uri=snapshot_manifest_uri,
        suite_version=SUITE_VERSION,
        run_root_uri=RUN_ROOT_URI,
        model_root_uri=MODEL_ROOT_URI,
        container_image_uri=IMAGE_URI,
        container_image_digest=IMAGE_DIGEST,
        source_git_commit=SOURCE_COMMIT,
    )


def test_training_worker_writes_three_immutable_packages_and_result_last(
    tmp_path,
    monkeypatch,
):
    store = RecordingLocalArtifactStore(tmp_path / "store")
    snapshot_manifest_uri, snapshot_content_sha256 = _seed_snapshot(
        tmp_path,
        store,
    )
    monkeypatch.setenv("FEWSNET_SOURCE_GIT_COMMIT", SOURCE_COMMIT)
    store.events.clear()

    result = run_training_worker(
        _worker_config(snapshot_manifest_uri),
        store=store,
    )

    assert list(result["packages"]) == ["0m", "6m", "12m"]
    for horizon_key in ("0m", "6m", "12m"):
        package = result["packages"][horizon_key]
        assert package["uri"] == f"{MODEL_ROOT_URI}/{horizon_key}"
        assert package["checksums"] == json.loads(
            store.read_text(f"{package['uri']}/checksums.json")
        )
        assert len(store.list(f"{package['uri']}/")) == 7

    run_report_uri = f"{RUN_ROOT_URI}/training_threshold_report.json"
    suite_report_uri = (
        f"gs://bucket/suites/{SUITE_VERSION}/training_threshold_report.json"
    )
    report_bytes = store.read_bytes(run_report_uri)
    assert report_bytes == store.read_bytes(suite_report_uri)
    validate_payload("training-report", json.loads(report_bytes))
    assert result["snapshot_content_sha256"] == snapshot_content_sha256
    assert result["training_threshold_report"] == {
        "run_uri": run_report_uri,
        "suite_uri": suite_report_uri,
        "sha256": hashlib.sha256(report_bytes).hexdigest(),
    }
    assert result["source_git_commit"] == SOURCE_COMMIT
    assert result["container_image_digest"] == IMAGE_DIGEST
    assert store.events[-1] == (
        "put_bytes",
        f"{RUN_ROOT_URI}/training_job_result.json",
    )
    assert json.loads(
        store.read_text(f"{RUN_ROOT_URI}/training_job_result.json")
    ) == result

    store.events.clear()
    assert run_training_worker(
        _worker_config(snapshot_manifest_uri),
        store=store,
    ) == result
    assert store.events[-1] == (
        "put_bytes",
        f"{RUN_ROOT_URI}/training_job_result.json",
    )


def test_training_worker_rejects_source_commit_that_differs_from_image(monkeypatch):
    monkeypatch.setenv("FEWSNET_SOURCE_GIT_COMMIT", "2" * 40)
    with pytest.raises(ValueError, match="FEWSNET_SOURCE_GIT_COMMIT"):
        run_training_worker(
            _worker_config("gs://bucket/missing/source_manifest.json"),
            store=LocalArtifactStore("/tmp/unused-fewsnet-training-store"),
        )


def _custom_job_config() -> TrainingCustomJobConfig:
    return TrainingCustomJobConfig(
        project_id="food-crisis-modeling",
        region="us-central1",
        run_id="run-001",
        job_id="fewsnet-train-run-001",
        snapshot_manifest_uri="gs://bucket/inputs/snapshots/snap/source_manifest.json",
        suite_version=SUITE_VERSION,
        run_root_uri=RUN_ROOT_URI,
        model_root_uri=MODEL_ROOT_URI,
        container_image_uri=IMAGE_URI,
        container_image_digest=IMAGE_DIGEST,
        source_git_commit=SOURCE_COMMIT,
        training_service_account=(
            "fewsnet-training@food-crisis-modeling.iam.gserviceaccount.com"
        ),
        training_machine_type="n2-highmem-8",
        training_timeout_seconds=21600,
    )


def test_training_custom_job_spec_is_one_digest_pinned_worker():
    config = _custom_job_config()
    request = build_training_custom_job_spec(config)
    worker_pools = request["job_spec"]["worker_pool_specs"]

    assert len(worker_pools) == 1
    assert worker_pools[0] == {
        "replica_count": 1,
        "machine_spec": {"machine_type": "n2-highmem-8"},
        "container_spec": {
            "image_uri": IMAGE_URI,
            "command": [
                "python3",
                "-m",
                "fewsnet_partitioned_rf_pipeline.cli.train",
            ],
            "args": [
                "--snapshot-manifest-uri",
                config.snapshot_manifest_uri,
                "--suite-version",
                SUITE_VERSION,
                "--run-root-uri",
                RUN_ROOT_URI,
                "--model-root-uri",
                MODEL_ROOT_URI,
                "--container-image-uri",
                IMAGE_URI,
                "--container-image-digest",
                IMAGE_DIGEST,
                "--source-git-commit",
                SOURCE_COMMIT,
            ],
            "env": [
                {"name": "PROJECT_ID", "value": "food-crisis-modeling"},
                {"name": "VERTEX_AI_REGION", "value": "us-central1"},
                {"name": "RUN_ID", "value": "run-001"},
                {"name": "SUITE_VERSION", "value": SUITE_VERSION},
                {"name": "TRAINING_OUTPUT_URI", "value": f"{RUN_ROOT_URI}/training"},
            ],
        },
    }
    assert request["job_spec"]["service_account"] == config.training_service_account
    assert request["job_spec"]["base_output_directory"] == {
        "output_uri_prefix": f"{RUN_ROOT_URI}/training"
    }
    assert request["job_spec"]["scheduling"] == {"timeout": "21600s"}


@pytest.mark.parametrize(
    "config",
    [
        replace(
            _custom_job_config(),
            container_image_uri="us-central1-docker.pkg.dev/project/repo/image:latest",
        ),
        replace(_custom_job_config(), container_image_digest="sha256:" + "b" * 64),
    ],
)
def test_training_custom_job_spec_rejects_unpinned_or_mismatched_images(config):
    with pytest.raises(ValueError, match="digest"):
        build_training_custom_job_spec(config)


class FakeTrainingBackend:
    def __init__(self, states):
        self.states = iter(states)
        self.events: list[tuple[str, object]] = []
        self.job_name = (
            "projects/food-crisis-modeling/locations/us-central1/"
            "customJobs/123"
        )

    def submit(self, request):
        self.events.append(("submit", request))
        return {"name": self.job_name, "state": "JOB_STATE_QUEUED"}

    def get(self, job_name):
        self.events.append(("get", job_name))
        return {"name": job_name, "state": next(self.states)}

    def cancel(self, job_name):
        self.events.append(("cancel", job_name))


class FakeCustomJobServiceClient:
    def __init__(
        self,
        config: TrainingCustomJobConfig,
        *,
        commit_then_raise: bool = False,
        zero_after_ambiguous: bool = False,
        preexisting_count: int = 0,
        mismatched: bool = False,
    ) -> None:
        self.config = config
        self.commit_then_raise = commit_then_raise
        self.zero_after_ambiguous = zero_after_ambiguous
        self.preexisting_count = preexisting_count
        self.mismatched = mismatched
        self.create_calls: list[dict[str, object]] = []
        self.list_calls: list[dict[str, object]] = []
        self.jobs: list[dict[str, object]] = []

    def _resource(
        self,
        operation_id: str,
        index: int,
        custom_job: dict[str, object] | None = None,
    ) -> dict[str, object]:
        if custom_job is None:
            custom_job = build_training_custom_job_spec(self.config)
            custom_job["labels"] = {
                **custom_job["labels"],
                "fewsnet_operation": operation_id,
            }
        resource = {
            "name": (
                "projects/food-crisis-modeling/locations/us-central1/"
                f"customJobs/{index}"
            ),
            "display_name": custom_job["display_name"],
            "job_spec": custom_job["job_spec"],
            "state": "JOB_STATE_QUEUED",
            "create_time": "2026-07-21T12:00:00Z",
            "start_time": None,
            "end_time": None,
            "update_time": "2026-07-21T12:00:00Z",
            "error": {},
            "labels": custom_job["labels"],
            "web_access_uris": {},
        }
        if self.mismatched:
            resource = json.loads(json.dumps(resource))
            resource["job_spec"]["service_account"] = (
                "other@food-crisis-modeling.iam.gserviceaccount.com"
            )
        return resource

    def list_custom_jobs(self, *, request):
        self.list_calls.append(dict(request))
        operation_id = str(request["filter"]).rsplit(
            "labels.fewsnet_operation=", 1
        )[1]
        if self.preexisting_count:
            return [
                self._resource(operation_id, index)
                for index in range(1, self.preexisting_count + 1)
            ]
        return list(self.jobs)

    def create_custom_job(self, *, request):
        self.create_calls.append(json.loads(json.dumps(request)))
        operation_id = request["custom_job"]["labels"]["fewsnet_operation"]
        resource = self._resource(
            operation_id,
            len(self.create_calls),
            custom_job=request["custom_job"],
        )
        if not self.zero_after_ambiguous:
            self.jobs.append(resource)
        if self.commit_then_raise or self.zero_after_ambiguous:
            raise ServiceUnavailable("lost Custom Job create response")
        return resource


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_submit_persists_normalized_request_and_resource_before_polling(tmp_path):
    config = _custom_job_config()
    store = RecordingLocalArtifactStore(tmp_path / "store")
    backend = FakeTrainingBackend(["JOB_STATE_RUNNING", "JOB_STATE_SUCCEEDED"])

    submitted = submit_and_persist_training_custom_job(
        config,
        backend=backend,
        store=store,
    )

    evidence_uri = f"{RUN_ROOT_URI}/training/custom_job.json"
    evidence = json.loads(store.read_text(evidence_uri))
    assert submitted == evidence["resource"]
    assert evidence["schema_version"] == "fewsnet-training-custom-job-v1"
    assert evidence["request"] == backend.events[0][1]
    assert backend.events == [("submit", evidence["request"])]

    clock = FakeClock()
    terminal = wait_for_training_custom_job(
        submitted["name"],
        backend=backend,
        training_timeout_seconds=21600,
        poll_interval_seconds=1,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    assert terminal["state"] == "JOB_STATE_SUCCEEDED"
    assert all(event[0] != "cancel" for event in backend.events)


def test_vertex_training_adapter_reconciles_commit_then_raise_without_duplicate(
    tmp_path,
):
    config = _custom_job_config()
    client = FakeCustomJobServiceClient(config, commit_then_raise=True)
    backend = _VertexTrainingBackend(client)
    store = RecordingLocalArtifactStore(tmp_path / "store")
    retries: list[int] = []

    submitted = retry_transient(
        lambda: submit_and_persist_training_custom_job(
            config,
            backend=backend,
            store=store,
        ),
        max_retries=1,
        on_retry=retries.append,
    )

    assert submitted["name"].endswith("/customJobs/1")
    assert len(client.create_calls) == 1
    assert len(client.list_calls) == 2
    assert retries == [1]
    evidence = json.loads(
        store.read_text(f"{RUN_ROOT_URI}/training/custom_job.json")
    )
    operation_id = evidence["request"]["custom_job"]["labels"][
        "fewsnet_operation"
    ]
    assert len(operation_id) == 63
    assert evidence["resource"] == submitted


def test_vertex_training_adapter_refuses_resubmit_after_ambiguous_zero_match(
    tmp_path,
):
    config = _custom_job_config()
    client = FakeCustomJobServiceClient(config, zero_after_ambiguous=True)
    backend = _VertexTrainingBackend(client)

    with pytest.raises(ValueError, match="no matching Custom Job"):
        retry_transient(
            lambda: submit_and_persist_training_custom_job(
                config,
                backend=backend,
                store=RecordingLocalArtifactStore(tmp_path / "store"),
            ),
            max_retries=1,
            on_retry=lambda _attempt: None,
        )

    assert len(client.create_calls) == 1
    assert len(client.list_calls) == 2


@pytest.mark.parametrize(
    ("preexisting_count", "mismatched", "message"),
    [
        (2, False, "multiple matching Custom Jobs"),
        (1, True, "does not match the submitted Custom Job request"),
    ],
)
def test_vertex_training_adapter_fails_closed_on_conflicting_matches(
    tmp_path,
    preexisting_count,
    mismatched,
    message,
):
    config = _custom_job_config()
    client = FakeCustomJobServiceClient(
        config,
        preexisting_count=preexisting_count,
        mismatched=mismatched,
    )

    with pytest.raises(ValueError, match=message):
        submit_and_persist_training_custom_job(
            config,
            backend=_VertexTrainingBackend(client),
            store=RecordingLocalArtifactStore(tmp_path / "store"),
        )

    assert client.create_calls == []


def test_wait_timeout_cancels_exact_job_then_waits_for_cancelled_terminal_state():
    backend = FakeTrainingBackend(
        [
            "JOB_STATE_QUEUED",
            "JOB_STATE_RUNNING",
            "JOB_STATE_CANCELLING",
            "JOB_STATE_CANCELLED",
        ]
    )
    clock = FakeClock()

    with pytest.raises(TrainingJobTimeoutError) as caught:
        wait_for_training_custom_job(
            backend.job_name,
            backend=backend,
            training_timeout_seconds=2,
            poll_interval_seconds=1,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )

    assert caught.value.resource["state"] == "JOB_STATE_CANCELLED"
    assert [event for event in backend.events if event[0] == "cancel"] == [
        ("cancel", backend.job_name)
    ]
    cancel_index = backend.events.index(("cancel", backend.job_name))
    assert any(
        event == ("get", backend.job_name)
        for event in backend.events[cancel_index + 1 :]
    )
