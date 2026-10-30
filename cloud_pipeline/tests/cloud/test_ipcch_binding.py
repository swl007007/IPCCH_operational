"""Task 10-29: combination envelope binding (design.md:27, R32, R45, R48, R51, R55), the exact-roster fixed geography
for providers and the output population from the population reference (no future period)."""

import builtins
import hashlib
import io
import json
import os
import shutil

import numpy as np
import pandas as pd
import pytest

from cloud.batch import remote_sources as rs
from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import binding as bd
from cloud.ipcch import geography as geo
from cloud.ipcch import initial
from cloud.ipcch.stores import StoreError, StoreRoot, VersionedTable
from tests.cloud.ipcch_binding_fixtures import finalize_entries, make_package, smoke_envelope
from tests.cloud.test_ipcch_assembly import ORDER, ROSTER, inputs
from tests.cloud.test_ipcch_initial import write_bundle

REAL, SMOKE = "gs://b/ipcch-v2/real", "gs://b/ipcch-v2/smoke"
POP = "admin_code,reference_period,population_estimate\n11,2026-04,100.0\n11,2026-12,999.0\n12,2026-08,200.0\n13,2025-01,300.0\n"


def add_population(bundle, man, text=POP):
    (bundle / "fixed" / "population_reference.csv").write_text(text)
    man["files"]["fixed/population_reference.csv"] = {"sha256": hashlib.sha256(text.encode()).hexdigest()}
    (bundle / "handoff_manifest.json").write_text(json.dumps(man))


def real_setup(tmp_path, name="a"):
    """A real (non-fixture) bundle with finalized entries, a package and an ACCEPTED envelope binding both."""
    base = tmp_path / name
    base.mkdir()
    bundle, man = write_bundle(base, inputs(), fixture=False)
    add_population(bundle, man)
    finalize_entries(str(bundle))
    pkg = make_package(base / "package", ORDER)
    env = bd.build_envelope(str(pkg), str(bundle), envelope_version=1, created_at="2026-10-31T00:00:00Z",
                            acceptor="research lead", accepted_at="2026-10-31")
    env_path = base / "envelope-v1.json"
    sha = bd.write_envelope(env, str(env_path))
    return bundle, man, pkg, env_path, sha


def real_binding(tmp_path, name="a"):
    bundle, man, pkg, env_path, sha = real_setup(tmp_path, name)
    return bundle, man, pkg, bd.verify_combination(str(env_path), str(pkg), mode="real", expected_envelope_sha256=sha)


def initialise_real(tmp_path, binding, bundle, store_dir="store"):
    store, root = LocalObjectStore(tmp_path / store_dir), StoreRoot("real", REAL)
    initial.install_acceptance(store, root, str(bundle), binding=binding)
    return store, root, initial.initialise(store, root, str(bundle), binding=binding)


def table_writes(path):
    return [p for p in path.rglob("*") if p.is_file() and "acceptance_manifest" not in str(p)]


# --------------------------------------------------------------------------- package and envelope


def test_package_identity_rehashes_every_file_and_refuses_unlisted(tmp_path):
    pkg = make_package(tmp_path / "p", ORDER)
    ident = bd.package_identity(str(pkg))
    assert ident["feature_count"] == 527 and ident["feature_order_sha256"] == bd.feature_order_sha256(ORDER)
    (pkg / "scope_6m" / "phase2_worse_model.json").write_text("{}")
    with pytest.raises(bd.BindingError, match="differs"):
        bd.package_identity(str(pkg))
    pkg = make_package(tmp_path / "q", ORDER)
    (pkg / "scope_0m" / "stray.json").write_text("{}")
    with pytest.raises(bd.BindingError, match="unlisted"):
        bd.package_identity(str(pkg))


def test_real_requires_accepted_envelope_and_rejects_another_package_with_the_same_schema(tmp_path):
    bundle, man, pkg, env_path, sha = real_setup(tmp_path)
    b = bd.verify_combination(str(env_path), str(pkg), mode="real", expected_envelope_sha256=sha)
    assert b.status == "accepted" and b.feature_order == ORDER and b.handoff["manifest_sha256"] == \
        hashlib.sha256((bundle / "handoff_manifest.json").read_bytes()).hexdigest()
    with pytest.raises(bd.BindingError, match="referenced"):
        bd.verify_combination(str(env_path), str(pkg), mode="real", expected_envelope_sha256="0" * 64)
    other = make_package(tmp_path / "other", ORDER, contract_body="model_feature,category,extra\n")   # same 527 names
    with pytest.raises(bd.BindingError, match="not the bound combination"):
        bd.verify_combination(str(env_path), str(other), mode="real")
    cand = bd.build_envelope(str(pkg), str(bundle), envelope_version=2, created_at="2026-10-31T00:00:00Z")
    cand_path = tmp_path / "envelope-v2.json"
    bd.write_envelope(cand, str(cand_path))
    assert cand["status"] == "candidate" and cand["handoff"]["acceptance_entries_sha256"] is None
    with pytest.raises(bd.BindingError, match="requires an accepted combination envelope"):
        bd.verify_combination(str(cand_path), str(pkg), mode="real")
    assert bd.verify_combination(str(cand_path), str(pkg), mode="smoke", fixture_root=str(tmp_path / "fx")).handoff is None
    with pytest.raises(bd.BindingError, match="declared fixture_root"):
        bd.verify_combination(str(cand_path), str(pkg), mode="smoke")                       # smoke needs its namespace
    with pytest.raises(FileExistsError):
        bd.write_envelope(cand, str(cand_path))                                              # versions never overwritten


def test_accepted_envelope_binds_finalized_entries_not_a_draft_digest(tmp_path):
    base = tmp_path / "d"
    base.mkdir()
    bundle, man = write_bundle(base, inputs(), fixture=False)
    entries = finalize_entries(str(bundle))
    draft = [{**e, "acceptor": None, "accepted_at": None} for e in entries]
    (bundle / "acceptance_entries.json").write_text(json.dumps(draft))
    pkg = make_package(base / "package", ORDER)
    with pytest.raises(bd.BindingError, match="not finalized"):
        bd.build_envelope(str(pkg), str(bundle), envelope_version=1, created_at="t", acceptor="x", accepted_at="2026-10-31")
    cand = bd.build_envelope(str(pkg), str(bundle), envelope_version=1, created_at="t")
    assert cand["handoff"]["draft_acceptance_entries_sha256"] == hashlib.sha256((bundle / "acceptance_entries.json").read_bytes()).hexdigest()
    finalize_entries(str(bundle), accepted_at="2026-10-31")
    env = bd.build_envelope(str(pkg), str(bundle), envelope_version=2, created_at="t", acceptor="x", accepted_at="2026-10-31")
    bd.write_envelope(env, str(base / "env.json"))
    b = bd.verify_combination(str(base / "env.json"), str(pkg), mode="real")
    assert bd.verify_handoff(b, str(bundle))["acceptance_entries_sha256"] == env["handoff"]["acceptance_entries_sha256"]
    finalize_entries(str(bundle), accepted_at="2026-11-02")                 # entries re-finalized later: stale binding
    with pytest.raises(bd.BindingError, match="acceptance_entries_sha256"):
        bd.verify_handoff(b, str(bundle))
    (bundle / "acceptance_entries.json").write_text(json.dumps(entries[:-1]))
    with pytest.raises(bd.BindingError, match="names differ"):
        bd.verify_handoff(b, str(bundle))


# --------------------------------------------------------------------------- real initialisation and mixing


def test_real_store_initialises_only_the_bound_bundle_and_reads_require_the_same_pairing(tmp_path):
    bundle, man, pkg, b = real_binding(tmp_path)
    store, root, rep = initialise_real(tmp_path, b, bundle)
    assert rep["pairing"]["bundle_manifest_sha256"] == b.handoff["manifest_sha256"] and rep["unchanged"] == []
    got = initial.read_assembly_inputs(store, root, b)
    assert got.order == ORDER and got.roster == ROSTER
    head, _ = VersionedTable(store, root, "fixed__roster").head()
    assert head["record"]["combination"]["envelope_sha256"] == b.envelope_sha256

    # another bundle with the SAME 527-column schema, roster and content shape, but a different history file
    other_bundle, other_man, _, other_b = real_binding(tmp_path, "b")
    assert (other_bundle / "handoff_manifest.json").read_bytes() == (bundle / "handoff_manifest.json").read_bytes()
    p = other_bundle / "history" / "idp_local.csv"
    p.write_text(p.read_text() + "13,2026-09,7.0\n")
    with pytest.raises(StoreError, match="bytes differ"):            # same manifest bytes, altered file
        initial.initialise(store, root, str(other_bundle), binding=b)
    other_man["files"]["history/idp_local.csv"]["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    (other_bundle / "handoff_manifest.json").write_text(json.dumps(other_man))   # a consistent, different bundle
    finalize_entries(str(other_bundle))
    with pytest.raises(StoreError, match="manifest_sha256"):
        initial.initialise(store, root, str(other_bundle), binding=b)
    fresh = LocalObjectStore(tmp_path / "fresh")
    with pytest.raises(StoreError, match="manifest_sha256"):
        initial.initialise(fresh, StoreRoot("real", REAL), str(other_bundle), binding=b)     # unbound bundle
    assert table_writes(tmp_path / "fresh") == []

    # a store initialised for one combination refuses another package/envelope (even with the same feature order)
    shutil.copytree(other_bundle, tmp_path / "b2")
    finalize_entries(str(tmp_path / "b2"))
    pkg2 = make_package(tmp_path / "pkg2", ORDER, combination_id="another-combination")
    env2 = bd.build_envelope(str(pkg2), str(bundle), envelope_version=1, created_at="t", acceptor="x", accepted_at="2026-10-31")
    bd.write_envelope(env2, str(tmp_path / "env2.json"))
    b2 = bd.verify_combination(str(tmp_path / "env2.json"), str(pkg2), mode="real")
    with pytest.raises(StoreError, match="bound to another combination"):
        initial.read_assembly_inputs(store, root, b2)
    with pytest.raises(StoreError, match="bound to another combination"):
        initial.initialise(store, root, str(bundle), binding=b2)
    with pytest.raises(StoreError, match="cannot read the real store"):
        initial.read_assembly_inputs(store, root, bd.verify_combination(str(tmp_path / "env2.json"), str(pkg2), mode="smoke",
                                                                        fixture_root=str(tmp_path / "fx")))


def test_real_refuses_fixture_bundles_unaccepted_records_and_smoke_refuses_real_bundles(tmp_path):
    bundle, man, pkg, b = real_binding(tmp_path)
    store, root = LocalObjectStore(tmp_path / "s"), StoreRoot("real", REAL)
    with pytest.raises(StoreError, match="no acceptance record"):
        initial.initialise(store, root, str(bundle), binding=b)              # store manifest not installed
    assert table_writes(tmp_path / "s") == []
    from cloud.ipcch.stores import AcceptanceManifest
    AcceptanceManifest(store, root).append([{"name": rel, "sha256": v["sha256"], "source": "s", "acceptor": "someone else",
                                             "accepted_at": "2026-10-30", "kind": "delivered"} for rel, v in man["files"].items()])
    with pytest.raises(StoreError, match="differs from the envelope-bound finalized entry"):
        initial.initialise(store, root, str(bundle), binding=b)
    assert table_writes(tmp_path / "s") == []
    fixture_dir = tmp_path / "fx"
    fixture_dir.mkdir()
    fx, _ = write_bundle(fixture_dir, inputs(), fixture=True)
    with pytest.raises(StoreError, match="fixture"):
        initial.initialise(LocalObjectStore(tmp_path / "s2"), StoreRoot("real", REAL), str(fx), binding=b)
    smoke = bd.verify_combination(str(tmp_path / "a" / "envelope-v1.json"), str(pkg), mode="smoke", fixture_root=str(fixture_dir))
    with pytest.raises(StoreError, match="outside the declared fixture root"):
        initial.initialise(LocalObjectStore(tmp_path / "s3"), StoreRoot("smoke", SMOKE), str(bundle), binding=smoke)
    inside = fixture_dir / "copied-real"
    shutil.copytree(bundle, inside)                                         # a non-fixture bundle inside the root
    with pytest.raises(StoreError, match="requires a fixture bundle"):
        initial.initialise(LocalObjectStore(tmp_path / "s5"), StoreRoot("smoke", SMOKE), str(inside), binding=smoke)
    with pytest.raises(StoreError, match="smoke binding cannot initialise the real store"):
        initial.initialise(LocalObjectStore(tmp_path / "s4"), StoreRoot("real", REAL), str(bundle), binding=smoke)


class ReadSpy:
    """Records every open/stat/lstat/listdir/scandir whose LEXICAL path lies under ``forbidden`` (the spy itself never
    touches the filesystem, so it can also watch os.lstat)."""

    def __init__(self, monkeypatch, forbidden):
        self.forbidden, self.touched = os.path.normpath(os.path.abspath(forbidden)), []
        for mod, name in ((builtins, "open"), (io, "open"), (os, "open"), (os, "stat"), (os, "lstat"),
                          (os, "listdir"), (os, "scandir")):
            monkeypatch.setattr(mod, name, self.guard(getattr(mod, name)))

    def guard(self, fn):
        def wrapped(path=".", *a, **k):
            if isinstance(path, (str, bytes, os.PathLike)):
                p = os.path.normpath(os.path.abspath(os.fsdecode(path)))
                if p == self.forbidden or p.startswith(self.forbidden + os.sep):
                    self.touched.append(p)
            return fn(path, *a, **k)
        return wrapped


def test_smoke_never_reads_the_real_handoff_bundle(tmp_path, monkeypatch):
    """R48 spy: smoke envelope/package verification, fixture initialisation, assembly-input and population reads, and a
    MISROUTED real bundle passed to smoke initialise/verify_fixture_bundle never open, stat, list or scan anything under
    the real handoff bundle."""
    real_bundle, _, pkg, env_path, _ = real_setup(tmp_path)
    fx_dir = tmp_path / "fixture"
    fx_dir.mkdir()
    fx, fx_man = write_bundle(fx_dir, inputs(), fixture=True)
    add_population(fx, fx_man)
    store, root = LocalObjectStore(tmp_path / "smoke-store"), StoreRoot("smoke", SMOKE)
    from tests.cloud.test_ipcch_initial import accept
    accept(store, root, fx_man)
    spy = ReadSpy(monkeypatch, real_bundle)
    b = bd.verify_combination(str(env_path), str(pkg), mode="smoke", fixture_root=str(fx_dir))   # ACCEPTED real envelope
    assert b.handoff is None
    rep = initial.initialise(store, root, str(fx), binding=b)
    assert rep["pairing"]["mode"] == "smoke" and rep["pairing"]["roster_size"] == len(ROSTER)
    initial.read_assembly_inputs(store, root, b)
    initial.read_population(store, root, b, "2026-08")
    with pytest.raises(bd.BindingError, match="smoke never resolves the real handoff bundle"):
        bd.verify_handoff(b, str(real_bundle))
    # misrouted: the real bundle handed to smoke admission is refused before any filesystem access
    with pytest.raises(bd.BindingError, match="outside the declared fixture root"):
        bd.verify_fixture_bundle(b, str(real_bundle))
    fresh = LocalObjectStore(tmp_path / "smoke-fresh")
    with pytest.raises(StoreError, match="outside the declared fixture root"):
        initial.initialise(fresh, root, str(real_bundle), binding=b)
    with pytest.raises(StoreError, match="outside the declared fixture root"):
        initial.initialise(fresh, root, str(fx_dir / ".." / real_bundle.relative_to(tmp_path)), binding=b)  # dot-dot
    monkeypatch.undo()
    assert spy.touched == []


def test_smoke_refuses_symlinks_out_of_the_fixture_root(tmp_path, monkeypatch):
    real_bundle, _, pkg, env_path, _ = real_setup(tmp_path)
    fx_dir = tmp_path / "fixture"
    fx_dir.mkdir()
    (fx_dir / "linked").symlink_to(real_bundle, target_is_directory=True)        # whole bundle linked
    part = fx_dir / "partial"
    part.mkdir()
    (part / "handoff_manifest.json").symlink_to(real_bundle / "handoff_manifest.json")
    b = bd.verify_combination(str(env_path), str(pkg), mode="smoke", fixture_root=str(fx_dir))
    opened = []
    real_open = builtins.open
    monkeypatch.setattr(builtins, "open", lambda f, *a, **k: (opened.append(os.fspath(f)), real_open(f, *a, **k))[1])
    for d in ("linked", "partial"):
        with pytest.raises(bd.BindingError, match="symlink"):
            bd.verify_fixture_bundle(b, str(fx_dir / d))
    monkeypatch.undo()
    assert not [p for p in opened if "linked" in p or "partial" in p]


# --------------------------------------------------------------------------- population and geometry


def test_population_snapshot_uses_the_existing_no_future_builder(tmp_path):
    ref = pd.read_csv(io.StringIO(POP), dtype={"admin_code": str})
    out, rep = geo.population_snapshot(ref, origin="2026-08", roster=ROSTER)
    got = out.set_index("admin_code")
    assert got.loc["11", "population_estimate"] == 100.0 and got.loc["11", "population_reference_period"] == "2026-04"
    assert got.loc["11", "population_imputation_method"] == "last_observation_carried_forward"   # 2026-12 never used
    assert got.loc["12", "population_imputation_method"] == "observed_feature_month"
    assert rep["future_reference_rows_ignored"] == 1 and rep["method_counts"] == {"observed_feature_month": 1,
                                                                                  "last_observation_carried_forward": 2}
    with pytest.raises(geo.GeographyError, match="unknown modeled areas"):
        geo.population_snapshot(pd.concat([ref, ref.assign(admin_code="1315")]), origin="2026-08", roster=ROSTER)
    from model_pipeline.ipcch_launch_runtime.population import PopulationSelectionError
    with pytest.raises(PopulationSelectionError, match="no current or prior population"):
        geo.population_snapshot(ref, origin="2024-12", roster=ROSTER)                 # area 13's first period is 2025-01


def test_real_population_read_from_the_bound_store(tmp_path):
    bundle, man, pkg, b = real_binding(tmp_path)
    store, root, _ = initialise_real(tmp_path, b, bundle)
    out, rep = initial.read_population(store, root, b, "2026-08")
    assert list(out["admin_code"]) == [str(a) for a in ROSTER] and rep["missing_area_count"] == 0


def _shapefile(dirpath, codes, crs="EPSG:4326"):
    import geopandas
    from shapely.geometry import box
    dirpath.mkdir(parents=True, exist_ok=True)
    gdf = geopandas.GeoDataFrame({"admin_code": [str(c) for c in codes]},
                                 geometry=[box(i, 0, i + 1, 1) for i, _ in enumerate(codes)], crs=crs)
    gdf.to_file(dirpath / "g.shp")
    return {f"fixed/geometry/{p.name}": {"sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in dirpath.iterdir()}


def test_roster_geometries_filter_declared_extras_and_feed_the_zonal_path(tmp_path):
    files = _shapefile(tmp_path / "fixed" / "geometry", [11, 12, 1315, 13])
    man = {"files": files, "roster_policy": {"fixed/geometry/g.dbf": {"out_of_roster_admins": [1315]}}}
    fc, rep = geo.roster_geometries(str(tmp_path), man, ROSTER)
    assert [f["properties"]["admin_code"] for f in fc["features"]] == ["11", "12", "13"] and rep["dropped_declared_extra"] == ["1315"]
    assert list(rs.native_geometries(fc, roster=[str(a) for a in ROSTER])) == ["11", "12", "13"]
    with pytest.raises(geo.GeographyError, match="unknown modeled-area identifiers"):
        geo.roster_geometries(str(tmp_path), {"files": files, "roster_policy": {}}, ROSTER)      # 1315 undeclared
    with pytest.raises(geo.GeographyError, match="lacks 1 roster areas"):
        geo.roster_geometries(str(tmp_path), man, (*ROSTER, 14))
    (tmp_path / "fixed" / "geometry" / "g.dbf").write_bytes((tmp_path / "fixed" / "geometry" / "g.dbf").read_bytes() + b"x")
    with pytest.raises(geo.GeographyError, match="bytes differ"):
        geo.roster_geometries(str(tmp_path), man, ROSTER)


def test_restrict_to_roster_for_provider_outputs():
    frame = pd.DataFrame({"admin_code": ["13", "1315", "11", "12"], "v": [3.0, 9.0, 1.0, 2.0]})
    out, dropped = geo.restrict_to_roster(frame, ROSTER, declared_extra={"1315"}, label="gpp 2026-08")
    assert out["admin_code"].tolist() == ["11", "12", "13"] and out["v"].tolist() == [1.0, 2.0, 3.0] and dropped == ["1315"]
    with pytest.raises(geo.GeographyError, match="unknown"):
        geo.restrict_to_roster(frame, ROSTER, label="gpp")
    with pytest.raises(geo.GeographyError, match="duplicate"):
        geo.restrict_to_roster(pd.concat([frame, frame.head(1)]), ROSTER, declared_extra={"1315"}, label="gpp")
