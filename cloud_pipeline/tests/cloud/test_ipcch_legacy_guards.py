"""Task 10-29 CP4 Phase D: legacy v1 route after the new IPCCH contract (R37, R46, R50, R63, R66, FCC) on fake stores -
request-time and publication-time cutover rejection, current-bound inheritance, post-activation FEWS NET-only as a v2
member with activation carried, shared per-system locks, and promote/verify refusing new-contract candidates."""

import copy
import json
from types import SimpleNamespace as NS

import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import locks
from cloud.ipcch import publication as pub
from cloud.orchestrator import delivery_job as dj
from tests.cloud import test_delivery_job as tj
from tests.cloud import test_ipcch_release_v2 as trv
from tests.cloud.test_ipcch_delivery_member import scored_batch
from tests.cloud.test_ipcch_generation import package  # noqa: F401 (fixture)

NS_ = "prod"


def activated(tmp_path, package, monkeypatch, *, activate=True):
    """Store whose current release (ROOT/prod) holds a legacy FEWS NET member and - when ``activate`` - the first real
    new-contract IPCCH member (activation set)."""
    monkeypatch.setattr(trv, "PROD", tj.ROOT)
    store = LocalObjectStore(tmp_path / "gcs")
    trv.seed_legacy_fews(store, origin="2026-10")
    if activate:
        kw = trv.real_inputs(scored_batch(tmp_path, package))
        g = pub.read_current(store, tj.ROOT, NS_)["generation"]
        assert trv.publish(store, kw, "ipcch-oct", g, root=tj.ROOT, ns=NS_, tmp=tmp_path)["status"] == "published"
    return store


def v1(client, store, *, systems=("fewsnet",), inherit=None, publication="current"):
    _, request = client
    request = copy.deepcopy(request)
    request["release"] = {"namespace": NS_, "expected_pointer_generation": pub.read_current(store, tj.ROOT, NS_)["generation"]}
    if systems != ("fewsnet", "ipcch"):
        request["execution"] = {"remote_update": False, "inference_systems": list(systems), "prepare_request": None,
                                "inherit": inherit or {}, "publication": publication}
    return request


def member_source(client, store, system="ipcch", origin=None, archive=None):
    """An inherit source naming exactly the current member (its pinned manifest bytes registered with the client)."""
    m = pub.members(pub.read_current(store, tj.ROOT, NS_)["record"])[system]
    ref = m["delivery"]["manifest"]
    client.put(ref["uri"], ref["generation"], store.read_bytes(ref["uri"]))
    return {"source_delivery_id": m.get("published_by_run", "x"), "origin_month": origin or m.get("feature_origin"),
            "manifest": dict(ref), "archive": dict(archive or ref)}


def fews_ready(tmp_path, client, request, scoped=False):
    """Rebind a v1 request to the content-valid FEWS member fixture (origin 2026-04): its prepared snapshot origin and
    FEWS packages in the local-package shape (model, training report, local_model_manifest, checksums); returns the
    deliver(fewsnet)-equivalent ``score``."""
    from tests.cloud import fews_member_fixture as fmf
    fixture = fmf.build(tmp_path / "fews-fixture")
    fake, request = client[0], request
    request["origin_month"] = fmf.ORIGIN
    snap = request["prepared_snapshot"]
    key = tuple(snap["manifest"]["uri"].removeprefix("gs://").split("/", 1)) + (snap["manifest"]["generation"],)
    body = json.loads(fake.objects[key])
    body["origin_month"] = fmf.ORIGIN
    snap["origin_month"] = fmf.ORIGIN
    if scoped:                                            # a FEWS NET-scoped preparation (post-activation remote run)
        body["selected_systems"] = ["fewsnet"]
        body["families"] = {f: {**v, "outputs": {"fewsnet": v["outputs"]["fewsnet"]}}
                            for f, v in body["families"].items() if "fewsnet" in v.get("outputs", {})}
    snap["manifest"].update(fake.put(snap["manifest"]["uri"], "77", json.dumps(body).encode()))
    for model in request["models"]:
        if model["system"] != "fewsnet":
            continue
        h, pid = model["horizon_months"], model["package_id"]
        members = fmf.local_package_members(pid, feature_schema_sha256=model["feature_schema_sha256"])
        files = [{"path": path, **fake.put(f"gs://ipcch-delivery/models/fewsnet/{h}m/v/{path}", "4", data)}
                 for path, data in members.items()]
        model["package_manifest"].update(fake.put(model["package_manifest"]["uri"], "5", json.dumps({
            "schema_version": dj.PACKAGE_MANIFEST_SCHEMA, "system": "fewsnet", "horizon_months": h,
            "package_id": pid, "files": files}).encode()))
        tj._rebind_acceptance(fake, model, tj._acceptance(model, request))
    return fixture


def run(tmp_path, client, request, store, score=None):
    return tj._execute(tmp_path, client[0], request, namespace=NS_, store=store, score=score)


@pytest.mark.parametrize("systems", [("fewsnet", "ipcch"), ("ipcch",)])
def test_after_activation_v1_requests_including_ipcch_are_rejected_before_work(tmp_path, package, monkeypatch, systems):
    store = activated(tmp_path, package, monkeypatch)
    client = tj._world(tmp_path)
    inherit = {"fewsnet": member_source(client[0], store, "fewsnet", origin="2026-10")} if systems == ("ipcch",) else None
    before = pub.read_current(store, tj.ROOT, NS_)["generation"]
    with pytest.raises(dj.AcceptanceError, match="submit IPCCH through the v2 manifest"):
        run(tmp_path, client, v1(client, store, systems=systems, inherit=inherit), store,
            score=lambda *a: pytest.fail("scored"))
    assert pub.read_current(store, tj.ROOT, NS_)["generation"] == before
    assert not store.list(f"{tj.ROOT}/locks/")                                      # rejected before any lock


def test_cutover_during_a_legacy_run_is_refused_at_publication(tmp_path, package, monkeypatch):
    """A both-system v1 run admitted before activation; activation lands while it scores -> the publication-time
    recheck refuses it and new IPCCH current stays (R37)."""
    store = activated(tmp_path, package, monkeypatch, activate=False)
    client = tj._world(tmp_path)
    request = v1(client, store, systems=("fewsnet", "ipcch"))
    kw = trv.real_inputs(scored_batch(tmp_path, package))
    fired = []

    def score(spec_path, system, out):
        (out / "reports").mkdir(parents=True, exist_ok=True)
        if not fired:                                    # the first real new-contract publication lands mid-run
            g = pub.read_current(store, tj.ROOT, NS_)["generation"]
            fired.append(trv.publish(store, kw, "ipcch-cutover", g, root=tj.ROOT, ns=NS_, tmp=tmp_path))
    with pytest.raises(dj.AcceptanceError, match="v2 manifest"):
        run(tmp_path, client, request, store, score=score)
    rec = pub.read_current(store, tj.ROOT, NS_)["record"]
    assert rec["run_id"] == "ipcch-cutover-ipcch" and rec["activation"]["activated_by_run"] == "ipcch-cutover-ipcch"
    assert not store.list(f"{tj.ROOT}/locks/")                                      # released


def test_post_activation_fews_only_publishes_a_v2_member_inheriting_the_new_ipcch_member(tmp_path, package, monkeypatch):
    store = activated(tmp_path, package, monkeypatch)
    client = tj._world(tmp_path)
    before = pub.read_current(store, tj.ROOT, NS_)
    from tests.cloud import fews_member_fixture as fmf
    request = v1(client, store, inherit={"ipcch": member_source(client[0], store)})
    fixture = fews_ready(tmp_path, client, request)
    calls = []
    status, _, _ = run(tmp_path, client, request, store, score=fmf.score_from(fixture, calls))
    assert status["status"] == "succeeded" and calls == ["fewsnet"]
    rec = pub.read_current(store, tj.ROOT, NS_)["record"]
    assert rec["schema"] == pub.RELEASE_SCHEMA and rec["run_id"] == "oct2026-r1-fewsnet"
    assert rec["previous"]["pointer_generation"] == before["generation"]
    assert rec["activation"] == before["record"]["activation"]                        # carried, never cleared (R46)
    ip = rec["systems"]["ipcch"]
    assert ip["contract"] == pub.IPCCH_CONTRACT and ip["published_by_run"] == "ipcch-oct-ipcch"   # inherited unchanged
    fw = rec["systems"]["fewsnet"]
    assert fw["origin_month"] == fmf.ORIGIN and fw["published_by_run"] == "oct2026-r1-fewsnet"
    assert sorted({p.split("/")[0] for p in fw["model_package"]}) == ["0m", "12m", "6m"]   # exact scored packages
    assert not list((tmp_path).glob("work-*/packages/ipcch/*"))                      # unused legacy IPCCH package
    assert not store.list(f"{tj.ROOT}/locks/")


@pytest.mark.parametrize("change,message", [
    ("origin", "own origin 2026-08"),
    ("manifest", "must name exactly"),
    ("archive", "delivery manifest"),
])
def test_post_activation_inheritance_must_name_the_current_member(tmp_path, package, monkeypatch, change, message):
    store = activated(tmp_path, package, monkeypatch)
    client = tj._world(tmp_path)
    source = member_source(client[0], store)
    if change == "origin":
        source["origin_month"] = "2026-10"                       # the outer FEWS origin, not the member's own O
    elif change == "manifest":
        source["manifest"] = {**source["manifest"], "generation": "999"}
    else:
        source["archive"] = {"uri": "gs://ipcch-requests/other.tar.gz", "generation": "1", "sha256": "e" * 64}
    with pytest.raises(dj.AcceptanceError, match=message):
        run(tmp_path, client, v1(client, store, inherit={"ipcch": source}), store, score=lambda *a: pytest.fail("scored"))


def test_pre_activation_legacy_inheritance_still_binds_to_the_current_release(tmp_path, package, monkeypatch):
    store = activated(tmp_path, package, monkeypatch, activate=False)               # legacy v1 record, FEWS only
    client = tj._world(tmp_path)
    with pytest.raises(dj.AcceptanceError, match="must name exactly the ipcch member"):
        run(tmp_path, client, v1(client, store, inherit={"ipcch": {
            "source_delivery_id": "elsewhere", "origin_month": "2026-10",
            "manifest": {"uri": "gs://src/manifest.json", "generation": "1", "sha256": "a" * 64},
            "archive": {"uri": "gs://src/a.tar.gz", "generation": "1", "sha256": "b" * 64}}}), store,
            score=lambda *a: pytest.fail("scored"))


def test_v1_runs_share_the_per_system_locks(tmp_path, package, monkeypatch):
    store = activated(tmp_path, package, monkeypatch)
    client = tj._world(tmp_path)
    held = locks.acquire(store, tj.ROOT, ["fewsnet"], "v2-run")
    with pytest.raises(locks.LockConflict, match="v2-run"):
        run(tmp_path, client, v1(client, store, inherit={"ipcch": member_source(client[0], store)}), store,
            score=lambda *a: pytest.fail("scored"))
    assert locks.release(store, held) == []


class FakeCloud:
    def __init__(self, store):
        self.store = store

    def latest(self, uri):
        meta = self.store.get_metadata(uri)
        return (json.loads(self.store.read_text(uri)), {"generation": meta.generation}) if meta else None


def test_promote_and_verify_reject_new_contract_candidates_and_bind_legacy_candidates(tmp_path, package, monkeypatch):
    import pipeline as p
    store = activated(tmp_path, package, monkeypatch)
    cloud, cfg = FakeCloud(store), {"bucket": tj.ROOT.removeprefix("gs://"), "namespace": NS_}
    (tmp_path / "cand").mkdir()
    kw = trv.real_inputs(scored_batch(tmp_path / "cand", package))
    g = pub.read_current(store, tj.ROOT, NS_)["generation"]
    assert trv.publish(store, kw, "cand", g, publication="candidate", root=tj.ROOT, ns=NS_, tmp=tmp_path)["status"] == \
        "candidate_written"
    with pytest.raises(ValueError, match="new-contract"):
        p.reject_new_contract_candidate(cfg, cloud, "cand")
    p.reject_new_contract_candidate(cfg, cloud, "legacy-run", {"run_id": "legacy-run"})       # legacy: allowed
    with pytest.raises(ValueError, match="v2 manifest"):                                     # IPCCH after activation
        p.bind_promotion(cfg, cloud, {"request_body": {}}, {"run_id": "legacy-run"})
    with pytest.raises(ValueError, match="not the current release's member"):
        p.bind_promotion(cfg, cloud, {"request_body": {"execution": {"inherit": {"ipcch": {
            "manifest": {"uri": "gs://x", "generation": "1", "sha256": "a" * 64}}}}}},
            {"execution": {"scored_systems": ["fewsnet"]}})
    p.bind_promotion(cfg, cloud, {"request_body": {"execution": {"inherit": {"ipcch": member_source(
        tj.FakeClient(), store)}}}}, {"execution": {"scored_systems": ["fewsnet"]}})          # bound: accepted


# --- finding 3: valid pre-activation v2-record state; finding 4: consistent legacy pointer read ---------------------


def ipcch_ready(client, request):
    """Rebind the v1 request's IPCCH packages to the legacy IPCCH package layout (shared root, every scope file; the
    scope feature contracts keep the request's feature schema)."""
    from tests.cloud import fews_member_fixture as fmf
    fake = client[0]
    members = fmf.ipcch_package_members("legacy-ipcch")
    for model in request["models"]:
        if model["system"] == "ipcch":
            members[f"scope_{model['horizon_months']}m/feature_contract.csv"] = (
                f"feature_name,source_column\nx{model['horizon_months']},x\n".encode())
    for model in request["models"]:
        if model["system"] != "ipcch":
            continue
        files = [{"path": path, **fake.put(f"gs://ipcch-delivery/models/ipcch/legacy/{path}", "4", data)}
                 for path, data in members.items()]
        model["package_manifest"].update(fake.put(model["package_manifest"]["uri"], "5", json.dumps({
            "schema_version": dj.PACKAGE_MANIFEST_SCHEMA, "system": "ipcch", "horizon_months": model["horizon_months"],
            "package_id": model["package_id"], "files": files}).encode()))
        tj._rebind_acceptance(fake, model, tj._acceptance(model, request))


def preactivation_v2_fews(tmp_path, monkeypatch):
    """A pre-activation v2 record: the first v2 publication was FEWS NET-only (legacy-format member), activation None."""
    from cloud.ipcch import release_v2 as rv
    from tests.cloud import fews_member_fixture as fmf
    monkeypatch.setattr(trv, "PROD", tj.ROOT)
    store = LocalObjectStore(tmp_path / "gcs")
    trv.seed_legacy_fews(store, origin=fmf.ORIGIN)
    fixture = fmf.build(tmp_path / "fx")
    g = pub.read_current(store, tj.ROOT, NS_)["generation"]
    out = rv.publish_member_run(store, tj.ROOT, system="fewsnet", namespace=NS_, run_id="fews-v2", mode="real",
                                publication="current", expected_pointer_generation=g, request_ref=trv.REQ,
                                write_member=lambda o: __import__("cloud.ipcch.fews_v2", fromlist=["x"]).write_member(
                                    o, score=fmf.score_from(fixture), spec_path=tmp_path / "s.json",
                                    origin=fmf.ORIGIN, packages=fixture["packages"], mode="real"),
                                workdir=str(tmp_path), now=trv.NOW)
    assert out["status"] == "published"
    rec = pub.read_current(store, tj.ROOT, NS_)["record"]
    assert rec["schema"] == pub.RELEASE_SCHEMA and rec["activation"] is None
    return store


def test_preactivation_legacy_ipcch_run_inherits_the_v2_stored_fews_member(tmp_path, package, monkeypatch):
    """Finding 3: before activation a v1 IPCCH-only run stays available against a v2 record: it inherits the
    v2-stored FEWS member by exact identity (archive repeats its manifest) and publishes a legacy-format IPCCH member;
    nothing is activated."""
    from tests.cloud import fews_member_fixture as fmf
    store = preactivation_v2_fews(tmp_path, monkeypatch)
    client = tj._world(tmp_path)
    fews_ready(tmp_path, client, client[1])                          # origin 2026-04 snapshot
    source = member_source(client[0], store, "fewsnet", origin=fmf.ORIGIN)
    request = v1(client, store, systems=("ipcch",), inherit={"fewsnet": source})
    request["origin_month"] = fmf.ORIGIN
    ipcch_ready(client, request)
    ipcch = fmf.build(tmp_path / "fx", system="ipcch")
    calls = []
    status, _, _ = run(tmp_path, client, request, store, score=fmf.score_from(ipcch, calls, system="ipcch"))
    assert status["status"] == "succeeded" and calls == ["ipcch"]
    rec = pub.read_current(store, tj.ROOT, NS_)["record"]
    assert rec["systems"]["ipcch"]["contract"] == "ipcch-legacy-scoring" and rec["activation"] is None
    assert rec["systems"]["fewsnet"]["published_by_run"] == "fews-v2-fewsnet"           # inherited unchanged
    assert not list(tmp_path.glob("work-*/packages/fewsnet/*"))                       # unused FEWS packages untouched
    bad = dict(source, archive={"uri": "gs://src/a.tar.gz", "generation": "1", "sha256": "b" * 64})
    with pytest.raises(dj.AcceptanceError, match="repeat the manifest ref"):
        run(tmp_path, client, v1(client, store, systems=("ipcch",), inherit={"fewsnet": bad}), store,
            score=lambda *a: pytest.fail("scored"))


def legacy_pointer(store, record=None):
    """A pre-generation legacy pointer (no release_record_generation)."""
    uri = f"{tj.ROOT}/{NS_}/releases/old/release.json"
    if record is not None:
        store.write_text(uri, json.dumps(record))
    store.write_text(pub.pointer_uri(tj.ROOT, NS_), json.dumps({"run_id": "old", "release_record": uri}))
    return uri


def test_legacy_pointer_is_read_consistently_with_integrity_binding(tmp_path):
    """Finding 4: a pointer without release_record_generation never crashes the guards; its legacy record is read
    stably; a v2/activated record named without its generation is refused (activation is never trusted unpinned);
    a missing record is refused for publication and seen as 'no record' by the gate-only callers."""
    store = LocalObjectStore(tmp_path / "gcs")
    legacy_pointer(store, {"run_id": "old", "origin_month": "2026-10", "manifest": {"uri": "gs://x/m.json"},
                           "execution": {"scored_systems": ["fewsnet", "ipcch"], "inherited_systems": []}})
    snap = pub.read_current(store, tj.ROOT, NS_)
    assert snap["legacy_pointer"] and pub.members(snap["record"]).keys() == {"fewsnet", "ipcch"}
    store2 = LocalObjectStore(tmp_path / "gcs2")
    legacy_pointer(store2, {"schema": pub.RELEASE_SCHEMA, "activation": {"contract": pub.IPCCH_CONTRACT}, "systems": {}})
    with pytest.raises(pub.PublicationRefused, match="named without its generation"):
        pub.read_current(store2, tj.ROOT, NS_, allow_missing_legacy_record=True)
    store3 = LocalObjectStore(tmp_path / "gcs3")
    legacy_pointer(store3)                                                         # the record does not exist
    with pytest.raises(pub.PublicationRefused, match="does not exist"):
        pub.read_current(store3, tj.ROOT, NS_)
    assert pub.read_current(store3, tj.ROOT, NS_, allow_missing_legacy_record=True)["record"] is None


def test_v1_runs_against_a_legacy_pointer_without_generation(tmp_path):
    """Finding 4 through execute: no crash; a both-system v1 run publishes as before; an inheriting run is rejected
    because the unpinned/missing record proves no member."""
    store = LocalObjectStore(tmp_path / "gcs")
    legacy_pointer(store)
    client = tj._world(tmp_path)
    request = copy.deepcopy(client[1])
    request["release"] = {"namespace": NS_, "expected_pointer_generation": store.get_metadata(
        pub.pointer_uri(tj.ROOT, NS_)).generation}
    status, calls, _ = run(tmp_path, client, request, store)
    assert status["status"] == "succeeded" and calls["score"] == ["ipcch", "fewsnet"]
    inheriting = v1(client, store, inherit={"ipcch": {
        "source_delivery_id": "old", "origin_month": "2026-10",
        "manifest": {"uri": "gs://old-bucket/m.json", "generation": "1", "sha256": "a" * 64},
        "archive": {"uri": "gs://old-bucket/a.tar.gz", "generation": "1", "sha256": "b" * 64}}})
    with pytest.raises(dj.AcceptanceError, match="must name exactly"):
        run(tmp_path, client, inheriting, store, score=lambda *a: pytest.fail("scored"))


def test_post_activation_fews_only_delivery_from_a_fews_scoped_snapshot_adopts_its_admission_lock(
        tmp_path, package, monkeypatch):
    """The resolved legacy FEWS NET-only run after activation: its FEWS-scoped snapshot serves FEWS NET (no IPCCH
    outputs required), the FEWS lock it holds since admission is adopted (never acquired twice) and released."""
    from tests.cloud import fews_member_fixture as fmf
    store = activated(tmp_path, package, monkeypatch)
    client = tj._world(tmp_path)
    request = v1(client, store, inherit={"ipcch": member_source(client[0], store)})
    fixture = fews_ready(tmp_path, client, request, scoped=True)
    held = locks.acquire(store, tj.ROOT, ["fewsnet"], request["run_id"])          # taken at admission
    status, _, _ = run(tmp_path, client, request, store, score=fmf.score_from(fixture))
    assert status["status"] == "succeeded" and not store.list(f"{tj.ROOT}/locks/")
    assert held and pub.read_current(store, tj.ROOT, NS_)["record"]["systems"]["fewsnet"]["origin_month"] == fmf.ORIGIN
    scored_ipcch = v1(client, store, systems=("fewsnet", "ipcch"))
    scored_ipcch["prepared_snapshot"] = request["prepared_snapshot"]
    scored_ipcch["origin_month"] = fmf.ORIGIN
    with pytest.raises(dj.AcceptanceError):                                       # activated: IPCCH never scored
        run(tmp_path, client, scored_ipcch, store, score=lambda *a: pytest.fail("scored"))
