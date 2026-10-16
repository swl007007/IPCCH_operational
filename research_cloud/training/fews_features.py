"""FEWS NET four-class scenario feature snapshot for one development target (new Linux research step; feeds
fews_fourclass trials).

Rebuilds FEWS's ``Availability`` on Linux from hashed base inputs (input manifest roles ``panel`` - the certified
pinned panel, re-certified by ``_certified_panel`` against its sha256 - ``observations``, ``release_ledger`` and
``alignment``) with FEWS's own builders, as ``run_experiment.scenario_context`` does but without its historical
Windows/runtime acceptance guard (``accept_prepared``), which is not used and not changed. Development truth is the
observations themselves (``development_truth=True``). ``Availability.stage1_input(T, k, strategy)`` then gives the
native roles for one development target T (``plan.DEV_TARGETS`` only; origin O = T - H):

* ``fit_variant`` - the lawful grouped fitting rows [O-59, O), released by O, excluding hidden cycles, with strategy
  variants and weights (``orig_key`` groups variants of one key);
* ``eval`` - one row per original key at its designated k (a second view of the SAME fitting key, not validation);
* ``target`` - the genuine target-month cohort at T (the validation cohort).

Output: ``rows.csv.gz`` (role, keys, class code, weight, variant), ``X.npy`` (the scenario feature columns, inf kept
as written by the builders), ``feature_order.csv``, ``audit.json`` and ``manifest.json`` (sha256 of each file; directly
usable as a trial input manifest).

  python -m research_cloud.training.fews_features --manifest BASE.json --horizon 4 --target 2019-02 --output DIR
      [--k 0] [--strategy A]
"""
import argparse
import gzip
import json
import os
import sys
import time

import numpy as np
import pandas as pd

from research_cloud.training.common import TrialError, resolve_inputs, runtime_identity, sha256_file

ROLES = ("fit_variant", "eval", "target")


def modules(src):
    for p in (src, os.path.join(src, "scripts")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import run_experiment as rx
    from src.experiment import availability as av, plan, stage3
    from src.feature import fourclass_features as ff
    from src.utils.run_identity import SCHEMA_PATH
    return rx, av, plan, ff, stage3, SCHEMA_PATH


def source_identity(src, schema_path):
    files = {}
    for rel in ("scripts/run_experiment.py", "src/experiment/availability.py", "src/experiment/plan.py",
                "src/experiment/stage3.py", "src/feature/fourclass_features.py", "src/model/native_xgb.py"):
        files[rel] = sha256_file(os.path.join(src, rel))
    files["feature-schema.json"] = sha256_file(schema_path)
    return {"fews_src": os.path.abspath(src), "files": dict(sorted(files.items()))}


def build(inputs, horizon, target, k, strategy, src):
    from pathlib import Path
    rx, av, plan, ff, stage3, schema_path = modules(src)
    if target not in plan.DEV_TARGETS:
        raise TrialError(f"target {target} is not a declared development target {plan.DEV_TARGETS}")
    if horizon not in (4, 8, 12):
        raise TrialError("horizon must be 4, 8 or 12")
    schema = rx.load_schema(schema_path)
    panel = rx._certified_panel(Path(inputs["panel"]), sha256_file(inputs["panel"]), schema)
    alignment = json.load(open(inputs["alignment"]))
    ledger = av.ReleaseLedger(pd.read_csv(inputs["release_ledger"], dtype=str), real=True)
    obs = rx.read_csv(Path(inputs["observations"]))[["area", "month", "country", "class_code"]]
    ctx = av.Availability(obs, ledger, ff.Scaffold(panel, rx._covariate_columns(schema)), schema, horizon, alignment,
                          truth=obs)
    frame = ctx.stage1_input(stage3.mi(target), k, strategy)
    return frame, list(ctx.features), source_identity(src, schema_path), ctx.inputs_sha256


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, help="base inputs: panel, observations, release_ledger, alignment")
    ap.add_argument("--horizon", type=int, required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--k", type=int, default=0)
    ap.add_argument("--strategy", default="A")
    ap.add_argument("--output", required=True)
    ap.add_argument("--fews-src", default=os.environ.get("FEWS_SRC"))
    args = ap.parse_args(argv)
    if not args.fews_src:
        raise SystemExit("--fews-src or FEWS_SRC is required")
    if os.path.exists(args.output):
        raise SystemExit(f"{args.output} exists; snapshots are written once")
    os.makedirs(args.output)
    t0 = time.time()
    inputs, manifest = resolve_inputs(args.manifest, args.output)
    frame, features, code, availability_sha = build(inputs, args.horizon, args.target, args.k, args.strategy, args.fews_src)
    if set(frame["role"]) - set(ROLES) or frame["role"].value_counts().get("target", 0) == 0:
        raise TrialError(f"unexpected roles {sorted(set(frame['role']))} or an empty target cohort")
    tag = f"h{args.horizon}_{args.target}_k{args.k}_{args.strategy}"
    out = {"rows": f"rows_{tag}.csv.gz", "X": f"X_{tag}.npy", "feature_order": "feature_order.csv"}
    out = {r: os.path.join(args.output, n) for r, n in out.items()}
    keys = frame[["role", "orig_key", "area", "country", "target_month", "origin_month", "class_code", "variant_k",
                  "weight", "horizon"]]
    with gzip.GzipFile(out["rows"], "wb", mtime=0) as f:
        f.write(keys.to_csv(index=False, lineterminator="\n").encode())
    np.save(out["X"], frame[features].to_numpy(dtype=np.float64))
    pd.DataFrame({"name": features}).to_csv(out["feature_order"], index=False, lineterminator="\n")
    snapshot = {"name": f"fews-scenario-fourclass-{tag}-linux", "gcp_project": manifest.get("gcp_project"),
                "derived_from": {"base_manifest": os.path.abspath(args.manifest), "base_manifest_sha256": sha256_file(args.manifest),
                                 "base_inputs": {r: e["sha256"] for r, e in manifest["files"].items()},
                                 "builder_code": code, "horizon": args.horizon, "target": args.target, "k": args.k,
                                 "strategy": args.strategy, "availability_inputs_sha256_linux": availability_sha,
                                 "recipe": "Availability(obs, ReleaseLedger, Scaffold(certified panel), schema, H, alignment, "
                                           "truth=obs).stage1_input(T, k, strategy)"},
                "files": {r: {"uri": os.path.abspath(p), "sha256": sha256_file(p)} for r, p in out.items()}}
    counts = frame["role"].value_counts().to_dict()
    with open(os.path.join(args.output, "audit.json"), "w") as f:
        json.dump({"roles": counts, "features": len(features), "original_fit_keys": int(frame.loc[frame.role == "fit_variant", "orig_key"].nunique()),
                   "target_class_counts": frame.loc[frame.role == "target", "class_code"].value_counts().sort_index().to_dict(),
                   "availability_note": "Linux digest; the Windows runs computed it with \\r\\n line terminators",
                   "runtime": runtime_identity(), "seconds": round(time.time() - t0, 1)}, f, indent=1, default=str)
    with open(os.path.join(args.output, "manifest.json"), "w") as f:
        json.dump(snapshot, f, indent=1)
    print(json.dumps({"roles": counts, "features": len(features), "seconds": round(time.time() - t0, 1)}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
