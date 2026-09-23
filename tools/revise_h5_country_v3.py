"""Country confidence v3: population-weighted area errors, fixed-cutoff flags,
country outcome/phase and IPCCH maximum-phase residual-transfer uncertainty."""
from __future__ import annotations

import argparse
import gc
import json
import platform
import shutil
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.refresh_h5_inputs import sha256, source_iso3, write_json
from tools.run_h5_model_delivery import read_csv, save_csv, TARGETS

POLICY = "reports/country_confidence_v3_policy.json"
PARENT_V2 = "reports/parent_v2"
STAGE3 = Path("/mnt/c/users/swl00/ifpri dropbox/weilun shi/google fund/analysis/2.source_code/step5_geo_rf_trial/"
              "food_crisis_cluster/paper_reproducibility_package/stage3_results/georf_fs1")
HIGH, MEDIUM = Fraction(1, 10), Fraction(1, 5)
PHASE_THRESHOLD, CRISIS_THRESHOLD = 0.2, 0.5
SEED, REPLICATES, PERCENTILES = 20260923, 10000, (2.5, 97.5)
BASIS = {"fewsnet": "h5_validation_error_proxy_stage3_2021_2024", "ipcch": "training_resubstitution"}
WEIGHTING = "population_weighted_mean_of_area_error_rates"
V2_COUNTRY_COLUMNS = ["country_training_error_rate", "country_training_area_count", "country_training_sample_count",
    "country_training_error_count", "country_confidence_method", "country_confidence_rank",
    "country_confidence_flag", "country_error_tied_at_boundary"]
V2_ARTIFACTS = ["fewsnet/country_training_confidence.csv", "ipcch/country_training_confidence.csv",
    "fewsnet/polygon_training_errors.csv", "reports/fewsnet_training_predictions.csv",
    "reports/fewsnet_confidence_summary.json", "reports/ipcch_confidence_summary.json",
    "reports/training_confidence_policy.json", "reports/training_confidence_summary.json",
    "reports/training_confidence_verification.json", "reports/training_confidence_spec.md",
    "reports/prior_boundary_flag_training_confidence_summary.json",
    "reports/prior_boundary_flag_training_confidence_verification.json",
    "reports/confidence_focused_checks.json", "reports/confidence_independent_review.json"]


def confidence_flag(rate):
    """Unrounded exact comparison: high <=10%, medium <=20%, low >20%; None when unavailable."""
    if rate is None:
        return None
    rate = Fraction(rate)
    return "high" if rate <= HIGH else "medium" if rate <= MEDIUM else "low"


def decode_cumulative_phase(scores, threshold=PHASE_THRESHOLD):
    """Raw cumulative Phase2+..Phase5+ scores (last axis) -> Phase1..5, same >=0.2 cascade as runtime."""
    active = np.asarray(scores, dtype=float) >= threshold
    cascaded = np.maximum.accumulate(active[..., ::-1], axis=-1)[..., ::-1]
    return np.where(cascaded.any(axis=-1), (cascaded * np.arange(2, 6)).max(axis=-1), 1)


def weighted_country_errors(areas, system, evidence_period, population_field):
    """areas: polygon_id, ISO3, sample_count, error_count, population, population_reference_period, population_source."""
    records = []
    for iso, group in areas.groupby("ISO3", sort=True):
        pop = group.population.to_numpy(dtype=float)
        known = np.isfinite(pop) & (pop > 0)
        evidence = group.sample_count.fillna(0).to_numpy() > 0
        eligible = known & evidence
        e = group.loc[eligible]
        if len(e):
            # Exact rational arithmetic: float weights and integer counts, classified before rounding.
            num = sum((Fraction(float(p)) * Fraction(int(k), int(n))
                       for p, k, n in zip(e.population, e.error_count, e.sample_count)), Fraction())
            exact = num / sum((Fraction(float(p)) for p in e.population), Fraction())
            rate = float(exact)
        else:
            exact = rate = None
        vintages = sorted(set(e.population_reference_period.dropna().astype(str)))
        records.append({"ISO3": iso, "country_error_rate": rate, "country_confidence_flag": confidence_flag(exact),
            "country_error_basis": BASIS[system], "country_error_weighting": WEIGHTING,
            "country_error_evidence_period": evidence_period,
            "country_confidence_thresholds": "high<=0.10; 0.10<medium<=0.20; low>0.20 (unrounded)",
            "country_error_eligible_area_count": int(eligible.sum()),
            "country_error_excluded_area_count": int(len(group) - eligible.sum()),
            "country_error_missing_evidence_area_count": int((~evidence).sum()),
            "country_error_missing_population_area_count": int((~np.isfinite(pop)).sum()),
            "country_error_nonpositive_population_area_count": int((np.isfinite(pop) & (pop <= 0)).sum()),
            "country_error_sample_count": int(e.sample_count.sum()),
            "country_error_mistake_count": int(e.error_count.sum()),
            "country_error_eligible_population_sum": float(e.population.sum()),
            "country_error_known_population_sum": float(pop[known].sum()),
            "country_error_known_population_coverage": float(e.population.sum() / pop[known].sum()) if known.any() else None,
            "country_error_population_field": population_field,
            "country_error_population_vintage": f"{vintages[0]}..{vintages[-1]}" if vintages else None,
            "country_error_population_source": ";".join(sorted(set(e.population_source.dropna().astype(str)))) or None})
    return pd.DataFrame(records)


def maximum_phase_uncertainty(mismatch_by_country, rng):
    """mismatch_by_country: ordered {ISO3: 0/1 array in chronological month order}. RNG consumed in ISO3 order."""
    records = []
    for iso in sorted(mismatch_by_country):
        x = np.asarray(mismatch_by_country[iso], dtype=float)
        m = len(x)
        point = float(x.mean()) if m else None
        lower = upper = None
        if m == 0:
            status = "no_complete_history"
        elif m == 1:
            status = "single_month"
        else:
            means = x[rng.integers(0, m, size=(REPLICATES, m))].mean(axis=1)
            lower, upper = (float(v) for v in np.percentile(means, PERCENTILES, method="linear"))
            status = "degenerate_empirical" if np.unique(x).size == 1 else "supported"
        records.append({"ISO3": iso, "country_maximum_phase_error_probability_proxy": point,
            "country_maximum_phase_error_probability_ci_lower": lower,
            "country_maximum_phase_error_probability_ci_upper": upper,
            "country_maximum_phase_history_month_count": m,
            "country_maximum_phase_uncertainty_status": status})
    return pd.DataFrame(records)


def append_country_v3(country, confidence):
    """Drop v2 quota diagnostics, apply v2 dispersion naming, append v3 diagnostics (used by export too)."""
    if country.ISO3.duplicated().any() or confidence.ISO3.duplicated().any() or set(country.ISO3) != set(confidence.ISO3):
        raise ValueError("Country confidence must cover the exact unique country universe")
    renames = {c: c.replace("_aggregation_uncertainty", "_area_dispersion")
               for c in country if c.endswith("_aggregation_uncertainty")}
    renames["aggregation_uncertainty_method"] = "area_dispersion_method"
    country = country.rename(columns=renames).drop(columns=[c for c in V2_COUNTRY_COLUMNS if c in country])
    added = [c for c in confidence if c != "ISO3"]
    return country.drop(columns=[c for c in added if c in country]).merge(
        confidence, on="ISO3", how="left", validate="one_to_one", sort=False)


def forecast_country_fields(system, country, predictions=None):
    """Country outcomes derived from the current forecast (not from frozen historical evidence)."""
    country = country.set_index("ISO3")
    if system == "fewsnet":
        return pd.DataFrame({"country_outcome_crisis": [pd.NA if pd.isna(v) else int(v >= CRISIS_THRESHOLD)
                                                        for v in country.probability_crisis]}, index=country.index).astype("Int64")
    scores = country[[f"{t}_score" for t in TARGETS]].to_numpy(dtype=float)
    finite = np.isfinite(scores).all(axis=1)
    overall = pd.array([int(v) if ok else pd.NA for v, ok in zip(decode_cumulative_phase(np.nan_to_num(scores)), finite)], dtype="Int64")
    out = pd.DataFrame({"country_overall_phase": overall}, index=country.index)
    if predictions is not None:
        out["country_maximum_phase"] = predictions.groupby("ISO3").overall_phase_pred.max().reindex(country.index).astype("Int64")
    return out


def check_forecast_fields(system, country, predictions=None):
    expected = forecast_country_fields(system, country, predictions)
    actual = country.set_index("ISO3")[expected.columns].astype("Int64")
    if not actual.equals(expected):
        raise ValueError(f"{system}: frozen country outcome/phase fields disagree with the current forecast; rerun revise_h5_country_v3")


def versions():
    import sklearn, xgboost
    return {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
            "xgboost": xgboost.__version__, "scikit-learn": sklearn.__version__}


def prepare(parent, root):
    parent, root = parent.resolve(), root.resolve()
    if root.exists() or parent == root or parent in root.parents:
        raise ValueError("Use a fresh sibling delivery directory")
    manifest = json.loads((parent / "manifest.json").read_text())
    assert manifest["status"] == "passed"
    for item in manifest["files"]:
        assert sha256(parent / item["path"]) == item["sha256"], item["path"]
    exclude = shutil.ignore_patterns("manifest.json", "bundle_manifest.json", "webapp_model_bundle.tar.gz",
        "final_verification.json", "final_integrity.json", "__pycache__", "*.pyc")
    print("Copying parent delivery", flush=True)
    shutil.copytree(parent, root, ignore=exclude)
    # Keep v1 parent provenance (parent_delivery_manifest/parent_final_verification) and add the v2 parent's own.
    (root / PARENT_V2).mkdir()
    shutil.copy2(parent / "manifest.json", root / PARENT_V2 / "manifest.json")
    shutil.copy2(parent / "reports/final_verification.json", root / PARENT_V2 / "final_verification.json")
    for relative in V2_ARTIFACTS:
        target = root / PARENT_V2 / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(root / relative, target)
    for system in ["fewsnet", "ipcch"]:
        path = root / f"{system}/country_predictions.csv"
        read_csv(path).drop(columns=V2_COUNTRY_COLUMNS).to_csv(path, index=False)
    source = STAGE3 / "predictions_monthly.csv"
    (root / "reports/fewsnet_stage3_source").mkdir()
    for name in ["predictions_monthly.csv", "run_manifest.json"]:
        shutil.copy2(STAGE3 / name, root / "reports/fewsnet_stage3_source" / name)
    for name in ["model_pipeline", "fewsnet_partitioned_rf_pipeline"]:
        shutil.copytree(ROOT / name, root / "runtime" / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for path in (ROOT / "tools").glob("*h5*.py"):
        shutil.copy2(path, root / "runtime/tools" / path.name)
    task = ROOT / ".trellis/tasks/09-23-country-uncertainty-phase-revision"
    shutil.copy2(task / "design.md", root / "reports/country_confidence_v3_spec.md")
    shutil.copy2(task / "implement.md", root / "reports/country_confidence_v3_execution_plan.md")
    write_json(root / POLICY, {"method": "country_confidence_v3", "parent_directory": str(parent),
        "parent_manifest_sha256": sha256(parent / "manifest.json"),
        "moved_parent_v2_artifacts": {r: f"{PARENT_V2}/{r}" for r in V2_ARTIFACTS},
        "country_error": {"formula": "sum(P_a * e_a) / sum(P_a) over areas with evidence and finite positive population",
            "area_error": "error_count / sample_count per polygon", "weighting": WEIGHTING,
            "population": {"fewsnet": "inputs/fewsnet_identity_population.csv population (delivered snapshot)",
                           "ipcch": "polygon_predictions population_estimate (delivered snapshot)"},
            "missing_support": "retain polygon, exclude from weighting, no zero fill, no downgrade; no eligible areas -> null rate and flag",
            "basis": BASIS},
        "confidence_flag": {"high": "rate <= 0.10", "medium": "0.10 < rate <= 0.20", "low": "rate > 0.20",
            "comparison": "exact rational, unrounded", "quota": None},
        "fewsnet": {"historical_source": str(source), "historical_source_sha256": sha256(source),
            "run_manifest_sha256": sha256(STAGE3 / "run_manifest.json"),
            "prediction_columns": "y_true vs y_pred_partitioned (saved .predict() decisions, not re-thresholded)",
            "label": "h5 validation-error proxy per meeting agreement; source is fs1 / 4-month-lag rolling Stage3, not an exact-horizon validation run",
            "polygon_confidence": "1 - polygon_error_rate",
            "country_outcome_crisis": "int(population-weighted probability_crisis >= 0.5); null if missing"},
        "ipcch": {"country_error_evidence": "saved area Phase3+ training-resubstitution errors (ipcch/polygon_training_errors.csv)",
            "country_overall_phase": "population-weighted cumulative scores, >=0.2 cascade decode, no clipping or normalization",
            "country_maximum_phase": "max(polygon overall_phase_pred) over full delivered roster",
            "maximum_phase_uncertainty": {"estimand": "training-residual-based maximum-phase error-probability proxy, not a calibrated probability",
                "residual": "actual cumulative share - replayed predicted score, all four targets, saved models, no fitting",
                "scenario": "September raw scores + one complete country/month residual field; decode; compare max with forecast max",
                "complete_month": "target month covering every polygon of the country's delivered roster",
                "bootstrap": {"unit": "complete historical month, equal weight, whole residual field", "replicates": REPLICATES,
                    "generator": f"numpy.random.Generator(PCG64({SEED}))", "seed": SEED,
                    "order": "countries ISO3 ascending; months chronological; one generator consumed sequentially for countries with >=2 months",
                    "interval": "percentile 2.5/97.5, numpy method=linear", "population_weighting": False},
                "status_priority": ["no_complete_history", "single_month", "degenerate_empirical", "supported"]}},
        "library_versions": versions(), "models_retrained": False, "forecasts_changed": False})
    print(f"Prepared {root}", flush=True)


def evaluate_fewsnet(root):
    hist = pd.read_csv(root / "reports/fewsnet_stage3_source/predictions_monthly.csv", dtype={"FEWSNET_admin_code": "string"})
    assert not hist.duplicated(["FEWSNET_admin_code", "month_start"]).any()
    assert hist.y_true.isin([0, 1]).all() and hist.y_pred_partitioned.isin([0, 1]).all()
    identity = read_csv(root / "inputs/fewsnet_identity_population.csv").rename(columns={"admin_code": "polygon_id"})
    assert not identity.polygon_id.duplicated().any()
    rows = hist.rename(columns={"FEWSNET_admin_code": "polygon_id"})
    rows["target_month"] = pd.to_datetime(rows.month_start).dt.to_period("M").astype(str)
    assert set(rows.polygon_id) <= set(identity.polygon_id), "historical polygon outside delivered roster"
    rows = rows.merge(identity[["polygon_id", "ISO3"]], on="polygon_id", how="left", validate="many_to_one")
    rows["error"] = rows.y_pred_partitioned.ne(rows.y_true).astype(int)
    rows["evidence_basis"] = BASIS["fewsnet"]
    rows = rows[["polygon_id", "ISO3", "target_month", "partition_id", "y_true", "y_prob_partitioned",
                 "y_pred_partitioned", "error", "evidence_basis"]].sort_values(["target_month", "polygon_id"], kind="stable")
    period = f"{rows.target_month.min()}..{rows.target_month.max()}"
    counts = rows.groupby("polygon_id").agg(sample_count=("error", "size"), error_count=("error", "sum")).reset_index()
    areas = identity[["polygon_id", "ISO3", "population", "population_reference_period", "population_source"]].merge(
        counts, on="polygon_id", how="left", validate="one_to_one")
    countries = weighted_country_errors(areas, "fewsnet", period, "population")
    polygons = areas.rename(columns={"sample_count": "historical_sample_count", "error_count": "historical_error_count"})
    polygons["polygon_error_rate"] = polygons.historical_error_count / polygons.historical_sample_count
    polygons["polygon_confidence"] = 1 - polygons.polygon_error_rate
    pop = polygons.population
    polygons["country_error_eligible"] = polygons.polygon_error_rate.notna() & pop.notna() & (pop > 0)
    polygons["evidence_basis"], polygons["evidence_period"] = BASIS["fewsnet"], period
    for c in ["historical_sample_count", "historical_error_count"]:
        polygons[c] = polygons[c].astype("Int64")
    country = read_csv(root / "fewsnet/country_predictions.csv")
    crisis = country.set_index("ISO3").probability_crisis
    outcome = pd.Series(pd.array([pd.NA if pd.isna(v) else int(v >= CRISIS_THRESHOLD) for v in crisis], dtype="Int64"), index=crisis.index)
    countries["country_outcome_crisis"] = countries.ISO3.map(outcome).astype("Int64")
    countries["country_outcome_crisis_threshold"] = CRISIS_THRESHOLD
    save_csv(rows, root / "reports/fewsnet_stage3_historical_errors.csv")
    save_csv(polygons, root / "fewsnet/polygon_confidence.csv")
    save_csv(countries, root / "fewsnet/country_confidence.csv")
    append_country_v3(country, countries).to_csv(root / "fewsnet/country_predictions.csv", index=False)
    summary = {"historical_rows": len(rows), "historical_polygons": int(counts.polygon_id.nunique()), "delivered_polygons": len(areas),
        "polygons_without_history": sorted(set(areas.polygon_id) - set(counts.polygon_id), key=int),
        "eligible_polygons": int(polygons.country_error_eligible.sum()), "evidence_period": period,
        "exact_half_probability_rows": int((rows.y_prob_partitioned == .5).sum()),
        "flags": {str(k): int(v) for k, v in countries.country_confidence_flag.value_counts(dropna=False).items()},
        "low_countries": countries.loc[countries.country_confidence_flag.eq("low"), "ISO3"].tolist(),
        "country_outcome_crisis": {str(k): int(v) for k, v in countries.country_outcome_crisis.value_counts(dropna=False).items()}}
    write_json(root / "reports/fewsnet_country_confidence_v3_summary.json", summary)
    print(json.dumps(summary), flush=True)


def replay_ipcch(root):
    """Four saved regressors on exact training rows (no fitting) with share-decoded actual phase."""
    from model_pipeline.ipcch_launch_runtime.model_package import load_scope_package
    from model_pipeline.ipcch_launch_runtime.feature_contract import apply_feature_contract
    keys = read_csv(root / "reports/ipcch_training_keys.csv")
    loaded = load_scope_package(root / "ipcch/model_package", 5)
    assert sha256(root / "inputs/ipcch_panel.csv") == loaded["metadata"]["source_panel_sha256"]
    columns = loaded["feature_columns"]
    shares = [f"phase{i}_percent" for i in range(1, 6)]
    feature_keys = pd.MultiIndex.from_frame(keys[["area_id", "feature_period"]])
    target_keys = pd.MultiIndex.from_frame(keys[["area_id", "target_period"]])
    features, labels = [], []
    for chunk in pd.read_csv(root / "inputs/ipcch_panel.csv", usecols=["admin_code", "year", "month", *columns, *shares],
                             dtype={"admin_code": "string"}, float_precision="round_trip", chunksize=50000):
        chunk = chunk.copy()
        chunk["area_id"] = chunk.admin_code.str.strip()
        chunk["period"] = pd.to_datetime(dict(year=chunk.year, month=chunk.month, day=1)).dt.to_period("M").astype(str)
        index = pd.MultiIndex.from_frame(chunk[["area_id", "period"]])
        features.append(chunk.loc[index.isin(feature_keys), ["area_id", "period", *columns]])
        labels.append(chunk.loc[index.isin(target_keys), ["area_id", "period", *shares]])
    f = pd.concat(features).rename(columns={"period": "feature_period"})
    y = pd.concat(labels).rename(columns={"period": "target_period"})
    del features, labels; gc.collect()
    train = keys.merge(f, on=["area_id", "feature_period"], validate="one_to_one", how="left", indicator=True)
    assert train._merge.eq("both").all(); train = train.drop(columns="_merge")
    train = train.merge(y, on=["area_id", "target_period"], validate="one_to_one", how="left", indicator=True)
    assert train._merge.eq("both").all()
    train[columns + shares] = train[columns + shares].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    matrix, _ = apply_feature_contract(train, loaded["contract"], columns, package_root=loaded["scope_dir"], metadata=loaded["metadata"])
    rows = keys.rename(columns={"area_id": "polygon_id", "feature_period": "feature_month", "target_period": "target_month"}).copy()
    for i, target in zip(range(2, 6), TARGETS):
        rows[f"{target}_actual"] = train[[f"phase{j}_percent" for j in range(i, 6)]].sum(axis=1, min_count=6 - i).to_numpy()
        # float32 model output held exactly as float64 so exported residuals round-trip through CSV.
        rows[f"{target}_predicted"] = loaded["models"][target].predict(matrix).astype(np.float64)
        rows[f"{target}_residual"] = rows[f"{target}_actual"] - rows[f"{target}_predicted"]
    assert np.isfinite(rows.filter(regex="_(actual|predicted)$").to_numpy()).all()
    rows["actual_overall_phase"] = decode_cumulative_phase(rows[[f"{t}_actual" for t in TARGETS]].to_numpy())
    rows["predicted_overall_phase"] = decode_cumulative_phase(rows[[f"{t}_predicted" for t in TARGETS]].to_numpy())
    share_values = train[shares].to_numpy(dtype=float)
    anomalies = {"rows": len(rows), "total_five_shares_gt_1.000001": int((np.nansum(share_values, axis=1) > 1.000001).sum()),
        "any_cumulative_target_gt_1.000001": int((rows[[f"{t}_actual" for t in TARGETS]] > 1.000001).any(axis=1).sum()),
        "any_individual_share_gt_1": int((share_values > 1).any(axis=1).sum()),
        "any_negative_share": int((share_values < 0).any(axis=1).sum()),
        "predicted_scores_outside_unit_interval": int(((rows.filter(like="_predicted") < 0) | (rows.filter(like="_predicted") > 1)).any(axis=1).sum()),
        "actual_phase_counts": {int(k): int(v) for k, v in rows.actual_overall_phase.value_counts().sort_index().items()},
        "predicted_phase_counts": {int(k): int(v) for k, v in rows.predicted_overall_phase.value_counts().sort_index().items()}}
    return rows, anomalies


def evaluate_ipcch(root):
    predictions = read_csv(root / "ipcch/polygon_predictions.csv")
    april = read_csv(root / "inputs/ipcch_april_panel.csv")
    reference = read_csv(root / "ipcch/country_population_reference.csv")
    lookup = april[["area_id", "country"]].merge(reference[["country", "ISO3"]], on="country", validate="many_to_one")
    iso = predictions[["polygon_id"]].merge(lookup.rename(columns={"area_id": "polygon_id"}), on="polygon_id", validate="one_to_one")
    april["ISO3_source"] = source_iso3(april)
    assert iso.merge(april[["area_id", "ISO3_source"]].rename(columns={"area_id": "polygon_id"}), on="polygon_id").pipe(
        lambda d: d.ISO3.eq(d.ISO3_source).all()), "country-name ISO3 and source ISO3 disagree"
    predictions = predictions.merge(iso[["polygon_id", "ISO3"]], on="polygon_id", validate="one_to_one")
    assert predictions.overall_phase_pred.isin(range(1, 6)).all() and not predictions.polygon_id.duplicated().any()
    np.testing.assert_array_equal(decode_cumulative_phase(predictions[[f"{t}_score" for t in TARGETS]].to_numpy()),
                                  predictions.overall_phase_pred.to_numpy())
    # Phase3+ population-weighted country error from the saved area training errors.
    saved = read_csv(root / "ipcch/polygon_training_errors.csv")
    keys = read_csv(root / "reports/ipcch_training_keys.csv")
    period = f"{keys.target_period.min()}..{keys.target_period.max()}"
    areas = predictions[["polygon_id", "ISO3", "population_estimate", "population_reference_period", "population_imputation_method"]].rename(
        columns={"population_estimate": "population", "population_imputation_method": "population_source"}).merge(
        saved.rename(columns={"ISO3": "ISO3_saved", "training_sample_count": "sample_count", "training_error_count": "error_count"}),
        on="polygon_id", how="left", validate="one_to_one")
    assert areas.ISO3_saved.eq(areas.ISO3).all()
    countries = weighted_country_errors(areas, "ipcch", period, "population_estimate")
    country = read_csv(root / "ipcch/country_predictions.csv")
    scores = country.set_index("ISO3")[[f"{t}_score" for t in TARGETS]]
    finite = np.isfinite(scores.to_numpy()).all(axis=1)
    overall = pd.Series(np.where(finite, decode_cumulative_phase(scores.to_numpy()), 0), index=scores.index)
    countries["country_overall_phase"] = countries.ISO3.map(overall.where(finite)).astype("Int64")
    countries["country_overall_phase_availability"] = countries.ISO3.map(pd.Series(np.where(finite, "available", "nonfinite_country_score"), index=scores.index))
    countries["country_overall_phase_method"] = "population-weighted raw cumulative scores; >=0.2 cascade; highest active boundary"
    forecast_max = predictions.groupby("ISO3").overall_phase_pred.max()
    countries["country_maximum_phase"] = countries.ISO3.map(forecast_max).astype("Int64")
    # Residual-transfer maximum-phase scenarios.
    print("ipcch: replaying four saved targets on exact training rows", flush=True)
    replay, anomalies = replay_ipcch(root)
    v2 = read_csv(root / "reports/ipcch_training_predictions.csv")
    check = replay[["polygon_id", "feature_month", "target_month", "phase3_worse_predicted", "phase3_worse_actual"]].merge(
        v2, on=["polygon_id", "feature_month", "target_month"], validate="one_to_one")
    assert len(check) == len(replay) == len(v2)
    # v2 exported the same float32 predictions at float32 text precision.
    np.testing.assert_array_equal(check.phase3_worse_predicted.astype(np.float32), check.predicted_score.astype(np.float32))
    np.testing.assert_allclose(check.phase3_worse_actual, check.actual_value, rtol=0, atol=1e-12)
    replay = replay.merge(predictions[["polygon_id", "ISO3"]], on="polygon_id", validate="many_to_one")
    roster = predictions.groupby("ISO3").polygon_id.apply(lambda s: sorted(s))
    coverage = replay.groupby(["ISO3", "target_month"]).polygon_id.nunique().rename("observed_polygon_count").reset_index()
    coverage["roster_polygon_count"] = coverage.ISO3.map(roster.map(len))
    coverage["complete"] = coverage.observed_polygon_count.eq(coverage.roster_polygon_count)
    residual_cols = [f"{t}_residual" for t in TARGETS]
    sept = predictions.set_index("polygon_id")[[f"{t}_score" for t in TARGETS]]
    scenarios, mismatch = [], {}
    for code in sorted(roster.index):
        ids = roster[code]
        months = sorted(coverage.loc[coverage.ISO3.eq(code) & coverage.complete, "target_month"])
        base = sept.loc[ids].to_numpy(dtype=float)
        values = []
        for month in months:
            r = replay.loc[replay.ISO3.eq(code) & replay.target_month.eq(month)].set_index("polygon_id").loc[ids, residual_cols].to_numpy()
            simulated = decode_cumulative_phase(base + r)
            values.append(int(simulated.max() != forecast_max[code]))
            scenarios.append({"ISO3": code, "target_month": month, "polygon_count": len(ids),
                "forecast_maximum_phase": int(forecast_max[code]), "simulated_maximum_phase": int(simulated.max()),
                "simulated_polygons_at_maximum": int((simulated == simulated.max()).sum()), "maximum_phase_mismatch": values[-1]})
        mismatch[code] = values
    uncertainty = maximum_phase_uncertainty(mismatch, np.random.Generator(np.random.PCG64(SEED)))
    countries = countries.merge(uncertainty, on="ISO3", validate="one_to_one")
    countries["country_maximum_phase_uncertainty_method"] = "training_residual_transfer_complete_month_bootstrap_proxy"
    save_csv(replay, root / "reports/ipcch_four_target_training_replay.csv")
    save_csv(coverage, root / "reports/ipcch_country_month_coverage.csv")
    save_csv(pd.DataFrame(scenarios), root / "reports/ipcch_maximum_phase_scenarios.csv")
    save_csv(countries, root / "ipcch/country_confidence.csv")
    append_country_v3(country, countries).to_csv(root / "ipcch/country_predictions.csv", index=False)
    summary = {"training_rows": len(replay), "eligible_polygons": int(countries.country_error_eligible_area_count.sum()),
        "evidence_period": period, "flags": {str(k): int(v) for k, v in countries.country_confidence_flag.value_counts(dropna=False).items()},
        "low_countries": countries.loc[countries.country_confidence_flag.eq("low"), "ISO3"].tolist(),
        "country_overall_phase": {int(k): int(v) for k, v in countries.country_overall_phase.value_counts().sort_index().items()},
        "country_maximum_phase": {int(k): int(v) for k, v in countries.country_maximum_phase.value_counts().sort_index().items()},
        "country_month_groups": len(coverage), "complete_country_months": int(coverage.complete.sum()),
        "uncertainty_status": {k: int(v) for k, v in countries.country_maximum_phase_uncertainty_status.value_counts().items()},
        "no_complete_history": countries.loc[countries.country_maximum_phase_history_month_count.eq(0), "ISO3"].tolist(),
        "replay_phase3_matches_v2_saved_predictions": True, "anomalies": anomalies,
        "replay_sources_sha256": {str(path.relative_to(root)): sha256(path) for path in [root / "inputs/ipcch_panel.csv",
            root / "reports/ipcch_training_keys.csv", root / "reports/ipcch_training_predictions.csv",
            *sorted((root / "ipcch/model_package/scope_5m").glob("*"))]}}
    write_json(root / "reports/ipcch_country_confidence_v3_summary.json", summary)
    print(json.dumps(summary), flush=True)


def selfcheck():
    assert [confidence_flag(v) for v in [0, Fraction(1, 10), 0.1, Fraction(1, 10) + Fraction(1, 10**12), Fraction(1, 5), 0.2,
            Fraction(1, 5) + Fraction(1, 10**12), 1, None]] == ["high", "high", "medium", "medium", "medium", "low", "low", "low", None]
    # float 0.1 exceeds 1/10 exactly; decimal boundary 1/10 itself stays high. Real rates are rational from floats.
    scores = np.array([[.2, .2, .2, .2], [.19, .2, 0, 0], [0, 0, 0, .2], [.5, .1, .3, 0], [0, 0, 0, 0], [-1, 2, -1, -1]])
    np.testing.assert_array_equal(decode_cumulative_phase(scores), [5, 3, 5, 4, 1, 3])
    areas = pd.DataFrame({"polygon_id": list("abcde"), "ISO3": ["AAA"] * 3 + ["BBB"] * 2,
        "sample_count": [10, 1, np.nan, 2, 3], "error_count": [1, 1, np.nan, 1, 0],
        "population": [3., 1., 5., np.nan, 0.], "population_reference_period": "2024-10", "population_source": "x"})
    out = weighted_country_errors(areas, "fewsnet", "p", "population").set_index("ISO3")
    assert out.loc["AAA", "country_error_rate"] == (3 * .1 + 1 * 1) / 4 and out.loc["AAA", "country_confidence_flag"] == "low"
    assert out.loc["AAA", "country_error_missing_evidence_area_count"] == 1 and abs(out.loc["AAA", "country_error_known_population_coverage"] - 4 / 9) < 1e-15
    assert pd.isna(out.loc["BBB", "country_error_rate"]) and pd.isna(out.loc["BBB", "country_confidence_flag"])
    run = lambda: maximum_phase_uncertainty({"A": [], "B": [1], "C": [0, 0, 0], "D": [0, 1, 0, 1], "E": [1]}, np.random.Generator(np.random.PCG64(SEED)))
    first, second = run().set_index("ISO3"), run().set_index("ISO3")
    pd.testing.assert_frame_equal(first, second)
    assert first.country_maximum_phase_uncertainty_status.tolist() == ["no_complete_history", "single_month", "degenerate_empirical", "supported", "single_month"]
    assert pd.isna(first.loc["A", "country_maximum_phase_error_probability_proxy"]) and first.loc["B", "country_maximum_phase_error_probability_proxy"] == 1
    assert pd.isna(first.loc["B", "country_maximum_phase_error_probability_ci_lower"])
    assert first.loc["C", "country_maximum_phase_error_probability_ci_upper"] == 0 and first.loc["D", "country_maximum_phase_error_probability_proxy"] == .5
    assert 0 <= first.loc["D", "country_maximum_phase_error_probability_ci_lower"] < .5 < first.loc["D", "country_maximum_phase_error_probability_ci_upper"] <= 1
    assert [int(v >= CRISIS_THRESHOLD) for v in [.4999999, .5, .43]] == [0, 1, 0]
    print("PASS: exact flag cutoffs, cascade decode, missing-support weighting, bootstrap statuses/reproducibility, 0.5 boundary")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "fewsnet", "ipcch", "selfcheck"])
    parser.add_argument("--root", type=Path)
    parser.add_argument("--parent", type=Path)
    args = parser.parse_args()
    if args.action == "prepare": prepare(args.parent, args.root)
    elif args.action == "fewsnet": evaluate_fewsnet(args.root)
    elif args.action == "ipcch": evaluate_ipcch(args.root)
    else: selfcheck()
