"""Task 10-29 retained stores: versioned HEAD + immutable versions, mode isolation, acceptance manifest (R45),
monthly append without rewrite (R8/R41), GPP unpublished fill and ledger (R9/R49), research-family interval refresh
(R59) and atomic snapshot replacement (R62/FCC8)."""

import numpy as np
import pandas as pd
import pytest

from cloud.common.object_store import GenerationConflict, LocalObjectStore
from cloud.ipcch import retained as rt
from cloud.ipcch.stores import AcceptanceManifest, StoreError, StoreRoot, VersionedTable

ROSTER = {"101", "102", "203"}


@pytest.fixture()
def env(tmp_path):
    store = LocalObjectStore(tmp_path)
    return store, StoreRoot("real", "gs://b/ipcch-v2/real"), StoreRoot("smoke", "gs://b/ipcch-v2/smoke")


def rows(*items):
    return pd.DataFrame(items, columns=["admin_code", "month", "value"])


def test_store_roots_are_mode_isolated():
    with pytest.raises(StoreError):
        StoreRoot("real", "gs://b/ipcch-v2/smoke")
    with pytest.raises(StoreError):
        StoreRoot("test", "gs://b/test")


def test_versions_are_immutable_and_head_cas_is_not_retried(env):
    store, real, smoke = env
    t = VersionedTable(store, real, "gpp_mean")
    first = rt.append_months(t, rows(("101", "2026-07", 1.5)), method_id="m1", roster=ROSTER)
    _, gen = t.head()
    rt.append_months(t, rows(("101", "2026-08", 2.0)), method_id="m1", roster=ROSTER)
    assert store.read_text(first["content"]).count("\n") == 2          # version 1 unchanged
    with pytest.raises(GenerationConflict):
        t.commit(pd.DataFrame({"x": [1]}), {}, expected_generation=gen)   # stale generation: refused
    assert VersionedTable(store, smoke, "gpp_mean").head() == (None, "0")  # smoke never sees real data


def test_append_never_rewrites_and_gpp_fills_only_unpublished_missing(env):
    store, real, _ = env
    t = VersionedTable(store, real, "gpp_mean")
    rt.append_months(t, rows(("101", "2026-06", np.nan), ("102", "2026-06", 3.0)), method_id="v3", roster=ROSTER)
    with pytest.raises(StoreError, match="never rewritten"):
        rt.append_months(t, rows(("102", "2026-06", 4.0)), method_id="v3", roster=ROSTER)
    with pytest.raises(StoreError, match="never rewritten"):                 # missing but not ledger-unpublished
        rt.append_months(t, rows(("101", "2026-06", 4.0)), method_id="v3", roster=ROSTER)
    with pytest.raises(StoreError, match="never rewritten"):                 # unpublished month, existing value
        rt.append_months(t, rows(("102", "2026-06", 4.0)), method_id="v3", roster=ROSTER, gpp_unpublished_months={"2026-06"})
    out = rt.append_months(t, rows(("101", "2026-06", 4.0)), method_id="v3", roster=ROSTER, gpp_unpublished_months={"2026-06"})
    assert out["record"]["filled_unpublished"] == 1
    frame, _ = rt.read_series(t)
    assert frame.set_index(["admin_code", "month"]).loc[("101", "2026-06"), "value"] == 4.0
    assert frame.set_index(["admin_code", "month"]).loc[("102", "2026-06"), "value"] == 3.0


def test_append_validation(env):
    store, real, _ = env
    t = VersionedTable(store, real, "nightlight_mean")
    with pytest.raises(StoreError, match="unknown modeled-area"):
        rt.append_months(t, rows(("999", "2026-07", 1.0)), method_id="m", roster=ROSTER)
    with pytest.raises(StoreError, match="duplicate keys"):
        rt.append_months(t, rows(("101", "2026-07", 1.0), ("101", "2026-07", 2.0)), method_id="m", roster=ROSTER)
    with pytest.raises(StoreError, match="infinite"):
        rt.append_months(t, rows(("101", "2026-07", np.inf)), method_id="m", roster=ROSTER)
    with pytest.raises(StoreError, match="YYYY-MM"):
        rt.append_months(t, rows(("101", "2026-13", 1.0)), method_id="m", roster=ROSTER)
    assert t.head() == (None, "0")                                         # refused: nothing written


def test_gpp_probe_classification_and_ledger(env):
    assert rt.classify_gpp_probe(http_status=404) == "unpublished"
    assert rt.classify_gpp_probe(listed=False) == "unpublished"
    assert rt.classify_gpp_probe(http_status=200) == "published"
    for kw in ({"http_status": 503}, {"error": "timeout"}, {"error": "checksum mismatch"}, {"http_status": None},
               {"http_status": 500, "listed": True}, {"http_status": 503, "listed": False},     # explicit failure blocks
               {"http_status": 404, "listed": True}, {"http_status": 200, "listed": False},     # contradictory
               {"http_status": 404, "error": "read error"}):
        with pytest.raises(rt.GppProcessingFailure):
            rt.classify_gpp_probe(**kw)
    assert rt.classify_gpp_probe(http_status=404, listed=False) == "unpublished"
    assert rt.classify_gpp_probe(http_status=200, listed=True) == "published"
    store, real, _ = env
    ledger = VersionedTable(store, real, "gpp_availability_ledger")
    rt.record_gpp_checks(ledger, [{"month": "2026-06", "status": "unpublished", "checked_at": "2026-08-31", "evidence": "404"}])
    rt.record_gpp_checks(ledger, [{"month": "2026-06", "status": "published", "checked_at": "2027-08-20", "evidence": "200"}])
    assert rt.latest_gpp_status(ledger) == {"2026-06": "published"}


def test_research_family_interval_refresh(env):
    store, real, _ = env
    t = VersionedTable(store, real, "nino34_anom")
    rt.append_months(t, rows(("101", "2026-01", 0.1), ("101", "2026-02", 0.2), ("101", "2026-03", 0.3)), method_id="delivered",
                     roster=ROSTER)
    with pytest.raises(StoreError, match="outside the declared interval"):
        rt.refresh_interval(t, rows(("101", "2026-04", 9.0)), start="2026-02", end="2026-03", roster=ROSTER,
                            source_ref={"sha256": "a" * 64})
    out = rt.refresh_interval(t, rows(("101", "2026-02", 2.0)), start="2026-02", end="2026-03", roster=ROSTER,
                              source_ref={"sha256": "a" * 64})
    frame, _ = rt.read_series(t)
    assert frame[["month", "value"]].values.tolist() == [["2026-01", 0.1], ["2026-02", 2.0]]   # 2026-03 removed (in interval)
    assert out["record"]["coverage_end"] == "2026-02" and out["record"]["replaced_rows"] == 2


def test_snapshot_atomic_replacement_and_warning(env):
    store, real, _ = env
    t = VersionedTable(store, real, "history_snapshot")
    snap = pd.DataFrame([["101", "2026-03", 3, "2026-04", "2026-07"], ["102", "2026-05", 2, "2026-06", "2026-07"]],
                        columns=list(rt.SNAPSHOT_COLUMNS))
    rt.replace_snapshot(t, snap, source_ref={"sha256": "b" * 64})
    smaller = pd.DataFrame([["101", "2026-03", 3, "2026-04", "2026-09"]], columns=list(rt.SNAPSHOT_COLUMNS))
    head = rt.replace_snapshot(t, smaller, source_ref={"sha256": "c" * 64})
    frame, _, _ = t.read({"area_id": str})
    assert list(frame["area_id"]) == ["101"]                                  # absent record removed (FCC8)
    assert rt.snapshot_warning(head, "2026-08") is None
    assert "before O" in rt.snapshot_warning(head, "2026-10")
    bad = smaller.assign(report_month="2026-10")
    with pytest.raises(StoreError, match="after the preparation cutoff"):
        rt.replace_snapshot(t, bad, source_ref={})


def test_acceptance_manifest(env):
    store, real, smoke = env
    acc = AcceptanceManifest(store, real)
    with pytest.raises(StoreError, match="no acceptance record"):
        acc.require("gpp_history.csv", "a" * 64)
    acc.append([{"name": "gpp_history.csv", "sha256": "a" * 64, "source": "training panel GPP_mean v3", "acceptor": "research",
                 "accepted_at": "2026-10-30", "kind": "delivered"}])
    assert acc.require("gpp_history.csv", "a" * 64)["kind"] == "delivered"
    with pytest.raises(StoreError, match="differs from every acceptance record"):
        acc.require("gpp_history.csv", "b" * 64)
    with pytest.raises(StoreError, match="no acceptance record"):
        AcceptanceManifest(store, smoke).require("gpp_history.csv", "a" * 64)   # smoke uses only its own records
    ok = {"name": "x", "sha256": "a" * 64, "source": "s", "acceptor": "a", "accepted_at": "2026-10-30", "kind": "runtime"}
    for bad in ({"kind": "other"}, {"name": " "}, {"source": ""}, {"acceptor": None}, {"accepted_at": "30/10/2026"},
                {"sha256": "A" * 64}, {"sha256": "a" * 63}):
        with pytest.raises(StoreError):
            acc.append([{**ok, **bad}])
    assert len(acc.records()) == 1                                         # refused appends wrote nothing


class FlakyHeadStore(LocalObjectStore):
    """Fails the next HEAD write after its content write succeeded (network error or lost CAS)."""

    fail_head = False

    def write_text(self, uri, content, *, if_generation_match=None):
        if self.fail_head and uri.endswith("/HEAD.json"):
            self.fail_head = False
            raise ConnectionError("simulated HEAD write failure")
        return super().write_text(uri, content, if_generation_match=if_generation_match)


def test_failed_head_move_leaves_an_orphan_that_never_blocks_the_next_commit(tmp_path):
    store = FlakyHeadStore(tmp_path)
    t = VersionedTable(store, StoreRoot("real", "gs://b/ipcch-v2/real"), "wfp_price")
    rt.append_months(t, rows(("101", "2026-07", 1.0)), method_id="m", roster=ROSTER)
    store.fail_head = True
    with pytest.raises(ConnectionError):
        rt.append_months(t, rows(("101", "2026-08", 2.0)), method_id="m", roster=ROSTER)
    head, _ = t.head()
    assert head["version"] == 1                                           # previous version still current
    orphans = [u for u in store.list("gs://b/ipcch-v2/real/wfp_price/versions/") if u != head["content"]]
    assert len(orphans) == 1                                              # orphan preserved as evidence
    out = rt.append_months(t, rows(("101", "2026-08", 2.0)), method_id="m", roster=ROSTER)
    assert out["version"] == 2 and out["content"] != orphans[0]


def test_writers_cas_from_their_own_snapshot(env):
    store, real, _ = env
    t = VersionedTable(store, real, "gpp_mean")
    rt.append_months(t, rows(("101", "2026-07", 1.0)), method_id="m", roster=ROSTER)
    stale_frame, stale_generation = rt.read_series(t)                     # writer A reads
    rt.append_months(t, rows(("102", "2026-07", 5.0)), method_id="m", roster=ROSTER)   # writer B commits
    with pytest.raises(GenerationConflict):                               # A cannot overwrite B with stale data
        t.commit(stale_frame, {}, expected_generation=stale_generation)
    frame, _ = rt.read_series(t)
    assert sorted(frame["admin_code"]) == ["101", "102"]


class MovingHeadStore(LocalObjectStore):
    """Moves HEAD between the two metadata reads of one snapshot."""

    move = None

    def read_text(self, uri):
        text = super().read_text(uri)
        if self.move and uri.endswith("/HEAD.json"):
            move, self.move = self.move, None
            move()
        return text


def test_head_changing_during_read_refuses(tmp_path):
    store = MovingHeadStore(tmp_path)
    t = VersionedTable(store, StoreRoot("real", "gs://b/ipcch-v2/real"), "gpp_mean")
    rt.append_months(t, rows(("101", "2026-07", 1.0)), method_id="m", roster=ROSTER)
    store.move = lambda: rt.append_months(t, rows(("102", "2026-07", 2.0)), method_id="m", roster=ROSTER)
    with pytest.raises(StoreError, match="changed while it was read"):
        t.read()


def test_head_content_outside_its_own_root_is_refused(env):
    store, real, smoke = env
    rt.append_months(VersionedTable(store, real, "gpp_mean"), rows(("101", "2026-07", 1.0)), method_id="m", roster=ROSTER)
    real_head, _ = VersionedTable(store, real, "gpp_mean").head()
    import json
    forged = {**real_head, "content": real_head["content"]}
    store.write_text("gs://b/ipcch-v2/smoke/gpp_mean/HEAD.json", json.dumps(forged))   # smoke HEAD pointing at real data
    with pytest.raises(StoreError, match="outside"):
        VersionedTable(store, smoke, "gpp_mean").read()
