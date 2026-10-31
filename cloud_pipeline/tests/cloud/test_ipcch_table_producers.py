"""Task 10-30 CP2: the seasonal table producers - source identity and JS/Python formula equivalence, offline graph
structure, demand planning (January prior-year VI, post-2026 chunks), immutable IDs, readback validation, and the
submit/wait/readback/map lifecycle through the real EETransport over a controlled-response EE world."""

import gzip
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import climate as cl
from cloud.ipcch import climate_tables as ct
from cloud.ipcch import table_producers as tp
from cloud.ipcch.climate_ee import AssetRefs
from cloud.ipcch.ee_transport import EETransport, EETransportError
from cloud.ipcch.stores import StoreRoot, VersionedTable
from tests.cloud import ee_pixel_mock as pm
from tests.cloud import ipcch_producer_world as pw
from tests.cloud.ee_offline import offline_ee

FIX = pm.FIXTURES
ADMINS = ["11", "12", "13"]
NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- source identity and formula equivalence


def test_vendored_scripts_are_the_ported_sources():
    for script, sha in tp.SCRIPTS.items():
        path = os.path.join(FIX, script.split("/")[-1])
        assert hashlib.sha256(open(path, "rb").read()).hexdigest() == sha


def values(x):
    return np.array([np.nan if v is None else v for v in x], dtype=float)


def same(port, js):
    a, b = values(port), values(js)
    assert np.array_equal(np.isnan(a), np.isnan(b))                    # identical masks
    np.testing.assert_array_equal(a[~np.isnan(a)], b[~np.isnan(b)])     # bit-identical values


@pytest.fixture(scope="module")
def ref():
    return pm.load_dataset()


def test_daily_fao56_et0_equals_both_upstream_scripts(ref):
    ee = pm.MockEE
    days = ee.ImageCollection(tp.ERA5_DAILY_ID).images
    assert len(days) == 58 and len(ref["js"]["01"]["daily_et0"]) == len(ref["js"]["02"]["daily_et0"]) == 58
    for i, image in enumerate(days):
        port = pm.band_values(tp.daily_fao56_et0(ee, image))
        same(port, ref["js"]["01"]["daily_et0"][i])
        same(port, ref["js"]["02"]["daily_et0"][i])
    floored = [v for i in range(58) for v in ref["js"]["01"]["daily_et0"][i] if v == 0.0]
    assert floored                                                     # the negative-ET0 floor is exercised


@pytest.mark.parametrize("month", ["2026-2", "2026-3", "2026-4"])
def test_monthly_et0_equals_01_and_patch32_cast_equals_02(ref, month):
    ee = pm.MockEE
    y, m = (int(x) for x in month.split("-"))
    plain, present = tp.monthly_et0(ee, y, m)
    cast, _ = tp.monthly_et0(ee, y, m, cast=True)
    js01, js02 = ref["js"]["01"]["monthly_et0"][month], ref["js"]["02"]["monthly_et0"][month]
    same(pm.band_values(plain), js01["values"])
    same(pm.band_values(cast), js02["values"])
    assert list(plain.bands) == list(cast.bands) == [js01["band"]] == [f"et0_{y}{m:02d}"]
    assert present.v == js01["props"]["days_present"] and plain.props["month_complete"] == js01["props"]["month_complete"]
    if month == "2026-2":                                              # 02's final toFloat is not a no-op
        assert values(js01["values"]).tolist() != values(js02["values"]).tolist()
        assert values(js02["values"]).tolist() == values(js01["values"]).astype(np.float32).astype(float).tolist()
    else:                                                              # incomplete (30/31) and empty months masked
        assert np.isnan(values(js01["values"])).all() and not plain.props["month_complete"]


@pytest.mark.parametrize("source", list(ct.SPI_SOURCES))
def test_monthly_precipitation_equals_01(ref, source):
    ee = pm.MockEE
    for month in ("2026-2", "2026-3", "2026-4"):
        y, m = (int(x) for x in month.split("-"))
        image, present = tp.monthly_precipitation(ee, source, y, m)
        js = ref["js"]["01"]["precipitation"][f"{ct.SPI_SOURCES[source]} {month}"]
        same(pm.band_values(image), js["values"])
        assert [js["band"]] == list(image.bands) and present.v == js["props"]["days_present"]
        assert {k: image.props[k] for k in ("days_expected", "month_complete")} == \
               {k: js["props"][k] for k in ("days_expected", "month_complete")}
    persiann_march = ref["js"]["01"]["precipitation"]["PERSIANN 2026-3"]
    assert persiann_march["props"]["month_complete"] == 1 and None not in persiann_march["values"]


def test_vi_quality_mask_equals_01(ref):
    ee = pm.MockEE
    for i, image in enumerate(ee.ImageCollection("MODIS/061/MOD13C1").images):
        p = tp.prepare_vi(ee, image)
        js = ref["js"]["01"]["vi"][i]
        assert list(p.bands) == list(js) == ["ndvi", "evi", "used_1km"]
        for band in js:
            same(pm.band_values(p.select(band)), js[band])
    assert [v is None for v in ref["js"]["01"]["vi"][0]["evi"]] == [True, False, True, True, False, False]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is a local evidence tool, not a runtime dependency")
def test_js_reference_regenerates_from_the_vendored_scripts(tmp_path, ref):
    dataset = tmp_path / "dataset.json"
    dataset.write_text(json.dumps({"pixels": ref["pixels"], "dataset": ref["dataset"]}))
    subprocess.run(["node", os.path.join(FIX, "run_js_reference.js"), str(dataset), str(tmp_path / "out.json")], check=True)
    assert json.loads((tmp_path / "out.json").read_text())["js"] == ref["js"]


# --------------------------------------------------------------------------- graph structure (real offline client)


def graph(obj):
    ee = offline_ee()
    return json.dumps(json.loads(ee.serializer.toJSON(obj)))


@pytest.fixture(scope="module")
def graphs():
    ee = offline_ee()
    admins = tp.admin_features(ee, AssetRefs())
    buffered = tp.buffered_patch32(ee, tp.patch32_targets(ee, AssetRefs()))
    return {"vi": graph(tp.vi_table(ee, "aqua", 2027, admins)), "prcp": graph(tp.precipitation_table(ee, "era5land", 2020, 2026, admins)),
            "et0": graph(tp.et0_table(ee, 2020, 2026, admins)), "patch": graph(tp.patch32_table(ee, 2020, 2026, buffered))}


def test_graphs_carry_the_scripts_operations(graphs):
    for g in graphs.values():
        assert "Image.reduceRegions" in g and "Reducer.mean" in g and "Reducer.stdDev" in g and "Reducer.count" in g
        assert '"tileScale": {"constantValue": 8}' in g and '"maxPixelsPerRegion": {"constantValue": 1000000000.0}' in g
        assert "Geometry.centroid" in g and "IPCCH_ADMIN_STATIC_CALENDAR_CROPFRAC_V1_G24" in g
        assert "projects/han-sandbox-505315/assets/" in g
    vi = graphs["vi"]
    assert "MODIS/061/MYD13C1" in vi and '"SummaryQA"' in vi and '"Pixel_1km"' in vi and "YYYYMMdd" in vi
    assert "composite_dates" in vi and "cmg_grid_total" in vi and "CMG_0P05_DEG" in vi and "admin_area_km2" in vi
    for key, prefix in (("prcp", "prcp"), ("et0", "et0"), ("patch", "et0")):
        g = graphs[key]
        for tag in pw.chunk_months(2020, 2026):
            assert f'"{prefix}_{tag}"' in g and f'"days_present_{tag}"' in g
        assert "source_grid_total" in g and "mm_month" in g and '"constantValue": 2027' not in g
    assert '"constantValue": 1000' in graphs["prcp"] and "total_precipitation_sum" in graphs["prcp"]
    for band in tp.ERA5_ET0_BANDS:
        assert f'"{band}"' in graphs["et0"]
    for constant in ("17.27", "237.3", "0.6108", "4098", "0.000665", "900", "0.34", "0.408", "1000000.0", "273.15"):
        assert f'"constantValue": {constant}' in graphs["et0"]
    patch = graphs["patch"]
    assert '"distance": {"constantValue": 30000}' in patch and "BUFFERED_ERA5LAND_MEAN" in patch and '"V2"' in patch
    assert all(f"{c}" in patch for c in tp.PATCH32_CODES) and "Collection.distinct" in patch
    assert '"admin_area_km2"' not in patch and '"original_admin_area_km2"' in patch


# --------------------------------------------------------------------------- planning


def test_year_chunks_roll_over_after_2026():
    assert ct.year_chunks(2026) == ct.YEAR_CHUNKS
    assert ct.year_chunks(2027)[-1] == (2027, 2032) and ct.year_chunks(2032)[-1] == (2027, 2032)
    assert ct.year_chunks(2033)[-2:] == ((2027, 2032), (2033, 2038))


def need(monthly=(), seasonal=()):
    return {"monthly": {b: list(monthly) for b in tp.TABLE_BASES},
            "seasonal": {b: [dict(s) for s in seasonal] for b in tp.TABLE_BASES}}


def names(jobs):
    return [j.name for j in jobs]


def test_required_tables_for_a_routine_month_are_the_seven_families():
    jobs = tp.required_tables(need(["2026-09"]), ct.TableRefs(year_chunks=ct.year_chunks(2026)))
    assert names(jobs) == ["S2E3_VI_CURRENT_ADMIN_AQUA_Y2026_CMG_V3", "S2E3_VI_CURRENT_ADMIN_TERRA_Y2026_CMG_V3",
                           "S2C3_DROUGHT_ADMIN_PRCP_CHIRPS_Y2020_2026_V3", "S2C3_DROUGHT_ADMIN_PRCP_PERSIANN_Y2020_2026_V3",
                           "S2C3_DROUGHT_ADMIN_PRCP_ERA5LAND_Y2020_2026_V3", "S2C3_DROUGHT_ADMIN_ET0_FAO56_Y2020_2026_V3",
                           "S2C3_ET0_PATCH32_Y2020_2026_V2"]
    assert {j.script for j in jobs if j.kind == "patch32"} == {"seasonal/02_et0_patch32_update.js"}


def test_january_reads_the_prior_year_aqua_and_both_chunks():
    jobs = tp.required_tables(need(["2027-01"]), ct.TableRefs(year_chunks=ct.year_chunks(2027)))
    vi = sorted((j.key, j.years[0]) for j in jobs if j.kind == "vi")
    assert vi == [("aqua", 2026), ("aqua", 2027), ("terra", 2027)]     # Aqua slot 23 of 2026 overlaps January
    assert sorted({j.years for j in jobs if j.kind != "vi"}) == [(2020, 2026), (2027, 2032)]   # Nov/Dec 2026 + Jan 2027
    assert len(jobs) == 13 and "S2C3_DROUGHT_ADMIN_PRCP_CHIRPS_Y2027_2032_V3" in names(jobs)
    with pytest.raises(cl.ClimateProcessingFailure, match="beyond the reader's chunks"):
        tp.required_tables(need(["2027-01"]), ct.TableRefs())


def test_seasonal_and_historical_demand():
    season = {"season_year": 2027, "season": "s1", "span": ["2027-03", "2027-06"]}
    jobs = tp.required_tables(need(seasonal=[season]), ct.TableRefs(year_chunks=ct.year_chunks(2027)))
    assert sorted((j.key, j.years[0]) for j in jobs if j.kind == "vi") == [("aqua", 2026), ("aqua", 2027),
                                                                          ("terra", 2026), ("terra", 2027)]
    assert {j.years for j in jobs if j.kind != "vi"} == {(2027, 2032)}          # inputs 2027-01..2027-06
    old = tp.required_tables(need(["2019-06"]), ct.TableRefs())
    assert [j.kind for j in old] == ["vi", "vi"]                                # 1990-2019 chunks are static history
    assert tp.required_tables(need(), ct.TableRefs()) == []


ROOT = StoreRoot("real", "gs://b/ipcch-v2/real")
WINDOWS = pd.DataFrame([{"admin_code": a, "season_year": y, "season": s, "gs_start_date": f"{y}-{sm}-01",
                         "gs_end_date_exclusive": f"{y}-{em}-01"}
                        for a in ADMINS for y in (2025, 2026, 2027) for s, sm, em in (("s1", "03", "07"), ("s2", "08", "11"))])


def seeded(tmp_path, through, seasons_through=(2026, "s2")):
    store = LocalObjectStore(tmp_path / "store")
    months = [str(p) for p in pd.period_range("2015-01", through, freq="M")]
    for base in cl.BASES:
        VersionedTable(store, ROOT, cl.table_name(base, cl.MONTHLY)).commit(pd.DataFrame(
            [{"admin_code": a, "month": m, "value": 0.0, "n_sources": 1, "ens_sd": np.nan, "method_id": "accepted"}
             for m in months for a in ADMINS]), {"action": "initialise"}, expected_generation="0")
        done = WINDOWS[[(y, s) <= seasons_through for y, s in zip(WINDOWS["season_year"], WINDOWS["season"])]]
        VersionedTable(store, ROOT, cl.table_name(base, cl.SEASONAL)).commit(
            done.assign(value=0.0, n_sources=1, ens_sd=np.nan, method_id="accepted")[list(cl.GS_COLUMNS)],
            {"action": "initialise"}, expected_generation="0")
    return store, (lambda b, t: VersionedTable(store, ROOT, cl.table_name(b, t)))


def test_demand_follows_the_climate_scheduling(tmp_path):
    _, tables = seeded(tmp_path, "2026-08", seasons_through=(2026, "s1"))
    d = tp.demand(tables, origin="2026-10", windows=WINDOWS)
    assert d["monthly"]["spei03"] == ["2026-09", "2026-10"]
    assert d["seasonal"]["evi_anom"] == [{"season_year": 2026, "season": "s2", "span": ["2026-08", "2026-10"]}]
    assert tp.demand(tables, origin="2026-08", windows=WINDOWS)["monthly"]["spi03"] == []      # retained: no demand


def test_output_ids_are_per_run_and_immutable():
    v = tp.output_version("run-2026-10-a", "2026-10")
    assert v == tp.output_version("run-2026-10-a", "2026-10") and v.startswith("M202610_run-2026-10-a_")
    assert tp.output_version("run-2026-10-b", "2026-10") != v                    # same day, new run -> new IDs
    assert tp.output_version("r.1", "2026-10") != tp.output_version("r_1", "2026-10")   # sanitising never collides
    p = tp.TableProducer(None, AssetRefs(), pw.OUT_ROOT, "run-2026-10-a", "2026-10")
    job = tp.TableJob("S2C3_ET0_PATCH32_Y2020_2026_V2", "patch32", None, (2020, 2026))
    assert p.asset_id(job) == f"{pw.OUT_ROOT}S2C3_ET0_PATCH32_Y2020_2026_V2__{v}"
    with pytest.raises(cl.ClimateProcessingFailure, match="projects/<p>/assets"):
        tp.TableProducer(None, AssetRefs(), "projects/p/assets", "r", "2026-10")
    with pytest.raises(cl.ClimateProcessingFailure, match="shared read-only input root"):
        tp.TableProducer(None, AssetRefs(), "projects/han-sandbox-505315/assets/x/", "r", "2026-10")


# --------------------------------------------------------------------------- readback validation


def test_readback_declares_completeness_and_validates_identity():
    name = "S2C3_DROUGHT_ADMIN_PRCP_CHIRPS_Y2020_2026_V3"
    job = pw.job_for(name)
    periods = tp.readback(job, pw.chunk_frame(name, ADMINS, "2026-09"))
    assert len(periods) == 84 and periods["202609"] and not periods["202610"] and periods["202001"]
    bad = {"unit": lambda f: f.assign(unit="mm_day"), "constant": lambda f: f.assign(source=["CHIRPS", "CHIRPS", "X"]),
           "absent": lambda f: f.drop(columns="days_present_202609"), "count": lambda f: f.assign(days_present_202609=29.5),
           "duplicate": lambda f: pd.concat([f, f.iloc[:1]]), "inf": lambda f: f.assign(prcp_202609_mean=np.inf),
           "text": lambda f: f.assign(prcp_202609_mean="n/a")}
    for why, fn in bad.items():
        with pytest.raises(cl.ClimateProcessingFailure):
            tp.readback(job, fn(pw.chunk_frame(name, ADMINS, "2026-09")))
    masked = pw.chunk_frame(name, ADMINS, "2026-09").assign(prcp_202609_mean=[1.0, None, 2.0])
    assert tp.readback(job, masked)["202609"]                                      # complete-but-masked is valid
    patch = "S2C3_ET0_PATCH32_Y2020_2026_V2"
    with pytest.raises(cl.ClimateProcessingFailure, match="32 targets"):
        tp.readback(pw.job_for(patch), pw.chunk_frame(patch, [str(c) for c in tp.PATCH32_CODES[:31]], "2026-09"))


def test_readback_vi_composites_including_an_explicit_empty_listing():
    name = "S2E3_VI_CURRENT_ADMIN_TERRA_Y2027_CMG_V3"
    job = pw.job_for(name)
    assert tp.readback(job, pw.vi_frame(name, ADMINS, "2027-01-31")) == {"20270101": True, "20270117": True}
    empty = pw.vi_frame(name, ADMINS, composites=[])
    assert tp.readback(job, empty) == {}                                          # no composite published yet
    ct.TableRefs(produced={name: ct.ProducedTable(pw.OUT_ROOT + "x", {})})        # accepted for VI only
    with pytest.raises(cl.ClimateProcessingFailure, match="lacks composite_dates"):
        tp.readback(job, empty.drop(columns="composite_dates"))
    for broken in ([None, None, None], ["", None, ""], ["", "20270101", ""]):         # null, mixed null/empty, mixed
        with pytest.raises(cl.ClimateProcessingFailure, match="composite_dates must be one value on every row"):
            tp.readback(job, empty.assign(composite_dates=broken))
    with pytest.raises(cl.ClimateProcessingFailure, match="malformed composite_dates"):
        tp.readback(job, empty.assign(composite_dates="2027-01-01"))
    with pytest.raises(cl.ClimateProcessingFailure, match="no source-calendar completeness"):
        ct.TableRefs(produced={"S2C3_DROUGHT_ADMIN_PRCP_CHIRPS_Y2020_2026_V3": ct.ProducedTable(pw.OUT_ROOT + "y", {})})


# --------------------------------------------------------------------------- lifecycle through EETransport


def transport(world_ee, store, run_id="run-2026-10-a", deadline=None, clock=None):
    return EETransport(ee=world_ee, client=None, store=store, output_root="gs://ops-exports/v2", run_id=run_id,
                       poll_seconds=0, sleep=lambda s: None, deadline_utc=deadline, clock=clock or (lambda: NOW))


def produce(tmp_path, *, through="2026-08", origin="2026-09", run_id="run-2026-10-a", server_through="2026-09",
            world=None, ee_kw=None, deadline=None, store=None, tables=None, month="2026-11"):
    if store is None:
        store, tables = seeded(tmp_path, through)
    world = world if world is not None else pw.static_world(ADMINS)
    wee = pw.WorldEE(world, pw.server_for(ADMINS, through=server_through), **(ee_kw or {}))
    t = transport(wee, store, run_id, deadline)
    producer = tp.TableProducer(t, AssetRefs(), pw.OUT_ROOT, run_id, month)
    return producer, t, wee, tables


def test_one_routine_month_produces_seven_tables_submitted_before_any_wait(tmp_path):
    producer, t, wee, tables = produce(tmp_path)
    production = producer.run(tables, origin="2026-09", windows=WINDOWS)
    assert len(wee.tasks) == 7 and all(task.polls >= 1 for task in wee.tasks)
    kinds = [k for k, _ in wee.events]
    assert kinds[:7] == ["submit"] * 7 and "submit" not in kinds[7:]          # all submitted before any wait
    assert sorted(pw.basename(a) for a in pw.exported(wee)) == sorted(production.produced)
    version = tp.output_version("run-2026-10-a", "2026-11")
    assert all(a.startswith(pw.OUT_ROOT) and a.endswith("__" + version) for a in pw.exported(wee))
    patch = production.produced["S2C3_ET0_PATCH32_Y2020_2026_V2"]
    assert patch.periods["202609"] and not patch.periods["202610"]
    receipts = production.report["receipts"]
    assert [r["task_id"] for r in receipts] == [f"T{k}" for k in range(7)] and {r["state"] for r in receipts} == {"completed"}
    assert {r["script_sha256"] for r in receipts} == set(tp.SCRIPTS.values())
    for r in receipts:                                           # durable task receipts under the run's export prefix
        rec = json.loads(t.store.read_text(f"gs://ops-exports/v2/ipcch_exports/run-2026-10-a/tasks/{r['table']}.json"))
        assert rec["state"] == "completed" and rec["task_id"] == r["task_id"] and rec["asset_id"] == r["asset_id"]
    assert set(production.frames) == {r["asset_id"] for r in receipts}


def test_retained_periods_produce_nothing(tmp_path):
    producer, t, wee, tables = produce(tmp_path, through="2026-09")
    production = producer.run(tables, origin="2026-09", windows=WINDOWS)
    assert production.produced == {} and wee.tasks == [] and wee.deadlines == []
    assert "already retained" in production.report["skipped"]


def test_a_failed_export_cancels_its_siblings_and_exposes_nothing(tmp_path):
    """Waits run in submission order: T0/T1 complete, T2 fails, T3-T6 are still running and are cancelled; nothing is
    mapped for consumers (the completed T0/T1 assets stay unexposed orphans of the failed run)."""
    def states(task):
        return {"T0": "COMPLETED", "T1": "COMPLETED", "T2": "FAILED"}.get(task.id, "RUNNING")
    producer, t, wee, tables = produce(tmp_path, ee_kw={"states": states})
    with pytest.raises(EETransportError, match="FAILED"):
        producer.run(tables, origin="2026-09", windows=WINDOWS)
    assert [task.cancelled for task in wee.tasks] == [False, False, False, True, True, True, True]
    assert [task.polls for task in wee.tasks] == [1, 1, 1, 0, 0, 0, 0]
    assert [a in wee.world for a in pw.exported(wee)] == [True, True, False, False, False, False, False]
    states_on_record = [json.loads(t.store.read_text(f"gs://ops-exports/v2/ipcch_exports/run-2026-10-a/tasks/{pw.basename(a)}.json"))["state"]
                        for a in pw.exported(wee)]
    assert states_on_record == ["completed", "completed", "FAILED"] + ["cancelled_after_failure"] * 4


def test_an_interrupted_wait_still_cancels_with_a_durable_receipt(tmp_path):
    def states(task):
        if task.id == "T0":
            raise KeyboardInterrupt
        return "RUNNING"
    producer, t, wee, tables = produce(tmp_path, ee_kw={"states": states})
    with pytest.raises(KeyboardInterrupt):
        producer.run(tables, origin="2026-09", windows=WINDOWS)
    assert all(task.cancelled for task in wee.tasks)              # including the interrupted one
    rec = json.loads(t.store.read_text("gs://ops-exports/v2/ipcch_exports/run-2026-10-a/tasks/"
                                       "S2E3_VI_CURRENT_ADMIN_AQUA_Y2026_CMG_V3.json"))
    assert rec["state"] == "cancelled_after_failure" and rec["cancel"] == "cancelled"


def test_timeout_is_cancelled_within_the_deadline(tmp_path):
    clock = {"t": NOW}
    deadline = NOW + timedelta(seconds=900 + 5)                   # 5 s of budget before the cleanup reserve
    producer, t, wee, tables = produce(tmp_path, ee_kw={"states": ("RUNNING",)}, deadline=deadline)
    t.poll_seconds = 1                                            # fake time advances by each bounded sleep
    t.clock = lambda: clock["t"]
    t.monotonic = lambda: (clock["t"] - NOW).total_seconds()
    t.sleep = lambda s: clock.__setitem__("t", clock["t"] + timedelta(seconds=s))
    with pytest.raises(EETransportError, match="timed out"):
        producer.run(tables, origin="2026-09", windows=WINDOWS)
    assert all(task.cancelled for task in wee.tasks)
    work = [(name, ms, retries) for name, ms, retries in wee.calls if name != "cancel"]
    cancels = [(name, ms, retries) for name, ms, retries in wee.calls if name == "cancel"]
    assert work and all(0 < ms <= 5000 and retries == 0 for _, ms, retries in work)    # within the pre-reserve budget
    assert len(cancels) == 7 and all(0 < ms <= 60000 and retries == 0 for _, ms, retries in cancels)   # capped per request
    assert (wee.state.deadline_ms, wee.state.max_retries) == (0, 5)                     # SDK settings restored


def test_an_expired_deadline_stops_before_any_earth_engine_call(tmp_path):
    producer, t, wee, tables = produce(tmp_path, deadline=NOW + timedelta(seconds=900))
    with pytest.raises(EETransportError, match="cleanup reserve reached"):
        producer.run(tables, origin="2026-09", windows=WINDOWS)
    assert wee.tasks == [] and wee.deadlines == []


def test_duplicate_run_and_existing_destination_never_resubmit(tmp_path):
    producer, t, wee, tables = produce(tmp_path)
    producer.run(tables, origin="2026-09", windows=WINDOWS)
    again = tp.TableProducer(transport(wee, t.store), AssetRefs(), pw.OUT_ROOT, "run-2026-10-a", "2026-11")
    with pytest.raises(cl.ClimateProcessingFailure, match="already exist"):
        again.run(tables, origin="2026-09", windows=WINDOWS)
    assert len(wee.tasks) == 7
    fresh_world = dict(wee.world)
    for a in pw.exported(wee):
        fresh_world.pop(a)
    wee2 = pw.WorldEE(fresh_world, wee.server)
    dup = tp.TableProducer(transport(wee2, t.store), AssetRefs(), pw.OUT_ROOT, "run-2026-10-a", "2026-11")
    with pytest.raises(EETransportError, match="already reserved"):           # durable reservation of the same run
        dup.run(tables, origin="2026-09", windows=WINDOWS)
    assert wee2.tasks == []
    same_day = tp.TableProducer(transport(wee, t.store, "run-2026-10-b"), AssetRefs(), pw.OUT_ROOT, "run-2026-10-b",
                                "2026-11").run(tables, origin="2026-09", windows=WINDOWS)
    assert len(wee.tasks) == 14 and not set(same_day.frames) & {a for a in pw.exported(wee)[:7]}


def test_patch32_target_check_and_malformed_outputs_block(tmp_path):
    producer, t, wee, tables = produce(tmp_path, ee_kw={"patch_count": {"rows": 31, "unique_codes": 31}})
    with pytest.raises(cl.ClimateProcessingFailure, match="32 rows"):
        producer.run(tables, origin="2026-09", windows=WINDOWS)
    assert wee.tasks == []
    name = "S2C3_DROUGHT_ADMIN_PRCP_PERSIANN_Y2020_2026_V3"
    wrong = pw.chunk_frame("S2C3_DROUGHT_ADMIN_ET0_FAO56_Y2020_2026_V3", ADMINS, "2026-09").assign(
        **pw.expected_props(pw.job_for(name)))                     # a PRCP table carrying ET0 fields
    for broken, match in ((wrong, "not a prcp field"),
                          (pw.chunk_frame(name, ADMINS, "2026-09").assign(prcp_202609_mean=np.inf), "infinite"),
                          (pw.chunk_frame(name, ADMINS, "2026-09").assign(prcp_202610_mean=5.0), "incomplete but carries")):
        store, tables = seeded(tmp_path / match.replace(" ", "_"), "2026-08")
        wee = pw.WorldEE(pw.static_world(ADMINS), pw.server_for(ADMINS, through="2026-09", overrides={name: broken}))
        p = tp.TableProducer(transport(wee, store), AssetRefs(), pw.OUT_ROOT, "run-2026-10-a", "2026-11")
        with pytest.raises(cl.ClimateProcessingFailure, match=match):
            p.run(tables, origin="2026-09", windows=WINDOWS)


def test_completed_task_without_its_asset_is_a_failure(tmp_path):
    store, tables = seeded(tmp_path, "2026-08")
    world = pw.static_world(ADMINS)
    wee = pw.WorldEE(world, pw.server_for(ADMINS, through="2026-09"))
    t = transport(wee, store)
    producer = tp.TableProducer(t, AssetRefs(), pw.OUT_ROOT, "run-2026-10-a", "2026-11")
    lost = producer.asset_id(pw.job_for("S2C3_ET0_PATCH32_Y2020_2026_V2"))
    wee.missing_after.add(lost)
    with pytest.raises(EETransportError, match="COMPLETED but"):
        producer.run(tables, origin="2026-09", windows=WINDOWS)
    rec = json.loads(store.read_text("gs://ops-exports/v2/ipcch_exports/run-2026-10-a/tasks/S2C3_ET0_PATCH32_Y2020_2026_V2.json"))
    assert rec["state"] == "completed_without_asset"


def test_start_failure_cancels_and_records(tmp_path):
    producer, t, wee, tables = produce(tmp_path, ee_kw={"start_error": RuntimeError("response lost")})
    with pytest.raises(EETransportError, match="start failed"):
        producer.run(tables, origin="2026-09", windows=WINDOWS)
    assert len(wee.tasks) == 1 and wee.tasks[0].cancelled
    rec = json.loads(t.store.read_text("gs://ops-exports/v2/ipcch_exports/run-2026-10-a/tasks/"
                                       "S2E3_VI_CURRENT_ADMIN_AQUA_Y2026_CMG_V3.json"))
    assert rec["state"] == "start_failed" and rec["cancel"] == "cancelled"
