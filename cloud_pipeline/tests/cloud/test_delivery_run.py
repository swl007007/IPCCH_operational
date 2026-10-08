import json

import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.orchestrator import delivery_run as dr

ROOT = "gs://delivery-bucket"
REQUEST = {"uri": f"{ROOT}/requests/oct-2026-a/run_manifest.json", "generation": "11", "sha256": "a" * 64}


def test_only_exact_request_paths_with_a_generation_trigger_work():
    event = {"bucket": "delivery-bucket", "name": "requests/oct-2026-a/run_manifest.json", "generation": 11}

    assert dr.request_from_event(event) == {"uri": REQUEST["uri"], "generation": "11", "run_id": "oct-2026-a"}
    for name in ("runs/oct-2026-a/run_status.json", "requests/oct-2026-a/notes.json", "reports/x.json"):
        assert dr.request_from_event({**event, "name": name}) is None
    for generation in (None, 0, "0", True, "latest"):
        with pytest.raises(ValueError, match="exact positive generation"):
            dr.request_from_event({**event, "generation": generation})


def test_identical_duplicate_returns_the_original_status_without_recomputing(tmp_path):
    store, calls = LocalObjectStore(tmp_path), []

    def compute():
        calls.append(1)
        return {"outputs": "deliveries/oct-2026-a/"}

    first = dr.run_once(store, ROOT, run_id="oct-2026-a", request_ref=REQUEST, compute=compute)
    second = dr.run_once(store, ROOT, run_id="oct-2026-a", request_ref=REQUEST, compute=compute)

    assert calls == [1]
    assert first["status"] == second["status"] == "succeeded" and second["duplicate"] is True
    assert second["outputs"] == "deliveries/oct-2026-a/"
    assert second["status_uri"] == first["status_uri"] == f"{ROOT}/runs/oct-2026-a/run_status.json"


def test_different_request_under_the_same_run_id_conflicts(tmp_path):
    store = LocalObjectStore(tmp_path)
    dr.run_once(store, ROOT, run_id="oct-2026-a", request_ref=REQUEST, compute=dict)

    with pytest.raises(dr.RunConflict, match="new run ID"):
        dr.run_once(store, ROOT, run_id="oct-2026-a", request_ref={**REQUEST, "generation": "12"}, compute=dict)


def test_failed_or_abandoned_runs_are_not_resumed_and_retry_needs_a_new_id(tmp_path):
    store = LocalObjectStore(tmp_path)

    def boom():
        raise RuntimeError("required input missing")

    with pytest.raises(RuntimeError):
        dr.run_once(store, ROOT, run_id="oct-2026-a", request_ref=REQUEST, compute=boom)
    again = dr.run_once(store, ROOT, run_id="oct-2026-a", request_ref=REQUEST, compute=lambda: pytest.fail("rerun"))
    assert again["status"] == "failed" and "required input missing" in again["error"]

    store.write_text(f"{ROOT}/runs/oct-2026-b/_RUN_ACQUIRED", json.dumps(
        {"run_id": "oct-2026-b", "request": REQUEST}, sort_keys=True) + "\n", if_generation_match=0)  # abandoned
    abandoned = dr.run_once(store, ROOT, run_id="oct-2026-b", request_ref=REQUEST, compute=lambda: pytest.fail("resume"))
    assert abandoned["status"] == dr.ABANDONED_OR_RUNNING
    assert abandoned["status_uri"] == f"{ROOT}/runs/oct-2026-b/run_status.json"  # where the original will report

    retry = dr.run_once(store, ROOT, run_id="oct-2026-c", request_ref=REQUEST, compute=dict)
    assert retry["status"] == "succeeded" and retry["duplicate"] is False


def _publish(store, run_id, expected, validate=lambda: None):
    return dr.publish(store, ROOT, run_id=run_id, namespace="fewsnet-ipcch", expected_pointer_generation=expected,
                      release_record={"run_id": run_id}, validate=validate)


def test_release_pointer_moves_by_generation_cas_and_conflicts_preserve_it(tmp_path):
    store = LocalObjectStore(tmp_path)
    first = _publish(store, "oct-2026-a", "0")
    pointer = store.read_text(first["pointer_uri"])

    with pytest.raises(dr.ReleaseConflict, match="recorded at"):  # stale expectation: another publisher won
        _publish(store, "oct-2026-b", "0")
    assert store.read_text(first["pointer_uri"]) == pointer
    conflict = json.loads(store.read_text(f"{ROOT}/runs/oct-2026-b/release_conflict.json"))
    assert conflict["status"] == "release_conflict" and conflict["expected_pointer_generation"] == "0"
    assert conflict["actual_pointer_generation"] == first["pointer_generation"]
    assert store.get_metadata(f"{ROOT}/fewsnet-ipcch/releases/oct-2026-b/release.json") is None

    second = _publish(store, "oct-2026-c", first["pointer_generation"])
    assert json.loads(store.read_text(second["pointer_uri"]))["run_id"] == "oct-2026-c"


def test_failed_validation_or_legacy_root_never_touches_the_pointer(tmp_path):
    store = LocalObjectStore(tmp_path)
    first = _publish(store, "oct-2026-a", "0")

    def invalid():
        raise ValueError("bundle hash mismatch")

    with pytest.raises(ValueError, match="hash mismatch"):
        _publish(store, "oct-2026-b", first["pointer_generation"], validate=invalid)
    with pytest.raises(ValueError, match="legacy"):
        dr.publish(store, ROOT, run_id="x", namespace="released", expected_pointer_generation="0",
                   release_record={}, validate=lambda: None)
    assert json.loads(store.read_text(first["pointer_uri"]))["run_id"] == "oct-2026-a"
    assert store.get_metadata(f"{ROOT}/fewsnet-ipcch/releases/oct-2026-b/release.json") is None


def test_concurrent_pointer_write_conflict_is_recorded_after_the_record_write(tmp_path):
    store = LocalObjectStore(tmp_path)
    original_write = store.write_text

    def racing_write(uri, content, *, if_generation_match=None):
        if uri.endswith("current.json") and not getattr(racing_write, "raced", False):
            racing_write.raced = True  # another publisher moves the pointer between precheck and write
            original_write(uri, "{}\n", if_generation_match=0)
        return original_write(uri, content, if_generation_match=if_generation_match)

    store.write_text = racing_write
    with pytest.raises(dr.ReleaseConflict):
        _publish(store, "oct-2026-a", "0")
    conflict = json.loads(store.read_text(f"{ROOT}/runs/oct-2026-a/release_conflict.json"))
    assert conflict["stage"] == "pointer_write" and conflict["unpublished_release_record"].endswith("release.json")
    assert store.read_text(f"{ROOT}/fewsnet-ipcch/current.json") == "{}\n"  # the winner is preserved
