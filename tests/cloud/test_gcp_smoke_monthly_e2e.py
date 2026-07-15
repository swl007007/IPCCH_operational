import json
import os
import subprocess
from io import StringIO

import pandas as pd
import pytest

from cloud.common.object_store import GCSObjectStore, LocalObjectStore
from cloud.orchestrator.inference import _validate_prediction_scope_contract
from model_pipeline.ipcch_launch_runtime.population import (
    POPULATION_OUTPUT_COLUMNS,
    PopulationContractError,
    validate_population_contract,
)


ENRICHED_PREDICTION_COLUMNS = {
    "population_estimate",
    "population_reference_period",
    "population_imputation_method",
    "prediction_uncertainty",
    "decision_margin",
    "uncertainty_critical_boundary",
    "uncertainty_method",
}

RESOLVED_THRESHOLDS_BY_SCOPE = {
    scope: {
        "phase2_worse": 0.20,
        "phase3_worse": 0.20,
        "phase4_worse": 0.20,
        "phase5_worse": 0.20,
    }
    for scope in ("0m", "6m", "12m")
}

VALID_INFERENCE_REPORT = json.dumps(
    {
        "status": "passed",
        "feature_month": "2026-04",
        "resolved_thresholds_by_scope": RESOLVED_THRESHOLDS_BY_SCOPE,
    }
)

ENRICHED_PREDICTION_CSV = """area_id,year,month,_row_id,population_estimate,population_reference_period,population_imputation_method,phase2_worse_score,phase2_worse_pred,phase3_worse_score,phase3_worse_pred,phase4_worse_score,phase4_worse_pred,phase5_worse_score,phase5_worse_pred,overall_phase_pred,feature_period,target_period,scope_months,model_package_id,source_input,prediction_uncertainty,decision_margin,uncertainty_critical_boundary,uncertainty_method
A,2026,4,0,1000,2025-01,last_observation_carried_forward,0.21,0,0.8,0,0.8,0,0.8,0,1,2026-04,2026-04,0,model,base,high,0.01,phase2_worse,qualitative_threshold_margin_v1
"""

BASE_INPUT_CSV = """area_id,year,month,_row_id,population_estimate,population_reference_period,population_imputation_method
A,2026,4,0,1000,2025-01,last_observation_carried_forward
"""


def _prediction_fixture_csv(scope):
    frame = pd.read_csv(StringIO(ENRICHED_PREDICTION_CSV))
    scope_months = {"0m": 0, "6m": 6, "12m": 12}[scope]
    target_period = {"0m": "2026-04", "6m": "2026-10", "12m": "2027-04"}[scope]
    frame["scope_months"] = scope_months
    frame["target_period"] = target_period
    return frame.to_csv(index=False)


def _base_input_fixture_path():
    return (
        "gs://bucket/monthly/released/202604/runs/run-1/assembly/"
        "ipcch_monthly_base_input_202604.csv"
    )


def build_cloud_run_dispatch_command(
    *, job_name, region, feature_month, input_manifest_uri, run_id
):
    return [
        "gcloud",
        "run",
        "jobs",
        "execute",
        job_name,
        "--region",
        region,
        "--wait",
        "--args",
        f"--feature-month={feature_month},--run-id={run_id},--input-manifest-uri={input_manifest_uri}",
    ]


def validate_release_manifest_after_smoke(*, store, release_manifest_uri, run_id):
    manifest = json.loads(store.read_text(release_manifest_uri))
    assert manifest.get("status") == "current"
    assert manifest.get("accepted_run_id") == run_id
    assert manifest.get("prediction_output_paths")
    inference_report_reference = manifest.get("inference_report_reference") or {}
    inference_report = json.loads(store.read_text(inference_report_reference["uri"]))
    feature_month = inference_report.get("feature_month")
    thresholds_by_scope = inference_report.get("resolved_thresholds_by_scope")
    assert feature_month, "inference report must provide feature_month"
    assert isinstance(thresholds_by_scope, dict), (
        "inference report must provide resolved_thresholds_by_scope"
    )
    base_candidates = [
        artifact["uri"]
        for artifact in manifest.get("released_copied_artifacts", [])
        if "/assembly/" in artifact.get("uri", "")
        and artifact["uri"].endswith(".csv")
        and "_summary" not in artifact["uri"]
    ]
    assert base_candidates, "released manifest must include the base input CSV"
    base_path = base_candidates[0]
    base_frame = pd.read_csv(StringIO(store.read_text(base_path)))
    try:
        validate_population_contract(base_frame, feature_month=feature_month)
    except (PopulationContractError, KeyError, TypeError, ValueError) as exc:
        raise AssertionError(
            f"released base input {base_path} failed semantic validation: {exc}"
        ) from exc
    base_key = ["area_id", "year", "month"]
    base_population = base_frame[base_key + list(POPULATION_OUTPUT_COLUMNS)].copy()
    for path in manifest["prediction_output_paths"]:
        frame = pd.read_csv(StringIO(store.read_text(path)))
        assert ENRICHED_PREDICTION_COLUMNS <= set(frame.columns)
        scope = next(
            scope for scope in ("0m", "6m", "12m") if f"_scope_{scope}_" in path
        )
        assert scope in thresholds_by_scope
        try:
            _validate_prediction_scope_contract(
                frame,
                scope=scope,
                feature_month=feature_month,
                thresholds=thresholds_by_scope[scope],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AssertionError(
                f"prediction artifact {path} failed semantic validation: {exc}"
            ) from exc
        merged = frame[base_key + list(POPULATION_OUTPUT_COLUMNS)].merge(
            base_population,
            on=base_key,
            how="left",
            suffixes=("", "_base"),
        )
        assert len(merged) == len(frame), (
            f"prediction artifact {path} must align to the released base input"
        )
        assert merged["population_estimate_base"].notna().all(), (
            f"prediction artifact {path} contains an area absent from the released base input"
        )
        for column in POPULATION_OUTPUT_COLUMNS:
            if column == "population_estimate":
                matches = merged[column] == merged[f"{column}_base"]
            else:
                matches = merged[column].astype(str) == merged[f"{column}_base"].astype(str)
            assert matches.all(), (
                f"prediction artifact {path} {column} must match the released base input"
            )
    for key in (
        "base_input_validation_report_reference",
        "vertex_ai_job_manifest_reference",
        "inference_report_reference",
        "gee_export_manifest_reference",
    ):
        reference = manifest.get(key) or {}
        assert reference.get("uri"), f"missing {key}.uri"
        assert reference.get("checksum"), f"missing {key}.checksum"
        store.read_text(reference["uri"])
    assert manifest.get("evi_evidence_references"), "missing EVI evidence refs"
    for reference in manifest["evi_evidence_references"]:
        assert reference.get("uri")
        assert reference.get("checksum")
        store.read_text(reference["uri"])
    for artifact in manifest.get("released_copied_artifacts", []):
        store.read_text(artifact["uri"])
    run_summary_ref = next(
        artifact
        for artifact in manifest.get("released_copied_artifacts", [])
        if artifact["uri"].endswith("/run_summary.json")
    )
    run_summary = json.loads(store.read_text(run_summary_ref["uri"]))
    assert run_summary["status"] == "released"
    return manifest


def test_live_gcp_smoke_release_validator_rejects_conflict_run_summary(tmp_path):
    store = LocalObjectStore(tmp_path)
    manifest_uri = "gs://bucket/monthly/released/202604/release_manifest.json"
    prediction_path = (
        "gs://bucket/monthly/released/202604/runs/run-1/inference/"
        "ipcch_launch_202604_scope_0m_predictions.csv"
    )
    base_path = _base_input_fixture_path()
    store.write_text(prediction_path, ENRICHED_PREDICTION_CSV)
    store.write_text(base_path, BASE_INPUT_CSV)
    copied_path = (
        "gs://bucket/monthly/released/202604/runs/run-1/qa/"
        "base_input_validation_report.json"
    )
    store.write_text(copied_path, VALID_INFERENCE_REPORT)
    run_summary_path = "gs://bucket/monthly/released/202604/runs/run-1/run_summary.json"
    store.write_text(run_summary_path, '{"status":"release_conflict"}')
    store.write_text(
        manifest_uri,
        json.dumps(
            {
                "status": "current",
                "accepted_run_id": "run-1",
                "prediction_output_paths": [prediction_path],
                "base_input_validation_report_reference": {
                    "uri": copied_path,
                    "checksum": "a" * 64,
                },
                "vertex_ai_job_manifest_reference": {
                    "uri": copied_path,
                    "checksum": "a" * 64,
                },
                "inference_report_reference": {
                    "uri": copied_path,
                    "checksum": "a" * 64,
                },
                "gee_export_manifest_reference": {
                    "uri": copied_path,
                    "checksum": "a" * 64,
                },
                "evi_evidence_references": [{"uri": copied_path, "checksum": "a" * 64}],
                "released_copied_artifacts": [
                    {"uri": base_path, "checksum": "b" * 64},
                    {"uri": run_summary_path, "checksum": "b" * 64}
                ],
            }
        ),
    )

    with pytest.raises(AssertionError):
        validate_release_manifest_after_smoke(
            store=store,
            release_manifest_uri=manifest_uri,
            run_id="run-1",
        )


def test_live_gcp_smoke_command_uses_cloud_run_job_dispatch():
    command = build_cloud_run_dispatch_command(
        job_name="ipcch-monthly-e2e-orchestrator",
        region="us-central1",
        feature_month="2026-04",
        input_manifest_uri="gs://bucket/input_manifest.json",
        run_id="202604-smoke",
    )

    assert command[:4] == ["gcloud", "run", "jobs", "execute"]
    assert "--wait" in command
    assert "--args" in command
    assert "--input-manifest-uri=gs://bucket/input_manifest.json" in command[-1]


def test_live_gcp_smoke_release_artifact_validator_checks_current_manifest(tmp_path):
    store = LocalObjectStore(tmp_path)
    manifest_uri = "gs://bucket/monthly/released/202604/release_manifest.json"
    base_path = _base_input_fixture_path()
    store.write_text(base_path, BASE_INPUT_CSV)
    prediction_paths = [
        f"gs://bucket/monthly/released/202604/runs/run-1/inference/ipcch_launch_202604_scope_{scope}_predictions.csv"
        for scope in ("0m", "6m", "12m")
    ]
    for path in prediction_paths:
        scope = next(scope for scope in ("0m", "6m", "12m") if f"_scope_{scope}_" in path)
        store.write_text(path, _prediction_fixture_csv(scope))
    copied_paths = {
        "base_input_validation_report_reference": "gs://bucket/monthly/released/202604/runs/run-1/qa/base_input_validation_report.json",
        "vertex_ai_job_manifest_reference": "gs://bucket/monthly/released/202604/runs/run-1/inference/vertex_ai_job_manifest.json",
        "inference_report_reference": "gs://bucket/monthly/released/202604/runs/run-1/inference/inference_report.json",
        "gee_export_manifest_reference": "gs://bucket/monthly/released/202604/runs/run-1/gee_exports/gee_export_manifest.json",
    }
    for key, path in copied_paths.items():
        store.write_text(
            path,
            VALID_INFERENCE_REPORT if key == "inference_report_reference" else '{"status":"passed"}',
        )
    evi_refs = [
        "gs://bucket/monthly/released/202604/runs/run-1/evi/evi_validation_report.json",
        "gs://bucket/monthly/released/202604/runs/run-1/evi/evi_extraction_manifest.json",
    ]
    for path in evi_refs:
        store.write_text(path, '{"status":"passed"}')
    run_summary_path = "gs://bucket/monthly/released/202604/runs/run-1/run_summary.json"
    store.write_text(run_summary_path, '{"status":"released"}')
    store.write_text(
        manifest_uri,
        json.dumps(
            {
                "status": "current",
                "accepted_run_id": "run-1",
                "prediction_output_paths": prediction_paths,
                **{
                    key: {"uri": value, "checksum": "a" * 64}
                    for key, value in copied_paths.items()
                },
                "evi_evidence_references": [
                    {"uri": uri, "checksum": "b" * 64} for uri in evi_refs
                ],
                "released_copied_artifacts": [
                    {"uri": base_path, "checksum": "b" * 64},
                    {"uri": run_summary_path, "checksum": "c" * 64}
                ],
            }
        ),
    )

    manifest = validate_release_manifest_after_smoke(
        store=store,
        release_manifest_uri=manifest_uri,
        run_id="run-1",
    )

    assert manifest["status"] == "current"


def test_live_gcp_smoke_release_validator_rejects_semantically_invalid_enriched_csv(
    tmp_path,
):
    store = LocalObjectStore(tmp_path)
    manifest_uri = "gs://bucket/monthly/released/202604/release_manifest.json"
    base_path = _base_input_fixture_path()
    store.write_text(base_path, BASE_INPUT_CSV)
    prediction_path = (
        "gs://bucket/monthly/released/202604/runs/run-1/inference/"
        "ipcch_launch_202604_scope_0m_predictions.csv"
    )
    invalid_prediction = ENRICHED_PREDICTION_CSV.replace(
        ",high,0.01,phase2_worse,", ",low,0.01,phase2_worse,"
    )
    store.write_text(prediction_path, invalid_prediction)
    copied_path = (
        "gs://bucket/monthly/released/202604/runs/run-1/qa/"
        "base_input_validation_report.json"
    )
    inference_path = (
        "gs://bucket/monthly/released/202604/runs/run-1/inference/"
        "inference_report.json"
    )
    store.write_text(copied_path, '{"status":"passed"}')
    store.write_text(inference_path, VALID_INFERENCE_REPORT)
    run_summary_path = (
        "gs://bucket/monthly/released/202604/runs/run-1/run_summary.json"
    )
    store.write_text(run_summary_path, '{"status":"released"}')
    store.write_text(
        manifest_uri,
        json.dumps(
            {
                "status": "current",
                "accepted_run_id": "run-1",
                "prediction_output_paths": [prediction_path],
                "base_input_validation_report_reference": {
                    "uri": copied_path,
                    "checksum": "a" * 64,
                },
                "vertex_ai_job_manifest_reference": {
                    "uri": copied_path,
                    "checksum": "a" * 64,
                },
                "inference_report_reference": {
                    "uri": inference_path,
                    "checksum": "a" * 64,
                },
                "gee_export_manifest_reference": {
                    "uri": copied_path,
                    "checksum": "a" * 64,
                },
                "evi_evidence_references": [
                    {"uri": copied_path, "checksum": "a" * 64}
                ],
                "released_copied_artifacts": [
                    {"uri": base_path, "checksum": "b" * 64},
                    {"uri": run_summary_path, "checksum": "b" * 64}
                ],
            }
        ),
    )

    with pytest.raises(AssertionError, match="semantic validation"):
        validate_release_manifest_after_smoke(
            store=store,
            release_manifest_uri=manifest_uri,
            run_id="run-1",
        )


def test_live_gcp_smoke_release_validator_rejects_invalid_released_base_population(
    tmp_path,
):
    store = LocalObjectStore(tmp_path)
    manifest_uri = "gs://bucket/monthly/released/202604/release_manifest.json"
    prediction_path = (
        "gs://bucket/monthly/released/202604/runs/run-1/inference/"
        "ipcch_launch_202604_scope_0m_predictions.csv"
    )
    base_path = (
        "gs://bucket/monthly/released/202604/runs/run-1/assembly/"
        "ipcch_monthly_base_input_202604.csv"
    )
    store.write_text(prediction_path, ENRICHED_PREDICTION_CSV)
    store.write_text(
        base_path,
        BASE_INPUT_CSV.replace(
            "1000,2025-01,last_observation_carried_forward",
            "-1,2025-01,last_observation_carried_forward",
        ),
    )
    copied_path = (
        "gs://bucket/monthly/released/202604/runs/run-1/qa/"
        "base_input_validation_report.json"
    )
    inference_path = (
        "gs://bucket/monthly/released/202604/runs/run-1/inference/"
        "inference_report.json"
    )
    store.write_text(copied_path, '{"status":"passed"}')
    store.write_text(inference_path, VALID_INFERENCE_REPORT)
    run_summary_path = (
        "gs://bucket/monthly/released/202604/runs/run-1/run_summary.json"
    )
    store.write_text(run_summary_path, '{"status":"released"}')
    store.write_text(
        manifest_uri,
        json.dumps(
            {
                "status": "current",
                "accepted_run_id": "run-1",
                "prediction_output_paths": [prediction_path],
                "base_input_validation_report_reference": {
                    "uri": copied_path,
                    "checksum": "a" * 64,
                },
                "vertex_ai_job_manifest_reference": {
                    "uri": copied_path,
                    "checksum": "a" * 64,
                },
                "inference_report_reference": {
                    "uri": inference_path,
                    "checksum": "a" * 64,
                },
                "gee_export_manifest_reference": {
                    "uri": copied_path,
                    "checksum": "a" * 64,
                },
                "evi_evidence_references": [
                    {"uri": copied_path, "checksum": "a" * 64}
                ],
                "released_copied_artifacts": [
                    {"uri": base_path, "checksum": "b" * 64},
                    {"uri": run_summary_path, "checksum": "c" * 64},
                ],
            }
        ),
    )

    with pytest.raises(AssertionError, match="base input"):
        validate_release_manifest_after_smoke(
            store=store,
            release_manifest_uri=manifest_uri,
            run_id="run-1",
        )


def test_live_gcp_smoke_release_validator_rejects_legacy_prediction_schema(
    tmp_path,
):
    store = LocalObjectStore(tmp_path)
    manifest_uri = "gs://bucket/monthly/released/202604/release_manifest.json"
    base_path = _base_input_fixture_path()
    store.write_text(base_path, BASE_INPUT_CSV)
    prediction_path = (
        "gs://bucket/monthly/released/202604/runs/run-1/inference/"
        "ipcch_launch_202604_scope_0m_predictions.csv"
    )
    store.write_text(prediction_path, "area_id,year,month\nA,2026,4\n")
    copied_path = (
        "gs://bucket/monthly/released/202604/runs/run-1/qa/"
        "base_input_validation_report.json"
    )
    store.write_text(copied_path, VALID_INFERENCE_REPORT)
    run_summary_path = "gs://bucket/monthly/released/202604/runs/run-1/run_summary.json"
    store.write_text(run_summary_path, '{"status":"released"}')
    store.write_text(
        manifest_uri,
        json.dumps(
            {
                "status": "current",
                "accepted_run_id": "run-1",
                "prediction_output_paths": [prediction_path],
                "base_input_validation_report_reference": {
                    "uri": copied_path,
                    "checksum": "a" * 64,
                },
                "vertex_ai_job_manifest_reference": {
                    "uri": copied_path,
                    "checksum": "a" * 64,
                },
                "inference_report_reference": {
                    "uri": copied_path,
                    "checksum": "a" * 64,
                },
                "gee_export_manifest_reference": {
                    "uri": copied_path,
                    "checksum": "a" * 64,
                },
                "evi_evidence_references": [
                    {"uri": copied_path, "checksum": "a" * 64}
                ],
                "released_copied_artifacts": [
                    {"uri": base_path, "checksum": "b" * 64},
                    {"uri": run_summary_path, "checksum": "b" * 64}
                ],
            }
        ),
    )

    with pytest.raises(AssertionError):
        validate_release_manifest_after_smoke(
            store=store,
            release_manifest_uri=manifest_uri,
            run_id="run-1",
        )


@pytest.mark.skipif(
    not os.environ.get("IPCCH_GCP_SMOKE_ENABLED"),
    reason="set IPCCH_GCP_SMOKE_ENABLED and deployment-specific GCP env vars to run live smoke",
)
def test_gated_live_gcp_monthly_e2e_smoke_is_explicitly_configured():
    required = [
        "IPCCH_GCP_PROJECT_ID",
        "IPCCH_GCP_REGION",
        "IPCCH_GCP_FEATURE_MONTH",
        "IPCCH_GCP_INPUT_MANIFEST_URI",
        "IPCCH_GCP_RUN_ID",
        "IPCCH_GCP_CLOUD_RUN_JOB",
        "IPCCH_GCP_RELEASE_MANIFEST_URI",
    ]
    missing = [name for name in required if not os.environ.get(name)]
    assert not missing, f"missing live GCP smoke env vars: {missing}"

    command = build_cloud_run_dispatch_command(
        job_name=os.environ["IPCCH_GCP_CLOUD_RUN_JOB"],
        region=os.environ["IPCCH_GCP_REGION"],
        feature_month=os.environ["IPCCH_GCP_FEATURE_MONTH"],
        input_manifest_uri=os.environ["IPCCH_GCP_INPUT_MANIFEST_URI"],
        run_id=os.environ["IPCCH_GCP_RUN_ID"],
    )
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    validate_release_manifest_after_smoke(
        store=GCSObjectStore.from_default(),
        release_manifest_uri=os.environ["IPCCH_GCP_RELEASE_MANIFEST_URI"],
        run_id=os.environ["IPCCH_GCP_RUN_ID"],
    )
