"""Independent verification of country confidence v3 (separate arithmetic from the builder)."""
import argparse
import json
import math
import random
import sys
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.run_h5_model_delivery import read_csv, TARGETS
from tools.refresh_h5_inputs import sha256, write_json


def flag(value):
    # Decimal-string cutoffs, independent of the builder's Fraction constants.
    if value is None:
        return None
    return "high" if value <= Fraction("0.1") else "medium" if value <= Fraction("0.2") else "low"


def phase(scores):
    """Loop decoder: activate >=0.2, propagate higher boundaries downward, highest active phase."""
    active = [s >= 0.2 for s in scores]
    for k in range(len(active) - 2, -1, -1):
        active[k] = active[k] or active[k + 1]
    top = [k + 2 for k, a in enumerate(active) if a]
    return max(top) if top else 1


def blank(value):
    return value is None or (isinstance(value, float) and math.isnan(value)) or value is pd.NA


def country_errors(areas):
    """areas rows: (polygon_id, iso, n, k, population). Returns exact country rates."""
    num, den = defaultdict(Fraction), defaultdict(Fraction)
    counts = defaultdict(lambda: defaultdict(int))
    for polygon, iso, n, k, pop in areas:
        counts[iso]["area"] += 1
        if blank(n) or n == 0 or blank(pop) or pop <= 0:
            counts[iso]["excluded"] += 1
            continue
        counts[iso]["eligible"] += 1
        counts[iso]["samples"] += int(n); counts[iso]["mistakes"] += int(k)
        num[iso] += Fraction(pop) * Fraction(int(k), int(n)); den[iso] += Fraction(pop)
    return {iso: (num[iso] / den[iso] if den[iso] else None) for iso in counts}, counts


def check_country(system, table, exact, counts):
    table = table.set_index("ISO3")
    assert set(table.index) == set(exact), system
    for iso, value in exact.items():
        row = table.loc[iso]
        if value is None:
            assert blank(row.country_error_rate) and blank(row.country_confidence_flag), iso
        else:
            np.testing.assert_allclose(row.country_error_rate, float(value), rtol=0, atol=1e-15)
            assert row.country_confidence_flag == flag(value), iso
        assert row.country_error_eligible_area_count == counts[iso]["eligible"]
        assert row.country_error_excluded_area_count == counts[iso]["excluded"]
        assert row.country_error_sample_count == counts[iso]["samples"]
        assert row.country_error_mistake_count == counts[iso]["mistakes"]
    return {"countries": len(exact), "flags": {f: sum(flag(v) == f for v in exact.values()) for f in ["high", "medium", "low"]},
            "null_flags": sum(v is None for v in exact.values()),
            "low_countries": sorted(i for i, v in exact.items() if flag(v) == "low")}


def verify(root):
    policy = json.loads((root / "reports/country_confidence_v3_policy.json").read_text())
    parent = Path(policy["parent_directory"])
    assert sha256(parent / "manifest.json") == policy["parent_manifest_sha256"]
    parent_manifest = json.loads((parent / "manifest.json").read_text())
    unchanged = 0
    for item in parent_manifest["files"]:
        relative = item["path"]
        assert sha256(parent / relative) == item["sha256"], relative
        if ("/model_package/" in relative or relative.startswith(("inputs/", "sources/")) or relative.endswith((
                "polygons.geojson", "polygon_model_mapping.csv", "country_population_reference.csv", "polygon_predictions.csv"))
                or relative in {"ipcch/polygon_training_errors.csv", "reports/ipcch_training_predictions.csv",
                                "reports/ipcch_training_keys.csv", "reports/fewsnet_training_keys.csv"}):
            assert sha256(root / relative) == item["sha256"], relative
            unchanged += 1
        if relative in policy["moved_parent_v2_artifacts"]:
            assert not (root / relative).exists(), relative
            assert sha256(root / policy["moved_parent_v2_artifacts"][relative]) == item["sha256"], relative
    report = {"status": "passed", "tests": "independent recomputation; no regression suite",
              "parent_files_verified": len(parent_manifest["files"]), "protected_files_unchanged": unchanged, "models": {}}

    # FEWSNET: recompute from the original historical CSV, not the exported error table.
    source = Path(policy["fewsnet"]["historical_source"])
    assert sha256(source) == policy["fewsnet"]["historical_source_sha256"]
    assert sha256(root / "reports/fewsnet_stage3_source/predictions_monthly.csv") == policy["fewsnet"]["historical_source_sha256"]
    hist = pd.read_csv(source, dtype={"FEWSNET_admin_code": str})
    per = defaultdict(lambda: [0, 0])
    for code, truth, pred in zip(hist.FEWSNET_admin_code, hist.y_true, hist.y_pred_partitioned):
        per[code][0] += 1; per[code][1] += int(truth != pred)
    identity = read_csv(root / "inputs/fewsnet_identity_population.csv")
    polygons = read_csv(root / "fewsnet/polygon_confidence.csv").set_index("polygon_id")
    assert len(polygons) == len(identity) == 5718 and set(polygons.index) == set(identity.admin_code)
    assert set(per) <= set(identity.admin_code)
    for code, row in polygons.iterrows():
        if code in per:
            n, k = per[code]
            assert (row.historical_sample_count, row.historical_error_count) == (n, k), code
            np.testing.assert_allclose([row.polygon_error_rate, row.polygon_confidence], [k / n, 1 - k / n], rtol=0, atol=1e-15)
        else:
            assert blank(row.polygon_error_rate) and blank(row.polygon_confidence) and blank(row.historical_sample_count), code
    exported = read_csv(root / "reports/fewsnet_stage3_historical_errors.csv")
    assert len(exported) == len(hist) and exported.error.sum() == sum(v[1] for v in per.values())
    exact, counts = country_errors([(r.admin_code, r.ISO3, per.get(r.admin_code, [None])[0],
        per.get(r.admin_code, [None, None])[1], None if pd.isna(r.population) else float(r.population))
        for r in identity.itertuples()])
    confidence = read_csv(root / "fewsnet/country_confidence.csv")
    summary = check_country("fewsnet", confidence, exact, counts)
    country = read_csv(root / "fewsnet/country_predictions.csv").set_index("ISO3")
    for iso, row in country.iterrows():
        expected = None if pd.isna(row.probability_crisis) else int(row.probability_crisis >= 0.5)
        assert (blank(row.country_outcome_crisis) and expected is None) or row.country_outcome_crisis == expected, iso
    summary["country_outcome_crisis_positive"] = int(country.country_outcome_crisis.sum())
    summary["historical_rows"], summary["historical_errors"] = len(hist), int(exported.error.sum())
    report["models"]["fewsnet"] = summary

    # IPCCH: Phase3+ country error from saved v2 row-level predictions (recount), population_estimate weights.
    rows = read_csv(root / "reports/ipcch_training_predictions.csv")
    per = defaultdict(lambda: [0, 0])
    for polygon, pred, actual in zip(rows.polygon_id, rows.predicted_score, rows.actual_value):
        per[polygon][0] += 1; per[polygon][1] += int((pred >= .2) != (actual >= .2))
    predictions = read_csv(root / "ipcch/polygon_predictions.csv")
    confidence = read_csv(root / "ipcch/country_confidence.csv")
    april = read_csv(root / "inputs/ipcch_april_panel.csv")
    reference = read_csv(root / "ipcch/country_population_reference.csv")
    iso_of = dict(zip(april.area_id, april.country.map(dict(zip(reference.country, reference.ISO3)))))
    assert all(isinstance(v, str) for v in iso_of.values())
    exact, counts = country_errors([(r.polygon_id, iso_of[r.polygon_id], per.get(r.polygon_id, [None])[0],
        per.get(r.polygon_id, [None, None])[1], float(r.population_estimate)) for r in predictions.itertuples()])
    summary = check_country("ipcch", confidence, exact, counts)
    country = read_csv(root / "ipcch/country_predictions.csv").set_index("ISO3")
    forecast_max = defaultdict(int)
    roster = defaultdict(set)
    for r in predictions.itertuples():
        assert r.overall_phase_pred == phase([getattr(r, f"{t}_score") for t in TARGETS])
        forecast_max[iso_of[r.polygon_id]] = max(forecast_max[iso_of[r.polygon_id]], r.overall_phase_pred)
        roster[iso_of[r.polygon_id]].add(r.polygon_id)
    for iso, row in country.iterrows():
        assert row.country_overall_phase == phase([row[f"{t}_score"] for t in TARGETS]), iso
        assert row.country_maximum_phase == forecast_max[iso], iso
    # Residual scenarios recomputed from the replay table; replay phase3 must equal the saved v2 predictions.
    replay = read_csv(root / "reports/ipcch_four_target_training_replay.csv")
    joined = replay.merge(rows, on=["polygon_id", "feature_month", "target_month"], validate="one_to_one")
    assert len(joined) == len(rows) == len(replay)
    np.testing.assert_array_equal(joined.phase3_worse_predicted.astype(np.float32), joined.predicted_score.astype(np.float32))
    np.testing.assert_allclose(joined.phase3_worse_actual, joined.actual_value, rtol=0, atol=1e-12)
    for t in TARGETS:
        np.testing.assert_allclose(replay[f"{t}_residual"], replay[f"{t}_actual"] - replay[f"{t}_predicted"], rtol=0, atol=0)
    actual_phase = [phase(v) for v in replay[[f"{t}_actual" for t in TARGETS]].itertuples(index=False)]
    assert list(replay.actual_overall_phase) == actual_phase
    sept = {r.polygon_id: [getattr(r, f"{t}_score") for t in TARGETS] for r in predictions.itertuples()}
    fields = defaultdict(dict)
    for r in replay.itertuples():
        fields[(iso_of[r.polygon_id], r.target_month)][r.polygon_id] = [getattr(r, f"{t}_residual") for t in TARGETS]
    mismatch = defaultdict(list)
    for (iso, month), field in sorted(fields.items()):
        if set(field) != roster[iso]:
            continue
        simulated = max(phase([s + e for s, e in zip(sept[p], field[p])]) for p in roster[iso])
        mismatch[iso].append(int(simulated != forecast_max[iso]))
    scenarios = read_csv(root / "reports/ipcch_maximum_phase_scenarios.csv")
    assert len(scenarios) == sum(len(v) for v in mismatch.values())
    table = confidence.set_index("ISO3")
    status_counts = defaultdict(int)
    for iso in sorted(roster):
        x = mismatch.get(iso, [])
        row = table.loc[iso]
        assert row.country_maximum_phase_history_month_count == len(x), iso
        if not x:
            assert blank(row.country_maximum_phase_error_probability_proxy) and row.country_maximum_phase_uncertainty_status == "no_complete_history"
        else:
            assert row.country_maximum_phase_error_probability_proxy == sum(x) / len(x), iso
        if len(x) <= 1:
            assert blank(row.country_maximum_phase_error_probability_ci_lower) and blank(row.country_maximum_phase_error_probability_ci_upper)
            if x:
                assert row.country_maximum_phase_uncertainty_status == "single_month"
        else:
            assert row.country_maximum_phase_uncertainty_status == ("degenerate_empirical" if len(set(x)) == 1 else "supported")
            lo, hi = row.country_maximum_phase_error_probability_ci_lower, row.country_maximum_phase_error_probability_ci_upper
            assert 0 <= lo <= hi <= 1, iso
            if len(set(x)) == 1:
                assert lo == hi == x[0]
            else:
                # Independent stdlib bootstrap: interval must agree with a different RNG within Monte Carlo error.
                rnd = random.Random(1)
                means = sorted(sum(rnd.choice(x) for _ in x) / len(x) for _ in range(4000))
                assert abs(means[int(.025 * 3999)] - lo) <= .15 and abs(means[int(.975 * 3999)] - hi) <= .15, iso
        status_counts[row.country_maximum_phase_uncertainty_status] += 1
    # Reproducibility: rerun builder bootstrap with recorded seed.
    from tools.revise_h5_country_v3 import maximum_phase_uncertainty
    rerun = maximum_phase_uncertainty({iso: mismatch.get(iso, []) for iso in roster},
                                      np.random.Generator(np.random.PCG64(policy["ipcch"]["maximum_phase_uncertainty"]["bootstrap"]["seed"]))).set_index("ISO3")
    for col in rerun:
        pd.testing.assert_series_equal(rerun[col].sort_index(), table[col].sort_index(), check_dtype=False, check_names=False)
    summary.update({"country_overall_phase": {int(k): int(v) for k, v in country.country_overall_phase.value_counts().sort_index().items()},
        "country_maximum_phase": {int(k): int(v) for k, v in country.country_maximum_phase.value_counts().sort_index().items()},
        "complete_country_months": len(scenarios), "uncertainty_status": dict(status_counts),
        "one_area_countries": sorted(i for i, r in roster.items() if len(r) == 1),
        "bootstrap_reproduced_from_recorded_seed": True})
    report["models"]["ipcch"] = summary
    # Formal country tables must not keep v2 quota columns or conflict with standalone diagnostics.
    for system in ["fewsnet", "ipcch"]:
        country = read_csv(root / f"{system}/country_predictions.csv").set_index("ISO3")
        stale = {"country_training_error_rate", "country_confidence_rank", "country_error_tied_at_boundary", "country_confidence_method"}
        assert not stale.intersection(country.columns), system
        diag = read_csv(root / f"{system}/country_confidence.csv").set_index("ISO3")
        pd.testing.assert_frame_equal(country[diag.columns].sort_index(), diag.sort_index())
        old = read_csv(parent / f"{system}/country_predictions.csv").set_index("ISO3")
        from tools.revise_h5_country_v3 import V2_COUNTRY_COLUMNS
        kept = [c for c in old.columns if c not in V2_COUNTRY_COLUMNS]
        pd.testing.assert_frame_equal(country[kept].sort_index(), old[kept].sort_index(), check_exact=True)
    write_json(root / "reports/country_confidence_v3_verification.json", report)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    verify(parser.parse_args().root)
