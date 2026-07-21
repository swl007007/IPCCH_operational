from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from fewsnet_partitioned_rf_pipeline.config import (
    PARTITION_ASSET_SHA256,
)
from fewsnet_partitioned_rf_pipeline.core import (
    ObjectRef,
    RegisteredModelVersion,
    SnapshotManifest,
)
from fewsnet_partitioned_rf_pipeline.core.inference import (
    FORMAL_PREDICTION_COLUMNS,
)
from fewsnet_partitioned_rf_pipeline.core.validation import (
    PredictionSuiteEntry,
    validate_prediction_suite,
)
from fewsnet_partitioned_rf_pipeline.vertex.promotion import (
    PromotionBusy,
    PromotionError,
    VertexAliasBackend,
    acquire_promotion_lease,
    promote_and_publish,
    release_promotion_lease,
)
from fewsnet_partitioned_rf_pipeline.vertex.registry import (
    suite_version_alias,
)
from fewsnet_partitioned_rf_pipeline.vertex.storage import (
    LocalArtifactStore,
)


ROOT_URI = "gs://test-bucket/fewsnet"
RUN_ID = "run-17"
SUITE_VERSION = "fewsnet-prf-202604-test"
SOURCE_COMMIT = "a" * 40
SNAPSHOT_DIGEST = "b" * 64
IMAGE_DIGEST = "sha256:" + "c" * 64
IMAGE_URI = f"us-central1-docker.pkg.dev/p/r/i@{IMAGE_DIGEST}"
NOW = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
HORIZON_MONTHS = {"0m": 0, "6m": 6, "12m": 12}
HORIZON_ORDER = ("0m", "6m", "12m")
BATCH_DIGESTS = {"0m": "6" * 64, "6m": "7" * 64, "12m": "8" * 64}
PREDICTION_DIGESTS = {
    "0m": "d" * 64,
    "6m": "e" * 64,
    "12m": "f" * 64,
}


def _ref(uri: str, digest: str = "d" * 64, generation: str = "7") -> ObjectRef:
    return ObjectRef(
        uri=uri,
        generation=generation,
        sha256=digest,
        size_bytes=123,
    )


def _snapshot(
    *,
    area_count: int = 3,
    latest_feature_month: str = "2026-04",
    snapshot_digest: str = SNAPSHOT_DIGEST,
) -> SnapshotManifest:
    return SnapshotManifest(
        snapshot_id="fewsnet-202604-test",
        created_at_utc="2026-07-20T00:00:00Z",
        snapshot_content_sha256=snapshot_digest,
        panel=_ref(f"{ROOT_URI}/inputs/panel.csv", "1" * 64),
        normalization_audit=_ref(
            f"{ROOT_URI}/inputs/normalization-audit.json",
            "2" * 64,
        ),
        boundaries=_ref(f"{ROOT_URI}/inputs/boundaries.parquet", "3" * 64),
        admin_universe=_ref(
            f"{ROOT_URI}/inputs/admin-universe.csv",
            "4" * 64,
        ),
        row_count=area_count * 24,
        area_count=area_count,
        spatial_feature_count=area_count,
        crs="EPSG:4326",
        latest_feature_month=latest_feature_month,
        latest_label_month="2026-02",
        source_identity={"panel_source_type": "test"},
        admin_code_mapping={
            "panel": "FEWSNET_admin_code",
            "boundaries": "admin_code",
            "canonical": "admin_code",
        },
    )


def _registered_versions(
    suite_version: str = SUITE_VERSION,
) -> dict[str, RegisteredModelVersion]:
    versions: dict[str, RegisteredModelVersion] = {}
    for index, horizon_key in enumerate(HORIZON_ORDER, start=101):
        parent = (
            "projects/test/locations/us-central1/models/"
            f"fewsnet-partitioned-rf-{horizon_key}"
        )
        versions[horizon_key] = RegisteredModelVersion(
            horizon_key=horizon_key,
            parent_model_resource_name=parent,
            version_resource_name=f"{parent}@{index}",
            version_id=str(index),
            suite_version_alias=suite_version_alias(suite_version),
            artifact_uri=(
                f"{ROOT_URI}/suites/{suite_version}/models/{horizon_key}"
            ),
        )
    return versions


def _target_month(feature_month: str, horizon_key: str) -> str:
    return str(
        pd.Period(feature_month, freq="M") + HORIZON_MONTHS[horizon_key]
    )


def _package_manifest(
    snapshot: SnapshotManifest,
    horizon_key: str,
    *,
    suite_version: str = SUITE_VERSION,
) -> dict:
    return {
        "schema_version": "fewsnet-model-package-v1",
        "suite_version": suite_version,
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_content_sha256": snapshot.snapshot_content_sha256,
        "horizon_key": horizon_key,
        "horizon_months": HORIZON_MONTHS[horizon_key],
        "target_month": _target_month(
            snapshot.latest_feature_month,
            horizon_key,
        ),
        "feature_schema_sha256": "5" * 64,
        "partition_sha256": PARTITION_ASSET_SHA256,
        "threshold": 0.5,
        "dependency_versions": {
            "python": "3.11",
            "numpy": "1",
            "pandas": "2",
            "scikit-learn": "1",
            "joblib": "1",
            "imbalanced-learn": "1",
        },
        "source_git_commit": SOURCE_COMMIT,
        "container_image_uri": IMAGE_URI,
        "container_image_digest": IMAGE_DIGEST,
        "training_target_month_range": {
            "start": "2023-05",
            "end": "2026-04",
        },
        "validation_target_month_range": {
            "start": "2025-11",
            "end": "2026-04",
        },
        "files": ["model.joblib"],
        "status": "validated",
    }


def _prediction_frame(
    snapshot: SnapshotManifest,
    version: RegisteredModelVersion,
    admin_codes: list[str],
    *,
    mapped_count: int | None = None,
) -> pd.DataFrame:
    if mapped_count is None:
        mapped_count = len(admin_codes)
    clusters = pd.array(
        [0] * mapped_count + [None] * (len(admin_codes) - mapped_count),
        dtype="Int64",
    )
    sources = ["partition_model"] * mapped_count + [
        "pooled_unmapped"
    ] * (len(admin_codes) - mapped_count)
    probabilities = [
        0.75 if index % 2 == 0 else 0.25
        for index in range(len(admin_codes))
    ]
    return pd.DataFrame(
        {
            "admin_code": admin_codes,
            "feature_month": [snapshot.latest_feature_month] * len(admin_codes),
            "target_month": [
                _target_month(snapshot.latest_feature_month, version.horizon_key)
            ]
            * len(admin_codes),
            "horizon_months": [HORIZON_MONTHS[version.horizon_key]]
            * len(admin_codes),
            "probability_crisis": probabilities,
            "predicted_crisis": [int(value >= 0.5) for value in probabilities],
            "threshold": [0.5] * len(admin_codes),
            "cluster_id": clusters,
            "prediction_source": sources,
            "suite_version": [SUITE_VERSION] * len(admin_codes),
            "vertex_model_resource_name": [version.version_resource_name]
            * len(admin_codes),
            "vertex_model_version_id": [version.version_id] * len(admin_codes),
        },
        columns=list(FORMAL_PREDICTION_COLUMNS),
    )


def _prediction_entries(
    snapshot: SnapshotManifest,
    versions: dict[str, RegisteredModelVersion],
    *,
    admin_codes: list[str] | None = None,
    mapped_count: int | None = None,
) -> dict[str, PredictionSuiteEntry]:
    if admin_codes is None:
        admin_codes = [f"A{index}" for index in range(snapshot.area_count)]
    entries: dict[str, PredictionSuiteEntry] = {}
    for horizon_key in HORIZON_ORDER:
        entries[horizon_key] = PredictionSuiteEntry(
            frame=_prediction_frame(
                snapshot,
                versions[horizon_key],
                admin_codes,
                mapped_count=mapped_count,
            ),
            batch_input=_ref(
                f"{ROOT_URI}/runs/{RUN_ID}/batch_prediction/"
                f"{horizon_key}/input.jsonl",
                digest=BATCH_DIGESTS[horizon_key],
            ),
            batch_snapshot_content_sha256=snapshot.snapshot_content_sha256,
            package_manifest=_package_manifest(snapshot, horizon_key),
        )
    return entries


def _validated_suite(
    *,
    area_count: int = 3,
    mapped_count: int | None = None,
) -> tuple[
    SnapshotManifest,
    dict[str, RegisteredModelVersion],
    dict[str, PredictionSuiteEntry],
]:
    snapshot = _snapshot(area_count=area_count)
    versions = _registered_versions()
    entries = _prediction_entries(
        snapshot,
        versions,
        mapped_count=mapped_count,
    )
    return snapshot, versions, entries


def test_validation_requires_exactly_three_horizons():
    snapshot, versions, entries = _validated_suite()
    entries.pop("12m")

    with pytest.raises(ValueError, match="horizon keys"):
        validate_prediction_suite(entries, snapshot, versions)


def test_validation_rejects_duplicate_admin_code():
    snapshot, versions, entries = _validated_suite()
    frame = entries["0m"].frame.copy()
    frame.loc[1, "admin_code"] = frame.loc[0, "admin_code"]
    entries["0m"] = replace(entries["0m"], frame=frame)

    with pytest.raises(ValueError, match="duplicate admin_code"):
        validate_prediction_suite(entries, snapshot, versions)


def test_validation_accepts_current_5718_area_snapshot_and_reports_fallback_totals():
    snapshot, versions, entries = _validated_suite(
        area_count=5_718,
        mapped_count=5_365,
    )

    result = validate_prediction_suite(entries, snapshot, versions)

    assert list(result["horizons"]) == list(HORIZON_ORDER)
    for horizon_key in HORIZON_ORDER:
        summary = result["horizons"][horizon_key]
        assert summary["row_count"] == 5_718
        assert sum(summary["source_counts"].values()) == 5_718
        assert summary["source_counts"] == {
            "partition_model": 5_365,
            "pooled_unmapped": 353,
            "pooled_small_partition": 0,
            "pooled_single_class": 0,
            "pooled_missing_partition_model": 0,
        }


def test_validation_rejects_different_same_size_admin_universe_across_horizons():
    snapshot, versions, entries = _validated_suite()
    frame = entries["6m"].frame.copy()
    frame.loc[0, "admin_code"] = "DIFFERENT"
    entries["6m"] = replace(entries["6m"], frame=frame)

    with pytest.raises(ValueError, match="admin universe"):
        validate_prediction_suite(entries, snapshot, versions)


def test_validation_rejects_invalid_probability_class_relationship():
    snapshot, versions, entries = _validated_suite()
    frame = entries["0m"].frame.copy()
    frame.loc[0, "predicted_crisis"] = 0
    entries["0m"] = replace(entries["0m"], frame=frame)

    with pytest.raises(ValueError, match="probability.*threshold"):
        validate_prediction_suite(entries, snapshot, versions)


def test_validation_rejects_invalid_route_source_pair():
    snapshot, versions, entries = _validated_suite()
    frame = entries["0m"].frame.copy()
    frame.loc[0, "prediction_source"] = "pooled_unmapped"
    entries["0m"] = replace(entries["0m"], frame=frame)

    with pytest.raises(ValueError, match="route/source"):
        validate_prediction_suite(entries, snapshot, versions)


def test_validation_rejects_partition_coverage_regression():
    snapshot, versions, entries = _validated_suite(
        area_count=100,
        mapped_count=91,
    )

    with pytest.raises(ValueError, match="partition coverage dropped"):
        validate_prediction_suite(entries, snapshot, versions)


def test_validation_rejects_exact_registered_model_version_mismatch():
    snapshot, versions, entries = _validated_suite()
    frame = entries["12m"].frame.copy()
    frame["vertex_model_version_id"] = "999"
    entries["12m"] = replace(entries["12m"], frame=frame)

    with pytest.raises(ValueError, match="registered model version"):
        validate_prediction_suite(entries, snapshot, versions)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("uri", "https://example.test/input.jsonl", "gs://"),
        ("generation", "latest", "numeric generation"),
        ("sha256", "D" * 64, "lowercase SHA-256"),
        ("size_bytes", -1, "non-negative size"),
    ],
)
def test_validation_rejects_invalid_batch_input_object_identity(
    field,
    value,
    message,
):
    snapshot, versions, entries = _validated_suite()
    original = entries["0m"].batch_input
    entries["0m"] = replace(
        entries["0m"],
        batch_input=replace(original, **{field: value}),
    )

    with pytest.raises(ValueError, match=message):
        validate_prediction_suite(entries, snapshot, versions)


def test_validation_rejects_batch_snapshot_digest_mismatch():
    snapshot, versions, entries = _validated_suite()
    entries["0m"] = replace(
        entries["0m"],
        batch_snapshot_content_sha256="e" * 64,
    )

    with pytest.raises(ValueError, match="Batch input snapshot digest"):
        validate_prediction_suite(entries, snapshot, versions)


def test_validation_rejects_package_snapshot_digest_mismatch():
    snapshot, versions, entries = _validated_suite()
    package = dict(entries["0m"].package_manifest)
    package["snapshot_content_sha256"] = "e" * 64
    entries["0m"] = replace(entries["0m"], package_manifest=package)

    with pytest.raises(ValueError, match="package snapshot digest"):
        validate_prediction_suite(entries, snapshot, versions)


class RecordingStore(LocalArtifactStore):
    def __init__(self, root):
        super().__init__(root)
        self.write_order: list[str] = []
        self.fail_uri: str | None = None

    def put_bytes(self, uri, data, *, if_generation_match=None):
        if uri == self.fail_uri:
            raise RuntimeError(f"injected write failure for {uri}")
        ref = super().put_bytes(
            uri,
            data,
            if_generation_match=if_generation_match,
        )
        self.write_order.append(uri)
        return ref


class FakeAliasBackend:
    def __init__(self, versions, *, fail_parent=None):
        self.versions = dict(versions)
        self.fail_parent = fail_parent
        self.current_calls: list[tuple[str, str]] = []
        self.move_calls: list[tuple[str, str, str]] = []
        self.restore_calls: list[tuple[str, str, str | None]] = []

    def current_version(self, parent, alias):
        self.current_calls.append((parent, alias))
        return self.versions.get(parent)

    def move_alias(self, parent, alias, target_version):
        self.move_calls.append((parent, alias, target_version))
        if parent == self.fail_parent:
            raise RuntimeError(f"injected alias failure for {parent}")
        self.versions[parent] = target_version

    def restore_alias(self, parent, alias, previous_version):
        self.restore_calls.append((parent, alias, previous_version))
        self.versions[parent] = previous_version


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _lease_payload(
    *,
    lease_id: str,
    run_id: str = "other-run",
    status: str = "acquired",
    acquired_at: datetime = NOW,
    expires_at: datetime | None = None,
) -> dict:
    if expires_at is None:
        expires_at = NOW + timedelta(minutes=10)
    return {
        "lease_id": lease_id,
        "run_id": run_id,
        "status": status,
        "acquired_at_utc": acquired_at.isoformat().replace("+00:00", "Z"),
        "expires_at_utc": expires_at.isoformat().replace("+00:00", "Z"),
    }


def _suite_manifest(
    snapshot: SnapshotManifest,
    versions: dict[str, RegisteredModelVersion],
    *,
    suite_version: str = SUITE_VERSION,
) -> dict:
    return {
        "schema_version": "fewsnet-suite-manifest-v1",
        "suite_version": suite_version,
        "feature_month": snapshot.latest_feature_month,
        "source_git_commit": SOURCE_COMMIT,
        "snapshot_ref": {
            "manifest": asdict(
                _ref(
                    f"{ROOT_URI}/inputs/snapshots/{snapshot.snapshot_id}/"
                    "source_manifest.json",
                    "9" * 64,
                )
            ),
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_content_sha256": snapshot.snapshot_content_sha256,
        },
        "container_image": {
            "uri": IMAGE_URI,
            "digest": IMAGE_DIGEST,
        },
        "partition": {
            "uri": (
                f"{ROOT_URI}/suites/{suite_version}/models/0m/"
                "cluster_mapping.csv"
            ),
            "sha256": PARTITION_ASSET_SHA256,
        },
        "model_versions": {
            horizon_key: asdict(versions[horizon_key])
            for horizon_key in HORIZON_ORDER
        },
        "predictions": {
            horizon_key: asdict(
                _ref(
                    f"{ROOT_URI}/suites/{suite_version}/predictions/"
                    f"{horizon_key}.csv",
                    digest=PREDICTION_DIGESTS[horizon_key],
                )
            )
            for horizon_key in HORIZON_ORDER
        },
        "alias_state": {
            horizon_key: {
                "alias": "production",
                "version_resource_name": versions[
                    horizon_key
                ].version_resource_name,
            }
            for horizon_key in HORIZON_ORDER
        },
        "released_at_utc": NOW.isoformat().replace("+00:00", "Z"),
    }


def _pointer_payload(
    *,
    suite_version: str,
    feature_month: str,
    snapshot_digest: str,
    suite_manifest_ref: ObjectRef,
) -> dict:
    return {
        "schema_version": "fewsnet-production-suite-pointer-v1",
        "suite_version": suite_version,
        "feature_month": feature_month,
        "snapshot_content_sha256": snapshot_digest,
        "suite_manifest": asdict(suite_manifest_ref),
        "released_at_utc": NOW.isoformat().replace("+00:00", "Z"),
    }


def _promotion_args(store, alias_backend, snapshot, versions, manifest):
    return {
        "store": store,
        "alias_backend": alias_backend,
        "root_uri": ROOT_URI,
        "run_id": RUN_ID,
        "snapshot": snapshot,
        "registered_versions": versions,
        "suite_manifest": manifest,
        "lease_id": "lease-17",
        "utc_now": lambda: NOW,
    }


def test_acquire_rejects_unexpired_competing_lease(tmp_path):
    store = RecordingStore(tmp_path)
    lease_uri = f"{ROOT_URI}/locks/production-promotion.json"
    store.put_bytes(
        lease_uri,
        _json_bytes(_lease_payload(lease_id="other-lease")),
        if_generation_match=0,
    )

    with pytest.raises(PromotionBusy) as exc_info:
        acquire_promotion_lease(
            store=store,
            root_uri=ROOT_URI,
            run_id=RUN_ID,
            lease_id="lease-17",
            utc_now=lambda: NOW,
        )

    assert exc_info.value.retryable is True


@pytest.mark.parametrize(
    "existing_payload",
    [
        _lease_payload(
            lease_id="released-lease",
            status="released",
        ),
        _lease_payload(
            lease_id="expired-lease",
            expires_at=NOW - timedelta(seconds=1),
        ),
    ],
)
def test_acquire_takes_over_released_or_expired_lease(
    tmp_path,
    existing_payload,
):
    store = RecordingStore(tmp_path)
    lease_uri = f"{ROOT_URI}/locks/production-promotion.json"
    store.put_bytes(
        lease_uri,
        _json_bytes(existing_payload),
        if_generation_match=0,
    )

    lease = acquire_promotion_lease(
        store=store,
        root_uri=ROOT_URI,
        run_id=RUN_ID,
        lease_id="lease-17",
        utc_now=lambda: NOW,
    )

    assert lease.ref.generation == "2"
    assert lease.payload["lease_id"] == "lease-17"
    assert lease.payload["status"] == "acquired"


def test_release_refuses_to_overwrite_a_different_lease(tmp_path):
    store = RecordingStore(tmp_path)
    lease = acquire_promotion_lease(
        store=store,
        root_uri=ROOT_URI,
        run_id=RUN_ID,
        lease_id="lease-17",
        utc_now=lambda: NOW,
    )
    store.put_bytes(
        lease.uri,
        _json_bytes(_lease_payload(lease_id="replacement")),
        if_generation_match=lease.ref.generation,
    )

    with pytest.raises(PromotionError, match="lease ownership was lost"):
        release_promotion_lease(store=store, lease=lease)


def test_promotion_moves_initially_absent_aliases_and_writes_current_last(
    tmp_path,
):
    snapshot = _snapshot()
    versions = _registered_versions()
    manifest = _suite_manifest(snapshot, versions)
    store = RecordingStore(tmp_path)
    aliases = FakeAliasBackend(
        {version.parent_model_resource_name: None for version in versions.values()}
    )

    result = promote_and_publish(
        **_promotion_args(store, aliases, snapshot, versions, manifest)
    )

    assert result["status"] == "RELEASED"
    for version in versions.values():
        assert aliases.versions[version.parent_model_resource_name] == (
            version.version_resource_name
        )
    non_lease_writes = [
        uri for uri in store.write_order if "/locks/" not in uri
    ]
    assert non_lease_writes[-1] == f"{ROOT_URI}/released/current.json"
    lease_payload = json.loads(
        store.read_text(f"{ROOT_URI}/locks/production-promotion.json")
    )
    assert lease_payload["status"] == "released"


def test_second_alias_failure_restores_first_alias(tmp_path):
    snapshot = _snapshot()
    versions = _registered_versions()
    manifest = _suite_manifest(snapshot, versions)
    previous = {
        version.parent_model_resource_name: (
            f"{version.parent_model_resource_name}@9"
        )
        for version in versions.values()
    }
    failing_parent = versions["6m"].parent_model_resource_name
    aliases = FakeAliasBackend(previous, fail_parent=failing_parent)
    store = RecordingStore(tmp_path)

    with pytest.raises(PromotionError, match="injected alias failure"):
        promote_and_publish(
            **_promotion_args(store, aliases, snapshot, versions, manifest)
        )

    assert aliases.versions == previous
    assert aliases.restore_calls == [
        (
            versions["0m"].parent_model_resource_name,
            "production",
            previous[versions["0m"].parent_model_resource_name],
        )
    ]
    assert not store.list(f"{ROOT_URI}/suites/{SUITE_VERSION}/")


def test_alias_movement_is_idempotent_when_targets_are_already_production(
    tmp_path,
):
    snapshot = _snapshot()
    versions = _registered_versions()
    manifest = _suite_manifest(snapshot, versions)
    aliases = FakeAliasBackend(
        {
            version.parent_model_resource_name: version.version_resource_name
            for version in versions.values()
        }
    )
    store = RecordingStore(tmp_path)

    result = promote_and_publish(
        **_promotion_args(store, aliases, snapshot, versions, manifest)
    )

    assert result["status"] == "RELEASED"
    assert aliases.move_calls == []
    assert aliases.restore_calls == []


def test_same_month_revision_replaces_month_pointer_by_generation(tmp_path):
    snapshot = _snapshot()
    versions = _registered_versions()
    manifest = _suite_manifest(snapshot, versions)
    store = RecordingStore(tmp_path)
    month_uri = (
        f"{ROOT_URI}/released/{snapshot.latest_feature_month}/"
        "production_suite_manifest.json"
    )
    current_uri = f"{ROOT_URI}/released/current.json"
    old_suite_ref = _ref(
        f"{ROOT_URI}/suites/old-suite/suite_manifest.json",
        "8" * 64,
        "1",
    )
    old_pointer = _pointer_payload(
        suite_version="old-suite",
        feature_month=snapshot.latest_feature_month,
        snapshot_digest="7" * 64,
        suite_manifest_ref=old_suite_ref,
    )
    store.put_bytes(month_uri, _json_bytes(old_pointer), if_generation_match=0)
    store.put_bytes(current_uri, _json_bytes(old_pointer), if_generation_match=0)
    aliases = FakeAliasBackend(
        {version.parent_model_resource_name: None for version in versions.values()}
    )
    store.write_order.clear()

    result = promote_and_publish(
        **_promotion_args(store, aliases, snapshot, versions, manifest)
    )

    assert result["month_pointer"].generation == "2"
    assert result["current_pointer"].generation == "2"
    assert json.loads(store.read_text(month_uri))["suite_version"] == SUITE_VERSION


def test_current_pointer_failure_restores_aliases_and_previous_month_pointer(
    tmp_path,
):
    snapshot = _snapshot()
    versions = _registered_versions()
    manifest = _suite_manifest(snapshot, versions)
    store = RecordingStore(tmp_path)
    month_uri = (
        f"{ROOT_URI}/released/{snapshot.latest_feature_month}/"
        "production_suite_manifest.json"
    )
    current_uri = f"{ROOT_URI}/released/current.json"
    old_suite_ref = _ref(
        f"{ROOT_URI}/suites/old-suite/suite_manifest.json",
        "8" * 64,
        "1",
    )
    old_pointer = _pointer_payload(
        suite_version="old-suite",
        feature_month=snapshot.latest_feature_month,
        snapshot_digest="7" * 64,
        suite_manifest_ref=old_suite_ref,
    )
    old_bytes = _json_bytes(old_pointer)
    store.put_bytes(month_uri, old_bytes, if_generation_match=0)
    store.put_bytes(current_uri, old_bytes, if_generation_match=0)
    previous = {
        version.parent_model_resource_name: (
            f"{version.parent_model_resource_name}@9"
        )
        for version in versions.values()
    }
    aliases = FakeAliasBackend(previous)
    store.fail_uri = current_uri

    with pytest.raises(PromotionError, match="injected write failure") as exc_info:
        promote_and_publish(
            **_promotion_args(store, aliases, snapshot, versions, manifest)
        )

    assert exc_info.value.original_error is not None
    assert aliases.versions == previous
    assert store.read_bytes(current_uri) == old_bytes
    assert store.read_bytes(month_uri) == old_bytes
    assert store.get_ref(month_uri).generation == "3"


def test_same_snapshot_current_pointer_returns_noop_before_alias_reads(tmp_path):
    snapshot = _snapshot()
    versions = _registered_versions()
    manifest = _suite_manifest(snapshot, versions)
    store = RecordingStore(tmp_path)
    current_uri = f"{ROOT_URI}/released/current.json"
    current_pointer = _pointer_payload(
        suite_version="already-released",
        feature_month=snapshot.latest_feature_month,
        snapshot_digest=snapshot.snapshot_content_sha256,
        suite_manifest_ref=_ref(
            f"{ROOT_URI}/suites/already-released/suite_manifest.json"
        ),
    )
    store.put_bytes(
        current_uri,
        _json_bytes(current_pointer),
        if_generation_match=0,
    )
    aliases = FakeAliasBackend({})

    result = promote_and_publish(
        **_promotion_args(store, aliases, snapshot, versions, manifest)
    )

    assert result["status"] == "NOOP"
    assert result["abandon_candidates"] is True
    assert aliases.current_calls == []
    assert aliases.move_calls == []


def test_newer_current_feature_month_fails_closed_before_alias_reads(tmp_path):
    snapshot = _snapshot()
    versions = _registered_versions()
    manifest = _suite_manifest(snapshot, versions)
    store = RecordingStore(tmp_path)
    current_uri = f"{ROOT_URI}/released/current.json"
    current_pointer = _pointer_payload(
        suite_version="newer-suite",
        feature_month="2026-05",
        snapshot_digest="7" * 64,
        suite_manifest_ref=_ref(
            f"{ROOT_URI}/suites/newer-suite/suite_manifest.json"
        ),
    )
    store.put_bytes(
        current_uri,
        _json_bytes(current_pointer),
        if_generation_match=0,
    )
    aliases = FakeAliasBackend({})

    with pytest.raises(PromotionError, match="newer feature month"):
        promote_and_publish(
            **_promotion_args(store, aliases, snapshot, versions, manifest)
        )

    assert aliases.current_calls == []
    assert aliases.move_calls == []


class FakeRegistry:
    def __init__(self, parent):
        self.parent = parent
        self.current_version_id: str | None = None
        self.add_calls: list[tuple[list[str], str]] = []
        self.remove_calls: list[tuple[list[str], str]] = []

    def get_version_info(self, alias):
        if self.current_version_id is None:
            from google.api_core.exceptions import NotFound

            raise NotFound(alias)
        return SimpleNamespace(
            model_resource_name=self.parent,
            version_id=self.current_version_id,
        )

    def add_version_aliases(self, aliases, version):
        self.add_calls.append((aliases, version))
        self.current_version_id = str(version)

    def remove_version_aliases(self, aliases, version):
        self.remove_calls.append((aliases, version))
        self.current_version_id = None


class FakeSDK:
    def __init__(self, registry):
        self.registry = registry

    def ModelRegistry(self, parent):
        assert parent == self.registry.parent
        return self.registry


def test_vertex_alias_adapter_uses_pinned_model_registry_alias_methods():
    parent = "projects/test/locations/us-central1/models/model-0m"
    registry = FakeRegistry(parent)
    backend = VertexAliasBackend(sdk=FakeSDK(registry))

    assert backend.current_version(parent, "production") is None
    backend.move_alias(parent, "production", f"{parent}@17")
    assert registry.add_calls == [(["production"], "17")]
    assert backend.current_version(parent, "production") == f"{parent}@17"
    backend.restore_alias(parent, "production", None)
    assert registry.remove_calls == [(["production"], "17")]
