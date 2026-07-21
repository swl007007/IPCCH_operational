#!/usr/bin/env python3
"""Build the checked-in Stage 3 parity fixture from the reference checkout."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import numpy as np


APPROVED_REFERENCE_COMMIT = "1ecf180669568bbf9eb2129683108162902a415a"
REFERENCE_MODULE = "scripts.compare_partitioned_vs_pooled_rf_k40_nc4"
REFERENCE_SCRIPT = Path("scripts/compare_partitioned_vs_pooled_rf_k40_nc4.py")
MIN_SAMPLES = 5
THRESHOLD = 0.5


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def _verified_reference_root(reference_root: Path) -> tuple[Path, str]:
    root = reference_root.expanduser().resolve(strict=True)
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or "git rev-parse failed"
        raise ValueError(f"cannot verify reference commit for {root}: {detail}") from exc
    commit = result.stdout.strip()
    if commit != APPROVED_REFERENCE_COMMIT:
        raise ValueError(
            "reference checkout commit mismatch: "
            f"expected {APPROVED_REFERENCE_COMMIT}, observed {commit}"
        )
    script = root / REFERENCE_SCRIPT
    if not script.is_file():
        raise ValueError(f"reference script is missing: {script}")
    return root, commit


def _reference_functions(reference_root: Path) -> tuple[Any, Any, Any, dict]:
    sys.path.insert(0, str(reference_root))
    prior_dont_write_bytecode = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        try:
            module = importlib.import_module(REFERENCE_MODULE)
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "reference import dependency is missing; install the reference "
                f"checkout's developer requirements ({exc.name})"
            ) from exc
    finally:
        sys.dont_write_bytecode = prior_dont_write_bytecode
    module_path = Path(module.__file__).resolve()
    expected_path = (reference_root / REFERENCE_SCRIPT).resolve()
    if module_path != expected_path:
        raise RuntimeError(
            f"imported unexpected reference module: {module_path}"
        )
    return (
        module.train_pooled_model,
        module.train_partitioned_model,
        module.predict_partitioned_probability,
        dict(module.RF_PARAMS),
    )


def _synthetic_matrix() -> tuple[np.ndarray, ...]:
    X_train = np.asarray(
        [
            [0.0, 0.0],
            [0.2, 0.1],
            [0.4, 0.2],
            [1.0, 1.0],
            [1.2, 1.1],
            [1.4, 1.2],
            [2.0, 0.0],
            [2.2, 0.2],
            [2.8, 1.0],
            [3.0, 1.2],
            [4.0, 0.0],
            [4.2, 0.2],
            [4.4, 0.4],
            [4.6, 0.6],
            [4.8, 0.8],
        ],
        dtype=float,
    )
    y_train = np.asarray(
        [0, 0, 0, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1],
        dtype=int,
    )
    groups_train = np.asarray([0] * 6 + [1] * 4 + [2] * 5, dtype=int)
    X_test = np.asarray(
        [
            [0.1, 0.05],
            [1.3, 1.15],
            [2.5, 0.6],
            [4.5, 0.5],
            [3.5, 0.7],
            [0.7, 0.6],
        ],
        dtype=float,
    )
    groups_test = np.asarray([0, 0, 1, 2, 99, -1], dtype=int)
    return X_train, y_train, groups_train, X_test, groups_test


def _expected_partition_status(
    models: dict,
    y_train: np.ndarray,
    groups_train: np.ndarray,
) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for group in sorted(int(value) for value in np.unique(groups_train) if value >= 0):
        group_target = y_train[groups_train == group]
        if models[group] is not None:
            status = "partition_model"
        elif len(group_target) < MIN_SAMPLES:
            status = "pooled_small_partition"
        elif len(np.unique(group_target)) < 2:
            status = "pooled_single_class"
        else:
            raise RuntimeError(f"cannot derive fallback status for partition {group}")
        statuses[str(group)] = status
    return statuses


def _build_payload(reference_root: Path, source_commit: str) -> dict[str, Any]:
    (
        train_pooled_model,
        train_partitioned_model,
        predict_partitioned_probability,
        rf_parameters,
    ) = _reference_functions(reference_root)
    X_train, y_train, groups_train, X_test, groups_test = _synthetic_matrix()
    pooled_model = train_pooled_model(X_train, y_train, lower_model="rf")
    partition_models = train_partitioned_model(
        X_train,
        y_train,
        groups_train,
        lower_model="rf",
        min_samples=MIN_SAMPLES,
    )
    expected_probability = predict_partitioned_probability(
        partition_models,
        pooled_model,
        X_test,
        groups_test,
    )
    return {
        "schema_version": "fewsnet-stage3-reference-parity-v1",
        "source_repository": "Food_Crisis_Cluster",
        "source_git_commit": source_commit,
        "source_relative_path": str(REFERENCE_SCRIPT),
        "rf_parameters": rf_parameters,
        "min_samples": MIN_SAMPLES,
        "threshold": THRESHOLD,
        "X_train": X_train.tolist(),
        "y_train": y_train.tolist(),
        "groups_train": groups_train.tolist(),
        "X_test": X_test.tolist(),
        "groups_test": groups_test.tolist(),
        "expected_probability": expected_probability.tolist(),
        "expected_class": (expected_probability >= THRESHOLD).astype(int).tolist(),
        "expected_partition_status": _expected_partition_status(
            partition_models,
            y_train,
            groups_train,
        ),
        "expected_model_presence": {
            str(int(group)): model is not None
            for group, model in sorted(partition_models.items())
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    reference_root, source_commit = _verified_reference_root(args.reference_root)
    payload = _build_payload(reference_root, source_commit)
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"reference_commit={source_commit}")
    print(f"output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
