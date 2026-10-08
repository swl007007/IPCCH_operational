"""Debug parity entry stages only pinned, hash-checked inputs (local fakes; not cloud acceptance)."""
import json

import pytest

from cloud.orchestrator import deliver_job as dbg
from cloud.orchestrator.delivery_job import AcceptanceError, PinnedDownloader
from tests.cloud.test_delivery_job import FakeClient


def _manifest(client, files, *, generation="5"):
    prepared = client.put("gs://b/prepared/p/prepared_manifest.json", "7", json.dumps(
        {"prepare_id": "p", "origin_month": "2026-10", "families": {"evi": {"outputs": {
            "ipcch": client.put("gs://b/prepared/p/evi.csv", "8", b"admin_code,month\n")}}}}).encode())
    body = {"schema_version": dbg.INPUTS_SCHEMA, "prepared_manifest": prepared,
            "files": {name: client.put(f"gs://b/in/{name}", "3", data) for name, data in files.items()}}
    return client.put("gs://b/in/inputs_manifest.json", generation, json.dumps(body).encode())


def test_inputs_are_staged_by_logical_path_from_pinned_generations(tmp_path):
    client = FakeClient()
    ref = _manifest(client, {"ipcch_panel.csv": b"a\n1\n", "fewsnet_package/0m/model.joblib": b"m"})

    spec = dbg.stage_inputs(PinnedDownloader(client, tmp_path / "dl"), ref, tmp_path / "inputs")

    assert (tmp_path / "inputs/ipcch_panel.csv").read_bytes() == b"a\n1\n"
    assert (tmp_path / "inputs/fewsnet_package/0m/model.joblib").read_bytes() == b"m"
    assert list(spec["reader_index"]) == ["gs://b/prepared/p/evi.csv#8"]
    assert all(generation is not None for _, _, generation in client.downloads)


def test_tampered_or_escaping_inputs_are_rejected(tmp_path):
    client = FakeClient()
    ref = _manifest(client, {"ipcch_panel.csv": b"a\n"})
    client.put("gs://b/in/ipcch_panel.csv", "3", b"tampered")
    with pytest.raises(AcceptanceError, match="sha256 mismatch"):
        dbg.stage_inputs(PinnedDownloader(client, tmp_path / "dl"), ref, tmp_path / "inputs")

    other = FakeClient()
    escaping = _manifest(other, {"../outside.csv": b"x"})
    with pytest.raises(ValueError, match="escapes the inputs root"):
        dbg.stage_inputs(PinnedDownloader(other, tmp_path / "dl2"), escaping, tmp_path / "inputs2")
    assert not (tmp_path / "outside.csv").exists()
