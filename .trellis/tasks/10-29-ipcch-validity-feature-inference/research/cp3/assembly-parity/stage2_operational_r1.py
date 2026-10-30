"""Assembly parity stage 2 (operational exact-lock env): cloud.ipcch.assembly on the CP2 handoff bundle (r4) for the
stage-1 keys, GPP history masked to each row's R57 cutoff (the training simulation; the runtime itself never filters),
aggregated ACLED from the research monthly series (the weekly-store port has its own parity, cp3c2-acled.md). Every
column is compared NaN-aware and bit-exact; mismatches are counted and characterised."""
import json, os, sys, time
import numpy as np, pandas as pd
sys.dont_write_bytecode = True
sys.path.insert(0, "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/cloud_pipeline")
from cloud.ipcch import assembly as asm
from cloud.ipcch.vendor import ipcch_compact as cp
STAGE1, BUNDLE, ACLED, PKG = sys.argv[1:5]
rd = lambda p, **k: pd.read_csv(os.path.join(BUNDLE, p), float_precision="round_trip", **k)
t0 = time.time()
roster = tuple(int(a) for a in rd("fixed/roster.csv")["admin_code"])
monthly = {b: rd(f"history/climate_month_{b}.csv", usecols=["admin_code", "month", "value"]) for b in cp.CLIMATE_BASES}
seasonal = {b: rd(f"history/climate_gs_{b}.csv", usecols=["admin_code", "season_year", "season", "value"]) for b in cp.CLIMATE_BASES}
interim = {f: rd(f"history/{f}.csv", usecols=["admin_code", "month", "value"]) for f in asm.INTERIM_FAMILIES}
acled = pd.read_csv(ACLED, float_precision="round_trip")
acled = acled.assign(admin_code=acled["area_id"].astype(np.int64), month=acled["year"].astype(str) + "-" + acled["month"].astype(int).map("{:02d}".format))
acled = acled[acled["admin_code"].isin(roster)]
order = tuple(json.load(open(os.path.join(PKG, "scope_0m", "feature_columns.json"))))
base = dict(climate_monthly=monthly, climate_seasonal=seasonal, season_windows=rd("fixed/season_windows.csv"), acled=acled,
            idp_national=rd("history/idp_national.csv", keep_default_na=False), idp_local=rd("history/idp_local.csv", usecols=["admin_code", "month", "value"]),
            snapshot=rd("history/history_snapshot.csv"), static29=rd("fixed/static29.csv"), descriptors=rd("fixed/ae_descriptors.csv"),
            identity=rd("fixed/area_identity.csv", keep_default_na=False, na_values=[""]), roster=roster, order=order)
print("loaded", round(time.time() - t0, 1), flush=True)
gpp = interim["GPP_mean"]
gpp_ord = gpp["month"].str[:4].astype(int) * 12 + gpp["month"].str[5:7].astype(int) - 1
result = {"order_equals_package": None, "horizons": {}}
for h in (2, 8, 14):
    r = np.load(os.path.join(STAGE1, f"research_h{h:02d}.npz"))
    research_order = json.load(open(os.path.join(STAGE1, f"order_h{h:02d}.json")))
    result["order_equals_package"] = (result["order_equals_package"] is not False) and tuple(research_order) == order
    Xr = r["X"]; got = np.full_like(Xr, np.nan)
    for thr in np.unique(r["gpp_through"]):
        sel = np.flatnonzero(r["gpp_through"] == thr)
        inter = dict(interim, GPP_mean=gpp[gpp_ord <= thr])
        X, _ = asm.assemble(asm.AssemblyInputs(interim=inter, **base), h, r["admin"][sel], r["target"][sel])
        got[sel] = X.to_numpy(float)
    same = (got == Xr) | (np.isnan(got) & np.isnan(Xr))
    bad_cols = np.flatnonzero(~same.all(axis=0))
    per_col = {order[j]: {"rows": int((~same[:, j]).sum()), "nan_mismatch": int((np.isnan(got[:, j]) != np.isnan(Xr[:, j])).sum()),
                          "max_abs": float(np.nanmax(np.abs(got[:, j] - Xr[:, j]))) if np.isfinite(got[:, j] - Xr[:, j]).any() else None,
                          "scored_rows": int((~same[r["scored"], j]).sum())} for j in bad_cols}
    result["horizons"][h] = {"rows": int(len(Xr)), "cells": int(Xr.size), "cells_equal": int(same.sum()),
                             "columns_exact": int(len(order) - len(bad_cols)), "columns_differing": per_col}
    print(json.dumps({h: {k: v for k, v in result["horizons"][h].items() if k != "columns_differing"} | {"differing": list(per_col)[:12]}}), flush=True)
result["seconds"] = round(time.time() - t0, 1)
json.dump(result, open(os.path.join(STAGE1, "stage2_parity.json"), "w"), indent=1)
