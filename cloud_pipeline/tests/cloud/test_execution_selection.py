"""Manifest step selection, inherited (unscored) systems and candidate publication."""

import copy
import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from cloud.orchestrator import delivery_job as dj
from cloud.orchestrator import delivery_manifest as dm
from tests.cloud import test_delivery_job as tj
from tests.cloud import test_delivery_manifest as tm

TARGETS = {0: "2026-10", 6: "2027-04", 12: "2027-10"}


def _execution(**override):
    execution = {"remote_update": False, "inference_systems": ["fewsnet"], "prepare_request": None,
                 "inherit": {"ipcch": {"source_delivery_id": "oct-confidence-20261009b", "origin_month": "2026-10",
                                       "manifest": tm._ref("deliveries/src/manifest.json"),
                                       "archive": tm._ref("deliveries/src/webapp_model_bundle.tar.gz")}},
                 "publication": "candidate"}
    execution.update(override)
    return execution


def test_fews_only_execution_with_inherited_ipcch_validates_and_legacy_keeps_both():
    request = tm._request()
    assert dm.selected_systems(tm._validate(request)) == ("fewsnet", "ipcch")  # legacy meaning unchanged
    validated = tm._validate({**request, "execution": _execution()})
    assert dm.selected_systems(validated) == ("fewsnet",)
    fields = {field for field, _ in dm.iter_object_refs(validated)}
    assert {"execution.inherit.ipcch.manifest", "execution.inherit.ipcch.archive"} <= fields


@pytest.mark.parametrize("override,message", [
    ({"inference_systems": []}, "selects no step"),
    ({"inherit": {}}, "must name exactly"),
    ({"inference_systems": ["fewsnet", "ipcch"]}, "must name exactly"),
    ({"inference_systems": ["fewsnet", "fewsnet"]}, "unique members"),
    ({"publication": "now"}, "publication"),
    ({"remote_update": True}, "prepare_request"),
    ({"prepare_request": tm._ref("prepare_requests/x/prepare_request.json")}, "must be null"),
])
def test_invalid_execution_selections_are_rejected(override, message):
    with pytest.raises(dm.DeliveryManifestError, match=message):
        tm._validate({**tm._request(), "execution": _execution(**override)})


def test_inherited_source_must_have_the_same_origin():
    execution = _execution()
    execution["inherit"]["ipcch"]["origin_month"] = "2026-09"
    with pytest.raises(dm.DeliveryManifestError, match="same origin"):
        tm._validate({**tm._request(), "execution": execution})


def test_prepared_snapshot_may_be_null_only_for_a_remote_update_intent():
    request = {**tm._request(), "prepared_snapshot": None}
    with pytest.raises(dm.DeliveryManifestError, match="remote-update intent"):
        tm._validate({**request, "execution": _execution()})
    intent = tm._validate({**request, "execution": _execution(
        remote_update=True, prepare_request=tm._ref("prepare_requests/p/prepare_request.json"))})
    assert "prepared_snapshot.manifest" not in {field for field, _ in dm.iter_object_refs(intent)}
    prepare_only = tm._validate({**request, "execution": _execution(
        remote_update=True, inference_systems=[], inherit={},
        prepare_request=tm._ref("prepare_requests/p/prepare_request.json"))})
    assert dm.selected_systems(prepare_only) == ()


def _bound(tmp_path):
    client, request = tj._world(tmp_path)
    request["execution"] = _execution()
    for ref in request["execution"]["inherit"]["ipcch"].values():
        if isinstance(ref, dict):
            ref.update(client.put(ref["uri"], ref["generation"], ref["uri"].encode()))
    return client, request


def test_only_selected_systems_score_and_a_candidate_never_moves_the_pointer(tmp_path, monkeypatch):
    client, request = _bound(tmp_path)
    inherited = []

    def fake_inherit(out, system, source, downloader, *, origin, package_dirs):
        inherited.append((system, source["source_delivery_id"], origin, sorted(package_dirs)))
        return {"members": {}}

    def package(out, spec, req, *, image_uri, inherited=None):
        assert set(inherited) == {"ipcch"}
        return {"validation": "passed", "archive": out / "webapp_model_bundle.tar.gz"}

    monkeypatch.setattr(dj, "inherit_system", fake_inherit)
    status, calls, store = tj._execute(tmp_path, client, request, package=package)
    assert status["status"] == "succeeded" and calls["score"] == ["fewsnet"]
    assert inherited == [("ipcch", "oct-confidence-20261009b", "2026-10", [""])]
    assert status["release"] is None and store.get_metadata(f"{tj.ROOT}/dual-system/current.json") is None
    candidate = json.loads(store.read_text(f"{tj.ROOT}/candidates/oct2026-r1/candidate.json"))
    assert candidate["execution"] == {"scored_systems": ["fewsnet"], "inherited_systems": ["ipcch"]}


def test_prepare_only_or_unresolved_intents_never_run_delivery(tmp_path):
    client, request = _bound(tmp_path)
    intent = copy.deepcopy(request)
    intent["execution"] = _execution(remote_update=True, inference_systems=[], inherit={},
                                     prepare_request=tm._ref("prepare_requests/p/prepare_request.json"))
    with pytest.raises(dj.AcceptanceError, match="prepare-only"):
        tj._execute(tmp_path, client, intent, score=lambda *a: pytest.fail("scored"))
    unresolved = copy.deepcopy(request)
    unresolved["prepared_snapshot"] = None
    unresolved["execution"] = _execution(remote_update=True,
                                         prepare_request=tm._ref("prepare_requests/p/prepare_request.json"))
    for ref in [unresolved["execution"]["prepare_request"]]:
        ref.update(client.put(ref["uri"], ref["generation"], b"intent"))
    status_or_error = None
    try:
        tj._execute(tmp_path, client, unresolved, score=lambda *a: pytest.fail("scored"))
    except dj.AcceptanceError as exc:
        status_or_error = str(exc)
    assert status_or_error and "unresolved remote-update intent" in status_or_error


# --- inherit_system on a real (small) source archive --------------------------------------------


def _source(tmp_path, *, origin="2026-10", target_shift=0, package_bytes=b"model"):
    root = tmp_path / "source"
    files = {"reports/delivery.json": json.dumps({"origin_month": origin, "run_id": "oct-confidence-20261009b"}).encode(),
             "ipcch/polygons.geojson": b"{}", "ipcch/country_population_reference.csv": b"ISO3\nSOM\n",
             "inputs/ipcch_origin_rows.csv": b"area_id\n1\n", "inputs/evidence/ipcch_0m_maximum_phase.csv": b"x\n",
             "reports/ipcch_diagnostic_declarations.json": b"{}", "reports/fewsnet_assembly.json": b"{}",
             "scopes/0m/fewsnet/polygon_predictions.csv": b"admin_code\n0\n",
             "ipcch/model_package/scope_0m/model.json": package_bytes,
             "ipcch/model_package/model_package_manifest.json": b"{}"}
    for horizon, target in TARGETS.items():
        month = target if not target_shift else "2030-01"
        for name in dj_scope_tables():
            body = (f"polygon_id,feature_period,target_period\n1,{origin},{month}\n".encode()
                    if name == "polygon_predictions" else b"polygon_id\n1\n")
            files[f"scopes/{horizon}m/ipcch/{name}.csv"] = body
    manifest = {"files": [{"path": path, "sha256": hashlib.sha256(data).hexdigest()} for path, data in files.items()],
                "provenance": {"run_id": "oct-confidence-20261009b", "image_uri": "old-image"}}
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as tar:
        for path, data in files.items():
            info = tarfile.TarInfo(path)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    root.mkdir()
    (root / "manifest.json").write_text(json.dumps(manifest))
    (root / "bundle.tar.gz").write_bytes(archive.getvalue())
    package = tmp_path / "package"
    (package / "scope_0m").mkdir(parents=True)
    (package / "scope_0m/model.json").write_bytes(b"model")
    (package / "model_package_manifest.json").write_bytes(b"{}")
    return root, files, package


def dj_scope_tables():
    from cloud.orchestrator.delivery_bundle import SCOPE_TABLES

    return SCOPE_TABLES["ipcch"]


class LocalDownloader:
    def __init__(self, paths):
        self.paths = paths

    def fetch(self, ref):
        path = self.paths[ref["uri"]]
        if hashlib.sha256(path.read_bytes()).hexdigest() != ref["sha256"]:
            raise dj.AcceptanceError("sha256 mismatch")
        return path


def _inherit(tmp_path, root, package):
    refs = {name: {"uri": f"gs://src/{name}", "generation": "1",
                   "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest()}
            for name in ("manifest.json", "bundle.tar.gz")}
    downloader = LocalDownloader({f"gs://src/{name}": root / name for name in refs})
    source = {"source_delivery_id": "oct-confidence-20261009b", "origin_month": "2026-10",
              "manifest": refs["manifest.json"], "archive": refs["bundle.tar.gz"]}
    out = tmp_path / "out"
    return out, dj.inherit_system(out, "ipcch", source, downloader, origin="2026-10", package_dirs={"": package})


def test_inherited_members_are_byte_identical_and_scoped_to_the_system(tmp_path):
    root, files, package = _source(tmp_path)
    out, record = _inherit(tmp_path, root, package)
    expected = {path for path in files if path.startswith(("scopes/", "ipcch/", "inputs/", "reports/ipcch"))
                and "/fewsnet/" not in path and "model_package" not in path}
    assert set(record["members"]) == expected
    assert all((out / path).read_bytes() == files[path] for path in expected)
    assert not (out / "reports/delivery.json").exists() and not (out / "scopes/0m/fewsnet").exists()
    assert record["model_package"] == {"scope_0m/model.json": hashlib.sha256(b"model").hexdigest(),
                                       "model_package_manifest.json": hashlib.sha256(b"{}").hexdigest()}
    assert record["source_run_id"] == "oct-confidence-20261009b"


@pytest.mark.parametrize("change,message", [
    ({"origin": "2026-09"}, "not an origin 2026-10 delivery"),
    ({"target_shift": 1}, "targets differ"),
    ({"package_bytes": b"other model"}, "model package differs"),
])
def test_inheritance_rejects_other_origins_targets_or_packages(tmp_path, change, message):
    root, _, package = _source(tmp_path, **change)
    with pytest.raises(dj.AcceptanceError, match=message):
        _inherit(tmp_path, root, package)


def test_inheritance_rejects_members_that_differ_from_the_source_inventory(tmp_path):
    root, _, package = _source(tmp_path)
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["files"][1]["sha256"] = "0" * 64
    (root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(dj.AcceptanceError, match="does not match the source inventory"):
        _inherit(tmp_path, root, package)
