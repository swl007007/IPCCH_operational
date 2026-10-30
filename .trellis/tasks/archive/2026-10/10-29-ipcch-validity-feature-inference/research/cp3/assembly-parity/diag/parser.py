import json, numpy as np, pandas as pd
m = json.load(open("/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.trellis/tasks/10-29-ipcch-validity-feature-inference/research/cp1/recipes/manifest-local-h02.json"))
cols = [f"acled_agg_{g}_{t}" for g in ("events", "fatalities", "exposure", "exposure_share", "spill_events", "spill_fatalities") for t in ("battles", "erv", "vac")]
use = ["admin_code", "year", "month", *cols]
default = pd.read_csv(m["files"]["interim"]["uri"], usecols=use)                      # the research load_sources call
exact = pd.read_csv(m["files"]["interim"]["uri"], usecols=use, float_precision="round_trip")
print("pandas", pd.__version__)
for c in cols:
    a, b = default[c].to_numpy(float), exact[c].to_numpy(float)
    both = np.isfinite(a) & np.isfinite(b)
    n = int((a[both] != b[both]).sum())
    if n:
        print(c, "cells default!=round_trip", n, "max abs", float(np.abs(a[both] - b[both]).max()), "max rel", float((np.abs(a[both] - b[both]) / np.abs(b[both])).max()))
print("NaN masks equal:", all((np.isnan(default[c]) == np.isnan(exact[c])).all() for c in cols))
