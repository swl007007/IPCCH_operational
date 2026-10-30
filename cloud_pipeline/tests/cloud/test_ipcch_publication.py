"""Task 10-29: v2 publication core - single pointer, per-system members, activation, candidates, CAS without retry,
R39 recheck, R18, smoke root isolation (R17, R18, R36, R37, R39, R46, R63, R66, FCC)."""

import json
from datetime import datetime, timezone

import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import publication as pub

PROD, SMOKE = "gs://ops-delivery/prod-root", "gs://ops-delivery-smoke/smoke-root"
NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
REQ = {"uri": "gs://ops/requests/r/run_manifest.json", "generation": "1", "sha256": "a" * 64}


def ipcch_member(m="2026-10", mode="real"):
    return {"contract": pub.IPCCH_CONTRACT, "execution_month": m, "feature_origin": "2026-08", "mode": mode,
            "model_horizons": [2, 8, 14], "public_leads": [0, 6, 12], "package": {"combination_id": "c", "envelope_sha256": "e" * 64}}


def fews_member(origin="2026-10"):
    return {"contract": "fewsnet-legacy-scoring", "origin_month": origin, "package": {"suite": "fews-2026-10"}}


def current(store, root=PROD):
    snap = pub.read_current(store, root, "prod")
    return snap


def publish(store, run_id, new, expected, publication="current", mode="real", root=PROD, ns="prod"):
    return pub.publish(store, root, run_id=run_id, namespace=ns, publication=publication, mode=mode,
                       expected_pointer_generation=expected, request_ref=REQ, new_members=new,
                       delivery={"manifest": {"uri": f"{root}/deliveries/{run_id}/manifest.json"}}, now=NOW)


def test_first_real_ipcch_current_activates_and_fews_publication_inherits_and_preserves_it(tmp_path):
    store = LocalObjectStore(tmp_path)
    out = publish(store, "ipcch-run-1", {"ipcch": ipcch_member()}, "0")
    assert out["status"] == "published" and out["activation"]["activated_by_run"] == "ipcch-run-1"
    snap = current(store)
    out2 = publish(store, "fews-run-1", {"fewsnet": fews_member("2026-11")}, snap["generation"])
    rec = current(store)["record"]
    assert rec["activation"]["activated_by_run"] == "ipcch-run-1"                       # carried forward (R37/R46)
    assert rec["systems"]["ipcch"]["execution_month"] == "2026-10"                       # own months, not relabelled
    assert rec["systems"]["ipcch"]["published_by_run"] == "ipcch-run-1"
    assert rec["systems"]["ipcch"]["inherited_from_pointer_generation"] == snap["generation"]
    assert rec["systems"]["fewsnet"]["origin_month"] == "2026-11" and out2["status"] == "published"


def test_candidate_never_moves_the_pointer_or_activates(tmp_path):
    store = LocalObjectStore(tmp_path)
    out = publish(store, "cand-1", {"ipcch": ipcch_member()}, "0", publication="candidate")
    assert out["status"] == "candidate_written" and current(store)["generation"] == "0"
    rec = json.loads(store.read_text(out["candidate_record"]))
    assert rec["publication"] == "candidate" and rec["activation"] is None
    assert publish(store, "real-1", {"fewsnet": fews_member()}, "0")["status"] == "published"
    assert current(store)["record"]["activation"] is None                               # a candidate does not count


def test_cas_conflict_fails_without_retry_and_keeps_the_winner(tmp_path):
    store = LocalObjectStore(tmp_path)
    publish(store, "base", {"fewsnet": fews_member()}, "0")
    g = current(store)["generation"]
    assert publish(store, "fews-a", {"fewsnet": fews_member("2026-11")}, g)["status"] == "published"
    winner = current(store)
    out = publish(store, "ipcch-b", {"ipcch": ipcch_member()}, g)                       # stale expected generation
    assert out["status"] == "publication_failed" and out["stage"] == "precheck"
    assert current(store)["generation"] == winner["generation"]                          # nothing replaced, no rebase
    conflict = json.loads(store.read_text(f"{PROD}/runs/ipcch-b/release_conflict.json"))
    assert conflict["expected_pointer_generation"] == g


def test_r39_recheck_and_r18_all_horizons(tmp_path):
    store = LocalObjectStore(tmp_path)
    publish(store, "ipcch-oct", {"ipcch": ipcch_member("2026-10")}, "0")
    g = current(store)["generation"]
    with pytest.raises(pub.PublicationRefused, match="R39"):
        publish(store, "ipcch-sep", {"ipcch": ipcch_member("2026-09")}, g)
    assert publish(store, "ipcch-sep-cand", {"ipcch": ipcch_member("2026-09")}, g, publication="candidate")["status"] == \
        "candidate_written"                                                             # candidate may use an earlier M
    assert publish(store, "ipcch-oct-rerun", {"ipcch": ipcch_member("2026-10")}, g)["status"] == "published"   # same M ok
    partial = {**ipcch_member("2026-11"), "model_horizons": [2, 8]}
    with pytest.raises(pub.PublicationRefused, match="R18"):
        publish(store, "ipcch-partial", {"ipcch": partial}, current(store)["generation"])


def test_smoke_root_is_isolated_and_never_activates(tmp_path):
    store = LocalObjectStore(tmp_path)
    out = publish(store, "smoke-1", {"ipcch": ipcch_member(mode="smoke")}, "0", mode="smoke", root=SMOKE, ns="smoke")
    assert out["status"] == "published" and out["activation"] is None
    assert pub.read_current(store, PROD, "prod")["generation"] == "0"
    assert not [p for p in tmp_path.rglob("*") if p.is_file() and "prod-root" in str(p)]


def test_legacy_release_records_are_read_as_one_origin_members(tmp_path):
    legacy = {"run_id": "v1-run", "origin_month": "2026-09", "manifest": {"uri": "m"}, "archive": {"uri": "a"},
              "execution": {"scored_systems": ["fewsnet", "ipcch"], "inherited_systems": []}}
    m = pub.members(legacy)
    assert m["ipcch"]["contract"] == pub.LEGACY_CONTRACT and pub.ipcch_execution_month(legacy) == "2026-09"
    assert pub.activation(legacy) is None


def test_pointer_moving_after_the_snapshot_read_is_a_conflict_not_a_rebase(tmp_path, monkeypatch):
    store = LocalObjectStore(tmp_path)
    publish(store, "base", {"fewsnet": fews_member()}, "0")
    g = current(store)["generation"]
    real_read = pub.read_current

    def read_then_race(*a, **k):
        snap = real_read(*a, **k)                                    # bound snapshot (generation g)
        monkeypatch.setattr(pub, "read_current", real_read)
        publish(store, "racer", {"fewsnet": fews_member("2026-12")}, g)   # concurrent winner moves the pointer
        return snap
    monkeypatch.setattr(pub, "read_current", read_then_race)
    out = publish(store, "ipcch-late", {"ipcch": ipcch_member()}, g)
    assert out["status"] == "publication_failed" and out["stage"] == "pointer_write"
    rec = current(store)["record"]
    assert rec["run_id"] == "racer" and "ipcch" not in rec["systems"]                # winner kept; nothing rebased
