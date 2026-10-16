"""Catalog every FEWS NET research run directory that holds fitted weights (bounded root).

Weights come from the exact-content hash cache produced by booster_search (every *.ubj under
the root). Labels describe provenance and completeness; they never exclude a run from the
acceptance ledger:
  completed_frozen_actual | candidate | development | diagnostic | replay_evidence |
  aborted | test_fixture
Saved prediction files and fold records are counted so replay feasibility is explicit.

Scope: weight counts come from the *.ubj content-hash cache only (other encodings such as
joblib/JSON boosters are not counted) and are provisional; cache paths are deduplicated
(last record per path). Directory-walk failures are recorded per run and make that run's
metadata counts ``null`` (unknown), never zero.

  python3 -m research_cloud.inventory.fews_catalog --cache UBJ_CACHE.jsonl --root /mnt/c/Users/swl00/geoxgb_runs --out OUT.json
"""
import argparse
import collections
import json
import os
import re
import time


def label(run, entries):
    if os.path.exists(os.path.join(run, "INTEGRATION_FIXTURE.json")) or re.match(r"(minirun|smoke)-", os.path.basename(run)):
        return "test_fixture"
    name = os.path.basename(run)
    if name.endswith(".failed_stage1"):
        return "aborted"
    if "replay-evidence" in name:
        return "replay_evidence"
    if os.path.exists(os.path.join(run, "scenario_final", "frozen.json")) and "scenario_actual" in entries:
        return "completed_frozen_actual"
    if name.startswith("confirm-"):
        return "candidate"
    if re.match(r"geoxgb-d\d+", name):
        return "diagnostic"
    if name.startswith("geoxgb-v"):
        return "development"
    return "unlabelled"


def count(run, patterns, errors):
    """Matching file count, or None when any part of the run could not be traversed."""
    n, failed = 0, []
    for dirpath, _, files in os.walk(run, onerror=lambda e: failed.append({"path": e.filename, "error": type(e).__name__})):
        n += sum(1 for f in files if any(re.search(p, f) for p in patterns))
    errors.extend(failed)
    return None if failed else n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    files, size, sub = collections.Counter(), collections.Counter(), collections.defaultdict(collections.Counter)
    prefix = args.root.rstrip("/") + "/"
    latest = {}
    for line in open(args.cache):
        r = json.loads(line)
        if r["path"].startswith(prefix):
            latest[r["path"]] = r          # append-only cache: keep the last record per path
    for r in latest.values():
        rel = r["path"][len(prefix):].split("/")
        files[rel[0]] += 1
        size[rel[0]] += r["bytes"]
        sub[rel[0]][rel[1] if len(rel) > 2 else "."] += 1
    runs, all_errors = [], []
    for name in sorted(files):
        run = os.path.join(args.root, name)
        errors = []
        entries = set(os.listdir(run))
        runs.append({"run": name, "label": label(run, entries), "weight_files": files[name], "weight_bytes": size[name],
                     "weight_subdirs": dict(sub[name].most_common(8)),
                     "prediction_files": count(run, [r"pred.*\.csv(\.gz)?$"], errors),
                     "fold_records": count(run, [r"^fold\.json$"], errors), "walk_errors": errors,
                     "completion_markers": sorted(m for m in ("completion.json", "frozen.json", "evaluation.json", "COMPLETE.json",
                                                               "INTEGRATION_FIXTURE.json") if m in entries)})
        all_errors.extend(errors)
    out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "root": args.root, "hash_cache": args.cache,
           "scope": "weights = *.ubj content-hash cache only (provisional; other encodings not counted)",
           "cache_records_deduplicated": len(latest), "walk_errors_total": len(all_errors),
           "runs": runs, "totals": {"runs": len(runs), "weight_files": sum(files.values()), "weight_bytes": sum(size.values())},
           "by_label": dict(collections.Counter(r["label"] for r in runs))}
    json.dump(out, open(args.out, "w"), indent=1)
    print(out["totals"], out["by_label"])


if __name__ == "__main__":
    main()
