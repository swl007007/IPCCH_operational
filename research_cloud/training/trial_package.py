"""Portable inference package for a pooled IPCCH quartet trial, in the historical GeoXGB package format.

Each fold's quartet is one unit (``weights/<unit>/q2..q5.ubj`` + ``record.json``), routed by its validation target
month for every admin (pooled: empty region map). The loader is the shared GeoXGB entry with the P6 ``quartet`` and
``projection`` modules vendored from the same source tree the trial imported; the reference sample is drawn from the
trial's own validation predictions, so ``research_cloud.packages.replay`` checks the package exactly as it checks
historical ones.
"""
import io
import json
import os

import numpy as np
import pandas as pd

from research_cloud.packages import geoxgb
from research_cloud.packages.common import PackageBuilder, select_reference, sha256_file

TARGETS = geoxgb.TARGETS


def build(out_dir, *, folds, keys, X, feature_order_path, geoxgb_src, identity, runtime, per_unit=32):
    """folds: [{"unit", "payloads": {q: bytes}, "record": dict, "validation_rows": idx, "raw", "star", "phase"}]."""
    b = PackageBuilder(out_dir)
    routing, refs = [], []
    for f in folds:
        for q in TARGETS:
            b.add_bytes(f"weights/{f['unit']}/{q}.ubj", f["payloads"][q])
        b.add_json(f"weights/{f['unit']}/record.json", f["record"])
        target = int(f["target_ord"])
        routing.append({"target_ord": target, "region": "", "unit": f["unit"], "route": "pooled_global"})
        frame = keys.iloc[f["validation_rows"]][["admin_code", "target_ord"]].reset_index(drop=True)
        frame["row"] = f["validation_rows"]
        frame["unit"], frame["route"] = f["unit"], "pooled_global"
        for j, q in enumerate(TARGETS):
            frame[f"{q}_raw"], frame[f"{q}_star"] = f["raw"][:, j], f["star"][:, j]
        frame["phase"] = f["phase"]
        refs.append(frame)
    b.add_bytes("deps/routing.csv", pd.DataFrame(routing).to_csv(index=False).encode())
    b.add_bytes("deps/frozen_map.csv", b"admin_code,node_id\n")   # pooled: every admin takes the "" region
    b.add_file(feature_order_path, "deps/feature_order.csv")
    served = pd.concat(refs, ignore_index=True)
    boundary = (served[[f"{q}_star" for q in TARGETS]] - 0.20).abs().min(axis=1)
    ref = select_reference(served, "unit", boundary, ["admin_code", "target_ord"], per_unit=per_unit, cover_cols=("route",))
    inputs = np.ascontiguousarray(np.asarray(X[ref["row"].to_numpy()], dtype=np.float64))
    buf = io.BytesIO()
    np.save(buf, inputs, allow_pickle=False)
    b.add_bytes("reference/inputs.npy", buf.getvalue())
    expected = ref[["admin_code", "target_ord", "route", "unit"] + [f"{q}_{k}" for q in TARGETS for k in ("raw", "star")] + ["phase"]]
    b.add_bytes("reference/expected.csv", expected.to_csv(index=False, float_format="%.17g").encode())
    pkg = os.path.join(geoxgb_src, "ipcch_geoxgb")
    b.add_bytes("loader/ipcch_geoxgb/__init__.py", b"")
    for name in geoxgb.LOADER_FILES:
        b.add_file(os.path.join(pkg, name), f"loader/ipcch_geoxgb/{name}")
    b.add_bytes("loader/entry.py", geoxgb.ENTRY.encode())
    n_features = len(pd.read_csv(feature_order_path))
    return b.finalize({
        "family": "ipcch_geoxgb_pooled_quartet_trial", "identity": identity, "lead_months": int(identity["horizon"]),
        "arm": "pooled", "status": "complete", "gaps": [], "fitted_units": len(folds),
        "routing": {"table": "deps/routing.csv", "frozen_map": "deps/frozen_map.csv", "feature_order": "deps/feature_order.csv",
                    "served_keys": int(len(served)), "routes_in_version": ["pooled_global"],
                    "rule": "each fold's quartet serves every admin of its validation target month"},
        "code": {"package": "ipcch_geoxgb", "vendored_from": pkg,
                 "vendored_files": {n: sha256_file(os.path.join(pkg, n)) for n in geoxgb.LOADER_FILES}},
        "runtime": {"linux": runtime},
        "loader": {"entry": "loader/entry.py", "call": "load(package_dir).predict(keys[admin_code,target_ord], X)",
                   "inputs": f"float64 rows ({n_features} features) in feature_order.csv order; NaN = missing",
                   "unserved_keys": "KeyError for target months that are not a fold's validation month"},
        "reference": {"rows": int(len(expected)), "per_unit_cap": per_unit, "routes_covered": ["pooled_global"],
                      "selection": "per fold unit (cap): half nearest a 0.20 boundary, rest by key hash"},
        "tolerance": {"declared_before_comparison": True,
                      "projected_shares": "abs(new-ref) <= 1e-3 + 1e-3*abs(ref)", "raw_shares": "abs(new-ref) <= 1e-3 + 1e-3*abs(ref)",
                      "phase": "new phase must decode from new projected shares", "routing": "unit and route exactly"},
    })
