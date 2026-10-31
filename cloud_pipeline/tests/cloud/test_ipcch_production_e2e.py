"""Task 10-30 CP2 / AC8: IPCCH generation with the real table producer, EETransport and table providers over a
controlled-response Earth Engine world: unsaved-month planning -> graph construction -> Asset export submit/wait ->
readback -> resolved IDs -> retained append (records carry the produced assets) -> assembly -> batch manifest receipts.
January 2027 exercises the prior-year Aqua table and the 2027-2032 chunk; a second run of the same month skips
production; a year without any published composite is legitimate unavailability that a later run recovers.
The raster bases (rainfall/temperature/soil) keep the smoke fixture providers; no live EE call is made."""

import json

import pytest

from cloud.ipcch import climate as cl
from cloud.ipcch import climate_run
from cloud.ipcch import generation as gen
from cloud.ipcch import table_producers as tp
from cloud.ipcch.climate_ee import AssetRefs
from cloud.ipcch.ee_transport import EETransport
from cloud.ipcch.stores import VersionedTable
from tests.cloud import ipcch_producer_world as pw
from tests.cloud import ipcch_smoke_fixture as fx
from tests.cloud.test_ipcch_assembly import ROSTER
from tests.cloud.test_ipcch_generation import SMOKE, package, setup  # noqa: F401 (package fixture)

CODES = [str(a) for a in ROSTER]
EXPORTS = "gs://ops-exports/v2"


def producing_generation(store, root, b, bundle, refs, request, tmp_path, wee):
    t = EETransport(ee=wee, client=None, store=store, output_root=EXPORTS, run_id=request["run_id"], poll_seconds=0,
                    sleep=lambda s: None)
    producer = tp.TableProducer(t, AssetRefs(), pw.OUT_ROOT, request["run_id"], request["execution_month"])
    accessor = lambda base, temporal: VersionedTable(store, root, cl.table_name(base, temporal))   # noqa: E731
    real_factory = climate_run.real_provider_factory(t, roster=CODES, producer=producer, tables=accessor)

    def factory(windows, origin):
        real, fixture = real_factory(windows, origin), fx.climate_providers()
        pick = lambda base: real if base in tp.TABLE_BASES else fixture                      # noqa: E731
        return climate_run.ClimateProviders(lambda base: pick(base).monthly(base), lambda base: pick(base).seasonal(base),
                                            production=real.production)
    return gen.Generation(store=store, root=root, binding=b, bundle_dir=str(bundle), request=request,
                          read_ref=refs.read, batch_root=SMOKE, climate_providers=factory, gpp_acquirer=fx.NoGpp(),
                          nightlight_acquirer=fx.NoNightlight(), workdir=str(tmp_path))


def head(store, root, base):
    return VersionedTable(store, root, cl.table_name(base, cl.MONTHLY)).head()[0]


def saved_record(store, root, base, month):
    """The retained version record that appended ``month`` (the climate append record of that version)."""
    table = VersionedTable(store, root, cl.table_name(base, cl.MONTHLY))
    h = table.head()[0]
    assert h["record"].get("month") == month, h["record"]
    return h["record"]


def test_january_2027_production_flows_into_retained_history_and_the_batch(tmp_path, package):  # noqa: F811
    store, root, b, bundle = setup(tmp_path, package)
    refs = fx.Refs()
    req = fx.smoke_request(refs, tmp_path / "env.json", execution_month="2027-03")          # O = 2027-01
    wee = pw.WorldEE(pw.static_world(CODES), pw.server_for(CODES, through="2027-01", vi_through="2027-01-31"))
    out = producing_generation(store, root, b, bundle, refs, req, tmp_path, wee).run()

    exported = pw.exported(wee)
    names = sorted(pw.basename(a) for a in exported)
    assert len(exported) == 13 and "S2E3_VI_CURRENT_ADMIN_AQUA_Y2026_CMG_V3" in names
    assert "S2C3_DROUGHT_ADMIN_PRCP_CHIRPS_Y2027_2032_V3" in names and "S2C3_ET0_PATCH32_Y2027_2032_V2" in names
    version = tp.output_version("smoke-run-1", "2027-03")
    assert all(a.startswith(pw.OUT_ROOT) and a.endswith("__" + version) for a in exported)

    manifest = json.loads(store.read_text(out["manifest_ref"]["uri"]))
    production = manifest["generation"]["climate_production"]
    receipts = {r["asset_id"]: r for r in production["receipts"]}
    assert set(receipts) == set(exported) and production["run_id"] == "smoke-run-1"
    assert production["demand"]["monthly"] == {"evi_anom": ["2027-01"], "spi03": ["2027-01"], "spei03": ["2027-01"]}
    assert all(r["state"] == "completed" and r["task_id"] for r in receipts.values())

    for base in tp.TABLE_BASES:                          # each saved month records the produced assets it consumed
        record = saved_record(store, root, base, "2027-01")
        used = {a for assets in record["produced_tables"].values() for a in assets}
        assert used and used <= set(exported)
        assert sorted(record["produced_tables"]) == sorted(cl.SOURCES[base])
        assert manifest["retained_inputs"][cl.table_name(base, cl.MONTHLY)]["version"] == head(store, root, base)["version"]
    evi = saved_record(store, root, "evi_anom", "2027-01")["produced_tables"]
    assert {pw.basename(a) for a in evi["aqua"]} == {"S2E3_VI_CURRENT_ADMIN_AQUA_Y2026_CMG_V3",
                                                    "S2E3_VI_CURRENT_ADMIN_AQUA_Y2027_CMG_V3"}  # January reads 2026 too
    spei = saved_record(store, root, "spei03", "2027-01")["produced_tables"]["chirps"]
    assert {pw.basename(a) for a in spei} >= {"S2C3_ET0_PATCH32_Y2020_2026_V2", "S2C3_ET0_PATCH32_Y2027_2032_V2"}
    frame, _ = cl.read_monthly(VersionedTable(store, root, cl.table_name("evi_anom", cl.MONTHLY)))
    jan = frame[frame["month"] == "2027-01"]
    assert len(jan) == len(CODES) and jan["value"].between(0.04, 0.16).all() and (jan["n_sources"] == 2).all()

    # a second run of the same month: everything retained -> nothing produced, the skip is reported in its batch
    req2 = fx.smoke_request(fx.Refs(), tmp_path / "env.json", execution_month="2027-03", run_id="smoke-run-2")
    req2["ipcch"]["acled"] = {"action": "keep"}
    wee2 = pw.WorldEE(wee.world, wee.server)
    out2 = producing_generation(store, root, b, bundle, fx.Refs(), req2, tmp_path, wee2).run()
    assert wee2.tasks == [] and wee2.calls == []
    skipped = json.loads(store.read_text(out2["manifest_ref"]["uri"]))["generation"]["climate_production"]
    assert skipped["receipts"] == [] and "already retained" in skipped["skipped"]


def test_a_year_without_composites_is_unavailable_until_a_later_run_recovers(tmp_path, package):  # noqa: F811
    store, root, b, bundle = setup(tmp_path, package)
    refs = fx.Refs()
    req = fx.smoke_request(refs, tmp_path / "env.json", execution_month="2027-03")
    empty = {n: pw.vi_frame(n, CODES, composites=[]) for n in ("S2E3_VI_CURRENT_ADMIN_TERRA_Y2027_CMG_V3",
                                                               "S2E3_VI_CURRENT_ADMIN_AQUA_Y2027_CMG_V3")}
    wee = pw.WorldEE(pw.static_world(CODES), pw.server_for(CODES, through="2027-01", overrides=empty))
    with pytest.raises(gen.GenerationFailure) as info:
        producing_generation(store, root, b, bundle, refs, req, tmp_path, wee).run()
    assert info.value.step == "climate" and isinstance(info.value.cause, cl.ClimateSourceMissing)
    assert "evi_anom" in str(info.value.cause)                     # no composite of 2027 yet: no source for O
    assert head(store, root, "evi_anom")["record"].get("month") != "2027-01"        # nothing saved for evi_anom
    assert saved_record(store, root, "spei03", "2027-01")["produced_tables"]           # drought months were saved

    req2 = fx.smoke_request(fx.Refs(), tmp_path / "env.json", execution_month="2027-03", run_id="smoke-run-2")
    req2["ipcch"]["acled"] = {"action": "keep"}
    wee2 = pw.WorldEE(wee.world, pw.server_for(CODES, through="2027-01", vi_through="2027-01-31"))
    out = producing_generation(store, root, b, bundle, fx.Refs(), req2, tmp_path, wee2).run()
    assert sorted(pw.basename(a) for a in pw.exported(wee2)) == ["S2E3_VI_CURRENT_ADMIN_AQUA_Y2026_CMG_V3",
                                                                 "S2E3_VI_CURRENT_ADMIN_AQUA_Y2027_CMG_V3",
                                                                 "S2E3_VI_CURRENT_ADMIN_TERRA_Y2027_CMG_V3"]
    assert all(a.endswith(tp.output_version("smoke-run-2", "2027-03")) for a in pw.exported(wee2))   # new run, new IDs
    record = saved_record(store, root, "evi_anom", "2027-01")
    assert {a for v in record["produced_tables"].values() for a in v} <= set(pw.exported(wee2))
    assert out["batch_id"]
