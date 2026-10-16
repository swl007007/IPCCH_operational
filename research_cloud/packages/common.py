"""Shared pieces of the historical inference-package contract.

A package is a directory with ``package.json`` (identity, status, gaps, runtime
records, loader entry, tolerance contract, and the sha256/bytes of every file),
``weights/``, ``deps/``, ``reference/`` and ``loader/``. Every byte copied in is
read fresh from its source and checked against the recorded digest when one
exists; nothing is taken from a hash cache.
"""
import hashlib
import json
import os
import time

PACKAGE_SCHEMA = "rc-inference-package/1"
# design.md "Package and relaxed numerical acceptance": shares/probabilities in [0, 1]
ABS_TOL = 1e-3
REL_TOL = 1e-3


class PackageError(RuntimeError):
    pass


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def tolerance(reference):
    return ABS_TOL + REL_TOL * abs(reference)


def safe_rel(rel):
    """A package-relative path: relative, normalized, no '..' component, no backslash tricks."""
    if not isinstance(rel, str) or not rel or os.path.isabs(rel) or "\\" in rel:
        raise PackageError(f"unsafe package path {rel!r}")
    norm = os.path.normpath(rel)
    if norm != rel or norm.startswith("..") or "/../" in f"/{norm}/":
        raise PackageError(f"unsafe package path {rel!r}")
    return norm


def inside(root, rel):
    """Absolute path of rel under root; refuses anything that resolves outside root (symlinks included)."""
    base = os.path.realpath(root)
    path = os.path.realpath(os.path.join(root, safe_rel(rel)))
    if os.path.commonpath([base, path]) != base:
        raise PackageError(f"package path {rel!r} escapes the package root")
    return path


def ensure_local(paths):
    """Refuse to read any Dropbox path that is not verified local (never hydrate placeholders)."""
    from research_cloud.inventory import dropbox_local
    drop = sorted({p for p in paths if p.startswith("/mnt/") and "ifpri dropbox" in p.lower()})
    bad = [r for r in dropbox_local.classify(drop) if r["status"] != "local"]
    if bad:
        raise PackageError(f"{len(bad)} source files are not verified local, e.g. {bad[:3]}")
    return len(drop)


class PackageBuilder:
    def __init__(self, root):
        if os.path.exists(root):
            raise PackageError(f"{root} exists; packages are built once into a fresh directory")
        self.root = root
        self.files = {}
        os.makedirs(root)

    def _record(self, rel, data):
        rel = safe_rel(rel)
        if rel in self.files:
            raise PackageError(f"duplicate package path {rel}")
        dest = inside(self.root, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
        self.files[rel] = {"sha256": sha256_bytes(data), "bytes": len(data)}
        return self.files[rel]

    def add_file(self, src, rel, expected_sha256=None, expected_bytes=None):
        with open(src, "rb") as f:
            data = f.read()
        digest = sha256_bytes(data)
        if expected_sha256 is not None and digest != expected_sha256:
            raise PackageError(f"{src}: sha256 {digest} != recorded {expected_sha256}")
        if expected_bytes is not None and len(data) != expected_bytes:
            raise PackageError(f"{src}: {len(data)} bytes != recorded {expected_bytes}")
        rec = self._record(rel, data)
        rec["source"] = src
        return rec

    def add_bytes(self, rel, data):
        return self._record(rel, data)

    def add_json(self, rel, obj):
        return self._record(rel, (json.dumps(obj, indent=1, sort_keys=True, default=str) + "\n").encode())

    def finalize(self, meta):
        body = {"schema": PACKAGE_SCHEMA, "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **meta,
                "files": dict(sorted(self.files.items()))}
        body["content_sha256"] = sha256_bytes(json.dumps(
            {k: v["sha256"] for k, v in body["files"].items()}, sort_keys=True).encode())
        with open(os.path.join(self.root, "package.json"), "w") as f:
            json.dump(body, f, indent=1, sort_keys=True, default=str)
        return body


def verify_package(root):
    """Re-hash every listed file; return list of problems (empty == intact). Extra files are problems too."""
    meta = json.load(open(os.path.join(root, "package.json")))
    problems = []
    listed = set(meta["files"])
    for rel, rec in meta["files"].items():
        try:
            path = inside(root, rel)
        except PackageError as exc:
            problems.append(str(exc))
            continue
        if os.path.islink(os.path.join(root, rel)):
            problems.append(f"symlink {rel}")
        elif not os.path.isfile(path):
            problems.append(f"missing {rel}")
        elif sha256_file(path) != rec["sha256"] or os.path.getsize(path) != rec["bytes"]:
            problems.append(f"altered {rel}")
    for dirpath, _, names in os.walk(root):
        for name in names:
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            if rel != "package.json" and rel not in listed and "__pycache__" not in rel:
                problems.append(f"unlisted {rel}")
    return problems


def select_reference(frame, unit_col, boundary, key_cols, per_unit=32, cover_cols=(), per_cover=4):
    """Deterministic sample with at most ``per_unit`` rows per fitted unit.

    Within each unit's cap: first reserve coverage rows (up to ``per_cover``, at least one) for every
    value of each ``cover_cols`` column present in that unit (e.g. route), then half of the remaining
    slots nearest the documented decision boundary, then the rest by sha256 of the key columns.
    Null units are refused. ``boundary`` is a Series (aligned with frame) of boundary distances."""
    if frame[unit_col].isna().any():
        raise PackageError(f"{int(frame[unit_col].isna().sum())} rows have no {unit_col}")
    hashed = frame[key_cols].astype(str).agg("|".join, axis=1).map(lambda s: sha256_bytes(s.encode()))
    chosen = []
    for _, group in frame.groupby(unit_col, sort=True):
        if len(group) <= per_unit:
            chosen.extend(group.index)
            continue
        picked = []
        for col in cover_cols:
            values = sorted(group[col].astype(str).unique())
            quota = max(1, min(per_cover, per_unit // max(1, len(values) * len(cover_cols))))
            for v in values:
                idx = group.index[group[col].astype(str) == v]
                picked.extend(i for i in hashed.loc[idx].sort_values(kind="mergesort").index[:quota] if i not in picked)
        picked = picked[:per_unit]
        left = group.index.difference(picked)
        n_near = (per_unit - len(picked)) // 2
        near = list(boundary.loc[left].sort_values(kind="mergesort").index[:n_near])
        rest = hashed.loc[left.difference(near)].sort_values(kind="mergesort").index[: per_unit - len(picked) - len(near)]
        chosen.extend(picked + near + list(rest))
    return frame.loc[sorted(set(chosen))]
