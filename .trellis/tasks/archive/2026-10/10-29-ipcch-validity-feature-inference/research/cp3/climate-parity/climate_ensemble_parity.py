"""CP3 climate ensemble parity (local, read-only). Domain: the delivered MODELING_READY monthly and seasonal tables' own
per-source columns, exactly as delivered (already after the out-of-scope upstream QA/merge, R35). The operational
``climate.ensemble`` rule is applied to them and compared with the delivered ``_ensmean/_n_sources/_ens_sd`` columns of the
13 model bases. No QA rule is added; mismatches are counted and characterised, not hidden."""
import hashlib, json, os, sys, time
import numpy as np, pandas as pd
sys.dont_write_bytecode = True
sys.path.insert(0, "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/cloud_pipeline")
from cloud.ipcch import climate as cl
S = "/mnt/c/users/swl00/ifpri dropbox/weilun shi/IPCCH_shared_folder"
FILES = {"month": ("climate_monthly_2015_2026_MODELING_READY.csv", "8082b72e"),
         "gs": ("climate_2015_2026_MODELING_READY.csv", "f024a66c")}
res = {"domain": __doc__, "tables": {}}
t0 = time.time()
for temporal, (name, sha_prefix) in FILES.items():
    path = os.path.join(S, name)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    sha = h.hexdigest()
    assert sha.startswith(sha_prefix), (name, sha)
    cols = [f"{b}_{temporal}_{s}" for b in cl.BASES for s in cl.SOURCES[b]]
    cols += [f"{b}_{temporal}_{k}" for b in cl.BASES for k in ("ensmean", "n_sources", "ens_sd")]
    d = pd.read_csv(path, usecols=cols, dtype="float64")
    out = {"sha256": sha, "rows": len(d), "bases": {}}
    for b in cl.BASES:
        e = cl.ensemble({s: d[f"{b}_{temporal}_{s}"] for s in cl.SOURCES[b]})
        dm, dn, ds = d[f"{b}_{temporal}_ensmean"].to_numpy(), d[f"{b}_{temporal}_n_sources"].to_numpy(), d[f"{b}_{temporal}_ens_sd"].to_numpy()
        em, en, es = e["value"].to_numpy(), e["n_sources"].to_numpy(), e["ens_sd"].to_numpy()
        both = np.isfinite(dm) & np.isfinite(em)
        sd_both = np.isfinite(ds) & np.isfinite(es)
        mean_nan_mismatch = int((np.isfinite(dm) != np.isfinite(em)).sum())
        n_mismatch = int((np.nan_to_num(dn, nan=-1) != en).sum())
        sd_nan_mismatch = np.isfinite(ds) != np.isfinite(es)
        rec = {"mean_nan_pattern_mismatch": mean_nan_mismatch,
               "mean_max_abs_diff": float(np.max(np.abs(dm[both] - em[both]))) if both.any() else None,
               "n_sources_mismatch": n_mismatch,
               "sd_nan_pattern_mismatch": int(sd_nan_mismatch.sum()),
               "sd_max_abs_diff": float(np.max(np.abs(ds[sd_both] - es[sd_both]))) if sd_both.any() else None,
               "n_counts": {str(int(k)): int(v) for k, v in pd.Series(en).value_counts().sort_index().items()}}
        if sd_nan_mismatch.any():
            idx = np.where(sd_nan_mismatch)[0]
            rec["sd_nan_mismatch_detail"] = {"delivered_sd_values": sorted({float(x) for x in ds[idx] if np.isfinite(x)})[:5],
                                             "operational_n_sources": {str(int(k)): int(v) for k, v in pd.Series(en[idx]).value_counts().items()}}
        if both.any():
            dd = np.abs(dm[both] - em[both]); sdd = np.abs(ds[sd_both] - es[sd_both]) if sd_both.any() else np.array([0.0])
            rec["mean_rows_gt_1e-9"] = int((dd > 1e-9).sum()); rec["sd_rows_gt_1e-9"] = int((sdd > 1e-9).sum())
            rec["mean_rel_max"] = float(np.max(dd / np.maximum(np.abs(dm[both]), 1e-12)))
        out["bases"][b] = rec
    res["tables"][temporal] = out
res["seconds"] = round(time.time() - t0, 1)
json.dump(res, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "climate_ensemble_parity.json"), "w"), indent=1)
print(json.dumps({t: {b: [r["mean_nan_pattern_mismatch"], r["mean_max_abs_diff"], r["n_sources_mismatch"], r["sd_nan_pattern_mismatch"], r["sd_max_abs_diff"]]
                      for b, r in v["bases"].items()} for t, v in res["tables"].items()}, indent=0))
