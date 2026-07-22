from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import io
from importlib import import_module
import json
from pathlib import Path
from types import SimpleNamespace

import geopandas as gpd
from google.api_core.exceptions import NotFound, ServiceUnavailable
import pandas as pd
import pytest
from shapely.geometry import Point

from fewsnet_partitioned_rf_pipeline.config import (
    FEATURE_CONTRACT_PATH,
    HORIZON_KEYS,
    PARTITION_ASSET_PATH,
    PARTITION_ASSET_SHA256,
)
from fewsnet_partitioned_rf_pipeline.core.inference import (
    FORMAL_PREDICTION_COLUMNS,
)
from fewsnet_partitioned_rf_pipeline.schemas import validate_payload
from fewsnet_partitioned_rf_pipeline.vertex.promotion import (
    PromotionBusy,
    PromotionIndeterminate,
)
from fewsnet_partitioned_rf_pipeline.vertex.storage import (
    LocalArtifactStore,
    put_immutable_or_verify,
    upload_file_immutable_or_verify,
)


ROOT_URI = "gs://bucket/fewsnet"
PROJECT_ID = "food-crisis-modeling"
REGION = "us-central1"
SOURCE_COMMIT = "1" * 40
IMAGE_DIGEST = f"sha256:{'a' * 64}"
IMAGE_URI = (
    "us-central1-docker.pkg.dev/food-crisis-modeling/fewsnet/model@"
    f"{IMAGE_DIGEST}"
)
NOW = datetime(2026, 7, 21, 20, 30, tzinfo=timezone.utc)
HORIZON_ORDER = ("0m", "6m", "12m")
HORIZON_MONTHS = {"0m": 0, "6m": 6, "12m": 12}


def _module():
    return import_module("fewsnet_partitioned_rf_pipeline.cli.run_latest")


def _deployment(*, max_retries: int = 2) -> dict[str, object]:
    return {
        "schema_version": "fewsnet-deployment-v1",
        "project_id": PROJECT_ID,
        "region": REGION,
        "object_store_root_uri": ROOT_URI,
        "orchestrator_service_account": (
            "fewsnet-orchestrator@food-crisis-modeling.iam.gserviceaccount.com"
        ),
        "training_service_account": (
            "fewsnet-training@food-crisis-modeling.iam.gserviceaccount.com"
        ),
        "batch_prediction_service_account": (
            "fewsnet-batch@food-crisis-modeling.iam.gserviceaccount.com"
        ),
        "container_image_uri": IMAGE_URI,
        "container_image_digest": IMAGE_DIGEST,
        "source_git_commit": SOURCE_COMMIT,
        "parent_model_ids": {
            "0m": "fewsnet-partitioned-rf-0m",
            "6m": "fewsnet-partitioned-rf-6m",
            "12m": "fewsnet-partitioned-rf-12m",
        },
        "training_machine_type": "n2-highmem-8",
        "batch_machine_type": "n2-standard-8",
        "training_timeout_seconds": 21600,
        "batch_timeout_seconds": 7200,
        "max_retries": max_retries,
    }


class RecordingStore(LocalArtifactStore):
    def __init__(self, root: Path):
        super().__init__(root)
        self.write_order: list[str] = []
        self.write_events: list[tuple[str, bytes, object]] = []
        self.read_order: list[str] = []
        self.list_order: list[str] = []

    def put_bytes(self, uri, data, *, if_generation_match=None):
        ref = super().put_bytes(
            uri,
            data,
            if_generation_match=if_generation_match,
        )
        self.write_order.append(uri)
        self.write_events.append((uri, bytes(data), if_generation_match))
        return ref

    def upload_file(self, path, uri, *, if_generation_match=None):
        ref = super().upload_file(
            path,
            uri,
            if_generation_match=if_generation_match,
        )
        data = Path(path).read_bytes()
        self.write_order.append(uri)
        self.write_events.append((uri, data, if_generation_match))
        return ref

    def read_bytes(self, uri, generation=None):
        self.read_order.append(uri)
        return super().read_bytes(uri, generation=generation)

    def list(self, prefix):
        self.list_order.append(prefix)
        return super().list(prefix)

    def clear_events(self) -> None:
        self.write_order.clear()
        self.write_events.clear()
        self.read_order.clear()
        self.list_order.clear()


class AmbiguousRunManifestStore(RecordingStore):
    def __init__(
        self,
        root: Path,
        *,
        committed_bytes: bytes | None = None,
        fail_readback: bool = False,
    ) -> None:
        super().__init__(root)
        self.committed_bytes = committed_bytes
        self.fail_readback = fail_readback
        self.ambiguous_write_committed = False
        self.manifest_read_generations: list[str | int | None] = []

    def put_bytes(self, uri, data, *, if_generation_match=None):
        if (
            not self.ambiguous_write_committed
            and uri.endswith("/run_manifest.json")
        ):
            self.ambiguous_write_committed = True
            super().put_bytes(
                uri,
                self.committed_bytes
                if self.committed_bytes is not None
                else data,
                if_generation_match=if_generation_match,
            )
            raise ServiceUnavailable(
                "run manifest response lost after commit"
            )
        return super().put_bytes(
            uri,
            data,
            if_generation_match=if_generation_match,
        )

    def read_bytes(self, uri, generation=None):
        if (
            self.ambiguous_write_committed
            and uri.endswith("/run_manifest.json")
        ):
            self.manifest_read_generations.append(generation)
            if self.fail_readback:
                raise ServiceUnavailable("run manifest readback unavailable")
        return super().read_bytes(uri, generation=generation)


class LaterAmbiguousRunManifestStore(AmbiguousRunManifestStore):
    def __init__(
        self,
        root: Path,
        *,
        committed_bytes: bytes | None = None,
        fail_readback: bool = False,
    ) -> None:
        super().__init__(
            root,
            committed_bytes=committed_bytes,
            fail_readback=fail_readback,
        )
        self.proven_manifest_generation: str | None = None
        self._initial_manifest_write_pending = True

    def put_bytes(self, uri, data, *, if_generation_match=None):
        if (
            self._initial_manifest_write_pending
            and uri.endswith("/run_manifest.json")
        ):
            self._initial_manifest_write_pending = False
            ref = RecordingStore.put_bytes(
                self,
                uri,
                data,
                if_generation_match=if_generation_match,
            )
            self.proven_manifest_generation = ref.generation
            return ref
        return super().put_bytes(
            uri,
            data,
            if_generation_match=if_generation_match,
        )


class ErrorArtifactFailureStore(RecordingStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.primary_failure_injected = False
        self.error_artifact_attempts = 0

    def put_bytes(self, uri, data, *, if_generation_match=None):
        if (
            not self.primary_failure_injected
            and uri.endswith("/inputs/selected_source_manifest.json")
        ):
            self.primary_failure_injected = True
            raise OSError("injected post-discovery primary failure")
        if uri.endswith("/error.json"):
            self.error_artifact_attempts += 1
            raise OSError("injected error artifact failure")
        return super().put_bytes(
            uri,
            data,
            if_generation_match=if_generation_match,
        )


class ErrorArtifactAndTerminalFailureStore(LaterAmbiguousRunManifestStore):
    def __init__(self, root: Path, *, fail_readback: bool) -> None:
        super().__init__(
            root,
            committed_bytes=(
                None if fail_readback else b'{"different":"later-payload"}'
            ),
            fail_readback=fail_readback,
        )
        self.error_artifact_attempts = 0

    def put_bytes(self, uri, data, *, if_generation_match=None):
        if uri.endswith("/error.json"):
            self.error_artifact_attempts += 1
            raise OSError("injected error artifact failure")
        return super().put_bytes(
            uri,
            data,
            if_generation_match=if_generation_match,
        )


class GCSNotFoundStore(RecordingStore):
    def get_ref(self, uri):
        try:
            return super().get_ref(uri)
        except FileNotFoundError as exc:
            raise NotFound(uri) from exc


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _panel_file_payload(path: Path, frame: pd.DataFrame) -> dict[str, object]:
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
        "row_count": len(frame),
        "column_count": len(frame.columns),
    }


def _write_panel(
    path: Path,
    *,
    latest_feature_month: str,
    variant: int,
) -> pd.DataFrame:
    contract = json.loads(FEATURE_CONTRACT_PATH.read_text(encoding="utf-8"))
    source_columns = list(contract["required_source_columns"])
    periods = pd.period_range(end=latest_feature_month, periods=18, freq="M")
    rows: list[dict[str, object]] = []
    for admin_code, latitude, longitude in (
        ("0", 9.551002, 29.130297),
        ("1", 9.786447, 28.414507),
    ):
        for index, period in enumerate(periods):
            row = {
                name: float((column_index % 11) + 1 + variant) + index / 1000
                for column_index, name in enumerate(source_columns)
            }
            crisis = (index + int(admin_code) + variant) % 2
            row.update(
                {
                    "FEWSNET_admin_code": admin_code,
                    "ISO": "SS",
                    "lat": latitude,
                    "lon": longitude,
                    "month": period.month,
                    "fews_ipc": 2 + crisis,
                    "fews_ipc_crisis": crisis,
                    "date": period.to_timestamp().strftime("%Y-%m-%d"),
                }
            )
            rows.append(row)
    frame = pd.DataFrame(rows, columns=source_columns)
    frame.to_csv(path, index=False, lineterminator="\n")
    return frame


def _seed_snapshot(
    tmp_path: Path,
    store: RecordingStore,
    *,
    latest_feature_month: str,
    created_at_utc: str,
    variant: int = 0,
) -> dict[str, object]:
    local_root = tmp_path / (
        f"snapshot-{latest_feature_month.replace('-', '')}-{variant}"
    )
    local_root.mkdir(parents=True, exist_ok=True)
    panel_path = local_root / "assembled_fewsnet.normalized.csv"
    audit_path = local_root / "panel_normalization_audit.json"
    boundaries_path = local_root / "admin_boundaries.parquet"
    admin_universe_path = local_root / "admin_universe.csv"
    panel = _write_panel(
        panel_path,
        latest_feature_month=latest_feature_month,
        variant=variant,
    )
    panel_file = _panel_file_payload(panel_path, panel)
    audit = {
        "schema_version": "fewsnet-panel-normalization-v1",
        "normalization_version": "deduplicate-before-global-rolling-zscore-v1",
        "source_panel": dict(panel_file),
        "output_panel": dict(panel_file),
        "key_columns": ["FEWSNET_admin_code", "feature_month"],
        "sort_columns": ["FEWSNET_admin_code", "date", "source_row_number"],
        "comparison_excluded_columns": ["Tair_zscore", "Rainf_zscore"],
        "climate_derivation": {
            "Tair_f_tavg_mean": "Tair_zscore",
            "Rainf_f_tavg_mean": "Rainf_zscore",
            "rolling_order": "global_after_stable_admin_date_sort",
            "window": 12,
            "minimum_periods": 1,
            "grouping_column": "FEWSNET_admin_code",
            "std_ddof": 1,
        },
        "latest_feature_month": latest_feature_month,
        "latest_label_month": latest_feature_month,
        "duplicate_group_count": 0,
        "duplicate_row_count": 0,
        "removed_row_count": 0,
        "conflict_group_count": 0,
        "duplicate_groups": [],
    }
    audit_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    boundaries = gpd.GeoDataFrame(
        {"admin_code": ["0", "1"]},
        geometry=[Point(29.130297, 9.551002), Point(28.414507, 9.786447)],
        crs="EPSG:4326",
    )
    boundaries.to_parquet(boundaries_path, index=False)
    pd.DataFrame({"admin_code": ["0", "1"]}).to_csv(
        admin_universe_path,
        index=False,
        lineterminator="\n",
    )

    admin_code_mapping = {
        "panel": "FEWSNET_admin_code",
        "boundaries": "admin_code",
        "canonical": "admin_code",
    }
    identity = {
        "schema_version": "fewsnet-source-snapshot-v2",
        "panel_sha256": _sha256(panel_path),
        "normalization_audit_sha256": _sha256(audit_path),
        "normalization_version": audit["normalization_version"],
        "boundaries_sha256": _sha256(boundaries_path),
        "admin_universe_sha256": _sha256(admin_universe_path),
        "row_count": len(panel),
        "area_count": 2,
        "spatial_feature_count": 2,
        "crs": "EPSG:4326",
        "latest_feature_month": latest_feature_month,
        "latest_label_month": latest_feature_month,
        "admin_code_mapping": admin_code_mapping,
    }
    snapshot_content_sha256 = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    snapshot_id = (
        f"fewsnet-{latest_feature_month.replace('-', '')}-"
        f"{snapshot_content_sha256[:8]}"
    )
    snapshot_root = f"{ROOT_URI}/inputs/snapshots/{snapshot_id}"
    panel_ref = upload_file_immutable_or_verify(
        store,
        panel_path,
        f"{snapshot_root}/assembled_fewsnet.normalized.csv",
    )
    audit_ref = upload_file_immutable_or_verify(
        store,
        audit_path,
        f"{snapshot_root}/panel_normalization_audit.json",
    )
    boundaries_ref = upload_file_immutable_or_verify(
        store,
        boundaries_path,
        f"{snapshot_root}/admin_boundaries.parquet",
    )
    admin_universe_ref = upload_file_immutable_or_verify(
        store,
        admin_universe_path,
        f"{snapshot_root}/admin_universe.csv",
    )
    manifest = {
        "schema_version": "fewsnet-source-snapshot-v2",
        "snapshot_id": snapshot_id,
        "created_at_utc": created_at_utc,
        "snapshot_content_sha256": snapshot_content_sha256,
        "panel": asdict(panel_ref),
        "normalization_audit": asdict(audit_ref),
        "boundaries": asdict(boundaries_ref),
        "admin_universe": asdict(admin_universe_ref),
        "row_count": len(panel),
        "area_count": 2,
        "spatial_feature_count": 2,
        "crs": "EPSG:4326",
        "latest_feature_month": latest_feature_month,
        "latest_label_month": latest_feature_month,
        "source_identity": {
            "panel_bootstrap_path": str(panel_path),
            "boundaries_bootstrap_path": str(boundaries_path),
            "panel_source_type": "synthetic_normalized_csv",
            "boundaries_source_type": "synthetic_geoparquet",
        },
        "admin_code_mapping": admin_code_mapping,
    }
    validate_payload("source-snapshot", manifest)
    manifest_uri = f"{snapshot_root}/source_manifest.json"
    manifest_ref = put_immutable_or_verify(
        store,
        manifest_uri,
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(),
    )
    return {
        "uri": manifest_uri,
        "ref": manifest_ref,
        "manifest": manifest,
    }


def _seed_current_pointer(
    store: RecordingStore,
    *,
    feature_month: str,
    snapshot_digest: str,
    suite_version: str = "fewsnet-prf-prior",
) -> None:
    suite_ref = put_immutable_or_verify(
        store,
        f"{ROOT_URI}/suites/{suite_version}/suite_manifest.json",
        b'{"prior":true}',
    )
    pointer = {
        "schema_version": "fewsnet-production-suite-pointer-v1",
        "suite_version": suite_version,
        "feature_month": feature_month,
        "snapshot_content_sha256": snapshot_digest,
        "suite_manifest": asdict(suite_ref),
        "released_at_utc": "2026-07-20T00:00:00Z",
    }
    store.put_bytes(
        f"{ROOT_URI}/released/current.json",
        json.dumps(pointer, sort_keys=True, separators=(",", ":")).encode(),
        if_generation_match=0,
    )


def _snapshot_from_store(store: RecordingStore, uri: str) -> dict[str, object]:
    ref = store.get_ref(uri)
    return json.loads(store.read_bytes(uri, generation=ref.generation))


def _target_month(feature_month: str, horizon_key: str) -> str:
    return str(
        pd.Period(feature_month, freq="M") + HORIZON_MONTHS[horizon_key]
    )


def _package_manifest(
    snapshot: dict[str, object],
    suite_version: str,
    horizon_key: str,
) -> dict[str, object]:
    return {
        "schema_version": "fewsnet-model-package-v1",
        "suite_version": suite_version,
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_content_sha256": snapshot["snapshot_content_sha256"],
        "horizon_key": horizon_key,
        "horizon_months": HORIZON_MONTHS[horizon_key],
        "target_month": _target_month(
            str(snapshot["latest_feature_month"]),
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
            "start": "2023-01",
            "end": str(snapshot["latest_feature_month"]),
        },
        "validation_target_month_range": {
            "start": "2024-01",
            "end": str(snapshot["latest_feature_month"]),
        },
        "files": ["model.joblib"],
        "status": "validated",
    }


def _training_threshold_report(suite_version: str) -> dict[str, object]:
    def cluster_state() -> dict[str, object]:
        return {
            "status": "partition_model",
            "sample_count": 50,
            "class_counts": {"0": 25, "1": 25},
            "smote_status": "resampled",
            "fallback_reason": None,
        }

    def smote_result() -> dict[str, object]:
        return {
            "status": "resampled",
            "original_class_counts": {"0": 25, "1": 25},
            "resampled_class_counts": {"0": 25, "1": 25},
            "failure_reason": None,
        }

    return {
        "schema_version": "fewsnet-training-report-v1",
        "suite_version": suite_version,
        "training_target_month_range": {"start": "2023-01", "end": "2024-12"},
        "validation_target_month_range": {"start": "2024-01", "end": "2024-12"},
        "horizon_thresholds": {
            horizon_key: {
                "threshold": 0.5,
                "precision": 0.8,
                "recall": 0.7,
                "f1": 0.75,
                "support": 20,
                "positive_cases": 8,
                "fallback_reason": None,
            }
            for horizon_key in HORIZON_ORDER
        },
        "cluster_states": {
            horizon_key: {
                str(cluster_id): cluster_state() for cluster_id in range(17)
            }
            for horizon_key in HORIZON_ORDER
        },
        "smote_results": {
            horizon_key: {
                str(cluster_id): smote_result() for cluster_id in range(17)
            }
            for horizon_key in HORIZON_ORDER
        },
        "fallback_counts": {
            horizon_key: {
                "pooled_unmapped": 0,
                "pooled_small_partition": 0,
                "pooled_single_class": 0,
                "pooled_missing_partition_model": 0,
            }
            for horizon_key in HORIZON_ORDER
        },
    }


def _custom_job_args(request: dict[str, object]) -> dict[str, str]:
    args = request["custom_job"]["job_spec"]["worker_pool_specs"][0][
        "container_spec"
    ]["args"]
    return dict(zip(args[::2], args[1::2], strict=True))


class FakeTrainingBackend:
    def __init__(
        self,
        store: RecordingStore,
        *,
        terminal_state: str = "JOB_STATE_SUCCEEDED",
        transient_failures: int = 0,
        commit_before_transient: bool = True,
    ) -> None:
        self.store = store
        self.terminal_state = terminal_state
        self.transient_failures = transient_failures
        self.commit_before_transient = commit_before_transient
        self.submit_requests: list[dict[str, object]] = []
        self.get_calls: list[str] = []
        self.cancel_calls: list[str] = []
        self.jobs: dict[str, dict[str, object]] = {}

    def submit(self, request):
        normalized = json.loads(json.dumps(request))
        self.submit_requests.append(normalized)
        args = _custom_job_args(normalized)
        job_name = (
            f"projects/{PROJECT_ID}/locations/{REGION}/customJobs/1001"
        )
        if self.commit_before_transient or self.transient_failures == 0:
            self.jobs.setdefault(
                job_name,
                {"name": job_name, "state": "JOB_STATE_QUEUED"},
            )
            if self.terminal_state == "JOB_STATE_SUCCEEDED":
                self._seed_training_outputs(args)
        if self.transient_failures > 0:
            self.transient_failures -= 1
            raise ServiceUnavailable("transient training submit")
        return dict(self.jobs[job_name])

    def get(self, job_name):
        self.get_calls.append(job_name)
        return {"name": job_name, "state": self.terminal_state}

    def cancel(self, job_name):
        self.cancel_calls.append(job_name)
        return {"name": job_name}

    def _seed_training_outputs(self, args: dict[str, str]) -> None:
        run_root = args["--run-root-uri"]
        model_root = args["--model-root-uri"]
        suite_version = args["--suite-version"]
        snapshot_uri = args["--snapshot-manifest-uri"]
        snapshot = _snapshot_from_store(self.store, snapshot_uri)
        packages: dict[str, dict[str, object]] = {}
        for horizon_key in HORIZON_ORDER:
            package_uri = f"{model_root}/{horizon_key}"
            manifest = _package_manifest(snapshot, suite_version, horizon_key)
            put_immutable_or_verify(
                self.store,
                f"{package_uri}/model_manifest.json",
                json.dumps(
                    manifest,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode(),
            )
            packages[horizon_key] = {"uri": package_uri, "checksums": {}}
        report_bytes = json.dumps(
            _training_threshold_report(suite_version),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        run_report_uri = f"{run_root}/training_threshold_report.json"
        suite_root = model_root.removesuffix("/models")
        suite_report_uri = f"{suite_root}/training_threshold_report.json"
        put_immutable_or_verify(self.store, run_report_uri, report_bytes)
        put_immutable_or_verify(self.store, suite_report_uri, report_bytes)
        result = {
            "schema_version": "fewsnet-training-job-result-v1",
            "suite_version": suite_version,
            "snapshot_id": snapshot["snapshot_id"],
            "snapshot_content_sha256": snapshot["snapshot_content_sha256"],
            "packages": packages,
            "training_threshold_report": {
                "run_uri": run_report_uri,
                "suite_uri": suite_report_uri,
                "sha256": hashlib.sha256(report_bytes).hexdigest(),
            },
            "source_git_commit": args["--source-git-commit"],
            "container_image_uri": args["--container-image-uri"],
            "container_image_digest": args["--container-image-digest"],
        }
        put_immutable_or_verify(
            self.store,
            f"{run_root}/training_job_result.json",
            json.dumps(result, sort_keys=True, separators=(",", ":")).encode(),
        )


class MismatchedTrainingReportBackend(FakeTrainingBackend):
    def _seed_training_outputs(self, args: dict[str, str]) -> None:
        super()._seed_training_outputs(args)
        run_root = args["--run-root-uri"]
        suite_root = args["--model-root-uri"].removesuffix("/models")
        report_bytes = json.dumps(
            _training_threshold_report("wrong-suite-version"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        for report_uri in (
            f"{run_root}/training_threshold_report.json",
            f"{suite_root}/training_threshold_report.json",
        ):
            report_ref = self.store.get_ref(report_uri)
            self.store.put_bytes(
                report_uri,
                report_bytes,
                if_generation_match=report_ref.generation,
            )
        result_uri = f"{run_root}/training_job_result.json"
        result_ref = self.store.get_ref(result_uri)
        result = json.loads(
            self.store.read_bytes(result_uri, generation=result_ref.generation)
        )
        result["training_threshold_report"]["sha256"] = hashlib.sha256(
            report_bytes
        ).hexdigest()
        self.store.put_bytes(
            result_uri,
            json.dumps(result, sort_keys=True, separators=(",", ":")).encode(),
            if_generation_match=result_ref.generation,
        )


class NonUtf8TrainingReportBackend(FakeTrainingBackend):
    def _seed_training_outputs(self, args: dict[str, str]) -> None:
        super()._seed_training_outputs(args)
        run_root = args["--run-root-uri"]
        suite_root = args["--model-root-uri"].removesuffix("/models")
        report_bytes = json.dumps(
            _training_threshold_report(args["--suite-version"]),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-16")
        for report_uri in (
            f"{run_root}/training_threshold_report.json",
            f"{suite_root}/training_threshold_report.json",
        ):
            report_ref = self.store.get_ref(report_uri)
            self.store.put_bytes(
                report_uri,
                report_bytes,
                if_generation_match=report_ref.generation,
            )
        result_uri = f"{run_root}/training_job_result.json"
        result_ref = self.store.get_ref(result_uri)
        result = json.loads(
            self.store.read_bytes(result_uri, generation=result_ref.generation)
        )
        result["training_threshold_report"]["sha256"] = hashlib.sha256(
            report_bytes
        ).hexdigest()
        self.store.put_bytes(
            result_uri,
            json.dumps(result, sort_keys=True, separators=(",", ":")).encode(),
            if_generation_match=result_ref.generation,
        )


@dataclass
class _EnvironmentVariable:
    name: str
    value: str


@dataclass
class _ContainerSpec:
    image_uri: str
    env: list[_EnvironmentVariable]


@dataclass
class _GcaResource:
    container_spec: _ContainerSpec


@dataclass
class _VersionInfo:
    version_id: str
    model_resource_name: str
    version_aliases: list[str]


class _FakeModel:
    def __init__(
        self,
        *,
        parent: str,
        version_id: str,
        artifact_uri: str,
        image_uri: str,
        image_digest: str,
        source_git_commit: str,
        labels: dict[str, str],
    ) -> None:
        self.resource_name = parent
        self.version_id = version_id
        self.versioned_resource_name = f"{parent}@{version_id}"
        self.uri = artifact_uri
        self.labels = dict(labels)
        self.gca_resource = _GcaResource(
            _ContainerSpec(
                image_uri,
                [
                    _EnvironmentVariable(
                        "FEWSNET_CONTAINER_IMAGE_DIGEST",
                        image_digest,
                    ),
                    _EnvironmentVariable(
                        "FEWSNET_SOURCE_GIT_COMMIT",
                        source_git_commit,
                    ),
                ],
            )
        )


class _FakeRegistry:
    def __init__(self, sdk: FakeRegistrySDK, parent: str) -> None:
        self.sdk = sdk
        self.parent = parent

    def list_versions(self):
        if self.parent not in self.sdk.parent_models:
            raise NotFound("parent model does not exist")
        return list(self.sdk.parent_models[self.parent].values())

    def get_version_info(self, alias: str):
        try:
            return self.sdk.version_info[(self.parent, alias)]
        except KeyError as exc:
            raise NotFound("version alias does not exist") from exc

    def update_version(self, version: str, *, labels: dict[str, str]):
        model = self.sdk.models[(self.parent, version)]
        model.labels = dict(labels)
        if labels.get("lifecycle") == "abandoned":
            self.sdk.abandoned_versions.append(model.versioned_resource_name)


class _ModelBoundary:
    def __init__(self, sdk: FakeRegistrySDK) -> None:
        self.sdk = sdk

    def __call__(self, *, model_name: str, version: str):
        return self.sdk.models[(model_name, version)]

    def upload(self, **kwargs):
        self.sdk.upload_calls.append(dict(kwargs))
        horizon_key = str(kwargs["labels"]["horizon"])
        if horizon_key == self.sdk.fail_horizon:
            raise RuntimeError(f"injected registration failure for {horizon_key}")
        parent = kwargs.get("parent_model")
        if parent is None:
            parent = (
                f"projects/{self.sdk.project}/locations/{self.sdk.region}/"
                f"models/{kwargs['model_id']}"
            )
        alias = str(kwargs["version_aliases"][0])
        version_id = {"0m": "101", "6m": "102", "12m": "103"}[
            horizon_key
        ]
        model = _FakeModel(
            parent=parent,
            version_id=version_id,
            artifact_uri=str(kwargs["artifact_uri"]),
            image_uri=str(kwargs["serving_container_image_uri"]),
            image_digest=str(
                kwargs["serving_container_environment_variables"][
                    "FEWSNET_CONTAINER_IMAGE_DIGEST"
                ]
            ),
            source_git_commit=str(
                kwargs["serving_container_environment_variables"][
                    "FEWSNET_SOURCE_GIT_COMMIT"
                ]
            ),
            labels=dict(kwargs["labels"]),
        )
        self.sdk.parent_models.setdefault(parent, {})[version_id] = model
        self.sdk.models[(parent, version_id)] = model
        self.sdk.models_by_resource[model.versioned_resource_name] = model
        self.sdk.version_info[(parent, alias)] = _VersionInfo(
            version_id=version_id,
            model_resource_name=parent,
            version_aliases=[alias, "default"],
        )
        if (
            horizon_key == self.sdk.transient_commit_horizon
            and horizon_key not in self.sdk.transient_raised
        ):
            self.sdk.transient_raised.add(horizon_key)
            raise ServiceUnavailable(
                f"transient registration response for {horizon_key}"
            )
        return model


class FakeRegistrySDK:
    def __init__(
        self,
        *,
        fail_horizon: str | None = None,
        transient_commit_horizon: str | None = None,
    ) -> None:
        self.fail_horizon = fail_horizon
        self.transient_commit_horizon = transient_commit_horizon
        self.transient_raised: set[str] = set()
        self.project = PROJECT_ID
        self.region = REGION
        self.upload_calls: list[dict[str, object]] = []
        self.parent_models: dict[str, dict[str, _FakeModel]] = {}
        self.models: dict[tuple[str, str], _FakeModel] = {}
        self.models_by_resource: dict[str, _FakeModel] = {}
        self.version_info: dict[tuple[str, str], _VersionInfo] = {}
        self.abandoned_versions: list[str] = []
        self.Model = _ModelBoundary(self)

    def init(self, *, project: str, location: str) -> None:
        self.project = project
        self.region = location

    def ModelRegistry(self, parent: str):
        return _FakeRegistry(self, parent)


class FakeBatchBackend:
    def __init__(
        self,
        store: RecordingStore,
        *,
        fail_horizon: str | None = None,
        output_failure_horizon: str | None = None,
        transient_failure_horizon: str | None = None,
    ) -> None:
        self.store = store
        self.fail_horizon = fail_horizon
        self.output_failure_horizon = output_failure_horizon
        self.transient_failure_horizon = transient_failure_horizon
        self.transient_failed: set[str] = set()
        self.submit_calls: list[dict[str, object]] = []
        self.get_calls: list[str] = []
        self.cancel_calls: list[str] = []
        self.jobs_by_display: dict[str, dict[str, object]] = {}
        self.submitted_input_refs: dict[str, list[object]] = {
            key: [] for key in HORIZON_ORDER
        }

    def submit(self, **kwargs):
        normalized = json.loads(json.dumps(kwargs))
        self.submit_calls.append(normalized)
        horizon_key = str(normalized["labels"]["fewsnet_horizon"])
        input_uri = str(normalized["gcs_source"])
        input_ref = self.store.get_ref(input_uri)
        self.submitted_input_refs[horizon_key].append(input_ref)
        display_name = str(normalized["job_display_name"])
        if (
            horizon_key == self.transient_failure_horizon
            and horizon_key not in self.transient_failed
        ):
            self.transient_failed.add(horizon_key)
            raise ServiceUnavailable(
                f"transient Batch submit before commit for {horizon_key}"
            )
        job = self.jobs_by_display.get(display_name)
        if job is None:
            job_id = {"0m": "2001", "6m": "2002", "12m": "2003"}[
                horizon_key
            ]
            destination = str(normalized["gcs_destination_prefix"])
            output_directory = f"{destination}/job-{job_id}"
            job = {
                "name": (
                    f"projects/{PROJECT_ID}/locations/{REGION}/"
                    f"batchPredictionJobs/{job_id}"
                ),
                "horizon_key": horizon_key,
                "output_directory": output_directory,
                "model": str(normalized["model_name"]),
            }
            self.jobs_by_display[display_name] = job
            self._seed_output(job, input_ref)
        return SimpleNamespace(resource_name=job["name"])

    def get(self, job_resource_name):
        self.get_calls.append(job_resource_name)
        job = next(
            item
            for item in self.jobs_by_display.values()
            if item["name"] == job_resource_name
        )
        if job["horizon_key"] == self.fail_horizon:
            return {
                "name": job_resource_name,
                "state": "JOB_STATE_FAILED",
                "error": {"message": "injected Batch failure"},
            }
        return {
            "name": job_resource_name,
            "state": "JOB_STATE_SUCCEEDED",
            "output_info": {
                "gcs_output_directory": job["output_directory"],
            },
        }

    def cancel(self, job_resource_name):
        self.cancel_calls.append(job_resource_name)
        return {"name": job_resource_name}

    def _seed_output(self, job: dict[str, object], input_ref: object) -> None:
        horizon_key = str(job["horizon_key"])
        if horizon_key == self.output_failure_horizon:
            self.store.put_bytes(
                f"{job['output_directory']}/errors_0001.jsonl",
                b'{"error":"injected output failure"}\n',
                if_generation_match=0,
            )
            return
        input_bytes = self.store.read_bytes(
            input_ref.uri,
            generation=input_ref.generation,
        )
        run_id = input_ref.uri.split("/runs/", 1)[1].split("/", 1)[0]
        records: list[str] = []
        for line in input_bytes.decode("utf-8").splitlines():
            instance = json.loads(line)
            probability = 0.75 if instance["admin_code"] == "0" else 0.25
            prediction = {
                "admin_code": instance["admin_code"],
                "feature_month": instance["feature_month"],
                "target_month": _target_month(
                    instance["feature_month"],
                    horizon_key,
                ),
                "horizon_months": HORIZON_MONTHS[horizon_key],
                "probability_crisis": probability,
                "predicted_crisis": int(probability >= 0.5),
                "threshold": 0.5,
                "cluster_id": 5,
                "prediction_source": "partition_model",
                "suite_version": run_id,
                "vertex_model_resource_name": "",
                "vertex_model_version_id": "",
            }
            records.append(
                json.dumps(
                    {"instance": instance, "prediction": prediction},
                    separators=(",", ":"),
                )
            )
        self.store.put_bytes(
            f"{job['output_directory']}/predictions_0001.jsonl",
            ("\n".join(records) + "\n").encode(),
            if_generation_match=0,
        )


class FakeAliasBackend:
    def __init__(self, store: RecordingStore) -> None:
        self.store = store
        self.versions = {
            (
                f"projects/{PROJECT_ID}/locations/{REGION}/models/"
                f"fewsnet-partitioned-rf-{horizon_key}"
            ): (
                f"projects/{PROJECT_ID}/locations/{REGION}/models/"
                f"fewsnet-partitioned-rf-{horizon_key}@9"
            )
            for horizon_key in HORIZON_ORDER
        }
        self.current_calls: list[tuple[str, str]] = []
        self.move_calls: list[tuple[str, str, str]] = []
        self.restore_calls: list[tuple[str, str, str | None]] = []
        self.validated_before_move: list[bool] = []

    def current_version(self, parent: str, alias: str):
        self.current_calls.append((parent, alias))
        return self.versions.get(parent)

    def move_alias(self, parent: str, alias: str, target_version: str):
        suite_predictions = [
            ref
            for ref in self.store.list(f"{ROOT_URI}/suites/")
            if "/predictions/" in ref.uri and ref.uri.endswith(".csv")
        ]
        self.validated_before_move.append(len(suite_predictions) == 3)
        self.move_calls.append((parent, alias, target_version))
        self.versions[parent] = target_version

    def restore_alias(
        self,
        parent: str,
        alias: str,
        previous_version: str | None,
    ) -> None:
        self.restore_calls.append((parent, alias, previous_version))
        self.versions[parent] = previous_version


class TransientPromotionAliasBackend(FakeAliasBackend):
    def __init__(self, store: RecordingStore) -> None:
        super().__init__(store)
        self.transient_failures = 1
        self.move_attempts: list[tuple[str, str, str]] = []

    def move_alias(self, parent: str, alias: str, target_version: str):
        self.move_attempts.append((parent, alias, target_version))
        if self.transient_failures:
            self.transient_failures -= 1
            raise ServiceUnavailable("transient promotion alias move")
        return super().move_alias(parent, alias, target_version)


def _backends(
    store: RecordingStore,
    *,
    training: FakeTrainingBackend | None = None,
    registry: FakeRegistrySDK | None = None,
    batch: FakeBatchBackend | None = None,
    aliases: FakeAliasBackend | None = None,
):
    return (
        training or FakeTrainingBackend(store),
        registry or FakeRegistrySDK(),
        batch or FakeBatchBackend(store),
        aliases or FakeAliasBackend(store),
    )


def _run(
    monkeypatch,
    deployment,
    store,
    backends,
    **kwargs,
):
    module = _module()
    monkeypatch.setenv("FEWSNET_SOURCE_GIT_COMMIT", SOURCE_COMMIT)
    monkeypatch.setattr(module, "_utc_now", lambda: NOW)
    monkeypatch.setattr(module, "_sleep", lambda _seconds: None)
    return module.run_latest(deployment, store, *backends, **kwargs)


def _read_json(store: RecordingStore, uri: str) -> dict[str, object]:
    ref = store.get_ref(uri)
    return json.loads(store.read_bytes(uri, generation=ref.generation))


def _assert_failed_evidence(store: RecordingStore, result: dict[str, object]):
    assert result["status"] == "FAILED"
    run_root = f"{ROOT_URI}/runs/{result['run_id']}"
    error = _read_json(store, f"{run_root}/error.json")
    manifest = _read_json(store, f"{run_root}/run_manifest.json")
    assert error["exception_type"]
    assert error["message"]
    assert manifest["phase"] == "FAILED"
    assert manifest["status"] == "failed"
    assert manifest["failure"]["message"] == error["message"]
    validate_payload("run-manifest", manifest)
    return manifest


def _phase_transitions(store: RecordingStore, run_id: str) -> list[str]:
    uri = f"{ROOT_URI}/runs/{run_id}/run_manifest.json"
    phases: list[str] = []
    for event_uri, data, _precondition in store.write_events:
        if event_uri != uri:
            continue
        phase = json.loads(data)["phase"]
        if not phases or phases[-1] != phase:
            phases.append(phase)
    return phases


def test_run_latest_module_exposes_task_18_interfaces():
    module = _module()

    assert callable(module.run_latest)
    assert callable(module.retry_transient)
    assert callable(module.main)


def test_run_latest_selects_newest_snapshot_and_releases_only_after_validation(
    tmp_path,
    monkeypatch,
):
    store = RecordingStore(tmp_path / "store")
    old_snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-11",
        created_at_utc="2026-07-20T00:00:00Z",
    )
    new_snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
        variant=1,
    )
    _seed_current_pointer(
        store,
        feature_month="2024-11",
        snapshot_digest=old_snapshot["manifest"]["snapshot_content_sha256"],
    )
    store.clear_events()
    training, registry, batch, aliases = _backends(store)

    result = _run(
        monkeypatch,
        _deployment(),
        store,
        (training, registry, batch, aliases),
    )

    assert result["status"] == "RELEASED"
    assert result["run_id"] == result["suite_version"]
    assert len(training.submit_requests) == 1
    training_args = _custom_job_args(training.submit_requests[0])
    immutable_manifest_uri = (
        f"{ROOT_URI}/runs/{result['run_id']}/inputs/"
        "selected_source_manifest.json"
    )
    assert training_args["--snapshot-manifest-uri"] == immutable_manifest_uri
    immutable_manifest_ref = store.get_ref(immutable_manifest_uri)
    assert store.read_bytes(
        immutable_manifest_uri,
        generation=immutable_manifest_ref.generation,
    ) == store.read_bytes(
        new_snapshot["uri"],
        generation=new_snapshot["ref"].generation,
    )
    assert training_args["--suite-version"] == result["suite_version"]
    assert len(registry.upload_calls) == 3
    assert [call["labels"]["horizon"] for call in registry.upload_calls] == [
        "0m",
        "6m",
        "12m",
    ]
    assert len(batch.submit_calls) == 3
    assert all("@" in str(call["model_name"]) for call in batch.submit_calls)
    assert len(aliases.move_calls) == 3
    assert aliases.validated_before_move == [True, True, True]
    assert _phase_transitions(store, result["run_id"]) == [
        "DISCOVERED",
        "INPUT_VALIDATED",
        "TRAINING",
        "PACKAGED",
        "REGISTERED_CANDIDATE",
        "BATCH_PREDICTING",
        "OUTPUT_VALIDATED",
        "PROMOTING",
        "RELEASED",
    ]
    run_manifest_uri = (
        f"{ROOT_URI}/runs/{result['run_id']}/run_manifest.json"
    )
    preconditions = [
        precondition
        for uri, _data, precondition in store.write_events
        if uri == run_manifest_uri
    ]
    assert preconditions[0] == 0
    assert preconditions[1:] == [
        str(generation) for generation in range(1, len(preconditions))
    ]
    current_uri = f"{ROOT_URI}/released/current.json"
    current = _read_json(store, current_uri)
    assert current["suite_version"] == result["suite_version"]
    assert current["snapshot_content_sha256"] == new_snapshot["manifest"][
        "snapshot_content_sha256"
    ]
    authoritative_writes = [
        uri
        for uri in store.write_order
        if "/locks/" not in uri and not uri.endswith("/run_manifest.json")
    ]
    assert authoritative_writes[-1] == current_uri


def test_snapshot_discovery_ranks_mixed_offsets_by_utc_instant(tmp_path):
    store = RecordingStore(tmp_path / "store")
    older = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00+14:00",
        variant=0,
    )
    newer = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-20T23:30:00Z",
        variant=1,
    )

    selected = _module()._discover_snapshot(
        store,
        root_uri=ROOT_URI,
        explicit_uri=None,
    )

    assert selected.snapshot.snapshot_id == newer["manifest"]["snapshot_id"]
    assert selected.snapshot.snapshot_id != older["manifest"]["snapshot_id"]


def test_snapshot_discovery_accepts_lowercase_t_and_z(tmp_path):
    store = RecordingStore(tmp_path / "store")
    snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21t00:00:00z",
    )

    selected = _module()._discover_snapshot(
        store,
        root_uri=ROOT_URI,
        explicit_uri=None,
    )

    assert selected.snapshot.snapshot_id == snapshot["manifest"]["snapshot_id"]


def test_snapshot_discovery_ranks_mixed_accepted_casing_by_utc_instant(tmp_path):
    store = RecordingStore(tmp_path / "store")
    older = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21t00:00:00+14:00",
        variant=0,
    )
    newer = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-20T23:30:00z",
        variant=1,
    )

    selected = _module()._discover_snapshot(
        store,
        root_uri=ROOT_URI,
        explicit_uri=None,
    )

    assert selected.snapshot.snapshot_id == newer["manifest"]["snapshot_id"]
    assert selected.snapshot.snapshot_id != older["manifest"]["snapshot_id"]


def test_snapshot_discovery_uses_snapshot_id_for_equal_mixed_case_instants(tmp_path):
    store = RecordingStore(tmp_path / "store")
    first = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21t00:00:00z",
        variant=0,
    )
    second = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T02:00:00+02:00",
        variant=1,
    )
    higher_id = max(
        (first, second),
        key=lambda item: item["manifest"]["snapshot_id"],
    )

    selected = _module()._discover_snapshot(
        store,
        root_uri=ROOT_URI,
        explicit_uri=None,
    )

    assert selected.snapshot.snapshot_id == higher_id["manifest"]["snapshot_id"]


def test_snapshot_discovery_uses_snapshot_id_for_equal_utc_instants(tmp_path):
    store = RecordingStore(tmp_path / "store")
    first = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
        variant=0,
    )
    second = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
        variant=1,
    )
    higher_id, lower_id = sorted(
        (first, second),
        key=lambda item: item["manifest"]["snapshot_id"],
        reverse=True,
    )
    for snapshot, created_at_utc in (
        (higher_id, "2026-07-21T00:00:00+00:00"),
        (lower_id, "2026-07-21T02:00:00+02:00"),
    ):
        manifest = {**snapshot["manifest"], "created_at_utc": created_at_utc}
        validate_payload("source-snapshot", manifest)
        snapshot["ref"] = store.put_bytes(
            snapshot["uri"],
            json.dumps(
                manifest,
                sort_keys=True,
                separators=(",", ":"),
            ).encode(),
            if_generation_match=snapshot["ref"].generation,
        )
        snapshot["manifest"] = manifest

    selected = _module()._discover_snapshot(
        store,
        root_uri=ROOT_URI,
        explicit_uri=None,
    )

    assert selected.snapshot.snapshot_id == higher_id["manifest"]["snapshot_id"]


def test_run_latest_rejects_checksum_bound_training_report_suite_mismatch(
    tmp_path,
    monkeypatch,
):
    store = RecordingStore(tmp_path / "store")
    _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    training = MismatchedTrainingReportBackend(store)
    registry = FakeRegistrySDK()
    batch = FakeBatchBackend(store)
    aliases = FakeAliasBackend(store)

    result = _run(
        monkeypatch,
        _deployment(),
        store,
        (training, registry, batch, aliases),
        promote=False,
    )

    assert result["status"] == "FAILED"
    assert result["preflight"] is False
    assert result["error"]["message"] == (
        "training threshold report suite_version differs"
    )
    assert registry.upload_calls == []


def test_run_latest_rejects_checksum_bound_non_utf8_training_report(
    tmp_path,
    monkeypatch,
):
    store = RecordingStore(tmp_path / "store")
    _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    training = NonUtf8TrainingReportBackend(store)
    registry = FakeRegistrySDK()
    batch = FakeBatchBackend(store)
    aliases = FakeAliasBackend(store)

    result = _run(
        monkeypatch,
        _deployment(),
        store,
        (training, registry, batch, aliases),
        promote=False,
    )

    assert result["status"] == "FAILED"
    assert result["preflight"] is False
    assert result["error"]["message"] == (
        "training threshold report must be valid UTF-8 JSON"
    )
    assert registry.upload_calls == []


def test_ambiguous_initial_run_manifest_write_still_records_terminal_failure(
    tmp_path,
    monkeypatch,
):
    store = AmbiguousRunManifestStore(tmp_path / "store")
    _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    store.clear_events()
    training, registry, batch, aliases = _backends(store)

    result = _run(
        monkeypatch,
        _deployment(),
        store,
        (training, registry, batch, aliases),
    )

    assert result["status"] == "FAILED"
    assert result.get("preflight") is not True
    assert result["error"]["exception_type"] == "ServiceUnavailable"
    manifest = _assert_failed_evidence(store, result)
    assert manifest["phase"] == "FAILED"
    assert manifest["status"] == "failed"
    assert store.manifest_read_generations[0] == "1"
    assert training.submit_requests == []
    assert registry.upload_calls == []
    assert batch.submit_calls == []
    assert aliases.move_calls == []


def test_run_manifest_write_does_not_reconcile_mismatched_committed_bytes(
    tmp_path,
):
    store = AmbiguousRunManifestStore(
        tmp_path / "store",
        committed_bytes=b'{"different":"payload"}',
    )
    snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    module = _module()
    selected = module._discover_snapshot(
        store,
        root_uri=ROOT_URI,
        explicit_uri=snapshot["uri"],
    )
    run_id = (
        f"fewsnet-prf-202412-{SOURCE_COMMIT[:8]}-"
        f"{selected.snapshot.snapshot_content_sha256[:8]}-"
        "20260721T203000Z"
    )
    manifest_uri = f"{ROOT_URI}/runs/{run_id}/run_manifest.json"
    state = module._RunState(
        store=store,
        uri=manifest_uri,
        run_id=run_id,
        suite_version=run_id,
        selected=selected,
    )

    with pytest.raises(
        ServiceUnavailable,
        match="run manifest response lost after commit",
    ):
        state.transition(
            module.RunPhase.DISCOVERED,
            gates={
                "deployment_validated": True,
                "snapshot_discovered": True,
            },
        )

    committed_ref = store.get_ref(manifest_uri)
    assert state.ref is None
    assert store.manifest_read_generations == [committed_ref.generation]
    assert store.read_bytes(
        manifest_uri,
        generation=committed_ref.generation,
    ) == b'{"different":"payload"}'


def test_run_manifest_write_does_not_reconcile_unreadable_committed_bytes(
    tmp_path,
):
    store = AmbiguousRunManifestStore(
        tmp_path / "store",
        fail_readback=True,
    )
    snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    module = _module()
    selected = module._discover_snapshot(
        store,
        root_uri=ROOT_URI,
        explicit_uri=snapshot["uri"],
    )
    run_id = (
        f"fewsnet-prf-202412-{SOURCE_COMMIT[:8]}-"
        f"{selected.snapshot.snapshot_content_sha256[:8]}-"
        "20260721T203000Z"
    )
    manifest_uri = f"{ROOT_URI}/runs/{run_id}/run_manifest.json"
    state = module._RunState(
        store=store,
        uri=manifest_uri,
        run_id=run_id,
        suite_version=run_id,
        selected=selected,
    )

    with pytest.raises(
        ServiceUnavailable,
        match="run manifest response lost after commit",
    ):
        state.transition(
            module.RunPhase.DISCOVERED,
            gates={
                "deployment_validated": True,
                "snapshot_discovered": True,
            },
        )

    committed_ref = store.get_ref(manifest_uri)
    assert state.ref is None
    assert store.manifest_read_generations == [committed_ref.generation]


@pytest.mark.parametrize(
    ("committed_bytes", "fail_readback"),
    [
        (b'{"different":"payload"}', False),
        (None, True),
    ],
    ids=("mismatched", "unreadable"),
)
def test_run_latest_returns_formal_indeterminate_failure_when_terminal_manifest_unprovable(
    tmp_path,
    monkeypatch,
    committed_bytes,
    fail_readback,
):
    store = AmbiguousRunManifestStore(
        tmp_path / "store",
        committed_bytes=committed_bytes,
        fail_readback=fail_readback,
    )
    snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    store.clear_events()

    result = _run(
        monkeypatch,
        _deployment(),
        store,
        _backends(store),
        snapshot_manifest_uri=snapshot["uri"],
    )

    assert result["status"] == "FAILED"
    assert result["preflight"] is False
    assert result["evidence_indeterminate"] is True
    assert result["run_id"] == result["suite_version"]
    assert result["phase"] == "FAILED"
    assert result["run_manifest"] is None
    assert result["error"]["exception_type"] == "ServiceUnavailable"
    assert result["terminal_manifest_error"]["exception_type"] == (
        "GenerationConflict"
    )
    error = _read_json(
        store,
        f"{ROOT_URI}/runs/{result['run_id']}/error.json",
    )
    assert error["exception_type"] == "ServiceUnavailable"
    manifest_uri = (
        f"{ROOT_URI}/runs/{result['run_id']}/run_manifest.json"
    )
    manifest_ref = store.get_ref(manifest_uri)
    manifest_writes = [
        event
        for event in store.write_events
        if event[0] == manifest_uri
    ]
    assert manifest_ref.generation == "1"
    assert len(manifest_writes) == 1
    assert LocalArtifactStore.read_bytes(
        store,
        manifest_uri,
        generation=manifest_ref.generation,
    ) == manifest_writes[0][1]
    if committed_bytes is not None:
        assert manifest_writes[0][1] == committed_bytes
    assert store.manifest_read_generations
    assert set(store.manifest_read_generations) == {"1"}


@pytest.mark.parametrize(
    ("committed_bytes", "fail_readback"),
    [
        (b'{"different":"payload"}', False),
        (None, True),
    ],
    ids=("mismatched", "unreadable"),
)
def test_cli_preserves_formal_indeterminate_failure_classification(
    tmp_path,
    monkeypatch,
    capsys,
    committed_bytes,
    fail_readback,
):
    module = _module()
    store = AmbiguousRunManifestStore(
        tmp_path / "store",
        committed_bytes=committed_bytes,
        fail_readback=fail_readback,
    )
    snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    deployment_uri = f"{ROOT_URI}/config/deployment.json"
    put_immutable_or_verify(
        store,
        deployment_uri,
        json.dumps(
            _deployment(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode(),
    )
    backends = _backends(store)
    store.clear_events()
    monkeypatch.setenv("FEWSNET_SOURCE_GIT_COMMIT", SOURCE_COMMIT)
    monkeypatch.setattr(module, "_utc_now", lambda: NOW)
    monkeypatch.setattr(module, "_sleep", lambda _seconds: None)
    monkeypatch.setattr(
        module.GCSArtifactStore,
        "from_default",
        classmethod(lambda _cls: store),
    )
    monkeypatch.setattr(module, "_default_backends", lambda _region: backends)

    exit_code = module.main(
        [
            "--deployment-manifest-uri",
            deployment_uri,
            "--snapshot-manifest-uri",
            snapshot["uri"],
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    result = json.loads(captured.err)
    assert result["status"] == "FAILED"
    assert result["preflight"] is False
    assert result["evidence_indeterminate"] is True
    assert result["run_id"] == result["suite_version"]
    assert result["run_manifest"] is None
    assert result["error"]["exception_type"] == "ServiceUnavailable"
    assert result["terminal_manifest_error"]["exception_type"] == (
        "GenerationConflict"
    )
    error = _read_json(
        store,
        f"{ROOT_URI}/runs/{result['run_id']}/error.json",
    )
    assert error["exception_type"] == "ServiceUnavailable"
    manifest_uri = (
        f"{ROOT_URI}/runs/{result['run_id']}/run_manifest.json"
    )
    manifest_ref = store.get_ref(manifest_uri)
    manifest_writes = [
        event
        for event in store.write_events
        if event[0] == manifest_uri
    ]
    assert manifest_ref.generation == "1"
    assert len(manifest_writes) == 1
    assert LocalArtifactStore.read_bytes(
        store,
        manifest_uri,
        generation=manifest_ref.generation,
    ) == manifest_writes[0][1]


def _assert_later_manifest_indeterminate_evidence(
    store,
    result,
    committed_bytes,
):
    assert result["status"] == "FAILED"
    assert result["preflight"] is False
    assert result["evidence_indeterminate"] is True
    assert result["run_id"] == result["suite_version"]
    assert result["phase"] == "FAILED"
    assert result["error"]["exception_type"] == "ServiceUnavailable"
    assert result["terminal_manifest_error"]["exception_type"] == (
        "GenerationConflict"
    )
    assert result["run_manifest"] is None

    error = _read_json(
        store,
        f"{ROOT_URI}/runs/{result['run_id']}/error.json",
    )
    assert error["exception_type"] == "ServiceUnavailable"
    manifest_uri = (
        f"{ROOT_URI}/runs/{result['run_id']}/run_manifest.json"
    )
    assert store.proven_manifest_generation == "1"
    manifest_ref = store.get_ref(manifest_uri)
    assert manifest_ref.generation == "2"
    manifest_writes = [
        event
        for event in store.write_events
        if event[0] == manifest_uri
    ]
    assert len(manifest_writes) == 2
    assert manifest_writes[0][2] == 0
    assert manifest_writes[1][2] == "1"
    proven_bytes = manifest_writes[0][1]
    proven_manifest = json.loads(proven_bytes)
    assert proven_manifest["phase"] == "DISCOVERED"
    assert proven_manifest["status"] == "running"
    unknown_bytes = LocalArtifactStore.read_bytes(
        store,
        manifest_uri,
        generation=manifest_ref.generation,
    )
    assert unknown_bytes == manifest_writes[1][1]
    if committed_bytes is not None:
        assert unknown_bytes == committed_bytes
    assert store.manifest_read_generations
    assert set(store.manifest_read_generations) == {"2"}


@pytest.mark.parametrize(
    ("committed_bytes", "fail_readback"),
    [
        (b'{"different":"later-payload"}', False),
        (None, True),
    ],
    ids=("mismatched", "unreadable"),
)
def test_run_latest_nulls_ref_when_later_manifest_write_indeterminate(
    tmp_path,
    monkeypatch,
    committed_bytes,
    fail_readback,
):
    store = LaterAmbiguousRunManifestStore(
        tmp_path / "store",
        committed_bytes=committed_bytes,
        fail_readback=fail_readback,
    )
    snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    store.clear_events()

    result = _run(
        monkeypatch,
        _deployment(),
        store,
        _backends(store),
        snapshot_manifest_uri=snapshot["uri"],
    )

    _assert_later_manifest_indeterminate_evidence(
        store,
        result,
        committed_bytes,
    )


@pytest.mark.parametrize(
    ("committed_bytes", "fail_readback"),
    [
        (b'{"different":"later-payload"}', False),
        (None, True),
    ],
    ids=("mismatched", "unreadable"),
)
def test_cli_nulls_ref_when_later_manifest_write_indeterminate(
    tmp_path,
    monkeypatch,
    capsys,
    committed_bytes,
    fail_readback,
):
    module = _module()
    store = LaterAmbiguousRunManifestStore(
        tmp_path / "store",
        committed_bytes=committed_bytes,
        fail_readback=fail_readback,
    )
    snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    deployment_uri = f"{ROOT_URI}/config/deployment.json"
    put_immutable_or_verify(
        store,
        deployment_uri,
        json.dumps(
            _deployment(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode(),
    )
    backends = _backends(store)
    store.clear_events()
    monkeypatch.setenv("FEWSNET_SOURCE_GIT_COMMIT", SOURCE_COMMIT)
    monkeypatch.setattr(module, "_utc_now", lambda: NOW)
    monkeypatch.setattr(module, "_sleep", lambda _seconds: None)
    monkeypatch.setattr(
        module.GCSArtifactStore,
        "from_default",
        classmethod(lambda _cls: store),
    )
    monkeypatch.setattr(module, "_default_backends", lambda _region: backends)

    exit_code = module.main(
        [
            "--deployment-manifest-uri",
            deployment_uri,
            "--snapshot-manifest-uri",
            snapshot["uri"],
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    result = json.loads(captured.err)
    _assert_later_manifest_indeterminate_evidence(
        store,
        result,
        committed_bytes,
    )


def test_read_current_pointer_treats_gcs_not_found_as_initial_absence(
    tmp_path,
):
    module = _module()
    store = GCSNotFoundStore(tmp_path / "store")

    assert module._read_current_pointer(store, ROOT_URI) is None


def test_run_latest_first_release_accepts_gcs_not_found_current_pointer(
    tmp_path,
    monkeypatch,
):
    store = GCSNotFoundStore(tmp_path / "store")
    snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    store.clear_events()
    training, registry, batch, aliases = _backends(store)

    result = _run(
        monkeypatch,
        _deployment(),
        store,
        (training, registry, batch, aliases),
        snapshot_manifest_uri=snapshot["uri"],
    )

    assert result["status"] == "RELEASED"
    assert len(training.submit_requests) == 1
    assert len(registry.upload_calls) == 3
    assert len(batch.submit_calls) == 3
    assert len(aliases.move_calls) == 3
    assert _read_json(
        store,
        f"{ROOT_URI}/released/current.json",
    )["suite_version"] == result["suite_version"]


def test_same_feature_month_and_snapshot_digest_is_noop_before_cloud_jobs(
    tmp_path,
    monkeypatch,
):
    store = RecordingStore(tmp_path / "store")
    snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    _seed_current_pointer(
        store,
        feature_month="2024-12",
        snapshot_digest=snapshot["manifest"]["snapshot_content_sha256"],
    )
    store.clear_events()
    training, registry, batch, aliases = _backends(store)

    result = _run(
        monkeypatch,
        _deployment(),
        store,
        (training, registry, batch, aliases),
    )

    assert result["status"] == "NOOP"
    assert training.submit_requests == []
    assert registry.upload_calls == []
    assert batch.submit_calls == []
    assert aliases.current_calls == []
    assert aliases.move_calls == []
    assert f"{ROOT_URI}/released/current.json" not in store.write_order
    assert _phase_transitions(store, result["run_id"]) == [
        "DISCOVERED",
        "NOOP",
    ]
    manifest = _read_json(
        store,
        f"{ROOT_URI}/runs/{result['run_id']}/run_manifest.json",
    )
    assert manifest["status"] == "noop"
    validate_payload("run-manifest", manifest)


def test_same_month_changed_snapshot_requires_explicit_revision(
    tmp_path,
    monkeypatch,
):
    store = RecordingStore(tmp_path / "store")
    prior = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-20T00:00:00Z",
    )
    _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
        variant=1,
    )
    _seed_current_pointer(
        store,
        feature_month="2024-12",
        snapshot_digest=prior["manifest"]["snapshot_content_sha256"],
    )
    store.clear_events()
    training, registry, batch, aliases = _backends(store)

    result = _run(
        monkeypatch,
        _deployment(),
        store,
        (training, registry, batch, aliases),
    )

    assert "revision_id is required" in result["error"]["message"]
    assert training.submit_requests == []
    assert registry.upload_calls == []
    assert batch.submit_calls == []
    assert aliases.move_calls == []
    manifest = _assert_failed_evidence(store, result)
    assert manifest["model_versions"] == {}
    assert manifest["batch_jobs"] == {}


def test_explicit_revision_releases_changed_same_month_as_new_suite(
    tmp_path,
    monkeypatch,
):
    store = RecordingStore(tmp_path / "store")
    prior = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-20T00:00:00Z",
    )
    changed = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
        variant=1,
    )
    _seed_current_pointer(
        store,
        feature_month="2024-12",
        snapshot_digest=prior["manifest"]["snapshot_content_sha256"],
    )
    store.clear_events()
    backends = _backends(store)

    result = _run(
        monkeypatch,
        _deployment(),
        store,
        backends,
        revision_id="corrected-input",
    )

    assert result["status"] == "RELEASED"
    assert "-rev-corrected-input-" in result["suite_version"]
    assert changed["manifest"]["snapshot_content_sha256"][:8] in result[
        "suite_version"
    ]
    current = _read_json(store, f"{ROOT_URI}/released/current.json")
    assert current["suite_version"] == result["suite_version"]


def test_identical_manifest_restage_at_new_generation_is_still_noop(
    tmp_path,
    monkeypatch,
):
    store = RecordingStore(tmp_path / "store")
    snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    _seed_current_pointer(
        store,
        feature_month="2024-12",
        snapshot_digest=snapshot["manifest"]["snapshot_content_sha256"],
    )
    manifest_ref = store.get_ref(snapshot["uri"])
    manifest_bytes = store.read_bytes(
        snapshot["uri"],
        generation=manifest_ref.generation,
    )
    restaged_ref = store.put_bytes(
        snapshot["uri"],
        manifest_bytes,
        if_generation_match=manifest_ref.generation,
    )
    assert restaged_ref.generation != manifest_ref.generation
    store.clear_events()
    training, registry, batch, aliases = _backends(store)

    result = _run(
        monkeypatch,
        _deployment(),
        store,
        (training, registry, batch, aliases),
    )

    assert result["status"] == "NOOP"
    evidence = _read_json(
        store,
        f"{ROOT_URI}/runs/{result['run_id']}/input_snapshot_ref.json",
    )
    assert evidence["manifest"]["generation"] == restaged_ref.generation
    assert training.submit_requests == []
    assert registry.upload_calls == []
    assert batch.submit_calls == []


def test_training_retries_use_run_immutable_manifest_after_source_restage(
    tmp_path,
    monkeypatch,
):
    store = RecordingStore(tmp_path / "store")
    snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    _seed_current_pointer(
        store,
        feature_month="2024-11",
        snapshot_digest="f" * 64,
    )
    source_ref = store.get_ref(snapshot["uri"])
    selected_manifest_bytes = store.read_bytes(
        snapshot["uri"],
        generation=source_ref.generation,
    )

    class RestagingTrainingBackend(FakeTrainingBackend):
        def __init__(self):
            super().__init__(
                store,
                transient_failures=1,
                commit_before_transient=False,
            )
            self.restaged_manifest_bytes: bytes | None = None

        def submit(self, request):
            if self.restaged_manifest_bytes is None:
                current_ref = store.get_ref(snapshot["uri"])
                changed_manifest = json.loads(selected_manifest_bytes)
                changed_manifest["snapshot_content_sha256"] = "e" * 64
                self.restaged_manifest_bytes = json.dumps(
                    changed_manifest,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
                store.put_bytes(
                    snapshot["uri"],
                    self.restaged_manifest_bytes,
                    if_generation_match=current_ref.generation,
                )
            return super().submit(request)

    training = RestagingTrainingBackend()
    registry = FakeRegistrySDK()
    batch = FakeBatchBackend(store)
    aliases = FakeAliasBackend(store)
    store.clear_events()

    result = _run(
        monkeypatch,
        _deployment(),
        store,
        (training, registry, batch, aliases),
    )

    assert result["status"] == "RELEASED"
    assert len(training.submit_requests) == 2
    assert training.submit_requests[0] == training.submit_requests[1]
    submitted_manifest_uris = {
        _custom_job_args(request)["--snapshot-manifest-uri"]
        for request in training.submit_requests
    }
    immutable_manifest_uri = (
        f"{ROOT_URI}/runs/{result['run_id']}/inputs/"
        "selected_source_manifest.json"
    )
    assert submitted_manifest_uris == {immutable_manifest_uri}
    immutable_ref = store.get_ref(immutable_manifest_uri)
    assert store.read_bytes(
        immutable_manifest_uri,
        generation=immutable_ref.generation,
    ) == selected_manifest_bytes
    assert training.restaged_manifest_bytes is not None
    assert store.read_bytes(snapshot["uri"]) == training.restaged_manifest_bytes
    assert training.restaged_manifest_bytes != selected_manifest_bytes


def test_training_failure_writes_terminal_evidence_without_registration(
    tmp_path,
    monkeypatch,
):
    store = RecordingStore(tmp_path / "store")
    snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    _seed_current_pointer(
        store,
        feature_month="2024-11",
        snapshot_digest="f" * 64,
    )
    store.clear_events()
    training = FakeTrainingBackend(
        store,
        terminal_state="JOB_STATE_FAILED",
    )
    registry = FakeRegistrySDK()
    batch = FakeBatchBackend(store)
    aliases = FakeAliasBackend(store)

    result = _run(
        monkeypatch,
        _deployment(),
        store,
        (training, registry, batch, aliases),
    )

    assert len(training.submit_requests) == 1
    assert _custom_job_args(training.submit_requests[0])[
        "--snapshot-manifest-uri"
    ] == (
        f"{ROOT_URI}/runs/{result['run_id']}/inputs/"
        "selected_source_manifest.json"
    )
    assert registry.upload_calls == []
    assert batch.submit_calls == []
    assert aliases.current_calls == []
    assert aliases.move_calls == []
    manifest = _assert_failed_evidence(store, result)
    assert manifest["phase"] == "FAILED"
    assert manifest["model_versions"] == {}


def test_registration_failure_abandons_earlier_candidates_and_stops_batch(
    tmp_path,
    monkeypatch,
):
    store = RecordingStore(tmp_path / "store")
    _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    _seed_current_pointer(
        store,
        feature_month="2024-11",
        snapshot_digest="f" * 64,
    )
    store.clear_events()
    training = FakeTrainingBackend(store)
    registry = FakeRegistrySDK(fail_horizon="6m")
    batch = FakeBatchBackend(store)
    aliases = FakeAliasBackend(store)

    result = _run(
        monkeypatch,
        _deployment(),
        store,
        (training, registry, batch, aliases),
    )

    assert [call["labels"]["horizon"] for call in registry.upload_calls] == [
        "0m",
        "6m",
    ]
    assert registry.abandoned_versions == [
        (
            f"projects/{PROJECT_ID}/locations/{REGION}/models/"
            "fewsnet-partitioned-rf-0m@101"
        )
    ]
    assert batch.submit_calls == []
    assert aliases.current_calls == []
    assert aliases.move_calls == []
    manifest = _assert_failed_evidence(store, result)
    assert set(manifest["model_versions"]) == {"0m"}


def test_one_batch_failure_prevents_promotion_and_abandons_all_candidates(
    tmp_path,
    monkeypatch,
):
    store = RecordingStore(tmp_path / "store")
    _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    _seed_current_pointer(
        store,
        feature_month="2024-11",
        snapshot_digest="f" * 64,
    )
    store.clear_events()
    training = FakeTrainingBackend(store)
    registry = FakeRegistrySDK()
    batch = FakeBatchBackend(store, fail_horizon="6m")
    aliases = FakeAliasBackend(store)

    result = _run(
        monkeypatch,
        _deployment(),
        store,
        (training, registry, batch, aliases),
    )

    assert [call["labels"]["fewsnet_horizon"] for call in batch.submit_calls] == [
        "0m",
        "6m",
    ]
    assert len(registry.abandoned_versions) == 3
    assert aliases.current_calls == []
    assert aliases.move_calls == []
    assert f"{ROOT_URI}/released/current.json" not in store.write_order
    manifest = _assert_failed_evidence(store, result)
    assert set(manifest["model_versions"]) == set(HORIZON_ORDER)
    assert set(manifest["batch_jobs"]) == {"0m", "6m"}


def test_output_failure_never_moves_aliases_and_is_not_retried(
    tmp_path,
    monkeypatch,
):
    store = RecordingStore(tmp_path / "store")
    _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    _seed_current_pointer(
        store,
        feature_month="2024-11",
        snapshot_digest="f" * 64,
    )
    store.clear_events()
    training = FakeTrainingBackend(store)
    registry = FakeRegistrySDK()
    batch = FakeBatchBackend(store, output_failure_horizon="6m")
    aliases = FakeAliasBackend(store)

    result = _run(
        monkeypatch,
        _deployment(),
        store,
        (training, registry, batch, aliases),
    )

    assert "error files" in result["error"]["message"]
    assert aliases.current_calls == []
    assert aliases.move_calls == []
    assert len(registry.abandoned_versions) == 3
    manifest = _assert_failed_evidence(store, result)
    assert manifest["retry_attempts"] == []
    assert [call["labels"]["fewsnet_horizon"] for call in batch.submit_calls] == [
        "0m",
        "6m",
    ]


def test_candidate_only_stops_after_output_validation_without_pointer_reads(
    tmp_path,
    monkeypatch,
):
    store = RecordingStore(tmp_path / "store")
    snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    _seed_current_pointer(
        store,
        feature_month="2024-12",
        snapshot_digest=snapshot["manifest"]["snapshot_content_sha256"],
    )
    store.clear_events()
    training, registry, batch, aliases = _backends(store)

    result = _run(
        monkeypatch,
        _deployment(),
        store,
        (training, registry, batch, aliases),
        promote=False,
    )

    assert result["status"] == "CANDIDATE_VALIDATED"
    assert result["phase"] == "OUTPUT_VALIDATED"
    assert f"{ROOT_URI}/released/current.json" not in store.read_order
    assert all("/released/" not in uri for uri in store.write_order)
    assert aliases.current_calls == []
    assert aliases.move_calls == []
    manifest = _read_json(
        store,
        f"{ROOT_URI}/runs/{result['run_id']}/run_manifest.json",
    )
    assert manifest["status"] == "candidate_validated"
    assert manifest["phase"] == "OUTPUT_VALIDATED"
    validate_payload("run-manifest", manifest)


def test_retry_transient_is_bounded_and_never_retries_validation_errors():
    module = _module()
    attempts = 0
    retry_numbers: list[int] = []

    def transient_operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ServiceUnavailable("try again")
        return "ok"

    assert module.retry_transient(
        transient_operation,
        max_retries=2,
        on_retry=retry_numbers.append,
    ) == "ok"
    assert attempts == 3
    assert retry_numbers == [1, 2]

    validation_attempts = 0

    def validation_failure():
        nonlocal validation_attempts
        validation_attempts += 1
        raise ValueError("invalid output")

    with pytest.raises(ValueError, match="invalid output"):
        module.retry_transient(
            validation_failure,
            max_retries=5,
            on_retry=lambda _attempt: pytest.fail("must not retry"),
        )
    assert validation_attempts == 1


def test_transient_retries_preserve_snapshot_image_artifacts_and_candidates(
    tmp_path,
    monkeypatch,
):
    module = _module()
    store = RecordingStore(tmp_path / "store")
    snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    _seed_current_pointer(
        store,
        feature_month="2024-11",
        snapshot_digest="f" * 64,
    )
    store.clear_events()
    training = FakeTrainingBackend(
        store,
        transient_failures=1,
        commit_before_transient=False,
    )
    registry = FakeRegistrySDK(transient_commit_horizon="6m")
    batch = FakeBatchBackend(store, transient_failure_horizon="12m")
    aliases = FakeAliasBackend(store)
    delays: list[float] = []
    promotion_calls: list[dict[str, object]] = []
    original_promotion = module.promote_and_publish

    def busy_once(**kwargs):
        promotion_calls.append(
            {
                "run_id": kwargs["run_id"],
                "snapshot_digest": kwargs[
                    "snapshot"
                ].snapshot_content_sha256,
                "versions": {
                    key: asdict(value)
                    for key, value in kwargs["registered_versions"].items()
                },
            }
        )
        if len(promotion_calls) == 1:
            raise PromotionBusy("lease busy")
        return original_promotion(**kwargs)

    monkeypatch.setenv("FEWSNET_SOURCE_GIT_COMMIT", SOURCE_COMMIT)
    monkeypatch.setattr(module, "_utc_now", lambda: NOW)
    monkeypatch.setattr(module, "_sleep", delays.append)
    monkeypatch.setattr(module, "promote_and_publish", busy_once)

    result = module.run_latest(
        _deployment(max_retries=2),
        store,
        training,
        registry,
        batch,
        aliases,
    )

    assert result["status"] == "RELEASED"
    assert [item["operation"] for item in result["retry_attempts"]] == [
        "training.submit",
        "registry.6m",
        "batch.submit.12m",
        "promotion",
    ]
    assert delays == [2, 2, 2, 2]
    assert len(training.submit_requests) == 2
    assert training.submit_requests[0] == training.submit_requests[1]
    assert len(training.jobs) == 1
    assert [call["labels"]["horizon"] for call in registry.upload_calls] == [
        "0m",
        "6m",
        "12m",
    ]
    assert all(
        call["serving_container_image_uri"] == IMAGE_URI
        for call in registry.upload_calls
    )
    batch_12m_calls = [
        call
        for call in batch.submit_calls
        if call["labels"]["fewsnet_horizon"] == "12m"
    ]
    assert len(batch_12m_calls) == 2
    assert batch_12m_calls[0] == batch_12m_calls[1]
    assert batch.submitted_input_refs["12m"][0] == (
        batch.submitted_input_refs["12m"][1]
    )
    assert batch.transient_failed == {"12m"}
    assert len(batch.jobs_by_display) == 3
    assert len(promotion_calls) == 2
    assert promotion_calls[0] == promotion_calls[1]
    assert promotion_calls[0]["snapshot_digest"] == snapshot["manifest"][
        "snapshot_content_sha256"
    ]
    assert all(
        version["artifact_uri"].startswith(
            f"{ROOT_URI}/suites/{result['suite_version']}/models/"
        )
        for version in promotion_calls[0]["versions"].values()
    )


def test_real_promotion_transient_retries_with_identical_release_identity(
    tmp_path,
    monkeypatch,
):
    module = _module()
    store = RecordingStore(tmp_path / "store")
    snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    _seed_current_pointer(
        store,
        feature_month="2024-11",
        snapshot_digest="f" * 64,
    )
    store.clear_events()
    training = FakeTrainingBackend(store)
    registry = FakeRegistrySDK()
    batch = FakeBatchBackend(store)
    aliases = TransientPromotionAliasBackend(store)
    delays: list[float] = []
    promotion_calls: list[dict[str, object]] = []
    original_promotion = module.promote_and_publish

    def recording_promotion(**kwargs):
        promotion_calls.append(
            {
                "run_id": kwargs["run_id"],
                "snapshot_digest": kwargs[
                    "snapshot"
                ].snapshot_content_sha256,
                "versions": {
                    key: asdict(value)
                    for key, value in kwargs["registered_versions"].items()
                },
                "suite_manifest": json.loads(
                    json.dumps(kwargs["suite_manifest"], sort_keys=True)
                ),
            }
        )
        return original_promotion(**kwargs)

    monkeypatch.setenv("FEWSNET_SOURCE_GIT_COMMIT", SOURCE_COMMIT)
    monkeypatch.setattr(module, "_utc_now", lambda: NOW)
    monkeypatch.setattr(module, "_sleep", delays.append)
    monkeypatch.setattr(module, "promote_and_publish", recording_promotion)

    result = module.run_latest(
        _deployment(max_retries=2),
        store,
        training,
        registry,
        batch,
        aliases,
    )

    assert result["status"] == "RELEASED"
    assert [item["operation"] for item in result["retry_attempts"]] == [
        "promotion"
    ]
    assert delays == [2]
    assert len(promotion_calls) == 2
    assert promotion_calls[0] == promotion_calls[1]
    assert promotion_calls[0]["run_id"] == result["run_id"]
    assert promotion_calls[0]["snapshot_digest"] == snapshot["manifest"][
        "snapshot_content_sha256"
    ]
    assert len(training.submit_requests) == 1
    assert len(registry.upload_calls) == 3
    assert len(batch.submit_calls) == 3
    assert aliases.transient_failures == 0
    assert aliases.move_attempts[0] == aliases.move_attempts[1]
    assert aliases.restore_calls == []
    assert all(
        version["artifact_uri"].startswith(
            f"{ROOT_URI}/suites/{result['suite_version']}/models/"
        )
        for version in promotion_calls[0]["versions"].values()
    )


def test_transient_failures_stop_after_exact_max_retries(
    tmp_path,
    monkeypatch,
):
    module = _module()
    store = RecordingStore(tmp_path / "store")
    _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    _seed_current_pointer(
        store,
        feature_month="2024-11",
        snapshot_digest="f" * 64,
    )
    store.clear_events()
    training = FakeTrainingBackend(
        store,
        transient_failures=3,
        commit_before_transient=False,
    )
    registry = FakeRegistrySDK()
    batch = FakeBatchBackend(store)
    aliases = FakeAliasBackend(store)
    delays: list[float] = []
    monkeypatch.setenv("FEWSNET_SOURCE_GIT_COMMIT", SOURCE_COMMIT)
    monkeypatch.setattr(module, "_utc_now", lambda: NOW)
    monkeypatch.setattr(module, "_sleep", delays.append)

    result = module.run_latest(
        _deployment(max_retries=2),
        store,
        training,
        registry,
        batch,
        aliases,
    )

    assert len(training.submit_requests) == 3
    assert result["status"] == "FAILED"
    assert [item["attempt"] for item in result["retry_attempts"]] == [1, 2]
    assert delays == [2, 4]
    assert registry.upload_calls == []
    assert batch.submit_calls == []
    _assert_failed_evidence(store, result)


def test_nontransient_suite_validation_failure_is_called_once_without_aliases(
    tmp_path,
    monkeypatch,
):
    module = _module()
    store = RecordingStore(tmp_path / "store")
    _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    _seed_current_pointer(
        store,
        feature_month="2024-11",
        snapshot_digest="f" * 64,
    )
    store.clear_events()
    training, registry, batch, aliases = _backends(store)
    validation_calls = 0

    def fail_validation(*_args, **_kwargs):
        nonlocal validation_calls
        validation_calls += 1
        raise ValueError("nontransient suite validation failure")

    monkeypatch.setenv("FEWSNET_SOURCE_GIT_COMMIT", SOURCE_COMMIT)
    monkeypatch.setattr(module, "_utc_now", lambda: NOW)
    monkeypatch.setattr(module, "_sleep", lambda _seconds: None)
    monkeypatch.setattr(module, "validate_prediction_suite", fail_validation)

    result = module.run_latest(
        _deployment(max_retries=5),
        store,
        training,
        registry,
        batch,
        aliases,
    )

    assert validation_calls == 1
    assert result["retry_attempts"] == []
    assert aliases.current_calls == []
    assert aliases.move_calls == []
    assert len(registry.abandoned_versions) == 3
    _assert_failed_evidence(store, result)


def test_promotion_indeterminate_is_terminal_without_destructive_recovery(
    tmp_path,
    monkeypatch,
):
    module = _module()
    store = RecordingStore(tmp_path / "store")
    _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    _seed_current_pointer(
        store,
        feature_month="2024-11",
        snapshot_digest="f" * 64,
    )
    store.clear_events()
    training, registry, batch, aliases = _backends(store)

    def indeterminate(**kwargs):
        registered_versions = kwargs["registered_versions"]
        for horizon_key in HORIZON_ORDER:
            version = registered_versions[horizon_key]
            aliases.move_alias(
                version.parent_model_resource_name,
                "production",
                version.version_resource_name,
            )
        suite_manifest = kwargs["suite_manifest"]
        suite_manifest_ref = put_immutable_or_verify(
            store,
            (
                f"{ROOT_URI}/suites/{suite_manifest['suite_version']}/"
                "suite_manifest.json"
            ),
            json.dumps(
                suite_manifest,
                sort_keys=True,
                separators=(",", ":"),
            ).encode(),
        )
        current_uri = f"{ROOT_URI}/released/current.json"
        current_ref = store.get_ref(current_uri)
        store.put_bytes(
            current_uri,
            json.dumps(
                {
                    "schema_version": "fewsnet-production-suite-pointer-v1",
                    "suite_version": suite_manifest["suite_version"],
                    "feature_month": suite_manifest["feature_month"],
                    "snapshot_content_sha256": suite_manifest[
                        "snapshot_ref"
                    ]["snapshot_content_sha256"],
                    "suite_manifest": asdict(suite_manifest_ref),
                    "released_at_utc": NOW.isoformat().replace("+00:00", "Z"),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode(),
            if_generation_match=current_ref.generation,
        )
        raise PromotionIndeterminate(
            "current pointer may have committed",
            uri=current_uri,
        )

    monkeypatch.setenv("FEWSNET_SOURCE_GIT_COMMIT", SOURCE_COMMIT)
    monkeypatch.setattr(module, "_utc_now", lambda: NOW)
    monkeypatch.setattr(module, "_sleep", lambda _seconds: None)
    monkeypatch.setattr(module, "promote_and_publish", indeterminate)

    result = module.run_latest(
        _deployment(),
        store,
        training,
        registry,
        batch,
        aliases,
    )

    assert result["status"] == "FAILED"
    assert result["indeterminate"] is True, result["error"]
    assert result["error"]["indeterminate"] is True
    assert aliases.restore_calls == []
    assert registry.abandoned_versions == []
    assert len(aliases.move_calls) == 3
    assert _read_json(
        store,
        f"{ROOT_URI}/released/current.json",
    )["suite_version"] == result["suite_version"]
    _assert_failed_evidence(store, result)


def test_released_promotion_evidence_failure_preserves_live_candidates(
    tmp_path,
    monkeypatch,
):
    module = _module()
    store = RecordingStore(tmp_path / "store")
    _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    _seed_current_pointer(
        store,
        feature_month="2024-11",
        snapshot_digest="f" * 64,
    )
    store.clear_events()
    training, registry, batch, aliases = _backends(store)
    original_put_bytes = store.put_bytes
    released_manifest_failure_injected = False

    def fail_released_run_manifest(uri, data, *, if_generation_match=None):
        nonlocal released_manifest_failure_injected
        if (
            not released_manifest_failure_injected
            and uri.endswith("/run_manifest.json")
            and json.loads(data)["phase"] == "RELEASED"
        ):
            released_manifest_failure_injected = True
            raise OSError("injected RELEASED run-manifest write failure")
        return original_put_bytes(
            uri,
            data,
            if_generation_match=if_generation_match,
        )

    monkeypatch.setattr(store, "put_bytes", fail_released_run_manifest)
    monkeypatch.setenv("FEWSNET_SOURCE_GIT_COMMIT", SOURCE_COMMIT)
    monkeypatch.setattr(module, "_utc_now", lambda: NOW)
    monkeypatch.setattr(module, "_sleep", lambda _seconds: None)

    result = module.run_latest(
        _deployment(),
        store,
        training,
        registry,
        batch,
        aliases,
    )

    assert released_manifest_failure_injected is True
    assert registry.abandoned_versions == []
    assert result["status"] == "FAILED"
    assert result["indeterminate"] is False
    assert result["evidence_warning"] is True
    assert result["release_status"] == "RELEASED"
    assert result["error"]["evidence_warning"] is True
    assert len(aliases.move_calls) == 3
    assert aliases.restore_calls == []
    assert _read_json(
        store,
        f"{ROOT_URI}/released/current.json",
    )["suite_version"] == result["suite_version"]
    _assert_failed_evidence(store, result)


@pytest.mark.parametrize(
    "failure_kind",
    [
        "invalid_deployment_json",
        "invalid_deployment",
        "source_commit_mismatch",
        "discovery_failure",
    ],
)
def test_cli_preflight_failures_are_structured_and_create_no_run_artifacts(
    tmp_path,
    monkeypatch,
    capsys,
    failure_kind,
):
    module = _module()
    store = RecordingStore(tmp_path / "store")
    deployment = _deployment()
    deployment_bytes = json.dumps(
        deployment,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    if failure_kind == "invalid_deployment_json":
        deployment_bytes = b"{not-json"
    elif failure_kind == "invalid_deployment":
        deployment.pop("region")
        deployment_bytes = json.dumps(
            deployment,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    deployment_uri = f"{ROOT_URI}/config/deployment.json"
    put_immutable_or_verify(store, deployment_uri, deployment_bytes)
    if failure_kind == "source_commit_mismatch":
        monkeypatch.setenv("FEWSNET_SOURCE_GIT_COMMIT", "2" * 40)
    else:
        monkeypatch.setenv("FEWSNET_SOURCE_GIT_COMMIT", SOURCE_COMMIT)
    monkeypatch.setattr(
        module.GCSArtifactStore,
        "from_default",
        classmethod(lambda _cls: store),
    )
    monkeypatch.setattr(
        module,
        "_default_backends",
        lambda _region: _backends(store),
    )

    exit_code = module.main(["--deployment-manifest-uri", deployment_uri])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    error = json.loads(captured.err)
    assert error["status"] == "FAILED"
    assert error["preflight"] is True
    assert error["error"]["exception_type"]
    assert error["error"]["message"]
    assert "run_id" not in error
    assert "suite_version" not in error
    assert "phase" not in error
    assert "run_manifest" not in error
    assert store.list(f"{ROOT_URI}/runs/") == []


def test_error_artifact_failure_still_returns_formal_failure_and_terminal_manifest(
    tmp_path,
    monkeypatch,
):
    store = ErrorArtifactFailureStore(tmp_path / "store")
    snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    store.clear_events()

    result = _run(
        monkeypatch,
        _deployment(),
        store,
        _backends(store),
        snapshot_manifest_uri=snapshot["uri"],
    )

    assert store.primary_failure_injected is True
    assert store.error_artifact_attempts == 1
    assert result["status"] == "FAILED"
    assert result["preflight"] is False
    assert result["run_id"] == result["suite_version"]
    assert result["error"]["message"] == "injected post-discovery primary failure"
    assert result["error_artifact_error"]["message"] == (
        "injected error artifact failure"
    )
    manifest = _read_json(
        store,
        f"{ROOT_URI}/runs/{result['run_id']}/run_manifest.json",
    )
    assert manifest["phase"] == "FAILED"
    assert manifest["failure"]["message"] == (
        "injected post-discovery primary failure"
    )


def test_cli_error_artifact_failure_is_not_reclassified_as_preflight(
    tmp_path,
    monkeypatch,
    capsys,
):
    module = _module()
    store = ErrorArtifactFailureStore(tmp_path / "store")
    snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    deployment_uri = f"{ROOT_URI}/config/deployment.json"
    put_immutable_or_verify(
        store,
        deployment_uri,
        json.dumps(
            _deployment(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode(),
    )
    store.clear_events()
    monkeypatch.setenv("FEWSNET_SOURCE_GIT_COMMIT", SOURCE_COMMIT)
    monkeypatch.setattr(module, "_utc_now", lambda: NOW)
    monkeypatch.setattr(module, "_sleep", lambda _seconds: None)
    monkeypatch.setattr(
        module.GCSArtifactStore,
        "from_default",
        classmethod(lambda _cls: store),
    )
    monkeypatch.setattr(
        module,
        "_default_backends",
        lambda _region: _backends(store),
    )

    exit_code = module.main(
        [
            "--deployment-manifest-uri",
            deployment_uri,
            "--snapshot-manifest-uri",
            snapshot["uri"],
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    result = json.loads(captured.err)
    assert result["status"] == "FAILED"
    assert result["preflight"] is False
    assert result["run_id"] == result["suite_version"]
    assert result["error"]["message"] == "injected post-discovery primary failure"
    assert result["error_artifact_error"]["message"] == (
        "injected error artifact failure"
    )
    assert store.error_artifact_attempts == 1


@pytest.mark.parametrize(
    "fail_readback",
    (False, True),
    ids=("mismatched", "unreadable"),
)
def test_error_artifact_and_terminal_manifest_failures_remain_formal_and_indeterminate(
    tmp_path,
    monkeypatch,
    fail_readback,
):
    store = ErrorArtifactAndTerminalFailureStore(
        tmp_path / "store",
        fail_readback=fail_readback,
    )
    snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    store.clear_events()

    result = _run(
        monkeypatch,
        _deployment(),
        store,
        _backends(store),
        snapshot_manifest_uri=snapshot["uri"],
    )

    assert result["status"] == "FAILED"
    assert result["preflight"] is False
    assert result["evidence_indeterminate"] is True
    assert result["run_id"] == result["suite_version"]
    assert result["run_manifest"] is None
    assert result["error"]["exception_type"] == "ServiceUnavailable"
    assert result["error_artifact_error"]["message"] == (
        "injected error artifact failure"
    )
    assert result["terminal_manifest_error"]["exception_type"] == (
        "GenerationConflict"
    )
    assert store.error_artifact_attempts == 1
    manifest_uri = f"{ROOT_URI}/runs/{result['run_id']}/run_manifest.json"
    assert store.get_ref(manifest_uri).generation == "2"


def test_first_post_discovery_evidence_failure_writes_terminal_artifacts(
    tmp_path,
    monkeypatch,
):
    module = _module()
    store = RecordingStore(tmp_path / "store")
    snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    store.clear_events()
    backends = _backends(store)
    original_put_bytes = store.put_bytes
    evidence_failure_injected = False

    def fail_selected_manifest_once(uri, data, *, if_generation_match=None):
        nonlocal evidence_failure_injected
        if (
            not evidence_failure_injected
            and uri.endswith("/inputs/selected_source_manifest.json")
        ):
            evidence_failure_injected = True
            raise OSError("injected selected-manifest evidence failure")
        return original_put_bytes(
            uri,
            data,
            if_generation_match=if_generation_match,
        )

    monkeypatch.setattr(store, "put_bytes", fail_selected_manifest_once)
    monkeypatch.setenv("FEWSNET_SOURCE_GIT_COMMIT", SOURCE_COMMIT)
    monkeypatch.setattr(module, "_utc_now", lambda: NOW)

    result = module.run_latest(
        _deployment(),
        store,
        *backends,
        snapshot_manifest_uri=snapshot["uri"],
    )

    assert evidence_failure_injected is True
    assert result["status"] == "FAILED"
    assert result.get("preflight") is not True
    assert result["run_id"] == result["suite_version"]
    manifest = _assert_failed_evidence(store, result)
    for key, value in asdict(snapshot["ref"]).items():
        assert manifest["snapshot_ref"][key] == value


def test_cli_candidate_only_uses_injected_boundaries_and_returns_zero(
    tmp_path,
    monkeypatch,
    capsys,
):
    module = _module()
    store = RecordingStore(tmp_path / "store")
    snapshot = _seed_snapshot(
        tmp_path,
        store,
        latest_feature_month="2024-12",
        created_at_utc="2026-07-21T00:00:00Z",
    )
    deployment_uri = f"{ROOT_URI}/config/deployment.json"
    put_immutable_or_verify(
        store,
        deployment_uri,
        json.dumps(
            _deployment(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode(),
    )
    backends = _backends(store)
    monkeypatch.setenv("FEWSNET_SOURCE_GIT_COMMIT", SOURCE_COMMIT)
    monkeypatch.setattr(module, "_utc_now", lambda: NOW)
    monkeypatch.setattr(module, "_sleep", lambda _seconds: None)
    monkeypatch.setattr(
        module.GCSArtifactStore,
        "from_default",
        classmethod(lambda _cls: store),
    )
    monkeypatch.setattr(module, "_default_backends", lambda _region: backends)

    exit_code = module.main(
        [
            "--deployment-manifest-uri",
            deployment_uri,
            "--snapshot-manifest-uri",
            snapshot["uri"],
            "--candidate-only",
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "CANDIDATE_VALIDATED"
    assert output["phase"] == "OUTPUT_VALIDATED"
    assert f"{ROOT_URI}/inputs/snapshots/" not in store.list_order
