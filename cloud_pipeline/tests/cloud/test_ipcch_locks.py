"""Task 10-29: per-system v2 run locks (R50, final convergence corrections)."""

import json

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


class SwapOnRead:
    """Store wrapper: on the first body read of ``uri`` the lock is replaced by run B's lock (deterministic race),
    either before the body is returned (``when='before'``: the body read is B's) or after (A's body, B's object)."""

    def __init__(self, inner, uri, when):
        self.inner, self.uri, self.when, self.done = inner, uri, when, False

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def _swap(self):
        self.done = True
        self.inner.delete(self.uri, if_generation_match=self.inner.get_metadata(self.uri).generation)
        self.inner.write_text(self.uri, '{"run_id": "run-B", "system": "fewsnet"}\n', if_generation_match=0)

    def read_text(self, uri):
        if uri == self.uri and not self.done:
            if self.when == "before":
                self._swap()
                return self.inner.read_text(uri)
            body = self.inner.read_text(uri)
            self._swap()
            return body
        return self.inner.read_text(uri)


@pytest.mark.parametrize("when", ["before", "after"])
@pytest.mark.parametrize("path", ["adopt", "release_owned"])
def test_a_lock_replaced_between_reads_is_never_adopted_or_deleted(tmp_path, when, path):
    """Supervisor residual B on 78a2aeb: owner and generation come from one stable read; a lock replaced by run B
    between the reads is refused - run A never adopts B's generation and never deletes B's lock."""
    store = LocalObjectStore(tmp_path / "gcs")
    locks.acquire(store, REAL, ["fewsnet"], "run-A")
    uri = locks.lock_uri(REAL, "fewsnet")
    racing = SwapOnRead(store, uri, when)
    with pytest.raises(locks.LockConflict):
        if path == "adopt":
            locks.acquire(racing, REAL, ["fewsnet"], "run-A", adopt_own=True)
        else:
            locks.release_owned(racing, REAL, "run-A")
    assert json.loads(store.read_text(uri))["run_id"] == "run-B"                    # B's lock intact
