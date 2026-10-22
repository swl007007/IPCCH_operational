"""Run one cloud command and append its record to cloud-operations.jsonl (P4 operation log).

usage: cloudop.py --purpose TEXT --scope read|write|mutation --effect TEXT -- argv...
The command's stdout is kept in full under runs/<utc>-<n>.out; the log holds a bounded tail.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE / "cloud-operations.jsonl"
OUT = Path("/home/swl007007/projects/food-crisis-research/staging/fewsnet-fixed-map-retrain-20261022/cloud-ops/p4")


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--purpose", required=True)
    parser.add_argument("--scope", required=True, choices=["read", "write", "mutation"])
    parser.add_argument("--effect", required=True)
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
    OUT.mkdir(parents=True, exist_ok=True)
    started = now()
    stem = OUT / f"{started.replace(':', '')}-{len(LOG.read_text().splitlines()) if LOG.exists() else 0}"
    completed = subprocess.run(argv, capture_output=True, text=True, timeout=args.timeout)
    stem.with_suffix(".out").write_text(completed.stdout)
    stem.with_suffix(".err").write_text(completed.stderr)
    record = {"started_utc": started, "finished_utc": now(), "argv": argv, "purpose": args.purpose,
              "scope": args.scope, "intended_effect": args.effect, "exit_code": completed.returncode,
              "stdout_file": str(stem.with_suffix(".out")), "stdout_tail": completed.stdout[-1500:],
              "stderr_tail": completed.stderr[-1500:]}
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
