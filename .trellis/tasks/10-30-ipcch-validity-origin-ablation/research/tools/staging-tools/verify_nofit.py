"""Independent no-fit check of the origin-ablation gate measurements against the retained CH-final job artifacts.

  verify_nofit.py --gates DIR --stage provisional|final --out FILE

Never rebuilds the dataset: the expected original-only memberships, fitting-row history overlays, fitting keys/targets/
weights and counts are derived from the CH-final run's own saved outputs (contexts/memberships.npz, contexts/arm_rows,
gcs-only/history_overlays.npz, dataset/labels.csv.gz q*_str, contexts/fit_ledger.csv) by keeping each saved fitting pool's
label_kind == original rows, and compared with the digests/counts the gate measured on its fresh build. The unsliced
retained artifacts must first reproduce the CH-final self-consistency pins, so the comparison is anchored to the run.
"""
import argparse
import gzip
import hashlib
import json
import sys

import numpy as np
import pandas as pd

W = "/home/swl007007/projects/food-crisis-research"
sys.path.insert(0, f"{W}/control-plane-origin-ablation")
from research_cloud.training import ipcch_validity_pooled as vp  # noqa: E402

UNCHANGED = ("rows", "arm_rows_csv_sha256", "targets_sha256", "phase_sha256", "observations_sha256", "calibration_keys_sha256",
             "feature_prefix_order_sha256", "feature_prefix_X_sha256", "feature_prefix_nan_mask_sha256")


def check_horizon(h, gates, stage):
    hh = f"{h:02d}"
    T = f"{W}/scratch/ch-validity-20261028/harvest/formal-h{hh}/trial-0"
    cfg = json.load(open(f"{W}/staging/ipcch-ch-validity-20261028/job-packet-ch/objects/config-formal-h{hh}.json"))
    pins = cfg["ch_correction"]["self_consistency"]
    eq = json.load(open(f"{gates}/{stage}-h{hh}/equivalence.json"))
    o, ch = eq["origin_ablation"], eq["ch_correction"]
    rows = pd.read_csv(f"{T}/contexts/arm_rows.csv.gz")
    kind = rows["label_kind"].to_numpy(dtype=object)
    admin, target = rows["admin_code"].to_numpy(np.int64), rows["target_ord"].to_numpy(np.int64)
    labels = pd.read_csv(f"{T}/dataset/labels.csv.gz", dtype={f"{q}_str": str for q in vp.TARGETS}, keep_default_na=False,
                         na_values=[""], usecols=[f"{q}_str" for q in vp.TARGETS])
    Y = np.column_stack([np.array([float(s) for s in labels[f"{q}_str"]], dtype=np.float64) for q in vp.TARGETS])
    members = dict(np.load(f"{T}/contexts/memberships.npz"))
    overlays = dict(np.load(f"{T}/gcs-only/history_overlays.npz"))
    ledger = pd.read_csv(f"{T}/contexts/fit_ledger.csv").rename(columns={"block": "fit_block"})
    checks = {}
    # anchor: the retained artifacts reproduce the CH-final pins
    checks["retained_memberships_equal_ch_pin"] = vp.digest({k: vp.array_digest(v) for k, v in members.items()}) == pins["memberships_sha256"]
    checks["retained_overlays_equal_ch_pin"] = vp.digest({k: vp.array_digest(v) for k, v in overlays.items()}) == pins["history_overlays_sha256"]
    checks["retained_fit_keys_equal_ch_pin"] = vp.frame_sha256(ledger[list(vp.FIT_KEY_COLUMNS)]) == pins["fit_keys_sha256"]
    checks["retained_arm_rows_equal_ch_pin"] = hashlib.sha256(gzip.open(f"{T}/contexts/arm_rows.csv.gz").read()).hexdigest() == pins["arm_rows_csv_sha256"]
    # the gate's unfiltered build is the CH-final build
    checks["gate_ch_contract_passed"] = bool(ch["passed"]) and not ch["self_consistency_differing"]
    checks["gate_unchanged_digests_equal_ch_pins"] = all(o["self_consistency"][k] == pins[k] for k in UNCHANGED)
    # expected original-only fitting memberships from the retained pools
    exp_members, exp_overlays, contexts, ledger_rows = dict(members), dict(overlays), {}, []
    for c in sorted({k.split("|")[0] for k in members if k.endswith("|score")}):
        base = members[f"{c}|backbone|train"]
        keep = kind[base] == "original"
        train = base[keep]
        exp_members[f"{c}|backbone|train"] = train.astype(np.int32)
        for s in ("src", "fam", "alias"):
            key = f"{c}|backbone|train_{s}"
            if key in overlays:
                exp_overlays[key] = overlays[key][keep]
        pinned = {"train_rows": int(len(train)), "fit_label_removed": int((~keep).sum()),
                  "train_keys_sha256": vp.array_digest(np.column_stack([admin[train], target[train]]))}
        got = {k: o["contexts"][c][k] for k in pinned}
        L = ledger.loc[(ledger["context"] == c) & (ledger["role"] == "backbone")].iloc[0]
        cutoff = vp.parse_month(L["cutoff"])
        ledger_rows.append({"context": c, "fit_block": L["fit_block"], "role": "backbone", "cutoff": L["cutoff"],
                            "train_rows": int(len(train)), "predicted_rows": int(L["predicted_rows"]),
                            "excluded_families": int(L["excluded_families"]), "excluded_families_sha256": L["excluded_families_sha256"],
                            "train_keys_sha256": pinned["train_keys_sha256"], "y_sha256": vp.array_digest(Y[train]),
                            "w_sha256": vp.array_digest(vp.decay(target[train], cutoff))})
        contexts[c] = {"expected": pinned, "gate": got, "equal": got == pinned, "baseline_train_rows": int(len(base)),
                       "copies_in_expected": int((kind[train] != "original").sum()),
                       "gate_checks_failed": sorted(k for k, v in o["contexts"][c]["checks"].items() if not v and k != "fit_counts_pinned")}
        checks[f"{c}:counts_and_keys_equal"] = got == pinned
        checks[f"{c}:gate_intervention_checks"] = not contexts[c]["gate_checks_failed"]
    exp = {"memberships_sha256": vp.digest({k: vp.array_digest(v) for k, v in exp_members.items()}),
           "history_overlays_sha256": vp.digest({k: vp.array_digest(v) for k, v in exp_overlays.items()}),
           "fit_keys_sha256": vp.frame_sha256(pd.DataFrame(ledger_rows, columns=list(vp.FIT_KEY_COLUMNS)))}
    for k, v in exp.items():
        checks[f"expected_{k}_equals_gate"] = v == o["self_consistency"][k]
    # A2 before any fit: the gate's freshly prepared labels, cut by the scheduled scoring windows, against the retained
    # CH-final predictions CSV (one-to-one keys, exact truths, label kind, family, country, period)
    lab = pd.read_csv(f"{gates}/{stage}-h{hh}/dataset/labels.csv.gz", dtype={"iso2": str, **{f"{q}_str": str for q in vp.TARGETS}},
                      keep_default_na=False, na_values=[""],
                      usecols=["admin_code", "month_ord", "label_kind", "source_family", "iso2", "phase_truth", *[f"{q}_str" for q in vp.TARGETS]])
    sched = vp.schedule_from_config(cfg, h)
    parts = []
    for b in vp.scoring_blocks(h, sched):
        f = lab[(lab["month_ord"] >= b.target_lo) & (lab["month_ord"] <= b.target_hi)].copy()
        f["context"], f["period"] = b.block_id, b.role
        parts.append(f)
    prep = pd.concat(parts, ignore_index=True).rename(columns={"month_ord": "target_ord"})
    for q in vp.TARGETS:
        prep[f"{q}_truth"] = [float(s) for s in prep[f"{q}_str"]]
    pred = pd.read_csv(f"{T}/predictions.csv.gz", float_precision="round_trip", keep_default_na=False, na_values=[""], dtype={"iso2": str})
    key = ["context", "admin_code", "target_ord"]
    m = prep.merge(pred, on=key, how="outer", suffixes=("_prep", "_csv"), indicator=True, validate="one_to_one")
    both = m[m["_merge"] == "both"]
    a2 = {"prepared_rows": int(len(prep)), "csv_rows": int(len(pred)), "matched": int(len(both)),
          "prepared_only": int((m["_merge"] == "left_only").sum()), "csv_only": int((m["_merge"] == "right_only").sum()),
          "mismatches": {c: int((both[f"{c}_prep"].to_numpy() != both[f"{c}_csv"].to_numpy()).sum())
                         for c in ("period", "label_kind", "source_family", "iso2", "phase_truth", *[f"{q}_truth" for q in vp.TARGETS])},
          "originals": int((prep["label_kind"] == "original").sum())}
    a2["gate_score_pairing"] = o.get("score_pairing")
    checks["a2_prepared_score_rows_equal_retained_csv"] = (a2["prepared_only"] == a2["csv_only"] == 0 and len(both) == len(pred) == len(prep)
                                                           and not any(a2["mismatches"].values()))
    if stage == "final":
        checks["final_gate_passed"] = bool(eq["passed"]) and not eq["differing"]
        checks["gate_score_pairing_passed"] = bool((o.get("score_pairing") or {}).get("passed"))
    return {"horizon": h, "checks": checks, "contexts": contexts, "expected_digests": exp, "a2_score_rows": a2,
            "gate_self_consistency": o["self_consistency"], "changed_by_fit_membership": o["digests_changed_by_fit_membership"],
            "passed": all(checks.values())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gates", required=True)
    ap.add_argument("--stage", choices=("provisional", "final"), required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = {f"h{h:02d}": check_horizon(h, a.gates, a.stage) for h in (0, 6, 12)}
    res["passed"] = all(r["passed"] for r in res.values() if isinstance(r, dict))
    with open(a.out, "w") as f:
        json.dump(res, f, indent=1)
    for k, r in res.items():
        if isinstance(r, dict):
            print(k, "passed" if r["passed"] else "FAILED", [c for c, v in r["checks"].items() if not v])
    sys.exit(0 if res["passed"] else 1)


if __name__ == "__main__":
    main()
