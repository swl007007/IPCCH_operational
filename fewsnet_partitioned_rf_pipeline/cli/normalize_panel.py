"""Administrative CLI for one-time FEWSNET panel normalization."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Sequence

from fewsnet_partitioned_rf_pipeline.core.normalization import normalize_panel


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize an immutable FEWSNET bootstrap panel."
    )
    parser.add_argument("--input-panel", required=True, type=Path)
    parser.add_argument("--output-panel", required=True, type=Path)
    parser.add_argument("--audit-output", required=True, type=Path)
    return parser


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = normalize_panel(
            args.input_panel,
            args.output_panel,
            args.audit_output,
        )
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "audit_path": str(result.audit_path),
                "audit_sha256": _sha256_file(result.audit_path),
                "duplicate_group_count": result.duplicate_group_count,
                "normalized_row_count": result.normalized_row_count,
                "output_panel_path": str(result.output_panel_path),
                "output_sha256": result.output_sha256,
                "raw_row_count": result.raw_row_count,
                "removed_row_count": result.removed_row_count,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
