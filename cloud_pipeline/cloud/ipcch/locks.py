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


class LockConflict(RuntimeError):
    """A selected system already has a run in progress; nothing was started."""

    def __init__(self, system: str, holder: Any):
        super().__init__(f"{system} run in progress (lock held by {holder}); the request is rejected (R50)")
        self.system, self.holder = system, holder


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


def acquire(store: ObjectStore, mode_root: str, systems: Iterable[str], run_id: str,
            now: datetime | None = None) -> list[Lock]:
    """All selected systems' locks or none (only this submission's own acquisitions are released on failure)."""
    held: list[Lock] = []
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for system in sorted(set(systems)):
        uri = lock_uri(mode_root, system)
        body = json.dumps({"system": system, "run_id": run_id, "acquired_at": stamp}, sort_keys=True) + "\n"
        try:
            meta = store.write_text(uri, body, if_generation_match=0)
        except GenerationConflict:
            holder = _holder(store, uri)
            release(store, held)
            raise LockConflict(system, holder) from None
        held.append(Lock(system, uri, str(meta.generation), run_id))
    return held


def release(store: ObjectStore, locks: Iterable[Lock]) -> list[str]:
    """Delete this run's locks at their own generations; a lock that moved is left alone and reported."""
    problems = []
    for lock in locks:
        try:
            store.delete(lock.uri, if_generation_match=lock.generation)
        except GenerationConflict as exc:
            problems.append(f"{lock.uri}: {exc}")
    return problems


def clear_lock(store: ObjectStore, mode_root: str, system: str, *, expected_run_id: str, generation: str) -> None:
    """Operations action: remove a stale lock only when it is still exactly the observed one (owner + generation)."""
    uri = lock_uri(mode_root, system)
    holder = _holder(store, uri)
    if holder != expected_run_id:
        raise LockConflict(system, holder)
    store.delete(uri, if_generation_match=generation)
