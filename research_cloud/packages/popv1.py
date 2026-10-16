"""IPCCH population-history pop-v1 inference packages (unregistered retained run; one package per arm x horizon).

Run: ``Food_Crisis_Cluster/IPCCHPopulationHistoryExperiment/runs/pop-v1`` (supervisor note
``remaining-packages-supervisor.md``). Each main fold (horizon x target month) fitted one model per arm with the
frozen config (``freeze.json`` selections) and recorded it in ``main/model_identity/{fold}.json``. The current
``run_pipeline.py`` matches neither recorded code hash, so the loader is a thin reimplementation of the documented
contract, accepted only through replay against the run's saved ``reports/main_predictions.csv.gz``:

* inputs: the rich561 row (``data/rich561_X.npy`` columns, ``data/feature_schema.csv`` order) plus ``persistence_b``;
  ``binary_history_xgb`` reads the first 93 columns (original93), every other arm all 561;
* XGB classifiers: P(class 1) via ``classes_``; ``share_xgb`` (regressor): raw output; ``rich_rf``: the joblib
  RandomForest on the row imputed with the fold's *saved* positional fill values (NaN only; never refitted);
  constant routes answer the recorded constant;
* crisis score: correction_xgb ``raw`` if b == 0 else ``1 - raw``; the regressor ``clip(raw, 0, 1)``; else raw;
* decision: ``crisis > t_b`` (strict; t0 for b == 0, t1 for b == 1; ``+/-Infinity`` literals) from the arm/horizon
  selection; rows without history (served by fullpool_xgb only) use 0.5.

A key routes to its fold through the saved prediction rows (``deps/routing.csv``): exactly the keys the run scored.
Two saved fields are kept apart and both checked exactly: ``support`` (``E_history`` / ``E_no_history``: which rows a
model scores and which threshold applies) and ``route`` (``model`` or the fold's constant route, e.g.
``constant_single_class``).

Before any reference is built the run's frozen inventories are bound to every fold identity: ``freeze.json``
selections must hash (``json.dumps(..., sort_keys=True)``, run_pipeline.py:1034-1035) to the identity's
``selections_sha256``; ``inputs/feature-schema.json`` and ``inputs/candidate-configs.json`` must hash to its ``spec``;
and ``data/feature_schema.csv`` must list exactly the frozen rich order (original93, then the appended blocks in
``BLOCK_ORDER``, prepare_data.py:165-276).
"""
import hashlib
import io
import json
import os

import numpy as np
import pandas as pd

from research_cloud.packages.common import PackageBuilder, PackageError, ensure_local, select_reference, sha256_file

KEYS = ["admin_code", "target_ord"]
ARMS = ("binary_history_xgb", "rich_direct_xgb", "correction_xgb", "share_xgb", "rich_rf", "fullpool_xgb")
NO_HISTORY_THRESHOLD = 0.5
# prepare_data.py BLOCK_ORDER: the appended 468 columns follow exactly this block sequence
BLOCK_ORDER = ("observation_levels", "observation_timing", "changes", "observation_trends", "window_statistics",
               "window_support", "prior_binary_states", "threshold_distance", "window_crisis", "event_and_run")


def frozen_rich_order(schema):
    """original93 + appended blocks in BLOCK_ORDER, validated as load_frozen_spec does."""
    original = list(schema["original_features"])
    if tuple(schema["additional_blocks"]) != BLOCK_ORDER:
        raise PackageError("feature-schema.json additional_blocks order differs from BLOCK_ORDER")
    additional = [n for block in BLOCK_ORDER for n in schema["additional_blocks"][block]]
    rich = original + additional
    if (len(original), len(additional), len(rich)) != (schema["original_count"], schema["additional_count"], schema["rich_count"]) \
            or len(set(rich)) != len(rich):
        raise PackageError("feature-schema.json counts or names inconsistent")
    return rich


def selections_digest(selections):
    """run_pipeline.py:1034-1035."""
    return hashlib.sha256(json.dumps(selections, sort_keys=True).encode("utf-8")).hexdigest()

ENTRY = '''"""Keyed loader for one historical IPCCH pop-v1 package (generated; see package.json)."""
import json
import os

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _decode(value):
    if isinstance(value, str):
        return {"+Infinity": np.inf, "-Infinity": -np.inf}[value]
    return float(value)


class Model:
    def __init__(self, package_dir=ROOT):
        self.root = package_dir
        self.meta = json.load(open(os.path.join(package_dir, "package.json")))
        self.arm = self.meta["arm"]
        self.columns = json.load(open(os.path.join(package_dir, "deps", "input_columns.json")))
        self.units = json.load(open(os.path.join(package_dir, "deps", "units.json")))
        th = self.meta["decision"]
        self.t0, self.t1, self.t_none = _decode(th["t0"]), _decode(th["t1"]), _decode(th["no_history"])
        route = pd.read_csv(os.path.join(package_dir, "deps", "routing.csv"), dtype={"fold_id": str, "support": str})
        self.route = {(int(a), int(t)): (f, s) for a, t, f, s in route[["admin_code", "target_ord", "fold_id", "support"]].itertuples(index=False)}
        self._m = {}

    def _model(self, fold):
        unit = self.units[fold]
        if unit["constant"] is not None:
            return None
        path = os.path.join(self.root, "weights", unit["file"])
        if path not in self._m:
            if unit["estimator"] == "RandomForestClassifier":
                self._m[path] = joblib.load(path)
            else:
                m = xgb.XGBRegressor() if unit["estimator"] == "XGBRegressor" else xgb.XGBClassifier()
                m.load_model(path)
                self._m[path] = m
        return self._m[path]

    def _raw(self, fold, X):
        unit = self.units[fold]
        if unit["constant"] is not None:
            return np.full(len(X), float(unit["constant"]))
        width = 93 if self.arm == "binary_history_xgb" else X.shape[1]
        Z = np.asarray(X[:, :width], dtype=np.float64)
        if unit["estimator"] == "RandomForestClassifier":
            fills = json.load(open(os.path.join(self.root, "deps", "imputers", fold + ".json")))
            Z = Z.copy()
            for col, value in fills.items():   # OutOfRangeImputer.transform: NaN -> saved fill value, by position
                c = int(col)
                Z[np.isnan(Z[:, c]), c] = value
        model = self._model(fold)
        if unit["estimator"] == "XGBRegressor":
            return np.asarray(model.predict(Z), dtype=np.float64)
        proba = model.predict_proba(Z)
        classes = list(np.asarray(model.classes_).ravel())
        if 1 in classes:
            return np.asarray(proba[:, classes.index(1)], dtype=np.float64)
        return np.zeros(len(Z), dtype=np.float64)

    def predict(self, keys, X):
        """keys: DataFrame[admin_code, target_ord]; X: (n, 562) float64 = rich561 row + persistence_b."""
        X = np.asarray(X, dtype=np.float64)
        if X.shape[1] != len(self.columns):
            raise ValueError("X does not match deps/input_columns.json")
        routed = [self.route[(int(a), int(t))] for a, t in zip(keys["admin_code"], keys["target_ord"])]   # KeyError if unserved
        folds = np.array([f for f, _ in routed], dtype=object)
        b = X[:, -1]
        raw = np.full(len(X), np.nan)
        for fold in sorted(set(folds)):
            idx = np.flatnonzero(folds == fold)
            raw[idx] = self._raw(fold, X[idx, :-1])
        if self.arm == "correction_xgb":
            if not np.isfinite(b).all():
                raise ValueError("correction scores need b on every row")
            crisis = np.where(b == 0.0, raw, 1.0 - raw)
        elif self.arm == "share_xgb":
            crisis = np.clip(raw, 0.0, 1.0)
        else:
            crisis = raw
        history = np.array([s == "E_history" for _, s in routed])
        threshold = np.where(history, np.where(b == 0.0, self.t0, self.t1), self.t_none)
        out = keys.reset_index(drop=True)[["admin_code", "target_ord"]].copy()
        out["unit"] = folds
        out["route"] = [self.units[f]["route"] for f in folds]   # model / constant_* as recorded
        out["support"] = [s for _, s in routed]
        out["raw_score"], out["crisis_score"] = raw, crisis
        out["threshold"] = threshold
        out["decision"] = (crisis > threshold).astype(np.int64)
        return out


def load(package_dir=ROOT):
    return Model(package_dir)
'''


def build(out_dir, *, run_root, arm, horizon, inventory, matrix_sha256, runtime, per_unit=32):
    if arm not in ARMS:
        raise PackageError(f"unknown arm {arm}")
    h = int(horizon)
    fixed = ["freeze.json", "folds/calendar.csv", "data/keys.csv.gz", "data/feature_schema.csv", "inputs/feature-schema.json",
             "inputs/candidate-configs.json", "reports/main_predictions.csv.gz", "manifest.json"]
    ensure_local([os.path.join(run_root, p) for p in fixed + ["data/rich561_X.npy"]])
    freeze = json.load(open(os.path.join(run_root, "freeze.json")))
    if freeze["matrix_sha256"] != matrix_sha256:
        raise PackageError("rich561_X.npy digest differs from freeze.json matrix_sha256")
    selection = freeze["selections"][arm][str(h)]
    config = selection["config_id"]
    calendar = pd.read_csv(os.path.join(run_root, "folds/calendar.csv"))
    folds = calendar[(calendar["stage"] == "main") & (calendar["horizon_months"] == h)]
    keys = pd.read_csv(os.path.join(run_root, "data/keys.csv.gz"))
    schema = pd.read_csv(os.path.join(run_root, "data/feature_schema.csv"))
    X = np.load(os.path.join(run_root, "data/rich561_X.npy"), mmap_mode="r")
    if X.shape != (len(keys), 561):
        raise PackageError(f"rich561 matrix shape {X.shape} does not match {len(keys)} keys x 561")
    schema = schema.sort_values("position")
    if schema["position"].tolist() != list(range(561)):
        raise PackageError("data/feature_schema.csv does not list positions 0..560")
    frozen_schema_path = os.path.join(run_root, "inputs/feature-schema.json")
    frozen_schema_sha = sha256_file(frozen_schema_path)
    configs_sha = sha256_file(os.path.join(run_root, "inputs/candidate-configs.json"))
    rich = frozen_rich_order(json.load(open(frozen_schema_path)))
    if schema["name"].astype(str).tolist() != rich:
        raise PackageError("data/feature_schema.csv order differs from the frozen rich order (original93 first)")
    columns = rich + ["persistence_b"]
    selections_sha = selections_digest(freeze["selections"])
    keys_sha = sha256_file(os.path.join(run_root, "data/keys.csv.gz"))
    calendar_sha = sha256_file(os.path.join(run_root, "folds/calendar.csv"))

    pred = pd.read_csv(os.path.join(run_root, "reports/main_predictions.csv.gz"))
    rows = pred[(pred["arm"] == arm) & (pred["horizon_months"] == h)].copy()
    if rows.empty:
        raise PackageError(f"no saved predictions for {arm} h{h}")
    if set(rows["config_id"]) != {config}:
        raise PackageError(f"saved config ids {sorted(set(rows['config_id']))} differ from the frozen selection {config}")
    rows["target_ord"] = keys.loc[rows["row_index"], "target_ord"].to_numpy()
    if not (keys.loc[rows["row_index"], "admin_code"].to_numpy() == rows["admin_code"].to_numpy()).all():
        raise PackageError("row_index does not resolve to the saved admin_code")
    if rows.duplicated(KEYS).any():
        raise PackageError("a key is scored twice for this arm/horizon")
    if not set(rows["fold_id"]) <= set(folds["fold_id"]):
        raise PackageError("saved predictions name folds outside the main calendar")

    files = {f["path"]: f for f in inventory}
    idents = {}
    for fold in sorted(rows["fold_id"].unique()):   # every fold identity is verified before a package is started
        ident_rel = f"main/model_identity/{fold}.json"
        ensure_local([os.path.join(run_root, ident_rel)])
        ident = idents[fold] = json.load(open(os.path.join(run_root, ident_rel)))
        idn = ident["identity"]
        if idn["keys_sha256"] != keys_sha or idn["calendar_sha256"] != calendar_sha or idn["matrix_sha256"] != matrix_sha256:
            raise PackageError(f"{fold}: identity does not bind the run's keys/calendar/matrix")
        if idn.get("selections_sha256") != selections_sha:
            raise PackageError(f"{fold}: freeze.json selections do not hash to the identity's selections_sha256")
        spec = idn.get("spec") or {}
        if (spec.get("feature_schema_sha256"), spec.get("candidate_configs_sha256")) != (frozen_schema_sha, configs_sha) \
                or (spec.get("original_count"), spec.get("rich_count")) != (93, 561):
            raise PackageError(f"{fold}: frozen feature schema / candidate configs differ from the identity's spec")
    units, gaps, b = {}, [], PackageBuilder(out_dir)
    for fold, ident in idents.items():
        ident_rel = f"main/model_identity/{fold}.json"
        entry = ident["models"].get(f"{arm}::{config}")
        if entry is None:
            gaps.append(f"{fold}: no {arm}::{config} model identity")
            continue
        unit = {"estimator": entry["estimator"], "constant": entry["constant"], "route": entry["route"], "file": None}
        if entry["constant"] is None:
            rel = entry["model"]["path"]
            name = os.path.basename(rel)
            rec = files.get(name)
            if rec is None or rec["sha256"] != entry["model"]["sha256"] or rec["bytes"] != entry["model"]["bytes"]:
                gaps.append(f"{fold}: model {name} not in the verified inventory with the identity's sha/bytes")
                continue
            ensure_local([os.path.join(run_root, rel)])
            b.add_file(os.path.join(run_root, rel), f"weights/{name}", entry["model"]["sha256"], entry["model"]["bytes"])
            unit["file"] = name
        if entry["estimator"] == "RandomForestClassifier":
            imp = ident["imputer"]
            if imp.get("strategy") != "max_plus" or len(imp["fill_values"]) != imp["columns"]:
                raise PackageError(f"{fold}: saved imputer record incomplete")
            b.add_json(f"deps/imputers/{fold}.json", imp["fill_values"])
        b.add_file(os.path.join(run_root, ident_rel), f"deps/source/{ident_rel}")
        units[fold] = unit
    saved_route = rows.groupby("fold_id")["route"].unique()
    for fold, unit in units.items():
        if list(saved_route[fold]) != [unit["route"]]:
            raise PackageError(f"{fold}: saved route {list(saved_route[fold])} differs from the identity route {unit['route']}")
    b.add_json("deps/units.json", units)
    b.add_json("deps/input_columns.json", columns)
    b.add_bytes("deps/feature_order.csv", pd.DataFrame({"name": columns}).to_csv(index=False).encode())
    b.add_bytes("deps/routing.csv", rows[KEYS + ["fold_id", "support", "route"]].sort_values(KEYS).to_csv(index=False).encode())
    for p in fixed:
        b.add_file(os.path.join(run_root, p), f"deps/source/{p}")

    rows["unit"] = rows["fold_id"]   # route and support stay the saved values
    boundary = (rows["crisis_score"] - rows["threshold"].replace([np.inf, -np.inf], np.nan)).abs().fillna(1.0)
    ref = select_reference(rows, "unit", boundary, KEYS, per_unit=per_unit, cover_cols=("route", "support"))
    idx = ref["row_index"].to_numpy()
    arr = np.column_stack([np.asarray(X[idx], dtype=np.float64), keys.loc[idx, "persistence_b"].to_numpy(dtype=np.float64)])
    buf = io.BytesIO()
    np.save(buf, np.ascontiguousarray(arr), allow_pickle=False)
    b.add_bytes("reference/inputs.npy", buf.getvalue())
    expected = ref[KEYS + ["unit", "route", "support", "raw_score", "crisis_score", "decision"]]
    b.add_bytes("reference/expected.csv", expected.to_csv(index=False, float_format="%.17g").encode())
    b.add_bytes("loader/entry.py", ENTRY.encode())
    manifest = json.load(open(os.path.join(run_root, "manifest.json")))
    no_history = arm == "fullpool_xgb"
    return b.finalize({
        "family": "ipcch_population_history", "identity": {"run": "pop-v1", "arm": arm, "horizon_months": h, "config_id": config,
                                                           "registry": "unregistered retained research run (package per arm x horizon)"},
        "arm": arm, "lead_months": h,
        "status": "complete" if not gaps else "retained_weights_missing_dependencies", "gaps": gaps,
        "fitted_units": len(units), "constant_units": sorted(f for f, u in units.items() if u["constant"] is not None),
        "decision": {"rule": "crisis_score > t_b (strict); t0 for b == 0, t1 for b == 1",
                     "t0": selection["t0"], "t1": selection["t1"],
                     "no_history": NO_HISTORY_THRESHOLD if no_history else "+Infinity",
                     "source": "freeze.json selections; run_pipeline.py apply_thresholds; report_results build_scored_table"},
        "routing": {"table": "deps/routing.csv", "feature_order": "deps/feature_order.csv", "served_keys": int(len(rows)),
                    "routes_in_version": sorted(rows["route"].unique()), "supports_in_version": sorted(rows["support"].unique())},
        "source": {"run_root": run_root, "matrix_sha256": matrix_sha256, "keys_sha256": keys_sha, "calendar_sha256": calendar_sha,
                   "selections_sha256": selections_sha, "feature_schema_sha256": frozen_schema_sha, "candidate_configs_sha256": configs_sha,
                   "main_predictions_sha256": sha256_file(os.path.join(run_root, "reports/main_predictions.csv.gz")),
                   "freeze_code_sha256": freeze.get("code_sha256")},
        "code": {"loader": "thin reimplementation of the documented contract; the current run_pipeline.py matches neither "
                           "recorded code hash, so acceptance is by replay against the saved predictions",
                 "anchors": ["run_pipeline.py ARMS :84-90", "class1_probability / crisis_oriented :292-320,468-475",
                             "OutOfRangeImputer (baseline GeoRFBaseline src/customize/customize.py) with saved fill values",
                             "apply_thresholds :978-1000"]},
        "runtime": {"original": manifest.get("runtime"), "linux_loader_tested": runtime},
        "loader": {"entry": "loader/entry.py", "keys": KEYS, "call": "load(package_dir).predict(keys[admin_code,target_ord], X)",
                   "inputs": "float64 rows: rich561 (deps/input_columns.json order, NaN = missing) + persistence_b",
                   "unserved_keys": "KeyError"},
        "reference": {"rows": int(len(expected)), "per_unit_cap": per_unit, "compare_columns": ["raw_score", "crisis_score", "decision"],
                      "exact_columns": ["support"],
                      "selection": "per fold (cap): >=1 row per route and per support, half nearest the decision threshold, rest by key hash",
                      "routes_covered": sorted(expected["route"].unique()), "supports_covered": sorted(expected["support"].unique()),
                      "rows_with_missing_features": int(np.isnan(arr[:, :561]).any(axis=1).sum())},
        "tolerance": {"declared_before_comparison": True,
                      "continuous": "abs(new-ref) <= 1e-3 + 1e-3*abs(ref) for raw_score and crisis_score",
                      "decision": "compared exactly (within the same tolerance on 0/1)",
                      "routing": "fold (unit), route and support must each equal the saved row exactly"},
    })
