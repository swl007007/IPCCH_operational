"""New-contract IPCCH delivery member (task 10-29; R18, R31, R32, R36, R47, R61, R63 and the Supervisor CP4 rulings).

``write_member`` builds the IPCCH member of a v2 delivery from one scored batch, keeping the existing file names and,
except for the contract-aware prediction header, the existing table layouts (R47):

    scopes/{0,6,12}m/ipcch/polygon_predictions.csv     V2_PREDICTION_HEADER = legacy IPCCH header + ``mode`` (R36)
    scopes/{0,6,12}m/ipcch/{country_predictions, polygon_model_mapping, polygon_training_errors, country_confidence}.csv
    ipcch/polygons.geojson                             deterministic export of the ACCEPTED geometry, exactly the roster
    ipcch/country_population_reference.csv             the pinned country reference bytes (delivery fields only)
    ipcch/model_package/...                            the bound package files (portable, inheritable) + envelope
    reports/ipcch_diagnostic_availability.csv          per-system sidecar (shared file rebuilt by explicit merge)
    reports/ipcch_diagnostic_declarations.json
    reports/ipcch_feature_fill_audit.csv               the batch's row/section temporal provenance (no fill; v2 schema)
    ipcch/system_provenance.json                       own M/O/targets/leads/mode/package identity + sha256 of every file

Public leads 0/6/12 are the scope directories (targets M, M+6, M+12); model horizons H2/H8/H14 and the feature origin
O = M - 2 are recorded in the provenance (R23). Diagnostics (R31) come from the package's own evidence files bound by
the envelope, through the unchanged ``scope_diagnostics`` (weighted confidence, maximum-phase proxy/bootstrap,
missing-evidence rules). The country reference joins areas by the accepted ``iso3_reference`` for delivery fields
only; per-area population is the batch's accepted snapshot at <= O, and training iso3 / national-IDP feature inputs are
untouched. ``verify_member`` re-checks a member (all files re-hashed; per horizon: roster-exact unique polygons, finite
q2..q5, O, targets, mode, package identity) - the publication verifier for new and inherited members.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from cloud.ipcch import batch as bt
from cloud.ipcch import binding as bd
from cloud.orchestrator import delivery_outputs as do

PROVENANCE_SCHEMA = "ipcch-system-provenance-v1"
CONTRACT = "ipcch-validity-h2h8h14-v2"
LEADS = {2: 0, 8: 6, 14: 12}
V2_PREDICTION_HEADER = (*do.SEPTEMBER_HEADERS["ipcch"]["polygon_predictions"], "mode")
SCORES = tuple(f"{t}_score" for t in do.PHASE_TARGETS)


REQUIRED_SCOPE_TABLES = ("polygon_predictions", "country_predictions", "polygon_model_mapping", "polygon_training_errors",
                         "country_confidence")
REQUIRED_FILES = ("ipcch/polygons.geojson", "ipcch/country_population_reference.csv", "ipcch/combination_envelope.json",
                  "ipcch/model_package/package_manifest.json", "reports/ipcch_diagnostic_availability.csv",
                  "reports/ipcch_diagnostic_declarations.json", "reports/ipcch_feature_fill_audit.csv",
                  *[f"scopes/{lead}m/ipcch/{t}.csv" for lead in (0, 6, 12) for t in REQUIRED_SCOPE_TABLES])


class MemberError(RuntimeError):
    """The IPCCH member is incomplete or does not verify; it must not be published."""


def is_member_file(rel: str) -> bool:
    """THE IPCCH member file predicate (writer inventory and verifier use the same one)."""
    parts = rel.split("/")
    return (rel.startswith("ipcch/") or rel.startswith("reports/ipcch_")
            or (len(parts) >= 4 and parts[0] == "scopes" and parts[2] == "ipcch"))


def _add_months(month: str, k: int) -> str:
    y, m = (int(x) for x in month.split("-"))
    o = y * 12 + m - 1 + k
    return f"{o // 12:04d}-{o % 12 + 1:02d}"


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def geometry_geojson(fc: Mapping[str, Any]) -> bytes:
    """Deterministic GeoJSON of the roster geometry (``geography.roster_geometries`` output, EPSG:4326)."""
    features = [{"type": "Feature", "properties": {"polygon_id": f["properties"]["admin_code"],
                                                   "admin_code": f["properties"]["admin_code"]},
                 "geometry": f["geometry"]} for f in fc["features"]]
    return (json.dumps({"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
                        "features": features}, sort_keys=True, separators=(",", ":"),
                       default=lambda o: list(o) if isinstance(o, tuple) else o) + "\n").encode("utf-8")


def _lookup(area_identity: pd.DataFrame, census: pd.DataFrame, roster: list[str]) -> tuple[pd.DataFrame, pd.Series]:
    ident = area_identity.assign(admin_code=area_identity["admin_code"].astype(str)).set_index("admin_code")
    missing = sorted(set(roster) - set(ident.index))
    if missing:
        raise MemberError(f"area identity lacks roster areas {missing[:5]}")
    iso = ident.loc[roster, "iso3_reference"].astype(str)
    names = census.drop_duplicates("ISO3").set_index("ISO3")
    absent = sorted(set(iso) - set(names.index))
    if absent:
        raise MemberError(f"country reference lacks ISO3 {absent[:5]} of roster areas")
    lookup = pd.DataFrame({"area_id": roster, "country": names.loc[iso, "country"].to_numpy(),
                           "country_en": names.loc[iso, "country_en"].to_numpy()})
    return lookup, pd.Series(iso.to_numpy(), index=pd.Index(roster, name="area_id"))


def _declarations(binding: bd.Binding, package_root: str, scope: str, lead: int,
                  roster: list[str] | None = None) -> tuple[dict, dict]:
    """The package's own evidence per diagnostic family, verified against the bound package manifest. SMOKE only: the
    accepted package's evidence covers the full training roster, so after that verification its rows are restricted
    to the declared fixture roster (the subset bytes are declared with their own sha256 and a URI naming the subset
    and the verified source file digest); real mode uses the package file unchanged."""
    manifest = json.load(open(os.path.join(package_root, bd.PACKAGE_MANIFEST)))
    ev = manifest["scopes"][scope]["evidence"]
    data = {}
    out = {}
    for family, part in (("polygon_training_errors", "area"), ("country_confidence", "area"), ("maximum_phase", "residual")):
        path = os.path.join(package_root, ev[part]["file"])
        blob = open(path, "rb").read()
        if hashlib.sha256(blob).hexdigest() != ev[part]["sha256"]:
            raise MemberError(f"package evidence {ev[part]['file']} differs from the bound package manifest")
        uri = f"envelope:{binding.envelope_id}/{ev[part]['file']}"
        if binding.mode == "smoke" and roster is not None:
            frame = pd.read_csv(io.BytesIO(blob), dtype=str, keep_default_na=False)
            blob = frame[frame["polygon_id"].isin(set(map(str, roster)))].to_csv(index=False,
                                                                                lineterminator="\n").encode()
            uri = f"{uri}#smoke-roster-subset-of-sha256:{ev[part]['sha256']}"
        out[family] = {"status": "available",
                       "ref": {"uri": uri, "generation": binding.package_manifest_sha256,
                               "sha256": hashlib.sha256(blob).hexdigest()},
                       "evidence_model_package_id": ev["model_package_id"], "evidence_horizon_months": lead}
        data[family] = blob
    return do.normalise_declarations("ipcch", lead, out), data


def write_member(out: Path, *, manifest: Mapping[str, Any], scored: Mapping[int, Mapping[str, Any]], binding: bd.Binding,
                 package_root: str, envelope_path: str, census_bytes: bytes, area_identity: pd.DataFrame,
                 geometry: bytes, roster: list[str], feature_provenance: bytes) -> dict[str, Any]:
    """Write the member under ``out`` (create-only files) and return its provenance (also written, hash-covered)."""
    out = Path(out)
    if sorted(scored) != [2, 8, 14]:
        raise MemberError(f"an IPCCH member needs H2/H8/H14 together, got {sorted(scored)} (R18)")
    census = pd.read_csv(io.BytesIO(census_bytes), dtype=str, keep_default_na=False).replace({"": pd.NA})
    if tuple(census.columns) != do.SEPTEMBER_HEADERS["ipcch"]["country_population_reference"]:
        raise MemberError("country reference does not have the existing country_population_reference columns")
    lookup, iso_by_polygon = _lookup(area_identity, census, roster)
    O, M = manifest["feature_origin"], manifest["execution_month"]
    pkg_manifest = json.load(open(os.path.join(package_root, bd.PACKAGE_MANIFEST)))
    reports = out / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    availability, declared_record, horizons = [], {}, []
    for h, lead in LEADS.items():
        scope, target = str(lead), manifest["horizons"][str(h)]["target_month"]
        package_id = pkg_manifest["scopes"][scope]["evidence"]["model_package_id"]
        p = scored[h]["predictions"].reset_index(drop=True).copy()
        p.insert(0, "polygon_id", p["admin_code"].astype(str))
        p["_row_id"] = np.arange(len(p))                       # the row index of this horizon's batch file
        p["model_package_id"] = package_id                     # the scope model (== its evidence identity)
        if sorted(p["polygon_id"]) != sorted(roster) or p["polygon_id"].duplicated().any():
            raise MemberError(f"H{h}: predictions are not exactly the roster")
        if not np.isfinite(p[list(SCORES)].to_numpy(float)).all():
            raise MemberError(f"H{h}: nonfinite raw scores (R18)")
        declarations, evidence = _declarations(binding, package_root, scope, lead, roster)
        diag = do.scope_diagnostics("ipcch", lead, p, declarations=declarations, evidence_bytes=lambda f, e=evidence: e[f],
                                    package_id=package_id, polygons=p["polygon_id"], census=census, area_lookup=lookup,
                                    iso_by_polygon=iso_by_polygon, origin=O,
                                    training_cutoff=pkg_manifest["scopes"][scope]["training_cutoff"])
        mapping = do.polygon_mapping("ipcch", p, origin=O, target=target, horizon=lead,
                                     package_path=f"ipcch/model_package/scope_{lead}m")
        d = out / f"scopes/{lead}m/ipcch"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "polygon_predictions.csv", "xb") as f:
            f.write(p[list(V2_PREDICTION_HEADER)].to_csv(index=False, lineterminator="\n").encode())
        do.write_table(diag["country"], d / "country_predictions.csv", system="ipcch", name="country_predictions")
        do.write_table(mapping, d / "polygon_model_mapping.csv", system="ipcch", name="polygon_model_mapping")
        do.write_table(diag["polygon_table"], d / f"{diag['polygon_name']}.csv", system="ipcch", name=diag["polygon_name"])
        do.write_table(diag["confidence"], d / "country_confidence.csv", system="ipcch", name="country_confidence")
        availability.append(diag["availability"])
        declared_record[f"{lead}m"] = {f: {**{k: v for k, v in e.items()}, "evidence_identity": diag["evidence_identity"].get(f)}
                                       for f, e in declarations.items()}
        horizons.append({"model_horizon_months": h, "public_lead_months": lead, "target_month": target,
                         "model_package_id": package_id, "training_cutoff": pkg_manifest["scopes"][scope]["training_cutoff"],
                         "rows": int(len(p))})
    do.write_table(pd.concat(availability, ignore_index=True), reports / "ipcch_diagnostic_availability.csv")
    (reports / "ipcch_diagnostic_declarations.json").write_text(json.dumps(declared_record, indent=2, sort_keys=True,
                                                                           default=str) + "\n")
    member = out / "ipcch"
    member.mkdir(parents=True, exist_ok=True)
    (member / "polygons.geojson").write_bytes(geometry)
    (member / "country_population_reference.csv").write_bytes(census_bytes)
    pkg_dir = member / "model_package"
    for rel in [*pkg_manifest["files"], bd.PACKAGE_MANIFEST]:
        dst = pkg_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(os.path.join(package_root, rel), dst)
    shutil.copyfile(envelope_path, member / "combination_envelope.json")
    if not feature_provenance:
        raise MemberError("the batch's feature provenance sidecar is required (actual no-fill/missingness provenance)")
    (reports / "ipcch_feature_fill_audit.csv").write_bytes(feature_provenance)     # existing file name, v2 schema
    files = sorted(rel for rel in (str(p.relative_to(out)).replace(os.sep, "/") for p in out.rglob("*") if p.is_file())
                   if is_member_file(rel))
    provenance = {"schema": PROVENANCE_SCHEMA, "system": "ipcch", "contract": CONTRACT, "mode": manifest["mode"],
                  "execution_month": M, "feature_origin": O, "horizons": horizons,
                  "package": {"combination_id": binding.combination_id, "envelope_id": binding.envelope_id,
                              "envelope_sha256": binding.envelope_sha256,
                              "package_manifest_sha256": binding.package_manifest_sha256,
                              "feature_order_sha256": binding.feature_order_sha256},
                  "batch": {"batch_id": manifest["batch_id"], "designation": manifest["designation"]},
                  "roster": {"size": len(roster), "sha256": bt.roster_sha256(roster)},
                  "files": {rel: _sha(out / rel) for rel in files}}
    with open(member / "system_provenance.json", "x") as f:
        f.write(json.dumps(provenance, indent=1, sort_keys=True) + "\n")
    return {**provenance, "provenance_sha256": _sha(member / "system_provenance.json")}


def _verify_geometry(path: Path, roster_sha: str, size: int) -> None:
    from shapely.geometry import shape

    try:
        geo = json.loads(path.read_text())
    except ValueError as exc:
        raise MemberError(f"polygons.geojson is not JSON: {exc}") from exc
    if (geo.get("type") != "FeatureCollection"
            or geo.get("crs", {}).get("properties", {}).get("name") != "EPSG:4326"):
        raise MemberError("polygons.geojson must be an EPSG:4326 FeatureCollection")
    ids = [str((f.get("properties") or {}).get("polygon_id")) for f in geo.get("features", [])]
    if len(ids) != size or len(set(ids)) != size or bt.roster_sha256(ids) != roster_sha:
        raise MemberError("polygons.geojson is not exactly the unique roster")
    for f in geo["features"]:
        try:
            g = shape(f["geometry"])
        except Exception as exc:
            raise MemberError(f"polygon {f['properties']['polygon_id']}: unreadable geometry ({exc})") from exc
        if g.is_empty or not g.is_valid or g.geom_type not in ("Polygon", "MultiPolygon"):
            raise MemberError(f"polygon {f['properties']['polygon_id']}: empty, invalid or non-polygon geometry")


def verify_member(out: Path, *, expected: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Re-verify an IPCCH member in a delivery tree (new or inherited), independent of its own inventory: exactly
    H2/H8/H14 with leads 0/6/12, O = M - 2 and T = M + lead; every required file present and listed; every listed file
    re-hashed and nothing unlisted (the same member predicate as the writer); the copied envelope equal to the recorded
    digest and identity (accepted in real mode); the model package re-verified against the recorded manifest digest;
    polygons.geojson exactly the unique roster with valid EPSG:4326 polygons; per horizon roster-exact unique polygons,
    finite q2..q5, O, target, mode and package id. ``expected`` (the release member record) must match the provenance
    identity (months, mode, package and, when given, the provenance digest)."""
    out = Path(out)
    path = out / "ipcch" / "system_provenance.json"
    if not path.is_file():
        raise MemberError("member has no ipcch/system_provenance.json")
    prov = json.loads(path.read_text())
    if prov.get("schema") != PROVENANCE_SCHEMA or prov.get("contract") != CONTRACT:
        raise MemberError("member provenance schema/contract not recognised")
    M, O = prov.get("execution_month"), prov.get("feature_origin")
    if not (isinstance(M, str) and isinstance(O, str)) or _add_months(M, -2) != O:
        raise MemberError("member feature origin is not M - 2")
    hz = sorted((h.get("model_horizon_months"), h.get("public_lead_months"), h.get("target_month"))
                for h in prov.get("horizons", []))
    want = sorted((h, lead, _add_months(M, lead)) for h, lead in LEADS.items())
    if hz != want:
        raise MemberError(f"member horizons {hz} are not exactly H2/H8/H14 with leads 0/6/12 and targets M+lead (R18)")
    if expected is not None:
        for key in ("execution_month", "feature_origin", "mode"):
            if prov.get(key) != expected.get(key):
                raise MemberError(f"member {key} {prov.get(key)} != expected {expected.get(key)}")
        if expected.get("package") is not None and prov.get("package") != expected["package"]:
            raise MemberError("member package identity differs from the expected (release) identity")
        if expected.get("provenance_sha256") and _sha(path) != expected["provenance_sha256"]:
            raise MemberError("member system_provenance.json differs from the release record")
    listed = prov["files"]
    present = {rel for rel in (str(p.relative_to(out)).replace(os.sep, "/") for p in out.rglob("*") if p.is_file())
               if is_member_file(rel)} - {"ipcch/system_provenance.json"}
    lacking = [r for r in REQUIRED_FILES if r not in listed or r not in present]
    if lacking:
        raise MemberError(f"member lacks required files {lacking[:3]}")
    if set(listed) != present:
        raise MemberError(f"member files differ from provenance: missing {sorted(set(listed) - present)[:3]}, "
                          f"unlisted {sorted(present - set(listed))[:3]}")
    bad = [rel for rel, sha in listed.items() if _sha(out / rel) != sha]
    if bad:
        raise MemberError(f"member files changed: {bad[:3]}")
    package = prov["package"]
    env_path = out / "ipcch" / "combination_envelope.json"
    if _sha(env_path) != package.get("envelope_sha256"):
        raise MemberError("copied combination envelope is not the recorded envelope")
    env = json.loads(env_path.read_text())
    if (env.get("schema") != bd.ENVELOPE_SCHEMA or env.get("envelope_id") != package.get("envelope_id")
            or env.get("package", {}).get("combination_id") != package.get("combination_id")
            or env.get("package", {}).get("package_manifest_sha256") != package.get("package_manifest_sha256")
            or env.get("package", {}).get("feature_order_sha256") != package.get("feature_order_sha256")):
        raise MemberError("copied combination envelope identity differs from the provenance")
    if prov.get("mode") == "real" and env.get("status") != "accepted":
        raise MemberError("a real member must carry an accepted combination envelope (R51)")
    try:
        ident = bd.package_identity(str(out / "ipcch" / "model_package"))
    except bd.BindingError as exc:
        raise MemberError(f"member model package: {exc}") from exc
    if (ident["package_manifest_sha256"], ident["combination_id"]) != (package["package_manifest_sha256"],
                                                                      package["combination_id"]):
        raise MemberError("member model package is not the recorded combination")
    _verify_geometry(out / "ipcch" / "polygons.geojson", prov["roster"]["sha256"], prov["roster"]["size"])
    for h in prov["horizons"]:
        lead = h["public_lead_months"]
        p = pd.read_csv(out / f"scopes/{lead}m/ipcch/polygon_predictions.csv", dtype={"polygon_id": str, "admin_code": str,
                                                                                    "area_id": str})
        if tuple(p.columns) != V2_PREDICTION_HEADER:
            raise MemberError(f"lead {lead}: prediction header is not the v2 contract header")
        ok = (len(p) == prov["roster"]["size"] and p["polygon_id"].is_unique
              and bt.roster_sha256(p["polygon_id"]) == prov["roster"]["sha256"]
              and np.isfinite(p[list(SCORES)].to_numpy(float)).all()
              and set(p["feature_period"]) == {O} and set(p["target_period"]) == {h["target_month"]}
              and set(p["mode"]) == {prov["mode"]} and set(p["model_package_id"]) == {h["model_package_id"]})
        if not ok:
            raise MemberError(f"lead {lead}: predictions do not verify (roster/finite/periods/mode/package)")
    return prov
