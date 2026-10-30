"""Per-system run locks for v2 submissions (task 10-29; R50 and the final convergence corrections).

One create-only lock object per system at ``{mode root}/locks/{system}`` (``locks/ipcch``, ``locks/fewsnet``), shared
across run ids and isolated by real/smoke namespace (each mode has its own root, R48); its content names the owner run.
A submission acquires every lock for the systems it selects, all or nothing: if any lock is held, it releases only the
locks it acquired itself (each deleted at its own generation) and the whole request is rejected, reporting the in-flight
run id - no queueing. Locks cover collection, retained-store writes and publication and are released at run end by
their owner. A lock left by a crashed run is cleared only by an explicit operations action (``clear_lock`` with the
observed owner and generation); the runtime never evicts locks automatically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from cloud.common.object_store import GenerationConflict, ObjectStore

SYSTEMS = ("ipcch", "fewsnet")


class LockAcquisitionError(RuntimeError):
    """A lock write failed for another reason (transport, permission); this submission's own locks were released."""

    def __init__(self, system: str, cause: BaseException, cleanup_failures: list[str]):
        super().__init__(f"acquiring the {system} lock failed: {type(cause).__name__}: {cause}"
                         + (f"; cleanup failures: {cleanup_failures}" if cleanup_failures else ""))
        self.system, self.cause, self.cleanup_failures = system, cause, cleanup_failures


class LockConflict(RuntimeError):
    """A selected system already has a run in progress; nothing was started."""

    def __init__(self, system: str, holder: Any, cleanup_failures: list[str] | None = None):
        super().__init__(f"{system} run in progress (lock held by {holder}); the request is rejected (R50)"
                         + (f"; cleanup failures: {cleanup_failures}" if cleanup_failures else ""))
        self.system, self.holder, self.cleanup_failures = system, holder, list(cleanup_failures or [])


@dataclass(frozen=True)
class Lock:
    system: str
    uri: str
    generation: str
    run_id: str


def lock_uri(mode_root: str, system: str) -> str:
    if system not in SYSTEMS:
        raise ValueError(f"unknown system {system!r}")
    return f"{mode_root.rstrip('/')}/locks/{system}"


def _holder(store: ObjectStore, uri: str) -> Any:
    try:
        return json.loads(store.read_text(uri)).get("run_id")
    except Exception as exc:                                  # unreadable lock content is still a held lock
        return f"unreadable lock ({type(exc).__name__})"


def _stable_holder(store: ObjectStore, uri: str) -> tuple[Any, str | None]:
    """(holder, generation) from ONE stable read: the generation before and after reading the body must be equal, so
    the owner and the generation always describe the same lock object; a lock that changed while read raises
    ``LockConflict`` (never adopted or released on a guess); an absent lock is (None, None)."""
    before = store.get_metadata(uri)
    if before is None:
        return None, None
    holder = _holder(store, uri)
    after = store.get_metadata(uri)
    if after is None or str(after.generation) != str(before.generation):
        raise LockConflict(uri.rsplit("/", 1)[-1], f"changed while read (generation {before.generation} -> "
                                                   f"{None if after is None else after.generation})")
    return holder, str(before.generation)


def acquire(store: ObjectStore, mode_root: str, systems: Iterable[str], run_id: str,
            now: datetime | None = None, adopt_own: bool = False) -> list[Lock]:
    """All selected systems' locks or none (only this submission's own acquisitions are released on failure).

    ``adopt_own``: a lock already held by THIS run (a legacy remote-update run holds its locks from admission through
    preparation, resolution and delivery) is adopted at its current generation instead of acquired twice; adopted
    locks are returned like acquired ones (released by their owner at the end) but never released on a failure here."""
    held: list[Lock] = []
    fresh: list[Lock] = []
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for system in sorted(set(systems)):
        uri = lock_uri(mode_root, system)
        body = json.dumps({"system": system, "run_id": run_id, "acquired_at": stamp}, sort_keys=True) + "\n"
        try:
            meta = store.write_text(uri, body, if_generation_match=0)
        except GenerationConflict as exc:
            try:
                holder, generation = _stable_holder(store, uri)
            except LockConflict as changed:
                raise LockConflict(system, changed.holder, release(store, fresh)) from exc
            except Exception as lookup:                   # the holder lookup failed: roll back THIS call's fresh locks
                raise LockAcquisitionError(system, lookup, release(store, fresh)) from exc
            if adopt_own and holder == run_id and generation is not None:
                held.append(Lock(system, uri, generation, run_id))   # owner and generation of the same object
                continue
            raise LockConflict(system, holder, release(store, fresh)) from exc
        except Exception as exc:                              # any other failure: release own locks, keep the cause
            raise LockAcquisitionError(system, exc, release(store, fresh)) from exc
        lock = Lock(system, uri, str(meta.generation), run_id)
        held.append(lock)
        fresh.append(lock)
    return held


def owned(store: ObjectStore, mode_root: str, run_id: str) -> list[Lock]:
    """The locks this run holds now (at their current generations)."""
    out = []
    for system in SYSTEMS:
        uri = lock_uri(mode_root, system)
        holder, generation = _stable_holder(store, uri)
        if holder == run_id:
            out.append(Lock(system, uri, generation, run_id))
    return out


def release_owned(store: ObjectStore, mode_root: str, run_id: str) -> list[str]:
    """Failure cleanup by the owner: release exactly the locks this run still holds (never another run's)."""
    return release(store, owned(store, mode_root, run_id))


def release(store: ObjectStore, locks: Iterable[Lock]) -> list[str]:
    """Delete this run's locks at their own generations, attempting every one; a lock that moved is left alone and
    every failure (moved, transport) is reported."""
    problems = []
    for lock in locks:
        try:
            store.delete(lock.uri, if_generation_match=lock.generation)
        except Exception as exc:
            problems.append(f"{lock.uri}: {type(exc).__name__}: {exc}")
    return problems


def clear_lock(store: ObjectStore, mode_root: str, system: str, *, expected_run_id: str, generation: str) -> None:
    """Operations action: remove a stale lock only when it is still exactly the observed one (owner + generation)."""
    uri = lock_uri(mode_root, system)
    holder = _holder(store, uri)
    if holder != expected_run_id:
        raise LockConflict(system, holder)
    store.delete(uri, if_generation_match=generation)
