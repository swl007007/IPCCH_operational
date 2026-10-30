"""Task 10-29: IPCCH feature generation end to end on a smoke fixture store (R5, R13, R32, R41, R43, R44, R48, R52,
R53, R62, R65) and inference from the produced batch through the runtime (R19, R36, R61)."""

import numpy as np
import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import batch_inference as bi
from cloud.ipcch import binding as bd
from cloud.ipcch import generation as gen
from cloud.ipcch import initial
from cloud.ipcch import retained
from cloud.ipcch.stores import StoreRoot, VersionedTable
from tests.cloud import ipcch_smoke_fixture as fx
from tests.cloud.ipcch_binding_fixtures import make_scoring_package, smoke_envelope
from tests.cloud.test_ipcch_assembly import ORDER, ROSTER
from tests.cloud.test_ipcch_initial import accept

SMOKE = "gs://b/ipcch-v2/smoke"


@pytest.fixture(scope="module")
def package(tmp_path_factory):
    return make_scoring_package(tmp_path_factory.mktemp("pkg") / "package", ORDER)


def setup(tmp_path, package):
    root_dir = tmp_path / "fixture-root"
    root_dir.mkdir()
    bundle, man = fx.build_bundle(root_dir)
    smoke_envelope(tmp_path / "env.json", package)
    b = bd.verify_combination(str(tmp_path / "env.json"), str(package), mode="smoke", fixture_root=str(root_dir))
    store, root = LocalObjectStore(tmp_path / "store"), StoreRoot("smoke", SMOKE)
    accept(store, root, man)
    initial.initialise(store, root, str(bundle), binding=b)
    return store, root, b, bundle


def generation(store, root, b, bundle, refs, request, tmp_path, providers=None):
    return gen.Generation(store=store, root=root, binding=b, bundle_dir=str(bundle), request=request,
                          read_ref=refs.read, batch_root=SMOKE, climate_providers=providers or fx.climate_providers(),
                          gpp_acquirer=fx.NoGpp(), nightlight_acquirer=fx.NoNightlight(), workdir=str(tmp_path))


def test_generation_writes_a_complete_batch_and_inference_scores_it(tmp_path, package):
    store, root, b, bundle = setup(tmp_path, package)
    refs = fx.Refs()
    req = fx.smoke_request(refs, inference=True)
    out = generation(store, root, b, bundle, refs, req, tmp_path).run()
    ref, batch_id = out["manifest_ref"], out["batch_id"]
    manifest, frames = bi.load_batch(store, ref, batch_id=batch_id, mode="smoke", execution_month="2027-03",
                                     binding=b, roster=[str(a) for a in ROSTER])
    assert manifest["feature_origin"] == "2027-01" and manifest["designation"] == "dummy"
    g = manifest["generation"]
    assert g["coverage_end"]["acled"] == "2027-01" and g["gaps"]["GPP_unpublished"] == ["2027-01"]
    assert g["gaps"]["nightlight"] == ["2027-01"]
    assert any("before O 2027-01" in w for w in g["warnings"])                  # snapshot older than O (R62)
    assert g["methods"]["WFP_Price"].startswith("research HDX") and g["methods"]["GPP_mean"].startswith("gosif-gpp-v3")
    assert manifest["retained_inputs"]["acled_agg_weekly"]["version"] == 1
    # climate saved the new month for every base, only roster areas (declared 1315 dropped)
    t = VersionedTable(store, root, "history__climate_month_cdd")
    jan = t.read({"admin_code": str, "month": str})[0].query("month == '2027-01'")
    assert sorted(jan["admin_code"]) == ["11", "12", "13"]
    # GPP/nightlight O unavailable -> NaN features, not a block (R65); ACLED A = O-1 present
    f2 = frames[2]
    assert f2["GPP_mean__value_at_origin"].isna().all()
    assert f2.filter(like="acled_agg_events_battles__value_at_origin_lag1").notna().all().all()
    assert list(f2["population_reference_period"]) == ["2026-04", "2026-04", "2025-01"]
    res = bi.score_batch(manifest, frames, str(package), b)
    assert set(res[14]["predictions"]["mode"]) == {"smoke"} and res[14]["predictions"]["target_period"].iloc[0] == "2028-03"


def test_origin_without_climate_source_blocks_after_saved_inputs(tmp_path, package):
    store, root, b, bundle = setup(tmp_path, package)
    refs = fx.Refs()
    req = fx.smoke_request(refs)
    import pandas as pd
    from cloud.ipcch import climate as cl
    from cloud.ipcch import climate_run
    unavailable = climate_run.ClimateProviders(lambda base: (lambda s, m: cl.SourceOutcome(s, "unavailable", detail="lag")),
                                               fx.climate_providers().seasonal)
    with pytest.raises(gen.GenerationFailure) as info:
        generation(store, root, b, bundle, refs, req, tmp_path, providers=unavailable).run()
    assert info.value.step == "climate" and "R13" in str(info.value)
    assert info.value.report["steps"]["acled"]["action"] == "refresh"              # saved inputs stay saved (R29/R41)
    _, records, _ = __import__("cloud.ipcch.acled", fromlist=["x"]).saved_weekly(VersionedTable(store, root, gen.ACLED_TABLE))
    assert len(records) == 1
    assert not list((tmp_path / "store").rglob("manifest.json"))                  # no batch


def test_real_keep_without_acled_history_is_refused(tmp_path, package):
    store, root, b, bundle = setup(tmp_path, package)
    refs = fx.Refs()
    req = fx.smoke_request(refs)
    req["ipcch"]["acled"] = {"action": "keep"}
    with pytest.raises(gen.GenerationFailure, match="needs saved regional-aggregate history"):
        generation(store, root, b, bundle, refs, req, tmp_path).run()
