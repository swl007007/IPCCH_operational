"""FEWS NET pooled four-class training trial (new Linux research identity; Vertex HPT entry).

Inputs: a ``fews_features`` snapshot (rows with roles, X, feature order; hashed through the input manifest) for one
declared development target T (``plan.DEV_TARGETS``; ``config['development_targets']`` must list it and the held-out
period starts at ``config['holdout_start']`` > T). Fit: FEWS's own ``native_xgb.fit_global`` on the ``fit_variant`` rows
(lawful labels [O-59, O) at each key's own origin; strategy weights passed as sample weights when not all 1) with
``config['fixed']`` + trial parameters; the booster's structural keys (objective, class axis, multi strategy, seed,
threads, device) come from ``native_xgb``/``plan`` and may not be set by a trial or the config. Validation: the
``target`` cohort only (the genuine development target month); ``eval`` rows are a second view of fitting keys and are
never scored. Objective ``crisis_f1``: exact crisis-positive F1 of argmax codes (code >= 2, first max wins) against
the target truth; undefined (no positives and no positive calls) fails the trial.

The trial writes its booster, record and target predictions, and a replayable package (weights, the target rows'
prepared X, reference sample, the shared pooled loader).

  python -m research_cloud.training.fews_fourclass --manifest M.json --config C.json --output DIR|gs://... [--max_depth=2 ...]
"""
import io
import json
import os
import sys

import numpy as np
import pandas as pd

from research_cloud.training.common import TrialError, adapter_identity, run_trial, sha256_file
from research_cloud.training.ipcch_quartet import config_int, integer_column

OBJECTIVE = "crisis_f1"
PROTECTED = {"objective", "num_class", "multi_strategy", "seed", "nthread", "device", "booster", "num_parallel_tree"}
LABELS = ("1", "2", "3", "4或5")


def modules(config):
    src = os.environ.get("FEWS_SRC", config.get("fews_src", ""))
    for p in (src, os.path.join(src, "scripts")):
        if p and p not in sys.path:
            sys.dont_write_bytecode = True   # never write __pycache__ into the source tree
            sys.path.insert(0, p)
    from src.experiment import plan
    from src.metrics import fourclass
    from src.model import native_xgb as nx
    return nx, plan, fourclass, src


def code_identity(src):
    files = {rel: sha256_file(os.path.join(src, rel)) for rel in
             ("src/model/native_xgb.py", "src/experiment/plan.py", "src/metrics/fourclass.py")}
    return {"fews_src": os.path.abspath(src), "files": files,
            "adapter": adapter_identity("research_cloud.training.fews_fourclass", "research_cloud.training.common",
                                        "research_cloud.training.ipcch_quartet", "research_cloud.packages.fews_confirm",
                                        "research_cloud.packages.fews_scen", "research_cloud.packages.common")}


def crisis_f1(truth, codes):
    z, a = truth >= 2, codes >= 2
    tp, fp, fn = int((z & a).sum()), int((~z & a).sum()), int((z & ~a).sum())
    return (2 * tp / (2 * tp + fp + fn) if tp + fp + fn else None), {"tp": tp, "fp": fp, "fn": fn,
                                                                       "tn": int((~z & ~a).sum())}


def fit(inputs, manifest, config, params, out):
    nx, plan, fourclass, src = modules(config)
    for key in PROTECTED:
        if key in config["fixed"] or key in config["space"]:
            raise TrialError(f"{key} is fixed by native_xgb and may not be configured or tuned")
    target = config["target"]
    h = config_int(config, "horizon")
    if h not in (4, 8, 12):
        raise TrialError(f"horizon {h} is not a FEWS horizon (4, 8, 12)")
    derived = manifest.get("derived_from") or {}
    if (derived.get("horizon"), derived.get("target")) != (h, target):
        raise TrialError(f"snapshot was built for horizon {derived.get('horizon')} / target {derived.get('target')}, "
                         f"the config declares {h} / {target}")
    if target not in plan.DEV_TARGETS or target not in config.get("development_targets", []):
        raise TrialError(f"target {target} is not a declared development target")
    if not target < config["holdout_start"]:
        raise TrialError(f"target {target} is inside the held-out period (>= {config['holdout_start']})")
    rows = pd.read_csv(inputs["rows"])
    X = np.load(inputs["X"], mmap_mode="r")
    order = pd.read_csv(inputs["feature_order"])["name"].astype(str).tolist()
    if X.shape != (len(rows), len(order)) or len(order) != config_int(config, "n_features"):
        raise TrialError(f"X {X.shape} does not match {len(rows)} rows x {len(order)} declared features")
    roles = rows["role"].astype(str)
    if set(roles) - {"fit_variant", "eval", "target"}:
        raise TrialError(f"unexpected roles {sorted(set(roles))}")
    labels = integer_column(rows, "class_code", 0, 3)
    weights = pd.to_numeric(rows["weight"], errors="coerce").to_numpy(np.float64)
    fit_rows, val_rows = np.flatnonzero(roles == "fit_variant"), np.flatnonzero(roles == "target")
    months = integer_column(rows, "target_month")
    if (integer_column(rows, "horizon") != h).any() or (integer_column(rows, "origin_month") != months - h).any():
        raise TrialError(f"snapshot rows are not built at horizon {h} with origin_month = target_month - H")
    t = int(target[:4]) * 12 + int(target[5:]) - 1
    if len(fit_rows) == 0 or len(val_rows) == 0:
        raise TrialError("empty fitting or target cohort")
    if (months[val_rows] != t).any() or months[fit_rows].max() >= t - h:
        raise TrialError("target rows are not at T, or fitting labels reach the origin O = T - H")
    if rows.iloc[val_rows].duplicated(["area"]).any():
        raise TrialError("duplicate target areas")
    w = weights[fit_rows]
    if not np.isfinite(w).all() or (w <= 0).any():
        raise TrialError("fitting weights must be finite and positive")
    params = dict(params)
    config_g = {**config["fixed"], **params}
    if "rounds" not in config_g:
        raise TrialError("rounds must be fixed or tuned")
    config_g["rounds"] = config_int({"r": config_g["rounds"]}, "r")
    booster, record = nx.fit_global(np.asarray(X[fit_rows]), labels[fit_rows], config_g,
                                    sample_weight=None if np.all(w == 1.0) else w)
    proba = nx.proba(booster, np.asarray(X[val_rows]))
    codes = fourclass.argmax_codes(proba)
    truth = labels[val_rows]
    f1, counts = crisis_f1(truth, codes)
    with open(out.path("model/global.ubj"), "wb") as f:
        f.write(nx.raw(booster))
    if sha256_file(out.path("model/global.ubj")) != record["booster_sha256"]:
        raise TrialError("saved booster bytes differ from the fit record")
    out.write_json("model/global.json", {**record, "fitting_keys_sha256": nx.keys_sha(rows["area"].iloc[fit_rows], months[fit_rows]),
                                         "target": target, "horizon": h, "config": config_g})
    preds = pd.DataFrame({"area": rows["area"].iloc[val_rows].to_numpy(), "target_month": target,
                          "y_true_code": truth, "y_pred_code": codes, "route": "pooled_arm", "cluster_id": -1})
    for k, l in enumerate(LABELS):
        preds[f"p_{l}"] = proba[:, k]
    preds.to_csv(out.path("predictions/target_predictions.csv.gz"), index=False, float_format="%.17g")
    package = build_package(out.path("package"), booster_file=out.path("model/global.ubj"),
                            record_file=out.path("model/global.json"), record=record, preds=preds,
                            X=np.asarray(X[val_rows]), order_path=inputs["feature_order"], identity={
                                "family": "fewsnet_pooled_fourclass_trial", "target": target, "horizon": h,
                                "trial": os.environ.get("CLOUD_ML_TRIAL_ID"), "job": os.environ.get("CLOUD_ML_JOB_ID"),
                                "params": config_g, "input_manifest": manifest, "trial_code": code_identity(src)})
    metrics = {"crisis_f1": f1, **{f"crisis_{k}": v for k, v in counts.items()}, "fit_rows": int(len(fit_rows)),
               "fit_original_keys": int(rows["orig_key"].iloc[fit_rows].nunique()), "target_rows": int(len(val_rows))}
    out.write_json("metrics.json", metrics)
    return {"metrics": metrics, "artifacts": ["model", "predictions", "package"], "model_params": config_g,
            "rounds": config_g["rounds"], "trial_code": code_identity(src),
            "package": {"path": "package", "content_sha256": package["content_sha256"]},
            "identity": {"family": "fewsnet_pooled_fourclass_trial", "kind": "new Linux research run (not a historical version)",
                         "target": target, "horizon": h}}


def build_package(root, booster_file, record_file, record, preds, X, order_path, identity, per_unit=200):
    """A replayable package for the trial booster, using the shared pooled loader (exact width and rows)."""
    from research_cloud.packages.common import PackageBuilder, select_reference
    from research_cloud.packages.fews_confirm import ENTRY
    b = PackageBuilder(root)
    b.add_file(booster_file, "weights/global.ubj", record["booster_sha256"], None)
    b.add_file(record_file, "weights/global.json")
    b.add_file(order_path, "deps/feature_order.csv")
    b.add_bytes("deps/routing.csv", preds[["area", "target_month", "route", "cluster_id"]].to_csv(index=False).encode())
    prob = [f"p_{l}" for l in LABELS]
    frame = preds.assign(unit=record["booster_sha256"][:16], route="pooled", row=np.arange(len(preds)))
    srt = np.sort(frame[prob].to_numpy(np.float64), axis=1)
    ref = select_reference(frame, "unit", pd.Series(srt[:, -1] - srt[:, -2]), ["area", "target_month"], per_unit=per_unit)
    buf = io.BytesIO()
    np.save(buf, np.ascontiguousarray(X[ref["row"].to_numpy()], dtype=np.float64), allow_pickle=False)
    b.add_bytes("reference/inputs.npy", buf.getvalue())
    b.add_bytes("reference/expected.csv", ref[["area", "target_month", "unit", "route"] + prob + ["y_pred_code"]]
                .to_csv(index=False, float_format="%.17g").encode())
    b.add_bytes("loader/entry.py", ENTRY.replace("one FEWS NET confirm-onset-v1 pooled package",
                                                 "one FEWS NET pooled four-class trial package").encode())
    return b.finalize({
        "family": identity["family"], "arm": "pooled", "status": "complete", "gaps": [], "identity": identity,
        "fitted_units": 1, "global": {"booster_sha256": record["booster_sha256"]},
        "routing": {"table": "deps/routing.csv", "feature_order": "deps/feature_order.csv", "routes_in_version": ["pooled"]},
        "loader": {"entry": "loader/entry.py", "keys": ["area", "target_month"],
                   "call": "load(package_dir).predict(keys[area,target_month], X)"},
        "reference": {"rows": int(len(ref)), "per_unit_cap": per_unit, "compare_columns": prob + ["y_pred_code"],
                      "routes_covered": ["pooled"], "selection": "half nearest an argmax tie, rest by key hash"},
        "tolerance": {"declared_before_comparison": True, "continuous": "abs(new-ref) <= 1e-3 + 1e-3*abs(ref) for p_1..p_4",
                      "decision": "y_pred_code exactly", "routing": "unit and route exactly"},
    })


if __name__ == "__main__":
    sys.exit(run_trial(fit, objective=OBJECTIVE))
