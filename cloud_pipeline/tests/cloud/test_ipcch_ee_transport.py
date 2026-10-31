"""Task 10-29: the concrete EE/GCS transport behind the IPCCH climate providers, driven through fakes of only the
network surfaces (ee.List.getInfo, ee.data, export tasks, storage); graphs are built by the real offline client."""

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import climate as cl
from cloud.ipcch import climate_ee as ce
from cloud.ipcch import climate_tables as ct
from cloud.ipcch.ee_transport import EETransport, EETransportError
from cloud.ipcch.stores import StoreRoot, VersionedTable
from tests.cloud.ee_offline import offline_ee
from tests.cloud.test_prepare import FakeGcs

ROOT = "gs://ipcch-runs/real"
AMBIGUOUS = "Asset '{}' does not exist or doesn't allow this operation."


class FakeData:
    def __init__(self, present=(), listed=None, list_error=None, get_error=None, table=None, compute_error=None):
        self.present, self.listed, self.list_error = set(present), listed, list_error
        self.get_error, self.table, self.compute_error = get_error, table, compute_error
        self.list_calls, self.compute_calls = [], []
        self.deadline_ms, self.max_retries, self.seen = 0, 5, []      # SDK request settings, recorded per request
        self.on_request = None

    def _get_state(self):
        return self

    def setDeadline(self, ms):
        self.deadline_ms = ms

    def setMaxRetries(self, n):
        self.max_retries = n

    def _request(self, name):
        self.seen.append((name, self.deadline_ms, self.max_retries))
        if self.on_request is not None:
            self.on_request(name)

    def getAsset(self, asset_id):
        self._request("getAsset")
        if self.get_error is not None:
            raise self.get_error
        if asset_id in self.present:
            return {"name": asset_id, "type": "TABLE"}
        raise Exception(AMBIGUOUS.format(asset_id))

    def listAssets(self, params):
        self._request("listAssets")
        self.list_calls.append(params["parent"])
        if self.list_error is not None:
            raise self.list_error
        names = sorted(n for n in (self.listed if self.listed is not None else self.present)
                       if n.startswith(params["parent"] + "/"))
        size, start = int(params["pageSize"]), int(params.get("pageToken") or 0)
        out = {"assets": [{"name": n, "id": n} for n in names[start:start + size]]}
        if start + size < len(names):
            out["nextPageToken"] = str(start + size)
        return out

    def computeFeatures(self, params):
        from tests.cloud.ipcch_producer_world import feature_page
        self._request("computeFeatures")
        self.compute_calls.append(params)
        if self.compute_error is not None:
            raise self.compute_error
        return feature_page(self.table, params)


class ProxyEE:
    """The real offline client for graph construction; only server calls are faked."""

    def __init__(self, gcs, listing=(), data=None, rows=None, states=("COMPLETED",), objects=1, start_error=None):
        real = offline_ee()
        self._real, self.data, self.tasks = real, data or FakeData(), []
        proxy = self

        class ListingList(real.List):
            def getInfo(self):
                return [[ms for ms, _ in listing], [i for _, i in listing]]

        class Task:
            def __init__(self, kw):
                self.kw, self.id, self.polls = kw, f"T{len(proxy.tasks)}", 0
                proxy.tasks.append(self)

            def start(self):
                if start_error is not None:
                    raise start_error

            def cancel(self):
                self.cancelled = True

            def status(self):
                state = states[min(self.polls, len(states) - 1)]
                self.polls += 1
                if state == "COMPLETED" and self.polls == 1 or (state == "COMPLETED" and not proxy._written(self)):
                    for k in range(objects):
                        name = f"gs://{self.kw['bucket']}/{self.kw['fileNamePrefix']}{'' if k == 0 else f'-{k}'}.csv"
                        gcs._write(name, (rows or default_rows)(self.kw["selectors"]).to_csv(index=False).encode(), None)
                return {"state": state}

        self.List = ListingList
        self.batch = type("batch", (), {"Export": type("Export", (), {"table": type("table", (), {
            "toCloudStorage": staticmethod(lambda **kw: Task(kw))})})})
        self._gcs = gcs

    def _written(self, task):
        return any(u.startswith(f"gs://{task.kw['bucket']}/{task.kw['fileNamePrefix']}") for u in self._gcs.versions)

    def __getattr__(self, name):
        return getattr(self._real, name)


def default_rows(selectors):
    frame = pd.DataFrame({"admin_code": ["1", "2", "3", "6227"]})
    for c in selectors[1:]:
        frame[c] = 1.0 if c.endswith(("area", "obs_num")) else 2.0
    return frame


def transport(gcs, ee, **kw):
    return EETransport(ee=ee, client=gcs, store=gcs, output_root=ROOT, run_id="run-2026-10-a", poll_seconds=0, **kw)


def daily(month_start, days, collection):
    t0 = datetime.fromisoformat(month_start).replace(tzinfo=timezone.utc)
    return [(int((t0 + timedelta(days=k)).timestamp() * 1000), f"{collection}/{k}") for k in range(days)]


# --------------------------------------------------------------------------- availability


def test_image_times_reuse_the_acquirer_listing_and_accept_daily_multiplicity():
    gcs = FakeGcs()
    coll = "UCSB-CHG/CHIRPS/DAILY"
    t = transport(gcs, ProxyEE(gcs, listing=daily("2026-08-01", 31, coll)))
    times = t.image_times(coll, "precipitation", "2026-08-01", "2026-09-01")
    assert len(times) == 31 and times == sorted(times)               # 31 images in one month: not "ambiguous"
    with pytest.raises(EETransportError, match="malformed image entry"):
        transport(gcs, ProxyEE(gcs, listing=[(1, "OTHER/x")])).image_times(coll, "b", "2026-08-01", "2026-09-01")


def test_missing_assets_reports_only_definitive_absence():
    gcs = FakeGcs()
    folder = "projects/p/assets"
    here, gone = f"{folder}/A", f"{folder}/B"
    data = FakeData(present=[here])
    assert transport(gcs, ProxyEE(gcs, data=data)).missing_assets([here, gone]) == [gone]   # parent listing omits B
    listed_unreadable = FakeData(present=[here], listed=[here, gone])
    with pytest.raises(EETransportError, match="exists but is not readable"):
        transport(gcs, ProxyEE(gcs, data=listed_unreadable)).missing_assets([gone])
    cannot_list = FakeData(present=[here], list_error=Exception("Permission denied on folder"))
    with pytest.raises(EETransportError, match="cannot list"):
        transport(gcs, ProxyEE(gcs, data=cannot_list)).missing_assets([gone])
    for err in (Exception("HTTP 403: caller does not have permission"), TimeoutError("deadline exceeded"),
                Exception("Please authorize access to your Earth Engine account")):
        d = FakeData(get_error=err)
        with pytest.raises(EETransportError, match="not treated as absent"):
            transport(gcs, ProxyEE(gcs, data=d)).missing_assets([here])
        assert d.list_calls == []                                    # never resolved as absence


def test_inaccessible_current_table_is_a_failure_not_unavailability():
    gcs = FakeGcs()
    refs = ct.TableRefs(root="projects/p/assets/")
    base = [refs.asset(refs.vi_baseline.format(label="TERRA", part=k)) for k in range(1, 5)]
    current = refs.asset(refs.vi_current.format(label="TERRA", year=2026))
    absent = transport(gcs, ProxyEE(gcs, data=FakeData(present=base)))
    out = ct.VegetationProvider(absent, refs=refs, admins=["1"]).fetch("terra", "2026-08")
    assert out.status == "unavailable" and current in out.detail      # definitively absent: ordinary unavailability
    hidden = transport(gcs, ProxyEE(gcs, data=FakeData(present=base, listed=base + [current])))
    with pytest.raises(cl.ClimateProcessingFailure, match="exists but is not readable"):
        ct.VegetationProvider(hidden, refs=refs, admins=["1"]).fetch("terra", "2026-08")


# --------------------------------------------------------------------------- export and read


def test_export_is_create_only_pinned_by_generation_and_read_exactly():
    gcs = FakeGcs()
    ee = ProxyEE(gcs)
    t = transport(gcs, ee)
    fc = ee.FeatureCollection("projects/p/assets/A")
    ref = t.export_table(fc, ["admin_code", "x_sum"], "ipcch_test_202608")
    uri, gen = ref.split("#")
    assert uri == f"{ROOT}/ipcch_exports/run-2026-10-a/tables/ipcch_test_202608.csv" and gen == "1"
    assert ee.tasks[0].kw["fileFormat"] == "CSV" and ee.tasks[0].kw["selectors"] == ["admin_code", "x_sum"]
    assert gcs.json(f"{ROOT}/ipcch_exports/run-2026-10-a/tasks/ipcch_test_202608.json")["task_id"] == "T0"
    frame = t.read_table(ref)
    assert frame["admin_code"].tolist() == ["1", "2", "3", "6227"] and t.receipts[-1]["kind"] == "read"
    gcs._write(uri, b"admin_code,x_sum\n1,9\n", None)                  # a later overwrite never changes the pinned read
    assert t.read_table(ref)["x_sum"].tolist() == [2.0] * 4
    with pytest.raises(EETransportError, match="already reserved"):
        t.export_table(fc, ["admin_code", "x_sum"], "ipcch_test_202608")
    assert len(ee.tasks) == 1                                                  # no second submission
    assert gcs.json(f"{ROOT}/ipcch_exports/run-2026-10-a/tasks/ipcch_test_202608.json")["state"] == "completed"


@pytest.mark.parametrize("kw,match", [({"states": ("RUNNING", "FAILED")}, "FAILED"),
                                      ({"objects": 2}, "expected exactly one CSV"),
                                      ({"start_error": RuntimeError("quota")}, "start failed")])
def test_export_failures_block(kw, match):
    gcs = FakeGcs()
    ee = ProxyEE(gcs, **kw)
    with pytest.raises(EETransportError, match=match):
        transport(gcs, ee).export_table(ee.FeatureCollection("projects/p/assets/A"), ["admin_code"], "d")


def test_no_export_inside_the_deadline_cleanup_reserve():
    gcs = FakeGcs()
    ee = ProxyEE(gcs)
    now = datetime(2026, 10, 31, tzinfo=timezone.utc)
    t = transport(gcs, ee, deadline_utc=now + timedelta(seconds=600), clock=lambda: now)
    with pytest.raises(EETransportError, match="cleanup reserve"):
        t.export_table(ee.FeatureCollection("projects/p/assets/A"), ["admin_code"], "d")
    assert ee.tasks == []


def test_asset_tables_read_without_geometry_and_canonical_admin_codes():
    gcs = FakeGcs()
    d = FakeData(table=pd.DataFrame({"geo": [None, None], "admin_code": [1.0, 2], "v": [0.5, 0.25]}))
    t = transport(gcs, ProxyEE(gcs, data=d))
    frame = t.read_asset_table("projects/p/assets/T")
    assert list(frame.columns) == ["admin_code", "v"] and frame["admin_code"].tolist() == ["1", "2"]
    assert "fileFormat" not in d.compute_calls[0] and d.compute_calls[0]["pageSize"] == 1000     # explicit pages
    for bad in (FakeData(table=pd.DataFrame({"admin_code": [1.5]})), FakeData(table=pd.DataFrame()),
                FakeData(compute_error=Exception("User memory limit exceeded"))):
        with pytest.raises(EETransportError):
            transport(gcs, ProxyEE(gcs, data=bad)).read_asset_table("projects/p/assets/T")


def test_monthly_provider_through_the_transport_saves_exact_roster(tmp_path):
    gcs = FakeGcs()
    refs = ce.AssetRefs(root="projects/p/assets/")
    data = FakeData(present=refs.required("rain_anomz", "chirps"))
    ee = ProxyEE(gcs, listing=daily("2026-08-01", 31, ce.FAMILIES["rain_anomz"][2]["chirps"]["collection"]), data=data)
    t = transport(gcs, ee)
    provider = ce.MonthlyEEProvider(t, refs=refs)
    table = VersionedTable(LocalObjectStore(tmp_path), StoreRoot("real", "gs://b/ipcch-v2/real"),
                           cl.table_name("prcp_anom", cl.MONTHLY))
    table.commit(pd.DataFrame([{"admin_code": a, "month": "2026-07", "value": 0.0, "n_sources": 3, "ens_sd": 0.0,
                                "method_id": "accepted"} for a in ("1", "2", "3")]), {"action": "initialise"},
                 expected_generation="0")
    fetch = provider.bound("prcp_anom")
    only_chirps = lambda source, month: fetch(source, month) if source == "chirps" else \
        cl.SourceOutcome(source, "unavailable", detail="not in this test")
    rep = cl.update_monthly(table, "prcp_anom", origin="2026-08", roster=["1", "2", "3"], fetch=only_chirps,
                            declared_extra=["6227"])
    assert rep["saved"] == ["2026-08"] and rep["months"]["2026-08"]["dropped_out_of_roster"] == {"chirps": 1}
    assert sorted(cl.read_monthly(table)[0].query("month == '2026-08'")["admin_code"]) == ["1", "2", "3"]
    assert [r["kind"] for r in t.receipts] == ["image_times", "missing_assets", "export", "read"]
    assert "Image.reduceRegions" in ee.serializer.toJSON(ee.tasks[0].kw["collection"])        # the real ported graph


def test_failed_export_is_never_resubmitted_under_the_same_run_and_description():
    gcs = FakeGcs()
    ee = ProxyEE(gcs, states=("RUNNING", "FAILED"))
    t = transport(gcs, ee)
    fc = ee.FeatureCollection("projects/p/assets/A")
    with pytest.raises(EETransportError, match="FAILED"):
        t.export_table(fc, ["admin_code"], "d")
    rec = gcs.json(f"{ROOT}/ipcch_exports/run-2026-10-a/tasks/d.json")
    assert rec["state"] == "FAILED" and rec["task_id"] == "T0"
    with pytest.raises(EETransportError, match="already reserved"):
        t.export_table(fc, ["admin_code"], "d")
    assert len(ee.tasks) == 1


def test_timeout_bounds_every_sleep_cancels_and_records():
    gcs = FakeGcs()
    ee = ProxyEE(gcs, states=("RUNNING",))
    now, sleeps = [0.0], []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds
    t = EETransport(ee=ee, client=gcs, store=gcs, output_root=ROOT, run_id="r", timeout_seconds=100, poll_seconds=60,
                    sleep=sleep, monotonic=lambda: now[0])
    with pytest.raises(EETransportError, match="timed out.*cancelled"):
        t.export_table(ee.FeatureCollection("projects/p/assets/A"), ["admin_code"], "d")
    assert sleeps == [60, 40] and getattr(ee.tasks[0], "cancelled", False)    # never sleeps past the budget
    rec = gcs.json(f"{ROOT}/ipcch_exports/r/tasks/d.json")
    assert rec["state"] == "timeout" and rec["cancel"] == "cancelled" and rec["task_id"] == "T0"
    # the authorization deadline (minus the cleanup reserve) bounds the wait too
    gcs2, ee2 = FakeGcs(), ProxyEE(FakeGcs(), states=("RUNNING",))
    start = datetime(2026, 10, 31, tzinfo=timezone.utc)
    now2, sleeps2 = [0.0], []
    t2 = EETransport(ee=ee2, client=gcs2, store=gcs2, output_root=ROOT, run_id="r", poll_seconds=60,
                     deadline_utc=start + timedelta(seconds=930), clock=lambda: start,
                     sleep=lambda x: (sleeps2.append(x), now2.__setitem__(0, now2[0] + x)), monotonic=lambda: now2[0])
    with pytest.raises(EETransportError, match="timed out"):
        t2.export_table(ee2.FeatureCollection("projects/p/assets/A"), ["admin_code"], "d")
    assert sleeps2 == [30]


def test_started_task_is_cancelled_when_its_id_cannot_be_persisted():
    gcs = FakeGcs()
    ee = ProxyEE(gcs, states=("RUNNING",))
    writes = []
    real = gcs.write_text

    def flaky(uri, content, *, if_generation_match=None):
        writes.append(uri)
        if len(writes) == 2:
            raise RuntimeError("503 backend error")
        return real(uri, content, if_generation_match=if_generation_match)
    gcs.write_text = flaky
    with pytest.raises(EETransportError, match="could not be persisted.*cancelled"):
        transport(gcs, ee).export_table(ee.FeatureCollection("projects/p/assets/A"), ["admin_code"], "d")
    assert getattr(ee.tasks[0], "cancelled", False)


def test_deadline_reached_during_reservation_submits_nothing():
    gcs = FakeGcs()
    ee = ProxyEE(gcs)
    start = datetime(2026, 10, 31, tzinfo=timezone.utc)
    ticks = iter([start, start + timedelta(seconds=200)] + [start + timedelta(seconds=200)] * 10)
    t = transport(gcs, ee, deadline_utc=start + timedelta(seconds=1000), clock=lambda: next(ticks))
    with pytest.raises(EETransportError, match="before submission; not submitted"):
        t.export_table(ee.FeatureCollection("projects/p/assets/A"), ["admin_code"], "d")
    assert ee.tasks == []
    assert gcs.json(f"{ROOT}/ipcch_exports/run-2026-10-a/tasks/d.json")["state"] == "deadline_before_submit"


def test_start_with_lost_response_keeps_the_known_task_id_and_cancels():
    gcs = FakeGcs()
    ee = ProxyEE(gcs, start_error=ConnectionError("response lost"))
    t = transport(gcs, ee)
    with pytest.raises(EETransportError, match=r"start failed \(request None, task T0; cancelled\)"):
        t.export_table(ee.FeatureCollection("projects/p/assets/A"), ["admin_code"], "d")
    assert getattr(ee.tasks[0], "cancelled", False)
    rec = gcs.json(f"{ROOT}/ipcch_exports/run-2026-10-a/tasks/d.json")
    assert rec["state"] == "start_failed" and rec["task_id"] == "T0" and rec["cancel"] == "cancelled"
    assert t.receipts[-1]["kind"] == "export_start_failed" and t.receipts[-1]["task_id"] == "T0"
    with pytest.raises(EETransportError, match="already reserved"):                 # never resubmitted automatically
        t.export_table(ee.FeatureCollection("projects/p/assets/A"), ["admin_code"], "d")
    assert len(ee.tasks) == 1


def test_persist_and_cancel_failure_still_reports_the_task_id():
    gcs = FakeGcs()
    ee = ProxyEE(gcs, states=("RUNNING",))
    real = gcs.write_text
    writes = []

    def flaky(uri, content, *, if_generation_match=None):
        writes.append(uri)
        if len(writes) >= 2:
            raise RuntimeError("503 backend error")
        return real(uri, content, if_generation_match=if_generation_match)
    gcs.write_text = flaky
    t = transport(gcs, ee)

    def broken_cancel():
        raise RuntimeError("cancel rejected")
    fc = ee.FeatureCollection("projects/p/assets/A")
    real_export = ee.batch.Export.table.toCloudStorage

    def export(**kw):
        task = real_export(**kw)
        task.cancel = broken_cancel
        return task
    ee.batch.Export.table.toCloudStorage = staticmethod(export)
    with pytest.raises(EETransportError, match=r"task T0 id could not be persisted.*cancel_failed"):
        t.export_table(fc, ["admin_code"], "d")
    untracked = [r for r in t.receipts if r["kind"] == "export_untracked"]
    assert untracked and untracked[0]["task_id"] == "T0" and untracked[0]["cancel"].startswith("cancel_failed")


def test_real_providers_route_every_base_through_the_one_transport(tmp_path):
    from cloud.ipcch import climate_run
    gcs = FakeGcs()
    t = transport(gcs, ProxyEE(gcs, data=FakeData()))
    windows = pd.DataFrame({"admin_code": ["1"], "season_year": [2026], "season": ["s1"], "gs_start_date": ["2026-03-01"],
                            "gs_end_date_exclusive": ["2026-07-01"]})
    p = climate_run.real_providers(t, origin="2026-08", roster=[1, 2, 3], calendar_windows=windows, asset_root="projects/x/assets/")
    assert all(callable(p.monthly(b)) and callable(p.seasonal(b)) for b in cl.BASES)
    # raster base: the transport's listing has no images -> the provider reports unavailability (not a fake value)
    out = p.monthly("prcp_anom")("chirps", "2026-08")
    assert out.status == "unavailable" and t.receipts[-1]["kind"] == "image_times"
    # S2E3 / S2C3 table bases: private assets definitively absent through the transport -> blocking failures
    with pytest.raises(cl.ClimateProcessingFailure, match="S2E3 baseline"):
        p.monthly("evi_anom")("terra", "2026-08")
    with pytest.raises(cl.ClimateProcessingFailure, match="S2C3"):
        p.monthly("spi03")("chirps", "2026-08")
    assert [r["kind"] for r in t.receipts].count("missing_assets") >= 2


def test_seasonal_factory_through_the_transport_saves_a_completed_season(tmp_path):
    """Successful integration: real_providers -> SeasonalEEProvider -> EETransport (listing, private-asset metadata,
    reserved create-only export, pinned read) -> climate.update_seasonal saves the season for the requested areas."""
    from cloud.ipcch import climate_ee as ce
    from cloud.ipcch import climate_ee_seasonal as cs
    from cloud.ipcch import climate_run

    def rows(selectors):
        f = pd.DataFrame({"admin_code": ["1", "2"]})
        for c in selectors[1:]:
            f[c] = 1.0 if c == "calendar_valid" else 122.0 if c == "duration" else 10.0 if c.endswith("_area") \
                else 5.0 if c.endswith("_num") else 1220.0
        return f
    gcs = FakeGcs()
    refs = ce.AssetRefs(root="projects/p/assets/")
    cpc = ce.TEMP_SOURCES["cpc"]["collection"]
    ee = ProxyEE(gcs, listing=daily("2026-03-01", 160, cpc), data=FakeData(present=refs.required("temperature", "cpc")),
                 rows=rows)
    t = transport(gcs, ee)
    windows = pd.DataFrame({"admin_code": ["1", "2"], "season_year": [2026, 2026], "season": ["s1", "s1"],
                            "gs_start_date": ["2026-03-01", "2026-03-01"], "gs_end_date_exclusive": ["2026-07-01", "2026-07-01"]})
    p = climate_run.real_providers(t, origin="2026-07", roster=["1", "2"], calendar_windows=windows,
                                   asset_root="projects/p/assets/")
    era5 = lambda source, year, season, win: cl.SourceOutcome(source, "unavailable", detail="not in this test")
    fetch = lambda source, year, season, win: p.seasonal("gdd")(source, year, season, win) if source == "cpc" \
        else era5(source, year, season, win)
    table = VersionedTable(LocalObjectStore(tmp_path), StoreRoot("real", "gs://b/ipcch-v2/real"), cl.table_name("gdd", cl.SEASONAL))
    rep = cl.update_seasonal(table, "gdd", origin="2026-07", roster=["1", "2"], windows=windows, fetch=fetch)
    assert rep["saved"] == ["2026-s1"]
    saved = cl.read_seasonal(table)[0]
    assert saved["admin_code"].tolist() == ["1", "2"] and saved["value"].tolist() == [0.5, 0.5]
    assert saved["n_sources"].tolist() == [1, 1]
    kinds = [r["kind"] for r in t.receipts]
    assert kinds == ["image_times", "missing_assets", "export", "read"]
    assert "Image.reduceRegion" in ee.serializer.toJSON(ee.tasks[0].kw["collection"])        # per-feature temperature graph
    assert ee.tasks[0].kw["description"].startswith("run-2026-10-a_ipcch_gs_temperature_cpc_2026_s1")


# --------------------------------------------------------------------------- task 10-30: explicit pages, bounded requests


def deadline_transport(gcs, data, seconds, clock):
    return transport(gcs, ProxyEE(gcs, data=data), deadline_utc=NOW + timedelta(seconds=seconds),
                     clock=lambda: clock["t"])


NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


def test_reads_page_explicitly_with_retries_disabled_and_settings_restored(monkeypatch):
    import cloud.ipcch.ee_transport as et
    monkeypatch.setattr(et, "READ_PAGE_SIZE", 2)
    gcs, clock = FakeGcs(), {"t": NOW}
    d = FakeData(table=pd.DataFrame({"admin_code": [1, 2, 3, 4, 5], "v": [0.1, None, 0.3, 0.4, 0.5]}))
    frame = deadline_transport(gcs, d, 3600, clock).read_asset_table("projects/p/assets/T")
    assert frame["admin_code"].tolist() == ["1", "2", "3", "4", "5"] and frame["v"].isna().tolist() == [False, True] + [False] * 3
    assert [c.get("pageToken") for c in d.compute_calls] == [None, "2", "4"]
    assert d.seen == [("computeFeatures", 60000, 0)] * 3              # one capped request each, no SDK retries
    assert (d.deadline_ms, d.max_retries) == (0, 5)                   # previous SDK settings restored


def test_the_deadline_is_rechecked_between_read_pages(monkeypatch):
    import cloud.ipcch.ee_transport as et
    monkeypatch.setattr(et, "READ_PAGE_SIZE", 2)
    gcs, clock = FakeGcs(), {"t": NOW}
    d = FakeData(table=pd.DataFrame({"admin_code": [1, 2, 3, 4, 5]}))
    d.on_request = lambda name: clock.__setitem__("t", clock["t"] + timedelta(seconds=60))   # each page takes 60 s
    t = deadline_transport(gcs, d, 900 + 90, clock)                   # 90 s before the cleanup reserve
    with pytest.raises(EETransportError, match="page 3: run deadline cleanup reserve reached; not started"):
        t.read_asset_table("projects/p/assets/T")
    assert len(d.compute_calls) == 2 and [s[1] for s in d.seen] == [60000, 30000]   # capped, then what was left
    assert (d.deadline_ms, d.max_retries) == (0, 5)


def test_listing_pages_keep_absence_definitive(monkeypatch):
    import cloud.ipcch.ee_transport as et
    monkeypatch.setattr(et, "LIST_PAGE_SIZE", 1)
    gcs = FakeGcs()
    folder = "projects/p/assets"
    here, hidden, gone = f"{folder}/A", f"{folder}/Z", f"{folder}/B"
    d = FakeData(present=[here], listed=[here, hidden])               # Z exists (2nd page) but is unreadable
    t = transport(gcs, ProxyEE(gcs, data=d))
    with pytest.raises(EETransportError, match="exists but is not readable"):
        t.missing_assets([hidden])
    assert t.missing_assets([gone]) == [gone] and d.list_calls == [folder, folder]   # both pages, listed once
    monkeypatch.setattr(et, "MAX_PAGES", 1)
    with pytest.raises(EETransportError, match="exceeded 1 pages; absence not established"):
        transport(gcs, ProxyEE(gcs, data=FakeData(present=[here], listed=[here, hidden]))).missing_assets([gone])


def test_bounded_requests_restore_sdk_settings_when_the_request_fails():
    gcs, clock = FakeGcs(), {"t": NOW}
    d = FakeData(get_error=TimeoutError("deadline exceeded"))
    with pytest.raises(EETransportError, match="not treated as absent"):
        deadline_transport(gcs, d, 3600, clock).missing_assets(["projects/p/assets/A"])
    assert d.seen == [("getAsset", 60000, 0)] and (d.deadline_ms, d.max_retries) == (0, 5)


class RealTaskEE:
    """Offline client whose toAsset returns a REAL ee.batch.Task; its single export RPC (ee.data.exportTable) is
    controlled per test, while metadata calls go to ``data``."""

    def __init__(self, data):
        real = offline_ee()
        self._real, self.data, self.created = real, data, []
        proxy = self

        def to_asset(**kw):
            task = real.batch.Task(None, real.batch.Task.Type.EXPORT_TABLE, real.batch.Task.State.UNSUBMITTED,
                                   config=dict(kw))
            proxy.created.append(task)
            return task
        self.batch = type("batch", (), {"Export": type("Export", (), {"table": type("table", (), {
            "toAsset": staticmethod(to_asset)})})})

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_real_task_start_is_bounded_and_a_lost_response_keeps_its_request_identity(monkeypatch):
    real = offline_ee()
    gcs, clock = FakeGcs(), {"t": NOW}
    d = FakeData()
    seen = []

    def lost(request_id, config):                    # the export RPC: settings in effect, then the response is lost
        seen.append((request_id, d.deadline_ms, d.max_retries, config["assetId"]))
        raise TimeoutError("response lost")
    monkeypatch.setattr(real.data, "exportTable", lost)
    ee = RealTaskEE(d)
    t = transport(gcs, ee, deadline_utc=NOW + timedelta(seconds=3600), clock=lambda: clock["t"])
    with pytest.raises(EETransportError, match="start failed .*not cancellable: no operation known"):
        t.submit_asset_export(real.FeatureCollection("projects/p/assets/A"), "projects/p/assets/OUT_1", "d1")
    (request_id, ms, retries, asset), = seen
    assert request_id and (ms, retries) == (60000, 0) and asset == "projects/p/assets/OUT_1"   # bounded, no SDK retry
    assert (d.deadline_ms, d.max_retries) == (0, 5)                                            # restored after failure
    rec = json.loads(gcs.read_text(f"{ROOT}/ipcch_exports/run-2026-10-a/tasks/d1.json"))
    assert rec["state"] == "start_failed" and rec["request_id"] == request_id and rec["task_id"] is None
    assert rec["operation_name"] is None and rec["cancel"].startswith("not cancellable")

    def accepted(request_id, config):
        return {"name": f"projects/p/operations/{request_id.upper()}"}
    monkeypatch.setattr(real.data, "exportTable", accepted)
    handle = t.submit_asset_export(real.FeatureCollection("projects/p/assets/A"), "projects/p/assets/OUT_2", "d2")
    rec = json.loads(gcs.read_text(f"{ROOT}/ipcch_exports/run-2026-10-a/tasks/d2.json"))
    assert rec["state"] == "submitted" and rec["operation_name"] == f"projects/p/operations/{rec['request_id'].upper()}"
    assert rec["task_id"] == rec["request_id"].upper() and handle.record["task_id"] == rec["task_id"]


def test_expired_budget_refuses_the_export_start_itself(monkeypatch):
    real = offline_ee()
    gcs, clock = FakeGcs(), {"t": NOW}
    calls = []
    monkeypatch.setattr(real.data, "exportTable", lambda request_id, config: calls.append(request_id))
    t = transport(gcs, RealTaskEE(FakeData()), deadline_utc=NOW + timedelta(seconds=960), clock=lambda: clock["t"])
    real_bounded = t._bounded

    def late(what, call, **kw):                      # the budget runs out between reservation and the start RPC
        if what.endswith(" start"):
            clock["t"] = NOW + timedelta(seconds=61)
        return real_bounded(what, call, **kw)
    t._bounded = late
    with pytest.raises(EETransportError, match="start failed"):
        t.submit_asset_export(real.FeatureCollection("projects/p/assets/A"), "projects/p/assets/OUT_3", "d3")
    assert calls == []                                                   # no export RPC was made
    rec = json.loads(gcs.read_text(f"{ROOT}/ipcch_exports/run-2026-10-a/tasks/d3.json"))
    assert rec["state"] == "start_failed" and "cleanup reserve reached; not started" in rec["error"]
    assert rec["request_id"] is None and rec["cancel"].endswith("the start request was not sent")
