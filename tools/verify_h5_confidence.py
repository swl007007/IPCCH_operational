"""Independent verification of saved training errors and revised country flags."""
import argparse
import json
import sys
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.run_h5_model_delivery import read_csv
from tools.refresh_h5_inputs import sha256, source_iso3, write_json


def verify(root):
    policy = json.loads((root / "reports/training_confidence_policy.json").read_text())
    parent = Path(policy["parent_directory"])
    assert sha256(parent / "manifest.json") == policy["parent_manifest_sha256"]
    manifest = json.loads((parent / "manifest.json").read_text())
    unchanged = 0
    for item in manifest["files"]:
        relative = item["path"]
        assert sha256(parent / relative) == item["sha256"], relative
        if "/model_package/" in relative or relative.startswith("inputs/") or relative.endswith(("polygons.geojson", "polygon_model_mapping.csv", "country_population_reference.csv")):
            assert sha256(root / relative) == item["sha256"], relative
            unchanged += 1
    report = {"status": "passed", "evaluation": "in_sample_resubstitution", "protected_files_unchanged": unchanged, "models": {}}
    summaries = {}
    for system, expected_rows, expected_areas, expected_countries, quota in [
            ("fewsnet", 188643, 5718, 22, 5), ("ipcch", 43551, 6227, 53, 11)]:
        rows = read_csv(root / f"reports/{system}_training_predictions.csv")
        keys = read_csv(root / f"reports/{system}_training_keys.csv").rename(columns={
            "admin_code": "polygon_id", "area_id": "polygon_id", "feature_period": "feature_month", "target_period": "target_month"})
        keycols = ["polygon_id", "feature_month", "target_month"]
        pd.testing.assert_frame_equal(rows[keycols], keys[keycols], check_dtype=False)
        assert len(rows) == expected_rows and not rows.duplicated(keycols).any()
        assert rows.model_system.eq(system).all()
        assert np.isfinite(rows[["predicted_score", "actual_value"]]).all().all()
        assert (pd.PeriodIndex(rows.feature_month, freq="M") + 5 == pd.PeriodIndex(rows.target_month, freq="M")).all()
        assert rows.target_month.le("2026-04").all()
        if system == "fewsnet":
            from fewsnet_partitioned_rf_pipeline.core.data import normalize_admin_code
            labels = read_csv(root / "inputs/fewsnet_panel.csv", usecols=["FEWSNET_admin_code", "date", "fews_ipc_crisis"])
            labels["polygon_id"] = labels.FEWSNET_admin_code.map(normalize_admin_code)
            labels["target_month"] = pd.to_datetime(labels.date).dt.to_period("M").astype(str)
            expected = rows[keycols].merge(labels[["polygon_id", "target_month", "fews_ipc_crisis"]],
                on=["polygon_id", "target_month"], validate="one_to_one", how="left").fews_ipc_crisis
            assert expected.notna().all()
            actual_binary = expected.to_numpy()
            threshold = json.loads((root / "fewsnet/model_package/threshold_report.json").read_text())["threshold"]
            identity = read_csv(root / "inputs/fewsnet_identity_population.csv").rename(columns={"admin_code": "polygon_id"})
        else:
            labels = read_csv(root / "inputs/ipcch_panel.csv", usecols=["admin_code", "year", "month", "phase3_percent", "phase4_percent", "phase5_percent"])
            labels["polygon_id"] = labels.admin_code.str.strip()
            labels["target_month"] = pd.to_datetime(dict(year=labels.year, month=labels.month, day=1)).dt.to_period("M").astype(str)
            labels["truth"] = labels[["phase3_percent", "phase4_percent", "phase5_percent"]].sum(axis=1, min_count=3)
            expected = rows[keycols].merge(labels[["polygon_id", "target_month", "truth"]],
                on=["polygon_id", "target_month"], validate="one_to_one", how="left").truth
            assert expected.notna().all()
            actual_binary = (expected >= .2).astype(int).to_numpy()
            threshold = .2
            identity = read_csv(root / "inputs/ipcch_april_panel.csv")
            identity["ISO3"] = source_iso3(identity)
            identity = identity.rename(columns={"area_id": "polygon_id"})
        np.testing.assert_allclose(rows.actual_value, expected, rtol=0, atol=1e-12)
        assert rows.decision_threshold.eq(threshold).all()
        predicted_binary = (rows.predicted_score.to_numpy() >= threshold).astype(int)
        np.testing.assert_array_equal(rows.predicted_phase3plus, predicted_binary)
        np.testing.assert_array_equal(rows.actual_phase3plus, actual_binary)
        errors = predicted_binary != actual_binary
        np.testing.assert_array_equal(rows.error, errors.astype(int))
        assert set(rows.polygon_id) == set(identity.polygon_id)
        expected_iso = rows.polygon_id.map(identity.set_index("polygon_id").ISO3)
        assert expected_iso.notna().all() and expected_iso.eq(rows.ISO3).all()
        # Rebuild counts using Python dictionaries and Boolean comparisons, independent of export groupby.
        counts = defaultdict(lambda: [0, 0])
        area_country = {}
        for polygon, iso, error in zip(rows.polygon_id, rows.ISO3, errors):
            counts[polygon][0] += 1; counts[polygon][1] += int(error); area_country[polygon] = iso
        areas = read_csv(root / f"{system}/polygon_training_errors.csv")
        assert len(areas) == expected_areas and not areas.polygon_id.duplicated().any()
        assert set(areas.polygon_id) == set(counts)
        country_values = defaultdict(list)
        for area in areas.itertuples():
            n, incorrect = counts[area.polygon_id]
            assert (area.training_sample_count, area.training_error_count, area.ISO3) == (n, incorrect, area_country[area.polygon_id])
            value = Fraction(incorrect, n)
            np.testing.assert_allclose(area.training_error_rate, float(value), rtol=0, atol=1e-15)
            country_values[area.ISO3].append(value)
        exact = {iso: sum(values, Fraction()) / len(values) for iso, values in country_values.items()}
        order = sorted(exact, key=lambda iso: (-exact[iso], iso))
        boundary_countries = [iso for iso in order if exact[iso] == exact[order[quota - 1]]]
        boundary_ties = boundary_countries if len(boundary_countries) > 1 else []
        confidence = read_csv(root / f"{system}/country_training_confidence.csv").set_index("ISO3")
        assert len(confidence) == expected_countries and confidence.index.is_unique and set(confidence.index) == set(order)
        for rank, iso in enumerate(order, 1):
            value = confidence.loc[iso]
            np.testing.assert_allclose(value.country_training_error_rate, float(exact[iso]), rtol=0, atol=1e-15)
            assert value.country_confidence_rank == rank
            assert value.country_confidence_flag == ("low" if rank <= quota else "high")
            assert bool(value.country_error_tied_at_boundary) == (iso in boundary_ties)
            supported = areas.loc[areas.ISO3.eq(iso)]
            assert value.country_training_area_count == len(supported)
            assert value.country_training_sample_count == supported.training_sample_count.sum()
            assert value.country_training_error_count == supported.training_error_count.sum()
            assert value.country_confidence_method == policy["method"]
        country = read_csv(root / f"{system}/country_predictions.csv").set_index("ISO3")
        pd.testing.assert_frame_equal(country[confidence.columns].sort_index(), confidence.sort_index())
        old_country = read_csv(parent / f"{system}/country_predictions.csv").set_index("ISO3")
        renames = {name: name.replace("_aggregation_uncertainty", "_area_dispersion") for name in old_country if name.endswith("_aggregation_uncertainty")}
        if "aggregation_uncertainty_method" in old_country:
            renames["aggregation_uncertainty_method"] = "area_dispersion_method"
        old_country = old_country.rename(columns=renames)
        pd.testing.assert_frame_equal(country[old_country.columns], old_country, check_exact=True)
        assert not any("uncertainty" in col for col in country)
        old_predictions = read_csv(parent / f"{system}/polygon_predictions.csv")
        if system == "ipcch":
            old_predictions = old_predictions.drop(columns=["prediction_uncertainty", "decision_margin", "uncertainty_critical_boundary", "uncertainty_method"])
        pd.testing.assert_frame_equal(read_csv(root / f"{system}/polygon_predictions.csv"), old_predictions, check_exact=True)
        report["models"][system] = {"training_rows": len(rows), "polygons": len(areas), "countries": len(country),
            "total_training_errors": int(errors.sum()), "training_samples_per_area_min": int(areas.training_sample_count.min()),
            "training_samples_per_area_max": int(areas.training_sample_count.max()), "low_count": quota,
            "high_count": expected_countries - quota, "low_countries": order[:quota],
            "boundary_tied_countries": boundary_ties,
            "actual_values_outside_unit_interval": int((~rows.actual_value.between(0, 1)).sum()),
            "predicted_scores_outside_unit_interval": int((~rows.predicted_score.between(0, 1)).sum()),
            "retained_predictions_country_values_models_unchanged": True}
        summaries[system] = json.loads((root / f"reports/{system}_confidence_summary.json").read_text())
    write_json(root / "reports/training_confidence_summary.json", summaries)
    write_json(root / "reports/training_confidence_verification.json", report)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    verify(parser.parse_args().root)
