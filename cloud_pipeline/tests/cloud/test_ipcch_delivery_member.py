"""Task 10-29: new-contract IPCCH delivery member from a scored smoke batch (R18, R31, R32, R36, R47, R61) and its
verifier (re-hash, roster/finite/periods/mode/package identity)."""

import json

import pandas as pd
import pytest

from cloud.ipcch import batch_inference as bi
from cloud.ipcch import binding as bd
from cloud.ipcch import delivery_member as dm
from cloud.ipcch import geography, initial
from tests.cloud import ipcch_smoke_fixture as fx
from tests.cloud.test_ipcch_assembly import ORDER, ROSTER
from tests.cloud.test_ipcch_generation import SMOKE, generation, package, setup  # noqa: F401 (fixture)


def scored_batch(tmp_path, package):
    store, root, b, bundle = setup(tmp_path, package)
    refs = fx.Refs()
    out = generation(store, root, b, bundle, refs, fx.smoke_request(refs, tmp_path / "env.json", inference=True),
                     tmp_path).run()
    roster = [str(a) for a in ROSTER]
    manifest, frames = bi.load_batch(store, out["manifest_ref"], batch_root=SMOKE, batch_id=out["batch_id"], mode="smoke",
                                     execution_month="2027-03", binding=b, roster=roster)
    scored = bi.score_batch(manifest, frames, str(package), b)
    man = json.load(open(bundle / "handoff_manifest.json"))
    fc, _ = geography.roster_geometries(str(bundle), man, roster)
    ident = initial._read(store, root, "fixed/area_identity.csv")
    return dict(manifest=manifest, scored=scored, binding=b, package_root=str(package),
                feature_provenance=bi.read_feature_provenance(store, manifest, batch_root=SMOKE),
                envelope_path=str(tmp_path / "env.json"), census_bytes=fx.COUNTRY_REFERENCE.encode(),
                area_identity=ident, geometry=dm.geometry_geojson(fc), roster=roster)


def test_member_tables_provenance_and_verification(tmp_path, package):
    kw = scored_batch(tmp_path, package)
    out = tmp_path / "delivery"
    prov = dm.write_member(out, **kw)
    assert prov["contract"] == dm.CONTRACT and prov["mode"] == "smoke" and prov["feature_origin"] == "2027-01"
    assert [(h["model_horizon_months"], h["public_lead_months"], h["target_month"]) for h in prov["horizons"]] == \
        [(2, 0, "2027-03"), (8, 6, "2027-09"), (14, 12, "2028-03")]
    p0 = pd.read_csv(out / "scopes/0m/ipcch/polygon_predictions.csv", dtype=str)
    assert tuple(p0.columns) == dm.V2_PREDICTION_HEADER and set(p0["mode"]) == {"smoke"}
    assert set(p0["model_package_id"]) == {"ipcch-test-scoring/scope_0m"} and set(p0["target_period"]) == {"2027-03"}
    c12 = pd.read_csv(out / "scopes/12m/ipcch/country_predictions.csv", dtype=str)
    assert sorted(c12["ISO3"]) == ["AAA", "BBB"] and set(c12["target_period"]) == {"2028-03"}
    conf = pd.read_csv(out / "scopes/6m/ipcch/country_confidence.csv", dtype=str)
    assert conf["country_error_rate"].notna().all()                                   # from the package's own evidence
    avail = pd.read_csv(out / "reports/ipcch_diagnostic_availability.csv", dtype=str)
    assert set(avail["diagnostic_family"]) == {"polygon_training_errors", "country_confidence", "maximum_phase"}
    assert avail["evidence_ref"].str.startswith("envelope:ipcch-test-scoring/envelope-v1/evidence/").all()
    geo = json.loads((out / "ipcch/polygons.geojson").read_text())
    assert [f["properties"]["polygon_id"] for f in geo["features"]] == ["11", "12", "13"]       # exact roster, no 1315
    assert dm.verify_member(out, expected={"execution_month": "2027-03", "feature_origin": "2027-01", "mode": "smoke",
                                           "provenance_sha256": prov["provenance_sha256"]})["system"] == "ipcch"


@pytest.mark.parametrize("tamper,match", [
    (lambda out: (out / "scopes/6m/ipcch/polygon_predictions.csv").write_text("x\n"), "member files changed"),
    (lambda out: (out / "scopes/6m/ipcch/extra.csv").write_text("x\n"), "unlisted"),
    (lambda out: (out / "ipcch/polygons.geojson").unlink(), "missing|lacks required files"),
])
def test_tampered_or_incomplete_members_do_not_verify(tmp_path, package, tamper, match):
    kw = scored_batch(tmp_path, package)
    out = tmp_path / "delivery"
    dm.write_member(out, **kw)
    tamper(out)
    with pytest.raises(dm.MemberError, match=match):
        dm.verify_member(out)


def test_member_requires_all_three_horizons_and_census_coverage(tmp_path, package):
    kw = scored_batch(tmp_path, package)
    with pytest.raises(dm.MemberError, match="R18"):
        dm.write_member(tmp_path / "a", **{**kw, "scored": {h: v for h, v in kw["scored"].items() if h != 14}})
    thin = fx.COUNTRY_REFERENCE.rsplit("BBB", 1)[0].rsplit("\n", 1)[0] + "\n"
    with pytest.raises(dm.MemberError, match="lacks ISO3"):
        dm.write_member(tmp_path / "b", **{**kw, "census_bytes": thin.encode()})
    with pytest.raises(dm.MemberError, match="mode"):
        out = tmp_path / "c"
        prov = dm.write_member(out, **kw)
        dm.verify_member(out, expected={**prov, "mode": "real"})



def test_feature_fill_sidecar_is_actual_no_fill_row_section_provenance(tmp_path, package):
    kw = scored_batch(tmp_path, package)
    out = tmp_path / "delivery"
    dm.write_member(out, **kw)
    a = pd.read_csv(out / "reports/ipcch_feature_fill_audit.csv", dtype=str, keep_default_na=False)
    assert len(a) == len(a[["polygon_id", "section"]].drop_duplicates()) and set(a["polygon_id"]) == {"11", "12", "13"}
    assert set(a["fill_method"]) == {"none"} and set(a["imputation_rule"]) == {"none"}
    gpp = a[a["section"] == "GPP_mean"].set_index("polygon_id")
    assert set(gpp["dependency_end"]) == {"2027-01"} and set(gpp["latest_observation"]) == {"2026-12"}   # O unpublished
    assert (gpp["missing_h02"].astype(int) > 0).all()                        # value at O missing, not filled
    acled = a[a["section"] == "acled_agg_events_battles"]
    assert set(acled["dependency_end"]) == {"2026-12"} and set(acled["observation_kind"]) == {"month_lag1"}  # A = O-1
    assert set(a[a["section"] == "static29"]["observation_kind"]) == {"static"}
    assert int(a["feature_count"].astype(int).groupby(a["polygon_id"]).sum().iloc[0]) == 527
    with pytest.raises(dm.MemberError, match="feature provenance"):
        dm.write_member(tmp_path / "x", **{**kw, "feature_provenance": b""})


def rewrite(out, rel, data, drop=False):
    """Edit a member file AND its provenance inventory self-consistently (the verifier must not rely on the inventory)."""
    import hashlib
    path = out / "ipcch/system_provenance.json"
    prov = json.loads(path.read_text())
    if drop:
        (out / rel).unlink()
        prov["files"].pop(rel)
    else:
        (out / rel).write_bytes(data)
        prov["files"][rel] = hashlib.sha256(data).hexdigest()
    path.write_text(json.dumps(prov))
    return prov


def test_review_regressions_member_verifier(tmp_path, package):
    kw = scored_batch(tmp_path, package)

    def fresh(name):
        out = tmp_path / name
        dm.write_member(out, **kw)
        return out
    mixed = fresh("mixed")                                     # FEWS files beside the member do not break it
    for rel in ("scopes/0m/fewsnet/polygon_predictions.csv", "reports/fewsnet_feature_fill_audit.csv", "fewsnet/x.csv"):
        (mixed / rel).parent.mkdir(parents=True, exist_ok=True)
        (mixed / rel).write_text("x\n")
    assert dm.verify_member(mixed)["system"] == "ipcch"
    out = fresh("nohorizons")
    path = out / "ipcch/system_provenance.json"
    prov = json.loads(path.read_text())
    prov["horizons"] = []
    path.write_text(json.dumps(prov))
    with pytest.raises(dm.MemberError, match="not exactly H2/H8/H14"):
        dm.verify_member(out)
    out = fresh("noscope")
    rewrite(out, "scopes/12m/ipcch/country_confidence.csv", None, drop=True)
    with pytest.raises(dm.MemberError, match="lacks required files"):
        dm.verify_member(out)
    out = fresh("envelope")
    rewrite(out, "ipcch/combination_envelope.json", b"{}")
    with pytest.raises(dm.MemberError, match="not the recorded envelope"):
        dm.verify_member(out)
    out = fresh("geometry")
    rewrite(out, "ipcch/polygons.geojson", b'{"type":"FeatureCollection","crs":{"type":"name","properties":'
                                           b'{"name":"EPSG:4326"}},"features":[]}')
    with pytest.raises(dm.MemberError, match="not exactly the unique roster"):
        dm.verify_member(out)
    out = fresh("package")
    prov = json.loads((out / "ipcch/system_provenance.json").read_text())
    with pytest.raises(dm.MemberError, match="package identity"):
        dm.verify_member(out, expected={**prov, "package": {**prov["package"], "combination_id": "other"}})


def test_seasonal_provenance_reports_actual_observations_not_calendar_selection(tmp_path, package):
    from cloud.ipcch import provenance as pv
    from tests.cloud.test_ipcch_assembly import inputs
    inp = inputs()
    inp.climate_seasonal = {b: f.assign(value=float("nan")) for b, f in inp.climate_seasonal.items()}   # all 13 NaN
    roster = [str(a) for a in ROSTER]
    frame = pd.DataFrame({"admin_code": roster, **{c: [1.0] * 3 for c in ORDER}})
    ledger = pd.DataFrame({"admin_code": [11, 12, 13], "season_cutoff_date": ["2026-12-01"] * 3,
                           "history_1_source_ord": [-1] * 3, "idp_report_ord": [-1] * 3})
    out = pv.section_provenance(inp, {2: frame, 8: frame, 14: frame}, ledger, order=ORDER, origin="2026-11", roster=roster,
                                retained_refs={"history__climate_gs_cdd": {"version": 4, "sha256": "e" * 64}})
    cdd = out[out["section"] == "gs_cdd"].set_index("polygon_id")
    assert cdd["latest_observation"].isna().all() and set(cdd["source_table"]) == {"history__climate_gs_cdd"}
    assert set(cdd["source_version"]) == {4}
    cal = out[out["section"] == "growing_season_calendar"].set_index("polygon_id")
    assert set(cal["latest_observation"]) == {"2026-s2"} and set(cal["observation_kind"]) == {"calendar_selection"}


def test_smoke_restricts_full_roster_package_evidence_to_the_fixture_roster(tmp_path_factory):
    """CP5 (actual package): the package's evidence covers its full training roster. SMOKE: after verification
    against the bound package manifest its rows are restricted to the fixture roster and declared as a subset (own
    sha256, URI naming the verified source digest); REAL: the unchanged rule refuses evidence outside the roster."""
    import dataclasses

    from cloud.orchestrator.delivery_outputs import EvidenceIntegrityError
    from tests.cloud.ipcch_binding_fixtures import make_scoring_package
    wide = make_scoring_package(tmp_path_factory.mktemp("wide") / "package", ORDER,
                                evidence_areas=("11", "12", "13", "990", "991"))
    tmp = tmp_path_factory.mktemp("smoke")
    kw = scored_batch(tmp, wide)
    prov = dm.write_member(tmp / "out", **kw)
    declared = json.loads((tmp / "out/reports/ipcch_diagnostic_declarations.json").read_text())
    ref = declared["0m"]["polygon_training_errors"]["ref"]
    assert prov["mode"] == "smoke" and "#smoke-roster-subset-of-sha256:" in ref["uri"]
    real = dict(kw, binding=dataclasses.replace(kw["binding"], mode="real"))
    with pytest.raises(EvidenceIntegrityError, match="must be roster IDs"):
        dm.write_member(tmp / "out-real", **real)


def test_smoke_evidence_without_any_roster_area_is_unavailable_with_reason(tmp_path_factory):
    """Supervisor on b3b5dd2: valid source evidence for areas 990/991 only and the fixture roster 11/12/13 -> the
    families are declared unavailable (no_eligible_area_history, R31) and the member still writes; never an empty
    'available' file."""
    from tests.cloud.ipcch_binding_fixtures import make_scoring_package
    other = make_scoring_package(tmp_path_factory.mktemp("other") / "package", ORDER, evidence_areas=("990", "991"))
    tmp = tmp_path_factory.mktemp("smoke-empty")
    kw = scored_batch(tmp, other)
    dm.write_member(tmp / "out", **kw)
    declared = json.loads((tmp / "out/reports/ipcch_diagnostic_declarations.json").read_text())
    for lead in ("0m", "6m", "12m"):
        for family in ("polygon_training_errors", "country_confidence", "maximum_phase"):
            assert (declared[lead][family]["status"], declared[lead][family]["reason"]) == (
                "unavailable", "no_eligible_area_history")
    availability = pd.read_csv(tmp / "out/reports/ipcch_diagnostic_availability.csv", dtype=str)
    assert set(availability["status"]) == {"unavailable"}


def test_smoke_validates_the_full_evidence_identity_before_restricting_it(tmp_path_factory):
    """A source file with a wrong identity is refused in smoke even when the roster subset would be empty."""
    import hashlib

    from cloud.orchestrator.delivery_outputs import EvidenceIntegrityError
    from tests.cloud.ipcch_binding_fixtures import make_scoring_package
    root = make_scoring_package(tmp_path_factory.mktemp("bad") / "package", ORDER, evidence_areas=("990", "991"))
    tmp = tmp_path_factory.mktemp("smoke-bad")
    kw = scored_batch(tmp, root)                                  # binding of the intact package
    manifest = json.loads((root / bd.PACKAGE_MANIFEST).read_text())
    ev = manifest["scopes"]["0"]["evidence"]["area"]
    path = root / ev["file"]
    text = path.read_text().replace(",0,training_resubstitution,", ",6,training_resubstitution,")   # wrong horizon
    path.write_text(text)
    ev["sha256"] = manifest["files"][ev["file"]]["sha256"] = hashlib.sha256(text.encode()).hexdigest()
    (root / bd.PACKAGE_MANIFEST).write_text(json.dumps(manifest))
    with pytest.raises(EvidenceIntegrityError):
        dm._declarations(kw["binding"], str(root), "0", 0, ["11", "12", "13"], "2027-01", "2025-11")
