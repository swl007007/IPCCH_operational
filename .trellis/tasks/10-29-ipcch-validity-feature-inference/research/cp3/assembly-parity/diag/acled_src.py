import json, numpy as np, pandas as pd
T = "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.trellis/tasks/10-29-ipcch-validity-feature-inference/research/cp1/recipes/manifest-local-h02.json"
m = json.load(open(T))
interim = m["files"]["interim"]["uri"]
cols = [f"acled_agg_{g}_{t}" for g in ("events", "fatalities", "exposure", "exposure_share", "spill_events", "spill_fatalities") for t in ("battles", "erv", "vac")]
I = pd.read_csv(interim, usecols=["admin_code", "year", "month", *cols], float_precision="round_trip")
P = pd.read_csv("/home/swl007007/projects/food-crisis-research/staging/ipcch-update-202610/sources/acled_agg/processed/acled_agg_monthly.csv", float_precision="round_trip")
P = P.rename(columns={"area_id": "admin_code"})
print("interim rows", len(I), I.year.min(), I.year.max(), "processed rows", len(P), P.year.min(), P.year.max())
k = ["admin_code", "year", "month"]
M = I.merge(P, on=k, how="outer", suffixes=("_i", "_p"), indicator=True)
print(M["_merge"].value_counts().to_dict())
b = M[M._merge == "both"]
for c in cols[:6] + ["acled_agg_exposure_share_battles"]:
    x, y = b[c + "_i"].to_numpy(float), b[c + "_p"].to_numpy(float)
    nanmis = int((np.isnan(x) != np.isnan(y)).sum()); both = np.isfinite(x) & np.isfinite(y)
    print(c, "nan-mask mismatches", nanmis, "i-NaN/p-val", int((np.isnan(x) & ~np.isnan(y)).sum()), "i-val/p-NaN", int((~np.isnan(x) & np.isnan(y)).sum()),
          "maxabs", float(np.abs(x[both] - y[both]).max()) if both.any() else None)
only_i = M[M._merge == "left_only"]; only_p = M[M._merge == "right_only"]
print("interim-only months", only_i.groupby("year").size().to_dict(), "processed-only", only_p.groupby(["year", "month"]).size().head(12).to_dict())
mis = b[np.isnan(b[cols[0] + "_i"].to_numpy(float)) != np.isnan(b[cols[0] + "_p"].to_numpy(float))]
print("nan-mask mismatch by year-month (events_battles):", mis.groupby(["year", "month"]).size().head(20).to_dict())
