"""IPCCH Somalia-oracle v1 (``somalia_oracle_information``) historical inference packages.

Rules read at the run's recorded commit f576e690 (``src/ipcch/somalia_oracle/modeling.py``; supervisor note
``somalia-v1-package-supervisor.md``): each registered version (arm A/B/C/D x horizon; C has no H0 version, its H0
view aliases B) holds 5 jobs x 4 direct cumulative regressors q2..q5 (``{job}_{arm}_{q}.ubj``). Inference casts the
arm's ordered schema columns (``feature_schema.json[hHH_<arm>]``) of the saved feature matrix to float32 and
predicts each target directly: no imputer, scaler, calibration, residual baseline, clipping or monotone repair, and
no averaging across jobs, arms or seeds. Phase is the unrounded descending q5->q2 decode with ``>= 0.2``, default 1
(modeling.py:55-66); a non-finite cumulative output is an error. Every saved prediction row (all five target months,
primary-evaluation or not) is servable: a key routes to the job of its target month.

Dependencies are bound twice: the importer plan's run-level ``files`` records (sha256 + bytes, enforced on copy)
and the run manifest's ``written`` hashes (cross-checked), so the matrices and predictions, which are not
per-version plan members, still carry recorded identities.
"""
import io
import json
import os

import numpy as np
import pandas as pd

from research_cloud.packages.common import PackageBuilder, PackageError, ensure_local, select_reference, sha256_file
from research_cloud.packages.somalia import VINTAGE_LIMITATION, information_status

KEYS = ["area_id", "target_ord"]
RUN = "results/experiments/somalia_oracle/v1"
ARM_LETTER = {"existing_predictors": "A", "seasonal_climate": "B", "weather_oracle": "C",
              "weather_oracle_with_share_history": "D"}
TARGETS = ("q2", "q3", "q4", "q5")
THRESHOLD = 0.2
RULE_FILES = ["src/ipcch/somalia_oracle/modeling.py (phase_from_predictions :55-66; float32 cast :167; predict :238-245)",
              "src/ipcch/somalia_oracle/pipeline.py (valid-score keys :284-293; H0 C alias :323-364)",
              "scripts/modeling/run_somalia_oracle_experiment.py (feature matrices :64-71)"]

ENTRY = '''"""Keyed loader for one historical IPCCH Somalia-oracle v1 package (generated; see package.json)."""
import json
import os

import numpy as np
import pandas as pd
import xgboost as xgb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGETS = ("q2", "q3", "q4", "q5")


def phase_from_predictions(pred, threshold):
    """Unrounded descending q5->q2 decode, >= threshold, default 1 (modeling.py:55-66 at f576e690)."""
    if not np.isfinite(pred).all():
        raise ValueError("non-finite cumulative prediction")
    phase = np.ones(pred.shape[0], dtype=np.int64)
    assigned = np.zeros(pred.shape[0], dtype=bool)
    for position, value in ((3, 5), (2, 4), (1, 3), (0, 2)):
        hit = ~assigned & (pred[:, position] >= threshold)
        phase[hit] = value
        assigned |= hit
    return phase


class Model:
    def __init__(self, package_dir=ROOT):
        self.root = package_dir
        self.meta = json.load(open(os.path.join(package_dir, "package.json")))
        self.columns = json.load(open(os.path.join(package_dir, "deps", "schema_columns.json")))
        self.arm = self.meta["arm_letter"]
        self.threshold = float(self.meta["loader"]["phase_threshold"])
        route = pd.read_csv(os.path.join(package_dir, "deps", "routing.csv"), dtype=str)
        self.route = {(int(a), int(t)): j for a, t, j in route[["area_id", "target_ord", "job_id"]].itertuples(index=False)}
        self._m = {}

    def _booster(self, job, target):
        path = os.path.join(self.root, "weights", f"{job}_{self.arm}_{target}.ubj")
        if path not in self._m:
            m = xgb.XGBRegressor()
            m.load_model(path)
            self._m[path] = m
        return self._m[path]

    def predict(self, keys, X):
        """keys: DataFrame[area_id, target_ord]; X: (n, len(schema)) rows of the saved feature matrix in
        deps/schema_columns.json order (float64 or float32; cast to float32 as the run did)."""
        X = np.asarray(X, dtype=np.float32)
        jobs = [self.route[(int(a), int(t))] for a, t in zip(keys["area_id"], keys["target_ord"])]   # KeyError if unserved
        out = keys.reset_index(drop=True)[["area_id", "target_ord"]].copy()
        out["unit"], out["route"] = jobs, jobs
        pred = np.full((len(out), 4), np.nan)
        for job in sorted(set(jobs)):
            idx = np.flatnonzero(np.asarray(jobs) == job)
            for j, q in enumerate(TARGETS):
                pred[idx, j] = self._booster(job, q).predict(X[idx]).astype(np.float64)
        for j, q in enumerate(TARGETS):
            out[f"{q}_raw"] = pred[:, j]
            out[f"{q}_star"] = pred[:, j]   # the run applies no projection; star equals raw
        out["phase"] = phase_from_predictions(pred, self.threshold)
        return out


def load(package_dir=ROOT):
    return Model(package_dir)
'''


def recorded_files(plan):
    out = {f["path"]: f for f in plan.get("files", [])}
    if not out:
        raise PackageError("plan records no run-level files")
    return out


def build(out_dir, *, ipcch_root, plan, plan_version, version_key, version, runtime, per_unit=32):
    run_root = os.path.join(ipcch_root, RUN)
    letter = ARM_LETTER[plan_version["arm"]]
    h = int(plan_version["lead"])
    hh = f"h{h:02d}"
    deps = {"manifest": "manifest.json", "pred": "predictions/predictions.csv.gz", "schema": "features/feature_schema.json",
            "jobs": "ledgers/jobs.csv", "matrix": f"features/feature_matrix_{hh}.csv.gz"}
    files = recorded_files(plan)
    members = {os.path.basename(m["path"]): m for m in plan_version["members"] if m["role"] == "booster"}
    ensure_local([os.path.join(run_root, p) for p in deps.values()] + [os.path.join(ipcch_root, m["path"]) for m in members.values()])
    for key, p in deps.items():   # verify before reading
        rec = files.get(f"{RUN}/{p}")
        if rec is None:
            raise PackageError(f"{p} has no run-level plan record")
        if sha256_file(os.path.join(run_root, p)) != rec["sha256"]:
            raise PackageError(f"{p} differs from its recorded sha256")
    manifest = json.load(open(os.path.join(run_root, deps["manifest"])))
    written = manifest.get("written", {})
    for key, name in (("pred", "predictions"), ("schema", "feature_schema"), ("jobs", "jobs"), ("matrix", f"feature_matrix_{hh}")):
        if written.get(name, {}).get("sha256") != files[f"{RUN}/{deps[key]}"]["sha256"]:
            raise PackageError(f"manifest written[{name}] does not bind the recorded {deps[key]}")

    schema = json.load(open(os.path.join(run_root, deps["schema"])))[f"{hh}_{letter}"]
    if len(schema) != written["feature_schema"]["widths"][f"{hh}_{letter}"]:
        raise PackageError("schema width differs from the manifest")
    pred = pd.read_csv(os.path.join(run_root, deps["pred"]))
    rows = pred[(pred["arm"] == letter) & (pred["horizon"] == h)].copy()
    if rows.empty or rows.duplicated(KEYS).any():
        raise PackageError(f"{version_key}: saved rows missing or keys repeated")
    jobs = pd.read_csv(os.path.join(run_root, deps["jobs"]))
    jobs = jobs[jobs["horizon"] == h]
    if sorted(rows["job_id"].unique()) != sorted(jobs["job_id"]):
        raise PackageError(f"{version_key}: saved prediction jobs differ from ledgers/jobs.csv")
    gaps = [f"model {j}_{letter}_{q} absent from the version's plan members"
            for j in sorted(jobs["job_id"]) for q in TARGETS if f"{j}_{letter}_{q}.ubj" not in members]
    matrix = pd.read_csv(os.path.join(run_root, deps["matrix"]), float_precision="round_trip")
    if matrix.duplicated(KEYS).any():
        raise PackageError("feature matrix repeats a key")
    lookup = matrix.set_index(KEYS)
    absent = [k for k in zip(rows["area_id"], rows["target_ord"]) if k not in lookup.index]
    if absent or [c for c in schema if c not in matrix.columns]:
        raise PackageError(f"{len(absent)} saved keys or schema columns absent from the feature matrix")

    b = PackageBuilder(out_dir)
    for name in sorted(n for n in members if any(n.endswith(f"_{letter}_{q}.ubj") for q in TARGETS)):
        m = members[name]
        b.add_file(os.path.join(ipcch_root, m["path"]), f"weights/{name}", m["sha256"], m["bytes"])
    for p in deps.values():
        rec = files[f"{RUN}/{p}"]
        b.add_file(os.path.join(run_root, p), "deps/source/" + p, rec["sha256"], rec["bytes"])
    b.add_json("deps/schema_columns.json", schema)
    b.add_bytes("deps/feature_order.csv", pd.DataFrame({"name": schema}).to_csv(index=False).encode())
    b.add_bytes("deps/routing.csv", rows[KEYS + ["job_id"]].sort_values(KEYS).to_csv(index=False).encode())

    rows["unit"] = rows["route"] = rows["job_id"]
    preds = rows[[f"{q}_pred" for q in TARGETS]].to_numpy(dtype=np.float64)
    boundary = np.abs(preds - THRESHOLD).min(axis=1)
    ref = select_reference(rows, "unit", pd.Series(boundary, index=rows.index), KEYS, per_unit=per_unit, cover_cols=("route",))
    arr = np.ascontiguousarray(lookup.loc[list(zip(ref["area_id"], ref["target_ord"])), schema].to_numpy(dtype=np.float64))
    buf = io.BytesIO()
    np.save(buf, arr, allow_pickle=False)
    b.add_bytes("reference/inputs.npy", buf.getvalue())
    expected = ref[KEYS + ["unit", "route"]].copy()
    for q in TARGETS:
        expected[f"{q}_raw"] = ref[f"{q}_pred"].to_numpy()
        expected[f"{q}_star"] = ref[f"{q}_pred"].to_numpy()
    expected["phase"] = ref["phase_pred"].to_numpy()
    b.add_bytes("reference/expected.csv", expected.to_csv(index=False, float_format="%.17g").encode())
    b.add_bytes("loader/entry.py", ENTRY.encode())

    return b.finalize({
        "family": version.get("family"), "identity": version, "version_key": version_key, "source_key": "somalia_oracle_v1",
        "lead_months": h, "arm": plan_version["arm"], "arm_letter": letter,
        "information": information_status(schema, h), "vintage_limitation": VINTAGE_LIMITATION,
        "status": "complete" if not gaps else "retained_weights_missing_dependencies", "gaps": gaps,
        "fitted_units": int(rows["job_id"].nunique()),
        "jobs": {j: {"target_month": t, "primary_rows": int(p)} for j, t, p in
                 jobs[["job_id", "target_month", "n_primary_rows"]].itertuples(index=False)},
        "dependency_hashes": {"enforced_against_plan_run_files": sorted(f"{RUN}/{p}" for p in deps.values()),
                              "cross_checked_against_manifest_written": ["predictions", "feature_schema", "jobs",
                                                                         f"feature_matrix_{hh}"],
                              "plan_fingerprint": plan.get("fingerprint")},
        "routing": {"table": "deps/routing.csv", "feature_order": "deps/feature_order.csv", "served_keys": int(len(rows)),
                    "routes_in_version": sorted(rows["job_id"].unique()),
                    "rule": "a key routes to the job of its target month; every saved row is served, primary or not"},
        "source": {"run_root": run_root, "predictions_sha256": files[f"{RUN}/{deps['pred']}"]["sha256"]},
        "code": {"loader": "thin reimplementation, accepted only through replay against the run's saved predictions",
                 "rules_read_at_recorded_commit": {"git": manifest.get("git"), "files": RULE_FILES}},
        "runtime": {"original": manifest.get("runtime"), "linux_loader_tested": runtime},
        "loader": {"entry": "loader/entry.py", "keys": KEYS, "call": "load(package_dir).predict(keys[area_id,target_ord], X)",
                   "inputs": f"rows of the saved feature matrix in deps/schema_columns.json order ({len(schema)} columns), cast to float32",
                   "phase_threshold": THRESHOLD, "unserved_keys": "KeyError"},
        "reference": {"rows": int(len(expected)), "per_unit_cap": per_unit,
                      "selection": "per job (cap): half nearest a 0.20 crossing, rest by key hash",
                      "routes_covered": sorted(expected["route"].unique()),
                      "rows_with_missing_features": int(np.isnan(arr).any(axis=1).sum())},
        "tolerance": {"declared_before_comparison": True,
                      "continuous": "abs(new-ref) <= 1e-3 + 1e-3*abs(ref) for q2..q5",
                      "phase": "new phase must decode from new outputs (q5->q2, >= 0.20); drift only within that reference's tolerance",
                      "routing": "job must equal the saved row's job exactly"},
    })
