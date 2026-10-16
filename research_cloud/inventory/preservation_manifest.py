"""Byte-preservation manifest for one research run root (input to the per-file transfer and its verification).

Every regular file under the root gets its relative path, bytes and sha256 (``.ubj`` hashes are reused from the exact-hash
cache only when path, size and mtime still match). Symlinks are recorded, not followed. Optional ``--recorded`` JSON
files map relative paths to sha256 values the run itself recorded (e.g. ``scenario_actual/actual.json`` ``outputs``);
each must match, and a mismatch or a missing recorded file fails the manifest.

  python -m research_cloud.inventory.preservation_manifest --root RUN --out MANIFEST.json
      [--cache ubj-hash-cache.jsonl] [--recorded PREFIX=FILE.json:key ...]
"""
import argparse
import hashlib
import json
import os
import sys
import time


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def load_cache(path):
    out = {}
    if path and os.path.exists(path):
        for line in open(path):
            r = json.loads(line)
            out[r["path"]] = r
    return out


def walk(root, cache):
    files, links, errors = [], [], []
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: errors.append(str(e))):
        for name in dirnames + filenames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                links.append({"path": os.path.relpath(full, root), "target": os.readlink(full)})
        dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                continue
            st = os.stat(full)
            hit = cache.get(full)
            cached = bool(hit and hit["bytes"] == st.st_size and hit.get("mtime_ns") == st.st_mtime_ns)
            digest = hit["sha256"] if cached else sha256(full)
            files.append({"path": os.path.relpath(full, root), "bytes": st.st_size, "sha256": digest,
                          "hash_source": "cache (path, bytes and mtime_ns equal)" if cached else "fresh"})
    return sorted(files, key=lambda r: r["path"]), links, errors


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache")
    ap.add_argument("--recorded", action="append", default=[], help="PREFIX=FILE.json:key (paths in key are under PREFIX)")
    args = ap.parse_args(argv)
    t0 = time.time()
    files, links, errors = walk(args.root, load_cache(args.cache))
    by_path = {f["path"]: f["sha256"] for f in files}
    checks = []
    for spec in args.recorded:
        prefix, _, ref = spec.partition("=")
        rec_file, _, key = ref.partition(":")
        try:
            recorded = json.load(open(os.path.join(args.root, rec_file)))[key]
        except (OSError, ValueError, KeyError) as exc:
            checks.append({"path": None, "recorded_by": rec_file, "ok": False, "present": False,
                           "error": f"{type(exc).__name__}: {exc}"})
            continue
        for rel, digest in recorded.items():
            path = os.path.normpath(os.path.join(prefix, rel))
            checks.append({"path": path, "recorded_by": rec_file, "ok": by_path.get(path) == digest,
                           "present": path in by_path})
    manifest = {"root": os.path.abspath(args.root), "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "files": files, "symlinks": links, "walk_errors": errors, "recorded_checks": checks,
                "totals": {"files": len(files), "bytes": sum(f["bytes"] for f in files),
                           "recorded_checked": len(checks), "recorded_ok": sum(c["ok"] for c in checks)},
                "complete": not errors and all(c["ok"] for c in checks), "seconds": round(time.time() - t0, 1)}
    json.dump(manifest, open(args.out, "w"), indent=1)
    print(json.dumps({**manifest["totals"], "complete": manifest["complete"], "seconds": manifest["seconds"]}))
    return 0 if manifest["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
