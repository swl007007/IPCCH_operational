"""Event binding, duplicate handling and generation-CAS release for the October delivery (CP4).

Composition only; no lease/recovery service (design section 9, G3):

* ``request_from_event``: a Cloud Storage ``object.v1.finalized`` event selects work only for
  ``gs://<bucket>/requests/<run_id>/run_manifest.json``; the event's exact generation is kept
  (normalised to a decimal string). Report/source writes are ignored.
* ``run_once``: create-only ``runs/<run_id>/_RUN_ACQUIRED`` bound to the request
  ``{uri, generation, sha256}``. The identical request again is a duplicate: the original
  status is returned and nothing is recomputed. Different content under one run ID is a
  conflict. A failed or abandoned run is never resumed; a retry uses a new run ID.
* ``publish``: validation first, then an immutable release record (create-only), then the
  pointer last with ``if_generation_match`` = the request's expected pointer generation.
  Any failure or conflict leaves the accepted pointer untouched.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Any

from cloud.common.object_store import GenerationConflict, ObjectStore
from cloud.orchestrator.delivery_manifest import _REQUEST_PATH_RE, LEGACY_RELEASE_NAMESPACE

ABANDONED_OR_RUNNING = "running_or_abandoned"


class RunConflict(RuntimeError):
    """A run ID is already bound to a different request."""


class ReleaseConflict(RuntimeError):
    """The release pointer moved since the request was prepared; nothing was replaced."""


def request_from_event(data: Mapping[str, Any]) -> dict[str, str] | None:
    """Exact request reference from a Storage event, or None for any other object."""
    uri = f"gs://{data.get('bucket', '')}/{data.get('name', '')}"
    match = _REQUEST_PATH_RE.fullmatch(uri)
    if match is None:
        return None
    generation = data.get("generation")
    if isinstance(generation, bool) or re.fullmatch(r"[1-9][0-9]*", str(generation)) is None:
        raise ValueError(f"event for {uri} lacks an exact positive generation: {generation!r}")
    return {"uri": uri, "generation": str(int(generation)), "run_id": match.group(1)}


def _run_uri(root_uri: str, run_id: str, name: str) -> str:
    return f"{root_uri.rstrip('/')}/runs/{run_id}/{name}"


def run_once(store: ObjectStore, root_uri: str, *, run_id: str, request_ref: Mapping[str, str],
             compute: Callable[[], Mapping[str, Any]]) -> dict[str, Any]:
    """Execute ``compute`` at most once per request identity; return the run status."""
    identity = {"run_id": run_id, "request": {key: str(request_ref[key]) for key in ("uri", "generation", "sha256")}}
    sentinel = _run_uri(root_uri, run_id, "_RUN_ACQUIRED")
    status_uri = _run_uri(root_uri, run_id, "run_status.json")
    try:
        store.write_text(sentinel, json.dumps(identity, sort_keys=True) + "\n", if_generation_match=0)
    except GenerationConflict:
        if json.loads(store.read_text(sentinel)) != identity:
            raise RunConflict(f"run_id {run_id} is bound to a different request; use a new run ID") from None
        original = {"duplicate": True, "status_uri": status_uri, "acquired_uri": sentinel}
        if store.get_metadata(status_uri) is None:  # still running, or abandoned: never resumed in place
            return {"run_id": run_id, "status": ABANDONED_OR_RUNNING, **original}
        return {**json.loads(store.read_text(status_uri)), **original}
    try:
        result = dict(compute())
        status = {"run_id": run_id, "status": "succeeded", "request": identity["request"], **result}
    except Exception as exc:  # recorded as the run's terminal state, then re-raised
        status = {"run_id": run_id, "status": "failed", "request": identity["request"],
                  "error": f"{type(exc).__name__}: {exc}"}
        store.write_text(status_uri, json.dumps(status, indent=2, sort_keys=True) + "\n", if_generation_match=0)
        raise
    store.write_text(status_uri, json.dumps(status, indent=2, sort_keys=True) + "\n", if_generation_match=0)
    return {**status, "duplicate": False, "status_uri": status_uri}


def _record_conflict(store: ObjectStore, root_uri: str, run_id: str, pointer_uri: str, expected, actual, *,
                     stage: str, release_record: str | None = None) -> None:
    """Persist the conflict (create-only) beside the run status, then raise; nothing is replaced."""
    record = {"run_id": run_id, "status": "release_conflict", "pointer_uri": pointer_uri, "stage": stage,
              "expected_pointer_generation": str(expected), "actual_pointer_generation": str(actual),
              "unpublished_release_record": release_record}
    uri = _run_uri(root_uri, run_id, "release_conflict.json")
    store.write_text(uri, json.dumps(record, indent=2, sort_keys=True) + "\n", if_generation_match=0)
    raise ReleaseConflict(f"pointer generation is {actual}, request expected {expected}; recorded at {uri}")


def publish(store: ObjectStore, root_uri: str, *, run_id: str, namespace: str, expected_pointer_generation: str,
            release_record: Mapping[str, Any], validate: Callable[[], None]) -> dict[str, str]:
    """Validate, write the immutable release record, then move the pointer by generation CAS."""
    if namespace == LEGACY_RELEASE_NAMESPACE:
        raise ValueError("the legacy IPCCH-only release root is preserved, never republished")
    validate()  # raises before anything is written: the accepted pointer stays as it is
    base = f"{root_uri.rstrip('/')}/{namespace}"
    pointer_uri = f"{base}/current.json"
    current = store.get_metadata(pointer_uri)
    if (current.generation if current else "0") != str(expected_pointer_generation):
        _record_conflict(store, root_uri, run_id, pointer_uri, expected_pointer_generation,
                         current.generation if current else "0", stage="precheck")
    record_uri = f"{base}/releases/{run_id}/release.json"
    record = store.write_text(record_uri, json.dumps(dict(release_record), indent=2, sort_keys=True) + "\n",
                              if_generation_match=0)
    pointer = {"run_id": run_id, "release_record": record_uri, "release_record_generation": record.generation}
    try:
        moved = store.write_text(pointer_uri, json.dumps(pointer, indent=2, sort_keys=True) + "\n",
                                 if_generation_match=int(expected_pointer_generation))
    except GenerationConflict:  # a concurrent publisher won; its pointer is preserved
        current = store.get_metadata(pointer_uri)
        _record_conflict(store, root_uri, run_id, pointer_uri, expected_pointer_generation,
                         current.generation if current else "0", stage="pointer_write", release_record=record_uri)
    return {"pointer_uri": pointer_uri, "pointer_generation": moved.generation, "release_record": record_uri}
