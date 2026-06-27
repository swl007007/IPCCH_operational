from __future__ import annotations

import argparse
import hashlib
import json
from io import StringIO
import time

import pandas as pd

from cloud.batch.evi_worker import run_fake_evi_worker
from cloud.common.forbidden_side_effects import scan_forbidden_side_effects
from cloud.common.manifest import validate_manifest
from cloud.common.object_store import GCSObjectStore
from cloud.common.object_store import ObjectStore
from cloud.common.object_refs import is_digest_pinned_image
from cloud.common.runtime_config import resolve_runtime_config
from cloud.orchestrator.assembly import write_monthly_assembly_artifacts
from cloud.orchestrator import batch_client as batch_jobs
from cloud.orchestrator import vertex_client as vertex_jobs
from cloud.orchestrator.base_input_validation import validate_base_input
from cloud.orchestrator.inference import run_inference_wrapper
from cloud.orchestrator.model_package import validate_model_package
from cloud.orchestrator.release import write_release
from cloud.orchestrator.roots import resolve_deployment_roots
from cloud.orchestrator.run_state import DuplicateRunError, RunState, RunStateManager


class OrchestrationPreflightError(RuntimeError):
    """Raised before run-prefix acquisition for preflight failures."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run IPCCH Cloud Run orchestrator")
    parser.add_argument("--feature-month", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--input-manifest-uri", required=True)
    parser.add_argument("--reference-sample-uri")
    parser.add_argument(
        "--release-mode",
        default="release_on_success",
        choices=["release_on_success"],
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    store = GCSObjectStore.from_default()
    manifest = validate_manifest(
        json.loads(store.read_text(args.input_manifest_uri)),
        feature_month=args.feature_month,
        run_id=args.run_id,
    )
    hooks = build_production_completion_hooks(manifest)
    result = run_cloud_orchestration(
        store=store,
        feature_month=args.feature_month,
        run_id=args.run_id,
        input_manifest_uri=args.input_manifest_uri,
        input_manifest=manifest,
        reference_sample_uri=args.reference_sample_uri,
        batch_client=_default_batch_client(),
        vertex_client=_default_vertex_client(
            manifest["deployment"]["vertex_ai_region"]
        ),
        **hooks,
    )
    release_manifest = result.get("release_manifest") or {}
    if release_manifest and release_manifest.get("status") != "current":
        return 1
    return 0


def start_orchestration(
    *,
    feature_month: str,
    run_id: str,
    input_manifest_uri: str,
    deployment: dict,
    container_image_digest: str,
    object_store_root_uri: str,
    run_root_uri: str | None = None,
    store: ObjectStore,
    waivers: list[dict] | None = None,
) -> dict:
    manager = RunStateManager(
        store, object_store_root_uri=object_store_root_uri, run_root_uri=run_root_uri
    )
    try:
        state = manager.acquire_run(
            feature_month=feature_month,
            run_id=run_id,
            input_manifest_uri=input_manifest_uri,
            deployment=deployment,
            container_image_digest=container_image_digest,
            waivers=waivers,
        )
    except DuplicateRunError as exc:
        raise OrchestrationPreflightError(f"duplicate run_id: {run_id}") from exc
    return json.loads(store.read_text(state.run_prefix_uri + "run_summary.json"))


def run_cloud_orchestration(
    *,
    store: ObjectStore,
    feature_month: str,
    run_id: str,
    input_manifest_uri: str,
    input_manifest: dict,
    reference_sample_uri: str | None = None,
    batch_client,
    vertex_client,
    batch_waiter=None,
    assembly_runner=None,
    vertex_waiter=None,
) -> dict:
    manifest = validate_manifest(
        input_manifest, feature_month=feature_month, run_id=run_id
    )
    deployment = manifest["deployment"]
    roots = resolve_deployment_roots(
        deployment, run_id=run_id, feature_month=feature_month
    )
    runtime = resolve_runtime_config(deployment)
    _validate_vertex_output_root(deployment, roots=roots)
    run_summary = start_orchestration(
        feature_month=feature_month,
        run_id=run_id,
        input_manifest_uri=input_manifest_uri,
        deployment=deployment,
        container_image_digest=deployment["vertex_ai_custom_job_container_digest"],
        object_store_root_uri=deployment["object_store_root_uri"],
        run_root_uri=roots["run_root_uri"],
        store=store,
        waivers=manifest.get("waivers", []),
    )
    run_prefix = run_summary["artifact_paths"]["run_prefix_uri"]
    manager = RunStateManager(
        store,
        object_store_root_uri=deployment["object_store_root_uri"],
        run_root_uri=roots["run_root_uri"],
    )
    state = RunState(
        feature_month=feature_month,
        run_id=run_id,
        run_prefix_uri=run_prefix,
        input_manifest_uri=input_manifest_uri,
        deployment=deployment,
        container_image_digest=deployment["vertex_ai_custom_job_container_digest"],
        waivers=manifest.get("waivers", []),
    )
    batch_parent = (
        f"projects/{deployment['project_id']}/locations/{deployment['region']}"
    )
    batch_config = batch_jobs.BatchJobConfig(
        job_name_prefix=deployment["cloud_batch_job_name_prefix"],
        image_uri=deployment["artifact_registry_image_uri"],
        service_account=deployment["cloud_batch_service_account"],
        run_id=run_id,
        feature_month=feature_month,
        worker_args=[
            "--feature-month",
            feature_month,
            "--run-id",
            run_id,
            "--run-root-uri",
            roots["run_root_uri"],
            "--gee-export-root-uri",
            roots["gee_export_root_uri"],
            "--evi-output-root-uri",
            roots["evi_output_root_uri"],
            "--logs-root-uri",
            roots["logs_root_uri"],
            "--input-manifest-uri",
            input_manifest_uri,
        ],
        runtime=runtime,
    )
    if reference_sample_uri:
        batch_config.worker_args.extend(
            ["--reference-sample-uri", reference_sample_uri]
        )
    try:
        batch_response = batch_jobs.submit_batch_job(
            batch_config, client=batch_client, parent=batch_parent
        )
    except Exception as exc:
        _raise_post_prefix_failure(
            manager, state, step_name="cloud_batch_submission", exc=exc
        )
    store.write_text(
        roots["batch_root_uri"] + "cloud_batch_job_manifest.json",
        json.dumps(
            {
                "status": "submitted",
                "request": batch_jobs.build_batch_job_spec(batch_config),
                "response": _json_safe_response(batch_response),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )

    completion_hooks = (batch_waiter, assembly_runner, vertex_waiter)
    if any(hook is not None for hook in completion_hooks):
        if not all(hook is not None for hook in completion_hooks):
            raise OrchestrationPreflightError(
                "batch_waiter, assembly_runner, and vertex_waiter must be provided together"
            )
        try:
            batch_result = batch_waiter(
                store=store,
                run_prefix_uri=run_prefix,
                feature_month=feature_month,
                run_id=run_id,
                response=_json_safe_response(batch_response),
            )
            _require_step_passed(batch_result, step_name="cloud_batch_evi")
        except Exception as exc:
            _raise_post_prefix_failure(
                manager, state, step_name="cloud_batch_evi", exc=exc
            )
        try:
            assembly_result = assembly_runner(
                store=store,
                run_prefix_uri=run_prefix,
                feature_month=feature_month,
                run_id=run_id,
            )
            _require_step_passed(assembly_result, step_name="monthly_assembly")
        except Exception as exc:
            _raise_post_prefix_failure(
                manager, state, step_name="monthly_assembly", exc=exc
            )
    try:
        model_package_evidence = _validate_model_package_from_manifest(
            store=store,
            manifest=manifest,
            base_input_uri=(
                roots["assembly_root_uri"]
                + f"ipcch_monthly_base_input_{feature_month.replace('-', '')}.csv"
                if all(hook is not None for hook in completion_hooks)
                else None
            ),
        )
    except Exception as exc:
        _raise_post_prefix_failure(manager, state, step_name="model_package", exc=exc)

    vertex_parent = f"projects/{deployment['project_id']}/locations/{deployment['vertex_ai_region']}"
    vertex_job_id = f"ipcch-{run_id}"
    vertex_job_resource_name = f"{vertex_parent}/customJobs/{vertex_job_id}"
    model_package_uri = model_package_evidence["model_package_uri"]
    model_version_or_checksum = _model_package_version_or_checksum(
        model_package_evidence
    )
    vertex_config = vertex_jobs.VertexJobConfig(
        project_id=deployment["project_id"],
        region=deployment["vertex_ai_region"],
        job_id=vertex_job_id,
        image_uri=deployment["vertex_ai_custom_job_container_image_uri"],
        image_digest=deployment["vertex_ai_custom_job_container_digest"],
        service_account=deployment["vertex_ai_custom_job_service_account"],
        staging_root_uri=deployment["vertex_ai_custom_job_staging_root_uri"],
        output_root_uri=deployment["vertex_ai_custom_job_output_root_uri"],
        args=[
            "--feature-month",
            feature_month,
            "--run-id",
            run_id,
            "--input-base-uri",
            roots["assembly_root_uri"]
            + f"ipcch_monthly_base_input_{feature_month.replace('-', '')}.csv",
            "--model-package-uri",
            model_package_uri,
            "--output-dir",
            roots["inference_root_uri"],
            "--container-image-digest",
            deployment["vertex_ai_custom_job_container_digest"],
            "--vertex-ai-job-id",
            vertex_job_id,
            "--vertex-ai-job-resource-name",
            vertex_job_resource_name,
            "--vertex-ai-project-id",
            deployment["project_id"],
            "--vertex-ai-region",
            deployment["vertex_ai_region"],
            "--vertex-ai-custom-job-container-image-uri",
            deployment["vertex_ai_custom_job_container_image_uri"],
            "--vertex-ai-custom-job-container-digest",
            deployment["vertex_ai_custom_job_container_digest"],
            "--model-version-or-checksum",
            model_version_or_checksum,
            "--vertex-ai-custom-job-timeout-seconds",
            str(runtime.vertex_ai_custom_job_timeout_seconds),
            "--max-retries",
            str(runtime.max_retries),
        ],
        runtime=runtime,
    )
    if reference_sample_uri:
        vertex_config.args.extend(["--reference-sample-uri", reference_sample_uri])
    try:
        vertex_response = vertex_jobs.submit_vertex_custom_job(
            vertex_config, client=vertex_client, parent=vertex_parent
        )
    except Exception as exc:
        _raise_post_prefix_failure(
            manager, state, step_name="vertex_ai_submission", exc=exc
        )
    store.write_text(
        roots["inference_root_uri"] + "vertex_ai_job_manifest.json",
        json.dumps(
            {
                "status": "submitted",
                "request": vertex_jobs.build_vertex_custom_job_spec(vertex_config),
                "response": _json_safe_response(vertex_response),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    if all(hook is not None for hook in completion_hooks):
        try:
            vertex_result = vertex_waiter(
                store=store,
                run_prefix_uri=run_prefix,
                feature_month=feature_month,
                run_id=run_id,
                response=_json_safe_response(vertex_response),
            )
            _require_step_passed(vertex_result, step_name="vertex_ai_inference")
            _reconcile_vertex_evidence_with_response(
                store=store,
                inference_prefix_uri=roots["inference_root_uri"],
                response=_json_safe_response(vertex_response),
            )
        except Exception as exc:
            _raise_post_prefix_failure(
                manager, state, step_name="vertex_ai_inference", exc=exc
            )

        findings = scan_forbidden_side_effects(
            observed_uris=store.list(run_prefix),
            allowed_prefixes=[run_prefix],
        )
        if findings:
            manager.write_terminal_summary(
                state,
                status="failed",
                hard_gates=[{"name": "forbidden_side_effects", "status": "failed"}],
                forbidden_side_effect_check={"findings": findings},
            )
            raise OrchestrationPreflightError("run produced forbidden side effects")

        release_root_uri = roots["release_root_uri"]
        release_manifest_uri = release_root_uri + "release_manifest.json"
        terminal_hard_gates = [
            {"name": "cloud_batch_evi", "status": "passed"},
            {"name": "monthly_assembly", "status": "passed"},
            {"name": "vertex_ai_inference", "status": "passed"},
            {"name": "forbidden_side_effects", "status": "passed"},
        ]
        terminal_summary = json.loads(store.read_text(run_prefix + "run_summary.json"))
        terminal_summary.update(
            {
                "status": "released",
                "hard_gates": terminal_hard_gates,
                "release_attempted": True,
                "released": True,
                "release_manifest_path": release_manifest_uri,
                "forbidden_side_effect_check": {
                    "status": "passed",
                    "findings": [],
                },
            }
        )
        try:
            release_manifest = write_release(
                store=store,
                feature_month=feature_month,
                run_id=run_id,
                run_prefix_uri=run_prefix,
                release_root_uri=release_root_uri,
                referenced_artifacts=batch_result.get("referenced_artifacts", []),
                staging_root_uri=roots["staging_root_uri"],
                source_roots=roots,
                input_manifest_uri=input_manifest_uri,
                container_image_digest=deployment[
                    "vertex_ai_custom_job_container_digest"
                ],
                model_package_reference={
                    "uri": model_package_evidence["model_package_uri"],
                    "model_package_id": model_package_evidence.get("model_package_id"),
                    **model_package_evidence["immutable_reference"],
                },
                validation_status={"base_input": "passed", "inference": "passed"},
                inference_status="passed",
                copied_artifact_contents={
                    "run_summary.json": json.dumps(
                        terminal_summary, indent=2, sort_keys=True
                    )
                    + "\n"
                },
            )
        except Exception as exc:
            _raise_post_prefix_failure(
                manager, state, step_name="release", exc=exc, status="release_failed"
            )
        released = release_manifest.get("status") == "current"
        manager.write_terminal_summary(
            state,
            status="released" if released else "release_conflict",
            hard_gates=terminal_hard_gates,
            release_attempted=True,
            released=released,
            release_manifest_path=release_manifest_uri,
            forbidden_side_effect_check={"status": "passed", "findings": []},
        )
        return {
            "run_summary": json.loads(store.read_text(run_prefix + "run_summary.json")),
            "batch_response": _json_safe_response(batch_response),
            "vertex_response": _json_safe_response(vertex_response),
            "release_manifest": release_manifest,
            "release_manifest_uri": release_manifest_uri,
        }
    return {
        "run_summary": json.loads(store.read_text(run_prefix + "run_summary.json")),
        "batch_response": _json_safe_response(batch_response),
        "vertex_response": _json_safe_response(vertex_response),
    }


def _json_safe_response(response) -> dict:
    if isinstance(response, dict):
        return response
    if hasattr(response, "name"):
        return {"name": response.name}
    return {"value": str(response)}


def _reconcile_vertex_evidence_with_response(
    *, store: ObjectStore, inference_prefix_uri: str, response: dict
) -> None:
    resource_name = response.get("name")
    if not resource_name:
        return
    for relative in ("vertex_ai_job_manifest.json", "inference_report.json"):
        uri = inference_prefix_uri + relative
        report = json.loads(store.read_text(uri))
        report["vertex_ai_job_resource_name"] = resource_name
        if relative == "vertex_ai_job_manifest.json":
            report["status"] = "passed"
        store.write_text(uri, json.dumps(report, indent=2, sort_keys=True) + "\n")


def _require_step_passed(result: dict, *, step_name: str) -> None:
    if result.get("status") not in {"passed", "passed_with_warnings"}:
        raise OrchestrationPreflightError(f"{step_name} failed")


def _raise_post_prefix_failure(
    manager: RunStateManager,
    state: RunState,
    *,
    step_name: str,
    exc: Exception,
    status: str = "failed",
) -> None:
    manager.write_terminal_summary(
        state,
        status=status,
        hard_gates=[{"name": step_name, "status": "failed"}],
        release_attempted=status == "release_failed",
        released=False,
        forbidden_side_effect_check={"status": "not_run", "findings": []},
    )
    raise OrchestrationPreflightError(f"{step_name} failed: {exc}") from exc


def _validate_model_package_from_manifest(
    *, store: ObjectStore, manifest: dict, base_input_uri: str | None = None
) -> dict:
    artifact = _manifest_artifact(manifest, "model_package")
    package_uri = artifact["uri"].rstrip("/")
    manifest_uri = package_uri + "/model_package_manifest.json"
    package_manifest = json.loads(store.read_text(manifest_uri))
    package = dict(artifact)
    package["manifest"] = package_manifest
    package["required_feature_columns"] = _load_model_feature_columns(
        store=store, package_uri=package_uri
    )
    base_input_columns = None
    if base_input_uri is not None:
        base_input_columns = list(
            pd.read_csv(StringIO(store.read_text(base_input_uri)), nrows=0).columns
        )
    return validate_model_package(
        package,
        expected_input_schema=artifact["schema_contract"],
        expected_output_schema="prediction-output-v1",
        base_input_columns=base_input_columns,
    )


def _load_model_feature_columns(*, store: ObjectStore, package_uri: str) -> list[str]:
    prefix = package_uri.rstrip("/") + "/"
    expected_scopes = ("0m", "6m", "12m")
    required: set[str] = set()
    missing = []
    for scope in expected_scopes:
        uri = prefix + f"scope_{scope}/feature_columns.json"
        try:
            raw_columns = json.loads(store.read_text(uri))
        except FileNotFoundError:
            missing.append(uri)
            continue
        columns = _parse_feature_columns(raw_columns, uri=uri)
        if not columns:
            raise OrchestrationPreflightError(f"feature_columns file is empty: {uri}")
        required.update(columns)
    if missing:
        raise OrchestrationPreflightError(
            f"missing required feature_columns files: {missing}"
        )
    return sorted(required)


def _parse_feature_columns(raw_columns, *, uri: str) -> list[str]:
    if isinstance(raw_columns, list):
        columns = raw_columns
    elif isinstance(raw_columns, dict) and isinstance(
        raw_columns.get("feature_columns"), list
    ):
        columns = raw_columns["feature_columns"]
    else:
        raise OrchestrationPreflightError(
            f"feature_columns file must be a list or object with feature_columns: {uri}"
        )
    return [str(column) for column in columns if str(column)]


def _model_package_version_or_checksum(model_package_evidence: dict) -> str:
    immutable = model_package_evidence.get("immutable_reference", {})
    for key in ("checksum", "generation", "version_id", "model_version"):
        if immutable.get(key):
            return str(immutable[key])
    return ""


def _validate_vertex_output_root(deployment: dict, *, roots: dict[str, str]) -> None:
    expected = roots["inference_root_uri"]
    observed = deployment["vertex_ai_custom_job_output_root_uri"]
    if not observed.endswith("/"):
        observed += "/"
    if observed != expected:
        raise OrchestrationPreflightError(
            f"Vertex output root must be {expected}; got {observed}"
        )


def build_production_completion_hooks(input_manifest: dict) -> dict:
    runtime = resolve_runtime_config(input_manifest["deployment"])

    def batch_waiter(*, store, run_prefix_uri, feature_month, run_id, response):
        yyyymm = feature_month.replace("-", "")
        roots = resolve_deployment_roots(
            input_manifest["deployment"], run_id=run_id, feature_month=feature_month
        )
        required = [
            roots["gee_export_root_uri"] + "gee_export_manifest.json",
            roots["evi_output_root_uri"] + "EVI_mean_extraction_results.csv",
            roots["evi_output_root_uri"] + "EVI_std_extraction_results.csv",
            roots["evi_output_root_uri"] + "EVI_mean_monthly_long.csv",
            roots["evi_output_root_uri"] + "EVI_std_monthly_long.csv",
            roots["evi_output_root_uri"] + "evi_extraction_manifest.json",
            roots["evi_output_root_uri"] + "evi_validation_report.json",
        ]
        _wait_for_objects(
            store,
            required,
            timeout_seconds=runtime.batch_job_timeout_seconds,
            poll_seconds=runtime.gee_poll_interval_seconds,
            failure_reports={
                "evi_worker_error": roots["evi_output_root_uri"]
                + "evi_worker_error.json",
                "gee_export_manifest": roots["gee_export_root_uri"]
                + "gee_export_manifest.json",
                "evi_extraction_manifest": roots["evi_output_root_uri"]
                + "evi_extraction_manifest.json",
                "evi_validation_report": roots["evi_output_root_uri"]
                + "evi_validation_report.json",
            },
        )
        gee_manifest = json.loads(store.read_text(required[0]))
        _require_report_status(
            gee_manifest, label="gee_export_manifest", allowed_statuses={"passed"}
        )
        _require_report_status(
            json.loads(
                store.read_text(
                    roots["evi_output_root_uri"] + "evi_extraction_manifest.json"
                )
            ),
            label="evi_extraction_manifest",
            allowed_statuses={"passed"},
        )
        _require_report_status(
            json.loads(
                store.read_text(
                    roots["evi_output_root_uri"] + "evi_validation_report.json"
                )
            ),
            label="evi_validation_report",
            allowed_statuses={"passed", "passed_with_warnings"},
        )
        referenced_artifacts = [
            {
                "name": "processed_evi_raster",
                "uri": gee_manifest["processed_raster_uri"],
                "generation": gee_manifest.get(
                    "processed_raster_generation_or_version"
                ),
                "checksum": gee_manifest.get("processed_raster_checksum"),
            },
            {
                "name": "evi_mean_wide",
                "uri": roots["evi_output_root_uri"] + "EVI_mean_extraction_results.csv",
                "checksum": _object_text_sha256(
                    store,
                    roots["evi_output_root_uri"] + "EVI_mean_extraction_results.csv",
                ),
            },
            {
                "name": "evi_std_wide",
                "uri": roots["evi_output_root_uri"] + "EVI_std_extraction_results.csv",
                "checksum": _object_text_sha256(
                    store,
                    roots["evi_output_root_uri"] + "EVI_std_extraction_results.csv",
                ),
            },
            {
                "name": "evi_mean_long",
                "uri": roots["evi_output_root_uri"] + "EVI_mean_monthly_long.csv",
                "checksum": _object_text_sha256(
                    store, roots["evi_output_root_uri"] + "EVI_mean_monthly_long.csv"
                ),
            },
            {
                "name": "evi_std_long",
                "uri": roots["evi_output_root_uri"] + "EVI_std_monthly_long.csv",
                "checksum": _object_text_sha256(
                    store, roots["evi_output_root_uri"] + "EVI_std_monthly_long.csv"
                ),
            },
        ]
        return {
            "status": "passed",
            "batch_response": response,
            "feature_month": feature_month,
            "yyyymm": yyyymm,
            "referenced_artifacts": referenced_artifacts,
        }

    def assembly_runner(*, store, run_prefix_uri, feature_month, run_id):
        roots = resolve_deployment_roots(
            input_manifest["deployment"], run_id=run_id, feature_month=feature_month
        )
        result = write_monthly_assembly_artifacts(
            store=store,
            feature_month=feature_month,
            run_id=run_id,
            output_prefix_uri=roots["assembly_root_uri"],
            scaffold_uri=_manifest_artifact(input_manifest, "scaffold")["uri"],
            source_panel_uri=_manifest_artifact(input_manifest, "source_panel")["uri"],
            fixed_slow_features_uri=_manifest_artifact(
                input_manifest, "fixed_slow_area_features"
            )["uri"],
            evi_mean_long_uri=roots["evi_output_root_uri"]
            + "EVI_mean_monthly_long.csv",
            evi_std_long_uri=roots["evi_output_root_uri"] + "EVI_std_monthly_long.csv",
        )
        base_input = pd.read_csv(StringIO(store.read_text(result["base_input_uri"])))
        scaffold = pd.read_csv(
            StringIO(
                store.read_text(_manifest_artifact(input_manifest, "scaffold")["uri"])
            )
        )
        validation_report = validate_base_input(
            base_input=base_input,
            scaffold=scaffold,
            feature_month=feature_month,
        )
        validation_report["run_id"] = run_id
        store.write_text(
            roots["qa_root_uri"] + "base_input_validation_report.json",
            json.dumps(validation_report, indent=2, sort_keys=True) + "\n",
        )
        return {"status": "passed", "assembly_result": result}

    def vertex_waiter(*, store, run_prefix_uri, feature_month, run_id, response):
        yyyymm = feature_month.replace("-", "")
        roots = resolve_deployment_roots(
            input_manifest["deployment"], run_id=run_id, feature_month=feature_month
        )
        required = [
            roots["inference_root_uri"]
            + f"ipcch_launch_{yyyymm}_scope_{scope}_predictions.csv"
            for scope in ("0m", "6m", "12m")
        ]
        required.append(roots["inference_root_uri"] + "vertex_ai_job_manifest.json")
        required.append(roots["inference_root_uri"] + "inference_report.json")
        _wait_for_objects(
            store,
            required,
            timeout_seconds=runtime.vertex_ai_custom_job_timeout_seconds,
            poll_seconds=runtime.gee_poll_interval_seconds,
            failure_reports={
                "vertex_ai_job_manifest": roots["inference_root_uri"]
                + "vertex_ai_job_manifest.json",
                "inference_report": roots["inference_root_uri"]
                + "inference_report.json",
                "inference_error": roots["inference_root_uri"] + "inference_error.json",
            },
        )
        _require_report_status(
            json.loads(
                store.read_text(
                    roots["inference_root_uri"] + "vertex_ai_job_manifest.json"
                )
            ),
            label="vertex_ai_job_manifest",
            allowed_statuses={"passed"},
        )
        _require_report_status(
            json.loads(
                store.read_text(roots["inference_root_uri"] + "inference_report.json")
            ),
            label="inference_report",
            allowed_statuses={"passed"},
        )
        return {"status": "passed", "vertex_response": response}

    return {
        "batch_waiter": batch_waiter,
        "assembly_runner": assembly_runner,
        "vertex_waiter": vertex_waiter,
    }


def _manifest_artifact(manifest: dict, artifact_type: str) -> dict:
    for artifact in manifest.get("artifacts", []):
        if artifact.get("artifact_type") == artifact_type:
            return artifact
    raise OrchestrationPreflightError(
        f"input manifest missing {artifact_type} artifact"
    )


def _wait_for_objects(
    store: ObjectStore,
    uris: list[str],
    *,
    timeout_seconds: int = 21600,
    poll_seconds: int = 60,
    failure_reports: dict[str, str] | None = None,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    missing = list(uris)
    while missing:
        _raise_if_failure_report_exists(store, failure_reports or {})
        next_missing = []
        for uri in missing:
            try:
                store.read_text(uri)
            except Exception as exc:
                if not _is_missing_object_error(exc):
                    raise OrchestrationPreflightError(
                        f"failed while waiting for required artifact {uri}: {exc}"
                    ) from exc
                next_missing.append(uri)
        if not next_missing:
            return
        if time.monotonic() >= deadline:
            raise OrchestrationPreflightError(
                f"timed out waiting for required artifacts: {next_missing}"
            )
        missing = next_missing
        time.sleep(poll_seconds)


def _raise_if_failure_report_exists(
    store: ObjectStore, failure_reports: dict[str, str]
) -> None:
    terminal_failed_job_statuses = {"FAILED", "CANCELLED", "CANCELED", "EXPIRED"}
    for label, uri in failure_reports.items():
        try:
            raw_report = store.read_text(uri)
        except Exception as exc:
            if _is_missing_object_error(exc):
                continue
            raise OrchestrationPreflightError(
                f"failed while checking failure report {uri}: {exc}"
            ) from exc
        try:
            report = json.loads(raw_report)
        except json.JSONDecodeError as exc:
            raise OrchestrationPreflightError(
                f"{label} failure report is not valid JSON: {uri}"
            ) from exc
        status = str(report.get("status") or "").lower()
        job_status = str(report.get("job_status") or "").upper()
        if status == "failed" or job_status in terminal_failed_job_statuses:
            reason = (
                report.get("error")
                or report.get("failure_reason")
                or report.get("message")
                or report.get("job_status")
                or "failed"
            )
            raise OrchestrationPreflightError(f"{label} failed: {reason}")


def _is_missing_object_error(exc: Exception) -> bool:
    return isinstance(exc, FileNotFoundError) or exc.__class__.__name__ == "NotFound"


def _require_report_status(
    report: dict, *, label: str, allowed_statuses: set[str]
) -> None:
    status = report.get("status")
    if status not in allowed_statuses:
        allowed = ", ".join(sorted(allowed_statuses))
        raise OrchestrationPreflightError(
            f"{label} status must be one of {allowed}; got {status!r}"
        )


def _object_text_sha256(store: ObjectStore, uri: str) -> str:
    return hashlib.sha256(store.read_text(uri).encode("utf-8")).hexdigest()


def _default_batch_client():
    from google.cloud import batch_v1

    return batch_v1.BatchServiceClient()


def _default_vertex_client(region: str):
    from google.cloud import aiplatform_v1

    return aiplatform_v1.JobServiceClient(
        client_options={"api_endpoint": f"{region}-aiplatform.googleapis.com"}
    )


def run_fake_cloud_e2e(
    *,
    store: ObjectStore,
    feature_month: str,
    run_id: str,
    input_manifest: dict,
    zones: list[dict],
) -> dict:
    _validate_fake_manifest(input_manifest, feature_month=feature_month, run_id=run_id)
    deployment = input_manifest["deployment"]
    object_store_root_uri = deployment["object_store_root_uri"]
    container_image_digest = deployment["vertex_ai_custom_job_container_digest"]
    manager = RunStateManager(store, object_store_root_uri=object_store_root_uri)
    input_manifest_uri = f"{object_store_root_uri}/input_manifest.json"
    store.write_text(
        input_manifest_uri, json.dumps(input_manifest, sort_keys=True) + "\n"
    )
    state = manager.acquire_run(
        feature_month=feature_month,
        run_id=run_id,
        input_manifest_uri=input_manifest_uri,
        deployment=deployment,
        container_image_digest=container_image_digest,
    )

    run_fake_evi_worker(
        store=store,
        feature_month=feature_month,
        run_id=run_id,
        run_prefix_uri=state.run_prefix_uri,
        zones=zones,
    )
    year, month = (int(part) for part in feature_month.split("-"))
    yyyymm = feature_month.replace("-", "")
    area_ids = [zone["area_id"] for zone in zones]
    scaffold_csv = pd.DataFrame(
        {"area_id": area_ids, "year": year, "month": month}
    ).to_csv(index=False)
    source_csv = pd.DataFrame(
        {"area_id": area_ids, "year": year, "month": month}
    ).to_csv(index=False)
    fixed_csv = pd.DataFrame({"area_id": area_ids}).to_csv(index=False)
    store.write_text(state.run_prefix_uri + "localized/scaffold.csv", scaffold_csv)
    store.write_text(state.run_prefix_uri + "localized/source_panel.csv", source_csv)
    store.write_text(
        state.run_prefix_uri + "localized/fixed_slow_features.csv", fixed_csv
    )
    assembly_result = write_monthly_assembly_artifacts(
        store=store,
        feature_month=feature_month,
        run_id=run_id,
        output_prefix_uri=state.run_prefix_uri + "assembly/",
        scaffold_uri=state.run_prefix_uri + "localized/scaffold.csv",
        source_panel_uri=state.run_prefix_uri + "localized/source_panel.csv",
        fixed_slow_features_uri=state.run_prefix_uri
        + "localized/fixed_slow_features.csv",
        evi_mean_long_uri=state.run_prefix_uri + "evi/EVI_mean_monthly_long.csv",
        evi_std_long_uri=state.run_prefix_uri + "evi/EVI_std_monthly_long.csv",
    )
    base_input = pd.read_csv(
        StringIO(store.read_text(assembly_result["base_input_uri"]))
    )
    scaffold = pd.read_csv(StringIO(scaffold_csv))
    validation_report = validate_base_input(
        base_input=base_input[["area_id", "year", "month"]],
        scaffold=scaffold,
        feature_month=feature_month,
    )
    store.write_text(
        state.run_prefix_uri + "qa/base_input_validation_report.json",
        json.dumps(validation_report, indent=2, sort_keys=True) + "\n",
    )
    run_inference_wrapper(
        store=store,
        feature_month=feature_month,
        run_id=run_id,
        base_input_uri=assembly_result["base_input_uri"],
        model_package_uri="gs://bucket/model/",
        output_prefix_uri=state.run_prefix_uri + "inference/",
        job_metadata={
            "vertex_ai_job_id": "fake-vertex-job",
            "vertex_ai_job_resource_name": "projects/test/locations/us/jobs/fake-vertex-job",
            "container_image_digest": container_image_digest,
        },
        allow_synthetic_predictions=True,
    )

    findings = scan_forbidden_side_effects(
        observed_uris=store.list(state.run_prefix_uri),
        allowed_prefixes=[state.run_prefix_uri],
    )
    if findings:
        manager.write_terminal_summary(
            state,
            status="failed",
            hard_gates=[{"name": "forbidden_side_effects", "status": "failed"}],
        )
        raise OrchestrationPreflightError("fake run produced forbidden side effects")

    release_root_uri = f"{object_store_root_uri}/released/{yyyymm}/"
    terminal_summary = json.loads(
        store.read_text(state.run_prefix_uri + "run_summary.json")
    )
    terminal_summary.update(
        {
            "status": "released",
            "hard_gates": [{"name": "fake_cloud_e2e", "status": "passed"}],
            "release_attempted": True,
            "released": True,
            "release_manifest_path": release_root_uri + "release_manifest.json",
        }
    )
    release_manifest = write_release(
        store=store,
        feature_month=feature_month,
        run_id=run_id,
        run_prefix_uri=state.run_prefix_uri,
        release_root_uri=release_root_uri,
        referenced_artifacts=[
            {
                "name": "processed_evi_raster",
                "uri": state.run_prefix_uri
                + f"gee_exports/MOD13A3_EVI_{year}_{month:02d}_processed.tif",
                "generation": "1",
            }
        ],
        input_manifest_uri=input_manifest_uri,
        container_image_digest=container_image_digest,
        model_package_reference={
            "uri": "gs://bucket/model/",
            "generation": "1",
            "model_package_id": "model",
        },
        validation_status={"base_input": "passed", "inference": "passed"},
        inference_status="passed",
        copied_artifact_contents={
            "run_summary.json": json.dumps(terminal_summary, indent=2, sort_keys=True)
            + "\n"
        },
    )
    release_manifest_uri = release_root_uri + "release_manifest.json"
    manager.write_terminal_summary(
        state,
        status="released",
        hard_gates=[{"name": "fake_cloud_e2e", "status": "passed"}],
        release_attempted=True,
        released=True,
        release_manifest_path=release_manifest_uri,
    )
    return {
        "run_summary": json.loads(
            store.read_text(state.run_prefix_uri + "run_summary.json")
        ),
        "release_manifest": release_manifest,
        "release_manifest_uri": release_manifest_uri,
    }


def _validate_fake_manifest(manifest: dict, *, feature_month: str, run_id: str) -> None:
    if manifest.get("feature_month") != feature_month:
        raise OrchestrationPreflightError("input manifest feature_month mismatch")
    if manifest.get("run_id") != run_id:
        raise OrchestrationPreflightError("input manifest run_id mismatch")
    deployment = manifest.get("deployment") or {}
    if not deployment.get("object_store_root_uri", "").startswith("gs://"):
        raise OrchestrationPreflightError(
            "input manifest object_store_root_uri must be gs://"
        )
    if not is_digest_pinned_image(deployment.get("artifact_registry_image_uri", "")):
        raise OrchestrationPreflightError("input manifest image must be digest pinned")
    if not deployment.get("vertex_ai_custom_job_container_digest"):
        raise OrchestrationPreflightError("input manifest image digest is required")


if __name__ == "__main__":
    raise SystemExit(main())
