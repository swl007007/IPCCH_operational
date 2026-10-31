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
   ``failed`` with its reason, and the run is ``partial_success`` when exactly one failed.

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
    climate_providers: Callable[[Any, str], Any] | None   # (derived windows, origin) -> ClimateProviders; generation only
    gpp_acquirer: Any                                     # None for inference-only (acquisition never needed)
    nightlight_acquirer: Any
    workdir: str
    roster: list                                    # the store's bound roster (fixed/roster.csv order)
    envelope_path: str = ""                         # the installed envelope file the binding was verified from
    publish_inputs: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]] | None = None
    # (request, scored result) -> member inputs for delivery_member.write_member (census bytes, area identity,
    # geometry, feature provenance ...); see member_inputs()


@dataclass(frozen=True)
class Deployment:
    """Where a mode's runs publish and lock: ``roots[mode]`` holds runs/, deliveries/, candidates/, conflict records,
    locks/ and the pointer namespace. Smoke and real roots are distinct and never nested (R36/R48)."""
    store: Any
    roots: Mapping[str, str]

    def __post_init__(self):
        if set(self.roots) != {"smoke", "real"}:
            raise ValueError("deployment roots must name exactly smoke and real")
        a, b = (self.roots["smoke"].rstrip("/") + "/", self.roots["real"].rstrip("/") + "/")
        if a.startswith(b) or b.startswith(a):
            raise ValueError("smoke and real roots must be distinct and not nested (R48)")


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
        out["_manifest"] = manifest
    return out


def member_inputs(request: Mapping[str, Any], ctx: IpcchContext, result: Mapping[str, Any]) -> dict[str, Any]:
    """The verified sources of the IPCCH delivery member: the pinned country reference (inference input), the bound
    store's area identity, the bound bundle's roster geometry (real: verify_handoff; smoke: admitted fixture bundle),
    the batch's feature provenance and the binding/package/envelope."""
    import json
    import os
    from cloud.batch import remote_sources as rs
    from cloud.ipcch import delivery_member as dm
    from cloud.ipcch import geography, initial

    manifest = result["_manifest"]
    if request["mode"] == "real":
        ident = bd.verify_handoff(ctx.binding, ctx.bundle_dir)
    else:
        ident = bd.verify_fixture_bundle(ctx.binding, ctx.bundle_dir)
    fc, _ = geography.roster_geometries(ctx.bundle_dir, ident["_manifest"], ctx.roster)
    rs.native_geometries(fc, roster=ctx.roster)
    return {"manifest": manifest, "scored": result["inference"]["horizons"], "binding": ctx.binding,
            "package_root": ctx.package_root, "envelope_path": ctx.envelope_path,
            "census_bytes": ctx.read_ref(request["ipcch"]["country_reference"]),
            "area_identity": initial._read(ctx.store, ctx.root, "fixed/area_identity.csv"),
            "geometry": dm.geometry_geojson(fc), "roster": list(ctx.roster),
            "feature_provenance": bi.read_feature_provenance(ctx.store, manifest, batch_root=ctx.root.uri)}


def publish_ipcch(request: Mapping[str, Any], ctx: IpcchContext, result: dict[str, Any], deployment: Deployment,
                  expected_generation: str) -> dict[str, Any]:
    """Candidate or current publication of this run's IPCCH member (inference only; generation-only never publishes)."""
    from cloud.ipcch import release_v2

    try:
        inputs = member_inputs(request, ctx, result)
        published = release_v2.publish_ipcch_run(
            deployment.store, deployment.roots[request["mode"]], namespace=request["release"]["namespace"],
            run_id=request["run_id"], mode=request["mode"], publication=request["publication"],
            expected_pointer_generation=expected_generation, request_ref=request["request"], member_inputs=inputs,
            workdir=ctx.workdir)
    except Exception as exc:
        raise IpcchRunFailure("publication", exc, {k: v for k, v in result.items() if k != "_manifest"}) from exc
    if published["status"] == "publication_failed":           # no retry, no rebase; batch/predictions kept
        raise IpcchRunFailure("publication", RuntimeError(published.get("reason", "pointer moved")),
                              {**{k: v for k, v in result.items() if k != "_manifest"}, "publication": published})
    return published


def run_request(data: Mapping[str, Any], *, admit_kwargs: Mapping[str, Any],
                ipcch_context: Callable[[Mapping[str, Any]], IpcchContext] | None = None,
                fewsnet_runner: Callable[[Mapping[str, Any], str], Any] | None = None,
                deployment: Deployment | None = None,
                reserve: Callable[[Mapping[str, Any]], Mapping[str, Any] | None] | None = None) -> dict[str, Any]:
    """With a ``deployment``: the executed systems' locks are taken after admission (all or none; a busy system rejects
    the whole request before any work, R50) and held through publication; IPCCH inference publishes candidate/current;
    a run executing both systems chains the pointer generation it produced itself (never another run's).
    ``reserve`` (task 10-30): called once with the admitted request before any lock or mutation; it records the run's
    identity create-only and returns the durable outcome instead when this identity already completed."""
    from cloud.ipcch import locks

    request = v2.admit(data, **admit_kwargs)            # raises before anything executes (R17)
    if reserve is not None:
        replayed = reserve(request)
        if replayed is not None:
            return dict(replayed)
    ops = request["operations"]
    systems = {"ipcch": ops["ipcch_generation"] or ops["ipcch_inference"],
               "fewsnet": ops["fewsnet_generation"] or ops["fewsnet_inference"]}
    held = []
    if deployment is not None:
        held = locks.acquire(deployment.store, deployment.roots[request["mode"]],
                             [s for s, sel in systems.items() if sel], request["run_id"])
    outcomes: dict[str, Any] = {}
    expected = str(request["release"]["expected_pointer_generation"])
    try:
        for system, selected in systems.items():
            if not selected:
                continue
            try:
                if system == "ipcch":
                    if ipcch_context is None:
                        raise RuntimeError("no IPCCH runtime configured")
                    ctx = ipcch_context(request)
                    result = run_ipcch(request, ctx)
                    if deployment is not None and ops["ipcch_inference"]:
                        result["publication"] = publish_ipcch(request, ctx, result, deployment, expected)
                        if result["publication"]["status"] == "published":
                            expected = str(result["publication"]["pointer_generation"])   # this run's own write
                    result.pop("_manifest", None)
                else:
                    if fewsnet_runner is None:
                        raise RuntimeError("no FEWS NET runtime configured")
                    result = fewsnet_runner(request, expected)
                outcomes[system] = {"status": "succeeded", "result": result}
            except Exception as exc:                    # one system's runtime failure never stops the other (R17)
                partial = getattr(exc, "partial", None)
                outcomes[system] = {"status": "failed", "reason": f"{type(exc).__name__}: {exc}",
                                    "step": getattr(exc, "step", None), "report": getattr(exc, "report", None),
                                    "failed_operation": getattr(exc, "operation", None),
                                    "result": {k: v for k, v in partial.items() if k != "_manifest"} if partial else None}
    finally:
        problems = locks.release(deployment.store, held) if held else []
    failed = [s for s, o in outcomes.items() if o["status"] == "failed"]
    status = "succeeded" if not failed else ("failed" if len(failed) == len(outcomes) else "partial_success")
    return {"run_id": request["run_id"], "mode": request["mode"], "status": status, "systems": outcomes,
            "lock_release_problems": problems,
            "derived": request.get("derived"), "verified_references": request["verified_references"]}
