"""FEWS NET stage-1 GeoRF candidate runs: v1, D26-D31 and D34 (one package per run, every candidate with saved
target predictions).

A candidate is a GeoRF partition tree over areas; its served boosters are the terminal partitions plus ``root`` (even
when root is not itself terminal; ``checkpoints/<candidate>/xgb_<branch>.ubj``). A row is routed by its area: ``correspondence_table.csv`` maps an area
to its terminal partition (leading zeros kept); an area outside the table is ``root_unassigned_test_area`` and takes
``xgb_root``. Intermediate node boosters in the checkpoint tree are preserved with the run archive, not packaged.

Binding before predictions: the run's prepared snapshot and ``features.json`` hash to its own
``prepared/manifests/outputs.json``; every served booster hashes to ``candidate.json`` ``checkpoints.sha256``. The
saved ``target_predictions.csv`` has no producer-recorded hash, so the full check binds it by content: every row is
re-routed (``branch_id``/``routing`` exactly), re-predicted from the snapshot at the candidate's target month
(<= 1e-6, ``y_pred_partitioned_code`` = argmax), its truth equals the snapshot class code, and the counts recomputed
from the saved rows equal ``candidate.json`` scores (``partitioned`` n and per-class tp/fp/fn, ``partitioned_crisis``
tp/fp/fn/tn) - a changed or truncated file fails.
"""
import io
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from research_cloud.packages.common import PackageBuilder, PackageError, select_reference, sha256_file
from research_cloud.packages.fews_ordinary import LABELS, ROOT, month_index

RUNS = ("geoxgb-v1-20261001", "geoxgb-d26-20261001", "geoxgb-d27-tb3-20261001", "geoxgb-d28-rootinc-20261001",
        "geoxgb-d29-confirm-20261001", "geoxgb-d30-recent-search-20261001", "geoxgb-d31-matched-search-20261001",
        "geoxgb-d34-e1-brier-20261002")
ROOT_ROUTE = "root_unassigned_test_area"

ENTRY = '''"""Keyed loader for one FEWS NET stage-1 candidate run package (generated; see package.json)."""
import json
import os

import numpy as np
import pandas as pd
import xgboost as xgb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Model:
    def __init__(self, package_dir=ROOT):
        self.dir = package_dir
        self.meta = json.load(open(os.path.join(package_dir, "package.json")))
        table = pd.read_csv(os.path.join(package_dir, "deps", "routing.csv"),
                            dtype={"candidate": str, "branch": str}, keep_default_na=False)
        self.branch = {(c, int(a)): b for c, a, b in table[["candidate", "area", "branch"]].itertuples(index=False)}
        self.n_features = len(pd.read_csv(os.path.join(package_dir, "deps", "feature_order.csv")))
        self.cache = {}

    def booster(self, unit):
        if unit not in self.cache:               # lazy: a run holds hundreds of branch boosters
            b = xgb.Booster()
            b.load_model(bytearray(open(os.path.join(self.dir, self.meta["units"][unit]["file"]), "rb").read()))
            self.cache[unit] = b
        return self.cache[unit]

    def predict(self, keys, X):
        """keys: DataFrame[candidate, area, target_month]; X: (n, 162) rows in deps/feature_order.csv order."""
        X = np.array(X, dtype=np.float64, copy=True)
        if X.ndim != 2 or X.shape[1] != self.n_features:
            raise ValueError(f"X must be (n, {self.n_features})")
        if len(X) != len(keys):
            raise ValueError(f"{len(keys)} keys but {len(X)} feature rows")
        X[np.isinf(X)] = np.nan                      # native_xgb.clean
        keys = keys.reset_index(drop=True)
        units, routes = [], []
        for cand, area in zip(keys["candidate"], keys["area"]):
            if cand not in self.meta["candidates"]:
                raise KeyError(f"{cand} is not a candidate of this run")
            branch = self.branch.get((cand, int(area)))
            units.append(f"{cand}|{branch if branch is not None else 'root'}")
            routes.append("terminal_branch" if branch is not None else "root_unassigned_test_area")
        proba = np.full((len(keys), 4), np.nan)
        for unit, idx in pd.Series(units).groupby(units).indices.items():
            pred = self.booster(unit).predict(xgb.DMatrix(X[idx], missing=np.nan, nthread=4))
            if pred.shape != (len(idx), 4):
                raise RuntimeError(f"{unit}: booster returned shape {pred.shape}")
            proba[idx] = pred
        out = keys[["candidate", "area", "target_month"]].copy()
        out["unit"] = [self.meta["units"][u]["sha256"][:16] for u in units]
        out["route"] = routes
        for k, label in enumerate(("1", "2", "3", "4或5")):
            out[f"p_{label}"] = proba[:, k]
        out["y_pred_code"] = np.argmax(proba, axis=1).astype(np.int64)   # first max wins
        return out


def load(package_dir=ROOT):
    return Model(package_dir)
'''


def stage_dir(run_dir):
    stages = [p for p in run_dir.iterdir() if p.is_dir() and p.name.startswith("stage1")
              and not p.name.endswith(("_compare", "_diagnostics"))]
    if len(stages) != 1:
        raise PackageError(f"{run_dir.name}: expected one stage-1 directory, found {[p.name for p in stages]}")
    return stages[0]


def prepared(run_dir):
    """(ordered features, schema sha, features.json sha, {h: snapshot path}) bound to the run's outputs.json."""
    manifests = run_dir / "prepared" / "manifests"
    outputs = json.load(open(manifests / "outputs.json"))
    features_sha = sha256_file(manifests / "features.json")
    if outputs.get("manifests/features.json") != features_sha:
        raise PackageError(f"{run_dir.name}: features.json differs from prepared outputs.json")
    features = json.load(open(manifests / "features.json"))
    snaps = {}
    for h in (4, 8, 12):
        path = run_dir / "prepared" / f"snapshot_h{h}.parquet"
        if sha256_file(path) != outputs.get(path.name):
            raise PackageError(f"{run_dir.name}: {path.name} differs from prepared outputs.json")
        snaps[h] = path
    if len(features["ordered_features"]) != features["count"]:
        raise PackageError(f"{run_dir.name}: features.json count mismatch")
    return features["ordered_features"], features["schema_sha256"], features_sha, snaps


def recount(truth, pred):
    """candidate.json scores: per-class tp/fp/fn on fixed-four labels and crisis (code >= 2) tp/fp/fn/tn."""
    per = {}
    for k, l in enumerate(LABELS):
        per[l] = {"tp": int(((pred == k) & (truth == k)).sum()), "fp": int(((pred == k) & (truth != k)).sum()),
                  "fn": int(((pred != k) & (truth == k)).sum())}
    z, a = truth >= 2, pred >= 2
    crisis = {"tp": int((z & a).sum()), "fp": int((~z & a).sum()), "fn": int((z & ~a).sum()), "tn": int((~z & ~a).sum())}
    return per, crisis


def check_candidate(sdir, name, snap, features):
    import xgboost as xgb
    cdir = sdir / "candidates" / name
    cand = json.load(open(cdir / "candidate.json"))
    h, target = int(name.split("_")[0][1:]), name.split("_")[1]
    terminals = list(cand["partition"]["terminal_partitions"])
    served = sorted(set(terminals) | {"root"})   # root serves areas outside the map even when it is not terminal
    recorded = cand["checkpoints"]["sha256"]
    ckpt = sdir / "checkpoints" / name
    units = {}
    for branch in served:
        f = f"xgb_{branch}.ubj"
        if f not in recorded or sha256_file(ckpt / f) != recorded[f]:
            raise PackageError(f"{name}: {f} differs from candidate.json checkpoints")
        units[branch] = ckpt / f
    corr = pd.read_csv(cdir / "correspondence_table.csv", dtype={"partition_id": str}, keep_default_na=False)
    corr_map = dict(zip(corr["FEWSNET_admin_code"].astype(int), corr["partition_id"]))
    if not set(corr_map.values()) <= set(terminals):
        raise PackageError(f"{name}: correspondence partitions are not terminal partitions")
    preds = pd.read_csv(cdir / "target_predictions.csv", dtype={"branch_id": str, "routing": str},
                        float_precision="round_trip", keep_default_na=False)
    areas = preds["FEWSNET_admin_code"].astype(int).to_numpy()
    branch = np.array([corr_map.get(a, "root") for a in areas], dtype=object)
    route = np.where([a in corr_map for a in areas], "terminal_branch", ROOT_ROUTE).astype(object)
    if not (np.array_equal(branch, preds["branch_id"].to_numpy(object))
            and np.array_equal(route, preds["routing"].to_numpy(object))):
        raise PackageError(f"{name}: re-derived branch/routing differ from target_predictions")
    keys = [(a, month_index(target)) for a in areas]
    absent = ~pd.MultiIndex.from_tuples(keys).isin(snap.index)
    if absent.any():
        raise PackageError(f"{name}: {int(absent.sum())} keys absent from the snapshot")
    data = snap.loc[keys]
    truth = preds["y_true_code"].to_numpy(int)
    if not np.array_equal(data["class_code"].to_numpy(int), truth):
        raise PackageError(f"{name}: saved truth differs from the snapshot class code")
    X = data[features].to_numpy(dtype=np.float64, copy=True)
    Xc = X.copy()
    Xc[np.isinf(Xc)] = np.nan
    proba = np.full((len(preds), 4), np.nan)
    for b in sorted(set(branch.tolist())):
        idx = np.flatnonzero(branch == b)
        bst = xgb.Booster()
        bst.load_model(bytearray(units[b].read_bytes()))
        proba[idx] = bst.predict(xgb.DMatrix(Xc[idx], missing=np.nan, nthread=4))
    saved = preds[[f"p_partitioned_{l}" for l in LABELS]].to_numpy(np.float64)
    err = np.abs(saved - proba)
    pred_code = preds["y_pred_partitioned_code"].to_numpy(int)
    if err.max() > 1e-6 or not np.array_equal(pred_code, np.argmax(proba, axis=1)):
        raise PackageError(f"{name}: full check failed (max {err.max()})")
    per, crisis = recount(truth, pred_code)
    scores = cand["scores"]
    want_per = {l: {k: scores["partitioned"]["per_class"][l][k] for k in ("tp", "fp", "fn")} for l in LABELS}
    want_crisis = {k: scores["partitioned_crisis"][k] for k in ("tp", "fp", "fn", "tn")}
    if scores["partitioned"]["n"] != len(preds) or per != want_per or crisis != want_crisis:
        raise PackageError(f"{name}: counts from the saved rows differ from candidate.json scores")
    frame = pd.DataFrame({"candidate": name, "area": areas, "target_month": target, "branch": branch, "route": route})
    for k, l in enumerate(LABELS):
        frame[f"p_{l}"] = saved[:, k]
    frame["y_pred_code"] = pred_code.astype(np.int64)
    check = {"rows": int(len(preds)), "max_abs_err": float(err.max()), "branches": len(served), "terminal_partitions": len(terminals),
             "root_rows": int((route == ROOT_ROUTE).sum()), "target_predictions_sha256": sha256_file(cdir / "target_predictions.csv"),
             "correspondence_sha256": sha256_file(cdir / "correspondence_table.csv")}
    return h, units, recorded, corr_map, frame, X, check


def build_run(out_root, run, runtime, per_unit=8):
    run_dir = ROOT / run
    sdir = stage_dir(run_dir)
    features, schema_sha, features_sha, snap_paths = prepared(run_dir)
    names = sorted(p.name for p in (sdir / "candidates").iterdir()
                   if (p / "target_predictions.csv").exists() and (p / "candidate.json").exists())
    b = PackageBuilder(os.path.join(out_root, f"fews-{run}"))
    snaps, units, routing, refs, inputs, checks = {}, {}, [], [], [], {}
    for name in names:
        h = int(name.split("_")[0][1:])
        if h not in snaps:
            frame = pd.read_parquet(snap_paths[h], columns=["area", "target_month", "class_code"] + features)
            snaps[h] = frame.set_index(["area", "target_month"])
            if not snaps[h].index.is_unique:
                raise PackageError(f"{run}: snapshot_h{h} keys are not unique")
        h, served, recorded, corr_map, frame, X, check = check_candidate(sdir, name, snaps[h], features)
        for branch, path in served.items():
            unit = f"{name}|{branch}"
            units[unit] = {"file": f"weights/{name}/xgb_{branch}.ubj", "sha256": recorded[path.name]}
            b.add_file(str(path), units[unit]["file"], recorded[path.name], None)
        for f in ("candidate.json", "correspondence_table.csv", "target_predictions.csv"):
            b.add_file(str(sdir / "candidates" / name / f), f"deps/source/{name}/{f}")
        routing.append(pd.DataFrame({"candidate": name, "area": list(corr_map), "branch": list(corr_map.values())}))
        frame["unit_key"] = name + "|" + frame["branch"]
        frame["unit"] = [units[u]["sha256"][:16] for u in frame["unit_key"]]
        srt = np.sort(frame[[f"p_{l}" for l in LABELS]].to_numpy(np.float64), axis=1)
        ref = select_reference(frame, "unit_key", pd.Series(srt[:, -1] - srt[:, -2], index=frame.index),
                               ["candidate", "area"], per_unit=per_unit, cover_cols=("route",))
        refs.append(ref)
        inputs.append(X[ref.index.to_numpy()])
        checks[name] = check
        print(run, name, check["rows"], check["branches"], check["max_abs_err"], flush=True)
    for f in ("outputs.json", "features.json", "identity.json"):
        b.add_file(str(run_dir / "prepared" / "manifests" / f), f"deps/source/prepared/{f}")
    b.add_bytes("deps/feature_order.csv", pd.DataFrame({"name": features}).to_csv(index=False).encode())
    b.add_bytes("deps/routing.csv", pd.concat(routing, ignore_index=True).to_csv(index=False).encode())
    ref = pd.concat(refs, ignore_index=True)
    buf = io.BytesIO()
    np.save(buf, np.ascontiguousarray(np.vstack(inputs), dtype=np.float64), allow_pickle=False)
    b.add_bytes("reference/inputs.npy", buf.getvalue())
    prob = [f"p_{l}" for l in LABELS]
    b.add_bytes("reference/expected.csv", ref[["candidate", "area", "target_month", "unit", "route"] + prob + ["y_pred_code"]]
                .to_csv(index=False, float_format="%.17g").encode())
    b.add_bytes("loader/entry.py", ENTRY.encode())
    total = {"candidates": len(names), "rows": sum(c["rows"] for c in checks.values()),
             "max_abs_err": max(c["max_abs_err"] for c in checks.values()),
             "root_rows": sum(c["root_rows"] for c in checks.values())}
    identity = json.load(open(run_dir / "prepared" / "manifests" / "identity.json"))
    return b.finalize({
        "family": "fewsnet_stage1_candidates", "status": "complete", "gaps": [],
        "identity": {"run": run, "stage_dir": sdir.name, "producer": identity.get("code") or identity.get("producer_code")},
        "candidates": names, "fitted_units": len(units), "units": units,
        "binding": {"schema_sha256": schema_sha, "features_json_sha256": features_sha,
                    "snapshots": {f"h{h}": sha256_file(p) for h, p in snap_paths.items()},
                    "rule": "snapshots and features.json == prepared outputs.json; served boosters == candidate.json "
                            "checkpoints.sha256; target_predictions bound by content (routing, predictions, truth and "
                            "candidate.json score counts)"},
        "full_cohort_check": {"total": total, "candidates": checks},
        "routing": {"table": "deps/routing.csv", "feature_order": "deps/feature_order.csv",
                    "rule": "correspondence_table area -> terminal partition booster; areas outside it -> xgb_root "
                            "(root_unassigned_test_area)", "routes_in_version": ["terminal_branch", ROOT_ROUTE]},
        "runtime": {"linux": runtime},
        "code": {"loader": "thin reimplementation (correspondence routing, native_xgb.clean/proba, argmax) accepted by replay"},
        "loader": {"entry": "loader/entry.py", "keys": ["candidate", "area", "target_month"],
                   "call": "load(package_dir).predict(keys[candidate,area,target_month], X)",
                   "inputs": "prepared float64 X: the run's 162 prepared snapshot features (deps/feature_order.csv) for "
                             "the row's area and target month; the prepared snapshots are preserved with the run archive. "
                             "Windows paths in deps/source are provenance only.",
                   "unserved_keys": "KeyError for a candidate outside this run; areas outside the map take xgb_root"},
        "preserved_not_packaged": "intermediate node boosters, validation/E2 predictions, branch tables, s_branch.pkl, "
                                  "checkpoint directories without a candidate record, gscreen/globals and compare stages",
        "reference": {"rows": int(len(ref)), "per_unit_cap": per_unit, "compare_columns": prob + ["y_pred_code"],
                      "routes_covered": sorted(ref["route"].unique()),
                      "selection": "per served booster: route coverage, then half nearest an argmax tie, rest by key hash"},
        "tolerance": {"declared_before_comparison": True, "continuous": "abs(new-ref) <= 1e-3 + 1e-3*abs(ref) for p_1..p_4",
                      "decision": "y_pred_code exactly", "routing": "unit and route exactly"},
    })


def main():
    import argparse
    from research_cloud.packages.build_fews_scen import RUNTIME
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--run", action="append", choices=RUNS)
    args = ap.parse_args()
    for run in args.run or list(RUNS):
        if os.path.exists(os.path.join(args.out, f"fews-{run}", "package.json")):
            print(run, "exists")
            continue
        m = build_run(args.out, run, RUNTIME)
        print(run, m["status"], m["full_cohort_check"]["total"], m["reference"]["rows"], flush=True)


if __name__ == "__main__":
    main()
