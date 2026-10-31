"""Operator submission of a v2 IPCCH monthly request (task 10-30; R9, AC9, D3, D5): the existing operator surface
(``pipeline.py submit``) turns the operator's 11 explicit keep/refresh choices and their associated files into the
pinned v2 request whose upload alone starts the event-driven run.

Order (identity preserving; nothing triggers before the end):

1. the selections (exactly the 11 IPCCH inputs: ACLED, WFP, history snapshot and the eight research families; refresh
   files as a local path, ``gs://object`` (latest generation pinned) or ``gs://object#generation``, with the declared
   interval/regions of their existing contracts) are validated STRUCTURALLY with provisional references (and a
   provisional, never persisted, time) and their planned upload locations are admitted to the mode's trusted
   namespace - an invalid selection uploads nothing;
2. ``--execute``: the run ID (no date in it) and the selections digest (choices + exact file bytes/objects) are saved
   in ``{work_dir}/runs-v2/<run_id>/state.json``; associated files are uploaded create-only under
   ``{inputs_prefix}/<run_id>/...`` (or pinned when already in GCS), each reference saved as soon as it exists, and
   the deployment's shared envelope / environment manifest / country reference are pinned. Upload time never selects
   the month (AC9);
3. FREEZE: ONE UTC instant is captured now - it fixes the routine execution month M and ``prepared_at`` (D5) - the
   current pointer is read fresh (expected generation; for real, the R39 current IPCCH month), the complete request
   is admitted locally exactly as the cloud entrypoint will (``delivery_request_v2.admit``: structure, mode/namespace
   rules, trusted prefixes, every reference's generation + sha256), and the request bytes and their instant are
   persisted together;
4. those persisted bytes are uploaded create-only to ``gs://<request bucket>/requests/<run_id>/run_manifest.json`` -
   the only execution-triggering object - LAST.

Re-running ``submit --run-id <id>`` resumes the same identity. Before the freeze it continues the uploads (a later
freeze takes its own instant: no request existed yet); after the freeze it re-uploads exactly the persisted bytes,
never a new month or body (a lost upload response is safe: the create-only upload accepts identical bytes). A different
selection under that run ID is refused. ``status`` reports v2 runs (``v2_run_status.json``/reservation/claim).
Preview (no ``--execute``) makes no cloud call.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from cloud.orchestrator import delivery_request_v2 as v2

SELECTIONS_SCHEMA = "ipcch-v2-selections-v1"
CHOICES = ("acled", "wfp", "history_snapshot", *v2.RESEARCH_FAMILIES)          # the 11 explicit keep/refresh inputs
STATE_DIR = "runs-v2"
_PROVISIONAL_SHA = "0" * 64


class SubmissionError(ValueError):
    """The selection or its submission is invalid; the execution-triggering request was not uploaded."""


def canonical(body: Any) -> bytes:
    return (json.dumps(body, indent=2, sort_keys=True) + "\n").encode("utf-8")


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def instant_fields(instant: datetime) -> dict[str, str]:
    """D5: M and prepared_at from ONE UTC instant (workstation timezone never matters)."""
    if instant.tzinfo is None:
        raise SubmissionError("the submission instant must be timezone-aware")
    utc = instant.astimezone(timezone.utc)
    return {"submitted_at": utc.strftime("%Y-%m-%dT%H:%M:%SZ"), "execution_month": utc.strftime("%Y-%m"),
            "prepared_at": utc.strftime("%Y-%m-%dT%H:%M:%SZ")}


# --------------------------------------------------------------------------- selections


def load_selections(path: str | Path) -> dict[str, Any]:
    body = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(body, dict) or body.get("schema") != SELECTIONS_SCHEMA:
        raise SubmissionError(f"selections must be a {SELECTIONS_SCHEMA} object")
    extra = sorted(set(body) - {"schema", "mode", "operations", "publication", "choices"})
    if extra:
        raise SubmissionError(f"selections carry unknown fields {extra}")
    if body.get("mode") not in v2.MODES:
        raise SubmissionError(f"selections.mode must be one of {v2.MODES} (no default)")
    ops = body.get("operations", ["ipcch_generation", "ipcch_inference"])
    if ops not in (["ipcch_generation"], ["ipcch_generation", "ipcch_inference"]):
        raise SubmissionError("routine submission runs IPCCH generation, optionally with inference "
                              "(operations: [ipcch_generation] or [ipcch_generation, ipcch_inference])")
    if body.get("publication", "current") not in v2.PUBLICATIONS:
        raise SubmissionError(f"selections.publication must be one of {v2.PUBLICATIONS}")
    choices = body.get("choices")
    if not isinstance(choices, dict) or sorted(choices) != sorted(CHOICES):
        missing = sorted(set(CHOICES) - set(choices or {}))
        unknown = sorted(set(choices or {}) - set(CHOICES))
        raise SubmissionError(f"selections.choices must declare exactly the 11 inputs {list(CHOICES)} "
                              f"(missing {missing}, unknown {unknown}); keep is never implied")
    for name, choice in choices.items():
        if not isinstance(choice, dict) or choice.get("action") not in ("keep", "refresh"):
            raise SubmissionError(f"choices.{name}.action must be keep or refresh")
        if choice["action"] == "refresh" and not isinstance(choice.get("file"), str):
            raise SubmissionError(f"choices.{name} refresh needs its file (local path or gs:// object)")
    return {"mode": body["mode"], "operations": ops, "publication": body.get("publication", "current"),
            "choices": choices}


def selections_sha256(selections: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical(selections)).hexdigest()


def _file_source(spec: str, base: Path) -> dict[str, Any]:
    """A refresh file: an existing GCS object (``gs://...`` latest, or ``#generation``) or a local file to upload."""
    if spec.startswith("gs://"):
        uri, _, generation = spec.partition("#")
        if generation and not re.fullmatch(r"[1-9][0-9]*", generation):
            raise SubmissionError(f"{spec}: a pinned GCS object is gs://bucket/object#generation")
        return {"kind": "gcs", "uri": uri, "generation": generation or None}
    path = (base / spec).resolve() if not Path(spec).is_absolute() else Path(spec)
    if not path.is_file():
        raise SubmissionError(f"{spec}: local file not found")
    return {"kind": "local", "path": str(path), "sha256": file_sha256(path), "name": path.name}


# --------------------------------------------------------------------------- request assembly


def _wire_choice(name: str, choice: Mapping[str, Any], ref: Mapping[str, str] | None) -> dict[str, Any]:
    if choice["action"] == "keep":
        return dict(choice)                 # verbatim: the v2 validator refuses any field beside the keep action
    fields = {k: v for k, v in choice.items() if k not in ("action", "file")}
    return {"action": "refresh", "file": dict(ref), **fields}


def build_request(*, run_id: str, selections: Mapping[str, Any], fields: Mapping[str, str], refs: Mapping[str, Any],
                  shared: Mapping[str, Any], combination_id: str, image_uri: str, operator: str, namespace: str,
                  expected_pointer_generation: str) -> dict[str, Any]:
    choices = selections["choices"]
    inference = "ipcch_inference" in selections["operations"]
    wire = {name: _wire_choice(name, choices[name], refs.get(name)) for name in CHOICES}
    ipcch = {"model_combination": {"combination_id": combination_id, "envelope": dict(shared["envelope"])},
             "acled": wire["acled"], "wfp": wire["wfp"], "history_snapshot": wire["history_snapshot"],
             "research_inputs": {f: wire[f] for f in v2.RESEARCH_FAMILIES}}
    if inference:
        ipcch["country_reference"] = dict(shared["country_reference"])
    return {"schema_version": v2.SCHEMA_VERSION, "run_id": run_id, "mode": selections["mode"],
            "execution_month": fields["execution_month"],
            "operations": {"ipcch_generation": True, "ipcch_inference": inference, "fewsnet_generation": False,
                           "fewsnet_inference": False},
            "ipcch": ipcch, "fewsnet": None, "publication": selections["publication"],
            "runtime": {"image_uri": image_uri, "environment_manifest": dict(shared["environment_manifest"])},
            "release": {"namespace": namespace, "expected_pointer_generation": str(expected_pointer_generation)},
            "operator": operator, "prepared_at": fields["prepared_at"]}


class Plan:
    """Everything a submission needs that does not depend on the cloud: deployment, selections, sources, URIs."""

    def __init__(self, cfg: Mapping[str, Any], selections_path: str | Path, run_id: str | None):
        from cloud.ipcch import entrypoint_v2

        self.cfg = cfg
        v2cfg = cfg.get("v2") or {}
        for key in ("deployment_config", "inputs_prefix", "envelope", "environment_manifest"):
            if key not in v2cfg:
                raise SubmissionError(f"project config v2.{key} is required for v2 submission")
        self.deployment = entrypoint_v2.load_config(v2cfg["deployment_config"])
        self.selections = load_selections(selections_path)
        self.mode = self.selections["mode"]
        self.namespace = self.deployment["namespaces"]["production" if self.mode == "real" else "smoke"]
        prefix = v2cfg["inputs_prefix"].get(self.mode) if isinstance(v2cfg["inputs_prefix"], dict) else None
        if not isinstance(prefix, str) or not prefix.startswith("gs://"):
            raise SubmissionError(f"project config v2.inputs_prefix.{self.mode} must be a gs:// prefix")
        self.inputs_prefix = prefix.rstrip("/")
        base = Path(selections_path).resolve().parent
        self.sources = {name: _file_source(c["file"], base) for name, c in self.selections["choices"].items()
                        if c["action"] == "refresh"}
        # shared envelope/environment manifest (one object for both modes) and the mode's country reference: a value
        # may be one spec or {"real": spec, "smoke": spec}
        self.shared_specs = {k: (v2cfg[k].get(self.mode) if isinstance(v2cfg[k], dict) else v2cfg[k])
                             for k in ("envelope", "environment_manifest", "country_reference") if k in v2cfg}
        self.shared_specs = {k: v for k, v in self.shared_specs.items() if v}
        if "ipcch_inference" in self.selections["operations"] and "country_reference" not in self.shared_specs:
            raise SubmissionError("IPCCH inference needs project config v2.country_reference")
        # the v2 runtime image is separate from the legacy top-level image_uri, which the legacy operator state
        # (initialized.json destination) and the legacy acceptance reports bind; it is required to execute
        self.image_uri = v2cfg.get("image_uri")
        if self.image_uri is not None and not re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", self.image_uri):
            raise SubmissionError("project config v2.image_uri must be digest pinned")
        self.run_id = run_id
        # the identity covers the choices AND the exact local bytes / GCS objects they name
        self.digest = selections_sha256({"selections": self.selections,
                                         "files": {n: src.get("sha256") or src["uri"] + "#" + str(src["generation"])
                                                   for n, src in sorted(self.sources.items())}})

    def new_run_id(self) -> str:
        return f"ipcch-{self.mode}-{uuid.uuid4().hex[:16]}"            # no date: the month is chosen at freeze

    def upload_uri(self, run_id: str, name: str) -> str:
        return f"{self.inputs_prefix}/{run_id}/{name}/{self.sources[name]['name']}"

    def request_uri(self, run_id: str) -> str:
        return f"gs://{self.cfg['request_bucket']}/requests/{run_id}/run_manifest.json"

    def provisional_refs(self, run_id: str) -> dict[str, dict[str, str]]:
        refs = {}
        for name, src in self.sources.items():
            if src["kind"] == "local":
                refs[name] = {"uri": self.upload_uri(run_id, name), "generation": "1", "sha256": src["sha256"]}
            else:
                refs[name] = {"uri": src["uri"], "generation": src["generation"] or "1", "sha256": _PROVISIONAL_SHA}
        return refs

    def check(self, body: Mapping[str, Any], fields: Mapping[str, str], request_uri: str) -> None:
        """Structure, mode rules and lexical namespace admission (no reference read)."""
        try:
            validated = v2.validate_request_v2(
                body, request_uri=request_uri, request_generation="1",
                now_utc=datetime.fromisoformat(fields["submitted_at"].replace("Z", "+00:00")),
                production_namespace=self.deployment["namespaces"]["production"],
                smoke_namespace=self.deployment["namespaces"]["smoke"], current_ipcch_execution_month=None)
            v2.admit_namespaces(validated, self.deployment["trusted_prefixes"], self.deployment["store_roots"])
        except v2.DeliveryRequestV2Error as exc:
            raise SubmissionError(f"invalid selection: {exc}") from None


# --------------------------------------------------------------------------- submission


def _state_path(cfg: Mapping[str, Any], run_id: str) -> Path:
    return Path(cfg["work_dir"]) / STATE_DIR / run_id / "state.json"


def _save(path: Path, body: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(canonical(body))
    tmp.replace(path)


def submit(cfg: Mapping[str, Any], selections_path: str | Path, *, execute: bool, cloud=None, run_id: str | None = None,
           now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> dict[str, Any]:
    """Preview or execute one v2 submission (see module docstring)."""
    plan = Plan(cfg, selections_path, run_id)
    state_path = _state_path(cfg, run_id) if run_id else None
    state = json.loads(state_path.read_text()) if state_path and state_path.exists() else None
    if run_id and state is None and execute:
        raise SubmissionError(f"no local state for run {run_id}; omit --run-id to start a new submission")
    if state is not None and state["selections_sha256"] != plan.digest:
        raise SubmissionError(f"run {run_id} is bound to different selections; a changed selection needs a new run ID")
    if execute and plan.image_uri is None:
        raise SubmissionError("project config v2.image_uri (the deployed v2 runtime image digest) is required to submit")
    image_uri = plan.image_uri or cfg["image_uri"]
    rid = run_id or plan.new_run_id()
    provisional_fields = instant_fields(now())                    # structural preflight only; never persisted
    # envelope / environment manifest are shared (v2.SHARED_REF_FIELDS); the country reference is a mode input, so its
    # configured object is admitted lexically in preflight too
    shared_provisional = {k: {"uri": plan.shared_specs.get(k, "gs://provisional/shared").partition("#")[0],
                              "generation": "1", "sha256": _PROVISIONAL_SHA}
                          for k in ("envelope", "environment_manifest", "country_reference")}
    provisional = build_request(run_id=rid, selections=plan.selections, fields=provisional_fields,
                                refs=plan.provisional_refs(rid), shared=shared_provisional, combination_id="provisional",
                                image_uri=image_uri, operator=cfg["operator"], namespace=plan.namespace,
                                expected_pointer_generation="0")
    plan.check(provisional, provisional_fields, plan.request_uri(rid))   # invalid -> nothing uploaded
    if not execute:
        return {"mode": "preview", "run_id": rid, "request": provisional,
                **({} if plan.image_uri else {"image_uri_pending": "v2.image_uri is not set; the preview shows the "
                                                                   "legacy top-level image"}),
                "note": "provisional references and time; --execute uploads/pins every file, then freezes the request "
                        "at one UTC submission instant (execution month, prepared_at) and uploads it last"}
    if state is None:
        state = {"run_id": rid, "selections": plan.selections, "selections_sha256": plan.digest, "phase": "created",
                 "refs": {}, "shared": {}}
        state_path = _state_path(cfg, rid)
        if state_path.exists():
            raise SubmissionError(f"run {rid} already has local state")
        _save(state_path, state)
    if state["phase"] == "submitted":
        return status(cfg, rid, cloud)
    if "request_body" not in state:
        _prepare_assets(plan, rid, state, state_path, cloud)
        _freeze(plan, rid, state, state_path, cloud, now)
    body_path = state_path.parent / "run_manifest.json"
    body_path.write_bytes(canonical(state["request_body"]))          # exactly the frozen bytes, also on resume
    state["request"] = cloud.put(plan.request_uri(rid), body_path)   # the only execution-triggering object, LAST
    if state["request"]["sha256"] != hashlib.sha256(canonical(state["request_body"])).hexdigest():
        raise SubmissionError(f"run {rid}: the uploaded request differs from the frozen bytes")
    state["phase"] = "submitted"
    _save(state_path, state)
    return status(cfg, rid, cloud)


def _prepare_assets(plan: Plan, rid: str, state: dict, state_path: Path, cloud) -> None:
    """Associated files: create-only uploads / exact pins, each saved as soon as it exists (no month is chosen)."""
    for name, src in plan.sources.items():
        if name not in state["refs"]:
            if src["kind"] == "local":
                ref = cloud.put(plan.upload_uri(rid, name), src["path"])
                if ref["sha256"] != src["sha256"]:
                    raise SubmissionError(f"{name}: uploaded bytes differ from {src['path']}")
            else:
                ref = cloud.pin_object(src["uri"] + (f"#{src['generation']}" if src["generation"] else ""))
            state["refs"][name] = ref
            _save(state_path, state)
    for key, spec in plan.shared_specs.items():
        if key not in state["shared"]:
            state["shared"][key] = cloud.pin_object(spec)
            _save(state_path, state)
    if "combination_id" not in state:
        env = cloud.read_bytes(state["shared"]["envelope"]["uri"], state["shared"]["envelope"]["generation"])
        if env is None or hashlib.sha256(env).hexdigest() != state["shared"]["envelope"]["sha256"]:
            raise SubmissionError("the pinned combination envelope is not readable at its generation")
        state["combination_id"] = json.loads(env)["package"]["combination_id"]
        _save(state_path, state)


def _freeze(plan: Plan, rid: str, state: dict, state_path: Path, cloud, now: Callable[[], datetime]) -> None:
    """The submission instant (D5) and the fresh current admission; the request bytes and instant persist together."""
    from cloud.ipcch import publication as pub

    fields = instant_fields(now())
    current = pub.read_current(cloud.store, plan.deployment["roots"][plan.mode], plan.namespace)
    current_month = pub.ipcch_execution_month(current["record"]) if plan.mode == "real" else None
    body = build_request(run_id=rid, selections=plan.selections, fields=fields, refs=state["refs"],
                         shared=state["shared"], combination_id=state["combination_id"], image_uri=plan.image_uri,
                         operator=plan.cfg["operator"], namespace=plan.namespace,
                         expected_pointer_generation=current["generation"])
    try:
        v2.admit(body, request_uri=plan.request_uri(rid), request_generation="1",
                 now_utc=datetime.fromisoformat(fields["submitted_at"].replace("Z", "+00:00")),
                 production_namespace=plan.deployment["namespaces"]["production"],
                 smoke_namespace=plan.deployment["namespaces"]["smoke"], current_ipcch_execution_month=current_month,
                 resolve=cloud.resolve, trusted_prefixes=plan.deployment["trusted_prefixes"],
                 batch_roots=plan.deployment["store_roots"], read=cloud.read_bytes)
    except (v2.DeliveryRequestV2Error, v2.ReferenceIdentityError) as exc:
        raise SubmissionError(f"request not admitted (nothing triggered): {exc}") from None
    state.update(fields, current_ipcch_execution_month=current_month, request_body=body)
    _save(state_path, state)


def status(cfg: Mapping[str, Any], run_id: str, cloud) -> dict[str, Any]:
    """A v2 run's durable state: local submission state, the Workflow claim, the entrypoint reservation and the final
    ``v2_run_status.json``."""
    from cloud.ipcch import entrypoint_v2

    state = json.loads(_state_path(cfg, run_id).read_text())
    deployment = entrypoint_v2.load_config(cfg["v2"]["deployment_config"])
    root = deployment["roots"][state["selections"]["mode"]].rstrip("/")

    def read(uri):
        meta = cloud.store.get_metadata(uri)
        return None if meta is None else json.loads(cloud.store.read_text(uri))
    claim = read(f"gs://{cfg['bucket']}/dispatch/{run_id}/claim.json") if state["phase"] == "submitted" else None
    reservation = read(f"{root}/runs/{run_id}/v2_reservation.json") if state["phase"] == "submitted" else None
    final = read(f"{root}/runs/{run_id}/v2_run_status.json") if state["phase"] == "submitted" else None
    phase = (final or {}).get("status") or ("running" if reservation else "claimed" if claim else state["phase"])
    return {"run_id": run_id, "mode": state["selections"]["mode"], "execution_month": state.get("execution_month"),
            "prepared_at": state.get("prepared_at"), "phase": state["phase"], "status": phase,
            "request": state.get("request"), "claim": claim, "reservation": reservation, "run_status": final}
