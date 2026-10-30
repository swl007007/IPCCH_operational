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


class Flaky(LocalObjectStore):
    def __init__(self, root, fail_write=None, fail_delete=()):
        super().__init__(root)
        self.fail_write, self.fail_delete = fail_write, set(fail_delete)

    def write_text(self, uri, content, *, if_generation_match=None):
        if self.fail_write and uri.endswith(self.fail_write):
            raise OSError("transport reset")
        return super().write_text(uri, content, if_generation_match=if_generation_match)

    def delete(self, uri, *, if_generation_match):
        if any(uri.endswith(s) for s in self.fail_delete):
            raise OSError("delete transport reset")
        return super().delete(uri, if_generation_match=if_generation_match)


def test_partial_acquisition_is_rolled_back_when_a_later_lock_is_held(tmp_path):
    store = LocalObjectStore(tmp_path)
    locks.acquire(store, REAL, ["ipcch"], "run-a")                                  # ipcch sorts AFTER fewsnet
    with pytest.raises(locks.LockConflict, match="run-a"):
        locks.acquire(store, REAL, ["ipcch", "fewsnet"], "run-b")
    assert store.get_metadata(locks.lock_uri(REAL, "fewsnet")) is None              # run-b's fewsnet lock removed


def test_transport_failure_releases_own_locks_and_keeps_the_cause(tmp_path):
    store = Flaky(tmp_path, fail_write="/locks/ipcch")
    with pytest.raises(locks.LockAcquisitionError, match="transport reset") as info:
        locks.acquire(store, REAL, ["ipcch", "fewsnet"], "run-b")
    assert isinstance(info.value.cause, OSError) and info.value.cleanup_failures == []
    assert store.get_metadata(locks.lock_uri(REAL, "fewsnet")) is None


def test_cleanup_attempts_every_lock_and_reports_failures(tmp_path):
    store = Flaky(tmp_path, fail_delete=["/locks/fewsnet"])
    held = locks.acquire(store, REAL, ["ipcch", "fewsnet"], "run-a")
    problems = locks.release(store, held)                                           # fewsnet delete fails first
    assert len(problems) == 1 and "fewsnet" in problems[0] and "delete transport reset" in problems[0]
    assert store.get_metadata(locks.lock_uri(REAL, "ipcch")) is None                # still attempted and released
    store2 = Flaky(tmp_path / "b", fail_write="/locks/ipcch", fail_delete=["/locks/fewsnet"])
    with pytest.raises(locks.LockAcquisitionError) as info:
        locks.acquire(store2, REAL, ["ipcch", "fewsnet"], "run-c")
    assert info.value.cleanup_failures and "fewsnet" in info.value.cleanup_failures[0]   # reported, not swallowed
