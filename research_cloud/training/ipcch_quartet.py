"""IPCCH pooled GeoXGB quartet training trial (new Linux research identity).

Reuses the P6 low-level functions vendored from its ``source_code`` artifact (``ipcch_geoxgb.quartet.fit_global_quartet``,
``projection.project_and_decode``, ``metrics.metric_panel``) without their historical Windows/runtime guards, which stay
in place for the historical runs. Inputs are a prepared rich561 bundle for one horizon (keys + X + feature order,
hashed through the input manifest).

Time-respecting validation (``config['folds']``, each a declared development fold): origin O, horizon H in
{1, 3, 6, 12}; fitting rows are target months [O-35, O] (the P6 training window); the validation cohort is target month
T = O + H, which must be before ``config['holdout_start_ord']`` and outside every fitting window. Multiple folds pool
crisis confusion counts. Objective ``crisis_f1``: exact F1 of the projected-decoded phase >= 3 against the truth;
undefined (no positives in truth and prediction) fails the trial. q3 R2 values are logged separately.

  python -m research_cloud.training.ipcch_quartet --manifest M.json --config C.json --output DIR|gs://... [--max_depth=4 ...]
"""
import importlib
import os
import sys

import numpy as np
import pandas as pd

from research_cloud.training.common import TrialError, run_trial

TARGETS = ("q2", "q3", "q4", "q5")
HORIZONS = {1, 3, 6, 12}


def _modules(config):
    src = os.environ.get("IPCCH_GEOXGB_SRC", config.get("geoxgb_src", ""))
    if src and src not in sys.path:
        sys.path.insert(0, src)
    return tuple(importlib.import_module(f"ipcch_geoxgb.{m}") for m in ("quartet", "projection", "metrics", "modelstore"))


def fit(inputs, manifest, config, params, out):
    quartet, projection, metrics, modelstore = _modules(config)
    h = int(config["horizon"])
    if h not in HORIZONS:
        raise TrialError(f"horizon {h} is not one of the historical GeoXGB horizons {sorted(HORIZONS)}")
    keys = pd.read_csv(inputs["keys"])
    X = np.load(inputs["X"], mmap_mode="r")
    order = pd.read_csv(inputs["feature_order"])
    if X.shape != (len(keys), len(order)) or keys.duplicated(["admin_code", "target_ord"]).any():
        raise TrialError("prepared bundle misaligned: keys, X and feature order disagree or keys repeat")
    if "origin_ord" in keys and ((keys["target_ord"] - keys["origin_ord"]) != h).any():
        raise TrialError("prepared rows are not built at origin = target - H")
    Y = keys[list(TARGETS)].to_numpy(dtype=np.float64)
    months = keys["target_ord"].to_numpy(np.int64)
    holdout = int(config["holdout_start_ord"])
    params = dict(params)   # the caller records the validated trial values unchanged
    rounds = int(params.pop("rounds"))
    model_params = {**config["fixed"], **params}

    counts, panels, fits = [], [], []
    for fold in config["folds"]:
        origin = int(fold["origin_ord"])
        target = origin + h
        if target >= holdout:
            raise TrialError(f"fold origin {origin}: validation month {target} is inside the holdout (>= {holdout})")
        fit_rows = np.flatnonzero((months >= origin - 35) & (months <= origin))
        val_rows = np.flatnonzero(months == target)
        if len(fit_rows) == 0 or len(val_rows) == 0:
            raise TrialError(f"fold origin {origin}: empty fitting or validation rows")
        if months[fit_rows].max() >= target:
            raise TrialError("fitting rows reach the validation month")
        q = quartet.fit_global_quartet(np.asarray(X[fit_rows]), Y[fit_rows], model_params, rounds)
        raw = q.predict_raw(np.asarray(X[val_rows]))
        star, phase = projection.project_and_decode(raw)
        truth = keys.iloc[val_rows]["phase_truth"].to_numpy(np.int64)
        panel = metrics.metric_panel(truth, phase, Y[val_rows, 1], star[:, 1], raw[:, 1])
        counts.append(metrics.crisis_counts(truth, phase))
        panels.append({"origin_ord": origin, "target_ord": target, "fit_rows": int(len(fit_rows)),
                       "validation_rows": int(len(val_rows)), "panel": panel})
        fold_dir = f"folds/o{origin}"
        for t, payload in q.payloads.items():
            with open(out.path(f"{fold_dir}/{t}.ubj"), "wb") as f:
                f.write(payload)
        out.write_json(f"{fold_dir}/record.json", {
            "booster_sha256": q.booster_shas(), "fit_records": q.records, "rounds": rounds, "params": model_params,
            "fitting_keys_sha256": modelstore.array_digest(keys.iloc[fit_rows][["admin_code", "target_ord"]].to_numpy(np.int64)),
            "y_sha256": modelstore.target_digests(Y[fit_rows]), "window": [origin - 35, origin], "validation_target_ord": target})
        pd.DataFrame({"admin_code": keys.iloc[val_rows]["admin_code"].to_numpy(), "target_ord": target,
                      **{f"{t}_raw": raw[:, j] for j, t in enumerate(TARGETS)},
                      **{f"{t}_star": star[:, j] for j, t in enumerate(TARGETS)}, "phase": phase,
                      "phase_truth": truth}).to_csv(out.path(f"{fold_dir}/predictions.csv.gz"), index=False)
        fits.append(fold_dir)
    pooled = metrics.add_counts(*counts)
    f1 = metrics.exact_f1(pooled)
    result_metrics = {"crisis_f1": float(f1) if f1 is not None else None,
                      "crisis_tp": pooled.get("tp"), "crisis_fp": pooled.get("fp"), "crisis_fn": pooled.get("fn"),
                      "folds": len(panels)}
    for name in ("q3_r2_projected", "q3_r2_raw"):
        values = [p["panel"].get(name) for p in panels]
        if all(v is not None for v in values):
            result_metrics[f"mean_{name}"] = float(np.mean(values))
    out.write_json("metrics.json", {"pooled_crisis_counts": pooled, "folds": panels})
    return {"metrics": result_metrics, "artifacts": fits, "model_params": model_params, "rounds": rounds,
            "identity": {"family": "ipcch_geoxgb_pooled_quartet", "kind": "new Linux research run (not a historical version)",
                         "horizon": h, "folds": [p["origin_ord"] for p in panels]}}


if __name__ == "__main__":
    sys.exit(run_trial(fit))
