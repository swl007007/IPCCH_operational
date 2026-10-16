"""FEWS NET ordinary 162-column diagnostic runs: D35 global increment, D37 recency, D46 class weight, D47 stump,
D48 known-origin, D38 persistence-margin, D51 78-column history/calendar and D52 binary roots (one package per run).

Each run fitted one four-class root booster per D34 root cell (``h{4,8,12}_{T}_{G}_r80_s42_e1pair``; 21 cells) and
saved row predictions for its parts (``rows_C``, ``rows_E3`` and, where written, ``rows_S``/``rows_FIT``; D48 files
carry ``_known``). Prediction is the ordinary kernel: the 162 D34 prepared features in ``features.json`` order,
``inf`` -> NaN, ``Booster.predict`` (n, 4) and argmax codes 0..3 (crisis = code >= 2; not used for packaging).
Weighting, recency, stumps and known-origin masks change the fit, not the prediction kernel. Columns of other arms in
the same files (``p_original_*``: D34's roots; ``p_root_*``; D46 ``p_posthoc2x_*``, a post-hoc transform, not a
booster) are preserved with the run, not packaged here.

Binding before reading predictions: the cell booster's sha256 equals its record (``*_sha256``), the D34 snapshot's
sha256 equals the run's ``identity.json`` ``inputs[cell].snapshot`` and the feature order equals D34
``prepared/manifests/features.json`` (``schema_sha256`` recorded). At build time every saved row of every part is
re-predicted from the snapshot (keyed by area and target month); probabilities must agree within 1e-6 and the saved
``y_<arm>`` must equal the argmax. Rows can appear in several cells, so a row is served by naming its cell; there is no
key router.

D38 differs only in its prediction input: its anchored boosters carry the ``geoxgb_base_margin`` marker and need the
per-row persistence base margin computed from the row's own ``hist_phase_o00`` (one of the 162 features), exactly as
the producer computed it; the saved ``origin_phase`` must equal that feature. Its ``prior_only`` and ``posthoc`` columns
are no-fit controls and are preserved, not packaged.

D51 takes the same 162-column X; its boosters read the 78 columns of the run's ``feature_map.json`` (``selected_index``
in global order, schema sha equal to D34's), a pure column take. D52's ``binary:logistic`` boosters return one crisis
probability per row; ``call_binary = p_binary >= 0.5``. Its four-class ``p_original`` columns are D34's roots and are
not fed to it.
"""
import io
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from research_cloud.packages.common import PackageBuilder, PackageError, select_reference, sha256_file

ROOT = Path("/mnt/c/Users/swl00/geoxgb_runs")
D34 = ROOT / "geoxgb-d34-e1-brier-20261002"
LABELS = ("1", "2", "3", "4或5")
DATES = ("2018-06", "2018-10", "2019-02", "2019-06", "2019-10", "2020-02", "2020-06")
G_OF = {4: "G1", 8: "G4", 12: "G2"}
RUNS = {
    "geoxgb-d35-global-increment-20261002": {"unit": "global_plus20", "record": "continuation.json", "arm": "global20",
                                              "parts": ("C", "E3", "S"), "suffix": "", "kind": "continuation of D34 root (+20 rounds)"},
    "geoxgb-d37-recency-root-20261002": {"unit": "weighted_root", "record": "weighted_root.json", "arm": "weighted",
                                          "parts": ("C", "E3"), "suffix": "", "kind": "recency-weighted root refit"},
    "geoxgb-d46-class-weight-root-20261002": {"unit": "weighted_root", "record": "weighted_root.json", "arm": "weighted",
                                               "parts": ("C", "E3", "FIT"), "suffix": "", "kind": "class-weighted root refit"},
    "geoxgb-d47-stump-root-20261002": {"unit": "stump_root", "record": "stump_root.json", "arm": "stump",
                                        "parts": ("C", "E3", "FIT"), "suffix": "", "kind": "depth-1 stump root refit"},
    "geoxgb-d48-known-origin-fit-20261002": {"unit": "known_root", "record": "known_root.json", "arm": "known",
                                              "parts": ("C", "E3", "FIT"), "suffix": "_known", "kind": "known-origin root refit"},
    "geoxgb-d38-persistence-margin-root-20261002": {"unit": "anchored_root", "record": "anchored_root.json", "arm": "anchored",
                                                     "parts": ("C", "E3"), "suffix": "", "kind": "root refit with a per-row persistence base margin",
                                                     "margin": {"attr": "geoxgb_base_margin", "marker": "d38-persistence-lambda0.5-v1",
                                                                "feature": "hist_phase_o00"}},
    "geoxgb-d51-history-calendar-root-20261002": {"unit": "h78_root", "record": "h78_root.json", "arm": "h78",
                                                   "parts": ("C", "E3", "FIT"), "suffix": "", "kind": "root refit on the 78 history/calendar columns",
                                                   "projection": "feature_map.json"},
    "geoxgb-d52-binary-root-20261002": {"unit": "binary_root", "record": "binary_root.json", "arm": "binary",
                                         "parts": ("C", "E3", "FIT"), "suffix": "", "kind": "binary:logistic crisis root",
                                         "binary": {"threshold": 0.5, "rule": "call_binary = p_binary >= 0.5 (d52_binary_root.THRESHOLD)"}},
}
MARGIN_RULE = ("lambda 0.5 prior from the row's own hist_phase_o00 (phase 5 -> code 3): known q = 0.625 own class, 0.125 "
               "others; margin = 0.5 + log(q) - mean(log(q)) as float32; missing origin exactly 0.5; set as the DMatrix "
               "base_margin (stage1_persistence_margin_root.persistence_margin, native_xgb.proba)")

ENTRY = '''"""Keyed loader for one FEWS NET ordinary diagnostic run package (generated; see package.json)."""
import json
import os

import numpy as np
import pandas as pd
import xgboost as xgb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def persistence_margin(phase):
    """D38 lambda=0.5 persistence prior as a centred log margin around 0.5, float32 (n, 4); missing origin -> 0.5."""
    p = np.asarray(phase, dtype=np.float64)
    known = np.isfinite(p)
    if not np.all(np.isin(p[known], (1.0, 2.0, 3.0, 4.0, 5.0))):
        raise ValueError("hist_phase_o00 holds values outside the IPC phases 1..5")
    codes = np.where(known, np.minimum(p, 4.0) - 1.0, np.nan)
    q = np.full((len(p), 4), 0.25)
    q[known] = (1.0 - 0.5) / 4
    q[np.flatnonzero(known), codes[known].astype(np.int64)] += 0.5
    m = np.full(q.shape, 0.5, dtype=np.float32)
    lq = np.log(q[known])
    m[known] = (0.5 + lq - lq.mean(axis=1, keepdims=True)).astype(np.float32)
    return np.ascontiguousarray(m)


class Model:
    def __init__(self, package_dir=ROOT):
        self.meta = json.load(open(os.path.join(package_dir, "package.json")))
        self.boosters = {}
        for cell, unit in self.meta["units"].items():
            b = xgb.Booster()
            b.load_model(bytearray(open(os.path.join(package_dir, unit["file"]), "rb").read()))
            self.boosters[cell] = b
        names = pd.read_csv(os.path.join(package_dir, "deps", "feature_order.csv"))["name"].tolist()
        self.n_features = len(names)
        self.columns = (self.meta.get("projection") or {}).get("selected_index")   # D51: 78-column take
        self.binary = self.meta.get("output") == "binary"                         # D52: scalar crisis probability
        self.margin = self.meta.get("base_margin")
        if self.margin:
            self.phase_col = names.index(self.margin["feature"])
            for cell, b in self.boosters.items():
                if b.attr(self.margin["attr"]) != self.margin["marker"]:
                    raise RuntimeError(f"{cell}: booster lacks the base-margin marker")

    def predict(self, keys, X):
        """keys: DataFrame[cell, area, target_month]; X: (n, 162) rows in deps/feature_order.csv order."""
        X = np.array(X, dtype=np.float64, copy=True)
        if X.ndim != 2 or X.shape[1] != self.n_features:
            raise ValueError(f"X must be (n, {self.n_features})")
        X[np.isinf(X)] = np.nan                      # native_xgb.clean
        keys = keys.reset_index(drop=True)
        proba = np.full((len(keys), 1 if self.binary else 4), np.nan)
        for cell, idx in keys.groupby("cell").indices.items():
            booster = self.boosters[cell]            # KeyError: not a cell of this run
            Xi = X[idx] if self.columns is None else X[idx][:, self.columns]
            dm = xgb.DMatrix(Xi, missing=np.nan, nthread=4)
            if self.margin:                          # D38: per-row persistence margin from the row's own origin phase
                dm.set_base_margin(persistence_margin(X[idx, self.phase_col]))
            pred = booster.predict(dm)
            if pred.shape != ((len(idx),) if self.binary else (len(idx), 4)):
                raise RuntimeError(f"{cell}: booster returned shape {pred.shape}")
            proba[idx] = pred.reshape(len(idx), -1)
        out = keys[["cell", "area", "target_month"]].copy()
        out["unit"] = [self.meta["units"][c]["sha256"][:16] for c in keys["cell"]]
        out["route"] = keys["cell"].astype(str)
        if self.binary:
            out["p_binary"] = proba[:, 0]
            out["call_binary"] = (proba[:, 0] >= self.meta["binary"]["threshold"]).astype(np.int64)
            return out
        for k, label in enumerate(("1", "2", "3", "4或5")):
            out[f"p_{label}"] = proba[:, k]
        out["y_pred_code"] = np.argmax(proba, axis=1).astype(np.int64)   # first max wins
        return out


def load(package_dir=ROOT):
    return Model(package_dir)
'''


def persistence_margin(phase):
    """D38 lambda=0.5 persistence prior as a centred log margin around 0.5, float32 (n, 4); missing origin -> 0.5."""
    p = np.asarray(phase, dtype=np.float64)
    known = np.isfinite(p)
    if not np.all(np.isin(p[known], (1.0, 2.0, 3.0, 4.0, 5.0))):
        raise ValueError("hist_phase_o00 holds values outside the IPC phases 1..5")
    codes = np.where(known, np.minimum(p, 4.0) - 1.0, np.nan)
    q = np.full((len(p), 4), 0.25)
    q[known] = (1.0 - 0.5) / 4
    q[np.flatnonzero(known), codes[known].astype(np.int64)] += 0.5
    m = np.full(q.shape, 0.5, dtype=np.float32)
    lq = np.log(q[known])
    m[known] = (0.5 + lq - lq.mean(axis=1, keepdims=True)).astype(np.float32)
    return np.ascontiguousarray(m)


def month_index(t):
    return int(t[:4]) * 12 + int(t[5:]) - 1


def feature_order():
    manifest = D34 / "prepared" / "manifests" / "features.json"
    features = json.load(open(manifest))
    names = features["ordered_features"]
    if len(names) != 162 or features["count"] != 162:
        raise PackageError("D34 features.json does not hold 162 ordered features")
    return names, features["schema_sha256"], sha256_file(manifest)


class Snapshots:
    """D34 prepared snapshots, read once per horizon and keyed by (area, month index)."""

    def __init__(self, features):
        self.features, self.cache = features, {}

    def get(self, h):
        if h not in self.cache:
            path = D34 / "prepared" / f"snapshot_h{h}.parquet"
            frame = pd.read_parquet(path, columns=["area", "target_month", "class_code"] + self.features)
            frame = frame.set_index(["area", "target_month"])
            if not frame.index.is_unique:
                raise PackageError(f"snapshot_h{h} keys are not unique")
            self.cache[h] = (frame, sha256_file(path))
        return self.cache[h]


def cells():
    return [f"h{h}_{t}_{G_OF[h]}_r80_s42_e1pair" for h in (4, 8, 12) for t in DATES]


def check_cell(run_dir, spec, cell, snapshots, identity, columns=None):
    """Bind the cell's booster and snapshot, then re-predict every saved row; returns (unit, rows, X, check)."""
    import xgboost as xgb
    h = int(cell.split("_")[0][1:])
    record = json.load(open(run_dir / cell / spec["record"]))
    ubj = run_dir / cell / f"{spec['unit']}.ubj"
    digest = sha256_file(ubj)
    if digest != record[f"{spec['unit']}_sha256"]:
        raise PackageError(f"{cell}: {ubj.name} sha256 differs from {spec['record']}")
    snap, snap_sha = snapshots.get(h)
    if snap_sha != identity["inputs"][cell]["snapshot"]:
        raise PackageError(f"{cell}: D34 snapshot_h{h} differs from the run identity")
    booster = xgb.Booster()
    booster.load_model(bytearray(ubj.read_bytes()))
    if booster.num_features() != (len(columns) if columns else len(snapshots.features)):
        raise PackageError(f"{cell}: booster expects {booster.num_features()} features")
    margin = spec.get("margin")
    if margin and not (booster.attr(margin["attr"]) == margin["marker"] == record.get(f"{spec['unit']}_marker")):
        raise PackageError(f"{cell}: booster/record base-margin marker differs")
    if not margin and booster.attr("geoxgb_base_margin") is not None:
        raise PackageError(f"{cell}: unexpected base-margin booster")
    prob = [f"p_{spec['arm']}_{l}" for l in LABELS]
    frames, Xs, check = [], [], {}
    for part in spec["parts"]:
        path = run_dir / cell / f"rows_{part}{spec['suffix']}.csv.gz"
        rows = pd.read_csv(path, float_precision="round_trip", dtype={"target_month": str})
        keys = list(zip(rows["area"].astype(int), rows["target_month"].map(month_index)))
        absent = ~pd.MultiIndex.from_tuples(keys).isin(snap.index)
        if absent.any():
            raise PackageError(f"{cell}/{part}: {int(absent.sum())} keys absent from the snapshot")
        data = snap.loc[keys]
        if not np.array_equal(data["class_code"].to_numpy(int), rows["truth"].to_numpy(int)):
            raise PackageError(f"{cell}/{part}: saved truth differs from the snapshot class_code")
        X = data[snapshots.features].to_numpy(dtype=np.float64, copy=True)
        Xc = X.copy()
        Xc[np.isinf(Xc)] = np.nan
        dm = xgb.DMatrix(Xc[:, columns] if columns else Xc, missing=np.nan, nthread=4)
        if margin:
            phase = Xc[:, snapshots.features.index(margin["feature"])]
            saved_phase = rows["origin_phase"].to_numpy(dtype=np.float64)
            if not np.array_equal(phase, saved_phase, equal_nan=True):
                raise PackageError(f"{cell}/{part}: saved origin_phase differs from the snapshot hist_phase_o00")
            dm.set_base_margin(persistence_margin(phase))
        proba = booster.predict(dm).astype(np.float64)
        binary = spec.get("binary")
        if binary:
            if proba.ndim != 1:
                raise PackageError(f"{cell}: binary booster returned shape {proba.shape}")
            err = np.abs(rows["p_binary"].to_numpy(dtype=np.float64) - proba)
            decided = rows["call_binary"].to_numpy(int) == (proba >= binary["threshold"]).astype(int)
        else:
            err = np.abs(rows[prob].to_numpy(dtype=np.float64) - proba)
            decided = rows[f"y_{spec['arm']}"].to_numpy(int) == np.argmax(proba, axis=1)
        check[part] = {"rows": int(len(rows)), "max_abs_err": float(err.max()), "decision_matches": int(decided.sum()),
                       "file_sha256": sha256_file(path)}
        if err.max() > 1e-6 or not decided.all():
            raise PackageError(f"{cell}/{part}: full-part check failed {check[part]}")
        if binary:
            frame = rows[["area", "target_month", "p_binary", "call_binary"]].copy()
            frame["call_binary"] = frame["call_binary"].astype(np.int64)
        else:
            frame = rows[["area", "target_month"] + prob].copy()
            frame.columns = ["area", "target_month"] + [f"p_{l}" for l in LABELS]
            frame["y_pred_code"] = rows[f"y_{spec['arm']}"].to_numpy(np.int64)
        frame["part"] = part
        frames.append(frame)
        Xs.append(X)
    unit = {"file": f"weights/{cell}.ubj", "sha256": digest, "record": f"deps/source/{cell}/{spec['record']}",
            "horizon": h, "root": cell, "origin_month": record.get("origin_month"),
            "fitting_keys_sha256": record.get("fitting_keys_sha256"), "fitting_rows": record.get("fitting_rows"),
            "original_root_sha256": record.get("original_root_sha256") or record.get("root_booster_sha256")}
    return unit, ubj, pd.concat(frames, ignore_index=True), np.vstack(Xs), check


def build_run(out_root, run, snapshots, schema, runtime, per_unit=64):
    spec = RUNS[run]
    run_dir = ROOT / run
    identity = json.load(open(run_dir / "identity.json"))
    gate = json.load(open(run_dir / "gate.json"))
    completion = json.load(open(run_dir / "completion.json"))
    if not gate.get("passed") or completion.get("status") != "completed":
        raise PackageError(f"{run}: gate not passed or run not completed")
    expected = cells()
    present = sorted(p.name for p in run_dir.iterdir() if p.is_dir())
    if present != sorted(expected):
        raise PackageError(f"{run}: cell directories differ from the 21 D34 roots")
    names, schema_sha, features_sha = schema
    b = PackageBuilder(os.path.join(out_root, f"fews-{run}"))
    columns, projection = None, None
    if spec.get("projection"):   # D51: the run's own feature map, checked against D34's order
        fmap_path = run_dir / spec["projection"]
        fmap = json.load(open(fmap_path))
        columns = [int(i) for i in fmap["selected_index"]]
        if fmap["schema_sha256"] != schema_sha or fmap["selected_names"] != [names[i] for i in columns] \
                or columns != sorted(columns) or len(columns) != 78:
            raise PackageError(f"{run}: feature_map does not select 78 D34 columns in global order")
        b.add_file(str(fmap_path), f"deps/source/{spec['projection']}")
        projection = {"feature_map": f"deps/source/{spec['projection']}", "selected_index": columns,
                      "selected_count": len(columns), "feature_map_sha256": sha256_file(fmap_path),
                      "rule": "pure column take of the 162-column X in global order (d51 project())"}
    units, refs, inputs, checks = {}, [], [], {}
    for cell in expected:
        unit, ubj, frame, X, check = check_cell(run_dir, spec, cell, snapshots, identity, columns)
        b.add_file(str(ubj), unit["file"], unit["sha256"], None)
        b.add_file(str(run_dir / cell / spec["record"]), unit["record"])
        units[cell], checks[cell] = unit, check
        frame["cell"] = cell
        frame["unit"] = unit["sha256"][:16]
        frame["route"] = cell
        frame["row"] = np.arange(len(frame))
        if spec.get("binary"):
            boundary = (frame["p_binary"] - spec["binary"]["threshold"]).abs()
        else:
            p = np.sort(frame[[f"p_{l}" for l in LABELS]].to_numpy(dtype=np.float64), axis=1)
            boundary = pd.Series(p[:, -1] - p[:, -2], index=frame.index)
        ref = select_reference(frame, "unit", boundary,
                               ["cell", "area", "target_month", "part"], per_unit=per_unit, cover_cols=("part",))
        refs.append(ref)
        inputs.append(X[ref["row"].to_numpy()])
        print(run, cell, {k: (v["rows"], v["max_abs_err"]) for k, v in check.items()}, flush=True)
    for name in ("identity.json", "gate.json", "completion.json", "summary.json"):
        b.add_file(str(run_dir / name), f"deps/source/{name}")
    b.add_file(str(D34 / "prepared" / "manifests" / "features.json"), "deps/source/d34_features.json", features_sha)
    b.add_bytes("deps/feature_order.csv", pd.DataFrame({"name": names}).to_csv(index=False).encode())
    ref = pd.concat(refs, ignore_index=True)
    buf = io.BytesIO()
    np.save(buf, np.ascontiguousarray(np.vstack(inputs), dtype=np.float64), allow_pickle=False)
    b.add_bytes("reference/inputs.npy", buf.getvalue())
    prob, decision = (["p_binary"], "call_binary") if spec.get("binary") else ([f"p_{l}" for l in LABELS], "y_pred_code")
    b.add_bytes("reference/expected.csv", ref[["cell", "area", "target_month", "part", "unit", "route"] + prob + [decision]]
                .to_csv(index=False, float_format="%.17g").encode())
    b.add_bytes("loader/entry.py", ENTRY.encode())
    total = {"rows": sum(v["rows"] for c in checks.values() for v in c.values()),
             "max_abs_err": max(v["max_abs_err"] for c in checks.values() for v in c.values()),
             "decision_matches": sum(v["decision_matches"] for c in checks.values() for v in c.values())}
    return b.finalize({
        "family": "fewsnet_ordinary_diagnostic", "status": "complete", "gaps": [],
        "identity": {"run": run, "stage": identity.get("stage"), "kind": spec["kind"], "arm_columns": f"p_{spec['arm']}_*",
                     "d34_run": "geoxgb-d34-e1-brier-20261002", "producer_rev": identity.get("producer_rev"),
                     "producer_code": identity.get("producer_code"), "script_code": identity.get("script_code")},
        "fitted_units": len(units), "units": units,
        "base_margin": ({**spec["margin"], "rule": MARGIN_RULE} if spec.get("margin") else None),
        "projection": projection, "output": "binary" if spec.get("binary") else "fourclass", "binary": spec.get("binary"),
        "binding": {"d34_features_schema_sha256": schema_sha, "d34_features_json_sha256": features_sha,
                    "snapshots": {f"h{h}": snapshots.get(h)[1] for h in (4, 8, 12)},
                    "rule": "unit sha256 == cell record; snapshot sha256 == identity.inputs[cell].snapshot"},
        "full_cohort_check": {"total": total, "cells": checks},
        "routing": {"by": "explicit cell (keys[cell]); rows recur across cells, so there is no key router",
                    "feature_order": "deps/feature_order.csv"},
        "runtime": {"original": identity.get("runtime"), "linux": runtime},
        "code": {"loader": "thin reimplementation (native_xgb.clean, Booster.predict, argmax) accepted by replay",
                 "original_code_sha256": identity.get("producer_code")},
        "loader": {"entry": "loader/entry.py", "keys": ["cell", "area", "target_month"],
                   "call": "load(package_dir).predict(keys[cell,area,target_month], X)",
                   "inputs": "prepared float64 X: the 162 D34 prepared snapshot features (deps/feature_order.csv) for "
                             "the row's area and target month at that horizon. The D34 snapshots and their raw inputs are "
                             "preserved with the D34 run record, not in this package; Windows paths in deps/source are "
                             "provenance only.",
                   "unserved_keys": "KeyError for a cell outside this run"},
        "preserved_not_packaged": "other arms' columns in the saved rows files (D34 original roots, p_root, D46 "
                                  "posthoc2x), fitting weights and per-part files beyond the reference sample",
        "reference": {"rows": int(len(ref)), "per_unit_cap": per_unit,
                      "compare_columns": prob + ([] if spec.get("binary") else ["y_pred_code"]),
                      "exact_columns": ["call_binary"] if spec.get("binary") else [],
                      "parts_covered": sorted(ref["part"].unique()),
                      "selection": "per cell: part coverage, then half nearest an argmax tie, rest by key hash"},
        "tolerance": {"declared_before_comparison": True, "continuous": f"abs(new-ref) <= 1e-3 + 1e-3*abs(ref) for {', '.join(prob)}",
                      "decision": f"{decision} exactly", "routing": "unit and route (= cell) exactly"},
    })
