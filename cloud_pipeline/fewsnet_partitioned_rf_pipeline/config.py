from pathlib import Path

HORIZON_MONTHS = (0, 6, 12)
HORIZON_KEYS = {0: "0m", 6: "6m", 12: "12m"}
TARGET_COLUMN = "fews_ipc_crisis"
ADMIN_SOURCE_COLUMN = "FEWSNET_admin_code"
ADMIN_CANONICAL_COLUMN = "admin_code"
TRAIN_WINDOW_MONTHS = 36
THRESHOLD_VALIDATION_MONTHS = 6
THRESHOLD_GRID = tuple(round(value / 100, 2) for value in range(5, 96))
PARTITION_MIN_SAMPLES = 50
SMOTE_MAX_NEIGHBORS = 5
PROMOTION_LEASE_SECONDS = 900
RF_PARAMS = {
    "n_estimators": 100,
    "max_depth": None,
    "random_state": 5,
    "n_jobs": 1,
}
# Full-history production fit (2026-10): thresholds are fixed, never searched.
FULL_DATA_THRESHOLDS = {"0m": 0.48, "6m": 0.41, "12m": 0.45}
FULL_DATA_THRESHOLD_SOURCE_SUITE = "local-202604-57cb3b981198-510375f58cd8"
FULL_DATA_TRAINING_REPORT_SCHEMA = "fewsnet-horizon-training-report-full-data-v1"
FIXED_THRESHOLD_REPORT_SCHEMA = "fewsnet-fixed-threshold-report-v1"
FULL_DATA_PACKAGE_SCHEMA = "fewsnet-local-model-package-full-data-v1"
PARENT_MODEL_IDS = {
    "0m": "fewsnet-partitioned-rf-0m",
    "6m": "fewsnet-partitioned-rf-6m",
    "12m": "fewsnet-partitioned-rf-12m",
}
PACKAGE_ROOT = Path(__file__).resolve().parent
PARTITION_ASSET_PATH = PACKAGE_ROOT / (
    "assets/partitions/cluster_mapping_k40_nc17_general_refined_contig3.csv"
)
PARTITION_ASSET_SHA256 = (
    "4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b"
)
FEATURE_CONTRACT_PATH = PACKAGE_ROOT / (
    "assets/feature_contracts/fewsnet_stage3_v1.json"
)
