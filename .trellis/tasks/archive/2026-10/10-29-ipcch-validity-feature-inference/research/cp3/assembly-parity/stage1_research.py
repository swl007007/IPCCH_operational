"""Assembly parity stage 1 (research env): per H, the research final matrix for every scored (2026) row and 3,000 random
fit rows, rebuilt with history WITHOUT training-context family exclusions (operational history has none), plus each
row's R57 GPP availability cutoff (training simulation) so stage 2 can feed the same GPP months."""
import json, os, sys, time
import numpy as np
sys.dont_write_bytecode = True
from research_cloud.training import ipcch_validity_pooled as vp, ipcch_validity_features as vf
from research_cloud.training.common import Output, resolve_inputs
OUT, REC = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
summary = {}
for h in (2, 8, 14):
    t0 = time.time()
    cfg = json.load(open(f"{REC}/config-final-h{h:02d}.json"))
    inputs, manifest = resolve_inputs(f"{REC}/manifest-local-h{h:02d}.json", f"{OUT}/work/h{h:02d}")
    prep = vp.prepare(inputs, cfg, Output(f"{OUT}/work/h{h:02d}/gate"), manifest)
    d, p = prep["d"], prep["plans"][0]
    rng = np.random.default_rng(100 + h)
    train = np.asarray(p["train"], np.int64)
    rows = np.unique(np.concatenate([np.asarray(p["score"], np.int64), rng.choice(train, 3000, replace=False)]))
    X = vp.materialize(d, rows, np.array([], np.int64))[0]
    origin = d.target[rows] - h
    np.savez_compressed(f"{OUT}/research_h{h:02d}.npz", X=X, admin=d.admin[rows], target=d.target[rows],
                        gpp_through=np.asarray(vf.gpp_available_through(origin), np.int64), scored=np.isin(rows, p["score"]))
    json.dump(list(d.order), open(f"{OUT}/order_h{h:02d}.json", "w"))
    summary[h] = {"rows": int(len(rows)), "scored": int(len(p["score"])), "seconds": round(time.time() - t0, 1)}
    print(json.dumps({h: summary[h]}), flush=True)
json.dump(summary, open(f"{OUT}/stage1.json", "w"), indent=1)
