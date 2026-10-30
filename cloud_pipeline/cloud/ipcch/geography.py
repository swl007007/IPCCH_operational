"""Fixed IPCCH geography for every provider and output population (task 10-29; R32, R55, R64, design.md:27).

The handoff geometry and the byte-preserved ACLED tables carry one admin outside the 6,226-area training roster (1315);
the bundle manifest declares it per file (``roster_policy[...]["out_of_roster_admins"]``). Every provider computes on, and
every computed output covers, exactly the roster:

* ``roster_geometries``: the bundle shapefile (each component re-hashed against the manifest) filtered to the roster in
  roster order, as the GeoJSON mapping the existing zonal-statistics path (``remote_sources.native_geometries``) requires
  to equal the roster. A missing roster area, a duplicate, an undeclared extra admin or a non-EPSG:4326 file fails.
* ``restrict_to_roster``: a provider output table (e.g. the shared GEE admin assets' 6,227 rows) reduced to the roster;
  only declared extras are dropped (and counted), anything else unknown fails (R32), every roster area must be present.
* ``population_snapshot``: the output population fields (estimate, reference period, imputation method) for feature
  month O from the delivered population reference through the existing no-future ``PopulationSnapshotBuilder``: the
  latest reference period <= O per area (observed when equal to O, else carried forward); later periods are never used.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any, Iterable, Mapping

import pandas as pd

from model_pipeline.ipcch_launch_runtime.population import (
    POPULATION_OUTPUT_COLUMNS,
    PopulationSnapshotBuilder,
    validate_population_contract,
)

GEOMETRY_PREFIX = "fixed/geometry/"
GEOMETRY_CRS = "EPSG:4326"


class GeographyError(RuntimeError):
    """The fixed geography contract (R32) is violated; nothing was computed."""


def declared_extras(manifest: Mapping[str, Any], rel: str | None = None) -> frozenset[str]:
    """Admins outside the roster that the bundle declares as fixed-source exceptions (one file, or all files)."""
    out = set()
    for name, policy in manifest.get("roster_policy", {}).items():
        extra = policy.get("out_of_roster_admins") if isinstance(policy, Mapping) else None
        if (rel is None or name == rel) and isinstance(extra, list):
            out.update(str(int(a)) for a in extra)
    return frozenset(out)


def _codes(values: Iterable[Any], label: str) -> list[str]:
    codes = [str(v).strip() for v in values]
    bad = sorted({c for c in codes if not c.isdigit() or c != str(int(c))})
    if bad:
        raise GeographyError(f"{label}: admin_code values must be canonical integers, got {bad[:5]}")
    return codes


def restrict_to_roster(frame: pd.DataFrame, roster: Iterable[Any], *, declared_extra: Iterable[str] = (),
                       label: str, key: str = "admin_code") -> tuple[pd.DataFrame, list[str]]:
    """(rows of exactly the roster in roster order, dropped declared extras); unknown or missing areas fail."""
    roster = _codes(roster, f"{label} roster")
    codes = pd.Series(_codes(frame[key], label), index=frame.index)
    if codes.duplicated().any():
        raise GeographyError(f"{label}: duplicate {key} {sorted(set(codes[codes.duplicated()]))[:5]}")
    inside = codes.isin(roster)
    extra = sorted(set(codes[~inside]))
    unknown = sorted(set(extra) - set(declared_extra))
    if unknown:
        raise GeographyError(f"{label}: unknown modeled-area identifiers {unknown[:5]} (R32)")
    missing = sorted(set(roster) - set(codes))
    if missing:
        raise GeographyError(f"{label}: lacks {len(missing)} roster areas {missing[:5]}")
    out = frame[inside.to_numpy()].assign(**{key: codes[inside].to_numpy()})
    out = out.set_index(key).loc[roster].reset_index()
    return out, extra


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def roster_geometries(bundle_dir: str, manifest: Mapping[str, Any], roster: Iterable[Any]) -> tuple[dict, dict[str, Any]]:
    """(GeoJSON FeatureCollection of exactly the roster, report) from the bundle's fixed geometry."""
    import geopandas
    from shapely.geometry import mapping

    parts = sorted(rel for rel in manifest.get("files", {}) if rel.startswith(GEOMETRY_PREFIX))
    shp = [rel for rel in parts if rel.endswith(".shp")]
    if len(shp) != 1:
        raise GeographyError(f"bundle must list exactly one geometry .shp under {GEOMETRY_PREFIX}, got {shp}")
    stem = shp[0][:-4]
    for rel in parts:
        if not rel.startswith(stem + "."):
            raise GeographyError(f"unexpected geometry file {rel}")
        if _sha(os.path.join(bundle_dir, rel)) != manifest["files"][rel]["sha256"]:
            raise GeographyError(f"{rel}: bytes differ from the bundle manifest")
    for ext in (".shp", ".shx", ".dbf", ".prj"):
        if stem + ext not in parts:
            raise GeographyError(f"geometry component {stem + ext} is not listed in the bundle manifest")
    gdf = geopandas.read_file(os.path.join(bundle_dir, shp[0]))
    if gdf.crs is None or gdf.crs.to_string() != GEOMETRY_CRS:
        raise GeographyError(f"geometry CRS {gdf.crs} != {GEOMETRY_CRS}")
    if gdf.geometry.isna().any() or gdf.geometry.is_empty.any():
        raise GeographyError("geometry has null or empty shapes")
    kept, dropped = restrict_to_roster(gdf[["admin_code", "geometry"]], roster,
                                       declared_extra=declared_extras(manifest, stem + ".dbf"), label=shp[0])
    fc = {"type": "FeatureCollection",
          "features": [{"type": "Feature", "properties": {"admin_code": code}, "geometry": mapping(geom)}
                       for code, geom in zip(kept["admin_code"], kept["geometry"])]}
    return fc, {"source": shp[0], "features": len(fc["features"]), "dropped_declared_extra": dropped}


def population_snapshot(reference: pd.DataFrame, *, origin: str, roster: Iterable[Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Output population fields for every roster area at feature month O (no future reference period is used)."""
    if list(reference.columns) != ["admin_code", "reference_period", "population_estimate"]:
        raise GeographyError("population reference needs exactly admin_code, reference_period, population_estimate")
    roster = _codes(roster, "population roster")
    codes = _codes(reference["admin_code"], "population reference")
    unknown = sorted(set(codes) - set(roster))
    if unknown:
        raise GeographyError(f"population reference has unknown modeled areas {unknown[:5]} (R32)")
    periods = reference["reference_period"].astype(str)
    if not periods.str.fullmatch(r"\d{4}-(0[1-9]|1[0-2])").all():
        raise GeographyError("population reference_period must be YYYY-MM")
    year, month = int(origin[:4]), int(origin[5:])
    builder = PopulationSnapshotBuilder(feature_year=year, feature_month=month)
    future = 0
    for code, period, value in zip(codes, periods, reference["population_estimate"]):
        future += int(period > origin)
        builder.add(code, int(period[:4]), int(period[5:]), value)
    snapshot, counts = builder.build(roster)
    out = pd.DataFrame({"admin_code": roster, **{c: [snapshot[a][c] for a in roster] for c in POPULATION_OUTPUT_COLUMNS}})
    methods = validate_population_contract(out, feature_month=origin)
    return out, {**counts, "method_counts": methods, "future_reference_rows_ignored": future,
                 "latest_reference_period": max(out["population_reference_period"])}
