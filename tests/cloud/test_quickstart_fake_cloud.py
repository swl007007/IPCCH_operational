import json

from cloud.common.object_store import LocalObjectStore
from cloud.common.release_reader import read_release_manifest
from cloud.orchestrator import main


def test_fake_cloud_quickstart_runs_manifest_validation_through_release_readback(
    tmp_path,
):
    store = LocalObjectStore(tmp_path)
    result = main.run_fake_cloud_e2e(
        store=store,
        feature_month="2026-04",
        run_id="run-quickstart",
        input_manifest={
            "feature_month": "2026-04",
            "run_id": "run-quickstart",
            "deployment": {
                "object_store_root_uri": "gs://bucket/monthly",
                "artifact_registry_image_uri": "us/pkg/ipcch@sha256:" + "a" * 64,
                "vertex_ai_custom_job_container_digest": "sha256:" + "a" * 64,
            },
        },
        zones=[{"area_id": "A", "values": [1000, 3000]}],
    )

    assert result["run_summary"]["status"] == "released"
    release = read_release_manifest(store, result["release_manifest_uri"])
    assert release["accepted_run_id"] == "run-quickstart"
    assert release["base_input_path"].endswith("ipcch_monthly_base_input_202604.csv")
    assert "prediction_output_paths" in release
    assert (
        json.loads(
            store.read_text("gs://bucket/monthly/runs/run-quickstart/run_summary.json")
        )["release_manifest_path"]
        == result["release_manifest_uri"]
    )
