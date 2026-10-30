"""Task 10-29 CP4: v2 IPCCH publication end to end on fake stores - delivery assembly bound to the current snapshot,
byte-for-byte inherited FEWS NET member under its own months, actual verifier, activation, candidate, conflict, smoke
root isolation (R17, R18, R36, R37, R47, R63, R66, FCC)."""

import copy
import dataclasses
import hashlib
import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import binding as bd
from cloud.ipcch import delivery_v2 as dv
from cloud.ipcch import publication as pub
from cloud.ipcch import release_v2 as rv
from tests.cloud.test_ipcch_delivery_member import scored_batch
from tests.cloud.test_ipcch_generation import package  # noqa: F401 (fixture)

PROD, SMOKE = "gs://ops-delivery/prod-root", "gs://ops-delivery-smoke/smoke-root"
NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
REQ = {"uri": "gs://ops/requests/r/run_manifest.json", "generation": "1", "sha256": "a" * 64}


def seed_legacy_fews(store, origin="2026-09"):
    """A legacy v1 release whose delivery holds a FEWS NET member (own origin, targets origin + 0/6/12)."""
    files = {"fewsnet/polygons.geojson": '{"type":"FeatureCollection","features":[]}\n',
             "fewsnet/country_population_reference.csv": "ISO3,country\nAAA,Aland\n",
             "fewsnet/model_package/0m/model.json": '{"m": 0}\n',
             "reports/fewsnet_diagnostic_availability.csv": "model_system,horizon_months,level,entity_id,diagnostic_family,"
                                                            "status,reason,evidence_ref\nfewsnet,0,polygon,1,polygon_confidence,"
                                                            "unavailable,missing_evidence,\n",
             "reports/fewsnet_feature_fill_audit.csv": "system,polygon_id,fill_method\nfewsnet,1,observed\n"}
    y, m = (int(x) for x in origin.split("-"))
    for lead in (0, 6, 12):
        o = y * 12 + m - 1 + lead
        files[f"scopes/{lead}m/fewsnet/polygon_predictions.csv"] = (
            f"admin_code,probability_crisis,feature_month,target_month\n1,0.4,{origin},{o // 12:04d}-{o % 12 + 1:02d}\n")
    base = f"{PROD}/deliveries/legacy-fews"
    for rel, text in files.items():
        store.write_text(f"{base}/{rel}", text, if_generation_match=0)
    inv = json.dumps({"files": [{"path": r, "sha256": hashlib.sha256(t.encode()).hexdigest()} for r, t in sorted(files.items())]})
    meta = store.write_text(f"{base}/manifest.json", inv, if_generation_match=0)
    manifest_ref = {"uri": f"{base}/manifest.json", "generation": meta.generation, "sha256": hashlib.sha256(inv.encode()).hexdigest()}
    record = {"run_id": "legacy-fews", "origin_month": origin, "manifest": manifest_ref, "archive": {"uri": "x"},
              "execution": {"scored_systems": ["fewsnet"], "inherited_systems": []}}
    rec = store.write_text(f"{PROD}/prod/releases/legacy-fews/release.json", json.dumps(record), if_generation_match=0)
    store.write_text(pub.pointer_uri(PROD, "prod"), json.dumps({"run_id": "legacy-fews", "release_record":
                                                                f"{PROD}/prod/releases/legacy-fews/release.json",
                                                                "release_record_generation": rec.generation}))
    return files


def real_inputs(kw):
    """The smoke-scored batch relabelled real for publication-mechanics tests (member writer records the mode)."""
    kw = copy.copy(kw)
    kw["manifest"] = {**kw["manifest"], "mode": "real", "designation": "real", "execution_month": "2026-10",
                      "feature_origin": "2026-08",
                      "horizons": {h: {**v, "target_month": {"2": "2026-10", "8": "2027-04", "14": "2027-10"}[h]}
                                   for h, v in kw["manifest"]["horizons"].items()}}
    kw["scored"] = {h: {**v, "predictions": v["predictions"].assign(
        mode="real", feature_period="2026-08", target_period=kw["manifest"]["horizons"][str(h)]["target_month"])}
        for h, v in kw["scored"].items()}
    env = json.load(open(kw["envelope_path"]))                    # an ACCEPTED envelope over the same package (R51)
    env.update(status="accepted", acceptor="test acceptor", accepted_at="2026-10-30", envelope_version=2,
               envelope_id=env["envelope_id"].replace("envelope-v1", "envelope-v2"))
    env["handoff"]["acceptance_entries_sha256"] = "d" * 64
    accepted = kw["envelope_path"].replace(".json", "-accepted.json")
    sha = bd.write_envelope(env, accepted)
    kw["envelope_path"] = accepted
    kw["binding"] = dataclasses.replace(kw["binding"], mode="real", fixture_root=None, status="accepted",
                                        envelope_sha256=sha, envelope_id=env["envelope_id"])
    return kw


def publish(store, kw, run_id, expected, publication="current", mode="real", root=PROD, ns="prod", tmp=None):
    return rv.publish_ipcch_run(store, root, namespace=ns, run_id=run_id, mode=mode, publication=publication,
                                expected_pointer_generation=expected, request_ref=REQ, member_inputs=kw,
                                workdir=str(tmp), now=NOW)


def test_first_real_ipcch_publication_inherits_legacy_fews_byte_for_byte_and_activates(tmp_path, package):
    kw = real_inputs(scored_batch(tmp_path, package))
    store = LocalObjectStore(tmp_path / "releases")
    files = seed_legacy_fews(store)
    g = pub.read_current(store, PROD, "prod")["generation"]
    out = publish(store, kw, "ipcch-oct", g, tmp=tmp_path)
    assert out["status"] == "published" and out["activation"]["activated_by_run"] == "ipcch-oct"
    rec = pub.read_current(store, PROD, "prod")["record"]
    assert rec["systems"]["fewsnet"]["origin_month"] == "2026-09" and rec["systems"]["ipcch"]["execution_month"] == "2026-10"
    base = f"{PROD}/deliveries/ipcch-oct"
    for rel, text in files.items():                                          # byte-for-byte inherited member
        assert store.read_text(f"{base}/{rel}") == text
    merged = pd.read_csv(store_path(tmp_path, f"{base}/reports/diagnostic_availability.csv"), dtype=str, keep_default_na=False)
    months = merged.groupby("member_system")[["member_execution_month", "member_feature_month"]].first()
    assert months.loc["fewsnet"].tolist() == ["2026-09", "2026-09"] and months.loc["ipcch"].tolist() == ["2026-10", "2026-08"]
    # the next IPCCH publication inherits the (already inherited) FEWS member under its own months: inherit-of-inherit
    g2 = pub.read_current(store, PROD, "prod")["generation"]
    out2 = publish(store, kw, "ipcch-oct-rerun", g2, tmp=tmp_path)
    assert out2["status"] == "published"
    rec2 = pub.read_current(store, PROD, "prod")["record"]
    assert rec2["systems"]["fewsnet"]["delivery"] == rec["systems"]["fewsnet"]["delivery"]
    assert rec2["activation"]["activated_by_run"] == "ipcch-oct"                 # activation never re-set or cleared


def store_path(tmp_path, uri):
    return tmp_path / "releases" / uri.removeprefix("gs://")


def test_tampered_inherited_member_refuses_publication(tmp_path, package):
    kw = real_inputs(scored_batch(tmp_path, package))
    store = LocalObjectStore(tmp_path / "releases")
    seed_legacy_fews(store)
    store.write_text(f"{PROD}/deliveries/legacy-fews/scopes/6m/fewsnet/polygon_predictions.csv", "tampered\n")
    g = pub.read_current(store, PROD, "prod")["generation"]
    with pytest.raises(dv.DeliveryError, match="differs from the source inventory"):
        publish(store, kw, "ipcch-oct", g, tmp=tmp_path)
    assert pub.read_current(store, PROD, "prod")["record"]["run_id"] == "legacy-fews"


def test_moved_pointer_fails_without_rebase_and_candidate_never_moves_it(tmp_path, package):
    kw = real_inputs(scored_batch(tmp_path, package))
    store = LocalObjectStore(tmp_path / "releases")
    seed_legacy_fews(store)
    g = pub.read_current(store, PROD, "prod")["generation"]
    out = publish(store, kw, "stale", str(int(g) + 5), tmp=tmp_path)
    assert out["status"] == "publication_failed" and out["stage"] == "precheck"
    cand = publish(store, kw, "cand", g, publication="candidate", tmp=tmp_path)
    assert cand["status"] == "candidate_written" and pub.read_current(store, PROD, "prod")["generation"] == g
    assert json.loads(store.read_text(cand["candidate_record"]))["activation"] is None


def test_smoke_publishes_under_its_own_root_only(tmp_path, package):
    kw = scored_batch(tmp_path, package)                                    # genuinely smoke
    store = LocalObjectStore(tmp_path / "releases")
    out = publish(store, kw, "smoke-1", "0", mode="smoke", root=SMOKE, ns="smoke", tmp=tmp_path)
    assert out["status"] == "published" and out["activation"] is None and out["members"] == ["ipcch"]
    assert pub.read_current(store, PROD, "prod")["generation"] == "0"
    assert not [p for p in (tmp_path / "releases").rglob("*") if p.is_file() and "prod-root" in str(p)]


@pytest.mark.parametrize("publication", ["current", "candidate"])
@pytest.mark.parametrize("tamper", ["edited_value", "missing_supporting_files"])
def test_edited_or_incomplete_inherited_member_with_regenerated_inventory_is_refused_by_publication(
        tmp_path, package, monkeypatch, tamper, publication):
    """Supervisor repro (6e57972): an inherited FEWS member edited (.4 -> .99) or stripped of package/geometry/sidecars
    AFTER the byte-for-byte copy, with the destination inventory regenerated self-consistently, must be refused by the
    actual verifier inside publication - before any current or candidate mutation."""
    kw = real_inputs(scored_batch(tmp_path, package))
    store = LocalObjectStore(tmp_path / "releases")
    seed_legacy_fews(store)
    before = pub.read_current(store, PROD, "prod")
    real_inherit = dv.inherit

    def tampering_inherit(out, *a, **k):
        rec = real_inherit(out, *a, **k)
        if tamper == "edited_value":
            p = out / "scopes/6m/fewsnet/polygon_predictions.csv"
            p.write_text(p.read_text().replace(",0.4,", ",0.99,"))
        else:
            for rel in ("fewsnet/model_package/0m/model.json", "fewsnet/polygons.geojson",
                        "reports/fewsnet_diagnostic_availability.csv"):
                (out / rel).unlink()
            (out / "reports/fewsnet_diagnostic_availability.csv").write_text(
                "model_system,horizon_months,level,entity_id,diagnostic_family,status,reason,evidence_ref\n")
        return rec
    monkeypatch.setattr(dv, "inherit", tampering_inherit)
    with pytest.raises(dv.DeliveryError, match="differ from (its|the) source inventory"):
        publish(store, kw, "tampered", before["generation"], publication=publication, tmp=tmp_path)
    after = pub.read_current(store, PROD, "prod")
    assert after["generation"] == before["generation"] and after["record"]["run_id"] == "legacy-fews"
    assert not list((tmp_path / "releases").rglob("candidate.json"))
