"""Crosswalk diagnostics for frozen HDX FEWS NET CS labels against the 5,718 production areas.

Stage 1 (per reporting month): verify the FDW unit-geometry records against the frozen HDX CSV
records (record `id` unique in the FDW month, the HDX month and the whole HDX freeze, joined
one-to-one; same country, reporting month, fnid and value). Only records passing every check
can later be accepted. Each production polygon is then intersected with all units of its own
country in EPSG:6933, whatever their unit type (camps, urban units and parks are kept and
reported, not dropped). For every (area, unit) pair it records
  cov_area = |P ∩ U| / |P|, cov_unit = |P ∩ U| / |U|, reciprocal = min(cov_area, cov_unit).
Stage 2 is done by `crosswalk_decide.py`; this script never assigns labels.

Usage: python crosswalk_cs_labels.py --hdx <freeze dir> --geometry <month geojson>...
           --production <production_geometry_6933.parquet> --out <dir>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely


def load_hdx(freeze: Path) -> pd.DataFrame:
    receipt = json.loads((freeze / "retrieval_receipt.json").read_text("utf-8"))
    frames = []
    for iso2, entry in receipt["countries"].items():
        for resource in entry["resources"]:
            if resource["format"] == "CSV":
                frame = pd.read_csv(freeze / iso2 / resource["download"]["local_file"],
                                    dtype=str, keep_default_na=False, na_values=[""])
                frame["roster_iso2"] = iso2
                frame["hdx_resource_id"] = resource["hdx_resource_id"]
                frames.append(frame)
    hdx = pd.concat(frames, ignore_index=True)
    hdx["month"] = hdx["reporting_date"].str[:7]
    hdx["phase"] = pd.to_numeric(hdx["value"], errors="coerce")
    return hdx


def record_checks(units: gpd.GeoDataFrame, month_hdx: pd.DataFrame, month: str,
                  freeze_id_counts: pd.Series) -> dict:
    """Return join diagnostics and the set of FDW record ids that pass every check."""
    fdw_counts = units["id"].value_counts()
    hdx_counts = month_hdx["id"].value_counts()
    joined = units[["id", "fnid", "value", "country_code", "reporting_date"]].merge(
        month_hdx[["id", "fnid", "phase", "roster_iso2", "month"]], on="id", how="outer",
        suffixes=("_fdw", "_hdx"), indicator=True)
    both = joined["_merge"] == "both"
    fdw_value = pd.to_numeric(joined["value"], errors="coerce")
    unique = (joined["id"].map(fdw_counts).eq(1) & joined["id"].map(hdx_counts).eq(1)
              & joined["id"].map(freeze_id_counts).eq(1))
    ok = (both & unique
          & (joined["fnid_fdw"] == joined["fnid_hdx"])
          & (joined["country_code"] == joined["roster_iso2"])
          & (pd.to_datetime(joined["reporting_date"], errors="coerce").dt.strftime("%Y-%m")
             == month)
          & (joined["month"] == month)
          & ((fdw_value == joined["phase"]) | (fdw_value.isna() & joined["phase"].isna())))
    return {
        "fdw_records": int(len(units)),
        "fdw_id_unique": bool(units["id"].is_unique),
        "hdx_records": int(len(month_hdx)),
        "hdx_id_unique_in_month": bool(month_hdx["id"].is_unique),
        "hdx_id_unique_whole_freeze_for_month": bool(month_hdx["id"].map(freeze_id_counts).eq(1).all()),
        "join": {k: int(v) for k, v in joined["_merge"].value_counts().items()},
        "records_with_unique_ids": int(unique.sum()),
        "records_passing_all_checks": int(ok.sum()),
        "failing_record_ids": sorted(joined.loc[~ok, "id"].astype(str))[:50],
        "passing_ids": set(joined.loc[ok, "id"]),
    }


def overlap_pairs(production: gpd.GeoDataFrame, units: gpd.GeoDataFrame) -> pd.DataFrame:
    tree = shapely.STRtree(units.geometry.values)
    p_idx, u_idx = tree.query(production.geometry.values, predicate="intersects")
    keep = production["ISO"].values[p_idx] == units["country_code"].values[u_idx]
    p_idx, u_idx = p_idx[keep], u_idx[keep]
    inter = shapely.area(shapely.intersection(production.geometry.values[p_idx],
                                              units.geometry.values[u_idx]))
    pairs = pd.DataFrame({
        "admin_code": production["admin_code"].values[p_idx],
        "ISO": production["ISO"].values[p_idx],
        "id": units["id"].values[u_idx], "fnid": units["fnid"].values[u_idx],
        "unit_type": units["unit_type"].values[u_idx],
        "unit_full_name": units["geographic_unit_full_name"].values[u_idx],
        "phase": units["phase"].values[u_idx],
        "record_checks_pass": units["record_checks_pass"].values[u_idx],
        "intersection_m2": inter,
        "cov_area": inter / production["area_m2"].values[p_idx],
        "cov_unit": inter / units["unit_area_m2"].values[u_idx],
    })
    pairs = pairs[pairs["intersection_m2"] > 0].copy()
    pairs["reciprocal"] = pairs[["cov_area", "cov_unit"]].min(axis=1)
    return pairs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hdx", required=True, type=Path)
    parser.add_argument("--geometry", required=True, type=Path, nargs="+")
    parser.add_argument("--production", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    production = gpd.read_parquet(args.production)
    countries = set(production["ISO"])
    hdx = load_hdx(args.hdx)
    summary = {"hdx_id_unique_whole_freeze": bool(hdx["id"].is_unique),
               "hdx_rows": int(len(hdx)), "months": {}}
    for path in args.geometry:
        month = path.stem.removeprefix("CS_")
        units = gpd.read_file(path, engine="pyogrio")
        units = units[units["country_code"].isin(countries)].copy()
        units["id"] = units["id"].astype(str)
        checks = record_checks(units, hdx[hdx["month"] == month], month,
                               hdx["id"].value_counts())
        units = units.merge(hdx.loc[hdx["month"] == month, ["id", "phase"]], on="id",
                            how="left")
        units["record_checks_pass"] = units["id"].isin(checks.pop("passing_ids"))
        units["geometry"] = shapely.make_valid(units.geometry.values)
        units = units.to_crs(6933)
        units["unit_area_m2"] = units.area
        pairs = overlap_pairs(production, units)
        pairs.insert(0, "month", month)
        pairs.to_parquet(args.out / f"overlap_pairs_{month}.parquet")
        summary["months"][month] = checks | {
            "unit_types": {k: int(v) for k, v in units["unit_type"].value_counts().items()},
            "pairs": int(len(pairs))}
        print(month, json.dumps({k: v for k, v in checks.items()
                                 if k != "failing_record_ids"}), flush=True)
    (args.out / "record_checks.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
