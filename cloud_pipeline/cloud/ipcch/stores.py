"""Versioned retained stores for the IPCCH v2 runtime (task 10-29; prd.md R8, R27-R29, R41, R45, R48, R59, R62).

Every retained table lives under one namespace root and is a HEAD pointer plus immutable versions::

    <root>/<table>/HEAD.json                 {"version": n, "content": uri, "sha256": ..., "rows": ..., "record": {...}}
    <root>/<table>/versions/<n>-<uuid>.csv   create-only (if_generation_match=0), unique per write attempt

``read``/``head`` return content and HEAD generation from one consistent snapshot (the HEAD generation is read before
and after; a change in between refuses). ``commit`` writes a new uniquely named version create-only and then moves HEAD
with a compare-and-swap on the generation of the snapshot the caller read. A conflict raises ``GenerationConflict`` and
is never retried here; a failure before or during the HEAD move leaves the previous version current, and an orphaned
version object is preserved as evidence without blocking the next commit. Versions are never deleted. HEAD content
must lie under this root's own ``<table>/versions/`` (mode isolation, R48).

Namespaces are isolated by mode (R48): a real store root and a smoke store root are distinct, and a store opened for
one mode refuses a root of the other. The acceptance manifest (R45) is itself a versioned table of records
``name, sha256, source, acceptor, accepted_at, kind`` (``delivered`` | ``runtime``); a historical input is usable in real
generation only with a matching record."""

from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd

from cloud.common.object_store import GenerationConflict, ObjectStore

MODES = ("smoke", "real")
ACCEPTANCE_TABLE = "acceptance_manifest"
ACCEPTANCE_COLUMNS = ("name", "sha256", "source", "acceptor", "accepted_at", "kind")
ACCEPTANCE_KINDS = ("delivered", "runtime")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class StoreError(RuntimeError):
    """A retained-store contract was violated; the store is unchanged."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def frame_to_csv(frame: pd.DataFrame) -> str:
    return frame.to_csv(index=False, lineterminator="\n", float_format=None)


def csv_to_frame(text: str, dtypes: Mapping[str, Any] | None = None) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(text), dtype=dtypes or None, keep_default_na=False, na_values=[""],
                       float_precision="round_trip")


@dataclass(frozen=True)
class StoreRoot:
    """One mode's isolated namespace root, e.g. gs://bucket/ipcch-v2/real or gs://bucket/ipcch-v2/smoke."""

    mode: str
    uri: str

    def __post_init__(self):
        if self.mode not in MODES:
            raise StoreError(f"store mode must be one of {MODES}")
        if not self.uri.startswith("gs://") or self.uri.endswith("/"):
            raise StoreError("store root must be a gs:// prefix without a trailing slash")
        if self.uri.rstrip("/").rsplit("/", 1)[-1] != self.mode:
            raise StoreError(f"a {self.mode} store root must end in /{self.mode} (mode isolation, R48)")


class VersionedTable:
    def __init__(self, store: ObjectStore, root: StoreRoot, table: str):
        if not table or "/" in table:
            raise StoreError("table names are single path segments")
        self.store, self.root, self.table = store, root, table
        self.head_uri = f"{root.uri}/{table}/HEAD.json"

    def head(self) -> tuple[dict[str, Any] | None, str]:
        """(HEAD record or None, HEAD generation; "0" when absent) from one stable snapshot: the generation is read
        before and after the HEAD text and must not change in between."""
        before = self.store.get_metadata(self.head_uri)
        if before is None:
            return None, "0"
        text = self.store.read_text(self.head_uri)
        after = self.store.get_metadata(self.head_uri)
        if after is None or after.generation != before.generation:
            raise StoreError(f"{self.table} HEAD changed while it was read; nothing was used")
        head = json.loads(text)
        prefix = f"{self.root.uri}/{self.table}/versions/"
        content = head.get("content")
        if not isinstance(content, str) or not content.startswith(prefix) or "/" in content[len(prefix):]:
            raise StoreError(f"{self.table} HEAD content {content!r} is outside {prefix} (R48)")
        return head, before.generation

    def read(self, dtypes: Mapping[str, Any] | None = None) -> tuple[pd.DataFrame | None, dict[str, Any] | None, str]:
        """(frame, HEAD record, HEAD generation) of one consistent snapshot; content verified by its HEAD sha256."""
        head, generation = self.head()
        if head is None:
            return None, None, generation
        text = self.store.read_text(head["content"])
        if sha256_text(text) != head["sha256"]:
            raise StoreError(f"{self.table} version {head['version']} content differs from its HEAD sha256")
        return csv_to_frame(text, dtypes), head, generation

    def commit(self, frame: pd.DataFrame, record: Mapping[str, Any], *, expected_generation: str) -> dict[str, Any]:
        """Write the next immutable version and CAS the HEAD from ``expected_generation`` (no retry)."""
        head, generation = self.head()
        if generation != str(expected_generation):
            raise GenerationConflict(f"{self.table} HEAD moved ({generation} != {expected_generation}); not retried")
        version = 1 if head is None else int(head["version"]) + 1
        text = frame_to_csv(frame)
        content = f"{self.root.uri}/{self.table}/versions/{version:06d}-{uuid.uuid4().hex}.csv"
        self.store.write_text(content, text, if_generation_match=0)
        new = {"version": version, "content": content, "sha256": sha256_text(text), "rows": int(len(frame)),
               "previous_version": None if head is None else head["version"], "record": dict(record)}
        self.store.write_text(self.head_uri, json.dumps(new, sort_keys=True, default=str), if_generation_match=generation)
        return new


class AcceptanceManifest:
    """R45 acceptance records kept with the retained store of one mode."""

    def __init__(self, store: ObjectStore, root: StoreRoot):
        self.table = VersionedTable(store, root, ACCEPTANCE_TABLE)

    def snapshot(self) -> tuple[pd.DataFrame, str]:
        frame, _, generation = self.table.read({c: str for c in ACCEPTANCE_COLUMNS})
        return (frame if frame is not None else pd.DataFrame(columns=list(ACCEPTANCE_COLUMNS))), generation

    def records(self) -> pd.DataFrame:
        return self.snapshot()[0]

    def require(self, name: str, sha256: str) -> dict[str, Any]:
        """The record accepting ``name`` at ``sha256``; refuses a missing record or a checksum mismatch."""
        rec = self.records()
        rows = rec[rec["name"] == name]
        if rows.empty:
            raise StoreError(f"{name}: no acceptance record (R45); not usable in real generation")
        if not (rows["sha256"] == sha256).any():
            raise StoreError(f"{name}: sha256 {sha256} differs from every acceptance record (R45)")
        return rows[rows["sha256"] == sha256].iloc[-1].to_dict()

    def append(self, entries: list[Mapping[str, Any]]) -> dict[str, Any]:
        for e in entries:
            if set(e) != set(ACCEPTANCE_COLUMNS) or e["kind"] not in ACCEPTANCE_KINDS:
                raise StoreError(f"acceptance entries need exactly {ACCEPTANCE_COLUMNS} and a known kind: {e}")
            if any(not isinstance(e[k], str) or not e[k].strip() for k in ("name", "source", "acceptor")):
                raise StoreError(f"acceptance entries need non-empty name, source and acceptor: {e}")
            if not isinstance(e["sha256"], str) or _SHA256.fullmatch(e["sha256"]) is None:
                raise StoreError(f"acceptance sha256 must be a lowercase hex digest: {e}")
            if not isinstance(e["accepted_at"], str) or _DATE.fullmatch(e["accepted_at"]) is None:
                raise StoreError(f"acceptance date must be YYYY-MM-DD: {e}")
        current, generation = self.snapshot()
        frame = pd.concat([current, pd.DataFrame(entries, columns=list(ACCEPTANCE_COLUMNS))], ignore_index=True)
        return self.table.commit(frame, {"appended": len(entries)}, expected_generation=generation)
