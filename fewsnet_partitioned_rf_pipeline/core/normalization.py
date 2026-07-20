"""One-time, fail-closed normalization of the assembled FEWSNET panel."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from fewsnet_partitioned_rf_pipeline.config import TARGET_COLUMN
from fewsnet_partitioned_rf_pipeline.core.data import normalize_admin_code
from fewsnet_partitioned_rf_pipeline.schemas import validate_payload


NORMALIZATION_SCHEMA_VERSION = "fewsnet-panel-normalization-v1"
NORMALIZATION_VERSION = "deduplicate-before-global-rolling-zscore-v1"
ADMIN_COLUMN = "FEWSNET_admin_code"
DATE_COLUMN = "date"
COMPARISON_EXCLUDED_COLUMNS = ("Tair_zscore", "Rainf_zscore")
CLIMATE_DERIVATIONS = {
    "Tair_f_tavg_mean": "Tair_zscore",
    "Rainf_f_tavg_mean": "Rainf_zscore",
}
ROLLING_WINDOW = 12
ROLLING_MIN_PERIODS = 1
ZSCORE_DDOF = 1

_SOURCE_ROW_COLUMN = "_source_row_number"
_PARSED_DATE_COLUMN = "_parsed_date"
_NORMALIZED_ADMIN_COLUMN = "_normalized_admin_code"
_FEATURE_MONTH_COLUMN = "_feature_month"
_VALIDATION_CHUNK_SIZE = 100_000


@dataclass(frozen=True)
class PanelNormalizationResult:
    output_panel_path: Path
    audit_path: Path
    raw_row_count: int
    normalized_row_count: int
    duplicate_group_count: int
    removed_row_count: int
    latest_feature_month: str
    latest_label_month: str
    output_sha256: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_columns(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        try:
            columns = next(csv.reader(handle))
        except StopIteration as exc:
            raise ValueError("raw panel must contain a header row") from exc
    duplicates = sorted(
        {column for column in columns if columns.count(column) > 1}
    )
    if duplicates:
        raise ValueError(f"raw panel columns must be unique: {duplicates}")
    return columns


def _values_equal(series: pd.Series) -> bool:
    first = series.iloc[0]
    if pd.isna(first):
        return bool(series.isna().all())
    return bool((series.eq(first) | series.isna() & pd.isna(first)).all())


def _csv_dimensions(path: Path) -> tuple[int, int]:
    columns = _source_columns(path)
    row_count = 0
    for chunk in pd.read_csv(
        path,
        usecols=[columns[0]],
        chunksize=_VALIDATION_CHUNK_SIZE,
    ):
        row_count += len(chunk)
    return row_count, len(columns)


def _panel_metadata(path: Path, row_count: int, column_count: int) -> dict:
    return {
        "path": str(path),
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
        "row_count": row_count,
        "column_count": column_count,
    }


def _validate_paths(
    raw_panel_path: Path,
    output_panel_path: Path,
    audit_path: Path,
) -> tuple[Path, Path, Path]:
    raw = Path(raw_panel_path).resolve()
    output = Path(output_panel_path).resolve()
    audit = Path(audit_path).resolve()
    if output == raw or audit == raw:
        raise ValueError("output and audit paths must be different from raw path")
    if output == audit:
        raise ValueError("output panel and audit paths must be different")
    for path in (output, audit):
        if path.exists():
            raise FileExistsError(f"versioned normalization artifact already exists: {path}")
    return raw, output, audit


def normalize_panel(
    raw_panel_path: Path,
    output_panel_path: Path,
    audit_path: Path,
) -> PanelNormalizationResult:
    """Create one immutable normalized panel and its matching audit."""
    raw, output, audit = _validate_paths(
        raw_panel_path,
        output_panel_path,
        audit_path,
    )
    source_columns = _source_columns(raw)
    required_columns = {
        ADMIN_COLUMN,
        DATE_COLUMN,
        TARGET_COLUMN,
        *CLIMATE_DERIVATIONS,
        *CLIMATE_DERIVATIONS.values(),
    }
    missing_columns = sorted(required_columns - set(source_columns))
    if missing_columns:
        raise ValueError(f"raw panel missing required columns: {missing_columns}")

    frame = pd.read_csv(raw, low_memory=False)
    if frame.empty:
        raise ValueError("raw panel must contain at least one row")
    frame[_SOURCE_ROW_COLUMN] = np.arange(1, len(frame) + 1, dtype=np.int64)
    frame[_PARSED_DATE_COLUMN] = pd.to_datetime(frame[DATE_COLUMN], errors="coerce")
    if frame[_PARSED_DATE_COLUMN].isna().any():
        rows = frame.loc[
            frame[_PARSED_DATE_COLUMN].isna(),
            _SOURCE_ROW_COLUMN,
        ].tolist()
        raise ValueError(f"raw panel contains invalid {DATE_COLUMN} values at rows {rows}")
    frame[_NORMALIZED_ADMIN_COLUMN] = frame[ADMIN_COLUMN].map(normalize_admin_code)
    if frame[_NORMALIZED_ADMIN_COLUMN].eq("").any():
        rows = frame.loc[
            frame[_NORMALIZED_ADMIN_COLUMN].eq(""),
            _SOURCE_ROW_COLUMN,
        ].tolist()
        raise ValueError(f"raw panel contains missing {ADMIN_COLUMN} at rows {rows}")
    frame[_FEATURE_MONTH_COLUMN] = frame[_PARSED_DATE_COLUMN].dt.to_period("M")
    frame = frame.sort_values(
        [ADMIN_COLUMN, _PARSED_DATE_COLUMN, _SOURCE_ROW_COLUMN],
        kind="mergesort",
    )

    key_columns = [_NORMALIZED_ADMIN_COLUMN, _FEATURE_MONTH_COLUMN]
    duplicate_rows = frame.duplicated(key_columns, keep=False)
    duplicate_groups: list[dict] = []
    comparison_columns = [
        column
        for column in source_columns
        if column not in COMPARISON_EXCLUDED_COLUMNS
    ]
    for (admin_code, feature_month), group in frame.loc[duplicate_rows].groupby(
        key_columns,
        sort=False,
    ):
        conflicting_columns = [
            column
            for column in comparison_columns
            if not _values_equal(group[column])
        ]
        if conflicting_columns:
            raise ValueError(
                "duplicate normalized area-month conflict for "
                f"{admin_code} + {feature_month}: "
                f"{', '.join(conflicting_columns)}"
            )
        differing_excluded_columns = [
            column
            for column in COMPARISON_EXCLUDED_COLUMNS
            if not _values_equal(group[column])
        ]
        duplicate_groups.append(
            {
                "admin_code": str(admin_code),
                "feature_month": str(feature_month),
                "source_row_numbers": [
                    int(value) for value in group[_SOURCE_ROW_COLUMN].tolist()
                ],
                "group_size": len(group),
                "differing_excluded_columns": differing_excluded_columns,
                "disposition": "collapsed_identical_or_derived_only",
            }
        )

    cleaned = frame.drop_duplicates(key_columns, keep="first").copy()
    for source_name, output_name in CLIMATE_DERIVATIONS.items():
        rolling = pd.to_numeric(cleaned[source_name], errors="coerce").rolling(
            window=ROLLING_WINDOW,
            min_periods=ROLLING_MIN_PERIODS,
        ).mean()
        grouped = rolling.groupby(cleaned[_NORMALIZED_ADMIN_COLUMN], sort=False)
        cleaned[output_name] = (
            rolling - grouped.transform("mean")
        ) / grouped.transform("std", ddof=ZSCORE_DDOF)

    raw_row_count = len(frame)
    normalized_row_count = len(cleaned)
    duplicate_group_count = len(duplicate_groups)
    duplicate_row_count = sum(group["group_size"] for group in duplicate_groups)
    removed_row_count = raw_row_count - normalized_row_count
    latest_feature_month = str(cleaned[_FEATURE_MONTH_COLUMN].max())
    labeled = cleaned[TARGET_COLUMN].fillna("").astype(str).str.strip().ne("")
    if not labeled.any():
        raise ValueError(f"raw panel has no non-null {TARGET_COLUMN} values")
    latest_label_month = str(cleaned.loc[labeled, _FEATURE_MONTH_COLUMN].max())
    output_frame = cleaned.loc[:, source_columns]

    output.parent.mkdir(parents=True, exist_ok=True)
    audit.parent.mkdir(parents=True, exist_ok=True)
    output_created = False
    audit_created = False
    try:
        with output.open("x", encoding="utf-8", newline="") as handle:
            output_created = True
            output_frame.to_csv(handle, index=False)
        payload = {
            "schema_version": NORMALIZATION_SCHEMA_VERSION,
            "normalization_version": NORMALIZATION_VERSION,
            "source_panel": _panel_metadata(
                raw,
                raw_row_count,
                len(source_columns),
            ),
            "output_panel": _panel_metadata(
                output,
                normalized_row_count,
                len(source_columns),
            ),
            "key_columns": [ADMIN_COLUMN, "feature_month"],
            "sort_columns": [ADMIN_COLUMN, DATE_COLUMN, "source_row_number"],
            "comparison_excluded_columns": list(COMPARISON_EXCLUDED_COLUMNS),
            "climate_derivation": {
                **CLIMATE_DERIVATIONS,
                "rolling_order": "global_after_stable_admin_date_sort",
                "window": ROLLING_WINDOW,
                "minimum_periods": ROLLING_MIN_PERIODS,
                "grouping_column": ADMIN_COLUMN,
                "std_ddof": ZSCORE_DDOF,
            },
            "latest_feature_month": latest_feature_month,
            "latest_label_month": latest_label_month,
            "duplicate_group_count": duplicate_group_count,
            "duplicate_row_count": duplicate_row_count,
            "removed_row_count": removed_row_count,
            "conflict_group_count": 0,
            "duplicate_groups": duplicate_groups,
        }
        validate_payload("panel-normalization", payload)
        with audit.open("x", encoding="utf-8", newline="\n") as handle:
            audit_created = True
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except Exception:
        if audit_created:
            audit.unlink(missing_ok=True)
        if output_created:
            output.unlink(missing_ok=True)
        raise

    return PanelNormalizationResult(
        output_panel_path=output,
        audit_path=audit,
        raw_row_count=raw_row_count,
        normalized_row_count=normalized_row_count,
        duplicate_group_count=duplicate_group_count,
        removed_row_count=removed_row_count,
        latest_feature_month=latest_feature_month,
        latest_label_month=latest_label_month,
        output_sha256=payload["output_panel"]["sha256"],
    )


def validate_normalization_audit(audit_path: Path, panel_path: Path) -> dict:
    """Validate an audit contract and prove it matches the supplied panel."""
    audit = Path(audit_path).resolve()
    panel = Path(panel_path).resolve()
    try:
        payload = json.loads(audit.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"normalization audit is not valid JSON: {audit}") from exc
    validate_payload("panel-normalization", payload)
    if payload["schema_version"] != NORMALIZATION_SCHEMA_VERSION:
        raise ValueError("normalization audit schema_version mismatch")
    if payload["normalization_version"] != NORMALIZATION_VERSION:
        raise ValueError("normalization audit normalization_version mismatch")

    duplicate_groups = payload["duplicate_groups"]
    duplicate_group_count = payload["duplicate_group_count"]
    duplicate_row_count = payload["duplicate_row_count"]
    removed_row_count = payload["removed_row_count"]
    if duplicate_group_count != len(duplicate_groups):
        raise ValueError("normalization audit duplicate_group_count invariant failed")
    if duplicate_row_count != sum(group["group_size"] for group in duplicate_groups):
        raise ValueError("normalization audit duplicate_row_count invariant failed")
    if any(
        group["group_size"] != len(group["source_row_numbers"])
        for group in duplicate_groups
    ):
        raise ValueError("normalization audit duplicate source-row invariant failed")
    if removed_row_count != duplicate_row_count - duplicate_group_count:
        raise ValueError("normalization audit removed_row_count invariant failed")
    if (
        payload["source_panel"]["row_count"]
        - payload["output_panel"]["row_count"]
        != removed_row_count
    ):
        raise ValueError("normalization audit panel row_count invariant failed")
    if payload["conflict_group_count"] != 0:
        raise ValueError("normalization audit conflict_group_count must be zero")

    row_count, column_count = _csv_dimensions(panel)
    actual = {
        "sha256": _sha256_file(panel),
        "size_bytes": panel.stat().st_size,
        "row_count": row_count,
        "column_count": column_count,
    }
    expected = payload["output_panel"]
    mismatches = [
        field for field, value in actual.items() if value != expected[field]
    ]
    if mismatches:
        labels = {
            "sha256": "checksum",
            "size_bytes": "size",
            "row_count": "row_count",
            "column_count": "column_count",
        }
        raise ValueError(
            "normalization audit does not match panel "
            f"{panel}: {', '.join(labels[field] for field in mismatches)}"
        )
    return payload
