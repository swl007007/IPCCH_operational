"""Task 10-29 CP4: the executable v2 route (cloud.ipcch.entrypoint_v2.run) on local stores - config validation,
installed binding vs the request's pinned envelope, admission, locks, publication and run status (R5, R17, R36, R48)."""

import json
from datetime import timedelta

import pytest

from cloud.ipcch import entrypoint_v2 as ep
from cloud.ipcch import publication as pub
from tests.cloud import ipcch_smoke_fixture as fx
from tests.cloud.test_ipcch_run_v2 import raw, smoke_world
from tests.cloud.test_ipcch_generation import package  # noqa: F401 (fixture)

ROOTS = {"smoke": "gs://ops-delivery-smoke/v2", "real": "gs://ops-delivery/v2"}
STORES = {"smoke": "gs://ipcch-store/ipcch-v2/smoke", "real": "gs://ipcch-store/ipcch-v2/real"}


class Reader:
    """Exact-generation reads over the pinned request/input objects and the local store (batch manifests)."""

    def __init__(self, refs, store):
        self.refs, self.store = refs, store

    def read_bytes(self, uri, generation):
        if (uri, generation) in self.refs.objects:
            return self.refs.objects[(uri, generation)]
        meta = self.store.get_metadata(uri)
        return self.store.read_text(uri).encode() if meta and meta.generation == generation else None


def config(tmp_path, package, **over):
    cfg = {"roots": ROOTS, "store_roots": STORES, "namespaces": {"production": "prod", "smoke": "smoke"},
           "trusted_prefixes": {"smoke": ["gs://ops-smoke/inputs/"], "real": ["gs://ops-real/inputs/"]},
           "installed": {"smoke": {"envelope": str(tmp_path / "env.json"), "package_root": str(package),
                                   "bundle_dir": str(tmp_path / "fixture-root" / "bundle"),
                                   "fixture_root": str(tmp_path / "fixture-root")},
                         "real": {"envelope": "/nonexistent/env.json", "package_root": "/nonexistent",
                                  "bundle_dir": "/nonexistent"}},
           "providers": {"smoke": "tests.cloud.ipcch_smoke_fixture:entrypoint_providers",
                         "real": "cloud.ipcch.entrypoint_v2:real_providers"},
           "earth_engine_project": "unused-in-smoke", "export_root": "gs://ops-exports/v2", "work_dir": str(tmp_path / "work")}
    cfg.update(over)
    path = tmp_path / "deployment.json"
    path.write_text(json.dumps(cfg))
    return ep.load_config(str(path))


def put_request(refs, req, run_id="smoke-run-1"):
    uri = f"gs://ops-smoke/requests/{run_id}/run_manifest.json"
    refs.objects[(uri, "1")] = json.dumps(req).encode()
    return uri


def test_smoke_request_runs_end_to_end_through_the_route(tmp_path, package):
    store, refs, _, _ = smoke_world(tmp_path, package)
    cfg = config(tmp_path, package)
    req = raw(fx.smoke_request(refs, tmp_path / "env.json", inference=True))
    req["publication"] = "current"
    uri = put_request(refs, req)
    out = ep.run(cfg, request_uri=uri, request_generation="1", store=store, reader=Reader(refs, store))
    assert out["status"] == "succeeded" and out["systems"]["ipcch"]["result"]["publication"]["status"] == "published"
    assert pub.read_current(store, ROOTS["smoke"], "smoke")["record"]["systems"]["ipcch"]["mode"] == "smoke"
    assert pub.read_current(store, ROOTS["real"], "prod")["generation"] == "0"
    assert json.loads(store.read_text(out["status_uri"]))["run_id"] == "smoke-run-1"


def test_request_envelope_other_than_the_installed_one_executes_nothing_ipcch(tmp_path, package):
    from cloud.ipcch import binding as bd
    from tests.cloud.ipcch_binding_fixtures import smoke_envelope
    store, refs, _, _ = smoke_world(tmp_path, package)
    cfg = config(tmp_path, package)
    other = tmp_path / "other.json"
    smoke_envelope(other, package, version=3)
    req = raw(fx.smoke_request(refs, other, inference=True))                     # pins a different envelope
    uri = put_request(refs, req)
    out = ep.run(cfg, request_uri=uri, request_generation="1", store=store, reader=Reader(refs, store))
    ip = out["systems"]["ipcch"]
    assert ip["status"] == "failed" and "referenced" in ip["reason"]              # installed sha != pinned sha
    assert not list((tmp_path / "store").rglob("manifest.json"))


def test_config_refuses_real_providers_for_smoke_and_nested_roots(tmp_path, package):
    with pytest.raises(ep.EntrypointError, match="R48"):
        config(tmp_path, package, providers={"smoke": "cloud.ipcch.entrypoint_v2:real_providers",
                                             "real": "cloud.ipcch.entrypoint_v2:real_providers"})
    with pytest.raises(ValueError, match="not nested"):
        config(tmp_path, package, roots={"smoke": "gs://ops-delivery/v2/smoke", "real": "gs://ops-delivery/v2"})


class Spy:
    """Store wrapper recording every URI touched; real-mode roots must never be touched by a smoke run (R48)."""

    def __init__(self, inner):
        self.inner, self.touched = inner, []

    def __getattr__(self, name):
        attr = getattr(self.inner, name)
        if not callable(attr):
            return attr

        def call(*a, **k):
            self.touched += [x for x in list(a) + list(k.values()) if isinstance(x, str) and x.startswith("gs://")]
            return attr(*a, **k)
        return call


def test_smoke_route_never_touches_real_state(tmp_path, package):
    """No production current read (R39 is real-only) and no real delivery/store path, through the executable route."""
    store, refs, _, _ = smoke_world(tmp_path, package)
    spy = Spy(store)
    cfg = config(tmp_path, package)
    req = raw(fx.smoke_request(refs, tmp_path / "env.json", inference=True))
    req["publication"] = "current"
    out = ep.run(cfg, request_uri=put_request(refs, req), request_generation="1", store=spy, reader=Reader(refs, spy))
    assert out["status"] == "succeeded"
    real = [u for u in spy.touched if u.startswith((ROOTS["real"], STORES["real"]))]
    assert spy.touched and not real


def failing_factory(**kw):
    raise AssertionError("provider factory must not be built for inference-only")


def test_saved_update_then_later_failure_keeps_the_structured_report(tmp_path, package):
    """R29/R41: an ACLED refresh saved before a later climate block is reported in the returned AND durable status."""
    store, refs, _, _ = smoke_world(tmp_path, package)
    cfg = config(tmp_path, package, providers={"smoke": "tests.cloud.test_ipcch_entrypoint_v2:unavailable_climate",
                                               "real": "cloud.ipcch.entrypoint_v2:real_providers"})
    uri = put_request(refs, raw(fx.smoke_request(refs, tmp_path / "env.json")))
    out = ep.run(cfg, request_uri=uri, request_generation="1", store=store, reader=Reader(refs, store))
    durable = json.loads(store.read_text(out["status_uri"]))
    for status in (out, durable):
        ip = status["systems"]["ipcch"]
        assert ip["status"] == "failed" and ip["failed_operation"] == "generation" and ip["step"] == "climate"
        assert ip["report"]["steps"]["acled"]["action"] == "refresh"          # the saved update stays reported


def unavailable_climate(**kw):
    from cloud.ipcch import climate as cl
    from cloud.ipcch import climate_run
    providers = fx.entrypoint_providers(**kw)
    blocked = climate_run.ClimateProviders(lambda base: (lambda s, m: cl.SourceOutcome(s, "unavailable", detail="lag")),
                                           fx.climate_providers().seasonal)
    return {**providers, "climate_providers": lambda windows, origin: blocked}


def test_real_inference_only_never_builds_acquisition_providers(tmp_path, package, monkeypatch):
    """An EE outage (ee.Initialize / the provider factory failing) must not block real inference from an existing
    batch: providers are constructed only when generation is selected."""
    import hashlib
    import sys
    import types

    from cloud.ipcch import batch as bt
    from cloud.ipcch import binding as bd
    from cloud.ipcch import initial
    from cloud.ipcch.stores import StoreRoot
    from cloud.common.object_store import LocalObjectStore
    from tests.cloud.ipcch_binding_fixtures import finalize_entries
    from tests.cloud.test_ipcch_assembly import ORDER, inputs
    from tests.cloud.test_ipcch_batch import frame
    from tests.cloud.test_ipcch_binding import add_population
    from tests.cloud.test_ipcch_initial import write_bundle

    monkeypatch.setitem(sys.modules, "ee", types.SimpleNamespace(
        Initialize=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("EE outage"))))
    base = tmp_path / "real"
    base.mkdir()
    bundle, man = write_bundle(base, inputs(), fixture=False)
    add_population(bundle, man)
    finalize_entries(str(bundle))
    env = bd.build_envelope(str(package), str(bundle), envelope_version=1, created_at="2026-10-31T00:00:00Z",
                            acceptor="research lead", accepted_at="2026-10-31")
    sha = bd.write_envelope(env, str(base / "env.json"))
    b = bd.verify_combination(str(base / "env.json"), str(package), mode="real", expected_envelope_sha256=sha)
    store, root = LocalObjectStore(tmp_path / "store"), StoreRoot("real", STORES["real"])
    initial.install_acceptance(store, root, str(bundle), binding=b)
    initial.initialise(store, root, str(bundle), binding=b)
    roster = ["11", "12", "13"]
    bid = bt.new_batch_id("gen-run", "2026-10")
    ref, _ = bt.write_batch(store, STORES["real"], batch_id=bid, run_id="gen-run", mode="real", execution_month="2026-10",
                            binding=b, horizons={h: frame(h) for h in (2, 8, 14)}, roster=roster, generation={},
                            acceptance=[], retained_refs={}, generated_at="2026-10-31T00:00:00Z")
    cfg = config(tmp_path, package, providers={"smoke": "tests.cloud.ipcch_smoke_fixture:entrypoint_providers",
                                               "real": "tests.cloud.test_ipcch_entrypoint_v2:failing_factory"},
                 installed={"smoke": {"envelope": "/x/env.json", "package_root": "/x", "bundle_dir": "/x/b",
                                      "fixture_root": "/x"},
                            "real": {"envelope": str(base / "env.json"), "package_root": str(package),
                                     "bundle_dir": str(bundle)}})
    objects = {}

    def put(name, data):
        r = {"uri": f"gs://ops-real/inputs/{name}", "generation": str(200 + len(objects)),
             "sha256": hashlib.sha256(data).hexdigest()}
        objects[(r["uri"], r["generation"])] = data
        return r
    req = {"schema_version": fx.v2.SCHEMA_VERSION, "run_id": "real-inf-1", "mode": "real", "execution_month": "2026-10",
           "operations": {"ipcch_generation": False, "ipcch_inference": True, "fewsnet_generation": False,
                          "fewsnet_inference": False},
           "ipcch": {"model_combination": {"combination_id": b.combination_id,
                                           "envelope": put("env.json", (base / "env.json").read_bytes())},
                     "feature_batch": {"batch_id": bid, "manifest": ref},
                     "country_reference": put("country_reference.csv", fx.COUNTRY_REFERENCE.encode())},
           "fewsnet": None, "publication": "candidate",
           "runtime": {"image_uri": "us-central1-docker.pkg.dev/p/r/img@sha256:" + "a" * 64,
                       "environment_manifest": put("env", b"e")},
           "release": {"namespace": "prod", "expected_pointer_generation": "0"},
           "operator": "ops@example.org", "prepared_at": "2026-10-30T05:00:00Z"}
    refs = fx.Refs()
    refs.objects = objects
    uri = "gs://ops-real/requests/real-inf-1/run_manifest.json"
    objects[(uri, "1")] = json.dumps(req).encode()
    out = ep.run(cfg, request_uri=uri, request_generation="1", store=store, reader=Reader(refs, store),
                 now=fx.datetime(2026, 10, 30, 6, tzinfo=fx.timezone.utc))
    ip = out["systems"]["ipcch"]
    assert ip["failed_operation"] in (None, "publication"), ip                 # never blocked before inference
    assert sorted(ip["result"]["inference"]["horizons"]) == ["14", "2", "8"]


def test_smoke_store_initialisation_route_then_a_request_runs(tmp_path, package):
    """The executable initialisation route (entrypoint_v2 initialise / initialise_store): a fresh smoke store is
    initialised from the installed binding + fixture bundle with fixture acceptance records only, then a smoke
    request runs end to end on it; real initialisation refuses an unaccepted (smoke/candidate) envelope."""
    from cloud.common.object_store import LocalObjectStore
    from tests.cloud.ipcch_binding_fixtures import smoke_envelope
    root_dir = tmp_path / "fixture-root"
    root_dir.mkdir()
    fx.build_bundle(root_dir)
    smoke_envelope(tmp_path / "env.json", package)
    cfg = config(tmp_path, package)
    store = LocalObjectStore(tmp_path / "fresh-store")
    with pytest.raises(ep.EntrypointError, match="--acceptor"):
        ep.initialise_store(cfg, "smoke", store=store)
    report = ep.initialise_store(cfg, "smoke", store=store, acceptor="ops@example.org")
    assert report["acceptance"]["fixture"] and report["acceptance"]["appended"] > 0
    refs = fx.Refs()
    req = raw(fx.smoke_request(refs, tmp_path / "env.json", inference=True))
    out = ep.run(cfg, request_uri=put_request(refs, req), request_generation="1", store=store,
                 reader=Reader(refs, store))
    assert out["status"] == "succeeded"
    real_cfg = dict(cfg, installed={**cfg["installed"], "real": {"envelope": str(tmp_path / "env.json"),
                                                                  "package_root": str(package),
                                                                  "bundle_dir": str(root_dir / "bundle")}})
    from cloud.ipcch import binding as bd
    with pytest.raises(bd.BindingError):
        ep.initialise_store(real_cfg, "real", store=LocalObjectStore(tmp_path / "real-store"))


def test_real_store_initialisation_route_installs_the_bound_acceptance_entries(tmp_path, package):
    """Real: the installed ACCEPTED envelope/package/bundle; the finalized entries are installed (R45) and the store is
    paired with the combination; a rerun is idempotent (no acceptance entry appended, every table unchanged)."""
    from cloud.common.object_store import LocalObjectStore
    from cloud.ipcch import binding as bd
    from cloud.ipcch.stores import StoreRoot
    from tests.cloud.test_ipcch_binding import real_setup
    bundle, _, pkg, env_path, _ = real_setup(tmp_path)
    cfg = config(tmp_path, package, installed={
        "smoke": {"envelope": "/x/env.json", "package_root": "/x", "bundle_dir": "/x/b", "fixture_root": "/x"},
        "real": {"envelope": str(env_path), "package_root": str(pkg), "bundle_dir": str(bundle)}})
    store = LocalObjectStore(tmp_path / "real-store")
    report = ep.initialise_store(cfg, "real", store=store)
    assert report["acceptance"]["appended"] > 0 and report["combination_id"]
    pairing, _ = bd.store_pairing(store, StoreRoot("real", STORES["real"]))
    assert pairing["mode"] == "real" and pairing["roster_size"] > 0
    again = ep.initialise_store(cfg, "real", store=store)                              # idempotent rerun
    assert again["acceptance"]["appended"] == 0 and again["initialise"]["initialised"] == []
    assert sorted(again["initialise"]["unchanged"]) == sorted(report["initialise"]["initialised"])


# --------------------------------------------------------------------------- task 10-30: replay reservation and deadline


def real_inference_world(tmp_path, package, publication="current"):
    """The real inference-only route of test_real_inference_only_never_builds_acquisition_providers (accepted real
    envelope, initialised real store, an existing batch), returning (cfg, store, refs, request body, objects)."""
    import hashlib

    from cloud.common.object_store import LocalObjectStore
    from cloud.ipcch import batch as bt
    from cloud.ipcch import binding as bd
    from cloud.ipcch import initial
    from cloud.ipcch.stores import StoreRoot
    from tests.cloud.ipcch_binding_fixtures import finalize_entries
    from tests.cloud.test_ipcch_assembly import inputs
    from tests.cloud.test_ipcch_batch import frame
    from tests.cloud.test_ipcch_binding import add_population
    from tests.cloud.test_ipcch_initial import write_bundle

    base = tmp_path / "real"
    base.mkdir()
    bundle, man = write_bundle(base, inputs(), fixture=False)
    add_population(bundle, man)
    finalize_entries(str(bundle))
    env = bd.build_envelope(str(package), str(bundle), envelope_version=1, created_at="2026-10-31T00:00:00Z",
                            acceptor="research lead", accepted_at="2026-10-31")
    sha = bd.write_envelope(env, str(base / "env.json"))
    b = bd.verify_combination(str(base / "env.json"), str(package), mode="real", expected_envelope_sha256=sha)
    store, root = LocalObjectStore(tmp_path / "store"), StoreRoot("real", STORES["real"])
    initial.install_acceptance(store, root, str(bundle), binding=b)
    initial.initialise(store, root, str(bundle), binding=b)
    bid = bt.new_batch_id("gen-run", "2026-10")
    ref, _ = bt.write_batch(store, STORES["real"], batch_id=bid, run_id="gen-run", mode="real", execution_month="2026-10",
                            binding=b, horizons={h: frame(h) for h in (2, 8, 14)}, roster=["11", "12", "13"],
                            generation={}, acceptance=[], retained_refs={}, generated_at="2026-10-31T00:00:00Z")
    cfg = config(tmp_path, package, providers={"smoke": "tests.cloud.ipcch_smoke_fixture:entrypoint_providers",
                                               "real": "tests.cloud.test_ipcch_entrypoint_v2:failing_factory"},
                 installed={"smoke": {"envelope": "/x/env.json", "package_root": "/x", "bundle_dir": "/x/b",
                                      "fixture_root": "/x"},
                            "real": {"envelope": str(base / "env.json"), "package_root": str(package),
                                     "bundle_dir": str(bundle)}})
    objects = {}

    def put(name, data):
        r = {"uri": f"gs://ops-real/inputs/{name}", "generation": str(200 + len(objects)),
             "sha256": hashlib.sha256(data).hexdigest()}
        objects[(r["uri"], r["generation"])] = data
        return r
    req = {"schema_version": fx.v2.SCHEMA_VERSION, "run_id": "real-inf-1", "mode": "real", "execution_month": "2026-10",
           "operations": {"ipcch_generation": False, "ipcch_inference": True, "fewsnet_generation": False,
                          "fewsnet_inference": False},
           "ipcch": {"model_combination": {"combination_id": b.combination_id,
                                           "envelope": put("env.json", (base / "env.json").read_bytes())},
                     "feature_batch": {"batch_id": bid, "manifest": ref},
                     "country_reference": put("country_reference.csv", fx.COUNTRY_REFERENCE.encode())},
           "fewsnet": None, "publication": publication,
           "runtime": {"image_uri": "us-central1-docker.pkg.dev/p/r/img@sha256:" + "a" * 64,
                       "environment_manifest": put("env", b"e")},
           "release": {"namespace": "prod", "expected_pointer_generation": "0"},
           "operator": "ops@example.org", "prepared_at": "2026-10-30T05:00:00Z"}
    refs = fx.Refs()
    refs.objects = objects
    return cfg, store, refs, req, objects


class Writes(Spy):
    """Store wrapper recording mutations only."""

    def __getattr__(self, name):
        attr = getattr(self.inner, name)
        if name in ("write_text", "write_bytes", "copy", "delete"):
            def call(*a, **k):
                self.touched.append((name, a[0] if a else None))
                return attr(*a, **k)
            return call
        return attr


def test_completed_october_request_redelivered_after_current_advanced_returns_its_durable_status(
        tmp_path, package, monkeypatch):
    from cloud.orchestrator import delivery_request_v2 as v2
    cfg, store, refs, req, objects = real_inference_world(tmp_path, package)
    uri = "gs://ops-real/requests/real-inf-1/run_manifest.json"
    objects[(uri, "1")] = json.dumps(req).encode()
    october = fx.datetime(2026, 10, 30, 6, tzinfo=fx.timezone.utc)
    first = ep.run(cfg, request_uri=uri, request_generation="1", store=store, reader=Reader(refs, store), now=october)
    reservation = json.loads(store.read_text(f"{ROOTS['real']}/runs/real-inf-1/v2_reservation.json"))
    assert reservation["deadline_utc"] == "2026-10-30T10:00:00Z" and reservation["request"]["generation"] == "1"

    monkeypatch.setattr(pub, "ipcch_execution_month", lambda record: "2026-11")         # current has advanced
    november = fx.datetime(2026, 11, 2, 6, tzinfo=fx.timezone.utc)
    calls = []
    monkeypatch.setattr(pub, "read_current", lambda *a, **k: calls.append("read_current"))
    monkeypatch.setattr(v2, "admit", lambda *a, **k: calls.append("admit"))
    writes = Writes(store)
    again = ep.run(cfg, request_uri=uri, request_generation="1", store=writes, reader=Reader(refs, store), now=november)
    assert again["replayed"] is True and calls == [] and writes.touched == []               # no admission/read/mutation
    assert {k: v for k, v in again.items() if k != "replayed"} == json.loads(json.dumps(first, default=str))
    assert json.loads(store.read_text(f"{ROOTS['real']}/runs/real-inf-1/v2_reservation.json")) == reservation  # no reset

    monkeypatch.undo()                                                                     # control: real admission
    monkeypatch.setattr(pub, "ipcch_execution_month", lambda record: "2026-11")
    other = dict(req, run_id="real-inf-2")
    uri2 = "gs://ops-real/requests/real-inf-2/run_manifest.json"
    objects[(uri2, "1")] = json.dumps(other).encode()
    with pytest.raises(v2.DeliveryRequestV2Error, match="earlier than the current IPCCH release month"):
        ep.run(cfg, request_uri=uri2, request_generation="1", store=store, reader=Reader(refs, store), now=november)
    assert store.get_metadata(f"{ROOTS['real']}/runs/real-inf-2/v2_reservation.json") is None   # rejected: no write


def test_changed_request_or_unfinished_reservation_is_never_relaunched(tmp_path, package):
    store, refs, _, _ = smoke_world(tmp_path, package)
    cfg = config(tmp_path, package, providers={"smoke": "tests.cloud.test_ipcch_entrypoint_v2:failing_factory",
                                               "real": "cloud.ipcch.entrypoint_v2:real_providers"})
    req = raw(fx.smoke_request(refs, tmp_path / "env.json", inference=True))
    uri = put_request(refs, req)
    changed = dict(req, operator="someone-else@example.org")
    refs.objects[(uri, "2")] = json.dumps(changed).encode()
    reservation = f"{ROOTS['smoke']}/runs/smoke-run-1/v2_reservation.json"
    import hashlib
    store.write_text(reservation, json.dumps({"request": {"uri": uri, "generation": "1", "sha256": hashlib.sha256(
        refs.objects[(uri, "1")]).hexdigest()}, "reserved_at": "2026-10-30T05:00:00Z"}), if_generation_match=0)
    writes = Writes(store)
    with pytest.raises(ep.EntrypointError, match="no final status .* not launched again"):
        ep.run(cfg, request_uri=uri, request_generation="1", store=writes, reader=Reader(refs, store))
    with pytest.raises(ep.EntrypointError, match="a changed request needs a new run ID"):
        ep.run(cfg, request_uri=uri, request_generation="2", store=writes, reader=Reader(refs, store))
    assert writes.touched == []                                     # neither attempt wrote or built providers


def test_failure_after_the_reservation_leaves_a_durable_failed_status(tmp_path, package, monkeypatch):
    from cloud.ipcch import locks
    store, refs, _, _ = smoke_world(tmp_path, package)
    cfg = config(tmp_path, package)
    uri = put_request(refs, raw(fx.smoke_request(refs, tmp_path / "env.json", inference=True)))
    monkeypatch.setattr(locks, "acquire", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("lock service down")))
    with pytest.raises(RuntimeError, match="lock service down"):
        ep.run(cfg, request_uri=uri, request_generation="1", store=store, reader=Reader(refs, store))
    status = json.loads(store.read_text(f"{ROOTS['smoke']}/runs/smoke-run-1/v2_run_status.json"))
    assert status["status"] == "failed" and "lock service down" in status["reason"]
    monkeypatch.undo()
    replay = ep.run(cfg, request_uri=uri, request_generation="1", store=store, reader=Reader(refs, store))
    assert replay["replayed"] is True and replay["status"] == "failed"               # failed identity: not rerun


CAPTURED = []


def capture_providers(**kw):
    CAPTURED.append(kw)
    return fx.entrypoint_providers(**kw)


def test_the_persisted_deadline_reaches_the_provider_factory(tmp_path, package):
    store, refs, _, _ = smoke_world(tmp_path, package)
    cfg = config(tmp_path, package, run_timeout_seconds=3600,
                 providers={"smoke": "tests.cloud.test_ipcch_entrypoint_v2:capture_providers",
                            "real": "cloud.ipcch.entrypoint_v2:real_providers"})
    uri = put_request(refs, raw(fx.smoke_request(refs, tmp_path / "env.json")))
    now = fx.datetime(2026, 10, 30, 6, tzinfo=fx.timezone.utc)
    CAPTURED.clear()
    out = ep.run(cfg, request_uri=uri, request_generation="1", store=store, reader=Reader(refs, store), now=now)
    (kw,) = CAPTURED
    assert kw["deadline_utc"] == now + timedelta(seconds=3600) and kw["execution_month"] == "2027-03"
    assert kw["root"].uri == STORES["smoke"] and kw["run_id"] == "smoke-run-1"
    reservation = json.loads(store.read_text(f"{ROOTS['smoke']}/runs/smoke-run-1/v2_reservation.json"))
    assert reservation["deadline_utc"] == out["deadline_utc"] == "2026-10-30T07:00:00Z"


@pytest.mark.parametrize("over, ok", [({"run_timeout_seconds": 14400}, True), ({"run_timeout_seconds": 3600}, True),
                                      ({"run_timeout_seconds": 14401}, False), ({"run_timeout_seconds": 900}, False),
                                      ({"run_timeout_seconds": True}, False), ({"run_timeout_seconds": 86400}, False),
                                      ({"producer_asset_root": "projects/feisty-flames-511718-d4/assets/"}, True),
                                      ({"producer_asset_root": "projects/p/assets"}, False)])
def test_config_caps_the_run_budget_at_the_job_timeout(tmp_path, package, over, ok):
    if ok:
        config(tmp_path, package, **over)
    else:
        with pytest.raises(ep.EntrypointError):
            config(tmp_path, package, **over)


def test_real_providers_wire_the_producer_and_the_persisted_deadline(tmp_path, monkeypatch):
    """entrypoint_v2.real_providers with the EE SDK/transport constructors stubbed: the table producer gets the
    configured asset root, run ID and execution month; the persisted deadline reaches the EE transport and the GPP/VIIRS
    acquirer; missing prerequisites refuse before any EE initialisation."""
    import sys
    import types

    from cloud.common.object_store import LocalObjectStore
    from cloud.ipcch import ee_transport
    from cloud.ipcch.stores import StoreRoot
    from cloud.ipcch.table_producers import TableProducer

    made = {}

    def fake_transport(**kw):
        made["transport"] = kw
        return types.SimpleNamespace(ee=None, **kw)
    monkeypatch.setattr(ee_transport, "from_environment", fake_transport)
    monkeypatch.setitem(sys.modules, "ee", types.SimpleNamespace())
    deadline = fx.datetime(2026, 10, 30, 10, tzinfo=fx.timezone.utc)
    cfg = {"earth_engine_project": "feisty-flames-511718-d4", "export_root": "gs://ops-exports/v2",
           "producer_asset_root": "projects/feisty-flames-511718-d4/assets/"}
    store, root = LocalObjectStore(tmp_path), StoreRoot("real", STORES["real"])
    out = ep.real_providers(cfg=cfg, store=store, client=None, run_id="real-run-1", roster=["11"], root=root,
                            deadline_utc=deadline, execution_month="2026-10")
    assert made["transport"] == {"project": "feisty-flames-511718-d4", "output_root": "gs://ops-exports/v2",
                                 "run_id": "real-run-1", "deadline_utc": deadline}
    assert out["gpp_acquirer"] is out["nightlight_acquirer"] and out["gpp_acquirer"].deadline_utc == deadline
    producer = out["climate_providers"].__closure__
    found = [c.cell_contents for c in producer if isinstance(c.cell_contents, TableProducer)]
    assert len(found) == 1 and (found[0].output_root, found[0].run_id, found[0].execution_month) == \
        ("projects/feisty-flames-511718-d4/assets/", "real-run-1", "2026-10")
    for missing in ({"deadline_utc": None}, {"root": None}, {"execution_month": None}):
        made.clear()
        kw = dict(cfg=cfg, store=store, client=None, run_id="r", roster=["11"], root=root, deadline_utc=deadline,
                  execution_month="2026-10")
        kw.update(missing)
        with pytest.raises(ep.EntrypointError, match="persisted deadline"):
            ep.real_providers(**kw)
        assert made == {}
    with pytest.raises(ep.EntrypointError, match="producer_asset_root"):
        ep.real_providers(cfg={k: v for k, v in cfg.items() if k != "producer_asset_root"}, store=store, client=None,
                          run_id="r", roster=["11"], root=root, deadline_utc=deadline, execution_month="2026-10")
