import hashlib
import json

import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.orchestrator import release
from cloud.orchestrator.release import write_release


def _write_required_release_inputs(store, run_prefix):
    store.write_text("gs://bucket/monthly/input_manifest.json", '{"run_id":"run-1"}\n')
    store.write_text(
        run_prefix + "assembly/ipcch_monthly_base_input_202604.csv",
        "area_id,year,month\nA,2026,4\n",
    )
    store.write_text(
        run_prefix + "assembly/ipcch_monthly_base_input_202604_summary.json", "{}\n"
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


def _release_metadata(run_prefix):
    return {
        "input_manifest_uri": "gs://bucket/monthly/input_manifest.json",
        "container_image_digest": "sha256:" + "a" * 64,
        "model_package_reference": {
            "uri": "gs://bucket/model/",
            "generation": "1",
            "model_package_id": "model",
        },
        "validation_status": {"base_input": "passed", "inference": "passed"},
        "inference_status": "passed",
        "referenced_artifacts": [
            {
                "name": "processed_evi_raster",
                "uri": run_prefix + "gee_exports/MOD13A3_EVI_2026_04_processed.tif",
                "generation": "1",
            }
        ],
    }


def test_release_writer_copies_v1_artifacts_references_evidence_and_writes_manifest_last(
    tmp_path,
):
    store = LocalObjectStore(tmp_path)
    run_prefix = "gs://bucket/monthly/runs/run-1/"
    release_root = "gs://bucket/monthly/released/202604/"
    input_manifest_uri = "gs://bucket/monthly/input_manifest.json"
    store.write_text(input_manifest_uri, '{"run_id":"run-1"}\n')
    _write_required_release_inputs(store, run_prefix)

    manifest = write_release(
        store=store,
        feature_month="2026-04",
        run_id="run-1",
        run_prefix_uri=run_prefix,
        staging_root_uri="gs://bucket/monthly/staging/run-1/",
        release_root_uri=release_root,
        **(_release_metadata(run_prefix) | {"input_manifest_uri": input_manifest_uri}),
    )

    assert manifest["status"] == "current"
    assert manifest["released_referenced_artifacts"] == [
        {
            "name": "processed_evi_raster",
            "uri": run_prefix + "gee_exports/MOD13A3_EVI_2026_04_processed.tif",
            "generation": "1",
        }
    ]
    assert release_root + "release_manifest.json" == store.list(release_root)[-1]
    released_paths = set(store.list(release_root))
    for relative in (
        "assembly/ipcch_monthly_base_input_202604.csv",
        "assembly/ipcch_monthly_base_input_202604_summary.json",
        "qa/base_input_validation_report.json",
        "inference/vertex_ai_job_manifest.json",
        "inference/inference_report.json",
        "gee_exports/gee_export_manifest.json",
        "evi/evi_validation_report.json",
        "evi/evi_extraction_manifest.json",
        "run_summary.json",
        "release/release_step_report.json",
    ):
        assert release_root + "runs/run-1/" + relative in released_paths
    stored_manifest = json.loads(
        store.read_text(release_root + "release_manifest.json")
    )
    current_input_metadata = store.get_metadata(input_manifest_uri)
    stored_step_report = json.loads(
        store.read_text(release_root + "runs/run-1/release/release_step_report.json")
    )
    run_step_report = json.loads(
        store.read_text(run_prefix + "release/release_step_report.json")
    )
    assert stored_step_report["release_mode"] == "release_on_success"
    assert (
        stored_step_report["staging_root_uri"] == "gs://bucket/monthly/staging/run-1/"
    )
    assert run_step_report["checksum_verification"] == {"status": "passed"}
    assert run_step_report["copy_results"]
    assert run_step_report["released_copied_artifacts"]
    assert run_step_report["manifest_generation_precondition"] == 0
    assert stored_step_report["status"] == run_step_report["status"] == "passed"
    assert stored_step_report["new_manifest_generation"] is None
    assert run_step_report["new_manifest_generation"] == "1"
    assert stored_step_report["failure_reason"] is None
    assert stored_manifest["accepted_run_id"] == "run-1"
    assert stored_manifest["input_manifest_reference"]["uri"] == input_manifest_uri
    assert (
        stored_manifest["input_manifest_reference"]["generation"]
        == current_input_metadata.generation
    )
    assert "checksum" in stored_manifest["input_manifest_reference"]
    assert stored_manifest["container_image_digest"] == "sha256:" + "a" * 64
    assert stored_manifest["model_package_reference"] == {
        "uri": "gs://bucket/model/",
        "generation": "1",
        "model_package_id": "model",
    }
    assert stored_manifest["validation_status"] == {
        "base_input": "passed",
        "inference": "passed",
    }
    assert stored_manifest["inference_status"] == "passed"
    assert stored_manifest["gee_export_manifest_reference"]["uri"].endswith(
        "gee_export_manifest.json"
    )
    assert stored_manifest["base_input_validation_report_reference"]["uri"].endswith(
        "base_input_validation_report.json"
    )
    assert stored_manifest["vertex_ai_job_manifest_reference"]["uri"].endswith(
        "vertex_ai_job_manifest.json"
    )
    assert stored_manifest["inference_report_reference"]["uri"].endswith(
        "inference_report.json"
    )
    assert len(stored_manifest["evi_evidence_references"]) == 2


def test_release_manifest_records_final_released_step_report_metadata(tmp_path):
    store = LocalObjectStore(tmp_path)
    run_prefix = "gs://bucket/monthly/runs/run-1/"
    release_root = "gs://bucket/monthly/released/202604/"
    _write_required_release_inputs(store, run_prefix)

    write_release(
        store=store,
        feature_month="2026-04",
        run_id="run-1",
        run_prefix_uri=run_prefix,
        release_root_uri=release_root,
        **_release_metadata(run_prefix),
    )

    step_report_uri = release_root + "runs/run-1/release/release_step_report.json"
    stored_manifest = json.loads(
        store.read_text(release_root + "release_manifest.json")
    )
    step_entry = next(
        artifact
        for artifact in stored_manifest["released_copied_artifacts"]
        if artifact["uri"] == step_report_uri
    )
    final_step_content = store.read_text(step_report_uri)
    final_step_metadata = store.get_metadata(step_report_uri)

    assert step_entry["generation"] == final_step_metadata.generation
    assert (
        step_entry["checksum"]
        == hashlib.sha256(final_step_content.encode("utf-8")).hexdigest()
    )


def test_release_writer_accepts_running_run_summary_and_copies_released_candidate(
    tmp_path,
):
    store = LocalObjectStore(tmp_path)
    run_prefix = "gs://bucket/monthly/runs/run-1/"
    release_root = "gs://bucket/monthly/released/202604/"
    _write_required_release_inputs(store, run_prefix)
    store.write_text(
        run_prefix + "run_summary.json",
        json.dumps(
            {
                "status": "running",
                "release_attempted": False,
                "released": False,
                "release_manifest_path": None,
            }
        )
        + "\n",
    )

    manifest = write_release(
        store=store,
        feature_month="2026-04",
        run_id="run-1",
        run_prefix_uri=run_prefix,
        release_root_uri=release_root,
        **_release_metadata(run_prefix),
    )

    released_summary = json.loads(
        store.read_text(release_root + "runs/run-1/run_summary.json")
    )
    source_summary = json.loads(store.read_text(run_prefix + "run_summary.json"))
    assert manifest["status"] == "current"
    assert released_summary["status"] == "released"
    assert released_summary["release_attempted"] is True
    assert released_summary["released"] is True
    assert released_summary["release_manifest_path"] == (
        release_root + "release_manifest.json"
    )
    assert source_summary["status"] == "running"


def test_release_writer_does_not_infer_model_package_id_from_uri(tmp_path):
    store = LocalObjectStore(tmp_path)
    run_prefix = "gs://bucket/monthly/runs/run-1/"
    release_root = "gs://bucket/monthly/released/202604/"
    _write_required_release_inputs(store, run_prefix)
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
                f"2026-04,{target_period},{scope_months},launch_2026_04,base\n"
            ),
        )

    manifest = write_release(
        store=store,
        feature_month="2026-04",
        run_id="run-1",
        run_prefix_uri=run_prefix,
        release_root_uri=release_root,
        **(
            _release_metadata(run_prefix)
            | {
                "model_package_reference": {
                    "uri": "gs://bucket/model_packages/package_dir/",
                    "generation": "1",
                    "model_package_id": "launch_2026_04",
                }
            }
        ),
    )

    assert manifest["status"] == "current"


def test_release_writer_requires_explicit_model_package_id_reference(tmp_path):
    store = LocalObjectStore(tmp_path)
    run_prefix = "gs://bucket/monthly/runs/run-1/"
    release_root = "gs://bucket/monthly/released/202604/"
    _write_required_release_inputs(store, run_prefix)

    with pytest.raises(ValueError, match="model_package_id"):
        write_release(
            store=store,
            feature_month="2026-04",
            run_id="run-1",
            run_prefix_uri=run_prefix,
            release_root_uri=release_root,
            **(
                _release_metadata(run_prefix)
                | {
                    "model_package_reference": {
                        "uri": "gs://bucket/model_packages/package_dir/",
                        "generation": "1",
                    }
                }
            ),
        )


def test_release_writer_does_not_overwrite_existing_released_run_artifacts(tmp_path):
    store = LocalObjectStore(tmp_path)
    run_prefix = "gs://bucket/monthly/runs/run-1/"
    release_root = "gs://bucket/monthly/released/202604/"
    _write_required_release_inputs(store, run_prefix)

    first = write_release(
        store=store,
        feature_month="2026-04",
        run_id="run-1",
        run_prefix_uri=run_prefix,
        release_root_uri=release_root,
        **_release_metadata(run_prefix),
    )
    released_base_uri = (
        release_root + "runs/run-1/assembly/ipcch_monthly_base_input_202604.csv"
    )
    previous_released_base = store.read_text(released_base_uri)
    store.write_text(
        run_prefix + "assembly/ipcch_monthly_base_input_202604.csv",
        "area_id,year,month\nA,2026,4\n",
    )

    second = write_release(
        store=store,
        feature_month="2026-04",
        run_id="run-1",
        run_prefix_uri=run_prefix,
        release_root_uri=release_root,
        **_release_metadata(run_prefix),
    )

    assert first["status"] == "current"
    assert second["status"] == "release_conflict"
    assert store.read_text(released_base_uri) == previous_released_base
    run_step_report = json.loads(
        store.read_text(run_prefix + "release/release_step_report.json")
    )
    assert run_step_report["failure_reason"] == "release_artifact_generation_conflict"


def test_release_writer_reports_released_step_report_generation_conflict(tmp_path):
    store = LocalObjectStore(tmp_path)
    run_prefix = "gs://bucket/monthly/runs/run-1/"
    release_root = "gs://bucket/monthly/released/202604/"
    _write_required_release_inputs(store, run_prefix)
    store.write_text(
        release_root + "runs/run-1/release/release_step_report.json",
        '{"status":"existing"}\n',
    )

    result = write_release(
        store=store,
        feature_month="2026-04",
        run_id="run-1",
        run_prefix_uri=run_prefix,
        release_root_uri=release_root,
        **_release_metadata(run_prefix),
    )

    assert result["status"] == "release_conflict"
    assert release_root + "release_manifest.json" not in store.list(
        "gs://bucket/monthly/released/202604/"
    )
    run_step_report = json.loads(
        store.read_text(run_prefix + "release/release_step_report.json")
    )
    assert run_step_report["status"] == "release_conflict"
    assert (
        run_step_report["failure_reason"] == "release_step_report_generation_conflict"
    )


def test_release_manifest_conflict_marks_released_step_report_as_conflict(tmp_path):
    store = LocalObjectStore(tmp_path)
    run1 = "gs://bucket/monthly/runs/run-1/"
    run2 = "gs://bucket/monthly/runs/run-2/"
    release_root = "gs://bucket/monthly/released/202604/"
    _write_required_release_inputs(store, run1)
    _write_required_release_inputs(store, run2)
    write_release(
        store=store,
        feature_month="2026-04",
        run_id="run-1",
        run_prefix_uri=run1,
        release_root_uri=release_root,
        **_release_metadata(run1),
    )
    original_write_text = store.write_text
    injected_conflict = False

    def racing_write_text(uri, content, *, if_generation_match=None):
        nonlocal injected_conflict
        if (
            uri == release_root + "release_manifest.json"
            and if_generation_match == "1"
            and not injected_conflict
        ):
            injected_conflict = True
            original_write_text(
                uri,
                '{"status":"current","accepted_run_id":"external"}\n',
                if_generation_match="1",
            )
        return original_write_text(
            uri, content, if_generation_match=if_generation_match
        )

    store.write_text = racing_write_text

    result = write_release(
        store=store,
        feature_month="2026-04",
        run_id="run-2",
        run_prefix_uri=run2,
        release_root_uri=release_root,
        **_release_metadata(run2),
    )

    assert result["status"] == "release_conflict"
    released_step_report = json.loads(
        store.read_text(release_root + "runs/run-2/release/release_step_report.json")
    )
    assert released_step_report["status"] == "release_conflict"
    assert released_step_report["new_manifest_generation"] is None
    assert (
        released_step_report["failure_reason"] == "release_manifest_generation_conflict"
    )


def test_release_writer_rejects_failed_hard_gate_report_before_copy(tmp_path):
    store = LocalObjectStore(tmp_path)
    run_prefix = "gs://bucket/monthly/runs/run-1/"
    release_root = "gs://bucket/monthly/released/202604/"
    _write_required_release_inputs(store, run_prefix)
    store.write_text(
        run_prefix + "qa/base_input_validation_report.json",
        '{"status":"failed","schema_result":{"status":"failed"}}\n',
    )

    with pytest.raises(ValueError, match="base_input_validation_report"):
        write_release(
            store=store,
            feature_month="2026-04",
            run_id="run-1",
            run_prefix_uri=run_prefix,
            release_root_uri=release_root,
            **_release_metadata(run_prefix),
        )

    assert store.list(release_root) == []


def test_release_writer_revalidates_actual_prediction_artifacts_before_copy(tmp_path):
    store = LocalObjectStore(tmp_path)
    run_prefix = "gs://bucket/monthly/runs/run-1/"
    release_root = "gs://bucket/monthly/released/202604/"
    _write_required_release_inputs(store, run_prefix)
    store.write_text(
        run_prefix + "inference/ipcch_launch_202604_scope_6m_predictions.csv",
        "area_id,year,month,prediction\nA,2026,4,1\n",
    )

    with pytest.raises(ValueError, match="prediction"):
        write_release(
            store=store,
            feature_month="2026-04",
            run_id="run-1",
            run_prefix_uri=run_prefix,
            release_root_uri=release_root,
            **_release_metadata(run_prefix),
        )

    assert store.list(release_root) == []


def test_release_writer_requires_release_metadata_and_immutable_references(tmp_path):
    store = LocalObjectStore(tmp_path)
    run_prefix = "gs://bucket/monthly/runs/run-1/"
    release_root = "gs://bucket/monthly/released/202604/"
    _write_required_release_inputs(store, run_prefix)

    with pytest.raises(ValueError, match="container_image_digest"):
        write_release(
            store=store,
            feature_month="2026-04",
            run_id="run-1",
            run_prefix_uri=run_prefix,
            release_root_uri=release_root,
            referenced_artifacts=[
                {
                    "name": "processed_evi_raster",
                    "uri": run_prefix + "gee_exports/MOD13A3_EVI_2026_04_processed.tif",
                    "generation": "1",
                }
            ],
            input_manifest_uri="gs://bucket/monthly/input_manifest.json",
            model_package_reference={"uri": "gs://bucket/model/", "generation": "1"},
            validation_status={"base_input": "passed", "inference": "passed"},
            inference_status="passed",
        )

    with pytest.raises(ValueError, match="immutable"):
        write_release(
            store=store,
            feature_month="2026-04",
            run_id="run-1",
            run_prefix_uri=run_prefix,
            release_root_uri=release_root,
            referenced_artifacts=[
                {
                    "name": "processed_evi_raster",
                    "uri": run_prefix + "gee_exports/MOD13A3_EVI_2026_04_processed.tif",
                }
            ],
            input_manifest_uri="gs://bucket/monthly/input_manifest.json",
            container_image_digest="sha256:" + "a" * 64,
            model_package_reference={"uri": "gs://bucket/model/", "generation": "1"},
            validation_status={"base_input": "passed", "inference": "passed"},
            inference_status="passed",
        )


def test_release_cli_parser_exposes_execution_contract_arguments():
    args = release.parse_args(
        [
            "--feature-month",
            "2026-04",
            "--run-id",
            "run-1",
            "--input-manifest-uri",
            "gs://bucket/monthly/input_manifest.json",
            "--run-root-uri",
            "gs://bucket/monthly/runs/run-1/",
            "--staging-root-uri",
            "gs://bucket/monthly/staging/run-1/",
            "--release-root-uri",
            "gs://bucket/monthly/released/202604/",
            "--model-package-id",
            "model",
        ]
    )

    assert args.feature_month == "2026-04"
    assert args.run_id == "run-1"
    assert args.input_manifest_uri == "gs://bucket/monthly/input_manifest.json"
    assert args.run_root_uri == "gs://bucket/monthly/runs/run-1/"
    assert args.staging_root_uri == "gs://bucket/monthly/staging/run-1/"
    assert args.release_root_uri == "gs://bucket/monthly/released/202604/"
    assert args.model_package_id == "model"


def test_release_cli_returns_nonzero_on_release_conflict(tmp_path, monkeypatch):
    store = LocalObjectStore(tmp_path)
    run_prefix = "gs://bucket/monthly/runs/run-1/"
    release_root = "gs://bucket/monthly/released/202604/"
    _write_required_release_inputs(store, run_prefix)
    store.write_text(
        release_root + "runs/run-1/assembly/ipcch_monthly_base_input_202604.csv",
        "area_id,year,month\nexisting,2026,4\n",
    )

    class FakeStoreFactory:
        @classmethod
        def from_default(cls):
            return store

    monkeypatch.setattr(release, "GCSObjectStore", FakeStoreFactory)

    exit_code = release.main(
        [
            "--feature-month",
            "2026-04",
            "--run-id",
            "run-1",
            "--input-manifest-uri",
            "gs://bucket/monthly/input_manifest.json",
            "--run-root-uri",
            run_prefix,
            "--staging-root-uri",
            "gs://bucket/monthly/staging/run-1/",
            "--release-root-uri",
            release_root,
            "--container-image-digest",
            "sha256:" + "a" * 64,
            "--model-package-uri",
            "gs://bucket/model/",
            "--model-package-id",
            "model",
            "--model-package-generation",
            "1",
            "--referenced-artifact-json",
            json.dumps(
                {
                    "name": "processed_evi_raster",
                    "uri": run_prefix + "gee_exports/MOD13A3_EVI_2026_04_processed.tif",
                    "generation": "1",
                }
            ),
        ]
    )

    assert exit_code == 1
