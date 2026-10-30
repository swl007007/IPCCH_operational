"""Task 10-29: the concrete EE/GCS transport behind the IPCCH climate providers, driven through fakes of only the
network surfaces (ee.List.getInfo, ee.data, export tasks, storage); graphs are built by the real offline client."""

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

    def getAsset(self, asset_id):
        if self.get_error is not None:
            raise self.get_error
        if asset_id in self.present:
            return {"name": asset_id, "type": "TABLE"}
        raise Exception(AMBIGUOUS.format(asset_id))

    def listAssets(self, params):
        self.list_calls.append(params["parent"])
        if self.list_error is not None:
            raise self.list_error
        names = self.listed if self.listed is not None else self.present
        return {"assets": [{"name": n, "id": n} for n in names if n.startswith(params["parent"] + "/")]}

    def computeFeatures(self, params):
        self.compute_calls.append(params)
        if self.compute_error is not None:
            raise self.compute_error
        return self.table


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
                                      ({"start_error": RuntimeError("quota")}, "could not start")])
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
    assert d.compute_calls[0]["fileFormat"] == "PANDAS_DATAFRAME"
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
