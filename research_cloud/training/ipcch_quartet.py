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
import json
import os
import sys

import numpy as np
import pandas as pd

from research_cloud.training.common import TrialError, run_trial

TARGETS = ("q2", "q3", "q4", "q5")
HORIZONS = {1, 3, 6, 12}
OBJECTIVE = "crisis_f1"


def integer_column(frame, name, lo=None, hi=None):
    """Raw values must be integers (no fraction, no NaN) within bounds before any int cast."""
    v = pd.to_numeric(frame[name], errors="coerce").to_numpy(dtype=np.float64)
    if not np.isfinite(v).all() or (v != np.round(v)).any() or (np.abs(v) > 2 ** 53).any():
        raise TrialError(f"{name} holds non-integer, non-finite or missing values")
    if (lo is not None and v.min() < lo) or (hi is not None and v.max() > hi):
        raise TrialError(f"{name} outside [{lo}, {hi}]")
    return v.astype(np.int64)


def config_int(config, *path):
    """An integral, finite config value; fractional or non-numeric values are refused, never truncated."""
    value = config
    for k in path:
        value = value[k]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value != int(value):
        raise TrialError(f"config {'.'.join(map(str, path))} must be an integer, got {value!r}")
    return int(value)


def _modules(config):
    src = os.environ.get("IPCCH_GEOXGB_SRC", config.get("geoxgb_src", ""))
    if src and src not in sys.path:
        sys.path.insert(0, src)
    return tuple(importlib.import_module(f"ipcch_geoxgb.{m}") for m in ("quartet", "projection", "metrics", "modelstore"))


def code_identity(mods, config):
    """sha256 of the vendored modules this trial imported and of the frozen schema it checked against."""
    from research_cloud.training.common import sha256_file
    src = os.environ.get("IPCCH_GEOXGB_SRC", config.get("geoxgb_src", ""))
    files = {f"ipcch_geoxgb/{os.path.basename(m.__file__)}": sha256_file(m.__file__) for m in mods}
    files["config/feature-schema.json"] = sha256_file(os.path.join(src, "config", "feature-schema.json"))
    from research_cloud.training.common import adapter_identity
    return {"geoxgb_src": os.path.abspath(src), "files": dict(sorted(files.items())),
            "adapter": adapter_identity("research_cloud.training.ipcch_quartet", "research_cloud.training.common",
                                        "research_cloud.training.trial_package")}


def fit(inputs, manifest, config, params, out):
    quartet, projection, metrics, modelstore = _modules(config)
    h = config_int(config, "horizon")
    if h not in HORIZONS:
        raise TrialError(f"horizon {h} is not one of the historical GeoXGB horizons {sorted(HORIZONS)}")
    if not config.get("folds"):
        raise TrialError("no development folds declared")
    keys = pd.read_csv(inputs["keys"])
    X = np.load(inputs["X"], mmap_mode="r")
    order = pd.read_csv(inputs["feature_order"])["name"].astype(str).tolist()
    frozen = json.load(open(os.path.join(os.environ.get("IPCCH_GEOXGB_SRC", config.get("geoxgb_src", "")),
                                         "config", "feature-schema.json")))["ordered_names"]
    if order != list(frozen) or len(order) != 561:
        raise TrialError("feature order is not the frozen rich561 ordered schema")
    missing = [c for c in ("admin_code", "target_ord", "origin_ord", "horizon_months", "phase_truth", *TARGETS) if c not in keys]
    if missing:
        raise TrialError(f"prepared keys lack {missing}")
    admin = integer_column(keys, "admin_code")
    months = integer_column(keys, "target_ord")
    origins = integer_column(keys, "origin_ord")
    horizons = integer_column(keys, "horizon_months")
    phases = integer_column(keys, "phase_truth", 1, 5)
    if X.shape != (len(keys), 561) or pd.Series(list(zip(admin, months))).duplicated().any():
        raise TrialError("prepared bundle misaligned: keys and X disagree or keys repeat")
    if (horizons != h).any() or ((months - origins) != h).any():
        raise TrialError("prepared rows are not built at their own origin O = T - H for this horizon")
    Y = keys[list(TARGETS)].to_numpy(dtype=np.float64)
    holdout = config_int(config, "holdout_start_ord")
    params = dict(params)   # the caller records the validated trial values unchanged
    rounds = int(params.pop("rounds"))
    model_params = {**config["fixed"], **params}

    counts, panels, fits, packaged = [], [], [], []
    for i, fold in enumerate(config["folds"]):
        origin = config_int(config, "folds", i, "origin_ord")
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
        truth = phases[val_rows]
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
        pd.DataFrame({"admin_code": admin[val_rows], "target_ord": target,
                      **{f"{t}_raw": raw[:, j] for j, t in enumerate(TARGETS)},
                      **{f"{t}_star": star[:, j] for j, t in enumerate(TARGETS)}, "phase": phase,
                      "phase_truth": truth}).to_csv(out.path(f"{fold_dir}/predictions.csv.gz"), index=False)
        fits.append(fold_dir)
        packaged.append({"unit": f"o{origin}_{q.booster_shas()['q3'][:16]}", "payloads": q.payloads,
                         "record": {"booster_sha256": q.booster_shas(), "fit_records": q.records},
                         "validation_rows": val_rows, "target_ord": target, "raw": raw, "star": star, "phase": phase})
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
    from research_cloud.training import trial_package
    from research_cloud.training.common import runtime_identity
    package_meta = trial_package.build(
        out.path("package"), folds=packaged, keys=keys, X=X, feature_order_path=inputs["feature_order"],
        geoxgb_src=os.environ.get("IPCCH_GEOXGB_SRC", config.get("geoxgb_src", "")),
        identity={"family": "ipcch_geoxgb_pooled_quartet", "horizon": h, "trial": os.environ.get("CLOUD_ML_TRIAL_ID"),
                  "job": os.environ.get("CLOUD_ML_JOB_ID"), "params": model_params, "rounds": rounds,
                  "input_manifest": manifest, "trial_code": code_identity((quartet, projection, metrics, modelstore), config)},
        runtime=runtime_identity())
    return {"metrics": result_metrics, "artifacts": fits + ["package"], "model_params": model_params, "rounds": rounds,
            "trial_code": code_identity((quartet, projection, metrics, modelstore), config),
            "package": {"path": "package", "content_sha256": package_meta["content_sha256"], "units": package_meta["fitted_units"]},
            "identity": {"family": "ipcch_geoxgb_pooled_quartet", "kind": "new Linux research run (not a historical version)",
                         "horizon": h, "folds": [p["origin_ord"] for p in panels]}}


if __name__ == "__main__":
    sys.exit(run_trial(fit, objective=OBJECTIVE))
