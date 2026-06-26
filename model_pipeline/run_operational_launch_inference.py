#!/usr/bin/env python3
"""Non-interactive operational launch inference CLI."""

import argparse
import hashlib
import sys
import traceback
from datetime import date
from pathlib import Path

if __package__ in (None, ""):
    REPO_ROOT = Path(__file__).resolve().parents[1]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

import pandas as pd

from model_pipeline.ipcch_launch_runtime import adapters
from model_pipeline.ipcch_launch_runtime import feature_contract
from model_pipeline.ipcch_launch_runtime import inference
from model_pipeline.ipcch_launch_runtime import model_package
from model_pipeline.ipcch_launch_runtime import outputs
from model_pipeline.ipcch_launch_runtime import visualization


SCOPES = (0, 6, 12)


class OperationalLaunchError(RuntimeError):
    """Raised for expected CLI runtime failures."""


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    model_package_root = Path(args.model_package)
    output_dir = Path(args.output_dir)
    map_disabled = bool(args.no_map)
    maps_enabled = not map_disabled
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = _base_summary(
        args=args,
        input_path=input_path,
        model_package_root=model_package_root,
        output_dir=output_dir,
        map_disabled=map_disabled,
    )

    temp_paths = []
    temp_to_final = []
    try:
        input_df = _read_monthly_csv(input_path)
        summary["input"]["sha256"] = _sha256(input_path)
        monthly_rows, input_report = adapters.validate_monthly_input(
            input_df,
            args.feature_month,
        )
        summary["feature_month"] = input_report["feature_month"]
        summary["input_report"] = input_report
        feature_month = input_report["feature_month"]

        if args.validate_only:
            summary["status"] = "passed"
            summary["final_status"] = "passed"
            outputs.write_json_atomic(summary, outputs.run_summary_path(output_dir))
            return 0

        if maps_enabled and not args.spatial_path:
            raise OperationalLaunchError("--spatial-path is required unless --no-map is set")

        path_sets = [
            outputs.scope_primary_paths(
                output_dir,
                feature_month,
                scope,
                include_map=maps_enabled,
            )
            for scope in SCOPES
        ]
        summary["planned_outputs"] = _outputs_by_scope(path_sets)
        outputs.assert_no_existing_primary_outputs(path_sets, overwrite=args.overwrite)

        for scope, path_set in zip(SCOPES, path_sets):
            target_month = add_calendar_months(feature_month, scope)
            summary["scopes_attempted"].append(scope)
            predictions, scope_summary = run_scope(
                monthly_rows=monthly_rows,
                model_package_root=model_package_root,
                feature_month=feature_month,
                scope_months=scope,
                target_month=target_month,
                source_input=str(input_path),
            )
            summary["scope_summaries"][str(scope)] = scope_summary
            if summary["model_package_id"] == _package_id_from_root(model_package_root):
                summary["model_package_id"] = scope_summary.get(
                    "model_package_id",
                    summary["model_package_id"],
                )

            prediction_temp = outputs.write_dataframe_temp(
                predictions,
                path_set["predictions_csv"],
            )
            temp_paths.append(prediction_temp)
            temp_to_final.append((prediction_temp, path_set["predictions_csv"]))

            if maps_enabled:
                map_temp = outputs.temp_path_for(path_set["map_png"])
                temp_paths.append(map_temp)
                map_summary = visualization.render_scope_map(
                    predictions,
                    args.spatial_path,
                    map_temp,
                )
                temp_to_final.append((map_temp, path_set["map_png"]))
                summary["scope_summaries"][str(scope)]["map_summary"] = map_summary

        outputs.commit_temp_outputs(temp_to_final)
        temp_paths = []
        summary["written_outputs"] = _outputs_by_scope(path_sets)
        summary["outputs"] = dict(summary["written_outputs"])
        summary["scopes_completed"] = list(SCOPES)
        summary["status"] = "passed"
        summary["final_status"] = "passed"
        outputs.write_json_atomic(summary, outputs.run_summary_path(output_dir))
        return 0
    except EXPECTED_ERRORS as exc:
        outputs.cleanup_temp_paths(temp_paths)
        summary["status"] = "failed"
        summary["final_status"] = "failed"
        summary["error"] = {
            "type": exc.__class__.__name__,
            "message": str(exc),
        }
        outputs.write_json_atomic(summary, outputs.run_summary_path(output_dir))
        print("Operational launch inference failed: {0}".format(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        outputs.cleanup_temp_paths(temp_paths)
        summary["status"] = "failed"
        summary["final_status"] = "failed"
        summary["error"] = {
            "type": exc.__class__.__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        outputs.write_json_atomic(summary, outputs.run_summary_path(output_dir))
        raise


def run_scope(
    *,
    monthly_rows,
    model_package_root,
    feature_month,
    scope_months,
    target_month,
    source_input,
):
    package = model_package.load_scope_package(model_package_root, scope_months)
    metadata = package.get("metadata", {})
    package_root = package.get("scope_dir", model_package_root)
    feature_matrix, contract_report = feature_contract.apply_feature_contract(
        monthly_rows,
        package["contract"],
        package["feature_columns"],
        package_root=package_root,
        metadata=metadata,
    )
    thresholds = _thresholds_from_metadata(metadata)
    model_package_id = _model_package_id(metadata, model_package_root)
    monotonicity_policy = str(metadata.get("monotonicity_policy", "cummax"))
    predictions, score_summary = inference.score_scope(
        monthly_rows=monthly_rows,
        feature_matrix=feature_matrix,
        models=package["models"],
        thresholds=thresholds,
        scope_months=scope_months,
        feature_month=feature_month,
        target_month=target_month,
        model_package_id=model_package_id,
        source_input=source_input,
        monotonicity_policy=monotonicity_policy,
    )
    scope_summary = dict(score_summary)
    scope_summary["feature_contract"] = contract_report
    scope_summary["model_package_id"] = model_package_id
    return predictions, scope_summary


def add_calendar_months(feature_month, months):
    year, month = _parse_feature_month(feature_month)
    month_index = (year * 12 + (month - 1)) + int(months)
    target_year = month_index // 12
    target_month = month_index % 12 + 1
    return "{0:04d}-{1:02d}".format(target_year, target_month)


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Run operational IPC-CH launch inference for fixed 0/6/12m scopes."
    )
    parser.add_argument("--input", required=True, help="Monthly production input CSV")
    parser.add_argument("--model-package", required=True, help="Model package root")
    parser.add_argument("--output-dir", required=True, help="Delivery output directory")
    parser.add_argument("--feature-month", required=True, help="Feature month YYYY-MM or YYYYMM")
    parser.add_argument("--spatial-path", help="Spatial boundary file for map generation")
    parser.add_argument("--validate-only", action="store_true", help="Validate input only")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing primary outputs")
    parser.add_argument("--no-map", action="store_true", help="Disable map generation")
    return parser


def _read_monthly_csv(input_path):
    try:
        return pd.read_csv(
            input_path,
            dtype={"area_id": "string", "admin_code": "string"},
        )
    except Exception as exc:
        raise OperationalLaunchError("Failed to read input CSV: {0}".format(exc)) from exc


def _base_summary(*, args, input_path, model_package_root, output_dir, map_disabled):
    return {
        "status": "started",
        "final_status": "started",
        "feature_month": str(args.feature_month),
        "model_package_id": _package_id_from_root(model_package_root),
        "model_package": {"path": str(model_package_root)},
        "scopes_attempted": [],
        "scopes_completed": [],
        "input": {
            "path": str(input_path),
            "sha256": None,
        },
        "input_report": None,
        "scope_summaries": {},
        "planned_outputs": {},
        "written_outputs": {},
        "outputs": {},
        "map_generation_disabled": bool(map_disabled),
        "validate_only": bool(args.validate_only),
        "overwrite": bool(args.overwrite),
        "output_dir": str(output_dir),
        "run_date": date.today().isoformat(),
    }


def _sha256(path):
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise OperationalLaunchError("Failed to hash input CSV: {0}".format(exc)) from exc
    return digest.hexdigest()


def _parse_feature_month(feature_month):
    value = str(feature_month).strip()
    if len(value) == 7 and value[4] == "-":
        year = int(value[:4])
        month = int(value[5:7])
    elif len(value) == 6:
        year = int(value[:4])
        month = int(value[4:6])
    else:
        raise OperationalLaunchError("feature_month must use YYYY-MM or YYYYMM format")
    return year, month


def _thresholds_from_metadata(metadata):
    if isinstance(metadata.get("thresholds"), dict):
        return metadata["thresholds"]
    if isinstance(metadata.get("decision_thresholds"), dict):
        return metadata["decision_thresholds"]
    if "threshold" in metadata:
        return {"default": metadata["threshold"]}
    return {"default": 0.2}


def _model_package_id(metadata, model_package_root):
    for key in ("model_package_id", "package_id", "model_id"):
        if key in metadata and metadata[key] not in (None, ""):
            return str(metadata[key])
    return _package_id_from_root(model_package_root)


def _package_id_from_root(model_package_root):
    return Path(model_package_root).name or str(model_package_root)


def _outputs_by_scope(path_sets):
    return {
        str(scope): {name: str(path) for name, path in path_set.items()}
        for scope, path_set in zip(SCOPES, path_sets)
    }


EXPECTED_ERRORS = (
    OperationalLaunchError,
    adapters.InputContractError,
    feature_contract.FeatureContractError,
    inference.InferenceError,
    model_package.ModelPackageError,
    outputs.OutputError,
    visualization.VisualizationError,
)


if __name__ == "__main__":
    sys.exit(main())
