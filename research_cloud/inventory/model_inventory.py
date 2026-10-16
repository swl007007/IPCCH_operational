"""Inventory retained model members of every MLflow-registered research family.

Reads the MLflow store strictly read-only (SQLite mode=ro, query_only) and the
member manifests that the importer stored as artifacts:

* dashboard families (experiment 1): manifests/models.tar.members.json, paths
  relative to the family's source run root (roots.json);
* forecasting families (experiment 3): manifests/plan.json, members per
  registered version, paths relative to the IPCCH repository root.

Every member is resolved to an absolute path and checked without opening
Dropbox placeholders (dropbox_local). Local files are hashed (resumable cache)
and compared with the recorded bytes/sha256.

A member is checked under EVERY declared candidate root (roots.json), not just
the first existing directory: an existing run directory is no evidence that a
given weight file survived there. The member resolves to the first candidate
whose bytes+sha256 match the record; all candidates and their states are kept.
Status per member: verified | hash_mismatch (local copies exist, none match) |
present_unverified (local, not hashed) | cloud_only | inspection_error |
missing (every declared candidate verified not-found). A root that is itself
cloud-only or uninspectable propagates to its members; it is never dropped.

Hashes may come from a resumable cache keyed by (path, size, mtime_ns); such
results are provisional (hash_source=cache). Final transfer/package acceptance
must use --fresh, which ignores the cache and re-reads every byte.

Usage:
  python3 -m research_cloud.inventory.model_inventory --out DIR [--hash [--fresh]] [--workers 4]
"""
import argparse
import collections
import glob
import hashlib
import json
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

from research_cloud.inventory import dropbox_local

STORE = "/home/swl007007/.local/share/ipcch-mlflow"
ROOTS = os.path.join(os.path.dirname(__file__), "roots.json")


def connect(store):
    db = sqlite3.connect(f"file:{store}/mlflow.db?mode=ro", uri=True)
    db.execute("PRAGMA query_only=ON")
    return db


def is_dropbox(path):
    return "ifpri dropbox" in path.lower()


def path_state(paths):
    """Map path -> status record; Dropbox paths via attributes only, others via stat."""
    out = {}
    drop = [p for p in paths if p.startswith("/mnt/") and is_dropbox(p)]
    for rec in dropbox_local.classify(drop):
        out[rec["path"]] = rec
    for p in paths:
        if p in out:
            continue
        try:
            st = os.stat(p)
            out[p] = {"path": p, "status": "local", "bytes": st.st_size}
        except FileNotFoundError:
            out[p] = {"path": p, "status": "missing"}
        except OSError as exc:
            out[p] = {"path": p, "status": "inspection_error", "error": type(exc).__name__}
    return out


def declared_roots(candidates, state_fn=None):
    """Return [{"root", "status"}] for EVERY declared candidate, in declared order."""
    states = (state_fn or path_state)(candidates)
    return [{"root": c, "status": states[c]["status"]} for c in candidates]


def dashboard_members(db, store, roots):
    rows = db.execute(
        "SELECT r.run_uuid, t.value FROM runs r JOIN tags t ON t.run_uuid=r.run_uuid AND t.key='zz_prov.source_key' "
        "WHERE r.experiment_id=1 AND r.run_uuid NOT IN (SELECT run_uuid FROM tags WHERE key='mlflow.parentRunId')"
    ).fetchall()
    fams = []
    for run_id, source_key in rows:
        family = db.execute("SELECT value FROM tags WHERE run_uuid=? AND key='family'", (run_id,)).fetchone()[0]
        manifest = f"{store}/artifacts/1/{run_id}/artifacts/manifests/models.tar.members.json"
        root = declared_roots(roots["dashboard"][source_key])
        members = json.load(open(manifest))
        fams.append({"kind": "dashboard", "family": family, "parent_run_id": run_id, "source_key": source_key,
                     "manifest": manifest, "roots": root,
                     "members": [dict(m, version_keys=None) for m in members]})
    return fams


def forecasting_members(store, roots):
    fams = []
    root = declared_roots([roots["forecasting_root"]])
    for plan_path in sorted(glob.glob(f"{store}/artifacts/3/*/artifacts/manifests/plan.json")):
        plan = json.load(open(plan_path))
        by_path = {}
        for version_key, version in plan["versions"].items():
            for m in version["members"]:
                rec = by_path.setdefault(m["path"], {"path": m["path"], "bytes": m["bytes"], "sha256": m["sha256"],
                                                     "role": m.get("role"), "kind": m.get("kind"), "version_keys": []})
                if rec["sha256"] != m["sha256"] or rec["bytes"] != m["bytes"]:
                    raise SystemExit(f"conflicting member records for {m['path']} in {plan_path}")
                rec["version_keys"].append(version_key)
        fams.append({"kind": "forecasting", "family": plan["source_key"], "parent_run_id": plan_path.split("/")[-4],
                     "source_key": plan["source_key"], "manifest": plan_path, "roots": root,
                     "members": list(by_path.values()),
                     "versions": {k: {"registered_model": v.get("registered_model"), "members": len(v["members"]),
                                      "arm": v.get("arm"), "lead": v.get("lead"), "family": v.get("family")}
                                  for k, v in plan["versions"].items()}})
    return fams


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def attach_candidates(fams, state_fn=None):
    """Give every member one candidate per DECLARED root. Members under an unreadable root keep
    that root's failure (root_cloud_only / root_inspection_error / root_missing) so it can never
    be silently dropped; members under readable roots get their own path status."""
    state_fn = state_fn or path_state
    paths = set()
    for fam in fams:
        for m in fam["members"]:
            m["candidates"] = []
            for r in fam["roots"]:
                cand = {"path": os.path.join(r["root"], m["path"])}
                if r["status"] == "local":
                    paths.add(cand["path"])
                else:
                    cand["status"] = "root_" + r["status"]
                m["candidates"].append(cand)
    states = state_fn(sorted(paths))
    for fam in fams:
        for m in fam["members"]:
            for c in m["candidates"]:
                if "status" in c:
                    continue
                st = states[c["path"]]
                c["status"] = st["status"]
                if st["status"] == "inspection_error":
                    c["error"] = st.get("error")


def resolve(member):
    """Pick the candidate matching the recorded bytes+sha256; never call a member missing unless
    every candidate was verified not-found."""
    cands = member["candidates"]
    if not cands:
        raise ValueError("member has no declared candidate roots")
    for c in cands:
        if c.get("sha256_actual") == member["sha256"] and c.get("bytes_actual") == member["bytes"]:
            return "verified", c["path"]
    statuses = {c["status"] for c in cands}
    if "local" in statuses:
        if any("sha256_actual" not in c for c in cands if c["status"] == "local"):
            return "present_unverified", None
        return "hash_mismatch", None
    for status in ("inspection_error", "root_inspection_error", "cloud_only", "root_cloud_only"):
        if status in statuses:
            return status.removeprefix("root_"), None
    if statuses <= {"missing", "root_missing"}:
        return "missing", None
    raise ValueError(f"unknown candidate statuses {sorted(statuses)}")


def load_cache(path):
    cache = {}
    if os.path.exists(path):
        for line in open(path):
            rec = json.loads(line)
            cache[(rec["path"], rec["bytes"], rec["mtime_ns"])] = rec["sha256"]
    return cache


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--store", default=STORE)
    ap.add_argument("--hash", action="store_true")
    ap.add_argument("--fresh", action="store_true", help="ignore the hash cache (implies --hash); required for acceptance")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    args.hash = args.hash or args.fresh
    os.makedirs(args.out, exist_ok=True)
    roots = json.load(open(ROOTS))
    db = connect(args.store)
    fams = dashboard_members(db, args.store, roots) + forecasting_members(args.store, roots)

    attach_candidates(fams)

    cache_path = os.path.join(args.out, "hash-cache.jsonl")
    cache = {} if args.fresh else load_cache(cache_path)
    todo = {}
    for fam in fams:
        for m in fam["members"]:
            for c in m["candidates"]:
                if c["status"] != "local":
                    continue
                s_ = os.stat(c["path"])
                c["bytes_actual"] = s_.st_size
                key = (c["path"], s_.st_size, s_.st_mtime_ns)
                if key in cache:
                    c["sha256_actual"], c["hash_source"] = cache[key], "cache"
                elif args.hash:
                    todo.setdefault(key, []).append(c)

    if todo:
        with open(cache_path, "a") as cache_out, ThreadPoolExecutor(args.workers) as pool:
            keys = list(todo)
            for key, digest in zip(keys, pool.map(lambda k: sha256(k[0]), keys)):
                cache_out.write(json.dumps({"path": key[0], "bytes": key[1], "mtime_ns": key[2], "sha256": digest}) + "\n")
                cache_out.flush()
                for c in todo[key]:
                    c["sha256_actual"], c["hash_source"] = digest, "fresh"

    for fam in fams:
        for m in fam["members"]:
            m["status"], m["resolved_path"] = resolve(m)

    summary = []
    with open(os.path.join(args.out, "members.jsonl"), "w") as out:
        for fam in fams:
            counts = collections.Counter()
            for m in fam["members"]:
                counts[m["status"]] += 1
                out.write(json.dumps({"family": fam["family"], **{k: v for k, v in m.items()}}) + "\n")
            members = fam["members"]
            summary.append({k: fam[k] for k in ("kind", "family", "parent_run_id", "source_key", "manifest", "roots")}
                           | {"member_count": len(members), "recorded_bytes": sum(m["bytes"] for m in members),
                              "largest_bytes": max((m["bytes"] for m in members), default=0),
                              "status_counts": dict(counts), "versions": fam.get("versions")})
    json.dump({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "store": args.store,
               "hash_mode": "fresh" if args.fresh else ("cache+fresh" if args.hash else "cache-only"),
               "families": summary}, open(os.path.join(args.out, "summary.json"), "w"), indent=1)
    for s in summary:
        print(s["kind"], s["family"], s["member_count"], round(s["recorded_bytes"] / 1e9, 3), "GB", s["status_counts"])


if __name__ == "__main__":
    main()
