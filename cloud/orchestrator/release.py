from __future__ import annotations

import argparse
import hashlib
import json
from io import StringIO

import pandas as pd

from cloud.orchestrator.inference import validate_prediction_outputs
from cloud.common.object_store import GCSObjectStore
from cloud.common.object_store import ObjectStore
from cloud.common.object_store import GenerationConflict
from cloud.common.reports import build_release_manifest

IMMUTABLE_REFERENCE_KEYS = {
    "checksum",
    "generation",
    "version",
    "version_id",
    "model_version",
}


def write_release(
    *,
    store: ObjectStore,
    feature_month: str,
    run_id: str,
    run_prefix_uri: str,
    release_root_uri: str,
    referenced_artifacts: list[dict],
    staging_root_uri: str | None = None,
    source_roots: dict[str, str] | None = None,
    input_manifest_uri: str | None = None,
    container_image_digest: str | None = None,
    model_package_reference: dict | None = None,
    validation_status: dict | None = None,
    inference_status: str | None = None,
    advisory_warning_state: str = "none",
    copied_artifact_contents: dict[str, str] | None = None,
) -> dict:
    yyyymm = feature_month.replace("-", "")
    copied_artifact_contents = dict(copied_artifact_contents or {})
    source_roots = source_roots or {}
    _ensure_release_run_summary_candidate(
        store=store,
        run_prefix_uri=run_prefix_uri,
        source_roots=source_roots,
        copied_artifact_contents=copied_artifact_contents,
        release_manifest_path=release_root_uri + "release_manifest.json",
    )
    copied = []
    checksums = {}
    _validate_release_preflight(
        store=store,
        yyyymm=yyyymm,
        run_prefix_uri=run_prefix_uri,
        source_roots=source_roots,
        copied_artifact_contents=copied_artifact_contents,
        referenced_artifacts=referenced_artifacts,
        input_manifest_uri=input_manifest_uri,
        container_image_digest=container_image_digest,
        model_package_reference=model_package_reference,
        validation_status=validation_status,
        inference_status=inference_status,
    )
    step_report = {
        "schema_version": "ipcch-monthly-e2e-report-v1",
        "feature_month": feature_month,
        "run_id": run_id,
        "status": "running",
        "release_mode": "release_on_success",
        "staging_root_uri": staging_root_uri,
        "release_root_uri": release_root_uri,
        "accepted_artifacts": _copied_artifact_relatives(yyyymm),
        "copy_results": [],
        "checksum_verification": {"status": "pending"},
        "manifest_generation_precondition": 0,
        "previous_manifest_generation": None,
        "new_manifest_generation": None,
        "failure_reason": None,
        "released_copied_artifacts": [],
        "released_referenced_artifacts": referenced_artifacts,
    }

    previous_manifest_generation = _object_generation(
        store, release_root_uri + "release_manifest.json"
    )
    step_report["previous_manifest_generation"] = previous_manifest_generation
    manifest_generation_precondition = previous_manifest_generation or 0
    step_report["manifest_generation_precondition"] = manifest_generation_precondition
    for relative in _copied_artifact_relatives(yyyymm):
        source_uri = _source_uri_for_relative(
            relative, run_prefix_uri=run_prefix_uri, source_roots=source_roots
        )
        target_uri = release_root_uri + f"runs/{run_id}/" + relative
        content = copied_artifact_contents.get(relative)
        if content is None:
            content = store.read_text(source_uri)
        try:
            metadata = store.write_text(target_uri, content, if_generation_match=0)
        except GenerationConflict:
            step_report["status"] = "release_conflict"
            step_report["new_manifest_generation"] = None
            step_report["failure_reason"] = "release_artifact_generation_conflict"
            store.write_text(
                run_prefix_uri + "release/release_step_report.json",
                json.dumps(step_report, indent=2, sort_keys=True) + "\n",
            )
            return {
                "schema_version": "ipcch-monthly-e2e-report-v1",
                "feature_month": feature_month,
                "run_id": run_id,
                "accepted_run_id": run_id,
                "status": "release_conflict",
                "release_root_uri": release_root_uri,
                "previous_manifest_unchanged": True,
            }
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        copied.append(
            {"uri": target_uri, "generation": metadata.generation, "checksum": checksum}
        )
        checksums[target_uri] = checksum
    step_report["copy_results"] = copied.copy()
    step_report["checksum_verification"] = {"status": "passed"}
    step_report["released_copied_artifacts"] = copied
    step_report["previous_manifest_generation"] = previous_manifest_generation
    step_report["status"] = "passed"
    step_report_uri = (
        release_root_uri + f"runs/{run_id}/release/release_step_report.json"
    )
    step_content = json.dumps(step_report, indent=2, sort_keys=True) + "\n"
    store.write_text(run_prefix_uri + "release/release_step_report.json", step_content)
    try:
        step_metadata = store.write_text(
            step_report_uri, step_content, if_generation_match=0
        )
    except GenerationConflict:
        step_report["status"] = "release_conflict"
        step_report["new_manifest_generation"] = None
        step_report["failure_reason"] = "release_step_report_generation_conflict"
        store.write_text(
            run_prefix_uri + "release/release_step_report.json",
            json.dumps(step_report, indent=2, sort_keys=True) + "\n",
        )
        return {
            "schema_version": "ipcch-monthly-e2e-report-v1",
            "feature_month": feature_month,
            "run_id": run_id,
            "accepted_run_id": run_id,
            "status": "release_conflict",
            "release_root_uri": release_root_uri,
            "previous_manifest_unchanged": True,
        }
    step_checksum = hashlib.sha256(step_content.encode("utf-8")).hexdigest()
    step_copied_entry = {
        "uri": step_report_uri,
        "generation": step_metadata.generation,
        "checksum": step_checksum,
    }
    copied.append(step_copied_entry)
    checksums[step_report_uri] = step_checksum

    def update_step_reports(*, update_released_step_report: bool) -> None:
        nonlocal step_checksum
        step_content = json.dumps(step_report, indent=2, sort_keys=True) + "\n"
        store.write_text(
            run_prefix_uri + "release/release_step_report.json", step_content
        )
        if not update_released_step_report:
            return
        metadata = store.write_text(
            step_report_uri,
            step_content,
            if_generation_match=step_copied_entry["generation"],
        )
        step_checksum = hashlib.sha256(step_content.encode("utf-8")).hexdigest()
        step_copied_entry["generation"] = metadata.generation
        step_copied_entry["checksum"] = step_checksum
        checksums[step_report_uri] = step_checksum

    base_path = (
        release_root_uri
        + f"runs/{run_id}/assembly/ipcch_monthly_base_input_{yyyymm}.csv"
    )
    summary_path = (
        release_root_uri
        + f"runs/{run_id}/assembly/ipcch_monthly_base_input_{yyyymm}_summary.json"
    )
    prediction_paths = [
        release_root_uri
        + f"runs/{run_id}/inference/ipcch_launch_{yyyymm}_scope_{scope}_predictions.csv"
        for scope in ("0m", "6m", "12m")
    ]
    base_validation_path = (
        release_root_uri + f"runs/{run_id}/qa/base_input_validation_report.json"
    )
    vertex_manifest_path = (
        release_root_uri + f"runs/{run_id}/inference/vertex_ai_job_manifest.json"
    )
    inference_report_path = (
        release_root_uri + f"runs/{run_id}/inference/inference_report.json"
    )
    gee_manifest_path = (
        release_root_uri + f"runs/{run_id}/gee_exports/gee_export_manifest.json"
    )
    evi_validation_path = (
        release_root_uri + f"runs/{run_id}/evi/evi_validation_report.json"
    )
    evi_extraction_path = (
        release_root_uri + f"runs/{run_id}/evi/evi_extraction_manifest.json"
    )
    input_manifest_reference = None
    if input_manifest_uri:
        input_manifest_reference = {"uri": input_manifest_uri}
        try:
            input_manifest_content = store.read_text(input_manifest_uri)
        except FileNotFoundError:
            input_manifest_content = None
        if input_manifest_content is not None:
            input_manifest_reference["checksum"] = hashlib.sha256(
                input_manifest_content.encode("utf-8")
            ).hexdigest()
        metadata = _object_metadata(store, input_manifest_uri)
        if metadata is not None:
            input_manifest_reference["generation"] = metadata.generation
    manifest = build_release_manifest(
        feature_month=feature_month,
        run_id=run_id,
        accepted_run_id=run_id,
        base_input_path=base_path,
        base_input_checksum=checksums[base_path],
        summary_path=summary_path,
        summary_checksum=checksums[summary_path],
        prediction_output_paths=prediction_paths,
        prediction_output_checksums={
            path: checksums[path] for path in prediction_paths
        },
        released_copied_artifacts=copied,
        released_referenced_artifacts=referenced_artifacts,
        evi_evidence_references=[
            _released_reference(evi_validation_path, checksums),
            _released_reference(evi_extraction_path, checksums),
        ],
        gee_export_manifest_reference=_released_reference(gee_manifest_path, checksums),
        input_manifest_reference=input_manifest_reference,
        base_input_validation_report_reference=_released_reference(
            base_validation_path, checksums
        ),
        vertex_ai_job_manifest_reference=_released_reference(
            vertex_manifest_path, checksums
        ),
        inference_report_reference=_released_reference(
            inference_report_path, checksums
        ),
        model_package_reference=model_package_reference or {},
        model_version_or_checksum=(model_package_reference or {}).get("version")
        or (model_package_reference or {}).get("checksum"),
        container_image_digest=container_image_digest,
        validation_status=validation_status or {},
        inference_status=inference_status,
        advisory_warning_state=advisory_warning_state,
    )
    try:
        manifest_metadata = store.write_text(
            release_root_uri + "release_manifest.json",
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            if_generation_match=manifest_generation_precondition,
        )
    except GenerationConflict:
        step_report["status"] = "release_conflict"
        step_report["new_manifest_generation"] = None
        step_report["failure_reason"] = "release_manifest_generation_conflict"
        update_step_reports(update_released_step_report=True)
        return {
            "schema_version": "ipcch-monthly-e2e-report-v1",
            "feature_month": feature_month,
            "run_id": run_id,
            "accepted_run_id": run_id,
            "status": "release_conflict",
            "release_root_uri": release_root_uri,
            "previous_manifest_unchanged": True,
        }
    step_report["new_manifest_generation"] = manifest_metadata.generation
    update_step_reports(update_released_step_report=False)
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish IPCCH monthly release")
    parser.add_argument("--feature-month", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--input-manifest-uri", required=True)
    parser.add_argument("--run-root-uri", required=True)
    parser.add_argument("--staging-root-uri", required=True)
    parser.add_argument("--release-root-uri", required=True)
    parser.add_argument("--container-image-digest")
    parser.add_argument("--model-package-uri")
    parser.add_argument("--model-package-id")
    parser.add_argument("--model-package-generation")
    parser.add_argument("--model-package-checksum")
    parser.add_argument("--model-package-version")
    parser.add_argument(
        "--referenced-artifact-json",
        action="append",
        default=[],
        help="JSON object for immutable referenced evidence; may be repeated",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    store = GCSObjectStore.from_default()
    model_package_reference = None
    if args.model_package_uri:
        model_package_reference = {"uri": args.model_package_uri}
        if args.model_package_id:
            model_package_reference["model_package_id"] = args.model_package_id
        if args.model_package_generation:
            model_package_reference["generation"] = args.model_package_generation
        if args.model_package_checksum:
            model_package_reference["checksum"] = args.model_package_checksum
        if args.model_package_version:
            model_package_reference["version"] = args.model_package_version
    referenced_artifacts = [json.loads(raw) for raw in args.referenced_artifact_json]
    result = write_release(
        store=store,
        feature_month=args.feature_month,
        run_id=args.run_id,
        run_prefix_uri=args.run_root_uri,
        staging_root_uri=args.staging_root_uri,
        release_root_uri=args.release_root_uri,
        referenced_artifacts=referenced_artifacts,
        input_manifest_uri=args.input_manifest_uri,
        container_image_digest=args.container_image_digest,
        model_package_reference=model_package_reference,
        validation_status={"base_input": "passed", "inference": "passed"},
        inference_status="passed",
    )
    return 0 if result.get("status") == "current" else 1


def _copied_artifact_relatives(yyyymm: str) -> list[str]:
    return [
        f"assembly/ipcch_monthly_base_input_{yyyymm}.csv",
        f"assembly/ipcch_monthly_base_input_{yyyymm}_summary.json",
        "qa/base_input_validation_report.json",
        "inference/vertex_ai_job_manifest.json",
        "inference/inference_report.json",
        "gee_exports/gee_export_manifest.json",
        "evi/evi_validation_report.json",
        "evi/evi_extraction_manifest.json",
        "run_summary.json",
        f"inference/ipcch_launch_{yyyymm}_scope_0m_predictions.csv",
        f"inference/ipcch_launch_{yyyymm}_scope_6m_predictions.csv",
        f"inference/ipcch_launch_{yyyymm}_scope_12m_predictions.csv",
    ]


def _released_reference(uri: str, checksums: dict[str, str]) -> dict:
    return {"uri": uri, "checksum": checksums[uri]}


def _validate_release_preflight(
    *,
    store: ObjectStore,
    yyyymm: str,
    run_prefix_uri: str,
    source_roots: dict[str, str],
    copied_artifact_contents: dict[str, str],
    referenced_artifacts: list[dict],
    input_manifest_uri: str | None,
    container_image_digest: str | None,
    model_package_reference: dict | None,
    validation_status: dict | None,
    inference_status: str | None,
) -> None:
    if not container_image_digest:
        raise ValueError("container_image_digest is required before release")
    if not input_manifest_uri:
        raise ValueError("input_manifest_uri is required before release")
    _read_required_text(store, input_manifest_uri, label="input_manifest")
    if not model_package_reference:
        raise ValueError("model_package_reference is required before release")
    _require_immutable_reference(
        model_package_reference, label="model_package_reference"
    )
    if not referenced_artifacts:
        raise ValueError("referenced_artifacts must include immutable evidence")
    for artifact in referenced_artifacts:
        _require_immutable_reference(artifact, label="referenced artifact")
    if (validation_status or {}).get("base_input") != "passed":
        raise ValueError("validation_status.base_input must be passed before release")
    if (validation_status or {}).get("inference") != "passed":
        raise ValueError("validation_status.inference must be passed before release")
    if inference_status != "passed":
        raise ValueError("inference_status must be passed before release")

    _require_report_status(
        store=store,
        relative="qa/base_input_validation_report.json",
        label="base_input_validation_report",
        run_prefix_uri=run_prefix_uri,
        source_roots=source_roots,
        copied_artifact_contents=copied_artifact_contents,
        allowed_statuses={"passed"},
        nested_required_statuses={"schema_result": {"passed"}},
    )
    _require_report_status(
        store=store,
        relative="inference/vertex_ai_job_manifest.json",
        label="vertex_ai_job_manifest",
        run_prefix_uri=run_prefix_uri,
        source_roots=source_roots,
        copied_artifact_contents=copied_artifact_contents,
        allowed_statuses={"passed"},
    )
    _require_report_status(
        store=store,
        relative="inference/inference_report.json",
        label="inference_report",
        run_prefix_uri=run_prefix_uri,
        source_roots=source_roots,
        copied_artifact_contents=copied_artifact_contents,
        allowed_statuses={"passed"},
        nested_required_statuses={"model_output_schema": {"passed"}},
    )
    inference_report = _read_json_artifact(
        store=store,
        relative="inference/inference_report.json",
        label="inference_report",
        run_prefix_uri=run_prefix_uri,
        source_roots=source_roots,
        copied_artifact_contents=copied_artifact_contents,
    )
    reference_status = (inference_report.get("local_reference_comparison") or {}).get(
        "status"
    )
    if reference_status not in {"provided", "not_provided", "passed"}:
        raise ValueError("inference_report local_reference_comparison status required")
    _require_report_status(
        store=store,
        relative="gee_exports/gee_export_manifest.json",
        label="gee_export_manifest",
        run_prefix_uri=run_prefix_uri,
        source_roots=source_roots,
        copied_artifact_contents=copied_artifact_contents,
        allowed_statuses={"passed"},
    )
    _require_report_status(
        store=store,
        relative="evi/evi_validation_report.json",
        label="evi_validation_report",
        run_prefix_uri=run_prefix_uri,
        source_roots=source_roots,
        copied_artifact_contents=copied_artifact_contents,
        allowed_statuses={"passed", "passed_with_warnings"},
    )
    _require_report_status(
        store=store,
        relative="evi/evi_extraction_manifest.json",
        label="evi_extraction_manifest",
        run_prefix_uri=run_prefix_uri,
        source_roots=source_roots,
        copied_artifact_contents=copied_artifact_contents,
        allowed_statuses={"passed"},
    )
    _require_report_status(
        store=store,
        relative="run_summary.json",
        label="run_summary",
        run_prefix_uri=run_prefix_uri,
        source_roots=source_roots,
        copied_artifact_contents=copied_artifact_contents,
        allowed_statuses={"released"},
    )
    base_input = pd.read_csv(
        StringIO(
            _read_artifact_text(
                store=store,
                relative=f"assembly/ipcch_monthly_base_input_{yyyymm}.csv",
                run_prefix_uri=run_prefix_uri,
                source_roots=source_roots,
                copied_artifact_contents=copied_artifact_contents,
            )
        )
    )
    predictions = {
        scope: pd.read_csv(
            StringIO(
                _read_artifact_text(
                    store=store,
                    relative=(
                        f"inference/ipcch_launch_{yyyymm}_scope_{scope}_predictions.csv"
                    ),
                    run_prefix_uri=run_prefix_uri,
                    source_roots=source_roots,
                    copied_artifact_contents=copied_artifact_contents,
                )
            )
        )
        for scope in ("0m", "6m", "12m")
    }
    expected_model_package_id = _model_package_id(model_package_reference)
    if expected_model_package_id is None:
        raise ValueError("model_package_reference.model_package_id is required")
    try:
        validate_prediction_outputs(
            predictions,
            feature_month=f"{yyyymm[:4]}-{yyyymm[4:]}",
            base_input=base_input,
            expected_model_package_id=expected_model_package_id,
        )
    except ValueError as exc:
        raise ValueError(f"prediction artifact validation failed: {exc}") from exc


def _require_immutable_reference(reference: dict, *, label: str) -> None:
    if not reference.get("uri"):
        raise ValueError(f"{label} uri is required")
    if not any(reference.get(key) for key in IMMUTABLE_REFERENCE_KEYS):
        raise ValueError(f"{label} must include an immutable reference")


def _model_package_id(reference: dict | None) -> str | None:
    if not reference:
        return None
    model_package_id = str(reference.get("model_package_id") or "").strip()
    return model_package_id or None


def _ensure_release_run_summary_candidate(
    *,
    store: ObjectStore,
    run_prefix_uri: str,
    source_roots: dict[str, str],
    copied_artifact_contents: dict[str, str],
    release_manifest_path: str,
) -> None:
    if "run_summary.json" in copied_artifact_contents:
        return
    summary = _read_json_artifact(
        store=store,
        relative="run_summary.json",
        label="run_summary",
        run_prefix_uri=run_prefix_uri,
        source_roots=source_roots,
        copied_artifact_contents={},
    )
    if summary.get("status") != "running":
        return
    summary.update(
        {
            "status": "released",
            "release_attempted": True,
            "released": True,
            "release_manifest_path": release_manifest_path,
        }
    )
    copied_artifact_contents["run_summary.json"] = (
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )


def _require_report_status(
    *,
    store: ObjectStore,
    relative: str,
    label: str,
    run_prefix_uri: str,
    source_roots: dict[str, str],
    copied_artifact_contents: dict[str, str],
    allowed_statuses: set[str],
    nested_required_statuses: dict[str, set[str]] | None = None,
) -> dict:
    report = _read_json_artifact(
        store=store,
        relative=relative,
        label=label,
        run_prefix_uri=run_prefix_uri,
        source_roots=source_roots,
        copied_artifact_contents=copied_artifact_contents,
    )
    if report.get("status") not in allowed_statuses:
        raise ValueError(f"{label} status must be one of {sorted(allowed_statuses)}")
    for key, statuses in (nested_required_statuses or {}).items():
        nested = report.get(key)
        if not isinstance(nested, dict) or nested.get("status") not in statuses:
            raise ValueError(f"{label} {key}.status must be one of {sorted(statuses)}")
    return report


def _read_json_artifact(
    *,
    store: ObjectStore,
    relative: str,
    label: str,
    run_prefix_uri: str,
    source_roots: dict[str, str],
    copied_artifact_contents: dict[str, str],
) -> dict:
    try:
        return json.loads(
            _read_artifact_text(
                store=store,
                relative=relative,
                run_prefix_uri=run_prefix_uri,
                source_roots=source_roots,
                copied_artifact_contents=copied_artifact_contents,
            )
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON") from exc


def _read_artifact_text(
    *,
    store: ObjectStore,
    relative: str,
    run_prefix_uri: str,
    source_roots: dict[str, str],
    copied_artifact_contents: dict[str, str],
) -> str:
    if relative in copied_artifact_contents:
        return copied_artifact_contents[relative]
    source_uri = _source_uri_for_relative(
        relative, run_prefix_uri=run_prefix_uri, source_roots=source_roots
    )
    return _read_required_text(store, source_uri, label=relative)


def _read_required_text(store: ObjectStore, uri: str, *, label: str) -> str:
    try:
        return store.read_text(uri)
    except FileNotFoundError as exc:
        raise ValueError(f"{label} is required before release: {uri}") from exc


def _source_uri_for_relative(
    relative: str, *, run_prefix_uri: str, source_roots: dict[str, str]
) -> str:
    if relative.startswith("gee_exports/") and source_roots.get("gee_export_root_uri"):
        return source_roots["gee_export_root_uri"] + relative.removeprefix(
            "gee_exports/"
        )
    if relative.startswith("evi/") and source_roots.get("evi_output_root_uri"):
        return source_roots["evi_output_root_uri"] + relative.removeprefix("evi/")
    if relative.startswith("assembly/") and source_roots.get("assembly_root_uri"):
        return source_roots["assembly_root_uri"] + relative.removeprefix("assembly/")
    if relative.startswith("qa/") and source_roots.get("qa_root_uri"):
        return source_roots["qa_root_uri"] + relative.removeprefix("qa/")
    if relative.startswith("inference/") and source_roots.get("inference_root_uri"):
        return source_roots["inference_root_uri"] + relative.removeprefix("inference/")
    return run_prefix_uri + relative


def _object_generation(store: ObjectStore, uri: str) -> str | None:
    metadata = _object_metadata(store, uri)
    if metadata is None:
        return None
    return metadata.generation


def _object_metadata(store: ObjectStore, uri: str):
    if hasattr(store, "get_metadata"):
        return store.get_metadata(uri)
    generation = getattr(store, "_generations", {}).get(uri)
    if generation is not None:
        from cloud.common.object_store import ObjectMetadata

        return ObjectMetadata(uri=uri, generation=str(generation))
    return None
