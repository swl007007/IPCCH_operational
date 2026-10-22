"""Operator release path: selected-step intents, maintenance hold, candidate download/receipt and
receipt-bound promotion with resumable activation and restoration (fakes only, no cloud)."""

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

import pipeline as p
from cloud.common.object_store import GenerationConflict, LocalObjectStore
from cloud.orchestrator.delivery_manifest import validate_delivery_request
from tests.test_operator_cli import Fake, run_args, setup  # noqa: F401 (fixture)

SNAPSHOT = "gs://destination-bucket/prepared/snap/prepared_manifest.json"


class PinFake(Fake):
    def pin(self, spec):
        uri, _, generation = spec.partition("#")
        assert uri in self.objects and generation == "1"
        return dict(uri=uri, generation="1", sha256=hashlib.sha256(self.objects[uri]).hexdigest())


def _candidate_args(**override):
    return run_args(**{"remote_update": "off", "infer": "fewsnet", "prepared_manifest": SNAPSHOT + "#1",
                       "inherit": "ipcch=oct-confidence-20261009b", "inherit_manifest": "gs://src/manifest.json#1",
                       "inherit_archive": "gs://src/bundle.tar.gz#1", "publication": "candidate", **override})


def _world(setup):
    cfg, root, baseline, args, _ = setup
    cloud = PinFake()
    p.initialize(args, cfg, cloud)
    cloud.json(SNAPSHOT, dict(status="succeeded", origin_month="2026-10", prepare_id="snap"))
    cloud.json("gs://destination-bucket/prepared/snap/prepare_status.json", dict(status="succeeded"))
    cloud.objects["gs://src/manifest.json"] = json.dumps({"provenance": {"run_id": "oct-confidence-20261009b"}}).encode()
    cloud.objects["gs://src/bundle.tar.gz"] = b"archive"
    return cfg, cloud


def test_candidate_intent_reuses_the_snapshot_and_pins_the_inherited_source(setup):
    cfg, cloud = _world(setup)
    result = p.run(_candidate_args(), cfg, cloud)
    assert result["status"] == "submitted" and result["preparation_mode"] == "reused snap"
    assert result["preparation"] == {"status": "succeeded"}  # the snapshot's own status, not this run's
    assert not any("prepare_requests" in uri for uri in cloud.objects)  # no preparation started
    uri = "gs://requests-bucket/requests/operator-test/run_manifest.json"
    request = validate_delivery_request(cloud.latest(uri)[0], request_uri=uri, request_generation="1")
    assert request["prepared_snapshot"] == {"prepare_id": "snap", "origin_month": "2026-10",
                                            "manifest": cloud.latest(SNAPSHOT)[1]}
    execution = request["execution"]
    assert (execution["remote_update"], execution["inference_systems"], execution["publication"]) == (
        False, ["fewsnet"], "candidate")
    assert execution["inherit"]["ipcch"]["archive"]["sha256"] == hashlib.sha256(b"archive").hexdigest()
    with pytest.raises(ValueError, match="different inputs"):
        p.run(_candidate_args(publication="current"), cfg, cloud)


def test_an_inherited_source_must_be_the_named_delivery_run(setup):
    cfg, cloud = _world(setup)
    with pytest.raises(ValueError, match="inherited ipcch source is run oct-confidence-20261009b, not oct-other"):
        p.run(_candidate_args(inherit="ipcch=oct-other"), cfg, cloud)
    assert not any(uri.endswith("/run_manifest.json") for uri in cloud.objects)


@pytest.mark.parametrize("override,message", [
    ({"prepared_manifest": None}, "off requires --prepared-manifest"),
    ({"remote_update": "on"}, "on prepares a new snapshot"),
    ({"inherit_archive": None}, "needs --inherit-manifest and --inherit-archive"),
])
def test_inconsistent_selections_are_rejected_before_any_upload(setup, override, message):
    cfg, cloud = _world(setup)
    before = dict(cloud.objects)
    with pytest.raises(ValueError, match=message):
        p.run(_candidate_args(**override), cfg, cloud)
    assert cloud.objects == before


def test_operator_runs_respect_the_maintenance_hold(setup):
    cfg, cloud = _world(setup)
    hold = "gs://destination-bucket/" + p.HOLD
    cloud.json(hold, dict(operation_id="op-1", admitted_run_ids=["fews-candidate"]))
    before = dict(cloud.objects)
    with pytest.raises(ValueError, match="paused by maintenance op-1; operator-test is not admitted"):
        p.run(run_args(), cfg, cloud)
    assert cloud.objects == before  # nothing published, nothing prepared
    cloud.json(hold, dict(operation_id="op-1", admitted_run_ids=["operator-test"]))
    assert p.run(_candidate_args(), cfg, cloud)["status"] == "submitted"


def test_candidate_download_uses_the_candidate_record_never_a_release(setup, tmp_path):
    cfg, cloud = _world(setup)
    p.run(_candidate_args(), cfg, cloud)
    base = "gs://destination-bucket"
    raw = b"result"
    cloud.objects[base + "/deliveries/operator-test/results.csv"] = raw
    manifest = cloud.json(base + "/deliveries/operator-test/manifest.json", dict(files=[
        dict(path="results.csv", sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw))]))
    cloud.objects[base + "/deliveries/operator-test/webapp_model_bundle.tar.gz"] = b"archive"
    archive = dict(uri=base + "/deliveries/operator-test/webapp_model_bundle.tar.gz", generation="1",
                   sha256=hashlib.sha256(b"archive").hexdigest())
    cloud.json(base + "/runs/operator-test/run_status.json", dict(status="succeeded", release=None))
    with pytest.raises(ValueError, match="no published release"):
        p.download(NS(run_id="operator-test", output=tmp_path / "a", candidate=False), cfg, cloud)
    record = cloud.json(base + "/candidates/operator-test/candidate.json",
                        dict(run_id="operator-test", validation="passed", manifest=manifest, archive=archive))
    result = p.download(NS(run_id="operator-test", output=tmp_path / "c", candidate=True), cfg, cloud)
    assert result["kind"] == "candidate" and result["record"] == record
    assert p.read(tmp_path / "c.download.json")["archive"] == archive
    assert not any(uri.endswith("/current.json") for uri in cloud.objects)


# --- maintenance + promotion on a generation-checked store --------------------------------------


class StoreCloud:
    """Operator cloud fake on LocalObjectStore: create-only puts, generations, CAS, deletes."""

    def __init__(self, root):
        self.store = LocalObjectStore(root)

    def latest(self, uri):
        meta = self.store.get_metadata(uri)
        if meta is None:
            return None
        raw = self.store.read_text(uri).encode()
        return json.loads(raw), {"uri": uri, "generation": meta.generation, "sha256": hashlib.sha256(raw).hexdigest()}

    def put(self, uri, path):
        raw = Path(path).read_bytes()
        meta = self.store.get_metadata(uri)
        if meta is not None:
            if self.store.read_text(uri).encode() != raw:
                raise ValueError(f"existing immutable object differs: {uri}")
        else:
            meta = self.store.write_text(uri, raw.decode(), if_generation_match=0)
        return {"uri": uri, "generation": meta.generation, "sha256": hashlib.sha256(raw).hexdigest()}

    def json(self, uri, body):
        self.store.write_text(uri, json.dumps(body))
        return self.latest(uri)[1]

    def delete(self, uri, generation):
        if (self.store.get_metadata(uri) or NS(generation=None)).generation != str(generation):
            raise GenerationConflict(uri)
        self.store._generations.pop(uri)
        self.store._path_for_uri(uri).unlink()


class Shared:
    """Stateful fake gcloud: describe/list/get-iam-policy reads, and the deploy/update/IAM commands
    the operator runs change the live jobs, workflow source/env and grants."""

    def __init__(self, image):
        self.jobs = {name: {"image": image, "args": ["-m", "x"]} for name in ("oct-delivery", "monthly-prepare")}
        self.workflow = {"source": "main: old", "env": {"DELIVERY_IMAGE_URI": image}}
        self.grants = {("oct-delivery", "roles/run.developer", "serviceAccount:wf@p", None)}
        self.active, self.commands, self.fail_on = [], [], None

    def __call__(self, argv):
        if argv[1:4] == ["run", "jobs", "describe"]:
            container = {"image": self.jobs[argv[4]]["image"], "args": self.jobs[argv[4]]["args"]}
            return {"spec": {"template": {"spec": {"template": {"spec": {"containers": [container],
                                                                         "serviceAccountName": "rt@p"}}}}}}
        if argv[1:3] == ["workflows", "describe"]:
            return {"revisionId": "r-" + hashlib.sha256(self.workflow["source"].encode()).hexdigest()[:6],
                    "serviceAccount": "wf@p", "userEnvVars": dict(self.workflow["env"]),
                    "sourceContents": self.workflow["source"]}
        if argv[1:5] == ["run", "jobs", "executions", "list"]:
            return [{"metadata": {"name": e}, "status": {}} for e in self.active]
        if "get-iam-policy" in argv:
            resource = argv[4]
            return {"bindings": [{"role": role, "members": [member],
                                  **({"condition": {"expression": cond}} if cond else {})}
                                 for res, role, member, cond in sorted(self.grants, key=str) if res == resource]}
        return []

    def run(self, argv, check):
        self.commands.append(argv)
        if self.fail_on and self.fail_on(argv):
            self.fail_on = None
            raise OSError("interrupted command")
        if argv[1:3] == ["run", "jobs"] and argv[3] in ("deploy", "update"):
            image = next((a for a in argv[argv.index("--image") + 1:argv.index("--image") + 2]), None)
            args = next((a.split("=", 1)[1].split(",") for a in argv if a.startswith("--args=")), None)
            self.jobs[argv[4]] = {"image": image, "args": args}
        elif argv[1:3] == ["workflows", "deploy"]:
            self.workflow = {"source": Path(argv[argv.index("--source") + 1]).read_text(),
                             "env": dict(item.split("=", 1) for item in argv[-1].split(","))}
        elif "add-iam-policy-binding" in argv or "remove-iam-policy-binding" in argv:
            grant = p._grant_identity(argv)
            (self.grants.add if "add-iam-policy-binding" in argv else self.grants.discard)(grant)


OLD, NEW = "registry/runtime@sha256:" + "a" * 64, "registry/runtime@sha256:" + "b" * 64
POINTER = "gs://data/monthly-staging/current.json"


@pytest.fixture
def release(tmp_path, monkeypatch):
    cfg = dict(project="dest", region="us-central1", bucket="data", request_bucket="requests", image_uri=NEW,
               service_account="rt@p", workflow_service_account="wf@p", namespace="monthly-staging",
               prepare_job="monthly-prepare", earth_engine_project="ee", operator="op@x",
               work_dir=str(tmp_path / "state"))
    cloud, shared = StoreCloud(tmp_path / "gcs"), Shared(OLD)
    monkeypatch.setattr(p.subprocess, "run", shared.run)
    manifest_raw = b'{"files": []}'
    record = {"run_id": "fews-candidate", "validation": "passed",
              "request": {"uri": "gs://requests/x", "generation": "1", "sha256": "0" * 64},
              "manifest": {"uri": "gs://data/deliveries/fews-candidate/manifest.json", "generation": "1",
                           "sha256": hashlib.sha256(manifest_raw).hexdigest()},
              "archive": {"uri": "gs://data/deliveries/fews-candidate/webapp_model_bundle.tar.gz", "generation": "1",
                          "sha256": "1" * 64}}
    candidate = cloud.json("gs://data/candidates/fews-candidate/candidate.json", record)
    cloud.json("gs://data/runs/fews-candidate/run_status.json", {"status": "succeeded", "release": None})
    p.save(Path(cfg["work_dir"]) / "runs/fews-candidate/state.json",
           {"run_id": "fews-candidate", "phase": "submitted",
            "request_body": {"release": {"expected_pointer_generation": "0"}}})
    receipt = {"schema_version": p.RECEIPT_SCHEMA, "status": "passed", "run_id": "fews-candidate",
               "candidate": candidate, "manifest": record["manifest"], "archive": record["archive"], "image_uri": NEW}
    receipt_path = tmp_path / "receipt.json"
    p.save(receipt_path, receipt)
    normal = tmp_path / "normal/project.json"
    p.save(normal, {"project": "dest", "image_uri": OLD, "work_dir": "operator-state"})
    staged, active = tmp_path / "fallback/staged", tmp_path / "fallback/october_2026"
    for directory, raw in ((staged, manifest_raw), (active, b'{"old": true}')):
        directory.mkdir(parents=True)
        (directory / "manifest.json").write_bytes(raw)
    promote_args = NS(operation_id="op-1", run_id="fews-candidate", receipt=str(receipt_path),
                      normal_config=str(normal), fallback_staged=str(staged), fallback_active=str(active), execute=True)
    return NS(cfg=cfg, cloud=cloud, shared=shared, promote=promote_args, normal=normal, staged=staged,
              active=active, receipt=receipt_path, record=record, tmp=tmp_path)


def _maintain(r, command, **extra):
    args = NS(operation_id="op-1", maintenance_command=command, execute=True, admit="fews-candidate", reconciled=None)
    for key, value in extra.items():
        setattr(args, key, value)
    return p.maintenance(args, r.cfg, r.cloud, runner=r.shared)


def _promote(r, **extra):
    return p.promote(NS(**{**vars(r.promote), **extra}), r.cfg, r.cloud, runner=r.shared)


def _ready(r):
    _maintain(r, "hold")
    _maintain(r, "gate")
    _maintain(r, "apply")


def _operation(r):
    return p.read(Path(r.cfg["work_dir"]) / "operations/op-1/operation.json")


def test_the_hold_aware_gate_is_installed_and_verified_before_any_job_change(release):
    r = release
    r.shared.active = ["oct-delivery-x1"]
    held = _maintain(r, "hold")
    assert _operation(r)["owner"] == "op@x" and _operation(r)["predecessor"]["jobs"]["oct-delivery"]["image"] == OLD
    assert held["active_work"]["job_executions"][0]["execution"] == "oct-delivery-x1"
    assert r.cloud.latest("gs://data/" + p.HOLD)[0]["admitted_run_ids"] == ["fews-candidate"]
    with pytest.raises(ValueError, match="already holds admission"):
        _maintain(r, "hold", operation_id="op-2")
    with pytest.raises(ValueError, match="install and verify the gate"):
        _maintain(r, "apply", reconciled="x")
    assert r.shared.commands == []
    gated = _maintain(r, "gate")
    assert r.shared.workflow["source"] == (p.ROOT / "deploy/workflow.yaml").read_text()  # reads hold.json
    assert r.shared.workflow["env"]["DELIVERY_IMAGE_URI"] == OLD and r.shared.jobs["oct-delivery"]["image"] == OLD
    assert gated["active_after_gate"]["job_executions"]  # reconciled again after the gate
    with pytest.raises(ValueError, match="finished or reconciled"):
        _maintain(r, "apply")
    r.shared.active = []
    _maintain(r, "apply")
    assert {job["image"] for job in r.shared.jobs.values()} == {NEW}
    assert not any(c[:3] == ["gcloud", "eventarc", "triggers"] for c in r.shared.commands)
    with pytest.raises(ValueError, match="release only after activation or restoration"):
        _maintain(r, "release")


def test_promotion_is_receipt_bound_and_reconciled(release):
    r = release
    _ready(r)
    bad = copy.deepcopy(p.read(r.receipt))
    bad["status"] = "failed"  # e.g. a failed relocated replay
    p.save(r.tmp / "bad.json", bad)
    with pytest.raises(ValueError, match="not a passed verification"):
        _promote(r, receipt=str(r.tmp / "bad.json"))
    assert r.cloud.latest(POINTER) is None
    result = _promote(r)
    assert result["status"] == "activated" and all(result["reconciled"].values())
    pointer = r.cloud.latest(POINTER)
    assert pointer[0]["run_id"] == "fews-candidate"
    assert r.cloud.latest(pointer[0]["release_record"])[0]["verification_receipt"]["sha256"] == p.sha(r.receipt)
    assert p.read(r.normal) == {"project": "dest", "image_uri": NEW, "work_dir": r.cfg["work_dir"]}
    assert (r.active / "manifest.json").read_bytes() == b'{"files": []}'
    (r.active / "manifest.json").write_text("tampered")
    with pytest.raises(ValueError, match="differ from the recorded activated state"):
        _maintain(r, "release")
    (r.active / "manifest.json").write_bytes(b'{"files": []}')
    assert _maintain(r, "release")["status"] == "released_activated"
    assert r.cloud.latest("gs://data/" + p.HOLD) is None


def _interrupt(monkeypatch, target, attribute, when):
    original = getattr(target, attribute)
    state = {"done": False}

    def wrapper(*args, **kwargs):
        if not state["done"] and when(*args, **kwargs):
            state["done"] = True
            raise OSError(f"interrupted at {attribute}")
        return original(*args, **kwargs)

    monkeypatch.setattr(target, attribute, wrapper)


@pytest.mark.parametrize("boundary", ["record_before_pointer", "after_pointer", "after_config",
                                      "after_first_rename", "after_second_rename"])
def test_an_interrupted_promotion_resumes_from_the_actual_state(release, monkeypatch, boundary):
    r = release
    _ready(r)
    real_rename = Path.rename
    if boundary == "record_before_pointer":  # immutable release record landed; the pointer CAS did not
        _interrupt(monkeypatch, r.cloud.store, "write_text", lambda uri, *a, **k: uri == POINTER)
    elif boundary == "after_pointer":
        _interrupt(monkeypatch, p, "_write_bytes", lambda path, data: Path(path) == r.normal)
    elif boundary == "after_config":
        _interrupt(monkeypatch, Path, "rename", lambda self, target: self == r.active)
    else:
        renames = {"n": 0}

        def rename(self, target):
            result = real_rename(self, target)
            renames["n"] += 1
            if renames["n"] == (1 if boundary == "after_first_rename" else 2):
                raise OSError("interrupted after rename")
            return result

        monkeypatch.setattr(Path, "rename", rename)
    with pytest.raises(OSError):
        _promote(r)
    monkeypatch.setattr(Path, "rename", real_rename)
    monkeypatch.undo()
    monkeypatch.setattr(p.subprocess, "run", r.shared.run)
    result = _promote(r)  # resume: no second release record, no second pointer move
    assert result["status"] == "activated", result
    assert r.cloud.latest(POINTER)[1]["generation"] == "1"
    assert p.read(r.normal)["image_uri"] == NEW and (r.active / "manifest.json").read_bytes() == b'{"files": []}'


@pytest.mark.parametrize("boundary", ["after_first_rename", "after_second_rename"])
def test_restore_from_an_interrupted_fallback_switch(release, monkeypatch, boundary):
    r = release
    _ready(r)
    real_rename = Path.rename
    renames = {"n": 0}

    def rename(self, target):
        result = real_rename(self, target)
        renames["n"] += 1
        if renames["n"] == (1 if boundary == "after_first_rename" else 2):
            raise OSError("interrupted after rename")
        return result

    monkeypatch.setattr(Path, "rename", rename)
    with pytest.raises(OSError):
        _promote(r)
    monkeypatch.setattr(Path, "rename", real_rename)
    assert _maintain(r, "restore")["status"] == "restored"
    assert r.cloud.latest(POINTER) is None  # absent predecessor pointer restored
    assert p.read(r.normal)["image_uri"] == OLD
    assert (r.active / "manifest.json").read_bytes() == b'{"old": true}' and (r.staged / "manifest.json").exists()
    assert {job["image"] for job in r.shared.jobs.values()} == {OLD}
    assert r.shared.workflow["source"] == "main: old"
    assert r.shared.grants == {("oct-delivery", "roles/run.developer", "serviceAccount:wf@p", None)}
    assert _maintain(r, "release")["status"] == "released_restored"


def test_concurrent_config_change_or_pointer_drift_stops_before_local_changes(release):
    r = release
    _ready(r)
    _promote(r)
    p.save(r.normal, {"project": "dest", "image_uri": "someone-else", "work_dir": "x"})
    with pytest.raises(ValueError, match="changed outside this operation; nothing restored"):
        _maintain(r, "restore")
    assert (r.active / "manifest.json").read_bytes() == b'{"files": []}'  # fallback untouched
    p.save(r.normal, json.loads(_operation(r)["promotion"]["intended_config_text"]))
    r.cloud.json(POINTER, {"run_id": "newer-release"})  # a concurrent newer release
    with pytest.raises(ValueError, match="changed outside this operation; nothing restored"):
        _maintain(r, "restore")
    assert p.read(r.normal)["image_uri"] == NEW and (r.active / "manifest.json").read_bytes() == b'{"files": []}'
    assert r.cloud.latest(POINTER)[0] == {"run_id": "newer-release"}


def test_a_competing_pointer_is_never_overwritten(release):
    r = release
    _ready(r)
    r.cloud.json(POINTER, {"run_id": "someone-else"})
    with pytest.raises(ValueError, match="not the expected predecessor generation 0"):
        _promote(r)
    assert r.cloud.latest(POINTER)[0] == {"run_id": "someone-else"}
    assert p.read(r.normal)["image_uri"] == OLD and (r.staged / "manifest.json").exists()


def test_a_present_predecessor_pointer_is_restored_by_cas(release):
    r = release
    r.cloud.json(POINTER, {"run_id": "previous-release", "release_record": "gs://data/x"})
    state = p.read(Path(r.cfg["work_dir"]) / "runs/fews-candidate/state.json")
    state["request_body"]["release"]["expected_pointer_generation"] = "1"
    p.save(Path(r.cfg["work_dir"]) / "runs/fews-candidate/state.json", state)
    _ready(r)
    assert _promote(r)["status"] == "activated"
    assert r.cloud.latest(POINTER)[1]["generation"] == "2"
    _maintain(r, "restore")
    assert r.cloud.latest(POINTER)[0] == {"run_id": "previous-release", "release_record": "gs://data/x"}
    assert _maintain(r, "release")["status"] == "released_restored"


def test_prepare_only_status_ends_at_the_resolved_snapshot(setup):
    cfg, cloud = _world(setup)
    p.run(run_args(infer="none"), cfg, cloud)
    assert p.status(cfg, "operator-test", cloud)["status"] == "submitted"
    snapshot = {"prepare_id": "operator-test", "origin_month": "2026-10",
                "manifest": {"uri": "gs://destination-bucket/prepared/operator-test/prepared_manifest.json",
                             "generation": "4", "sha256": "f" * 64}}
    cloud.json("gs://destination-bucket/dispatch/operator-test/resolution.json",
               dict(status="resolved", prepared_snapshot=snapshot, inference_systems=[]))
    current = p.status(cfg, "operator-test", cloud)
    assert current["status"] == "prepared" and current["prepared_snapshot"] == snapshot


@pytest.mark.parametrize("runtime,all_equal,passed", [("bundle", True, True), ("worktree", True, False),
                                                      ("bundle", False, False)])
def test_candidate_receipt_requires_a_bundled_runtime_replay(setup, tmp_path, monkeypatch, runtime, all_equal, passed):
    import io
    import tarfile

    from cloud.orchestrator import delivery_bundle

    cfg, cloud = _world(setup)
    p.run(_candidate_args(), cfg, cloud)
    out = tmp_path / "candidate"
    out.mkdir()
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as tar:
        info = tarfile.TarInfo("runtime/cloud/__init__.py")
        tar.addfile(info, io.BytesIO(b""))
    (out / "webapp_model_bundle.tar.gz").write_bytes(archive.getvalue())
    (out / "manifest.json").write_text(json.dumps({"provenance": {"image_uri": cfg["image_uri"]}}))
    (out / "model_inventory.json").write_text("{}")
    base = "gs://destination-bucket"
    request_uri = "gs://requests-bucket/requests/operator-test/run_manifest.json"
    record = dict(run_id="operator-test", validation="passed", request=cloud.latest(request_uri)[1],
                  manifest=dict(uri=f"{base}/m", generation="1", sha256=p.sha(out / "manifest.json")),
                  archive=dict(uri=f"{base}/a", generation="1", sha256=p.sha(out / "webapp_model_bundle.tar.gz")))
    ref = cloud.json(f"{base}/candidates/operator-test/candidate.json", record)
    p.save(tmp_path / "candidate.download.json", {"kind": "candidate", "record": ref})
    monkeypatch.setattr(delivery_bundle, "verify_inventory", lambda root: None)
    monkeypatch.setattr(delivery_bundle, "validate_delivery", lambda root: {"status": "passed", "failures": []})
    inherit = cloud.latest(request_uri)[0]["execution"]["inherit"]
    monkeypatch.setattr(delivery_bundle, "inherited_systems", lambda root: {
        system: {"manifest": source["manifest"], "archive": source["archive"], "source_run_id": source["source_delivery_id"],
                 "source_delivery_id": source["source_delivery_id"]} for system, source in inherit.items()})
    seen = {}

    def replay(argv, **kwargs):
        seen.update(argv=argv, cwd=kwargs["cwd"], env=kwargs["env"])
        root = (Path(argv[argv.index("--root") + 1]) / "runtime") if runtime == "bundle" else p.ROOT
        stderr = "REPLAY_RUNTIME " + json.dumps([str(root / "cloud/x.py"), str(root / "f/__init__.py"), [str(root / "m")]])
        body = {"all_equal": all_equal, "summary": {str(h): {"fewsnet": 5718, "ipcch": "inherited"} for h in p.HORIZONS}}
        return NS(returncode=0 if all_equal else 1, stdout=json.dumps(body), stderr=stderr)

    monkeypatch.setattr(p.subprocess, "run", replay)
    receipt = p.verify_candidate(NS(run_id="operator-test", download=str(out), python=None, check=None,
                                    execute=False), cfg, cloud)
    assert "-P" in seen["argv"] and Path(seen["cwd"]).name == "candidate-replay-cwd" and not any(Path(seen["cwd"]).iterdir())
    assert seen["env"]["PYTHONPATH"].endswith("candidate-relocated/runtime")
    assert (receipt["status"] == "passed") is passed, receipt["checks"]
    assert receipt["checks"]["replay_used_bundled_runtime"] is (runtime == "bundle")


def test_a_foreign_pointer_after_restore_inspection_is_never_deleted(release, monkeypatch):
    r = release
    _ready(r)
    _promote(r)
    inspect = p._inspect
    landed = {"done": False}

    def inspect_then_race(cloud, promotion):
        result = inspect(cloud, promotion)
        if not landed["done"]:  # a newer release lands right after restore inspected our pointer
            landed["done"] = True
            r.cloud.store.write_text(POINTER, json.dumps({"run_id": "newer-release"}), if_generation_match=1)
        return result

    monkeypatch.setattr(p, "_inspect", inspect_then_race)
    with pytest.raises(GenerationConflict):
        _maintain(r, "restore")
    assert r.cloud.latest(POINTER)[0] == {"run_id": "newer-release"}
    assert p.read(r.normal)["image_uri"] == NEW and (r.active / "manifest.json").read_bytes() == b'{"files": []}'


def test_a_config_edit_during_cloud_publication_is_never_overwritten(release, monkeypatch):
    r = release
    _ready(r)
    publish = p._publish_resumable

    def publish_then_edit(*args):
        result = publish(*args)
        p.save(r.normal, {"project": "dest", "image_uri": "edited-meanwhile", "work_dir": "x"})
        return result

    monkeypatch.setattr(p, "_publish_resumable", publish_then_edit)
    with pytest.raises(ValueError, match="normal operator config changed outside this operation"):
        _promote(r)
    assert p.read(r.normal)["image_uri"] == "edited-meanwhile"
    assert (r.active / "manifest.json").read_bytes() == b'{"old": true}' and _operation(r)["phase"] == "activation_inconsistent"


def test_a_config_edit_during_restore_is_never_overwritten(release, monkeypatch):
    r = release
    _ready(r)
    _promote(r)
    delete = r.cloud.delete

    def delete_then_edit(uri, generation):
        delete(uri, generation)
        p.save(r.normal, {"project": "dest", "image_uri": "edited-meanwhile", "work_dir": "x"})

    monkeypatch.setattr(r.cloud, "delete", delete_then_edit)
    with pytest.raises(ValueError, match="normal operator config changed outside this operation"):
        _maintain(r, "restore")
    assert p.read(r.normal)["image_uri"] == "edited-meanwhile"
