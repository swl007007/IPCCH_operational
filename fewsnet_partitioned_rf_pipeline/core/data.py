"""Immutable FEWSNET source snapshot inspection and staging."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

import geopandas as gpd
import pandas as pd

from fewsnet_partitioned_rf_pipeline.config import (
    ADMIN_CANONICAL_COLUMN,
    ADMIN_SOURCE_COLUMN,
    TARGET_COLUMN,
)
from fewsnet_partitioned_rf_pipeline.core import ObjectRef, SnapshotManifest
from fewsnet_partitioned_rf_pipeline.schemas import validate_payload
from fewsnet_partitioned_rf_pipeline.vertex.storage import (
    ArtifactStore,
    GenerationConflict,
    put_immutable_or_verify,
    sha256_file,
    upload_file_immutable_or_verify,
)


PANEL_CHUNK_SIZE = 100_000
SNAPSHOT_SCHEMA_VERSION = "fewsnet-source-snapshot-v1"
BOUNDARY_SOURCE_COLUMN = "admin_code"
PANEL_DATE_COLUMN = "date"
ADMIN_CODE_MAPPING = {
    "panel": ADMIN_SOURCE_COLUMN,
    "boundaries": BOUNDARY_SOURCE_COLUMN,
    "canonical": ADMIN_CANONICAL_COLUMN,
}


def normalize_admin_code(value: object) -> str:
    """Return one stable string identity for panel and boundary admin codes."""
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        number = Decimal(text)
    except InvalidOperation:
        return text
    if not number.is_finite() or number != number.to_integral_value():
        return text
    integer = number.to_integral_value()
    return "0" if integer == 0 else format(integer, "f")


def inspect_panel(path: Path) -> dict:
    """Inspect panel identity and latest months without loading all columns."""
    panel_path = Path(path)
    required_columns = [ADMIN_SOURCE_COLUMN, PANEL_DATE_COLUMN, TARGET_COLUMN]
    try:
        chunks = pd.read_csv(
            panel_path,
            usecols=required_columns,
            chunksize=PANEL_CHUNK_SIZE,
            dtype={ADMIN_SOURCE_COLUMN: "string"},
            keep_default_na=False,
        )
    except ValueError as exc:
        raise ValueError(
            f"panel must contain columns {required_columns}: {exc}"
        ) from exc

    row_count = 0
    admin_codes: set[str] = set()
    area_period_keys: set[tuple[str, str]] = set()
    periods: set[pd.Period] = set()
    labeled_periods: set[pd.Period] = set()

    for chunk in chunks:
        codes = chunk[ADMIN_SOURCE_COLUMN].map(normalize_admin_code)
        if codes.eq("").any():
            raise ValueError(f"panel contains missing {ADMIN_SOURCE_COLUMN}")

        dates = pd.to_datetime(chunk[PANEL_DATE_COLUMN], errors="coerce")
        if dates.isna().any():
            raise ValueError(f"panel contains invalid {PANEL_DATE_COLUMN} values")
        monthly_periods = dates.dt.to_period("M")
        labeled = (
            chunk[TARGET_COLUMN]
            .fillna("")
            .astype(str)
            .str.strip()
            .ne("")
        )

        for code, period, has_label in zip(
            codes,
            monthly_periods,
            labeled,
            strict=True,
        ):
            period_text = str(period)
            key = (code, period_text)
            if key in area_period_keys:
                raise ValueError(
                    "duplicate FEWSNET_admin_code + date month: "
                    f"{code} + {period_text}"
                )
            area_period_keys.add(key)
            admin_codes.add(code)
            periods.add(period)
            if has_label:
                labeled_periods.add(period)
        row_count += len(chunk)

    if row_count == 0:
        raise ValueError("panel must contain at least one row")
    if not labeled_periods:
        raise ValueError(f"panel has no non-null {TARGET_COLUMN} values")

    return {
        "row_count": row_count,
        "area_count": len(admin_codes),
        "admin_codes": tuple(sorted(admin_codes)),
        "latest_feature_month": str(max(periods)),
        "latest_label_month": str(max(labeled_periods)),
    }


def normalize_boundaries(path: Path, output_parquet: Path) -> dict:
    """Validate and write deterministic WGS84 boundaries as GeoParquet."""
    boundaries_path = Path(path)
    gdf = gpd.read_file(boundaries_path)
    if BOUNDARY_SOURCE_COLUMN not in gdf.columns:
        raise ValueError(
            f"boundaries must contain {BOUNDARY_SOURCE_COLUMN}"
        )
    if gdf.crs is None or str(gdf.crs).upper() != "EPSG:4326":
        raise ValueError("boundaries CRS must be exactly EPSG:4326")

    normalized = gdf.copy()
    normalized[BOUNDARY_SOURCE_COLUMN] = normalized[
        BOUNDARY_SOURCE_COLUMN
    ].map(normalize_admin_code)
    invalid_admin = normalized[BOUNDARY_SOURCE_COLUMN].eq("")
    invalid_geometry = normalized.geometry.isna()
    duplicate_admin = normalized[BOUNDARY_SOURCE_COLUMN].duplicated(keep=False)
    if (
        len(normalized) == 0
        or invalid_admin.any()
        or invalid_geometry.any()
        or duplicate_admin.any()
    ):
        raise ValueError(
            "boundaries must contain exactly one non-null geometry per "
            "normalized admin_code"
        )

    normalized = normalized.sort_values(
        BOUNDARY_SOURCE_COLUMN,
        kind="mergesort",
    ).reset_index(drop=True)
    target = Path(output_parquet)
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_parquet(target, index=False)
    admin_codes = tuple(normalized[BOUNDARY_SOURCE_COLUMN].tolist())
    return {
        "feature_count": len(normalized),
        "crs": "EPSG:4326",
        "admin_codes": admin_codes,
    }


def _snapshot_semantic_payload(payload: dict) -> dict:
    """Return fields that must agree for an existing snapshot no-op."""
    return {
        "schema_version": payload["schema_version"],
        "snapshot_id": payload["snapshot_id"],
        "snapshot_content_sha256": payload["snapshot_content_sha256"],
        "panel": {
            key: value
            for key, value in payload["panel"].items()
            if key != "generation"
        },
        "boundaries": {
            key: value
            for key, value in payload["boundaries"].items()
            if key != "generation"
        },
        "admin_universe": {
            key: value
            for key, value in payload["admin_universe"].items()
            if key != "generation"
        },
        "row_count": payload["row_count"],
        "area_count": payload["area_count"],
        "spatial_feature_count": payload["spatial_feature_count"],
        "crs": payload["crs"],
        "latest_feature_month": payload["latest_feature_month"],
        "latest_label_month": payload["latest_label_month"],
        "source_types": {
            "panel_source_type": payload["source_identity"]["panel_source_type"],
            "boundaries_source_type": payload["source_identity"][
                "boundaries_source_type"
            ],
        },
        "admin_code_mapping": payload["admin_code_mapping"],
    }


def _manifest_from_payload(payload: dict) -> SnapshotManifest:
    return SnapshotManifest(
        snapshot_id=payload["snapshot_id"],
        created_at_utc=payload["created_at_utc"],
        snapshot_content_sha256=payload["snapshot_content_sha256"],
        panel=ObjectRef(**payload["panel"]),
        boundaries=ObjectRef(**payload["boundaries"]),
        admin_universe=ObjectRef(**payload["admin_universe"]),
        row_count=payload["row_count"],
        area_count=payload["area_count"],
        spatial_feature_count=payload["spatial_feature_count"],
        crs=payload["crs"],
        latest_feature_month=payload["latest_feature_month"],
        latest_label_month=payload["latest_label_month"],
        source_identity=payload["source_identity"],
        admin_code_mapping=payload["admin_code_mapping"],
    )


def _validate_exact_artifact_references(
    store: ArtifactStore,
    payload: dict,
    verification_root: Path,
) -> None:
    for field in ("panel", "boundaries", "admin_universe"):
        reference = ObjectRef(**payload[field])
        verification_path = verification_root / f"{field}.artifact"
        try:
            store.download_file(
                reference.uri,
                verification_path,
                generation=reference.generation,
            )
        except (FileNotFoundError, GenerationConflict, ValueError) as exc:
            raise GenerationConflict(
                "existing snapshot manifest exact artifact reference is "
                f"unreadable: {reference.uri}@{reference.generation}"
            ) from exc
        actual_size = verification_path.stat().st_size
        actual_sha256 = sha256_file(verification_path)
        if actual_size != reference.size_bytes or actual_sha256 != reference.sha256:
            raise GenerationConflict(
                "existing snapshot manifest exact artifact reference does not "
                f"match recorded bytes: {reference.uri}@{reference.generation}"
            )


def _reuse_existing_manifest(
    store: ArtifactStore,
    manifest_ref: ObjectRef,
    expected_payload: dict,
    verification_root: Path,
) -> SnapshotManifest:
    try:
        existing_payload = json.loads(
            store.read_bytes(
                manifest_ref.uri,
                generation=manifest_ref.generation,
            )
        )
        validate_payload("source-snapshot", existing_payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise GenerationConflict(
            f"existing snapshot manifest is invalid: {manifest_ref.uri}"
        ) from exc
    if _snapshot_semantic_payload(existing_payload) != _snapshot_semantic_payload(
        expected_payload
    ):
        raise GenerationConflict(
            "existing snapshot manifest has different content identity: "
            f"{manifest_ref.uri}"
        )
    _validate_exact_artifact_references(
        store,
        existing_payload,
        verification_root,
    )
    return _manifest_from_payload(existing_payload)


def stage_snapshot(
    *,
    panel_path: Path,
    boundaries_path: Path,
    destination_root: str,
    store: ArtifactStore,
    created_at_utc: str,
) -> SnapshotManifest:
    """Validate local bootstrap inputs and stage one immutable snapshot."""
    panel_path = Path(panel_path)
    boundaries_path = Path(boundaries_path)

    with tempfile.TemporaryDirectory(prefix="fewsnet-source-snapshot-") as temp_dir:
        temp_root = Path(temp_dir)
        captured_panel_path = temp_root / "assembled_fewsnet.csv"
        normalized_boundaries_path = temp_root / "admin_boundaries.parquet"
        admin_universe_path = temp_root / "admin_universe.csv"
        shutil.copyfile(panel_path, captured_panel_path)
        panel_info = inspect_panel(captured_panel_path)
        boundary_info = normalize_boundaries(
            boundaries_path,
            normalized_boundaries_path,
        )

        panel_admin_codes = set(panel_info["admin_codes"])
        boundary_admin_codes = set(boundary_info["admin_codes"])
        if panel_admin_codes != boundary_admin_codes:
            missing_from_boundaries = sorted(
                panel_admin_codes - boundary_admin_codes
            )
            missing_from_panel = sorted(boundary_admin_codes - panel_admin_codes)
            raise ValueError(
                "panel/spatial area set mismatch: "
                f"missing_from_boundaries={missing_from_boundaries}, "
                f"missing_from_panel={missing_from_panel}"
            )

        with admin_universe_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow([ADMIN_CANONICAL_COLUMN])
            writer.writerows((code,) for code in boundary_info["admin_codes"])
        panel_sha256 = sha256_file(captured_panel_path)
        boundaries_sha256 = sha256_file(normalized_boundaries_path)
        admin_universe_sha256 = sha256_file(admin_universe_path)
        identity_payload = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "panel_sha256": panel_sha256,
            "boundaries_sha256": boundaries_sha256,
            "admin_universe_sha256": admin_universe_sha256,
            "row_count": panel_info["row_count"],
            "area_count": panel_info["area_count"],
            "spatial_feature_count": boundary_info["feature_count"],
            "crs": "EPSG:4326",
            "latest_feature_month": panel_info["latest_feature_month"],
            "latest_label_month": panel_info["latest_label_month"],
            "admin_code_mapping": ADMIN_CODE_MAPPING,
        }
        canonical_identity = json.dumps(
            identity_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        snapshot_content_sha256 = hashlib.sha256(canonical_identity).hexdigest()
        latest_feature = panel_info["latest_feature_month"]
        snapshot_id = (
            f"fewsnet-{latest_feature.replace('-', '')}-"
            f"{snapshot_content_sha256[:8]}"
        )
        snapshot_root = (
            f"{destination_root.rstrip('/')}/inputs/snapshots/{snapshot_id}"
        )

        panel_ref = upload_file_immutable_or_verify(
            store,
            captured_panel_path,
            f"{snapshot_root}/assembled_fewsnet.csv",
        )
        boundaries_ref = upload_file_immutable_or_verify(
            store,
            normalized_boundaries_path,
            f"{snapshot_root}/admin_boundaries.parquet",
        )
        admin_universe_ref = upload_file_immutable_or_verify(
            store,
            admin_universe_path,
            f"{snapshot_root}/admin_universe.csv",
        )
        manifest = SnapshotManifest(
            snapshot_id=snapshot_id,
            created_at_utc=created_at_utc,
            snapshot_content_sha256=snapshot_content_sha256,
            panel=panel_ref,
            boundaries=boundaries_ref,
            admin_universe=admin_universe_ref,
            row_count=panel_info["row_count"],
            area_count=panel_info["area_count"],
            spatial_feature_count=boundary_info["feature_count"],
            crs="EPSG:4326",
            latest_feature_month=panel_info["latest_feature_month"],
            latest_label_month=panel_info["latest_label_month"],
            source_identity={
                "panel_bootstrap_path": str(panel_path),
                "boundaries_bootstrap_path": str(boundaries_path),
                "panel_source_type": "assembled_fewsnet_csv",
                "boundaries_source_type": "fewsnet_admin_boundaries_v3",
            },
            admin_code_mapping=dict(ADMIN_CODE_MAPPING),
        )
        manifest_payload = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            **asdict(manifest),
        }
        validate_payload("source-snapshot", manifest_payload)
        manifest_bytes = json.dumps(
            manifest_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        manifest_uri = f"{snapshot_root}/source_manifest.json"
        existing_manifest = next(
            (ref for ref in store.list(f"{snapshot_root}/") if ref.uri == manifest_uri),
            None,
        )
        if existing_manifest is not None:
            return _reuse_existing_manifest(
                store,
                existing_manifest,
                manifest_payload,
                temp_root / "existing-manifest-artifacts",
            )
        try:
            put_immutable_or_verify(store, manifest_uri, manifest_bytes)
        except GenerationConflict:
            return _reuse_existing_manifest(
                store,
                store.get_ref(manifest_uri),
                manifest_payload,
                temp_root / "existing-manifest-artifacts",
            )
        return manifest
