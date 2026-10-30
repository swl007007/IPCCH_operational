"""The cloud Workflow (deploy/workflow.yaml) executed step by step by a small fake Workflows interpreter
against fake Cloud Storage / Cloud Run connectors whose jobs call the real dispatch code: maintenance
hold and run claim before any job, admission before preparation, one snapshot gate for prepare-only
and inference intents, bounded waits, and duplicate or conflicting events."""

import hashlib
import json
import re
import urllib.parse
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

from cloud.batch import remote_sources as rs  # noqa: E402
from cloud.common.object_store import GenerationConflict, LocalObjectStore  # noqa: E402
from cloud.ipcch import locks  # noqa: E402
from cloud.ipcch import publication as pub  # noqa: E402
from cloud.orchestrator import delivery_job as dj  # noqa: E402
from cloud.orchestrator import delivery_manifest as dm  # noqa: E402
from cloud.orchestrator import delivery_run  # noqa: E402
from cloud.orchestrator import prepare  # noqa: E402
from tests.cloud import test_delivery_manifest as tm  # noqa: E402

WORKFLOW = yaml.safe_load((Path(__file__).resolve().parents[2] / "deploy/workflow.yaml").read_text())
ENV = {"GOOGLE_CLOUD_PROJECT_ID": "dest", "DELIVERY_LOCATION": "us-central1", "DELIVERY_JOB": "oct-delivery",
       "PREPARE_JOB": "monthly-prepare", "DELIVERY_OUTPUT_ROOT": "gs://data", "DELIVERY_RELEASE_NAMESPACE": "dual-system",
       "DELIVERY_IMAGE_URI": "registry/image@sha256:" + "c" * 64, "EARTH_ENGINE_PROJECT": "ee",
       "BATCH_PARENT": "projects/dest/locations/us-central1", "BATCH_SERVICE_ACCOUNT": "batch@dest",
       "PREPARE_POLL_SECONDS": "60", "PREPARE_MAX_POLLS": "3"}
REQUEST_BUCKET, NAME = "ipcch-requests", "requests/oct2026-r1/run_manifest.json"
RUN = "oct2026-r1"
PREPARE_URI = "gs://data/prepare_requests/prep-a/prepare_request.json"


# --- a fake Workflows interpreter (the subset this definition uses) ---------------------------------


class WorkflowRaised(Exception):
    def __init__(self, value):
        super().__init__(value)
        self.value = value


class HttpError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.value = {"code": code, "message": f"HTTP {code}"}


class _Jump(Exception):
    def __init__(self, target):
        self.target = target


class _Return(Exception):
    def __init__(self, value):
        self.value = value


class Attr(dict):
    def __getattr__(self, key):
        return self[key]


def _wrap(value):
    if isinstance(value, dict):
        return Attr({key: _wrap(item) for key, item in value.items()})
    if isinstance(value, list):
        return [_wrap(item) for item in value]
    return value


class _NS:
    def __init__(self, **functions):
        self.__dict__.update(functions)


def _type(value):
    return {dict: "map", Attr: "map", str: "string", bytes: "bytes", list: "list", int: "integer",
            bool: "boolean", type(None): "null"}[type(value)]


class Interpreter:
    def __init__(self, definition, connectors, env):
        self.definition, self.connectors = definition, connectors
        self.helpers = {
            "sys": _NS(get_env=env.__getitem__), "json": _NS(decode=json.loads),
            "text": _NS(split=lambda s, sep: s.split(sep), match_regex=lambda s, p: re.search(p, s) is not None,
                        url_encode=lambda s: urllib.parse.quote(s, safe="")),
            "map": _NS(get=lambda m, k: m.get(k)), "default": lambda v, d: d if v is None else v,
            "string": str, "int": int, "len": len, "get_type": _type}

    def run(self, name, args):
        routine = self.definition[name]
        scope = {param: _wrap(args.get(param)) for param in routine.get("params", [])}
        try:
            self._block(routine["steps"], scope)
        except _Return as result:
            return result.value
        return None

    def _eval(self, value, scope):
        if isinstance(value, str):
            match = re.fullmatch(r"\$\{(.*)\}", value, re.S)
            if not match:
                return value
            parts = re.split(r'("(?:[^"\\]|\\.)*")', match.group(1))
            code = "".join(part if i % 2 else re.sub(r"\b(null|true|false)\b",
                                                      lambda m: {"null": "None", "true": "True",
                                                                 "false": "False"}[m.group(1)], part)
                           for i, part in enumerate(parts))
            return eval(code, {"__builtins__": {}}, {**self.helpers, **scope})  # noqa: S307 (test-only)
        if isinstance(value, dict):
            return {key: self._eval(item, scope) for key, item in value.items()}
        if isinstance(value, list):
            return [self._eval(item, scope) for item in value]
        return value

    def _block(self, steps, scope):
        names = [next(iter(step)) for step in steps]
        index = 0
        while index < len(steps):
            try:
                target = self._step(steps[index][names[index]], scope)
            except _Jump as jump:
                if jump.target not in names:
                    raise
                target = jump.target
            if target is None:
                index += 1
            elif target in names:
                index = names.index(target)
            else:
                raise _Jump(target)

    def _act(self, body, scope):
        if "return" in body:
            raise _Return(self._eval(body["return"], scope))
        if "raise" in body:
            raise WorkflowRaised(self._eval(body["raise"], scope))
        return body.get("next")

    def _step(self, body, scope):
        if "assign" in body:
            for item in body["assign"]:
                (key, value), = item.items()
                scope[key] = _wrap(self._eval(value, scope))
            return body.get("next")
        if "switch" in body:
            for case in body["switch"]:
                if self._eval(case["condition"], scope):
                    return self._act(case, scope)
            return body.get("next")
        if "try" in body:
            try:
                self._step(body["try"], scope)
            except (HttpError, WorkflowRaised) as error:
                scope[body["except"]["as"]] = _wrap(error.value)
                self._block(body["except"]["steps"], scope)
            return body.get("next")
        if "call" in body:
            args = self._eval(body.get("args", {}), scope)
            call = body["call"]
            result = self.run(call, args) if call in self.definition else self.connectors[call](**args)
            if "result" in body:
                scope[body["result"]] = _wrap(result)
            return body.get("next")
        return self._act(body, scope)


# --- fake cloud: storage on LocalObjectStore, jobs calling the real dispatch code --------------------


class StoreReader:
    def __init__(self, store):
        self.store = store

    def read_bytes(self, uri, generation):
        meta = self.store.get_metadata(uri)
        return self.store.read_text(uri).encode() if meta and meta.generation == str(generation) else None


class Cloud:
    def __init__(self, store, preparation):
        self.store, self.preparation = store, preparation
        self.jobs, self.sleeps, self.executed = [], 0, []
        self.prepare_flags, self.locks_during_preparation, self.released = [], [], []
        self.fail_submission = {}                         # job verb -> exception raised by the submission itself
        self.connectors = {"googleapis.storage.v1.objects.get": self.get,
                           "googleapis.storage.v1.objects.insert": self.insert,
                           "googleapis.run.v2.projects.locations.jobs.run": self.run_job,
                           "sys.sleep": self.sleep}

    def get(self, bucket, object, alt=None, generation=None):
        uri = f"gs://{bucket}/{urllib.parse.unquote(object)}"
        meta = self.store.get_metadata(uri)
        if meta is None or (generation is not None and str(generation) != meta.generation):
            raise HttpError(404)
        return self.store.read_text(uri)  # text/plain objects come back as text

    def insert(self, bucket, name, body, uploadType, ifGenerationMatch=None):
        try:
            meta = self.store.write_text(f"gs://{bucket}/{name}", json.dumps(body), if_generation_match=ifGenerationMatch)
        except GenerationConflict:
            raise HttpError(412) from None
        return {"name": name, "generation": meta.generation}

    def sleep(self, seconds):
        self.sleeps += 1

    def run_job(self, name, body, connector_params):
        assert connector_params == {"skip_polling": True}
        args = body["overrides"]["containerOverrides"][0]["args"]
        flags = dict(zip(args[3::2], args[4::2]))
        if args[2] in self.fail_submission:
            raise self.fail_submission.pop(args[2])
        self.jobs.append((name.rsplit("/", 1)[-1], args[2]))
        if args[1] == "cloud.orchestrator.prepare":
            self.prepare_flags.append(flags)
            self.locks_during_preparation.append(sorted(l.system for l in locks.owned(self.store, "gs://data", RUN)))
            self.preparation(self.store, flags)
            return {"name": "operations/prepare"}
        if args[2] == "release":
            self.released.append(dj.release_run(self.store, request_uri=flags["--request-uri"],
                                                output_root=flags["--output-root"]))
            return {"name": "operations/release"}
        data = StoreReader(self.store).read_bytes(flags["--request-uri"], flags["--request-generation"])
        ref = {"uri": flags["--request-uri"], "generation": flags["--request-generation"],
               "sha256": hashlib.sha256(data).hexdigest()}
        if args[2] in ("admit", "resolve"):
            try:
                record, resolved = dj.dispatch_step("admission" if args[2] == "admit" else "resolution",
                                                    intent_ref=ref, intent_bytes=data, output_root=flags["--output-root"],
                                                    store=self.store, reader=StoreReader(self.store))
            except dj.AcceptanceError:
                return {"name": "operations/failed"}  # the job fails; its rejected record is the outcome
            if args[2] == "resolve" and record["inference_systems"]:
                resolved_ref, resolved_bytes = resolved
                request = dm.validate_delivery_request(json.loads(resolved_bytes), request_uri=resolved_ref["uri"],
                                                       request_generation=resolved_ref["generation"],
                                                       new_contract_inherit=("ipcch",))   # as delivery_job.execute
                dj.verify_resolution(request, data)
                self.executed.append(resolved_ref)
        else:
            self.executed.append(ref)
        return {"name": "operations/delivery"}


def _write(store, uri, payload):
    data = json.dumps(payload, sort_keys=True)
    meta = store.write_text(uri, data)
    return {"uri": uri, "generation": meta.generation, "sha256": hashlib.sha256(data.encode()).hexdigest()}


def _prepare_request(store, *, origin="2026-10"):
    intent_assets = tm._request()["assets"]
    systems = {system: {"geometry": intent_assets[system]["geometry"], "roster": intent_assets[system]["roster"],
                        "history": {family: tm._ref(f"history/{system}/{family}.csv")
                                    for family in rs.SYSTEM_FAMILIES[system]}}
               for system in dm.SYSTEMS}
    return _write(store, PREPARE_URI, {
        "schema_version": prepare.PREPARE_SCHEMA_VERSION, "prepare_id": "prep-a", "origin_month": origin,
        "cutoff_utc": "2026-10-21T00:00:00Z", "extraction_contract_version": rs.EXTRACTION_CONTRACT_VERSION,
        "systems": systems, "operator": "operator@ifpri.example"})


def _intent(prepare_ref=None, *, inference=("fewsnet",), remote=True):
    request = tm._request()
    execution = {"remote_update": remote, "inference_systems": list(inference), "prepare_request": prepare_ref,
                 "inherit": ({"ipcch": {"source_delivery_id": "src", "origin_month": "2026-10",
                                        "manifest": tm._ref("deliveries/src/manifest.json"),
                                        "archive": tm._ref("deliveries/src/bundle.tar.gz")}}
                             if list(inference) == ["fewsnet"] else {}),
                 "publication": "candidate"}
    if remote:
        request["prepared_snapshot"] = None
    request["execution"] = execution
    return request


def _snapshot(prepare_ref, **override):
    assets = tm._request()["assets"]
    manifest = {"status": "succeeded", "prepare_id": "prep-a", "origin_month": "2026-10", "request": prepare_ref,
                "extraction_contract_version": rs.EXTRACTION_CONTRACT_VERSION,
                "systems": {system: {kind: {"sha256": assets[system][kind]["sha256"]} for kind in ("roster", "geometry")}
                            for system in dm.SYSTEMS},
                "families": {family: {"outputs": {system: tm._ref(f"prepared/{family}/{system}.csv")
                                                  for system in dm.SYSTEMS if family in rs.SYSTEM_FAMILIES[system]}}
                             for family in prepare.FAMILIES}}
    manifest.update(override)
    return manifest


def _preparation(status="succeeded", manifest=None, *, write_manifest=True):
    def run(store, flags):
        assert flags["--request-uri"] == PREPARE_URI
        if status is None:
            return  # Batch still pending: no durable status yet
        ref = {"uri": PREPARE_URI, "generation": flags["--request-generation"],
               "sha256": hashlib.sha256(store.read_text(PREPARE_URI).encode()).hexdigest()}
        if write_manifest:
            store.write_text("gs://data/prepared/prep-a/prepared_manifest.json",
                             json.dumps(manifest(ref) if manifest else _snapshot(ref)))
        store.write_text("gs://data/prepared/prep-a/prepare_status.json", json.dumps({"status": status}))
    return run


def _world(tmp_path, intent=None, *, preparation=None, origin="2026-10"):
    store = LocalObjectStore(tmp_path / "gcs")
    prepare_ref = _prepare_request(store, origin=origin)
    body = intent(prepare_ref) if callable(intent) else (intent or _intent(prepare_ref))
    generation = store.write_text(f"gs://{REQUEST_BUCKET}/{NAME}", json.dumps(body)).generation
    cloud = Cloud(store, preparation or _preparation())
    return store, cloud, generation


def _event(generation, name=NAME):
    return {"data": {"bucket": REQUEST_BUCKET, "name": name, "generation": int(generation)}}


def _run(cloud, generation, name=NAME):
    return Interpreter(WORKFLOW, cloud.connectors, ENV).run("main", {"event": _event(generation, name)})


def _record(store, stage):
    meta = store.get_metadata(f"gs://data/dispatch/oct2026-r1/{stage}.json")
    return json.loads(store.read_text(f"gs://data/dispatch/oct2026-r1/{stage}.json")) if meta else None


# --- behaviour -------------------------------------------------------------------------------------


def test_own_writes_are_ignored_and_never_claimed(tmp_path):
    store, cloud, _ = _world(tmp_path)
    assert _run(cloud, 3, "resolved_requests/oct2026-r1/run_manifest.json").startswith("ignored")
    assert cloud.jobs == [] and _record(store, "claim") is None
    assert delivery_run.request_from_event({"bucket": "b", "name": "resolved_requests/r1/run_manifest.json",
                                            "generation": 3}) is None


def test_inference_intent_is_admitted_prepared_resolved_and_run_once(tmp_path):
    store, cloud, generation = _world(tmp_path)
    result = _run(cloud, generation)
    assert cloud.jobs == [("oct-delivery", "admit"), ("monthly-prepare", "plan"), ("oct-delivery", "resolve")]
    assert result["resolved_request"]["uri"] == "gs://ipcch-requests/resolved_requests/oct2026-r1/run_manifest.json"
    assert result["delivery_status"] == "gs://data/runs/oct2026-r1/run_status.json"
    assert cloud.executed == [result["resolved_request"]]
    resolved = json.loads(store.read_text(result["resolved_request"]["uri"]))
    assert resolved["execution"]["intent"] == _record(store, "admission")["intent"]
    assert resolved["execution"]["intent"]["generation"] == generation


def test_prepare_only_returns_the_immutable_snapshot_after_the_same_gate(tmp_path):
    store, cloud, generation = _world(tmp_path, lambda ref: _intent(ref, inference=()))
    result = _run(cloud, generation)
    manifest_uri = "gs://data/prepared/prep-a/prepared_manifest.json"
    assert result["delivery"] == "not selected" and cloud.executed == []
    assert result["prepared_snapshot"]["manifest"] == {
        "uri": manifest_uri, "generation": store.get_metadata(manifest_uri).generation,
        "sha256": hashlib.sha256(store.read_text(manifest_uri).encode()).hexdigest()}
    assert _record(store, "resolution")["status"] == "resolved"


@pytest.mark.parametrize("manifest,write_manifest,reason", [
    (lambda ref: _snapshot(ref, origin_month="2026-09"), True, "not a succeeded snapshot"),
    (lambda ref: _snapshot({**ref, "generation": "99"}), True, "not the succeeded preparation of this intent"),
    (None, False, "has no prepared manifest"),
    (lambda ref: _snapshot(ref, extraction_contract_version="other"), True, "extraction contract"),
    (lambda ref: {**_snapshot(ref), "systems": {"fewsnet": {"roster": {"sha256": "0" * 64}}}}, True, "roster"),
])
@pytest.mark.parametrize("inference", [(), ("fewsnet",)])
def test_both_branches_stop_on_a_wrong_or_missing_snapshot(tmp_path, manifest, write_manifest, reason, inference):
    store, cloud, generation = _world(tmp_path, lambda ref: _intent(ref, inference=inference),
                                      preparation=_preparation(manifest=manifest, write_manifest=write_manifest))
    with pytest.raises(WorkflowRaised, match="has no compatible succeeded snapshot"):
        _run(cloud, generation)
    assert reason in _record(store, "resolution")["reason"]
    assert cloud.executed == []
    assert store.get_metadata("gs://ipcch-requests/resolved_requests/oct2026-r1/run_manifest.json") is None


def test_an_inadmissible_intent_never_starts_preparation(tmp_path):
    store, cloud, generation = _world(tmp_path, origin="2026-09")
    with pytest.raises(WorkflowRaised, match="was not admitted: prepare request origin 2026-09"):
        _run(cloud, generation)
    assert cloud.jobs == [("oct-delivery", "admit")]


def test_failed_or_unfinished_preparation_stops_before_resolution(tmp_path):
    store, cloud, generation = _world(tmp_path, preparation=_preparation(status="failed"))
    with pytest.raises(WorkflowRaised, match="preparation prep-a failed; no inference"):
        _run(cloud, generation)
    store, cloud, generation = _world(tmp_path / "pending", preparation=_preparation(status=None))
    with pytest.raises(WorkflowRaised, match="prepare_status.json not written after 3 polls"):
        _run(cloud, generation)
    assert cloud.sleeps == 3 and ("oct-delivery", "resolve") not in cloud.jobs


@pytest.mark.parametrize("intent", [lambda ref: tm._request(), lambda ref: _intent(ref)])
def test_duplicate_events_dispatch_nothing_and_a_new_generation_conflicts(tmp_path, intent):
    store, cloud, generation = _world(tmp_path, intent)
    _run(cloud, generation)
    launched = list(cloud.jobs)
    assert _run(cloud, generation) == {"run_id": "oct2026-r1", "duplicate_event": generation, "dispatched": False}
    assert cloud.jobs == launched  # the replay launched nothing
    newer = store.write_text(f"gs://{REQUEST_BUCKET}/{NAME}", store.read_text(f"gs://{REQUEST_BUCKET}/{NAME}"))
    with pytest.raises(WorkflowRaised, match="already claimed by .*#1; a changed intent needs a new run ID"):
        _run(cloud, newer.generation)
    assert cloud.jobs == launched


def test_legacy_and_remote_off_requests_run_the_delivery_job_directly(tmp_path):
    store, cloud, generation = _world(tmp_path, lambda ref: _intent(None, remote=False))
    _run(cloud, generation)
    assert cloud.jobs == [("oct-delivery", "run")]


def test_a_maintenance_hold_admits_only_its_bound_runs(tmp_path):
    store, cloud, generation = _world(tmp_path, lambda ref: tm._request())
    hold = {"operation_id": "fews-retrain-20261022", "admitted_run_ids": ["fews-candidate-20261022"]}
    store.write_text("gs://data/maintenance/hold.json", json.dumps(hold))
    with pytest.raises(WorkflowRaised, match="paused by maintenance fews-retrain-20261022; run oct2026-r1"):
        _run(cloud, generation)
    assert cloud.jobs == [] and _record(store, "claim") is None  # not claimed: resubmittable after the hold
    hold["admitted_run_ids"].append("oct2026-r1")
    store.write_text("gs://data/maintenance/hold.json", json.dumps(hold))
    _run(cloud, generation)
    assert cloud.jobs == [("oct-delivery", "run")]


# --- resolution identity ---------------------------------------------------------------------------


def _resolved(tmp_path):
    store, cloud, generation = _world(tmp_path)
    reader = StoreReader(store)
    prepare_ref = json.loads(store.read_text(f"gs://{REQUEST_BUCKET}/{NAME}"))["execution"]["prepare_request"]
    _preparation()(store, {"--request-uri": PREPARE_URI, "--request-generation": prepare_ref["generation"]})
    data = store.read_text(f"gs://{REQUEST_BUCKET}/{NAME}").encode()
    ref = {"uri": f"gs://{REQUEST_BUCKET}/{NAME}", "generation": generation, "sha256": hashlib.sha256(data).hexdigest()}
    return store, reader, ref, data


def test_resolution_pins_the_exact_initial_intent_and_equal_content_does_not_collapse(tmp_path):
    store, reader, ref, data = _resolved(tmp_path)
    resolved_ref, resolved_bytes, _ = dj.resolve_intent(intent_ref=ref, intent_bytes=data, output_root="gs://data",
                                                        store=store, reader=reader)
    again = dj.resolve_intent(intent_ref=ref, intent_bytes=data, output_root="gs://data", store=store, reader=reader)
    assert again[0] == resolved_ref  # identical replay of the same initial generation
    request = dm.validate_delivery_request(json.loads(resolved_bytes), request_uri=resolved_ref["uri"],
                                           request_generation=resolved_ref["generation"])
    assert request["execution"]["intent"] == ref
    assert ("execution.intent", ref) in dm.iter_object_refs(request)
    dj.verify_resolution(request, data)
    newer = store.write_text(ref["uri"], data.decode()).generation  # same bytes, new initial generation
    with pytest.raises(dj.AcceptanceError, match="already holds a different resolution"):
        dj.resolve_intent(intent_ref={**ref, "generation": newer}, intent_bytes=data, output_root="gs://data",
                          store=store, reader=reader)


def test_a_resolved_request_must_equal_its_initial_intent(tmp_path):
    store, reader, ref, data = _resolved(tmp_path)
    resolved_ref, resolved_bytes, _ = dj.resolve_intent(intent_ref=ref, intent_bytes=data, output_root="gs://data",
                                                        store=store, reader=reader)
    body = json.loads(resolved_bytes)
    body["operator"] = "someone-else@ifpri.example"
    request = dm.validate_delivery_request(body, request_uri=resolved_ref["uri"], request_generation="9")
    with pytest.raises(dj.AcceptanceError, match="not its pinned initial intent"):
        dj.verify_resolution(request, data)


def test_resolved_paths_require_the_initial_intent_identity_and_initial_paths_forbid_it(tmp_path):
    store, reader, ref, data = _resolved(tmp_path)
    resolved_ref, resolved_bytes, _ = dj.resolve_intent(intent_ref=ref, intent_bytes=data, output_root="gs://data",
                                                        store=store, reader=reader)
    body = json.loads(resolved_bytes)
    without = {**body, "execution": {k: v for k, v in body["execution"].items() if k != "intent"}}
    with pytest.raises(dm.DeliveryManifestError, match="missing \\['intent'\\]"):
        dm.validate_delivery_request(without, request_uri=resolved_ref["uri"], request_generation="9")
    other = {**body, "execution": {**body["execution"], "intent": {**ref, "uri": ref["uri"].replace("r1", "r2")}}}
    with pytest.raises(dm.DeliveryManifestError, match="must pin this run's initial request"):
        dm.validate_delivery_request(other, request_uri=resolved_ref["uri"], request_generation="9")
    with pytest.raises(dm.DeliveryManifestError, match="unexpected \\['intent'\\]"):
        dm.validate_delivery_request(body, request_uri=ref["uri"], request_generation="9")
    with pytest.raises(dm.DeliveryManifestError, match="resolved request"):
        dm.validate_delivery_request(tm._request(), request_uri=resolved_ref["uri"], request_generation="3")


def test_job_argv_parses_with_every_configured_flag():
    with pytest.raises(SystemExit) as missing:
        dj.main(["admit", "--request-uri", "gs://b/requests/r1/run_manifest.json"])
    assert missing.value.code == 2
    with pytest.raises(SystemExit) as missing:
        dj.main(["resolve", "--request-uri", "gs://b/requests/r1/run_manifest.json"])
    assert missing.value.code == 2


# --- R37 / R50 through the real workflow and admission seams (Supervisor findings 2 on 6d8ea08) ----------------------


def _owned(store):
    return sorted(lock.system for lock in locks.owned(store, "gs://data", RUN))


def test_remote_run_holds_both_locks_from_admission_and_resolution_hands_them_to_delivery(tmp_path):
    """Before activation the legacy preparation collects both systems: both locks are taken at admission, held
    through preparation and resolution (adopted, never acquired twice) and left for the delivery to adopt/release."""
    store, cloud, generation = _world(tmp_path)
    _run(cloud, generation)
    assert cloud.locks_during_preparation == [["fewsnet", "ipcch"]]
    assert cloud.prepare_flags[0]["--systems"] == "fewsnet,ipcch"                     # unchanged default scope
    assert _record(store, "admission")["locks"].keys() == {"fewsnet", "ipcch"}
    assert "prepare_systems" not in _record(store, "admission")
    assert _owned(store) == ["fewsnet", "ipcch"]                                       # delivery adopts and releases
    held = locks.acquire(store, "gs://data", ["fewsnet", "ipcch"], RUN, adopt_own=True)
    assert [l.generation for l in held] == [l.generation for l in locks.owned(store, "gs://data", RUN)]


@pytest.mark.parametrize("case", ["failed_preparation", "prepare_only", "resolution_rejected"])
def test_remote_run_locks_are_released_on_every_failure_and_after_prepare_only(tmp_path, case):
    if case == "failed_preparation":
        store, cloud, generation = _world(tmp_path, preparation=_preparation(status="failed"))
        with pytest.raises(WorkflowRaised, match="preparation prep-a failed"):
            _run(cloud, generation)
        assert ("oct-delivery", "release") in cloud.jobs and cloud.released[0]["released"]
    elif case == "prepare_only":
        store, cloud, generation = _world(tmp_path, lambda ref: _intent(ref, inference=()))
        _run(cloud, generation)
    else:
        store, cloud, generation = _world(tmp_path, preparation=_preparation(
            manifest=lambda ref: _snapshot(ref, origin_month="2026-09")))
        with pytest.raises(WorkflowRaised, match="has no compatible succeeded snapshot"):
            _run(cloud, generation)
    assert cloud.locks_during_preparation and _owned(store) == []


def test_a_busy_system_rejects_admission_before_preparation(tmp_path):
    store, cloud, generation = _world(tmp_path)
    other = locks.acquire(store, "gs://data", ["fewsnet"], "v2-run")
    with pytest.raises(WorkflowRaised, match="was not admitted: .*fewsnet run in progress"):
        _run(cloud, generation)
    assert cloud.jobs == [("oct-delivery", "admit")] and _owned(store) == []
    assert locks.release(store, other) == []


def _activate(store):
    """An activated current release (namespace of the intents) holding a new-contract IPCCH member."""
    manifest = tm._ref("deliveries/ipcch-new/manifest.json")
    record = {"schema": pub.RELEASE_SCHEMA, "run_id": "ipcch-new-ipcch", "mode": "real",
              "activation": {"contract": pub.IPCCH_CONTRACT, "activated_by_run": "ipcch-new-ipcch"},
              "systems": {"ipcch": {"contract": pub.IPCCH_CONTRACT, "execution_month": "2026-10",
                                    "feature_origin": "2026-08", "mode": "real", "delivery": {"manifest": manifest}}}}
    meta = store.write_text("gs://data/dual-system/releases/ipcch-new-ipcch/release.json", json.dumps(record))
    store.write_text("gs://data/dual-system/current.json", json.dumps({
        "run_id": "ipcch-new-ipcch", "release_record": "gs://data/dual-system/releases/ipcch-new-ipcch/release.json",
        "release_record_generation": meta.generation}))
    return manifest


def test_after_activation_a_legacy_fews_only_remote_run_prepares_fews_only(tmp_path):
    """Finding 2 (Supervisor ruling): the legacy FEWS NET-only remote request stays usable after activation - its
    preparation is scoped to FEWS NET (no IPCCH collection), only the FEWS lock is taken, and resolution requires the
    snapshot of exactly the admitted scope."""
    def intent(ref):
        body = _intent(ref)
        body["execution"]["inherit"] = {"ipcch": {"source_delivery_id": "ipcch-new-ipcch", "origin_month": "2026-08",
                                                  "manifest": member, "archive": member}}
        return body

    def fews_snapshot(ref):
        snap = _snapshot(ref, selected_systems=["fewsnet"])
        snap["families"] = {f: {"outputs": {"fewsnet": v["outputs"]["fewsnet"]}} for f, v in snap["families"].items()
                            if "fewsnet" in v["outputs"]}
        return snap
    store = LocalObjectStore(tmp_path / "gcs")
    member = _activate(store)
    prepare_ref = _prepare_request(store)
    generation = store.write_text(f"gs://{REQUEST_BUCKET}/{NAME}", json.dumps(intent(prepare_ref))).generation
    cloud = Cloud(store, _preparation(manifest=fews_snapshot))
    result = _run(cloud, generation)
    admission = _record(store, "admission")
    assert admission["prepare_systems"] == ["fewsnet"] and set(admission["locks"]) == {"fewsnet"}
    assert cloud.prepare_flags[0]["--systems"] == "fewsnet" and cloud.locks_during_preparation == [["fewsnet"]]
    assert result["resolved_request"] and _owned(store) == ["fewsnet"]
    # a both-system snapshot is not the admitted scope
    store2 = LocalObjectStore(tmp_path / "gcs2")
    member = _activate(store2)
    prepare_ref = _prepare_request(store2)
    generation = store2.write_text(f"gs://{REQUEST_BUCKET}/{NAME}", json.dumps(intent(prepare_ref))).generation
    cloud2 = Cloud(store2, _preparation())
    with pytest.raises(WorkflowRaised, match="has no compatible succeeded snapshot"):
        _run(cloud2, generation)
    assert "admitted preparation scope" in _record(store2, "resolution")["reason"] and _owned(store2) == []


@pytest.mark.parametrize("inference", [("ipcch",), ("fewsnet", "ipcch")])
def test_after_activation_legacy_ipcch_remote_intents_are_rejected_before_any_collection(tmp_path, inference):
    store = LocalObjectStore(tmp_path / "gcs")
    _activate(store)
    prepare_ref = _prepare_request(store)
    body = _intent(prepare_ref, inference=inference)
    if inference == ("ipcch",):
        body["execution"]["inherit"] = {"fewsnet": {"source_delivery_id": "src", "origin_month": "2026-10",
                                                    "manifest": tm._ref("deliveries/src/manifest.json"),
                                                    "archive": tm._ref("deliveries/src/bundle.tar.gz")}}
    generation = store.write_text(f"gs://{REQUEST_BUCKET}/{NAME}", json.dumps(body)).generation
    cloud = Cloud(store, _preparation())
    with pytest.raises(WorkflowRaised, match="was not admitted: .*v2 manifest"):
        _run(cloud, generation)
    assert cloud.jobs == [("oct-delivery", "admit")] and cloud.prepare_flags == [] and _owned(store) == []


# --- residuals C/D on 78a2aeb: definitive submission rejection and every terminal path release the owned locks -------


class FailingStore:
    """Store wrapper failing writes (``fail_write``) or reads (``fail_read``) of one URI suffix."""

    def __init__(self, inner, fail_write=None, fail_read=None):
        self.inner, self.fail_write, self.fail_read = inner, fail_write, fail_read

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def write_text(self, uri, content, **kw):
        if self.fail_write and uri.endswith(self.fail_write):
            raise OSError(f"write of {uri} failed")
        return self.inner.write_text(uri, content, **kw)

    def read_text(self, uri):
        if self.fail_read and uri.endswith(self.fail_read):
            raise RuntimeError(f"read of {uri} failed")
        return self.inner.read_text(uri)


@pytest.mark.parametrize("verb", ["plan", "resolve"])
@pytest.mark.parametrize("code,released", [(403, True), (404, True), (503, False)])
def test_a_definitively_rejected_job_submission_releases_the_admission_locks(tmp_path, verb, code, released):
    """C: a definitive rejection (4xx) of the prepare or resolve job submission means nothing runs - the owner
    releases; an ambiguous outcome (5xx / timeout) keeps the locks (the job may be running)."""
    store, cloud, generation = _world(tmp_path)
    cloud.fail_submission[verb] = HttpError(code)
    with pytest.raises(WorkflowRaised):
        _run(cloud, generation)
    assert _owned(store) == ([] if released else ["fewsnet", "ipcch"])
    assert (("oct-delivery", "release") in cloud.jobs) == released


def test_resolution_read_failure_releases_the_admission_locks(tmp_path):
    """D: a non-acceptance error during resolution (here: the prepared manifest read) releases and is re-raised."""
    store, cloud, generation = _world(tmp_path)
    real = cloud.store
    cloud.store = FailingStore(real, fail_read="prepared/prep-a/prepared_manifest.json")
    try:
        with pytest.raises(RuntimeError, match="prepared_manifest.json failed"):
            _run(cloud, generation)
    finally:
        cloud.store = real
    assert _owned(store) == []


@pytest.mark.parametrize("record", ["admission.json", "resolution.json"])
def test_dispatch_record_write_failure_releases_what_the_step_owns(tmp_path, record):
    store, cloud, generation = _world(tmp_path)
    real = cloud.store
    cloud.store = FailingStore(real, fail_write=f"dispatch/{RUN}/{record}")
    try:
        with pytest.raises(OSError, match="failed"):
            _run(cloud, generation)
    finally:
        cloud.store = real
    assert _owned(store) == []


def test_admission_replay_failure_never_releases_locks_adopted_from_the_first_admission(tmp_path):
    """The cleanup at admission releases only what that call freshly acquired: a replayed admission whose record
    write fails keeps the locks the first admission holds."""
    store, cloud, generation = _world(tmp_path)
    data = store.read_text(f"gs://{REQUEST_BUCKET}/{NAME}").encode()
    ref = {"uri": f"gs://{REQUEST_BUCKET}/{NAME}", "generation": generation, "sha256": hashlib.sha256(data).hexdigest()}
    dj.dispatch_step("admission", intent_ref=ref, intent_bytes=data, output_root="gs://data", store=store,
                     reader=StoreReader(store))
    held = _owned(store)
    with pytest.raises(OSError):
        dj.dispatch_step("admission", intent_ref=ref, intent_bytes=data, output_root="gs://data",
                         store=FailingStore(store, fail_write="admission.json"), reader=StoreReader(store))
    assert held == ["fewsnet", "ipcch"] and _owned(store) == held


def test_delivery_rejected_by_a_changed_current_release_releases_the_admission_locks(tmp_path):
    """D: after resolution the current release changes (now a v2 record without the inherited member): the delivery's
    binding rejects it before scoring and the run's admission locks are released."""
    store, cloud, generation = _world(tmp_path)
    result = _run(cloud, generation)
    assert _owned(store) == ["fewsnet", "ipcch"]
    record = {"schema": pub.RELEASE_SCHEMA, "run_id": "other", "mode": "real", "activation": None, "systems": {}}
    meta = store.write_text("gs://data/dual-system/releases/other/release.json", json.dumps(record))
    store.write_text("gs://data/dual-system/current.json", json.dumps({
        "run_id": "other", "release_record": "gs://data/dual-system/releases/other/release.json",
        "release_record_generation": meta.generation}))
    resolved = result["resolved_request"]
    data = store.read_text(resolved["uri"]).encode()
    with pytest.raises(dj.AcceptanceError, match="must name exactly"):
        dj.execute(request_ref=resolved, request_bytes=data, output_root="gs://data", release_namespace="dual-system",
                   image_uri="unused", store=store, downloader=None, work=tmp_path / "w",
                   score=lambda *a: pytest.fail("scored"), package=None, upload=None)
    assert _owned(store) == []
