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


def fews_ready(tmp_path, client, request):
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
    ("origin", "feature origin"),
    ("manifest", "must name exactly"),
    ("archive", "archive must repeat"),
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
