from __future__ import annotations

from io import StringIO
import json

import pandas as pd

from cloud.common.object_store import ObjectStore
from cloud.common.reports import build_validation_report


ID_COLUMNS = ["area_id", "admin_code", "lat", "lon", "year", "month"]
SOURCE_KEY_COLUMNS = {"area_id", "admin_code", "lat", "lon", "year", "month"}
ENGINEERED_MARKERS = (
    "__l",
    "__roll",
    "__slope",
    "__accel",
    "__hist_",
    "__forecast_sequence",
    "__delayed_control",
    "__x__",
    "_asof",
    "_lag",
    "lag1",
)


def assemble_monthly_base_input(
    *,
    scaffold: pd.DataFrame,
    source_panel: pd.DataFrame,
    fixed_slow_features: pd.DataFrame,
    evi_mean_long: pd.DataFrame,
    evi_std_long: pd.DataFrame,
    feature_month: str,
) -> tuple[pd.DataFrame, dict]:
    key = ["area_id", "year", "month"]
    year, month = (int(part) for part in feature_month.split("-"))
    scaffold = _prepare_scaffold(scaffold, year=year, month=month)
    fixed_slow_features = _normalize_area_id(fixed_slow_features)
    source_panel = _normalize_area_id(source_panel)
    evi_mean_long = _normalize_area_id(evi_mean_long)
    evi_std_long = _normalize_area_id(evi_std_long)

    fixed_feature_columns = [
        column
        for column in fixed_slow_features.columns
        if column not in {"area_id", "admin_code", "lat", "lon"}
    ]
    if fixed_slow_features["area_id"].eq("").any():
        raise ValueError("fixed/slow features contain blank area_id")
    if fixed_slow_features["area_id"].duplicated().any():
        raise ValueError("fixed/slow features must be unique by area_id")
    source_scanned_rows = int(len(source_panel))
    source_panel = source_panel[
        (source_panel["year"] == year) & (source_panel["month"] == month)
    ].copy()
    if source_panel["area_id"].eq("").any():
        raise ValueError("source panel contains blank area_id")
    source_duplicate_rows = int(source_panel.duplicated(key).sum())
    if source_duplicate_rows:
        raise ValueError("duplicate source keys for selected feature month")
    source_panel = source_panel.drop_duplicates(key, keep="first")
    target_month_present = not source_panel.empty
    source_feature_columns = [
        column
        for column in source_panel.columns
        if column not in SOURCE_KEY_COLUMNS
        and column not in fixed_feature_columns
        and not _is_engineered_column(column)
    ]
    evi_frames = [
        _select_feature_columns(evi_mean_long, key, ["EVI_mean"]),
        _select_feature_columns(evi_std_long, key, ["EVI_std"]),
    ]
    base = scaffold[ID_COLUMNS].copy()
    base = base.merge(
        fixed_slow_features[["area_id", *fixed_feature_columns]],
        on=["area_id"],
        how="left",
        validate="many_to_one",
    )
    base = base.merge(
        source_panel[[*key, *source_feature_columns]],
        on=key,
        how="left",
        validate="one_to_one",
    )
    for frame in evi_frames:
        base = base.merge(frame, on=key, how="left", validate="one_to_one")
    fixed_matched = int(
        base[fixed_feature_columns].notna().any(axis=1).sum()
        if fixed_feature_columns
        else 0
    )
    source_matched = int(
        base[source_feature_columns].notna().any(axis=1).sum()
        if source_feature_columns
        else 0
    )
    report = build_validation_report(
        report_type="monthly_base_input_summary",
        feature_month=feature_month,
        run_id="local-assembly",
        status="passed",
        row_count=len(base),
        column_count=len(base.columns),
        scaffold_row_count=len(scaffold),
        key_columns=key,
        join_coverage={},
        missingness={
            "target_month_present_in_source": target_month_present,
            "missing_value_counts": base.isna().sum().to_dict(),
        },
        input_lineage={},
        evi_feature_sources=["EVI_mean_monthly_long.csv", "EVI_std_monthly_long.csv"],
        source_join={
            "matched_rows": source_matched,
            "unmatched_rows": len(base) - source_matched,
            "feature_columns": len(source_feature_columns),
            "scanned_rows": source_scanned_rows,
            "target_month_rows": int(len(source_panel) + source_duplicate_rows),
            "duplicate_rows": source_duplicate_rows,
            "target_month_present_in_source": target_month_present,
        },
        fixed_slow_join={
            "matched_rows": fixed_matched,
            "unmatched_rows": len(base) - fixed_matched,
            "feature_columns": len(fixed_feature_columns),
        },
    )
    return base, report


def _prepare_scaffold(scaffold: pd.DataFrame, *, year: int, month: int) -> pd.DataFrame:
    result = _normalize_area_id(scaffold)
    observed_months = set(
        zip(result["year"].astype(int), result["month"].astype(int), strict=False)
    )
    if len(observed_months) != 1:
        raise ValueError(
            f"scaffold must contain exactly one month; found {sorted(observed_months)}"
        )
    if (year, month) not in observed_months:
        raise ValueError(f"scaffold month must match target {year}-{month:02d}")
    if result["area_id"].eq("").any():
        raise ValueError("scaffold area_id/admin_code must be nonblank")
    result = result[
        (result["year"].astype(int) == year) & (result["month"].astype(int) == month)
    ].copy()
    if result.duplicated(["area_id", "year", "month"]).any():
        raise ValueError("duplicate scaffold keys")
    for column in ID_COLUMNS:
        if column not in result.columns:
            result[column] = ""
    result["year"] = year
    result["month"] = month
    return result


def _normalize_area_id(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "area_id" not in result.columns and "admin_code" in result.columns:
        result["area_id"] = result["admin_code"].map(_normalize_identifier)
    elif "area_id" in result.columns:
        result["area_id"] = result["area_id"].map(_normalize_identifier)
    if "admin_code" in result.columns:
        normalized_admin = result["admin_code"].astype(str).str.strip()
        if (
            "area_id" in result.columns
            and not (
                result["area_id"] == normalized_admin.map(_normalize_identifier)
            ).all()
        ):
            raise ValueError("area_id must equal normalized admin_code when both exist")
    return result


def _normalize_identifier(value) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer():
        return str(int(number))
    return text


def _is_engineered_column(column: str) -> bool:
    lowered = column.lower()
    return any(marker in lowered for marker in ENGINEERED_MARKERS)


def _select_feature_columns(
    frame: pd.DataFrame, key: list[str], feature_columns: list[str]
) -> pd.DataFrame:
    available_features = [
        column for column in feature_columns if column in frame.columns
    ]
    return frame[[*key, *available_features]].copy()


def write_monthly_assembly_artifacts(
    *,
    store: ObjectStore,
    feature_month: str,
    run_id: str,
    output_prefix_uri: str,
    scaffold_uri: str,
    source_panel_uri: str,
    fixed_slow_features_uri: str,
    evi_mean_long_uri: str,
    evi_std_long_uri: str,
) -> dict:
    base_input, report = assemble_monthly_base_input(
        scaffold=_read_csv(store, scaffold_uri),
        source_panel=_read_csv(store, source_panel_uri),
        fixed_slow_features=_read_csv(store, fixed_slow_features_uri),
        evi_mean_long=_read_csv(store, evi_mean_long_uri),
        evi_std_long=_read_csv(store, evi_std_long_uri),
        feature_month=feature_month,
    )
    yyyymm = feature_month.replace("-", "")
    report["run_id"] = run_id
    base_uri = output_prefix_uri + f"ipcch_monthly_base_input_{yyyymm}.csv"
    summary_uri = output_prefix_uri + f"ipcch_monthly_base_input_{yyyymm}_summary.json"
    store.write_text(base_uri, base_input.to_csv(index=False))
    store.write_text(summary_uri, json.dumps(report, indent=2, sort_keys=True) + "\n")
    return {
        "status": "passed",
        "base_input_uri": base_uri,
        "summary_uri": summary_uri,
        "report": report,
    }


def _read_csv(store: ObjectStore, uri: str) -> pd.DataFrame:
    return pd.read_csv(StringIO(store.read_text(uri)))
