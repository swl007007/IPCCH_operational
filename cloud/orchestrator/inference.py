from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from io import StringIO
import math
from pathlib import Path
import subprocess

import pandas as pd

from cloud.common.object_store import GCSObjectStore, ObjectStore
from cloud.common.reports import build_validation_report
from cloud.common.runtime_config import RuntimeDefaults


PREDICTION_SCOPES = ("0m", "6m", "12m")
REQUIRED_PREDICTION_COLUMNS = (
    "area_id",
    "year",
    "month",
    "_row_id",
    "phase2_worse_score",
    "phase2_worse_pred",
    "phase3_worse_score",
    "phase3_worse_pred",
    "phase4_worse_score",
    "phase4_worse_pred",
    "phase5_worse_score",
    "phase5_worse_pred",
    "overall_phase_pred",
    "feature_period",
    "target_period",
    "scope_months",
    "model_package_id",
    "source_input",
)
OPTIONAL_PREDICTION_COLUMNS = ("admin_code",)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run IPCCH Vertex AI inference wrapper"
    )
    parser.add_argument("--feature-month", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--input-base-uri", "--base-input-uri", dest="base_input_uri", required=True
    )
    parser.add_argument("--model-package-uri", required=True)
    parser.add_argument(
        "--output-dir", "--output-prefix-uri", dest="output_prefix_uri", required=True
    )
    parser.add_argument("--container-image-digest", required=True)
    parser.add_argument("--vertex-ai-job-id", required=True)
    parser.add_argument("--vertex-ai-job-resource-name", required=True)
    parser.add_argument("--vertex-ai-project-id", required=True)
    parser.add_argument("--vertex-ai-region", required=True)
    parser.add_argument("--vertex-ai-custom-job-container-image-uri", required=True)
    parser.add_argument("--vertex-ai-custom-job-container-digest", required=True)
    parser.add_argument("--model-version-or-checksum", required=True)
    parser.add_argument(
        "--vertex-ai-custom-job-timeout-seconds", type=int, default=7200
    )
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--custom-job-log-uri")
    parser.add_argument("--reference-sample-uri")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_inference_wrapper(
        store=GCSObjectStore.from_default(),
        feature_month=args.feature_month,
        run_id=args.run_id,
        base_input_uri=args.base_input_uri,
        model_package_uri=args.model_package_uri,
        output_prefix_uri=args.output_prefix_uri,
        job_metadata={
            "vertex_ai_job_id": args.vertex_ai_job_id,
            "vertex_ai_job_resource_name": args.vertex_ai_job_resource_name,
            "vertex_ai_project_id": args.vertex_ai_project_id,
            "vertex_ai_region": args.vertex_ai_region,
            "vertex_ai_custom_job_container_image_uri": (
                args.vertex_ai_custom_job_container_image_uri
            ),
            "vertex_ai_custom_job_container_digest": (
                args.vertex_ai_custom_job_container_digest
            ),
            "container_image_digest": args.container_image_digest,
            "model_version_or_checksum": args.model_version_or_checksum,
            "custom_job_log_uri": args.custom_job_log_uri,
        },
        runtime=RuntimeDefaults(
            vertex_ai_custom_job_timeout_seconds=(
                args.vertex_ai_custom_job_timeout_seconds
            ),
            max_retries=args.max_retries,
        ),
        reference_sample_uri=args.reference_sample_uri,
    )
    return 0


def build_inference_command(
    *,
    base_input_path: str,
    model_package_path: str,
    output_dir: str,
    feature_month: str,
) -> list[str]:
    return [
        "python3",
        "model_pipeline/run_operational_launch_inference.py",
        "--input",
        base_input_path,
        "--model-package",
        model_package_path,
        "--output-dir",
        output_dir,
        "--feature-month",
        feature_month,
        "--no-map",
        "--overwrite",
    ]


def validate_prediction_outputs(
    predictions: dict[str, pd.DataFrame],
    *,
    feature_month: str,
    base_input: pd.DataFrame | None = None,
    reference_predictions: dict[str, pd.DataFrame] | None = None,
    expected_model_package_id: str | None = None,
) -> tuple[dict[str, pd.DataFrame], dict]:
    missing = set(PREDICTION_SCOPES) - set(predictions)
    if missing:
        raise ValueError(f"missing prediction scopes: {sorted(missing)}")
    year, month = (int(part) for part in feature_month.split("-"))
    enriched = {}
    advisory_warnings = []
    missing_admin_code = False
    for scope in PREDICTION_SCOPES:
        frame = predictions[scope].copy()
        if "year" not in frame.columns:
            frame["year"] = year
        if "month" not in frame.columns:
            frame["month"] = month
        missing_columns = [
            column
            for column in REQUIRED_PREDICTION_COLUMNS
            if column not in frame.columns
        ]
        if missing_columns:
            raise ValueError(f"{scope} prediction missing columns: {missing_columns}")
        _validate_prediction_scope_contract(
            frame,
            scope=scope,
            feature_month=feature_month,
            expected_model_package_id=expected_model_package_id,
        )
        missing_admin_code = missing_admin_code or "admin_code" not in frame.columns
        enriched[scope] = frame
    if missing_admin_code:
        advisory_warnings.append(
            {
                "column": "admin_code",
                "message": "prediction output omitted optional admin_code metadata",
            }
        )
    key = ["area_id", "year", "month"]
    row_universe_match = True
    duplicate_key_count = sum(
        int(frame.duplicated(key).sum()) for frame in enriched.values()
    )
    combined_key = ["area_id", "year", "month", "scope_months"]
    combined = pd.concat(enriched.values(), ignore_index=True)
    duplicate_key_count += int(combined.duplicated(combined_key).sum())
    missing_key_counts = {column: 0 for column in key}
    base_input_row_count = None
    for frame in enriched.values():
        for column in key:
            missing_key_counts[column] += int(frame[column].isna().sum())
    if duplicate_key_count:
        raise ValueError("prediction output contains duplicate keys")
    if base_input is not None:
        base_input_row_count = len(base_input)
        base_keys = set(map(tuple, base_input[key].itertuples(index=False, name=None)))
        for frame in enriched.values():
            prediction_keys = set(
                map(tuple, frame[key].itertuples(index=False, name=None))
            )
            row_universe_match = row_universe_match and prediction_keys == base_keys
        if not row_universe_match:
            raise ValueError("prediction row universe must match base input")
        _validate_prediction_base_alignment(enriched, base_input=base_input)
    comparison = {"status": "not_provided"}
    if reference_predictions is not None:
        comparison = _compare_reference_predictions(
            enriched,
            reference_predictions,
            feature_month=feature_month,
        )
    report = build_validation_report(
        report_type="inference_report",
        feature_month=feature_month,
        run_id="vertex-ai-custom-job",
        status="passed",
        prediction_outputs={
            scope: {"row_count": len(enriched[scope])} for scope in PREDICTION_SCOPES
        },
        prediction_row_counts={
            scope: len(enriched[scope]) for scope in PREDICTION_SCOPES
        },
        base_input_row_count=base_input_row_count,
        row_universe_match=row_universe_match,
        key_columns=key,
        duplicate_key_count=duplicate_key_count,
        missing_key_counts=missing_key_counts,
        model_output_schema={
            "schema_version": "prediction-output-v1",
            "required_columns": list(REQUIRED_PREDICTION_COLUMNS),
            "optional_columns": list(OPTIONAL_PREDICTION_COLUMNS),
            "status": "passed",
        },
        extra_columns={
            scope: [
                column
                for column in enriched[scope].columns
                if column
                not in REQUIRED_PREDICTION_COLUMNS + OPTIONAL_PREDICTION_COLUMNS
            ]
            for scope in PREDICTION_SCOPES
        },
        local_reference_comparison=comparison,
        advisory_warnings=advisory_warnings,
    )
    return enriched, report


def _validate_prediction_scope_contract(
    frame: pd.DataFrame,
    *,
    scope: str,
    feature_month: str,
    expected_model_package_id: str | None = None,
) -> None:
    score_columns = [
        "phase2_worse_score",
        "phase3_worse_score",
        "phase4_worse_score",
        "phase5_worse_score",
    ]
    pred_columns = [
        "phase2_worse_pred",
        "phase3_worse_pred",
        "phase4_worse_pred",
        "phase5_worse_pred",
    ]
    for column in score_columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isna().any() or not values.map(math.isfinite).all():
            raise ValueError(f"{scope} prediction {column} must be finite numeric")
    for column in pred_columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isna().any() or not values.isin([0, 1]).all():
            raise ValueError(f"{scope} prediction {column} must be 0 or 1")
    overall_phase = pd.to_numeric(frame["overall_phase_pred"], errors="coerce")
    if (
        overall_phase.isna().any()
        or not overall_phase.map(lambda value: float(value).is_integer()).all()
        or not overall_phase.isin([1, 2, 3, 4, 5]).all()
    ):
        raise ValueError(
            f"{scope} prediction overall_phase_pred must be an integer 1-5"
        )
    row_ids = pd.to_numeric(frame["_row_id"], errors="coerce")
    expected_row_ids = set(range(len(frame)))
    observed_row_ids = set(row_ids.dropna().astype(int).tolist())
    if (
        row_ids.isna().any()
        or not row_ids.map(lambda value: float(value).is_integer()).all()
        or observed_row_ids != expected_row_ids
    ):
        raise ValueError(
            f"{scope} prediction _row_id must be the 0-based row id from base input"
        )
    if expected_model_package_id is not None:
        observed_model_package_ids = {str(value) for value in frame["model_package_id"]}
        if observed_model_package_ids != {expected_model_package_id}:
            raise ValueError(
                f"{scope} prediction model_package_id must be "
                f"{expected_model_package_id}; got {sorted(observed_model_package_ids)}"
            )
    expected_scope_months = _scope_to_months(scope)
    observed_scope_months = {
        _normalize_scope_months(value) for value in frame["scope_months"]
    }
    if observed_scope_months != {expected_scope_months}:
        raise ValueError(
            f"{scope} prediction scope_months must be {expected_scope_months}; "
            f"got {sorted(observed_scope_months)}"
        )
    observed_feature_periods = {str(value) for value in frame["feature_period"]}
    if observed_feature_periods != {feature_month}:
        raise ValueError(
            f"{scope} prediction feature_period must be {feature_month}; "
            f"got {sorted(observed_feature_periods)}"
        )
    expected_target_period = _target_period(feature_month, expected_scope_months)
    observed_target_periods = {str(value) for value in frame["target_period"]}
    if observed_target_periods != {expected_target_period}:
        raise ValueError(
            f"{scope} prediction target_period must be {expected_target_period}; "
            f"got {sorted(observed_target_periods)}"
        )


def _validate_prediction_base_alignment(
    predictions: dict[str, pd.DataFrame], *, base_input: pd.DataFrame
) -> None:
    key = ["area_id", "year", "month"]
    base = base_input.copy()
    if "_row_id" not in base.columns:
        base["_row_id"] = range(len(base))
    expected = base[key + ["_row_id"]].copy()
    expected["_row_id"] = pd.to_numeric(expected["_row_id"], errors="coerce")
    if "admin_code" in base.columns:
        expected["admin_code"] = base["admin_code"].astype(str)
    for scope, frame in predictions.items():
        observed_columns = key + ["_row_id"]
        if "admin_code" in frame.columns:
            observed_columns.append("admin_code")
        observed = frame[observed_columns].copy()
        observed["_row_id"] = pd.to_numeric(observed["_row_id"], errors="coerce")
        merged = observed.merge(expected, on=key, how="left", suffixes=("", "_base"))
        if not (merged["_row_id"] == merged["_row_id_base"]).all():
            raise ValueError(f"{scope} prediction _row_id must match base input")
        if "admin_code_base" in merged.columns and "admin_code" in merged.columns:
            expected_admin_code = merged["admin_code_base"]
            has_expected_admin_code = expected_admin_code.notna()
            admin_code_matches = merged.loc[
                has_expected_admin_code, "admin_code"
            ].astype(str) == expected_admin_code.loc[has_expected_admin_code].astype(
                str
            )
            if not bool(admin_code_matches.all()):
                raise ValueError(f"{scope} prediction admin_code must match base input")


def _compare_reference_predictions(
    predictions: dict[str, pd.DataFrame],
    reference_predictions: dict[str, pd.DataFrame],
    *,
    feature_month: str,
) -> dict:
    missing = set(PREDICTION_SCOPES) - set(reference_predictions)
    if missing:
        raise ValueError(f"reference predictions missing scopes: {sorted(missing)}")
    key = ["area_id", "year", "month", "scope_months"]
    exact_columns = [
        "phase2_worse_pred",
        "phase3_worse_pred",
        "phase4_worse_pred",
        "phase5_worse_pred",
        "overall_phase_pred",
        "feature_period",
        "target_period",
    ]
    score_columns = [
        "phase2_worse_score",
        "phase3_worse_score",
        "phase4_worse_score",
        "phase5_worse_score",
    ]
    matched_row_counts = {}
    advisory_differences = []
    hard_gate_failures = []
    for scope in PREDICTION_SCOPES:
        reference = reference_predictions[scope].copy()
        if reference.empty:
            raise ValueError(f"{scope} reference prediction has no matched rows")
        missing_columns = [
            column
            for column in REQUIRED_PREDICTION_COLUMNS
            if column not in reference.columns
        ]
        if missing_columns:
            raise ValueError(
                f"{scope} reference prediction missing columns: {missing_columns}"
            )
        _validate_prediction_scope_contract(
            reference, scope=scope, feature_month=feature_month
        )
        cloud = predictions[scope].copy()
        cloud_keys = set(map(tuple, cloud[key].itertuples(index=False, name=None)))
        reference_keys = set(
            map(tuple, reference[key].itertuples(index=False, name=None))
        )
        if cloud_keys != reference_keys:
            raise ValueError(
                f"{scope} reference prediction keys must match cloud output"
            )
        matched_row_counts[scope] = len(cloud_keys)
        cloud_indexed = cloud.set_index(key).sort_index()
        reference_indexed = reference.set_index(key).sort_index()
        for column in exact_columns:
            mismatches = cloud_indexed[column] != reference_indexed[column]
            if bool(mismatches.any()):
                hard_gate_failures.append(
                    {
                        "scope": scope,
                        "column": column,
                        "mismatch_count": int(mismatches.sum()),
                    }
                )
        for column in score_columns:
            cloud_values = pd.to_numeric(cloud_indexed[column], errors="coerce")
            reference_values = pd.to_numeric(reference_indexed[column], errors="coerce")
            differences = (cloud_values - reference_values).abs()
            mismatches = differences.fillna(0) > 0
            if bool(mismatches.any()):
                advisory_differences.append(
                    {
                        "scope": scope,
                        "column": column,
                        "difference_count": int(mismatches.sum()),
                        "max_abs_difference": float(differences[mismatches].max()),
                    }
                )
    if hard_gate_failures:
        raise ValueError(
            f"reference prediction hard gate failures: {hard_gate_failures}"
        )
    return {
        "status": "provided",
        "matched_row_counts": matched_row_counts,
        "advisory_differences": advisory_differences,
        "hard_gate_failures": hard_gate_failures,
    }


def _scope_to_months(scope: str) -> int:
    return int(scope.removesuffix("m"))


def _normalize_scope_months(value) -> int:
    if isinstance(value, str) and value.endswith("m"):
        raise ValueError("scope_months must be integer 0, 6, or 12")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("scope_months must be integer 0, 6, or 12") from exc
    if normalized not in {0, 6, 12}:
        raise ValueError("scope_months must be one of 0, 6, or 12")
    return normalized


def _target_period(feature_month: str, scope_months: int) -> str:
    year, month = (int(part) for part in feature_month.split("-"))
    month_index = (year * 12) + (month - 1) + scope_months
    return f"{month_index // 12:04d}-{(month_index % 12) + 1:02d}"


def run_inference_wrapper(
    *,
    store: ObjectStore,
    feature_month: str,
    run_id: str,
    base_input_uri: str,
    model_package_uri: str,
    output_prefix_uri: str,
    job_metadata: dict,
    reference_predictions: dict[str, pd.DataFrame] | None = None,
    reference_sample_uri: str | None = None,
    command_runner=None,
    workspace_root: str | Path | None = None,
    allow_synthetic_predictions: bool = False,
    runtime: RuntimeDefaults | None = None,
) -> dict:
    runtime = runtime or RuntimeDefaults()
    try:
        return _run_inference_wrapper_success(
            store=store,
            feature_month=feature_month,
            run_id=run_id,
            base_input_uri=base_input_uri,
            model_package_uri=model_package_uri,
            output_prefix_uri=output_prefix_uri,
            job_metadata=job_metadata,
            reference_predictions=reference_predictions,
            reference_sample_uri=reference_sample_uri,
            command_runner=command_runner,
            workspace_root=workspace_root,
            allow_synthetic_predictions=allow_synthetic_predictions,
            runtime=runtime,
        )
    except Exception as exc:
        _write_inference_failure_artifacts(
            store=store,
            feature_month=feature_month,
            run_id=run_id,
            base_input_uri=base_input_uri,
            model_package_uri=model_package_uri,
            output_prefix_uri=output_prefix_uri,
            job_metadata=job_metadata,
            runtime=runtime,
            error=exc,
        )
        raise


def _run_inference_wrapper_success(
    *,
    store: ObjectStore,
    feature_month: str,
    run_id: str,
    base_input_uri: str,
    model_package_uri: str,
    output_prefix_uri: str,
    job_metadata: dict,
    reference_predictions: dict[str, pd.DataFrame] | None,
    reference_sample_uri: str | None,
    command_runner,
    workspace_root: str | Path | None,
    allow_synthetic_predictions: bool,
    runtime: RuntimeDefaults,
) -> dict:
    base_input = pd.read_csv(StringIO(store.read_text(base_input_uri)))
    yyyymm = feature_month.replace("-", "")
    expected_model_package_id = _model_package_id_from_manifest(
        store=store, model_package_uri=model_package_uri
    )
    if command_runner is None and allow_synthetic_predictions:
        predictions = {
            scope: _synthetic_prediction_frame(
                base_input=base_input,
                feature_month=feature_month,
                scope=scope,
                model_package_uri=model_package_uri,
                model_package_id=expected_model_package_id,
            )
            for scope in PREDICTION_SCOPES
        }
        command = []
        command_result = {"returncode": 0, "stdout": "", "stderr": ""}
    else:
        effective_runner = command_runner or _default_command_runner
        predictions, command, command_result = _run_script_and_collect_predictions(
            store=store,
            feature_month=feature_month,
            base_input_uri=base_input_uri,
            model_package_uri=model_package_uri,
            command_runner=effective_runner,
            workspace_root=workspace_root,
        )
    effective_reference_predictions = reference_predictions
    if effective_reference_predictions is None and reference_sample_uri:
        effective_reference_predictions = _load_reference_predictions(
            store, reference_sample_uri
        )
    enriched, report = validate_prediction_outputs(
        predictions,
        feature_month=feature_month,
        base_input=base_input,
        reference_predictions=effective_reference_predictions,
        expected_model_package_id=expected_model_package_id,
    )
    report["run_id"] = run_id
    report["model_package_uri"] = model_package_uri
    report["reference_sample_uri"] = reference_sample_uri
    report["input_base_uri"] = base_input_uri
    report["input_base_path"] = base_input_uri
    report["vertex_ai_job_id"] = job_metadata.get("vertex_ai_job_id")
    report["cloud_runtime_validation_status"] = "passed"
    report["model_package_validation_status"] = "passed"
    report["custom_job_command"] = command
    report["custom_job_exit_code"] = command_result.get("returncode", 0)
    report["custom_job_log_uri"] = job_metadata.get("custom_job_log_uri")
    report["retry_policy"] = {"max_retries": runtime.max_retries}
    report["vertex_ai_custom_job_timeout_seconds"] = (
        runtime.vertex_ai_custom_job_timeout_seconds
    )
    prediction_output_paths = {}
    for scope, frame in enriched.items():
        output_uri = (
            output_prefix_uri + f"ipcch_launch_{yyyymm}_scope_{scope}_predictions.csv"
        )
        prediction_output_paths[scope] = output_uri
        store.write_text(output_uri, frame.to_csv(index=False))
    report["prediction_output_paths"] = prediction_output_paths
    now = _utc_now()
    job_manifest = {
        "schema_version": "ipcch-monthly-e2e-report-v1",
        "feature_month": feature_month,
        "run_id": run_id,
        "vertex_ai_project_id": job_metadata.get("vertex_ai_project_id"),
        "vertex_ai_region": job_metadata.get("vertex_ai_region"),
        "vertex_ai_job_id": job_metadata.get("vertex_ai_job_id"),
        "vertex_ai_job_resource_name": job_metadata.get("vertex_ai_job_resource_name"),
        "inference_mode": "vertex_ai_custom_job",
        "model_package_uri": model_package_uri,
        "model_version_or_checksum": job_metadata.get("model_version_or_checksum"),
        "vertex_ai_custom_job_container_image_uri": job_metadata.get(
            "vertex_ai_custom_job_container_image_uri"
        ),
        "vertex_ai_custom_job_container_digest": job_metadata.get(
            "vertex_ai_custom_job_container_digest",
            job_metadata.get("container_image_digest"),
        ),
        "container_image_digest": job_metadata.get("container_image_digest"),
        "input_base_uri": base_input_uri,
        "output_uri": output_prefix_uri,
        "job_status": "SUCCEEDED",
        "created_at_utc": job_metadata.get("created_at_utc", now),
        "completed_at_utc": job_metadata.get("completed_at_utc", now),
        "retry_policy": {"max_retries": runtime.max_retries},
        "vertex_ai_custom_job_timeout_seconds": (
            runtime.vertex_ai_custom_job_timeout_seconds
        ),
        "status": "passed",
        "artifact_paths": {},
        "checksums": {},
    }
    store.write_text(
        output_prefix_uri + "vertex_ai_job_manifest.json",
        json.dumps(job_manifest, indent=2, sort_keys=True) + "\n",
    )
    store.write_text(
        output_prefix_uri + "inference_report.json",
        json.dumps(report, indent=2, sort_keys=True) + "\n",
    )
    return {"status": "passed", "job_manifest": job_manifest, "report": report}


def _write_inference_failure_artifacts(
    *,
    store: ObjectStore,
    feature_month: str,
    run_id: str,
    base_input_uri: str,
    model_package_uri: str,
    output_prefix_uri: str,
    job_metadata: dict,
    runtime: RuntimeDefaults,
    error: Exception,
) -> None:
    now = _utc_now()
    error_message = str(error)
    error_payload = {
        "schema_version": "ipcch-monthly-e2e-report-v1",
        "feature_month": feature_month,
        "run_id": run_id,
        "status": "failed",
        "error_type": type(error).__name__,
        "error_message": error_message,
        "created_at_utc": now,
    }
    job_manifest = {
        "schema_version": "ipcch-monthly-e2e-report-v1",
        "feature_month": feature_month,
        "run_id": run_id,
        "vertex_ai_project_id": job_metadata.get("vertex_ai_project_id"),
        "vertex_ai_region": job_metadata.get("vertex_ai_region"),
        "vertex_ai_job_id": job_metadata.get("vertex_ai_job_id"),
        "vertex_ai_job_resource_name": job_metadata.get("vertex_ai_job_resource_name"),
        "inference_mode": "vertex_ai_custom_job",
        "model_package_uri": model_package_uri,
        "model_version_or_checksum": job_metadata.get("model_version_or_checksum"),
        "vertex_ai_custom_job_container_image_uri": job_metadata.get(
            "vertex_ai_custom_job_container_image_uri"
        ),
        "vertex_ai_custom_job_container_digest": job_metadata.get(
            "vertex_ai_custom_job_container_digest",
            job_metadata.get("container_image_digest"),
        ),
        "container_image_digest": job_metadata.get("container_image_digest"),
        "input_base_uri": base_input_uri,
        "output_uri": output_prefix_uri,
        "job_status": "FAILED",
        "failure_reason": error_message,
        "created_at_utc": job_metadata.get("created_at_utc", now),
        "completed_at_utc": now,
        "retry_policy": {"max_retries": runtime.max_retries},
        "vertex_ai_custom_job_timeout_seconds": (
            runtime.vertex_ai_custom_job_timeout_seconds
        ),
        "status": "failed",
        "artifact_paths": {},
        "checksums": {},
    }
    report = {
        "schema_version": "ipcch-monthly-e2e-report-v1",
        "feature_month": feature_month,
        "run_id": run_id,
        "status": "failed",
        "input_base_uri": base_input_uri,
        "input_base_path": base_input_uri,
        "model_package_uri": model_package_uri,
        "vertex_ai_job_id": job_metadata.get("vertex_ai_job_id"),
        "cloud_runtime_validation_status": "failed",
        "model_package_validation_status": "not_completed",
        "model_output_schema": {"status": "failed"},
        "local_reference_comparison": {"status": "not_provided"},
        "custom_job_exit_code": None,
        "custom_job_log_uri": job_metadata.get("custom_job_log_uri"),
        "failure_reason": error_message,
        "retry_policy": {"max_retries": runtime.max_retries},
        "vertex_ai_custom_job_timeout_seconds": (
            runtime.vertex_ai_custom_job_timeout_seconds
        ),
        "prediction_output_paths": {},
    }
    store.write_text(
        output_prefix_uri + "inference_error.json",
        json.dumps(error_payload, indent=2, sort_keys=True) + "\n",
    )
    store.write_text(
        output_prefix_uri + "vertex_ai_job_manifest.json",
        json.dumps(job_manifest, indent=2, sort_keys=True) + "\n",
    )
    store.write_text(
        output_prefix_uri + "inference_report.json",
        json.dumps(report, indent=2, sort_keys=True) + "\n",
    )


def _load_reference_predictions(
    store: ObjectStore, reference_sample_uri: str
) -> dict[str, pd.DataFrame]:
    frame = pd.read_csv(StringIO(store.read_text(reference_sample_uri)))
    if "scope_months" not in frame.columns:
        return {scope: frame.copy() for scope in PREDICTION_SCOPES}
    normalized = frame["scope_months"].map(_normalize_scope_months)
    return {
        scope: frame[normalized == _scope_to_months(scope)].copy()
        for scope in PREDICTION_SCOPES
        if not frame[normalized == _scope_to_months(scope)].empty
    }


def _model_package_id_from_manifest(
    *, store: ObjectStore, model_package_uri: str
) -> str | None:
    manifest_uri = model_package_uri.rstrip("/") + "/model_package_manifest.json"
    if store.get_metadata(manifest_uri) is None:
        return None
    manifest = json.loads(store.read_text(manifest_uri))
    model_package_id = manifest.get("model_package_id")
    if model_package_id is None:
        return None
    return str(model_package_id)


def _run_script_and_collect_predictions(
    *,
    store: ObjectStore,
    feature_month: str,
    base_input_uri: str,
    model_package_uri: str,
    command_runner,
    workspace_root: str | Path | None,
) -> tuple[dict[str, pd.DataFrame], list[str], dict]:
    workspace = Path(workspace_root or "/tmp/ipcch-vertex-inference")
    input_dir = workspace / "input"
    model_dir = workspace / "model_package"
    output_dir = workspace / "inference"
    input_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    yyyymm = feature_month.replace("-", "")
    base_input_path = input_dir / f"ipcch_monthly_base_input_{yyyymm}.csv"
    base_input_path.write_text(store.read_text(base_input_uri), encoding="utf-8")
    _localize_model_package(
        store=store,
        model_package_uri=model_package_uri,
        model_dir=model_dir,
    )

    command = build_inference_command(
        base_input_path=str(base_input_path),
        model_package_path=str(model_dir),
        output_dir=str(output_dir),
        feature_month=feature_month,
    )
    result = command_runner(command, output_dir=output_dir)
    if result and result.get("returncode", 0) != 0:
        raise RuntimeError(f"inference command failed: {result.get('stderr', '')}")

    predictions = {}
    for scope in PREDICTION_SCOPES:
        path = output_dir / f"ipcch_launch_{yyyymm}_scope_{scope}_predictions.csv"
        predictions[scope] = pd.read_csv(path)
    return predictions, command, result or {"returncode": 0}


def _localize_model_package(
    *, store: ObjectStore, model_package_uri: str, model_dir: Path
) -> None:
    prefix = (
        model_package_uri
        if model_package_uri.endswith("/")
        else model_package_uri + "/"
    )
    object_uris = [uri for uri in store.list(prefix) if not uri.endswith("/")]
    if not object_uris:
        raise RuntimeError(
            f"model package has no materializable files: {model_package_uri}"
        )
    for uri in object_uris:
        relative = uri.removeprefix(prefix)
        if not relative or relative.startswith("../") or "/../" in relative:
            raise RuntimeError(f"invalid model package object path: {uri}")
        target = model_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(store.read_text(uri), encoding="utf-8")
    (model_dir / "SOURCE_URI.txt").write_text(
        model_package_uri + "\n", encoding="utf-8"
    )


def _default_command_runner(command, *, output_dir):
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _synthetic_prediction_frame(
    *,
    base_input: pd.DataFrame,
    feature_month: str,
    scope: str,
    model_package_uri: str,
    model_package_id: str | None = None,
) -> pd.DataFrame:
    frame = base_input.copy()
    if "admin_code" not in frame.columns:
        frame["admin_code"] = frame["area_id"]
    if "_row_id" not in frame.columns:
        frame["_row_id"] = range(len(frame))
    for phase in ("phase2", "phase3", "phase4", "phase5"):
        frame[f"{phase}_worse_score"] = 0.0
        frame[f"{phase}_worse_pred"] = 0
    frame["overall_phase_pred"] = 1
    frame["feature_period"] = feature_month
    scope_months = _scope_to_months(scope)
    frame["target_period"] = _target_period(feature_month, scope_months)
    frame["scope_months"] = scope_months
    frame["model_package_id"] = (
        model_package_id or model_package_uri.rstrip("/").rsplit("/", 1)[-1]
    )
    frame["source_input"] = "base"
    return frame[list(REQUIRED_PREDICTION_COLUMNS)]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
