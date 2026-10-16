"""Package builder for IPCCH Somalia-oracle registered versions (runs somalia_oracle/v2_q3, v3_validity, v4_calibrated_d).

Rules were read at each run's recorded commit (manifest ``git_head``), not the current checkout:
- v2_q3 (d75378d): ``src/ipcch/somalia_oracle/q3opt.py`` final_task / predict_q3 / apply_branches /
  bound_share / Q3Mapping, ``modeling.py`` FittedRegressor, ``configs/somalia_q3_optimization.json``
  (residual baseline ``residual_baseline``, source ``history_obs1_source_ord``);
- v3_validity (1f3bfcec): ``augexp.py`` final_task / fit_predict_q3 / _baseline (same q3opt mapping and
  bound; label branch original/augmented in model and mapping identity).
Per saved final-prediction row of a version: X = the run's saved ``features/feature_matrix_hXX`` row
(area_id, target_ord) in the version's schema; q2/q4/q5 and q3_direct = XGBRegressor.predict(X) (or a
saved constant); a unit with a ``q3_residual_delta`` model predicts q3 = residual_baseline + delta where the
baseline is supported (finite and history_obs1_source_ord >= 0, from ``ledgers/row_provenance_hXX``),
else direct (branch fallback_direct); then the recorded per-branch calibration mapping and the [0, 1]
bound. All raw/mapped/final columns the run saved are compared. The loader is a thin reimplementation,
accepted only through that replay.
"""
import io
import json
import os

import numpy as np
import pandas as pd

from research_cloud.packages.common import PackageBuilder, PackageError, ensure_local, select_reference, sha256_file

KEYS = ["area_id", "target_ord"]
# IPCCH IPCCHMLflow/naming.py ARMS (raw arm -> readable arm), inverted
VIEW_OF_ARM = {"existing_predictors": "A", "seasonal_climate": "B", "weather_oracle": "C",
               "share_history_direct": "D_direct", "share_history_residual": "D_residual",
               "share_history_selected": "D_selected"}
# src/ipcch/somalia_oracle/__init__.py:56 (identical at d75378d, 1f3bfcec, a787257)
ORACLE_WEATHER_VARIABLES = ("Rainf_f_tavg_mean", "Tair_f_tavg_mean")
VINTAGE_LIMITATION = ("inputs are the run's saved feature matrices built from revised/latest-vintage sources; real-time "
                      "vintages are not certified by this migration")


def oracle_feature_names(horizon):
    return [f"oracle_{var}_o{k}" for k in range(1, min(int(horizon), 6) + 1) for var in ORACLE_WEATHER_VARIABLES]


def information_status(schema, horizon):
    """Realized-future (oracle) inputs actually in the version's schema; H0 has none by definition. Says nothing
    about data vintages."""
    declared = oracle_feature_names(horizon)
    served = [c for c in schema if c in declared]
    stray = [c for c in schema if c.startswith("oracle_") and c not in declared]
    if stray:
        raise PackageError(f"schema has oracle-named inputs outside the source definition: {stray[:3]}")
    if served:
        return {"status": "oracle_realized_future_information", "oracle_features": served,
                "evidence": f"schema serves {len(served)} oracle_feature_names({horizon}) inputs"}
    return {"status": "no_declared_oracle_input", "evidence": f"schema serves none of oracle_feature_names({horizon})"}


SCHEMA_ARM = {"A": "A", "B": "B", "C": "C", "D_direct": "D", "D_residual": "D", "D_selected": "D"}   # q3opt.VIEW_SPEC


def _v2_rows(pred, plan_version):
    view = VIEW_OF_ARM[plan_version["arm"]]
    rows = pred[(pred["view"] == view) & (pred["horizon"] == int(plan_version["lead"]))].copy()
    reused = rows["reused_from"].fillna("").astype(str)
    rows["model_view"] = reused.where(reused != "", view)
    rows["stem"] = rows["job_id"] + "_" + rows["model_view"]
    rows["map_key"] = rows["job_id"] + "|" + rows["model_view"]
    return rows, view, f"h{int(plan_version['lead']):02d}_{SCHEMA_ARM[view]}"


def _v2_maps(maps):
    return maps.assign(map_key=maps["job_id"] + "|" + maps["view"], prediction_branch=maps["branch"])


def _v3_rows(pred, plan_version):
    view = VIEW_OF_ARM[plan_version["arm"]]
    label = {"somalia_validity_observed": "original", "somalia_validity_augmented": "augmented"}[plan_version["family"]]
    rows = pred[(pred["view"] == view) & (pred["label_branch"] == label) & (pred["horizon"] == int(plan_version["lead"]))].copy()
    rows["model_view"] = view
    rows["stem"] = rows["job_id"] + "_" + label + "_" + view
    rows["map_key"] = rows["job_id"] + "|" + label + "|" + view
    return rows, view, f"h{int(plan_version['lead']):02d}_D"


def _v3_maps(maps):
    return maps.assign(map_key=maps["job_id"] + "|" + maps["branch"] + "|" + maps["view"])


def _v4_rows(pred, plan_version):
    setting = {"somalia_calibrated_observed": "original", "somalia_calibrated_augmented": "augmented"}[plan_version["family"]]
    rows = pred[(pred["data_setting"] == setting) & (pred["horizon"] == int(plan_version["lead"]))].copy()
    rows["model_view"] = "D_calibrated"
    rows["stem"] = rows["job_id"]
    rows["map_key"] = rows["job_id"]
    rows["branch"] = rows["prediction_branch"]
    return rows, "D_calibrated", f"h{int(plan_version['lead']):02d}_D"


def _v4_maps(maps):
    return maps.assign(map_key=maps["job_id"])


V4_OVERRIDE_FILES = {"override_features": "features/final_override_features.csv.gz",
                     "history_overrides": "selection/history_overrides.csv.gz"}


def _v4_overrides(sources, rows, inputs, schema):
    """augexp._v4_matrix (a787257): a test row exposed to its job's test families uses recomputed history.
    The run saved those exact feature rows (features/final_override_features) and their baseline/support
    (selection/history_overrides, role test_prediction). `sources` maps V4_OVERRIDE_FILES keys to hash-verified paths.
    Within this version's served (job, key) set the two files must correspond one-to-one."""
    feats = pd.read_csv(sources["override_features"], float_precision="round_trip")
    hist = pd.read_csv(sources["history_overrides"], float_precision="round_trip")
    hist = hist[hist["role"] == "test_prediction"].assign(job_id=lambda d: d["scope"].str.removeprefix("job:"))
    jk = ["job_id"] + KEYS
    for name, frame in (("override features", feats), ("history overrides", hist)):
        if frame.duplicated(jk).any():
            raise PackageError(f"{name} repeat a (job, area, target) key")
    served = set(zip(rows["job_id"], rows["area_id"], rows["target_ord"]))
    def mine(frame):   # boolean array mask, so an empty frame keeps its columns
        return frame.loc[np.array([k in served for k in zip(frame["job_id"], frame["area_id"], frame["target_ord"])], dtype=bool)]
    mine_f, mine_h = mine(feats), mine(hist)
    f_keys, h_keys = set(map(tuple, mine_f[jk].to_numpy().tolist())), set(map(tuple, mine_h[jk].to_numpy().tolist()))
    if f_keys != h_keys:
        raise PackageError(f"override features/history disagree for this version: "
                           f"{sorted(f_keys - h_keys)[:3]} lack history, {sorted(h_keys - f_keys)[:3]} lack features")
    hist_of = {k: r for k, r in zip(map(tuple, mine_h[jk].to_numpy().tolist()), mine_h.to_dict("records"))}
    applied = []
    out = inputs.set_index(KEYS)
    for r in mine_f.to_dict("records"):
        key = (r["area_id"], r["target_ord"])
        if key not in out.index:
            raise PackageError(f"override for {r['job_id']} {key}: key absent from the saved feature matrix")
        h = hist_of[(r["job_id"],) + key]
        b, src = float(h["context_hist_q3_obs1"]), h["context_obs1_source_ord"]
        ok = bool(np.isfinite(b) and not pd.isna(src) and int(src) >= 0)
        # the override X row holds the float32 model input; the residual adds the float64 context baseline
        if ok != bool(h["context_base_ok"]) or (np.isfinite(b) and np.float32(b) != np.float32(r["hist_q3_obs1"])):
            raise PackageError(f"override for {r['job_id']} {key}: recorded baseline/support disagree")
        out.loc[key, schema] = [r[c] for c in schema]
        out.loc[key, "history_obs1_source_ord"] = src
        out.loc[key, "residual_baseline"] = b
        applied.append({"job_id": r["job_id"], "area_id": key[0], "target_ord": key[1], "hx": r["hx"], "base_ok": ok})
    return out.reset_index(), applied


SPECS = {
    "somalia_oracle_v2_q3": {"run": "results/experiments/somalia_oracle/v2_q3", "rows": _v2_rows, "maps": _v2_maps,
                             "compare": ["q2_raw", "q3_raw", "q4_raw", "q5_raw", "q3_mapped", "q3_final"],
                             "rule_files": ["src/ipcch/somalia_oracle/q3opt.py", "src/ipcch/somalia_oracle/modeling.py",
                                            "scripts/modeling/run_somalia_q3_optimization.py", "configs/somalia_q3_optimization.json"]},
    "somalia_oracle_v3_validity": {"run": "results/experiments/somalia_oracle/v3_validity", "rows": _v3_rows, "maps": _v3_maps,
                                   "compare": ["q2_raw", "q3_raw", "q4_raw", "q5_raw", "q3_final"],
                                   "rule_files": ["src/ipcch/somalia_oracle/augexp.py", "src/ipcch/somalia_oracle/q3opt.py",
                                                  "src/ipcch/somalia_oracle/modeling.py",
                                                  "scripts/modeling/run_somalia_validity_augmentation.py"]},
    "somalia_oracle_v4_calibrated_d": {"run": "results/experiments/somalia_oracle/v4_calibrated_d", "rows": _v4_rows, "maps": _v4_maps,
                                       "override": _v4_overrides, "override_files": V4_OVERRIDE_FILES,
                                       "compare": ["q2_raw", "q3_raw", "q4_raw", "q5_raw", "q3_final"],
                                       "rule_files": ["src/ipcch/somalia_oracle/augexp.py (v4_final_task, v4_fit_predict, _v4_matrix)",
                                                      "src/ipcch/somalia_oracle/q3opt.py", "src/ipcch/somalia_oracle/modeling.py",
                                                      "scripts/modeling/run_somalia_v4_calibrated_d.py"]},
}

ENTRY = '''"""Keyed loader for one historical IPCCH Somalia-oracle package (generated; see package.json)."""
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
        self.columns = json.load(open(os.path.join(package_dir, "deps", "input_columns.json")))
        self.schema = json.load(open(os.path.join(package_dir, "deps", "schema_columns.json")))
        route = pd.read_csv(os.path.join(package_dir, "deps", "routing.csv"), dtype=str)
        self.route = {(int(a), int(t)): (s, m) for a, t, s, m in route[["area_id", "target_ord", "stem", "map_key"]].itertuples(index=False)}
        maps = pd.read_csv(os.path.join(package_dir, "deps", "calibration_mappings.csv"))
        self.maps = {(r["map_key"], r["prediction_branch"]): r for r in maps.to_dict("records")}
        self.job_available = json.load(open(os.path.join(package_dir, "deps", "job_calibration.json")))
        self._m = {}

    def has(self, stem, target):
        return any(os.path.exists(os.path.join(self.root, "weights", f"{stem}_{target}.{ext}")) for ext in ("ubj", "json"))

    def predict_target(self, stem, target, X):
        ubj = os.path.join(self.root, "weights", f"{stem}_{target}.ubj")
        if os.path.exists(ubj):
            if ubj not in self._m:
                m = xgb.XGBRegressor()
                m.load_model(ubj)
                self._m[ubj] = m
            return self._m[ubj].predict(X).astype(np.float64)
        const = json.load(open(os.path.join(self.root, "weights", f"{stem}_{target}.json")))   # saved constant model
        return np.full(X.shape[0], float(const["value"]), dtype=np.float64)

    def calibrate(self, map_key, branch, raw):
        m = self.maps.get((map_key, branch))
        if m is None or m["status"] != "ok":
            return np.full(raw.shape, np.nan)
        if m["method"] == "none":
            return raw.copy()
        if m["method"] == "shift":
            return raw - float(m["shift"])
        return np.interp(raw, json.loads(m["isotonic_x"]), json.loads(m["isotonic_y"]))   # IsotonicRegression clip

    def predict(self, keys, X):
        """keys: DataFrame[area_id, target_ord]; X: (n, len(input_columns)) float64 rows of the run's saved
        feature matrix + provenance in deps/input_columns.json order."""
        frame = pd.DataFrame(np.asarray(X, dtype=np.float64), columns=self.columns)
        out = keys[["area_id", "target_ord"]].reset_index(drop=True).copy()
        resolved = []
        for k in zip(out["area_id"].astype(int), out["target_ord"].astype(int)):
            if k not in self.route:
                raise KeyError(f"key {k} is not served by this package")
            resolved.append(self.route[k])
        stems = np.array([s for s, _ in resolved], dtype=object)
        out["unit"] = stems
        vals = {c: np.full(len(out), np.nan) for c in ("q2_raw", "q3_raw", "q4_raw", "q5_raw", "q3_mapped")}
        branch = np.empty(len(out), dtype=object)
        for stem in sorted(set(stems)):
            idx = np.flatnonzero(stems == stem)
            map_key = resolved[idx[0]][1]
            Xs = frame.iloc[idx][self.schema].to_numpy(dtype=np.float64)
            for t in ("q2", "q4", "q5"):
                vals[t + "_raw"][idx] = self.predict_target(stem, t, Xs)
            raw = self.predict_target(stem, "q3_direct", Xs)
            br = np.full(len(idx), "direct", dtype=object)
            if self.has(stem, "q3_residual_delta"):
                b = frame["residual_baseline"].to_numpy()[idx]
                src = frame["history_obs1_source_ord"].to_numpy()[idx]
                ok = np.isfinite(b) & (np.nan_to_num(src, nan=-1) >= 0)
                res = np.where(ok, b + self.predict_target(stem, "q3_residual_delta", Xs), np.nan)
                br = np.where(np.isfinite(res), "residual", "fallback_direct").astype(object)
                raw = np.where(np.isfinite(res), res, raw)
            vals["q3_raw"][idx] = raw
            branch[idx] = br
            # q3opt.apply_branches over the ORIGINAL full job: if any branch present in that job lacks a supported
            # mapping, the job has no mapped/final q3. Frozen per job at build time, independent of this request.
            if self.job_available[map_key]["available"]:
                for name in sorted(set(br)):
                    sel = br == name
                    vals["q3_mapped"][idx[sel]] = self.calibrate(map_key, name, raw[sel])
        for c, v in vals.items():
            out[c] = v
        out["q3_final"] = np.clip(out["q3_mapped"], 0.0, 1.0)
        out["route"] = branch
        return out


def load(package_dir=ROOT):
    return Model(package_dir)
'''


def build(out_dir, *, source_key, ipcch_root, plan_version, version_key, version, runtime, per_unit=32):
    spec = SPECS[source_key]
    run_root = os.path.join(ipcch_root, spec["run"])
    h = int(plan_version["lead"])
    hh = f"h{h:02d}"
    paths = {"pred": "predictions/final_predictions.csv.gz", "maps": "fits/calibration_mappings.csv",
             "schema": "features/feature_schema.json", "matrix": f"features/feature_matrix_{hh}.csv.gz",
             "prov": f"ledgers/row_provenance_{hh}.csv.gz", "inventory": "models/model_inventory.csv", "manifest": "manifest.json"}
    paths.update(spec.get("override_files", {}))
    recorded = {m["path"]: m for m in plan_version["members"]}
    members = {os.path.basename(m["path"]): m for m in plan_version["members"] if m["role"] == "booster"}
    ensure_local([os.path.join(run_root, p) for p in paths.values()] + [os.path.join(ipcch_root, m["path"]) for m in members.values()])
    manifest = json.load(open(os.path.join(run_root, paths["manifest"])))
    pred = pd.read_csv(os.path.join(run_root, paths["pred"]), low_memory=False, dtype={"reused_from": str})
    rows, view, schema_key = spec["rows"](pred, plan_version)
    if rows.empty or rows.duplicated(KEYS).any():
        raise PackageError(f"{version_key}: saved rows missing or keys repeated")
    gaps = []
    for stem in sorted(rows["stem"].unique()):
        for t in ("q2", "q3_direct", "q4", "q5"):
            if f"{stem}_{t}.ubj" not in members and f"{stem}_{t}.json" not in members:
                gaps.append(f"model {stem}_{t} absent from the version's plan members")
    branch_col = "branch" if "branch" in rows else "prediction_branch"
    residual_rows = rows[branch_col].isin(["residual", "fallback_direct"])
    for stem in sorted(rows.loc[residual_rows, "stem"].unique()):
        if f"{stem}_q3_residual_delta.ubj" not in members and f"{stem}_q3_residual_delta.json" not in members:
            gaps.append(f"residual delta model for {stem} absent from the version's plan members")
    schema = json.load(open(os.path.join(run_root, paths["schema"])))[schema_key]
    matrix = pd.read_csv(os.path.join(run_root, paths["matrix"]), float_precision="round_trip")
    prov = pd.read_csv(os.path.join(run_root, paths["prov"]), float_precision="round_trip")
    if matrix.duplicated(KEYS).any() or prov.duplicated(KEYS).any():
        raise PackageError("feature matrix or provenance ledger repeats a key")
    inputs = matrix.merge(prov[KEYS + ["history_obs1_source_ord"]], on=KEYS, how="left", validate="one_to_one")
    inputs["residual_baseline"] = inputs["hist_q3_obs1"]   # frame baseline; history overrides replace it below
    missing_cols = [c for c in schema + ["hist_q3_obs1"] if c not in inputs]
    if missing_cols:
        raise PackageError(f"saved feature matrix lacks {missing_cols[:3]}")
    overrides_applied = []
    if "override" in spec:
        sources = {}
        for k, p in spec["override_files"].items():   # recorded plan members only; verified before they are read
            m = recorded.get(os.path.join(spec["run"], p))
            if m is None:
                raise PackageError(f"{version_key}: override dependency {p} is not a recorded plan member")
            if sha256_file(os.path.join(run_root, p)) != m["sha256"]:
                raise PackageError(f"{version_key}: override dependency {p} differs from its recorded sha256")
            sources[k] = os.path.join(run_root, p)
        inputs, overrides_applied = spec["override"](sources, rows, inputs, schema)
    columns = [c for c in inputs.columns if c not in KEYS]
    stems = set(rows["stem"])
    used_members = sorted(n for n in members if any(n.startswith(s + "_") for s in stems))

    b = PackageBuilder(out_dir)
    for name in used_members:
        m = members[name]
        b.add_file(os.path.join(ipcch_root, m["path"]), f"weights/{name}", m["sha256"], m["bytes"])
    maps = spec["maps"](pd.read_csv(os.path.join(run_root, paths["maps"])))
    maps = maps[maps["map_key"].isin(set(rows["map_key"]))]
    branch_col_full = "branch" if "branch" in rows else "prediction_branch"
    status_of = {(k, br): st for k, br, st in maps[["map_key", "prediction_branch", "status"]].itertuples(index=False)}
    job_cal = {}
    for key, part in rows.groupby("map_key"):
        branches = sorted(part[branch_col_full].astype(str).unique())
        available = all(status_of.get((key, br)) == "ok" for br in branches)
        rec_status = sorted(part["calibration_status"].astype(str).unique())
        if rec_status != (["ok"] if available else ["unavailable"]):
            raise PackageError(f"job {key}: derived calibration availability {available} disagrees with the recorded status {rec_status}")
        job_cal[key] = {"available": available, "job_branches": branches, "recorded_calibration_status": rec_status[0]}
    b.add_json("deps/job_calibration.json", job_cal)
    b.add_bytes("deps/calibration_mappings.csv", maps.to_csv(index=False).encode())
    b.add_json("deps/schema_columns.json", schema)
    b.add_json("deps/input_columns.json", columns)
    b.add_bytes("deps/feature_order.csv", pd.DataFrame({"name": columns}).to_csv(index=False).encode())
    b.add_bytes("deps/routing.csv", rows[KEYS + ["stem", "map_key"]].sort_values(KEYS).to_csv(index=False).encode())
    for p in ("pred", "maps", "schema", "inventory", "manifest", "matrix", "prov") + tuple(spec.get("override_files", {})):
        rel = os.path.join(spec["run"], paths[p])
        m = recorded.get(rel)   # enforce the plan's recorded bytes/sha256 wherever the dependency was recorded
        b.add_file(os.path.join(run_root, paths[p]), "deps/source/" + paths[p],
                   m["sha256"] if m else None, m["bytes"] if m else None)

    rows["unit"], rows["route"] = rows["stem"], rows[branch_col]
    over = {(o["area_id"], o["target_ord"]) for o in overrides_applied}
    rows["input_source"] = ["history_override" if k in over else "feature_matrix" for k in zip(rows["area_id"], rows["target_ord"])]
    boundary = (rows["q3_final"] - 0.20).abs()
    ref = select_reference(rows, "unit", boundary.fillna(1.0), KEYS, per_unit=per_unit, cover_cols=("route", "input_source"))
    arr = np.ascontiguousarray(inputs.set_index(KEYS).loc[list(zip(ref["area_id"], ref["target_ord"])), columns].to_numpy(dtype=np.float64))
    buf = io.BytesIO()
    np.save(buf, arr, allow_pickle=False)
    b.add_bytes("reference/inputs.npy", buf.getvalue())
    expected = ref[KEYS + ["unit", "route"] + spec["compare"]]
    b.add_bytes("reference/expected.csv", expected.to_csv(index=False, float_format="%.17g").encode())
    b.add_bytes("loader/entry.py", ENTRY.encode())

    return b.finalize({
        "family": version.get("family"), "identity": version, "version_key": version_key, "source_key": source_key,
        "lead_months": h, "arm": plan_version["arm"], "view": view,
        "information": information_status(schema, h),
        "vintage_limitation": VINTAGE_LIMITATION,
        "status": "complete" if not gaps else "retained_weights_missing_dependencies", "gaps": gaps,
        "fitted_units": int(rows["stem"].nunique()),
        "dependency_hashes": {"enforced_against_plan": sorted(os.path.join(spec["run"], paths[p]) for p in paths
                                                              if os.path.join(spec["run"], paths[p]) in recorded),
                              "fresh_hash_only": sorted(os.path.join(spec["run"], paths[p]) for p in paths
                                                        if os.path.join(spec["run"], paths[p]) not in recorded)},
        "history_overrides_applied": overrides_applied,
        "job_calibration_scope": "frozen per original job (deps/job_calibration.json); never derived from a request batch",
        "routing": {"table": "deps/routing.csv", "feature_order": "deps/feature_order.csv", "served_keys": int(len(rows)),
                    "routes_in_version": sorted(rows["route"].astype(str).unique())},
        "source": {"run_root": run_root, "final_predictions_sha256": sha256_file(os.path.join(run_root, paths["pred"])),
                   "override_dependencies": {k: {"path": "deps/source/" + p, **{f: recorded[os.path.join(spec["run"], p)][f]
                                                                                 for f in ("sha256", "bytes")}}
                                             for k, p in spec.get("override_files", {}).items()}},
        "code": {"loader": "thin reimplementation, accepted only through replay against the run's saved final predictions",
                 "rules_read_at_recorded_commit": {"git_head": manifest.get("git_head") or (manifest.get("git") or {}).get("head"),
                                                   "git_dirty": manifest.get("git_dirty", (manifest.get("git") or {}).get("dirty_paths")),
                                                   "files": spec["rule_files"]}},
        "runtime": {"original": manifest.get("runtime"), "linux_loader_tested": runtime},
        "loader": {"entry": "loader/entry.py", "keys": KEYS, "call": "load(package_dir).predict(keys[area_id,target_ord], X)",
                   "inputs": f"float64 rows ({len(columns)} columns) of the run's saved feature matrix + provenance (deps/input_columns.json)",
                   "unserved_keys": "KeyError"},
        "reference": {"rows": int(len(expected)), "per_unit_cap": per_unit, "compare_columns": spec["compare"],
                      "selection": "per model unit (cap): >=1 row per prediction branch, half nearest q3_final=0.20, rest by key hash",
                      "routes_covered": sorted(expected["route"].astype(str).unique()),
                      "rows_with_missing_features": int(np.isnan(arr).any(axis=1).sum())},
        "tolerance": {"declared_before_comparison": True,
                      "continuous": "abs(new-ref) <= 1e-3 + 1e-3*abs(ref) for every compared column; NaN only where the reference is NaN",
                      "phase": "not compared: the run's final predictions record no phase",
                      "routing": "model unit and prediction branch must equal the saved row exactly"},
    })
