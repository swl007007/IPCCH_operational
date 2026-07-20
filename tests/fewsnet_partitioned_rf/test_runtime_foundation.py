import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PARTITION = ROOT / (
    "fewsnet_partitioned_rf_pipeline/assets/partitions/"
    "cluster_mapping_k40_nc17_general_refined_contig3.csv"
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
