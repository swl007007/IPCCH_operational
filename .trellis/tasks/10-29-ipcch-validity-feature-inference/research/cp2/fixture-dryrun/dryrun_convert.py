"""FIXTURE-ONLY dry run (task 10-29 C7): the retained 10-28 H0 h00_supp_2026 boosters (NOT a new model; never a
substitute for the H2/H8/H14 artifacts) applied to the real rebuilt H2 final fit matrix, to exercise the C7 conversion
at full scale (JSON == UBJ scores on every fitted row) and produce a scope directory for the operational runtime loader."""
import json, os, sys, time
import numpy as np, pandas as pd
sys.dont_write_bytecode = True
from research_cloud.training import ipcch_validity_pooled as vp
from research_cloud.training.common import Output, resolve_inputs
from research_cloud.packages import operational_ipcch as oi
OUT = sys.argv[1]
REC = ("/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.trellis/tasks/10-29-ipcch-validity-feature-inference/"
       "research/cp1/recipes")
OLD = "/home/swl007007/projects/food-crisis-research/scratch/ch-validity-20261028/harvest/formal-h00/trial-0/package"
t0 = time.time()
cfg = json.load(open(f"{REC}/config-final-h02.json"))
inputs, manifest = resolve_inputs(f"{REC}/manifest-local-h02.json", f"{OUT}/work")
prep = vp.prepare(inputs, cfg, Output(f"{OUT}/gate"), manifest)
d, p = prep["d"], prep["plans"][0]
old_order = pd.read_csv(f"{OLD}/deps/feature_order.csv")
old_order = old_order["name"].tolist() if "name" in old_order.columns else old_order.iloc[:, -1].tolist()
assert old_order == list(prep["order"]), "fixture booster order differs from the final order"
train = np.asarray(p["train"], dtype=np.int64)
X = vp.materialize(d, train, p.get("train_excluded", p["S_E"]))[0]
boosters, _ = oi.load_boosters(OLD, "h00_supp_2026")
P = vp.predict_quartet(boosters, X)
replay = {"d": d, "train": train, "X": X, "P": P, "record": {}, "context": "FIXTURE:h00_supp_2026(10-28 H0)",
          "cutoff": p["block"].cutoff, "boosters": boosters, "weights": vp.fit_weights(d, train, p["block"].cutoff)}
os.makedirs(f"{OUT}/package")
rec = oi.convert_scope(replay, prep["order"], 2, f"{OUT}/package/scope_0m", "FIXTURE-NOT-A-MODEL", {"fixture": OLD})
area, res, audit, ident = oi.evidence_frames(replay, "FIXTURE-NOT-A-MODEL", 0)
np.save(f"{OUT}/probe_rows.npy", train[:2000])
np.save(f"{OUT}/probe_X.npy", X[:2000])
np.save(f"{OUT}/probe_P.npy", P[:2000])
json.dump({"fixture": "10-28 H0 boosters on the H2 final fit matrix (dry run only)", "rows": int(len(train)),
           "json_equals_ubj_on_all_rows": True, "scope": rec, "evidence_identity": ident, "areas": int(len(area)),
           "errors": int(area["error_count"].sum()), "seconds": round(time.time() - t0, 1)},
          open(f"{OUT}/dryrun.json", "w"), indent=1)
print(open(f"{OUT}/dryrun.json").read())
