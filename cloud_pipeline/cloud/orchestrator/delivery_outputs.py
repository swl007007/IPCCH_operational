"""September-compatible per-scope output tables for the October delivery (CP3).

Reuses the September composition exactly: country tables are the existing
aggregators (``aggregate_country_probabilities`` / ``aggregate_country_scores``)
followed by ``append_country_v3``; forecast-derived country fields come from
``forecast_country_fields`` on the current scores. Historical error diagnostics for
a model/horizon without accepted evidence are blank (never zero, never an h5 proxy)
and explained in ``reports/diagnostic_availability.csv``. Column order is frozen to
the September v3 headers below; every table is written create-only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from tools.build_fewsnet_country_level_predictions import aggregate_country_probabilities
from tools.build_ipcch_country_level_predictions import aggregate_country_scores
from tools.revise_h5_country_v3 import (
    CRISIS_THRESHOLD,
    SEED,
    append_country_v3,
    decode_cumulative_phase,
    forecast_country_fields,
    maximum_phase_uncertainty,
    weighted_country_errors,
)

AVAILABILITY_COLUMNS = ["model_system", "horizon_months", "level", "entity_id", "diagnostic_family", "status",
                        "reason", "evidence_ref"]
IPCCH_PHASE_METHOD = "population-weighted raw cumulative scores; >=0.2 cascade; highest active boundary"
DIAGNOSTIC_FAMILIES = {
    "fewsnet": {"polygon_confidence": "polygon", "country_confidence": "country"},
    "ipcch": {"polygon_training_errors": "polygon", "country_confidence": "country", "maximum_phase": "country"},
}

SEPTEMBER_HEADERS = {
    "fewsnet": {
        "polygon_predictions": (
            "admin_code", "ADMIN0", "ADMIN1", "ADMIN2", "ADMIN3", "ISO3", "lat", "lon", "population",
            "population_reference_period", "population_source", "probability_crisis", "predicted_crisis",
            "threshold", "cluster_id", "prediction_source", "feature_month", "target_month",
            "horizon_months", "suite_version", "model_artifact_path", "source_input",
        ),
        "country_predictions": (
            "ISO3", "country_code", "country", "country_en", "referenced_population",
            "population_reference_year", "population_reference_date", "population_measure",
            "population_source", "population_vintage", "population_source_url", "census_genc_codes",
            "feature_month", "target_month", "horizon_months", "probability_crisis",
            "probability_crisis_area_dispersion", "area_count", "finite_population_area_count",
            "positive_population_area_count", "zero_population_area_count", "missing_population_area_count",
            "area_population_weight_sum", "area_classification_threshold", "score_aggregation_method",
            "area_dispersion_method", "aggregation_weight_field", "suite_version", "model_artifact_path",
            "source_input", "country_error_rate", "country_confidence_flag", "country_error_basis",
            "country_error_weighting", "country_error_evidence_period", "country_confidence_thresholds",
            "country_error_eligible_area_count", "country_error_excluded_area_count",
            "country_error_missing_evidence_area_count", "country_error_missing_population_area_count",
            "country_error_nonpositive_population_area_count", "country_error_sample_count",
            "country_error_mistake_count", "country_error_eligible_population_sum",
            "country_error_known_population_sum", "country_error_known_population_coverage",
            "country_error_population_field", "country_error_population_vintage",
            "country_error_population_source", "country_outcome_crisis", "country_outcome_crisis_threshold",
        ),
        "polygon_model_mapping": (
            "polygon_id", "admin_code", "cluster_id", "prediction_source", "suite_version", "actual_model",
            "fallback_reason", "model_system", "model_package", "feature_month", "target_month",
            "horizon_months",
        ),
        "polygon_confidence": (
            "polygon_id", "ISO3", "population", "population_reference_period", "population_source",
            "historical_sample_count", "historical_error_count", "polygon_error_rate", "polygon_confidence",
            "country_error_eligible", "evidence_basis", "evidence_period",
        ),
        "country_confidence": (
            "ISO3", "country_error_rate", "country_confidence_flag", "country_error_basis",
            "country_error_weighting", "country_error_evidence_period", "country_confidence_thresholds",
            "country_error_eligible_area_count", "country_error_excluded_area_count",
            "country_error_missing_evidence_area_count", "country_error_missing_population_area_count",
            "country_error_nonpositive_population_area_count", "country_error_sample_count",
            "country_error_mistake_count", "country_error_eligible_population_sum",
            "country_error_known_population_sum", "country_error_known_population_coverage",
            "country_error_population_field", "country_error_population_vintage",
            "country_error_population_source", "country_outcome_crisis", "country_outcome_crisis_threshold",
        ),
        "country_population_reference": (
            "ISO3", "country", "country_en", "referenced_population", "population_reference_year",
            "population_reference_date", "population_measure", "population_source", "population_vintage",
            "population_source_url", "census_genc_codes",
        ),
    },
    "ipcch": {
        "polygon_predictions": (
            "polygon_id", "area_id", "admin_code", "_row_id", "population_estimate",
            "population_reference_period", "population_imputation_method", "phase2_worse_score",
            "phase2_worse_pred", "phase3_worse_score", "phase3_worse_pred", "phase4_worse_score",
            "phase4_worse_pred", "phase5_worse_score", "phase5_worse_pred", "overall_phase_pred",
            "feature_period", "target_period", "scope_months", "model_package_id", "source_input",
        ),
        "country_predictions": (
            "ISO3", "country", "country_en", "referenced_population", "population_reference_year",
            "population_reference_date", "population_measure", "population_source", "population_vintage",
            "population_source_url", "census_genc_codes", "feature_period", "target_period", "scope_months",
            "area_count", "positive_weight_area_count", "phase2_worse_score",
            "phase2_worse_score_area_dispersion", "phase3_worse_score", "phase3_worse_score_area_dispersion",
            "phase4_worse_score", "phase4_worse_score_area_dispersion", "phase5_worse_score",
            "phase5_worse_score_area_dispersion", "score_aggregation_method", "area_dispersion_method",
            "aggregation_weight_field", "model_package_id", "source_input", "country_error_rate",
            "country_confidence_flag", "country_error_basis", "country_error_weighting",
            "country_error_evidence_period", "country_confidence_thresholds",
            "country_error_eligible_area_count", "country_error_excluded_area_count",
            "country_error_missing_evidence_area_count", "country_error_missing_population_area_count",
            "country_error_nonpositive_population_area_count", "country_error_sample_count",
            "country_error_mistake_count", "country_error_eligible_population_sum",
            "country_error_known_population_sum", "country_error_known_population_coverage",
            "country_error_population_field", "country_error_population_vintage",
            "country_error_population_source", "country_overall_phase", "country_overall_phase_availability",
            "country_overall_phase_method", "country_maximum_phase",
            "country_maximum_phase_error_probability_proxy",
            "country_maximum_phase_error_probability_ci_lower",
            "country_maximum_phase_error_probability_ci_upper", "country_maximum_phase_history_month_count",
            "country_maximum_phase_uncertainty_status", "country_maximum_phase_uncertainty_method",
        ),
        "polygon_model_mapping": (
            "polygon_id", "area_id", "admin_code", "model_package_id", "cluster_id", "actual_model",
            "fallback_reason", "model_system", "model_package", "feature_month", "target_month",
            "horizon_months",
        ),
        "polygon_training_errors": (
            "polygon_id", "ISO3", "training_sample_count", "training_error_count", "training_error_rate",
        ),
        "country_confidence": (
            "ISO3", "country_error_rate", "country_confidence_flag", "country_error_basis",
            "country_error_weighting", "country_error_evidence_period", "country_confidence_thresholds",
            "country_error_eligible_area_count", "country_error_excluded_area_count",
            "country_error_missing_evidence_area_count", "country_error_missing_population_area_count",
            "country_error_nonpositive_population_area_count", "country_error_sample_count",
            "country_error_mistake_count", "country_error_eligible_population_sum",
            "country_error_known_population_sum", "country_error_known_population_coverage",
            "country_error_population_field", "country_error_population_vintage",
            "country_error_population_source", "country_overall_phase", "country_overall_phase_availability",
            "country_overall_phase_method", "country_maximum_phase",
            "country_maximum_phase_error_probability_proxy",
            "country_maximum_phase_error_probability_ci_lower",
            "country_maximum_phase_error_probability_ci_upper", "country_maximum_phase_history_month_count",
            "country_maximum_phase_uncertainty_status", "country_maximum_phase_uncertainty_method",
        ),
        "country_population_reference": (
            "ISO3", "country", "country_en", "referenced_population", "population_reference_year",
            "population_reference_date", "population_measure", "population_source", "population_vintage",
            "population_source_url", "census_genc_codes",
        ),
    },
}


class OutputSchemaError(ValueError):
    """A table does not match its frozen September column contract."""


class EvidenceIntegrityError(ValueError):
    """Supplied diagnostic evidence is malformed or belongs to another model/horizon.

    Never converted into an "unavailable" diagnostic: the run fails.
    """


# Self-describing evidence: every row carries the identity it was computed for, so foreign
# evidence is detected from its own bytes, not only from the manifest declaration.
EVIDENCE_IDENTITY = ("model_package_id", "horizon_months", "basis", "period")
AREA_EVIDENCE_COLUMNS = ("polygon_id", "sample_count", "error_count")
PHASE_TARGETS = ("phase2_worse", "phase3_worse", "phase4_worse", "phase5_worse")
RESIDUAL_COLUMNS = tuple(f"{target}_residual" for target in PHASE_TARGETS)
MAXIMUM_PHASE_METHOD = "training_residual_transfer_complete_month_bootstrap_proxy"
# Accepted evidence semantics per system (design section 7). FEWSNET evidence must come from the
# package's own recorded validation split; IPCCH evidence is training resubstitution of that
# package. Anything else (e.g. the h5 basis relabelled for 0/6/12) is rejected unless it is exactly an
# APPROVED_PROXY_EVIDENCE pair.
EVIDENCE_BASIS = {"fewsnet": "package_validation_split", "ipcch": "training_resubstitution"}
# Explicitly approved FEWSNET proxies (user decisions 2026-10-09): saved Stage3 research-run errors, not
# the delivered package's own validation. 6m/12m use the 8-/12-month-lag runs; 0m uses the 4-month-lag
# run (the accepted h5 evidence), which is more pessimistic than true 0m error. Only these exact
# (horizon -> basis, period) pairs are accepted; the basis string discloses the proxy in every output.
APPROVED_PROXY_EVIDENCE = {
    ("fewsnet", 0): ("h0_validation_error_proxy_stage3_fs1_lag4_2021_2024", "2021-02..2024-10"),
    ("fewsnet", 6): ("h6_validation_error_proxy_stage3_fs2_lag8_2021_2024", "2021-02..2024-10"),
    ("fewsnet", 12): ("h12_validation_error_proxy_stage3_fs3_lag12_2021_2024", "2021-02..2024-10"),
}
_PERIOD = re.compile(r"^(\d{4}-(?:0[1-9]|1[0-2]))\.\.(\d{4}-(?:0[1-9]|1[0-2]))$")


def ipcch_training_cutoff_month(package_root) -> str:
    """Month of the IPCCH package's recorded ``training_cutoff``: resubstitution evidence cannot end later."""
    cutoff = json.loads((Path(package_root) / "model_package_manifest.json").read_text())["training_cutoff"]
    return str(pd.Period(cutoff[:7], "M"))


def fewsnet_validation_period(package_dir) -> str:
    """``start..end`` of the package's recorded validation target months (training_report.json)."""
    window = json.loads((Path(package_dir) / "training_report.json").read_text())["validation_target_month_range"]
    return f"{window['start']}..{window['end']}"
MAXIMUM_PHASE_FIELDS = ("country_maximum_phase_error_probability_proxy", "country_maximum_phase_error_probability_ci_lower",
                        "country_maximum_phase_error_probability_ci_upper", "country_maximum_phase_history_month_count",
                        "country_maximum_phase_uncertainty_status", "country_maximum_phase_uncertainty_method")


def _evidence_identity(frame: pd.DataFrame, *, model_package_id: str, horizon: int, declared: dict,
                       acceptance: dict) -> dict:
    """The evidence's own (constant) identity must equal the scored package/horizon and the manifest,
    and its basis/period must be the accepted semantics for the system (``acceptance``:
    ``system``, ``origin``; FEWSNET: the package's recorded validation ``period``; IPCCH: the
    package's ``training_cutoff`` month as ``latest_end``), or exactly an ``APPROVED_PROXY_EVIDENCE``
    pair for this system/horizon."""
    missing = [column for column in EVIDENCE_IDENTITY if column not in frame]
    if missing:
        raise EvidenceIntegrityError(f"evidence lacks identity columns {missing}")
    identity = {}
    for column in EVIDENCE_IDENTITY:
        values = frame[column].astype(str).str.strip().unique()
        if len(values) != 1 or values[0] in ("", "nan", "<NA>"):
            raise EvidenceIntegrityError(f"evidence {column} must be one non-blank value")
        identity[column] = values[0]
    if not identity["horizon_months"].isdigit():
        raise EvidenceIntegrityError("evidence horizon_months must be an integer")
    identity["horizon_months"] = int(identity["horizon_months"])
    actual = (identity["model_package_id"], identity["horizon_months"])
    if actual != (model_package_id, horizon) or actual != (declared.get("evidence_model_package_id"),
                                                           declared.get("evidence_horizon_months")):
        raise EvidenceIntegrityError(f"evidence belongs to {actual[0]}/{actual[1]}, not {model_package_id}/{horizon} "
                                     f"(declared {declared.get('evidence_model_package_id')}/"
                                     f"{declared.get('evidence_horizon_months')})")
    system = acceptance["system"]
    proxy = APPROVED_PROXY_EVIDENCE.get((system, horizon))
    approved_proxy = proxy is not None and identity["basis"] == proxy[0]
    if approved_proxy and identity["period"] != proxy[1]:
        raise EvidenceIntegrityError(f"approved {system}/{horizon}m proxy period {identity['period']!r} is not "
                                     f"the allowlisted {proxy[1]!r}")
    if not approved_proxy and identity["basis"] != EVIDENCE_BASIS[system]:
        allowed = f" or the approved {horizon}m proxy {proxy[0]!r}" if proxy else ""
        raise EvidenceIntegrityError(f"evidence basis {identity['basis']!r} is not the accepted {system} basis "
                                     f"{EVIDENCE_BASIS[system]!r}{allowed}")
    match = _PERIOD.fullmatch(identity["period"])
    if match is None or match.group(1) > match.group(2) or match.group(2) > acceptance["origin"]:
        raise EvidenceIntegrityError(f"evidence period {identity['period']!r} must be YYYY-MM..YYYY-MM ending at or "
                                     f"before {acceptance['origin']}")
    if system == "ipcch" and (not acceptance.get("latest_end") or match.group(2) > acceptance["latest_end"]):
        raise EvidenceIntegrityError(f"IPCCH training-resubstitution period {identity['period']!r} must end at or "
                                     f"before the package training cutoff {acceptance.get('latest_end')!r}")
    if system == "fewsnet" and not approved_proxy and identity["period"] != acceptance.get("period"):
        raise EvidenceIntegrityError(f"FEWSNET evidence period {identity['period']!r} is not the package's recorded "
                                     f"validation split {acceptance.get('period')!r}")
    return identity


def _roster_ids(frame: pd.DataFrame, roster, key) -> pd.DataFrame:
    table = frame.copy()
    table["polygon_id"] = table["polygon_id"].astype(str)
    if table.duplicated(key).any() or not table["polygon_id"].isin(set(map(str, roster))).all():
        raise EvidenceIntegrityError(f"evidence {key} must be unique and polygon IDs must be roster IDs")
    return table


def area_evidence(frame: pd.DataFrame, *, roster, model_package_id: str, horizon: int,
                  declared: dict, acceptance: dict) -> tuple[pd.DataFrame, dict]:
    """Validated per-polygon error counts + their identity (basis/period come from the evidence)."""
    identity = _evidence_identity(frame, model_package_id=model_package_id, horizon=horizon, declared=declared,
                                  acceptance=acceptance)
    missing = [column for column in AREA_EVIDENCE_COLUMNS if column not in frame]
    if missing:
        raise EvidenceIntegrityError(f"evidence lacks columns {missing}")
    table = _roster_ids(frame[list(AREA_EVIDENCE_COLUMNS)], roster, ["polygon_id"])
    for column in ("sample_count", "error_count"):
        values = pd.to_numeric(table[column], errors="coerce")
        if values.isna().any() or (values % 1 != 0).any() or (values < 0).any():
            raise EvidenceIntegrityError(f"evidence {column} must be non-negative integers")
        table[column] = values.astype("int64")
    if (table["error_count"] > table["sample_count"]).any():
        raise EvidenceIntegrityError("evidence error_count exceeds sample_count")
    return table, identity


def residual_evidence(frame: pd.DataFrame, *, roster, model_package_id: str, horizon: int,
                      declared: dict, acceptance: dict) -> tuple[pd.DataFrame, dict]:
    """Validated joint residual fields (actual cumulative share - replayed saved-model score)
    per polygon/target month for the matching package and horizon."""
    identity = _evidence_identity(frame, model_package_id=model_package_id, horizon=horizon, declared=declared,
                                  acceptance=acceptance)
    missing = [column for column in ("polygon_id", "target_month", *RESIDUAL_COLUMNS) if column not in frame]
    if missing:
        raise EvidenceIntegrityError(f"residual evidence lacks columns {missing}")
    table = _roster_ids(frame[["polygon_id", "target_month", *RESIDUAL_COLUMNS]], roster, ["polygon_id", "target_month"])
    table["target_month"] = table["target_month"].astype(str)
    if not table["target_month"].str.fullmatch(r"\d{4}-(0[1-9]|1[0-2])").all():
        raise EvidenceIntegrityError("residual evidence target_month must be YYYY-MM")
    start, end = identity["period"].split("..")
    if not table["target_month"].between(start, end).all():
        raise EvidenceIntegrityError(f"residual target months must lie inside the evidence period {identity['period']}")
    values = table[list(RESIDUAL_COLUMNS)].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise EvidenceIntegrityError("residual evidence values must be finite numbers")
    table[list(RESIDUAL_COLUMNS)] = values
    return table, identity


def maximum_phase_diagnostics(predictions: pd.DataFrame, residuals: pd.DataFrame, iso_by_polygon: pd.Series,
                              countries) -> pd.DataFrame:
    """v3 residual transfer at the current scores: per country, each complete historical month's
    whole residual field is added to the current raw scores, decoded with the >=0.2 cascade and
    its maximum compared with the forecast maximum; whole-month bootstrap (PCG64 seed, 10,000
    replicates, linear 2.5/97.5), restarted for every scope. A proxy, not calibrated uncertainty."""
    current = predictions.assign(polygon_id=predictions["polygon_id"].astype(str))
    current["ISO3"] = current["polygon_id"].map(iso_by_polygon)
    scores = current.set_index("polygon_id")[[f"{t}_score" for t in PHASE_TARGETS]].astype(float)
    forecast_max = current.groupby("ISO3")["overall_phase_pred"].max()
    roster = current.groupby("ISO3")["polygon_id"].apply(sorted)
    fields = residuals.assign(ISO3=residuals["polygon_id"].map(current.set_index("polygon_id")["ISO3"]))
    mismatch = {}
    for code in sorted(countries):
        ids = roster.get(code, [])
        values = []
        if ids:
            group = fields.loc[fields["ISO3"].eq(code)]
            counts = group.groupby("target_month")["polygon_id"].nunique()
            base = scores.loc[ids].to_numpy()
            for month in sorted(counts.index[counts.eq(len(ids))]):  # complete months only
                field = group.loc[group["target_month"].eq(month)].set_index("polygon_id").loc[ids, list(RESIDUAL_COLUMNS)]
                simulated = decode_cumulative_phase(base + field.to_numpy())
                values.append(int(simulated.max() != forecast_max[code]))
        mismatch[code] = values
    out = maximum_phase_uncertainty(mismatch, np.random.Generator(np.random.PCG64(SEED)))
    out["country_maximum_phase_uncertainty_method"] = MAXIMUM_PHASE_METHOD
    return out[["ISO3", *MAXIMUM_PHASE_FIELDS]]


def supported_diagnostics(system: str, predictions: pd.DataFrame, evidence: pd.DataFrame, *, identity: dict,
                          iso_by_polygon: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(polygon diagnostic table, country error fields) from validated evidence (v3 arithmetic)."""
    if system == "fewsnet":
        areas = pd.DataFrame({"polygon_id": predictions["admin_code"].astype(str), "ISO3": predictions["ISO3"],
                              "population": predictions["population"],
                              "population_reference_period": predictions["population_reference_period"],
                              "population_source": predictions["population_source"]})
        field = "population"
    else:
        areas = pd.DataFrame({"polygon_id": predictions["polygon_id"].astype(str),
                              "population": predictions["population_estimate"],
                              "population_reference_period": predictions["population_reference_period"],
                              "population_source": predictions["population_imputation_method"]})
        areas["ISO3"] = areas["polygon_id"].map(iso_by_polygon)
        field = "population_estimate"
    areas = areas.merge(evidence, on="polygon_id", how="left", validate="one_to_one")  # no zero fill
    countries = weighted_country_errors(areas, system, identity["period"], field)
    countries["country_error_basis"] = identity["basis"]  # the evidence's own basis, never the h5 label
    if system == "fewsnet":
        polygons = areas.rename(columns={"sample_count": "historical_sample_count", "error_count": "historical_error_count"})
        polygons["polygon_error_rate"] = polygons["historical_error_count"] / polygons["historical_sample_count"]
        polygons["polygon_confidence"] = 1 - polygons["polygon_error_rate"]
        pop = polygons["population"]
        polygons["country_error_eligible"] = polygons["polygon_error_rate"].notna() & pop.notna() & (pop > 0)
        polygons["evidence_basis"], polygons["evidence_period"] = identity["basis"], identity["period"]
        for column in ("historical_sample_count", "historical_error_count"):
            polygons[column] = polygons[column].astype("Int64")
        name = "polygon_confidence"
    else:
        polygons = areas.rename(columns={"sample_count": "training_sample_count", "error_count": "training_error_count"})
        polygons["training_error_rate"] = polygons["training_error_count"] / polygons["training_sample_count"]
        for column in ("training_sample_count", "training_error_count"):
            polygons[column] = polygons[column].astype("Int64")
        name = "polygon_training_errors"
    return polygons[list(SEPTEMBER_HEADERS[system][name])], countries


def polygon_mapping(system: str, predictions: pd.DataFrame, *, origin: str, target: str, horizon: int,
                    package_path: str, ipcch_models: str = "phase2_worse,phase3_worse,phase4_worse,phase5_worse") -> pd.DataFrame:
    if system == "fewsnet":
        mapping = predictions[["admin_code", "cluster_id", "prediction_source", "suite_version"]].copy()
        mapping.insert(0, "polygon_id", mapping["admin_code"].astype(str))
        mapping["actual_model"] = [f"partition_models[{int(c)}]" if s == "partition_model" else "pooled_model"
                                   for c, s in zip(mapping["cluster_id"], mapping["prediction_source"])]
        mapping["fallback_reason"] = mapping["prediction_source"].where(mapping["prediction_source"].ne("partition_model"), "")
    else:
        mapping = predictions[["polygon_id", "area_id", "admin_code", "model_package_id"]].copy()
        mapping["cluster_id"] = pd.NA
        mapping["actual_model"] = f"scope_{horizon}m:{ipcch_models}"
        mapping["fallback_reason"] = ""
    mapping["model_system"] = system
    mapping["model_package"] = package_path
    mapping["feature_month"], mapping["target_month"], mapping["horizon_months"] = origin, target, horizon
    if mapping["polygon_id"].duplicated().any():
        raise OutputSchemaError(f"{system}: duplicate polygon_id in mapping")
    return mapping[list(SEPTEMBER_HEADERS[system]["polygon_model_mapping"])]


def validate_ipcch_phases(predictions: pd.DataFrame) -> None:
    """Upstream integrity: every current polygon phase is a non-missing integer 1..5.

    Zero-population areas count too (they take part in ``country_maximum_phase``). A
    violation is a scoring/integrity failure, never an unavailable diagnostic.
    """
    phase = pd.to_numeric(predictions["overall_phase_pred"], errors="coerce")
    bad = phase.isna() | (phase % 1 != 0) | ~phase.between(1, 5)
    if bad.any():
        examples = predictions.loc[bad, "polygon_id"].astype(str).head(5).tolist()
        raise OutputSchemaError(f"IPCCH overall_phase_pred must be integral 1..5; bad polygons {examples}")


def country_tables(system: str, predictions: pd.DataFrame, *, census: pd.DataFrame,
                   area_lookup: pd.DataFrame | None = None,
                   country_errors: pd.DataFrame | None = None,
                   maximum_phase: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(country_predictions, country_confidence): current outcomes; error fields from
    ``country_errors`` and IPCCH maximum-phase fields from ``maximum_phase`` (validated
    evidence), blank when no evidence is available."""
    import pycountry

    if system == "fewsnet":
        scope = census[["ISO3", "country", "country_en"]].copy()
        scope["country_code"] = scope["ISO3"].map(lambda x: pycountry.countries.get(alpha_3=x).alpha_2)
        country = aggregate_country_probabilities(predictions, scope, census)
        forecast = forecast_country_fields(system, country)
    else:
        validate_ipcch_phases(predictions)  # population weights keep their own existing validation
        country = aggregate_country_scores(predictions, area_lookup[["area_id", "country", "country_en"]], census)
        iso = area_lookup[["area_id", "country"]].merge(census[["country", "ISO3"]], on="country", validate="many_to_one")
        with_iso = predictions.merge(iso[["area_id", "ISO3"]], on="area_id", validate="one_to_one")
        forecast = forecast_country_fields(system, country, with_iso)
    confidence = pd.DataFrame({"ISO3": sorted(country["ISO3"])})
    for column in SEPTEMBER_HEADERS[system]["country_confidence"][1:]:
        confidence[column] = pd.NA  # unsupported historical diagnostics stay blank
    for supplied in (country_errors, maximum_phase):
        if supplied is not None:
            values = supplied.set_index("ISO3").reindex(confidence["ISO3"])
            for column in values.columns:
                if column in confidence:
                    confidence[column] = values[column].to_numpy()
    forecast = forecast.reindex(confidence["ISO3"])
    if system == "fewsnet":
        confidence["country_outcome_crisis"] = forecast["country_outcome_crisis"].to_numpy()
        confidence["country_outcome_crisis_threshold"] = CRISIS_THRESHOLD
    else:
        overall = forecast["country_overall_phase"]
        confidence["country_overall_phase"] = overall.to_numpy()
        confidence["country_overall_phase_availability"] = ["available" if pd.notna(v) else pd.NA for v in overall]
        confidence["country_overall_phase_method"] = [IPCCH_PHASE_METHOD if pd.notna(v) else pd.NA for v in overall]
        confidence["country_maximum_phase"] = forecast["country_maximum_phase"].to_numpy()
    confidence = confidence[list(SEPTEMBER_HEADERS[system]["country_confidence"])]
    combined = append_country_v3(country, confidence)
    return combined[list(SEPTEMBER_HEADERS[system]["country_predictions"])], confidence


def polygon_diagnostics_unavailable(system: str, predictions: pd.DataFrame, iso_by_polygon: pd.Series) -> pd.DataFrame:
    """Polygon diagnostic table with every evidence field blank (no accepted evidence)."""
    if system == "fewsnet":
        table = pd.DataFrame({"polygon_id": predictions["admin_code"].astype(str),
                              "ISO3": predictions["ISO3"],
                              "population": predictions["population"],
                              "population_reference_period": predictions["population_reference_period"],
                              "population_source": predictions["population_source"]})
        name = "polygon_confidence"
    else:
        table = pd.DataFrame({"polygon_id": predictions["polygon_id"].astype(str)})
        table["ISO3"] = table["polygon_id"].map(iso_by_polygon)
        name = "polygon_training_errors"
    for column in SEPTEMBER_HEADERS[system][name]:
        if column not in table:
            table[column] = pd.NA
    return table[list(SEPTEMBER_HEADERS[system][name])]


def availability_rows(system: str, horizon: int, *, polygons, countries, reason: str = "missing_evidence") -> pd.DataFrame:
    rows = []
    for family, level in DIAGNOSTIC_FAMILIES[system].items():
        for entity in (polygons if level == "polygon" else countries):
            rows.append({"model_system": system, "horizon_months": horizon, "level": level, "entity_id": str(entity),
                         "diagnostic_family": family, "status": "unavailable", "reason": reason, "evidence_ref": pd.NA})
    return pd.DataFrame(rows, columns=AVAILABILITY_COLUMNS)


POLYGON_FAMILY = {"fewsnet": "polygon_confidence", "ipcch": "polygon_training_errors"}


def normalise_declarations(system: str, horizon: int, declared_families) -> dict:
    """Bridge CP1 per-family diagnostic declarations; absent -> unavailable/missing_evidence.

    Available: ``{"status", "ref": {uri, generation, sha256}, "evidence_model_package_id",
    "evidence_horizon_months"}`` (the manifest entry). Unavailable: ``{"status", "reason"}``.
    """
    declared_families = declared_families or {}
    unknown = set(declared_families) - set(DIAGNOSTIC_FAMILIES[system])
    if unknown:
        raise EvidenceIntegrityError(f"{system}/{horizon}m: unknown diagnostic families {sorted(unknown)}")
    out = {}
    for family in DIAGNOSTIC_FAMILIES[system]:
        entry = dict(declared_families.get(family) or {"status": "unavailable", "reason": "missing_evidence"})
        if entry.get("status") == "available":
            ref = entry.get("ref") or {}
            if not all(ref.get(key) for key in ("uri", "generation", "sha256")):
                raise EvidenceIntegrityError(f"{system}/{horizon}m/{family}: available evidence needs a hash-bound ref")
            if not entry.get("evidence_model_package_id") or entry.get("evidence_horizon_months") != horizon:
                raise EvidenceIntegrityError(f"{system}/{horizon}m/{family}: evidence must declare this "
                                             "horizon and its model package")
        elif entry.get("status") == "unavailable":
            if not entry.get("reason"):
                raise EvidenceIntegrityError(f"{system}/{horizon}m/{family}: unavailable needs a reason")
        else:
            raise EvidenceIntegrityError(f"{system}/{horizon}m/{family}: status must be available or unavailable")
        out[family] = entry
    return out


MAXIMUM_PHASE_STATUS = {"supported": ("available", pd.NA), "degenerate_empirical": ("available", pd.NA),
                        "single_month": ("limited", "single_month_interval_unavailable"),
                        "no_complete_history": ("unavailable", "no_complete_history")}


def scope_diagnostics(system: str, horizon: int, predictions: pd.DataFrame, *, declarations: dict, evidence_bytes,
                      package_id: str, polygons, census: pd.DataFrame, area_lookup, iso_by_polygon: pd.Series,
                      origin: str, accepted_period: str | None = None, training_cutoff: str | None = None) -> dict:
    """Polygon/country diagnostic tables + availability for one scope (shared by deliver and rescore).

    ``evidence_bytes(family) -> bytes`` returns the pinned evidence; its sha256 must equal the
    ref. Each family is selected, validated and frozen independently (country errors use the
    country family's own area evidence); the bytes used are returned for freezing.
    """
    import hashlib
    import io

    frozen, identities = {}, {}
    acceptance = {"system": system, "origin": origin, "period": accepted_period, "latest_end": training_cutoff}

    def load(family, parse):
        entry = declarations[family]
        data = evidence_bytes(family)
        if hashlib.sha256(data).hexdigest() != entry["ref"]["sha256"]:
            raise EvidenceIntegrityError(f"{system}/{horizon}m/{family}: evidence bytes do not match the ref")
        try:
            frame = pd.read_csv(io.BytesIO(data), dtype={"polygon_id": str, "target_month": str})
        except (ValueError, UnicodeDecodeError) as exc:  # malformed bytes are an integrity failure
            raise EvidenceIntegrityError(f"{system}/{horizon}m/{family}: unreadable evidence ({exc})") from exc
        table, identities[family] = parse(frame, roster=polygons, model_package_id=package_id, horizon=horizon,
                                          declared=entry, acceptance=acceptance)
        frozen[family] = data
        return table

    polygon_family = POLYGON_FAMILY[system]
    errors, evidence, maximum = None, None, None
    if declarations[polygon_family]["status"] == "available":
        evidence = load(polygon_family, area_evidence)
        polygon_table, _ = supported_diagnostics(system, predictions, evidence, identity=identities[polygon_family],
                                                 iso_by_polygon=iso_by_polygon)
    else:
        polygon_table = polygon_diagnostics_unavailable(system, predictions, iso_by_polygon)
    if declarations["country_confidence"]["status"] == "available":
        country_evidence = load("country_confidence", area_evidence)
        _, errors = supported_diagnostics(system, predictions, country_evidence,
                                          identity=identities["country_confidence"], iso_by_polygon=iso_by_polygon)
    if declarations.get("maximum_phase", {}).get("status") == "available":
        validate_ipcch_phases(predictions)
        residuals = load("maximum_phase", residual_evidence)
        countries = sorted(set(predictions["polygon_id"].astype(str).map(iso_by_polygon).dropna()))
        maximum = maximum_phase_diagnostics(predictions, residuals, iso_by_polygon, countries)
    country, confidence = country_tables(system, predictions, census=census, area_lookup=area_lookup,
                                         country_errors=errors, maximum_phase=maximum)
    rows = []
    for family, level in DIAGNOSTIC_FAMILIES[system].items():
        entry = declarations[family]
        ref = f"{entry['ref']['uri']}#{entry['ref']['generation']}" if entry["status"] == "available" else pd.NA
        if entry["status"] != "available":
            entities = [(e, "unavailable", entry["reason"]) for e in (polygons if level == "polygon" else confidence["ISO3"])]
        elif family == "maximum_phase":
            entities = [(iso, *MAXIMUM_PHASE_STATUS[status]) for iso, status in
                        zip(confidence["ISO3"], confidence["country_maximum_phase_uncertainty_status"])]
        elif level == "polygon":
            supported = set(evidence.loc[evidence["sample_count"] > 0, "polygon_id"])
            entities = [(e, "available", pd.NA) if e in supported else (e, "unavailable", "no_eligible_area_history")
                        for e in map(str, polygons)]
        else:
            entities = [(iso, "available", pd.NA) if pd.notna(rate) else (iso, "unavailable", "no_eligible_area_history")
                        for iso, rate in zip(confidence["ISO3"], confidence["country_error_rate"])]
        rows.extend({"model_system": system, "horizon_months": horizon, "level": level, "entity_id": str(entity),
                     "diagnostic_family": family, "status": status, "reason": reason, "evidence_ref": ref}
                    for entity, status, reason in entities)
    return {"polygon_table": polygon_table, "polygon_name": polygon_family, "country": country,
            "confidence": confidence, "availability": pd.DataFrame(rows, columns=AVAILABILITY_COLUMNS),
            "frozen_evidence": frozen, "evidence_identity": identities}


def write_table(frame: pd.DataFrame, path: Path, *, system: str | None = None, name: str | None = None) -> Path:
    """Create-only UTF-8 CSV with blank missing values; frozen column order when (system, name) given."""
    if system is not None:
        expected = list(SEPTEMBER_HEADERS[system][name])
        if list(frame.columns) != expected:
            raise OutputSchemaError(f"{system}/{name} columns differ from the September contract")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as handle:
        frame.to_csv(handle, index=False, lineterminator="\n")
    return path
