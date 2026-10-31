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
* ``submit_asset_export`` / ``wait_asset_export`` / ``cancel_asset_export`` (task 10-30): the same reservation, task-id
  persistence, bounded wait and cancellation for ``Export.table.toAsset`` to a destination that must not exist yet;
  COMPLETED additionally requires the destination asset to exist; submission and waiting are separate so a run submits
  all of its tables first. ``evaluate``: one bounded ``getInfo`` (e.g. the PATCH32 target count).
* ``read_table``: that exact generation (``GcsPinnedReader``), sha256 recorded in ``receipts``.
* ``read_asset_table``: ``ee.data.computeFeatures`` of the asset's properties without geometry, paged explicitly
  (pageSize/pageToken, no SDK fileFormat auto-paging) with the deadline rechecked before every page; integral
  ``admin_code`` values are normalised to canonical integer text; any failure blocks.
* Every synchronous request (listing/metadata/read pages, evaluate, task status and cancellation) runs through
  ``_bounded`` under the run deadline with SDK retries disabled and the previous SDK settings restored.

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
RPC_TIMEOUT_SECONDS = 60       # one Earth Engine request (metadata, listing/read page, evaluate, status, cancel)
READ_PAGE_SIZE = 1000          # computeFeatures rows per request (the SDK default page)
LIST_PAGE_SIZE = 1000          # listAssets entries per request
MAX_PAGES = 1000               # a larger table/folder is a failure, never a silently truncated read or listing


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
            pairs = list(self._bounded(f"{collection} listing", lambda: self._acquirer._list_images(collection, start, end)))
        except EETransportError:
            raise
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
            names, token = set(), None
            for page in range(1, MAX_PAGES + 1):                  # explicit pages: one bounded request each
                params = {"parent": parent, "pageSize": LIST_PAGE_SIZE, **({"pageToken": token} if token else {})}
                try:
                    listed = self._bounded(f"listing {parent} page {page}", lambda: self.ee.data.listAssets(dict(params)))
                except EETransportError:
                    raise
                except Exception as exc:
                    raise EETransportError(f"cannot list {parent} to resolve an ambiguous asset lookup "
                                           f"({type(exc).__name__}: {exc}); not treated as absent") from exc
                for a in (listed or {}).get("assets", []):
                    names.update(v for v in (a.get("name"), a.get("id")) if isinstance(v, str))
                token = (listed or {}).get("nextPageToken")
                if not token:
                    break
            else:
                raise EETransportError(f"listing {parent} exceeded {MAX_PAGES} pages; absence not established")
            self._children[parent] = names
        return self._children[parent]

    def missing_assets(self, asset_ids: list[str]) -> list[str]:
        """The ids that DEFINITIVELY do not exist (see module docstring); anything ambiguous raises."""
        absent = []
        for asset_id in asset_ids:
            try:
                info = self._bounded(f"{asset_id} metadata", lambda: self.ee.data.getAsset(asset_id))
            except EETransportError:
                raise
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

    def _bounded(self, what: str, call: Callable[[], Any], *, cleanup: bool = False) -> Any:
        """ONE Earth Engine request under the run deadline. Refused once only the cleanup reserve is left (``cleanup``:
        cancellation may use the reserve itself, never beyond the deadline); otherwise the request runs with SDK retries
        disabled (``setMaxRetries(0)`` - retry backoff/jitter could not be bounded) and its timeout set to the smaller of
        ``RPC_TIMEOUT_SECONDS`` and the remaining budget (``setDeadline``), so no single metadata/status/read request -
        and no first cancellation - can consume the cleanup reserve that sibling cancellations need; the SDK's previous
        deadline/retry settings are restored afterwards, also on failure. Callers page explicitly, so every request is
        one bounded call and the budget is rechecked between pages."""
        if self.deadline_utc is None:
            return call()
        total = (self.deadline_utc - self.clock()).total_seconds()
        left = total if cleanup else total - self.cleanup_reserve_seconds
        if left <= 0:
            raise EETransportError(f"{what}: run deadline {'' if cleanup else 'cleanup reserve '}reached; not started")
        data = self.ee.data
        state = data._get_state() if hasattr(data, "_get_state") else None
        previous = (state.deadline_ms, state.max_retries) if state is not None else (0, 5)    # SDK defaults
        data.setMaxRetries(0)
        data.setDeadline(max(1, int(min(left, RPC_TIMEOUT_SECONDS) * 1000)))
        try:
            return call()
        finally:
            data.setDeadline(previous[0])
            data.setMaxRetries(previous[1])

    def _record(self, uri: str, record: dict, generation) -> str:
        return self.store.write_text(uri, json.dumps(record, sort_keys=True) + "\n",
                                     if_generation_match=generation).generation

    def _cancel(self, task) -> str:
        """Bounded cancellation (may use the cleanup reserve, never past the deadline); the outcome is recorded."""
        try:
            self._bounded("cancel", task.cancel, cleanup=True)
            return "cancelled"
        except Exception as exc:
            return f"cancel_failed: {type(exc).__name__}: {exc}"

    def _best_effort_record(self, uri: str, record: dict, generation) -> None:
        """One bounded attempt (no retry): the outcome is already in the exception and the receipts."""
        try:
            self._record(uri, record, generation)
        except Exception as exc:
            self.receipts.append({"kind": "record_failed", "uri": uri, "error": str(exc)})

    def _wait(self, task, description: str, record_uri: str, record: dict, generation: str) -> dict:
        """IPCCH wait (the shared FEWS ``_wait_for_ee_task`` is unchanged): every sleep is bounded by the remaining
        budget (task timeout and authorization deadline minus the cleanup reserve); on timeout the task is cancelled
        and the cancellation recorded; FAILED/CANCELLED are recorded. Any of these is a processing failure."""
        budget_end = self.monotonic() + min(self.timeout_seconds, max(0.0, self._remaining_seconds()))
        while True:
            try:
                status = self._bounded("status", task.status)
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
                cancel = self._cancel(task)               # recorded; the task id is persisted for operations cleanup
                self._record(record_uri, {**record, "state": "timeout", "cancel": cancel, "status": status}, generation)
                raise EETransportError(f"export {description} timed out ({status}); {cancel}")
            self.sleep(min(self.poll_seconds, left))

    def _reserve(self, description: str, extra: dict) -> tuple[str, dict, str]:
        """Create-only task record BEFORE any submission (a duplicate is refused without a second task)."""
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", description):
            raise EETransportError(f"export description {description!r} is not a plain identifier")
        record_uri = f"{self.output_root}/ipcch_exports/{self.run_id}/tasks/{description}.json"
        if self._remaining_seconds() <= 0:
            raise EETransportError("authorization deadline cleanup reserve reached; no new exports")
        record = {"run_id": self.run_id, "description": description, **extra, "task_id": None, "state": "reserved"}
        try:
            generation = self._record(record_uri, record, 0)
        except Exception as exc:
            raise EETransportError(f"export {description} already reserved for run {self.run_id} ({exc}); "
                                   f"not submitted again") from exc
        return record_uri, record, generation

    def _submit(self, create: Callable[[], Any], description: str, record_uri: str, record: dict,
                generation: str) -> tuple[Any, dict, str]:
        """Deadline re-check -> create -> start -> persist the task id (an untracked task is cancelled)."""
        if self._remaining_seconds() <= 0:               # re-checked immediately before submission
            self._record(record_uri, {**record, "state": "deadline_before_submit"}, generation)
            raise EETransportError("authorization deadline cleanup reserve reached before submission; not submitted")
        try:
            task = create()
        except Exception as exc:                         # no task object: nothing was submitted
            self._record(record_uri, {**record, "state": "create_failed", "error": f"{type(exc).__name__}: {exc}"}, generation)
            raise EETransportError(f"export {description} could not be created: {type(exc).__name__}: {exc}") from exc
        try:
            self._bounded(f"export {description} start", task.start)      # the one export RPC (mutation), bounded
        except Exception as exc:                         # ambiguous: the export may have started (response lost)
            ident = _task_identity(task)
            operation = ident["operation_name"] or ident["task_id"]
            if operation:
                cancel = self._cancel(task)
            elif ident["request_id"]:
                cancel = (f"not cancellable: no operation known (request id {ident['request_id']}); "
                          "the export may have started")
            else:
                cancel = "not cancellable: no operation known; the start request was not sent"
            failed = {**record, **ident, "state": "start_failed", "cancel": cancel,
                      "error": f"{type(exc).__name__}: {exc}"}
            self.receipts.append({"kind": "export_start_failed", **failed})
            self._best_effort_record(record_uri, failed, generation)
            raise EETransportError(f"export {description} start failed (request {ident['request_id']}, task "
                                   f"{ident['task_id']}; {cancel}): {type(exc).__name__}: {exc}") from exc
        record = {**record, **_task_identity(task), "state": "submitted"}
        try:
            generation = self._record(record_uri, record, generation)
        except Exception as exc:                         # an untracked task must not keep running
            cancel = self._cancel(task)
            self.receipts.append({"kind": "export_untracked", **record, "cancel": cancel, "error": str(exc)})
            raise EETransportError(f"export {description}: task {record['task_id']} id could not be persisted ({exc}); "
                                   f"{cancel}") from exc
        return task, record, generation

    def export_table(self, collection: Any, selectors: list[str], description: str) -> str:
        """Reserve -> submit -> persist id -> bounded wait -> pin the single CSV object (see module docstring)."""
        from cloud.batch.evi_service import _parse_gcs_uri

        prefix_uri = f"{self.output_root}/ipcch_exports/{self.run_id}/tables/{description}"
        record_uri, record, generation = self._reserve(description, {"prefix": prefix_uri, "selectors": list(selectors)})
        if self.store.list(prefix_uri):
            raise EETransportError(f"export prefix already has objects: {prefix_uri} (exports are never reused)")
        bucket, blob_prefix = _parse_gcs_uri(prefix_uri)
        task, record, generation = self._submit(lambda: self.ee.batch.Export.table.toCloudStorage(
            collection=collection, description=f"{self.run_id}_{description}"[:100], bucket=bucket,
            fileNamePrefix=blob_prefix, fileFormat="CSV", selectors=list(selectors)), description, record_uri, record,
            generation)
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

    # ------------------------------------------------------------------ table-to-Asset exports (task 10-30)

    def submit_asset_export(self, collection: Any, asset_id: str, description: str) -> "AssetExport":
        """Reserve -> refuse an existing destination -> ``Export.table.toAsset`` -> persist the task id. Waiting is
        separate (``wait_asset_export``) so a run submits all of its tables before waiting on any."""
        if not re.fullmatch(r"projects/[^/]+/assets/[A-Za-z0-9_/-]+", asset_id or ""):
            raise EETransportError(f"asset id {asset_id!r} is not projects/<p>/assets/<name>")
        record_uri, record, generation = self._reserve(description, {"kind": "table_to_asset", "asset_id": asset_id})
        if asset_id not in self.missing_assets([asset_id]):
            self._record(record_uri, {**record, "state": "destination_exists"}, generation)
            raise EETransportError(f"export {description}: destination {asset_id} already exists (never reused)")
        task, record, generation = self._submit(lambda: self.ee.batch.Export.table.toAsset(
            collection=collection, description=f"{self.run_id}_{description}"[:100], assetId=asset_id),
            description, record_uri, record, generation)
        return AssetExport(description, asset_id, task, record_uri, record, generation)

    def wait_asset_export(self, handle: "AssetExport") -> dict:
        """Bounded wait (deadline minus cleanup reserve); COMPLETED must also leave a readable destination asset.
        EE completion is not data readiness: the caller validates the table before exposing its ID."""
        try:
            self._wait(handle.task, handle.description, handle.record_uri, handle.record, handle.generation)
        except EETransportError:
            handle.done = True        # _wait recorded a terminal state (FAILED/CANCELLED, or timeout after cancelling)
            raise
        handle.done = True            # COMPLETED; any other interruption above leaves the task cancellable
        if handle.asset_id in self.missing_assets([handle.asset_id]):
            self._record(handle.record_uri, {**handle.record, "state": "completed_without_asset"}, handle.generation)
            raise EETransportError(f"export {handle.description} COMPLETED but {handle.asset_id} does not exist")
        done = {**handle.record, "state": "completed"}
        handle.generation = self._record(handle.record_uri, done, handle.generation)
        self.receipts.append({"kind": "asset_export", **done})
        return done

    def cancel_asset_export(self, handle: "AssetExport") -> dict:
        """Best-effort cancellation of a still-running sibling after another table failed (recorded, never raises)."""
        if handle.done:
            return {"description": handle.description, "state": "finished"}
        handle.done = True
        cancel = self._cancel(handle.task)
        self._best_effort_record(handle.record_uri, {**handle.record, "state": "cancelled_after_failure",
                                                     "cancel": cancel}, handle.generation)
        return {"description": handle.description, "task_id": handle.record.get("task_id"), "state": cancel}

    def evaluate(self, value: Any) -> Any:
        """One small server-side evaluation (``getInfo``), e.g. the PATCH32 target count, under the run deadline
        (``_bounded``); failure blocks."""
        try:
            out = self._bounded("evaluation", value.getInfo)
        except EETransportError:
            raise
        except Exception as exc:
            raise EETransportError(f"evaluation failed: {type(exc).__name__}: {exc}") from exc
        self.receipts.append({"kind": "evaluate"})
        return out

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
        rows, token = [], None
        try:
            fc = self.ee.FeatureCollection(asset_id).map(lambda f: self.ee.Feature(None, self.ee.Feature(f).toDictionary()))
            for page in range(1, MAX_PAGES + 1):                  # explicit pages (no fileFormat auto-paging)
                params = {"expression": fc, "pageSize": READ_PAGE_SIZE, **({"pageToken": token} if token else {})}
                response = self._bounded(f"reading {asset_id} page {page}",
                                         lambda: self.ee.data.computeFeatures(dict(params)))
                features = response.get("features") if isinstance(response, dict) else None
                if not isinstance(features, list):
                    raise EETransportError(f"reading table {asset_id} page {page}: malformed response")
                for f in features:
                    props = f.get("properties") if isinstance(f, dict) else None
                    if not isinstance(props, dict):
                        raise EETransportError(f"reading table {asset_id} page {page}: feature without properties")
                    rows.append(props)
                token = response.get("nextPageToken")
                if not token:
                    break
            else:
                raise EETransportError(f"reading table {asset_id} exceeded {MAX_PAGES} pages")
        except EETransportError:
            raise
        except Exception as exc:
            raise EETransportError(f"reading table {asset_id} failed: {type(exc).__name__}: {exc}") from exc
        frame = pd.DataFrame(rows)
        if frame.empty or "admin_code" not in frame.columns:
            raise EETransportError(f"table {asset_id} is empty or has no admin_code")
        frame = frame.drop(columns=[c for c in ("geo", "geometry") if c in frame.columns])
        frame["admin_code"] = [_admin_text(v, asset_id) for v in frame["admin_code"]]
        digest = hashlib.sha256(frame.to_csv(index=False).encode("utf-8")).hexdigest()
        self.receipts.append({"kind": "asset_table", "asset": asset_id, "rows": int(len(frame)), "sha256": digest})
        return frame


def _task_identity(task) -> dict:
    """What is known of a submitted export: ``ee.batch.Task`` creates its request id locally before the RPC and learns
    the task id / operation name only from a successful response (fakes may carry only ``id``)."""
    return {"task_id": getattr(task, "id", None), "operation_name": getattr(task, "name", None),
            "request_id": getattr(task, "_request_id", None)}


@dataclass
class AssetExport:
    """A submitted table-to-Asset export (its task record is durable under the run's export prefix)."""
    description: str
    asset_id: str
    task: Any
    record_uri: str
    record: dict
    generation: str
    done: bool = False


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
