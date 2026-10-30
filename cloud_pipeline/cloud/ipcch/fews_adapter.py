"""v2 FEWS NET operations on the existing mechanisms (task 10-29; R60 and the Supervisor D1-D3 rulings, design.md
"R60 FEWS adapter wiring"). Real mode only (R38: smoke selects no FEWS NET operation).

* generation = the existing preparation (``prepare.run_prepare``) of the admitted, pinned ``fewsnet.prepare_request``
  with the FEWS NET-only execution scope (``systems=("fewsnet",)``: no IPCCH roster/history read, acquisition or
  output although the existing schema declares both systems). It then writes, create-only beside the prepared
  manifest, the generation SOURCE BINDING ``prepared/<prepare_id>/fewsnet_v2_sources.json``: the run's ACLED/WFP
  keep/refresh choices (pinned refs + converter contract) bound to the exact prepared-manifest identity. A later
  inference-only run therefore applies exactly the refresh choices of its generation (D2: gen-only -> inf-only ==
  gen+inf); a snapshot without a binding is refused for v2 inference-only (no silently lost refresh choice).
* inference = the existing delivery scoring on a v1-shaped FEWS NET-only request built from ``fewsnet.delivery``, the
  snapshot (this run's, or the explicitly referenced one) and the bound choices, through
  ``delivery_job.publish_scored_member`` - the same function the legacy single-system route uses: ``prepare_inputs``
  (all pinned refs, acceptance, environment, packages; keep = the FEWS-row projection of the pinned retained
  snapshot against the pinned FEWS history), ``deliver(system="fewsnet")`` in its subprocess, exact 0/6/12 packages,
  the FEWS-scoped checks, and ``publish_member_run(system="fewsnet")`` inheriting IPCCH and the activation.
  Gen+inf consumes exactly the snapshot it produced. No FEWS NET feature batch exists (R60).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

SOURCES_SCHEMA = "fewsnet-v2-generation-sources-v1"


class FewsRunFailure(RuntimeError):
    """A FEWS NET operation failed; ``partial`` keeps what already succeeded (e.g. the produced snapshot)."""

    def __init__(self, operation: str, cause: BaseException, partial: Mapping[str, Any]):
        super().__init__(f"FEWS NET {operation} failed: {type(cause).__name__}: {cause}")
        self.operation, self.cause, self.partial = operation, cause, dict(partial)


def sources_uri(output_root: str, prepare_id: str) -> str:
    return f"{output_root.rstrip('/')}/prepared/{prepare_id}/fewsnet_v2_sources.json"


def _ref(store, uri: str) -> dict[str, str]:
    meta = store.get_metadata(uri)
    data = store.read_text(uri).encode("utf-8")
    if meta is None or store.get_metadata(uri).generation != meta.generation:
        raise RuntimeError(f"{uri} is missing or moved while read")
    return {"uri": uri, "generation": str(meta.generation), "sha256": hashlib.sha256(data).hexdigest()}


def generate(request: Mapping[str, Any], *, store, reader, acquirer, output_root: str, workdir: Path) -> dict:
    """The existing preparation, FEWS NET scope, plus the create-only generation source binding."""
    from cloud.orchestrator.prepare import run_prepare

    prepare = request["fewsnet_prepare"]                  # validated pinned body (admission, D1)
    Path(workdir).mkdir(parents=True, exist_ok=True)
    run_prepare(prepare, store=store, reader=reader, acquirer=acquirer, output_root=output_root, workdir=Path(workdir),
                systems=("fewsnet",))
    manifest = _ref(store, f"{output_root.rstrip('/')}/prepared/{prepare['prepare_id']}/prepared_manifest.json")
    fews = request["fewsnet"]
    binding = {"schema": SOURCES_SCHEMA, "prepare_id": prepare["prepare_id"], "origin_month": prepare["origin_month"],
               "prepared_manifest": manifest, "acled": dict(fews["acled"]), "wfp": dict(fews["wfp"]),
               "run_id": request["run_id"], "request": dict(request["request"])}
    meta = store.write_text(sources_uri(output_root, prepare["prepare_id"]),
                            json.dumps(binding, indent=2, sort_keys=True) + "\n", if_generation_match=0)
    return {"prepared_snapshot": {"prepare_id": prepare["prepare_id"], "origin_month": prepare["origin_month"],
                                  "manifest": manifest},
            "sources_binding": {"uri": sources_uri(output_root, prepare["prepare_id"]), "generation": str(meta.generation)}}


def bound_choices(store, output_root: str, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """The ACLED/WFP choices bound to exactly this prepared snapshot by its generation (refused when absent)."""
    uri = sources_uri(output_root, snapshot["prepare_id"])
    if store.get_metadata(uri) is None:
        raise RuntimeError(f"prepared snapshot {snapshot['prepare_id']} has no v2 FEWS NET generation source binding "
                           f"({uri}); its ACLED/WFP refresh choices are unknown - not scored")
    binding = json.loads(store.read_text(uri))
    if binding.get("schema") != SOURCES_SCHEMA or binding.get("prepare_id") != snapshot["prepare_id"]:
        raise RuntimeError(f"{uri} is not the generation source binding of {snapshot['prepare_id']}")
    if {k: str(v) for k, v in binding["prepared_manifest"].items()} != {k: str(v) for k, v in snapshot["manifest"].items()}:
        raise RuntimeError(f"{uri} binds another prepared manifest than the referenced snapshot")
    return {"acled": binding["acled"], "wfp": binding["wfp"], "binding": {"uri": uri,
                                                                          "generation": str(store.get_metadata(uri).generation)}}


def v1_request(request: Mapping[str, Any], snapshot: Mapping[str, Any], choices: Mapping[str, Any]) -> dict[str, Any]:
    """The v1-shaped FEWS NET-only scoring request the existing delivery path consumes (structural fields only)."""
    delivery = request["fewsnet"]["delivery"]
    return {"run_id": request["run_id"], "origin_month": snapshot["origin_month"], "prepared_snapshot": dict(snapshot),
            "acled": dict(choices["acled"]), "wfp": dict(choices["wfp"]), "models": list(delivery["models"]),
            "assets": dict(delivery["assets"]), "diagnostics": list(delivery["diagnostics"]),
            "contracts": dict(delivery["contracts"]), "runtime": dict(request["runtime"]),
            "release": dict(request["release"]), "request": dict(request["request"]), "validation_level": "structural",
            "execution": {"remote_update": False, "inference_systems": ["fewsnet"], "prepare_request": None,
                          "inherit": {}, "publication": request["publication"]}}


def runner(*, store, reader, output_root: str, work_root: Path, image_uri: str, downloader_factory: Callable,
           score: Callable, acquirer_factory: Callable[[], Any] | None = None) -> Callable[[Mapping[str, Any], str], dict]:
    """``fewsnet_runner(request, expected_generation)`` for ``run_v2.run_request`` (real mode)."""
    from cloud.orchestrator import delivery_job as dj

    def run(request: Mapping[str, Any], expected_generation: str) -> dict:
        if request["mode"] != "real":
            raise RuntimeError("FEWS NET operations are real-mode only (R38)")
        ops = request["operations"]
        work = Path(work_root) / f"{request['run_id']}-fewsnet"
        work.mkdir(parents=True, exist_ok=False)
        out: dict[str, Any] = {}
        if ops["fewsnet_generation"]:
            try:
                acquirer = acquirer_factory() if acquirer_factory else None
                out["generation"] = generate(request, store=store, reader=reader, acquirer=acquirer,
                                             output_root=output_root, workdir=work / "prepare")
            except Exception as exc:
                raise FewsRunFailure("generation", exc, out) from exc
            snapshot = out["generation"]["prepared_snapshot"]
        else:
            snapshot = request["fewsnet"]["prepared_snapshot"]
        if ops["fewsnet_inference"]:
            try:
                choices = bound_choices(store, output_root, snapshot)
                shaped = v1_request(request, snapshot, choices)
                body = (json.dumps(shaped, indent=2, sort_keys=True) + "\n").encode()
                published = dj.publish_scored_member(
                    shaped, request["request"], body, "fewsnet", output_root=output_root, store=store,
                    downloader=downloader_factory(work / "inputs"), work=work, image_uri=image_uri, score=score,
                    publication=request["publication"], expected_pointer_generation=expected_generation,
                    source={"request_schema": "fewsnet-ipcch-delivery-request-v2", "prepare_id": snapshot["prepare_id"],
                            "sources_binding": choices["binding"]})
            except Exception as exc:
                raise FewsRunFailure("inference", exc, out) from exc
            out["inference"] = {"prepared_snapshot": dict(snapshot), "sources_binding": choices["binding"]}
            if published["status"] == "publication_failed":
                raise FewsRunFailure("publication", RuntimeError(published.get("reason", "pointer moved")),
                                     {**out, "publication": published})
            out["publication"] = published
        return out
    return run
