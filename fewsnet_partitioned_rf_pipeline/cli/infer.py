"""Normalize one completed Vertex batch output into formal FEWSNET CSVs."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import io
import json
from pathlib import Path
import tempfile
from typing import Sequence

import pandas as pd

from fewsnet_partitioned_rf_pipeline.cli.train import (
    _load_snapshot_manifest,
    _localize_snapshot,
    _validate_localized_snapshot,
)
from fewsnet_partitioned_rf_pipeline.config import (
    FEATURE_CONTRACT_PATH,
    HORIZON_KEYS,
)
from fewsnet_partitioned_rf_pipeline.core.horizons import (
    select_latest_inference_frame,
)
from fewsnet_partitioned_rf_pipeline.core.preprocessing import (
    Stage3FeatureBuilder,
    load_feature_contract,
)
from fewsnet_partitioned_rf_pipeline.core.types import RegisteredModelVersion
from fewsnet_partitioned_rf_pipeline.vertex.batch_prediction import (
    normalize_batch_output,
)
from fewsnet_partitioned_rf_pipeline.vertex.storage import (
    ArtifactStore,
    GCSArtifactStore,
    put_immutable_or_verify,
)


@dataclass(frozen=True)
class InferenceWorkerConfig:
    model_ref: RegisteredModelVersion
    snapshot_manifest_uri: str
    suite_version: str
    horizon_months: int
    raw_output_prefix: str
    run_csv_uri: str
    suite_csv_uri: str


def normalize_and_publish_batch_output(
    *,
    raw_paths: Sequence[str | Path],
    input_frame: pd.DataFrame,
    model_ref: RegisteredModelVersion,
    suite_version: str,
    run_csv_uri: str,
    suite_csv_uri: str,
    store: ArtifactStore,
) -> pd.DataFrame:
    """Validate every row, serialize once, then immutably write both CSVs."""
    _validate_prediction_uris(
        model_ref=model_ref,
        suite_version=suite_version,
        run_csv_uri=run_csv_uri,
        suite_csv_uri=suite_csv_uri,
    )
    predictions = normalize_batch_output(
        raw_paths,
        input_frame,
        model_ref,
        suite_version,
    )
    buffer = io.StringIO(newline="")
    predictions.to_csv(buffer, index=False, lineterminator="\n")
    canonical_csv = buffer.getvalue().encode("utf-8")
    put_immutable_or_verify(store, run_csv_uri, canonical_csv)
    put_immutable_or_verify(store, suite_csv_uri, canonical_csv)
    return predictions


def run_inference_worker(
    config: InferenceWorkerConfig,
    *,
    store: ArtifactStore,
) -> pd.DataFrame:
    """Rebuild the exact latest input frame and publish one formal horizon CSV."""
    _validate_worker_config(config)
    with tempfile.TemporaryDirectory(prefix="fewsnet-infer-") as temp_dir:
        temp_root = Path(temp_dir)
        manifest = _load_snapshot_manifest(config.snapshot_manifest_uri, store)
        localized = _localize_snapshot(
            manifest,
            store,
            temp_root / "snapshot",
        )
        panel = _validate_localized_snapshot(manifest, localized)
        contract = load_feature_contract(FEATURE_CONTRACT_PATH)
        feature_frame = Stage3FeatureBuilder().transform(panel, contract)
        input_frame = select_latest_inference_frame(
            feature_frame,
            manifest.latest_feature_month,
            config.horizon_months,
        )

        raw_paths = _localize_raw_output(
            config.raw_output_prefix,
            store,
            temp_root / "raw",
        )
        return normalize_and_publish_batch_output(
            raw_paths=raw_paths,
            input_frame=input_frame,
            model_ref=config.model_ref,
            suite_version=config.suite_version,
            run_csv_uri=config.run_csv_uri,
            suite_csv_uri=config.suite_csv_uri,
            store=store,
        )


def _localize_raw_output(
    prefix: str,
    store: ArtifactStore,
    output_root: Path,
) -> list[Path]:
    refs = store.list(prefix.rstrip("/") + "/")
    error_refs = [
        ref
        for ref in refs
        if Path(ref.uri).name.startswith("errors_")
        and Path(ref.uri).suffix == ".jsonl"
    ]
    if error_refs:
        raise ValueError(
            "raw Batch Prediction output contains error files: "
            f"{[ref.uri for ref in error_refs]}"
        )
    prediction_refs = [
        ref
        for ref in refs
        if Path(ref.uri).name.startswith("predictions_")
        and Path(ref.uri).suffix == ".jsonl"
    ]
    if not prediction_refs:
        raise ValueError("raw Batch Prediction output is missing prediction files")
    output_root.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, ref in enumerate(prediction_refs):
        path = output_root / f"predictions_{index:05d}.jsonl"
        store.download_file(ref.uri, path, generation=ref.generation)
        paths.append(path)
    return paths


def _validate_worker_config(config: InferenceWorkerConfig) -> None:
    if not isinstance(config, InferenceWorkerConfig):
        raise TypeError("config must be an InferenceWorkerConfig")
    expected_horizon_key = HORIZON_KEYS.get(config.horizon_months)
    if expected_horizon_key is None:
        raise ValueError(f"unsupported horizon_months: {config.horizon_months}")
    if config.model_ref.horizon_key != expected_horizon_key:
        raise ValueError("candidate model reference differs from requested horizon")
    for name, uri in (
        ("snapshot_manifest_uri", config.snapshot_manifest_uri),
        ("raw_output_prefix", config.raw_output_prefix),
        ("run_csv_uri", config.run_csv_uri),
        ("suite_csv_uri", config.suite_csv_uri),
    ):
        if not isinstance(uri, str) or not uri.startswith("gs://"):
            raise ValueError(f"{name} must be a gs:// URI")


def _validate_prediction_uris(
    *,
    model_ref: RegisteredModelVersion,
    suite_version: str,
    run_csv_uri: str,
    suite_csv_uri: str,
) -> None:
    horizon_key = model_ref.horizon_key
    expected_suffix = f"/predictions/{horizon_key}.csv"
    expected_suite_suffix = f"/suites/{suite_version}{expected_suffix}"
    if (
        not isinstance(suite_csv_uri, str)
        or not suite_csv_uri.startswith("gs://")
        or not suite_csv_uri.endswith(expected_suite_suffix)
    ):
        raise ValueError(
            "suite_csv_uri must be "
            "suites/{suite_version}/predictions/{horizon}.csv"
        )
    publication_root = suite_csv_uri[: -len(expected_suite_suffix)]
    expected_run_prefix = f"{publication_root}/runs/"
    if (
        not isinstance(run_csv_uri, str)
        or not run_csv_uri.startswith(expected_run_prefix)
        or not run_csv_uri.endswith(expected_suffix)
    ):
        raise ValueError(
            "run_csv_uri must be runs/{run_id}/predictions/{horizon}.csv"
        )
    run_id = run_csv_uri[len(expected_run_prefix) : -len(expected_suffix)]
    if not run_id or "/" in run_id:
        raise ValueError(
            "run_csv_uri must be runs/{run_id}/predictions/{horizon}.csv"
        )
    expected_artifact_uri = (
        f"{publication_root}/suites/{suite_version}/models/{horizon_key}"
    )
    if model_ref.artifact_uri != expected_artifact_uri:
        raise ValueError(
            "model artifact URI must match the exact suite publication root"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize one exact-version FEWSNET Vertex batch output"
    )
    parser.add_argument("--model-horizon-key", required=True)
    parser.add_argument("--model-parent-resource-name", required=True)
    parser.add_argument("--model-version-resource-name", required=True)
    parser.add_argument("--model-version-id", required=True)
    parser.add_argument("--model-suite-version-alias", required=True)
    parser.add_argument("--model-artifact-uri", required=True)
    parser.add_argument("--snapshot-manifest-uri", required=True)
    parser.add_argument("--suite-version", required=True)
    parser.add_argument(
        "--horizon-months",
        required=True,
        type=int,
        choices=sorted(HORIZON_KEYS),
    )
    parser.add_argument("--raw-output-prefix", required=True)
    parser.add_argument("--run-csv-uri", required=True)
    parser.add_argument("--suite-csv-uri", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    model_ref = RegisteredModelVersion(
        horizon_key=args.model_horizon_key,
        parent_model_resource_name=args.model_parent_resource_name,
        version_resource_name=args.model_version_resource_name,
        version_id=args.model_version_id,
        suite_version_alias=args.model_suite_version_alias,
        artifact_uri=args.model_artifact_uri,
    )
    config = InferenceWorkerConfig(
        model_ref=model_ref,
        snapshot_manifest_uri=args.snapshot_manifest_uri,
        suite_version=args.suite_version,
        horizon_months=args.horizon_months,
        raw_output_prefix=args.raw_output_prefix,
        run_csv_uri=args.run_csv_uri,
        suite_csv_uri=args.suite_csv_uri,
    )
    predictions = run_inference_worker(
        config,
        store=GCSArtifactStore.from_default(),
    )
    print(
        json.dumps(
            {
                "row_count": len(predictions),
                "run_csv_uri": config.run_csv_uri,
                "suite_csv_uri": config.suite_csv_uri,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
