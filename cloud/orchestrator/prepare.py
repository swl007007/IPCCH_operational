"""Operator-initiated remote-sensing preparation for one origin month.

Compute placement (design section 2):

1. ``python -m cloud.orchestrator.prepare plan ...`` runs as the Cloud Run preparation
   job. It acquires a create-only ``prepare_id`` sentinel before any provider work,
   reads every pinned input at its exact generation, discovers the latest completed
   provider month per family (binding exact Earth Engine image IDs / provider URLs),
   writes a create-only ``prepare_plan.json`` and submits one Cloud Batch job through
   the existing ``batch_client`` launcher (no automatic Batch retries).
2. ``python -m cloud.orchestrator.prepare extract ...`` is that Batch job's command. It
   reads the plan at its pinned generation, exports/downloads exactly the planned
   provider objects, extracts both native rosters separately and writes create-only
   features, ``source_coverage.csv``, ``area_latest_observation.csv`` and
   ``prepared_manifest.json``.

``run_prepare`` composes both phases in-process for local fixtures; the deployed path
is plan (Cloud Run) -> Batch extract. A provider/query/download failure fails the
preparation with retained status evidence; it is never reported as publication lag,
and there is no fallback to an older preparation. Scoring never re-queries providers.
A retry is a deliberate new ``prepare_id``.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd

from cloud.batch.remote_sources import (
    EXTRACTION_CONTRACT_VERSION,
    NATIVE_KEY,
    SOURCE_CONTRACTS,
    SourceRetrievalError,
    gee_export_spec,
    gee_published_months,
    gosif_url,
    http_published_months,
    last_eligible_month,
    latest_completed_month,
    months_between,
    mosaic_shards,
    native_geometries,
    stamp_band_names,
    zonal_statistics,
)
from cloud.common.object_store import GenerationConflict, ObjectStore
from cloud.common.runtime_config import RuntimeDefaults
from cloud.orchestrator.batch_client import BatchJobConfig
from cloud.orchestrator.delivery_manifest import (
    DeliveryManifestError,
    ReferenceIdentityError,
    SYSTEMS,
    _exact_keys,
    _month,
    _ref,
    _text,
    _timestamp,
)


PREPARE_SCHEMA_VERSION = "fewsnet-ipcch-prepare-request-v1"
FAMILIES = ("evi", "fldas", "gosif_mean", "gosif_sd", "viirs")
COVERAGE_COLUMNS = [
    "system", "family", "product", "month", "status", "provider_id", "areas_total", "areas_with_values",
    "areas_without_values", "source_uri", "source_generation", "source_sha256",
]
_PREPARE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,62}$")
_REQUEST_PATH_RE = re.compile(
    r"^gs://[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]/prepare_requests/([^/]+)/prepare_request\.json$"
)


class PreparationConflict(RuntimeError):
    """The prepare_id (or its extraction) was already started; retry with a new ID."""


@dataclass
class AcquiredRaster:
    path: str  # local GeoTIFF readable by rasterio
    source: dict = field(default_factory=dict)  # uri/url, generation, sha256 of retained bytes


class SourceAcquirer(Protocol):
    def published_months(self, family: str, *, start_month: str, end_month: str) -> dict[str, str]:
        """Month -> exact provider identity (Earth Engine image ID or provider URL)."""

    def acquire(self, family: str, month: str, *, provider_id: str, prepare_id: str,
                workdir: Path) -> AcquiredRaster:
        """Retrieve exactly ``provider_id``; never re-resolve the month."""


class PinnedReader(Protocol):
    def read_bytes(self, uri: str, generation: str) -> bytes | None:
        """Bytes of that exact object generation, or None if that generation does not exist."""


class GcsPinnedReader:
    """Reads an exact GCS object generation; an older live version stays readable."""

    def __init__(self, client):
        self.client = client

    def read_bytes(self, uri: str, generation: str) -> bytes | None:
        from cloud.batch.evi_service import _parse_gcs_uri

        bucket, name = _parse_gcs_uri(uri)
        blob = self.client.bucket(bucket).blob(name, generation=int(generation))
        try:
            return blob.download_as_bytes()
        except Exception as exc:
            if exc.__class__.__name__ in {"NotFound", "FakeNotFound"}:
                return None
            raise


def read_pinned(reader: PinnedReader, ref: Mapping[str, str]) -> bytes:
    """Exact generation plus content hash: both must match the reference."""
    data = reader.read_bytes(ref["uri"], ref["generation"])
    if data is None:
        raise ReferenceIdentityError(f"{ref['uri']}#{ref['generation']} not found")
    if hashlib.sha256(data).hexdigest() != ref["sha256"]:
        raise ReferenceIdentityError(f"sha256 mismatch for {ref['uri']}#{ref['generation']}")
    return data


def validate_prepare_request(data: Mapping[str, Any], *, request_uri: str, request_generation: str,
                             request_sha256: str) -> dict:
    """Structural validation of the operator's preparation request.

    ``request_sha256`` is the SHA-256 of the exact raw request bytes read at
    ``request_generation``; it is carried into the plan and prepared manifest.
    """
    _exact_keys(data, ("schema_version", "prepare_id", "origin_month", "cutoff_utc",
                       "extraction_contract_version", "systems", "operator"), "prepare request")
    if data["schema_version"] != PREPARE_SCHEMA_VERSION:
        raise DeliveryManifestError(f"schema_version must be {PREPARE_SCHEMA_VERSION}")
    prepare_id = data["prepare_id"]
    if not isinstance(prepare_id, str) or _PREPARE_ID_RE.fullmatch(prepare_id) is None:
        raise DeliveryManifestError("prepare_id must be 3-63 lowercase [a-z0-9._-] characters")
    match = _REQUEST_PATH_RE.fullmatch(request_uri or "")
    if match is None or match.group(1) != prepare_id:
        raise DeliveryManifestError("request_uri must be gs://<bucket>/prepare_requests/<prepare_id>/prepare_request.json")
    if not isinstance(request_generation, str) or re.fullmatch(r"[1-9][0-9]*", request_generation) is None:
        raise DeliveryManifestError("request_generation must be a positive integer string")
    if not isinstance(request_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", request_sha256) is None:
        raise DeliveryManifestError("request_sha256 must be the lowercase SHA-256 of the raw request bytes")
    _month(data["origin_month"], "origin_month")
    _timestamp(data["cutoff_utc"], "cutoff_utc")
    if data["extraction_contract_version"] != EXTRACTION_CONTRACT_VERSION:
        raise DeliveryManifestError(f"extraction_contract_version must be {EXTRACTION_CONTRACT_VERSION}")
    _exact_keys(data["systems"], SYSTEMS, "systems")
    for system in SYSTEMS:
        assets = data["systems"][system]
        _exact_keys(assets, ("geometry", "roster", "history"), f"systems.{system}")
        _ref(assets["geometry"], f"systems.{system}.geometry")
        _ref(assets["roster"], f"systems.{system}.roster")
        # Pinned accepted history snapshot per family, in the current extraction layout.
        _exact_keys(assets["history"], FAMILIES, f"systems.{system}.history")
        for family in FAMILIES:
            _ref(assets["history"][family], f"systems.{system}.history.{family}")
    _text(data["operator"], "operator")
    validated = dict(data)
    validated["request"] = {"uri": request_uri, "generation": request_generation, "sha256": request_sha256}
    return validated


def run_prepare(request, *, store, reader, acquirer, output_root: str, workdir: Path) -> dict:
    """Local in-process composition of plan + extract (the deployed path splits them)."""
    plan = plan_prepare(request, store=store, reader=reader, acquirer=acquirer, output_root=output_root)
    return execute_prepare_plan(plan["plan_ref"], store=store, reader=reader, acquirer=acquirer, workdir=workdir)


def plan_prepare(request, *, store: ObjectStore, reader: PinnedReader, acquirer: SourceAcquirer,
                 output_root: str) -> dict:
    """Cloud Run phase: sentinel, pinned inputs, completed-month discovery, create-only plan."""
    prepare_root = f"{output_root.rstrip('/')}/prepared/{request['prepare_id']}/"
    _acquire_sentinel(store, f"{prepare_root}_PREPARE_ACQUIRED", request["prepare_id"])
    try:
        origin = request["origin_month"]
        cutoff = datetime.fromisoformat(request["cutoff_utc"].replace("Z", "+00:00"))
        # History cannot claim a month that had not ended by the cutoff, nor one after O.
        limit = last_eligible_month(origin, cutoff)
        rosters = {system: _load_system(reader, request["systems"][system])[0] for system in SYSTEMS}
        families = {}
        for family in FAMILIES:
            history_through = {
                system: _history(reader, request["systems"][system]["history"][family], family,
                                 rosters[system], limit)[1]
                for system in SYSTEMS
            }
            earliest = min(history_through.values())
            published: dict[str, str] = {}
            latest = None
            if earliest < limit:
                published = acquirer.published_months(
                    family, start_month=months_between(earliest, origin)[0], end_month=origin)
                latest = latest_completed_month(published, origin_month=origin, cutoff_utc=cutoff)
            system_months = {
                system: months_between(through, latest) if latest and latest > through else []
                for system, through in history_through.items()
            }
            wanted = sorted(set().union(*system_months.values()))
            families[family] = {
                "product": SOURCE_CONTRACTS[family].product,
                "history_through": history_through,
                "provider_latest_completed_month": latest,
                "months": {month: published[month] for month in wanted if month in published},
                "not_published_months": [month for month in wanted if month not in published],
                "system_months": system_months,
            }
        plan = {
            "schema_version": "fewsnet-ipcch-prepare-plan-v1",
            "prepare_id": request["prepare_id"],
            "origin_month": origin,
            "cutoff_utc": request["cutoff_utc"],
            "extraction_contract_version": EXTRACTION_CONTRACT_VERSION,
            "request": request["request"],
            "systems": request["systems"],
            "families": families,
            "prepare_root": prepare_root,
        }
        plan_ref = _write_create_only(store, f"{prepare_root}prepare_plan.json", _json(plan))
    except Exception as exc:
        _write_failure(store, prepare_root, request, exc)
        raise
    return {**plan, "plan_ref": plan_ref}


def execute_prepare_plan(plan_ref, *, store: ObjectStore, reader: PinnedReader, acquirer: SourceAcquirer,
                         workdir: Path) -> dict:
    """Batch phase: acquire exactly the planned provider objects and extract both rosters."""
    plan = json.loads(read_pinned(reader, plan_ref))
    prepare_root = plan["prepare_root"]
    _acquire_sentinel(store, f"{prepare_root}_EXTRACT_ACQUIRED", plan["prepare_id"])
    try:
        manifest = _extract(plan, plan_ref, store=store, reader=reader, acquirer=acquirer,
                            prepare_root=prepare_root, workdir=workdir)
    except Exception as exc:
        _write_failure(store, prepare_root, plan, exc)
        raise
    _write_status(store, prepare_root, plan, "succeeded", None, None)
    return manifest


def _extract(plan, plan_ref, *, store, reader, acquirer, prepare_root, workdir) -> dict:
    origin = plan["origin_month"]
    limit = last_eligible_month(origin, datetime.fromisoformat(plan["cutoff_utc"].replace("Z", "+00:00")))
    loaded = {system: _load_system(reader, plan["systems"][system]) for system in SYSTEMS}
    coverage_rows, latest_rows, families = [], [], {}
    for family, family_plan in plan["families"].items():
        product = SOURCE_CONTRACTS[family].product
        system_months = family_plan["system_months"]
        histories = {
            system: _history(reader, plan["systems"][system]["history"][family], family, loaded[system][0], limit)
            for system in SYSTEMS
        }
        for system in SYSTEMS:
            history, through = histories[system]
            coverage_rows.append(_coverage(system, family, product, through, "history_snapshot", None,
                                           len(loaded[system][0]), history.loc[history["month"].eq(through)],
                                           plan["systems"][system]["history"][family]))
            for month in family_plan["not_published_months"]:
                if month in system_months[system]:
                    coverage_rows.append(_coverage(system, family, product, month, "not_published", None,
                                                   len(loaded[system][0]), None, {}))
        frames = {system: [] for system in SYSTEMS}
        sources = []
        for month, provider_id in sorted(family_plan["months"].items()):
            raster = acquirer.acquire(family, month, provider_id=provider_id,
                                      prepare_id=plan["prepare_id"], workdir=workdir)
            sources.append({"month": month, "provider_id": provider_id, **raster.source})
            for system in SYSTEMS:
                if month not in system_months[system]:
                    continue  # already in this system's pinned history
                stats = zonal_statistics(raster.path, loaded[system][1], family=family, month=month)
                frames[system].append(stats)
                coverage_rows.append(_coverage(system, family, product, month, "observed", provider_id,
                                               len(loaded[system][0]), stats, raster.source))
        outputs, latest_observation = {}, {}
        for system in SYSTEMS:
            combined = histories[system][0]
            if frames[system]:
                new = pd.concat(frames[system], ignore_index=True)
                outputs[system] = _write_create_only(store, f"{prepare_root}features/{system}/{family}.csv",
                                                     new.to_csv(index=False, lineterminator="\n"))
                combined = pd.concat([combined, new], ignore_index=True)
            rows = _area_latest(system, family, loaded[system][0], combined)
            latest_rows.extend(rows)
            latest_observation[system] = max(row["latest_observation_month"] for row in rows
                                             if row["latest_observation_month"] is not None)
        families[family] = {
            "product": product,
            "script": SOURCE_CONTRACTS[family].script,
            "reducers": list(SOURCE_CONTRACTS[family].reducers),
            "history": {system: plan["systems"][system]["history"][family] for system in SYSTEMS},
            "history_through": family_plan["history_through"],
            "provider_latest_completed_month": family_plan["provider_latest_completed_month"],
            "latest_observation_month": latest_observation,
            "not_published_months": family_plan["not_published_months"],
            "sources": sources,
            "outputs": outputs,
        }
    coverage = pd.DataFrame(coverage_rows, columns=COVERAGE_COLUMNS).to_csv(index=False, lineterminator="\n")
    coverage_ref = _write_create_only(store, f"{prepare_root}source_coverage.csv", coverage)
    latest_ref = _write_create_only(store, f"{prepare_root}area_latest_observation.csv",
                                    pd.DataFrame(latest_rows).to_csv(index=False, lineterminator="\n"))
    manifest = {
        "schema_version": "fewsnet-ipcch-prepared-snapshot-v1",
        "prepare_id": plan["prepare_id"],
        "origin_month": origin,
        "cutoff_utc": plan["cutoff_utc"],
        "extraction_contract_version": EXTRACTION_CONTRACT_VERSION,
        "native_key": NATIVE_KEY,
        "request": plan["request"],
        "plan": dict(plan_ref),
        "systems": plan["systems"],
        "families": families,
        "source_coverage": coverage_ref,
        "area_latest_observation": latest_ref,
        "status": "succeeded",
    }
    _write_create_only(store, f"{prepare_root}prepared_manifest.json", _json(manifest))
    return manifest


def _load_system(reader, assets) -> tuple[list[str], dict[str, dict]]:
    roster_frame = pd.read_csv(io.BytesIO(read_pinned(reader, assets["roster"])), dtype={NATIVE_KEY: str},
                               keep_default_na=False)
    if NATIVE_KEY not in roster_frame:
        raise ReferenceIdentityError(f"roster lacks {NATIVE_KEY}")
    roster = roster_frame[NATIVE_KEY].tolist()
    geometries = native_geometries(json.loads(read_pinned(reader, assets["geometry"])), roster=roster)
    return roster, geometries


def _history(reader, ref, family: str, roster: list[str], limit: str) -> tuple[pd.DataFrame, str]:
    """Validate a pinned history snapshot; its latest observed month is the evidenced baseline.

    ``limit`` is min(origin, last calendar month ended before the cutoff).
    """
    contract = SOURCE_CONTRACTS[family]
    columns = [f"{band}__{reducer}" for band in contract.bands for reducer in contract.reducers]
    frame = pd.read_csv(io.BytesIO(read_pinned(reader, ref)), dtype={NATIVE_KEY: str, "month": str})
    if list(frame.columns) != [NATIVE_KEY, "month", *columns]:
        raise ValueError(f"{family} history {ref['uri']} columns must be {[NATIVE_KEY, 'month', *columns]}")
    if frame[NATIVE_KEY].isna().any() or not frame[NATIVE_KEY].isin(roster).all():
        raise ValueError(f"{family} history {ref['uri']} has IDs outside the roster")
    for month in frame["month"]:
        if _month(month, "history month") > limit:
            raise ValueError(f"{family} history {ref['uri']} has months after {limit}, "
                             "the last completed month at the cutoff (or the origin)")
    if frame.duplicated([NATIVE_KEY, "month"]).any():
        raise ValueError(f"{family} history {ref['uri']} has duplicate area-month keys")
    values = frame[columns].apply(pd.to_numeric, errors="raise")
    if np.isinf(values.to_numpy(dtype="float64")).any():
        raise ValueError(f"{family} history {ref['uri']} contains non-finite values")
    observed = values.notna().any(axis=1)
    if not observed.any():
        raise ValueError(f"{family} history {ref['uri']} has no observations")
    return frame, frame.loc[observed, "month"].max()


def _area_latest(system, family, roster, frame) -> list[dict]:
    value_columns = [column for column in frame.columns if "__" in column]
    observed = frame.loc[frame[value_columns].notna().any(axis=1)]
    latest = observed.groupby(NATIVE_KEY)["month"].max()
    return [{"system": system, "family": family, NATIVE_KEY: key,
             "latest_observation_month": latest.get(key)} for key in roster]


def _coverage(system, family, product, month, status, provider_id, total, stats, source) -> dict:
    with_values = None
    if stats is not None:
        value_columns = [column for column in stats.columns if "__" in column]
        with_values = int(stats[value_columns].notna().any(axis=1).sum())
    return {
        "system": system, "family": family, "product": product, "month": month, "status": status,
        "provider_id": provider_id, "areas_total": total, "areas_with_values": with_values,
        "areas_without_values": None if with_values is None else total - with_values,
        "source_uri": source.get("uri") or source.get("url"), "source_generation": source.get("generation"),
        "source_sha256": source.get("sha256"),
    }


def _acquire_sentinel(store: ObjectStore, uri: str, prepare_id: str) -> None:
    try:
        store.write_text(uri, f"{prepare_id}\n", if_generation_match=0)
    except GenerationConflict as exc:
        raise PreparationConflict(f"{uri} already exists; retry with a new prepare_id") from exc


def _write_create_only(store: ObjectStore, uri: str, content: str) -> dict:
    metadata = store.write_text(uri, content, if_generation_match=0)
    return {"uri": uri, "generation": str(metadata.generation),
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}


def _write_failure(store, prepare_root, request, exc) -> None:
    reason = "source_retrieval_failed" if isinstance(exc, SourceRetrievalError) else "preparation_error"
    _write_status(store, prepare_root, request, "failed", reason, f"{type(exc).__name__}: {exc}")


def _write_status(store, prepare_root, request, status, reason, message) -> None:
    payload = {
        "prepare_id": request["prepare_id"],
        "origin_month": request["origin_month"],
        "status": status,
        "failure_reason": reason,
        "message": message,
        "written_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    store.write_text(f"{prepare_root}prepare_status.json", _json(payload), if_generation_match=0)


def _json(payload) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"


def plan_and_submit(request, *, store: ObjectStore, reader: PinnedReader, acquirer: SourceAcquirer,
                    output_root: str, submit, image_uri: str, service_account: str,
                    earth_engine_project: str) -> dict:
    """Cloud Run entry: plan, then submit the Batch extract job.

    A submission failure after the plan was written leaves the sentinel and plan as
    evidence and records ``batch_submit_failed``; the operator retries with a new ID.
    """
    planned = plan_prepare(request, store=store, reader=reader, acquirer=acquirer, output_root=output_root)
    config = prepare_batch_job_config(planned["plan_ref"], prepare_id=request["prepare_id"],
                                      origin_month=request["origin_month"], image_uri=image_uri,
                                      service_account=service_account, earth_engine_project=earth_engine_project)
    try:
        job = submit(config)
    except Exception as exc:
        _write_status(store, planned["prepare_root"], request, "failed", "batch_submit_failed",
                      f"{type(exc).__name__}: {exc}")
        raise
    return {**planned, "batch_job": getattr(job, "name", None)}


def prepare_batch_job_config(plan_ref: Mapping[str, str], *, prepare_id: str, origin_month: str,
                             image_uri: str, service_account: str, earth_engine_project: str) -> BatchJobConfig:
    """Batch job for the extract phase; no automatic retries (a retry is a new prepare_id)."""
    return BatchJobConfig(
        job_name_prefix="ipcch-prepare",
        image_uri=image_uri,
        service_account=service_account,
        run_id=prepare_id,
        feature_month=origin_month,
        worker_args=["extract", "--plan-uri", plan_ref["uri"], "--plan-generation", plan_ref["generation"],
                     "--plan-sha256", plan_ref["sha256"], "--earth-engine-project", earth_engine_project],
        runtime=RuntimeDefaults(max_retries=0),
        worker_module="cloud.orchestrator.prepare",
    )


# --- production acquirer (Earth Engine exports + GOSIF HTTP); boundary tested with fakes ---


class CloudSourceAcquirer:
    """Earth Engine and GOSIF HTTP acquisition with immutable retained copies.

    ``ee`` is the initialised earthengine-api module, ``client`` a google-cloud-storage
    client and ``http`` a requests-like session. Provider bytes are retained create-only
    under the preparation prefix, so the prepared snapshot never points at a moving URL.
    """

    def __init__(self, *, ee, client, http, store: ObjectStore, output_root: str,
                 timeout_seconds: int = 21600, poll_seconds: int = 60, http_timeout: int = 180):
        self.ee, self.client, self.http, self.store = ee, client, http, store
        self.output_root = output_root.rstrip("/")
        self.timeout_seconds, self.poll_seconds, self.http_timeout = timeout_seconds, poll_seconds, http_timeout

    def published_months(self, family: str, *, start_month: str, end_month: str) -> dict[str, str]:
        contract = SOURCE_CONTRACTS[family]
        if contract.provider == "gee":
            return gee_published_months(self._list_images, contract.product,
                                        start_month=start_month, end_month=end_month)
        candidates = months_between(_previous_month(start_month), end_month)
        return http_published_months(self._head, contract.export["url"], candidates)

    def acquire(self, family: str, month: str, *, provider_id: str, prepare_id: str,
                workdir: Path) -> AcquiredRaster:
        if SOURCE_CONTRACTS[family].provider == "gee":
            return self._acquire_gee(family, month, provider_id, prepare_id, workdir)
        return self._acquire_http(family, month, provider_id, prepare_id, workdir)

    def _list_images(self, collection: str, start: str, end: str) -> list[tuple[int, str]]:
        # One server call so time_start and image ID come from the same listing.
        images = self.ee.ImageCollection(collection).filterDate(start, end)
        starts, ids = self.ee.List([images.aggregate_array("system:time_start"),
                                    images.aggregate_array("system:id")]).getInfo()
        return list(zip(starts, ids))

    def _head(self, url: str) -> int:
        return self.http.head(url, timeout=self.http_timeout, allow_redirects=True).status_code

    def _acquire_http(self, family, month, provider_id, prepare_id, workdir) -> AcquiredRaster:
        url = gosif_url(SOURCE_CONTRACTS[family].export["url"], month)
        if provider_id != url:
            raise SourceRetrievalError(f"discovered URL {provider_id} differs from {url}")
        try:
            response = self.http.get(url, timeout=self.http_timeout)
        except Exception as exc:
            raise SourceRetrievalError(f"download failed for {url}: {exc}") from exc
        if response.status_code != 200:
            raise SourceRetrievalError(f"unexpected HTTP {response.status_code} for {url}")
        data = response.content
        try:
            raster_bytes = gzip.decompress(data)
        except OSError as exc:
            raise SourceRetrievalError(f"malformed gzip from {url}") from exc
        uri = f"{self.output_root}/prepared/{prepare_id}/sources/{family}/{url.rsplit('/', 1)[-1]}"
        generation = _upload_create_only(self.client, uri, data)
        path = Path(workdir) / f"{family}_{month}.tif"
        path.write_bytes(raster_bytes)
        return AcquiredRaster(str(path), {"url": url, "uri": uri, "generation": generation,
                                          "sha256": hashlib.sha256(data).hexdigest()})

    def _acquire_gee(self, family, month, provider_id, prepare_id, workdir) -> AcquiredRaster:
        from cloud.batch.evi_service import _parse_gcs_uri, _wait_for_ee_task

        spec = gee_export_spec(family, month)
        if not provider_id.startswith(spec["collection"] + "/"):
            raise SourceRetrievalError(f"{provider_id} is not an image of {spec['collection']}")
        prefix_uri = f"{self.output_root}/prepared/{prepare_id}/sources/{family}/{family}_{month}"
        bucket, blob_prefix = _parse_gcs_uri(prefix_uri)
        if self.store.list(prefix_uri):
            raise SourceRetrievalError(f"export prefix already has objects: {prefix_uri}")
        # The exact discovered image, with the contract's bands selected explicitly and in order.
        image = self.ee.Image(provider_id).select(spec["bands"])
        export = {"description": f"{prepare_id}_{family}_{month}".replace("-", "_")[:100],
                  "bucket": bucket, "fileNamePrefix": blob_prefix, "maxPixels": 1e13, "fileFormat": "GeoTIFF"}
        if "region" in spec:
            export["region"] = self.ee.Geometry.Rectangle(list(spec["region"]), "EPSG:4326", False)
        if "crs_transform" in spec:
            if spec.get("resample"):
                image = image.resample(spec["resample"]).reproject(crs=spec["crs"],
                                                                   crsTransform=list(spec["crs_transform"]))
            export["crs"], export["crsTransform"] = spec["crs"], list(spec["crs_transform"])
        else:
            export["scale"] = spec["scale"]
        task = self.ee.batch.Export.image.toCloudStorage(image=image, **export)
        task.start()
        try:
            _wait_for_ee_task(task, timeout_seconds=self.timeout_seconds, poll_seconds=self.poll_seconds)
        except Exception as exc:
            raise SourceRetrievalError(f"Earth Engine export failed for {family} {month}: {exc}") from exc
        shards, refs, band_names = [], [], "single_band"
        for uri in sorted(self.store.list(prefix_uri)):
            blob = self.client.bucket(bucket).blob(_parse_gcs_uri(uri)[1])
            blob.reload()
            data = blob.download_as_bytes(if_generation_match=blob.generation)
            local = Path(workdir) / uri.rsplit("/", 1)[-1]
            local.write_bytes(data)
            if len(spec["bands"]) > 1:
                band_names = stamp_band_names(str(local), spec["bands"])
            shards.append(str(local))
            refs.append({"uri": uri, "generation": str(blob.generation), "sha256": hashlib.sha256(data).hexdigest()})
        if not refs:
            raise SourceRetrievalError(f"Earth Engine export produced no objects under {prefix_uri}")
        path = mosaic_shards(shards, str(Path(workdir) / f"{family}_{month}_mosaic.tif"))
        if len(refs) == 1:
            return AcquiredRaster(path, {**refs[0], "band_names": band_names})
        digest = hashlib.sha256("".join(ref["sha256"] for ref in refs).encode()).hexdigest()
        return AcquiredRaster(path, {"uri": prefix_uri, "generation": None, "sha256": digest,
                                     "shards": refs, "band_names": band_names})


def _upload_create_only(client, uri: str, data: bytes) -> str:
    from cloud.batch.evi_service import _parse_gcs_uri

    bucket, name = _parse_gcs_uri(uri)
    blob = client.bucket(bucket).blob(name)
    blob.upload_from_string(data, if_generation_match=0)
    return str(blob.generation)


def _previous_month(month: str) -> str:
    year, number = int(month[:4]), int(month[5:7])
    return f"{year - (number == 1):04d}-{12 if number == 1 else number - 1:02d}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare remote-sensing inputs for one origin month.")
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="Cloud Run: validate, discover, write plan, submit Batch extract")
    plan.add_argument("--request-uri", required=True)
    plan.add_argument("--request-generation", required=True)
    plan.add_argument("--output-root", required=True)
    plan.add_argument("--earth-engine-project", required=True)
    plan.add_argument("--batch-parent", required=True, help="projects/<project>/locations/<region>")
    plan.add_argument("--batch-image-uri", required=True)
    plan.add_argument("--batch-service-account", required=True)
    extract = commands.add_parser("extract", help="Cloud Batch: acquire planned sources and extract")
    extract.add_argument("--plan-uri", required=True)
    extract.add_argument("--plan-generation", required=True)
    extract.add_argument("--plan-sha256", required=True)
    extract.add_argument("--earth-engine-project", required=True)
    args = parser.parse_args(argv)

    import ee
    import requests
    from google.cloud import storage

    from cloud.common.object_store import GCSObjectStore

    client = storage.Client()
    store, reader = GCSObjectStore(client), GcsPinnedReader(client)
    ee.Initialize(project=args.earth_engine_project)
    if args.command == "plan":
        from google.cloud import batch_v1

        from cloud.orchestrator.batch_client import submit_batch_job

        # Read the event's exact request generation, not whatever is latest.
        raw = reader.read_bytes(args.request_uri, args.request_generation)
        if raw is None:
            raise ReferenceIdentityError(f"{args.request_uri}#{args.request_generation} not found")
        request = validate_prepare_request(json.loads(raw), request_uri=args.request_uri,
                                           request_generation=args.request_generation,
                                           request_sha256=hashlib.sha256(raw).hexdigest())
        acquirer = CloudSourceAcquirer(ee=ee, client=client, http=requests.Session(), store=store,
                                       output_root=args.output_root)
        batch = batch_v1.BatchServiceClient()
        plan_and_submit(request, store=store, reader=reader, acquirer=acquirer, output_root=args.output_root,
                        submit=lambda config: submit_batch_job(config, client=batch, parent=args.batch_parent),
                        image_uri=args.batch_image_uri, service_account=args.batch_service_account,
                        earth_engine_project=args.earth_engine_project)
        return 0
    plan_ref = {"uri": args.plan_uri, "generation": args.plan_generation, "sha256": args.plan_sha256}
    output_root = args.plan_uri.split("/prepared/")[0]
    acquirer = CloudSourceAcquirer(ee=ee, client=client, http=requests.Session(), store=store,
                                   output_root=output_root)
    with tempfile.TemporaryDirectory() as workdir:
        execute_prepare_plan(plan_ref, store=store, reader=reader, acquirer=acquirer, workdir=Path(workdir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
