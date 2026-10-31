"""Task 10-30 CP3 (R9/AC9, D3, D5): the v2 operator submission on the existing CLI surface - explicit choices, automatic
pins, the single UTC submission instant captured at freeze (never at asset upload), the execution-triggering request
uploaded last, invalid selections triggering nothing, identity-preserving resume and v2 status."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import pipeline as p
from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import publication as pub
from cloud.orchestrator import delivery_request_v2 as v2
from cloud.orchestrator import submit_v2 as sv

IMAGE = "us-central1-docker.pkg.dev/feisty-flames-511718-d4/monthly-delivery/runtime@sha256:" + "a" * 64
DEPLOYMENT = {
    "roots": {"real": "gs://data-bucket", "smoke": "gs://smoke-bucket/v2"},
    "store_roots": {"real": "gs://data-bucket/ipcch-v2/real", "smoke": "gs://smoke-bucket/ipcch-v2/smoke"},
    "namespaces": {"production": "monthly-staging", "smoke": "monthly-smoke"},
    "trusted_prefixes": {"real": ["gs://data-bucket/inputs/v2/"], "smoke": ["gs://smoke-bucket/inputs/"]},
    "installed": {"real": {"envelope": "/opt/ipcch/envelope/env.json", "package_root": "/opt/ipcch/package",
                           "bundle_dir": "/opt/ipcch/handoff-bundle"},
                  "smoke": {"envelope": "/opt/ipcch/envelope/env.json", "package_root": "/opt/ipcch/package",
                            "bundle_dir": "/opt/ipcch/smoke-fixture/bundle", "fixture_root": "/opt/ipcch/smoke-fixture"}},
    "providers": {"real": "cloud.ipcch.entrypoint_v2:real_providers",
                  "smoke": "cloud.ipcch.smoke_providers:entrypoint_providers"},
    "earth_engine_project": "feisty-flames-511718-d4", "export_root": "gs://data-bucket/ipcch-v2/exports",
    "work_dir": "/tmp/ipcch-v2-work", "producer_asset_root": "projects/feisty-flames-511718-d4/assets/",
    "run_timeout_seconds": 14400}
ENVELOPE = json.dumps({"package": {"combination_id": "ipcch-validity-h2h8h14-final-20261030"}}).encode()
REQUEST_PREFIX = "gs://req-bucket/requests/"
IMAGE_V2 = "us-central1-docker.pkg.dev/feisty-flames-511718-d4/monthly-delivery/runtime@sha256:" + "b" * 64


class Clock:
    def __init__(self, *instants):
        self.instants, self.calls = list(instants), 0

    def __call__(self):
        self.calls += 1
        return self.instants.pop(0) if len(self.instants) > 1 else self.instants[0]


class FakeCloud:
    """The pipeline.Cloud surface submit_v2 uses, over a LocalObjectStore (create-only puts, exact generations)."""

    def __init__(self, store):
        self.store, self.order, self.lose_response, self.on_put = store, [], set(), None

    def put(self, uri, path):
        data = Path(path).read_bytes()
        meta = self.store.get_metadata(uri)
        if meta is not None:
            if self.store.read_bytes(uri) != data:
                raise ValueError(f"existing immutable object differs: {uri}")
        else:
            meta = self.store.write_bytes(uri, data, if_generation_match=0)
        self.order.append(uri)
        if self.on_put:
            self.on_put(uri)
        if uri in self.lose_response:
            self.lose_response.discard(uri)
            raise OSError("upload response lost")
        return {"uri": uri, "generation": meta.generation, "sha256": hashlib.sha256(data).hexdigest()}

    def pin_object(self, spec):
        uri, _, generation = spec.partition("#")
        meta = self.store.get_metadata(uri)
        if meta is None or (generation and generation != meta.generation):
            raise ValueError(f"{spec} not found")
        return {"uri": uri, "generation": meta.generation,
                "sha256": hashlib.sha256(self.store.read_bytes(uri)).hexdigest()}

    def read_bytes(self, uri, generation):
        meta = self.store.get_metadata(uri)
        return self.store.read_bytes(uri) if meta and meta.generation == str(generation) else None

    def resolve(self, uri, generation):
        data = self.read_bytes(uri, generation)
        return None if data is None else hashlib.sha256(data).hexdigest()


def acled_choice(path="acled.csv", start="2025-07-26", end="2026-10-16", regions=("Eastern Africa", "Western Africa")):
    return {"action": "refresh", "file": path, "start": start, "end": end, "regions": list(regions)}


def selections(tmp_path, mode="real", **over):
    choices = {name: {"action": "keep"} for name in sv.CHOICES}
    choices["acled"] = acled_choice()
    choices.update(over.pop("choices", {}))
    body = {"schema": sv.SELECTIONS_SCHEMA, "mode": mode, "operations": ["ipcch_generation", "ipcch_inference"],
            "publication": "current", "choices": choices, **over}
    path = tmp_path / "selections.json"
    path.write_text(json.dumps(body))
    (tmp_path / "acled.csv").write_text("week,region\n2026-10-10,Eastern Africa\n")
    return path


@pytest.fixture
def world(tmp_path):
    deployment = tmp_path / "deployment.json"
    deployment.write_text(json.dumps(DEPLOYMENT))
    cfg = {"bucket": "data-bucket", "request_bucket": "req-bucket", "image_uri": IMAGE, "operator": "weilun.shi",
           "namespace": "monthly-staging", "work_dir": str(tmp_path / "operator-state"),
           "v2": {"deployment_config": str(deployment), "image_uri": IMAGE_V2,
                  "inputs_prefix": {"real": "gs://data-bucket/inputs/v2", "smoke": "gs://smoke-bucket/inputs"},
                  "envelope": "gs://data-bucket/shared/ipcch-combination-envelope-v2-accepted.json",
                  "environment_manifest": "gs://data-bucket/shared/environment.json",
                  "country_reference": {"real": "gs://data-bucket/inputs/v2/reference/country_reference.csv",
                                        "smoke": "gs://smoke-bucket/inputs/reference/country_reference.csv"}}}
    store = LocalObjectStore(tmp_path / "gcs")
    store.write_bytes(cfg["v2"]["envelope"], ENVELOPE, if_generation_match=0)
    store.write_bytes(cfg["v2"]["environment_manifest"], b"lock", if_generation_match=0)
    for uri in cfg["v2"]["country_reference"].values():
        store.write_bytes(uri, b"ISO3\nAAA\n", if_generation_match=0)
    return cfg, FakeCloud(store), store


def set_current(store, month, root="gs://data-bucket", namespace="monthly-staging"):
    rec_uri = f"{root}/{namespace}/releases/r-{month}/release.json"
    meta = store.write_text(rec_uri, json.dumps({"schema": pub.RELEASE_SCHEMA, "systems": {
        "ipcch": {"contract": pub.IPCCH_CONTRACT, "execution_month": month}}}))
    pointer = pub.pointer_uri(root, namespace)
    store.write_text(pointer, json.dumps({"release_record": rec_uri, "release_record_generation": meta.generation}))
    return store.get_metadata(pointer).generation


def state_of(cfg, run_id):
    return json.loads((Path(cfg["work_dir"]) / "runs-v2" / run_id / "state.json").read_text())


T = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))                       # noqa: E731


def test_preview_makes_no_cloud_call_and_writes_no_state(world, tmp_path):
    cfg, _, store = world
    out = sv.submit(cfg, selections(tmp_path), execute=False, cloud=None, now=Clock(T("2026-10-31T12:00:00Z")))
    assert out["mode"] == "preview" and out["request"]["ipcch"]["acled"]["file"]["uri"].startswith(
        f"gs://data-bucket/inputs/v2/{out['run_id']}/acled/")
    assert not (Path(cfg["work_dir"]) / "runs-v2").exists()


@pytest.mark.parametrize("bad, match", [
    ({"choices": {"wfp": {"action": "refresh"}}}, "refresh needs its file"),
    ({"choices": {"acled": acled_choice(start="2025-07-27")}}, "Saturday start"),
    ({"choices": {"acled": acled_choice(regions=())}}, "regions"),
    ({"choices": {"nino34_anom": {"action": "refresh", "file": "acled.csv", "start": "2026-09", "end": "2026-08"}}},
     "reversed"),
    ({"choices": {"history_snapshot": {"action": "keep", "file": "acled.csv"}}}, "keep carries no other field"),
    ({"choices": {"acled": acled_choice(path="missing.csv")}}, "local file not found"),
    ({"mode": "test"}, "selections.mode"),
])
def test_invalid_selections_upload_nothing_and_trigger_nothing(world, tmp_path, bad, match):
    cfg, cloud, store = world
    with pytest.raises(sv.SubmissionError, match=match):
        sv.submit(cfg, selections(tmp_path, **bad), execute=True, cloud=cloud, now=Clock(T("2026-10-31T12:00:00Z")))
    assert cloud.order == [] and not store.list("gs://req-bucket/") and not store.list("gs://data-bucket/inputs/v2/x")


def test_every_one_of_the_eleven_choices_is_explicit(world, tmp_path):
    cfg, cloud, _ = world
    path = selections(tmp_path)
    body = json.loads(path.read_text())
    del body["choices"]["idp_local"]
    path.write_text(json.dumps(body))
    with pytest.raises(sv.SubmissionError, match=r"missing \['idp_local'\], unknown \[\]\); keep is never implied"):
        sv.submit(cfg, path, execute=True, cloud=cloud)
    assert cloud.order == []


def test_inference_preview_admits_the_configured_country_reference_and_refuses_one_outside(world, tmp_path):
    cfg, cloud, _ = world
    out = sv.submit(cfg, selections(tmp_path), execute=False, cloud=None, now=Clock(T("2026-10-31T12:00:00Z")))
    assert out["request"]["ipcch"]["country_reference"]["uri"] == cfg["v2"]["country_reference"]["real"]
    cfg["v2"]["country_reference"]["real"] = "gs://elsewhere/reference/country_reference.csv"
    with pytest.raises(sv.SubmissionError, match="ipcch.country_reference .* outside the trusted real namespace"):
        sv.submit(cfg, selections(tmp_path), execute=True, cloud=cloud, now=Clock(T("2026-10-31T12:00:00Z")))
    assert cloud.order == []


@pytest.mark.parametrize("extra", [{"file": "acled.csv"}, {"start": "2026-01"}, {"regions": ["x"]}])
def test_keep_with_any_extra_field_is_refused_before_any_cloud_call(world, tmp_path, extra):
    cfg, cloud, _ = world
    path = selections(tmp_path, choices={"wfp": {"action": "keep", **extra}})
    with pytest.raises(sv.SubmissionError, match="keep carries no other field"):
        sv.submit(cfg, path, execute=True, cloud=cloud, now=Clock(T("2026-10-31T12:00:00Z")))
    assert cloud.order == [] and not (Path(cfg["work_dir"]) / "runs-v2").exists()


def test_uploads_outside_the_trusted_namespace_are_refused_before_any_upload(world, tmp_path):
    cfg, cloud, _ = world
    cfg["v2"]["inputs_prefix"]["real"] = "gs://elsewhere/inputs"
    with pytest.raises(sv.SubmissionError, match="outside the trusted real namespace"):
        sv.submit(cfg, selections(tmp_path), execute=True, cloud=cloud, now=Clock(T("2026-10-31T12:00:00Z")))
    assert cloud.order == []


def test_month_is_frozen_at_submission_not_at_asset_upload(world, tmp_path):
    """Preflight and asset upload on 31 October, freeze just after midnight UTC: M is November; the pointer generation
    is read fresh at freeze (it moved during the uploads)."""
    cfg, cloud, store = world
    set_current(store, "2026-10")
    moved = {}
    cloud.on_put = lambda uri: moved.setdefault("g", set_current(store, "2026-10")) if "/acled/" in uri else None
    clock = Clock(T("2026-10-31T23:58:00Z"), T("2026-11-01T00:01:00Z"))
    out = sv.submit(cfg, selections(tmp_path), execute=True, cloud=cloud, now=clock)
    st = state_of(cfg, out["run_id"])
    body = st["request_body"]
    assert body["execution_month"] == "2026-11" and body["prepared_at"] == "2026-11-01T00:01:00Z" == st["submitted_at"]
    assert body["release"]["expected_pointer_generation"] == moved["g"] and clock.calls == 2
    assert cloud.order[-1] == f"{REQUEST_PREFIX}{out['run_id']}/run_manifest.json"            # triggering object last
    assert cloud.order[0].startswith(f"gs://data-bucket/inputs/v2/{out['run_id']}/acled/")
    uploaded = store.read_bytes(cloud.order[-1])
    assert uploaded == sv.canonical(body) and out["status"] == "submitted"
    validated = v2.validate_request_v2(json.loads(uploaded), request_uri=cloud.order[-1], request_generation="1",
                                       now_utc=T("2026-11-01T00:02:00Z"), production_namespace="monthly-staging",
                                       smoke_namespace="monthly-smoke", current_ipcch_execution_month="2026-10")
    assert validated["derived"]["feature_origin"] == "2026-09"
    assert [h["target_month"] for h in validated["derived"]["horizons"]] == ["2026-11", "2027-05", "2027-11"]


def test_the_v2_runtime_image_is_separate_from_the_legacy_destination_image(world, tmp_path):
    cfg, cloud, _ = world
    out = sv.submit(cfg, selections(tmp_path), execute=True, cloud=cloud, now=Clock(T("2026-10-31T12:00:00Z")))
    assert state_of(cfg, out["run_id"])["request_body"]["runtime"]["image_uri"] == IMAGE_V2 != cfg["image_uri"]
    del cfg["v2"]["image_uri"]
    preview = sv.submit(cfg, selections(tmp_path), execute=False, cloud=None)
    assert preview["request"]["runtime"]["image_uri"] == cfg["image_uri"] and "image_uri_pending" in preview
    calls = len(cloud.order)
    with pytest.raises(sv.SubmissionError, match="v2.image_uri"):
        sv.submit(cfg, selections(tmp_path), execute=True, cloud=cloud)
    assert len(cloud.order) == calls


def test_workstation_timezone_never_selects_the_month(world, tmp_path):
    cfg, cloud, _ = world
    local = datetime(2026, 11, 1, 1, 30, tzinfo=timezone(timedelta(hours=2)))       # 2026-10-31T23:30Z
    out = sv.submit(cfg, selections(tmp_path), execute=True, cloud=cloud, now=Clock(local))
    assert state_of(cfg, out["run_id"])["request_body"]["execution_month"] == "2026-10"


def test_lost_request_upload_response_resumes_with_the_frozen_bytes_and_instant(world, tmp_path):
    cfg, cloud, store = world
    cloud.lose_response = {"pending"}
    original = cloud.put

    def lossy(uri, path):
        if uri.endswith("/run_manifest.json") and "pending" in cloud.lose_response:
            cloud.lose_response = {uri}
        return original(uri, path)
    cloud.put = lossy
    with pytest.raises(OSError, match="response lost"):
        sv.submit(cfg, selections(tmp_path), execute=True, cloud=cloud, now=Clock(T("2026-10-31T12:00:00Z")))
    (run_dir,) = (Path(cfg["work_dir"]) / "runs-v2").iterdir()
    frozen = state_of(cfg, run_dir.name)
    assert frozen["phase"] == "created" and frozen["request_body"]["execution_month"] == "2026-10"
    later = Clock(T("2026-12-02T09:00:00Z"))                                     # delayed resume, next month
    out = sv.submit(cfg, selections(tmp_path), execute=True, cloud=cloud, run_id=run_dir.name, now=later)
    after = state_of(cfg, run_dir.name)
    assert out["status"] == "submitted" and after["request_body"] == frozen["request_body"]
    assert after["submitted_at"] == frozen["submitted_at"] == "2026-10-31T12:00:00Z"
    assert store.get_metadata(f"{REQUEST_PREFIX}{run_dir.name}/run_manifest.json").generation == "1"   # one object
    again = sv.submit(cfg, selections(tmp_path), execute=True, cloud=cloud, run_id=run_dir.name, now=later)
    assert again["phase"] == "submitted" and store.get_metadata(f"{REQUEST_PREFIX}{run_dir.name}/run_manifest.json").generation == "1"


def test_a_failure_before_freeze_freezes_later_at_its_own_instant(world, tmp_path):
    cfg, cloud, store = world
    store.delete(cfg["v2"]["environment_manifest"], if_generation_match="1")       # a shared pin fails first
    with pytest.raises(ValueError, match="not found"):
        sv.submit(cfg, selections(tmp_path), execute=True, cloud=cloud, now=Clock(T("2026-10-31T23:00:00Z")))
    (run_dir,) = (Path(cfg["work_dir"]) / "runs-v2").iterdir()
    assert "request_body" not in state_of(cfg, run_dir.name) and not store.list(REQUEST_PREFIX)
    store.write_bytes(cfg["v2"]["environment_manifest"], b"lock")
    out = sv.submit(cfg, selections(tmp_path), execute=True, cloud=cloud, run_id=run_dir.name,
                    now=Clock(T("2026-11-01T08:00:00Z")))
    assert state_of(cfg, run_dir.name)["request_body"]["execution_month"] == "2026-11" and out["status"] == "submitted"


def test_admission_failure_at_freeze_triggers_nothing(world, tmp_path):
    cfg, cloud, store = world
    set_current(store, "2026-11")                       # current already holds a later IPCCH month (R39)
    with pytest.raises(sv.SubmissionError, match="earlier than the current IPCCH release month"):
        sv.submit(cfg, selections(tmp_path), execute=True, cloud=cloud, now=Clock(T("2026-10-31T12:00:00Z")))
    assert not store.list(REQUEST_PREFIX)
    (run_dir,) = (Path(cfg["work_dir"]) / "runs-v2").iterdir()
    assert "request_body" not in state_of(cfg, run_dir.name)
    cloud2 = FakeCloud(store)
    pin = cloud2.pin_object

    def pin_then_replace(spec):                         # the environment manifest changes after it was pinned
        ref = pin(spec)
        if "country_reference" in spec:
            store.write_bytes(cfg["v2"]["environment_manifest"], b"lock-2")
        return ref
    cloud2.pin_object = pin_then_replace
    (tmp_path / "b").mkdir()
    with pytest.raises(sv.SubmissionError, match="request not admitted .*runtime.environment_manifest"):
        sv.submit(cfg, selections(tmp_path / "b"), execute=True, cloud=cloud2, now=Clock(T("2026-12-01T12:00:00Z")))
    assert not store.list(REQUEST_PREFIX)


def test_changed_selection_or_file_under_a_run_id_is_refused(world, tmp_path):
    cfg, cloud, _ = world
    out = sv.submit(cfg, selections(tmp_path), execute=True, cloud=cloud, now=Clock(T("2026-10-31T12:00:00Z")))
    (tmp_path / "acled.csv").write_text("week,region\n2026-10-10,Western Africa\n")
    path = tmp_path / "selections.json"
    with pytest.raises(sv.SubmissionError, match="bound to different selections"):
        sv.submit(cfg, path, execute=True, cloud=cloud, run_id=out["run_id"])
    with pytest.raises(sv.SubmissionError, match="no local state"):
        sv.submit(cfg, path, execute=True, cloud=cloud, run_id="ipcch-real-unknown")


def test_smoke_submission_stays_in_the_smoke_namespace(world, tmp_path):
    cfg, cloud, store = world
    out = sv.submit(cfg, selections(tmp_path, mode="smoke"), execute=True, cloud=cloud,
                    now=Clock(T("2026-10-31T12:00:00Z")))
    body = state_of(cfg, out["run_id"])["request_body"]
    assert body["mode"] == "smoke" and body["release"]["namespace"] == "monthly-smoke"
    assert body["ipcch"]["acled"]["file"]["uri"].startswith("gs://smoke-bucket/inputs/")
    assert body["ipcch"]["country_reference"]["uri"] == cfg["v2"]["country_reference"]["smoke"]


def test_status_reports_claim_reservation_and_final_status(world, tmp_path):
    cfg, cloud, store = world
    out = sv.submit(cfg, selections(tmp_path), execute=True, cloud=cloud, now=Clock(T("2026-10-31T12:00:00Z")))
    rid = out["run_id"]
    assert out["status"] == "submitted" and out["claim"] is None
    store.write_text(f"gs://data-bucket/dispatch/{rid}/claim.json", json.dumps({"generation": "1"}))
    store.write_text(f"gs://data-bucket/runs/{rid}/v2_reservation.json", json.dumps({"deadline_utc": "x"}))
    assert sv.status(cfg, rid, cloud)["status"] == "running"
    store.write_text(f"gs://data-bucket/runs/{rid}/v2_run_status.json", json.dumps({"status": "succeeded"}))
    assert sv.status(cfg, rid, cloud)["status"] == "succeeded"
    assert p.is_v2_run(cfg, rid) and not p.is_v2_run(cfg, "legacy-run")


def test_cli_submit_preview_runs_on_the_existing_surface(world, tmp_path, capsys):
    cfg, _, _ = world
    project = tmp_path / "project.json"
    project.write_text(json.dumps({**cfg, "project": "feisty-flames-511718-d4", "region": "us-central1",
                                   "service_account": "sa@x", "prepare_job": "monthly-prepare",
                                   "earth_engine_project": "feisty-flames-511718-d4"}))
    assert p.main(["submit", "--config", str(project), "--selections", str(selections(tmp_path))]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["mode"] == "preview" and printed["request"]["schema_version"] == v2.SCHEMA_VERSION
