from __future__ import annotations

import argparse
import json
import os
from datetime import date
from importlib import import_module
from io import StringIO

import pandas as pd

from cloud.batch.evi_outputs import write_selected_month_long_outputs
from cloud.batch.evi_extract import compute_evi_zone_stats, wide_month_to_long
from cloud.batch.evi_reference import compare_evi_reference
from cloud.batch.evi_service import EarthEngineRasterioEVIService
from cloud.batch.evi_validation import build_evi_validation_report
from cloud.batch.gee_export import build_gee_export_manifest
from cloud.common.manifest import validate_manifest
from cloud.common.object_store import GCSObjectStore, ObjectStore
from cloud.common.reports import build_evi_extraction_manifest
from cloud.common.runtime_config import resolve_runtime_config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run IPCCH cloud EVI worker")
    parser.add_argument("--feature-month", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-prefix-uri")
    parser.add_argument("--run-root-uri")
    parser.add_argument("--gee-export-root-uri")
    parser.add_argument("--evi-output-root-uri")
    parser.add_argument("--logs-root-uri")
    parser.add_argument("--reference-sample-uri")
    parser.add_argument("--zones-json")
    parser.add_argument("--input-manifest-uri")
    return parser.parse_args(argv)


def run_worker_cli(
    argv: list[str] | None = None,
    *,
    store: ObjectStore | None = None,
    evi_service=None,
) -> int:
    args = parse_args(argv)
    roots = _resolve_output_roots(args)
    if store is None:
        store = GCSObjectStore.from_default()
    try:
        if args.zones_json:
            zones = json.loads(args.zones_json)
            run_fake_evi_worker(
                store=store,
                feature_month=args.feature_month,
                run_id=args.run_id,
                run_prefix_uri=roots["run_root_uri"],
                zones=zones,
            )
        else:
            if not args.input_manifest_uri:
                raise ValueError(
                    "--input-manifest-uri is required without --zones-json"
                )
            if evi_service is None:
                evi_service = build_default_evi_service()
            run_manifest_backed_evi_worker(
                store=store,
                feature_month=args.feature_month,
                run_id=args.run_id,
                run_prefix_uri=roots["run_root_uri"],
                input_manifest_uri=args.input_manifest_uri,
                output_roots=roots,
                evi_service=evi_service,
                reference_sample_uri=args.reference_sample_uri,
            )
    except Exception as exc:
        store.write_text(
            roots["evi_output_root_uri"] + "evi_worker_error.json",
            json.dumps({"status": "failed", "error": str(exc)}) + "\n",
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    return run_worker_cli(argv)


def build_default_evi_service():
    factory_path = os.environ.get("IPCCH_EVI_SERVICE_FACTORY")
    if factory_path:
        return ConfiguredEVIServiceFactory(factory_path).build()
    return EarthEngineRasterioEVIService()


class ConfiguredEVIServiceFactory:
    def __init__(self, factory_path: str | None = None):
        self.factory_path = factory_path or os.environ.get("IPCCH_EVI_SERVICE_FACTORY")

    def build(self):
        if not self.factory_path:
            raise ValueError(
                "IPCCH_EVI_SERVICE_FACTORY must point to a callable returning "
                "the production Earth Engine/rasterio EVI service"
            )
        module_name, separator, function_name = self.factory_path.partition(":")
        if not separator or not module_name or not function_name:
            raise ValueError(
                "IPCCH_EVI_SERVICE_FACTORY must use 'module:function' format"
            )
        factory = getattr(import_module(module_name), function_name)
        return factory()


def run_manifest_backed_evi_worker(
    *,
    store: ObjectStore,
    feature_month: str,
    run_id: str,
    run_prefix_uri: str,
    input_manifest_uri: str,
    evi_service,
    output_roots: dict[str, str] | None = None,
    reference_sample_uri: str | None = None,
) -> dict:
    output_roots = output_roots or _default_output_roots(run_prefix_uri)
    manifest = validate_manifest(
        json.loads(store.read_text(input_manifest_uri)),
        feature_month=feature_month,
        run_id=run_id,
    )
    export_result = evi_service.export_processed_raster(
        feature_month=feature_month,
        run_id=run_id,
        manifest=manifest,
        run_prefix_uri=output_roots["run_root_uri"],
    )
    gee_manifest = build_gee_export_manifest(
        feature_month=feature_month,
        run_id=run_id,
        earth_engine_project_id=export_result["earth_engine_project_id"],
        export_task_id=export_result["export_task_id"],
        export_status=export_result["export_status"],
        processed_raster_uri=export_result["processed_raster_uri"],
        processed_raster_generation_or_version=export_result[
            "processed_raster_generation_or_version"
        ],
        processed_raster_checksum=export_result.get("processed_raster_checksum"),
    )
    extraction_result = evi_service.extract_zonal_stats(
        feature_month=feature_month,
        run_id=run_id,
        manifest=manifest,
        raster_uri=gee_manifest["processed_raster_uri"],
    )
    long_outputs = write_selected_month_long_outputs(
        mean_wide_csv=extraction_result["mean_wide_csv"],
        std_wide_csv=extraction_result["std_wide_csv"],
        feature_month=feature_month,
        scaffold_area_ids=extraction_result["scaffold_area_ids"],
    )
    mean_wide = pd.read_csv(StringIO(extraction_result["mean_wide_csv"]))
    std_wide = pd.read_csv(StringIO(extraction_result["std_wide_csv"]))
    mean_long = pd.read_csv(StringIO(long_outputs["EVI_mean_monthly_long.csv"]))
    std_long = pd.read_csv(StringIO(long_outputs["EVI_std_monthly_long.csv"]))
    geometry_artifact = _manifest_artifact(manifest, "geometry")
    runtime = resolve_runtime_config(manifest["deployment"])
    evi_manifest = build_evi_extraction_manifest(
        feature_month=feature_month,
        run_id=run_id,
        cloud_batch_job_id=extraction_result["cloud_batch_job_id"],
        cloud_batch_job_resource_name=extraction_result[
            "cloud_batch_job_resource_name"
        ],
        worker_entrypoint="python3 -m cloud.batch.evi_worker",
        worker_container_image_uri=manifest["deployment"][
            "artifact_registry_image_uri"
        ],
        worker_container_image_digest=manifest["deployment"][
            "vertex_ai_custom_job_container_digest"
        ],
        gee_export_task_id=gee_manifest["export_task_id"],
        source_raster_uri=gee_manifest["processed_raster_uri"],
        source_raster_generation_or_version=gee_manifest[
            "processed_raster_generation_or_version"
        ],
        geometry_uri=extraction_result.get("geometry_uri", geometry_artifact["uri"]),
        geometry_version_or_checksum=extraction_result.get(
            "geometry_version_or_checksum",
            geometry_artifact.get("generation")
            or geometry_artifact.get("checksum")
            or geometry_artifact.get("version_id")
            or "",
        ),
        zone_count=extraction_result["zone_count"],
        empty_zone_count=extraction_result["empty_zone_count"],
        gee_poll_interval_seconds=runtime.gee_poll_interval_seconds,
        gee_export_timeout_seconds=runtime.gee_export_timeout_seconds,
        batch_job_timeout_seconds=runtime.batch_job_timeout_seconds,
        retry_policy={"max_retries": runtime.max_retries},
        output_roots=output_roots,
    )
    reference_frame = None
    if reference_sample_uri:
        reference_frame = pd.read_csv(StringIO(store.read_text(reference_sample_uri)))
    validation_report = build_evi_validation_report(
        feature_month=feature_month,
        run_id=run_id,
        mean_wide=mean_wide,
        std_wide=std_wide,
        mean_long=mean_long,
        std_long=std_long,
        scaffold_area_ids=extraction_result["scaffold_area_ids"],
        reference_comparison=compare_evi_reference(mean_long, reference_frame),
    )
    store.write_text(
        output_roots["gee_export_root_uri"] + "gee_export_manifest.json",
        json.dumps(gee_manifest),
    )
    store.write_text(
        output_roots["evi_output_root_uri"] + "EVI_mean_extraction_results.csv",
        extraction_result["mean_wide_csv"],
    )
    store.write_text(
        output_roots["evi_output_root_uri"] + "EVI_std_extraction_results.csv",
        extraction_result["std_wide_csv"],
    )
    store.write_text(
        output_roots["evi_output_root_uri"] + "EVI_mean_monthly_long.csv",
        long_outputs["EVI_mean_monthly_long.csv"],
    )
    store.write_text(
        output_roots["evi_output_root_uri"] + "EVI_std_monthly_long.csv",
        long_outputs["EVI_std_monthly_long.csv"],
    )
    store.write_text(
        output_roots["evi_output_root_uri"] + "evi_extraction_manifest.json",
        json.dumps(evi_manifest),
    )
    store.write_text(
        output_roots["evi_output_root_uri"] + "evi_validation_report.json",
        json.dumps(validation_report),
    )
    return {"status": "passed", "artifact_paths": evi_manifest["artifact_paths"]}


def _manifest_artifact(manifest: dict, artifact_type: str) -> dict:
    for artifact in manifest.get("artifacts", []):
        if artifact.get("artifact_type") == artifact_type:
            return artifact
    raise ValueError(f"input manifest missing {artifact_type} artifact")


def _resolve_output_roots(args: argparse.Namespace) -> dict[str, str]:
    run_root = args.run_root_uri or args.run_prefix_uri
    if not run_root:
        raise ValueError("--run-root-uri is required")
    roots = {
        "run_root_uri": run_root,
        "gee_export_root_uri": args.gee_export_root_uri or run_root + "gee_exports/",
        "evi_output_root_uri": args.evi_output_root_uri or run_root + "evi/",
        "logs_root_uri": args.logs_root_uri or run_root + "logs/",
    }
    return {key: _ensure_trailing_slash(value) for key, value in roots.items()}


def _default_output_roots(run_prefix_uri: str) -> dict[str, str]:
    return {
        "run_root_uri": _ensure_trailing_slash(run_prefix_uri),
        "gee_export_root_uri": _ensure_trailing_slash(run_prefix_uri + "gee_exports/"),
        "evi_output_root_uri": _ensure_trailing_slash(run_prefix_uri + "evi/"),
        "logs_root_uri": _ensure_trailing_slash(run_prefix_uri + "logs/"),
    }


def _ensure_trailing_slash(uri: str) -> str:
    return uri if uri.endswith("/") else uri + "/"


def run_fake_evi_worker(
    *,
    store: ObjectStore,
    feature_month: str,
    run_id: str,
    run_prefix_uri: str,
    zones: list[dict],
) -> dict:
    year, month = (int(part) for part in feature_month.split("-"))
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    month_col = f"{year}_{month:02d}"
    stats = compute_evi_zone_stats(
        zones, pixel_inclusion_rule="all_touched_false_center_inside"
    )
    wide_mean = pd.DataFrame(
        [{"region_id": row["region_id"], month_col: row["EVI_mean"]} for row in stats]
    )
    wide_std = pd.DataFrame(
        [{"region_id": row["region_id"], month_col: row["EVI_std"]} for row in stats]
    )
    area_ids = [zone["area_id"] for zone in zones]
    mean_long = wide_month_to_long(
        wide_mean,
        feature_name="EVI_mean",
        feature_month=feature_month,
        scaffold_area_ids=area_ids,
    )
    std_long = wide_month_to_long(
        wide_std,
        feature_name="EVI_std",
        feature_month=feature_month,
        scaffold_area_ids=area_ids,
    )

    gee_manifest = {
        "schema_version": "ipcch-monthly-e2e-report-v1",
        "feature_month": feature_month,
        "run_id": run_id,
        "earth_engine_collection": "MODIS/061/MOD13A3",
        "band": "EVI",
        "date_window": {"start": f"{feature_month}-01", "end": next_month.isoformat()},
        "processing_params": {"raw_scaled_integer": True},
        "export_task_id": "fake-task",
        "export_status": "COMPLETED",
        "processed_raster_uri": run_prefix_uri
        + f"gee_exports/MOD13A3_EVI_{year}_{month:02d}_processed.tif",
        "processed_raster_generation_or_version": "1",
        "processed_raster_checksum": None,
        "created_at_utc": "2026-06-26T00:00:00Z",
        "status": "passed",
        "artifact_paths": {},
        "checksums": {},
    }
    evi_manifest = build_evi_extraction_manifest(
        feature_month=feature_month,
        run_id=run_id,
        cloud_batch_job_id="fake-batch-job",
        cloud_batch_job_resource_name="projects/test/locations/us/jobs/fake-batch-job",
        worker_entrypoint="python3 -m cloud.batch.evi_worker",
        worker_container_image_uri="image@sha256:" + "a" * 64,
        worker_container_image_digest="sha256:" + "a" * 64,
        gee_export_task_id="fake-task",
        source_raster_uri=gee_manifest["processed_raster_uri"],
        source_raster_generation_or_version="1",
        geometry_uri="gs://bucket/geometry.gpkg",
        geometry_version_or_checksum="1",
        zone_count=len(zones),
        empty_zone_count=sum(1 for row in stats if row["EVI_mean"] is None),
    )
    validation_report = build_evi_validation_report(
        feature_month=feature_month,
        run_id=run_id,
        mean_wide=wide_mean,
        std_wide=wide_std,
        mean_long=mean_long,
        std_long=std_long,
        scaffold_area_ids=area_ids,
        reference_comparison=compare_evi_reference(None, None),
    )

    store.write_text(
        run_prefix_uri + "gee_exports/gee_export_manifest.json",
        json.dumps(gee_manifest),
    )
    store.write_text(
        run_prefix_uri + "evi/EVI_mean_extraction_results.csv",
        wide_mean.to_csv(index=False),
    )
    store.write_text(
        run_prefix_uri + "evi/EVI_std_extraction_results.csv",
        wide_std.to_csv(index=False),
    )
    store.write_text(
        run_prefix_uri + "evi/EVI_mean_monthly_long.csv", mean_long.to_csv(index=False)
    )
    store.write_text(
        run_prefix_uri + "evi/EVI_std_monthly_long.csv", std_long.to_csv(index=False)
    )
    store.write_text(
        run_prefix_uri + "evi/evi_extraction_manifest.json", json.dumps(evi_manifest)
    )
    store.write_text(
        run_prefix_uri + "evi/evi_validation_report.json", json.dumps(validation_report)
    )
    return {"status": "passed", "artifact_paths": evi_manifest["artifact_paths"]}


if __name__ == "__main__":
    raise SystemExit(main())
