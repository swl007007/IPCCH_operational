"""Task 10-29: IPCCH feature generation end to end on a smoke fixture store (R5, R13, R32, R33, R41, R43, R44, R45, R48,
R52, R53, R59, R62, R65) and inference from the produced batch through the runtime (R19, R36, R61)."""

import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import acled as ac
from cloud.ipcch import batch_inference as bi
from cloud.ipcch import binding as bd
from cloud.ipcch import climate as cl
from cloud.ipcch import climate_run
from cloud.ipcch import generation as gen
from cloud.ipcch import initial
from cloud.ipcch.stores import AcceptanceManifest, StoreError, StoreRoot, VersionedTable
from tests.cloud import ipcch_smoke_fixture as fx
from tests.cloud.ipcch_binding_fixtures import make_scoring_package, smoke_envelope
from tests.cloud.test_ipcch_assembly import ORDER, ROSTER
from tests.cloud.test_ipcch_initial import accept

SMOKE = "gs://ipcch-store/ipcch-v2/smoke"


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
                          read_ref=refs.read, batch_root=SMOKE, climate_providers=lambda w, o: providers or fx.climate_providers(),
                          gpp_acquirer=fx.NoGpp(), nightlight_acquirer=fx.NoNightlight(), workdir=str(tmp_path))


def files(path):
    return sorted(str(p) for p in path.rglob("*") if p.is_file())


def runtime_records(store, root):
    rec = AcceptanceManifest(store, root).records()
    return rec[rec["kind"] == "runtime"]


def recorded(rt, table):
    """Runtime records of one table's saved versions (name = the immutable version content path)."""
    return rt[rt["name"].str.contains(f"/{table}/versions/", regex=False)]


def test_generation_writes_a_complete_batch_and_inference_scores_it(tmp_path, package):
    store, root, b, bundle = setup(tmp_path, package)
    refs = fx.Refs()
    req = fx.smoke_request(refs, tmp_path / "env.json", inference=True)
    out = generation(store, root, b, bundle, refs, req, tmp_path).run()
    ref, batch_id = out["manifest_ref"], out["batch_id"]
    manifest, frames = bi.load_batch(store, ref, batch_root=SMOKE, batch_id=batch_id, mode="smoke",
                                     execution_month="2027-03", binding=b, roster=[str(a) for a in ROSTER])
    assert manifest["feature_origin"] == "2027-01" and manifest["designation"] == "dummy"
    g = manifest["generation"]
    assert g["coverage_end"]["acled"] == "2027-01" and g["gaps"]["GPP_unpublished"] == ["2027-01"]
    assert g["gaps"]["nightlight"] == ["2027-01"]
    assert any("before O 2027-01" in w and "snapshot" in w for w in g["warnings"])           # R62
    assert any(w.startswith("WFP_Price coverage ends 2026-12, before O 2027-01") for w in g["warnings"])   # R65
    assert any(w.startswith("GPP_mean coverage ends") for w in g["warnings"])
    assert g["methods"]["WFP_Price"].startswith("research HDX") and g["methods"]["GPP_mean"].startswith("gosif-gpp-v3")
    assert manifest["retained_inputs"]["acled_agg_weekly"]["version"] == 1
    t = VersionedTable(store, root, "history__climate_month_cdd")
    jan = t.read({"admin_code": str, "month": str})[0].query("month == '2027-01'")
    assert sorted(jan["admin_code"]) == ["11", "12", "13"]                             # declared 1315 dropped
    f2 = frames[2]
    assert f2["GPP_mean__value_at_origin"].isna().all()
    assert f2.filter(like="acled_agg_events_battles__value_at_origin_lag1").notna().all().all()
    assert list(f2["population_reference_period"]) == ["2026-04", "2026-04", "2025-01"]
    res = bi.score_batch(manifest, frames, str(package), b)
    assert set(res[14]["predictions"]["mode"]) == {"smoke"} and res[14]["predictions"]["target_period"].iloc[0] == "2028-03"
    # R45: every saved update has a runtime acceptance record bound to its HEAD content
    rt = runtime_records(store, root)
    for table in ("acled_agg_weekly", "history__climate_month_cdd", "gpp_availability_ledger"):
        assert not recorded(rt, table).empty
    head = VersionedTable(store, root, "history__climate_month_cdd").head()[0]
    assert (head["content"], head["sha256"]) in set(zip(rt["name"], rt["sha256"]))     # the saved version file itself
    assert set(rt["acceptor"]) == {"ipcch-runtime:smoke-run-1"}


def test_request_selection_must_match_the_binding_before_any_write(tmp_path, package):
    store, root, b, bundle = setup(tmp_path, package)
    refs = fx.Refs()
    before = files(tmp_path / "store")
    other = tmp_path / "other-env.json"
    smoke_envelope(other, package, version=2)                                          # same package, other envelope
    for req in (fx.smoke_request(refs, other), fx.smoke_request(refs, tmp_path / "env.json", combination_id="ipcch-other")):
        with pytest.raises(StoreError, match="nothing was executed"):
            generation(store, root, b, bundle, refs, req, tmp_path).run()
    assert files(tmp_path / "store") == before                                         # zero writes


def test_future_completed_seasons_come_from_the_delivered_calendar(tmp_path, package):
    """The delivered windows end with 2026 (as the accepted handoff); O = 2027-07 completes 2027-s1: its window is derived
    from the delivered calendar, saved by the climate update and used by assembly from the same frame (R33)."""
    store, root, b, bundle = setup(tmp_path, package)
    refs = fx.Refs()
    req = fx.smoke_request(refs, tmp_path / "env.json", execution_month="2027-09", inference=True)
    g = generation(store, root, b, bundle, refs, req, tmp_path)
    out = g.run()
    ext = g.report["season_windows_extension"]
    assert ext == {"delivered_through": 2026, "derived_years": [2027], "derived_rows": 6}
    gs = VersionedTable(store, root, "history__climate_gs_cdd").read({"admin_code": str, "season": str})[0]
    saved = gs[gs["season_year"] == 2027]
    assert sorted(zip(saved["admin_code"], saved["season"])) == [("11", "s1"), ("12", "s1"), ("13", "s1")]
    assert set(saved["gs_end_date_exclusive"]) == {"2027-07-01"}                         # 2027-s2 not complete by O
    manifest, frames = bi.load_batch(store, out["manifest_ref"], batch_root=SMOKE, batch_id=out["batch_id"], mode="smoke",
                                     execution_month="2027-09", binding=b, roster=[str(a) for a in ROSTER])
    assert (frames[2]["gs_last1__cdd_gs_ensmean__at_origin"] == 0.5).all()              # the derived 2027-s1 season


def test_calendar_that_does_not_reproduce_delivered_windows_is_refused(tmp_path, package):
    store, root, b, bundle = setup(tmp_path, package)
    t = VersionedTable(store, root, "fixed__season_calendar")
    frame, head, generation_ = t.read({"admin_code": str})
    t.commit(frame.assign(s1_eos_day=29), {"action": "test-tamper"}, expected_generation=generation_)
    refs = fx.Refs()
    with pytest.raises(gen.GenerationFailure, match="does not reproduce the delivered 2026 windows"):
        generation(store, root, b, bundle, refs, fx.smoke_request(refs, tmp_path / "env.json", execution_month="2027-09"),
                   tmp_path).run()


def test_origin_without_climate_source_blocks_after_saved_inputs_with_runtime_records(tmp_path, package):
    store, root, b, bundle = setup(tmp_path, package)
    refs = fx.Refs()
    req = fx.smoke_request(refs, tmp_path / "env.json")
    unavailable = climate_run.ClimateProviders(lambda base: (lambda s, m: cl.SourceOutcome(s, "unavailable", detail="lag")),
                                               fx.climate_providers().seasonal)
    with pytest.raises(gen.GenerationFailure) as info:
        generation(store, root, b, bundle, refs, req, tmp_path, providers=unavailable).run()
    assert info.value.step == "climate" and "R13" in str(info.value)
    assert info.value.report["steps"]["acled"]["action"] == "refresh"              # saved inputs stay saved (R29/R41)
    assert len(ac.saved_weekly(VersionedTable(store, root, gen.ACLED_TABLE))[1]) == 1
    assert len(recorded(runtime_records(store, root), "acled_agg_weekly")) == 1      # saved progress recorded (R45)
    assert not list((tmp_path / "store").rglob("manifest.json"))
    # rerun: nothing new saved before the same block -> no duplicate runtime records
    n = len(runtime_records(store, root))
    req2 = fx.smoke_request(fx.Refs(), tmp_path / "env.json")
    req2["ipcch"]["acled"] = {"action": "keep"}
    with pytest.raises(gen.GenerationFailure):
        generation(store, root, b, bundle, fx.Refs(), req2, tmp_path, providers=unavailable).run()
    assert len(runtime_records(store, root)) == n


def test_research_family_failure_report_keeps_earlier_committed_refreshes(tmp_path, package):
    store, root, b, bundle = setup(tmp_path, package)
    refs = fx.Refs()
    req = fx.smoke_request(refs, tmp_path / "env.json")
    req["ipcch"]["research_inputs"]["nino34_anom"] = {
        "action": "refresh", "file": refs.put("nino.csv", "admin_code,month,value\n11,2027-01,0.5\n"),
        "start": "2027-01", "end": "2027-01"}
    req["ipcch"]["research_inputs"]["bbg_oilgas"] = {
        "action": "refresh", "file": refs.put("oil.csv", "admin_code,month,value\n11,2027-01,abc\n"),
        "start": "2027-01", "end": "2027-01"}
    with pytest.raises(gen.GenerationFailure) as info:
        generation(store, root, b, bundle, refs, req, tmp_path).run()
    assert info.value.step == "research_inputs"
    assert info.value.report["steps"]["research_inputs"]["nino34_anom"]["action"] == "refresh"
    assert len(recorded(runtime_records(store, root), "history__nino34_anom")) == 1


def test_real_keep_without_acled_history_is_refused(tmp_path, package):
    store, root, b, bundle = setup(tmp_path, package)
    refs = fx.Refs()
    req = fx.smoke_request(refs, tmp_path / "env.json")
    req["ipcch"]["acled"] = {"action": "keep"}
    with pytest.raises(gen.GenerationFailure, match="needs saved regional-aggregate history"):
        generation(store, root, b, bundle, refs, req, tmp_path).run()



def failing_last_base():
    good = fx.climate_providers()
    last = cl.BASES[-1]

    def monthly(base):
        if base == last:
            def fail(source, month):
                raise cl.ClimateProcessingFailure(f"{base} {source} {month}: injected processing failure")
            return fail
        return good.monthly(base)
    return climate_run.ClimateProviders(monthly, good.seasonal)


def test_every_saved_version_gets_its_own_runtime_record_even_when_a_later_base_fails(tmp_path, package):
    store, root, b, bundle = setup(tmp_path, package)
    refs = fx.Refs()
    req = fx.smoke_request(refs, tmp_path / "env.json", execution_month="2027-04")       # O = 2027-02: two new months
    with pytest.raises(gen.GenerationFailure, match="injected processing failure"):
        generation(store, root, b, bundle, refs, req, tmp_path, providers=failing_last_base()).run()
    first = cl.table_name(cl.BASES[0], cl.MONTHLY)
    head = VersionedTable(store, root, first).head()[0]
    saved = [v for v in head["lineage"] if v["action"] != "initialise"]
    assert [v["version"] for v in saved] == [2, 3]                                       # 2027-01 and 2027-02
    rt = recorded(runtime_records(store, root), first)
    assert sorted(zip(rt["name"], rt["sha256"])) == sorted((v["content"], v["sha256"]) for v in saved)


def test_lost_acceptance_write_is_repaired_once_on_retry_without_resaving(tmp_path, package, monkeypatch):
    store, root, b, bundle = setup(tmp_path, package)
    refs = fx.Refs()
    req = fx.smoke_request(refs, tmp_path / "env.json")
    real = AcceptanceManifest.append
    state = {"failed": False}

    def flaky(self, entries):
        if not state["failed"] and any("/history__climate_month_" in e["name"] for e in entries):
            state["failed"] = True
            raise RuntimeError("injected acceptance write failure")
        return real(self, entries)
    monkeypatch.setattr(AcceptanceManifest, "append", flaky)
    with pytest.raises(gen.GenerationFailure, match="injected acceptance write failure") as info:
        generation(store, root, b, bundle, refs, req, tmp_path).run()
    assert info.value.step == "climate:runtime_acceptance"
    assert info.value.report["steps"]["climate"]["monthly"]["cdd"]["saved"] == ["2027-01"]     # saved progress reported
    assert info.value.report["steps"]["acled"]["action"] == "refresh"
    climate_heads = {t: VersionedTable(store, root, t).head()[0]["version"] for t in
                     (cl.table_name(base, cl.MONTHLY) for base in cl.BASES)}
    assert recorded(runtime_records(store, root), "history__climate_month_cdd").empty   # saved, receipt lost
    req2 = fx.smoke_request(fx.Refs(), tmp_path / "env.json", run_id="smoke-run-2")
    req2["ipcch"]["acled"] = {"action": "keep"}
    out = generation(store, root, b, bundle, fx.Refs(), req2, tmp_path).run()
    assert out["batch_id"]
    assert {t: VersionedTable(store, root, t).head()[0]["version"] for t in climate_heads} == climate_heads  # not re-saved
    rt = runtime_records(store, root)
    for t in climate_heads:
        r = recorded(rt, t)
        assert len(r) == 1 and r["source"].iloc[0].startswith("runtime smoke-run-2 reconcile")    # repaired exactly once
    assert not rt.duplicated(["name", "sha256"]).any()



def test_real_factory_builds_seasonal_providers_from_the_derived_windows(tmp_path, package):
    """Supervisor residual on 3e97139: the seasonal EE provider must hold the SAME calendar-extended windows as the
    scheduling and assembly. Generation calls the factory with its derived frame; a real provider built from it computes
    2027 rainfall bounds, while one built from the delivered windows alone cannot."""
    from tests.cloud.test_ipcch_climate_ee_seasonal import Backend
    store, root, b, bundle = setup(tmp_path, package)
    refs = fx.Refs()
    seen = {}

    def factory(windows, origin):
        seen["windows"], seen["origin"] = windows, origin
        return fx.climate_providers()
    g = gen.Generation(store=store, root=root, binding=b, bundle_dir=str(bundle),
                       request=fx.smoke_request(refs, tmp_path / "env.json", execution_month="2027-09"),
                       read_ref=refs.read, batch_root=SMOKE, climate_providers=factory, gpp_acquirer=fx.NoGpp(),
                       nightlight_acquirer=fx.NoNightlight(), workdir=str(tmp_path))
    g.run()
    assert seen["windows"] is g.windows and seen["origin"] == "2027-07" and 2027 in set(seen["windows"]["season_year"])
    win = seen["windows"].query("season_year == 2027 and season == 's1'")
    backend = Backend(cover_to="2027-08-01")
    derived = climate_run.real_provider_factory(backend, roster=["11", "12", "13"])(seen["windows"], "2027-07")
    out = derived.seasonal("prcp_z")("chirps", 2027, "s1", win)
    assert out.status == "published" and backend.exports                              # bounds from the derived calendar
    delivered = initial._read(store, root, "fixed/season_windows.csv").assign(
        season_year=lambda f: f["season_year"].astype(int))
    stale = climate_run.real_provider_factory(Backend(cover_to="2027-08-01"), roster=["11", "12", "13"])(delivered, "2027-07")
    with pytest.raises(cl.ClimateProcessingFailure, match="no calendar windows for season year 2027"):
        stale.seasonal("prcp_z")("chirps", 2027, "s1", win)



def test_reconcile_receipt_failure_is_a_reported_generation_failure(tmp_path, package, monkeypatch):
    store, root, b, bundle = setup(tmp_path, package)
    refs = fx.Refs()
    with pytest.raises(gen.GenerationFailure):                     # leaves saved ACLED without a receipt
        monkeypatch.setattr(AcceptanceManifest, "append", lambda self, e: (_ for _ in ()).throw(RuntimeError("down")))
        generation(store, root, b, bundle, refs, fx.smoke_request(refs, tmp_path / "env.json"), tmp_path).run()
    with pytest.raises(gen.GenerationFailure) as info:
        generation(store, root, b, bundle, refs, fx.smoke_request(refs, tmp_path / "env.json"), tmp_path).run()
    assert info.value.step == "reconcile:runtime_acceptance" and info.value.report["run_id"] == "smoke-run-1"
