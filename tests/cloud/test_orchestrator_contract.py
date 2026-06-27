import copy
import json
from pathlib import Path

import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.orchestrator import main


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "cloud"


class FakeBatchClient:
    def __init__(self):
        self.requests = []

    def create_job(self, request):
        self.requests.append(request)
        return {"name": f"{request['parent']}/jobs/{request['job_id']}"}


class FakeVertexClient:
    def __init__(self):
        self.requests = []

    def create_custom_job(self, request):
        self.requests.append(request)
        return {
            "name": f"{request['parent']}/customJobs/{request['custom_job']['display_name']}"
        }


def _valid_manifest(run_id="run-202604-valid"):
    manifest = json.loads(
        (FIXTURE_DIR / "input_manifest_202604_valid.json").read_text(encoding="utf-8")
    )
    manifest = copy.deepcopy(manifest)
    manifest["run_id"] = run_id
    deployment = manifest["deployment"]
    deployment["run_root_uri"] = f"gs://ipcch-test/monthly_e2e/runs/{run_id}/"
    deployment["staging_root_uri"] = f"gs://ipcch-test/monthly_e2e/staging/{run_id}/"
    deployment["release_root_uri"] = "gs://ipcch-test/monthly_e2e/released/202604/"
    deployment["gee_export_root_uri"] = (
        f"gs://ipcch-test/monthly_e2e/runs/{run_id}/gee_exports/"
    )
    deployment["logs_root_uri"] = f"gs://ipcch-test/monthly_e2e/runs/{run_id}/logs/"
    deployment["vertex_ai_custom_job_staging_root_uri"] = (
        f"gs://ipcch-test/monthly_e2e/vertex_staging/{run_id}/"
    )
    deployment["vertex_ai_custom_job_output_root_uri"] = (
        f"gs://ipcch-test/monthly_e2e/runs/{run_id}/inference/"
    )
    return manifest


def _seed_model_package_manifest(store, manifest):
    store.write_text(
        "gs://ipcch-test/monthly_e2e/input_manifest.json",
        json.dumps(manifest),
    )
    model_artifact = next(
        artifact
        for artifact in manifest["artifacts"]
        if artifact["artifact_type"] == "model_package"
    )
    model_prefix = model_artifact["uri"].rstrip("/") + "/"
    store.write_text(
        model_prefix + "model_package_manifest.json",
        json.dumps(_complete_model_package_manifest(model_artifact)),
    )
    for scope in ("0m", "6m", "12m"):
        store.write_text(
            model_prefix + f"scope_{scope}/feature_columns.json",
            json.dumps(["area_id", "year", "month"]),
        )


def _complete_model_package_manifest(model_artifact):
    return {
        "schema_version": "ipcch-launch-model-package-v1",
        "model_package_id": "launch_2026_04",
        "model_version": "2026.04.0",
        "created_at_utc": "2026-04-30T00:00:00Z",
        "source_git_commit": "a" * 40,
        "weights_files": ["scope_0m/phase2_worse_model.json"],
        "weights_checksums": {"scope_0m/phase2_worse_model.json": "b" * 64},
        "inference_entrypoint": "model_pipeline/run_operational_launch_inference.py",
        "inference_code_version": "a" * 40,
        "dependency_manifest": {"requirements": "requirements-cloud.txt"},
        "expected_input_schema": model_artifact["schema_contract"],
        "expected_output_schema": "prediction-output-v1",
        "local_validation_status": "passed",
        "local_validation_artifact_reference": {
            "uri": model_artifact["uri"].rstrip("/") + "/local_validation.json",
            "generation": "1",
        },
        "status": "passed",
    }


def test_orchestrator_acquires_run_and_returns_running_summary(tmp_path):
    store = LocalObjectStore(tmp_path)

    summary = main.start_orchestration(
        feature_month="2026-04",
        run_id="run-1",
        input_manifest_uri="gs://bucket/input_manifest.json",
        deployment={"provider": "gcp"},
        container_image_digest="sha256:" + "a" * 64,
        object_store_root_uri="gs://bucket/monthly",
        store=store,
    )

    assert summary["status"] == "running"
    assert (
        summary["artifact_paths"]["run_prefix_uri"] == "gs://bucket/monthly/runs/run-1/"
    )


def test_orchestrator_duplicate_run_id_fails_preflight(tmp_path):
    store = LocalObjectStore(tmp_path)
    kwargs = {
        "feature_month": "2026-04",
        "run_id": "run-1",
        "input_manifest_uri": "gs://bucket/input_manifest.json",
        "deployment": {"provider": "gcp"},
        "container_image_digest": "sha256:" + "a" * 64,
        "object_store_root_uri": "gs://bucket/monthly",
        "store": store,
    }
    main.start_orchestration(**kwargs)

    with pytest.raises(main.OrchestrationPreflightError, match="duplicate run_id"):
        main.start_orchestration(**kwargs)


def test_orchestrator_cli_parser_accepts_optional_reference_and_release_mode():
    args = main.parse_args(
        [
            "--feature-month",
            "2026-04",
            "--run-id",
            "run-1",
            "--input-manifest-uri",
            "gs://bucket/input_manifest.json",
            "--reference-sample-uri",
            "gs://bucket/reference.csv",
            "--release-mode",
            "release_on_success",
        ]
    )

    assert args.feature_month == "2026-04"
    assert args.run_id == "run-1"
    assert args.input_manifest_uri == "gs://bucket/input_manifest.json"
    assert args.reference_sample_uri == "gs://bucket/reference.csv"
    assert args.release_mode == "release_on_success"


def test_orchestrator_cli_defaults_to_release_on_success():
    args = main.parse_args(
        [
            "--feature-month",
            "2026-04",
            "--run-id",
            "run-1",
            "--input-manifest-uri",
            "gs://bucket/input_manifest.json",
        ]
    )

    assert args.release_mode == "release_on_success"


def test_orchestrator_cli_rejects_undefined_release_modes():
    with pytest.raises(SystemExit):
        main.parse_args(
            [
                "--feature-month",
                "2026-04",
                "--run-id",
                "run-1",
                "--input-manifest-uri",
                "gs://bucket/input_manifest.json",
                "--release-mode",
                "dry_run",
            ]
        )


def test_fake_orchestrator_sequence_writes_required_terminal_artifacts(tmp_path):
    store = LocalObjectStore(tmp_path)

    result = main.run_fake_cloud_e2e(
        store=store,
        feature_month="2026-04",
        run_id="run-sequence",
        input_manifest={
            "feature_month": "2026-04",
            "run_id": "run-sequence",
            "deployment": {
                "object_store_root_uri": "gs://bucket/monthly",
                "artifact_registry_image_uri": "us/pkg/ipcch@sha256:" + "a" * 64,
                "vertex_ai_custom_job_container_digest": "sha256:" + "a" * 64,
            },
        },
        zones=[{"area_id": "A", "values": [1000, 3000]}],
    )

    run_prefix = "gs://bucket/monthly/runs/run-sequence/"
    assert result["run_summary"]["status"] == "released"
    assert set(store.list(run_prefix)) >= {
        run_prefix + "qa/base_input_validation_report.json",
        run_prefix + "inference/vertex_ai_job_manifest.json",
        run_prefix + "inference/inference_report.json",
        run_prefix + "release/release_step_report.json",
        run_prefix + "run_summary.json",
    }


def test_cloud_orchestrator_dispatches_batch_and_vertex_clients_from_manifest(
    tmp_path,
):
    store = LocalObjectStore(tmp_path)
    batch = FakeBatchClient()
    vertex = FakeVertexClient()
    manifest = _valid_manifest(run_id="run-dispatch")
    _seed_model_package_manifest(store, manifest)

    result = main.run_cloud_orchestration(
        store=store,
        feature_month="2026-04",
        run_id="run-dispatch",
        input_manifest_uri="gs://ipcch-test/monthly_e2e/input_manifest.json",
        input_manifest=manifest,
        batch_client=batch,
        vertex_client=vertex,
    )

    run_prefix = "gs://ipcch-test/monthly_e2e/runs/run-dispatch/"
    assert result["run_summary"]["status"] == "running"
    assert batch.requests[0]["job_id"] == "ipcch-evi-run-dispatch"
    assert vertex.requests[0]["custom_job"]["display_name"] == "ipcch-run-dispatch"
    batch_args = batch.requests[0]["job"]["task_groups"][0]["task_spec"]["runnables"][
        0
    ]["container"]["commands"]
    assert batch_args[batch_args.index("--run-root-uri") + 1] == run_prefix
    assert "--run-prefix-uri" not in batch_args
    assert (
        batch_args[batch_args.index("--gee-export-root-uri") + 1]
        == run_prefix + "gee_exports/"
    )
    assert (
        batch_args[batch_args.index("--evi-output-root-uri") + 1] == run_prefix + "evi/"
    )
    assert batch_args[batch_args.index("--logs-root-uri") + 1] == run_prefix + "logs/"
    vertex_args = vertex.requests[0]["custom_job"]["job_spec"]["worker_pool_specs"][0][
        "container_spec"
    ]["args"]
    assert vertex_args[vertex_args.index("--input-base-uri") + 1] == (
        run_prefix + "assembly/ipcch_monthly_base_input_202604.csv"
    )
    assert vertex_args[vertex_args.index("--output-dir") + 1] == (
        run_prefix + "inference/"
    )
    assert "--base-input-uri" not in vertex_args
    assert "--output-prefix-uri" not in vertex_args
    assert "--vertex-ai-job-id" in vertex_args
    assert "--vertex-ai-job-resource-name" in vertex_args
    assert "--vertex-ai-project-id" in vertex_args
    assert "--vertex-ai-region" in vertex_args
    assert "--vertex-ai-custom-job-container-image-uri" in vertex_args
    assert "--vertex-ai-custom-job-container-digest" in vertex_args
    assert "--model-version-or-checksum" in vertex_args
    assert set(store.list(run_prefix)) >= {
        run_prefix + "batch/cloud_batch_job_manifest.json",
        run_prefix + "inference/vertex_ai_job_manifest.json",
    }


def test_cloud_orchestrator_copies_manifest_waivers_to_run_summary(tmp_path):
    store = LocalObjectStore(tmp_path)
    batch = FakeBatchClient()
    vertex = FakeVertexClient()
    manifest = _valid_manifest(run_id="run-waiver")
    waiver = {
        "artifact_id": "scaffold-202604",
        "waiver_type": "immutable_reference_exception",
        "reason": "operator-approved source-generation outage",
        "approved_by": "ops@example.org",
        "approved_at_utc": "2026-06-26T00:00:00Z",
        "expires_at_utc": "2026-06-27T00:00:00Z",
    }
    manifest["waivers"] = [waiver]
    _seed_model_package_manifest(store, manifest)

    result = main.run_cloud_orchestration(
        store=store,
        feature_month="2026-04",
        run_id="run-waiver",
        input_manifest_uri="gs://ipcch-test/monthly_e2e/input_manifest.json",
        input_manifest=manifest,
        batch_client=batch,
        vertex_client=vertex,
    )

    assert result["run_summary"]["waivers"] == [waiver]


def test_cloud_orchestrator_honors_deployment_root_overrides(tmp_path):
    store = LocalObjectStore(tmp_path)
    batch = FakeBatchClient()
    vertex = FakeVertexClient()
    manifest = _valid_manifest(run_id="run-custom-roots")
    deployment = manifest["deployment"]
    deployment["run_root_uri"] = "gs://ipcch-test/custom/run-root/"
    deployment["gee_export_root_uri"] = "gs://ipcch-test/custom/gee/"
    deployment["logs_root_uri"] = "gs://ipcch-test/custom/logs/"
    deployment["staging_root_uri"] = "gs://ipcch-test/custom/staging/"
    deployment["release_root_uri"] = "gs://ipcch-test/custom/released/"
    deployment["vertex_ai_custom_job_output_root_uri"] = (
        "gs://ipcch-test/custom/run-root/inference/"
    )
    _seed_model_package_manifest(store, manifest)

    result = main.run_cloud_orchestration(
        store=store,
        feature_month="2026-04",
        run_id="run-custom-roots",
        input_manifest_uri="gs://ipcch-test/monthly_e2e/input_manifest.json",
        input_manifest=manifest,
        batch_client=batch,
        vertex_client=vertex,
    )

    run_prefix = "gs://ipcch-test/custom/run-root/"
    batch_args = batch.requests[0]["job"]["task_groups"][0]["task_spec"]["runnables"][
        0
    ]["container"]["commands"]
    vertex_args = vertex.requests[0]["custom_job"]["job_spec"]["worker_pool_specs"][0][
        "container_spec"
    ]["args"]
    assert result["run_summary"]["artifact_paths"]["run_prefix_uri"] == run_prefix
    assert batch_args[batch_args.index("--run-root-uri") + 1] == run_prefix
    assert (
        batch_args[batch_args.index("--gee-export-root-uri") + 1]
        == "gs://ipcch-test/custom/gee/"
    )
    assert batch_args[batch_args.index("--logs-root-uri") + 1] == (
        "gs://ipcch-test/custom/logs/"
    )
    assert vertex_args[vertex_args.index("--output-dir") + 1] == (
        run_prefix + "inference/"
    )


def test_cloud_orchestrator_passes_reference_sample_uri_to_batch_and_vertex(
    tmp_path,
):
    store = LocalObjectStore(tmp_path)
    batch = FakeBatchClient()
    vertex = FakeVertexClient()
    manifest = _valid_manifest(run_id="run-reference")
    _seed_model_package_manifest(store, manifest)

    main.run_cloud_orchestration(
        store=store,
        feature_month="2026-04",
        run_id="run-reference",
        input_manifest_uri="gs://ipcch-test/monthly_e2e/input_manifest.json",
        input_manifest=manifest,
        reference_sample_uri="gs://ipcch-test/monthly_e2e/reference.csv",
        batch_client=batch,
        vertex_client=vertex,
    )

    batch_args = batch.requests[0]["job"]["task_groups"][0]["task_spec"]["runnables"][
        0
    ]["container"]["commands"]
    vertex_args = vertex.requests[0]["custom_job"]["job_spec"]["worker_pool_specs"][0][
        "container_spec"
    ]["args"]
    assert batch_args[batch_args.index("--reference-sample-uri") + 1] == (
        "gs://ipcch-test/monthly_e2e/reference.csv"
    )
    assert vertex_args[vertex_args.index("--reference-sample-uri") + 1] == (
        "gs://ipcch-test/monthly_e2e/reference.csv"
    )


def test_cloud_orchestrator_applies_manifest_runtime_overrides_to_submitted_jobs(
    tmp_path,
):
    store = LocalObjectStore(tmp_path)
    batch = FakeBatchClient()
    vertex = FakeVertexClient()
    manifest = _valid_manifest(run_id="run-runtime")
    manifest["deployment"]["batch_job_timeout_seconds"] = 123
    manifest["deployment"]["vertex_ai_custom_job_timeout_seconds"] = 456
    manifest["deployment"]["retry_policy"] = {"max_retries": 1}
    _seed_model_package_manifest(store, manifest)

    main.run_cloud_orchestration(
        store=store,
        feature_month="2026-04",
        run_id="run-runtime",
        input_manifest_uri="gs://ipcch-test/monthly_e2e/input_manifest.json",
        input_manifest=manifest,
        batch_client=batch,
        vertex_client=vertex,
    )

    batch_task_spec = batch.requests[0]["job"]["task_groups"][0]["task_spec"]
    vertex_job_spec = vertex.requests[0]["custom_job"]["job_spec"]
    vertex_args = vertex_job_spec["worker_pool_specs"][0]["container_spec"]["args"]
    assert batch_task_spec["max_run_duration"] == "123s"
    assert batch_task_spec["max_retry_count"] == 1
    assert vertex_job_spec["scheduling"]["timeout"] == "456s"
    assert (
        vertex_args[vertex_args.index("--vertex-ai-custom-job-timeout-seconds") + 1]
        == "456"
    )
    assert vertex_args[vertex_args.index("--max-retries") + 1] == "1"


def test_production_completion_hooks_use_runtime_timeouts_for_batch_and_vertex_waits(
    tmp_path, monkeypatch
):
    store = LocalObjectStore(tmp_path)
    manifest = _valid_manifest(run_id="run-wait-runtime")
    manifest["deployment"]["batch_job_timeout_seconds"] = 123
    manifest["deployment"]["vertex_ai_custom_job_timeout_seconds"] = 456
    manifest["deployment"]["gee_poll_interval_seconds"] = 7
    hooks = main.build_production_completion_hooks(manifest)
    run_prefix = "gs://ipcch-test/monthly_e2e/runs/run-wait-runtime/"
    wait_calls = []

    def fake_wait_for_objects(
        store, uris, *, timeout_seconds=21600, poll_seconds=60, failure_reports=None
    ):
        wait_calls.append((tuple(uris), timeout_seconds, poll_seconds))

    monkeypatch.setattr(main, "_wait_for_objects", fake_wait_for_objects)
    store.write_text(
        run_prefix + "gee_exports/gee_export_manifest.json",
        json.dumps(
            {
                "status": "passed",
                "processed_raster_uri": run_prefix
                + "gee_exports/MOD13A3_EVI_2026_04_processed.tif",
                "processed_raster_generation_or_version": "1",
            }
        ),
    )
    for relative in (
        "evi/EVI_mean_extraction_results.csv",
        "evi/EVI_std_extraction_results.csv",
        "evi/EVI_mean_monthly_long.csv",
        "evi/EVI_std_monthly_long.csv",
    ):
        store.write_text(run_prefix + relative, "area_id,value\nA,1\n")
    store.write_text(
        run_prefix + "evi/evi_extraction_manifest.json",
        json.dumps({"status": "passed"}),
    )
    store.write_text(
        run_prefix + "evi/evi_validation_report.json", json.dumps({"status": "passed"})
    )
    for scope in ("0m", "6m", "12m"):
        store.write_text(
            run_prefix + f"inference/ipcch_launch_202604_scope_{scope}_predictions.csv",
            "area_id,year,month\nA,2026,4\n",
        )
    store.write_text(
        run_prefix + "inference/vertex_ai_job_manifest.json",
        json.dumps({"status": "passed"}),
    )
    store.write_text(
        run_prefix + "inference/inference_report.json", json.dumps({"status": "passed"})
    )

    hooks["batch_waiter"](
        store=store,
        run_prefix_uri=run_prefix,
        feature_month="2026-04",
        run_id="run-wait-runtime",
        response={"name": "batch-job"},
    )
    hooks["vertex_waiter"](
        store=store,
        run_prefix_uri=run_prefix,
        feature_month="2026-04",
        run_id="run-wait-runtime",
        response={"name": "vertex-job"},
    )

    assert wait_calls[0][1:] == (123, 7)
    assert wait_calls[1][1:] == (456, 7)


def test_cloud_orchestrator_worker_error_sentinel_fails_run_without_timeout(tmp_path):
    store = LocalObjectStore(tmp_path)
    batch = FakeBatchClient()
    vertex = FakeVertexClient()
    manifest = _valid_manifest(run_id="run-worker-error")
    manifest["deployment"]["batch_job_timeout_seconds"] = 1
    manifest["deployment"]["gee_poll_interval_seconds"] = 1
    _seed_model_package_manifest(store, manifest)
    run_prefix = "gs://ipcch-test/monthly_e2e/runs/run-worker-error/"
    store.write_text(
        run_prefix + "evi/evi_worker_error.json",
        json.dumps({"status": "failed", "error": "earth engine export failed"}),
    )
    hooks = main.build_production_completion_hooks(manifest)

    with pytest.raises(main.OrchestrationPreflightError, match="evi_worker_error"):
        main.run_cloud_orchestration(
            store=store,
            feature_month="2026-04",
            run_id="run-worker-error",
            input_manifest_uri="gs://ipcch-test/monthly_e2e/input_manifest.json",
            input_manifest=manifest,
            batch_client=batch,
            vertex_client=vertex,
            **hooks,
        )

    run_summary = json.loads(store.read_text(run_prefix + "run_summary.json"))
    assert run_summary["status"] == "failed"
    assert run_summary["hard_gates"] == [
        {"name": "cloud_batch_evi", "status": "failed"}
    ]
    assert vertex.requests == []


def test_vertex_waiter_failed_job_manifest_fails_without_waiting_for_predictions(
    tmp_path,
):
    store = LocalObjectStore(tmp_path)
    manifest = _valid_manifest(run_id="run-vertex-failed")
    manifest["deployment"]["vertex_ai_custom_job_timeout_seconds"] = 1
    manifest["deployment"]["gee_poll_interval_seconds"] = 1
    hooks = main.build_production_completion_hooks(manifest)
    run_prefix = "gs://ipcch-test/monthly_e2e/runs/run-vertex-failed/"
    store.write_text(
        run_prefix + "inference/vertex_ai_job_manifest.json",
        json.dumps(
            {
                "status": "failed",
                "job_status": "FAILED",
                "failure_reason": "custom job container exited 1",
            }
        ),
    )

    with pytest.raises(
        main.OrchestrationPreflightError, match="vertex_ai_job_manifest"
    ):
        hooks["vertex_waiter"](
            store=store,
            run_prefix_uri=run_prefix,
            feature_month="2026-04",
            run_id="run-vertex-failed",
            response={"name": "vertex-job"},
        )


def test_wait_for_objects_fails_fast_on_non_missing_object_errors():
    class PermissionDeniedStore:
        def read_text(self, uri):
            raise PermissionError(f"permission denied: {uri}")

    with pytest.raises(main.OrchestrationPreflightError, match="permission denied"):
        main._wait_for_objects(
            PermissionDeniedStore(),
            ["gs://bucket/run/inference/inference_report.json"],
            timeout_seconds=0,
            poll_seconds=0,
        )


def test_cloud_orchestrator_rejects_vertex_output_root_mismatch_before_dispatch(
    tmp_path,
):
    store = LocalObjectStore(tmp_path)
    batch = FakeBatchClient()
    vertex = FakeVertexClient()
    manifest = _valid_manifest(run_id="run-output-root")
    manifest["deployment"]["vertex_ai_custom_job_output_root_uri"] = (
        "gs://ipcch-test/monthly_e2e/other/inference/"
    )

    with pytest.raises(main.OrchestrationPreflightError, match="Vertex output root"):
        main.run_cloud_orchestration(
            store=store,
            feature_month="2026-04",
            run_id="run-output-root",
            input_manifest_uri="gs://ipcch-test/monthly_e2e/input_manifest.json",
            input_manifest=manifest,
            batch_client=batch,
            vertex_client=vertex,
        )

    assert batch.requests == []
    assert vertex.requests == []


def test_production_assembly_hook_validates_admin_code_only_scaffold(tmp_path):
    store = LocalObjectStore(tmp_path)
    manifest = _valid_manifest(run_id="run-admin-code")
    artifact_uris = {
        artifact["artifact_type"]: artifact["uri"]
        for artifact in manifest["artifacts"]
        if "uri" in artifact
    }
    store.write_text(
        artifact_uris["scaffold"],
        "admin_code,year,month\nA,2026,4\nB,2026,4\n",
    )
    store.write_text(
        artifact_uris["source_panel"],
        "admin_code,year,month,price\nA,2026,4,1.0\nB,2026,4,2.0\n",
    )
    store.write_text(
        artifact_uris["fixed_slow_area_features"],
        "admin_code,admin_name\nA,alpha\nB,beta\n",
    )
    run_prefix = "gs://ipcch-test/monthly_e2e/runs/run-admin-code/"
    store.write_text(
        run_prefix + "evi/EVI_mean_monthly_long.csv",
        "area_id,year,month,EVI_mean\nA,2026,4,1.5\nB,2026,4,2.5\n",
    )
    store.write_text(
        run_prefix + "evi/EVI_std_monthly_long.csv",
        "area_id,year,month,EVI_std\nA,2026,4,0.1\nB,2026,4,0.2\n",
    )
    hooks = main.build_production_completion_hooks(manifest)

    result = hooks["assembly_runner"](
        store=store,
        run_prefix_uri=run_prefix,
        feature_month="2026-04",
        run_id="run-admin-code",
    )

    assert result["status"] == "passed"
    validation_report = json.loads(
        store.read_text(run_prefix + "qa/base_input_validation_report.json")
    )
    assert validation_report["status"] == "passed"


def test_orchestrator_main_cli_runs_production_completion_hooks_and_releases(
    tmp_path, monkeypatch
):
    store = LocalObjectStore(tmp_path)
    manifest = _valid_manifest(run_id="run-cli")
    manifest_uri = "gs://ipcch-test/monthly_e2e/input_manifest.json"
    store.write_text(manifest_uri, json.dumps(manifest))
    _seed_model_package_manifest(store, manifest)

    class FakeStoreFactory:
        @classmethod
        def from_default(cls):
            return store

    def fake_hook_factory(input_manifest):
        assert input_manifest["run_id"] == "run-cli"

        def batch_waiter(*, store, run_prefix_uri, feature_month, run_id, response):
            store.write_text(
                run_prefix_uri + "gee_exports/gee_export_manifest.json",
                json.dumps(
                    {
                        "status": "passed",
                        "feature_month": feature_month,
                        "run_id": run_id,
                        "processed_raster_uri": run_prefix_uri
                        + "gee_exports/MOD13A3_EVI_2026_04_processed.tif",
                        "processed_raster_generation_or_version": "1",
                    }
                ),
            )
            store.write_text(
                run_prefix_uri + "evi/evi_validation_report.json",
                json.dumps({"status": "passed", "feature_month": feature_month}),
            )
            store.write_text(
                run_prefix_uri + "evi/evi_extraction_manifest.json",
                json.dumps({"status": "passed", "feature_month": feature_month}),
            )
            return {
                "status": "passed",
                "referenced_artifacts": [
                    {
                        "name": "processed_evi_raster",
                        "uri": run_prefix_uri
                        + "gee_exports/MOD13A3_EVI_2026_04_processed.tif",
                        "generation": "1",
                    }
                ],
            }

        def assembly_runner(*, store, run_prefix_uri, feature_month, run_id):
            yyyymm = feature_month.replace("-", "")
            store.write_text(
                run_prefix_uri + f"assembly/ipcch_monthly_base_input_{yyyymm}.csv",
                "area_id,year,month\nA,2026,4\n",
            )
            store.write_text(
                run_prefix_uri
                + f"assembly/ipcch_monthly_base_input_{yyyymm}_summary.json",
                json.dumps({"status": "passed", "row_count": 1}),
            )
            store.write_text(
                run_prefix_uri + "qa/base_input_validation_report.json",
                json.dumps({"status": "passed", "schema_result": {"status": "passed"}}),
            )
            return {"status": "passed"}

        def vertex_waiter(*, store, run_prefix_uri, feature_month, run_id, response):
            yyyymm = feature_month.replace("-", "")
            for scope in ("0m", "6m", "12m"):
                scope_months = {"0m": 0, "6m": 6, "12m": 12}[scope]
                target_period = {"0m": "2026-04", "6m": "2026-10", "12m": "2027-04"}[
                    scope
                ]
                store.write_text(
                    run_prefix_uri
                    + f"inference/ipcch_launch_{yyyymm}_scope_{scope}_predictions.csv",
                    (
                        "area_id,year,month,admin_code,_row_id,phase2_worse_score,"
                        "phase2_worse_pred,phase3_worse_score,phase3_worse_pred,"
                        "phase4_worse_score,phase4_worse_pred,phase5_worse_score,"
                        "phase5_worse_pred,overall_phase_pred,feature_period,"
                        "target_period,scope_months,model_package_id,source_input\n"
                        f"A,2026,4,A,0,0.1,0,0.2,0,0.3,0,0.4,0,1,"
                        f"2026-04,{target_period},{scope_months},launch_2026_04,base\n"
                    ),
                )
            store.write_text(
                run_prefix_uri + "inference/inference_report.json",
                json.dumps(
                    {
                        "status": "passed",
                        "model_output_schema": {"status": "passed"},
                        "local_reference_comparison": {"status": "not_provided"},
                    }
                ),
            )
            return {"status": "passed"}

        return {
            "batch_waiter": batch_waiter,
            "assembly_runner": assembly_runner,
            "vertex_waiter": vertex_waiter,
        }

    monkeypatch.setattr(main, "GCSObjectStore", FakeStoreFactory)
    monkeypatch.setattr(main, "_default_batch_client", lambda: FakeBatchClient())
    monkeypatch.setattr(
        main, "_default_vertex_client", lambda region: FakeVertexClient()
    )
    monkeypatch.setattr(
        main, "build_production_completion_hooks", fake_hook_factory, raising=False
    )

    exit_code = main.main(
        [
            "--feature-month",
            "2026-04",
            "--run-id",
            "run-cli",
            "--input-manifest-uri",
            manifest_uri,
        ]
    )

    assert exit_code == 0
    release_manifest = json.loads(
        store.read_text(
            "gs://ipcch-test/monthly_e2e/released/202604/release_manifest.json"
        )
    )
    assert release_manifest["status"] == "current"


def test_orchestrator_main_cli_returns_nonzero_on_release_conflict(
    tmp_path, monkeypatch
):
    store = LocalObjectStore(tmp_path)
    manifest = _valid_manifest(run_id="run-cli-conflict")
    manifest_uri = "gs://ipcch-test/monthly_e2e/input_manifest.json"
    store.write_text(manifest_uri, json.dumps(manifest))

    class FakeStoreFactory:
        @classmethod
        def from_default(cls):
            return store

    monkeypatch.setattr(main, "GCSObjectStore", FakeStoreFactory)
    monkeypatch.setattr(main, "_default_batch_client", lambda: FakeBatchClient())
    monkeypatch.setattr(
        main, "_default_vertex_client", lambda region: FakeVertexClient()
    )
    monkeypatch.setattr(
        main,
        "build_production_completion_hooks",
        lambda input_manifest: {
            "batch_waiter": object(),
            "assembly_runner": object(),
            "vertex_waiter": object(),
        },
    )
    monkeypatch.setattr(
        main,
        "run_cloud_orchestration",
        lambda **kwargs: {"release_manifest": {"status": "release_conflict"}},
    )

    exit_code = main.main(
        [
            "--feature-month",
            "2026-04",
            "--run-id",
            "run-cli-conflict",
            "--input-manifest-uri",
            manifest_uri,
        ]
    )

    assert exit_code == 1


def test_cloud_orchestrator_completes_validation_release_and_terminal_summary(
    tmp_path,
):
    store = LocalObjectStore(tmp_path)
    manifest = _valid_manifest(run_id="run-release")
    _seed_model_package_manifest(store, manifest)
    batch = FakeBatchClient()
    vertex = FakeVertexClient()
    calls = []

    def batch_waiter(*, store, run_prefix_uri, feature_month, run_id, response):
        calls.append(("batch", response["name"]))
        store.write_text(
            run_prefix_uri + "gee_exports/gee_export_manifest.json",
            json.dumps(
                {
                    "status": "passed",
                    "feature_month": feature_month,
                    "run_id": run_id,
                    "processed_raster_uri": run_prefix_uri
                    + "gee_exports/MOD13A3_EVI_2026_04_processed.tif",
                    "processed_raster_generation_or_version": "1",
                }
            ),
        )
        store.write_text(
            run_prefix_uri + "evi/evi_validation_report.json",
            json.dumps({"status": "passed", "feature_month": feature_month}),
        )
        store.write_text(
            run_prefix_uri + "evi/evi_extraction_manifest.json",
            json.dumps({"status": "passed", "feature_month": feature_month}),
        )
        return {
            "status": "passed",
            "referenced_artifacts": [
                {
                    "name": "processed_evi_raster",
                    "uri": run_prefix_uri
                    + "gee_exports/MOD13A3_EVI_2026_04_processed.tif",
                    "generation": "1",
                }
            ],
        }

    def assembly_runner(*, store, run_prefix_uri, feature_month, run_id):
        calls.append(("assembly", run_id))
        yyyymm = feature_month.replace("-", "")
        store.write_text(
            run_prefix_uri + f"assembly/ipcch_monthly_base_input_{yyyymm}.csv",
            "area_id,year,month\nA,2026,4\n",
        )
        store.write_text(
            run_prefix_uri + f"assembly/ipcch_monthly_base_input_{yyyymm}_summary.json",
            json.dumps({"status": "passed", "row_count": 1}),
        )
        store.write_text(
            run_prefix_uri + "qa/base_input_validation_report.json",
            json.dumps({"status": "passed", "schema_result": {"status": "passed"}}),
        )
        return {"status": "passed"}

    def vertex_waiter(*, store, run_prefix_uri, feature_month, run_id, response):
        calls.append(("vertex", response["name"]))
        yyyymm = feature_month.replace("-", "")
        for scope in ("0m", "6m", "12m"):
            scope_months = {"0m": 0, "6m": 6, "12m": 12}[scope]
            target_period = {"0m": "2026-04", "6m": "2026-10", "12m": "2027-04"}[scope]
            store.write_text(
                run_prefix_uri
                + f"inference/ipcch_launch_{yyyymm}_scope_{scope}_predictions.csv",
                (
                    "area_id,year,month,admin_code,_row_id,phase2_worse_score,"
                    "phase2_worse_pred,phase3_worse_score,phase3_worse_pred,"
                    "phase4_worse_score,phase4_worse_pred,phase5_worse_score,"
                    "phase5_worse_pred,overall_phase_pred,feature_period,"
                    "target_period,scope_months,model_package_id,source_input\n"
                    f"A,2026,4,A,0,0.1,0,0.2,0,0.3,0,0.4,0,1,"
                    f"2026-04,{target_period},{scope_months},launch_2026_04,base\n"
                ),
            )
        store.write_text(
            run_prefix_uri + "inference/inference_report.json",
            json.dumps(
                {
                    "status": "passed",
                    "model_output_schema": {"status": "passed"},
                    "local_reference_comparison": {"status": "not_provided"},
                }
            ),
        )
        return {"status": "passed"}

    result = main.run_cloud_orchestration(
        store=store,
        feature_month="2026-04",
        run_id="run-release",
        input_manifest_uri="gs://ipcch-test/monthly_e2e/input_manifest.json",
        input_manifest=manifest,
        batch_client=batch,
        vertex_client=vertex,
        batch_waiter=batch_waiter,
        assembly_runner=assembly_runner,
        vertex_waiter=vertex_waiter,
    )

    run_prefix = "gs://ipcch-test/monthly_e2e/runs/run-release/"
    release_root = "gs://ipcch-test/monthly_e2e/released/202604/"
    assert result["run_summary"]["status"] == "released"
    assert (
        json.loads(store.read_text(run_prefix + "run_summary.json"))["status"]
        == "released"
    )
    assert (
        json.loads(store.read_text(release_root + "release_manifest.json"))["status"]
        == "current"
    )
    assert (
        json.loads(store.read_text(release_root + "runs/run-release/run_summary.json"))[
            "status"
        ]
        == "released"
    )
    assert calls == [
        (
            "batch",
            "projects/ipcch-test-project/locations/us-central1/jobs/ipcch-evi-run-release",
        ),
        ("assembly", "run-release"),
        (
            "vertex",
            "projects/ipcch-test-project/locations/us-central1/customJobs/ipcch-run-release",
        ),
    ]


def test_cloud_orchestrator_reconciles_vertex_manifest_with_actual_response_name(
    tmp_path,
):
    store = LocalObjectStore(tmp_path)
    manifest = _valid_manifest(run_id="run-vertex-name")
    _seed_model_package_manifest(store, manifest)
    batch = FakeBatchClient()

    class ServiceAssignedVertexClient:
        def __init__(self):
            self.requests = []

        def create_custom_job(self, request):
            self.requests.append(request)
            return {
                "name": (
                    request["parent"] + "/customJobs/service-assigned-vertex-resource"
                )
            }

    vertex = ServiceAssignedVertexClient()

    def batch_waiter(*, store, run_prefix_uri, feature_month, run_id, response):
        store.write_text(
            run_prefix_uri + "gee_exports/gee_export_manifest.json",
            json.dumps(
                {
                    "status": "passed",
                    "feature_month": feature_month,
                    "run_id": run_id,
                    "processed_raster_uri": run_prefix_uri
                    + "gee_exports/MOD13A3_EVI_2026_04_processed.tif",
                    "processed_raster_generation_or_version": "1",
                }
            ),
        )
        store.write_text(
            run_prefix_uri + "evi/evi_validation_report.json",
            json.dumps({"status": "passed", "feature_month": feature_month}),
        )
        store.write_text(
            run_prefix_uri + "evi/evi_extraction_manifest.json",
            json.dumps({"status": "passed", "feature_month": feature_month}),
        )
        return {
            "status": "passed",
            "referenced_artifacts": [
                {
                    "name": "processed_evi_raster",
                    "uri": run_prefix_uri
                    + "gee_exports/MOD13A3_EVI_2026_04_processed.tif",
                    "generation": "1",
                }
            ],
        }

    def assembly_runner(*, store, run_prefix_uri, feature_month, run_id):
        yyyymm = feature_month.replace("-", "")
        store.write_text(
            run_prefix_uri + f"assembly/ipcch_monthly_base_input_{yyyymm}.csv",
            "area_id,year,month\nA,2026,4\n",
        )
        store.write_text(
            run_prefix_uri + f"assembly/ipcch_monthly_base_input_{yyyymm}_summary.json",
            json.dumps({"status": "passed", "row_count": 1}),
        )
        store.write_text(
            run_prefix_uri + "qa/base_input_validation_report.json",
            json.dumps({"status": "passed", "schema_result": {"status": "passed"}}),
        )
        return {"status": "passed"}

    def vertex_waiter(*, store, run_prefix_uri, feature_month, run_id, response):
        yyyymm = feature_month.replace("-", "")
        for scope in ("0m", "6m", "12m"):
            scope_months = {"0m": 0, "6m": 6, "12m": 12}[scope]
            target_period = {"0m": "2026-04", "6m": "2026-10", "12m": "2027-04"}[scope]
            store.write_text(
                run_prefix_uri
                + f"inference/ipcch_launch_{yyyymm}_scope_{scope}_predictions.csv",
                (
                    "area_id,year,month,admin_code,_row_id,phase2_worse_score,"
                    "phase2_worse_pred,phase3_worse_score,phase3_worse_pred,"
                    "phase4_worse_score,phase4_worse_pred,phase5_worse_score,"
                    "phase5_worse_pred,overall_phase_pred,feature_period,"
                    "target_period,scope_months,model_package_id,source_input\n"
                    f"A,2026,4,A,0,0.1,0,0.2,0,0.3,0,0.4,0,1,"
                    f"2026-04,{target_period},{scope_months},launch_2026_04,base\n"
                ),
            )
        store.write_text(
            run_prefix_uri + "inference/vertex_ai_job_manifest.json",
            json.dumps(
                {
                    "status": "passed",
                    "vertex_ai_job_resource_name": "projects/p/locations/us-central1/customJobs/stale",
                    "model_output_schema": {"status": "passed"},
                    "local_reference_comparison": {"status": "not_provided"},
                }
            ),
        )
        store.write_text(
            run_prefix_uri + "inference/inference_report.json",
            json.dumps(
                {
                    "status": "passed",
                    "vertex_ai_job_resource_name": "projects/p/locations/us-central1/customJobs/stale",
                    "model_output_schema": {"status": "passed"},
                    "local_reference_comparison": {"status": "not_provided"},
                }
            ),
        )
        return {"status": "passed"}

    main.run_cloud_orchestration(
        store=store,
        feature_month="2026-04",
        run_id="run-vertex-name",
        input_manifest_uri="gs://ipcch-test/monthly_e2e/input_manifest.json",
        input_manifest=manifest,
        batch_client=batch,
        vertex_client=vertex,
        batch_waiter=batch_waiter,
        assembly_runner=assembly_runner,
        vertex_waiter=vertex_waiter,
    )

    run_prefix = "gs://ipcch-test/monthly_e2e/runs/run-vertex-name/"
    manifest_json = json.loads(
        store.read_text(run_prefix + "inference/vertex_ai_job_manifest.json")
    )
    report_json = json.loads(
        store.read_text(run_prefix + "inference/inference_report.json")
    )
    assert manifest_json["vertex_ai_job_resource_name"].endswith(
        "/customJobs/service-assigned-vertex-resource"
    )
    assert report_json["vertex_ai_job_resource_name"].endswith(
        "/customJobs/service-assigned-vertex-resource"
    )


def test_cloud_orchestrator_blocks_missing_model_package_manifest_after_prefix(
    tmp_path,
):
    store = LocalObjectStore(tmp_path)
    manifest = _valid_manifest(run_id="run-missing-model")

    def batch_waiter(*, store, run_prefix_uri, feature_month, run_id, response):
        return {"status": "passed", "referenced_artifacts": []}

    def assembly_runner(*, store, run_prefix_uri, feature_month, run_id):
        return {"status": "passed"}

    def vertex_waiter(*, store, run_prefix_uri, feature_month, run_id, response):
        return {"status": "passed"}

    with pytest.raises(main.OrchestrationPreflightError, match="model_package"):
        main.run_cloud_orchestration(
            store=store,
            feature_month="2026-04",
            run_id="run-missing-model",
            input_manifest_uri="gs://ipcch-test/monthly_e2e/input_manifest.json",
            input_manifest=manifest,
            batch_client=FakeBatchClient(),
            vertex_client=FakeVertexClient(),
            batch_waiter=batch_waiter,
            assembly_runner=assembly_runner,
            vertex_waiter=vertex_waiter,
        )

    run_summary = json.loads(
        store.read_text(
            "gs://ipcch-test/monthly_e2e/runs/run-missing-model/run_summary.json"
        )
    )
    assert run_summary["status"] == "failed"
    assert run_summary["hard_gates"] == [{"name": "model_package", "status": "failed"}]


def test_cloud_orchestrator_blocks_base_input_missing_model_feature_columns(
    tmp_path,
):
    store = LocalObjectStore(tmp_path)
    manifest = _valid_manifest(run_id="run-missing-feature")
    model_artifact = next(
        artifact
        for artifact in manifest["artifacts"]
        if artifact["artifact_type"] == "model_package"
    )
    model_prefix = model_artifact["uri"].rstrip("/") + "/"
    store.write_text(
        model_prefix + "model_package_manifest.json",
        json.dumps(_complete_model_package_manifest(model_artifact)),
    )
    for scope in ("0m", "6m", "12m"):
        store.write_text(
            model_prefix + f"scope_{scope}/feature_columns.json",
            json.dumps(["EVI_mean", "missing_model_feature"]),
        )

    def batch_waiter(*, store, run_prefix_uri, feature_month, run_id, response):
        return {"status": "passed", "referenced_artifacts": []}

    def assembly_runner(*, store, run_prefix_uri, feature_month, run_id):
        store.write_text(
            run_prefix_uri + "assembly/ipcch_monthly_base_input_202604.csv",
            "area_id,year,month,EVI_mean\nA,2026,4,1.0\n",
        )
        return {"status": "passed"}

    def vertex_waiter(*, store, run_prefix_uri, feature_month, run_id, response):
        return {"status": "passed"}

    vertex = FakeVertexClient()
    with pytest.raises(main.OrchestrationPreflightError, match="feature columns"):
        main.run_cloud_orchestration(
            store=store,
            feature_month="2026-04",
            run_id="run-missing-feature",
            input_manifest_uri="gs://ipcch-test/monthly_e2e/input_manifest.json",
            input_manifest=manifest,
            batch_client=FakeBatchClient(),
            vertex_client=vertex,
            batch_waiter=batch_waiter,
            assembly_runner=assembly_runner,
            vertex_waiter=vertex_waiter,
        )

    assert vertex.requests == []


def test_cloud_orchestrator_requires_all_scope_feature_column_files(tmp_path):
    store = LocalObjectStore(tmp_path)
    manifest = _valid_manifest(run_id="run-missing-feature-file")
    model_artifact = next(
        artifact
        for artifact in manifest["artifacts"]
        if artifact["artifact_type"] == "model_package"
    )
    model_prefix = model_artifact["uri"].rstrip("/") + "/"
    store.write_text(
        model_prefix + "model_package_manifest.json",
        json.dumps(_complete_model_package_manifest(model_artifact)),
    )
    store.write_text(
        model_prefix + "scope_0m/feature_columns.json", json.dumps(["EVI_mean"])
    )
    store.write_text(
        model_prefix + "scope_6m/feature_columns.json", json.dumps(["EVI_mean"])
    )
    base_input_uri = "gs://ipcch-test/monthly_e2e/runs/run-missing-feature-file/assembly/ipcch_monthly_base_input_202604.csv"
    store.write_text(base_input_uri, "area_id,year,month,EVI_mean\nA,2026,4,1.0\n")

    with pytest.raises(main.OrchestrationPreflightError, match="feature_columns"):
        main._validate_model_package_from_manifest(
            store=store,
            manifest=manifest,
            base_input_uri=base_input_uri,
        )


def test_cloud_orchestrator_accepts_dict_shaped_scope_feature_columns(tmp_path):
    store = LocalObjectStore(tmp_path)
    manifest = _valid_manifest(run_id="run-dict-features")
    model_artifact = next(
        artifact
        for artifact in manifest["artifacts"]
        if artifact["artifact_type"] == "model_package"
    )
    model_prefix = model_artifact["uri"].rstrip("/") + "/"
    store.write_text(
        model_prefix + "model_package_manifest.json",
        json.dumps(_complete_model_package_manifest(model_artifact)),
    )
    for scope in ("0m", "6m", "12m"):
        store.write_text(
            model_prefix + f"scope_{scope}/feature_columns.json",
            json.dumps({"feature_columns": ["EVI_mean"]}),
        )
    base_input_uri = "gs://ipcch-test/monthly_e2e/runs/run-dict-features/assembly/ipcch_monthly_base_input_202604.csv"
    store.write_text(base_input_uri, "area_id,year,month,EVI_mean\nA,2026,4,1.0\n")

    evidence = main._validate_model_package_from_manifest(
        store=store,
        manifest=manifest,
        base_input_uri=base_input_uri,
    )

    assert evidence["required_feature_columns"] == ["EVI_mean"]


def test_cloud_orchestrator_writes_failed_terminal_summary_after_prefix_failure(
    tmp_path,
):
    store = LocalObjectStore(tmp_path)
    manifest = _valid_manifest(run_id="run-failure")

    def batch_waiter(*, store, run_prefix_uri, feature_month, run_id, response):
        return {"status": "passed", "referenced_artifacts": []}

    def assembly_runner(*, store, run_prefix_uri, feature_month, run_id):
        raise RuntimeError("assembly exploded")

    def vertex_waiter(*, store, run_prefix_uri, feature_month, run_id, response):
        return {"status": "passed"}

    with pytest.raises(main.OrchestrationPreflightError, match="monthly_assembly"):
        main.run_cloud_orchestration(
            store=store,
            feature_month="2026-04",
            run_id="run-failure",
            input_manifest_uri="gs://ipcch-test/monthly_e2e/input_manifest.json",
            input_manifest=manifest,
            batch_client=FakeBatchClient(),
            vertex_client=FakeVertexClient(),
            batch_waiter=batch_waiter,
            assembly_runner=assembly_runner,
            vertex_waiter=vertex_waiter,
        )

    run_summary = json.loads(
        store.read_text("gs://ipcch-test/monthly_e2e/runs/run-failure/run_summary.json")
    )
    assert run_summary["status"] == "failed"
    assert run_summary["hard_gates"] == [
        {"name": "monthly_assembly", "status": "failed"}
    ]


def test_production_completion_hooks_fail_on_failed_report_status(tmp_path):
    store = LocalObjectStore(tmp_path)
    manifest = _valid_manifest(run_id="run-hooks")
    hooks = main.build_production_completion_hooks(manifest)
    run_prefix = "gs://ipcch-test/monthly_e2e/runs/run-hooks/"
    store.write_text(
        run_prefix + "gee_exports/gee_export_manifest.json",
        json.dumps(
            {
                "status": "passed",
                "processed_raster_uri": run_prefix
                + "gee_exports/MOD13A3_EVI_2026_04_processed.tif",
                "processed_raster_generation_or_version": "1",
            }
        ),
    )
    store.write_text(run_prefix + "evi/EVI_mean_extraction_results.csv", "x\n")
    store.write_text(run_prefix + "evi/EVI_std_extraction_results.csv", "x\n")
    store.write_text(run_prefix + "evi/EVI_mean_monthly_long.csv", "x\n")
    store.write_text(run_prefix + "evi/EVI_std_monthly_long.csv", "x\n")
    store.write_text(
        run_prefix + "evi/evi_extraction_manifest.json",
        json.dumps({"status": "failed"}),
    )
    store.write_text(
        run_prefix + "evi/evi_validation_report.json",
        json.dumps({"status": "passed"}),
    )

    with pytest.raises(main.OrchestrationPreflightError, match="evi_extraction"):
        hooks["batch_waiter"](
            store=store,
            run_prefix_uri=run_prefix,
            feature_month="2026-04",
            run_id="run-hooks",
            response={"name": "batch-job"},
        )


def test_production_completion_hooks_attach_checksums_to_evi_references(tmp_path):
    store = LocalObjectStore(tmp_path)
    manifest = _valid_manifest(run_id="run-hooks")
    hooks = main.build_production_completion_hooks(manifest)
    run_prefix = "gs://ipcch-test/monthly_e2e/runs/run-hooks/"
    store.write_text(
        run_prefix + "gee_exports/gee_export_manifest.json",
        json.dumps(
            {
                "status": "passed",
                "processed_raster_uri": run_prefix
                + "gee_exports/MOD13A3_EVI_2026_04_processed.tif",
                "processed_raster_generation_or_version": "1",
            }
        ),
    )
    for relative in (
        "evi/EVI_mean_extraction_results.csv",
        "evi/EVI_std_extraction_results.csv",
        "evi/EVI_mean_monthly_long.csv",
        "evi/EVI_std_monthly_long.csv",
    ):
        store.write_text(run_prefix + relative, "area_id,value\nA,1\n")
    store.write_text(
        run_prefix + "evi/evi_extraction_manifest.json",
        json.dumps({"status": "passed"}),
    )
    store.write_text(
        run_prefix + "evi/evi_validation_report.json",
        json.dumps({"status": "passed"}),
    )

    result = hooks["batch_waiter"](
        store=store,
        run_prefix_uri=run_prefix,
        feature_month="2026-04",
        run_id="run-hooks",
        response={"name": "batch-job"},
    )

    evi_refs = [
        ref for ref in result["referenced_artifacts"] if ref["name"].startswith("evi_")
    ]
    assert len(evi_refs) == 4
    assert all(ref.get("checksum") for ref in evi_refs)
