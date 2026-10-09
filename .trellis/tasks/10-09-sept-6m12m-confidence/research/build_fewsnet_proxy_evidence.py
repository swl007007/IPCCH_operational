"""One-time builder: FEWSNET 6m/12m Stage3 proxy area evidence (user decisions D4/D9/D14).

Per polygon, count saved Stage3 partitioned decisions ``y_pred_partitioned != y_true`` (the
September h5 rule: saved decisions, no re-thresholding). Gate G1 first rebuilds the h5 counts
from ``georf_fs1`` and requires an exact per-polygon match with the accepted
``september_manual/fewsnet/polygon_confidence.csv``; only then are fs2 -> 6m and fs3 -> 12m
evidence CSVs written to ``cloud_pipeline/bootstrap/evidence/``.

Reads external research outputs read-only; the cloud runtime never reads them.
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve()
REPO = HERE.parents[4]
CP = REPO / "cloud_pipeline"
STAGE3 = REPO.parent / ("Google fund/Analysis/2.source_code/Step5_Geo_RF_trial/food_crisis_cluster/"
                        "paper_reproducibility_package/stage3_results")
EVIDENCE = CP / "bootstrap/evidence"
REPORT = HERE.parent / "fewsnet_proxy_evidence.json"
SEPTEMBER = REPO / "september_manual/fewsnet/polygon_confidence.csv"
PROXIES = {  # horizon -> (Stage3 run, basis label approved 2026-10-09)
    6: ("georf_fs2", "h6_validation_error_proxy_stage3_fs2_lag8_2021_2024"),
    12: ("georf_fs3", "h12_validation_error_proxy_stage3_fs3_lag12_2021_2024"),
}
EXPECTED_PERIOD = "2021-02..2024-10"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def roster() -> list[str]:
    ids = pd.read_csv(CP / "bootstrap/assets/fewsnet/roster.csv", dtype=str)["admin_code"].str.strip()
    assert not ids.duplicated().any() and len(ids) == 5718, len(ids)
    return ids.tolist()


def area_counts(run: str) -> tuple[pd.DataFrame, str, dict]:
    path = STAGE3 / run / "predictions_monthly.csv"
    rows = pd.read_csv(path, dtype={"FEWSNET_admin_code": str})
    rows["polygon_id"] = rows["FEWSNET_admin_code"].str.strip()
    assert not rows.duplicated(["polygon_id", "month_start"]).any()
    assert rows["y_true"].isin([0, 1]).all() and rows["y_pred_partitioned"].isin([0, 1]).all()
    rows["target_month"] = pd.to_datetime(rows["month_start"]).dt.to_period("M").astype(str)
    rows["error"] = rows["y_pred_partitioned"].ne(rows["y_true"]).astype(int)
    counts = rows.groupby("polygon_id").agg(sample_count=("error", "size"), error_count=("error", "sum")).reset_index()
    period = f"{rows['target_month'].min()}..{rows['target_month'].max()}"
    source = {"path": str(path.relative_to(REPO.parent)), "sha256": sha256(path), "rows": len(rows),
              "polygons": int(counts["polygon_id"].nunique()), "errors": int(rows["error"].sum()),
              "months": sorted(rows["target_month"].unique().tolist()), "period": period,
              "exact_half_probability_rows": int((rows["y_prob_partitioned"] == 0.5).sum()),
              "run_manifest_sha256": sha256(STAGE3 / run / "run_manifest.json"),
              "run_manifest": json.loads((STAGE3 / run / "run_manifest.json").read_text())}
    return counts, period, source


def regression_g1(ids: list[str]) -> dict:
    counts, period, source = area_counts("georf_fs1")
    accepted = pd.read_csv(SEPTEMBER, dtype={"polygon_id": str})
    merged = accepted[["polygon_id", "historical_sample_count", "historical_error_count"]].merge(
        counts, on="polygon_id", how="outer", indicator=True)
    only_stage3 = merged.loc[merged["_merge"].eq("right_only"), "polygon_id"].tolist()
    a = merged.loc[merged["_merge"].eq("both")]
    sample_mismatch = a["historical_sample_count"].astype("Int64").ne(a["sample_count"].astype("Int64")).fillna(True)
    error_mismatch = a["historical_error_count"].astype("Int64").ne(a["error_count"].astype("Int64")).fillna(True)
    # Accepted rows with no Stage3 history must be blank there too.
    left = merged.loc[merged["_merge"].eq("left_only")]
    blank_ok = left[["historical_sample_count", "historical_error_count"]].isna().all(axis=None)
    bad = a.loc[sample_mismatch | error_mismatch, "polygon_id"].tolist()
    passed = not bad and not only_stage3 and bool(blank_ok) and period == EXPECTED_PERIOD
    return {"gate": "G1", "passed": passed, "reference": str(SEPTEMBER.relative_to(REPO)),
            "reference_sha256": sha256(SEPTEMBER), "stage3_source": source,
            "compared_polygons": len(a), "mismatched_polygons": bad[:50], "mismatch_count": len(bad),
            "stage3_ids_absent_from_accepted": only_stage3,
            "accepted_polygons_without_stage3": sorted(left["polygon_id"].tolist(), key=int),
            "accepted_blank_where_absent": bool(blank_ok),
            "total_samples": int(counts["sample_count"].sum()), "total_errors": int(counts["error_count"].sum()),
            "accepted_total_errors": int(accepted["historical_error_count"].sum()),
            "roster_size": len(ids)}


def write_create_only(path: Path, data: bytes) -> str:
    if path.exists():
        if path.read_bytes() != data:
            raise SystemExit(f"{path} exists with different bytes; refusing to overwrite")
        return "unchanged"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    assert tmp.read_bytes() == data
    tmp.rename(path)
    return "written"


def main() -> int:
    ids = roster()
    baseline = json.loads((CP / "bootstrap/baseline.json").read_text())
    packages = {m["horizon_months"]: m["package_id"] for m in baseline["models"] if m["system"] == "fewsnet"}
    report = {"builder": str(HERE.relative_to(REPO)), "builder_sha256": sha256(HERE),
              "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
              "python": sys.version.split()[0], "platform": platform.platform(), "pandas": pd.__version__,
              "error_rule": "int(y_pred_partitioned != y_true) on saved Stage3 decisions; no re-thresholding",
              "roster": {"path": "cloud_pipeline/bootstrap/assets/fewsnet/roster.csv",
                         "sha256": sha256(CP / "bootstrap/assets/fewsnet/roster.csv"), "size": len(ids)}}
    report["regression"] = regression_g1(ids)
    if not report["regression"]["passed"]:
        REPORT.write_text(json.dumps(report, indent=1) + "\n")
        print(json.dumps(report["regression"], indent=1)[:4000])
        print("G1 FAILED: no 6m/12m evidence written", file=sys.stderr)
        return 1
    print(f"G1 PASS: {report['regression']['compared_polygons']} polygons exact, "
          f"{report['regression']['total_errors']} errors / {report['regression']['total_samples']} samples")
    roster_set = set(ids)
    report["evidence"] = {}
    for horizon, (run, basis) in PROXIES.items():
        counts, period, source = area_counts(run)
        if period != EXPECTED_PERIOD:
            raise SystemExit(f"{run}: observed period {period} differs from approved {EXPECTED_PERIOD}")
        dropped = sorted(set(counts["polygon_id"]) - roster_set, key=int)
        kept = counts.loc[counts["polygon_id"].isin(roster_set)].copy()
        kept = kept.sort_values("polygon_id", key=lambda s: s.astype(int)).reset_index(drop=True)
        kept["model_package_id"] = packages[horizon]
        kept["horizon_months"] = horizon
        kept["basis"] = basis
        kept["period"] = period
        name = f"fewsnet_{horizon}m_stage3_{run.split('_')[1]}_area.csv"
        data = kept[["polygon_id", "sample_count", "error_count", "model_package_id", "horizon_months", "basis",
                     "period"]].to_csv(index=False, lineterminator="\n").encode()
        status = write_create_only(EVIDENCE / name, data)
        report["evidence"][name] = {
            "system": "fewsnet", "horizon_months": horizon, "model_package_id": packages[horizon], "basis": basis,
            "period": period, "source": source, "rows": len(kept), "dropped_non_roster_ids": dropped,
            "roster_polygons_without_evidence": sorted(roster_set - set(kept["polygon_id"]), key=int),
            "sample_total": int(kept["sample_count"].sum()), "error_total": int(kept["error_count"].sum()),
            "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "write": status}
        print(f"{name}: {len(kept)} polygons, {kept['error_count'].sum()} errors / {kept['sample_count'].sum()} "
              f"samples, dropped {len(dropped)} ({status})")
    REPORT.write_text(json.dumps(report, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
