import json

from cloud.common.object_store import LocalObjectStore, ObjectMetadata
from cloud.orchestrator.release import write_release


def _seed_required_run_artifacts(store, run_prefix, yyyymm):
    store.write_text("gs://bucket/monthly/input_manifest.json", '{"run_id":"run"}\n')
    store.write_text(
        run_prefix + f"assembly/ipcch_monthly_base_input_{yyyymm}.csv",
        "area_id,year,month\nA,2026,4\n",
    )
    store.write_text(
        run_prefix + f"assembly/ipcch_monthly_base_input_{yyyymm}_summary.json", "{}\n"
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
            run_prefix
            + f"inference/ipcch_launch_{yyyymm}_scope_{scope}_predictions.csv",
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


def test_release_supersession_updates_current_manifest_with_previous_generation(
    tmp_path,
):
    store = LocalObjectStore(tmp_path)
    release_root = "gs://bucket/monthly/released/202604/"
    run1 = "gs://bucket/monthly/runs/run-1/"
    run2 = "gs://bucket/monthly/runs/run-2/"
    _seed_required_run_artifacts(store, run1, "202604")
    _seed_required_run_artifacts(store, run2, "202604")
    first = write_release(
        store=store,
        feature_month="2026-04",
        run_id="run-1",
        run_prefix_uri=run1,
        release_root_uri=release_root,
        **_release_metadata(run1),
    )
    previous_manifest = store.read_text(release_root + "release_manifest.json")

    second = write_release(
        store=store,
        feature_month="2026-04",
        run_id="run-2",
        run_prefix_uri=run2,
        release_root_uri=release_root,
        **_release_metadata(run2),
    )

    assert first["status"] == "current"
    assert second["status"] == "current"
    current_manifest = json.loads(
        store.read_text(release_root + "release_manifest.json")
    )
    assert current_manifest["accepted_run_id"] == "run-2"
    run2_step_report = json.loads(
        store.read_text(run2 + "release/release_step_report.json")
    )
    assert run2_step_report["status"] == "passed"
    assert run2_step_report["checksum_verification"] == {"status": "passed"}
    assert run2_step_report["previous_manifest_generation"] == "1"
    assert run2_step_report["new_manifest_generation"] == "2"
    assert run2_step_report["failure_reason"] is None
    assert json.loads(previous_manifest)["accepted_run_id"] == "run-1"


def test_release_conflict_preserves_externally_updated_manifest(tmp_path):
    store = LocalObjectStore(tmp_path)
    release_root = "gs://bucket/monthly/released/202604/"
    run1 = "gs://bucket/monthly/runs/run-1/"
    run2 = "gs://bucket/monthly/runs/run-2/"
    _seed_required_run_artifacts(store, run1, "202604")
    _seed_required_run_artifacts(store, run2, "202604")
    write_release(
        store=store,
        feature_month="2026-04",
        run_id="run-1",
        run_prefix_uri=run1,
        release_root_uri=release_root,
        **_release_metadata(run1),
    )
    original_write_text = store.write_text
    external_manifest = '{"status":"current","accepted_run_id":"external"}\n'
    injected_conflict = False

    def racing_write_text(uri, content, *, if_generation_match=None):
        nonlocal injected_conflict
        if (
            uri == release_root + "release_manifest.json"
            and if_generation_match == "1"
            and not injected_conflict
        ):
            injected_conflict = True
            original_write_text(uri, external_manifest, if_generation_match="1")
        return original_write_text(
            uri, content, if_generation_match=if_generation_match
        )

    store.write_text = racing_write_text

    second = write_release(
        store=store,
        feature_month="2026-04",
        run_id="run-2",
        run_prefix_uri=run2,
        release_root_uri=release_root,
        **_release_metadata(run2),
    )

    assert second["status"] == "release_conflict"
    assert store.read_text(release_root + "release_manifest.json") == external_manifest
    run2_step_report = json.loads(
        store.read_text(run2 + "release/release_step_report.json")
    )
    assert run2_step_report["status"] == "release_conflict"
    assert run2_step_report["previous_manifest_generation"] == "1"
    assert run2_step_report["new_manifest_generation"] is None
    assert run2_step_report["failure_reason"] == "release_manifest_generation_conflict"


class MetadataOnlyObjectStore:
    """GCS-like fake that exposes object metadata but no private _generations map."""

    def __init__(self, root):
        self._store = LocalObjectStore(root)

    def write_text(self, uri, content, *, if_generation_match=None):
        return self._store.write_text(
            uri, content, if_generation_match=if_generation_match
        )

    def read_text(self, uri):
        return self._store.read_text(uri)

    def list(self, prefix_uri):
        return self._store.list(prefix_uri)

    def copy(self, source_uri, target_uri, *, if_generation_match=None):
        return self._store.copy(
            source_uri, target_uri, if_generation_match=if_generation_match
        )

    def get_metadata(self, uri):
        generation = self._store._generations.get(uri)
        if generation is None:
            return None
        return ObjectMetadata(uri=uri, generation=str(generation))


def test_release_supersession_uses_object_metadata_not_local_private_state(tmp_path):
    store = MetadataOnlyObjectStore(tmp_path)
    release_root = "gs://bucket/monthly/released/202604/"
    run1 = "gs://bucket/monthly/runs/run-1/"
    run2 = "gs://bucket/monthly/runs/run-2/"
    _seed_required_run_artifacts(store, run1, "202604")
    _seed_required_run_artifacts(store, run2, "202604")
    write_release(
        store=store,
        feature_month="2026-04",
        run_id="run-1",
        run_prefix_uri=run1,
        release_root_uri=release_root,
        **_release_metadata(run1),
    )

    second = write_release(
        store=store,
        feature_month="2026-04",
        run_id="run-2",
        run_prefix_uri=run2,
        release_root_uri=release_root,
        **_release_metadata(run2),
    )

    assert second["status"] == "current"
    assert (
        json.loads(store.read_text(release_root + "release_manifest.json"))[
            "accepted_run_id"
        ]
        == "run-2"
    )
    run2_step_report = json.loads(
        store.read_text(run2 + "release/release_step_report.json")
    )
    assert run2_step_report["manifest_generation_precondition"] == "1"
