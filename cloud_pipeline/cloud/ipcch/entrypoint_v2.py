"""Executable v2 request route (task 10-29; R5, R17, R36, R37, R39, R48, R50 and the CP4 rulings).

``python -m cloud.ipcch.entrypoint_v2 run --config deployment.json --request-uri gs://.../requests/<run>/run_manifest.json
--request-generation N`` (also reached from ``delivery_job run --v2-config`` when the request body is v2):

1. the request is read at its exact generation; the current IPCCH execution month for R39 is read from the
   production pointer of the deployment (``publication.ipcch_execution_month``);
2. ``run_v2.run_request``: admission (structure, trusted namespaces, every reference verified by exact generation +
   sha256) BEFORE anything else; per-system locks; IPCCH generation/inference; publication;
3. the IPCCH context of the request's mode is built from the deployment config: the INSTALLED envelope/package verified
   against the request's pinned envelope (``verify_combination`` with the pinned sha; smoke with its fixture root), the
   mode's retained store root, the bound bundle, and the mode's providers - real: ``EETransport.from_environment`` +
   ``climate_run.real_provider_factory`` and ``CloudSourceAcquirer`` (GPP/VIIRS); smoke: a configured fixture provider
   factory (never the real transport, R48);
4. a create-only run status is written under ``{mode root}/runs/{run_id}/v2_run_status.json``.

Config (JSON, validated): ``roots`` {smoke, real} (deliveries/pointer/locks/runs), ``store_roots`` {smoke, real}
(retained stores, each ending in its mode), ``namespaces`` {production, smoke}, ``trusted_prefixes`` {smoke, real},
``installed`` {mode: {envelope, package_root, bundle_dir[, fixture_root]}}, ``providers`` {mode: "module:function"},
``earth_engine_project``, ``export_root``, ``work_dir``.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from cloud.ipcch import binding as bd
from cloud.ipcch import initial
from cloud.ipcch import publication as pub
from cloud.ipcch import run_v2
from cloud.ipcch.stores import StoreRoot
from cloud.orchestrator import delivery_request_v2 as v2

CONFIG_KEYS = ("roots", "store_roots", "namespaces", "trusted_prefixes", "installed", "providers",
               "earth_engine_project", "export_root", "work_dir")


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
    return cfg


def resolve_factory(spec: str) -> Callable[..., Mapping[str, Any]]:
    module, _, name = spec.partition(":")
    return getattr(importlib.import_module(module), name)


def real_providers(*, cfg: Mapping[str, Any], store, client, run_id: str, roster, deadline_utc=None) -> dict[str, Any]:
    """The real provider route: the concrete EE transport (all climate bases) and the GCS/HTTP acquirer (GPP/VIIRS)."""
    import ee
    import requests

    from cloud.ipcch import climate_run
    from cloud.ipcch.ee_transport import from_environment
    from cloud.orchestrator.prepare import CloudSourceAcquirer

    transport = from_environment(project=cfg["earth_engine_project"], output_root=cfg["export_root"], run_id=run_id,
                                 deadline_utc=deadline_utc)
    acquirer = CloudSourceAcquirer(ee=ee, client=client, http=requests.Session(), store=store,
                                   output_root=cfg["export_root"], deadline_utc=deadline_utc)
    return {"climate_providers": climate_run.real_provider_factory(transport, roster=roster),
            "gpp_acquirer": acquirer, "nightlight_acquirer": acquirer}


def run(cfg: Mapping[str, Any], *, request_uri: str, request_generation: str, store, reader, client=None,
        now: datetime | None = None) -> dict[str, Any]:
    """Execute one v2 request (see module docstring); ``reader.read_bytes(uri, generation)`` reads exact generations."""
    now = now or datetime.now(timezone.utc)
    data = reader.read_bytes(request_uri, request_generation)
    if data is None:
        raise EntrypointError(f"request {request_uri}#{request_generation} not found")
    body = json.loads(data)
    if not v2.is_v2(body):
        raise EntrypointError("not a v2 request; the v1 route handles it")
    current = pub.read_current(store, cfg["roots"]["real"], cfg["namespaces"]["production"])

    def resolve(uri, generation):
        blob = reader.read_bytes(uri, generation)
        return None if blob is None else hashlib.sha256(blob).hexdigest()

    admit_kwargs = dict(request_uri=request_uri, request_generation=request_generation, now_utc=now,
                        production_namespace=cfg["namespaces"]["production"], smoke_namespace=cfg["namespaces"]["smoke"],
                        current_ipcch_execution_month=pub.ipcch_execution_month(current["record"]), resolve=resolve,
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
        providers = resolve_factory(cfg["providers"][mode])(cfg=cfg, store=store, client=client,
                                                            run_id=request["run_id"], roster=roster)
        work = os.path.join(cfg["work_dir"], request["run_id"])
        os.makedirs(work, exist_ok=False)                          # one work dir per run
        return run_v2.IpcchContext(store=store, root=root, binding=binding, package_root=inst["package_root"],
                                   bundle_dir=inst["bundle_dir"], read_ref=read_ref, workdir=work, roster=roster,
                                   envelope_path=inst["envelope"], **providers)

    deployment = run_v2.Deployment(store=store, roots=cfg["roots"])
    outcome = run_v2.run_request(body, admit_kwargs=admit_kwargs, ipcch_context=context, deployment=deployment)
    status = {k: v for k, v in outcome.items() if k != "systems"}
    status["systems"] = {s: {k: v for k, v in o.items() if k in ("status", "reason", "step", "failed_operation")}
                         | ({"publication": (o.get("result") or {}).get("publication"),
                             "batch": (o.get("result") or {}).get("batch")} if isinstance(o.get("result"), dict) else {})
                         for s, o in outcome["systems"].items()}
    uri = f"{cfg['roots'][outcome['mode']].rstrip('/')}/runs/{outcome['run_id']}/v2_run_status.json"
    store.write_text(uri, json.dumps(status, indent=2, sort_keys=True, default=str) + "\n", if_generation_match=0)
    return {**status, "status_uri": uri}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="v2 IPCCH/FEWS NET request route")
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    for flag in ("--config", "--request-uri", "--request-generation"):
        r.add_argument(flag, required=True)
    args = parser.parse_args(argv)
    from google.cloud import storage

    from cloud.common.object_store import GCSObjectStore
    from cloud.orchestrator.prepare import GcsPinnedReader

    client = storage.Client()
    status = run(load_config(args.config), request_uri=args.request_uri, request_generation=args.request_generation,
                 store=GCSObjectStore(client), reader=GcsPinnedReader(client), client=client)
    print(json.dumps(status, indent=2, sort_keys=True, default=str))
    return 0 if status["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
