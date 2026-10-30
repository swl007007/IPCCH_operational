"""Assembly parity stage 3 (operational exact-lock env): EFFECTIVE model inputs and outputs. For each H, the stage-2
assembled array and the research array are cast to the float32 XGBoost consumes and compared bitwise (NaN-aware), and
both are scored through the package's operational runtime (model_pipeline.ipcch_launch_runtime) - raw q2..q5 scores
compared bitwise. Machine verdict: EFFECTIVE_IDENTICAL (rc 0) / EFFECTIVE_DIFFERS (rc 2); other rc = failure."""
import json, os, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.dont_write_bytecode = True
sys.path.insert(0, "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/cloud_pipeline")
from model_pipeline.ipcch_launch_runtime.model_package import load_scope_package
from model_pipeline.ipcch_launch_runtime.feature_contract import apply_feature_contract
from model_pipeline.ipcch_launch_runtime.inference import score_scope
STAGE1, STAGE2_JSON, PKG, OUT = sys.argv[1:5]
if os.path.exists(OUT):
    raise SystemExit(f"{OUT} exists; never overwrite earlier evidence")
pkg_root = Path(PKG)
pid = json.load(open(pkg_root / "package_manifest.json"))["combination_id"]
res, ok = {"stage2": STAGE2_JSON, "package": str(pkg_root), "combination_id": pid, "horizons": {}}, True


def scores(X, pkg, s, admin):
    monthly = pd.DataFrame(X, columns=pkg["feature_columns"])
    monthly.insert(0, "area_id", admin)
    for c, v in (("population_estimate", 1000.0), ("population_reference_period", "2026-08"), ("population_imputation_method", "observed_feature_month")):
        monthly[c] = v
    matrix, report = apply_feature_contract(monthly, pkg["contract"], pkg["feature_columns"], package_root=pkg_root, metadata=pkg["metadata"])
    out, _ = score_scope(monthly_rows=monthly, feature_matrix=matrix, models=pkg["models"], thresholds=pkg["metadata"]["thresholds"],
                         scope_months=s, feature_month="2026-08", target_month="2026-10", model_package_id=pid,
                         source_input="historical-feature-probe", monotonicity_policy=pkg["metadata"]["monotonicity_policy"])
    return np.column_stack([out[f"phase{k}_worse_score"].to_numpy() for k in (2, 3, 4, 5)]), report


for h, s in ((2, 0), (8, 6), (14, 12)):
    r = np.load(os.path.join(STAGE1, f"research_h{h:02d}.npz"))
    got = np.load(STAGE2_JSON[:-5] + f"_assembled_h{h:02d}.npy")
    want = r["X"]
    g32, w32 = got.astype(np.float32), want.astype(np.float32)
    f32_same = (g32 == w32) | (np.isnan(g32) & np.isnan(w32))
    f64_same = (got == want) | (np.isnan(got) & np.isnan(want))
    pkg = load_scope_package(pkg_root, s)
    sg, rep_g = scores(got, pkg, s, r["admin"])
    sw, rep_w = scores(want, pkg, s, r["admin"])
    score_same = (sg == sw)
    rec = {"rows": int(len(got)), "float64_cells_differing": int((~f64_same).sum()),
           "float32_cells_differing": int((~f32_same).sum()),
           "float32_columns_differing": [pkg["feature_columns"][j] for j in np.flatnonzero(~f32_same.all(axis=0))][:20],
           "raw_scores_differing": {f"q{k}": int((~score_same[:, i]).sum()) for i, k in enumerate((2, 3, 4, 5))},
           "contract_reports": [rep_g["status"], rep_w["status"]]}
    rec["identical"] = rec["float32_cells_differing"] == 0 and not any(rec["raw_scores_differing"].values())
    ok &= rec["identical"]
    res["horizons"][h] = rec
    print(json.dumps({h: rec}), flush=True)
res["verdict"] = "EFFECTIVE_IDENTICAL" if ok else "EFFECTIVE_DIFFERS"
json.dump(res, open(OUT, "w"), indent=1)
print(json.dumps({"verdict": res["verdict"]}))
sys.exit(0 if ok else 2)
