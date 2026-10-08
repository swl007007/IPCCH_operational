"""Request-driven delivery entry: pinned inputs, acceptance and release ordering (local fakes; not cloud acceptance)."""
import hashlib
import json

import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.orchestrator import delivery_job as dj
from cloud.orchestrator import delivery_manifest as dm
from tests.cloud.test_delivery_manifest import _request

IMAGE = "europe-docker.pkg.dev/p/r/delivery@sha256:" + "c" * 64
ROOT = "gs://ipcch-requests"
REQUEST_REF = {"uri": f"{ROOT}/requests/oct2026-r1/run_manifest.json", "generation": "1759900000000001"}


class FakeNotFound(Exception):
    pass


class FakeBlob:
    def __init__(self, objects, key):
        self.objects, self.key = objects, key

    def download_to_filename(self, path):
        if self.key not in self.objects:
            raise FakeNotFound(self.key)
        with open(path, "wb") as handle:
            handle.write(self.objects[self.key])


class FakeClient:
    def __init__(self):
        self.objects, self.downloads = {}, []

    def bucket(self, name):
        client = self

        class Bucket:
            def blob(self, blob_name, generation=None):
                client.downloads.append((name, blob_name, generation))
                return FakeBlob(client.objects, (name, blob_name, str(generation)))

        return Bucket()

    def put(self, uri, generation, data):
        bucket, _, name = uri.removeprefix("gs://").partition("/")
        self.objects[(bucket, name, str(generation))] = data
        return {"uri": uri, "generation": str(generation), "sha256": hashlib.sha256(data).hexdigest()}


FAMILY_COLUMNS = None


def _history_panels():
    from tools.refresh_h5_inputs import CONFLICT_COLUMNS, WFP_COLUMNS

    family = {column: "0.5" for column in WFP_COLUMNS + CONFLICT_COLUMNS}
    fews = "FEWSNET_admin_code,date," + ",".join(family) + "\n" + "".join(
        f"{area},2026-0{month}-01," + ",".join(family.values()) + "\n" for area in ("1", "2") for month in (3, 4))
    ipcch = "admin_code,year,month," + ",".join(family) + "\n" + "".join(
        f"{area},2026,{month}," + ",".join(family.values()) + "\n" for area in ("a", "b") for month in (3, 4))
    return {"fewsnet": fews.encode(), "ipcch": ipcch.encode()}


def _snapshot(tmp_path, history_bytes, family):
    paths = {}
    for system, data in history_bytes.items():
        paths[system] = tmp_path / f"history_{system}.csv"
        paths[system].write_bytes(data)
    return "".join(dj.retained_family_rows({k: str(v) for k, v in paths.items()}, family)).encode()


def _world(tmp_path):
    """A structurally valid request whose every pinned ref exists with its exact bytes and bindings."""
    from cloud.batch.remote_sources import EXTRACTION_CONTRACT_VERSION, SYSTEM_FAMILIES

    client, request = FakeClient(), _request()
    request["runtime"]["image_uri"] = IMAGE
    request["acled"] = {"action": "keep", "retained_snapshot": request["acled"]["raw_upload"],
                        "converter_contract": request["acled"]["converter_contract"]}

    def bind(ref, data):
        ref.update(client.put(ref["uri"], ref["generation"], data))

    history = _history_panels()
    for system, kinds in request["assets"].items():
        bind(kinds["roster"], f"roster of {system}".encode())
        bind(kinds["geometry"], f"geometry of {system}".encode())
        bind(kinds["history_panel"], history[system])
    for name in ("acled", "wfp"):
        bind(request[name]["retained_snapshot"], _snapshot(tmp_path, history, name))
    bind(request["runtime"]["environment_manifest"], json.dumps(
        {"image_uri": IMAGE, "requirements_lock_sha256": dj.lock_sha256()}).encode())
    outputs = {family: {"outputs": {system: client.put(f"gs://ipcch-delivery/prepared/{family}_{system}.csv", "2",
                                                       b"admin_code,month\n")
                                    for system in ("fewsnet", "ipcch") if family in SYSTEM_FAMILIES[system]}}
               for family in sorted(set(SYSTEM_FAMILIES["fewsnet"]) | set(SYSTEM_FAMILIES["ipcch"]))}
    systems = {system: {"roster": dict(kinds["roster"]), "geometry": dict(kinds["geometry"])}
               for system, kinds in request["assets"].items()}
    bind(request["prepared_snapshot"]["manifest"], json.dumps(
        {"prepare_id": "prep-202610-a", "origin_month": "2026-10", "status": "succeeded", "families": outputs,
         "systems": systems, "extraction_contract_version": EXTRACTION_CONTRACT_VERSION}).encode())
    shared = client.put("gs://ipcch-delivery/models/ipcch/model_package_manifest.json", "3", b'{"training_cutoff": "2026-04-01"}')
    for model in request["models"]:
        system, horizon, package_id = model["system"], model["horizon_months"], model["package_id"]
        if system == "fewsnet":
            schema = hashlib.sha256(f"schema {horizon}".encode()).hexdigest()
            members = {"model.bin": f"{package_id}".encode(),
                       "training_report.json": json.dumps({"feature_schema_sha256": schema}).encode()}
        else:
            contract = f"feature_name,source_column\nx{horizon},x\n".encode()
            schema = hashlib.sha256(contract).hexdigest()
            members = {f"scope_{horizon}m/feature_contract.csv": contract, f"scope_{horizon}m/model.bin": package_id.encode()}
        model["feature_schema_sha256"] = schema
        files = [{"path": path, **client.put(f"gs://ipcch-delivery/models/{system}/{horizon}m/{path}", "3", data)}
                 for path, data in members.items()]
        if system == "ipcch":
            files.append({"path": "model_package_manifest.json", **shared})  # overlapping member, identical bytes
        bind(model["package_manifest"], json.dumps({
            "schema_version": dj.PACKAGE_MANIFEST_SCHEMA, "system": system, "horizon_months": horizon,
            "package_id": package_id, "files": files}).encode())
    for model in request["models"]:
        bind(model["acceptance_report"], json.dumps(_acceptance(model, request)).encode())
    for field, ref in dm.iter_object_refs({**request, "validation_level": "structural"}):
        placeholder = hashlib.sha256(ref["uri"].removeprefix("gs://ipcch-delivery/").encode()).hexdigest()
        if ref["sha256"] == placeholder:  # not yet bound above
            bind(ref, f"bytes of {field}".encode())
    return client, request


def _acceptance(model, request, **override):
    return {"schema_version": dj.ACCEPTANCE_REPORT_SCHEMA, "system": model["system"],
            "horizon_months": model["horizon_months"], "package_id": model["package_id"], "status": "accepted",
            "package_manifest_sha256": model["package_manifest"]["sha256"],
            "feature_schema_sha256": model["feature_schema_sha256"],
            "runtime": {"image_uri": request["runtime"]["image_uri"],
                        "environment_manifest_sha256": request["runtime"]["environment_manifest"]["sha256"]},
            **override}


def _rebind_acceptance(client, model, report):
    model["acceptance_report"].update(client.put(model["acceptance_report"]["uri"], "90", json.dumps(report).encode()))


def _execute(tmp_path, client, request, *, image=IMAGE, namespace="dual-system", score=None, package=None, store=None):
    calls = {"score": [], "package": 0, "upload": 0}

    def fake_score(spec_path, system, out):
        calls["score"].append(system)
        spec = json.loads(spec_path.read_text())
        assert sorted(spec["packages"]["fewsnet"]) == ["0", "12", "6"] and spec["packages"]["ipcch"]
        (out / "reports").mkdir(parents=True, exist_ok=True)

    def fake_package(out, spec, req, *, image_uri):
        calls["package"] += 1
        return {"validation": "passed", "archive": out / "webapp_model_bundle.tar.gz"}

    def fake_upload(out, run_id):
        calls["upload"] += 1
        return {name: {"uri": f"{ROOT}/deliveries/{run_id}/{name}", "generation": "1", "sha256": "d" * 64}
                for name in ("manifest.json", "webapp_model_bundle.tar.gz")}

    store = store or LocalObjectStore(tmp_path / "gcs")
    data = json.dumps(request).encode()
    ref = {**REQUEST_REF, "sha256": hashlib.sha256(data).hexdigest()}
    status = dj.execute(request_ref=ref, request_bytes=data, output_root=ROOT, release_namespace=namespace,
                        image_uri=image, store=store, downloader=dj.PinnedDownloader(client, tmp_path / "in"),
                        work=tmp_path / f"work-{len(list(tmp_path.glob('work-*')))}", score=score or fake_score,
                        package=package or fake_package, upload=fake_upload)
    return status, calls, store


def test_request_scores_each_system_from_verified_local_inputs_then_publishes_last(tmp_path):
    client, request = _world(tmp_path)

    status, calls, store = _execute(tmp_path, client, request)

    assert status["status"] == "succeeded" and calls["score"] == ["ipcch", "fewsnet"] and calls["upload"] == 1
    assert all(generation is not None for _, _, generation in client.downloads)  # never a latest-object read
    pointer = json.loads(store.read_text(f"{ROOT}/dual-system/current.json"))
    assert pointer["run_id"] == "oct2026-r1"
    record = json.loads(store.read_text(pointer["release_record"]))
    assert record["request"]["sha256"] == hashlib.sha256(json.dumps(request).encode()).hexdigest()

    again, calls_again, _ = _execute(tmp_path, client, request, store=store)  # duplicate event
    assert again["duplicate"] is True and again["status"] == "succeeded" and calls_again["score"] == []


@pytest.mark.parametrize("break_it", [
    "image", "asset_bytes", "acceptance", "package_path", "prepared_status", "smoke_roster", "prepared_contract",
    "prepared_geometry", "prepared_family_missing", "schema_changed", "acceptance_schema", "acceptance_manifest",
    "acceptance_runtime_missing", "environment_lock", "conflicting_member", "retained_snapshot_differs"])
def test_acceptance_failures_stop_before_any_scoring_and_leave_no_release(tmp_path, break_it):
    client, request = _world(tmp_path)
    image = IMAGE
    if break_it == "image":
        image = IMAGE.replace("c" * 64, "e" * 64)
    elif break_it == "asset_bytes":
        ref = request["assets"]["ipcch"]["history_panel"]
        client.put(ref["uri"], ref["generation"], b"tampered")
    elif break_it == "acceptance":
        model = request["models"][4]
        bad = json.dumps({"schema_version": dj.ACCEPTANCE_REPORT_SCHEMA, "system": model["system"],
                          "horizon_months": model["horizon_months"], "package_id": "h5-proxy", "status": "accepted"})
        model["acceptance_report"].update(client.put(model["acceptance_report"]["uri"], "99", bad.encode()))
    elif break_it == "package_path":
        model = request["models"][0]
        manifest = json.dumps({"schema_version": dj.PACKAGE_MANIFEST_SCHEMA, "system": model["system"],
                               "horizon_months": model["horizon_months"], "package_id": model["package_id"],
                               "files": [{"path": "../escape.bin", **client.put("gs://ipcch-delivery/x", "1", b"x")}]})
        model["package_manifest"].update(client.put(model["package_manifest"]["uri"], "98", manifest.encode()))
        _rebind_acceptance(client, model, _acceptance(model, request))
    elif break_it == "smoke_roster":  # a bounded 12-area preparation cannot serve the full delivery roster
        _rebind_prepared(client, request, lambda m: m["systems"]["fewsnet"].update(
            roster=client.put("gs://ipcch-delivery/assets/smoke/roster.csv", "5", b"12 areas")))
    elif break_it == "prepared_contract":
        _rebind_prepared(client, request, lambda m: m.update(extraction_contract_version="other-v0"))
    elif break_it == "prepared_geometry":
        _rebind_prepared(client, request, lambda m: m["systems"]["ipcch"].update(
            geometry=client.put("gs://ipcch-delivery/assets/other.geojson", "5", b"other geometry")))
    elif break_it == "prepared_family_missing":
        _rebind_prepared(client, request, lambda m: m["families"]["viirs"]["outputs"].pop("ipcch"))
    elif break_it in ("schema_changed", "acceptance_schema"):
        for model in request["models"]:  # all six schemas relabelled consistently in request and reports
            model["feature_schema_sha256"] = "f" * 64
            _rebind_acceptance(client, model, _acceptance(model, request))
        if break_it == "acceptance_schema":
            _rebind_acceptance(client, request["models"][0], _acceptance(request["models"][0], request,
                                                                          feature_schema_sha256="e" * 64))
    elif break_it == "acceptance_manifest":
        _rebind_acceptance(client, request["models"][3], _acceptance(request["models"][3], request,
                                                                      package_manifest_sha256="0" * 64))
    elif break_it == "acceptance_runtime_missing":
        report = _acceptance(request["models"][2], request)
        report.pop("runtime")
        _rebind_acceptance(client, request["models"][2], report)
    elif break_it == "environment_lock":
        env = request["runtime"]["environment_manifest"]
        env.update(client.put(env["uri"], "91", json.dumps({"image_uri": IMAGE,
                                                            "requirements_lock_sha256": "0" * 64}).encode()))
        for model in request["models"]:
            _rebind_acceptance(client, model, _acceptance(model, request))
    elif break_it == "conflicting_member":
        model = request["models"][4]  # ipcch/6m: a shared member with different bytes
        manifest = json.loads(client.objects[_key(model["package_manifest"])])
        manifest["files"].append({"path": "model_package_manifest.json",
                                  **client.put("gs://ipcch-delivery/models/other.json", "4", b"{}")})
        model["package_manifest"].update(client.put(model["package_manifest"]["uri"], "92",
                                                    json.dumps(manifest).encode()))
        _rebind_acceptance(client, model, _acceptance(model, request))
    elif break_it == "retained_snapshot_differs":  # keep must equal the consumed history family exactly
        history = _history_panels()
        history["ipcch"] = history["ipcch"].replace(b"0.5", b"0.7", 1)
        ref = request["wfp"]["retained_snapshot"]
        ref.update(client.put(ref["uri"], "93", _snapshot(tmp_path, history, "wfp")))
    else:
        _rebind_prepared(client, request, lambda m: m.update(status="failed"))

    with pytest.raises((dj.AcceptanceError, dm.ReferenceIdentityError), match=REASONS[break_it]):
        _execute(tmp_path, client, request, image=image, score=lambda *a: pytest.fail("scored"))

    store = LocalObjectStore(tmp_path / "gcs")
    status = json.loads(store.read_text(f"{ROOT}/runs/oct2026-r1/run_status.json"))
    assert status["status"] == "failed"
    assert store.get_metadata(f"{ROOT}/dual-system/current.json") is None


REASONS = {
    "image": "job image", "asset_bytes": "history_panel sha256 mismatch", "acceptance": "does not accept",
    "package_path": "escapes its root", "prepared_status": "not a succeeded snapshot", "smoke_roster": "roster",
    "prepared_contract": "extraction contract", "prepared_geometry": "geometry", "prepared_family_missing": "lacks viirs",
    "schema_changed": "feature schema", "acceptance_schema": "does not accept", "acceptance_manifest": "does not accept",
    "acceptance_runtime_missing": "does not accept", "environment_lock": "environment manifest",
    "conflicting_member": "conflicting package member", "retained_snapshot_differs": "retained snapshot",
}


def _key(ref):
    bucket, _, name = ref["uri"].removeprefix("gs://").partition("/")
    return (bucket, name, str(ref["generation"]))


def _rebind_prepared(client, request, change):
    ref = request["prepared_snapshot"]["manifest"]
    manifest = json.loads(client.objects[_key(ref)])
    change(manifest)
    ref.update(client.put(ref["uri"], "95", json.dumps(manifest).encode()))


@pytest.mark.parametrize(("wfp", "acled"), [("keep", "keep"), ("keep", "refresh"), ("refresh", "keep"),
                                           ("refresh", "refresh")])
def test_all_four_source_choices_use_exactly_the_named_family(tmp_path, monkeypatch, wfp, acled):
    import tools.refresh_h5_inputs as refresh

    client, request = _world(tmp_path)
    for name, action in (("wfp", wfp), ("acled", acled)):
        if action == "refresh":
            snapshot = request[name].pop("retained_snapshot")
            request[name] = {"action": "refresh", "raw_upload": snapshot,
                             "converter_contract": request[name]["converter_contract"]}
    spec = dj.prepare_inputs(dm.validate_delivery_request(
        json.loads(json.dumps(request)), request_uri=REQUEST_REF["uri"], request_generation=REQUEST_REF["generation"]),
        dj.PinnedDownloader(client, tmp_path / "in"), tmp_path / "work", image_uri=IMAGE)
    monkeypatch.setattr(refresh, "wfp_aggregates", lambda path, cutoff: ({"converted": str(path)}, {}))
    monkeypatch.setattr(refresh, "conflict_aggregates", lambda path, cutoff: ({"converted": str(path)}, {}))

    frames = dj._source_frames(spec)

    for frame, action, name in zip(frames, (wfp, acled), ("wfp", "acled")):
        if action == "keep":
            assert frame is None  # validated retained family == consumed history family
        else:
            assert frame == {"converted": spec["sources"][name]["path"]}


def test_configured_namespace_mismatch_is_rejected_before_acquiring_the_run(tmp_path):
    client, request = _world(tmp_path)

    with pytest.raises(dm.DeliveryManifestError, match="namespace"):
        _execute(tmp_path, client, request, namespace="other-namespace")
    assert LocalObjectStore(tmp_path / "gcs").get_metadata(f"{ROOT}/runs/oct2026-r1/_RUN_ACQUIRED") is None


def test_failed_validation_never_moves_the_pointer(tmp_path):
    client, request = _world(tmp_path)

    def failed_package(out, spec, req, *, image_uri):
        return {"validation": "failed", "archive": None}

    with pytest.raises(dj.AcceptanceError, match="validation did not pass"):
        _execute(tmp_path, client, request, package=failed_package)
    assert LocalObjectStore(tmp_path / "gcs").get_metadata(f"{ROOT}/dual-system/current.json") is None


def test_local_reader_serves_only_verified_copies(tmp_path):
    path = tmp_path / "x.csv"
    path.write_bytes(b"a\n")
    reader = dj.LocalPinnedReader({"gs://b/x.csv#3": str(path)})
    assert reader.read_bytes("gs://b/x.csv", "3") == b"a\n" and reader.read_bytes("gs://b/x.csv", "4") is None


@pytest.mark.parametrize("existing", ["none", "same", "size", "crc", "other_error"])
def test_upload_tree_is_create_only_and_accepts_a_landed_retry_only_on_size_and_crc(tmp_path, existing):
    (tmp_path / "out").mkdir()
    path = tmp_path / "out/a.csv"
    path.write_text("x,y\n1,2\n")
    crc, size = dj._crc32c(path), path.stat().st_size

    class Blob:
        def __init__(self, name):
            self.name, self.generation = name, 5
            self.size, self.crc32c = (size + 1 if existing == "size" else size), ("bad" if existing == "crc" else crc)

        def upload_from_filename(self, local, **kwargs):
            assert kwargs["if_generation_match"] == 0 and kwargs["timeout"] == 600  # create-only, never overwrite
            if existing == "other_error":
                raise RuntimeError("network down")
            if existing != "none":
                raise dj.PreconditionFailed("object exists")

    class Bucket:
        def blob(self, name):
            return Blob(name)

        def get_blob(self, name):
            return Blob(name)

    class Client:
        def bucket(self, name):
            return Bucket()

    if existing in ("none", "same"):
        refs = dj.upload_tree(Client(), tmp_path / "out", "gs://b", "r1")
        assert refs["a.csv"]["uri"] == "gs://b/deliveries/r1/a.csv" and refs["a.csv"]["sha256"] == dj._stream_sha256(path)
    else:
        with pytest.raises((dj.PreconditionFailed, RuntimeError)):
            dj.upload_tree(Client(), tmp_path / "out", "gs://b", "r1")
