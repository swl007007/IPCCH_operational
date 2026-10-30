"""v2 request execution without publication (task 10-29; R5, R17, R19, R36, R48, R52, R60).

``run_request`` is the single entry point for a v2 request:

1. ``delivery_request_v2.admit`` - the whole request (incl. the complete FEWS NET delivery) is validated and EVERY
   pinned reference verified BEFORE anything else; an invalid request executes nothing (R17): no lock, no collection,
   no store read/write, no provider or runner call;
2. IPCCH (when selected): generation -> this run's immutable batch (R52); inference from this run's batch
   (generation + inference, R5) or from the request's named batch (inference-only, R19); predictions carry
   ``mode`` and ``batch_id`` (R36). Generation-only produces the batch and its summary and never predictions;
3. FEWS NET (when selected): the injected runner maps the operations onto the existing prepare/deliver mechanisms (R60);
4. a runtime failure of one selected system never stops the other (R17): each system's outcome is ``succeeded`` or
   ``failed`` with its reason, and the run is ``partial`` when exactly one failed.

Publication (pointer, inheritance, locks, current replacement) is applied by the caller on the returned outcomes (CP4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from cloud.ipcch import batch_inference as bi
from cloud.ipcch import binding as bd
from cloud.ipcch.generation import Generation
from cloud.orchestrator import delivery_request_v2 as v2


@dataclass
class IpcchContext:
    """Everything the IPCCH operations need for one mode (smoke or real), constructed by the deployment."""
    store: Any
    root: Any                                       # StoreRoot of the request's mode
    binding: bd.Binding                             # verified combination binding for the request's model_combination
    package_root: str                               # the installed, bound package directory
    bundle_dir: str                                 # real: the accepted bundle; smoke: the fixture bundle
    read_ref: Callable[[Mapping[str, str]], bytes]
    climate_providers: Callable[[Any, str], Any]      # (derived season windows, origin) -> ClimateProviders
    gpp_acquirer: Any
    nightlight_acquirer: Any
    workdir: str
    roster: list                                    # the store's bound roster (fixed/roster.csv order)


class IpcchRunFailure(RuntimeError):
    """An IPCCH operation failed; ``partial`` keeps what already succeeded (e.g. the generated batch id/ref) so a
    successful generation is reported and reusable even when this run's inference fails."""

    def __init__(self, operation: str, cause: BaseException, partial: Mapping[str, Any]):
        super().__init__(f"IPCCH {operation} failed: {type(cause).__name__}: {cause}")
        self.operation, self.cause, self.partial = operation, cause, dict(partial)
        self.step, self.report = getattr(cause, "step", None), getattr(cause, "report", None)


def run_ipcch(request: Mapping[str, Any], ctx: IpcchContext) -> dict[str, Any]:
    # the request's pinned envelope (verified by admit) must be the installed, verified binding - before any access
    bd.require_selection(ctx.binding, request["ipcch"]["model_combination"])
    ops = request["operations"]
    mode, M = request["mode"], request["execution_month"]
    out: dict[str, Any] = {"mode": mode, "execution_month": M}
    if ops["ipcch_generation"]:
        gen = Generation(store=ctx.store, root=ctx.root, binding=ctx.binding, bundle_dir=ctx.bundle_dir, request=request,
                         read_ref=ctx.read_ref, batch_root=ctx.root.uri, climate_providers=ctx.climate_providers,
                         gpp_acquirer=ctx.gpp_acquirer, nightlight_acquirer=ctx.nightlight_acquirer, workdir=ctx.workdir)
        try:
            produced = gen.run()
        except Exception as exc:
            raise IpcchRunFailure("generation", exc, out) from exc
        out["batch"] = produced
        out["generation"] = {"status": "succeeded", **produced}
        batch_id, ref = produced["batch_id"], produced["manifest_ref"]
    elif ops["ipcch_inference"]:
        named = request["ipcch"]["feature_batch"]
        batch_id, ref = named["batch_id"], named["manifest"]
    if ops["ipcch_inference"]:
        try:
            manifest, frames = bi.load_batch(ctx.store, ref, batch_root=ctx.root.uri, batch_id=batch_id, mode=mode,
                                             execution_month=M, binding=ctx.binding, roster=ctx.roster)
            scored = bi.score_batch(manifest, frames, ctx.package_root, ctx.binding)
        except Exception as exc:                       # the generated batch stays reported and reusable (R5/R52)
            raise IpcchRunFailure("inference", exc, out) from exc
        out["inference"] = {"batch_id": batch_id, "manifest_ref": dict(ref), "horizons": scored}
    return out


def run_request(data: Mapping[str, Any], *, admit_kwargs: Mapping[str, Any],
                ipcch_context: Callable[[Mapping[str, Any]], IpcchContext] | None = None,
                fewsnet_runner: Callable[[Mapping[str, Any]], Any] | None = None) -> dict[str, Any]:
    request = v2.admit(data, **admit_kwargs)            # raises before anything executes (R17)
    ops = request["operations"]
    systems = {"ipcch": ops["ipcch_generation"] or ops["ipcch_inference"],
               "fewsnet": ops["fewsnet_generation"] or ops["fewsnet_inference"]}
    outcomes: dict[str, Any] = {}
    for system, selected in systems.items():
        if not selected:
            continue
        try:
            if system == "ipcch":
                if ipcch_context is None:
                    raise RuntimeError("no IPCCH runtime configured")
                result = run_ipcch(request, ipcch_context(request))
            else:
                if fewsnet_runner is None:
                    raise RuntimeError("no FEWS NET runtime configured")
                result = fewsnet_runner(request)
            outcomes[system] = {"status": "succeeded", "result": result}
        except Exception as exc:                        # one system's runtime failure never stops the other (R17)
            outcomes[system] = {"status": "failed", "reason": f"{type(exc).__name__}: {exc}",
                                "step": getattr(exc, "step", None), "report": getattr(exc, "report", None),
                                "failed_operation": getattr(exc, "operation", None),
                                "result": getattr(exc, "partial", None)}
    failed = [s for s, o in outcomes.items() if o["status"] == "failed"]
    status = "succeeded" if not failed else ("failed" if len(failed) == len(outcomes) else "partial")
    return {"run_id": request["run_id"], "mode": request["mode"], "status": status, "systems": outcomes,
            "derived": request.get("derived"), "verified_references": request["verified_references"]}
