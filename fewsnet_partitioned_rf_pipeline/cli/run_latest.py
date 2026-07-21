"""Deterministic orchestration for the latest FEWSNET model suite."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any
import uuid

from google.api_core.exceptions import (
    DeadlineExceeded,
    ServiceUnavailable,
    TooManyRequests,
)

try:
    from google.auth.exceptions import TransportError as GoogleTransportError
except ImportError:  # pragma: no cover - google-auth is a pinned dependency.
    GoogleTransportError = ConnectionError  # type: ignore[misc,assignment]

try:
    from requests.exceptions import (
        ConnectionError as RequestsConnectionError,
        Timeout as RequestsTimeout,
    )
except ImportError:  # pragma: no cover - requests ships with google clients.
    RequestsConnectionError = ConnectionError  # type: ignore[misc,assignment]
    RequestsTimeout = TimeoutError  # type: ignore[misc,assignment]

from fewsnet_partitioned_rf_pipeline.cli.infer import (
    _localize_raw_output,
    normalize_and_publish_batch_output,
)
from fewsnet_partitioned_rf_pipeline.cli.train import (
    _localize_snapshot,
    _validate_localized_snapshot,
)
from fewsnet_partitioned_rf_pipeline.config import (
    FEATURE_CONTRACT_PATH,
    HORIZON_KEYS,
    HORIZON_MONTHS,
    PARTITION_ASSET_PATH,
    PARTITION_ASSET_SHA256,
)
from fewsnet_partitioned_rf_pipeline.core.horizons import (
    select_latest_inference_frame,
)
from fewsnet_partitioned_rf_pipeline.core.preprocessing import (
    Stage3FeatureBuilder,
    load_feature_contract,
)
from fewsnet_partitioned_rf_pipeline.core.types import (
    BatchJobRef,
    ObjectRef,
    RegisteredModelVersion,
    RunPhase,
    SnapshotManifest,
)
from fewsnet_partitioned_rf_pipeline.core.validation import (
    PredictionSuiteEntry,
    validate_prediction_suite,
)
from fewsnet_partitioned_rf_pipeline.schemas import (
    validate_deployment,
    validate_payload,
)
from fewsnet_partitioned_rf_pipeline.vertex.batch_prediction import (
    VertexBatchBackend,
    submit_batch_prediction,
    wait_batch_prediction,
    write_batch_input_jsonl,
)
from fewsnet_partitioned_rf_pipeline.vertex.promotion import (
    PromotionBusy,
    PromotionIndeterminate,
    VertexAliasBackend,
    promote_and_publish,
)
from fewsnet_partitioned_rf_pipeline.vertex.registry import (
    mark_registered_versions_abandoned,
    register_candidate_version,
    suite_version_alias,
)
from fewsnet_partitioned_rf_pipeline.vertex.storage import (
    ArtifactStore,
    GCSArtifactStore,
    GenerationConflict,
    put_immutable_or_verify,
)
from fewsnet_partitioned_rf_pipeline.vertex.training_job import (
    TrainingCustomJobConfig,
    submit_and_persist_training_custom_job,
    wait_for_training_custom_job,
)


_REVISION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
_MONTH_PATTERN = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_HORIZON_ORDER = tuple(HORIZON_KEYS[months] for months in HORIZON_MONTHS)
_RUNNING_STATUS = "running"
_utc_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
_sleep: Callable[[float], None] = time.sleep

RETRYABLE_EXCEPTIONS = (
    TooManyRequests,
    ServiceUnavailable,
    DeadlineExceeded,
    PromotionBusy,
    GoogleTransportError,
    RequestsConnectionError,
    RequestsTimeout,
)


@dataclass(frozen=True)
class _SelectedSnapshot:
    snapshot: SnapshotManifest
    manifest_ref: ObjectRef
    manifest_bytes: bytes


def retry_transient(
    operation: Callable[[], Any],
    *,
    max_retries: int,
    on_retry: Callable[[int], None],
) -> Any:
    """Retry only the explicitly transient exception classes."""
    if isinstance(max_retries, bool) or not isinstance(max_retries, int):
        raise TypeError("max_retries must be an integer")
    if max_retries < 0:
        raise ValueError("max_retries must be nonnegative")
    if not callable(operation) or not callable(on_retry):
        raise TypeError("operation and on_retry must be callable")
    for attempt in range(max_retries + 1):
        try:
            return operation()
        except RETRYABLE_EXCEPTIONS:
            if attempt == max_retries:
                raise
            on_retry(attempt + 1)
    raise AssertionError("retry loop ended without returning or raising")


class _RunState:
    def __init__(
        self,
        *,
        store: ArtifactStore,
        uri: str,
        run_id: str,
        suite_version: str,
        selected: _SelectedSnapshot,
    ) -> None:
        self.store = store
        self.uri = uri
        self.ref: ObjectRef | None = None
        self.payload: dict[str, Any] = {
            "schema_version": "fewsnet-run-manifest-v1",
            "run_id": run_id,
            "suite_version": suite_version,
            "phase": RunPhase.DISCOVERED.value,
            "status": _RUNNING_STATUS,
            "snapshot_ref": {
                **asdict(selected.manifest_ref),
                "snapshot_id": selected.snapshot.snapshot_id,
                "snapshot_content_sha256": (
                    selected.snapshot.snapshot_content_sha256
                ),
            },
            "model_versions": {},
            "batch_jobs": {},
            "hard_gates": {},
            "timestamps": {},
            "retry_attempts": [],
            "failure": None,
        }

    @property
    def run_id(self) -> str:
        return str(self.payload["run_id"])

    @property
    def suite_version(self) -> str:
        return str(self.payload["suite_version"])

    def transition(
        self,
        phase: RunPhase,
        *,
        status: str = _RUNNING_STATUS,
        gates: Mapping[str, bool] | None = None,
    ) -> None:
        self.payload["phase"] = phase.value
        self.payload["status"] = status
        if gates:
            self.payload["hard_gates"].update(dict(gates))
        self.payload["timestamps"][phase.value.lower()] = _timestamp(_utc_now())
        self._write()

    def record_model(self, version: RegisteredModelVersion) -> None:
        self.payload["model_versions"][version.horizon_key] = asdict(version)
        self._write()

    def record_batch(self, job: BatchJobRef) -> None:
        self.payload["batch_jobs"][job.horizon_key] = asdict(job)
        self._write()

    def record_retry(
        self,
        operation: str,
        retry_number: int,
        error: BaseException,
    ) -> None:
        self.payload["retry_attempts"].append(
            {
                "operation": operation,
                "attempt": retry_number,
                "timestamp_utc": _timestamp(_utc_now()),
                "error": f"{type(error).__name__}: {error}",
            }
        )
        self._write()

    def fail(self, error: BaseException) -> None:
        failure = {
            "exception_type": type(error).__name__,
            "message": str(error) or type(error).__name__,
            "timestamp_utc": _timestamp(_utc_now()),
        }
        self.payload["failure"] = failure
        self.payload["phase"] = RunPhase.FAILED.value
        self.payload["status"] = "failed"
        self.payload["timestamps"][RunPhase.FAILED.value.lower()] = failure[
            "timestamp_utc"
        ]
        self._write()

    def _write(self) -> None:
        validate_payload("run-manifest", self.payload)
        expected_generation: str | int = (
            0 if self.ref is None else self.ref.generation
        )
        payload_bytes = _canonical_json(self.payload)
        try:
            self.ref = self.store.put_bytes(
                self.uri,
                payload_bytes,
                if_generation_match=expected_generation,
            )
        except Exception:
            try:
                committed_ref = self.store.get_ref(self.uri)
                if int(committed_ref.generation) > int(expected_generation):
                    committed_bytes = self.store.read_bytes(
                        self.uri,
                        generation=committed_ref.generation,
                    )
                    if committed_bytes == payload_bytes:
                        self.ref = committed_ref
            except Exception:
                pass
            raise


def run_latest(
    deployment: Mapping[str, Any],
    store: ArtifactStore,
    training_backend: Any,
    registry_backend: Any,
    batch_backend: Any,
    alias_backend: Any,
    *,
    revision_id: str | None = None,
    snapshot_manifest_uri: str | None = None,
    promote: bool = True,
) -> dict[str, Any]:
    """Run one monotonic discover-to-release FEWSNET suite orchestration."""
    state: _RunState | None = None
    registered: dict[str, RegisteredModelVersion] = {}
    root_uri: str | None = None
    release_committed = False
    try:
        if not isinstance(deployment, Mapping):
            raise TypeError("deployment must be a mapping")
        deployment_payload = dict(deployment)
        validate_deployment(deployment_payload)
        source_git_commit = str(deployment_payload["source_git_commit"])
        if os.environ.get("FEWSNET_SOURCE_GIT_COMMIT") != source_git_commit:
            raise ValueError(
                "deployment source_git_commit must equal image environment "
                "FEWSNET_SOURCE_GIT_COMMIT"
            )
        if revision_id is not None and (
            not isinstance(revision_id, str)
            or _REVISION_PATTERN.fullmatch(revision_id) is None
        ):
            raise ValueError(
                "revision_id must match ^[a-z0-9][a-z0-9-]{0,31}$"
            )

        root_uri = str(deployment_payload["object_store_root_uri"]).rstrip("/")
        selected = _discover_snapshot(
            store,
            root_uri=root_uri,
            explicit_uri=snapshot_manifest_uri,
        )
        feature_month = selected.snapshot.latest_feature_month
        run_stamp = _utc_now().strftime("%Y%m%dT%H%M%SZ")
        suite_version = (
            f"fewsnet-prf-{feature_month.replace('-', '')}-"
            f"{source_git_commit[:8]}-"
            f"{selected.snapshot.snapshot_content_sha256[:8]}-"
            f"{('rev-' + revision_id + '-') if revision_id else ''}"
            f"{run_stamp}"
        )
        run_id = suite_version
        run_root_uri = f"{root_uri}/runs/{run_id}"
        suite_root_uri = f"{root_uri}/suites/{suite_version}"
        state = _RunState(
            store=store,
            uri=f"{run_root_uri}/run_manifest.json",
            run_id=run_id,
            suite_version=suite_version,
            selected=selected,
        )
        state.transition(
            RunPhase.DISCOVERED,
            gates={"deployment_validated": True, "snapshot_discovered": True},
        )
        selected_manifest_ref = put_immutable_or_verify(
            store,
            f"{run_root_uri}/inputs/selected_source_manifest.json",
            selected.manifest_bytes,
        )
        snapshot_evidence = _canonical_json(
            {
                "manifest": asdict(selected.manifest_ref),
                "snapshot_id": selected.snapshot.snapshot_id,
                "snapshot_content_sha256": (
                    selected.snapshot.snapshot_content_sha256
                ),
            }
        )
        input_snapshot_ref = put_immutable_or_verify(
            store,
            f"{run_root_uri}/input_snapshot_ref.json",
            snapshot_evidence,
        )

        if promote:
            current = _read_current_pointer(store, root_uri)
            if current is not None:
                current_month = str(current["feature_month"])
                current_digest = str(current["snapshot_content_sha256"])
                if current_month > feature_month:
                    raise ValueError(
                        "current production has a newer feature month"
                    )
                if current_month == feature_month and current_digest == (
                    selected.snapshot.snapshot_content_sha256
                ):
                    state.transition(
                        RunPhase.NOOP,
                        status="noop",
                        gates={"current_pointer_match": True},
                    )
                    return _result(state, "NOOP", current_pointer=current)
                if (
                    current_month == feature_month
                    and current_digest
                    != selected.snapshot.snapshot_content_sha256
                    and revision_id is None
                ):
                    raise ValueError(
                        "same feature month has a different snapshot checksum; "
                        "revision_id is required"
                    )

        with tempfile.TemporaryDirectory(prefix="fewsnet-run-latest-") as temp_dir:
            temp_root = Path(temp_dir)
            localized = _localize_snapshot(
                selected.snapshot,
                store,
                temp_root / "snapshot",
            )
            panel = _validate_localized_snapshot(selected.snapshot, localized)
            feature_contract = load_feature_contract(FEATURE_CONTRACT_PATH)
            feature_frame = Stage3FeatureBuilder().transform(
                panel,
                feature_contract,
            )
            admin_universe_bytes = _read_ref_bytes(
                store,
                selected.snapshot.admin_universe,
            )
            state.transition(
                RunPhase.INPUT_VALIDATED,
                gates={"snapshot_artifacts_validated": True},
            )

            training_config = TrainingCustomJobConfig(
                project_id=str(deployment_payload["project_id"]),
                region=str(deployment_payload["region"]),
                run_id=run_id,
                job_id=f"fewsnet-train-{run_id}",
                snapshot_manifest_uri=selected_manifest_ref.uri,
                suite_version=suite_version,
                run_root_uri=run_root_uri,
                model_root_uri=f"{suite_root_uri}/models",
                container_image_uri=str(
                    deployment_payload["container_image_uri"]
                ),
                container_image_digest=str(
                    deployment_payload["container_image_digest"]
                ),
                source_git_commit=source_git_commit,
                training_service_account=str(
                    deployment_payload["training_service_account"]
                ),
                training_machine_type=str(
                    deployment_payload["training_machine_type"]
                ),
                training_timeout_seconds=int(
                    deployment_payload["training_timeout_seconds"]
                ),
            )
            state.transition(RunPhase.TRAINING)
            submitted_training = _retry(
                state,
                "training.submit",
                int(deployment_payload["max_retries"]),
                lambda: submit_and_persist_training_custom_job(
                    training_config,
                    backend=training_backend,
                    store=store,
                ),
            )
            training_name = _required_string(
                "submitted training job name",
                submitted_training.get("name"),
            )
            completed_training = _retry(
                state,
                "training.wait",
                int(deployment_payload["max_retries"]),
                lambda: wait_for_training_custom_job(
                    training_name,
                    backend=training_backend,
                    training_timeout_seconds=int(
                        deployment_payload["training_timeout_seconds"]
                    ),
                    sleep=_sleep,
                ),
            )
            if completed_training.get("state") != "JOB_STATE_SUCCEEDED":
                raise RuntimeError(
                    "FEWSNET training Custom Job did not succeed: "
                    f"{completed_training.get('state')}"
                )
            training_result, package_manifests = _verified_training_result(
                store,
                run_root_uri=run_root_uri,
                suite_root_uri=suite_root_uri,
                suite_version=suite_version,
                snapshot=selected.snapshot,
                deployment=deployment_payload,
            )
            state.transition(
                RunPhase.PACKAGED,
                gates={"training_succeeded": True, "packages_verified": True},
            )

            for horizon_key in _HORIZON_ORDER:
                artifact_uri = str(
                    training_result["packages"][horizon_key]["uri"]
                )

                def update_manifest(
                    version: RegisteredModelVersion,
                ) -> None:
                    state.record_model(version)

                registered[horizon_key] = _retry(
                    state,
                    f"registry.{horizon_key}",
                    int(deployment_payload["max_retries"]),
                    lambda horizon_key=horizon_key, artifact_uri=artifact_uri: (
                        register_candidate_version(
                            project_id=str(deployment_payload["project_id"]),
                            region=str(deployment_payload["region"]),
                            run_root_uri=run_root_uri,
                            suite_version=suite_version,
                            horizon_key=horizon_key,
                            artifact_uri=artifact_uri,
                            image_uri=str(
                                deployment_payload["container_image_uri"]
                            ),
                            image_digest=str(
                                deployment_payload["container_image_digest"]
                            ),
                            source_git_commit=source_git_commit,
                            version_description=(
                                "immutable FEWSNET candidate suite "
                                f"{suite_version}"
                            ),
                            labels={
                                "fewsnet_run": hashlib.sha256(
                                    run_id.encode("utf-8")
                                ).hexdigest()[:16]
                            },
                            store=store,
                            update_run_manifest=update_manifest,
                            sdk=registry_backend,
                        )
                    ),
                )
            state.transition(
                RunPhase.REGISTERED_CANDIDATE,
                gates={"candidates_registered": True},
            )

            state.transition(RunPhase.BATCH_PREDICTING)
            entries: dict[str, PredictionSuiteEntry] = {}
            for horizon_months in HORIZON_MONTHS:
                horizon_key = HORIZON_KEYS[horizon_months]
                input_frame = select_latest_inference_frame(
                    feature_frame,
                    selected.snapshot.latest_feature_month,
                    horizon_months,
                )
                input_path = temp_root / "batch" / horizon_key / "input.jsonl"
                write_batch_input_jsonl(
                    input_frame,
                    feature_contract,
                    input_path,
                )
                input_bytes = input_path.read_bytes()
                input_uri = (
                    f"{run_root_uri}/batch_prediction/{horizon_key}/input.jsonl"
                )
                input_ref = put_immutable_or_verify(store, input_uri, input_bytes)
                destination_prefix = (
                    f"{run_root_uri}/batch_prediction/{horizon_key}/raw"
                )
                submission_config = {
                    "deployment": deployment_payload,
                    "run_id": run_id,
                    "horizon_key": horizon_key,
                    "model_ref": registered[horizon_key],
                    "input_uri": input_uri,
                    "destination_prefix": destination_prefix,
                    "job_display_name": (
                        f"fewsnet-batch-{run_id}-{horizon_key}"
                    ),
                    "labels": {
                        "fewsnet_mode": "batch-prediction",
                        "fewsnet_run": hashlib.sha256(
                            run_id.encode("utf-8")
                        ).hexdigest()[:16],
                        "fewsnet_horizon": horizon_key,
                    },
                }
                submitted_job = _retry(
                    state,
                    f"batch.submit.{horizon_key}",
                    int(deployment_payload["max_retries"]),
                    lambda submission_config=submission_config: (
                        submit_batch_prediction(
                            submission_config,
                            batch_backend,
                        )
                    ),
                )
                submitted_input_ref = store.get_ref(submitted_job.input_uri)
                if submitted_input_ref != input_ref:
                    raise GenerationConflict(
                        "submitted Batch input changed after exact binding"
                    )
                state.record_batch(submitted_job)
                completed_job = _retry(
                    state,
                    f"batch.wait.{horizon_key}",
                    int(deployment_payload["max_retries"]),
                    lambda submitted_job=submitted_job: wait_batch_prediction(
                        submitted_job,
                        int(deployment_payload["batch_timeout_seconds"]),
                        batch_backend,
                        sleep=_sleep,
                    ),
                )
                state.record_batch(completed_job)
                raw_paths = _localize_raw_output(
                    _required_string(
                        "Batch output directory",
                        completed_job.gcs_output_directory,
                    ),
                    store,
                    temp_root / "raw" / horizon_key,
                )
                run_csv_uri = (
                    f"{run_root_uri}/predictions/{horizon_key}.csv"
                )
                suite_csv_uri = (
                    f"{suite_root_uri}/predictions/{horizon_key}.csv"
                )
                predictions = normalize_and_publish_batch_output(
                    raw_paths=raw_paths,
                    input_frame=input_frame,
                    model_ref=registered[horizon_key],
                    suite_version=suite_version,
                    run_csv_uri=run_csv_uri,
                    suite_csv_uri=suite_csv_uri,
                    store=store,
                )
                run_prediction = store.get_ref(run_csv_uri)
                suite_prediction = store.get_ref(suite_csv_uri)
                prediction_bytes = _read_ref_bytes(store, run_prediction)
                if _read_ref_bytes(store, suite_prediction) != prediction_bytes:
                    raise GenerationConflict(
                        "run and suite prediction bytes differ"
                    )
                entries[horizon_key] = PredictionSuiteEntry(
                    frame=predictions,
                    batch_input=input_ref,
                    submitted_batch_input=submitted_input_ref,
                    batch_snapshot_content_sha256=(
                        selected.snapshot.snapshot_content_sha256
                    ),
                    package_manifest=package_manifests[horizon_key],
                    admin_universe_bytes=admin_universe_bytes,
                    batch_input_bytes=input_bytes,
                    batch_job=completed_job,
                    run_prediction=run_prediction,
                    suite_prediction=suite_prediction,
                    prediction_csv_bytes=prediction_bytes,
                    input_snapshot_ref=input_snapshot_ref,
                    input_snapshot_ref_bytes=snapshot_evidence,
                )

            validation_summary = validate_prediction_suite(
                entries,
                selected.snapshot,
                registered,
            )
            state.transition(
                RunPhase.OUTPUT_VALIDATED,
                status=("candidate_validated" if not promote else _RUNNING_STATUS),
                gates={"batch_jobs_succeeded": True, "outputs_validated": True},
            )
            suite_manifest = _suite_manifest(
                deployment_payload,
                selected,
                registered,
                entries,
                suite_version=suite_version,
            )
            if not promote:
                return _result(
                    state,
                    "CANDIDATE_VALIDATED",
                    validation=validation_summary,
                    suite_manifest=suite_manifest,
                )

            state.transition(RunPhase.PROMOTING)
            lease_id = f"promotion-{uuid.uuid5(uuid.NAMESPACE_URL, run_id)}"
            promotion_result = _retry(
                state,
                "promotion",
                int(deployment_payload["max_retries"]),
                lambda: promote_and_publish(
                    store=store,
                    alias_backend=alias_backend,
                    root_uri=root_uri,
                    run_id=run_id,
                    snapshot=selected.snapshot,
                    registered_versions=registered,
                    suite_manifest=suite_manifest,
                    lease_id=lease_id,
                    utc_now=_utc_now,
                    revision_id=revision_id,
                ),
            )
            if promotion_result["status"] == "NOOP":
                if promotion_result.get("abandon_candidates"):
                    mark_registered_versions_abandoned(
                        list(registered.values()),
                        project_id=str(deployment_payload["project_id"]),
                        region=str(deployment_payload["region"]),
                        sdk=registry_backend,
                    )
                state.transition(
                    RunPhase.NOOP,
                    status="noop",
                    gates={"promotion_noop": True},
                )
                return _result(
                    state,
                    "NOOP",
                    promotion=promotion_result,
                    validation=validation_summary,
                )
            if promotion_result["status"] != "RELEASED":
                raise RuntimeError(
                    "promotion returned an unsupported terminal status"
                )
            release_committed = True
            state.transition(
                RunPhase.RELEASED,
                status="released",
                gates={"promotion_released": True},
            )
            return _result(
                state,
                "RELEASED",
                promotion=promotion_result,
                validation=validation_summary,
            )
    except Exception as exc:
        abandonment_error: str | None = None
        promotion_indeterminate = isinstance(exc, PromotionIndeterminate)
        preserve_live_candidates = promotion_indeterminate or release_committed
        if (
            registered
            and isinstance(deployment, Mapping)
            and not preserve_live_candidates
        ):
            try:
                mark_registered_versions_abandoned(
                    list(registered.values()),
                    project_id=str(deployment.get("project_id", "")),
                    region=str(deployment.get("region", "")),
                    sdk=registry_backend,
                )
            except Exception as abandon_exc:  # pragma: no cover - best effort.
                abandonment_error = (
                    f"{type(abandon_exc).__name__}: {abandon_exc}"
                )
        if state is not None and root_uri is not None:
            error_payload: dict[str, Any] = {
                "exception_type": type(exc).__name__,
                "message": str(exc) or type(exc).__name__,
                "timestamp_utc": _timestamp(_utc_now()),
                "run_id": state.run_id,
                "suite_version": state.suite_version,
                "indeterminate": promotion_indeterminate,
            }
            if release_committed:
                error_payload["evidence_warning"] = True
                error_payload["release_status"] = "RELEASED"
            if abandonment_error is not None:
                error_payload["abandonment_error"] = abandonment_error
            put_immutable_or_verify(
                store,
                f"{root_uri}/runs/{state.run_id}/error.json",
                _canonical_json(error_payload),
            )
            state.fail(exc)
            return _result(
                state,
                "FAILED",
                error=error_payload,
                indeterminate=promotion_indeterminate,
                evidence_warning=release_committed,
                release_status=("RELEASED" if release_committed else None),
            )
        return _preflight_failure(exc)


def _retry(
    state: _RunState,
    operation_name: str,
    max_retries: int,
    operation: Callable[[], Any],
) -> Any:
    def on_retry(retry_number: int) -> None:
        error = sys.exception()
        if not isinstance(error, BaseException):
            raise RuntimeError("retry callback lost the active exception")
        state.record_retry(operation_name, retry_number, error)
        _sleep(min(60, 2**retry_number))

    return retry_transient(
        operation,
        max_retries=max_retries,
        on_retry=on_retry,
    )


def _discover_snapshot(
    store: ArtifactStore,
    *,
    root_uri: str,
    explicit_uri: str | None,
) -> _SelectedSnapshot:
    if explicit_uri is not None:
        if not isinstance(explicit_uri, str) or not explicit_uri:
            raise ValueError("snapshot_manifest_uri must be a nonempty string")
        refs = [store.get_ref(explicit_uri)]
    else:
        refs = [
            ref
            for ref in store.list(f"{root_uri}/inputs/snapshots/")
            if ref.uri.endswith("/source_manifest.json")
        ]
    if not refs:
        raise FileNotFoundError("no complete FEWSNET source snapshots were found")
    candidates = [_load_snapshot_candidate(store, ref) for ref in refs]
    selected = max(
        candidates,
        key=lambda item: (
            item.snapshot.latest_feature_month,
            item.snapshot.created_at_utc,
            item.snapshot.snapshot_id,
        ),
    )
    expected_uri = (
        f"{root_uri}/inputs/snapshots/{selected.snapshot.snapshot_id}/"
        "source_manifest.json"
    )
    if selected.manifest_ref.uri != expected_uri:
        raise ValueError("selected snapshot manifest URI is not canonical")
    return selected


def _load_snapshot_candidate(
    store: ArtifactStore,
    ref: ObjectRef,
) -> _SelectedSnapshot:
    manifest_bytes = _read_ref_bytes(store, ref)
    try:
        payload = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"snapshot manifest must be valid UTF-8 JSON: {ref.uri}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError("snapshot manifest must contain a JSON object")
    validate_payload("source-snapshot", payload)
    snapshot = SnapshotManifest(
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
        source_identity=dict(payload["source_identity"]),
        admin_code_mapping=dict(payload["admin_code_mapping"]),
    )
    return _SelectedSnapshot(
        snapshot=snapshot,
        manifest_ref=ref,
        manifest_bytes=manifest_bytes,
    )


def _read_ref_bytes(store: ArtifactStore, ref: ObjectRef) -> bytes:
    data = store.read_bytes(ref.uri, generation=ref.generation)
    if (
        len(data) != ref.size_bytes
        or hashlib.sha256(data).hexdigest() != ref.sha256
    ):
        raise GenerationConflict(
            f"artifact bytes differ from exact ObjectRef: {ref.uri}@{ref.generation}"
        )
    return data


def _read_current_pointer(
    store: ArtifactStore,
    root_uri: str,
) -> dict[str, Any] | None:
    uri = f"{root_uri}/released/current.json"
    try:
        ref = store.get_ref(uri)
    except FileNotFoundError:
        return None
    data = _read_ref_bytes(store, ref)
    try:
        payload = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("released/current.json must be valid UTF-8 JSON") from exc
    expected_fields = {
        "schema_version",
        "suite_version",
        "feature_month",
        "snapshot_content_sha256",
        "suite_manifest",
        "released_at_utc",
    }
    if not isinstance(payload, dict) or set(payload) != expected_fields:
        raise ValueError("released/current.json fields differ")
    if payload["schema_version"] != "fewsnet-production-suite-pointer-v1":
        raise ValueError("released/current.json schema_version differs")
    if (
        not isinstance(payload["feature_month"], str)
        or _MONTH_PATTERN.fullmatch(payload["feature_month"]) is None
    ):
        raise ValueError("released/current.json feature_month is invalid")
    if (
        not isinstance(payload["snapshot_content_sha256"], str)
        or _SHA256_PATTERN.fullmatch(
            payload["snapshot_content_sha256"]
        )
        is None
    ):
        raise ValueError(
            "released/current.json snapshot_content_sha256 is invalid"
        )
    if not isinstance(payload["suite_manifest"], Mapping):
        raise ValueError("released/current.json suite_manifest is invalid")
    try:
        ObjectRef(**dict(payload["suite_manifest"]))
    except TypeError as exc:
        raise ValueError(
            "released/current.json suite_manifest is invalid"
        ) from exc
    return payload


def _verified_training_result(
    store: ArtifactStore,
    *,
    run_root_uri: str,
    suite_root_uri: str,
    suite_version: str,
    snapshot: SnapshotManifest,
    deployment: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    result_uri = f"{run_root_uri}/training_job_result.json"
    result_ref = store.get_ref(result_uri)
    result_bytes = _read_ref_bytes(store, result_ref)
    try:
        result = json.loads(result_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("training_job_result.json must be valid UTF-8 JSON") from exc
    expected_fields = {
        "schema_version",
        "suite_version",
        "snapshot_id",
        "snapshot_content_sha256",
        "packages",
        "training_threshold_report",
        "source_git_commit",
        "container_image_uri",
        "container_image_digest",
    }
    if not isinstance(result, dict) or set(result) != expected_fields:
        raise ValueError("training_job_result.json fields differ")
    expected_identity = {
        "schema_version": "fewsnet-training-job-result-v1",
        "suite_version": suite_version,
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_content_sha256": snapshot.snapshot_content_sha256,
        "source_git_commit": deployment["source_git_commit"],
        "container_image_uri": deployment["container_image_uri"],
        "container_image_digest": deployment["container_image_digest"],
    }
    for name, expected in expected_identity.items():
        if result[name] != expected:
            raise ValueError(f"training_job_result.json {name} differs")
    packages = result["packages"]
    if not isinstance(packages, Mapping) or set(packages) != set(_HORIZON_ORDER):
        raise ValueError("training_job_result.json package horizons differ")
    manifests: dict[str, dict[str, Any]] = {}
    for horizon_key in _HORIZON_ORDER:
        package = packages[horizon_key]
        if not isinstance(package, Mapping) or set(package) != {
            "uri",
            "checksums",
        }:
            raise ValueError(
                f"training_job_result.json {horizon_key} package fields differ"
            )
        expected_uri = f"{suite_root_uri}/models/{horizon_key}"
        if package["uri"] != expected_uri:
            raise ValueError(
                f"training_job_result.json {horizon_key} package URI differs"
            )
        if not isinstance(package["checksums"], Mapping):
            raise ValueError(
                f"training_job_result.json {horizon_key} checksums are invalid"
            )
        manifest_uri = f"{expected_uri}/model_manifest.json"
        manifest_ref = store.get_ref(manifest_uri)
        manifest_bytes = _read_ref_bytes(store, manifest_ref)
        try:
            manifest = json.loads(manifest_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"{horizon_key} model_manifest.json must be valid UTF-8 JSON"
            ) from exc
        if not isinstance(manifest, dict):
            raise ValueError(
                f"{horizon_key} model_manifest.json must be an object"
            )
        validate_payload("model-package", manifest)
        exact_values = {
            "suite_version": suite_version,
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_content_sha256": snapshot.snapshot_content_sha256,
            "horizon_key": horizon_key,
            "horizon_months": next(
                months
                for months, key in HORIZON_KEYS.items()
                if key == horizon_key
            ),
            "source_git_commit": deployment["source_git_commit"],
            "container_image_uri": deployment["container_image_uri"],
            "container_image_digest": deployment["container_image_digest"],
            "partition_sha256": PARTITION_ASSET_SHA256,
            "status": "validated",
        }
        for name, expected in exact_values.items():
            if manifest[name] != expected:
                raise ValueError(
                    f"{horizon_key} model_manifest.json {name} differs"
                )
        manifests[horizon_key] = manifest

    report = result["training_threshold_report"]
    if not isinstance(report, Mapping) or set(report) != {
        "run_uri",
        "suite_uri",
        "sha256",
    }:
        raise ValueError("training threshold report reference fields differ")
    expected_run_uri = f"{run_root_uri}/training_threshold_report.json"
    expected_suite_uri = f"{suite_root_uri}/training_threshold_report.json"
    if report["run_uri"] != expected_run_uri or report["suite_uri"] != (
        expected_suite_uri
    ):
        raise ValueError("training threshold report URIs differ")
    run_report_ref = store.get_ref(expected_run_uri)
    suite_report_ref = store.get_ref(expected_suite_uri)
    run_report_bytes = _read_ref_bytes(store, run_report_ref)
    suite_report_bytes = _read_ref_bytes(store, suite_report_ref)
    if run_report_bytes != suite_report_bytes:
        raise ValueError("run and suite training threshold reports differ")
    if hashlib.sha256(run_report_bytes).hexdigest() != report["sha256"]:
        raise ValueError("training threshold report checksum differs")
    return result, manifests


def _suite_manifest(
    deployment: Mapping[str, Any],
    selected: _SelectedSnapshot,
    registered: Mapping[str, RegisteredModelVersion],
    entries: Mapping[str, PredictionSuiteEntry],
    *,
    suite_version: str,
) -> dict[str, Any]:
    manifest = {
        "schema_version": "fewsnet-suite-manifest-v1",
        "suite_version": suite_version,
        "feature_month": selected.snapshot.latest_feature_month,
        "source_git_commit": deployment["source_git_commit"],
        "snapshot_ref": {
            "manifest": asdict(selected.manifest_ref),
            "snapshot_id": selected.snapshot.snapshot_id,
            "snapshot_content_sha256": (
                selected.snapshot.snapshot_content_sha256
            ),
        },
        "container_image": {
            "uri": deployment["container_image_uri"],
            "digest": deployment["container_image_digest"],
        },
        "partition": {
            "uri": PARTITION_ASSET_PATH.as_posix(),
            "sha256": PARTITION_ASSET_SHA256,
        },
        "model_versions": {
            horizon_key: asdict(registered[horizon_key])
            for horizon_key in _HORIZON_ORDER
        },
        "predictions": {
            horizon_key: asdict(entries[horizon_key].suite_prediction)
            for horizon_key in _HORIZON_ORDER
        },
        "alias_state": {
            horizon_key: {
                "alias": "production",
                "version_resource_name": registered[
                    horizon_key
                ].version_resource_name,
            }
            for horizon_key in _HORIZON_ORDER
        },
        "released_at_utc": _timestamp(_utc_now()),
    }
    validate_payload("suite-manifest", manifest)
    return manifest


def _result(state: _RunState, status: str, **extra: Any) -> dict[str, Any]:
    result = {
        "status": status,
        "run_id": state.run_id,
        "suite_version": state.suite_version,
        "phase": state.payload["phase"],
        "run_manifest": asdict(state.ref) if state.ref is not None else None,
        "retry_attempts": list(state.payload["retry_attempts"]),
    }
    result.update(extra)
    return result


def _preflight_failure(error: BaseException) -> dict[str, Any]:
    return {
        "status": "FAILED",
        "preflight": True,
        "error": {
            "exception_type": type(error).__name__,
            "message": str(error) or type(error).__name__,
        },
    }


def _canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("UTC timestamps must be timezone-aware datetimes")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _required_string(name: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} is required")
    return value


class _VertexTrainingBackend:
    def __init__(self, client: Any) -> None:
        self.client = client
        self._ambiguous_operations: set[str] = set()

    @classmethod
    def from_default(cls, region: str) -> _VertexTrainingBackend:
        from google.api_core.client_options import ClientOptions
        from google.cloud import aiplatform_v1

        return cls(
            aiplatform_v1.JobServiceClient(
                client_options=ClientOptions(
                    api_endpoint=f"{region}-aiplatform.googleapis.com"
                )
            )
        )

    def submit(self, request: dict[str, Any]) -> object:
        parent = _required_string("Custom Job parent", request.get("parent"))
        custom_job = request.get("custom_job")
        if not isinstance(custom_job, Mapping):
            raise ValueError("Custom Job request must contain custom_job")
        display_name = _required_string(
            "Custom Job display_name",
            custom_job.get("display_name"),
        )
        labels = custom_job.get("labels")
        if not isinstance(labels, Mapping):
            raise ValueError("Custom Job request must contain labels")
        operation_id = _required_string(
            "Custom Job operation identity",
            labels.get("fewsnet_operation"),
        )
        candidates = list(
            self.client.list_custom_jobs(
                request={
                    "parent": parent,
                    "filter": (
                        f'display_name="{display_name}" AND '
                        f"labels.fewsnet_operation={operation_id}"
                    ),
                }
            )
        )
        if len(candidates) > 1:
            raise ValueError(
                "multiple matching Custom Jobs exist for operation identity "
                f"{operation_id}"
            )
        if candidates:
            return _validate_training_job_candidate(
                candidates[0],
                request=request,
            )
        if operation_id in self._ambiguous_operations:
            raise ValueError(
                "ambiguous Custom Job submit has no matching Custom Job; "
                "refusing to resubmit"
            )
        try:
            created = self.client.create_custom_job(request=request)
        except Exception:
            self._ambiguous_operations.add(operation_id)
            raise
        return _validate_training_job_candidate(created, request=request)

    def get(self, job_name: str) -> object:
        return self.client.get_custom_job(name=job_name)

    def cancel(self, job_name: str) -> object:
        return self.client.cancel_custom_job(name=job_name)


def _validate_training_job_candidate(
    value: object,
    *,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    candidate = _normalize_vertex_mapping(value, "Custom Job resource")
    parent = str(request["parent"])
    expected = request["custom_job"]
    name = candidate.get("name")
    if not isinstance(name, str) or not name.startswith(f"{parent}/customJobs/"):
        raise ValueError("matching Custom Job has an invalid resource name")
    for field in ("display_name", "job_spec", "labels"):
        if candidate.get(field) != expected.get(field):
            raise ValueError(
                "matching Custom Job does not match the submitted Custom Job "
                f"request field: {field}"
            )
    return candidate


def _normalize_vertex_mapping(value: object, name: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        normalized = {
            str(key): _normalize_vertex_value(item)
            for key, item in value.items()
        }
    else:
        to_dict = getattr(type(value), "to_dict", None)
        if not callable(to_dict):
            raise ValueError(f"{name} must be a mapping or proto resource")
        try:
            normalized = _normalize_vertex_value(
                to_dict(value, use_integers_for_enums=False)
            )
        except TypeError:
            normalized = _normalize_vertex_value(to_dict(value))
    if not isinstance(normalized, dict):
        raise ValueError(f"{name} must normalize to an object")
    return normalized


def _normalize_vertex_value(value: object) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_vertex_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_vertex_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    to_dict = getattr(type(value), "to_dict", None)
    if callable(to_dict):
        try:
            return _normalize_vertex_value(
                to_dict(value, use_integers_for_enums=False)
            )
        except TypeError:
            return _normalize_vertex_value(to_dict(value))
    raise ValueError(
        f"Vertex resource value is not JSON-normalizable: {type(value).__name__}"
    )


def _default_backends(region: str) -> tuple[Any, Any, Any, Any]:
    from google.cloud import aiplatform

    return (
        _VertexTrainingBackend.from_default(region),
        aiplatform,
        VertexBatchBackend.from_default(region=region, sdk=aiplatform),
        VertexAliasBackend(sdk=aiplatform),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the latest deterministic FEWSNET model suite release."
    )
    parser.add_argument("--deployment-manifest-uri", required=True)
    parser.add_argument("--revision-id")
    parser.add_argument("--snapshot-manifest-uri")
    parser.add_argument("--candidate-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        store = GCSArtifactStore.from_default()
        deployment_ref = store.get_ref(args.deployment_manifest_uri)
        deployment_bytes = _read_ref_bytes(store, deployment_ref)
        deployment = json.loads(deployment_bytes)
        if not isinstance(deployment, dict):
            raise ValueError("deployment manifest must contain a JSON object")
        backends = _default_backends(str(deployment.get("region", "")))
        result = run_latest(
            deployment,
            store,
            *backends,
            revision_id=args.revision_id,
            snapshot_manifest_uri=args.snapshot_manifest_uri,
            promote=not args.candidate_only,
        )
    except Exception as exc:
        print(
            json.dumps(_preflight_failure(exc), sort_keys=True),
            file=sys.stderr,
        )
        return 1
    stream = sys.stderr if result.get("status") == "FAILED" else sys.stdout
    print(json.dumps(result, sort_keys=True, default=str), file=stream)
    return 1 if result.get("status") == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
