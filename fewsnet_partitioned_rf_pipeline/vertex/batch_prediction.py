"""Exact-version Vertex Batch Prediction boundary for FEWSNET inference."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass, replace
import json
from pathlib import Path
import time
from typing import Any, Callable, Protocol

import pandas as pd
from google.cloud import aiplatform

from fewsnet_partitioned_rf_pipeline.config import HORIZON_KEYS
from fewsnet_partitioned_rf_pipeline.core.data import normalize_admin_code
from fewsnet_partitioned_rf_pipeline.core.inference import (
    FORMAL_PREDICTION_COLUMNS,
)
from fewsnet_partitioned_rf_pipeline.core.types import (
    BatchJobRef,
    FeatureContract,
    RegisteredModelVersion,
)
from fewsnet_partitioned_rf_pipeline.schemas import (
    validate_deployment,
    validate_payload,
)


_TERMINAL_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
    "JOB_STATE_PARTIALLY_SUCCEEDED",
}
_CANCEL_TERMINAL_STATES = {
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
}
_HORIZON_MONTHS_BY_KEY = {
    horizon_key: horizon_months
    for horizon_months, horizon_key in HORIZON_KEYS.items()
}


class BatchPredictionBackend(Protocol):
    """Minimal asynchronous SDK plus public JobService boundary."""

    def submit(self, **kwargs: object) -> object: ...

    def get(self, job_resource_name: str) -> object: ...

    def cancel(self, job_resource_name: str) -> object: ...


class VertexBatchBackend:
    """Production adapter over SDK 1.161.0 and the public JobService."""

    def __init__(self, *, sdk: Any, job_service: Any) -> None:
        self.sdk = sdk
        self.job_service = job_service

    @classmethod
    def from_default(
        cls,
        *,
        region: str,
        sdk: Any = aiplatform,
    ) -> "VertexBatchBackend":
        from google.api_core.client_options import ClientOptions
        from google.cloud import aiplatform_v1

        job_service = aiplatform_v1.JobServiceClient(
            client_options=ClientOptions(
                api_endpoint=f"{region}-aiplatform.googleapis.com"
            )
        )
        return cls(sdk=sdk, job_service=job_service)

    def submit(self, **kwargs: object) -> object:
        return self.sdk.BatchPredictionJob.submit(**kwargs)

    def get(self, job_resource_name: str) -> object:
        return self.job_service.get_batch_prediction_job(
            name=job_resource_name
        )

    def cancel(self, job_resource_name: str) -> object:
        return self.job_service.cancel_batch_prediction_job(
            name=job_resource_name
        )


class BatchPredictionJobError(RuntimeError):
    """Raised when Vertex reaches a non-success terminal state."""

    def __init__(
        self,
        job_ref: BatchJobRef,
        resource: dict[str, Any],
    ) -> None:
        state = resource.get("state", "<unknown>")
        error = resource.get("error")
        super().__init__(
            f"FEWSNET Batch Prediction reached {state}: "
            f"{job_ref.job_resource_name}; error={error}"
        )
        self.job_ref = job_ref
        self.resource = resource


class BatchPredictionTimeoutError(TimeoutError):
    """Raised only after a timed-out job reaches cancelled or failed."""

    def __init__(
        self,
        job_ref: BatchJobRef,
        resource: dict[str, Any],
    ) -> None:
        super().__init__(
            "FEWSNET Batch Prediction exceeded its timeout and reached "
            f"{resource.get('state', '<unknown>')}: "
            f"{job_ref.job_resource_name}"
        )
        self.job_ref = job_ref
        self.resource = resource


def write_batch_input_jsonl(
    frame: pd.DataFrame,
    contract: FeatureContract,
    output_path: str | Path,
) -> None:
    """Write one horizon-neutral JSON object per latest-month area."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas.DataFrame")
    if not isinstance(contract, FeatureContract):
        raise TypeError("contract must be a FeatureContract")
    if frame.empty:
        raise ValueError("batch input frame must not be empty")

    duplicate_columns = _duplicates([str(name) for name in frame.columns])
    if duplicate_columns:
        raise ValueError(
            f"batch input frame contains duplicate columns: {duplicate_columns}"
        )
    ordered_columns = [
        "admin_code",
        "feature_month",
        *contract.feature_columns,
    ]
    missing_columns = sorted(set(ordered_columns) - set(frame.columns))
    if missing_columns:
        raise ValueError(
            f"batch input frame is missing required columns: {missing_columns}"
        )

    admin_codes = frame["admin_code"].map(normalize_admin_code)
    if admin_codes.eq("").any():
        raise ValueError("batch input admin_code contains missing or blank values")
    feature_months = _normalize_months(
        frame["feature_month"],
        "feature_month",
    )
    if admin_codes.duplicated(keep=False).any():
        duplicates = sorted(admin_codes[admin_codes.duplicated(keep=False)].unique())
        raise ValueError(
            f"batch input contains duplicate admin_code values: {duplicates}"
        )
    if len(set(feature_months)) != 1:
        raise ValueError("batch input must contain exactly one latest feature_month")

    lines: list[str] = []
    for row_index, (_, row) in enumerate(frame.iterrows()):
        instance: dict[str, object] = {
            "admin_code": admin_codes.iloc[row_index],
            "feature_month": feature_months[row_index],
        }
        for feature_name in contract.feature_columns:
            instance[feature_name] = _json_scalar(row[feature_name])
        lines.append(
            json.dumps(
                instance,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
        )

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def submit_batch_prediction(
    config: object,
    backend: BatchPredictionBackend,
) -> BatchJobRef:
    """Submit one asynchronous exact-version Vertex Batch Prediction job."""
    deployment_value = _config_value(config, "deployment")
    if not isinstance(deployment_value, Mapping):
        raise TypeError("config.deployment must be a mapping")
    deployment = dict(deployment_value)
    validate_deployment(deployment)

    run_id = _required_string("run_id", _config_value(config, "run_id"))
    if "/" in run_id:
        raise ValueError("run_id must not contain path separators")
    horizon_key = _required_string(
        "horizon_key",
        _config_value(config, "horizon_key"),
    )
    if horizon_key not in _HORIZON_MONTHS_BY_KEY:
        raise ValueError(f"unsupported horizon_key: {horizon_key}")
    model_ref = _config_value(config, "model_ref")
    _validate_model_ref(model_ref, expected_horizon_key=horizon_key)

    object_store_root = str(deployment["object_store_root_uri"]).rstrip("/")
    input_uri = (
        f"{object_store_root}/runs/{run_id}/batch_prediction/"
        f"{horizon_key}/input.jsonl"
    )
    destination_prefix = (
        f"{object_store_root}/runs/{run_id}/batch_prediction/"
        f"{horizon_key}/raw"
    )
    _validate_optional_exact_config_uri(config, "input_uri", input_uri)
    _validate_optional_exact_config_uri(
        config,
        "destination_prefix",
        destination_prefix,
    )
    job_display_name = _optional_config_value(config, "job_display_name")
    if job_display_name is None:
        job_display_name = f"fewsnet-batch-{run_id}-{horizon_key}"
    job_display_name = _required_string(
        "job_display_name",
        job_display_name,
    )
    labels_value = _optional_config_value(config, "labels")
    labels = {} if labels_value is None else _string_mapping(labels_value, "labels")

    job = backend.submit(
        job_display_name=job_display_name,
        model_name=model_ref.version_resource_name,
        instances_format="jsonl",
        predictions_format="jsonl",
        gcs_source=input_uri,
        gcs_destination_prefix=destination_prefix,
        machine_type=deployment["batch_machine_type"],
        starting_replica_count=1,
        max_replica_count=1,
        service_account=deployment["batch_prediction_service_account"],
        labels=labels,
        project=deployment["project_id"],
        location=deployment["region"],
    )
    job_resource_name = getattr(job, "resource_name", None)
    if not isinstance(job_resource_name, str) or not job_resource_name:
        raise ValueError("submitted Batch Prediction job must expose resource_name")
    return BatchJobRef(
        horizon_key=horizon_key,
        job_resource_name=job_resource_name,
        model_version_resource_name=model_ref.version_resource_name,
        input_uri=input_uri,
        destination_prefix=destination_prefix,
    )


def wait_batch_prediction(
    job_ref: BatchJobRef,
    timeout_seconds: int,
    backend: BatchPredictionBackend,
    *,
    poll_interval_seconds: float = 30.0,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> BatchJobRef:
    """Poll the exact public resource, cancelling and draining on timeout."""
    if not isinstance(job_ref, BatchJobRef):
        raise TypeError("job_ref must be a BatchJobRef")
    _required_string("job_resource_name", job_ref.job_resource_name)
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or timeout_seconds <= 0
    ):
        raise ValueError("timeout_seconds must be a positive integer")
    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be positive")

    started_at = monotonic()
    cancellation_requested = False
    while True:
        if (
            not cancellation_requested
            and monotonic() - started_at >= timeout_seconds
        ):
            backend.cancel(job_ref.job_resource_name)
            cancellation_requested = True

        resource = _normalize_mapping(
            backend.get(job_ref.job_resource_name),
            "Batch Prediction job resource",
        )
        if resource.get("name") != job_ref.job_resource_name:
            raise ValueError(
                "Batch Prediction backend returned a different resource name: "
                f"expected {job_ref.job_resource_name}, got {resource.get('name')}"
            )
        state = _state_name(resource.get("state"))
        resource["state"] = state

        if cancellation_requested:
            if state in _CANCEL_TERMINAL_STATES:
                raise BatchPredictionTimeoutError(job_ref, resource)
            if state in _TERMINAL_STATES:
                raise RuntimeError(
                    "timed-out Batch Prediction job reached an unexpected "
                    f"terminal state: {state}"
                )
        elif state == "JOB_STATE_SUCCEEDED":
            output_info = resource.get("output_info")
            if not isinstance(output_info, Mapping):
                raise ValueError(
                    "successful Batch Prediction job is missing output_info"
                )
            output_directory = output_info.get("gcs_output_directory")
            if not isinstance(output_directory, str) or not output_directory:
                raise ValueError(
                    "successful Batch Prediction job is missing "
                    "gcs_output_directory"
                )
            return replace(
                job_ref,
                gcs_output_directory=output_directory,
            )
        elif state in _TERMINAL_STATES:
            raise BatchPredictionJobError(job_ref, resource)
        sleep(poll_interval_seconds)


def normalize_batch_output(
    raw_paths: Sequence[str | Path],
    input_frame: pd.DataFrame,
    model_ref: RegisteredModelVersion,
    suite_version: str,
) -> pd.DataFrame:
    """Fail closed while restoring one formal record per input identity."""
    _validate_model_ref(model_ref)
    suite_version = _required_string("suite_version", suite_version)
    expected_horizon_months = _HORIZON_MONTHS_BY_KEY[model_ref.horizon_key]
    input_identities = _input_identities(input_frame)
    expected_keys = set(input_identities)

    if isinstance(raw_paths, (str, bytes, Path)):
        raise TypeError("raw_paths must be a sequence of paths")
    paths = [Path(path) for path in raw_paths]
    if not paths:
        raise ValueError("raw Batch Prediction output is missing prediction files")
    error_paths = sorted(
        str(path)
        for path in paths
        if path.name.startswith("errors_") and path.suffix == ".jsonl"
    )
    if error_paths:
        raise ValueError(
            f"raw Batch Prediction output contains error files: {error_paths}"
        )

    records_by_key: dict[tuple[str, str], dict[str, object]] = {}
    for path in sorted(paths, key=lambda item: str(item)):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"Batch Prediction output is not valid UTF-8 JSONL: {path}"
            ) from exc
        lines = text.splitlines()
        if not lines:
            raise ValueError(f"Batch Prediction output file is empty: {path}")
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                raise ValueError(
                    f"Batch Prediction output contains a blank JSONL line: "
                    f"{path}:{line_number}"
                )
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Batch Prediction output contains malformed JSON: "
                    f"{path}:{line_number}"
                ) from exc
            if not isinstance(payload, Mapping):
                raise ValueError(
                    f"Batch Prediction JSONL line must be an object: "
                    f"{path}:{line_number}"
                )
            if "error" in payload:
                raise ValueError(
                    f"Batch Prediction output contains a line-level error: "
                    f"{path}:{line_number}"
                )
            instance = payload.get("instance")
            prediction = payload.get("prediction")
            if not isinstance(instance, Mapping) or not isinstance(
                prediction, Mapping
            ):
                raise ValueError(
                    "Batch Prediction output line must contain instance and "
                    f"prediction objects: {path}:{line_number}"
                )

            instance_key = _identity_from_mapping(instance, "instance")
            if instance_key not in expected_keys:
                raise ValueError(
                    "Batch Prediction instance identity is absent from the "
                    f"input frame: {instance_key}"
                )
            prediction_key = _identity_from_mapping(prediction, "prediction")
            if prediction_key != instance_key:
                raise ValueError(
                    "Batch Prediction prediction identity differs from its "
                    f"instance identity: instance={instance_key}, "
                    f"prediction={prediction_key}"
                )
            if instance_key in records_by_key:
                raise ValueError(
                    f"Batch Prediction output contains duplicate identity: "
                    f"{instance_key}"
                )

            record = dict(prediction)
            _set_exact_identity(
                record,
                "suite_version",
                suite_version,
            )
            _set_exact_identity(
                record,
                "vertex_model_resource_name",
                model_ref.version_resource_name,
            )
            _set_exact_identity(
                record,
                "vertex_model_version_id",
                model_ref.version_id,
            )
            if record.get("horizon_months") != expected_horizon_months:
                raise ValueError(
                    "prediction horizon_months differs from the candidate "
                    "model horizon"
                )
            expected_target_month = str(
                pd.Period(instance_key[1], freq="M")
                + expected_horizon_months
            )
            if record.get("target_month") != expected_target_month:
                raise ValueError(
                    "prediction target_month differs from feature_month plus "
                    "the candidate model horizon"
                )
            validate_payload("prediction-record", record)
            records_by_key[instance_key] = record

    missing_keys = [key for key in input_identities if key not in records_by_key]
    if missing_keys:
        raise ValueError(
            f"Batch Prediction output is missing input identities: {missing_keys}"
        )
    ordered_records = [records_by_key[key] for key in input_identities]
    return pd.DataFrame(
        ordered_records,
        columns=list(FORMAL_PREDICTION_COLUMNS),
    )


def _input_identities(input_frame: pd.DataFrame) -> list[tuple[str, str]]:
    if not isinstance(input_frame, pd.DataFrame):
        raise TypeError("input_frame must be a pandas.DataFrame")
    if input_frame.empty:
        raise ValueError("input_frame must not be empty")
    duplicate_columns = _duplicates(
        [str(name) for name in input_frame.columns]
    )
    if duplicate_columns:
        raise ValueError(
            f"input_frame contains duplicate columns: {duplicate_columns}"
        )
    missing = sorted(
        {"admin_code", "feature_month"} - set(input_frame.columns)
    )
    if missing:
        raise ValueError(f"input_frame is missing identity columns: {missing}")
    admin_codes = input_frame["admin_code"].map(normalize_admin_code)
    if admin_codes.eq("").any():
        raise ValueError("input_frame admin_code contains missing or blank values")
    feature_months = _normalize_months(
        input_frame["feature_month"],
        "feature_month",
    )
    identities = list(zip(admin_codes.tolist(), feature_months, strict=True))
    duplicate_keys = sorted(
        {key for key in identities if identities.count(key) > 1}
    )
    if duplicate_keys:
        raise ValueError(
            f"input_frame contains duplicate identity values: {duplicate_keys}"
        )
    return identities


def _identity_from_mapping(
    payload: Mapping[object, object],
    name: str,
) -> tuple[str, str]:
    if "admin_code" not in payload or "feature_month" not in payload:
        raise ValueError(f"{name} is missing admin identity fields")
    admin_code = normalize_admin_code(payload["admin_code"])
    if not admin_code:
        raise ValueError(f"{name} admin_code is missing or blank")
    feature_month = _normalize_month_value(
        payload["feature_month"],
        f"{name}.feature_month",
    )
    return admin_code, feature_month


def _set_exact_identity(
    record: dict[str, object],
    field: str,
    expected: str,
) -> None:
    existing = record.get(field)
    if existing not in (None, "", expected):
        raise ValueError(
            f"prediction {field} differs from the exact suite/model identity"
        )
    record[field] = expected


def _validate_model_ref(
    model_ref: object,
    *,
    expected_horizon_key: str | None = None,
) -> None:
    if not isinstance(model_ref, RegisteredModelVersion):
        raise TypeError("model_ref must be a RegisteredModelVersion")
    if model_ref.horizon_key not in _HORIZON_MONTHS_BY_KEY:
        raise ValueError(
            f"unsupported model horizon_key: {model_ref.horizon_key}"
        )
    if (
        expected_horizon_key is not None
        and model_ref.horizon_key != expected_horizon_key
    ):
        raise ValueError("model version horizon differs from the requested horizon")
    if not model_ref.version_id.isdigit():
        raise ValueError("model version ID must be numeric")
    expected_resource_name = (
        f"{model_ref.parent_model_resource_name}@{model_ref.version_id}"
    )
    if model_ref.version_resource_name != expected_resource_name:
        raise ValueError(
            "model version resource name must contain the exact numeric "
            "@version_id"
        )


def _normalize_months(values: pd.Series, name: str) -> list[str]:
    return [_normalize_month_value(value, name) for value in values]


def _normalize_month_value(value: object, name: str) -> str:
    candidate = value.strip() if isinstance(value, str) else value
    try:
        missing = bool(pd.isna(candidate))
    except (TypeError, ValueError):
        missing = False
    if missing or (isinstance(candidate, str) and not candidate):
        raise ValueError(f"{name} contains invalid or missing values")
    try:
        return str(pd.Period(candidate, freq="M"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} contains invalid or missing values") from exc


def _json_scalar(value: object) -> object:
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    item = getattr(value, "item", None)
    if callable(item):
        value = item()
    if isinstance(value, pd.Period):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError(
        f"batch input value is not JSON scalar-compatible: {type(value).__name__}"
    )


def _config_value(config: object, name: str) -> object:
    value = _optional_config_value(config, name)
    if value is None:
        raise ValueError(f"config.{name} is required")
    return value


def _optional_config_value(config: object, name: str) -> object | None:
    if isinstance(config, Mapping):
        return config.get(name)
    return getattr(config, name, None)


def _validate_optional_exact_config_uri(
    config: object,
    name: str,
    expected: str,
) -> None:
    actual = _optional_config_value(config, name)
    if actual is not None and actual != expected:
        raise ValueError(
            f"config.{name} must equal the deterministic run URI: {expected}"
        )


def _required_string(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value


def _string_mapping(value: object, name: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    normalized = dict(value)
    if not all(
        isinstance(key, str) and isinstance(item, str)
        for key, item in normalized.items()
    ):
        raise ValueError(f"{name} must contain string pairs")
    return normalized


def _normalize_mapping(value: object, name: str) -> dict[str, Any]:
    normalized = _normalize_json(value)
    if not isinstance(normalized, dict):
        raise ValueError(f"{name} must normalize to a JSON object")
    return normalized


def _normalize_json(value: object) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_json(item)
            for key, item in value.items()
        }
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize_json(asdict(value))
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    to_dict = getattr(type(value), "to_dict", None)
    if callable(to_dict):
        try:
            return _normalize_json(to_dict(value, use_integers_for_enums=False))
        except TypeError:
            return _normalize_json(to_dict(value))
    raise ValueError(
        f"value is not JSON-normalizable: {type(value).__name__}"
    )


def _state_name(value: object) -> str:
    if isinstance(value, str) and value:
        return value.rsplit(".", 1)[-1]
    enum_name = getattr(value, "name", None)
    if isinstance(enum_name, str) and enum_name:
        return enum_name
    raise ValueError("Batch Prediction job resource must contain a named state")


def _duplicates(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)
