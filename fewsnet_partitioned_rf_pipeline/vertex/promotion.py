"""Serialized, reversible publication of one validated FEWSNET model suite."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any, Protocol

from google.api_core.exceptions import NotFound
from google.cloud import aiplatform

from fewsnet_partitioned_rf_pipeline.config import (
    HORIZON_KEYS,
    PARTITION_ASSET_SHA256,
    PROMOTION_LEASE_SECONDS,
)
from fewsnet_partitioned_rf_pipeline.core import (
    ObjectRef,
    RegisteredModelVersion,
    SnapshotManifest,
)
from fewsnet_partitioned_rf_pipeline.schemas import validate_payload
from fewsnet_partitioned_rf_pipeline.vertex.registry import (
    suite_version_alias,
)
from fewsnet_partitioned_rf_pipeline.vertex.storage import (
    ArtifactStore,
    GenerationConflict,
    put_immutable_or_verify,
    put_mutable_or_verify,
)


HORIZON_ORDER = tuple(HORIZON_KEYS[months] for months in sorted(HORIZON_KEYS))
LEASE_RELATIVE_URI = "locks/production-promotion.json"
CURRENT_RELATIVE_URI = "released/current.json"
LEASE_FIELDS = {
    "lease_id",
    "run_id",
    "status",
    "acquired_at_utc",
    "expires_at_utc",
}
MONTH_PATTERN = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")
VERSION_RESOURCE_PATTERN = re.compile(r"^(.+)@([0-9]+)$")


class PromotionBusy(RuntimeError):
    """Retryable signal that another promotion owns the production lease."""

    retryable = True


class PromotionError(RuntimeError):
    """Promotion failed, including any rollback or lease-release failures."""

    def __init__(
        self,
        original_error: BaseException | str,
        rollback_failures: tuple[str, ...] = (),
        warnings: tuple[str, ...] = (),
    ) -> None:
        self.original_error = original_error
        self.rollback_failures = rollback_failures
        self.warnings = warnings
        rollback_text = (
            "; ".join(rollback_failures) if rollback_failures else "none"
        )
        warning_text = "; ".join(warnings) if warnings else "none"
        super().__init__(
            f"promotion failed: {original_error}; "
            f"rollback failures: {rollback_text}; warnings: {warning_text}"
        )


@dataclass(frozen=True)
class PromotionLease:
    """One generation-pinned ownership record for production publication."""

    uri: str
    ref: ObjectRef
    payload: dict[str, str]


@dataclass(frozen=True)
class _CapturedObject:
    uri: str
    generation: str
    data: bytes | None


class AliasBackend(Protocol):
    """Narrow boundary for reading, moving, and restoring one version alias."""

    def current_version(self, parent: str, alias: str) -> str | None: ...

    def move_alias(
        self,
        parent: str,
        alias: str,
        target_version: str,
    ) -> None: ...

    def restore_alias(
        self,
        parent: str,
        alias: str,
        previous_version: str | None,
    ) -> None: ...


class VertexAliasBackend:
    """Pinned ``google-cloud-aiplatform`` Model Registry alias adapter."""

    def __init__(self, *, sdk: Any = aiplatform):
        self.sdk = sdk

    def current_version(self, parent: str, alias: str) -> str | None:
        registry = self.sdk.ModelRegistry(parent)
        try:
            info = registry.get_version_info(alias)
        except NotFound:
            return None
        if getattr(info, "model_resource_name", None) != parent:
            raise PromotionError(
                "Vertex alias resolved to a different parent model"
            )
        version_id = str(getattr(info, "version_id", ""))
        if not version_id.isdigit():
            raise PromotionError("Vertex alias resolved to a non-numeric version")
        return f"{parent}@{version_id}"

    def move_alias(
        self,
        parent: str,
        alias: str,
        target_version: str,
    ) -> None:
        version_id = _version_id(parent, target_version)
        self.sdk.ModelRegistry(parent).add_version_aliases(
            [alias],
            version=version_id,
        )

    def restore_alias(
        self,
        parent: str,
        alias: str,
        previous_version: str | None,
    ) -> None:
        registry = self.sdk.ModelRegistry(parent)
        if previous_version is None:
            current = self.current_version(parent, alias)
            if current is None:
                return
            registry.remove_version_aliases(
                [alias],
                version=_version_id(parent, current),
            )
            return
        registry.add_version_aliases(
            [alias],
            version=_version_id(parent, previous_version),
        )


def acquire_promotion_lease(
    *,
    store: ArtifactStore,
    root_uri: str,
    run_id: str,
    lease_id: str,
    utc_now: Callable[[], datetime],
    lease_seconds: int = PROMOTION_LEASE_SECONDS,
) -> PromotionLease:
    """Acquire or generation-safely take over the production promotion lease."""
    root = _root_uri(root_uri)
    _required_string("run_id", run_id)
    _required_string("lease_id", lease_id)
    if not callable(utc_now):
        raise TypeError("utc_now must be callable")
    if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int):
        raise TypeError("lease_seconds must be an integer")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    now = _utc_datetime(utc_now(), "utc_now")
    uri = f"{root}/{LEASE_RELATIVE_URI}"
    existing = _capture_optional(store, uri)
    if existing.data is not None:
        existing_payload = _lease_json(existing.data)
        expires_at = _parse_timestamp(
            existing_payload["expires_at_utc"],
            "lease.expires_at_utc",
        )
        if (
            existing_payload["status"] == "acquired"
            and expires_at > now
        ):
            if (
                existing_payload["lease_id"] == lease_id
                and existing_payload["run_id"] == run_id
            ):
                return PromotionLease(
                    uri=uri,
                    ref=store.get_ref(uri),
                    payload=existing_payload,
                )
            raise PromotionBusy(
                "production promotion lease is held by "
                f"run {existing_payload['run_id']} until "
                f"{existing_payload['expires_at_utc']}"
            )
    payload = {
        "lease_id": lease_id,
        "run_id": run_id,
        "status": "acquired",
        "acquired_at_utc": _timestamp(now),
        "expires_at_utc": _timestamp(
            now + timedelta(seconds=lease_seconds)
        ),
    }
    try:
        ref = put_mutable_or_verify(
            store,
            uri,
            _canonical_json(payload),
            expected_generation=existing.generation,
        )
    except GenerationConflict as exc:
        raise PromotionBusy(
            "production promotion lease changed during acquisition"
        ) from exc
    return PromotionLease(uri=uri, ref=ref, payload=payload)


def release_promotion_lease(
    *,
    store: ArtifactStore,
    lease: PromotionLease,
) -> ObjectRef:
    """Release only the lease whose current generation still names this owner."""
    if not isinstance(lease, PromotionLease):
        raise TypeError("lease must be a PromotionLease")
    current = _capture_optional(store, lease.uri)
    if current.data is None:
        raise PromotionError("promotion lease ownership was lost: object missing")
    payload = _lease_json(current.data)
    if (
        payload["lease_id"] != lease.payload["lease_id"]
        or payload["run_id"] != lease.payload["run_id"]
    ):
        raise PromotionError("promotion lease ownership was lost")
    if payload["status"] == "released":
        return store.get_ref(lease.uri)
    if payload["status"] != "acquired":
        raise PromotionError(
            f"promotion lease has invalid status: {payload['status']}"
        )
    released = dict(payload)
    released["status"] = "released"
    try:
        return put_mutable_or_verify(
            store,
            lease.uri,
            _canonical_json(released),
            expected_generation=current.generation,
        )
    except GenerationConflict as exc:
        raise PromotionError(
            "promotion lease ownership was lost during release"
        ) from exc


def promote_and_publish(
    *,
    store: ArtifactStore,
    alias_backend: AliasBackend,
    root_uri: str,
    run_id: str,
    snapshot: SnapshotManifest,
    registered_versions: Mapping[str, RegisteredModelVersion],
    suite_manifest: Mapping[str, Any],
    lease_id: str,
    utc_now: Callable[[], datetime],
    lease_seconds: int = PROMOTION_LEASE_SECONDS,
) -> dict[str, Any]:
    """Move all production aliases reversibly and publish current last."""
    root = _root_uri(root_uri)
    manifest = _validated_suite_manifest(
        suite_manifest,
        snapshot=snapshot,
        registered_versions=registered_versions,
    )
    lease = acquire_promotion_lease(
        store=store,
        root_uri=root,
        run_id=run_id,
        lease_id=lease_id,
        utc_now=utc_now,
        lease_seconds=lease_seconds,
    )
    warnings: list[str] = []
    result: dict[str, Any] | None = None
    failure: PromotionError | None = None
    previous_aliases: dict[str, str | None] = {}
    attempted_aliases: list[str] = []
    previous_month: _CapturedObject | None = None
    written_month_ref: ObjectRef | None = None
    try:
        current_uri = f"{root}/{CURRENT_RELATIVE_URI}"
        previous_current = _capture_optional(store, current_uri)
        current_payload = _optional_pointer_json(previous_current.data)
        if current_payload is not None:
            if (
                current_payload["snapshot_content_sha256"]
                == snapshot.snapshot_content_sha256
            ):
                result = {
                    "status": "NOOP",
                    "abandon_candidates": True,
                    "current_pointer": (
                        store.get_ref(current_uri)
                        if previous_current.data is not None
                        else None
                    ),
                    "warnings": warnings,
                }
            elif current_payload["feature_month"] > snapshot.latest_feature_month:
                raise PromotionError(
                    "current production has a newer feature month"
                )
        if result is None:
            feature_month = snapshot.latest_feature_month
            month_uri = (
                f"{root}/released/{feature_month}/"
                "production_suite_manifest.json"
            )
            previous_month = _capture_optional(store, month_uri)
            for horizon_key in HORIZON_ORDER:
                version = registered_versions[horizon_key]
                previous = alias_backend.current_version(
                    version.parent_model_resource_name,
                    "production",
                )
                _validate_optional_alias_version(
                    version.parent_model_resource_name,
                    previous,
                )
                previous_aliases[horizon_key] = previous
            for horizon_key in HORIZON_ORDER:
                version = registered_versions[horizon_key]
                if previous_aliases[horizon_key] == version.version_resource_name:
                    continue
                attempted_aliases.append(horizon_key)
                alias_backend.move_alias(
                    version.parent_model_resource_name,
                    "production",
                    version.version_resource_name,
                )

            suite_uri = (
                f"{root}/suites/{manifest['suite_version']}/suite_manifest.json"
            )
            suite_ref = put_immutable_or_verify(
                store,
                suite_uri,
                _canonical_json(manifest),
            )
            pointer = _production_pointer(manifest, suite_ref)
            pointer_bytes = _canonical_json(pointer)
            written_month_ref = _put_mutable_or_reconcile(
                store,
                month_uri,
                pointer_bytes,
                expected_generation=previous_month.generation,
            )
            current_ref = _put_mutable_or_reconcile(
                store,
                current_uri,
                pointer_bytes,
                expected_generation=previous_current.generation,
            )
            result = {
                "status": "RELEASED",
                "abandon_candidates": False,
                "suite_manifest": suite_ref,
                "month_pointer": written_month_ref,
                "current_pointer": current_ref,
                "warnings": warnings,
            }
    except Exception as exc:
        rollback_failures = _rollback_aliases(
            store,
            lease,
            utc_now,
            alias_backend,
            registered_versions,
            previous_aliases,
            attempted_aliases,
        )
        if (
            previous_month is not None
            and previous_month.data is not None
            and written_month_ref is not None
        ):
            try:
                _assert_active_lease_owner(store, lease, utc_now)
                _put_mutable_or_reconcile(
                    store,
                    previous_month.uri,
                    previous_month.data,
                    expected_generation=written_month_ref.generation,
                )
            except Exception as restore_exc:
                rollback_failures.append(
                    "month pointer restore skipped or failed: "
                    f"{restore_exc}"
                )
        failure = PromotionError(exc, tuple(rollback_failures))
    finally:
        try:
            release_promotion_lease(store=store, lease=lease)
        except Exception as release_exc:
            warning = f"promotion lease release warning: {release_exc}"
            warnings.append(warning)
            if failure is not None:
                failure = PromotionError(
                    failure.original_error,
                    failure.rollback_failures,
                    tuple(warnings),
                )
    if failure is not None:
        raise failure
    if result is None:
        raise PromotionError("promotion ended without a result")
    return result


def _validated_suite_manifest(
    value: Mapping[str, Any],
    *,
    snapshot: SnapshotManifest,
    registered_versions: Mapping[str, RegisteredModelVersion],
) -> dict[str, Any]:
    if not isinstance(snapshot, SnapshotManifest):
        raise TypeError("snapshot must be a SnapshotManifest")
    if not isinstance(value, Mapping):
        raise TypeError("suite_manifest must be a mapping")
    if not isinstance(registered_versions, Mapping):
        raise TypeError("registered_versions must be a mapping")
    if set(registered_versions) != set(HORIZON_ORDER):
        raise ValueError("registered_versions horizon keys differ")
    manifest = dict(value)
    validate_payload("suite-manifest", manifest)
    if manifest["feature_month"] != snapshot.latest_feature_month:
        raise ValueError("suite manifest feature month does not match snapshot")
    snapshot_ref = manifest["snapshot_ref"]
    if snapshot_ref["snapshot_id"] != snapshot.snapshot_id:
        raise ValueError("suite manifest snapshot ID does not match")
    if (
        snapshot_ref["snapshot_content_sha256"]
        != snapshot.snapshot_content_sha256
    ):
        raise ValueError("suite manifest snapshot digest does not match")
    if manifest["partition"]["sha256"] != PARTITION_ASSET_SHA256:
        raise ValueError("suite manifest partition digest does not match")
    expected_alias = suite_version_alias(manifest["suite_version"])
    for horizon_key in HORIZON_ORDER:
        version = registered_versions[horizon_key]
        if not isinstance(version, RegisteredModelVersion):
            raise TypeError(
                "registered_versions must contain RegisteredModelVersion instances"
            )
        if version.horizon_key != horizon_key:
            raise ValueError("registered version horizon does not match its key")
        _version_id(
            version.parent_model_resource_name,
            version.version_resource_name,
        )
        if version.version_id != _version_id(
            version.parent_model_resource_name,
            version.version_resource_name,
        ):
            raise ValueError("registered version numeric identity is inconsistent")
        if version.suite_version_alias != expected_alias:
            raise ValueError("registered version suite alias does not match")
        if manifest["model_versions"][horizon_key] != asdict(version):
            raise ValueError("suite manifest model version identity does not match")
        alias_state = manifest["alias_state"][horizon_key]
        if alias_state["version_resource_name"] != version.version_resource_name:
            raise ValueError("suite manifest alias target does not match")
    return manifest


def _rollback_aliases(
    store: ArtifactStore,
    lease: PromotionLease,
    utc_now: Callable[[], datetime],
    alias_backend: AliasBackend,
    registered_versions: Mapping[str, RegisteredModelVersion],
    previous_aliases: Mapping[str, str | None],
    attempted_aliases: list[str],
) -> list[str]:
    failures: list[str] = []
    for horizon_key in reversed(attempted_aliases):
        version = registered_versions[horizon_key]
        try:
            _assert_active_lease_owner(store, lease, utc_now)
        except Exception as exc:
            failures.append(
                f"{horizon_key} alias restore skipped: {exc}"
            )
            break
        try:
            alias_backend.restore_alias(
                version.parent_model_resource_name,
                "production",
                previous_aliases[horizon_key],
            )
        except Exception as exc:
            failures.append(f"{horizon_key} alias restore failed: {exc}")
    return failures


def _assert_active_lease_owner(
    store: ArtifactStore,
    lease: PromotionLease,
    utc_now: Callable[[], datetime],
) -> ObjectRef:
    try:
        ref = store.get_ref(lease.uri)
        data = store.read_bytes(lease.uri, generation=ref.generation)
        payload = _lease_json(data)
    except Exception as exc:
        raise PromotionError(
            "promotion lease ownership was lost: object is unreadable"
        ) from exc
    if (
        payload["lease_id"] != lease.payload["lease_id"]
        or payload["run_id"] != lease.payload["run_id"]
    ):
        raise PromotionError("promotion lease ownership was lost")
    if payload["status"] != "acquired":
        raise PromotionError(
            "promotion lease ownership was lost: lease is not acquired"
        )
    now = _utc_datetime(utc_now(), "utc_now")
    expires_at = _parse_timestamp(
        payload["expires_at_utc"],
        "lease.expires_at_utc",
    )
    if expires_at <= now:
        raise PromotionError(
            "promotion lease ownership was lost: lease expired"
        )
    return ref


def _put_mutable_or_reconcile(
    store: ArtifactStore,
    uri: str,
    data: bytes,
    *,
    expected_generation: str,
) -> ObjectRef:
    try:
        return put_mutable_or_verify(
            store,
            uri,
            data,
            expected_generation=expected_generation,
        )
    except Exception as write_exc:
        try:
            ref = store.get_ref(uri)
            observed = store.read_bytes(uri, generation=ref.generation)
        except Exception:
            raise write_exc
        if observed == data:
            return ref
        raise write_exc


def _capture_optional(store: ArtifactStore, uri: str) -> _CapturedObject:
    try:
        ref = store.get_ref(uri)
    except FileNotFoundError:
        return _CapturedObject(uri=uri, generation="0", data=None)
    data = store.read_bytes(uri, generation=ref.generation)
    return _CapturedObject(uri=uri, generation=ref.generation, data=data)


def _lease_json(data: bytes) -> dict[str, str]:
    payload = _json_mapping(data, "promotion lease")
    if set(payload) != LEASE_FIELDS:
        raise PromotionError("promotion lease fields differ from the contract")
    if not all(isinstance(payload[field], str) for field in LEASE_FIELDS):
        raise PromotionError("promotion lease fields must be strings")
    if payload["status"] not in {"acquired", "released"}:
        raise PromotionError("promotion lease status is invalid")
    _parse_timestamp(payload["acquired_at_utc"], "lease.acquired_at_utc")
    _parse_timestamp(payload["expires_at_utc"], "lease.expires_at_utc")
    return {field: payload[field] for field in payload}


def _optional_pointer_json(data: bytes | None) -> dict[str, Any] | None:
    if data is None:
        return None
    payload = _json_mapping(data, "production suite pointer")
    required = {
        "schema_version",
        "suite_version",
        "feature_month",
        "snapshot_content_sha256",
        "suite_manifest",
        "released_at_utc",
    }
    if set(payload) != required:
        raise PromotionError("production suite pointer fields differ")
    if payload["schema_version"] != "fewsnet-production-suite-pointer-v1":
        raise PromotionError("production suite pointer schema version is invalid")
    if (
        not isinstance(payload["feature_month"], str)
        or MONTH_PATTERN.fullmatch(payload["feature_month"]) is None
    ):
        raise PromotionError("production suite pointer feature month is invalid")
    digest = payload["snapshot_content_sha256"]
    if (
        not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
    ):
        raise PromotionError("production suite pointer snapshot digest is invalid")
    return payload


def _production_pointer(
    manifest: Mapping[str, Any],
    suite_ref: ObjectRef,
) -> dict[str, Any]:
    return {
        "schema_version": "fewsnet-production-suite-pointer-v1",
        "suite_version": manifest["suite_version"],
        "feature_month": manifest["feature_month"],
        "snapshot_content_sha256": manifest["snapshot_ref"][
            "snapshot_content_sha256"
        ],
        "suite_manifest": asdict(suite_ref),
        "released_at_utc": manifest["released_at_utc"],
    }


def _json_mapping(data: bytes, name: str) -> dict[str, Any]:
    try:
        payload = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PromotionError(f"{name} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise PromotionError(f"{name} must be a JSON object")
    return payload


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _validate_optional_alias_version(
    parent: str,
    version_resource: str | None,
) -> None:
    if version_resource is not None:
        _version_id(parent, version_resource)


def _version_id(parent: str, version_resource: str) -> str:
    match = VERSION_RESOURCE_PATTERN.fullmatch(version_resource)
    if match is None or match.group(1) != parent:
        raise PromotionError(
            "model version resource must equal parent@numeric-version"
        )
    return match.group(2)


def _root_uri(value: object) -> str:
    root = _required_string("root_uri", value).rstrip("/")
    if re.fullmatch(r"gs://[^/]+/.+", root) is None:
        raise ValueError("root_uri must be a gs://bucket/prefix URI")
    return root


def _required_string(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value


def _utc_datetime(value: object, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must return a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise PromotionError(f"{name} must be a timestamp string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise PromotionError(f"{name} is invalid") from exc
    return _utc_datetime(parsed, name)
