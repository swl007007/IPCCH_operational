"""Strict crosswalk decisions and diagnostics from `crosswalk_cs_labels.py` overlap pairs.

A production area receives a candidate label for month M only if
  * exactly one unit (any unit type) of the same country is boundary-equivalent to it within the
    measured numerical tolerance (reciprocal overlap >= TOLERANCE, see below),
  * that unit is equivalent to no other production area in M (one-to-one),
  * the unit's FDW geometry record passed the record checks against the frozen HDX record
    (unique id, one-to-one join, country, month, fnid and value agree), and
  * the HDX phase is a valid 1-5 value. Missing/invalid phases stay missing.
TOLERANCE comes from the production-vintage month (2021-06), where the units the production
polygons were cut from match at 1 - reciprocal <= 1e-6. Looser overlaps are reported only.
The production-vintage fnid linked to each area is reported as persistent-ID evidence.

Old 2025-10/2026-02 panel labels are classed by lineage: `source_FEWS_2025` when FEWS_2025.csv
carries a value for the key, `imputed_fill_proven` when it does not and the panel value is the
fill value 1 written by assemble_latest_FEWSNET/01_extract_invariables_and_scaffold.ipynb cell 38
(`fews_ipc.fillna(1)`), else `unverified_lineage`. Old values are never changed here.

Usage: python crosswalk_decide.py --pairs <strict dir> --labels <training_panel_labels.parquet>
           --fews2025 <FEWS_2025.csv> --production <production_geometry_6933.parquet> --out <dir>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

TOLERANCE = 0.999999
DIAGNOSTIC_THRESHOLDS = (0.99, 0.999, 0.9999, 0.99999, 0.999999)
VINTAGE = "2021-06"
TARGETS = ("2024-10", "2025-10", "2026-02", "2026-06")
VALID = {1.0, 2.0, 3.0, 4.0, 5.0}
COMPETING_MIN_COVERAGE = 1e-6
FILLED_MONTHS = ("2025-10", "2026-02")
FILL_VALUE = 1.0


def strict_matches(pairs: pd.DataFrame) -> pd.DataFrame:
    """One row per area with its unique, one-to-one, record-checked equivalent unit."""
    eq = pairs[(pairs["reciprocal"] >= TOLERANCE) & pairs["record_checks_pass"]]
    per_area = eq.groupby("admin_code")["id"].transform("size")
    per_unit = eq.groupby("id")["admin_code"].transform("size")
    return eq[(per_area == 1) & (per_unit == 1)].set_index("admin_code")


def area_diagnostics(pairs: pd.DataFrame, codes: pd.Index) -> pd.DataFrame:
    ordered = pairs.sort_values("reciprocal", ascending=False)
    best = ordered.drop_duplicates("admin_code").set_index("admin_code")
    competing = pairs[pairs["cov_area"] > COMPETING_MIN_COVERAGE]
    stats = competing.groupby("admin_code").agg(
        overlapping_units=("id", "size"),
        overlapping_valid_phases=("phase", lambda s: int(s[s.isin(VALID)].nunique())))
    out = pd.DataFrame(index=codes)
    out["best_fnid"] = best["fnid"]
    out["best_reciprocal"] = best["reciprocal"]
    out["best_cov_area"] = best["cov_area"]
    out["best_cov_unit"] = best["cov_unit"]
    out["best_phase"] = best["phase"]
    out = out.join(stats)
    out["overlapping_units"] = out["overlapping_units"].fillna(0).astype(int)
    out["overlapping_valid_phases"] = out["overlapping_valid_phases"].fillna(0).astype(int)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", required=True, type=Path)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--fews2025", required=True, type=Path)
    parser.add_argument("--production", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    production = gpd.read_parquet(args.production).drop(columns="geometry")
    codes = pd.Index(production["admin_code"], name="admin_code")
    names = production.set_index("admin_code")["unit_name"]
    iso = production.set_index("admin_code")["ISO"]

    panel = pd.read_parquet(args.labels)
    panel["month"] = panel["date"].str[:7]
    panel = panel.rename(columns={"FEWSNET_admin_code": "admin_code"})
    old = pd.read_csv(args.fews2025)
    old = old[old["fews_ipc"].notna()]
    old["admin_code"] = old["admin_code"].astype(int).astype(str)
    old["month"] = (old["year"].astype(int).astype(str) + "-"
                    + old["month"].astype(int).map("{:02d}".format))
    name_merged = set(zip(old["admin_code"], old["month"]))

    vintage = strict_matches(pd.read_parquet(args.pairs / f"overlap_pairs_{VINTAGE}.parquet"))
    vintage_fnid = vintage["fnid"].reindex(codes)
    summary: dict[str, object] = {
        "tolerance": TOLERANCE, "vintage_month": VINTAGE,
        "vintage_strict_links": int(vintage_fnid.notna().sum()),
        "months": {}}
    rows = []
    for month in TARGETS:
        pairs = pd.read_parquet(args.pairs / f"overlap_pairs_{month}.parquet")
        strict = strict_matches(pairs).reindex(codes)
        diag = area_diagnostics(pairs, codes)
        frame = pd.DataFrame(index=codes)
        frame["month"] = month
        frame["ISO"] = iso
        frame["production_unit_name"] = names
        frame["fnid"] = strict["fnid"]
        frame["hdx_record_id"] = strict["id"]
        frame["unit_type"] = strict["unit_type"]
        frame["unit_full_name"] = strict["unit_full_name"]
        frame["reciprocal"] = strict["reciprocal"]
        frame["hdx_phase"] = strict["phase"]
        frame["vintage_fnid"] = vintage_fnid
        frame["fnid_persistent"] = frame["fnid"].notna() & (frame["fnid"] == frame["vintage_fnid"])
        frame["name_equal"] = frame["unit_full_name"] == frame["production_unit_name"]
        frame = frame.join(diag)
        reported = pairs.groupby("admin_code")["fnid"].agg(set).reindex(codes)
        frame["vintage_fnid_reported_in_month"] = [
            isinstance(fnids, set) and vf in fnids
            for fnids, vf in zip(reported, frame["vintage_fnid"])]
        has_unit = frame["fnid"].notna()
        valid = frame["hdx_phase"].isin(VALID)
        frame["accepted_phase"] = frame["hdx_phase"].where(has_unit & valid)
        frame["gap_reason"] = np.select(
            [has_unit & valid, has_unit & ~valid, frame["best_fnid"].isna()],
            [None, "equivalent_unit_phase_missing_or_invalid", "no_overlapping_unit"],
            default="no_boundary_equivalent_unit")
        prod = panel[panel["month"] == month].set_index("admin_code")["fews_ipc"].reindex(codes)
        frame["production_phase"] = prod
        frame["production_label_source"] = np.where(
            prod.isna(), "none",
            np.where([(c, month) in name_merged for c in codes], "source_FEWS_2025",
                     np.where(month not in FILLED_MONTHS, "historical",
                              np.where(prod == FILL_VALUE, "imputed_fill_proven",
                                       "unverified_lineage"))))
        accepted = frame["accepted_phase"].notna()
        same = accepted & (frame["accepted_phase"] == frame["production_phase"])
        frame["comparison"] = np.select(
            [accepted & frame["production_phase"].isna(),
             accepted & (frame["production_label_source"] == "imputed_fill_proven"),
             same,
             accepted & ~same,
             ~accepted & (frame["production_label_source"] == "imputed_fill_proven"),
             ~accepted & frame["production_phase"].notna()],
            ["addition_no_production_label", "replaces_proven_imputed_fill",
             "agrees_with_production", "differs_from_production",
             "proven_imputed_fill_no_strict_label",
             "production_label_no_strict_label"],
            default="gap_no_production_label")
        frame = frame.reset_index()
        accepted = frame["accepted_phase"].notna()
        rows.append(frame)
        best = diag["best_reciprocal"]
        summary["months"][month] = {
            "areas_with_overlap": int(best.notna().sum()),
            "best_reciprocal_at_least": {str(t): int((best >= t).sum())
                                         for t in DIAGNOSTIC_THRESHOLDS},
            "strict_equivalent_units": int(has_unit.sum()),
            "accepted_valid_phase": int(accepted.sum()),
            "accepted_countries": int(frame.loc[accepted, "ISO"].nunique()),
            "accepted_fnid_persistent_from_vintage": int(frame.loc[accepted, "fnid_persistent"].sum()),
            "accepted_name_equal": int(frame.loc[accepted, "name_equal"].sum()),
            "accepted_unit_types": {k: int(v) for k, v in
                                    frame.loc[accepted, "unit_type"].value_counts().items()},
            "strict_equivalent_unit_types": {k: int(v) for k, v in
                                             frame["unit_type"].value_counts().items()},
            "vintage_fnid_reported_in_month": int(frame["vintage_fnid_reported_in_month"].sum()),
            "vintage_fnid_reported_but_not_strict": int(
                (frame["vintage_fnid_reported_in_month"] & frame["fnid"].isna()).sum()),
            "accepted_with_competing_overlap": int((frame.loc[accepted, "overlapping_units"] > 1).sum()),
            "gap_reason": {k: int(v) for k, v in frame["gap_reason"].value_counts().items()},
            "nonstrict_areas_with_conflicting_overlap_phases":
                int(((~accepted) & (frame["overlapping_valid_phases"] > 1)).sum()),
            "comparison": {k: int(v) for k, v in frame["comparison"].value_counts().items()},
            "accepted_by_country": {k: int(v) for k, v in
                                    frame.loc[accepted].groupby("ISO").size().items()},
            "accepted_phase_counts": {str(int(k)): int(v) for k, v in
                                      frame.loc[accepted, "accepted_phase"].value_counts().sort_index().items()},
        }
        print(month, json.dumps({k: summary["months"][month][k] for k in
                                 ("accepted_valid_phase", "accepted_fnid_persistent_from_vintage",
                                  "comparison")}), flush=True)
    decisions = pd.concat(rows, ignore_index=True)
    decisions.to_csv(args.out / "strict_crosswalk_decisions.csv", index=False)
    (args.out / "strict_crosswalk_summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
