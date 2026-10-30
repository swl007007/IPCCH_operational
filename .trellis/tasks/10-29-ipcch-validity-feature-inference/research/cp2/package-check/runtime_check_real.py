"""Real package check, stage 2 (operational exact-lock env): load each scope of the REAL combination with the operational
runtime (model_pipeline.ipcch_launch_runtime) from a relocated copy and score the stage-1 probes: runtime raw scores must
equal the harvested UBJ booster scores bit for bit; NaN cells reach the model unchanged; no feature imputation."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.dont_write_bytecode = True
sys.path.insert(0, "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/cloud_pipeline")
from model_pipeline.ipcch_launch_runtime.model_package import load_scope_package
from model_pipeline.ipcch_launch_runtime.feature_contract import apply_feature_contract
from model_pipeline.ipcch_launch_runtime.inference import score_scope
pkg_root, probes = Path(sys.argv[1]), Path(sys.argv[2])
pid = json.load(open(pkg_root / "package_manifest.json")).get("model_package_id") or json.load(open(pkg_root / "package_manifest.json")).get("package_id")
res, ok = {"package_root": str(pkg_root), "model_package_id": pid}, True
for h, s in ((2, 0), (8, 6), (14, 12)):
    pkg = load_scope_package(pkg_root, s)
    X, P, rows = (np.load(probes / f"probe_h{h:02d}_{k}.npy") for k in ("X", "P", "rows"))
    monthly = pd.DataFrame(X, columns=pkg["feature_columns"])
    monthly.insert(0, "area_id", rows)
    for c, v in (("population_estimate", 1000.0), ("population_reference_period", "2026-08"), ("population_imputation_method", "observed_feature_month")):
        monthly[c] = v      # probe identity columns required by score_scope (not model features)
    matrix, report = apply_feature_contract(monthly, pkg["contract"], pkg["feature_columns"], package_root=pkg_root, metadata=pkg["metadata"])
    out, summary = score_scope(monthly_rows=monthly, feature_matrix=matrix, models=pkg["models"], thresholds=pkg["metadata"]["thresholds"],
                               scope_months=s, feature_month="2026-08", target_month="2026-10", model_package_id=str(pid),
                               source_input="real-package-check", monotonicity_policy=pkg["metadata"]["monotonicity_policy"])
    eq = {t: bool(np.array_equal(out[f"{t}_worse_score"].to_numpy(), P[:, k])) for k, t in enumerate(("phase2", "phase3", "phase4", "phase5"))}
    nan_in, nan_mat = int(np.isnan(X).sum()), int(matrix.isna().to_numpy().sum())
    r = {"scope": s, "rows": int(len(X)), "features": len(pkg["feature_columns"]), "report_status": report["status"],
         "filled_features": len(report["filled_features"]), "nan_cells_input": nan_in, "nan_cells_matrix": nan_mat,
         "raw_scores_equal_booster": eq, "thresholds": summary["thresholds"], "monotonicity": summary["monotonicity_policy"],
         "phase_counts": {str(k): int(v) for k, v in out["overall_phase_pred"].value_counts().sort_index().items()}}
    r["ok"] = all(eq.values()) and nan_in == nan_mat and report["status"] == "passed" and not report["filled_features"]
    ok &= r["ok"]; res[f"H{h}"] = r
    print(json.dumps({f"H{h}": {k: r[k] for k in ("rows", "features", "raw_scores_equal_booster", "nan_cells_input", "ok")}}), flush=True)
res["ok"] = ok
json.dump(res, open(probes / "runtime_check_real.json", "w"), indent=1, default=str)
sys.exit(0 if ok else 1)
