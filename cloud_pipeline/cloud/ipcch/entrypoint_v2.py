"""Executable v2 request route (task 10-29; R5, R17, R36, R37, R39, R48, R50 and the CP4 rulings).

``python -m cloud.ipcch.entrypoint_v2 run --config deployment.json --request-uri gs://.../requests/<run>/run_manifest.json
--request-generation N`` (also reached from ``delivery_job run --v2-config`` when the request body is v2); the one-time
store initialisation of a mode is ``python -m cloud.ipcch.entrypoint_v2 initialise --config deployment.json --mode real``
(``initialise_store``):

1. the request is read at its exact generation and structurally validated (mode/namespace rules) BEFORE any state
   read; only a REAL IPCCH inference published to current then reads the production pointer for the R39 month
   (``publication.ipcch_execution_month``) - smoke never reads real state (R48);
2. ``run_v2.run_request``: admission (structure, trusted namespaces, every reference verified by exact generation +
   sha256) BEFORE anything else; per-system locks; IPCCH generation/inference; publication;
3. the IPCCH context of the request's mode is built from the deployment config: the INSTALLED envelope/package verified
   against the request's pinned envelope (``verify_combination`` with the pinned sha; smoke with its fixture root), the
   mode's retained store root, the bound bundle, and - only when generation is selected - the mode's providers - real: ``EETransport.from_environment`` +
   ``climate_run.real_provider_factory`` and ``CloudSourceAcquirer`` (GPP/VIIRS); smoke: a configured fixture provider
   factory (never the real transport, R48);
4. a create-only run status is written under ``{mode root}/runs/{run_id}/v2_run_status.json`` carrying each system's
   structured report (saved updates/warnings survive a later failure, R29/R41); the same status is returned.

Replay protection and the run deadline (task 10-30): after admission and before any lock or mutation the run's identity
(request URI, generation, sha256) is reserved create-only in ``{mode root}/runs/{run_id}/v2_reservation.json`` together
with the whole-run deadline (entry time + ``run_timeout_seconds``, default the 4 h Cloud Run task timeout). A
redelivered identical request returns the durable status without executing anything (read before admission, so an
invalid fresh request still writes nothing, R17); a changed request under the same run ID conflicts; a reserved run
without a final status (active, interrupted or indeterminate) is never launched again - retry with a new run ID. The
persisted deadline (never reset by a redelivery) reaches the EE transport, the table producer and the GPP/VIIRS
acquirer; exports and EE calls stop at the deadline minus the 15-minute cleanup reserve.

Config (JSON, validated): ``roots`` {smoke, real} (deliveries/pointer/locks/runs), ``store_roots`` {smoke, real}
(retained stores, each ending in its mode), ``namespaces`` {production, smoke}, ``trusted_prefixes`` {smoke, real},
``installed`` {mode: {envelope, package_root, bundle_dir[, fixture_root]}}, ``providers`` {mode: "module:function"},
``earth_engine_project``, ``export_root``, ``work_dir``; optional ``fewsnet`` {image_uri} for the real FEWS NET route
(R60, ``cloud.ipcch.fews_adapter``; FEWS NET outputs and prepared snapshots live under the real root).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from cloud.ipcch import binding as bd
from cloud.ipcch import initial
from cloud.ipcch import publication as pub
from cloud.ipcch import run_v2
from cloud.ipcch.stores import StoreRoot
from cloud.orchestrator import delivery_request_v2 as v2

CONFIG_KEYS = ("roots", "store_roots", "namespaces", "trusted_prefixes", "installed", "providers",
               "earth_engine_project", "export_root", "work_dir")
RUN_TIMEOUT_SECONDS = 4 * 3600          # the Cloud Run task timeout (deploy/setup.py --task-timeout 4h, zero retries);
                                        # a shorter configured budget is allowed, a longer one needs a deployment revision
CLEANUP_RESERVE_SECONDS = 900           # EETransport / CloudSourceAcquirer cancellation reserve before the deadline
RESERVATION_SCHEMA = "ipcch-v2-run-reservation-v1"


class EntrypointError(RuntimeError):
    """The deployment config or the request route is invalid; nothing was executed."""


def load_config(path: str) -> dict[str, Any]:
    cfg = json.load(open(path))
    missing = [k for k in CONFIG_KEYS if k not in cfg]
    if missing:
        raise EntrypointError(f"deployment config lacks {missing}")
    for key in ("roots", "store_roots", "trusted_prefixes", "installed", "providers"):
        if set(cfg[key]) != {"smoke", "real"}:
            raise EntrypointError(f"config {key} must define exactly smoke and real")
    for mode in ("smoke", "real"):
        StoreRoot(mode, cfg["store_roots"][mode])                 # mode-suffixed retained roots (R48)
        inst = cfg["installed"][mode]
        need = ("envelope", "package_root", "bundle_dir") + (("fixture_root",) if mode == "smoke" else ())
        if any(k not in inst for k in need):
            raise EntrypointError(f"installed.{mode} needs {need}")
    if cfg["providers"]["smoke"] == cfg["providers"]["real"] or "real_providers" in cfg["providers"]["smoke"]:
        raise EntrypointError("smoke must use a fixture provider factory, never the real providers (R48)")
    run_v2.Deployment(store=None, roots=cfg["roots"])             # distinct, not nested
    timeout = cfg.get("run_timeout_seconds", RUN_TIMEOUT_SECONDS)
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not CLEANUP_RESERVE_SECONDS < timeout <= RUN_TIMEOUT_SECONDS:
        raise EntrypointError(f"run_timeout_seconds must be an integer above the {CLEANUP_RESERVE_SECONDS} s cleanup "
                              f"reserve and at most the {RUN_TIMEOUT_SECONDS} s job timeout")
    if "producer_asset_root" in cfg and not re.fullmatch(r"projects/[^/]+/assets/(?:[^/]+/)*", cfg["producer_asset_root"]):
        raise EntrypointError("producer_asset_root must be projects/<project>/assets/[folder/...] ending in /")
    return cfg


def resolve_factory(spec: str) -> Callable[..., Mapping[str, Any]]:
    module, _, name = spec.partition(":")
    return getattr(importlib.import_module(module), name)


def real_providers(*, cfg: Mapping[str, Any], store, client, run_id: str, roster, root=None, deadline_utc=None,
                   execution_month: str | None = None) -> dict[str, Any]:
    """The real provider route: the concrete EE transport (all climate bases), the table producer (this run's unsaved
    VI/PRCP/ET0/PATCH32 periods, ``table_producers``) and the GCS/HTTP acquirer (GPP/VIIRS), all under the run's
    persisted deadline."""
    import ee
    import requests

    from cloud.ipcch import climate as cl
    from cloud.ipcch import climate_run
    from cloud.ipcch.climate_ee import AssetRefs
    from cloud.ipcch.ee_transport import from_environment
    from cloud.ipcch.stores import VersionedTable
    from cloud.ipcch.table_producers import TableProducer
    from cloud.orchestrator.prepare import CloudSourceAcquirer

    if deadline_utc is None or root is None or execution_month is None:
        raise EntrypointError("real providers need the run's persisted deadline, retained store root and execution month")
    if "producer_asset_root" not in cfg:
        raise EntrypointError("real generation needs deployment producer_asset_root (the writable EE asset root)")
    transport = from_environment(project=cfg["earth_engine_project"], output_root=cfg["export_root"], run_id=run_id,
                                 deadline_utc=deadline_utc)
    acquirer = CloudSourceAcquirer(ee=ee, client=client, http=requests.Session(), store=store,
                                   output_root=cfg["export_root"], deadline_utc=deadline_utc)
    producer = TableProducer(transport, inputs=AssetRefs(), output_root=cfg["producer_asset_root"], run_id=run_id,
                             execution_month=execution_month)
    return {"climate_providers": climate_run.real_provider_factory(
                transport, roster=roster, producer=producer,
                tables=lambda base, temporal: VersionedTable(store, root, cl.table_name(base, temporal))),
            "gpp_acquirer": acquirer, "nightlight_acquirer": acquirer}


def real_fewsnet_runner(cfg: Mapping[str, Any], *, store, reader, client):
    """The real v2 FEWS NET route (R60): the existing preparation (FEWS NET scope) and delivery scoring in its
    per-system subprocess, published as a v2 member; EE/acquisition is built only when generation runs."""
    import subprocess
    import sys
    from pathlib import Path

    from cloud.ipcch import fews_adapter
    from cloud.orchestrator.delivery_job import PinnedDownloader

    fews = cfg.get("fewsnet") or {}
    if "image_uri" not in fews:
        raise EntrypointError("FEWS NET operations need deployment fewsnet.image_uri (the delivery job image)")

    def score(spec_path, system, out):
        subprocess.run([sys.executable, "-m", "cloud.orchestrator.delivery_job", "system", "--spec", str(spec_path),
                        "--system", system, "--out", str(out)], check=True)

    def acquirer():
        import ee
        import requests

        from cloud.orchestrator.prepare import CloudSourceAcquirer

        ee.Initialize(project=cfg["earth_engine_project"])
        return CloudSourceAcquirer(ee=ee, client=client, http=requests.Session(), store=store,
                                   output_root=cfg["roots"]["real"])
    return fews_adapter.runner(store=store, reader=reader, output_root=cfg["roots"]["real"],
                               work_root=Path(cfg["work_dir"]), image_uri=fews["image_uri"],
                               downloader_factory=lambda root: PinnedDownloader(client, root), score=score,
                               acquirer_factory=acquirer)


def run(cfg: Mapping[str, Any], *, request_uri: str, request_generation: str, store, reader, client=None,
        now: datetime | None = None, fewsnet_runner=None) -> dict[str, Any]:
    """Execute one v2 request (see module docstring); ``reader.read_bytes(uri, generation)`` reads exact generations."""
    now = now or datetime.now(timezone.utc)
    data = reader.read_bytes(request_uri, request_generation)
    if data is None:
        raise EntrypointError(f"request {request_uri}#{request_generation} not found")
    body = json.loads(data)
    if not v2.is_v2(body):
        raise EntrypointError("not a v2 request; the v1 route handles it")
    # structure + mode/namespace rules FIRST, without any current read; only a real IPCCH inference published to current
    # then reads the production pointer for R39 (smoke never reads real state, R48; publication rechecks R39 anyway)
    pre = v2.validate_request_v2(body, request_uri=request_uri, request_generation=request_generation, now_utc=now,
                                 production_namespace=cfg["namespaces"]["production"],
                                 smoke_namespace=cfg["namespaces"]["smoke"], current_ipcch_execution_month=None)
    mode_root = cfg["roots"][pre["mode"]].rstrip("/")
    reservation_uri = f"{mode_root}/runs/{pre['run_id']}/v2_reservation.json"
    status_uri = f"{mode_root}/runs/{pre['run_id']}/v2_run_status.json"
    identity = {"uri": request_uri, "generation": str(request_generation), "sha256": hashlib.sha256(data).hexdigest()}
    # a redelivered identity returns its durable status before any state read or admission (an old month is not
    # re-admitted against a newer current) and before any provider/context is built
    replayed = _replay(store, reservation_uri, status_uri, identity, pre["run_id"])
    if replayed is not None:
        return replayed
    current_month = None
    if pre["mode"] == "real" and pre["operations"]["ipcch_inference"] and pre["publication"] == "current":
        current = pub.read_current(store, cfg["roots"]["real"], cfg["namespaces"]["production"])
        current_month = pub.ipcch_execution_month(current["record"])

    timeout = int(cfg.get("run_timeout_seconds", RUN_TIMEOUT_SECONDS))
    state: dict[str, Any] = {}

    def reserve(request):
        deadline = now + timedelta(seconds=timeout)
        record = {"schema": RESERVATION_SCHEMA, "run_id": request["run_id"], "mode": request["mode"], "request": identity,
                  "reserved_at": _iso(now), "deadline_utc": _iso(deadline), "run_timeout_seconds": timeout}
        try:
            store.write_text(reservation_uri, json.dumps(record, indent=2, sort_keys=True) + "\n", if_generation_match=0)
        except Exception as exc:                       # a concurrent duplicate won the reservation
            again = _replay(store, reservation_uri, status_uri, identity, request["run_id"])
            if again is not None:
                return again
            raise EntrypointError(f"run {request['run_id']} could not be reserved ({exc})") from exc
        state.update(reserved=True, deadline=deadline)
        return None

    def resolve(uri, generation):
        blob = reader.read_bytes(uri, generation)
        return None if blob is None else hashlib.sha256(blob).hexdigest()

    admit_kwargs = dict(request_uri=request_uri, request_generation=request_generation, now_utc=now,
                        production_namespace=cfg["namespaces"]["production"], smoke_namespace=cfg["namespaces"]["smoke"],
                        current_ipcch_execution_month=current_month, resolve=resolve, read=reader.read_bytes,
                        trusted_prefixes=cfg["trusted_prefixes"],
                        batch_roots={m: cfg["store_roots"][m] for m in ("smoke", "real")})

    def read_ref(ref):
        blob = reader.read_bytes(ref["uri"], ref["generation"])
        if blob is None or hashlib.sha256(blob).hexdigest() != ref["sha256"]:
            raise EntrypointError(f"{ref['uri']}#{ref['generation']} missing or not the pinned bytes")
        return blob

    def context(request):
        mode = request["mode"]
        inst = cfg["installed"][mode]
        binding = bd.verify_combination(inst["envelope"], inst["package_root"], mode=mode,
                                        expected_envelope_sha256=request["ipcch"]["model_combination"]["envelope"]["sha256"],
                                        fixture_root=inst.get("fixture_root") if mode == "smoke" else None)
        root = StoreRoot(mode, cfg["store_roots"][mode])
        roster = [str(a) for a in initial._read(store, root, "fixed/roster.csv")["admin_code"]]
        providers = {"climate_providers": None, "gpp_acquirer": None, "nightlight_acquirer": None}
        if request["operations"]["ipcch_generation"]:   # acquisition only when generating (inference never needs EE)
            providers = resolve_factory(cfg["providers"][mode])(cfg=cfg, store=store, client=client,
                                                                run_id=request["run_id"], roster=roster, root=root,
                                                                deadline_utc=state["deadline"],
                                                                execution_month=request["execution_month"])
        work = os.path.join(cfg["work_dir"], request["run_id"])
        os.makedirs(work, exist_ok=False)                          # one work dir per run
        return run_v2.IpcchContext(store=store, root=root, binding=binding, package_root=inst["package_root"],
                                   bundle_dir=inst["bundle_dir"], read_ref=read_ref, workdir=work, roster=roster,
                                   envelope_path=inst["envelope"], **providers)

    deployment = run_v2.Deployment(store=store, roots=cfg["roots"])
    fews_selected = pre["operations"]["fewsnet_generation"] or pre["operations"]["fewsnet_inference"]
    if fews_selected and fewsnet_runner is None:        # built only when FEWS NET is selected (real only, R38)
        fewsnet_runner = real_fewsnet_runner(cfg, store=store, reader=reader, client=client)
    try:
        outcome = run_v2.run_request(body, admit_kwargs=admit_kwargs, ipcch_context=context, deployment=deployment,
                                     fewsnet_runner=fewsnet_runner, reserve=reserve)
    except Exception as exc:
        if state.get("reserved"):                      # reserved, then failed: a durable failed status (best effort)
            failed = {"run_id": pre["run_id"], "mode": pre["mode"], "status": "failed",
                      "reason": f"{type(exc).__name__}: {exc}", "systems": {}}
            try:
                store.write_text(status_uri, json.dumps(failed, indent=2, sort_keys=True) + "\n", if_generation_match=0)
            except Exception:
                pass                                   # stays indeterminate: still never relaunched under this ID
        raise
    if outcome.get("replayed"):
        return dict(outcome)
    status = {k: v for k, v in outcome.items() if k != "systems"}
    status["systems"] = {s: _durable(o) for s, o in outcome["systems"].items()}
    status["deadline_utc"] = _iso(state["deadline"])
    store.write_text(status_uri, json.dumps(status, indent=2, sort_keys=True, default=str) + "\n", if_generation_match=0)
    return {**status, "status_uri": status_uri}


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _replay(store, reservation_uri: str, status_uri: str, identity: Mapping[str, str], run_id: str):
    """None when the run ID is unreserved; the durable status (``replayed``) for the same completed identity; otherwise
    an ``EntrypointError`` (changed request, or reserved without a final status - never launched again)."""
    if store.get_metadata(reservation_uri) is None:
        return None
    record = json.loads(store.read_text(reservation_uri))
    if record.get("request") != dict(identity):
        raise EntrypointError(f"run {run_id} is reserved for request {record.get('request')}; a changed request "
                              f"needs a new run ID")
    if store.get_metadata(status_uri) is None:
        raise EntrypointError(f"run {run_id} was reserved at {record.get('reserved_at')} and has no final status "
                              "(active, interrupted or indeterminate); it is not launched again - retry with a new run ID")
    return {**json.loads(store.read_text(status_uri)), "status_uri": status_uri, "replayed": True}


def _durable(outcome: Mapping[str, Any]) -> dict[str, Any]:
    """A system outcome for the run status: status, reason, failing step/operation, the structured generation report
    (saved updates, warnings, gaps - R29/R41) and the result without prediction frames (summaries kept)."""
    out = {k: outcome.get(k) for k in ("status", "reason", "step", "failed_operation", "report")}
    result = outcome.get("result")
    if isinstance(result, Mapping):
        slim = {k: v for k, v in result.items() if k != "inference"}
        inf = result.get("inference")
        if isinstance(inf, Mapping):
            slim["inference"] = {"batch_id": inf.get("batch_id"), "manifest_ref": inf.get("manifest_ref"),
                                 "horizons": {str(h): {"rows": int(len(v["predictions"])), "summary": v.get("summary")}
                                              for h, v in inf.get("horizons", {}).items()}}
        out["result"] = slim
    else:
        out["result"] = result
    return out


def initialise_store(cfg: Mapping[str, Any], mode: str, *, store, acceptor: str | None = None,
                     now: datetime | None = None) -> dict[str, Any]:
    """One-time initialisation of a mode's retained store from the INSTALLED binding (operator step before the first
    run of that mode): verify the installed envelope/package (real: accepted; smoke: with its fixture root), then
    real - append the envelope-bound finalized acceptance entries of the handoff bundle (R45); smoke - admit the fixture
    bundle only (R48) and append fixture acceptance records for its manifest files (FCC10: smoke validates fixture
    records only); then the two-phase ``initial.initialise`` (whole-bundle validation before any commit, pairing last)."""
    from cloud.ipcch.stores import AcceptanceManifest

    if mode not in ("smoke", "real"):
        raise EntrypointError(f"mode must be smoke or real, got {mode!r}")
    inst = cfg["installed"][mode]
    binding = bd.verify_combination(inst["envelope"], inst["package_root"], mode=mode,
                                    fixture_root=inst.get("fixture_root") if mode == "smoke" else None)
    root = StoreRoot(mode, cfg["store_roots"][mode])
    if mode == "real":
        acceptance = initial.install_acceptance(store, root, inst["bundle_dir"], binding=binding)
    else:
        if not acceptor:
            raise EntrypointError("smoke initialisation needs --acceptor for its fixture acceptance records")
        manifest = bd.verify_fixture_bundle(binding, inst["bundle_dir"])["_manifest"]
        have = AcceptanceManifest(store, root).records()
        present = set(zip(have["name"], have["sha256"])) if len(have) else set()
        stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
        new = [{"name": rel, "sha256": v["sha256"], "source": "fixture bundle", "acceptor": acceptor,
                "accepted_at": stamp, "kind": "delivered"}
               for rel, v in sorted(manifest["files"].items()) if (rel, v["sha256"]) not in present]
        if new:
            AcceptanceManifest(store, root).append(new)
        acceptance = {"appended": len(new), "fixture": True}
    report = initial.initialise(store, root, inst["bundle_dir"], binding=binding)
    return {"mode": mode, "store_root": root.uri, "combination_id": binding.combination_id,
            "acceptance": acceptance, "initialise": report}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="v2 IPCCH/FEWS NET request route")
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    for flag in ("--config", "--request-uri", "--request-generation"):
        r.add_argument(flag, required=True)
    i = sub.add_parser("initialise", help="one-time retained-store initialisation of a mode from the installed binding")
    i.add_argument("--config", required=True)
    i.add_argument("--mode", required=True, choices=["real", "smoke"])
    i.add_argument("--acceptor", help="smoke only: who accepts the fixture records")
    args = parser.parse_args(argv)
    from google.cloud import storage

    from cloud.common.object_store import GCSObjectStore
    from cloud.orchestrator.prepare import GcsPinnedReader

    client = storage.Client()
    if args.command == "initialise":
        report = initialise_store(load_config(args.config), args.mode, store=GCSObjectStore(client), acceptor=args.acceptor)
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
        return 0
    status = run(load_config(args.config), request_uri=args.request_uri, request_generation=args.request_generation,
                 store=GCSObjectStore(client), reader=GcsPinnedReader(client), client=client)
    print(json.dumps(status, indent=2, sort_keys=True, default=str))
    return 0 if status["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
