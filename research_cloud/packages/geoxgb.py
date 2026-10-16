"""Package builder for the IPCCH GeoXGB reference (P6) registered versions.

A registered version is (lead, arm). The frozen run determines, for every
(admin_code, target_ord) key, which fitted quartet serves it:
- ``pooled``: the fold's global quartet (``global_identity``);
- ``partitioned_gated``: the area's frozen region (``stage1/frozen_map_hXX.csv``) and the
  fold's gate decision give ``provider`` (a local quartet, or the global on fallback /
  unmapped areas).
The package ships that resolution as ``deps/routing.csv`` (one row per (target_ord, region))
and a keyed loader that applies it, so callers pass keys + feature rows only.

Unit files ``models/<d[:2]>/<d>/{q2..q5.ubj,record.json}`` are copied with their recorded
member hashes. The loader code is vendored from the family run's MLflow ``source_code/``
artifact. Every Dropbox source path is classified before it is opened.
"""
import io
import json
import os

import numpy as np
import pandas as pd

from research_cloud.packages.common import (PackageBuilder, PackageError, ensure_local, select_reference,
                                            sha256_file)

TARGETS = ("q2", "q3", "q4", "q5")
ARMS = {"pooled": ("global_identity", "pool_"), "partitioned_gated": ("provider", "geo_")}
LOADER_FILES = ("errors.py", "quartet.py", "projection.py")

ENTRY = '''"""Keyed loader for one historical IPCCH GeoXGB package (generated; see package.json)."""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ipcch_geoxgb import projection, quartet  # vendored from the run's source_code artifact


class Model:
    def __init__(self, package_dir=ROOT):
        self.root = package_dir
        self.meta = json.load(open(os.path.join(package_dir, "package.json")))
        self.lead = int(self.meta["lead_months"])
        self.unit_col = self.meta["routing"]["unit_column"]
        regions = pd.read_csv(os.path.join(package_dir, "deps", "stage1", "frozen_map_h%02d.csv" % self.lead))
        self.region_of = dict(zip(regions["admin_code"].astype(int), regions["node_id"].astype(str)))
        routes = pd.read_csv(os.path.join(package_dir, "deps", "routing.csv"), dtype={"region": str}, keep_default_na=False)
        self.routes = {(int(t), r): row for t, r, row in zip(routes["target_ord"], routes["region"], routes.to_dict("records"))}
        self._units = {}

    def unit(self, digest):
        """Low-level: the quartet for one fitted unit."""
        if digest not in self._units:
            base = os.path.join(self.root, "weights", digest)
            record = json.load(open(os.path.join(base, "record.json")))
            boosters = {q: open(os.path.join(base, q + ".ubj"), "rb").read() for q in quartet.TARGETS}
            self._units[digest] = quartet.Quartet(boosters, record["fit_records"])
        return self._units[digest]

    def resolve(self, keys):
        """Frozen (unit, route) for each (admin_code, target_ord); unknown keys are errors."""
        out = []
        for a, t in zip(keys["admin_code"].astype(int), keys["target_ord"].astype(int)):
            route = self.routes.get((t, self.region_of.get(a, "")))
            if route is None:
                raise KeyError(f"no frozen route for admin_code={a} target_ord={t} in this package")
            out.append((route[self.unit_col], route["route"] if self.unit_col == "provider" else "pooled_global"))
        return out

    def predict(self, keys, X):
        """Keyed prediction. keys: DataFrame[admin_code, target_ord]; X: (n, 561) float64 rows in
        deps/prepared/feature_order.csv order, NaN = missing. Returns a DataFrame per row."""
        X = np.asarray(X, dtype=np.float64)
        if len(X) != len(keys):
            raise ValueError("keys and X differ in length")
        resolved = self.resolve(keys)
        raw = np.zeros((len(X), 4)); star = np.zeros((len(X), 4)); phase = np.zeros(len(X), dtype=np.int64)
        units = np.array([u for u, _ in resolved], dtype=object)
        for u in sorted(set(units)):
            idx = np.flatnonzero(units == u)
            raw[idx] = self.unit(u).predict_raw(X[idx])
            star[idx], phase[idx] = projection.project_and_decode(raw[idx])
        out = pd.DataFrame({"admin_code": keys["admin_code"].to_numpy(), "target_ord": keys["target_ord"].to_numpy(),
                            "unit": units, "route": [r for _, r in resolved]})
        for j, q in enumerate(quartet.TARGETS):
            out[q + "_raw"], out[q + "_star"] = raw[:, j], star[:, j]
        out["phase"] = phase
        return out


def load(package_dir=ROOT):
    return Model(package_dir)
'''


def _members(manifest_path):
    return {m["path"]: m for m in json.load(open(manifest_path))}


def _routing(pred, region_of, lead):
    pred = pred.assign(region=pred["region"].fillna("").astype(str))
    if ((pred["target_ord"] - pred["origin_ord"]) != lead).any():
        raise PackageError("origin is not target - H for some rows")
    mapped = pred["admin_code"].astype(int).map(lambda a: region_of.get(a, ""))
    if not (mapped == pred["region"]).all():
        raise PackageError("frozen map disagrees with the saved prediction regions")
    cols = ["target_ord", "region", "fold_id", "origin_ord", "route", "provider", "global_identity"]
    routing = pred[cols].drop_duplicates()
    if routing.duplicated(["target_ord", "region"]).any():
        raise PackageError("a (target_ord, region) has more than one frozen route")
    return routing.sort_values(["target_ord", "region"])


def build(out_dir, *, run_root, source_code_dir, members_manifest, version, lead, arm, code_identity,
          original_runtime, linux_runtime, per_unit=32):
    if arm not in ARMS:
        raise PackageError(f"unknown arm {arm}")
    unit_col, prefix = ARMS[arm]
    h = f"h{int(lead):02d}"
    members = _members(members_manifest)
    deps = ["prepared/feature_order.csv", f"stage1/frozen_map_{h}.csv", f"stage1/frozen_{h}.json",
            f"stage3/{h}/gate_decisions.jsonl", f"stage3/{h}/fold_ledger.csv", f"stage3/{h}/predictions.csv.gz"]
    pred_path = os.path.join(run_root, "stage3", h, "predictions.csv.gz")
    keys_path = os.path.join(run_root, "prepared", f"keys_{h}.csv.gz")
    x_path = os.path.join(run_root, "prepared", f"X_rich561_{h}.npy")
    ensure_local([pred_path, keys_path, x_path] + [os.path.join(run_root, d) for d in deps])

    pred = pd.read_csv(pred_path)
    keys = pd.read_csv(keys_path)
    X = np.load(x_path, mmap_mode="r")
    if len(keys) != len(X) or keys.duplicated(["admin_code", "target_ord"]).any():
        raise PackageError("keys/X misaligned or non-unique (admin_code, target_ord)")
    frozen = pd.read_csv(os.path.join(run_root, "stage1", f"frozen_map_{h}.csv"))
    routing = _routing(pred, dict(zip(frozen["admin_code"].astype(int), frozen["node_id"].astype(str))), int(lead))

    units = sorted(pred[unit_col].dropna().unique())
    unit_files = [(d, n) for d in units for n in [q + ".ubj" for q in TARGETS] + ["record.json"]]
    ensure_local([os.path.join(run_root, f"models/{d[:2]}/{d}/{n}") for d, n in unit_files])
    b = PackageBuilder(out_dir)
    gaps = []
    for d, name in unit_files:
        rel = f"models/{d[:2]}/{d}/{name}"
        m = members.get(rel)
        if m is None:
            gaps.append(f"unit {d} file {name} not in the member manifest")
            continue
        b.add_file(os.path.join(run_root, rel), f"weights/{d}/{name}", m["sha256"], m["bytes"])
    for rel in deps:
        b.add_file(os.path.join(run_root, rel), "deps/" + rel)
    b.add_bytes("deps/routing.csv", routing.to_csv(index=False).encode())

    star_cols = [f"{prefix}{q}_star" for q in TARGETS]
    boundary = (pred[star_cols] - 0.20).abs().min(axis=1)
    cover = ("route",) if arm == "partitioned_gated" else ()
    ref = select_reference(pred, unit_col, boundary, ["admin_code", "target_ord"], per_unit=per_unit, cover_cols=cover)
    row_of = pd.Series(np.arange(len(keys)), index=pd.MultiIndex.from_frame(keys[["admin_code", "target_ord"]]))
    rows = row_of.loc[list(zip(ref["admin_code"], ref["target_ord"]))].to_numpy()
    inputs = np.ascontiguousarray(X[rows], dtype=np.float64)
    buf = io.BytesIO()
    np.save(buf, inputs, allow_pickle=False)
    b.add_bytes("reference/inputs.npy", buf.getvalue())
    expected = ref[["admin_code", "target_ord", "fold_id", "route", unit_col]].rename(columns={unit_col: "unit"}).copy()
    for q in TARGETS:
        expected[f"{q}_raw"] = ref[f"{prefix}{q}_raw"].to_numpy()
        expected[f"{q}_star"] = ref[f"{prefix}{q}_star"].to_numpy()
    expected["phase"] = ref[f"{prefix}phase"].to_numpy()
    if arm == "pooled":
        expected["route"] = "pooled_global"
    b.add_bytes("reference/expected.csv", expected.to_csv(index=False, float_format="%.17g").encode())

    src_pkg = os.path.join(source_code_dir, "ipcch_geoxgb")
    b.add_bytes("loader/ipcch_geoxgb/__init__.py", b"")
    for name in LOADER_FILES:
        b.add_file(os.path.join(src_pkg, name), f"loader/ipcch_geoxgb/{name}")
    b.add_bytes("loader/entry.py", ENTRY.encode())

    raw_cols = [f"{prefix}{q}_raw" for q in TARGETS]
    return b.finalize({
        "family": "geoxgb_reference",
        "identity": version,
        "lead_months": int(lead), "arm": arm,
        "status": "complete" if not gaps else "retained_weights_missing_dependencies",
        "gaps": gaps,
        "fitted_units": len(units),
        "routing": {"unit_column": unit_col, "table": "deps/routing.csv",
                    "routes_in_version": sorted(pred["route"].unique()) if arm == "partitioned_gated" else ["pooled_global"]},
        "source": {"run_root": run_root, "members_manifest": members_manifest,
                   "members_manifest_sha256": sha256_file(members_manifest),
                   "predictions_sha256": sha256_file(pred_path)},
        "code": {"identity": code_identity, "vendored_from": src_pkg,
                 "vendored_files": {n: sha256_file(os.path.join(src_pkg, n)) for n in LOADER_FILES}},
        "runtime": {"original": original_runtime, "linux": linux_runtime},
        "loader": {"entry": "loader/entry.py",
                   "call": "load(package_dir).predict(keys[admin_code,target_ord], X)",
                   "inputs": "float64 rows in deps/prepared/feature_order.csv order; NaN = missing"},
        "reference": {"rows": int(len(expected)), "per_unit_cap": per_unit,
                      "selection": "per fitted unit: half nearest a 0.20 phase boundary, rest by sha256 of (admin_code,target_ord); plus >=4 rows of every route",
                      "rows_with_missing_features": int(np.isnan(inputs).any(axis=1).sum()),
                      "routes_covered": sorted(expected["route"].unique()),
                      "raw_range_in_sample": [float(ref[raw_cols].min().min()), float(ref[raw_cols].max().max())]},
        "tolerance": {
            "declared_before_comparison": True,
            "projected_shares": "abs(new-ref) <= 1e-3 + 1e-3*abs(ref) (design.md approved contract, values in [0,1])",
            "raw_shares": "abs(new-ref) <= 1e-3 + 1e-3*abs(ref); raw quartet outputs are unbounded regression values "
                          "(sample range recorded above), so the relative term scales with |ref|",
            "phase": "change allowed only where each changed threshold crossing has |ref_star-0.20| within tolerance and continuous outputs pass",
            "routing": "resolved unit and route must equal the frozen reference exactly"},
    })
