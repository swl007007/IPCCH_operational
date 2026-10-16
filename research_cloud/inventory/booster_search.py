"""Search bounded roots for files with given sha256 digests (exact-content search).

Hashes every file matching --pattern under each root (resumable cache keyed by
path/size/mtime) and reports which target digests were found where. Roots must
not be Dropbox placeholders; callers classify Dropbox roots first.

Traversal and read failures are recorded and make the search ``partial``;
"not_found" is conclusive only when ``complete`` is true. Symlinked files and
directories are never followed (they could lead outside the declared roots);
they are listed for review instead.

Usage: python3 -m research_cloud.inventory.booster_search --targets T.json --root R [--root R2]
          --pattern '*.ubj' --cache C.jsonl --out OUT.json
"""
import argparse
import fnmatch
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def walk(roots, pattern):
    """Return (matching regular files, traversal errors, skipped symlinks)."""
    paths, errors, links = [], [], []
    for root in roots:
        if not os.path.isdir(root):
            errors.append({"path": root, "error": "root is not a readable directory"})
            continue
        for dirpath, dirs, files in os.walk(root, followlinks=False,
                                            onerror=lambda e: errors.append({"path": e.filename, "error": type(e).__name__})):
            links += [os.path.join(dirpath, d) for d in dirs if os.path.islink(os.path.join(dirpath, d))]
            for name in files:
                path = os.path.join(dirpath, name)
                if not fnmatch.fnmatch(name, pattern):
                    continue
                if os.path.islink(path):
                    links.append(path)
                else:
                    paths.append(path)
    return paths, errors, links


def safe_sha(path):
    try:
        return sha256(path)
    except OSError as exc:
        return OSError(type(exc).__name__)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", required=True, help="JSON {label: sha256}")
    ap.add_argument("--root", action="append", required=True)
    ap.add_argument("--pattern", default="*")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    targets = json.load(open(args.targets))
    cache = {}
    if os.path.exists(args.cache):
        for line in open(args.cache):
            r = json.loads(line)
            cache[(r["path"], r["bytes"], r["mtime_ns"])] = r["sha256"]
    paths, errors, links = walk(args.root, args.pattern)
    todo, keyed = [], {}
    for path in paths:
        try:
            st = os.stat(path)
        except OSError as exc:
            errors.append({"path": path, "error": type(exc).__name__})
            continue
        key = (path, st.st_size, st.st_mtime_ns)
        keyed[path] = key
        if key not in cache:
            todo.append(key)
    with open(args.cache, "a") as out, ThreadPoolExecutor(args.workers) as pool:
        for key, digest in zip(todo, pool.map(lambda k: safe_sha(k[0]), todo)):
            if isinstance(digest, OSError):
                errors.append({"path": key[0], "error": str(digest)})
                continue
            cache[key] = digest
            out.write(json.dumps({"path": key[0], "bytes": key[1], "mtime_ns": key[2], "sha256": digest}) + "\n")
    by_sha = {}
    for path, key in keyed.items():
        if key in cache:
            by_sha.setdefault(cache[key], []).append(path)
    found = {label: by_sha.get(digest, []) for label, digest in targets.items()}
    report = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "roots": args.root, "pattern": args.pattern,
              "files_hashed_total": len(keyed), "newly_hashed": len(todo),
              "targets": len(targets), "found": {k: v for k, v in found.items() if v},
              "not_found": sorted(k for k, v in found.items() if not v),
              "complete": not errors, "errors": errors, "skipped_symlinks": links,
              "not_found_is_conclusive": not errors}
    json.dump(report, open(args.out, "w"), indent=1)
    print(json.dumps({k: report[k] for k in ("files_hashed_total", "newly_hashed", "targets", "complete")}),
          "found", len(report["found"]), "not_found", len(report["not_found"]))


if __name__ == "__main__":
    main()
