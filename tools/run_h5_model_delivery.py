"""Local-only April -> September 2026 training, export and portable scoring."""
from __future__ import annotations

import argparse
import gc
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.refresh_h5_inputs import sha256, write_json

FEATURE_MONTH, TARGET_MONTH, HORIZON = "2026-04", "2026-09", 5
TARGETS = [f"phase{i}_worse" for i in range(2, 6)]
XGB_PARAMS = dict(objective="reg:squarederror", n_estimators=200, max_depth=6,
                  learning_rate=0.08, subsample=0.9, colsample_bytree=0.8,
                  random_state=42, n_jobs=4)


def read_csv(path, **kwargs):
    return pd.read_csv(path, low_memory=False, float_precision="round_trip",
                       dtype={"admin_code": "string", "area_id": "string", "polygon_id": "string"}, **kwargs)


def save_csv(frame, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as stream:
        frame.to_csv(stream, index=False)


def training_keys(frame, feature, target, root, system):
    assert (frame[target] == frame[feature] + HORIZON).all()
    assert frame[target].max() <= pd.Period(FEATURE_MONTH, freq="M")
    identity = "admin_code" if system == "fewsnet" else "area_id"
    save_csv(frame[[identity, feature, target]], root / f"reports/{system}_training_keys.csv")
    return {"rows": len(frame), "feature_min": str(frame[feature].min()),
            "feature_max": str(frame[feature].max()), "target_min": str(frame[target].min()),
            "target_max": str(frame[target].max()),
            "target_periods": [str(p) for p in sorted(frame[target].unique())]}


def train_fewsnet(root, commit):
    from fewsnet_partitioned_rf_pipeline.config import FEATURE_CONTRACT_PATH, PARTITION_ASSET_PATH, PARTITION_ASSET_SHA256
    from fewsnet_partitioned_rf_pipeline.core.preprocessing import Stage3FeatureBuilder, load_feature_contract
    from fewsnet_partitioned_rf_pipeline.core.partitions import PartitionMap
    from fewsnet_partitioned_rf_pipeline.core.horizons import align_horizon, select_training_window, select_latest_inference_frame
    from fewsnet_partitioned_rf_pipeline.core.normalization import validate_normalization_audit
    from fewsnet_partitioned_rf_pipeline.core.training import train_horizon_model
    from fewsnet_partitioned_rf_pipeline.local.outputs import build_identity_population_frame
    from fewsnet_partitioned_rf_pipeline.local.package import LocalPackageMetadata, write_local_model_package
    panel_path, audit_path = root / "inputs/fewsnet_panel.csv", root / "inputs/fewsnet_panel.audit.json"
    audit = validate_normalization_audit(audit_path, panel_path)
    panel = read_csv(panel_path)
    contract = load_feature_contract(FEATURE_CONTRACT_PATH)
    partitions = PartitionMap.load(PARTITION_ASSET_PATH, PARTITION_ASSET_SHA256)
    print("FEWSNET: constructing frozen Stage3 features", flush=True)
    features = Stage3FeatureBuilder().transform(panel, contract)
    identity, _ = build_identity_population_frame(panel, FEATURE_MONTH)
    save_csv(identity, root / "inputs/fewsnet_identity_population.csv")
    april = select_latest_inference_frame(features, FEATURE_MONTH, HORIZON)
    save_csv(april, root / "inputs/fewsnet_april_features.csv")
    del panel; gc.collect()
    aligned = align_horizon(features, HORIZON).frame
    aligned = aligned.loc[aligned.target_month <= pd.Period(FEATURE_MONTH, freq="M")]
    latest = str(aligned.target_month.max())
    train = select_training_window(aligned, latest, months=36)
    keys = training_keys(train, "feature_month", "target_month", root, "fewsnet")
    del features, aligned; gc.collect()
    print(f"FEWSNET: training {len(train)} rows, {keys['target_min']}..{latest}", flush=True)
    result = train_horizon_model(train, contract, partitions, "5m")
    panel_hash = sha256(panel_path)
    version = f"local-202604-{commit[:12]}-{panel_hash[:12]}"
    metadata = LocalPackageMetadata(version, FEATURE_MONTH, TARGET_MONTH, latest, commit,
        "inputs/fewsnet_panel.csv", panel_hash, panel_path.stat().st_size, audit["output_panel"]["row_count"],
        "inputs/fewsnet_panel.audit.json", sha256(audit_path), audit_path.stat().st_size)
    write_local_model_package(root / "fewsnet/model_package", result.predictor, metadata,
        {"training_report": result.training_report, "threshold_report": result.threshold_report})
    write_json(root / "reports/fewsnet_training.json", {**keys, "source_git_commit": commit,
        "fit_periods": keys["target_periods"][:-6], "validation_periods": keys["target_periods"][-6:]})
    print("FEWSNET: package exported", flush=True)


def train_ipcch(root, commit):
    """Same production-safe launch fit; frozen columns and explicit label cutoff."""
    from xgboost import XGBRegressor
    old = ROOT / "model_artifacts/launch_2026_04/scope_6m"
    columns = json.loads((old / "feature_columns.json").read_text())
    if isinstance(columns, dict):
        columns = columns["feature_columns"]
    phase_cols = [f"phase{i}_percent" for i in range(2, 6)]
    panel = read_csv(root / "inputs/ipcch_panel.csv", usecols=["admin_code", "year", "month", *columns, *phase_cols])
    panel["area_id"] = panel.admin_code.str.strip()
    panel["period"] = pd.to_datetime(dict(year=panel.year, month=panel.month, day=1)).dt.to_period("M")
    panel = panel.loc[panel.period <= pd.Period(FEATURE_MONTH, freq="M")].copy()
    assert not panel.duplicated(["area_id", "period"]).any()
    panel[columns + phase_cols] = panel[columns + phase_cols].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    for i, target in zip(range(2, 6), TARGETS):
        required = [f"phase{j}_percent" for j in range(i, 6)]
        panel[target] = panel[required].sum(axis=1, min_count=len(required))
    labels = panel.dropna(subset=TARGETS)[["area_id", "period", *TARGETS]].rename(columns={"period": "target_period"})
    labels["feature_period"] = labels.target_period - HORIZON
    train = panel[["area_id", "period", *columns]].rename(columns={"period": "feature_period"}).merge(
        labels, on=["area_id", "feature_period"], how="inner", validate="one_to_one")
    train = train.loc[(train.feature_period < pd.Period(FEATURE_MONTH, freq="M")) &
                      (train.target_period <= pd.Period(FEATURE_MONTH, freq="M"))].sort_values(["feature_period", "area_id"]).reset_index(drop=True)
    report = training_keys(train, "feature_period", "target_period", root, "ipcch")
    medians = train[columns].median()
    if medians.isna().any():
        raise ValueError(f"Frozen IPCCH features entirely missing: {list(medians.index[medians.isna()])}")
    matrix = train[columns].fillna(medians)
    del panel, labels; gc.collect()
    out = root / "ipcch/model_package/scope_5m"; out.mkdir(parents=True)
    for target in TARGETS:
        print(f"IPCCH: training {target}, {len(train)} rows", flush=True)
        model = XGBRegressor(**XGB_PARAMS).fit(matrix, train[target])
        model.save_model(out / f"{target}_model.json")
    contract = read_csv(old / "feature_contract.csv")
    assert list(contract.feature_name) == columns
    contract["scope_months"] = HORIZON
    save_csv(contract, out / "feature_contract.csv")
    write_json(out / "feature_columns.json", columns)
    metadata = {"model_package_id": f"{root.name}-ipcch-{commit[:12]}", "feature_month": FEATURE_MONTH,
        "target_month": TARGET_MONTH, "scope_months": HORIZON, "source_git_commit": commit,
        "thresholds": {"default": 0.2}, "monotonicity_policy": "cummax", "parameters": XGB_PARAMS,
        "imputation_statistics": {f"median:{col}": float(value) for col, value in medians.items()},
        "training": report, "baseline_feature_columns_sha256": sha256(old / "feature_columns.json"),
        "source_panel_sha256": sha256(root / "inputs/ipcch_panel.csv"),
        "method_source": "IPCCH/scripts/modeling/train_export_operational_launch_production_safe.py"}
    write_json(out / "model_metadata.json", metadata)
    write_json(root / "reports/ipcch_training.json", metadata)


def score(root, out):
    from fewsnet_partitioned_rf_pipeline.local.package import load_local_model_package
    from fewsnet_partitioned_rf_pipeline.local.outputs import enrich_local_predictions, validate_local_prediction_frame
    from model_pipeline.ipcch_launch_runtime.adapters import validate_monthly_input
    from model_pipeline.run_operational_launch_inference import run_scope
    loaded = load_local_model_package(root / "fewsnet/model_package")
    features = read_csv(root / "inputs/fewsnet_april_features.csv")
    identity = read_csv(root / "inputs/fewsnet_identity_population.csv")
    predictions = enrich_local_predictions(loaded.predictor.predict_frame(features), identity,
        model_artifact_path="fewsnet/model_package", source_input="inputs/fewsnet_april_features.csv")
    validate_local_prediction_frame(predictions, expected_admin_codes=identity.admin_code,
        feature_month=FEATURE_MONTH, target_month=TARGET_MONTH, horizon_months=HORIZON,
        suite_version=loaded.predictor.suite_version)
    save_csv(predictions, out / "fewsnet/polygon_predictions.csv")
    monthly, _ = validate_monthly_input(read_csv(root / "inputs/ipcch_april_panel.csv"), FEATURE_MONTH)
    ipcch, summary = run_scope(monthly_rows=monthly, model_package_root=root / "ipcch/model_package",
        feature_month=FEATURE_MONTH, scope_months=HORIZON, target_month=TARGET_MONTH,
        source_input="inputs/ipcch_april_panel.csv")
    ipcch.insert(0, "polygon_id", ipcch.area_id.astype(str))
    save_csv(ipcch, out / "ipcch/polygon_predictions.csv")
    write_json(out / "reports/ipcch_scoring.json", summary)
    print(f"Reloaded scoring complete: FEWSNET={len(predictions)}, IPCCH={len(ipcch)}", flush=True)


def export_tables(root):
    import geopandas as gpd
    import pycountry
    from tools.build_fewsnet_country_level_predictions import aggregate_country_probabilities
    from tools.build_ipcch_country_level_predictions import aggregate_country_scores
    for system in ["fewsnet", "ipcch"]:
        predictions = read_csv(root / f"{system}/polygon_predictions.csv")
        census_path = ROOT / f"Outcome/{'fewsnet_partitioned_rf' if system == 'fewsnet' else 'ipcch_unified'}/predictions/202604/country_level/census_idb_2026_{system}_country_population.csv"
        census = read_csv(census_path)
        shutil.copy2(census_path, root / f"{system}/country_population_reference.csv")
        if system == "fewsnet":
            scope = census[["ISO3", "country", "country_en"]].copy()
            scope["country_code"] = scope.ISO3.map(lambda x: pycountry.countries.get(alpha_3=x).alpha_2)
            country = aggregate_country_probabilities(predictions, scope, census)
            mapping = predictions[["admin_code", "cluster_id", "prediction_source", "suite_version"]].copy()
            mapping.insert(0, "polygon_id", mapping.admin_code)
            mapping["actual_model"] = [f"partition_models[{int(c)}]" if s == "partition_model" else "pooled_model"
                                       for c, s in zip(mapping.cluster_id, mapping.prediction_source)]
            mapping["fallback_reason"] = mapping.prediction_source.where(mapping.prediction_source.ne("partition_model"), "")
            geometry = gpd.read_file(ROOT / "Outcome/fewsnet_partitioned_rf/spatial/fewsnet_admin_geometry_plot.gpkg")
            geometry["polygon_id"] = geometry.admin_code.astype(str)
        else:
            monthly = read_csv(root / "inputs/ipcch_april_panel.csv")
            country = aggregate_country_scores(predictions, monthly[["area_id", "country", "country_en"]], census)
            mapping = predictions[["polygon_id", "area_id", "admin_code", "model_package_id"]].copy()
            mapping["cluster_id"] = pd.NA
            mapping["actual_model"] = "scope_5m:phase2_worse,phase3_worse,phase4_worse,phase5_worse"
            mapping["fallback_reason"] = ""
            geometry = gpd.read_file(ROOT / "Outcome/ipcch_unified/spatial/ipcch_admin_geometry.shp")
            geometry["polygon_id"] = geometry.admin_code.astype(str)
        mapping["model_system"] = system
        mapping["model_package"] = f"{system}/model_package"
        mapping["feature_month"], mapping["target_month"], mapping["horizon_months"] = FEATURE_MONTH, TARGET_MONTH, HORIZON
        assert not mapping.polygon_id.duplicated().any()
        assert not geometry.polygon_id.duplicated().any()
        assert set(mapping.polygon_id) == set(geometry.polygon_id)
        save_csv(mapping, root / f"{system}/polygon_model_mapping.csv")
        save_csv(country, root / f"{system}/country_predictions.csv")
        geometry = geometry[["polygon_id", "geometry"]].to_crs(4326)
        payload = json.loads(geometry.to_json(na="null", drop_id=True))
        write_json(root / f"{system}/polygons.geojson", payload)
        print(f"{system}: {len(mapping)} polygons, {len(country)} countries exported", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["train-fewsnet", "train-ipcch", "score", "export"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.action.startswith("train-"):
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        {"train-fewsnet": train_fewsnet, "train-ipcch": train_ipcch}[args.action](args.root, commit)
    elif args.action == "score":
        score(args.root, args.output or args.root)
    else:
        export_tables(args.root)
