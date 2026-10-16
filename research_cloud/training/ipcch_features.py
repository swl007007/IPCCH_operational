"""IPCCH rich561 feature snapshot from base inputs (new Linux research step; feeds ipcch_quartet trials).

Generates one horizon's prepared bundle from the hashed base inputs (raw ``IPCCH_2026_completed.csv`` panel and the
country lookup) with the P6 low-level builders vendored from P6's ``source_code`` artifact: ``targets.build_target_ledger``
-> ``valid_targets``; ``features.load_covariate_panel`` -> ``build_panel_grid``; ``build_history_index`` over the full
valid ledger; ``prepare.build_horizon`` (original93 + history468 in the frozen schema order, each row at its own
origin O = T - H). P6's ``run_prepare`` Windows/runtime guards are not used and not changed.

Output: ``keys_hHH.csv.gz``, ``X_rich561_hHH.npy``, ``feature_order.csv``, ``audit.json`` and ``manifest.json``
(sha256 of each file; directly usable as a trial input manifest). ``--compare`` takes a manifest of an existing
prepared bundle (e.g. P6's) and records whether keys and X are identical (NaN positions included).

  python -m research_cloud.training.ipcch_features --manifest BASE.json --horizon 3 --output DIR [--compare P6.json]
"""
import argparse
import gzip
import importlib
import json
import os
import sys
import time

import numpy as np
import pandas as pd

from research_cloud.training.common import TrialError, resolve_inputs, runtime_identity, sha256_file

HORIZONS = {1, 3, 6, 12}


def modules(src):
    if src not in sys.path:
        sys.path.insert(0, src)
    names = ("targets", "features", "prepare", "geography", "contract", "artifacts")
    return {n: importlib.import_module(f"ipcch_geoxgb.{n}") for n in names}


def build(inputs, horizon, src):
    m = modules(src)
    schema = m["contract"].load_feature_schema()
    feat = m["features"]
    if tuple(schema["original_features"]) != feat.ORIGINAL_FEATURES:
        raise TrialError("original93 implementation order differs from the frozen feature schema")
    ledger = m["targets"].build_target_ledger(inputs["raw_panel"])
    valid = m["targets"].valid_targets(ledger)
    lookup, _ = m["geography"].load_country_lookup(inputs["country_lookup"])
    country = dict(zip(lookup["area_id"].tolist(), lookup["country_key"].tolist()))
    missing = sorted(set(valid["admin_code"].tolist()) - set(country))
    if missing:
        raise TrialError(f"{len(missing)} areas with valid outcomes lack a country key")
    panel, _ = feat.load_covariate_panel(inputs["raw_panel"])
    grid = feat.build_panel_grid(panel)
    index = feat.build_history_index(valid)
    X, keys, audit = m["prepare"].build_horizon(valid, panel, grid, index, schema, int(horizon), country)
    return X, keys, audit, schema


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, help="base inputs: raw_panel, country_lookup")
    ap.add_argument("--horizon", type=int, required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--geoxgb-src", default=os.environ.get("IPCCH_GEOXGB_SRC"))
    ap.add_argument("--compare")
    args = ap.parse_args(argv)
    if args.horizon not in HORIZONS:
        raise SystemExit(f"horizon must be one of {sorted(HORIZONS)} (H0 would read contemporaneous labels)")
    if os.path.exists(args.output):
        raise SystemExit(f"{args.output} exists; snapshots are written once")
    os.makedirs(args.output)
    t0 = time.time()
    inputs, manifest = resolve_inputs(args.manifest, args.output)
    X, keys, audit, schema = build(inputs, args.horizon, args.geoxgb_src)
    hh = f"h{args.horizon:02d}"
    names = {"keys": f"keys_{hh}.csv.gz", "X": f"X_rich561_{hh}.npy", "feature_order": "feature_order.csv"}
    out = {k: os.path.join(args.output, v) for k, v in names.items()}
    with gzip.GzipFile(out["keys"], "wb", mtime=0) as f:   # deterministic bytes, as P6 writes them
        f.write(keys.to_csv(index=False, lineterminator="\n").encode())
    np.save(out["X"], X)
    pd.DataFrame({"name": schema["ordered_names"]}).to_csv(out["feature_order"], index=False, lineterminator="\n")
    snapshot = {"name": f"ipcch-rich561-{hh}-linux", "gcp_project": manifest.get("gcp_project"),
                "derived_from": {"base_manifest": os.path.abspath(args.manifest), "base_manifest_sha256": sha256_file(args.manifest),
                                 "base_inputs": {r: e["sha256"] for r, e in manifest["files"].items()}},
                "files": {k: {"uri": os.path.abspath(p), "sha256": sha256_file(p)} for k, p in out.items()}}
    comparison = None
    if args.compare:
        ref, _ = resolve_inputs(args.compare, args.output)
        rk = pd.read_csv(ref["keys"])
        rx = np.load(ref["X"], mmap_mode="r")
        same_keys = rk.shape == keys.shape and all(
            np.array_equal(rk[c].to_numpy(), keys[c].to_numpy(), equal_nan=True) for c in ("admin_code", "target_ord", "origin_ord"))
        same_x = rx.shape == X.shape and np.array_equal(np.asarray(rx), X, equal_nan=True)
        comparison = {"reference": os.path.abspath(args.compare), "keys_identical": bool(same_keys), "X_identical": bool(same_x),
                      "X_sha256_equal": snapshot["files"]["X"]["sha256"] == sha256_file(ref["X"]),
                      "shape": list(X.shape), "reference_shape": list(rx.shape)}
        if not same_x and rx.shape == X.shape:
            diff = ~((np.asarray(rx) == X) | (np.isnan(rx) & np.isnan(X)))
            comparison.update(differing_cells=int(diff.sum()), differing_columns=int(diff.any(axis=0).sum()))
    with open(os.path.join(args.output, "audit.json"), "w") as f:
        json.dump({"horizon": args.horizon, "rows": int(len(keys)), "audit": audit, "comparison": comparison,
                   "runtime": runtime_identity(), "seconds": round(time.time() - t0, 1)}, f, indent=1, default=str)
    with open(os.path.join(args.output, "manifest.json"), "w") as f:
        json.dump(snapshot, f, indent=1)
    print(json.dumps({"rows": int(len(keys)), "shape": list(X.shape), "comparison": comparison, "seconds": round(time.time() - t0, 1)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
