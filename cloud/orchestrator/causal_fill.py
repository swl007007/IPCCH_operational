"""Same-area, past-only filling of base monthly features with an audit trail.

Raw observations are never modified. For each native polygon, base feature and
calendar month, the value used is the latest finite observation of the same
polygon at or before that month. Calendar lags/rolling features are recomputed
downstream by the existing system builders from the filled base series.

Two steps, kept separate:

* ``carry_forward_base_series`` works on source (base) features only. A month
  with no eligible same-area history stays missing (``no_eligible_history``);
  nothing here imputes it, and there is no zero or cross-area fallback.
* ``bind_model_features`` binds the audit to final model features of one
  package/horizon. The saved package imputers (FEWS ``MaxPlusImputer``, IPCCH
  training medians) act on final model columns such as ``EVI_lag3``, not on the
  base source, so the caller supplies which final values are actually missing
  after the system builder ran. Only those are recorded as ``model_imputation``,
  under that package's rule for that final feature; without one, the formal
  release is blocked.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence

import pandas as pd


FILL_POLICY_VERSION = "area-past-only-carry-forward-v1"
SYSTEMS = ("fewsnet", "ipcch")
AUDIT_COLUMNS = [
    "system",
    "horizon_months",
    "model_package_id",
    "polygon_id",
    "model_feature",
    "feature_month",
    "source_feature",
    "dependency_month",
    "source_ref",
    "source_sha256",
    "observation_month",
    "staleness_months",
    "fill_method",
    "derived_from_filled",
    "feature_value_method",
    "imputation_rule",
]
OBSERVED = "observed"
CARRY_FORWARD = "carry_forward"
NO_ELIGIBLE_HISTORY = "no_eligible_history"
COMPUTED = "computed"
MODEL_IMPUTATION = "model_imputation"

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GENERATION_RE = re.compile(r"^[1-9][0-9]*$")


class RequiredInputUnavailable(ValueError):
    """A required input has no eligible observation and no package imputation rule."""


def carry_forward_base_series(
    observations: pd.DataFrame,
    *,
    system: str,
    id_column: str,
    month_column: str,
    feature_columns: Sequence[str],
    roster: Iterable[str],
    months: Sequence[str],
    source_ref: Mapping[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fill each roster polygon x month x base feature from its own past only.

    ``observations`` may include months before ``months`` (needed history) but
    never contributes a later month to an earlier one. ``source_ref`` is the
    immutable ``{"uri", "generation", "sha256"}`` of the observation snapshot.
    Returns the filled grid (``id_column``, ``month_column`` + features) and
    source-level audit rows (not yet bound to a model feature or package).
    """
    if system not in SYSTEMS:
        raise ValueError(f"system must be one of {SYSTEMS}, got {system!r}")
    ref_text, ref_sha256 = _source_identity(source_ref)
    roster_ids = _require_native_ids(pd.Series(list(roster), dtype=object), "roster")
    if roster_ids.duplicated().any():
        raise ValueError("roster contains duplicate native IDs")
    grid_months = [_require_month(month, "months") for month in months]
    if len(set(grid_months)) != len(grid_months):
        raise ValueError("months must be unique")
    missing = [col for col in (id_column, month_column, *feature_columns) if col not in observations]
    if missing:
        raise ValueError(f"observations lack columns: {missing}")

    observations = observations.reset_index(drop=True)
    ids = _require_native_ids(observations[id_column], id_column)
    unknown = sorted(set(ids) - set(roster_ids))
    if unknown:
        raise ValueError(f"observations contain IDs outside the roster: {unknown[:5]}")
    obs_months = observations[month_column].map(lambda value: _require_month(value, month_column))
    keys = pd.DataFrame({"id": ids, "month": obs_months})
    if keys.duplicated().any():
        raise ValueError("observations contain duplicate polygon-month keys")

    grid = pd.MultiIndex.from_product(
        [roster_ids.tolist(), sorted(grid_months)], names=["id", "month"]
    ).to_frame(index=False)
    grid["id"] = grid["id"].astype(str)
    grid["ordinal"] = grid["month"].map(_month_ordinal).astype("int64")
    filled = grid[["id", "month"]].rename(columns={"id": id_column, "month": month_column})
    audit_parts = []
    for feature in feature_columns:
        values = pd.to_numeric(observations[feature], errors="raise")
        if values.map(lambda value: isinstance(value, float) and math.isinf(value)).any():
            raise ValueError(f"{feature} contains non-finite observations; they are neither observed nor missing")
        eligible = pd.DataFrame(
            {"id": ids, "observation_month": obs_months, "value": values}
        ).dropna(subset=["value"])
        # Explicit dtypes: an all-missing feature leaves ``eligible`` empty, and
        # merge_asof still needs matching key types to return no_eligible_history.
        eligible["id"] = eligible["id"].astype(str)
        eligible["ordinal"] = eligible["observation_month"].map(_month_ordinal).astype("int64")
        # Backward as-of join within the same id: latest observation at or before.
        joined = pd.merge_asof(
            grid.sort_values("ordinal"),
            eligible.sort_values("ordinal"),
            on="ordinal",
            by="id",
            direction="backward",
        )
        joined = grid[["id", "month"]].merge(joined, on=["id", "month"], how="left", validate="one_to_one")
        filled[feature] = joined["value"].to_numpy()
        staleness = joined["month"].map(_month_ordinal) - joined["observation_month"].map(
            _month_ordinal, na_action="ignore"
        )
        method = pd.Series(NO_ELIGIBLE_HISTORY, index=joined.index, dtype=object)
        method[staleness.eq(0)] = OBSERVED
        method[staleness.gt(0)] = CARRY_FORWARD
        audit_parts.append(
            pd.DataFrame(
                {
                    "system": system,
                    "horizon_months": pd.NA,
                    "model_package_id": pd.NA,
                    "polygon_id": joined["id"],
                    "model_feature": pd.NA,
                    "feature_month": joined["month"],
                    "source_feature": feature,
                    "dependency_month": joined["month"],
                    "source_ref": ref_text,
                    "source_sha256": ref_sha256,
                    "observation_month": joined["observation_month"],
                    "staleness_months": staleness.astype("Int64"),
                    "fill_method": method,
                    "derived_from_filled": method.ne(OBSERVED),
                    "feature_value_method": pd.NA,
                    "imputation_rule": pd.NA,
                }
            )
        )
    audit = pd.concat(audit_parts, ignore_index=True)[AUDIT_COLUMNS]
    return filled, audit


def bind_model_features(
    base_audit: pd.DataFrame,
    dependencies: Mapping[str, tuple[str, Sequence[int]]],
    *,
    feature_month: str,
    horizon_months: int,
    model_package_id: str,
    final_missing: pd.DataFrame,
    imputation_rules: Mapping[str, str],
) -> pd.DataFrame:
    """Audit rows for the final model features of one package/horizon at ``feature_month``.

    ``dependencies`` maps final model feature -> (base source feature, lag months);
    lag 0 is the same month (direct features), ``(1, ..., 12)`` a prior window.
    ``final_missing`` (index polygon_id, one boolean column per model feature) says
    which final values the package's own saved rule imputes, as determined from the
    built feature matrix before imputation. ``imputation_rules`` maps final model
    feature -> that package's rule. A derivative is never reported as computed
    from imputed base values: base gaps stay ``no_eligible_history`` and the final
    value is ``model_imputation`` or ``computed`` exactly as the builder produced it.
    """
    origin = _month_ordinal(_require_month(feature_month, "feature_month"))
    if horizon_months not in (0, 6, 12) or type(horizon_months) is not int:
        raise ValueError("horizon_months must be 0, 6 or 12")
    if not isinstance(model_package_id, str) or not model_package_id:
        raise ValueError("model_package_id must be a non-empty string")
    polygons = pd.Index(base_audit["polygon_id"].unique())
    missing_columns = sorted(set(dependencies) - set(final_missing.columns))
    if missing_columns or not polygons.isin(final_missing.index).all():
        raise ValueError(f"final_missing must cover every polygon and model feature; missing {missing_columns[:5]}")
    if final_missing.index.duplicated().any() or not all(dtype == bool for dtype in final_missing.dtypes):
        raise ValueError("final_missing must have unique polygon_id index and boolean columns")

    parts = []
    for model_feature, (source_feature, lags) in dependencies.items():
        dependency_months = sorted({_ordinal_month(origin - lag) for lag in _require_lags(lags, model_feature)})
        rows = base_audit.loc[
            base_audit["source_feature"].eq(source_feature)
            & base_audit["feature_month"].isin(dependency_months)
        ].copy()
        # Coverage is checked per polygon: one polygon's gap is not hidden by others.
        counts = rows.groupby("polygon_id")["feature_month"].nunique().reindex(polygons, fill_value=0)
        incomplete = counts[counts.ne(len(dependency_months))]
        if len(incomplete):
            raise ValueError(
                f"{model_feature} needs {source_feature} months {dependency_months}; "
                f"incomplete for polygons {incomplete.index[:5].tolist()}"
            )
        missing_final = final_missing[model_feature].reindex(rows["polygon_id"]).to_numpy(dtype=bool)
        if missing_final.any() and model_feature not in imputation_rules:
            examples = rows.loc[missing_final, "polygon_id"].unique()[:5].tolist()
            raise RequiredInputUnavailable(
                f"{model_feature} is missing for polygons {examples} and package "
                f"{model_package_id} has no imputation rule for it"
            )
        filled_any = rows.groupby("polygon_id")["fill_method"].transform(lambda m: m.ne(OBSERVED).any())
        rows["model_feature"] = model_feature
        rows["dependency_month"] = rows["feature_month"]
        rows["feature_month"] = feature_month
        rows["horizon_months"] = horizon_months
        rows["model_package_id"] = model_package_id
        rows["derived_from_filled"] = filled_any.to_numpy()
        rows["feature_value_method"] = [MODEL_IMPUTATION if flag else COMPUTED for flag in missing_final]
        rows["imputation_rule"] = [
            f"{model_package_id}:{imputation_rules[model_feature]}" if flag else pd.NA for flag in missing_final
        ]
        parts.append(rows)
    if not parts:
        return pd.DataFrame(columns=AUDIT_COLUMNS)
    return pd.concat(parts, ignore_index=True)[AUDIT_COLUMNS]


def _require_lags(lags: Sequence[int], model_feature: str) -> list[int]:
    values = list(lags)
    if not values or any(type(lag) is not int or lag < 0 for lag in values) or len(set(values)) != len(values):
        raise ValueError(f"{model_feature} lags must be unique non-negative integers, got {values}")
    return values


def _source_identity(source_ref: Mapping[str, str]) -> tuple[str, str]:
    """The audit names the exact observation snapshot: URI, generation and SHA-256."""
    if not isinstance(source_ref, Mapping) or set(source_ref) != {"uri", "generation", "sha256"}:
        raise ValueError("source_ref must be {uri, generation, sha256}")
    uri, generation, sha256 = source_ref["uri"], source_ref["generation"], source_ref["sha256"]
    if not isinstance(uri, str) or not uri.startswith("gs://") or uri.endswith("/"):
        raise ValueError("source_ref.uri must be a gs:// object URI")
    if not isinstance(generation, str) or _GENERATION_RE.fullmatch(generation) is None:
        raise ValueError("source_ref.generation must be a positive integer string")
    if not isinstance(sha256, str) or _SHA256_RE.fullmatch(sha256) is None:
        raise ValueError("source_ref.sha256 must be a lowercase SHA-256 hex digest")
    return f"{uri}#{generation}", sha256


def _require_native_ids(values: pd.Series, name: str) -> pd.Series:
    """Native IDs stay strings; numeric coercion could merge distinct codes."""
    if values.isna().any() or not values.map(lambda value: isinstance(value, str) and value != "").all():
        raise ValueError(f"{name} native IDs must be non-empty strings")
    return values.astype(object).reset_index(drop=True)


def _require_month(value: object, name: str) -> str:
    if not isinstance(value, str) or _MONTH_RE.fullmatch(value) is None:
        raise ValueError(f"{name} values must be YYYY-MM strings, got {value!r}")
    return value


def _month_ordinal(value: str) -> int:
    return int(value[:4]) * 12 + int(value[5:7]) - 1


def _ordinal_month(ordinal: int) -> str:
    return f"{ordinal // 12:04d}-{ordinal % 12 + 1:02d}"
