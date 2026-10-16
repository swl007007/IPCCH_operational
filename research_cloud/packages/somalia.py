"""Package builder for the IPCCH Somalia-oracle q3-optimization versions (run somalia_oracle/v2_q3).

Rules were read at the run's recorded commit (manifest ``git_head`` d75378d, not the current checkout):
``src/ipcch/somalia_oracle/q3opt.py`` final_task/predict_q3/apply_branches/bound_share/Q3Mapping and
``modeling.py`` FittedRegressor. Per saved final-prediction row of a version (view V, horizon h):
- model view = ``reused_from`` when set (copied rows), else V; job boosters ``<job>_<model view>_<target>.ubj``;
- X = the run's saved ``features/feature_matrix_hXX.csv.gz`` row (area_id, target_ord), columns of the
  model view's arm schema (``features/feature_schema.json``);
- q2/q4/q5 and q3_direct = XGBRegressor.predict(X); residual views: q3 = hist_q3_obs1 + delta(X) where the
  baseline is supported (finite and history_obs1_source_ord >= 0, from ``ledgers/row_provenance_hXX``),
  else the direct q3 (branch fallback_direct);
- q3_mapped = the recorded (job, model view, branch) calibration mapping (none / shift / isotonic via its saved
  thresholds); q3_final = clip(q3_mapped, 0, 1).
Every raw, mapped and final column is compared with the saved row. The loader is a thin reimplementation;
it is accepted only through that replay.
"""
import io
import json
import os
import re

import numpy as np
import pandas as pd

from research_cloud.packages.common import PackageBuilder, PackageError, ensure_local, select_reference, sha256_file

# IPCCH IPCCHMLflow/naming.py ARMS (raw arm -> readable arm), inverted for this run's views
VIEW_OF_ARM = {"existing_predictors": "A", "seasonal_climate": "B", "weather_oracle": "C",
               "share_history_direct": "D_direct", "share_history_residual": "D_residual",
               "share_history_selected": "D_selected"}
SCHEMA_ARM = {"A": "A", "B": "B", "C": "C", "D_direct": "D", "D_residual": "D"}   # q3opt.VIEW_SPEC
BOOSTER = re.compile(r"^(?P<job>y\d{4}_h\d{2}_o\d{4}-\d{2})_(?P<view>A|B|C|D_direct|D_residual)_(?P<target>q2|q3_direct|q3_residual_delta|q4|q5)\.ubj$")
COMPARE = ["q2_raw", "q3_raw", "q4_raw", "q5_raw", "q3_mapped", "q3_final"]
KEYS = ["area_id", "target_ord"]

ENTRY = '''"""Keyed loader for one historical IPCCH Somalia q3-optimization package (generated; see package.json)."""
import json
import os

import numpy as np
import pandas as pd
import xgboost as xgb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Model:
    def __init__(self, package_dir=ROOT):
        self.root = package_dir
        self.meta = json.load(open(os.path.join(package_dir, "package.json")))
        self.schema = json.load(open(os.path.join(package_dir, "deps", "feature_schema.json")))
        self.columns = json.load(open(os.path.join(package_dir, "deps", "input_columns.json")))
        self.h = int(self.meta["lead_months"])
        route = pd.read_csv(os.path.join(package_dir, "deps", "routing.csv"), dtype={"job_id": str, "model_view": str})
        self.route = {(int(a), int(t)): (j, v) for a, t, j, v in route[["area_id", "target_ord", "job_id", "model_view"]].itertuples(index=False)}
        maps = pd.read_csv(os.path.join(package_dir, "deps", "calibration_mappings.csv"))
        self.maps = {(r["job_id"], r["view"], r["branch"]): r for r in maps.to_dict("records")}
        self._m = {}

    def model(self, job, view, target):
        key = (job, view, target)
        if key not in self._m:
            m = xgb.XGBRegressor()
            m.load_model(os.path.join(self.root, "weights", f"{job}_{view}_{target}.ubj"))
            self._m[key] = m
        return self._m[key]

    def x(self, frame, view):
        cols = self.schema["h%02d_%s" % (self.h, {"D_direct": "D", "D_residual": "D"}.get(view, view))]
        return frame[cols].to_numpy(dtype=np.float64)

    def calibrate(self, job, view, branch, raw):
        m = self.maps.get((job, view, branch))
        if m is None or m["status"] != "ok":
            return np.full(raw.shape, np.nan)
        if m["method"] == "none":
            return raw.copy()
        if m["method"] == "shift":
            return raw - float(m["shift"])
        return np.interp(raw, json.loads(m["isotonic_x"]), json.loads(m["isotonic_y"]))   # out_of_bounds="clip"

    def predict(self, keys, X):
        """keys: DataFrame[area_id, target_ord]; X: (n, len(input_columns)) float64 rows of the run's saved
        feature matrix in deps/input_columns.json order (includes hist_q3_obs1, history_obs1_source_ord)."""
        frame = pd.DataFrame(np.asarray(X, dtype=np.float64), columns=self.columns)
        out = keys[["area_id", "target_ord"]].reset_index(drop=True).copy()
        resolved = []
        for k in zip(out["area_id"].astype(int), out["target_ord"].astype(int)):
            if k not in self.route:
                raise KeyError(f"key {k} is not served by this package")
            resolved.append(self.route[k])
        out["unit"] = [f"{j}|{v}" for j, v in resolved]
        cols = {c: np.full(len(out), np.nan) for c in ("q2_raw", "q3_raw", "q4_raw", "q5_raw", "q3_mapped")}
        branch = np.empty(len(out), dtype=object)
        for unit in sorted(set(out["unit"])):
            idx = np.flatnonzero(out["unit"].to_numpy() == unit)
            job, view = unit.split("|")
            Xv = self.x(frame.iloc[idx], view)
            for t in ("q2", "q4", "q5"):
                cols[t + "_raw"][idx] = self.model(job, view, t).predict(Xv).astype(np.float64)
            raw = self.model(job, view, "q3_direct").predict(Xv).astype(np.float64)
            br = np.full(len(idx), "direct", dtype=object)
            if view == "D_residual":
                b = frame["hist_q3_obs1"].to_numpy()[idx]
                src = frame["history_obs1_source_ord"].to_numpy()[idx]
                supported = np.isfinite(b) & (np.nan_to_num(src, nan=-1) >= 0)
                delta = self.model(job, view, "q3_residual_delta").predict(Xv).astype(np.float64)
                res = np.where(supported, b + delta, np.nan)
                br = np.where(np.isfinite(res), "residual", "fallback_direct").astype(object)
                raw = np.where(np.isfinite(res), res, raw)
            cols["q3_raw"][idx] = raw
            branch[idx] = br
            for name in sorted(set(br)):
                rows = idx[br == name]
                cols["q3_mapped"][rows] = self.calibrate(job, view, name, raw[br == name])
        for c, v in cols.items():
            out[c] = v
        out["q3_final"] = np.clip(out["q3_mapped"], 0.0, 1.0)
        out["route"] = branch
        return out


def load(package_dir=ROOT):
    return Model(package_dir)
'''


def build(out_dir, *, ipcch_root, run_root, plan_version, version_key, version, runtime, per_unit=32):
    arm, h = plan_version["arm"], int(plan_version["lead"])
    view = VIEW_OF_ARM[arm]
    manifest = json.load(open(os.path.join(run_root, "manifest.json")))
    hh = f"h{h:02d}"
    paths = {"pred": "predictions/final_predictions.csv.gz", "maps": "fits/calibration_mappings.csv",
             "schema": "features/feature_schema.json", "matrix": f"features/feature_matrix_{hh}.csv.gz",
             "prov": f"ledgers/row_provenance_{hh}.csv.gz", "inventory": "models/model_inventory.csv"}
    ensure_local([os.path.join(run_root, p) for p in paths.values()] + [os.path.join(run_root, "manifest.json")] +
                 [os.path.join(ipcch_root, m["path"]) for m in plan_version["members"] if m["role"] == "booster"])
    pred = pd.read_csv(os.path.join(run_root, paths["pred"]), low_memory=False, dtype={"reused_from": str})
    pred = pred[(pred["view"] == view) & (pred["horizon"] == h)].copy()
    if pred.empty or pred.duplicated(KEYS).any():
        raise PackageError(f"{version_key}: saved rows missing or keys repeated")
    pred["model_view"] = pred["reused_from"].where(pred["reused_from"].notna() & (pred["reused_from"] != ""), view)
    members = {os.path.basename(m["path"]): m for m in plan_version["members"] if m["role"] == "booster"}
    gaps = []
    needed = set()
    for (job, mv) in pred[["job_id", "model_view"]].drop_duplicates().itertuples(index=False):
        targets = ["q2", "q3_direct", "q4", "q5"] + (["q3_residual_delta"] if mv == "D_residual" else [])
        for t in targets:
            name = f"{job}_{mv}_{t}.ubj"
            if name in members:
                needed.add(name)
            else:
                gaps.append(f"booster {name} absent from the version's plan members")
    schema = json.load(open(os.path.join(run_root, paths["schema"])))
    matrix = pd.read_csv(os.path.join(run_root, paths["matrix"]), float_precision="round_trip")
    prov = pd.read_csv(os.path.join(run_root, paths["prov"]), float_precision="round_trip")
    if matrix.duplicated(KEYS).any() or prov.duplicated(KEYS).any():
        raise PackageError("feature matrix or provenance ledger repeats a key")
    inputs_frame = matrix.merge(prov[KEYS + ["history_obs1_source_ord"]], on=KEYS, how="left", validate="one_to_one")
    if "hist_q3_obs1" not in inputs_frame:
        raise PackageError("saved feature matrix lacks the residual baseline hist_q3_obs1")
    columns = [c for c in inputs_frame.columns if c not in KEYS]

    b = PackageBuilder(out_dir)
    for name in sorted(needed):
        m = members[name]
        b.add_file(os.path.join(ipcch_root, m["path"]), f"weights/{name}", m["sha256"], m["bytes"])
    maps = pd.read_csv(os.path.join(run_root, paths["maps"]))
    jobs = set(pred["job_id"])
    used = maps[maps["job_id"].isin(jobs) & maps["view"].isin(set(pred["model_view"]))]
    b.add_bytes("deps/calibration_mappings.csv", used.to_csv(index=False).encode())
    b.add_json("deps/feature_schema.json", {k: v for k, v in schema.items() if k.startswith(hh)})
    b.add_json("deps/input_columns.json", columns)
    b.add_bytes("deps/feature_order.csv", pd.DataFrame({"name": columns}).to_csv(index=False).encode())
    b.add_bytes("deps/routing.csv", pred[KEYS + ["job_id", "model_view"]].sort_values(KEYS).to_csv(index=False).encode())
    for p in ("pred", "maps", "schema", "inventory"):
        b.add_file(os.path.join(run_root, paths[p]), "deps/source/" + paths[p])

    pred["unit"] = pred["job_id"] + "|" + pred["model_view"]
    boundary = (pred["q3_final"] - 0.20).abs()
    ref = select_reference(pred, "unit", boundary, KEYS, per_unit=per_unit, cover_cols=("branch",))
    rows = inputs_frame.set_index(KEYS).loc[list(zip(ref["area_id"], ref["target_ord"])), columns]
    arr = np.ascontiguousarray(rows.to_numpy(dtype=np.float64))
    buf = io.BytesIO()
    np.save(buf, arr, allow_pickle=False)
    b.add_bytes("reference/inputs.npy", buf.getvalue())
    expected = ref[KEYS + ["unit", "branch"] + COMPARE].rename(columns={"branch": "route"})
    b.add_bytes("reference/expected.csv", expected.to_csv(index=False, float_format="%.17g").encode())
    b.add_bytes("loader/entry.py", ENTRY.encode())

    return b.finalize({
        "family": version.get("family"), "identity": version, "version_key": version_key, "source_key": "somalia_oracle_v2_q3",
        "lead_months": h, "arm": arm, "view": view,
        "information": {"status": "oracle_realized_future_information" if view == "C" else "per run contract (see view definition)",
                        "evidence": "IPCCHMLflow/naming.py ARMS: C = weather_oracle (realized weather); A/B/D information sets per the run's design"},
        "status": "complete" if not gaps else "retained_weights_missing_dependencies", "gaps": gaps,
        "fitted_units": int(pred["unit"].nunique()),
        "routing": {"table": "deps/routing.csv", "feature_order": "deps/feature_order.csv", "served_keys": int(len(pred)),
                    "routes_in_version": sorted(pred["branch"].unique())},
        "source": {"run_root": run_root, "final_predictions_sha256": sha256_file(os.path.join(run_root, paths["pred"]))},
        "code": {"loader": "thin reimplementation, accepted only through replay against the run's saved final predictions",
                 "rules_read_at_recorded_commit": {"git_head": manifest.get("git_head"), "git_dirty": manifest.get("git_dirty"),
                                                   "files": ["src/ipcch/somalia_oracle/q3opt.py", "src/ipcch/somalia_oracle/modeling.py",
                                                             "scripts/modeling/run_somalia_q3_optimization.py", "configs/somalia_q3_optimization.json"]}},
        "runtime": {"original": manifest.get("runtime"), "linux_loader_tested": runtime},
        "loader": {"entry": "loader/entry.py", "keys": KEYS, "call": "load(package_dir).predict(keys[area_id,target_ord], X)",
                   "inputs": f"float64 rows ({len(columns)} columns) of the run's saved feature matrix + provenance, deps/input_columns.json order",
                   "unserved_keys": "KeyError"},
        "reference": {"rows": int(len(expected)), "per_unit_cap": per_unit, "compare_columns": COMPARE,
                      "selection": "per job x model-view unit (cap): >=1 row per branch, half nearest q3_final=0.20, rest by key hash",
                      "routes_covered": sorted(expected["route"].unique()),
                      "rows_with_missing_features": int(np.isnan(arr).any(axis=1).sum())},
        "tolerance": {"declared_before_comparison": True,
                      "continuous": "abs(new-ref) <= 1e-3 + 1e-3*abs(ref) for q2/q3/q4/q5 raw, q3_mapped, q3_final; NaN only where the reference is NaN",
                      "phase": "not compared: the run's final predictions record no phase",
                      "routing": "unit (job|model view) and branch must equal the saved row exactly"},
    })
