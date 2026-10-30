"""Task 10-29: R45 initialisation of the retained stores from an accepted handoff bundle, and assembly from the stores
equals assembly from the same inputs held in memory (bit-exact round trip through the stores)."""

import hashlib
import json
import os

import numpy as np
import pandas as pd
import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import assembly as asm
from cloud.ipcch import initial
from cloud.ipcch import retained
from cloud.ipcch.stores import AcceptanceManifest, StoreError, StoreRoot, VersionedTable
from cloud.ipcch.vendor import ipcch_compact as cp
from cloud.ipcch import binding as bd
from tests.cloud.ipcch_binding_fixtures import make_package, smoke_envelope
from tests.cloud.test_ipcch_assembly import ORDER, ROSTER, inputs, ords

SMOKE = "gs://b/ipcch-v2/smoke"


def smoke_binding(tmp_path):
    pkg = make_package(tmp_path / "package", ORDER)
    smoke_envelope(tmp_path / "envelope.json", pkg)
    return bd.verify_combination(str(tmp_path / "envelope.json"), str(pkg), mode="smoke", fixture_root=str(tmp_path / "bundle"))


def write_bundle(tmp_path, inp, fixture=True):
    d = tmp_path / "bundle"
    files = {"fixed/roster.csv": pd.DataFrame({"admin_code": list(ROSTER)}), "fixed/static29.csv": inp.static29,
             "fixed/ae_descriptors.csv": inp.descriptors, "fixed/area_identity.csv": inp.identity.assign(iso2="XX", iso3_reference="XXX")[["admin_code", "iso3", "iso2", "lat", "lon", "iso3_reference"]],
             "fixed/season_windows.csv": inp.season_windows, "history/idp_national.csv": inp.idp_national,
             "history/idp_local.csv": inp.idp_local, "history/history_snapshot.csv": inp.snapshot}
    for b in cp.CLIMATE_BASES:
        files[f"history/climate_month_{b}.csv"] = inp.climate_monthly[b].assign(n_sources=1, ens_sd=np.nan, method_id="m")
        w = inp.season_windows.merge(inp.climate_seasonal[b], on=["admin_code", "season_year", "season"])
        files[f"history/climate_gs_{b}.csv"] = w.assign(n_sources=1, ens_sd=np.nan, method_id="m")
    for f in asm.INTERIM_FAMILIES:
        files[f"history/{f}.csv"] = inp.interim[f].assign(method_id="m")
    man = {"schema": initial.SCHEMA, "roster_size": len(ROSTER), "files": {}, **({"fixture": True} if fixture else {})}
    (d / "fixed" / "geometry").mkdir(parents=True, exist_ok=True)
    (d / "fixed" / "geometry" / "g.shp").write_bytes(b"\x00\x01binary")
    man["files"]["fixed/geometry/g.shp"] = {"sha256": hashlib.sha256(b"\x00\x01binary").hexdigest()}
    for rel, frame in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(p, index=False, lineterminator="\n")
        man["files"][rel] = {"sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
    (d / "handoff_manifest.json").write_text(json.dumps(man))
    return d, man


def accept(store, root, man, skip=()):
    AcceptanceManifest(store, root).append([{"name": rel, "sha256": v["sha256"], "source": "test bundle", "acceptor": "tester",
                                             "accepted_at": "2026-10-30", "kind": "delivered"}
                                            for rel, v in man["files"].items() if rel not in skip])


def test_initialise_requires_acceptance_and_round_trips(tmp_path):
    inp = inputs()
    bundle, man = write_bundle(tmp_path, inp)
    B = smoke_binding(tmp_path)
    store, root = LocalObjectStore(tmp_path / "store"), StoreRoot("smoke", SMOKE)
    with pytest.raises(StoreError, match="no acceptance record"):
        initial.initialise(store, root, str(bundle), binding=B)
    accept(store, root, man, skip=("history/GPP_mean.csv",))
    with pytest.raises(StoreError, match="GPP_mean.csv: no acceptance record"):
        initial.initialise(store, root, str(bundle), binding=B)
    assert not (tmp_path / "store").joinpath("b/ipcch-v2/smoke/history__climate_month_cdd").exists()   # nothing written
    accept(store, root, {"files": {"history/GPP_mean.csv": man["files"]["history/GPP_mean.csv"]}})
    rep = initial.initialise(store, root, str(bundle), binding=B)
    assert len(rep["initialised"]) == len(man["files"]) - 1 and rep["verified_files"] == ["fixed/geometry/g.shp"]
    assert initial.initialise(store, root, str(bundle), binding=B)["unchanged"] == sorted(r for r in man["files"] if r.endswith(".csv"))
    got = initial.read_assembly_inputs(store, root, B)
    got.acled = inp.acled
    target = [ords("2026-10")] * 3
    for h in (2, 8, 14):
        a, _ = asm.assemble(inp, h, list(ROSTER), target)
        b, _ = asm.assemble(got, h, list(ROSTER), target)
        np.testing.assert_array_equal(a.to_numpy(float), b.to_numpy(float))
    (bundle / "history/idp_local.csv").write_text("admin_code,month,value\n11,2020-01,1.0\n")
    with pytest.raises(StoreError, match="bytes differ"):
        initial.initialise(store, root, str(bundle), binding=B)



def test_preflight_rejects_a_malformed_later_file_before_any_write(tmp_path):
    inp = inputs()
    bundle, man = write_bundle(tmp_path, inp)
    B = smoke_binding(tmp_path)
    bad = bundle / "history/idp_national.csv"                                   # sorts after every climate/fixed table
    bad.write_text("iso3,report_month,stock\nAAA,2025-06,100\nAAA,2025-06,120\n")   # duplicate country-month
    man["files"]["history/idp_national.csv"]["sha256"] = hashlib.sha256(bad.read_bytes()).hexdigest()
    (bundle / "handoff_manifest.json").write_text(json.dumps(man))
    store, root = LocalObjectStore(tmp_path / "store"), StoreRoot("smoke", SMOKE)
    accept(store, root, man)
    with pytest.raises(StoreError, match="duplicate"):
        initial.initialise(store, root, str(bundle), binding=B)
    assert VersionedTable(store, root, "fixed__roster").head()[0] is None                     # nothing committed
    assert VersionedTable(store, root, "history__climate_month_cdd").head()[0] is None


def test_existing_head_conflict_detected_before_writes_and_snapshot_warning(tmp_path):
    inp = inputs()
    bundle, man = write_bundle(tmp_path, inp)
    B = smoke_binding(tmp_path)
    store, root = LocalObjectStore(tmp_path / "store"), StoreRoot("smoke", SMOKE)
    accept(store, root, man)
    other = VersionedTable(store, root, "history__idp_national")
    other.commit(pd.DataFrame({"iso3": ["ZZZ"], "report_month": ["2020-01"], "stock": ["1"]}), {"source_sha256": "f" * 64},
                 expected_generation="0")
    with pytest.raises(StoreError, match="already holds different accepted content"):
        initial.initialise(store, root, str(bundle), binding=B)
    assert VersionedTable(store, root, "fixed__roster").head()[0] is None
    store2, root2 = LocalObjectStore(tmp_path / "store2"), StoreRoot("smoke", SMOKE)
    accept(store2, root2, man)
    initial.initialise(store2, root2, str(bundle), binding=B)
    head, _ = VersionedTable(store2, root2, "history__history_snapshot").head()
    assert head["record"]["preparation_cutoff"] == "2026-12" and head["record"]["action"] == "initialise"
    assert retained.snapshot_warning(head, "2026-11") is None
    assert "before O 2027-01" in retained.snapshot_warning(head, "2027-01")



@pytest.mark.parametrize("rel,col,bad", [("history/history_snapshot.csv", "area_id", "broken"),
                                         ("fixed/season_windows.csv", "season_year", "broken"),
                                         ("history/idp_local.csv", "month", "2020-13"),
                                         ("fixed/season_windows.csv", "gs_end_date_exclusive", "2026-02-31"),
                                         ("history/climate_month_cdd.csv", "admin_code", "11.0"),
                                         ("history/idp_national.csv", "iso3", "aa1")])
def test_invalid_fields_refused_before_any_write(tmp_path, rel, col, bad):
    inp = inputs()
    bundle, man = write_bundle(tmp_path, inp)
    B = smoke_binding(tmp_path)
    path = bundle / rel
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame.loc[0, col] = bad
    frame.to_csv(path, index=False, lineterminator="\n")
    man["files"][rel]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()       # checksum + acceptance match
    (bundle / "handoff_manifest.json").write_text(json.dumps(man))
    store, root = LocalObjectStore(tmp_path / "store"), StoreRoot("smoke", SMOKE)
    accept(store, root, man)
    with pytest.raises(StoreError):
        initial.initialise(store, root, str(bundle), binding=B)
    written = [p for p in (tmp_path / "store").rglob("*") if p.is_file() and "acceptance_manifest" not in str(p)]
    assert written == []                                                              # zero table writes
