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
    assert out["status"] == "succeeded" and out["systems"]["ipcch"]["publication"]["status"] == "published"
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
