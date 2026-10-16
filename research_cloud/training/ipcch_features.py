"""IPCCH rich561 feature snapshot from base inputs (new Linux research step; feeds ipcch_quartet trials).

Generates one horizon's prepared bundle from the hashed base inputs (raw ``IPCCH_2026_completed.csv`` panel and the
country lookup) with the P6 low-level builders vendored from P6's ``source_code`` artifact: ``targets.build_target_ledger``
-> ``valid_targets``; ``features.load_covariate_panel`` -> ``build_panel_grid``; ``build_history_index`` over the full
valid ledger; ``prepare.build_horizon`` (original93 + history468 in the frozen schema order, each row at its own
origin O = T - H). P6's ``run_prepare`` Windows/runtime guards are not used and not changed.

Output: ``keys_hHH.csv.gz``, ``X_rich561_hHH.npy``, ``feature_order.csv``, ``audit.json`` and ``manifest.json``
(sha256 of each file; directly usable as a trial input manifest). ``--compare`` takes a manifest of an existing
prepared bundle (e.g. P6's) and compares the two saved bundles: keys by decompressed bytes, X by the loaded arrays
(NaN positions included). ``--compare-only DIR`` re-runs that comparison for an existing snapshot without rebuilding
it and writes ``DIR/comparison.json``.

  python -m research_cloud.training.ipcch_features --manifest BASE.json --horizon 3 --output DIR [--compare P6.json]
  python -m research_cloud.training.ipcch_features --compare-only DIR --compare P6.json
"""
import argparse
import gzip
import hashlib
import importlib
import json
import os
import sys
import time

import numpy as np
import pandas as pd

from research_cloud.training.common import TrialError, adapter_identity, resolve_inputs, runtime_identity, sha256_file

HORIZONS = {1, 3, 6, 12}


def modules(src):
    if src not in sys.path:
        sys.path.insert(0, src)
    names = ("targets", "features", "prepare", "geography", "contract", "artifacts")
    return {n: importlib.import_module(f"ipcch_geoxgb.{n}") for n in names}


def source_identity(mods, src):
    """sha256 of every builder module actually imported, plus the frozen schema/contract files they read."""
    files = {f"ipcch_geoxgb/{os.path.basename(m.__file__)}": sha256_file(m.__file__) for m in mods.values()}
    for name in ("feature-schema.json", "experiment-contract.json", "inputs.json"):
        path = os.path.join(src, "config", name)
        if os.path.exists(path):
            files[f"config/{name}"] = sha256_file(path)
    return {"geoxgb_src": os.path.abspath(src), "files": dict(sorted(files.items())),
            "adapter": adapter_identity("research_cloud.training.ipcch_features", "research_cloud.training.common")}


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
    return X, keys, audit, schema, source_identity(m, src)


def keys_bytes(path):
    with gzip.open(path, "rb") as f:
        return f.read()


def compare_saved(saved, reference_manifest, workdir):
    """Compare the two SAVED bundles (never the in-memory frames): keys by decompressed bytes, then per column of
    the re-read CSVs when the bytes differ; X by the loaded arrays (NaN positions included)."""
    ref, _ = resolve_inputs(reference_manifest, workdir)
    a_bytes, b_bytes = keys_bytes(saved["keys"]), keys_bytes(ref["keys"])
    keys_identical = a_bytes == b_bytes
    differing_key_columns = []
    if not keys_identical:
        a, b = pd.read_csv(saved["keys"]), pd.read_csv(ref["keys"])
        differing_key_columns = sorted(set(a.columns) ^ set(b.columns))
        if len(a) != len(b):
            differing_key_columns.append("<row count>")
        else:
            differing_key_columns += [c for c in a.columns if c in b.columns
                                      and a[c].astype(str).tolist() != b[c].astype(str).tolist()]
    x, rx = np.load(saved["X"], mmap_mode="r"), np.load(ref["X"], mmap_mode="r")
    comparison = {"reference": os.path.abspath(reference_manifest), "compared": "saved artifacts on both sides",
                  "keys_identical": keys_identical,
                  "keys_decompressed_sha256": hashlib.sha256(a_bytes).hexdigest(),
                  "reference_keys_decompressed_sha256": hashlib.sha256(b_bytes).hexdigest(),
                  "differing_key_columns": differing_key_columns,
                  "X_sha256_equal": sha256_file(saved["X"]) == sha256_file(ref["X"]),
                  "shape": list(x.shape), "reference_shape": list(rx.shape)}
    same_shape = x.shape == rx.shape
    comparison["X_identical"] = bool(same_shape and np.array_equal(np.asarray(x), np.asarray(rx), equal_nan=True))
    if same_shape and not comparison["X_identical"]:
        x, rx = np.asarray(x, dtype=np.float64), np.asarray(rx, dtype=np.float64)
        nan_a, nan_b = np.isnan(x), np.isnan(rx)
        diff = ~((x == rx) | (nan_a & nan_b))
        both = diff & ~nan_a & ~nan_b
        abs_err = np.abs(x[both] - rx[both])
        comparison.update(differing_cells=int(diff.sum()), differing_columns=int(diff.any(axis=0).sum()),
                          nan_pattern_differs=bool((nan_a != nan_b).any()),
                          max_abs_diff=float(abs_err.max()) if abs_err.size else 0.0,
                          max_rel_diff=float((abs_err / np.maximum(np.abs(rx[both]), np.finfo(float).tiny)).max()) if abs_err.size else 0.0)
    return comparison


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", help="base inputs: raw_panel, country_lookup")
    ap.add_argument("--horizon", type=int)
    ap.add_argument("--output")
    ap.add_argument("--geoxgb-src", default=os.environ.get("IPCCH_GEOXGB_SRC"))
    ap.add_argument("--compare")
    ap.add_argument("--compare-only", metavar="DIR", help="compare an existing snapshot's saved files; no rebuild")
    args = ap.parse_args(argv)
    if args.compare_only:
        if not args.compare:
            raise SystemExit("--compare-only needs --compare")
        files = json.load(open(os.path.join(args.compare_only, "manifest.json")))["files"]
        for role, entry in files.items():
            if sha256_file(entry["uri"]) != entry["sha256"]:
                raise SystemExit(f"{role}: saved file no longer matches the snapshot manifest")
        comparison = compare_saved({r: e["uri"] for r, e in files.items()}, args.compare, args.compare_only)
        with open(os.path.join(args.compare_only, "comparison.json"), "w") as f:
            json.dump(comparison, f, indent=1)
        print(json.dumps(comparison))
        return 0
    if not (args.manifest and args.horizon is not None and args.output):
        raise SystemExit("--manifest, --horizon and --output are required to build a snapshot")
    if args.horizon not in HORIZONS:
        raise SystemExit(f"horizon must be one of {sorted(HORIZONS)} (H0 would read contemporaneous labels)")
    if os.path.exists(args.output):
        raise SystemExit(f"{args.output} exists; snapshots are written once")
    os.makedirs(args.output)
    t0 = time.time()
    inputs, manifest = resolve_inputs(args.manifest, args.output)
    X, keys, audit, schema, code = build(inputs, args.horizon, args.geoxgb_src)
    hh = f"h{args.horizon:02d}"
    names = {"keys": f"keys_{hh}.csv.gz", "X": f"X_rich561_{hh}.npy", "feature_order": "feature_order.csv"}
    out = {k: os.path.join(args.output, v) for k, v in names.items()}
    with gzip.GzipFile(out["keys"], "wb", mtime=0) as f:   # deterministic bytes, as P6 writes them
        f.write(keys.to_csv(index=False, lineterminator="\n").encode())
    np.save(out["X"], X)
    pd.DataFrame({"name": schema["ordered_names"]}).to_csv(out["feature_order"], index=False, lineterminator="\n")
    snapshot = {"name": f"ipcch-rich561-{hh}-linux", "gcp_project": manifest.get("gcp_project"),
                "derived_from": {"base_manifest": os.path.abspath(args.manifest), "base_manifest_sha256": sha256_file(args.manifest),
                                 "base_inputs": {r: e["sha256"] for r, e in manifest["files"].items()},
                                 "builder_code": code, "horizon": args.horizon,
                                 "recipe": "targets.build_target_ledger -> valid_targets; features.load_covariate_panel -> "
                                           "build_panel_grid; build_history_index; prepare.build_horizon"},
                "files": {k: {"uri": os.path.abspath(p), "sha256": sha256_file(p)} for k, p in out.items()}}
    comparison = compare_saved(out, args.compare, args.output) if args.compare else None
    with open(os.path.join(args.output, "audit.json"), "w") as f:
        json.dump({"horizon": args.horizon, "rows": int(len(keys)), "audit": audit, "comparison": comparison,
                   "runtime": runtime_identity(), "seconds": round(time.time() - t0, 1)}, f, indent=1, default=str)
    with open(os.path.join(args.output, "manifest.json"), "w") as f:
        json.dump(snapshot, f, indent=1)
    print(json.dumps({"rows": int(len(keys)), "shape": list(X.shape), "comparison": comparison, "seconds": round(time.time() - t0, 1)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
