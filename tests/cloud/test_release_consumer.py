import json

import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.common.release_reader import ReleaseManifestError, read_release_manifest


def test_release_reader_resolves_consumer_paths_only_from_manifest(tmp_path):
    store = LocalObjectStore(tmp_path)
    manifest_uri = "gs://bucket/monthly/released/202604/release_manifest.json"
    store.write_text(
        manifest_uri,
        json.dumps(
            {
                "status": "current",
                "accepted_run_id": "run-1",
                "base_input_path": "gs://bucket/monthly/released/202604/runs/run-1/base.csv",
                "summary_path": "gs://bucket/monthly/released/202604/runs/run-1/summary.json",
                "prediction_output_paths": [
                    "gs://bucket/monthly/released/202604/runs/run-1/pred.csv"
                ],
                "released_referenced_artifacts": [
                    {"name": "evi_raster", "uri": "gs://bucket/runs/run-1/evi.tif"}
                ],
            }
        ),
    )

    release = read_release_manifest(store, manifest_uri)

    assert release["base_input_path"].endswith("base.csv")
    assert release["prediction_output_paths"] == [
        "gs://bucket/monthly/released/202604/runs/run-1/pred.csv"
    ]


def test_release_reader_rejects_bare_folder_inference(tmp_path):
    store = LocalObjectStore(tmp_path)

    with pytest.raises(ReleaseManifestError, match="release_manifest.json"):
        read_release_manifest(store, "gs://bucket/monthly/released/202604/")
