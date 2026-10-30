"""Concrete Earth Engine / Cloud Storage transport for the IPCCH climate providers (task 10-29; R1, R13, R43, R49).

``EETransport`` implements both provider boundaries — ``climate_ee.EEBackend`` (raster families) and
``climate_tables.TableBackend`` (S2E3/S2C3 asset tables) — on the existing production patterns:

* ``image_times``: the existing ``CloudSourceAcquirer._list_images`` single listing call (time_start and image id from
  one query). Unlike ``gee_published_months`` it accepts several images per month (daily / 3-hourly collections); every
  entry must be a numeric time and an image id of that collection, else the check fails (never "unpublished").
* ``missing_assets``: definitive absence only. ``ee.data.getAsset`` success -> present. Earth Engine reports a missing
  asset and an unreadable one with the same "does not exist or does not allow this operation" message, so that message
  is resolved by listing the asset's parent: a successful listing that omits the id -> absent; listed but unreadable,
  or a parent that cannot be listed -> ``EETransportError``. Any other error (403/permission, authentication, quota,
  timeout, transport) -> ``EETransportError`` at once. Callers therefore see "absent" only when it is definitive, and
  ``climate_tables`` never reports an inaccessible current table as ordinary unavailability.
* ``export_table``: the run/description task record is RESERVED create-only before submission (a duplicate is refused
  without a second task), then one ``Export.table.toCloudStorage`` CSV under a run-scoped prefix that must be empty;
  the task id is persisted (if that fails the started task is cancelled); an IPCCH wait loop (the shared FEWS
  ``_wait_for_ee_task`` is untouched) bounds every sleep by the remaining budget (timeout and authorization deadline
  minus the cleanup reserve), cancels the task on timeout and records each terminal state; the result is the single
  exported object pinned as ``uri#generation``.
* ``read_table``: that exact generation (``GcsPinnedReader``), sha256 recorded in ``receipts``.
* ``read_asset_table``: ``ee.data.computeFeatures`` (PANDAS_DATAFRAME, paged by the client) of the asset's properties
  without geometry; integral ``admin_code`` values are normalised to canonical integer text; any failure blocks.

Every failure is an ``EETransportError`` (a ``ClimateProcessingFailure``): it blocks generation and is never
reclassified as source unavailability. Live execution needs an Earth Engine project and is deferred (no EE compute is
run by the tests, which drive this class through fakes of the ``ee``/storage APIs).
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import pandas as pd

from cloud.common.object_store import ObjectStore
from cloud.ipcch.climate import ClimateProcessingFailure

_AMBIGUOUS = re.compile(r"does not exist or (does not|doesn't) allow", re.IGNORECASE)


class EETransportError(ClimateProcessingFailure):
    """An Earth Engine / Cloud Storage operation failed or was ambiguous; generation stops (never 'unavailable')."""


def _parent(asset_id: str) -> str:
    if "/" not in asset_id:
        raise EETransportError(f"asset id {asset_id!r} has no parent")
    return asset_id.rsplit("/", 1)[0]


@dataclass
class EETransport:
    ee: Any                                   # initialised earthengine-api module
    client: Any                               # google-cloud-storage client
    store: ObjectStore
    output_root: str                          # gs://bucket/prefix of this system's run exports
    run_id: str
    timeout_seconds: int = 21600
    poll_seconds: int = 60
    deadline_utc: datetime | None = None
    cleanup_reserve_seconds: int = 900
    clock: Callable[[], datetime] | None = None
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.monotonic
    receipts: list = field(default_factory=list)
    _children: dict = field(default_factory=dict)
    _acquirer: Any = None

    def __post_init__(self):
        from cloud.orchestrator.prepare import CloudSourceAcquirer

        if not self.output_root.startswith("gs://") or not re.fullmatch(r"[A-Za-z0-9_.-]+", self.run_id or ""):
            raise EETransportError("output_root must be gs:// and run_id a plain identifier")
        self.output_root = self.output_root.rstrip("/")
        self.clock = self.clock or (lambda: datetime.now(timezone.utc))
        self._acquirer = CloudSourceAcquirer(ee=self.ee, client=self.client, http=None, store=self.store,
                                             output_root=self.output_root, timeout_seconds=self.timeout_seconds,
                                             poll_seconds=self.poll_seconds, deadline_utc=self.deadline_utc,
                                             cleanup_reserve_seconds=self.cleanup_reserve_seconds, clock=self.clock)

    # ------------------------------------------------------------------ availability

    def image_times(self, collection: str, band: str, start: str, end: str) -> list[int]:
        """``system:time_start`` (ms) of every image of ``collection`` in [start, end) (``band`` is part of the
        provider contract; availability is per image)."""
        try:
            pairs = list(self._acquirer._list_images(collection, start, end))
        except Exception as exc:
            raise EETransportError(f"{collection} availability listing failed: {type(exc).__name__}: {exc}") from exc
        times = []
        for entry in pairs:
            millis, image_id = entry if isinstance(entry, (tuple, list)) and len(entry) == 2 else (None, None)
            if not isinstance(millis, (int, float)) or isinstance(millis, bool) or not isinstance(image_id, str) \
                    or not image_id.startswith(collection + "/"):
                raise EETransportError(f"{collection} returned malformed image entry {entry!r}")
            times.append(int(millis))
        self.receipts.append({"kind": "image_times", "collection": collection, "start": start, "end": end,
                              "images": len(times)})
        return sorted(times)

    def _listing(self, parent: str) -> set[str]:
        if parent not in self._children:
            try:
                listed = self.ee.data.listAssets({"parent": parent})
            except Exception as exc:
                raise EETransportError(f"cannot list {parent} to resolve an ambiguous asset lookup "
                                       f"({type(exc).__name__}: {exc}); not treated as absent") from exc
            names = set()
            for a in (listed or {}).get("assets", []):
                names.update(v for v in (a.get("name"), a.get("id")) if isinstance(v, str))
            self._children[parent] = names
        return self._children[parent]

    def missing_assets(self, asset_ids: list[str]) -> list[str]:
        """The ids that DEFINITIVELY do not exist (see module docstring); anything ambiguous raises."""
        absent = []
        for asset_id in asset_ids:
            try:
                info = self.ee.data.getAsset(asset_id)
            except Exception as exc:
                if not _AMBIGUOUS.search(str(exc)):
                    raise EETransportError(f"{asset_id}: metadata read failed ({type(exc).__name__}: {exc}); "
                                           f"not treated as absent") from exc
                if asset_id in self._listing(_parent(asset_id)):
                    raise EETransportError(f"{asset_id} exists but is not readable ({exc}); not treated as absent") from exc
                absent.append(asset_id)
                continue
            if not isinstance(info, dict) or not info:
                raise EETransportError(f"{asset_id}: malformed metadata {info!r}")
        self.receipts.append({"kind": "missing_assets", "checked": len(asset_ids), "absent": list(absent)})
        return absent

    # ------------------------------------------------------------------ exports

    def _remaining_seconds(self) -> float:
        if self.deadline_utc is None:
            return float("inf")
        return (self.deadline_utc - self.clock()).total_seconds() - self.cleanup_reserve_seconds

    def _record(self, uri: str, record: dict, generation) -> str:
        return self.store.write_text(uri, json.dumps(record, sort_keys=True) + "\n",
                                     if_generation_match=generation).generation

    def _wait(self, task, description: str, record_uri: str, record: dict, generation: str) -> dict:
        """IPCCH wait (the shared FEWS ``_wait_for_ee_task`` is unchanged): every sleep is bounded by the remaining
        budget (task timeout and authorization deadline minus the cleanup reserve); on timeout the task is cancelled
        and the cancellation recorded; FAILED/CANCELLED are recorded. Any of these is a processing failure."""
        budget_end = self.monotonic() + min(self.timeout_seconds, max(0.0, self._remaining_seconds()))
        while True:
            try:
                status = task.status()
            except Exception as exc:
                status = {"state": "STATUS_ERROR", "error": f"{type(exc).__name__}: {exc}"}
            state = status.get("state")
            if state == "COMPLETED":
                return status
            if state in {"FAILED", "CANCELLED"}:
                self._record(record_uri, {**record, "state": state, "status": status}, generation)
                raise EETransportError(f"export {description} {state}: {status}")
            left = budget_end - self.monotonic()
            if left <= 0:
                cancel = "cancelled"
                try:
                    task.cancel()
                except Exception as exc:                 # recorded; the task id is persisted for operations cleanup
                    cancel = f"cancel_failed: {type(exc).__name__}: {exc}"
                self._record(record_uri, {**record, "state": "timeout", "cancel": cancel, "status": status}, generation)
                raise EETransportError(f"export {description} timed out ({status}); {cancel}")
            self.sleep(min(self.poll_seconds, left))

    def export_table(self, collection: Any, selectors: list[str], description: str) -> str:
        """Reserve -> submit -> persist id -> bounded wait -> pin the single CSV object (see module docstring)."""
        from cloud.batch.evi_service import _parse_gcs_uri

        if not re.fullmatch(r"[A-Za-z0-9_.-]+", description):
            raise EETransportError(f"export description {description!r} is not a plain identifier")
        base = f"{self.output_root}/ipcch_exports/{self.run_id}"
        prefix_uri, record_uri = f"{base}/tables/{description}", f"{base}/tasks/{description}.json"
        if self._remaining_seconds() <= 0:
            raise EETransportError("authorization deadline cleanup reserve reached; no new exports")
        record = {"run_id": self.run_id, "description": description, "prefix": prefix_uri, "selectors": list(selectors),
                  "task_id": None, "state": "reserved"}
        try:                                             # create-only reservation BEFORE any submission
            generation = self._record(record_uri, record, 0)
        except Exception as exc:
            raise EETransportError(f"export {description} already reserved for run {self.run_id} ({exc}); "
                                   f"not submitted again") from exc
        if self.store.list(prefix_uri):
            raise EETransportError(f"export prefix already has objects: {prefix_uri} (exports are never reused)")
        bucket, blob_prefix = _parse_gcs_uri(prefix_uri)
        try:
            task = self.ee.batch.Export.table.toCloudStorage(
                collection=collection, description=f"{self.run_id}_{description}"[:100], bucket=bucket,
                fileNamePrefix=blob_prefix, fileFormat="CSV", selectors=list(selectors))
            task.start()
        except Exception as exc:
            self._record(record_uri, {**record, "state": "submit_failed", "error": f"{type(exc).__name__}: {exc}"}, generation)
            raise EETransportError(f"export {description} could not start: {type(exc).__name__}: {exc}") from exc
        record = {**record, "task_id": getattr(task, "id", None), "state": "submitted"}
        try:
            generation = self._record(record_uri, record, generation)
        except Exception as exc:                         # an untracked task must not keep running
            try:
                task.cancel()
                cancel = "cancelled"
            except Exception as cexc:
                cancel = f"cancel_failed: {cexc}"
            raise EETransportError(f"export {description}: task id could not be persisted ({exc}); {cancel}") from exc
        self._wait(task, description, record_uri, record, generation)
        objects = sorted(self.store.list(prefix_uri))
        if len(objects) != 1 or not objects[0].endswith(".csv"):
            raise EETransportError(f"export {description} produced {objects}, expected exactly one CSV object")
        meta = self.store.get_metadata(objects[0])
        if meta is None:
            raise EETransportError(f"export object {objects[0]} vanished before it was pinned")
        self._record(record_uri, {**record, "state": "completed", "uri": objects[0], "generation": meta.generation},
                     generation)
        self.receipts.append({"kind": "export", **record, "uri": objects[0], "generation": meta.generation})
        return f"{objects[0]}#{meta.generation}"

    def read_table(self, ref: str) -> pd.DataFrame:
        from cloud.orchestrator.prepare import GcsPinnedReader

        uri, _, generation = ref.rpartition("#")
        if not uri or not generation.isdigit():
            raise EETransportError(f"table reference {ref!r} is not uri#generation")
        try:
            data = GcsPinnedReader(self.client).read_bytes(uri, generation)
        except Exception as exc:
            raise EETransportError(f"reading {ref} failed: {type(exc).__name__}: {exc}") from exc
        if data is None:
            raise EETransportError(f"{ref} not found")
        self.receipts.append({"kind": "read", "uri": uri, "generation": generation,
                              "sha256": hashlib.sha256(data).hexdigest()})
        try:
            return pd.read_csv(io.BytesIO(data), dtype={"admin_code": str}, keep_default_na=False, na_values=[""],
                               float_precision="round_trip")
        except Exception as exc:
            raise EETransportError(f"{ref} is not a readable CSV: {exc}") from exc

    # ------------------------------------------------------------------ asset tables

    def read_asset_table(self, asset_id: str) -> pd.DataFrame:
        try:
            fc = self.ee.FeatureCollection(asset_id).map(lambda f: self.ee.Feature(None, self.ee.Feature(f).toDictionary()))
            frame = self.ee.data.computeFeatures({"expression": fc, "fileFormat": "PANDAS_DATAFRAME"})
        except Exception as exc:
            raise EETransportError(f"reading table {asset_id} failed: {type(exc).__name__}: {exc}") from exc
        if not isinstance(frame, pd.DataFrame) or frame.empty or "admin_code" not in frame.columns:
            raise EETransportError(f"table {asset_id} is empty or has no admin_code")
        frame = frame.drop(columns=[c for c in ("geo", "geometry") if c in frame.columns])
        frame["admin_code"] = [_admin_text(v, asset_id) for v in frame["admin_code"]]
        digest = hashlib.sha256(frame.to_csv(index=False).encode("utf-8")).hexdigest()
        self.receipts.append({"kind": "asset_table", "asset": asset_id, "rows": int(len(frame)), "sha256": digest})
        return frame


def _admin_text(value: Any, asset_id: str) -> str:
    if isinstance(value, bool):
        raise EETransportError(f"{asset_id}: boolean admin_code")
    if isinstance(value, (int, float)) and float(value).is_integer():
        return str(int(value))
    text = str(value).strip()
    if not re.fullmatch(r"\d+", text):
        raise EETransportError(f"{asset_id}: admin_code {value!r} is not an integral identifier")
    return text


def from_environment(*, project: str, output_root: str, run_id: str, deadline_utc: datetime | None = None) -> EETransport:
    """Production constructor (the existing worker pattern): ``ee.Initialize(project=...)`` and a storage client."""
    import ee
    from google.cloud import storage

    from cloud.common.object_store import GCSObjectStore

    client = storage.Client()
    ee.Initialize(project=project)
    return EETransport(ee=ee, client=client, store=GCSObjectStore(client), output_root=output_root, run_id=run_id,
                       deadline_utc=deadline_utc)
