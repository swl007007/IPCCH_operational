"""Independent recomputation of the origin-ablation TUI tables from saved keyed predictions (task 10-30; local only).

Does not import the training code (metrics: task 10-27 ``recompute_metrics.py``, imported unchanged). Per horizon:
1. pairing: the new run's predictions and the CH-final run's retained predictions must have the same unique
   (context, admin_code, target_ord) keys, with equal period, phase and q2..q5 truth, label kind, source family and iso2;
   contexts/periods/windows are derived from the horizon calendar, never from the files;
2. TUI cells for historical_2023 / 2024 / 2025 (declared windows; an empty window is NA with its reason), historical_pooled
   (rows of the three years concatenated; never the holdout) and holdout_2026_01_10: original = new predictions on the
   CH-final label_kind == original rows, matched_augmented = CH-final predictions on exactly those rows, augmented_total =
   CH-final predictions on every row; delta = matched_augmented - original (NA if either is NA);
3. reconciliation: every augmented_total cell reproduces the CH-final run's OWN whole-population results (its trial
   metrics.json ``scopes``: six metrics, n/original/copy rows and NA presence; and its <scope>.<metric> / n_rows MLflow
   scalars), i.e. the baseline is not refitted or altered (A4); unless --no-job, every cell (metrics, n, declared and
   observed windows, NA presence) equals the job's origin_comparison.json and the run's origin.* MLflow scalars (an
   undefined value has NO scalar), and the new run's whole-population scopes equal its metrics.json scopes and scalars.
NA reasons are read off the quantities the 10-27 primitive itself tests (zero binary denominators, a four-class level
absent from truth and prediction, n < 2 or constant q3 truth, an empty declared window); no metric definition changes.
Writes one JSON plus tui.csv / tui.md (F1, phase-3+ share R2, N, declared/observed window, NA reason).

  python3 -B recompute_origin.py --pair H=NEW_TRIAL_DIR,CH_TRIAL_DIR [...] --out DIR [--no-job]
"""
import argparse, importlib.util, json, math, os, sys
import numpy as np
import pandas as pd

R10 = "/home/swl007007/projects/food-crisis-research/.trellis/tasks/10-27-ipcch-gosif2025-retrain/research/cp5/recompute_metrics.py"
_spec = importlib.util.spec_from_file_location("recompute_metrics_10_27", R10)
rm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rm)
METRICS, FIRST, metrics, close, ord_ = rm.METRICS, rm.FIRST, rm.metrics, rm.close, rm.ord_
KEYS = ["context", "admin_code", "target_ord"]
SAME = ["period", "phase_truth", "q2_truth", "q3_truth", "q4_truth", "q5_truth", "label_kind", "source_family", "iso2"]
GROUPS = ("original", "matched_augmented", "augmented_total")
DELTA = "delta_matched_augmented_minus_original"
TUI = ("binary_f1", "phase3plus_r2")


def read(path):
    return pd.read_csv(path, keep_default_na=False, na_values=[""], float_precision="round_trip", dtype={"iso2": str})


def lab(o):
    return f"{o // 12}-{o % 12 + 1:02d}"


def calendar(h):
    lo, hi = ord_(*FIRST[h]), ord_(2025, 12)
    ctx = {f"h{h:02d}_main_{y}": ("main", max(lo, y * 12), min(hi, y * 12 + 11)) for y in range(lo // 12, hi // 12 + 1)}
    ctx[f"h{h:02d}_supp_2026"] = ("supplement", ord_(2026, 1), ord_(2026, 10))
    periods = {}
    for y in (2023, 2024, 2025):
        a, b = max(lo, y * 12), min(hi, y * 12 + 11)
        periods[f"historical_{y}"] = ("main", a, b, None) if a <= b else \
            ("main", None, None, f"no evaluation rows: {y} precedes the H{h} historical window starting {lab(lo)}")
    periods["historical_pooled"] = ("main", lo, hi, None)
    periods["holdout_2026_01_10"] = ("supplement", ord_(2026, 1), ord_(2026, 10), None)
    return ctx, periods


def pair(new, old, h):
    ctx, _ = calendar(h)
    for side, f in (("new", new), ("ch_final", old)):
        if f.duplicated(KEYS).any():
            raise SystemExit(f"H{h} {side}: duplicate keys")
        t = f["target_ord"].to_numpy(int)
        for c, (role, a, b) in ctx.items():
            sel = (f["context"] == c).to_numpy()
            if (f.loc[sel, "period"] != role).any() or (t[sel] < a).any() or (t[sel] > b).any():
                raise SystemExit(f"H{h} {side}: {c} rows outside the calendar")
        if not f["context"].isin(list(ctx)).all():
            raise SystemExit(f"H{h} {side}: unknown context")
    m = new.merge(old, on=KEYS, how="outer", suffixes=("", "_old"), indicator=True)
    if (m["_merge"] != "both").any():
        raise SystemExit(f"H{h}: unmatched keys {m['_merge'].value_counts().to_dict()}")
    bad = {c: int((m[c].to_numpy() != m[f"{c}_old"].to_numpy()).sum()) for c in SAME}
    if any(bad.values()):
        raise SystemExit(f"H{h}: paired keys differ {bad}")
    return m, bad


def reasons(g, m):
    """Why each undefined metric of the 10-27 primitive is NA, read off the quantities that primitive tests."""
    if m.get("empty_reason"):
        return {k: m["empty_reason"] for k in m["na"]}
    if not len(g):
        return {k: "no evaluation rows" for k in m["na"]}
    t, p = g["phase_truth"].to_numpy(int), g["phase"].to_numpy(int)
    ct, cp = np.minimum(t, 4), np.minimum(p, 4)
    tp, fp, fn = int(((t >= 3) & (p >= 3)).sum()), int(((t < 3) & (p >= 3)).sum()), int(((t >= 3) & (p < 3)).sum())
    absent = [("1", "2", "3", "4-5")[k - 1] for k in (1, 2, 3, 4) if not ((ct == k) | (cp == k)).any()]
    y = g["q3_truth"].to_numpy(float)
    why = {"binary_precision": f"no predicted crisis rows (tp + fp = {tp + fp})",
           "binary_recall": f"no true crisis rows (tp + fn = {tp + fn})",
           "binary_f1": f"no crisis in truth or prediction (tp + fp + fn = {tp + fp + fn})",
           "binary_f2": f"no crisis in truth or prediction (5tp + 4fn + fp = {5 * tp + 4 * fn + fp})",
           "macro_f1": f"four-class level(s) {absent} absent from both truth and prediction",
           "phase3plus_r2": f"fewer than 2 rows (n = {len(y)})" if len(y) < 2 else "constant q3 truth"}
    return {k: why[k] for k in m["na"]}


def cells(m, h):
    _, periods = calendar(h)
    t, role = m["target_ord"].to_numpy(int), m["period"].to_numpy()
    orig = (m["label_kind_old"] == "original").to_numpy()
    old = m.drop(columns=["phase", "q3_star"]).rename(columns={"phase_old": "phase", "q3_star_old": "q3_star"})
    out = {}
    for name, (r, a, b, why) in periods.items():
        sel = np.zeros(len(m), bool) if why else (role == r) & (t >= a) & (t <= b)
        dec = None if why else (a, b)
        frames = {"original": m[sel & orig], "matched_augmented": old[sel & orig], "augmented_total": old[sel]}
        g = {k: metrics(f, dec, why) for k, f in frames.items()}
        for k, f in frames.items():
            g[k]["na_reasons"] = reasons(f, g[k])
        d = {k: None if g["matched_augmented"][k] is None or g["original"][k] is None else g["matched_augmented"][k] - g["original"][k]
             for k in METRICS}
        dwhy = {k: "; ".join(f"{x} undefined: {g[x]['na_reasons'][k]}" for x in ("matched_augmented", "original") if g[x][k] is None)
                for k in METRICS if d[k] is None}
        out[name] = {"groups": g, DELTA: d, "delta_na_reasons": dwhy}
    pooled = out["historical_pooled"]["groups"]["augmented_total"]["n_rows"]
    if pooled != sum(out[f"historical_{y}"]["groups"]["augmented_total"]["n_rows"] for y in (2023, 2024, 2025)):
        raise SystemExit(f"H{h}: annual periods do not add up to the pooled period")
    return out


def whole(new, h):
    _, periods = calendar(h)
    t, role = new["target_ord"].to_numpy(int), new["period"].to_numpy()
    return {n: metrics(new[(role == r) & (t >= a) & (t <= b)]) for n, (r, a, b, why) in periods.items() if not why}


def reconcile(h, mine, new_trial, ch_trial, scopes_new, scopes_ch, no_job):
    problems = []
    ch_pub = json.load(open(os.path.join(ch_trial, "publication.json")))["trial"]["metrics"]
    ch_scopes = json.load(open(os.path.join(ch_trial, "metrics.json")))["scopes"]
    if sorted(ch_scopes) != sorted(scopes_ch):
        problems.append(f"CH-final metrics.json scopes {sorted(ch_scopes)} != {sorted(scopes_ch)}")
    for n, s in scopes_ch.items():          # the CH-final model's own whole-population results (metrics.json + scalars)
        aug, js = mine[n]["groups"]["augmented_total"], ch_scopes.get(n) or {}
        for c in ("n_rows", "original_rows", "copy_rows"):
            if not aug[c] == s[c] == js.get(c):
                problems.append(f"{n}.{c}: augmented_total {aug[c]} / recomputed CH {s[c]} vs CH-final metrics.json {js.get(c)}")
        if ch_pub.get(f"{n}.n_rows") != float(aug["n_rows"]):
            problems.append(f"{n}.n_rows: CH-final scalar {ch_pub.get(f'{n}.n_rows')}")
        for k in METRICS:
            if not close(aug[k], s[k]) or not close(aug[k], js.get(k)) or not close(aug[k], ch_pub.get(f"{n}.{k}")):
                problems.append(f"{n}.{k}: augmented_total {aug[k]} vs CH-final metrics.json {js.get(k)} / scalar {ch_pub.get(f'{n}.{k}')}")
            if (aug[k] is None) != bool((js.get("na_reasons") or {}).get(k)):
                problems.append(f"{n}.{k}: NA presence differs from the CH-final metrics.json")
    if no_job:
        return problems
    job = json.load(open(os.path.join(new_trial, "origin_comparison.json")))["cells"]
    pub = json.load(open(os.path.join(new_trial, "publication.json")))["trial"]["metrics"]
    if sorted(job) != sorted(mine):
        problems.append(f"periods {sorted(job)} != {sorted(mine)}")
    for n, c in mine.items():
        for g in GROUPS:
            jb, mb = job[n]["groups"][g], c["groups"][g]
            for side, field in (("declared_from", "declared_from"), ("declared_to", "declared_to")):
                if job[n].get(side) != mb[field]:
                    problems.append(f"{n}.{g}.{field}: job {job[n].get(side)} vs mine {mb[field]}")
            for field in ("observed_from", "observed_to", "original_rows", "copy_rows"):
                if jb.get(field) != mb[field]:
                    problems.append(f"{n}.{g}.{field}: job {jb.get(field)} vs mine {mb[field]}")
            if jb["n_rows"] != mb["n_rows"] or pub.get(f"origin.{n}.{g}.n_rows") != float(mb["n_rows"]):
                problems.append(f"{n}.{g}: n {jb['n_rows']} / {pub.get(f'origin.{n}.{g}.n_rows')} vs {mb['n_rows']}")
            for k in METRICS:
                key = f"origin.{n}.{g}.{k}"
                if not close(mb[k], jb[k]) or (mb[k] is None) != (key not in pub) or (mb[k] is not None and not close(mb[k], pub[key])):
                    problems.append(f"{key}: mine {mb[k]} job {jb[k]} scalar {pub.get(key)}")
                if (mb[k] is None) != bool(jb["na_reasons"].get(k)):
                    problems.append(f"{key}: NA reason presence differs")
        for k in METRICS:
            key = f"origin.{n}.{DELTA}.{k}"
            v = c[DELTA][k]
            if not close(v, job[n][DELTA][k]) or (v is None) != (key not in pub) or (v is not None and not close(v, pub[key])):
                problems.append(f"{key}: mine {v} job {job[n][DELTA][k]} scalar {pub.get(key)}")
    new_scopes = json.load(open(os.path.join(new_trial, "metrics.json")))["scopes"]
    for n, s in scopes_new.items():
        js = new_scopes.get(n) or {}
        for c in ("n_rows", "original_rows", "copy_rows"):
            if s[c] != js.get(c):
                problems.append(f"{n}.{c}: whole population {s[c]} vs new metrics.json {js.get(c)}")
        for k in METRICS:
            if not close(s[k], js.get(k)):
                problems.append(f"{n}.{k}: whole population {s[k]} vs new metrics.json {js.get(k)}")
            if not close(s[k], pub.get(f"{n}.{k}")):
                problems.append(f"{n}.{k}: whole population {s[k]} vs scalar {pub.get(f'{n}.{k}')}")
        if pub.get(f"{n}.n_rows") != float(s["n_rows"]):
            problems.append(f"{n}.n_rows mismatch")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", action="append", required=True, help="H=NEW_TRIAL_DIR,CH_FINAL_TRIAL_DIR")
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-job", action="store_true", help="validation mode: no job artifacts to reconcile")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=False)
    res, rows = {}, []
    for spec in a.pair:
        h, dirs = spec.split("=", 1)
        h = int(h)
        new_dir, ch_dir = dirs.split(",")
        new, old = read(os.path.join(new_dir, "predictions.csv.gz")), read(os.path.join(ch_dir, "predictions.csv.gz"))
        if (new["horizon"] != h).any() or (old["horizon"] != h).any():
            raise SystemExit(f"H{h}: horizon column differs")
        m, _ = pair(new, old, h)
        mine = cells(m, h)
        problems = reconcile(h, mine, new_dir, ch_dir, whole(new, h), whole(old, h), a.no_job)
        res[f"h{h:02d}"] = {"pairing": {"rows": int(len(m)), "unmatched": 0, "truth_kind_family_country_mismatches": 0,
                                        "originals": int((m["label_kind_old"] == "original").sum())},
                            "cells": mine, "problems": problems, "passed": not problems}
        for n, c in mine.items():
            for g in (*GROUPS, DELTA):
                b = c["groups"].get(g)
                v = c[DELTA] if b is None else b
                rows.append({"horizon": h, "period": n, "group": g, "n_rows": (c["groups"]["original"] if b is None else b)["n_rows"],
                             **{k: v[k] for k in TUI},
                             "declared": None if b is None or b["declared_from"] is None else f"{b['declared_from']}..{b['declared_to']}",
                             "observed": None if b is None or b["observed_from"] is None else f"{b['observed_from']}..{b['observed_to']}",
                             "na_reason": "; ".join(f"{k}: {(c['delta_na_reasons'] if b is None else b['na_reasons'])[k]}"
                                                    for k in TUI if v[k] is None) or None})
    res["passed"] = all(r["passed"] for r in res.values() if isinstance(r, dict))
    json.dump(res, open(os.path.join(a.out, "recompute.json"), "w"), indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    t = pd.DataFrame(rows)
    t.to_csv(os.path.join(a.out, "tui.csv"), index=False, float_format="%.17g")
    fmt = lambda x: "NA" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.4f}"
    with open(os.path.join(a.out, "tui.md"), "w") as f:
        for h in sorted(t["horizon"].unique()):
            f.write(f"\n### H{h}\n\n| period | group | declared | observed | N | binary F1 | phase-3+ R2 | NA reason |\n"
                    "|---|---|---|---|---:|---:|---:|---|\n")
            txt = lambda x: x if isinstance(x, str) else ""
            for r in t[t["horizon"] == h].itertuples():
                f.write(f"| {r.period} | {r.group} | {txt(r.declared)} | {txt(r.observed)} | {r.n_rows} | {fmt(r.binary_f1)} | "
                        f"{fmt(r.phase3plus_r2)} | {txt(r.na_reason)} |\n")
    print(json.dumps({k: (v["passed"], v["problems"][:5]) if isinstance(v, dict) else v for k, v in res.items()}, indent=1))
    sys.exit(0 if res["passed"] else 1)


if __name__ == "__main__":
    main()
