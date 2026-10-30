"""CP3 ACLED port parity (local, read-only inputs): the operational converter on the research raw exports and delivered
work tables must reproduce research processed/acled_agg_monthly.csv on its keys, 2010-01..2026-09, all 18 columns."""
import hashlib, json, os, sys, tempfile, time
import numpy as np, pandas as pd
sys.dont_write_bytecode = True
sys.path.insert(0, "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/cloud_pipeline")
from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import acled as ac
from cloud.ipcch.stores import StoreRoot, VersionedTable
S = "/home/swl007007/projects/food-crisis-research/staging/ipcch-update-202610/sources/acled_agg"
W = f"{S}/work"
t0 = time.time()
man = json.load(open(f"{S}/raw/aggregated_2026-10-20/exports_manifest.json"))
regions = man["f3_region_filter"]["kept_regions_f1_f2"]
frames = []
for name, rec in man["files"].items():
    p = f"{S}/raw/aggregated_2026-10-20/{name}"
    assert hashlib.sha256(open(p, "rb").read()).hexdigest() == rec["sha256"]
    frames.append(pd.read_csv(p, dtype=str, keep_default_na=False))
raw = pd.concat(frames, ignore_index=True)
raw = raw[raw["region"].isin(regions)].reset_index(drop=True)          # operator exports the declared regions only
tables = ac.AcledTables.from_files({"mapping": f"{W}/acled_admin1_to_poly.csv", "population": f"{W}/admin1_population.csv",
                                    "neighbours": f"{W}/admin1_neighbours.csv", "coverage_start": f"{W}/coverage_start.csv",
                                    "unit_weights": f"{W}/unit_admin1_weights.csv", "unit_iso3": f"{W}/unit_iso3.csv"})
rows, rep = ac.parse_export(raw, start="2009-12-26", end="2026-10-16", regions=regions, tables=tables)
tmp = tempfile.mkdtemp()
t = VersionedTable(LocalObjectStore(tmp), StoreRoot("real", "gs://p/ipcch-v2/real"), "acled_weekly")
head = ac.refresh(t, rows, start="2009-12-26", end="2026-10-16", regions=regions, source_ref={"sha256": "x" * 64},
                  feature_origin="2026-08", tables=tables)
weekly, records, _ = ac.saved_weekly(t)
ref = pd.read_csv(f"{S}/processed/acled_agg_monthly.csv", float_precision="round_trip")
ref["admin_code"] = ref["area_id"].astype(str)
ref["month"] = ref["year"].astype(str) + "-" + ref["month"].map(lambda m: f"{m:02d}")
months = sorted(ref["month"].unique())
units = sorted(ref["admin_code"].unique())
out = ac.monthly_series(weekly, records, tables, months, units)
m = ref[["admin_code", "month", *ac.COLS]].merge(out, on=["admin_code", "month"], suffixes=("_r", "_o"), how="left", validate="one_to_one")
res = {"ref_rows": int(len(ref)), "matched": int(m[[f"{c}_o" for c in ac.COLS]].notna().any(axis=1).sum() + m[[f"{c}_r" for c in ac.COLS]].isna().all(axis=1).sum()),
       "parse_report": rep, "weekly_rows": int(len(weekly)), "coverage_end_2026_09": ac.coverage_end(records, tables, "2026-09"), "columns": {}}
ok = True
for c in ac.COLS:
    r, o = m[f"{c}_r"].to_numpy(float), m[f"{c}_o"].to_numpy(float)
    nan_eq = bool((np.isnan(r) == np.isnan(o)).all())
    both = ~np.isnan(r) & ~np.isnan(o)
    maxdiff = float(np.abs(r[both] - o[both]).max()) if both.any() else 0.0
    res["columns"][c] = {"nan_pattern_equal": nan_eq, "max_abs_diff": maxdiff, "nonnull": int(both.sum())}
    ok &= nan_eq and maxdiff <= 1e-9
res["ok"], res["seconds"] = bool(ok), round(time.time() - t0, 1)
json.dump(res, open(os.path.join(os.path.dirname(__file__), "acled_parity_result.json"), "w"), indent=1)
print(json.dumps({k: res[k] for k in ("ref_rows", "weekly_rows", "coverage_end_2026_09", "ok", "seconds")}))
print({c: (v["nan_pattern_equal"], v["max_abs_diff"]) for c, v in res["columns"].items() if not (v["nan_pattern_equal"] and v["max_abs_diff"] <= 1e-9)})
sys.exit(0 if ok else 1)
