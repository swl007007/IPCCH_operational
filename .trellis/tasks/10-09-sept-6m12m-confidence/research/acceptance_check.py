"""AC1/AC2 checks of the published ``september_manual/scopes/`` (Step 6) -> research/acceptance-check.json.

Plus informational comparisons (never gating): September-origin vs October-origin scores for
the same 6m/12m packages, and 6m/12m country confidence flags vs the accepted h5 flags.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve()
REPO = HERE.parents[4]
CP = REPO / "cloud_pipeline"
SEPT = REPO / "september_manual"
SCOPES = SEPT / "scopes"
OCT = CP / "fallback/october_2026"
ORIGIN = "2026-09"
TARGETS = {6: "2027-03", 12: "2027-09"}
ROSTER = {"fewsnet": (5718, 22), "ipcch": (6227, 53)}
BASIS = {("fewsnet", 6): "h6_validation_error_proxy_stage3_fs2_lag8_2021_2024",
         ("fewsnet", 12): "h12_validation_error_proxy_stage3_fs3_lag12_2021_2024",
         ("ipcch", 6): "training_resubstitution", ("ipcch", 12): "training_resubstitution"}
PERIOD = {"fewsnet": "2021-02..2024-10", "ipcch": "2014-01..2026-04"}


def read(path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def header(path) -> list[str]:
    return pd.read_csv(path, nrows=0).columns.tolist()


def counts(series: pd.Series) -> dict:
    return {str(k): int(v) for k, v in series.value_counts(dropna=False).sort_index().items()}


def nonblank(series: pd.Series) -> int:
    return int(series.ne("").sum())


def main() -> int:
    baseline = json.loads((CP / "bootstrap/baseline.json").read_text())
    package = {(m["system"], m["horizon_months"]): m["package_id"] for m in baseline["models"]}
    inventory = json.loads((SCOPES / "inventory.json").read_text())
    result = {"ac1": {}, "ac2": {}, "informational": {}}
    checks = {}
    inventory_ok = all(
        hashlib.sha256((SCOPES / rel).read_bytes()).hexdigest() == entry["sha256"]
        for rel, entry in inventory["files"].items())
    checks["inventory_hashes_match"] = inventory_ok
    expected_files = {p.relative_to(SCOPES).as_posix() for p in SCOPES.rglob("*") if p.is_file()} - {"inventory.json"}
    checks["inventory_membership_exact"] = expected_files == set(inventory["files"])
    for horizon in TARGETS:
        for system in ("fewsnet", "ipcch"):
            key = f"{system}/{horizon}m"
            ours = SCOPES / f"{horizon}m/{system}"
            octo = OCT / f"scopes/{horizon}m/{system}"
            names = sorted(p.name for p in ours.glob("*.csv"))
            item = {"files": names, "file_set_equals_october": names == sorted(p.name for p in octo.glob("*.csv"))}
            item["headers_equal_october"] = all(header(ours / n) == header(octo / n) for n in names)
            item["headers_equal_h5_root"] = all(header(ours / n) == header(SEPT / system / n) for n in names
                                                if (SEPT / system / n).exists())
            item["h5_root_tables_compared"] = sorted(n for n in names if (SEPT / system / n).exists())
            mapping = read(ours / "polygon_model_mapping.csv")
            predictions = read(ours / "polygon_predictions.csv")
            country = read(ours / "country_predictions.csv")
            confidence = read(ours / "country_confidence.csv")
            polygon_ids = mapping["polygon_id"]
            item["polygon_rows"] = {n: len(read(ours / n)) for n in names if not n.startswith("country")}
            item["country_rows"] = {n: len(read(ours / n)) for n in names if n.startswith("country")}
            item["polygon_unique"] = int(polygon_ids.nunique())
            item["roster_ok"] = (set(item["polygon_rows"].values()) == {ROSTER[system][0]}
                                 and item["polygon_unique"] == ROSTER[system][0]
                                 and set(item["country_rows"].values()) == {ROSTER[system][1]})
            item["mapping_months"] = {c: sorted(mapping[c].unique()) for c in ("feature_month", "target_month",
                                                                                "horizon_months")}
            if system == "fewsnet":
                pred_months = {c: sorted(predictions[c].unique()) for c in ("feature_month", "target_month",
                                                                             "horizon_months")}
                country_months = {c: sorted(country[c].unique()) for c in ("feature_month", "target_month",
                                                                           "horizon_months")}
                ids = sorted(set(predictions["suite_version"] + "/" + f"{horizon}m"))
                item["package_ids"] = ids
                item["package_ok"] = ids == [package[(system, horizon)]]
            else:
                pred_months = {c: sorted(predictions[c].unique()) for c in ("feature_period", "target_period",
                                                                             "scope_months")}
                country_months = {c: sorted(country[c].unique()) for c in ("feature_period", "target_period",
                                                                           "scope_months")}
                ids = sorted(set(predictions["model_package_id"]) | set(mapping["model_package_id"]))
                item["package_ids"] = ids
                item["package_ok"] = all(i == package[(system, horizon)] or i + f"/scope_{horizon}m" ==
                                         package[(system, horizon)] for i in ids)
            item["prediction_months"], item["country_months"] = pred_months, country_months
            wanted = [ORIGIN, TARGETS[horizon], str(horizon)]
            item["months_ok"] = all(list(v.values()) == [[w] for w in wanted]
                                    for v in (item["mapping_months"], pred_months, country_months))
            result["ac1"][key] = item
            # AC2
            diag = {}
            if system == "fewsnet":
                polygon = read(ours / "polygon_confidence.csv")
                diag["polygon_confidence_populated"] = nonblank(polygon["polygon_confidence"])
                diag["historical_sample_count_populated"] = nonblank(polygon["historical_sample_count"])
                diag["blank_polygon_ids"] = sorted(polygon.loc[polygon["polygon_confidence"].eq(""), "polygon_id"])
                diag["evidence_basis"] = counts(polygon["evidence_basis"])
                diag["evidence_period"] = counts(polygon["evidence_period"])
            else:
                polygon = read(ours / "polygon_training_errors.csv")
                diag["training_error_rate_populated"] = nonblank(polygon["training_error_rate"])
                diag["training_sample_count_populated"] = nonblank(polygon["training_sample_count"])
                diag["max_phase_status"] = counts(confidence["country_maximum_phase_uncertainty_status"])
                no_hist = confidence[confidence["country_maximum_phase_uncertainty_status"].eq("no_complete_history")]
                diag["no_complete_history_iso3"] = sorted(no_hist["ISO3"])
                diag["no_complete_history_blank"] = bool(no_hist[[
                    "country_maximum_phase_error_probability_proxy", "country_maximum_phase_error_probability_ci_lower",
                    "country_maximum_phase_error_probability_ci_upper"]].eq("").all().all())
                single = confidence[confidence["country_maximum_phase_uncertainty_status"].eq("single_month")]
                diag["single_month_ci_blank"] = bool(single[["country_maximum_phase_error_probability_ci_lower",
                                                             "country_maximum_phase_error_probability_ci_upper"]]
                                                     .eq("").all().all())
                diag["max_phase_proxy_populated"] = nonblank(confidence["country_maximum_phase_error_probability_proxy"])
                diag["max_phase_method"] = counts(confidence["country_maximum_phase_uncertainty_method"])
                diag["country_overall_phase_populated"] = nonblank(confidence["country_overall_phase"])
            diag["country_error_rate_populated"] = nonblank(confidence["country_error_rate"])
            diag["country_flag_distribution"] = counts(confidence["country_confidence_flag"])
            diag["country_error_basis"] = counts(confidence["country_error_basis"])
            diag["country_error_evidence_period"] = counts(confidence["country_error_evidence_period"])
            diag["country_predictions_flag_equals_confidence"] = bool(
                country.set_index("ISO3")["country_confidence_flag"].sort_index().equals(
                    confidence.set_index("ISO3")["country_confidence_flag"].sort_index()))
            populated_basis = {k for k in diag["country_error_basis"] if k}
            diag["basis_ok"] = populated_basis == {BASIS[(system, horizon)]} and (
                system != "fewsnet" or set(diag["evidence_basis"]) - {""} == {BASIS[(system, horizon)]})
            periods = {k for k in diag["country_error_evidence_period"] if k}
            diag["period_ok"] = periods == {PERIOD[system]} and (
                system != "fewsnet" or set(diag["evidence_period"]) - {""} == {PERIOD[system]})
            result["ac2"][key] = diag
    availability = read(SCOPES / "reports/diagnostic_availability.csv")
    result["ac2"]["availability"] = {
        "horizons": sorted(availability["horizon_months"].unique()),
        "status_reason": {f"{s}/{h}/{st}/{r}": int(n) for (s, h, st, r), n in availability.groupby(
            ["model_system", "horizon_months", "status", "reason"]).size().items()},
        "missing_evidence_rows": int(availability["reason"].eq("missing_evidence").sum())}
    # Informational: vs October-origin scores (same packages; origin 2026-10) and vs h5 flags.
    info = {}
    for horizon in TARGETS:
        for system in ("fewsnet", "ipcch"):
            key, idcol = f"{system}/{horizon}m", ("admin_code" if system == "fewsnet" else "polygon_id")
            ours = pd.read_csv(SCOPES / f"{horizon}m/{system}/polygon_predictions.csv", dtype={idcol: str})
            octo = pd.read_csv(OCT / f"scopes/{horizon}m/{system}/polygon_predictions.csv", dtype={idcol: str})
            merged = ours.merge(octo, on=idcol, suffixes=("_sep", "_oct"))
            scores = ["probability_crisis"] if system == "fewsnet" else [f"phase{k}_worse_score" for k in range(2, 6)]
            entry = {"matched_polygons": len(merged)}
            for score in scores:
                diff = (merged[f"{score}_sep"] - merged[f"{score}_oct"]).abs()
                entry[score] = {"median_abs_diff": float(diff.median()), "max_abs_diff": float(diff.max()),
                                "share_exactly_equal": float((diff == 0).mean())}
            label = "predicted_crisis" if system == "fewsnet" else "overall_phase_pred"
            entry[f"{label}_agreement"] = float((merged[f"{label}_sep"] == merged[f"{label}_oct"]).mean())
            entry["september_class_distribution"] = {str(k): int(v) for k, v in
                                                     ours[label].value_counts().sort_index().items()}
            h5 = read(SEPT / f"{system}/country_confidence.csv")[["ISO3", "country_confidence_flag"]]
            ours_flag = read(SCOPES / f"{horizon}m/{system}/country_confidence.csv")[["ISO3", "country_confidence_flag"]]
            both = h5.merge(ours_flag, on="ISO3", suffixes=("_h5", "_scope"))
            entry["country_flag_vs_h5"] = {
                "h5_distribution": counts(h5["country_confidence_flag"]),
                "agreement": float((both["country_confidence_flag_h5"] == both["country_confidence_flag_scope"]).mean()),
                "transitions": {f"{a}->{b}": int(n) for (a, b), n in both.groupby(
                    ["country_confidence_flag_h5", "country_confidence_flag_scope"]).size().items()}}
            info[key] = entry
    result["informational"] = info
    for key, item in result["ac1"].items():
        for name in ("file_set_equals_october", "headers_equal_october", "headers_equal_h5_root", "roster_ok",
                     "package_ok", "months_ok"):
            checks[f"ac1.{key}.{name}"] = bool(item[name])
    for key, diag in result["ac2"].items():
        if key == "availability":
            continue
        checks[f"ac2.{key}.basis_ok"] = diag["basis_ok"]
        checks[f"ac2.{key}.period_ok"] = diag["period_ok"]
        checks[f"ac2.{key}.country_flag_consistent"] = diag["country_predictions_flag_equals_confidence"]
        if key.startswith("fewsnet"):
            checks[f"ac2.{key}.polygon_confidence_populated_5713"] = diag["polygon_confidence_populated"] == 5713
        else:
            checks[f"ac2.{key}.training_errors_populated"] = diag["training_error_rate_populated"] > 0
            checks[f"ac2.{key}.no_complete_history_blank"] = diag["no_complete_history_blank"]
            checks[f"ac2.{key}.single_month_ci_blank"] = diag["single_month_ci_blank"]
        checks[f"ac2.{key}.country_error_populated"] = diag["country_error_rate_populated"] > 0
    checks["ac2.availability.horizons_6_12_only"] = result["ac2"]["availability"]["horizons"] == ["12", "6"]
    checks["ac2.availability.no_missing_evidence"] = result["ac2"]["availability"]["missing_evidence_rows"] == 0
    result["checks"] = checks
    result["passed"] = all(checks.values())
    (HERE.parent / "acceptance-check.json").write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"passed": result["passed"], "failed": [k for k, v in checks.items() if not v]}, indent=1))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
