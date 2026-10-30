"""Task 10-30 origin-ablation candidate recipes and local manifests (no fit, no cloud).

  make_origin_recipes.py provisional            -> candidate/provisional/{formal-origin-hXX,manifest-origin-local-hXX}.json
  make_origin_recipes.py final --gates DIR      -> candidate/final/...  (origin_ablation pins from the provisional gates'
                                                   measured equivalence.json; refuses unless the measured record is
                                                   otherwise clean)

Every recipe is the CH-final run's uploaded recipe (byte-checked equal to its retained trial config) with exactly these
changes: baseline -> the CH-final run (13 digests = its ch_correction self-consistency), comparison.baseline_predictions ->
the CH-final retained predictions, new origin_ablation block, the model card fields whose text would otherwise be false
(family_title, role, summary, evaluation, limitations, target, feature_engineering prefix) and three new provenance tags.
``provenance.code_overlay`` is restated from the actual build in the job packet (it is the inherited CH value here).
"""
import copy
import hashlib
import json
import os
import sys

W = "/home/swl007007/projects/food-crisis-research"
ST = f"{W}/staging/ipcch-origin-ablation-20261030"
sys.path.insert(0, f"{W}/control-plane-origin-ablation")
from research_cloud.training import ipcch_validity_pooled as vp  # noqa: E402

CH_RUNS = {0: "298c4718b4d64e6f8a5c315e8c22d25d", 6: "00d4e94c824343bf86a0c2b79d5b9ed0", 12: "f436da15c71c469199784db065f3b63b"}
VERSION = "gosif-v3-input-20261027+ch-validity-20261028+original-label-fit-20261030"
TITLE = "Original-label fit ablation (GOSIF v3 + CH validity 20261028)"
CHANGED_TOP = ("baseline", "comparison", "origin_ablation", "model_card", "provenance_tags", "training_window")
CHANGED_CARD = ("family_title", "role", "summary", "evaluation", "limitations", "target", "feature_engineering")


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def sources(h):
    hh = f"{h:02d}"
    trial = f"{W}/scratch/ch-validity-20261028/harvest/formal-h{hh}/trial-0"
    cfg_path = f"{W}/staging/ipcch-ch-validity-20261028/job-packet-ch/objects/config-formal-h{hh}.json"
    pub = json.load(open(f"{trial}/publication.json"))
    cfg = json.load(open(cfg_path))
    if cfg != pub["trial"]["config"] or pub["run_id"] != CH_RUNS[h] or pub.get("status") != "complete":
        raise SystemExit(f"H{h}: CH-final recipe/publication pins disagree")
    return trial, cfg_path, cfg, pub


def card(h, cfg, pub, fit_counts):
    c = copy.deepcopy(cfg["model_card"])
    run = CH_RUNS[h]
    winner = cfg["frozen"]["winner_trial_id"]
    fits = (", ".join(f"{k} {v['train_rows']:,}" for k, v in sorted(fit_counts.items())) if fit_counts
            else "per-context counts pinned in origin_ablation.fit_counts")
    c["family_title"] = TITLE
    c["role"] = ("Original-label fit ablation of the CH-final tuned aggregated-ACLED refit: validity copies removed from the "
                 "fitting labels only, full inherited cohort scored (research comparison)")
    c["summary"] = (f"Fixed-parameter refit of the CH-final run of {vp.HPT_ARM}, lead {h} months (MLflow {run}; "
                    f"{cfg['ch_correction']['data_version']}), whose only change is the backbone fitting-label membership: each "
                    "annual context keeps only the final CH-corrected label_kind == original rows of its CH-final fitting pool "
                    f"({fits}); IPC and CH validity copies are removed from fitting labels only. The quartet parameters frozen for "
                    f"this horizon (winner search {winner}), seed, unnormalized 24-month half-life weights of the retained rows, "
                    "features, reported-phase histories, report-family and alias exclusions (copy families included), contexts, "
                    "cutoffs and identity calibration are reused without re-tuning; the full inherited cohort (originals and copies) "
                    "is scored. Linked comparison baseline: the CH-final run (not refitted), paired on identical keys and truths.")
    c["evaluation"] = (
        "Selection is inherited (the tuned parameters were frozen by the original search; no new search). This refit: the "
        "CH-final run's annual expanding contexts and calendar; the whole inherited scored cohort (historical and 2026-01..10, "
        "originals and copies, unweighted) gives the standard six metrics (binary F1/F2/precision/recall, phase3plus R2, macro "
        "F1) for the pooled historical window, each historical year and 2026-01..10 (MLflow <scope>.<metric>, <scope>.n_rows) "
        "and the inherited report tables (six report regions x primary / 2026-01..10 holdout; all regions and the Somalia subset "
        "x 2023/2024/2025/holdout; report_tables.csv/.json, MLflow report.*). Paired original-label view against the CH-final "
        "run's retained predictions on exactly paired (context, admin_code, target_ord) keys with identical truths: for "
        "historical_2023/2024/2025 (declared windows respected; an empty window is NA with its reason), historical_pooled "
        "(recomputed from rows, never the 2026 holdout) and holdout_2026_01_10: original = this run on the CH-final run's "
        "label_kind == original rows; matched_augmented = the CH-final run on exactly those rows; augmented_total = the "
        "CH-final run on every inherited row; delta = matched_augmented - original (MLflow origin.<period>.<group>.<metric>, "
        "origin.<period>.<group>.n_rows, origin.<period>.delta_matched_augmented_minus_original.<metric>; origin_comparison.json/"
        ".csv, origin_tui.csv). Total versus matched is a population contrast, not an isolated model effect. region_mapping.csv "
        "is the frozen map of the inherited pairing only.")
    old = cfg["model_card"]["limitations"]
    tail = old[old.index("CH copies take the reference-window start month"):]
    c["limitations"] = (
        f"Versus the linked CH-final run (MLflow {run}): only the backbone fitting-label membership differs (validity copies "
        "removed; the retained original rows keep their CH-final weights, which are not renormalized, so the total fitting "
        "weight is smaller); labels, cohort, scored rows, report families, aliases, histories, features, parameters, seed, "
        "contexts, cutoffs and identity calibration are identical (verified before fitting). Copy report families remain "
        "excluded from fitting labels and histories exactly as in the CH-final run. The original-only fits use fewer rows, "
        "so the comparison reflects both the absence of copy supervision and the smaller fitting sample. Final label_kind is "
        "the CH-final classification; unresolved and cross-country CH originals stay as in the CH-final run and CH copy-only "
        "source events are not promoted to original labels. One seed; descriptive point estimates and paired differences only "
        "(no bootstrap, interval or significance test). " + tail.replace("Not promoted over the GOSIF-v3 run.",
                                                                        "Not promoted over the GOSIF-v3 run. Not promoted over the CH-final run."))
    t = cfg["model_card"]["target"]
    if "training and evaluation rows include" not in t:
        raise SystemExit("unexpected inherited target text")
    c["target"] = (t.replace("training and evaluation rows include", "evaluation rows include")
                   + "; fitting labels exclude every validity copy (final label_kind == original only), scoring keeps all rows")
    c["feature_engineering"] = ("Original-label fit ablation (task 10-30): label preparation, CH validity correction, features "
                                "and reported-phase histories are exactly those of the CH-final run; validity copies are scored "
                                "but excluded from the backbone fitting labels. Inherited description: " + cfg["model_card"]["feature_engineering"])
    return c


def recipe(h, fit_counts=None, self_consistency=None):
    trial, cfg_path, cfg, pub = sources(h)
    out = copy.deepcopy(cfg)
    cc = cfg["ch_correction"]
    run = CH_RUNS[h]
    preds = sha(f"{trial}/predictions.csv.gz")
    out["baseline"] = {"kind": "frozen_baseline", "arm": vp.HPT_ARM, "run_id": run, "model_id": pub["model_id"],
                       "registered_model": pub["registered_model"], "model_version": str(pub["model_version"]),
                       "package_json_sha256": pub["package.json_sha256"],
                       "relation": (f"Linked comparison baseline: the CH-final run of this horizon (MLflow {run}; not refitted). Same "
                                    "inputs, CH-corrected labels and label kinds, cohort, scored rows, report families and aliases, "
                                    "histories, features, frozen quartet parameters, seed, per-row weights, contexts, cutoffs and "
                                    "identity calibration (the unfiltered no-fit build equals the CH-final self-consistency digests); "
                                    "only each backbone's fitting labels are restricted to the final label_kind == original rows, so "
                                    "memberships, fitting keys, fitting-row histories, schedule and fit ledger differ. Comparisons pair "
                                    "(context, admin_code, target_ord) one to one with identical truth: original-only fitted model vs "
                                    "the CH-final model on the CH-final original rows; the CH-final model's whole cohort is a "
                                    "separate population."),
                       "equivalence": {k: cc["self_consistency"][k] for k in vp.EQUIVALENCE_KEYS}}
    out["comparison"] = {"baseline_predictions": preds, "region_mapping": cfg["comparison"]["region_mapping"]}
    out["origin_ablation"] = {
        "kind": vp.ORIGIN_KIND, "data_version": VERSION, "fit_labels": "original_only",
        "ch_baseline": {"run_id": run, "recipe_sha256": sha(cfg_path), "predictions_sha256": preds,
                        "package_json_sha256": pub["package.json_sha256"], "ch_correction_sha256": vp.digest(cc),
                        "params_sha256": cfg["frozen"]["params_sha256"]},
        "fit_counts": fit_counts or {"provisional": {"train_rows": 1, "fit_label_removed": 1, "train_keys_sha256": "0" * 64}},
        "self_consistency": self_consistency or {k: "0" * 64 for k in vp.EQUIVALENCE_KEYS},
        "relation": ("original-only backbone fitting labels on the CH-final panel; every input, label, scored row, exclusion, "
                     "history, feature, parameter, weight, context and cutoff inherited from the CH-final run")}
    out["model_card"] = card(h, cfg, pub, fit_counts or {})
    tags = dict(cfg["provenance_tags"])
    tags.update({"provenance.ch_final_run": f"{run} (recipe sha256 {sha(cfg_path)}; package.json sha256 {pub['package.json_sha256']})",
                 "provenance.fit_labels": "original_only: backbone fitting labels = final label_kind == original rows of each "
                                          "CH-final fitting pool; copies scored, never fitted",
                 "provenance.origin_ablation": f"{VERSION}; task 10-30 original-label fit ablation (fit membership only)"})
    if "GOSIF-v3 run's retained predictions" not in tags["provenance.input_manifest"]:
        raise SystemExit("unexpected inherited provenance.input_manifest text")
    tags["provenance.input_manifest"] = ("task-scoped cloud manifest of task 10-30 (roles, sha256 and object generations in the "
                                         "run's trial record and DatasetInput): every role and generation equals the CH-final "
                                         f"run's uploaded manifest (task 10-28) except baseline_predictions = the CH-final run "
                                         f"{run}'s retained predictions (copied to the task store)")
    out["provenance_tags"] = tags
    if out["training_window"] != "annual refit at each context cutoff; every eligible label up to the cutoff; weights halve every 24 months":
        raise SystemExit("unexpected inherited training_window")
    out["training_window"] = ("annual refit at each context cutoff; every eligible ORIGINAL label (final label_kind == original) up "
                              "to the cutoff, validity copies not fitted; retained rows keep their weights, which halve every 24 months")
    vp.check_hpt_config(out, h)
    diff = sorted(k for k in set(out) | set(cfg) if out.get(k) != cfg.get(k))
    if diff != sorted(CHANGED_TOP):
        raise SystemExit(f"H{h}: unexpected top-level differences {diff}")
    cdiff = sorted(k for k in out["model_card"] if out["model_card"][k] != cfg["model_card"][k])
    if cdiff != sorted(CHANGED_CARD):
        raise SystemExit(f"H{h}: unexpected model card differences {cdiff}")
    return out, trial


def manifest(h, trial):
    src = json.load(open(f"{W}/staging/ipcch-ch-validity-20261028/candidate/recipes/final/manifest-chvalidity-local-h{h:02d}.json"))
    m = copy.deepcopy(src)
    m["name"] = f"origin-ablation-local-formal-h{h:02d}"
    p = f"{trial}/predictions.csv.gz"
    m["files"]["baseline_predictions"] = {"sha256": sha(p), "uri": p}
    return m


def main():
    stage = sys.argv[1]
    out_dir = f"{ST}/candidate/{stage}"
    os.makedirs(out_dir, exist_ok=False)
    summary = {}
    for h in (0, 6, 12):
        pins = {}
        if stage.startswith("final"):
            gates = sys.argv[sys.argv.index("--gates") + 1]
            eq = json.load(open(f"{gates}/provisional-h{h:02d}/equivalence.json"))
            o, c = eq["origin_ablation"], eq["ch_correction"]
            other = [k for k in eq["differing"] if not k.startswith("origin")]
            if other or not c["passed"]:
                raise SystemExit(f"H{h}: the provisional gate failed outside the origin pins: {other}")
            pins = {"fit_counts": {k: {f: v[f] for f in vp.ORIGIN_FIT_KEYS} for k, v in o["contexts"].items()},
                    "self_consistency": o["self_consistency"]}
            bad = [f"{k}:{n}" for k, v in o["contexts"].items() for n, ok in v["checks"].items() if not ok and n != "fit_counts_pinned"]
            if bad:
                raise SystemExit(f"H{h}: measured origin checks failed {bad}")
        cfg, trial = recipe(h, **pins)
        m = manifest(h, trial)
        for name, obj in ((f"formal-origin-h{h:02d}.json", cfg), (f"manifest-origin-local-h{h:02d}.json", m)):
            with open(f"{out_dir}/{name}", "w") as f:
                json.dump(obj, f, indent=1, sort_keys=True)
            summary[name] = sha(f"{out_dir}/{name}")
    with open(f"{out_dir}/SHA256SUMS", "w") as f:
        f.writelines(f"{v}  {k}\n" for k, v in sorted(summary.items()))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
