"""Task 10-29 CP4: the executable v2 route (cloud.ipcch.entrypoint_v2.run) on local stores - config validation,
installed binding vs the request's pinned envelope, admission, locks, publication and run status (R5, R17, R36, R48)."""

import json

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
