"""Real package check, stage 1 (research env): per horizon rebuild the final fit (replay_fit verifies it against the
trial's ledger/membership), then take 2,000 fit rows and up to 2,000 scored (2026 supplement) rows with the harvested
UBJ boosters' raw quartet scores as probes for the operational runtime loader (stage 2)."""
import json, os, sys, time
import numpy as np
sys.dont_write_bytecode = True
from research_cloud.training import ipcch_validity_pooled as vp
from research_cloud.training.common import Output, resolve_inputs
from research_cloud.packages import operational_ipcch as oi
OUT, REC, HARV = sys.argv[1], sys.argv[2], sys.argv[3]
res = {}
for h in (2, 8, 14):
    t0 = time.time()
    cfg = json.load(open(f"{REC}/config-final-h{h:02d}.json"))
    inputs, manifest = resolve_inputs(f"{REC}/manifest-local-h{h:02d}.json", f"{OUT}/work/h{h:02d}")
    prep = vp.prepare(inputs, cfg, Output(f"{OUT}/work/h{h:02d}/gate"), manifest)
    trial = f"{HARV}/final-h{h:02d}/trial-0"
    r = oi.replay_fit(prep, trial)
    p, d = prep["plans"][0], prep["d"]
    rng = np.random.default_rng(h)
    fit_idx = np.sort(rng.choice(len(r["train"]), size=2000, replace=False))
    rows, X, P = [r["train"][fit_idx]], [r["X"][fit_idx]], [r["P"][fit_idx]]
    score = p.get("score")
    n_score = 0
    if score is not None and len(score):
        score = np.asarray(score, dtype=np.int64)
        score = np.sort(rng.choice(score, size=min(2000, len(score)), replace=False))
        Xs = vp.materialize(d, score, p.get("score_excluded", p.get("train_excluded", p["S_E"])))[0]
        rows.append(score); X.append(Xs); P.append(vp.predict_quartet(r["boosters"], Xs)); n_score = len(score)
    np.save(f"{OUT}/probe_h{h:02d}_rows.npy", np.concatenate(rows))
    np.save(f"{OUT}/probe_h{h:02d}_X.npy", np.concatenate(X))
    np.save(f"{OUT}/probe_h{h:02d}_P.npy", np.concatenate(P))
    res[h] = {"context": r["context"], "fit_rows": int(len(r["train"])), "probe_fit_rows": 2000, "probe_score_rows": n_score,
              "plan_keys": sorted(p.keys()), "seconds": round(time.time() - t0, 1)}
    print(json.dumps({h: res[h]}), flush=True)
json.dump(res, open(f"{OUT}/probe_real.json", "w"), indent=1)
