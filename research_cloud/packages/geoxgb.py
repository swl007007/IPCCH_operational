"""Package builder for IPCCH GeoXGB registered versions (P6 reference and yearly refit).

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
LOADER_FILES = ("errors.py", "quartet.py", "projection.py")
REQUIRED_UNIT_FILES = ("q2.ubj", "q3.ubj", "q4.ubj", "q5.ubj", "record.json")


def _p6_pooled(p):
    return p["global_identity"], pd.Series("pooled_global", index=p.index), "pool_", pd.Series(True, index=p.index)


def _p6_gated(p):
    return p["provider"], p["route"], "geo_", pd.Series(True, index=p.index)


def _yr_pooled(p):
    return p["pool_provider"], pd.Series("pooled_global", index=p.index), "pool_", pd.Series(True, index=p.index)


def _yr_gated(p):
    unit = p["local_provider"].where(p["route"] == "local", p["pool_provider"])
    return unit, p["route"], "geo_", pd.Series(True, index=p.index)


def _yr_ungated(p):
    served = p["local_provider"].fillna("").astype(str) != ""
    return p["local_provider"], pd.Series("regional_local_ungated", index=p.index), "local_", served


FAMILIES = {
    "geoxgb_reference": {
        "package": "ipcch_geoxgb", "predictions": "stage3/{h}/predictions.csv.gz",
        "keys": "prepared/keys_{h}.csv.gz", "X": "prepared/X_rich561_{h}.npy",
        "feature_order": "prepared/feature_order.csv", "frozen_map": "stage1/frozen_map_{h}.csv",
        "deps": ["stage1/frozen_{h}.json", "stage3/{h}/gate_decisions.jsonl", "stage3/{h}/fold_ledger.csv"],
        "arms": {"pooled": _p6_pooled, "partitioned_gated": _p6_gated}},
    "geoxgb_yearly_refit": {
        "package": "ipcch_yearly_xgb", "predictions": "predict/{h}/predictions.csv.gz",
        "keys": "inputs/run/prepared/keys_{h}.csv.gz", "X": "inputs/run/prepared/X_rich561_{h}.npy",
        "feature_order": "inputs/run/prepared/feature_order.csv", "frozen_map": "inputs/run/stage1/frozen_map_{h}.csv",
        "deps": ["inputs/run/stage1/frozen_{h}.json", "predict/{h}/gate_decisions.jsonl", "predict/{h}/fold_ledger.csv",
                 "predict/{h}/block_ledger.json"],
        "arms": {"pooled": _yr_pooled, "partitioned_gated": _yr_gated, "regional_ungated": _yr_ungated}},
}


ENTRY = '''"""Keyed loader for one historical IPCCH GeoXGB package (generated; see package.json)."""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import importlib
_META = json.load(open(os.path.join(ROOT, "package.json")))
projection = importlib.import_module(_META["code"]["package"] + ".projection")  # vendored from the run's
quartet = importlib.import_module(_META["code"]["package"] + ".quartet")        # source_code artifact


class Model:
    def __init__(self, package_dir=ROOT):
        self.root = package_dir
        self.meta = json.load(open(os.path.join(package_dir, "package.json")))
        self.lead = int(self.meta["lead_months"])
        regions = pd.read_csv(os.path.join(package_dir, self.meta["routing"]["frozen_map"]))
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
                raise KeyError(f"no frozen route/model for admin_code={a} target_ord={t} in this package's arm")
            out.append((route["unit"], route["route"]))
        return out

    def predict(self, keys, X):
        """Keyed prediction. keys: DataFrame[admin_code, target_ord]; X: (n, 561) float64 rows in
        the package's feature_order.csv order, NaN = missing. Returns a DataFrame per row."""
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


def _routing(served, unit, route, region_of, lead):
    frame = served.assign(region=served["region"].fillna("").astype(str), unit=unit, route_out=route)
    if "origin_ord" in frame and ((frame["target_ord"] - frame["origin_ord"]) != lead).any():
        raise PackageError("origin is not target - H for some rows")
    mapped = frame["admin_code"].astype(int).map(lambda a: region_of.get(a, ""))
    if not (mapped == frame["region"]).all():
        raise PackageError("frozen map disagrees with the saved prediction regions")
    routing = frame[["target_ord", "region", "unit", "route_out"]].drop_duplicates().rename(columns={"route_out": "route"})
    if routing.duplicated(["target_ord", "region"]).any():
        raise PackageError("a (target_ord, region) has more than one frozen unit/route")
    return routing.sort_values(["target_ord", "region"])


def build(out_dir, *, family, run_root, source_code_dir, members_manifest, version, lead, arm, code_identity,
          original_runtime, linux_runtime, per_unit=32):
    spec = FAMILIES[family]
    if arm not in spec["arms"]:
        raise PackageError(f"unknown arm {arm} for {family}")
    h = f"h{int(lead):02d}"
    rel = {k: spec[k].format(h=h) for k in ("predictions", "keys", "X", "feature_order", "frozen_map")}
    deps = [rel["feature_order"], rel["frozen_map"], rel["predictions"]] + [d.format(h=h) for d in spec["deps"]]
    ensure_local([os.path.join(run_root, r) for r in [rel["keys"], rel["X"]] + deps])
    members = _members(members_manifest)

    pred = pd.read_csv(os.path.join(run_root, rel["predictions"]), dtype={"local_provider": str, "provider": str})
    keys = pd.read_csv(os.path.join(run_root, rel["keys"]))
    X = np.load(os.path.join(run_root, rel["X"]), mmap_mode="r")
    if len(keys) != len(X) or keys.duplicated(["admin_code", "target_ord"]).any():
        raise PackageError("keys/X misaligned or non-unique (admin_code, target_ord)")
    n_features = len(pd.read_csv(os.path.join(run_root, rel["feature_order"])))
    if X.shape[1] != n_features:
        raise PackageError(f"X has {X.shape[1]} columns but feature_order lists {n_features}")
    unit, route, prefix, served = spec["arms"][arm](pred)
    served_pred = pred[served.to_numpy()].copy()
    unit, route = unit[served.to_numpy()], route[served.to_numpy()]
    frozen = pd.read_csv(os.path.join(run_root, rel["frozen_map"]))
    routing = _routing(served_pred, unit, route, dict(zip(frozen["admin_code"].astype(int), frozen["node_id"].astype(str))),
                       int(lead))

    units = sorted(unit.dropna().unique())
    unit_files = sorted(m for m in members if any(m.startswith(f"models/{d[:2]}/{d}/") for d in units))
    gaps = []
    for d in units:  # required inference components of every served quartet
        for name in REQUIRED_UNIT_FILES:
            if f"models/{d[:2]}/{d}/{name}" not in members:
                gaps.append(f"unit {d}: required member {name} absent from the member manifest")
    ensure_local([os.path.join(run_root, m) for m in unit_files])
    b = PackageBuilder(out_dir)
    for m in unit_files:
        b.add_file(os.path.join(run_root, m), "weights/" + "/".join(m.split("/")[2:]), members[m]["sha256"], members[m]["bytes"])
    for d in units:
        record_path = os.path.join(out_dir, "weights", d, "record.json")
        if not os.path.exists(record_path):
            continue
        record = json.load(open(record_path))
        for q in TARGETS:
            booster = os.path.join(out_dir, "weights", d, f"{q}.ubj")
            if not os.path.exists(booster):
                continue
            if record.get("booster_sha256", {}).get(q) != b.files[f"weights/{d}/{q}.ubj"]["sha256"]:
                gaps.append(f"unit {d}: {q}.ubj bytes differ from record.json booster_sha256")
            if q not in record.get("fit_records", {}):
                gaps.append(f"unit {d}: record.json has no fit record for {q}")
    for r in deps:
        b.add_file(os.path.join(run_root, r), "deps/" + r)
    b.add_bytes("deps/routing.csv", routing.to_csv(index=False).encode())

    served_pred["unit"], served_pred["route_out"] = unit.to_numpy(), route.to_numpy()
    star_cols = [f"{prefix}{q}_star" for q in TARGETS]
    boundary = (served_pred[star_cols] - 0.20).abs().min(axis=1)
    ref = select_reference(served_pred, "unit", boundary, ["admin_code", "target_ord"], per_unit=per_unit,
                           cover_cols=("route_out",))
    row_of = pd.Series(np.arange(len(keys)), index=pd.MultiIndex.from_frame(keys[["admin_code", "target_ord"]]))
    rows = row_of.loc[list(zip(ref["admin_code"], ref["target_ord"]))].to_numpy()
    inputs = np.ascontiguousarray(X[rows], dtype=np.float64)
    buf = io.BytesIO()
    np.save(buf, inputs, allow_pickle=False)
    b.add_bytes("reference/inputs.npy", buf.getvalue())
    expected = ref[["admin_code", "target_ord", "fold_id", "route_out", "unit"]].rename(columns={"route_out": "route"}).copy()
    for q in TARGETS:
        expected[f"{q}_raw"] = ref[f"{prefix}{q}_raw"].to_numpy()
        expected[f"{q}_star"] = ref[f"{prefix}{q}_star"].to_numpy()
    expected["phase"] = ref[f"{prefix}phase"].to_numpy()
    b.add_bytes("reference/expected.csv", expected.to_csv(index=False, float_format="%.17g").encode())

    src_pkg = os.path.join(source_code_dir, spec["package"])
    b.add_bytes(f"loader/{spec['package']}/__init__.py", b"")
    for name in LOADER_FILES:
        b.add_file(os.path.join(src_pkg, name), f"loader/{spec['package']}/{name}")
    b.add_bytes("loader/entry.py", ENTRY.encode())

    raw_cols = [f"{prefix}{q}_raw" for q in TARGETS]
    return b.finalize({
        "family": family,
        "identity": version,
        "lead_months": int(lead), "arm": arm,
        "status": "complete" if not gaps else "retained_weights_missing_dependencies",
        "gaps": gaps,
        "fitted_units": len(units),
        "routing": {"table": "deps/routing.csv", "frozen_map": "deps/" + rel["frozen_map"],
                    "feature_order": "deps/" + rel["feature_order"],
                    "served_keys": int(served.sum()), "unserved_keys_in_saved_predictions": int((~served).sum()),
                    "routes_in_version": sorted(route.unique())},
        "source": {"run_root": run_root, "members_manifest": members_manifest,
                   "members_manifest_sha256": sha256_file(members_manifest),
                   "predictions_sha256": sha256_file(os.path.join(run_root, rel["predictions"]))},
        "code": {"identity": code_identity, "package": spec["package"], "vendored_from": src_pkg,
                 "vendored_files": {n: sha256_file(os.path.join(src_pkg, n)) for n in LOADER_FILES}},
        "runtime": {"original": original_runtime, "linux": linux_runtime},
        "loader": {"entry": "loader/entry.py",
                   "call": "load(package_dir).predict(keys[admin_code,target_ord], X)",
                   "inputs": f"float64 rows ({n_features} features) in the routing.feature_order order; NaN = missing",
                   "unserved_keys": "KeyError (no frozen model for that key in this arm)"},
        "reference": {"rows": int(len(expected)), "per_unit_cap": per_unit,
                      "selection": "per fitted unit (cap): >=1 row of every route present in the unit, half the rest nearest a 0.20 phase boundary, rest by sha256 of (admin_code,target_ord)",
                      "rows_with_missing_features": int(np.isnan(inputs).any(axis=1).sum()),
                      "routes_covered": sorted(expected["route"].unique()),
                      "raw_range_in_sample": [float(ref[raw_cols].min().min()), float(ref[raw_cols].max().max())]},
        "tolerance": {
            "declared_before_comparison": True,
            "projected_shares": "abs(new-ref) <= 1e-3 + 1e-3*abs(ref) (design.md approved contract, values in [0,1])",
            "raw_shares": "abs(new-ref) <= 1e-3 + 1e-3*abs(ref); raw quartet outputs are unbounded regression values "
                          "(sample range recorded above), so the relative term scales with |ref|",
            "phase": "new phase must decode from new projected shares; a change is accepted only where each changed crossing has |ref_star-0.20| within that reference's tolerance and all continuous outputs pass",
            "routing": "resolved unit and route must equal the frozen reference exactly"},
    })
