"""Local-only CLI for the FEWSNET partitioned-RF experiment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from fewsnet_partitioned_rf_pipeline.local.runner import (
    LocalExperimentConfig,
    run_local_experiment,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train and run the local FEWSNET partitioned-RF experiment."
    )
    parser.add_argument("--panel", required=True, type=Path)
    parser.add_argument("--normalization-audit", required=True, type=Path)
    parser.add_argument("--feature-month", required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("Outcome/fewsnet_partitioned_rf"),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = LocalExperimentConfig(
        panel_path=args.panel,
        normalization_audit_path=args.normalization_audit,
        feature_month=args.feature_month,
        output_root=args.output_root,
        overwrite=args.overwrite,
    )
    try:
        result = run_local_experiment(config)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "status": "failed",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result.to_payload(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
