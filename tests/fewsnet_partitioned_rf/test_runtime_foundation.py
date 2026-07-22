import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PARTITION = ROOT / (
    "fewsnet_partitioned_rf_pipeline/assets/partitions/"
    "cluster_mapping_k40_nc17_general_refined_contig3.csv"
)
FEATURE_CONTRACT = ROOT / (
    "fewsnet_partitioned_rf_pipeline/assets/feature_contracts/"
    "fewsnet_stage3_v1.json"
)


def test_dedicated_requirements_pin_model_serialization_stack():
    requirements = (ROOT / "requirements-fewsnet-partitioned-rf.txt").read_text()
    for requirement in (
        "scikit-learn==1.8.0",
        "joblib==1.5.3",
        "imbalanced-learn==0.14.0",
        "fastapi==0.116.1",
        "uvicorn==0.35.0",
        "geopandas==1.1.1",
        "pyarrow==20.0.0",
        "google-cloud-aiplatform==1.161.0",
        "google-cloud-storage==3.13.0",
        "jsonschema==4.26.0",
        "pytest==9.1.1",
    ):
        assert requirement in requirements
    assert "-r requirements-cloud.txt" not in requirements


def test_fixed_partition_asset_has_approved_identity():
    digest = hashlib.sha256(PARTITION.read_bytes()).hexdigest()
    assert digest == "4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b"
    manifest = json.loads(PARTITION.with_name("partition_manifest.json").read_text())
    assert manifest["mapped_area_count"] == 5365
    assert manifest["cluster_ids"] == list(range(17))
    assert manifest["sha256"] == digest


def test_fixed_feature_contract_has_approved_identity():
    digest = hashlib.sha256(FEATURE_CONTRACT.read_bytes()).hexdigest()
    assert digest == "3779c6bcde70560c0e1514c563ced6e7bd559c6d352689398c3cecb93d44a67b"
    contract = json.loads(FEATURE_CONTRACT.read_text(encoding="utf-8"))
    features = contract["feature_columns"]

    assert contract["feature_schema_sha256"] == (
        "6e6f0bdc2df7bb40ec37f2d44926d2a24fbb746bc5272ed9b93a7ae4047d891b"
    )
    assert len(features) == 123
    assert len(features) == len(set(features))
    for required in (
        "FEWSNET_admin_code",
        "lat",
        "lon",
        "month",
        "fews_ha",
        "fews_ipc_crisis_lag_4",
        "fews_ipc_lag_12",
        "WFP_Price_m4",
        "WFP_Price_m12",
        "nightlight_m12",
        "EVI_l12",
    ):
        assert required in features
    for excluded in ("fews_ipc_crisis", "fews_ipc", "fews_proj_med"):
        assert excluded not in features
