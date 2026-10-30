"""Characterise the seasonal rows where the delivered table's ensemble differs from the accepted equal-valid-source rule
(read-only; no rule is changed). For each base: delivered vs operational n_sources, which finite source the delivered
mean omits (by matching the delivered mean to a subset of sources), season_year, and the delivered SD for single sources."""
import itertools, json, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/cloud_pipeline")
from cloud.ipcch import climate as cl
S = "/mnt/c/users/swl00/ifpri dropbox/weilun shi/IPCCH_shared_folder/climate_2015_2026_MODELING_READY.csv"
bases = ["prcp_z", "rainy_days", "cdd", "tmean_anom", "tmax_anom", "hot_days_p95", "gdd", "edd"]
cols = ["admin_code", "season_year", "season"] + [f"{b}_gs_{s}" for b in bases for s in cl.SOURCES[b]] + \
       [f"{b}_gs_{k}" for b in bases for k in ("ensmean", "n_sources", "ens_sd")]
d = pd.read_csv(S, usecols=cols)
out = {}
for b in bases:
    srcs = cl.SOURCES[b]
    e = cl.ensemble({s: d[f"{b}_gs_{s}"] for s in srcs})
    dm, dn, ds = d[f"{b}_gs_ensmean"], d[f"{b}_gs_n_sources"], d[f"{b}_gs_ens_sd"]
    mean_diff = (dm - e["value"]).abs() > 1e-9
    sd_case = dn.eq(1) & ds.eq(0)
    rows = d[mean_diff | sd_case | (dn.fillna(-1).to_numpy() != e["n_sources"].to_numpy())]
    detail = []
    for i, r in rows.iterrows():
        finite = [s for s in srcs if np.isfinite(r[f"{b}_gs_{s}"])]
        match = [list(c) for k in range(1, len(finite) + 1) for c in itertools.combinations(finite, k)
                 if abs(np.mean([r[f"{b}_gs_{s}"] for s in c]) - r[f"{b}_gs_ensmean"]) < 1e-9]
        detail.append({"season_year": int(r["season_year"]), "delivered_n": None if pd.isna(r[f"{b}_gs_n_sources"]) else int(r[f"{b}_gs_n_sources"]),
                       "finite_sources": finite, "delivered_mean_equals_mean_of": match[:1], "delivered_sd": r[f"{b}_gs_ens_sd"]})
    f = pd.DataFrame(detail)
    out[b] = {"rows": len(f),
              "by_season_year": {str(k): int(v) for k, v in f["season_year"].value_counts().sort_index().items()} if len(f) else {},
              "delivered_n_vs_finite": {f"{a}/{c}": int(v) for (a, c), v in f.assign(nf=f["finite_sources"].map(len)).groupby(["delivered_n", "nf"]).size().items()} if len(f) else {},
              "omitted_source": {str(k): int(v) for k, v in f.apply(lambda r: ",".join(sorted(set(r["finite_sources"]) - set((r["delivered_mean_equals_mean_of"] or [[]])[0]))) if r["delivered_mean_equals_mean_of"] else "no-subset-match", axis=1).value_counts().items()} if len(f) else {},
              "single_source_sd_zero": int(sd_case.sum())}
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "seasonal_divergence_detail.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
