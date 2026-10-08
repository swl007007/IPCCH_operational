"""Score the six accepted 0/6/12 packages at a fixed origin (CP3).

Reuses the existing pure scoring APIs without fitting anything:

* FEWSNET: ``load_local_model_package`` (checksums + exact runtime pins),
  ``Stage3FeatureBuilder.transform``, ``select_latest_inference_frame``,
  ``predict_frame`` (saved ``MaxPlusImputer``), ``enrich_local_predictions``.
  Stage3 runs on the O-12..O calendar window (13 months) taken from the FULL
  normalised panel (z-scores unchanged); identity, population and the area universe
  come from a thin full-history read. Supervisor April parity proof:
  ``research/cp3_evidence/fews_window_replay`` (all 0/6/12 outputs exact). This is a
  memory bound, not a normalisation or modelling change.
* IPCCH: ``run_scope`` (saved per-feature training medians), without the removed
  threshold-margin uncertainty fields, as in the September v3 delivery.

Final-feature missingness is taken from the actual matrix each package imputes, and
the audit rule names that package's saved statistic for that final feature.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pandas as pd

from cloud.orchestrator.delivery_inputs import FEWSNET_IDENTITY
from fewsnet_partitioned_rf_pipeline.core.data import normalize_admin_code
from fewsnet_partitioned_rf_pipeline.core.horizons import select_latest_inference_frame
from fewsnet_partitioned_rf_pipeline.core.preprocessing import Stage3FeatureBuilder
from fewsnet_partitioned_rf_pipeline.local.outputs import (
    _RAW_REQUIRED_COLUMNS,
    build_identity_population_frame,
    enrich_local_predictions,
    validate_local_prediction_frame,
)
from fewsnet_partitioned_rf_pipeline.local.package import load_local_model_package
from model_pipeline.ipcch_launch_runtime import model_package as ipcch_model_package
from model_pipeline.run_operational_launch_inference import add_calendar_months, run_scope

HORIZONS = (0, 6, 12)
FEWSNET_STAGE3_WINDOW_MONTHS = 12  # O-12..O inclusive: 13 calendar months
_LAG = re.compile(r"^(EVI|fews_ipc_crisis|fews_ipc)_(?:l|lag_)(\d+)$")
_WINDOW = re.compile(r"^(WFP_Price|nightlight)_m(\d+)$")
FEWSNET_ZSCORE_SOURCES = {"Tair_zscore": "Tair_f_tavg_mean", "Rainf_zscore": "Rainf_f_tavg_mean"}
# The audit lists the 12 local rolling inputs; the z-score also depends on per-admin
# mean/std of whole-table rolling values over the full cutoff-bounded panel
# (core/normalization.py, deduplicate-before-global-rolling-zscore-v1). That snapshot
# dependency is disclosed with the normalised panel identity, not claimed as 12-month-only.
FEWSNET_ZSCORE_DISCLOSURE = ("climate zscore = (rolling12 - per-admin mean) / per-admin std over the whole "
                             "cutoff-bounded panel; normalization deduplicate-before-global-rolling-zscore-v1")


def fewsnet_dependencies(feature_columns, raw_columns) -> tuple[dict, list[str]]:
    """Final feature -> (source column, lag months) following the existing Stage3/normalisation code.

    Returns the mapping and the identity/calendar-derived features it does not audit.
    """
    dependencies, unaudited = {}, []
    for feature in feature_columns:
        lag, window = _LAG.match(feature), _WINDOW.match(feature)
        if lag:
            source = {"EVI": "EVI", "fews_ipc_crisis": "fews_ipc_crisis", "fews_ipc": "fews_ipc"}[lag.group(1)]
            dependencies[feature] = (source, (int(lag.group(2)),))
        elif window:  # prior complete calendar window, current month excluded
            dependencies[feature] = (window.group(1), tuple(range(1, int(window.group(2)) + 1)))
        elif feature in FEWSNET_ZSCORE_SOURCES:  # 12-month rolling mean including the current month
            dependencies[feature] = (FEWSNET_ZSCORE_SOURCES[feature], tuple(range(0, 12)))
        elif feature in raw_columns and feature not in FEWSNET_IDENTITY:  # identity/calendar: never filled
            dependencies[feature] = (feature, (0,))
        else:
            unaudited.append(feature)
    return dependencies, unaudited


def fewsnet_window(origin: str) -> tuple[str, str]:
    return str(pd.Period(origin, "M") - FEWSNET_STAGE3_WINDOW_MONTHS), origin


def _months(dates: pd.Series) -> pd.Series:
    return pd.to_datetime(dates.astype(str)).dt.to_period("M").astype(str)


def load_fewsnet_scoring_inputs(normalized_path: str | Path, origin: str, *, identity_path: str | Path,
                                chunksize: int = 40000) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(thin full-history identity/population source, O-12..O calendar window); the whole panel
    is never held in memory.

    ``identity_path`` is the pre-fill panel (same rows): population provenance must name the
    month it was actually observed, never a carried-forward window row.
    """
    identity_source = pd.read_csv(identity_path, usecols=list(_RAW_REQUIRED_COLUMNS),
                                  dtype={"FEWSNET_admin_code": "string"})
    first, last = fewsnet_window(origin)
    blocks = []
    for chunk in pd.read_csv(normalized_path, chunksize=chunksize, dtype={"FEWSNET_admin_code": "string"},
                             low_memory=False):
        blocks.append(chunk.loc[_months(chunk["date"]).between(first, last)].copy())
    return identity_source, pd.concat(blocks, ignore_index=True)


def fewsnet_identity_and_window(identity_panel: pd.DataFrame, window_panel: pd.DataFrame, origin: str):
    """Identity/population from full history; the window must hold exactly O-12..O rows of the
    same area universe (an area present only in older history is rejected, never dropped)."""
    first, last = fewsnet_window(origin)
    months = _months(window_panel["date"])
    if not months.between(first, last).all():
        raise ValueError(f"FEWSNET scoring window must contain only {first}..{last} rows")
    universe = set(identity_panel["FEWSNET_admin_code"].map(normalize_admin_code))
    in_window = set(window_panel["FEWSNET_admin_code"].map(normalize_admin_code))
    if universe != in_window:
        raise ValueError(f"FEWSNET areas outside the {first}..{last} window: "
                         f"old-only {sorted(universe - in_window)[:10]}, unknown {sorted(in_window - universe)[:10]}")
    return build_identity_population_frame(identity_panel, origin)


def score_fewsnet(window_panel: pd.DataFrame, package_dirs: Mapping[int, str | Path], *, identity_panel: pd.DataFrame,
                  origin: str, source_input: str, artifact_paths: Mapping[int, str]) -> dict[int, dict]:
    identity, population = fewsnet_identity_and_window(identity_panel, window_panel, origin)
    features_by_contract: dict[tuple, pd.DataFrame] = {}
    results = {}
    for horizon in HORIZONS:  # sequential: one package loaded at a time (design section 6)
        package = load_local_model_package(package_dirs[horizon])
        predictor = package.predictor
        contract = predictor.feature_contract
        key = tuple(contract.feature_columns)
        if key not in features_by_contract:
            features_by_contract[key] = Stage3FeatureBuilder().transform(window_panel, contract)
        frame = select_latest_inference_frame(features_by_contract[key], origin, horizon)
        if set(frame["admin_code"].astype(str)) != set(identity["admin_code"]):
            raise ValueError(f"FEWSNET {horizon}m inference frame does not cover the full-history universe")
        matrix = frame[list(contract.feature_columns)].apply(pd.to_numeric, errors="coerce")
        final_missing = matrix.isna() | np.isinf(matrix.to_numpy(dtype="float64"))
        final_missing.index = frame["admin_code"].astype(str).to_numpy()
        rules = {column: f"MaxPlusImputer[{column}]={value!r}"
                 for column, value in zip(contract.feature_columns, predictor.imputer.impute_values_)}
        formal = predictor.predict_frame(frame)
        predictions = enrich_local_predictions(formal, identity, model_artifact_path=artifact_paths[horizon],
                                               source_input=source_input)
        validate_local_prediction_frame(
            predictions, expected_admin_codes=identity["admin_code"], feature_month=origin,
            target_month=add_calendar_months(origin, horizon), horizon_months=horizon,
            suite_version=predictor.suite_version)
        results[horizon] = {"predictions": predictions, "final_missing": final_missing, "rules": rules,
                            "package_id": f"{predictor.suite_version}/{predictor.horizon_key}",
                            "threshold": float(predictor.threshold), "population": population,
                            "inference_frame": frame, "identity": identity,
                            "zscore_dependency_disclosure": FEWSNET_ZSCORE_DISCLOSURE}
        del package, predictor  # release before loading the next horizon
    return results


def score_ipcch(rows: pd.DataFrame, package_root: str | Path, *, origin: str, source_input: str) -> dict[int, dict]:
    from model_pipeline.ipcch_launch_runtime.adapters import validate_monthly_input

    monthly, _ = validate_monthly_input(rows, origin)
    results = {}
    for scope in HORIZONS:
        package = ipcch_model_package.load_scope_package(Path(package_root), scope)
        contract, metadata = package["contract"], package.get("metadata", {})
        sources = dict(zip(contract["feature_name"], contract["source_column"]))
        stats = metadata["imputation_statistics"]
        final_missing = pd.DataFrame(
            {feature: (monthly[source].isna() if source in monthly else True) for feature, source in sources.items()})
        final_missing.index = monthly["admin_code"].astype(str).to_numpy()
        rules = {feature: f"{key}={stats[key]!r}"
                 for feature, key in zip(contract["feature_name"], contract["fill_value_or_stat_key"])}
        predictions, summary = run_scope(monthly_rows=monthly, model_package_root=Path(package_root),
                                         feature_month=origin, scope_months=scope,
                                         target_month=add_calendar_months(origin, scope),
                                         source_input=source_input, include_uncertainty=False)
        predictions.insert(0, "polygon_id", predictions["area_id"].astype(str))
        results[scope] = {"predictions": predictions, "final_missing": final_missing, "rules": rules,
                          "package_id": summary["model_package_id"], "summary": summary,
                          "dependencies": {feature: (source, (0,)) for feature, source in sources.items()}}
    return results
