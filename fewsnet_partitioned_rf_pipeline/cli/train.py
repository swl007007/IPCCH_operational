"""In-container worker that trains and packages the full FEWSNET RF suite."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import geopandas as gpd
import pandas as pd

from fewsnet_partitioned_rf_pipeline.config import (
    ADMIN_CANONICAL_COLUMN,
    ADMIN_SOURCE_COLUMN,
    FEATURE_CONTRACT_PATH,
    HORIZON_KEYS,
    HORIZON_MONTHS,
    PARTITION_ASSET_PATH,
    PARTITION_ASSET_SHA256,
    TRAIN_WINDOW_MONTHS,
)
from fewsnet_partitioned_rf_pipeline.core.data import (
    ADMIN_CODE_MAPPING,
    inspect_panel,
    normalize_admin_code,
)
from fewsnet_partitioned_rf_pipeline.core.horizons import (
    align_horizon,
    select_training_window,
)
from fewsnet_partitioned_rf_pipeline.core.normalization import (
    validate_normalization_audit,
)
from fewsnet_partitioned_rf_pipeline.core.package import (
    PACKAGE_FILES,
    write_model_package,
)
from fewsnet_partitioned_rf_pipeline.core.partitions import PartitionMap
from fewsnet_partitioned_rf_pipeline.core.preprocessing import (
    Stage3FeatureBuilder,
    load_feature_contract,
)
from fewsnet_partitioned_rf_pipeline.core.training import train_horizon_model
from fewsnet_partitioned_rf_pipeline.core.types import ObjectRef, SnapshotManifest
from fewsnet_partitioned_rf_pipeline.schemas import validate_payload
from fewsnet_partitioned_rf_pipeline.vertex.storage import (
    ArtifactStore,
    GCSArtifactStore,
    GenerationConflict,
    put_immutable_or_verify,
    sha256_file,
    upload_file_immutable_or_verify,
)


_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_LOCAL_ARTIFACT_NAMES = {
    "panel": "assembled_fewsnet.normalized.csv",
    "normalization_audit": "panel_normalization_audit.json",
    "boundaries": "admin_boundaries.parquet",
    "admin_universe": "admin_universe.csv",
}


@dataclass(frozen=True)
class TrainingWorkerConfig:
    snapshot_manifest_uri: str
    suite_version: str
    run_root_uri: str
    model_root_uri: str
    container_image_uri: str
    container_image_digest: str
    source_git_commit: str


def run_training_worker(
    config: TrainingWorkerConfig,
    *,
    store: ArtifactStore,
) -> dict:
    """Localize one immutable snapshot and publish one three-model suite."""
    _validate_worker_config(config)
    image_source_commit = os.environ.get("FEWSNET_SOURCE_GIT_COMMIT")
    if image_source_commit != config.source_git_commit:
        raise ValueError(
            "--source-git-commit must equal image environment "
            "FEWSNET_SOURCE_GIT_COMMIT"
        )

    run_root_uri = config.run_root_uri.rstrip("/")
    model_root_uri = config.model_root_uri.rstrip("/")
    if not model_root_uri.endswith("/models"):
        raise ValueError("model_root_uri must end with /models")
    suite_root_uri = model_root_uri.removesuffix("/models")

    with tempfile.TemporaryDirectory(prefix="fewsnet-training-") as temp_dir:
        temp_root = Path(temp_dir)
        manifest = _load_snapshot_manifest(config.snapshot_manifest_uri, store)
        localized = _localize_snapshot(manifest, store, temp_root / "snapshot")
        panel = _validate_localized_snapshot(manifest, localized)

        feature_contract = load_feature_contract(FEATURE_CONTRACT_PATH)
        feature_frame = Stage3FeatureBuilder().transform(
            panel,
            feature_contract,
        )
        partition_map = PartitionMap.load(
            PARTITION_ASSET_PATH,
            PARTITION_ASSET_SHA256,
        )

        packages: dict[str, dict] = {}
        horizon_results: dict[str, object] = {}
        for horizon_months in HORIZON_MONTHS:
            horizon_key = HORIZON_KEYS[horizon_months]
            aligned = align_horizon(feature_frame, horizon_months).frame
            training_frame = select_training_window(
                aligned,
                manifest.latest_label_month,
                months=TRAIN_WINDOW_MONTHS,
            )
            training_result = train_horizon_model(
                training_frame,
                feature_contract,
                partition_map,
                horizon_key,
            )
            horizon_results[horizon_key] = training_result

            package_dir = temp_root / "packages" / horizon_key
            target_month = str(
                pd.Period(manifest.latest_feature_month, freq="M")
                + horizon_months
            )
            write_model_package(
                package_dir,
                training_result.predictor,
                {
                    "suite_version": config.suite_version,
                    "snapshot_id": manifest.snapshot_id,
                    "snapshot_content_sha256": manifest.snapshot_content_sha256,
                    "target_month": target_month,
                    "source_git_commit": config.source_git_commit,
                    "container_image_uri": config.container_image_uri,
                    "container_image_digest": config.container_image_digest,
                    "status": "validated",
                },
                {
                    "training_report": training_result.training_report,
                    "threshold_report": training_result.threshold_report,
                },
            )
            package_uri = f"{model_root_uri}/{horizon_key}"
            for filename in PACKAGE_FILES:
                upload_file_immutable_or_verify(
                    store,
                    package_dir / filename,
                    f"{package_uri}/{filename}",
                )
            checksums = _read_json_object(
                package_dir / "checksums.json",
                "checksums.json",
            )
            packages[horizon_key] = {
                "uri": package_uri,
                "checksums": checksums,
            }

        aggregate_report = _aggregate_training_report(
            config.suite_version,
            horizon_results,
        )
        validate_payload("training-report", aggregate_report)
        report_path = temp_root / "training_threshold_report.json"
        report_bytes = _json_file_bytes(aggregate_report)
        report_path.write_bytes(report_bytes)
        run_report_uri = f"{run_root_uri}/training_threshold_report.json"
        suite_report_uri = f"{suite_root_uri}/training_threshold_report.json"
        upload_file_immutable_or_verify(store, report_path, run_report_uri)
        upload_file_immutable_or_verify(store, report_path, suite_report_uri)

        result = {
            "schema_version": "fewsnet-training-job-result-v1",
            "suite_version": config.suite_version,
            "snapshot_id": manifest.snapshot_id,
            "snapshot_content_sha256": manifest.snapshot_content_sha256,
            "packages": packages,
            "training_threshold_report": {
                "run_uri": run_report_uri,
                "suite_uri": suite_report_uri,
                "sha256": hashlib.sha256(report_bytes).hexdigest(),
            },
            "source_git_commit": config.source_git_commit,
            "container_image_uri": config.container_image_uri,
            "container_image_digest": config.container_image_digest,
        }
        put_immutable_or_verify(
            store,
            f"{run_root_uri}/training_job_result.json",
            _canonical_json_bytes(result),
        )
        return result


def _load_snapshot_manifest(
    uri: str,
    store: ArtifactStore,
) -> SnapshotManifest:
    manifest_ref = store.get_ref(uri)
    manifest_bytes = store.read_bytes(uri, generation=manifest_ref.generation)
    if (
        len(manifest_bytes) != manifest_ref.size_bytes
        or hashlib.sha256(manifest_bytes).hexdigest() != manifest_ref.sha256
    ):
        raise GenerationConflict(
            f"snapshot manifest bytes differ from their ObjectRef: {uri}"
        )
    try:
        payload = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("snapshot manifest must be valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("snapshot manifest must contain a JSON object")
    validate_payload("source-snapshot", payload)
    return SnapshotManifest(
        snapshot_id=payload["snapshot_id"],
        created_at_utc=payload["created_at_utc"],
        snapshot_content_sha256=payload["snapshot_content_sha256"],
        panel=ObjectRef(**payload["panel"]),
        normalization_audit=ObjectRef(**payload["normalization_audit"]),
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


def _localize_snapshot(
    manifest: SnapshotManifest,
    store: ArtifactStore,
    output_root: Path,
) -> dict[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    localized: dict[str, Path] = {}
    for field, filename in _LOCAL_ARTIFACT_NAMES.items():
        reference = getattr(manifest, field)
        target = output_root / filename
        store.download_file(
            reference.uri,
            target,
            generation=reference.generation,
        )
        if (
            target.stat().st_size != reference.size_bytes
            or sha256_file(target) != reference.sha256
        ):
            raise GenerationConflict(
                "localized snapshot object differs from its ObjectRef: "
                f"{reference.uri}@{reference.generation}"
            )
        localized[field] = target
    return localized


def _validate_localized_snapshot(
    manifest: SnapshotManifest,
    localized: dict[str, Path],
) -> pd.DataFrame:
    if manifest.admin_code_mapping != ADMIN_CODE_MAPPING:
        raise ValueError("snapshot admin_code_mapping differs from the runtime contract")

    normalization_audit = validate_normalization_audit(
        localized["normalization_audit"],
        localized["panel"],
    )
    panel_info = inspect_panel(localized["panel"])
    expected_panel = {
        "row_count": manifest.row_count,
        "area_count": manifest.area_count,
        "latest_feature_month": manifest.latest_feature_month,
        "latest_label_month": manifest.latest_label_month,
    }
    observed_panel = {
        name: panel_info[name]
        for name in expected_panel
    }
    if observed_panel != expected_panel:
        raise ValueError(
            "localized panel metadata differs from snapshot manifest: "
            f"expected={expected_panel}, observed={observed_panel}"
        )
    if (
        normalization_audit["latest_feature_month"]
        != manifest.latest_feature_month
        or normalization_audit["latest_label_month"]
        != manifest.latest_label_month
    ):
        raise ValueError("normalization audit month range differs from snapshot manifest")

    boundaries = gpd.read_parquet(localized["boundaries"])
    if ADMIN_CANONICAL_COLUMN not in boundaries.columns:
        raise ValueError("localized boundaries must contain admin_code")
    if boundaries.crs is None or boundaries.crs != manifest.crs:
        raise ValueError("localized boundaries CRS differs from snapshot manifest")
    boundary_codes = boundaries[ADMIN_CANONICAL_COLUMN].map(normalize_admin_code)
    if (
        len(boundaries) == 0
        or boundary_codes.eq("").any()
        or boundary_codes.duplicated(keep=False).any()
        or boundaries.geometry.isna().any()
    ):
        raise ValueError(
            "localized boundaries must contain one non-null geometry per admin_code"
        )
    if len(boundaries) != manifest.spatial_feature_count:
        raise ValueError(
            "localized boundary feature count differs from snapshot manifest"
        )

    admin_universe = pd.read_csv(
        localized["admin_universe"],
        dtype={ADMIN_CANONICAL_COLUMN: "string"},
        keep_default_na=False,
    )
    if list(admin_universe.columns) != [ADMIN_CANONICAL_COLUMN]:
        raise ValueError("admin universe must contain exactly the admin_code column")
    universe_codes = admin_universe[ADMIN_CANONICAL_COLUMN].map(
        normalize_admin_code
    )
    if (
        universe_codes.eq("").any()
        or universe_codes.duplicated(keep=False).any()
        or len(universe_codes) != manifest.area_count
    ):
        raise ValueError("admin universe violates unique area-count contract")

    expected_codes = set(panel_info["admin_codes"])
    if (
        set(boundary_codes) != expected_codes
        or set(universe_codes) != expected_codes
    ):
        raise ValueError("panel, boundaries, and admin universe area sets differ")

    identity = {
        "schema_version": "fewsnet-source-snapshot-v2",
        "panel_sha256": manifest.panel.sha256,
        "normalization_audit_sha256": manifest.normalization_audit.sha256,
        "normalization_version": normalization_audit["normalization_version"],
        "boundaries_sha256": manifest.boundaries.sha256,
        "admin_universe_sha256": manifest.admin_universe.sha256,
        "row_count": manifest.row_count,
        "area_count": manifest.area_count,
        "spatial_feature_count": manifest.spatial_feature_count,
        "crs": manifest.crs,
        "latest_feature_month": manifest.latest_feature_month,
        "latest_label_month": manifest.latest_label_month,
        "admin_code_mapping": manifest.admin_code_mapping,
    }
    actual_snapshot_digest = hashlib.sha256(
        _canonical_json_bytes(identity)
    ).hexdigest()
    if actual_snapshot_digest != manifest.snapshot_content_sha256:
        raise ValueError("snapshot_content_sha256 does not match localized artifacts")

    return pd.read_csv(
        localized["panel"],
        dtype={ADMIN_SOURCE_COLUMN: "string"},
        low_memory=False,
    )


def _aggregate_training_report(
    suite_version: str,
    horizon_results: dict[str, object],
) -> dict:
    ordered_keys = [HORIZON_KEYS[months] for months in HORIZON_MONTHS]
    if list(horizon_results) != ordered_keys:
        raise ValueError("horizon training results must preserve HORIZON_MONTHS order")
    reports = {
        key: horizon_results[key].training_report
        for key in ordered_keys
    }
    training_ranges = {
        json.dumps(report["training_target_month_range"], sort_keys=True)
        for report in reports.values()
    }
    validation_ranges = {
        json.dumps(report["validation_target_month_range"], sort_keys=True)
        for report in reports.values()
    }
    if len(training_ranges) != 1 or len(validation_ranges) != 1:
        raise ValueError("all horizons must use shared training and validation ranges")
    first_report = reports[ordered_keys[0]]
    return {
        "schema_version": "fewsnet-training-report-v1",
        "suite_version": suite_version,
        "training_target_month_range": dict(
            first_report["training_target_month_range"]
        ),
        "validation_target_month_range": dict(
            first_report["validation_target_month_range"]
        ),
        "horizon_thresholds": {
            key: dict(horizon_results[key].threshold_report)
            for key in ordered_keys
        },
        "cluster_states": {
            key: reports[key]["cluster_states"]
            for key in ordered_keys
        },
        "smote_results": {
            key: reports[key]["smote_results"]
            for key in ordered_keys
        },
        "fallback_counts": {
            key: reports[key]["fallback_counts"]
            for key in ordered_keys
        },
    }


def _validate_worker_config(config: TrainingWorkerConfig) -> None:
    if not isinstance(config, TrainingWorkerConfig):
        raise TypeError("config must be a TrainingWorkerConfig")
    required = {
        "snapshot_manifest_uri": config.snapshot_manifest_uri,
        "suite_version": config.suite_version,
        "run_root_uri": config.run_root_uri,
        "model_root_uri": config.model_root_uri,
        "container_image_uri": config.container_image_uri,
        "container_image_digest": config.container_image_digest,
        "source_git_commit": config.source_git_commit,
    }
    missing = sorted(
        name
        for name, value in required.items()
        if not isinstance(value, str) or not value.strip()
    )
    if missing:
        raise ValueError(f"training worker fields are required: {missing}")
    for name, uri in (
        ("snapshot_manifest_uri", config.snapshot_manifest_uri),
        ("run_root_uri", config.run_root_uri),
        ("model_root_uri", config.model_root_uri),
    ):
        if not uri.startswith("gs://"):
            raise ValueError(f"{name} must be a gs:// URI")
    if _DIGEST_PATTERN.fullmatch(config.container_image_digest) is None:
        raise ValueError("container_image_digest must be sha256:<64 lowercase hex>")
    if not config.container_image_uri.endswith(
        f"@{config.container_image_digest}"
    ):
        raise ValueError(
            "container_image_uri must end with @container_image_digest"
        )
    if _COMMIT_PATTERN.fullmatch(config.source_git_commit) is None:
        raise ValueError("source_git_commit must be 40 lowercase hexadecimal characters")


def _read_json_object(path: Path, name: str) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{name} must be valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return payload


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _json_file_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train and package the three-horizon FEWSNET RF suite."
    )
    parser.add_argument("--snapshot-manifest-uri", required=True)
    parser.add_argument("--suite-version", required=True)
    parser.add_argument("--run-root-uri", required=True)
    parser.add_argument("--model-root-uri", required=True)
    parser.add_argument("--container-image-uri", required=True)
    parser.add_argument("--container-image-digest", required=True)
    parser.add_argument("--source-git-commit", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = run_training_worker(
            TrainingWorkerConfig(
                snapshot_manifest_uri=args.snapshot_manifest_uri,
                suite_version=args.suite_version,
                run_root_uri=args.run_root_uri,
                model_root_uri=args.model_root_uri,
                container_image_uri=args.container_image_uri,
                container_image_digest=args.container_image_digest,
                source_git_commit=args.source_git_commit,
            ),
            store=GCSArtifactStore.from_default(),
        )
    except (GenerationConflict, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
