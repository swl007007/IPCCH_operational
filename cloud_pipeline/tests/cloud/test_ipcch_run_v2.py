"""Task 10-29: v2 request execution without publication - admit before anything (R17), IPCCH generation/inference on
the smoke fixture (R5, R19, R36, R52), partial success across systems (R17)."""

import copy
import hashlib
from datetime import datetime, timezone

import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import binding as bd
from cloud.ipcch import initial
from cloud.ipcch import run_v2
from cloud.ipcch.stores import StoreRoot
from cloud.orchestrator import delivery_request_v2 as v2
from cloud.orchestrator.delivery_manifest import ReferenceIdentityError
from tests.cloud import ipcch_smoke_fixture as fx
from tests.cloud import test_delivery_request_v2 as tv2
from tests.cloud.ipcch_binding_fixtures import make_scoring_package, smoke_envelope
from tests.cloud.test_ipcch_assembly import ORDER, ROSTER
from tests.cloud.test_ipcch_initial import accept

SMOKE = "gs://ipcch-store/ipcch-v2/smoke"
REAL = "gs://ipcch-store/ipcch-v2/real"
NAMESPACES = dict(trusted_prefixes={"smoke": ["gs://ops-smoke/inputs/"], "real": ["gs://ops-bucket/objects/"]},
                  batch_roots={"smoke": SMOKE, "real": REAL})
SMOKE_ADMIT = dict(request_uri="gs://ops-smoke/requests/smoke-run-1/run_manifest.json", request_generation="1",
                   now_utc=datetime(2026, 10, 30, 6, tzinfo=timezone.utc), production_namespace="prod",
                   smoke_namespace="smoke", current_ipcch_execution_month=None, **NAMESPACES)


@pytest.fixture(scope="module")
def package(tmp_path_factory):
    return make_scoring_package(tmp_path_factory.mktemp("pkg") / "package", ORDER)


def smoke_world(tmp_path, package):
    root_dir = tmp_path / "fixture-root"
    root_dir.mkdir()
    bundle, man = fx.build_bundle(root_dir)
    smoke_envelope(tmp_path / "env.json", package)
    b = bd.verify_combination(str(tmp_path / "env.json"), str(package), mode="smoke", fixture_root=str(root_dir))
    store, root = LocalObjectStore(tmp_path / "store"), StoreRoot("smoke", SMOKE)
    accept(store, root, man)
    initial.initialise(store, root, str(bundle), binding=b)
    refs = fx.Refs()

    def context(request):
        return run_v2.IpcchContext(store=store, root=root, binding=b, package_root=str(package), bundle_dir=str(bundle),
                                   read_ref=refs.read, climate_providers=lambda w, o: fx.climate_providers(), gpp_acquirer=fx.NoGpp(),
                                   nightlight_acquirer=fx.NoNightlight(), workdir=str(tmp_path),
                                   roster=[str(a) for a in ROSTER])

    def resolve(uri, generation):
        if (uri, generation) in refs.objects:
            return hashlib.sha256(refs.objects[(uri, generation)]).hexdigest()
        meta = store.get_metadata(uri)
        return hashlib.sha256(store.read_text(uri).encode()).hexdigest() if meta and meta.generation == generation else None
    return store, refs, context, resolve


def raw(validated):
    """The submitted JSON of a validated request (validator-added keys removed)."""
    d = copy.deepcopy(validated)
    for k in ("derived", "request", "validation_level"):
        d.pop(k, None)
    return d


def test_smoke_generation_then_inference_only_from_the_named_batch(tmp_path, package):
    store, refs, context, resolve = smoke_world(tmp_path, package)
    req = raw(fx.smoke_request(refs, tmp_path / "env.json", inference=True))
    out = run_v2.run_request(req, admit_kwargs={**SMOKE_ADMIT, "resolve": resolve}, ipcch_context=context)
    assert out["status"] == "succeeded" and out["systems"]["ipcch"]["status"] == "succeeded"
    res = out["systems"]["ipcch"]["result"]
    batch_id, mref = res["batch"]["batch_id"], res["batch"]["manifest_ref"]
    assert res["inference"]["batch_id"] == batch_id and sorted(res["inference"]["horizons"]) == [2, 8, 14]
    assert set(res["inference"]["horizons"][2]["predictions"]["mode"]) == {"smoke"}
    # inference-only names that exact batch (R19); no IPCCH input refresh allowed
    inf = raw(fx.smoke_request(refs, tmp_path / "env.json", run_id="smoke-run-2"))
    inf["operations"] = {**inf["operations"], "ipcch_generation": False, "ipcch_inference": True}
    inf["ipcch"] = {"model_combination": inf["ipcch"]["model_combination"],
                    "country_reference": refs.put("country_reference.csv", fx.COUNTRY_REFERENCE),
                    "feature_batch": {"batch_id": batch_id, "manifest": mref}}
    out2 = run_v2.run_request(inf, admit_kwargs={**SMOKE_ADMIT, "request_uri": "gs://ops-smoke/requests/smoke-run-2/run_manifest.json",
                                                "resolve": resolve}, ipcch_context=context)
    r2 = out2["systems"]["ipcch"]["result"]
    assert out2["status"] == "succeeded" and "batch" not in r2 and r2["inference"]["batch_id"] == batch_id
    p1 = res["inference"]["horizons"][8]["predictions"]
    p2 = r2["inference"]["horizons"][8]["predictions"]
    assert p1.drop(columns=["batch_id"]).equals(p2.drop(columns=["batch_id"]))     # same batch -> same predictions


def test_generation_only_writes_a_batch_and_no_predictions(tmp_path, package):
    store, refs, context, resolve = smoke_world(tmp_path, package)
    req = raw(fx.smoke_request(refs, tmp_path / "env.json"))
    out = run_v2.run_request(req, admit_kwargs={**SMOKE_ADMIT, "resolve": resolve}, ipcch_context=context)
    res = out["systems"]["ipcch"]["result"]
    assert out["status"] == "succeeded" and "batch" in res and "inference" not in res


def test_invalid_mixed_request_executes_nothing(tmp_path):
    """Real mixed IPCCH generation+inference + FEWS NET inference with one wrong nested FEWS hash: rejected by admit;
    the IPCCH context factory, the FEWS runner and the store are never touched (R17)."""
    data = tv2.mixed_request()
    good = {(r["uri"], r["generation"]): r["sha256"] for _, r in v2.iter_object_refs(tv2.check(data))}
    data["fewsnet"]["delivery"]["models"][2]["acceptance_report"] = tv2.ref(77)
    calls = []
    store_dir = tmp_path / "store"
    kw = dict(request_uri=tv2.URI, request_generation="5", now_utc=tv2.NOW, production_namespace="prod",
              smoke_namespace="smoke", current_ipcch_execution_month="2026-09",
              resolve=lambda u, g: good.get((u, g), "0" * 64), **NAMESPACES)
    with pytest.raises(ReferenceIdentityError, match="fewsnet.delivery.models"):
        run_v2.run_request(data, admit_kwargs=kw, ipcch_context=lambda r: calls.append("ipcch"),
                           fewsnet_runner=lambda r: calls.append("fews"))
    assert calls == [] and not store_dir.exists()


def test_partial_success_when_one_system_fails(tmp_path):
    data = tv2.mixed_request()
    good = {(r["uri"], r["generation"]): r["sha256"] for _, r in v2.iter_object_refs(tv2.check(data))}
    kw = dict(request_uri=tv2.URI, request_generation="5", now_utc=tv2.NOW, production_namespace="prod",
              smoke_namespace="smoke", current_ipcch_execution_month="2026-09", resolve=lambda u, g: good.get((u, g)),
              **NAMESPACES)

    def broken_ipcch(request):
        raise RuntimeError("IPCCH store unavailable")
    out = run_v2.run_request(data, admit_kwargs=kw, ipcch_context=broken_ipcch, fewsnet_runner=lambda r: {"delivered": True})
    assert out["status"] == "partial"
    assert out["systems"]["ipcch"]["status"] == "failed" and "IPCCH store unavailable" in out["systems"]["ipcch"]["reason"]
    assert out["systems"]["fewsnet"] == {"status": "succeeded", "result": {"delivered": True}}



def test_misrouted_batch_and_refresh_refs_are_refused_before_any_resolve(tmp_path, package):
    """R48: a smoke request naming a real batch manifest or a real-namespace refresh file is refused LEXICALLY by admit;
    the resolver, the IPCCH context factory and the stores are never touched for the real URI."""
    store, refs, context, resolve = smoke_world(tmp_path, package)
    touched, calls = [], []

    def spy(uri, generation):
        touched.append(uri)
        return resolve(uri, generation)
    real_manifest = {"uri": f"{REAL}/feature_batches/ipcch-2027-03-smoke-run-1-abc/manifest.json", "generation": "1",
                     "sha256": "a" * 64}
    inf = raw(fx.smoke_request(refs, tmp_path / "env.json", run_id="smoke-run-3"))
    inf["operations"] = {**inf["operations"], "ipcch_generation": False, "ipcch_inference": True}
    inf["ipcch"] = {"model_combination": inf["ipcch"]["model_combination"],
                    "country_reference": refs.put("country_reference.csv", fx.COUNTRY_REFERENCE),
                    "feature_batch": {"batch_id": "ipcch-2027-03-smoke-run-1-abc", "manifest": real_manifest}}
    kw = {**SMOKE_ADMIT, "request_uri": "gs://ops-smoke/requests/smoke-run-3/run_manifest.json", "resolve": spy}
    with pytest.raises(v2.DeliveryRequestV2Error, match="outside the smoke batch namespace"):
        run_v2.run_request(inf, admit_kwargs=kw, ipcch_context=lambda r: calls.append(r))
    gen = raw(fx.smoke_request(refs, tmp_path / "env.json"))
    gen["ipcch"]["acled"]["file"] = {"uri": "gs://ops-bucket/objects/real-acled.csv", "generation": "3", "sha256": "b" * 64}
    with pytest.raises(v2.DeliveryRequestV2Error, match="outside the trusted smoke namespace"):
        run_v2.run_request(gen, admit_kwargs={**SMOKE_ADMIT, "resolve": spy}, ipcch_context=lambda r: calls.append(r))
    assert calls == [] and not [u for u in touched if "/real/" in u or "ops-bucket" in u]


def test_failed_inference_keeps_the_generated_batch_in_the_outcome(tmp_path, package, monkeypatch):
    store, refs, context, resolve = smoke_world(tmp_path, package)
    from cloud.ipcch import batch_inference as bi

    def broken(*a, **k):
        raise bi.InferenceOutputError("H2 phase2_worse_score nonfinite at areas ['12'] (1 rows) (R18)")
    monkeypatch.setattr(bi, "score_batch", broken)
    req = raw(fx.smoke_request(refs, tmp_path / "env.json", inference=True))
    out = run_v2.run_request(req, admit_kwargs={**SMOKE_ADMIT, "resolve": resolve}, ipcch_context=context)
    ipcch = out["systems"]["ipcch"]
    assert out["status"] == "failed" and ipcch["status"] == "failed" and ipcch["failed_operation"] == "inference"
    assert ipcch["result"]["generation"]["status"] == "succeeded"
    batch = ipcch["result"]["batch"]
    assert batch["batch_id"].startswith("ipcch-2027-03-smoke-run-1-") and batch["manifest_ref"]["uri"].endswith("manifest.json")
    assert "nonfinite" in ipcch["reason"]


def test_smoke_country_reference_must_be_a_fixture_object(tmp_path, package):
    store, refs, context, resolve = smoke_world(tmp_path, package)
    touched = []
    req = raw(fx.smoke_request(refs, tmp_path / "env.json", inference=True))
    req["ipcch"]["country_reference"] = {"uri": "gs://ops-bucket/objects/ipcch_population.csv", "generation": "4",
                                         "sha256": "c" * 64}                   # the real operational census
    with pytest.raises(v2.DeliveryRequestV2Error, match="ipcch.country_reference .* outside the trusted smoke namespace"):
        run_v2.run_request(req, admit_kwargs={**SMOKE_ADMIT, "resolve": lambda u, g: touched.append(u)},
                           ipcch_context=context)
    assert touched == []
