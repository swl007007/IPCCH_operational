import json
import os
import subprocess

import pytest

from cloud.common.object_store import GCSObjectStore, LocalObjectStore


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
    for path in manifest["prediction_output_paths"]:
        store.read_text(path)
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
    store.write_text(prediction_path, "area_id,year,month\nA,2026,4\n")
    copied_path = (
        "gs://bucket/monthly/released/202604/runs/run-1/qa/"
        "base_input_validation_report.json"
    )
    store.write_text(copied_path, '{"status":"passed"}')
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
    prediction_paths = [
        f"gs://bucket/monthly/released/202604/runs/run-1/inference/ipcch_launch_202604_scope_{scope}_predictions.csv"
        for scope in ("0m", "6m", "12m")
    ]
    for path in prediction_paths:
        store.write_text(path, "area_id,year,month\nA,2026,4\n")
    copied_paths = {
        "base_input_validation_report_reference": "gs://bucket/monthly/released/202604/runs/run-1/qa/base_input_validation_report.json",
        "vertex_ai_job_manifest_reference": "gs://bucket/monthly/released/202604/runs/run-1/inference/vertex_ai_job_manifest.json",
        "inference_report_reference": "gs://bucket/monthly/released/202604/runs/run-1/inference/inference_report.json",
        "gee_export_manifest_reference": "gs://bucket/monthly/released/202604/runs/run-1/gee_exports/gee_export_manifest.json",
    }
    for path in copied_paths.values():
        store.write_text(path, '{"status":"passed"}')
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
