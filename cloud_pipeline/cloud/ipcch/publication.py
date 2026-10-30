"""v2 publication core: the single current pointer, per-system release members, activation and candidates (task 10-29;
R17, R18, R37, R39, R46, R47, R63, R66 and the final convergence corrections).

* ``read_current``: one stable read of ``{mode root}/{namespace}/current.json`` (generation before/after) and of the
  release record it names at the generation it records. The snapshot's generation is the CAS precondition of the
  publication that inherits from it: inherited members are exactly those of the release bound to the expected
  generation; a moved pointer is a conflict, never a rebase (FCC).
* Release record v2 (``fewsnet-ipcch-release-v2``): ``systems.{ipcch,fewsnet}`` each carry their own member provenance
  (contract, execution month, feature origin, targets/leads, mode, package identity, delivery member refs, source run)
  - a published member keeps its source run's months without relabelling (R63); ``activation`` (R37/R46) is copied
  from the bound snapshot by every current publication and set once, by the first successful REAL current publication
  of a new-contract IPCCH member; it is never cleared.
* ``publish``: candidate (R66) writes an immutable create-only candidate record under the namespace and never moves the
  pointer, never activates and is not promotable; current re-checks R39 against the bound snapshot, builds the record
  (new members + inherited members) and moves the pointer through ``delivery_run.publish`` (create-only release
  record, generation CAS, conflict recorded, no retry). A conflict returns ``publication_failed`` with the reason; the
  generated batch and delivery stay reported by the caller (FCC).
Smoke publishes under its own root (R36/R48); production paths are unchanged.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from cloud.common.object_store import GenerationConflict, ObjectStore
from cloud.orchestrator import delivery_run

RELEASE_SCHEMA = "fewsnet-ipcch-release-v2"
IPCCH_CONTRACT = "ipcch-validity-h2h8h14-v2"
LEGACY_CONTRACT = "legacy-v1"
LEGACY_IPCCH_MEMBER = "ipcch-legacy-scoring"          # legacy-format IPCCH member in a v2 record; never activates
SYSTEMS = ("ipcch", "fewsnet")


class PublicationRefused(RuntimeError):
    """A publication rule refused the release before anything was written (the pointer is unchanged)."""


def pointer_uri(root_uri: str, namespace: str) -> str:
    return f"{root_uri.rstrip('/')}/{namespace}/current.json"


def read_current(store: ObjectStore, root_uri: str, namespace: str, *,
                 allow_missing_legacy_record: bool = False) -> dict[str, Any]:
    """{"generation": str ("0" = none), "pointer": dict|None, "record": dict|None} from one stable read.

    A pre-generation legacy pointer (no ``release_record_generation``) is read consistently: its record is read stably
    at the generation it has now (records are create-only) and must be a legacy record - a v2 or activated record is
    only trusted when the pointer pins its generation, so activation is never inferred from an unpinned record. A
    missing legacy record is refused, except for callers that only gate on it (``allow_missing_legacy_record``: the
    legacy v1 guards), which then see no record, hence no members to inherit and no activation."""
    uri = pointer_uri(root_uri, namespace)
    before = store.get_metadata(uri)
    if before is None:
        return {"generation": "0", "pointer": None, "record": None}
    pointer = json.loads(store.read_text(uri))
    after = store.get_metadata(uri)
    if after is None or after.generation != before.generation:
        raise GenerationConflict(f"{uri} moved while it was read")
    if "release_record_generation" not in pointer:
        return _legacy_snapshot(store, str(before.generation), pointer, allow_missing_legacy_record)
    rec_uri, want = pointer["release_record"], str(pointer["release_record_generation"])
    rec_before = store.get_metadata(rec_uri)
    if rec_before is None or str(rec_before.generation) != want:
        raise PublicationRefused(f"release record {rec_uri} is not the generation the pointer names")
    text = store.read_text(rec_uri)
    rec_after = store.get_metadata(rec_uri)                    # stable read: the bytes are those of the named generation
    if rec_after is None or str(rec_after.generation) != want:
        raise PublicationRefused(f"release record {rec_uri} changed while it was read; nothing was used")
    return {"generation": str(before.generation), "pointer": pointer, "record": json.loads(text)}


def _legacy_snapshot(store: ObjectStore, generation: str, pointer: Mapping[str, Any], allow_missing: bool) -> dict[str, Any]:
    rec_uri = pointer.get("release_record")
    meta = store.get_metadata(rec_uri) if rec_uri else None
    if meta is None:
        if allow_missing:
            return {"generation": generation, "pointer": dict(pointer), "record": None, "legacy_pointer": True,
                    "record_missing": True}
        raise PublicationRefused(f"legacy pointer names release record {rec_uri} which does not exist")
    text = store.read_text(rec_uri)
    again = store.get_metadata(rec_uri)
    if again is None or str(again.generation) != str(meta.generation):
        raise PublicationRefused(f"release record {rec_uri} changed while it was read; nothing was used")
    record = json.loads(text)
    if record.get("schema") == RELEASE_SCHEMA or record.get("activation"):
        raise PublicationRefused(f"{rec_uri} is a v2/activated release record named without its generation; refused")
    return {"generation": generation, "pointer": dict(pointer), "record": record, "legacy_pointer": True,
            "record_generation": str(meta.generation)}


def members(record: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Per-system members of a release record (v2 records carry them; a legacy v1 record is one-origin for both)."""
    if record is None:
        return {}
    if record.get("schema") == RELEASE_SCHEMA:
        return {s: dict(m) for s, m in record["systems"].items()}
    scored = record.get("execution", {}).get("scored_systems", list(SYSTEMS))
    inherited = record.get("execution", {}).get("inherited_systems", [])
    return {s: {"contract": LEGACY_CONTRACT, "origin_month": record.get("origin_month"), "source_run_id": record.get("run_id"),
                "delivery": {"manifest": record.get("manifest")}, "archive": record.get("archive"),
                "inherited_in_legacy_record": s in inherited}
            for s in (*scored, *inherited) if s in SYSTEMS}


def activation(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    return None if record is None else record.get("activation")


def ipcch_execution_month(record: Mapping[str, Any] | None) -> str | None:
    """R39 comparison month: a new-contract member's execution month; a legacy release's origin_month (prd FCC note)."""
    m = members(record).get("ipcch")
    if not m:
        return None
    return m.get("execution_month") if m.get("contract") == IPCCH_CONTRACT else m.get("origin_month")


def build_record(*, run_id: str, request_ref: Mapping[str, str], mode: str, snapshot: Mapping[str, Any],
                 new_members: Mapping[str, Mapping[str, Any]], delivery: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    """The v2 release record: new members for the executed systems, every other member inherited unchanged from the
    bound snapshot, activation carried forward (set on the first real new-contract IPCCH current publication)."""
    current = members(snapshot["record"])
    systems = {}
    for s in SYSTEMS:
        if s in new_members:
            systems[s] = {**new_members[s], "published_by_run": run_id}
        elif s in current:                                 # unchanged member; the marker records THIS inheritance
            systems[s] = {**{k: v for k, v in current[s].items() if k != "inherited_from_pointer_generation"},
                          "inherited_from_pointer_generation": snapshot["generation"]}
    act = activation(snapshot["record"])
    new_ipcch = new_members.get("ipcch", {})
    if act is None and mode == "real" and new_ipcch.get("contract") == IPCCH_CONTRACT:
        act = {"contract": IPCCH_CONTRACT, "activated_by_run": run_id,
               "execution_month": new_ipcch.get("execution_month"), "at": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
    return {"schema": RELEASE_SCHEMA, "run_id": run_id, "request": dict(request_ref), "mode": mode, "systems": systems,
            "activation": act, "delivery": dict(delivery),
            "previous": {"pointer_generation": snapshot["generation"],
                         "release_record": (snapshot["pointer"] or {}).get("release_record")}}


def publish(store: ObjectStore, root_uri: str, *, run_id: str, namespace: str, publication: str, mode: str,
            expected_pointer_generation: str, request_ref: Mapping[str, str], new_members: Mapping[str, Mapping[str, Any]],
            delivery: Mapping[str, Any], verify_delivery: Callable[[Mapping[str, Any], Mapping[str, Any]], None],
            now: datetime | None = None) -> dict[str, Any]:
    """Candidate or current publication of the executed systems' members (see module docstring).

    ``verify_delivery(snapshot, record)`` is REQUIRED (no no-op default): it verifies the actual delivery - every
    member's artifacts, the three IPCCH horizons, inherited members' hashes and package identities against the bound
    snapshot - and raises before any record or pointer write."""
    now = now or datetime.now(timezone.utc)
    if publication not in ("candidate", "current"):
        raise PublicationRefused(f"publication must be candidate or current, got {publication!r}")
    if not callable(verify_delivery):
        raise PublicationRefused("a delivery verifier is required before any publication write")
    wrong = sorted(s for s, m in new_members.items() if m.get("mode") != mode)
    if wrong:
        raise PublicationRefused(f"new members {wrong} carry a mode other than the run's {mode!r} (R36)")
    if "ipcch" in new_members and new_members["ipcch"].get("contract") not in (IPCCH_CONTRACT, LEGACY_IPCCH_MEMBER):
        raise PublicationRefused("a new IPCCH member is the new contract or a legacy-format (pre-activation) member")
    if (new_members.get("ipcch", {}).get("contract") == IPCCH_CONTRACT
            and sorted(new_members["ipcch"].get("model_horizons", [])) != [2, 8, 14]):
        raise PublicationRefused("an IPCCH member publishes all three horizons H2/H8/H14 together or nothing (R18)")
    snapshot = read_current(store, root_uri, namespace)
    if publication == "candidate":
        record = build_record(run_id=run_id, request_ref=request_ref, mode=mode, snapshot=snapshot,
                              new_members=new_members, delivery=delivery, now=now)
        record["activation"] = activation(snapshot["record"])             # a candidate never activates (R66)
        record["publication"] = "candidate"
        verify_delivery(snapshot, record)
        uri = f"{root_uri.rstrip('/')}/{namespace}/candidates/{run_id}/candidate.json"
        meta = store.write_text(uri, json.dumps(record, indent=2, sort_keys=True) + "\n", if_generation_match=0)
        return {"status": "candidate_written", "candidate_record": uri, "generation": meta.generation,
                "pointer_generation": snapshot["generation"]}
    if snapshot["generation"] != str(expected_pointer_generation):
        return _failed(store, root_uri, run_id, namespace, expected_pointer_generation, snapshot["generation"], "precheck")
    month = new_members.get("ipcch", {}).get("execution_month")
    current_month = ipcch_execution_month(snapshot["record"])
    if mode == "real" and month and current_month and month < current_month:
        raise PublicationRefused(f"IPCCH M {month} is earlier than the current release's {current_month} (R39 recheck)")
    record = build_record(run_id=run_id, request_ref=request_ref, mode=mode, snapshot=snapshot, new_members=new_members,
                          delivery=delivery, now=now)
    record["publication"] = "current"
    try:
        out = delivery_run.publish(store, root_uri, run_id=run_id, namespace=namespace,
                                   expected_pointer_generation=str(expected_pointer_generation), release_record=record,
                                   validate=lambda: verify_delivery(snapshot, record))
    except delivery_run.ReleaseConflict as exc:                           # no retry, no rescoring, no rebase
        return {"status": "publication_failed", "reason": str(exc), "stage": "pointer_write"}
    return {"status": "published", **out, "activation": record["activation"]}


def _failed(store, root_uri, run_id, namespace, expected, actual, stage) -> dict[str, Any]:
    try:
        delivery_run._record_conflict(store, root_uri, run_id, pointer_uri(root_uri, namespace), expected, actual,
                                      stage=stage)
    except delivery_run.ReleaseConflict as exc:
        return {"status": "publication_failed", "reason": str(exc), "stage": stage}
    return {"status": "publication_failed", "stage": stage}
