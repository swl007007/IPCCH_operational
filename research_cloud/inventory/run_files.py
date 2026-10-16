"""Classify (Dropbox-safe) and freshly hash every file under one run directory matching patterns.

For identified unregistered research runs. Dropbox placeholders are never opened; per-file
read errors are recorded, not dropped.

  python3 -m research_cloud.inventory.run_files --root RUN_DIR --pattern '*.ubj' --pattern '*.joblib' --out OUT.json
"""
import argparse
import fnmatch
import hashlib
import json
import os
import time

from research_cloud.inventory import dropbox_local


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--pattern", action="append", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    walk_errors, paths = [], []
    for dirpath, _, files in os.walk(args.root, onerror=lambda e: walk_errors.append({"path": e.filename, "error": type(e).__name__})):
        paths += [os.path.join(dirpath, f) for f in files if any(fnmatch.fnmatch(f, p) for p in args.pattern)]
    paths.sort()
    if "ifpri dropbox" in args.root.lower():
        states = {r["path"]: r for r in dropbox_local.classify(paths)}
    else:
        states = {p: {"status": "local"} for p in paths}
    records = []
    for p in paths:
        rec = {"path": os.path.relpath(p, args.root), "status": states[p]["status"]}
        if rec["status"] == "local":
            try:
                h = hashlib.sha256()
                with open(p, "rb") as f:
                    for block in iter(lambda: f.read(1 << 20), b""):
                        h.update(block)
                rec.update(bytes=os.path.getsize(p), sha256=h.hexdigest())
            except OSError as exc:
                rec.update(status="read_error", error=type(exc).__name__)
        records.append(rec)
    out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "root": args.root, "patterns": args.pattern,
           "walk_errors": walk_errors, "complete": not walk_errors and all(r["status"] == "local" for r in records),
           "files": records}
    json.dump(out, open(args.out, "w"), indent=1)
    import collections
    print(len(records), dict(collections.Counter(r["status"] for r in records)), "bytes",
          sum(r.get("bytes", 0) for r in records), "complete", out["complete"])


if __name__ == "__main__":
    main()
