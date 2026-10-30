"""Task 10-29: per-system v2 run locks (R50, final convergence corrections)."""

import pytest

from cloud.common.object_store import GenerationConflict, LocalObjectStore
from cloud.ipcch import locks

REAL, SMOKE = "gs://ipcch-store/ipcch-v2/real", "gs://ipcch-store/ipcch-v2/smoke"


def test_all_or_nothing_acquisition_releases_only_own_locks(tmp_path):
    store = LocalObjectStore(tmp_path)
    held = locks.acquire(store, REAL, ["fewsnet"], "run-a")
    with pytest.raises(locks.LockConflict, match="fewsnet run in progress .*run-a") as info:
        locks.acquire(store, REAL, ["ipcch", "fewsnet"], "run-b")
    assert info.value.holder == "run-a"
    assert store.get_metadata(locks.lock_uri(REAL, "ipcch")) is None               # run-b's own ipcch lock released
    assert store.get_metadata(locks.lock_uri(REAL, "fewsnet")).generation == held[0].generation   # run-a's untouched
    other = locks.acquire(store, REAL, ["ipcch"], "run-c")                         # different systems run in parallel
    assert [l.system for l in other] == ["ipcch"]
    assert locks.release(store, held + other) == []
    assert locks.acquire(store, REAL, ["ipcch", "fewsnet"], "run-d")


def test_namespaces_are_isolated_and_stale_locks_need_an_explicit_operations_action(tmp_path):
    store = LocalObjectStore(tmp_path)
    locks.acquire(store, REAL, ["ipcch"], "real-run")
    assert locks.acquire(store, SMOKE, ["ipcch"], "smoke-run")                      # smoke never contends with real
    crashed = locks.acquire(store, REAL, ["fewsnet"], "crashed-run")
    with pytest.raises(locks.LockConflict):                                        # no automatic eviction
        locks.acquire(store, REAL, ["fewsnet"], "next-run")
    with pytest.raises(locks.LockConflict, match="crashed-run"):
        locks.clear_lock(store, REAL, "fewsnet", expected_run_id="someone-else", generation=crashed[0].generation)
    with pytest.raises(GenerationConflict):
        locks.clear_lock(store, REAL, "fewsnet", expected_run_id="crashed-run", generation="99")
    locks.clear_lock(store, REAL, "fewsnet", expected_run_id="crashed-run", generation=crashed[0].generation)
    assert locks.acquire(store, REAL, ["fewsnet"], "next-run")


def test_release_never_deletes_a_lock_that_moved(tmp_path):
    store = LocalObjectStore(tmp_path)
    mine = locks.acquire(store, REAL, ["ipcch"], "run-a")
    locks.clear_lock(store, REAL, "ipcch", expected_run_id="run-a", generation=mine[0].generation)
    theirs = locks.acquire(store, REAL, ["ipcch"], "run-b")
    problems = locks.release(store, mine)                                          # run-a's stale handle
    assert problems and store.get_metadata(locks.lock_uri(REAL, "ipcch")).generation == theirs[0].generation
