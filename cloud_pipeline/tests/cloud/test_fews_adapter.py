"""Task 10-29 R60 (Supervisor D1-D3): v2 FEWS NET generation / inference-only / combined through run_v2 on fake stores -
the existing preparation with the FEWS NET-only scope, the generation source binding (gen-only -> inf-only == gen+inf),
the FEWS-row keep projection, the shared scorer (same member bytes as the legacy route) and v2 publication."""

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from cloud.batch import remote_sources as rs
from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import fews_adapter as fa
from cloud.ipcch import publication as pub
from cloud.ipcch import run_v2
from cloud.orchestrator import delivery_job as dj
from cloud.orchestrator import delivery_manifest as dm
from cloud.orchestrator import delivery_request_v2 as v2
from cloud.orchestrator import prepare
from tests.cloud import fews_member_fixture as fmf
from tests.cloud import test_delivery_job as tj
from tests.cloud import test_prepare as tp

ROOT = "gs://prep-bucket"
ORIGIN = fmf.ORIGIN                                      # 2026-04: the content-valid FEWS member fixture's origin
IMAGE = "us-central1-docker.pkg.dev/p/r/img@sha256:" + "a" * 64
NOW = datetime(2026, 5, 20, tzinfo=timezone.utc)
PUBLISHED = {"evi": ["2026-03", "2026-04"], "fldas": ["2026-03", "2026-04"], "gosif_mean": ["2026-03", "2026-04"],
             "gosif_sd": ["2026-03", "2026-04"], "viirs": ["2026-03", "2026-04"]}


class Acquirer(tp.FakeAcquirer):
    def latest_published(self, family, *, floor_month, end_month):
        self.queries.append(("latest", family))
        found = [m for m in PUBLISHED[family] if floor_month <= m <= end_month]
        return (found[-1], f"{family}:{found[-1]}") if found else None

    def published_months(self, family, *, start_month, end_month):
        return {m: f"{family}:{m}" for m in PUBLISHED[family] if start_month <= m <= end_month}


class Reader:
    """Exact-generation reads over the local store (each object is written once)."""

    def __init__(self, store):
        self.store, self.reads = store, []

    def read_bytes(self, uri, generation):
        self.reads.append(uri)
        meta = self.store.get_metadata(uri)
        return self.store.read_bytes(uri) if meta and str(meta.generation) == str(generation) else None


class Client:
    """The GCS client surface PinnedDownloader uses, over the local store."""

    class NotFound(Exception):
        pass

    def __init__(self, reader):
        self.reader = reader

    def bucket(self, name):
        reader = self.reader

        class Bucket:
            def blob(self, blob, generation=None):
                class Blob:
                    def download_to_filename(self, path):
                        data = reader.read_bytes(f"gs://{name}/{blob}", str(generation))
                        if data is None:
                            raise tp.FakeNotFound(blob)
                        Path(path).write_bytes(data)
                return Blob()
        return Bucket()


def put(store, uri, data: bytes):
    meta = store.write_bytes(uri, data)
    return {"uri": uri, "generation": str(meta.generation), "sha256": hashlib.sha256(data).hexdigest()}


def prepare_request(store, prepare_id):
    systems = {}
    for system, polygons in tp.ROSTERS.items():
        geometry = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"admin_code": k}, "geometry": g} for k, g in polygons.items()]}
        systems[system] = {
            "geometry": put(store, f"gs://assets/{system}/geometry.geojson", json.dumps(geometry).encode()),
            "roster": put(store, f"gs://assets/{system}/roster.csv",
                          pd.DataFrame({"admin_code": list(polygons)}).to_csv(index=False).encode()),
            "history": {f: put(store, f"gs://assets/{system}/history/{f}.csv",
                               tp._history_csv(system, f, "2026-03", start="2026-01")) for f in rs.SYSTEM_FAMILIES[system]}}
    body = {"schema_version": prepare.PREPARE_SCHEMA_VERSION, "prepare_id": prepare_id, "origin_month": ORIGIN,
            "cutoff_utc": "2026-05-05T12:00:00Z", "extraction_contract_version": rs.EXTRACTION_CONTRACT_VERSION,
            "systems": systems, "operator": "ops@example.org"}
    return put(store, f"{ROOT}/prepare_requests/{prepare_id}/prepare_request.json", json.dumps(body).encode()), systems


def world(tmp_path, *, refresh=False):
    store = LocalObjectStore(tmp_path / "gcs")
    prep_ref, systems = prepare_request(store, "prep-2604")
    panel = tj._history_panels()["fewsnet"]
    history = put(store, "gs://assets/fewsnet/history_panel.csv", panel)
    (tmp_path / "panel.csv").write_bytes(panel)
    choices = {}
    for name in ("acled", "wfp"):
        contract = {"version": dm.RAW_CONVERTER_CONTRACT_VERSION, "sha256": "b" * 64}
        if refresh:
            choices[name] = {"action": "refresh", "raw_upload": put(store, f"gs://assets/raw/{name}.csv", b"raw " + name.encode()),
                             "converter_contract": contract}
        else:                                        # D2: the FEWS-row projection of the canonical retained stream
            projection = "".join(dj.retained_family_rows({"fewsnet": str(tmp_path / "panel.csv")}, name)).encode()
            choices[name] = {"action": "keep", "retained_snapshot": put(store, f"gs://assets/retained/{name}.csv",
                                                                        projection), "converter_contract": contract}
    env = put(store, "gs://assets/env.json", json.dumps({"image_uri": IMAGE,
                                                         "requirements_lock_sha256": dj.lock_sha256()}).encode())
    models = []
    for h in dm.HORIZONS_MONTHS:
        pid, schema = f"fewsnet-2604-{h}m", hashlib.sha256(f"schema {h}".encode()).hexdigest()
        files = [{"path": n, **put(store, f"gs://assets/models/fewsnet/{h}m/{n}", d)}
                 for n, d in fmf.local_package_members(pid, feature_schema_sha256=schema).items()]
        manifest = put(store, f"gs://assets/models/fewsnet/{h}m/package_manifest.json", json.dumps({
            "schema_version": dj.PACKAGE_MANIFEST_SCHEMA, "system": "fewsnet", "horizon_months": h, "package_id": pid,
            "files": files}).encode())
        model = {"system": "fewsnet", "horizon_months": h, "package_id": pid, "package_manifest": manifest,
                 "feature_schema_sha256": schema}
        model["acceptance_report"] = put(store, f"gs://assets/models/fewsnet/{h}m/acceptance.json", json.dumps(
            tj._acceptance(model, {"runtime": {"image_uri": IMAGE, "environment_manifest": env}})).encode())
        models.append(model)
    assets = {"fewsnet": {"geometry": systems["fewsnet"]["geometry"], "roster": systems["fewsnet"]["roster"],
                          "population": put(store, "gs://assets/fewsnet/population.csv", b"pop\n"),
                          "country_reference": put(store, "gs://assets/fewsnet/census.csv", b"ISO3\nSSD\n"),
                          "history_panel": history}}
    diagnostics = [{"system": "fewsnet", "horizon_months": h, "family": f, "status": "unavailable", "evidence": None,
                    "reason": "missing_evidence"} for h in dm.HORIZONS_MONTHS for f in dm.DIAGNOSTIC_FAMILIES["fewsnet"]]
    contract = lambda v: {"version": v, "sha256": "d" * 64}
    delivery = {"models": models, "assets": assets, "diagnostics": diagnostics,
                "contracts": {"feature": contract("feature-v1"), "fill": contract(dm.FILL_POLICY_VERSION),
                              "output": contract("september-v3-output-v1"), "diagnostic": contract("diag-v1")}}
    return {"store": store, "reader": Reader(store), "prep_ref": prep_ref, "choices": choices, "delivery": delivery,
            "env": env, "fixture": fmf.build(tmp_path / "fx"), "tmp": tmp_path}


def request(w, run_id, *, gen=True, inf=True, snapshot=None, expected="0"):
    fews = {}
    if gen:
        fews.update(acled=w["choices"]["acled"], wfp=w["choices"]["wfp"], prepare_request=w["prep_ref"])
    if inf and not gen:
        fews["prepared_snapshot"] = snapshot
    if inf:
        fews["delivery"] = w["delivery"]
    return {"schema_version": v2.SCHEMA_VERSION, "run_id": run_id, "mode": "real", "execution_month": ORIGIN,
            "operations": {"ipcch_generation": False, "ipcch_inference": False, "fewsnet_generation": gen,
                           "fewsnet_inference": inf},
            "ipcch": None, "fewsnet": fews, "publication": "current",
            "runtime": {"image_uri": IMAGE, "environment_manifest": w["env"]},
            "release": {"namespace": "prod", "expected_pointer_generation": expected},
            "operator": "ops@example.org", "prepared_at": "2026-05-20T05:00:00Z"}


def execute(w, data, *, scored=None):
    store, reader = w["store"], w["reader"]
    admission = Reader(store)                     # admission verifies EVERY nested ref (incl. unused IPCCH ones, D1)
    uri = f"gs://ops-bucket/requests/{data['run_id']}/run_manifest.json"
    admit = dict(request_uri=uri, request_generation="1", now_utc=NOW, production_namespace="prod",
                 smoke_namespace="smoke", current_ipcch_execution_month=None,
                 resolve=lambda u, g: (lambda b: None if b is None else hashlib.sha256(b).hexdigest())(admission.read_bytes(u, g)),
                 read=admission.read_bytes, trusted_prefixes={"real": ["gs://assets/", f"{ROOT}/"], "smoke": ["gs://x/"]},
                 batch_roots={"real": "gs://ipcch/real", "smoke": "gs://ipcch/smoke"})
    sources = []

    def score(spec_path, system, out):                    # the deliver(fewsnet) stand-in records its inputs
        spec = json.loads(Path(spec_path).read_text())
        sources.append({k: {"action": v["action"], "sha256": hashlib.sha256(Path(v["path"]).read_bytes()).hexdigest()}
                        for k, v in spec["sources"].items()})
        fmf.score_from(w["fixture"])(spec_path, system, out)
    acquirer = Acquirer(w["tmp"])
    fews = fa.runner(store=store, reader=reader, output_root=ROOT, work_root=w["tmp"] / "work", image_uri=IMAGE,
                     downloader_factory=lambda root: dj.PinnedDownloader(Client(reader), root), score=score,
                     acquirer_factory=lambda: acquirer)
    deployment = run_v2.Deployment(store=store, roots={"real": ROOT, "smoke": "gs://smoke-bucket/v2"})
    out = run_v2.run_request(data, admit_kwargs=admit, fewsnet_runner=fews, deployment=deployment)
    if scored is not None:
        scored.extend(sources)
    return out, acquirer


def member_bytes(store, publication_id):
    base = f"{ROOT}/deliveries/{publication_id}"
    manifest = json.loads(store.read_text(f"{base}/manifest.json"))
    return {e["path"]: e["sha256"] for e in manifest["files"] if e["path"].startswith(("scopes/", "fewsnet/", "inputs/fewsnet"))}


def test_combined_generation_and_inference_publishes_a_fews_member_from_its_own_snapshot(tmp_path):
    w = world(tmp_path)
    out, acquirer = execute(w, request(w, "fews-comb"))
    fews = out["systems"]["fewsnet"]
    assert out["status"] == "succeeded", fews
    snap = fews["result"]["generation"]["prepared_snapshot"]
    assert fews["result"]["inference"]["prepared_snapshot"] == snap                  # consumes exactly its own snapshot
    manifest = json.loads(w["store"].read_text(snap["manifest"]["uri"]))
    assert manifest["selected_systems"] == ["fewsnet"] and "gosif_sd" not in manifest["families"]
    assert w["reader"].reads and not [u for u in w["reader"].reads if "/ipcch/" in u]  # execution: no IPCCH read
    assert "gosif_sd" not in {f for f, _, _ in acquirer.acquired}
    rec = pub.read_current(w["store"], ROOT, "prod")["record"]
    assert rec["systems"]["fewsnet"]["published_by_run"] == "fews-comb-fewsnet" and rec["activation"] is None
    assert rec["systems"]["fewsnet"]["source"]["sources_binding"]["uri"].endswith("prep-2604/fewsnet_v2_sources.json")
    assert not w["store"].list(f"{ROOT}/locks/")


@pytest.mark.parametrize("refresh", [False, True])
def test_generation_only_then_inference_only_equals_combined(tmp_path, refresh):
    """D2: the refresh/keep choices made at generation reach the later inference-only scoring unchanged - the same
    scorer inputs and the same member bytes as the combined run on identical inputs."""
    combined = world(tmp_path / "a", refresh=refresh)
    seen_combined = []
    execute(combined, request(combined, "fews-x"), scored=seen_combined)
    split = world(tmp_path / "b", refresh=refresh)
    gen_out, _ = execute(split, request(split, "fews-gen", inf=False))
    assert gen_out["status"] == "succeeded" and "publication" not in gen_out["systems"]["fewsnet"]["result"]
    snapshot = gen_out["systems"]["fewsnet"]["result"]["generation"]["prepared_snapshot"]
    seen_split = []
    inf_out, acquirer = execute(split, request(split, "fews-x", gen=False, snapshot=snapshot), scored=seen_split)
    assert inf_out["status"] == "succeeded" and acquirer.acquired == []               # inference-only: no acquisition
    assert seen_split == seen_combined and seen_split[0]["acled"]["action"] == ("refresh" if refresh else "keep")
    assert member_bytes(split["store"], "fews-x-fewsnet") == member_bytes(combined["store"], "fews-x-fewsnet")


def test_inference_only_refuses_a_snapshot_without_its_generation_binding(tmp_path):
    w = world(tmp_path)
    gen_out, _ = execute(w, request(w, "fews-gen", inf=False))
    snapshot = gen_out["systems"]["fewsnet"]["result"]["generation"]["prepared_snapshot"]
    w["store"].delete(fa.sources_uri(ROOT, "prep-2604"), if_generation_match=w["store"].get_metadata(
        fa.sources_uri(ROOT, "prep-2604")).generation)
    out, _ = execute(w, request(w, "fews-inf", gen=False, snapshot=snapshot))
    fews = out["systems"]["fewsnet"]
    assert fews["status"] == "failed" and "no v2 FEWS NET generation source binding" in fews["reason"]
    assert pub.read_current(w["store"], ROOT, "prod")["generation"] == "0"


def test_keep_checks_the_fews_row_projection_against_the_pinned_history(tmp_path):
    """D2: keep verifies the actual pinned retained bytes against the pinned FEWS history (no IPCCH panel needed)."""
    w = world(tmp_path)
    data = request(w, "fews-keep")
    wrong = put(w["store"], "gs://assets/retained/acled-wrong.csv", b"system,admin_code,month\nfewsnet,1,2026-03\n")
    data["fewsnet"]["acled"] = {**data["fewsnet"]["acled"], "retained_snapshot": wrong}
    out, _ = execute(w, data)
    fews = out["systems"]["fewsnet"]
    assert fews["status"] == "failed" and "retained snapshot does not equal" in fews["reason"]
    assert fews["result"]["generation"]["prepared_snapshot"]                          # the snapshot stays reported


def test_v2_member_equals_the_legacy_single_system_route_on_the_same_inputs(tmp_path):
    """D3: the v2 adapter and the legacy single-system route share publish_scored_member: on identical inputs the
    published FEWS member files are byte-identical."""
    w = world(tmp_path)
    gen_out, _ = execute(w, request(w, "fews-gen", inf=False))
    snapshot = gen_out["systems"]["fewsnet"]["result"]["generation"]["prepared_snapshot"]
    execute(w, request(w, "fews-v2", gen=False, snapshot=snapshot))
    choices = fa.bound_choices(w["store"], ROOT, snapshot)
    legacy = request(w, "fews-v1", gen=False, snapshot=snapshot,
                     expected=pub.read_current(w["store"], ROOT, "prod")["generation"])
    legacy["request"] = {"uri": "gs://ops/requests/fews-v1/run_manifest.json", "generation": "1", "sha256": "a" * 64}
    shaped = fa.v1_request(legacy, snapshot, choices)
    work = tmp_path / "legacy-work"
    work.mkdir()
    dj.publish_scored_member(shaped, {"uri": "gs://ops/requests/fews-v1/run_manifest.json", "generation": "1",
                                      "sha256": "a" * 64}, json.dumps(shaped).encode(), "fewsnet", output_root=ROOT,
                             store=w["store"], downloader=dj.PinnedDownloader(Client(w["reader"]), work / "in"),
                             work=work, image_uri=IMAGE, score=fmf.score_from(w["fixture"]), publication="current",
                             expected_pointer_generation=shaped["release"]["expected_pointer_generation"],
                             source={"request_schema": "fewsnet-ipcch-delivery-request-v1"})
    assert member_bytes(w["store"], "fews-v1-fewsnet") == member_bytes(w["store"], "fews-v2-fewsnet")


from tests.cloud.test_ipcch_generation import package  # noqa: E402,F401 (fixture)


def activate(w, package):
    """The first real new-contract IPCCH publication to current under the same real root (activation set)."""
    from tests.cloud import test_ipcch_release_v2 as trv
    from tests.cloud.test_ipcch_delivery_member import scored_batch
    (w["tmp"] / "ipcch").mkdir()
    kw = trv.real_inputs(scored_batch(w["tmp"] / "ipcch", package))
    out = trv.publish(w["store"], kw, "ipcch-oct", pub.read_current(w["store"], ROOT, "prod")["generation"], root=ROOT,
                      ns="prod", tmp=w["tmp"])
    assert out["status"] == "published" and out["activation"]
    return pub.read_current(w["store"], ROOT, "prod")


def test_fews_current_inherits_the_new_contract_ipcch_member_and_carries_activation(tmp_path, package):
    w = world(tmp_path)
    before = activate(w, package)
    out, _ = execute(w, request(w, "fews-after", expected=before["generation"]))
    assert out["status"] == "succeeded", out["systems"]["fewsnet"]
    rec = pub.read_current(w["store"], ROOT, "prod")["record"]
    assert rec["activation"] == before["record"]["activation"]
    assert rec["systems"]["ipcch"]["published_by_run"] == "ipcch-oct-ipcch"           # inherited byte-for-byte
    assert rec["systems"]["fewsnet"]["origin_month"] == ORIGIN


def test_fews_candidate_never_moves_the_pointer(tmp_path):
    w = world(tmp_path)
    data = request(w, "fews-cand")
    data["publication"] = "candidate"
    out, _ = execute(w, data)
    assert out["status"] == "succeeded"
    assert out["systems"]["fewsnet"]["result"]["publication"]["status"] == "candidate_written"
    assert pub.read_current(w["store"], ROOT, "prod")["generation"] == "0"
    assert w["store"].get_metadata(f"{ROOT}/prod/candidates/fews-cand-fewsnet/candidate.json") is not None


def test_two_system_partial_failure_keeps_the_successful_fews_member(tmp_path):
    """IPCCH fails at its runtime while FEWS NET succeeds in the same run: partial_success, the FEWS member is
    published and the pointer carries it (R17)."""
    w = world(tmp_path)
    data = request(w, "both-sys")
    data["operations"].update(ipcch_inference=True)
    data["ipcch"] = {"model_combination": {"combination_id": "c", "envelope": put(w["store"], "gs://assets/env-c.json", b"{}")},
                     "feature_batch": {"batch_id": "b", "manifest": put(w["store"], "gs://ipcch/real/feature_batches/b/manifest.json", b"{}")},
                     "country_reference": put(w["store"], "gs://assets/cref.csv", b"ISO3\n")}
    store, reader = w["store"], w["reader"]
    uri = "gs://ops-bucket/requests/both-sys/run_manifest.json"
    admit = dict(request_uri=uri, request_generation="1", now_utc=NOW, production_namespace="prod",
                 smoke_namespace="smoke", current_ipcch_execution_month=None,
                 resolve=lambda u, g: (lambda b: None if b is None else hashlib.sha256(b).hexdigest())(reader.read_bytes(u, g)),
                 read=reader.read_bytes, trusted_prefixes={"real": ["gs://assets/", f"{ROOT}/", "gs://ipcch/"], "smoke": ["gs://x/"]},
                 batch_roots={"real": "gs://ipcch/real", "smoke": "gs://ipcch/smoke"})
    fews = fa.runner(store=store, reader=reader, output_root=ROOT, work_root=w["tmp"] / "work", image_uri=IMAGE,
                     downloader_factory=lambda root: dj.PinnedDownloader(Client(reader), root),
                     score=fmf.score_from(w["fixture"]), acquirer_factory=lambda: Acquirer(w["tmp"]))

    def broken(request):
        raise RuntimeError("IPCCH store unavailable")
    out = run_v2.run_request(data, admit_kwargs=admit, ipcch_context=broken, fewsnet_runner=fews,
                             deployment=run_v2.Deployment(store=store, roots={"real": ROOT, "smoke": "gs://smoke-bucket/v2"}))
    assert out["status"] == "partial_success" and out["systems"]["ipcch"]["status"] == "failed"
    assert pub.read_current(store, ROOT, "prod")["record"]["systems"]["fewsnet"]["published_by_run"] == "both-sys-fewsnet"
    assert not store.list(f"{ROOT}/locks/")
