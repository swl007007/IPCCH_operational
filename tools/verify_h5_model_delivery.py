"""Independent checks of delivered polygons, training keys, countries and reloads."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from tools.run_h5_model_delivery import read_csv, TARGETS
from tools.refresh_h5_inputs import write_json


def verify(root):
    revised = (root / "reports/training_confidence_policy.json").exists()
    report = {"status": "passed", "tests": "focused artifact checks and independent arithmetic; no regression suite", "models": {}}
    for system, count in [("fewsnet", 5718), ("ipcch", 6227)]:
        p = read_csv(root / f"{system}/polygon_predictions.csv")
        m = read_csv(root / f"{system}/polygon_model_mapping.csv")
        c = read_csv(root / f"{system}/country_predictions.csv")
        geo = json.loads((root / f"{system}/polygons.geojson").read_text(), parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
        identity = "admin_code" if system == "fewsnet" else "area_id"
        feature, target, horizon = ("feature_month", "target_month", "horizon_months") if system == "fewsnet" else ("feature_period", "target_period", "scope_months")
        inputs = read_csv(root / ("inputs/fewsnet_april_features.csv" if system == "fewsnet" else "inputs/ipcch_april_panel.csv"))
        geo_ids = [f["properties"]["polygon_id"] for f in geo["features"]]
        assert all(isinstance(v, str) for v in geo_ids)
        assert len(p) == len(m) == len(geo_ids) == count
        assert not p[identity].duplicated().any() and not m.polygon_id.duplicated().any() and len(set(geo_ids)) == count
        assert set(p[identity]) == set(m.polygon_id) == set(geo_ids) == set(inputs[identity])
        assert m.polygon_id.eq(m[identity]).all()
        if "polygon_id" in p:
            assert p.polygon_id.eq(p[identity]).all()
        assert not c.ISO3.duplicated().any() and c.ISO3.notna().all()
        reference = read_csv(root / f"{system}/country_population_reference.csv").set_index("ISO3")
        reference_columns = [col for col in reference if col not in ["country", "country_en"]]
        pd.testing.assert_frame_equal(c.set_index("ISO3")[reference_columns].sort_index(),
            reference.loc[c.ISO3, reference_columns].sort_index(), check_dtype=False)
        for df, fields in [(p, (feature, target, horizon)), (c, (feature, target, horizon)), (m, ("feature_month", "target_month", "horizon_months"))]:
            assert df[fields[0]].eq("2026-04").all() and df[fields[1]].eq("2026-09").all() and df[fields[2]].eq(5).all()
        keys = read_csv(root / f"reports/{system}_training_keys.csv")
        a, b = pd.PeriodIndex(keys[feature], freq="M"), pd.PeriodIndex(keys[target], freq="M")
        assert (a + 5 == b).all() and b.max() <= pd.Period("2026-04", freq="M")
        assert not keys.duplicated([identity, feature]).any()
        model_report = {"polygons": count, "countries": len(c), "training_rows": len(keys),
                        "training_feature_max": str(a.max()), "training_label_max": str(b.max())}
        if system == "fewsnet":
            from fewsnet_partitioned_rf_pipeline.local.package import load_local_model_package
            loaded = load_local_model_package(root / "fewsnet/model_package")
            expected_periods = sorted(keys.target_month.unique())
            assert len(expected_periods) == 36
            meta = json.loads((root / "reports/fewsnet_training.json").read_text())
            assert meta["fit_periods"] == expected_periods[:-6] and meta["validation_periods"] == expected_periods[-6:]
            assert loaded.training_report["sample_count"] == len(keys)
            assert loaded.training_report["fit_sample_count"] == int(keys.target_month.isin(expected_periods[:-6]).sum())
            assert loaded.training_report["validation_sample_count"] == int(keys.target_month.isin(expected_periods[-6:]).sum())
            scores, weight = ["probability_crisis"], "population"
            population_input = read_csv(root / "inputs/fewsnet_identity_population.csv").set_index(identity)
            assert np.isfinite(p.probability_crisis).all() and p.probability_crisis.between(0, 1).all()
            assert (p.predicted_crisis == (p.probability_crisis >= p.threshold).astype(int)).all()
            assert p.threshold.eq(loaded.predictor.threshold).all()
            for row in m.itertuples():
                cluster = loaded.predictor.partition_map.get(row.polygon_id)
                model = loaded.predictor.partition_models.get(cluster)
                actual = f"partition_models[{cluster}]" if model is not None else "pooled_model"
                assert actual == row.actual_model
                assert (pd.isna(row.cluster_id) and cluster is None) or row.cluster_id == cluster
            model_report["prediction_sources"] = p.prediction_source.value_counts().to_dict()
            model_report["threshold"] = loaded.predictor.threshold
            grouped = p.groupby("ISO3")
        else:
            if revised:
                assert not {"prediction_uncertainty", "decision_margin", "uncertainty_critical_boundary", "uncertainty_method"}.intersection(p.columns)
            scores, weight = [f"{v}_score" for v in TARGETS], "population_estimate"
            population_input = inputs.set_index(identity)
            values = p[scores].to_numpy()
            assert np.isfinite(values).all()
            binary = np.maximum.accumulate((values >= .2)[:, ::-1], axis=1)[:, ::-1]
            np.testing.assert_array_equal(binary, p[[f"{v}_pred" for v in TARGETS]].to_numpy())
            phase = np.where(binary.any(axis=1), (binary * np.arange(2, 6)).max(axis=1), 1)
            np.testing.assert_array_equal(phase, p.overall_phase_pred)
            model_report["scores_below_zero"] = {s: int((p[s] < 0).sum()) for s in scores}
            model_report["scores_above_one"] = {s: int((p[s] > 1).sum()) for s in scores}
            model_report["nonmonotonic_raw_score_rows"] = int((np.diff(values, axis=1) > 0).any(axis=1).sum())
            assert m.cluster_id.isna().all() and m.actual_model.nunique() == 1
            lookup = inputs[["area_id", "country"]].merge(
                reference.reset_index()[["country", "ISO3"]], on="country", validate="many_to_one")
            p = p.merge(lookup[["area_id", "ISO3"]], on="area_id", validate="one_to_one")
            model_report["input_iso3_missing_rows_resolved_by_country"] = int(inputs.ISO3.isna().sum())
            grouped = p.groupby("ISO3")
        assert set(c.ISO3) == set(p.ISO3)
        np.testing.assert_allclose(p[weight], population_input.loc[p[identity], weight], rtol=0, atol=0, equal_nan=True)
        for iso, group in grouped:
            row = c.loc[c.ISO3.eq(iso)].iloc[0]
            w = group[weight].to_numpy(dtype=float)
            positive = np.isfinite(w) & (w > 0)
            assert row.area_count == len(group)
            if system == "fewsnet":
                assert row.positive_population_area_count == positive.sum()
                assert row.missing_population_area_count == np.isnan(w).sum()
                assert row.zero_population_area_count == (w == 0).sum()
                assert row.finite_population_area_count == np.isfinite(w).sum()
                np.testing.assert_allclose(row.area_population_weight_sum, w[positive].sum(), rtol=1e-12)
            else:
                assert np.isfinite(w).all() and (w >= 0).all()
                assert row.positive_weight_area_count == positive.sum()
            for score in scores:
                s, weights = group[score].to_numpy()[positive], w[positive]
                mean = np.dot(s, weights) / weights.sum()
                sd = np.sqrt(np.dot((s - mean) ** 2, weights) / weights.sum())
                dispersion = "probability_crisis_area_dispersion" if system == "fewsnet" else f"{score}_aggregation_uncertainty"
                if revised and system == "ipcch":
                    dispersion = f"{score}_area_dispersion"
                np.testing.assert_allclose([row[score], row[dispersion]], [mean, sd], rtol=0, atol=1e-12)
        report["models"][system] = model_report
    # Relocate only the self-contained scoring delivery; histories and geometries are not scoring dependencies.
    with tempfile.TemporaryDirectory(prefix="h5-reload-") as tmp:
        moved = Path(tmp) / "delivery"; moved.mkdir()
        shutil.copytree(root / "runtime", moved / "runtime")
        if revised:
            (moved / "reports").mkdir()
            shutil.copy2(root / "reports/training_confidence_policy.json", moved / "reports/training_confidence_policy.json")
        for system in ["fewsnet", "ipcch"]:
            shutil.copytree(root / f"{system}/model_package", moved / f"{system}/model_package")
        (moved / "inputs").mkdir()
        for name in ["fewsnet_april_features.csv", "fewsnet_identity_population.csv", "ipcch_april_panel.csv"]:
            shutil.copy2(root / "inputs" / name, moved / "inputs" / name)
        env = {k: v for k, v in os.environ.items() if k not in ["PYTHONPATH", "GOOGLE_APPLICATION_CREDENTIALS"]}
        subprocess.run([sys.executable, "-B", str(moved / "runtime/tools/run_h5_model_delivery.py"), "score",
                        "--root", str(moved), "--output", str(moved / "rescored")], cwd=tmp, env=env, check=True)
        for system in ["fewsnet", "ipcch"]:
            original = read_csv(root / f"{system}/polygon_predictions.csv")
            rescored = read_csv(moved / f"rescored/{system}/polygon_predictions.csv")
            pd.testing.assert_frame_equal(original, rescored, check_exact=False, rtol=0, atol=1e-12)
            report["models"][system]["relocated_reload_all_fields_equal"] = True
    write_json(root / "reports/final_verification.json", report)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    verify(parser.parse_args().root)
