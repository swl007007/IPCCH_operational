"""Negative tests for recompute_origin.py reporting (Supervisor review of sha 634e94ad): NA reasons from the primitive's
own NA conditions, declared/observed window reconciliation and display (H6 partial 2023, H12 empty 2023), and the CH-final
metrics.json baseline reconciliation. Synthetic, consistent job/CH-final trial directories pass; each single mutation is
reported. Does not import the training code.

  python3 -B test_recompute_origin.py
"""
import copy, json, os, subprocess, sys, tempfile
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import recompute_origin as r  # noqa: E402


def frames(h, seed=0):
    rng = np.random.default_rng(seed)
    ctx, _ = r.calendar(h)
    rows = []
    for c, (role, a, b) in ctx.items():
        for t in range(a, b + 1):
            for adm in range(5):
                rows.append({"horizon": h, "context": c, "period": role, "admin_code": adm, "target_ord": t, "iso2": "TD",
                             "label_kind": "original" if (adm + t) % 3 == 0 else "copy", "source_family": adm * 1000 + t})
    base = pd.DataFrame(rows)
    base["phase_truth"] = rng.integers(1, 6, len(base))
    for q in ("q2", "q3", "q4", "q5"):
        base[f"{q}_truth"] = rng.random(len(base))
    old, new = base.copy(), base.copy()
    for f in (old, new):
        f["phase"] = rng.integers(1, 6, len(f))
        f["q3_star"] = rng.random(len(f))
    return new, old


def job_files(h, new, old, d):
    """Consistent job and CH-final trial directories derived from the recompute's own cells (the job format)."""
    m, _ = r.pair(new, old, h)
    mine = r.cells(m, h)
    nd, cd = os.path.join(d, "new"), os.path.join(d, "ch")
    os.makedirs(nd), os.makedirs(cd)
    job = {"cells": {}}
    pub = {}
    for n, c in mine.items():
        g0 = c["groups"]["original"]
        job["cells"][n] = {"declared_from": g0["declared_from"], "declared_to": g0["declared_to"], r.DELTA: c[r.DELTA], "groups": {}}
        for g in r.GROUPS:
            b = c["groups"][g]
            job["cells"][n]["groups"][g] = {**{k: b[k] for k in ("n_rows", "original_rows", "copy_rows", "observed_from", "observed_to", *r.METRICS)},
                                            "na_reasons": b["na_reasons"]}
            pub[f"origin.{n}.{g}.n_rows"] = float(b["n_rows"])
            pub.update({f"origin.{n}.{g}.{k}": b[k] for k in r.METRICS if b[k] is not None})
        pub.update({f"origin.{n}.{r.DELTA}.{k}": v for k, v in c[r.DELTA].items() if v is not None})

    def scopes(f):
        out, sc = {}, r.whole(f, h)
        for n, s in sc.items():
            out[n] = {k: s[k] for k in ("n_rows", "original_rows", "copy_rows", *r.METRICS)}
            out[n]["na_reasons"] = {k: "x" for k in r.METRICS if s[k] is None}
        return out, {**{f"{n}.{k}": s[k] for n, s in sc.items() for k in r.METRICS if s[k] is not None},
                     **{f"{n}.n_rows": float(s["n_rows"]) for n, s in sc.items()}}
    ns, nsc = scopes(new)
    cs, csc = scopes(old)
    json.dump(job, open(f"{nd}/origin_comparison.json", "w"))
    json.dump({"scopes": ns}, open(f"{nd}/metrics.json", "w"))
    json.dump({"trial": {"metrics": {**pub, **nsc}}}, open(f"{nd}/publication.json", "w"))
    json.dump({"scopes": cs}, open(f"{cd}/metrics.json", "w"))
    json.dump({"trial": {"metrics": csc}}, open(f"{cd}/publication.json", "w"))
    return mine, nd, cd


def run_reconcile(h, new, old, nd, cd, mine):
    return r.reconcile(h, mine, nd, cd, r.whole(new, h), r.whole(old, h), False)


def mutate(path, fn):
    j = json.load(open(path))
    fn(j)
    json.dump(j, open(path, "w"))


def main():
    res = {}
    # reasons from the primitive's own NA conditions
    g = pd.DataFrame({"phase_truth": [1, 2, 2], "phase": [1, 1, 2], "q3_truth": [0.1, 0.1, 0.1], "q3_star": [0.2, 0.1, 0.0],
                      "target_ord": [1, 2, 3], "label_kind": "original"})
    m = r.metrics(g)
    w = r.reasons(g, m)
    res["reasons_no_crisis"] = (sorted(m["na"]) == sorted(["binary_precision", "binary_recall", "binary_f1", "binary_f2", "macro_f1", "phase3plus_r2"])
                                and "tp + fp = 0" in w["binary_precision"] and "tp + fn = 0" in w["binary_recall"]
                                and "['3', '4-5']" in w["macro_f1"] and w["phase3plus_r2"] == "constant q3 truth")
    g1 = g.iloc[:1]
    res["reasons_single_row"] = r.reasons(g1, r.metrics(g1))["phase3plus_r2"] == "fewer than 2 rows (n = 1)"
    # H12 empty 2023 and H6 partial 2023 (declared/observed shown)
    for h in (6, 12):
        new, old = frames(h)
        d = tempfile.mkdtemp()
        mine, nd, cd = job_files(h, new, old, d)
        c23 = mine["historical_2023"]
        if h == 12:
            res["h12_2023_empty_reason"] = all(c23["groups"][k]["na_reasons"].get("binary_f1", "").startswith("no evaluation rows: 2023 precedes the H12")
                                               for k in r.GROUPS) and "binary_f1" in c23["delta_na_reasons"]
        else:
            res["h6_2023_declared_partial"] = (c23["groups"]["augmented_total"]["declared_from"], c23["groups"]["augmented_total"]["declared_to"],
                                               c23["groups"]["augmented_total"]["observed_from"]) == ("2023-07", "2023-12", "2023-07")
        res[f"h{h}_consistent_passes"] = run_reconcile(h, new, old, nd, cd, mine) == []
    h = 6
    new, old = frames(h, 1)
    cases = {
        "observed_from_mutated": ("new/origin_comparison.json", lambda j: j["cells"]["historical_2024"]["groups"]["original"].update(observed_from="2024-02"), "observed_from"),
        "declared_mutated": ("new/origin_comparison.json", lambda j: j["cells"]["historical_2023"].update(declared_from="2023-01"), "declared_from"),
        "copy_rows_mutated": ("new/origin_comparison.json", lambda j: j["cells"]["holdout_2026_01_10"]["groups"]["augmented_total"].update(copy_rows=-1), "copy_rows"),
        "ch_metrics_json_count": ("ch/metrics.json", lambda j: j["scopes"]["historical_pooled"].update(original_rows=0), "original_rows"),
        "ch_metrics_json_value": ("ch/metrics.json", lambda j: j["scopes"]["historical_2025"].update(binary_f1=0.123), "binary_f1"),
        "ch_metrics_json_scope_missing": ("ch/metrics.json", lambda j: j["scopes"].pop("historical_2024"), "scopes"),
        "new_metrics_json_value": ("new/metrics.json", lambda j: j["scopes"]["holdout_2026_01_10"].update(macro_f1=0.5), "macro_f1"),
    }
    for name, (rel, fn, needle) in cases.items():
        d = tempfile.mkdtemp()
        mine, nd, cd = job_files(h, new, old, d)
        mutate(os.path.join(d, rel), fn)
        probs = run_reconcile(h, new, old, nd, cd, mine)
        res[name] = bool(probs) and any(needle in p for p in probs)
    # Markdown shows declared/observed windows (end-to-end CLI on the synthetic H6 pair)
    d = tempfile.mkdtemp()
    mine, nd, cd = job_files(h, new, old, d)
    new.to_csv(f"{nd}/predictions.csv.gz", index=False, float_format="%.17g")
    old.to_csv(f"{cd}/predictions.csv.gz", index=False, float_format="%.17g")
    p = subprocess.run([sys.executable, "-B", os.path.join(HERE, "recompute_origin.py"), "--pair", f"6={nd},{cd}", "--out", f"{d}/out"],
                       capture_output=True, text=True)
    md = open(f"{d}/out/tui.md").read() if os.path.exists(f"{d}/out/tui.md") else ""
    res["cli_consistent_rc0"] = p.returncode == 0
    res["markdown_declared_observed"] = "| historical_2023 | augmented_total | 2023-07..2023-12 | 2023-07..2023-12 |" in md
    ok = all(res.values())
    print(json.dumps({"ok": ok, "cases": res}, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
