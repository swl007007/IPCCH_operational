from cloud.orchestrator.release_manifest import build_current_release_manifest
from cloud.common.object_store import LocalObjectStore
from cloud.orchestrator.release import write_release


def test_release_manifest_contract_contains_required_current_fields():
    manifest = build_current_release_manifest(
        feature_month="2026-04",
        run_id="run-1",
        accepted_run_id="run-1",
        container_image_digest="sha256:" + "a" * 64,
        model_package={"uri": "gs://bucket/model/", "checksum": "b" * 64},
        validation_status={"base_input": "passed", "inference": "passed"},
        inference_status="passed",
        advisory_warning_state="none",
        copied_artifacts=[
            {
                "name": "base_input",
                "uri": "gs://bucket/released/202604/runs/run-1/base.csv",
                "checksum": "c" * 64,
            }
        ],
        referenced_artifacts=[
            {
                "name": "evi_raster",
                "uri": "gs://bucket/runs/run-1/gee_exports/evi.tif",
                "generation": "1",
            }
        ],
    )

    required = {
        "schema_version",
        "feature_month",
        "run_id",
        "accepted_run_id",
        "status",
        "container_image_digest",
        "model_package",
        "validation_status",
        "inference_status",
        "advisory_warning_state",
        "release_timestamp_utc",
        "released_copied_artifacts",
        "released_referenced_artifacts",
    }
    assert required <= manifest.keys()
    assert manifest["status"] == "current"
    assert manifest["inference_status"] == "passed"
    assert manifest["advisory_warning_state"] == "none"
    assert manifest["released_copied_artifacts"][0]["name"] == "base_input"
    assert manifest["released_referenced_artifacts"][0]["name"] == "evi_raster"


def test_write_release_emits_required_current_manifest_contract(tmp_path):
    store = LocalObjectStore(tmp_path)
    run_prefix = "gs://bucket/monthly/runs/run-1/"
    release_root = "gs://bucket/monthly/released/202604/"
    store.write_text("gs://bucket/monthly/input_manifest.json", '{"run_id":"run-1"}\n')
    store.write_text(
        run_prefix + "assembly/ipcch_monthly_base_input_202604.csv",
        "area_id,year,month\nA,2026,4\n",
    )
    store.write_text(
        run_prefix + "assembly/ipcch_monthly_base_input_202604_summary.json",
        '{"status":"passed"}\n',
    )
    store.write_text(
        run_prefix + "qa/base_input_validation_report.json",
        '{"status":"passed","schema_result":{"status":"passed"}}\n',
    )
    store.write_text(
        run_prefix + "inference/vertex_ai_job_manifest.json",
        '{"status":"passed"}\n',
    )
    store.write_text(
        run_prefix + "inference/inference_report.json",
        '{"status":"passed","model_output_schema":{"status":"passed"},'
        '"local_reference_comparison":{"status":"not_provided"}}\n',
    )
    store.write_text(
        run_prefix + "gee_exports/gee_export_manifest.json",
        '{"status":"passed"}\n',
    )
    store.write_text(
        run_prefix + "evi/evi_validation_report.json",
        '{"status":"passed"}\n',
    )
    store.write_text(
        run_prefix + "evi/evi_extraction_manifest.json",
        '{"status":"passed"}\n',
    )
    store.write_text(run_prefix + "run_summary.json", '{"status":"released"}\n')
    for scope in ("0m", "6m", "12m"):
        scope_months = {"0m": 0, "6m": 6, "12m": 12}[scope]
        target_period = {"0m": "2026-04", "6m": "2026-10", "12m": "2027-04"}[scope]
        store.write_text(
            run_prefix + f"inference/ipcch_launch_202604_scope_{scope}_predictions.csv",
            (
                "area_id,year,month,admin_code,_row_id,"
                "phase2_worse_score,phase2_worse_pred,"
                "phase3_worse_score,phase3_worse_pred,"
                "phase4_worse_score,phase4_worse_pred,"
                "phase5_worse_score,phase5_worse_pred,"
                "overall_phase_pred,feature_period,target_period,scope_months,"
                "model_package_id,source_input\n"
                f"A,2026,4,A,0,0.1,0,0.2,0,0.3,0,0.4,0,1,"
                f"2026-04,{target_period},{scope_months},model,base\n"
            ),
        )

    manifest = write_release(
        store=store,
        feature_month="2026-04",
        run_id="run-1",
        run_prefix_uri=run_prefix,
        release_root_uri=release_root,
        input_manifest_uri="gs://bucket/monthly/input_manifest.json",
        container_image_digest="sha256:" + "a" * 64,
        model_package_reference={
            "uri": "gs://bucket/model/",
            "generation": "1",
            "model_package_id": "model",
        },
        validation_status={"base_input": "passed", "inference": "passed"},
        inference_status="passed",
        referenced_artifacts=[
            {
                "name": "processed_evi_raster",
                "uri": run_prefix + "gee_exports/MOD13A3_EVI_2026_04_processed.tif",
                "generation": "1",
            }
        ],
    )

    required = {
        "schema_version",
        "feature_month",
        "run_id",
        "accepted_run_id",
        "status",
        "base_input_path",
        "base_input_checksum",
        "summary_path",
        "summary_checksum",
        "evi_evidence_references",
        "gee_export_manifest_reference",
        "input_manifest_reference",
        "base_input_validation_report_reference",
        "vertex_ai_job_manifest_reference",
        "inference_report_reference",
        "prediction_output_paths",
        "prediction_output_checksums",
        "model_package_reference",
        "model_version_or_checksum",
        "container_image_digest",
        "validation_status",
        "inference_status",
        "advisory_warning_state",
        "release_timestamp_utc",
        "released_copied_artifacts",
        "released_referenced_artifacts",
    }
    assert required <= manifest.keys()
    assert manifest["status"] == "current"
    assert manifest["model_package_reference"] == {
        "uri": "gs://bucket/model/",
        "generation": "1",
        "model_package_id": "model",
    }
    assert manifest["container_image_digest"] == "sha256:" + "a" * 64
