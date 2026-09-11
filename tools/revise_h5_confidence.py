"""Re-score saved training rows, macro-average area errors, revise local delivery."""
from __future__ import annotations

import argparse
import gc
import json
import math
import shutil
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.refresh_h5_inputs import sha256, source_iso3, write_json
from tools.run_h5_model_delivery import read_csv, save_csv

POLICY = "reports/training_confidence_policy.json"
METHOD = "phase3plus_training_resubstitution_area_macro_v1"
LEGACY = ["prediction_uncertainty", "decision_margin", "uncertainty_critical_boundary", "uncertainty_method"]


def aggregate_errors(rows):
    if rows.empty or rows[["polygon_id", "ISO3", "error"]].isna().any().any():
        raise ValueError("Every training observation needs polygon, country and binary error")
    if not rows.error.isin([0, 1]).all() or rows.groupby("polygon_id").ISO3.nunique().ne(1).any():
        raise ValueError("Invalid binary error or conflicting polygon country")
    areas = rows.groupby(["polygon_id", "ISO3"], as_index=False).agg(
        training_sample_count=("error", "size"), training_error_count=("error", "sum"))
    areas["training_error_rate"] = areas.training_error_count / areas.training_sample_count
    records, exact = [], {}
    for iso, group in areas.groupby("ISO3"):
        value = sum((Fraction(int(r.training_error_count), int(r.training_sample_count))
                     for r in group.itertuples()), Fraction()) / len(group)
        exact[iso] = value
        records.append({"ISO3": iso, "country_training_error_rate": float(value),
            "country_training_area_count": len(group), "country_training_sample_count": int(group.training_sample_count.sum()),
            "country_training_error_count": int(group.training_error_count.sum()),
            "country_confidence_method": METHOD})
    countries = pd.DataFrame(records)
    # Exact rational comparisons prevent floating summation noise breaking mathematical ties.
    order = sorted(exact, key=lambda iso: (-exact[iso], iso))
    ranks = {iso: i + 1 for i, iso in enumerate(order)}
    quota = math.ceil(len(order) / 5)
    boundary = exact[order[quota - 1]]
    boundary_countries = [iso for iso in order if exact[iso] == boundary]
    tied_countries = boundary_countries if len(boundary_countries) > 1 else []
    countries["country_confidence_rank"] = countries.ISO3.map(ranks)
    countries["country_confidence_flag"] = np.where(countries.country_confidence_rank <= quota, "low", "high")
    countries["country_error_tied_at_boundary"] = countries.ISO3.isin(tied_countries)
    audit = {"countries": len(order), "low_quota": quota, "actual_low_fraction": quota / len(order),
        "boundary_error_rate": float(boundary), "boundary_tied_countries": tied_countries,
        "low_countries": order[:quota], "tie_break": "ISO3 ascending; exact rational error comparison"}
    return areas, countries, audit


def append_country_confidence(country, confidence):
    if country.ISO3.duplicated().any() or confidence.ISO3.duplicated().any() or set(country.ISO3) != set(confidence.ISO3):
        raise ValueError("Country confidence must cover the exact unique country universe")
    renames = {c: c.replace("_aggregation_uncertainty", "_area_dispersion")
               for c in country if c.endswith("_aggregation_uncertainty")}
    renames["aggregation_uncertainty_method"] = "area_dispersion_method"
    return country.rename(columns=renames).merge(confidence, on="ISO3", how="left", validate="one_to_one", sort=False)


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
    shutil.copytree(parent, root, ignore=exclude)
    shutil.copy2(parent / "manifest.json", root / "reports/parent_delivery_manifest.json")
    shutil.copy2(parent / "reports/final_verification.json", root / "reports/parent_final_verification.json")
    write_json(root / POLICY, {"method": METHOD, "parent_directory": str(parent),
        "parent_manifest_sha256": sha256(parent / "manifest.json"), "evaluation": "in_sample_final_model_resubstitution",
        "event": "Phase3+ binary disagreement; IPCCH raw phase3_worse score and true cumulative share each >=0.2",
        "country_aggregation": "equal polygon mean of per-polygon errors, not pooled rows or population weighting",
        "low_fraction": 0.2, "quota": "ceil(N/5)", "ranking": "error descending, ISO3 ascending for ties",
        "flags": ["low", "high"], "models_retrained": False, "forecasts_changed": False})
    pred_path = root / "ipcch/polygon_predictions.csv"
    read_csv(pred_path).drop(columns=LEGACY).to_csv(pred_path, index=False)
    summary_path = root / "reports/ipcch_scoring.json"
    summary = json.loads(summary_path.read_text()); summary.pop("uncertainty", None)
    summary_path.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    for name in ["model_pipeline", "fewsnet_partitioned_rf_pipeline"]:
        shutil.copytree(ROOT / name, root / "runtime" / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for path in (ROOT / "tools").glob("*h5*.py"):
        shutil.copy2(path, root / "runtime/tools" / path.name)
    shutil.copy2(ROOT / "docs/superpowers/specs/2026-09-11-training-confidence.md", root / "reports/training_confidence_spec.md")
    readme = (root / "README.md").read_text()
    readme = readme.replace("`prediction_uncertainty`/`decision_margin` retain the original qualitative threshold-margin method, not a statistical confidence interval.",
        "The old polygon threshold-margin uncertainty fields and calculation are removed in this revision.")
    readme = readme.replace("`*_dispersion` / `*_aggregation_uncertainty`", "`*_dispersion`")
    note = """# Training-confidence revision, 2026-09-11

Country tables now include `country_training_error_rate` (0..1) and `country_confidence_flag` (`low`/`high`). These are **in-sample training-fit diagnostics**, not held-out accuracy, calibrated uncertainty or future failure probabilities. Saved models and September forecasts are unchanged.

Each polygon's error is its count of incorrect Phase3+ training decisions divided by its own training sample count. Country error is the **equal-weight mean over polygons**. Population and number of rows per polygon do not weight this mean. FEWSNET uses its saved crisis threshold; IPCCH compares its raw Phase3+ share score and actual cumulative share with >=0.2 (distinct from the cumulative overall-phase decoder).

Rank separately within each model by highest country error first. Exactly ceil(N/5) countries are low:5/22 FEWSNET and11/53 IPCCH. Others are high. Mathematical ties use ISO3 ascending, including when all errors are zero; `country_error_tied_at_boundary` and the policy/report disclose this forced allocation. High means relatively better training fit, not absolute reliability.

`{model}/polygon_training_errors.csv` contains polygon ID, ISO3, training sample/error counts and error rate. `reports/{model}_training_predictions.csv` contains each training key, predicted score/decision, actual value/decision, threshold and error. `{model}/country_training_confidence.csv` is the country diagnostic table joined into `country_predictions.csv`, including support counts and confidence rank. `reports/training_confidence_summary.json` records quotas and boundary ties.

IPCCH polygon CSV no longer contains prediction_uncertainty, decision_margin, uncertainty_critical_boundary or uncertainty_method. Country score standard deviations are preserved as `phase*_worse_score_area_dispersion` with `area_dispersion_method`; FEWSNET dispersion names stay the same. This dispersion remains population-weighted spatial variation, separate from the new equal-polygon error.

The portable scoring command below still works. Confidence tables describe the frozen training evidence and are already included; they do not change when the fixed April inputs are rescored. Recomputing training diagnostics requires full delivered history panels, which are outside the application archive. `reports/parent_*` and original execution reports are provenance of the unchanged base model; the root manifest and current final verification certify this revision.

---

"""
    (root / "README.md").write_text(note + readme)
    print(f"Prepared {root}", flush=True)


def load_training(root, system):
    keys = read_csv(root / f"reports/{system}_training_keys.csv")
    if system == "fewsnet":
        from fewsnet_partitioned_rf_pipeline.local.package import load_local_model_package
        from fewsnet_partitioned_rf_pipeline.core.preprocessing import Stage3FeatureBuilder
        from fewsnet_partitioned_rf_pipeline.core.horizons import align_horizon
        loaded = load_local_model_package(root / "fewsnet/model_package")
        assert sha256(root / "inputs/fewsnet_panel.csv") == loaded.manifest["source_panel"]["sha256"]
        panel = read_csv(root / "inputs/fewsnet_panel.csv")
        features = Stage3FeatureBuilder().transform(panel, loaded.predictor.feature_contract)
        del panel; gc.collect()
        train = align_horizon(features, 5).frame
        del features; gc.collect()
        for c in ["feature_month", "target_month"]:
            train[c] = train[c].astype(str)
        train = keys.merge(train, on=list(keys.columns), how="left", validate="one_to_one", indicator=True)
        assert train._merge.eq("both").all()
        prediction = loaded.predictor.predict_frame(train)
        rows = keys.rename(columns={"admin_code": "polygon_id"}).copy()
        rows["predicted_score"] = prediction.probability_crisis.to_numpy()
        rows["actual_value"] = train.fews_ipc_crisis.to_numpy()
        threshold = loaded.predictor.threshold
        rows["predicted_phase3plus"] = prediction.predicted_crisis.to_numpy()
        rows["actual_phase3plus"] = train.fews_ipc_crisis.to_numpy(dtype=int)
        identity = read_csv(root / "inputs/fewsnet_identity_population.csv")[["admin_code", "ISO3"]].rename(columns={"admin_code": "polygon_id"})
    else:
        from model_pipeline.ipcch_launch_runtime.model_package import load_scope_package
        from model_pipeline.ipcch_launch_runtime.feature_contract import apply_feature_contract
        loaded = load_scope_package(root / "ipcch/model_package", 5)
        assert sha256(root / "inputs/ipcch_panel.csv") == loaded["metadata"]["source_panel_sha256"]
        columns = loaded["feature_columns"]
        phases = [f"phase{i}_percent" for i in range(2, 6)]
        feature_keys = pd.MultiIndex.from_frame(keys[["area_id", "feature_period"]])
        target_keys = pd.MultiIndex.from_frame(keys[["area_id", "target_period"]])
        features, labels = [], []
        for chunk in pd.read_csv(root / "inputs/ipcch_panel.csv", usecols=["admin_code", "year", "month", *columns, *phases],
                                 dtype={"admin_code": "string"}, float_precision="round_trip", chunksize=50000):
            chunk["area_id"] = chunk.admin_code.str.strip()
            chunk["period"] = pd.to_datetime(dict(year=chunk.year, month=chunk.month, day=1)).dt.to_period("M").astype(str)
            index = pd.MultiIndex.from_frame(chunk[["area_id", "period"]])
            features.append(chunk.loc[index.isin(feature_keys), ["area_id", "period", *columns]])
            labels.append(chunk.loc[index.isin(target_keys), ["area_id", "period", *phases]])
        f = pd.concat(features).rename(columns={"period": "feature_period"})
        y = pd.concat(labels).rename(columns={"period": "target_period"})
        train = keys.merge(f, on=["area_id", "feature_period"], validate="one_to_one", how="left", indicator=True)
        assert train._merge.eq("both").all(); train = train.drop(columns="_merge")
        train = train.merge(y, on=["area_id", "target_period"], validate="one_to_one", how="left", indicator=True)
        assert train._merge.eq("both").all()
        train[columns + phases] = train[columns + phases].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
        assert train[phases].notna().all().all()
        matrix, _ = apply_feature_contract(train, loaded["contract"], columns,
            package_root=loaded["scope_dir"], metadata=loaded["metadata"])
        rows = keys.rename(columns={"area_id": "polygon_id", "feature_period": "feature_month", "target_period": "target_month"}).copy()
        rows["predicted_score"] = loaded["models"]["phase3_worse"].predict(matrix)
        rows["actual_value"] = train[["phase3_percent", "phase4_percent", "phase5_percent"]].sum(axis=1, min_count=3)
        threshold = .2
        rows["predicted_phase3plus"] = (rows.predicted_score >= threshold).astype(int)
        rows["actual_phase3plus"] = (rows.actual_value >= threshold).astype(int)
        identity = read_csv(root / "inputs/ipcch_april_panel.csv")
        identity["ISO3"] = source_iso3(identity)
        identity = identity[["area_id", "ISO3"]].rename(columns={"area_id": "polygon_id"})
    assert len(rows) == len(keys) and not rows.duplicated(["polygon_id", "feature_month", "target_month"]).any()
    assert np.isfinite(rows[["predicted_score", "actual_value"]]).all().all()
    assert rows.actual_phase3plus.isin([0, 1]).all()
    assert set(rows.polygon_id) == set(identity.polygon_id)
    rows["decision_threshold"] = threshold
    rows["error"] = rows.predicted_phase3plus.ne(rows.actual_phase3plus).astype(int)
    rows = rows.merge(identity, on="polygon_id", how="left", validate="many_to_one")
    rows["model_system"] = system
    return rows


def evaluate(root, system):
    print(f"{system}: loading saved model and reconstructing exact training rows", flush=True)
    rows = load_training(root, system)
    areas, countries, audit = aggregate_errors(rows)
    save_csv(rows, root / f"reports/{system}_training_predictions.csv")
    save_csv(areas, root / f"{system}/polygon_training_errors.csv")
    save_csv(countries, root / f"{system}/country_training_confidence.csv")
    country_path = root / f"{system}/country_predictions.csv"
    augmented = append_country_confidence(read_csv(country_path), countries)
    augmented.to_csv(country_path, index=False)
    write_json(root / f"reports/{system}_confidence_summary.json", {**audit, "training_rows": len(rows), "polygons": len(areas), "method": METHOD})
    print(json.dumps(audit), flush=True)


def selfcheck():
    # A: (1/1 + 0/9)/2 = 0.5, not pooled 1/10. B..F tie at zero.
    rows = pd.DataFrame({"polygon_id": ["a"] + ["b"] * 9 + list("cdefg"),
        "ISO3": ["AAA"] * 10 + ["BBB", "CCC", "DDD", "EEE", "FFF"], "error": [1] + [0] * 14})
    _, country, audit = aggregate_errors(rows)
    assert country.set_index("ISO3").loc["AAA", "country_training_error_rate"] == .5
    assert audit["low_quota"] == 2 and audit["low_countries"] == ["AAA", "BBB"]
    assert audit["boundary_tied_countries"] == ["BBB", "CCC", "DDD", "EEE", "FFF"]
    _, reversed_country, _ = aggregate_errors(rows.iloc[::-1])
    pd.testing.assert_frame_equal(country, reversed_country)
    assert [(p >= .2) != (a >= .2) for p, a in [(.2, .2), (.199, .2), (.2, .199)]] == [False, True, True]
    print("PASS: polygon macro vs pooled error, ceil quota, ISO3 boundary ties, row-order invariance, Phase3 threshold")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "evaluate", "selfcheck"])
    parser.add_argument("--root", type=Path)
    parser.add_argument("--parent", type=Path)
    parser.add_argument("--system", choices=["fewsnet", "ipcch"])
    args = parser.parse_args()
    if args.action == "prepare": prepare(args.parent, args.root)
    elif args.action == "evaluate": evaluate(args.root, args.system)
    else: selfcheck()
