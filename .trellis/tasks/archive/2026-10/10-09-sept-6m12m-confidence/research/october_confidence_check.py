"""AC8: compare the confidence rerun (new delivery tree) with the accepted October smoke output (old fallback).

Usage: python october_confidence_check.py --new <downloaded delivery root> [--old <fallback dir>]

* Prediction tables (polygon_predictions, country_predictions, polygon_model_mapping), all systems/horizons:
  equal under the bundle comparator (exact text for IDs/discrete fields, continuous atol 1e-12, rtol 0,
  identical blank masks, identical column order and row order).
* Confidence tables (FEWS polygon/country confidence, IPCCH polygon training errors/country confidence):
  same columns/rows; every column already populated in the old output is equal; columns blank in the old
  output are now populated and their remaining blanks are only structural:
  FEWS no Stage3 history, IPCCH no training rows, max-phase blanks per uncertainty status.
* Cross-checks: FEWS 0m counts = accepted h5 September counts; FEWS/IPCCH 6m/12m evidence columns = the
  September-origin scopes (same evidence); diagnostic availability has no ``missing_evidence``.
Writes ``research/october_confidence_check.json``; exit 0 only if every gate passes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve()
REPO = HERE.parents[4]
CP = REPO / "cloud_pipeline"
sys.path.insert(0, str(CP))
from cloud.orchestrator.delivery_bundle import _compare_frames  # noqa: E402

HORIZONS = (0, 6, 12)
PREDICTION = ("polygon_predictions", "country_predictions", "polygon_model_mapping")
CONFIDENCE = {"fewsnet": ("polygon_confidence", "country_confidence"),
              "ipcch": ("polygon_training_errors", "country_confidence")}
FEWS_NO_HISTORY = {"216", "2786", "4375", "4511", "5500"}
MAX_FIELDS = ("country_maximum_phase_error_probability_proxy", "country_maximum_phase_error_probability_ci_lower",
              "country_maximum_phase_error_probability_ci_upper", "country_maximum_phase_history_month_count",
              "country_maximum_phase_uncertainty_status", "country_maximum_phase_uncertainty_method")


def read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def blanks(frame: pd.DataFrame) -> dict:
    return {c: int(frame[c].eq("").sum()) for c in frame.columns if frame[c].eq("").any()}


def confidence_check(system: str, name: str, old: pd.DataFrame, new: pd.DataFrame, horizon: int) -> dict:
    result = {"rows": len(new), "same_shape": list(old.columns) == list(new.columns) and len(old) == len(new)}
    if not result["same_shape"]:
        return {**result, "passed": False}
    populated_before = [c for c in old.columns if old[c].ne("").any()]
    equal, diff, bad = _compare_frames(old[populated_before], new[populated_before])
    result.update({"previously_populated_columns_equal": equal, "previously_populated_max_abs_diff": diff,
                   "previously_populated_mismatch": bad,
                   "newly_populated_columns": [c for c in old.columns if old[c].eq("").all() and new[c].ne("").any()],
                   "still_entirely_blank_columns": [c for c in new.columns if new[c].eq("").all()],
                   "blank_counts": blanks(new)})
    ok = equal
    if name == "polygon_confidence":
        missing = set(new.loc[new["historical_sample_count"].eq(""), "polygon_id"])
        result["no_history_polygons"] = sorted(missing, key=int)
        result["populated_polygons"] = int(new["historical_sample_count"].ne("").sum())
        result["country_error_eligible"] = new["country_error_eligible"].value_counts().to_dict()
        result["basis"] = sorted(new.loc[new["evidence_basis"].ne(""), "evidence_basis"].unique())
        result["period"] = sorted(new.loc[new["evidence_period"].ne(""), "evidence_period"].unique())
        ok &= missing == FEWS_NO_HISTORY and result["populated_polygons"] == len(new) - 5
        for column in ("historical_error_count", "polygon_error_rate", "polygon_confidence"):
            ok &= set(new.loc[new[column].eq(""), "polygon_id"]) == FEWS_NO_HISTORY
        # basis/period label every row (incl. no-history polygons) with the declared evidence identity
        ok &= len(result["basis"]) == 1 and len(result["period"]) == 1 and new["evidence_basis"].ne("").all()
    elif name == "polygon_training_errors":
        missing = new["training_sample_count"].eq("")
        result["populated_polygons"] = int((~missing).sum())
        result["no_training_rows_polygons"] = int(missing.sum())
        ok &= all(new.loc[missing, c].eq("").all() and new.loc[~missing, c].ne("").all()
                  for c in ("training_sample_count", "training_error_count", "training_error_rate"))
    else:
        result["countries"] = len(new)
        result["country_error_rate_populated"] = int(new["country_error_rate"].ne("").sum())
        result["flags"] = new["country_confidence_flag"].replace("", "<blank>").value_counts().to_dict()
        result["basis"] = sorted(new.loc[new["country_error_basis"].ne(""), "country_error_basis"].unique())
        no_eligible = new["country_error_eligible_area_count"].isin(["", "0"])
        result["no_eligible_area_countries"] = new.loc[no_eligible, "ISO3"].tolist()
        ok &= (new["country_error_rate"].eq("") == no_eligible).all()
        ok &= (new["country_confidence_flag"].eq("") == no_eligible).all()
        if system == "ipcch":
            status = new["country_maximum_phase_uncertainty_status"]
            result["maximum_phase_status"] = status.value_counts().to_dict()
            proxy, low, high = (new[c].eq("") for c in MAX_FIELDS[:3])
            ok &= status.ne("").all()
            ok &= (proxy == status.eq("no_complete_history")).all()
            ok &= ((low & high) == status.isin(["no_complete_history", "single_month"])).all()
    result["passed"] = bool(ok)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--new", required=True)
    parser.add_argument("--old", default=str(CP / "fallback/october_2026"))
    parser.add_argument("--report", default=str(HERE.with_suffix(".json")))
    args = parser.parse_args()
    old_root, new_root = Path(args.old), Path(args.new)
    report = {"old": str(old_root), "new": str(new_root), "predictions": {}, "confidence": {}, "cross_checks": {}}
    gates = []
    for h in HORIZONS:
        for system in ("fewsnet", "ipcch"):
            for name in PREDICTION:
                rel = f"scopes/{h}m/{system}/{name}.csv"
                old, new = read(old_root / rel), read(new_root / rel)
                if name != "country_predictions":
                    equal, diff, bad = _compare_frames(old, new)
                    report["predictions"][rel] = {"equal": equal, "max_abs_diff": diff, "mismatch_columns": bad}
                    gates.append(equal)
                    continue
                # country_predictions also carries the country confidence columns (September layout): every
                # column populated before must be equal; the previously blank confidence columns must equal
                # this scope's country_confidence.csv.
                before = [c for c in old.columns if old[c].ne("").any()]
                filled = [c for c in old.columns if c not in before]
                equal, diff, bad = _compare_frames(old[before], new[before])
                confidence = read(new_root / f"scopes/{h}m/{system}/country_confidence.csv")
                consistent = (list(old.columns) == list(new.columns) and set(filled) <= set(confidence.columns)
                              and new[["ISO3", *filled]].equals(confidence[["ISO3", *filled]]))
                report["predictions"][rel] = {"equal": bool(equal and consistent), "max_abs_diff": diff,
                                              "mismatch_columns": bad, "compared_columns": len(before),
                                              "confidence_columns_now_filled": filled,
                                              "confidence_columns_equal_country_confidence": bool(consistent)}
                gates.append(equal and consistent)
            for name in CONFIDENCE[system]:
                rel = f"scopes/{h}m/{system}/{name}.csv"
                item = confidence_check(system, name, read(old_root / rel), read(new_root / rel), h)
                report["confidence"][rel] = item
                gates.append(item["passed"])

    availability = read(new_root / "reports/diagnostic_availability.csv")
    old_availability = read(old_root / "reports/diagnostic_availability.csv")
    counts = availability.groupby(["model_system", "horizon_months", "diagnostic_family", "status", "reason"]).size()
    report["availability"] = {
        "rows": len(availability), "old_rows": len(old_availability),
        "same_entities": sorted(map(tuple, availability[["model_system", "horizon_months", "level", "entity_id",
                                                         "diagnostic_family"]].values.tolist()))
        == sorted(map(tuple, old_availability[["model_system", "horizon_months", "level", "entity_id",
                                               "diagnostic_family"]].values.tolist())),
        "missing_evidence_rows": int(availability["reason"].eq("missing_evidence").sum()),
        "status_reason_counts": {"/".join(map(str, k)): int(v) for k, v in counts.items()}}
    gates += [report["availability"]["same_entities"], report["availability"]["missing_evidence_rows"] == 0]

    # FEWS 0m = accepted h5 September evidence counts
    h5 = pd.read_csv(REPO / "september_manual/fewsnet/polygon_confidence.csv", dtype=str, keep_default_na=False)
    new0 = read(new_root / "scopes/0m/fewsnet/polygon_confidence.csv")
    cols = ["polygon_id", "historical_sample_count", "historical_error_count", "polygon_error_rate"]
    merged = h5[cols].merge(new0[cols], on="polygon_id", suffixes=("_h5", "_new"))
    same = all(merged[f"{c}_h5"].equals(merged[f"{c}_new"]) for c in cols[1:3]) and len(merged) == len(h5) == len(new0)
    rate_diff = (pd.to_numeric(merged["polygon_error_rate_h5"], errors="coerce")
                 - pd.to_numeric(merged["polygon_error_rate_new"], errors="coerce")).abs().max()
    report["cross_checks"]["fewsnet_0m_counts_equal_h5"] = {"equal": bool(same), "rows": len(merged),
                                                            "max_abs_rate_diff": float(rate_diff)}
    gates.append(same)
    # 6m/12m evidence columns = September-origin scopes (same evidence, same roster)
    for h in (6, 12):
        for system, name, columns in (("fewsnet", "polygon_confidence",
                                       ["polygon_id", "historical_sample_count", "historical_error_count",
                                        "evidence_basis", "evidence_period"]),
                                      ("ipcch", "polygon_training_errors",
                                       ["polygon_id", "training_sample_count", "training_error_count"])):
            rel = f"scopes/{h}m/{system}/{name}.csv"
            sept = REPO / "september_manual" / rel
            equal = read(sept)[columns].equals(read(new_root / rel)[columns])
            report["cross_checks"][f"{rel}_evidence_equal_september_scopes"] = bool(equal)
            gates.append(equal)
    report["check_revisions"] = [
        "2026-10-09 after first run on oct-confidence-20261009a: country_predictions carries the country confidence "
        "columns by design, so it is compared on previously populated columns plus consistency with "
        "country_confidence.csv; FEWS evidence_basis/period label every row and left the no-history blank rule."]
    report["passed"] = bool(all(gates))
    Path(args.report).write_text(json.dumps(report, indent=1, default=str) + "\n")
    print(json.dumps({"passed": report["passed"],
                      "predictions_equal": sum(v["equal"] for v in report["predictions"].values()),
                      "confidence_passed": sum(v["passed"] for v in report["confidence"].values()),
                      "missing_evidence_rows": report["availability"]["missing_evidence_rows"],
                      "cross_checks": report["cross_checks"]}, indent=1))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
