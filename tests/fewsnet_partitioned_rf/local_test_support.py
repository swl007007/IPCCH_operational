from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from fewsnet_partitioned_rf_pipeline.config import (
    FEATURE_CONTRACT_PATH,
    PARTITION_ASSET_PATH,
    PARTITION_ASSET_SHA256,
)
from fewsnet_partitioned_rf_pipeline.core.inference import PartitionedRFPredictor
from fewsnet_partitioned_rf_pipeline.core.normalization import normalize_panel
from fewsnet_partitioned_rf_pipeline.core.partitions import PartitionMap
from fewsnet_partitioned_rf_pipeline.core.preprocessing import (
    MaxPlusImputer,
    load_feature_contract,
)
from fewsnet_partitioned_rf_pipeline.local.package import LocalPackageMetadata


def _cluster_state() -> dict[str, object]:
    return {
        "status": "pooled_small_partition",
        "sample_count": 4,
        "class_counts": {"0": 2, "1": 2},
        "smote_status": "not_applicable_small_partition",
        "fallback_reason": "sample_count_lt_50",
    }


def _smote_result() -> dict[str, object]:
    return {
        "status": "not_applicable_small_partition",
        "original_class_counts": {"0": 2, "1": 2},
        "resampled_class_counts": None,
        "failure_reason": None,
    }


def _partition_metadata() -> dict[str, object]:
    cluster_state = _cluster_state()
    smote_result = _smote_result()
    return {
        **cluster_state,
        "original_class_counts": smote_result["original_class_counts"],
        "resampled_class_counts": smote_result["resampled_class_counts"],
        "smote_k_neighbors": None,
        "smote_failure_reason": smote_result["failure_reason"],
    }


def build_package_fixture() -> tuple[
    PartitionedRFPredictor,
    LocalPackageMetadata,
    dict[str, object],
]:
    """Return a valid predictor, local metadata, and validated reports."""
    feature_contract = load_feature_contract(FEATURE_CONTRACT_PATH)
    partition_map = PartitionMap.load(
        PARTITION_ASSET_PATH,
        PARTITION_ASSET_SHA256,
    )
    feature_count = len(feature_contract.feature_columns)
    matrix = np.vstack(
        [
            np.zeros(feature_count),
            np.ones(feature_count),
            np.full(feature_count, 2.0),
            np.full(feature_count, 3.0),
        ]
    )
    target = np.asarray([0, 1, 0, 1], dtype=np.int8)
    imputer = MaxPlusImputer(multiplier=100.0).fit(matrix)
    pooled_model = RandomForestClassifier(
        n_estimators=8,
        random_state=5,
        n_jobs=1,
    ).fit(matrix, target)
    cluster_ids = partition_map.cluster_ids
    predictor = PartitionedRFPredictor(
        imputer=imputer,
        pooled_model=pooled_model,
        partition_models={cluster_id: None for cluster_id in cluster_ids},
        partition_status={
            cluster_id: "pooled_small_partition" for cluster_id in cluster_ids
        },
        partition_metadata={
            cluster_id: _partition_metadata() for cluster_id in cluster_ids
        },
        partition_map=dict(partition_map._clusters_by_admin),
        feature_contract=feature_contract,
        threshold=0.51,
        horizon_key="0m",
        horizon_months=0,
        suite_version="",
        vertex_model_resource_name="",
        vertex_model_version_id="",
    )
    metadata = LocalPackageMetadata(
        suite_version="local-202604-111111111111-222222222222",
        feature_month="2026-04",
        target_month="2026-04",
        latest_label_month="2026-02",
        source_git_commit="1" * 40,
        panel_path="/tmp/panel.csv",
        panel_sha256="2" * 64,
        panel_size_bytes=10,
        panel_row_count=20,
        normalization_audit_path="/tmp/panel.audit.json",
        normalization_audit_sha256="3" * 64,
        normalization_audit_size_bytes=11,
    )
    training_report = {
        "schema_version": "fewsnet-horizon-training-report-v1",
        "horizon_key": "0m",
        "horizon_months": 0,
        "feature_schema_sha256": feature_contract.feature_schema_sha256,
        "partition_asset_sha256": PARTITION_ASSET_SHA256,
        "partition_coverage_pct": 100.0,
        "training_target_month_range": {
            "start": "2023-03",
            "end": "2026-02",
        },
        "fit_target_month_range": {
            "start": "2023-03",
            "end": "2025-08",
        },
        "validation_target_month_range": {
            "start": "2025-09",
            "end": "2026-02",
        },
        "sample_count": 100,
        "fit_sample_count": 80,
        "validation_sample_count": 20,
        "pooled_class_counts": {"0": 50, "1": 50},
        "cluster_states": {
            str(cluster_id): _cluster_state() for cluster_id in cluster_ids
        },
        "smote_results": {
            str(cluster_id): _smote_result() for cluster_id in cluster_ids
        },
        "fallback_counts": {
            "pooled_unmapped": 0,
            "pooled_small_partition": len(cluster_ids),
            "pooled_single_class": 0,
            "pooled_missing_partition_model": 0,
        },
    }
    threshold_report = {
        "threshold": 0.51,
        "precision": 0.75,
        "recall": 0.6,
        "f1": 2 * 0.75 * 0.6 / (0.75 + 0.6),
        "support": 20,
        "positive_cases": 8,
        "fallback_reason": None,
    }
    reports = {
        "training_report": training_report,
        "threshold_report": threshold_report,
    }
    return predictor, metadata, reports


def write_normalized_local_panel_fixture(
    root: Path,
) -> tuple[Path, Path, pd.DataFrame]:
    root.mkdir(parents=True, exist_ok=False)
    contract = load_feature_contract(FEATURE_CONTRACT_PATH)
    source_columns = list(contract.required_source_columns)
    periods = pd.period_range("2022-03", "2026-04", freq="M")
    rows: list[dict[str, object]] = []
    admin_rows = (
        ("0", 9.551002, 29.130297, "Country A", "A1", "A2", "A3"),
        ("1", 9.786447, 28.414507, "Country A", "A1", "B2", "B3"),
        ("2", 7.799214, 32.853080, "Country B", "C1", "C2", "C3"),
        ("3", 8.417933, 26.895620, "Country B", "C1", "D2", "D3"),
    )
    for area_index, values in enumerate(admin_rows):
        admin_code, lat, lon, admin0, admin1, admin2, admin3 = values
        for month_index, period in enumerate(periods):
            row = {
                name: float((column_index % 13) + 1) + month_index / 1000
                for column_index, name in enumerate(source_columns)
            }
            has_label = period <= pd.Period("2026-02", freq="M")
            row.update(
                {
                    "FEWSNET_admin_code": admin_code,
                    "ISO": "SS",
                    "lat": lat,
                    "lon": lon,
                    "month": period.month,
                    "fews_ipc": float(2 + ((month_index + area_index) % 2)),
                    "fews_ipc_crisis": (
                        float((month_index + area_index) % 2)
                        if has_label
                        else None
                    ),
                    "date": period.to_timestamp().strftime("%Y-%m-%d"),
                    "pop": (
                        float(1000 + area_index * 100)
                        if area_index < 2
                        and period <= pd.Period("2024-10", freq="M")
                        else None
                    ),
                    "ADMIN0": admin0,
                    "ADMIN1": admin1,
                    "ADMIN2": admin2,
                    "ADMIN3": admin3,
                    "ISO3": "SSD",
                }
            )
            rows.append(row)

    raw_identity_columns = (
        "FEWSNET_admin_code",
        "ISO",
        "lat",
        "lon",
        "month",
        "fews_ipc",
        "fews_ipc_crisis",
        "date",
        "pop",
        "ADMIN0",
        "ADMIN1",
        "ADMIN2",
        "ADMIN3",
        "ISO3",
    )
    raw_columns = [
        *raw_identity_columns,
        *(name for name in source_columns if name not in raw_identity_columns),
    ]
    raw_frame = pd.DataFrame(rows, columns=raw_columns)
    raw_path = root / "panel.raw.csv"
    normalized_path = root / "panel.normalized-v1.csv"
    audit_path = root / "panel.normalized-v1.audit.json"
    raw_frame.to_csv(raw_path, index=False, lineterminator="\n")
    normalize_panel(raw_path, normalized_path, audit_path)
    return normalized_path, audit_path, raw_frame
