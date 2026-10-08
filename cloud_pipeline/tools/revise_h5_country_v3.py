"""Shared country statistics; manual September construction stays in the legacy archive."""
from __future__ import annotations
from fractions import Fraction
import numpy as np
import pandas as pd
TARGETS = ["phase2_worse", "phase3_worse", "phase4_worse", "phase5_worse"]
HIGH, MEDIUM = Fraction(1, 10), Fraction(1, 5)
PHASE_THRESHOLD, CRISIS_THRESHOLD = 0.2, 0.5
SEED, REPLICATES, PERCENTILES = 20260923, 10000, (2.5, 97.5)
BASIS = {"fewsnet": "h5_validation_error_proxy_stage3_2021_2024", "ipcch": "training_resubstitution"}
WEIGHTING = "population_weighted_mean_of_area_error_rates"
V2_COUNTRY_COLUMNS = ["country_training_error_rate", "country_training_area_count", "country_training_sample_count",
    "country_training_error_count", "country_confidence_method", "country_confidence_rank",
    "country_confidence_flag", "country_error_tied_at_boundary"]


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
