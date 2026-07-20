"""Immutable FEWSNET source snapshot inspection and staging."""

from __future__ import annotations

import hashlib
import json
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
from fewsnet_partitioned_rf_pipeline.core import SnapshotManifest
from fewsnet_partitioned_rf_pipeline.schemas import validate_payload
from fewsnet_partitioned_rf_pipeline.vertex.storage import (
    ArtifactStore,
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
        labeled = chunk[TARGET_COLUMN].notna()

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
    panel_info = inspect_panel(panel_path)

    with tempfile.TemporaryDirectory(prefix="fewsnet-source-snapshot-") as temp_dir:
        temp_root = Path(temp_dir)
        normalized_boundaries_path = temp_root / "admin_boundaries.parquet"
        admin_universe_path = temp_root / "admin_universe.csv"
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

        admin_universe_path.write_text(
            "admin_code\n" + "\n".join(boundary_info["admin_codes"]) + "\n",
            encoding="utf-8",
            newline="",
        )
        panel_sha256 = sha256_file(panel_path)
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
            panel_path,
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
        put_immutable_or_verify(
            store,
            f"{snapshot_root}/source_manifest.json",
            manifest_bytes,
        )
        return manifest
