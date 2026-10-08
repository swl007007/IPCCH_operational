from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal


@dataclass(frozen=True)
class ObjectRef:
    uri: str
    generation: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class SnapshotManifest:
    snapshot_id: str
    created_at_utc: str
    snapshot_content_sha256: str
    panel: ObjectRef
    normalization_audit: ObjectRef
    boundaries: ObjectRef
    admin_universe: ObjectRef
    row_count: int
    area_count: int
    spatial_feature_count: int
    crs: str
    latest_feature_month: str
    latest_label_month: str
    source_identity: dict[str, str]
    admin_code_mapping: dict[str, str]


@dataclass(frozen=True)
class FeatureContract:
    schema_version: str
    transformation_version: str
    feature_columns: tuple[str, ...]
    feature_dtypes: tuple[str, ...]
    required_source_columns: tuple[str, ...]
    iso_mapping: dict[str, int]
    source_columns_sha256: str
    feature_schema_sha256: str


PartitionStatus = Literal[
    "partition_model",
    "pooled_unmapped",
    "pooled_small_partition",
    "pooled_single_class",
    "pooled_missing_partition_model",
]


@dataclass(frozen=True)
class ThresholdResult:
    threshold: float
    precision: float | None
    recall: float | None
    f1: float | None
    support: int
    positive_cases: int
    fallback_reason: str | None


@dataclass(frozen=True)
class RegisteredModelVersion:
    horizon_key: str
    parent_model_resource_name: str
    version_resource_name: str
    version_id: str
    suite_version_alias: str
    artifact_uri: str


@dataclass(frozen=True)
class BatchJobRef:
    horizon_key: str
    job_resource_name: str
    model_version_resource_name: str
    input_uri: str
    destination_prefix: str
    gcs_output_directory: str | None = None


class RunPhase(str, Enum):
    DISCOVERED = "DISCOVERED"
    INPUT_VALIDATED = "INPUT_VALIDATED"
    TRAINING = "TRAINING"
    PACKAGED = "PACKAGED"
    REGISTERED_CANDIDATE = "REGISTERED_CANDIDATE"
    BATCH_PREDICTING = "BATCH_PREDICTING"
    OUTPUT_VALIDATED = "OUTPUT_VALIDATED"
    PROMOTING = "PROMOTING"
    RELEASED = "RELEASED"
    NOOP = "NOOP"
    FAILED = "FAILED"
