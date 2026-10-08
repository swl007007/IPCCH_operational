"""Shared platform-independent FEWSNET model-suite contracts."""

from .types import (
    BatchJobRef,
    FeatureContract,
    ObjectRef,
    PartitionStatus,
    RegisteredModelVersion,
    RunPhase,
    SnapshotManifest,
    ThresholdResult,
)

__all__ = [
    "BatchJobRef",
    "FeatureContract",
    "ObjectRef",
    "PartitionStatus",
    "RegisteredModelVersion",
    "RunPhase",
    "SnapshotManifest",
    "ThresholdResult",
]
