"""Replay a historical package's frozen reference sample and compare under the D11 contract.

Runs inside the package's Linux runtime (only numpy/pandas + the package loader):
  python -m research_cloud.packages.replay PACKAGE_DIR --report OUT.json

Continuous outputs (raw and projected shares): abs(new-ref) <= 1e-3 + 1e-3*abs(ref), every
value checked. Phase: a change is accepted only as boundary drift, i.e. every threshold
whose crossing changed has |ref_star - 0.20| within tolerance AND all continuous values
of that row pass; any other change fails. Shapes/keys/units must match exactly.
"""
import argparse
import importlib.util
import json
import os
import platform
import sys
import time

import numpy as np
import pandas as pd

from research_cloud.packages.common import ABS_TOL, REL_TOL, verify_package

TARGETS = ("q2", "q3", "q4", "q5")
THRESHOLD = 0.20


def load_entry(package_dir):
    spec = importlib.util.spec_from_file_location("rc_package_entry", os.path.join(package_dir, "loader", "entry.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load(package_dir)


def decode(star, threshold=THRESHOLD):
    """Highest phase k+2 whose score q_k >= threshold, else 1. For the monotone projected quartets (GeoXGB,
    AlphaEarth) this equals 1 + count; for raw unprojected forecasting scores it is the families' own
    highest-crossing rule (IPCCH origin_safe.classify_cumulative), not a count."""
    phase = np.ones(len(star), dtype=np.int64)
    for k in range(4):
        phase = np.where(star[:, k] >= threshold, k + 2, phase)
    return phase


def compare(expected, raw, star, phase, threshold=THRESHOLD):
    """Every value checked; boundary drift accepted only when the new phase is the correct decode of
    the new projected vector, each changed crossing's reference score lies within that reference's
    tolerance of 0.20, and every continuous output of the row passes."""
    n = len(expected)
    report = {"rows": int(n), "columns": {}, "phase_changes": [], "failed_rows": [], "checks": {}}
    if n == 0:
        report.update(passed=False, error="empty reference sample")
        return report
    raw, star, phase = np.asarray(raw, dtype=np.float64), np.asarray(star, dtype=np.float64), np.asarray(phase)
    shape_ok = raw.shape == (n, 4) and star.shape == (n, 4) and phase.shape == (n,)
    finite_ok = shape_ok and bool(np.isfinite(raw).all() and np.isfinite(star).all())
    report["checks"].update(shapes=shape_ok, finite=finite_ok)
    if not finite_ok:
        report.update(passed=False, error="output shape or finiteness violated")
        return report
    row_ok = np.ones(n, dtype=bool)
    for kind, new in (("raw", raw), ("star", star)):
        for j, q in enumerate(TARGETS):
            ref = expected[f"{q}_{kind}"].to_numpy(dtype=np.float64)
            err = np.abs(new[:, j] - ref)
            ok = err <= ABS_TOL + REL_TOL * np.abs(ref)
            row_ok &= ok
            report["columns"][f"{q}_{kind}"] = {"max_abs_err": float(err.max()), "mean_abs_err": float(err.mean()),
                                                "failures": int((~ok).sum())}
    ref_phase = expected["phase"].to_numpy()
    ref_star = expected[[f"{q}_star" for q in TARGETS]].to_numpy(dtype=np.float64)
    decoded_new_ok = decode(star, threshold) == phase
    decoded_ref_ok = decode(ref_star, threshold) == ref_phase
    report["checks"].update(new_phase_decodes=int((~decoded_new_ok).sum()) == 0,
                            reference_phase_decodes=int((~decoded_ref_ok).sum()) == 0)
    phase_ok = decoded_new_ok & decoded_ref_ok
    for i in np.flatnonzero(phase != ref_phase):
        changed = np.flatnonzero((star[i] >= threshold) != (ref_star[i] >= threshold))
        near = all(abs(ref_star[i, k] - threshold) <= ABS_TOL + REL_TOL * abs(ref_star[i, k]) for k in changed)
        accepted = bool(len(changed)) and near and bool(row_ok[i]) and bool(phase_ok[i])
        phase_ok[i] = accepted
        report["phase_changes"].append({"row": int(i), "ref_phase": int(ref_phase[i]), "new_phase": int(phase[i]),
                                        "thresholds": [TARGETS[k] for k in changed],
                                        "ref_star": [float(ref_star[i, k]) for k in changed],
                                        "classification": "boundary_drift" if accepted else "FAIL"})
    bad = ~(row_ok & phase_ok)
    report["failed_rows"] = [int(i) for i in np.flatnonzero(bad)]
    report["passed"] = not bad.any()
    return report


def compare_columns(expected, got, columns):
    """Declared continuous columns: every value within tolerance; NaN accepted only where the reference is NaN."""
    report = {"rows": int(len(expected)), "columns": {}, "phase_changes": [], "checks": {}}
    if len(expected) == 0:
        report.update(passed=False, error="empty reference sample")
        return report
    bad = np.zeros(len(expected), dtype=bool)
    for col in columns:
        ref = expected[col].to_numpy(dtype=np.float64)
        new = got[col].to_numpy(dtype=np.float64)
        both_nan = np.isnan(ref) & np.isnan(new)
        err = np.where(both_nan, 0.0, np.abs(new - ref))
        ok = both_nan | (np.isfinite(err) & (err <= ABS_TOL + REL_TOL * np.abs(np.nan_to_num(ref))))
        bad |= ~ok
        finite = err[np.isfinite(err)]
        report["columns"][col] = {"max_abs_err": float(finite.max()) if finite.size else 0.0,
                                  "mean_abs_err": float(finite.mean()) if finite.size else 0.0,
                                  "failures": int((~ok).sum()), "reference_nan": int(np.isnan(ref).sum())}
    report["failed_rows"] = [int(i) for i in np.flatnonzero(bad)]
    report["passed"] = not bad.any()
    return report


def check_output(got, expected, key_columns=("admin_code", "target_ord"), threshold=THRESHOLD, columns=None,
                 exact_columns=()):
    """Exact keys/order/routing first; numeric comparison only on a correctly keyed output."""
    keys_ok = len(got) == len(expected) and all(
        np.array_equal(got[k].to_numpy(), expected[k].to_numpy()) for k in key_columns)
    if not keys_ok:
        return {"passed": False, "error": "output keys/order differ from the requested reference keys",
                "checks": {"keys_and_order": False}}
    mismatch = (got["unit"].to_numpy() != expected["unit"].to_numpy()) | \
               (got["route"].to_numpy() != expected["route"].to_numpy())
    if columns:
        result = compare_columns(expected, got, columns)
    else:
        result = compare(expected, got[[f"{q}_raw" for q in TARGETS]].to_numpy(),
                         got[[f"{q}_star" for q in TARGETS]].to_numpy(), got["phase"].to_numpy(), threshold)
    result["checks"]["keys_and_order"] = True
    for col in exact_columns:   # declared categorical outputs (e.g. pop-v1 support) must equal the reference exactly
        diff = got[col].astype(str).to_numpy() != expected[col].astype(str).to_numpy()
        result["checks"][f"exact_{col}"] = not diff.any()
        mismatch = mismatch | diff
    result["routing_mismatches"] = int(mismatch.sum())
    if mismatch.any():
        result["passed"] = False
    return result


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("package")
    ap.add_argument("--report", required=True)
    args = ap.parse_args(argv)
    t0 = time.time()
    from research_cloud.packages.common import sha256_file
    package_json_sha = sha256_file(os.path.join(args.package, "package.json"))
    problems = verify_package(args.package)
    out = {"package": os.path.abspath(args.package), "package_json_sha256": package_json_sha, "integrity_problems": problems,
           "runtime": {"python": platform.python_version(), "platform": platform.platform()}}
    if not problems:
        import xgboost
        out["runtime"].update(xgboost=xgboost.__version__, numpy=np.__version__, pandas=pd.__version__)
        meta = json.load(open(os.path.join(args.package, "package.json")))
        out["identity"] = meta["identity"]
        model = load_entry(args.package)
        X = np.load(os.path.join(args.package, "reference", "inputs.npy"), allow_pickle=False)
        expected = pd.read_csv(os.path.join(args.package, "reference", "expected.csv"), dtype={"unit": str})
        n_features = len(pd.read_csv(os.path.join(args.package, meta["routing"]["feature_order"])))
        if len(expected) == 0 or len(X) != len(expected) or X.ndim != 2 or X.shape[1] != n_features:
            out["error"] = (f"reference contract violated: inputs {X.shape}, expected rows {len(expected)}, "
                            f"feature_order {n_features}")
        else:
            key_columns = meta.get("loader", {}).get("keys", ["admin_code", "target_ord"])
            got = model.predict(expected[key_columns], X)
            threshold = float(meta.get("loader", {}).get("phase_threshold", THRESHOLD))
            columns = meta.get("reference", {}).get("compare_columns")
            exact = meta.get("reference", {}).get("exact_columns", [])
            out.update(check_output(got, expected, key_columns, threshold, columns, exact))
    out["passed"] = bool(out.get("passed")) and not problems and "error" not in out
    out["seconds"] = round(time.time() - t0, 2)
    with open(args.report, "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps({k: out.get(k) for k in ("passed", "rows", "seconds")}))
    return 0 if out["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
