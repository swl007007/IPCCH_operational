from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
import time
from typing import Any

import pandas as pd

from cloud.common.object_store import GCSObjectStore, ObjectStore
from cloud.common.runtime_config import resolve_runtime_config


class EVIServiceError(RuntimeError):
    """Raised when the production EVI service cannot complete a hard gate."""


@dataclass
class EarthEngineRasterioEVIService:
    store: ObjectStore | None = None
    ee_adapter: Any | None = None
    rasterio_adapter: Any | None = None

    def __post_init__(self) -> None:
        if self.store is None:
            self.store = LazyDefaultGCSObjectStore()
        if self.ee_adapter is None:
            self.ee_adapter = EarthEngineEVIExportAdapter(store=self.store)
        if self.rasterio_adapter is None:
            self.rasterio_adapter = RasterioZonalStatsAdapter(store=self.store)

    def export_processed_raster(
        self, *, feature_month: str, run_id: str, manifest: dict, run_prefix_uri: str
    ) -> dict:
        return self.ee_adapter.export_processed_raster(
            feature_month=feature_month,
            run_id=run_id,
            manifest=manifest,
            run_prefix_uri=run_prefix_uri,
        )

    def extract_zonal_stats(
        self, *, feature_month: str, run_id: str, manifest: dict, raster_uri: str
    ) -> dict:
        return self.rasterio_adapter.extract_zonal_stats(
            feature_month=feature_month,
            run_id=run_id,
            manifest=manifest,
            raster_uri=raster_uri,
        )


@dataclass
class EarthEngineEVIExportAdapter:
    store: ObjectStore

    def export_processed_raster(
        self, *, feature_month: str, run_id: str, manifest: dict, run_prefix_uri: str
    ) -> dict:
        try:
            import ee
        except Exception as exc:  # pragma: no cover - depends on cloud image deps
            raise EVIServiceError("earthengine-api is required for GEE export") from exc

        deployment = manifest["deployment"]
        evi_config = _manifest_artifact(manifest, "gee_evi_export_config")
        date_window = evi_config.get("date_window") or {}
        processing_params = evi_config.get("processing_params") or {}
        runtime = resolve_runtime_config(deployment)
        year, month = (int(part) for part in feature_month.split("-"))
        next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
        expected_window = {
            "start": f"{feature_month}-01",
            "end": next_month.isoformat(),
        }
        if date_window and date_window != expected_window:
            raise EVIServiceError("GEE EVI date window must match selected month")
        collection = evi_config.get("earth_engine_collection") or evi_config.get(
            "version_id", "MODIS/061/MOD13A3"
        )
        band = evi_config.get("band", "EVI")
        if collection != "MODIS/061/MOD13A3" or band != "EVI":
            raise EVIServiceError("GEE EVI config must use MODIS/061/MOD13A3 EVI")
        raster_uri = (
            run_prefix_uri + f"gee_exports/MOD13A3_EVI_{year}_{month:02d}_processed.tif"
        )
        bucket, blob_name = _parse_gcs_uri(raster_uri)
        file_prefix = blob_name.removesuffix(".tif")
        project_id = deployment["earth_engine_project_id"]
        ee.Initialize(project=project_id)
        image = (
            ee.ImageCollection(collection)
            .filterDate(expected_window["start"], expected_window["end"])
            .select(band)
            .first()
        )
        export_kwargs = {
            "image": image,
            "description": f"ipcch_{run_id}_mod13a3_evi_{year}_{month:02d}",
            "bucket": bucket,
            "fileNamePrefix": file_prefix,
            "scale": processing_params.get("scale", 1000),
            "maxPixels": 1_000_000_000_000,
        }
        if processing_params.get("export_region") is not None:
            export_kwargs["region"] = processing_params["export_region"]
        if processing_params.get("crs") is not None:
            export_kwargs["crs"] = processing_params["crs"]
        task = ee.batch.Export.image.toCloudStorage(
            **export_kwargs,
        )
        task.start()
        status = _wait_for_ee_task(
            task,
            timeout_seconds=runtime.gee_export_timeout_seconds,
            poll_seconds=runtime.gee_poll_interval_seconds,
        )
        generation = _gcs_generation(self.store, raster_uri)
        checksum = _gcs_sha256_checksum(self.store, raster_uri)
        if not generation and not checksum:
            raise EVIServiceError(
                "processed raster requires immutable GCS generation/version or sha256 checksum"
            )
        return {
            "earth_engine_project_id": project_id,
            "export_task_id": getattr(task, "id", None) or status.get("id", run_id),
            "export_status": status.get("state", "COMPLETED"),
            "processed_raster_uri": raster_uri,
            "processed_raster_generation_or_version": generation,
            "processed_raster_checksum": checksum,
        }


@dataclass
class RasterioZonalStatsAdapter:
    store: ObjectStore

    def extract_zonal_stats(
        self, *, feature_month: str, run_id: str, manifest: dict, raster_uri: str
    ) -> dict:
        try:
            import rasterio
            from rasterio.mask import mask
        except Exception as exc:  # pragma: no cover - depends on cloud image deps
            raise EVIServiceError("rasterio is required for EVI extraction") from exc

        geometry_artifact = _manifest_artifact(manifest, "geometry")
        scaffold = _read_scaffold(self.store, manifest, feature_month)
        geometry = _read_geometry_features(self.store, geometry_artifact["uri"])
        geometry_by_area = _geometry_by_area_id(geometry["features"])
        scaffold_area_ids = list(scaffold["area_id"])
        if set(geometry_by_area) != set(scaffold_area_ids):
            raise EVIServiceError("geometry area ids must match scaffold area ids")
        rows = []
        with rasterio.open(_rasterio_uri(raster_uri)) as dataset:
            for area_id in scaffold_area_ids:
                geometry_shape = _geometry_for_dataset(
                    geometry_by_area[area_id], geometry, dataset
                )
                values = _masked_values(mask, dataset, geometry_shape)
                if values:
                    mean_value = sum(values) / len(values)
                    variance = sum((value - mean_value) ** 2 for value in values) / len(
                        values
                    )
                    rows.append(
                        {
                            "region_id": area_id,
                            _month_column(feature_month): mean_value,
                            "_std": math.sqrt(variance),
                        }
                    )
                else:
                    rows.append(
                        {
                            "region_id": area_id,
                            _month_column(feature_month): None,
                            "_std": None,
                        }
                    )
        mean_wide = pd.DataFrame(
            [
                {
                    "region_id": row["region_id"],
                    _month_column(feature_month): row[_month_column(feature_month)],
                }
                for row in rows
            ]
        )
        std_wide = pd.DataFrame(
            [
                {
                    "region_id": row["region_id"],
                    _month_column(feature_month): row["_std"],
                }
                for row in rows
            ]
        )
        return {
            "mean_wide_csv": mean_wide.to_csv(index=False),
            "std_wide_csv": std_wide.to_csv(index=False),
            "scaffold_area_ids": scaffold_area_ids,
            "cloud_batch_job_id": run_id,
            "cloud_batch_job_resource_name": f"cloud-batch/{run_id}",
            "geometry_uri": geometry_artifact["uri"],
            "geometry_version_or_checksum": geometry_artifact.get("generation")
            or geometry_artifact.get("checksum")
            or geometry_artifact.get("version_id")
            or "",
            "zone_count": len(rows),
            "empty_zone_count": sum(1 for row in rows if row["_std"] is None),
        }


class LazyDefaultGCSObjectStore:
    def __init__(self) -> None:
        self._store: GCSObjectStore | None = None

    @property
    def store(self) -> GCSObjectStore:
        if self._store is None:
            self._store = GCSObjectStore.from_default()
        return self._store

    def write_text(self, *args, **kwargs):
        return self.store.write_text(*args, **kwargs)

    def read_text(self, *args, **kwargs):
        return self.store.read_text(*args, **kwargs)

    def list(self, *args, **kwargs):
        return self.store.list(*args, **kwargs)

    def copy(self, *args, **kwargs):
        return self.store.copy(*args, **kwargs)


def _wait_for_ee_task(task, *, timeout_seconds: int, poll_seconds: int) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while True:
        status = task.status()
        state = status.get("state")
        if state == "COMPLETED":
            return status
        if state in {"FAILED", "CANCELLED"}:
            raise EVIServiceError(f"GEE export failed: {status}")
        if time.monotonic() >= deadline:
            raise EVIServiceError(f"GEE export timed out: {status}")
        time.sleep(poll_seconds)


def _masked_values(mask_func, dataset, geometry: dict) -> list[float]:
    try:
        data, _ = mask_func(
            dataset, [geometry], crop=True, all_touched=False, filled=False
        )
    except ValueError as exc:
        if "overlap" in str(exc).lower():
            return []
        raise
    values = data[0]
    compressed = (
        values.compressed() if hasattr(values, "compressed") else values.ravel()
    )
    result = []
    for value in compressed:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isnan(numeric):
            result.append(numeric)
    return result


def _read_scaffold(
    store: ObjectStore, manifest: dict, feature_month: str
) -> pd.DataFrame:
    artifact = _manifest_artifact(manifest, "scaffold")
    scaffold = pd.read_csv(_read_text_buffer(store, artifact["uri"]))
    year, month = (int(part) for part in feature_month.split("-"))
    if "area_id" not in scaffold.columns and "admin_code" in scaffold.columns:
        scaffold["area_id"] = scaffold["admin_code"].astype(str).str.strip()
    scaffold = scaffold[(scaffold["year"] == year) & (scaffold["month"] == month)]
    area_ids = scaffold["area_id"].astype(str).str.strip()
    if area_ids.eq("").any() or area_ids.isna().any():
        raise EVIServiceError("scaffold contains blank area_id")
    if area_ids.duplicated().any():
        raise EVIServiceError("scaffold contains duplicate area_id")
    scaffold = scaffold.copy()
    scaffold["area_id"] = area_ids
    return scaffold


def _read_text_buffer(store: ObjectStore, uri: str):
    from io import StringIO

    return StringIO(store.read_text(uri))


def _read_geometry_features(store: ObjectStore, uri: str) -> dict:
    try:
        return _read_geojson_geometry(store, uri)
    except Exception:
        if uri.endswith((".json", ".geojson")):
            raise
    try:
        import fiona
    except Exception as exc:  # pragma: no cover - depends on cloud image deps
        raise EVIServiceError(
            "fiona is required to read non-GeoJSON geometry artifacts"
        ) from exc
    features = []
    crs = None
    with fiona.open(_vsigs_uri(uri)) as collection:
        crs = collection.crs_wkt or collection.crs
        for feature in collection:
            features.append(
                {
                    "type": "Feature",
                    "properties": dict(feature["properties"]),
                    "geometry": feature["geometry"],
                }
            )
    return {"type": "FeatureCollection", "features": features, "crs": crs}


def _read_geojson_geometry(store: ObjectStore, uri: str) -> dict:
    content = store.read_text(uri)
    parsed = json.loads(content)
    if parsed.get("type") == "FeatureCollection":
        return parsed
    if parsed.get("type") == "Feature":
        return {"type": "FeatureCollection", "features": [parsed]}
    raise EVIServiceError("geometry artifact must be GeoJSON FeatureCollection")


def _geometry_by_area_id(features: list[dict]) -> dict[str, dict]:
    by_area = {}
    for feature in features:
        area_id = str(
            feature.get("properties", {}).get("area_id")
            or feature.get("properties", {}).get("admin_code")
            or ""
        ).strip()
        if not area_id:
            raise EVIServiceError("geometry contains blank area_id")
        if area_id in by_area:
            raise EVIServiceError(f"geometry contains duplicate area_id: {area_id}")
        by_area[area_id] = feature["geometry"]
    return by_area


def _geometry_for_dataset(geometry: dict, feature_collection: dict, dataset) -> dict:
    source_crs = feature_collection.get("crs")
    dataset_crs = getattr(dataset, "crs", None)
    if source_crs and dataset_crs and str(source_crs) != str(dataset_crs):
        try:
            from rasterio.warp import transform_geom
        except Exception as exc:  # pragma: no cover - depends on cloud image deps
            raise EVIServiceError("rasterio.warp is required for reprojection") from exc
        return transform_geom(source_crs, dataset_crs, geometry)
    return geometry


def _manifest_artifact(manifest: dict, artifact_type: str) -> dict:
    for artifact in manifest.get("artifacts", []):
        if artifact.get("artifact_type") == artifact_type:
            return artifact
    raise EVIServiceError(f"input manifest missing {artifact_type} artifact")


def _month_column(feature_month: str) -> str:
    year, month = feature_month.split("-")
    return f"{year}_{int(month):02d}"


def _rasterio_uri(uri: str) -> str:
    if uri.startswith("gs://"):
        return "/vsigs/" + uri.removeprefix("gs://")
    return uri


def _vsigs_uri(uri: str) -> str:
    if uri.startswith("gs://"):
        return "/vsigs/" + uri.removeprefix("gs://")
    return uri


def _parse_gcs_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise EVIServiceError(f"expected gs:// URI: {uri}")
    bucket, _, blob = uri.removeprefix("gs://").partition("/")
    if not bucket or not blob:
        raise EVIServiceError(f"expected gs://bucket/object URI: {uri}")
    return bucket, blob


def _gcs_generation(store: ObjectStore, uri: str) -> str | None:
    generation = getattr(store, "_generations", {}).get(uri)
    if generation is not None:
        return str(generation)
    client = getattr(store, "client", None)
    if client is None:
        return None
    bucket_name, blob_name = _parse_gcs_uri(uri)
    blob = client.bucket(bucket_name).blob(blob_name)
    blob.reload()
    return str(blob.generation)


def _gcs_sha256_checksum(store: ObjectStore, uri: str) -> str | None:
    client = getattr(store, "client", None)
    if client is None:
        return None
    bucket_name, blob_name = _parse_gcs_uri(uri)
    blob = client.bucket(bucket_name).blob(blob_name)
    data = blob.download_as_bytes()
    return "sha256:" + hashlib.sha256(data).hexdigest()
