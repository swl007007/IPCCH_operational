import json

import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.orchestrator.run_state import DuplicateRunError, RunStateManager


def test_run_state_acquires_sentinel_and_initial_summary(tmp_path):
    store = LocalObjectStore(tmp_path)
    manager = RunStateManager(store, object_store_root_uri="gs://bucket/monthly")

    state = manager.acquire_run(
        feature_month="2026-04",
        run_id="run-1",
        input_manifest_uri="gs://bucket/input_manifest.json",
        deployment={"provider": "gcp"},
        container_image_digest="sha256:" + "a" * 64,
    )

    assert state.run_prefix_uri == "gs://bucket/monthly/runs/run-1/"
    assert (
        store.read_text("gs://bucket/monthly/runs/run-1/_RUN_PREFIX_ACQUIRED")
        == "run-1\n"
    )
    summary = json.loads(
        store.read_text("gs://bucket/monthly/runs/run-1/run_summary.json")
    )
    assert summary["status"] == "running"


def test_run_state_uses_explicit_run_root_uri_when_supplied(tmp_path):
    store = LocalObjectStore(tmp_path)
    manager = RunStateManager(
        store,
        object_store_root_uri="gs://bucket/monthly",
        run_root_uri="gs://bucket/custom/runs/run-1/",
    )

    state = manager.acquire_run(
        feature_month="2026-04",
        run_id="run-1",
        input_manifest_uri="gs://bucket/input_manifest.json",
        deployment={"provider": "gcp"},
        container_image_digest="sha256:" + "a" * 64,
    )

    assert state.run_prefix_uri == "gs://bucket/custom/runs/run-1/"
    assert store.read_text("gs://bucket/custom/runs/run-1/_RUN_PREFIX_ACQUIRED")


def test_duplicate_run_id_fails_before_overwriting_existing_summary(tmp_path):
    store = LocalObjectStore(tmp_path)
    manager = RunStateManager(store, object_store_root_uri="gs://bucket/monthly")
    kwargs = {
        "feature_month": "2026-04",
        "run_id": "run-1",
        "input_manifest_uri": "gs://bucket/input_manifest.json",
        "deployment": {"provider": "gcp"},
        "container_image_digest": "sha256:" + "a" * 64,
    }
    manager.acquire_run(**kwargs)
    initial_summary = store.read_text("gs://bucket/monthly/runs/run-1/run_summary.json")

    with pytest.raises(DuplicateRunError):
        manager.acquire_run(**kwargs)

    assert (
        store.read_text("gs://bucket/monthly/runs/run-1/run_summary.json")
        == initial_summary
    )


def test_terminal_summary_records_failure_and_keeps_run_prefix(tmp_path):
    store = LocalObjectStore(tmp_path)
    manager = RunStateManager(store, object_store_root_uri="gs://bucket/monthly")
    state = manager.acquire_run(
        feature_month="2026-04",
        run_id="run-1",
        input_manifest_uri="gs://bucket/input_manifest.json",
        deployment={"provider": "gcp"},
        container_image_digest="sha256:" + "a" * 64,
    )

    manager.write_terminal_summary(
        state, status="failed", hard_gates=[{"name": "base_input", "status": "failed"}]
    )

    summary = json.loads(
        store.read_text("gs://bucket/monthly/runs/run-1/run_summary.json")
    )
    assert summary["status"] == "failed"
    assert summary["hard_gates"] == [{"name": "base_input", "status": "failed"}]
    assert (
        summary["artifact_paths"]["run_prefix_uri"] == "gs://bucket/monthly/runs/run-1/"
    )
