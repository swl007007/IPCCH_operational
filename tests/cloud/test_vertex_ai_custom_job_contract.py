import json

import pandas as pd
import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.common.runtime_config import RuntimeDefaults
from cloud.orchestrator import inference, model_package, vertex_client


class FakeVertexJobClient:
    def __init__(self):
        self.requests = []

    def create_custom_job(self, request):
        self.requests.append(request)
        return {
            "name": f"{request['parent']}/customJobs/{request['custom_job']['display_name']}"
        }


def _seed_model_package_files(
    store: LocalObjectStore, prefix: str = "gs://bucket/model/"
):
    for scope in ("0m", "6m", "12m"):
        scope_prefix = f"{prefix.rstrip('/')}/scope_{scope}/"
        store.write_text(scope_prefix + "feature_columns.json", '["EVI_mean"]\n')
        store.write_text(
            scope_prefix + "feature_contract.csv", "feature_name\nEVI_mean\n"
        )
        store.write_text(scope_prefix + "model_metadata.json", '{"model":"test"}\n')
        for target in (
            "phase2_worse",
            "phase3_worse",
            "phase4_worse",
            "phase5_worse",
        ):
            store.write_text(scope_prefix + f"{target}_model.json", "{}\n")


def _complete_model_package_manifest(**overrides):
    manifest = {
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
        "expected_input_schema": "model-input-forecast-v1",
        "expected_output_schema": "prediction-output-v1",
        "local_validation_status": "passed",
        "local_validation_artifact_reference": {
            "uri": "gs://bucket/model_packages/launch_2026_04/local_validation.json",
            "generation": "1",
        },
        "status": "passed",
    }
    manifest.update(overrides)
    return manifest


def test_inference_command_uses_no_map_overwrite_and_never_validate_only():
    command = inference.build_inference_command(
        base_input_path="/gcs/run/assembly/ipcch_monthly_base_input_202604.csv",
        model_package_path="/gcs/model",
        output_dir="/gcs/run/inference",
        feature_month="2026-04",
    )

    assert "--no-map" in command
    assert "--overwrite" in command
    assert "--validate-only" not in command


def test_prediction_validation_requires_three_scopes_and_adds_year_month():
    base_columns = {
        "area_id": ["A"],
        "admin_code": ["A"],
        "_row_id": [0],
        "phase2_worse_score": [0.1],
        "phase2_worse_pred": [0],
        "phase3_worse_score": [0.2],
        "phase3_worse_pred": [0],
        "phase4_worse_score": [0.3],
        "phase4_worse_pred": [0],
        "phase5_worse_score": [0.4],
        "phase5_worse_pred": [0],
        "overall_phase_pred": [1],
        "feature_period": ["2026-04"],
        "model_package_id": ["model"],
        "source_input": ["base"],
    }
    scope_months = {"0m": 0, "6m": 6, "12m": 12}
    target_periods = {"0m": "2026-04", "6m": "2026-10", "12m": "2027-04"}
    predictions = {
        scope: pd.DataFrame(
            {
                **base_columns,
                "target_period": [target_periods[scope]],
                "scope_months": [scope_months[scope]],
            }
        )
        for scope in ("0m", "6m", "12m")
    }

    enriched, report = inference.validate_prediction_outputs(
        predictions, feature_month="2026-04"
    )

    assert report["status"] == "passed"
    assert set(enriched) == {"0m", "6m", "12m"}
    assert enriched["0m"].loc[0, "year"] == 2026
    assert enriched["0m"].loc[0, "month"] == 4
    assert report["local_reference_comparison"]["status"] == "not_provided"


def test_prediction_validation_rejects_scope_months_mismatching_scope_file():
    predictions = {
        "0m": _prediction_frame(scope_months=0, target_period="2026-04"),
        "6m": _prediction_frame(scope_months=6, target_period="2026-10"),
        "12m": _prediction_frame(scope_months=6, target_period="2027-04"),
    }

    with pytest.raises(ValueError, match="scope_months"):
        inference.validate_prediction_outputs(predictions, feature_month="2026-04")


def test_prediction_validation_rejects_target_period_mismatching_scope():
    predictions = {
        "0m": _prediction_frame(scope_months=0, target_period="2026-04"),
        "6m": _prediction_frame(scope_months=6, target_period="2026-04"),
        "12m": _prediction_frame(scope_months=12, target_period="2027-04"),
    }

    with pytest.raises(ValueError, match="target_period"):
        inference.validate_prediction_outputs(predictions, feature_month="2026-04")


@pytest.mark.parametrize(
    ("mutator", "expected_error"),
    [
        (lambda frame: frame.assign(admin_code=["wrong"]), "admin_code"),
        (lambda frame: frame.assign(_row_id=[99]), "_row_id"),
        (lambda frame: frame.assign(phase2_worse_score=[float("inf")]), "finite"),
        (lambda frame: frame.assign(phase2_worse_pred=[2]), "phase2_worse_pred"),
        (lambda frame: frame.assign(overall_phase_pred=[9]), "overall_phase_pred"),
        (lambda frame: frame.assign(model_package_id=["wrong"]), "model_package_id"),
    ],
)
def test_prediction_validation_rejects_v1_hard_gate_violations(mutator, expected_error):
    predictions = {
        "0m": _prediction_frame(scope_months=0, target_period="2026-04"),
        "6m": _prediction_frame(scope_months=6, target_period="2026-10"),
        "12m": _prediction_frame(scope_months=12, target_period="2027-04"),
    }
    predictions["0m"] = mutator(predictions["0m"])
    base_input = pd.DataFrame(
        {"area_id": ["A"], "year": [2026], "month": [4], "admin_code": ["A"]}
    )

    with pytest.raises(ValueError, match=expected_error):
        inference.validate_prediction_outputs(
            predictions,
            feature_month="2026-04",
            base_input=base_input,
            expected_model_package_id="model",
        )


def test_prediction_validation_allows_missing_admin_code_as_advisory():
    predictions = {
        "0m": _prediction_frame(scope_months=0, target_period="2026-04").drop(
            columns=["admin_code"]
        ),
        "6m": _prediction_frame(scope_months=6, target_period="2026-10").drop(
            columns=["admin_code"]
        ),
        "12m": _prediction_frame(scope_months=12, target_period="2027-04").drop(
            columns=["admin_code"]
        ),
    }
    base_input = pd.DataFrame(
        {"area_id": ["A"], "year": [2026], "month": [4], "admin_code": ["A"]}
    )

    _, report = inference.validate_prediction_outputs(
        predictions,
        feature_month="2026-04",
        base_input=base_input,
        expected_model_package_id="model",
    )

    assert report["status"] == "passed"
    assert report["advisory_warnings"] == [
        {
            "column": "admin_code",
            "message": "prediction output omitted optional admin_code metadata",
        }
    ]


def test_prediction_validation_records_reference_comparison_evidence():
    predictions = {
        "0m": _prediction_frame(scope_months=0, target_period="2026-04"),
        "6m": _prediction_frame(scope_months=6, target_period="2026-10", score=0.6),
        "12m": _prediction_frame(scope_months=12, target_period="2027-04"),
    }
    reference_predictions = {
        "0m": _prediction_frame(scope_months=0, target_period="2026-04"),
        "6m": _prediction_frame(scope_months=6, target_period="2026-10", score=0.4),
        "12m": _prediction_frame(scope_months=12, target_period="2027-04"),
    }

    _, report = inference.validate_prediction_outputs(
        predictions,
        feature_month="2026-04",
        reference_predictions=reference_predictions,
    )

    comparison = report["local_reference_comparison"]
    assert comparison["status"] == "provided"
    assert comparison["matched_row_counts"] == {"0m": 1, "6m": 1, "12m": 1}
    assert comparison["advisory_differences"][0]["scope"] == "6m"
    assert comparison["hard_gate_failures"] == []


def test_prediction_validation_rejects_reference_missing_required_rows():
    predictions = {
        "0m": _prediction_frame(scope_months=0, target_period="2026-04"),
        "6m": _prediction_frame(scope_months=6, target_period="2026-10"),
        "12m": _prediction_frame(scope_months=12, target_period="2027-04"),
    }
    reference_predictions = dict(predictions)
    reference_predictions["12m"] = reference_predictions["12m"].iloc[0:0].copy()

    with pytest.raises(ValueError, match="reference"):
        inference.validate_prediction_outputs(
            predictions,
            feature_month="2026-04",
            reference_predictions=reference_predictions,
        )


def test_vertex_submitter_builds_custom_job_spec_with_same_digest_and_timeout():
    config = vertex_client.VertexJobConfig(
        project_id="ipcch-project",
        region="us-central1",
        job_id="ipcch-run-1",
        image_uri="us/pkg/ipcch@sha256:" + "a" * 64,
        image_digest="sha256:" + "a" * 64,
        service_account="vertex@project.iam.gserviceaccount.com",
        staging_root_uri="gs://bucket/vertex_staging/run-1/",
        output_root_uri="gs://bucket/runs/run-1/inference/",
        args=[
            "--feature-month",
            "2026-04",
            "--run-id",
            "run-1",
            "--input-base-uri",
            "gs://bucket/runs/run-1/assembly/base.csv",
            "--model-package-uri",
            "gs://bucket/model/",
            "--output-dir",
            "gs://bucket/runs/run-1/inference/",
        ],
    )

    spec = vertex_client.build_vertex_custom_job_spec(config)

    worker = spec["job_spec"]["worker_pool_specs"][0]
    container = worker["container_spec"]
    assert spec["display_name"] == "ipcch-run-1"
    assert container["image_uri"].endswith("@sha256:" + "a" * 64)
    assert container["args"] == [
        "--feature-month",
        "2026-04",
        "--run-id",
        "run-1",
        "--input-base-uri",
        "gs://bucket/runs/run-1/assembly/base.csv",
        "--model-package-uri",
        "gs://bucket/model/",
        "--output-dir",
        "gs://bucket/runs/run-1/inference/",
    ]
    assert "service_account" not in worker
    assert spec["job_spec"]["service_account"] == (
        "vertex@project.iam.gserviceaccount.com"
    )
    assert spec["job_spec"]["scheduling"]["timeout"] == "7200s"
    assert spec["job_spec"]["base_output_directory"]["output_uri_prefix"] == (
        "gs://bucket/runs/run-1/inference/"
    )
    env = {entry["name"]: entry["value"] for entry in container["env"]}
    assert env == {
        "PROJECT_ID": "ipcch-project",
        "VERTEX_AI_REGION": "us-central1",
        "RUN_ID": "run-1",
        "FEATURE_MONTH": "2026-04",
        "MODEL_PACKAGE_URI": "gs://bucket/model/",
        "INPUT_BASE_URI": "gs://bucket/runs/run-1/assembly/base.csv",
        "INFERENCE_OUTPUT_URI": "gs://bucket/runs/run-1/inference/",
        "IPCCH_VERTEX_OUTPUT_ROOT_URI": "gs://bucket/runs/run-1/inference/",
    }
    assert spec["labels"]["inference_mode"] == "vertex_ai_custom_job"


def test_vertex_submitter_rejects_digest_mismatch():
    config = vertex_client.VertexJobConfig(
        project_id="ipcch-project",
        region="us-central1",
        job_id="ipcch-run-1",
        image_uri="us/pkg/ipcch@sha256:" + "a" * 64,
        image_digest="sha256:" + "b" * 64,
        service_account="vertex@project.iam.gserviceaccount.com",
        staging_root_uri="gs://bucket/vertex_staging/run-1/",
        output_root_uri="gs://bucket/runs/run-1/inference/",
        args=[],
    )

    with pytest.raises(vertex_client.VertexJobConfigError, match="same image digest"):
        vertex_client.build_vertex_custom_job_spec(config)


def test_vertex_submitter_calls_custom_job_client_with_request():
    fake_client = FakeVertexJobClient()
    config = vertex_client.VertexJobConfig(
        project_id="ipcch-project",
        region="us-central1",
        job_id="ipcch-run-1",
        image_uri="us/pkg/ipcch@sha256:" + "a" * 64,
        image_digest="sha256:" + "a" * 64,
        service_account="vertex@project.iam.gserviceaccount.com",
        staging_root_uri="gs://bucket/vertex_staging/run-1/",
        output_root_uri="gs://bucket/runs/run-1/inference/",
        args=["--feature-month", "2026-04"],
    )

    response = vertex_client.submit_vertex_custom_job(
        config,
        client=fake_client,
        parent="projects/ipcch/locations/us-central1",
    )

    assert response == {
        "name": "projects/ipcch/locations/us-central1/customJobs/ipcch-run-1"
    }
    assert fake_client.requests == [
        {
            "parent": "projects/ipcch/locations/us-central1",
            "custom_job": vertex_client.build_vertex_custom_job_spec(config),
        }
    ]


def test_model_package_validation_requires_manifest_and_immutable_reference():
    package = {
        "uri": "gs://bucket/model_packages/launch_2026_04/",
        "manifest": _complete_model_package_manifest(),
        "checksum": "a" * 64,
        "checksum_algorithm": "sha256",
    }

    evidence = model_package.validate_model_package(
        package,
        expected_input_schema="model-input-forecast-v1",
        expected_output_schema="prediction-output-v1",
    )

    assert evidence["status"] == "passed"
    assert evidence["model_package_uri"] == "gs://bucket/model_packages/launch_2026_04/"


@pytest.mark.parametrize(
    "missing_field",
    [
        "schema_version",
        "model_package_id",
        "model_version",
        "created_at_utc",
        "source_git_commit",
        "weights_files",
        "weights_checksums",
        "inference_entrypoint",
        "inference_code_version",
        "dependency_manifest",
        "expected_input_schema",
        "expected_output_schema",
        "local_validation_status",
        "local_validation_artifact_reference",
        "status",
    ],
)
def test_model_package_validation_rejects_missing_contract_manifest_fields(
    missing_field,
):
    manifest = _complete_model_package_manifest()
    manifest.pop(missing_field)
    package = {
        "uri": "gs://bucket/model_packages/launch_2026_04/",
        "manifest": manifest,
        "checksum": "a" * 64,
        "checksum_algorithm": "sha256",
    }

    with pytest.raises(model_package.ModelPackageValidationError, match=missing_field):
        model_package.validate_model_package(
            package,
            expected_input_schema="model-input-forecast-v1",
            expected_output_schema="prediction-output-v1",
        )


def test_model_package_validation_rejects_missing_manifest_model_package_id():
    manifest = _complete_model_package_manifest()
    manifest.pop("model_package_id")
    package = {
        "uri": "gs://bucket/model_packages/launch_2026_04/",
        "manifest": manifest,
        "checksum": "a" * 64,
        "checksum_algorithm": "sha256",
    }

    with pytest.raises(
        model_package.ModelPackageValidationError, match="model_package_id"
    ):
        model_package.validate_model_package(
            package,
            expected_input_schema="model-input-forecast-v1",
            expected_output_schema="prediction-output-v1",
        )


def test_model_package_validation_rejects_missing_immutable_reference():
    with pytest.raises(model_package.ModelPackageValidationError, match="immutable"):
        model_package.validate_model_package(
            {"uri": "gs://bucket/model_packages/launch_2026_04/", "manifest": {}},
            expected_input_schema="model-input-forecast-v1",
            expected_output_schema="prediction-output-v1",
        )


def test_model_package_validation_rejects_non_contract_manifest_shape():
    package = {
        "uri": "gs://bucket/model_packages/launch_2026_04/",
        "manifest": _complete_model_package_manifest(expected_input_schema="wrong"),
        "checksum": "a" * 64,
        "checksum_algorithm": "sha256",
    }

    with pytest.raises(
        model_package.ModelPackageValidationError, match="expected_input_schema"
    ):
        model_package.validate_model_package(
            package,
            expected_input_schema="model-input-forecast-v1",
            expected_output_schema="prediction-output-v1",
        )


def test_model_package_validation_rejects_missing_required_feature_columns():
    package = {
        "uri": "gs://bucket/model_packages/launch_2026_04/",
        "manifest": _complete_model_package_manifest(),
        "checksum": "a" * 64,
        "checksum_algorithm": "sha256",
        "required_feature_columns": ["EVI_mean", "missing_feature"],
    }

    with pytest.raises(
        model_package.ModelPackageValidationError, match="feature columns"
    ):
        model_package.validate_model_package(
            package,
            expected_input_schema="model-input-forecast-v1",
            expected_output_schema="prediction-output-v1",
            base_input_columns=["area_id", "year", "month", "EVI_mean"],
        )


def test_inference_wrapper_writes_three_prediction_csvs_report_and_job_manifest(
    tmp_path,
):
    store = LocalObjectStore(tmp_path)
    store.write_text(
        "gs://bucket/run/assembly/base.csv", "area_id,year,month\nA,2026,4\n"
    )

    result = inference.run_inference_wrapper(
        store=store,
        feature_month="2026-04",
        run_id="run-1",
        base_input_uri="gs://bucket/run/assembly/base.csv",
        model_package_uri="gs://bucket/model/",
        output_prefix_uri="gs://bucket/run/inference/",
        job_metadata={
            "vertex_ai_job_id": "job-1",
            "vertex_ai_job_resource_name": "projects/p/locations/us/jobs/job-1",
            "vertex_ai_project_id": "p",
            "vertex_ai_region": "us-central1",
            "vertex_ai_custom_job_container_image_uri": "image@sha256:" + "a" * 64,
            "vertex_ai_custom_job_container_digest": "sha256:" + "a" * 64,
            "container_image_digest": "sha256:" + "a" * 64,
            "model_version_or_checksum": "generation:1",
        },
        allow_synthetic_predictions=True,
    )

    assert result["status"] == "passed"
    assert set(store.list("gs://bucket/run/inference/")) >= {
        "gs://bucket/run/inference/vertex_ai_job_manifest.json",
        "gs://bucket/run/inference/inference_report.json",
        "gs://bucket/run/inference/ipcch_launch_202604_scope_0m_predictions.csv",
        "gs://bucket/run/inference/ipcch_launch_202604_scope_6m_predictions.csv",
        "gs://bucket/run/inference/ipcch_launch_202604_scope_12m_predictions.csv",
    }


def test_inference_cli_accepts_execution_contract_argument_names():
    args = inference.parse_args(
        [
            "--feature-month",
            "2026-04",
            "--run-id",
            "run-1",
            "--input-base-uri",
            "gs://bucket/run/assembly/base.csv",
            "--model-package-uri",
            "gs://bucket/model/",
            "--output-dir",
            "gs://bucket/run/inference/",
            "--container-image-digest",
            "sha256:" + "a" * 64,
            "--vertex-ai-job-id",
            "job-1",
            "--vertex-ai-job-resource-name",
            "projects/p/locations/us-central1/customJobs/123",
            "--vertex-ai-project-id",
            "p",
            "--vertex-ai-region",
            "us-central1",
            "--vertex-ai-custom-job-container-image-uri",
            "image@sha256:" + "a" * 64,
            "--vertex-ai-custom-job-container-digest",
            "sha256:" + "a" * 64,
            "--model-version-or-checksum",
            "generation:1",
        ]
    )

    assert args.base_input_uri == "gs://bucket/run/assembly/base.csv"
    assert args.output_prefix_uri == "gs://bucket/run/inference/"


def test_inference_wrapper_reads_reference_predictions_from_uri(tmp_path):
    store = LocalObjectStore(tmp_path)
    store.write_text(
        "gs://bucket/run/assembly/base.csv",
        "area_id,year,month\nA,2026,4\n",
    )
    reference_header = (
        "area_id,year,month,admin_code,_row_id,phase2_worse_score,"
        "phase2_worse_pred,phase3_worse_score,phase3_worse_pred,"
        "phase4_worse_score,phase4_worse_pred,phase5_worse_score,"
        "phase5_worse_pred,overall_phase_pred,feature_period,target_period,"
        "scope_months,model_package_id,source_input\n"
    )
    reference_csv = reference_header + "".join(
        [
            "A,2026,4,A,0,0.0,0,0.0,0,0.0,0,0.0,0,1,2026-04,2026-04,0,model,base\n",
            "A,2026,4,A,0,0.0,0,0.0,0,0.0,0,0.0,0,1,2026-04,2026-10,6,model,base\n",
            "A,2026,4,A,0,0.0,0,0.0,0,0.0,0,0.0,0,1,2026-04,2027-04,12,model,base\n",
        ]
    )
    store.write_text("gs://bucket/reference/predictions.csv", reference_csv)

    result = inference.run_inference_wrapper(
        store=store,
        feature_month="2026-04",
        run_id="run-reference",
        base_input_uri="gs://bucket/run/assembly/base.csv",
        model_package_uri="gs://bucket/model/",
        output_prefix_uri="gs://bucket/run/inference/",
        job_metadata={
            "vertex_ai_job_id": "job-1",
            "vertex_ai_job_resource_name": "projects/p/locations/us/jobs/job-1",
            "vertex_ai_project_id": "p",
            "vertex_ai_region": "us-central1",
            "vertex_ai_custom_job_container_image_uri": "image@sha256:" + "a" * 64,
            "vertex_ai_custom_job_container_digest": "sha256:" + "a" * 64,
            "container_image_digest": "sha256:" + "a" * 64,
            "model_version_or_checksum": "generation:1",
        },
        reference_sample_uri="gs://bucket/reference/predictions.csv",
        allow_synthetic_predictions=True,
    )

    assert result["report"]["local_reference_comparison"]["status"] == "provided"


def test_inference_wrapper_runs_script_and_uploads_script_outputs(tmp_path):
    store = LocalObjectStore(tmp_path)
    store.write_text(
        "gs://bucket/run/assembly/base.csv",
        "area_id,year,month,admin_code,_row_id\nA,2026,4,A,0\n",
    )
    _seed_model_package_files(store)
    commands = []

    def command_runner(command, *, output_dir):
        commands.append(command)
        model_package_path = command[command.index("--model-package") + 1]
        assert (
            tmp_path
            / "workspace"
            / "model_package"
            / "scope_0m"
            / "feature_columns.json"
        ).exists()
        assert str(tmp_path / "workspace" / "model_package") == model_package_path
        header = (
            "area_id,year,month,admin_code,_row_id,phase2_worse_score,"
            "phase2_worse_pred,phase3_worse_score,phase3_worse_pred,"
            "phase4_worse_score,phase4_worse_pred,phase5_worse_score,"
            "phase5_worse_pred,overall_phase_pred,feature_period,target_period,"
            "scope_months,model_package_id,source_input\n"
        )
        target_periods = {"0m": "2026-04", "6m": "2026-10", "12m": "2027-04"}
        scope_months = {"0m": 0, "6m": 6, "12m": 12}
        for scope in ("0m", "6m", "12m"):
            (
                output_dir / f"ipcch_launch_202604_scope_{scope}_predictions.csv"
            ).write_text(
                header
                + "A,2026,4,A,0,0.1,0,0.2,0,0.3,0,0.4,0,1,"
                + f"2026-04,{target_periods[scope]},{scope_months[scope]},"
                + "model,base\n",
                encoding="utf-8",
            )
        return {"returncode": 0, "stdout": "ok", "stderr": ""}

    result = inference.run_inference_wrapper(
        store=store,
        feature_month="2026-04",
        run_id="run-script",
        base_input_uri="gs://bucket/run/assembly/base.csv",
        model_package_uri="gs://bucket/model/",
        output_prefix_uri="gs://bucket/run/inference/",
        job_metadata={
            "vertex_ai_job_id": "job-1",
            "vertex_ai_job_resource_name": "projects/p/locations/us/jobs/job-1",
            "vertex_ai_project_id": "p",
            "vertex_ai_region": "us-central1",
            "vertex_ai_custom_job_container_image_uri": "image@sha256:" + "a" * 64,
            "vertex_ai_custom_job_container_digest": "sha256:" + "a" * 64,
            "container_image_digest": "sha256:" + "a" * 64,
            "model_version_or_checksum": "generation:1",
        },
        command_runner=command_runner,
        workspace_root=tmp_path / "workspace",
    )

    assert result["status"] == "passed"
    assert commands
    assert "model_pipeline/run_operational_launch_inference.py" in commands[0]
    uploaded = store.read_text(
        "gs://bucket/run/inference/ipcch_launch_202604_scope_0m_predictions.csv"
    )
    assert "phase2_worse_score" in uploaded
    assert "prediction" not in uploaded.splitlines()[0]
    report = store.read_text("gs://bucket/run/inference/inference_report.json")
    assert "prediction_output_paths" in report
    assert "custom_job_command" in report
    manifest = store.read_text("gs://bucket/run/inference/vertex_ai_job_manifest.json")
    assert "vertex_ai_project_id" in manifest
    assert "model_version_or_checksum" in manifest


def test_inference_wrapper_uses_manifest_model_package_id_for_prediction_validation(
    tmp_path,
):
    store = LocalObjectStore(tmp_path)
    model_package_uri = "gs://bucket/model_packages/package_dir/"
    store.write_text(
        "gs://bucket/run/assembly/base.csv",
        "area_id,year,month,admin_code,_row_id\nA,2026,4,A,0\n",
    )
    _seed_model_package_files(store, prefix=model_package_uri)
    store.write_text(
        model_package_uri + "model_package_manifest.json",
        json.dumps(_complete_model_package_manifest()),
    )

    def command_runner(command, *, output_dir):
        header = (
            "area_id,year,month,admin_code,_row_id,phase2_worse_score,"
            "phase2_worse_pred,phase3_worse_score,phase3_worse_pred,"
            "phase4_worse_score,phase4_worse_pred,phase5_worse_score,"
            "phase5_worse_pred,overall_phase_pred,feature_period,target_period,"
            "scope_months,model_package_id,source_input\n"
        )
        target_periods = {"0m": "2026-04", "6m": "2026-10", "12m": "2027-04"}
        scope_months = {"0m": 0, "6m": 6, "12m": 12}
        for scope in ("0m", "6m", "12m"):
            (
                output_dir / f"ipcch_launch_202604_scope_{scope}_predictions.csv"
            ).write_text(
                header
                + "A,2026,4,A,0,0.1,0,0.2,0,0.3,0,0.4,0,1,"
                + f"2026-04,{target_periods[scope]},{scope_months[scope]},"
                + "launch_2026_04,base\n",
                encoding="utf-8",
            )
        return {"returncode": 0, "stdout": "ok", "stderr": ""}

    result = inference.run_inference_wrapper(
        store=store,
        feature_month="2026-04",
        run_id="run-manifest-id",
        base_input_uri="gs://bucket/run/assembly/base.csv",
        model_package_uri=model_package_uri,
        output_prefix_uri="gs://bucket/run/inference/",
        job_metadata={
            "vertex_ai_job_id": "job-1",
            "vertex_ai_job_resource_name": "projects/p/locations/us/jobs/job-1",
            "vertex_ai_project_id": "p",
            "vertex_ai_region": "us-central1",
            "vertex_ai_custom_job_container_image_uri": "image@sha256:" + "a" * 64,
            "vertex_ai_custom_job_container_digest": "sha256:" + "a" * 64,
            "container_image_digest": "sha256:" + "a" * 64,
            "model_version_or_checksum": "generation:1",
        },
        command_runner=command_runner,
        workspace_root=tmp_path / "workspace",
    )

    assert result["status"] == "passed"


def test_inference_wrapper_uses_default_command_runner_for_production_path(
    tmp_path, monkeypatch
):
    store = LocalObjectStore(tmp_path)
    store.write_text(
        "gs://bucket/run/assembly/base.csv",
        "area_id,year,month,admin_code,_row_id\nA,2026,4,A,0\n",
    )
    _seed_model_package_files(store)
    commands = []

    def default_runner(command, *, output_dir):
        commands.append(command)
        header = (
            "area_id,year,month,admin_code,_row_id,phase2_worse_score,"
            "phase2_worse_pred,phase3_worse_score,phase3_worse_pred,"
            "phase4_worse_score,phase4_worse_pred,phase5_worse_score,"
            "phase5_worse_pred,overall_phase_pred,feature_period,target_period,"
            "scope_months,model_package_id,source_input\n"
        )
        target_periods = {"0m": "2026-04", "6m": "2026-10", "12m": "2027-04"}
        scope_months = {"0m": 0, "6m": 6, "12m": 12}
        for scope in ("0m", "6m", "12m"):
            (
                output_dir / f"ipcch_launch_202604_scope_{scope}_predictions.csv"
            ).write_text(
                header
                + "A,2026,4,A,0,0.1,0,0.2,0,0.3,0,0.4,0,1,"
                + f"2026-04,{target_periods[scope]},{scope_months[scope]},"
                + "model,base\n",
                encoding="utf-8",
            )
        return {"returncode": 0, "stdout": "ok", "stderr": ""}

    monkeypatch.setattr(
        inference, "_default_command_runner", default_runner, raising=False
    )

    inference.run_inference_wrapper(
        store=store,
        feature_month="2026-04",
        run_id="run-default",
        base_input_uri="gs://bucket/run/assembly/base.csv",
        model_package_uri="gs://bucket/model/",
        output_prefix_uri="gs://bucket/run/inference/",
        job_metadata={
            "vertex_ai_job_id": "job-1",
            "vertex_ai_job_resource_name": "projects/p/locations/us/jobs/job-1",
            "vertex_ai_project_id": "p",
            "vertex_ai_region": "us-central1",
            "vertex_ai_custom_job_container_image_uri": "image@sha256:" + "a" * 64,
            "vertex_ai_custom_job_container_digest": "sha256:" + "a" * 64,
            "container_image_digest": "sha256:" + "a" * 64,
            "model_version_or_checksum": "generation:1",
        },
        workspace_root=tmp_path / "workspace",
    )

    assert commands
    uploaded = store.read_text(
        "gs://bucket/run/inference/ipcch_launch_202604_scope_0m_predictions.csv"
    )
    assert "phase2_worse_score" in uploaded


def test_inference_wrapper_writes_failure_evidence_when_command_fails(tmp_path):
    store = LocalObjectStore(tmp_path)
    store.write_text(
        "gs://bucket/run/assembly/base.csv",
        "area_id,year,month,admin_code,_row_id\nA,2026,4,A,0\n",
    )
    _seed_model_package_files(store)

    def failing_runner(command, *, output_dir):
        return {"returncode": 2, "stdout": "", "stderr": "model crashed"}

    with pytest.raises(RuntimeError, match="model crashed"):
        inference.run_inference_wrapper(
            store=store,
            feature_month="2026-04",
            run_id="run-failed-inference",
            base_input_uri="gs://bucket/run/assembly/base.csv",
            model_package_uri="gs://bucket/model/",
            output_prefix_uri="gs://bucket/run/inference/",
            job_metadata={
                "vertex_ai_job_id": "job-1",
                "vertex_ai_job_resource_name": "projects/p/locations/us/jobs/job-1",
                "vertex_ai_project_id": "p",
                "vertex_ai_region": "us-central1",
                "vertex_ai_custom_job_container_image_uri": "image@sha256:" + "a" * 64,
                "vertex_ai_custom_job_container_digest": "sha256:" + "a" * 64,
                "container_image_digest": "sha256:" + "a" * 64,
                "model_version_or_checksum": "generation:1",
            },
            command_runner=failing_runner,
            workspace_root=tmp_path / "workspace",
        )

    error = json.loads(
        store.read_text("gs://bucket/run/inference/inference_error.json")
    )
    job_manifest = json.loads(
        store.read_text("gs://bucket/run/inference/vertex_ai_job_manifest.json")
    )
    report = json.loads(
        store.read_text("gs://bucket/run/inference/inference_report.json")
    )
    assert error["status"] == "failed"
    assert error["error_message"] == "inference command failed: model crashed"
    assert job_manifest["status"] == "failed"
    assert job_manifest["job_status"] == "FAILED"
    assert report["status"] == "failed"


def test_inference_wrapper_records_effective_runtime_overrides(tmp_path):
    store = LocalObjectStore(tmp_path)
    store.write_text(
        "gs://bucket/run/assembly/base.csv",
        "area_id,year,month\nA,2026,4\n",
    )

    inference.run_inference_wrapper(
        store=store,
        feature_month="2026-04",
        run_id="run-runtime",
        base_input_uri="gs://bucket/run/assembly/base.csv",
        model_package_uri="gs://bucket/model/",
        output_prefix_uri="gs://bucket/run/inference/",
        job_metadata={
            "vertex_ai_job_id": "job-1",
            "vertex_ai_job_resource_name": "projects/p/locations/us/jobs/job-1",
            "vertex_ai_project_id": "p",
            "vertex_ai_region": "us-central1",
            "vertex_ai_custom_job_container_image_uri": "image@sha256:" + "a" * 64,
            "vertex_ai_custom_job_container_digest": "sha256:" + "a" * 64,
            "container_image_digest": "sha256:" + "a" * 64,
            "model_version_or_checksum": "generation:1",
        },
        runtime=RuntimeDefaults(
            vertex_ai_custom_job_timeout_seconds=456,
            max_retries=1,
        ),
        allow_synthetic_predictions=True,
    )

    report = json.loads(
        store.read_text("gs://bucket/run/inference/inference_report.json")
    )
    manifest = json.loads(
        store.read_text("gs://bucket/run/inference/vertex_ai_job_manifest.json")
    )
    assert report["vertex_ai_custom_job_timeout_seconds"] == 456
    assert report["retry_policy"] == {"max_retries": 1}
    assert manifest["vertex_ai_custom_job_timeout_seconds"] == 456
    assert manifest["retry_policy"] == {"max_retries": 1}


def _prediction_frame(
    *,
    scope_months,
    target_period: str = "2026-04",
    score: float = 0.1,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "area_id": ["A"],
            "year": [2026],
            "month": [4],
            "admin_code": ["A"],
            "_row_id": [0],
            "phase2_worse_score": [score],
            "phase2_worse_pred": [0],
            "phase3_worse_score": [0.2],
            "phase3_worse_pred": [0],
            "phase4_worse_score": [0.3],
            "phase4_worse_pred": [0],
            "phase5_worse_score": [0.4],
            "phase5_worse_pred": [0],
            "overall_phase_pred": [1],
            "feature_period": ["2026-04"],
            "target_period": [target_period],
            "scope_months": [scope_months],
            "model_package_id": ["model"],
            "source_input": ["base"],
        }
    )
