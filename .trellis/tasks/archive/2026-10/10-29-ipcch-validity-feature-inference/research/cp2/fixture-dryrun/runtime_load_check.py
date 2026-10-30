"""FIXTURE-ONLY: load the converted scope with the OPERATIONAL runtime (model_pipeline.ipcch_launch_runtime) and score
2,000 real H2 fit rows: runtime raw scores must equal the research booster scores; NaN cells reach the model unchanged."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.dont_write_bytecode = True
sys.path.insert(0, "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/cloud_pipeline")
from model_pipeline.ipcch_launch_runtime.model_package import load_scope_package
from model_pipeline.ipcch_launch_runtime.feature_contract import apply_feature_contract
from model_pipeline.ipcch_launch_runtime.inference import score_scope
run = Path(sys.argv[1])
pkg = load_scope_package(run / "package", 0)
X, P, rows = np.load(run / "probe_X.npy"), np.load(run / "probe_P.npy"), np.load(run / "probe_rows.npy")
monthly = pd.DataFrame(X, columns=pkg["feature_columns"])
monthly.insert(0, "area_id", rows)
for c, v in (("population_estimate", 1000.0), ("population_reference_period", "2026-08"), ("population_imputation_method", "observed_feature_month")):
    monthly[c] = v      # fixture identity columns required by score_scope (not model features)
matrix, report = apply_feature_contract(monthly, pkg["contract"], pkg["feature_columns"], package_root=run / "package",
                                        metadata=pkg["metadata"])
nan_in, nan_mat = int(np.isnan(X).sum()), int(matrix.isna().to_numpy().sum())
out, summary = score_scope(monthly_rows=monthly, feature_matrix=matrix, models=pkg["models"], thresholds=pkg["metadata"]["thresholds"],
                           scope_months=0, feature_month="2026-08", target_month="2026-10", model_package_id="FIXTURE-NOT-A-MODEL",
                           source_input="fixture", monotonicity_policy=pkg["metadata"]["monotonicity_policy"])
eq = {t: bool(np.array_equal(out[f"{t}_worse_score"].to_numpy(), P[:, k])) for k, t in enumerate(("phase2", "phase3", "phase4", "phase5"))}
res = {"report_status": report["status"], "filled_features": len(report["filled_features"]), "nan_cells_input": nan_in,
       "nan_cells_matrix": nan_mat, "raw_scores_equal_booster": eq, "score_min": float(out[[f"phase{k}_worse_score" for k in (2, 3, 4, 5)]].min().min()),
       "score_max": float(out[[f"phase{k}_worse_score" for k in (2, 3, 4, 5)]].max().max()),
       "phase_counts": out["overall_phase_pred"].value_counts().sort_index().to_dict(), "thresholds": summary["thresholds"],
       "monotonicity": summary["monotonicity_policy"]}
json.dump(res, open(run / "runtime_load_check.json", "w"), indent=1, default=str)
print(json.dumps(res, indent=1, default=str))
sys.exit(0 if all(eq.values()) and nan_in == nan_mat and report["status"] == "passed" and not report["filled_features"] else 1)
