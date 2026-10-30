import json, os, sys, numpy as np, pandas as pd
sys.path.insert(0, "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/cloud_pipeline")
sys.path.insert(0, "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.trellis/tasks/10-29-ipcch-validity-feature-inference/research/cp3/assembly-parity")
from cloud.ipcch import assembly as asm
from cloud.ipcch.vendor import ipcch_compact as cp
S = "/home/swl007007/projects/food-crisis-research/scratch/h2h8h14-final/assembly-parity"
B = "/home/swl007007/projects/food-crisis-research/scratch/h2h8h14-final/handoff-build/out-r4"
rd = lambda p, **k: pd.read_csv(os.path.join(B, p), float_precision="round_trip", **k)
r = np.load(f"{S}/research_h02.npz"); order = json.load(open(f"{S}/order_h02.json"))
sel = np.flatnonzero(r["gpp_through"] == np.unique(r["gpp_through"])[-1])[:400]
roster = tuple(int(a) for a in rd("fixed/roster.csv")["admin_code"])
interim = {f: rd(f"history/{f}.csv", usecols=["admin_code", "month", "value"]) for f in asm.INTERIM_FAMILIES}
gpp = interim["GPP_mean"]; o = gpp["month"].str[:4].astype(int) * 12 + gpp["month"].str[5:7].astype(int) - 1
interim["GPP_mean"] = gpp[o <= np.unique(r["gpp_through"])[-1]]
_m = json.load(open("/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.trellis/tasks/10-29-ipcch-validity-feature-inference/research/cp1/recipes/manifest-local-h02.json"))
_cols = [f"acled_agg_{g}_{t}" for g in ("events","fatalities","exposure","exposure_share","spill_events","spill_fatalities") for t in ("battles","erv","vac")]
ac = pd.read_csv(_m["files"]["interim"]["uri"], usecols=["admin_code","year","month",*_cols]).rename(columns={"admin_code": "area_id"})   # research load_sources parse
ac = ac.assign(admin_code=ac["area_id"].astype(np.int64), month=ac["year"].astype(str) + "-" + ac["month"].astype(int).map("{:02d}".format))
ac = ac[ac["admin_code"].isin(roster)]
inp = asm.AssemblyInputs(climate_monthly={b: rd(f"history/climate_month_{b}.csv", usecols=["admin_code", "month", "value"]) for b in cp.CLIMATE_BASES},
    climate_seasonal={b: rd(f"history/climate_gs_{b}.csv", usecols=["admin_code", "season_year", "season", "value"]) for b in cp.CLIMATE_BASES},
    season_windows=rd("fixed/season_windows.csv"), interim=interim, acled=ac, idp_national=rd("history/idp_national.csv", keep_default_na=False),
    idp_local=rd("history/idp_local.csv", usecols=["admin_code", "month", "value"]), snapshot=rd("history/history_snapshot.csv"),
    static29=rd("fixed/static29.csv"), descriptors=rd("fixed/ae_descriptors.csv"), identity=rd("fixed/area_identity.csv", keep_default_na=False, na_values=[""]),
    roster=roster, order=tuple(order))
X, led = asm.assemble(inp, 2, r["admin"][sel], r["target"][sel])
got, want = X.to_numpy(float), r["X"][sel]
for c in ["lat", "acled_agg_events_battles__value_at_origin_lag1", "acled_agg_events_battles__ma12_at_origin_lag1", "acled_agg_exposure_share_vac__sd12_at_origin_lag1"]:
    j = order.index(c)
    d = ~((got[:, j] == want[:, j]) | (np.isnan(got[:, j]) & np.isnan(want[:, j])))
    print(c, "mismatch rows", int(d.sum()), "of", len(sel))
    for i in np.flatnonzero(d)[:4]:
        print("   admin", int(r["admin"][sel][i]), "target", int(r["target"][sel][i]), "A_ord", int(led["acled_cutoff_ord"][i]), "ops", got[i, j], "research", want[i, j])


acols = [j for j, c in enumerate(order) if c.startswith("acled_agg_")]
d = ~((got[:, acols] == want[:, acols]) | (np.isnan(got[:, acols]) & np.isnan(want[:, acols])))
print("ACLED cells differing with the research parse:", int(d.sum()), "of", d.size)
