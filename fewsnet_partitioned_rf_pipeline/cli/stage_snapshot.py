"""Administrative bootstrap for immutable FEWSNET source snapshots."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from fewsnet_partitioned_rf_pipeline.core.data import stage_snapshot
from fewsnet_partitioned_rf_pipeline.vertex.storage import (
    GCSArtifactStore,
    GenerationConflict,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage an immutable FEWSNET source snapshot."
    )
    parser.add_argument("--panel", required=True, type=Path)
    parser.add_argument("--boundaries", required=True, type=Path)
    parser.add_argument("--destination-root", required=True)
    parser.add_argument("--created-at-utc", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = stage_snapshot(
            panel_path=args.panel,
            boundaries_path=args.boundaries,
            destination_root=args.destination_root,
            store=GCSArtifactStore.from_default(),
            created_at_utc=args.created_at_utc,
        )
    except (ValueError, GenerationConflict) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1

    manifest_uri = (
        f"{args.destination_root.rstrip('/')}/inputs/snapshots/"
        f"{manifest.snapshot_id}/source_manifest.json"
    )
    print(json.dumps({"manifest_uri": manifest_uri}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
