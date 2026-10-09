import json, time, sys
import numpy as np, pandas as pd
t0=time.time()
RAW="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_IPCCH/raw/IPCCH_2026_completed.csv"
REF="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/cloud_pipeline/bootstrap/assets/ipcch/history_panel.csv"
PK="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/cloud_pipeline/bootstrap/models/ipcch"
cols=json.load(open(f"{PK}/scope_6m/feature_columns.json"))
P=[f"phase{i}_percent" for i in range(1,6)]
T={"phase2_worse":P[1:],"phase3_worse":P[2:],"phase4_worse":P[3:],"phase5_worse":P[4:]}
h5keys=pd.read_csv("/tmp/sept_bundle/reports/ipcch_training_keys.csv",dtype={"area_id":str})
out={}
for name,path in [("raw_ae696087",RAW),("bootstrap_refreshed_6ab4e447",REF)]:
    s=pd.read_csv(path,usecols=["admin_code","year","month",*P,*cols],dtype={"admin_code":"string"})
    s=s.replace([np.inf,-np.inf],np.nan)
    s["area_id"]=s.admin_code.astype("string").str.strip()
    s["period"]=pd.PeriodIndex(s.year.astype(int).astype(str)+"-"+s.month.astype(int).astype(str).str.zfill(2),freq="M")
    for c in [*P,*cols]: s[c]=pd.to_numeric(s[c],errors="coerce")
    for t,cs in T.items(): s[t]=s[cs].sum(axis=1,min_count=len(cs))
    labels=s.dropna(subset=list(T))[["area_id","period"]].rename(columns={"period":"target_period"})
    res={"rows":len(s),"labeled_rows":len(labels),"read_s":round(time.time()-t0,1)}
    for scope in (0,6,12):
        lab=labels.copy(); lab["feature_period"]=lab.target_period-scope
        tr=s[["area_id","period",*cols]].rename(columns={"period":"feature_period"}).merge(lab,on=["area_id","feature_period"],how="inner",validate="one_to_one")
        tr=tr[tr.feature_period<pd.Period("2026-04",freq="M")]
        med=tr[cols].median(numeric_only=True)
        meta=json.load(open(f"{PK}/scope_{scope}m/model_metadata.json"))["imputation_statistics"]
        diff=max(abs(med[c]-meta[f"median:{c}"]) for c in cols)
        ndiff=sum(1 for c in cols if not np.isclose(med[c],meta[f"median:{c}"],rtol=0,atol=1e-12))
        r={"train_rows":len(tr),"feature_min":str(tr.feature_period.min()),"feature_max":str(tr.feature_period.max()),
           "target_min":str(tr.target_period.min()),"target_max":str(tr.target_period.max()),
           "max_abs_median_diff_vs_saved":float(diff),"n_median_mismatch":ndiff}
        if scope in (6,12):
            k=set(zip(tr.area_id.astype(str),tr.target_period.astype(str)))
            hk=set(zip(h5keys.area_id.astype(str),h5keys.target_period.astype(str)))
            r["target_keys_equal_h5"]=(k==hk)
        res[f"scope_{scope}m"]=r
    out[name]=res
    print(name,json.dumps(res),flush=True)
    del s
json.dump(out,open("/tmp/verify_medians.json","w"),indent=1)
print("done",round(time.time()-t0,1))
