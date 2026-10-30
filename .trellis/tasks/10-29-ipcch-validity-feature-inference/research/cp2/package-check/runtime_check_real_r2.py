"""Real package check, stage 2 r2 (operational exact-lock env). Repairs r1's receipt identity: the package id is the
manifest's ``combination_id`` (r1 read a non-existent key -> "None"), and each scope's nominal dates follow the operational
mapping for execution month M = 2026-10: feature_month O = M - 2 = 2026-08, target_month = M + scope (2026-10 / 2027-04 /
2027-10). The summary/output identity and dates are asserted.

SCOPE OF THIS EVIDENCE: historical feature probes (stage-1 rows from the rebuilt 2010-2026 fit/scored matrices) scored
through model_pipeline.ipcch_launch_runtime on the RELOCATED package for raw-score parity with the harvested UBJ boosters.
The dates are identity labels only; this is NOT current-month generation/scoring (real current-month features, target-year
dummies and E2E are CP5)."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.dont_write_bytecode = True
sys.path.insert(0, "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/cloud_pipeline")
from model_pipeline.ipcch_launch_runtime.model_package import load_scope_package
from model_pipeline.ipcch_launch_runtime.feature_contract import apply_feature_contract
from model_pipeline.ipcch_launch_runtime.inference import score_scope
M, O = "2026-10", "2026-08"


def add_months(month, k):
    y, m = (int(x) for x in month.split("-"))
    o = y * 12 + m - 1 + k
    return f"{o // 12:04d}-{o % 12 + 1:02d}"


pkg_root, probes = Path(sys.argv[1]), Path(sys.argv[2])
man = json.load(open(pkg_root / "package_manifest.json"))
pid = man.get("combination_id")
assert isinstance(pid, str) and pid, "package_manifest.json has no combination_id"
res = {"evidence_scope": "historical feature probes for raw-score parity; not current-month E2E (CP5)",
       "package_root": str(pkg_root), "combination_id": pid, "package_status": man.get("status"),
       "execution_month": M, "feature_month": O}
ok = man.get("status") == "candidate"
for h, s in ((2, 0), (8, 6), (14, 12)):
    target = add_months(M, s)
    pkg = load_scope_package(pkg_root, s)
    X, P, rows = (np.load(probes / f"probe_h{h:02d}_{k}.npy") for k in ("X", "P", "rows"))
    monthly = pd.DataFrame(X, columns=pkg["feature_columns"])
    monthly.insert(0, "area_id", rows)
    for c, v in (("population_estimate", 1000.0), ("population_reference_period", O), ("population_imputation_method", "observed_feature_month")):
        monthly[c] = v      # probe identity columns required by score_scope (not model features)
    matrix, report = apply_feature_contract(monthly, pkg["contract"], pkg["feature_columns"], package_root=pkg_root, metadata=pkg["metadata"])
    out, summary = score_scope(monthly_rows=monthly, feature_matrix=matrix, models=pkg["models"], thresholds=pkg["metadata"]["thresholds"],
                               scope_months=s, feature_month=O, target_month=target, model_package_id=pid,
                               source_input="historical-feature-probe", monotonicity_policy=pkg["metadata"]["monotonicity_policy"])
    eq = {t: bool(np.array_equal(out[f"{t}_worse_score"].to_numpy(), P[:, k])) for k, t in enumerate(("phase2", "phase3", "phase4", "phase5"))}
    nan_in, nan_mat = int(np.isnan(X).sum()), int(matrix.isna().to_numpy().sum())
    identity = {"summary_scope_months": summary["scope_months"] == s, "summary_feature_month": summary["feature_month"] == O,
                "summary_target_month": summary["target_month"] == target, "summary_rows": summary["row_count"] == len(X),
                "output_package_id": set(out["model_package_id"]) == {pid}, "output_feature_period": set(out["feature_period"]) == {O},
                "output_target_period": set(out["target_period"]) == {target}, "output_scope": set(out["scope_months"]) == {s}}
    r = {"scope": s, "target_month": target, "rows": int(len(X)), "features": len(pkg["feature_columns"]),
         "report_status": report["status"], "filled_features": len(report["filled_features"]), "nan_cells_input": nan_in,
         "nan_cells_matrix": nan_mat, "raw_scores_equal_booster": eq, "identity_and_dates": identity,
         "thresholds": summary["thresholds"], "monotonicity": summary["monotonicity_policy"],
         "phase_counts": {str(k): int(v) for k, v in out["overall_phase_pred"].value_counts().sort_index().items()}}
    r["ok"] = (all(eq.values()) and all(identity.values()) and nan_in == nan_mat and report["status"] == "passed"
               and not report["filled_features"])
    ok &= r["ok"]; res[f"H{h}"] = r
    print(json.dumps({f"H{h}": {k: r[k] for k in ("target_month", "rows", "raw_scores_equal_booster", "ok")}}), flush=True)
res["ok"] = bool(ok)
json.dump(res, open(probes / "runtime_check_real_r2.json", "w"), indent=1, default=str)
sys.exit(0 if ok else 1)
