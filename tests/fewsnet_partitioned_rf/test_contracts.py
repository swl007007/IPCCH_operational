import json
from pathlib import Path

import pytest

from fewsnet_partitioned_rf_pipeline.core.types import ObjectRef, RunPhase
from fewsnet_partitioned_rf_pipeline.schemas import validate_deployment, validate_payload


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/fewsnet_partitioned_rf"


def test_source_snapshot_fixture_validates():
    payload = json.loads((FIXTURES / "source_snapshot_valid.json").read_text())
    validate_payload("source-snapshot", payload)


def test_source_snapshot_requires_immutable_object_generation():
    payload = json.loads((FIXTURES / "source_snapshot_valid.json").read_text())
    payload["panel"].pop("generation")
    with pytest.raises(ValueError, match="generation"):
        validate_payload("source-snapshot", payload)


def test_shared_types_freeze_object_identity_and_run_phases():
    ref = ObjectRef("gs://bucket/object", "7", "a" * 64, 12)
    assert ref.generation == "7"
    assert RunPhase.RELEASED.value == "RELEASED"


def test_deployment_requires_digest_pinned_image_and_matching_digest():
    payload = json.loads((FIXTURES / "deployment_valid.json").read_text())
    validate_deployment(payload)
    payload["container_image_digest"] = "sha256:" + "b" * 64
    with pytest.raises(ValueError, match="container_image_digest"):
        validate_deployment(payload)
