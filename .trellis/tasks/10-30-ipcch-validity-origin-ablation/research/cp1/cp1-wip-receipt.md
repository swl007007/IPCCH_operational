# CP1 WIP receipt — implementation commit 7023d10 + Supervisor WIP fixes

Commit 7023d10 on task/ipcch-validity-origin-ablation (pooled d2c07d7d…, dataset_input 2b74098a…).

Supervisor WIP findings (classification: none changes a result; 1 breaks a required check, 2 weakens published
evidence, 3 is a missing pre-expense gate) — fixed:
1. `plan --digests --check` under original_only: filtered digests vs `origin_ablation.self_consistency` AND unfiltered
   plans vs `baseline.equivalence` (CH-final pins), separately labelled `origin:`/`baseline:`. Test PlanCli (valid
   passes; wrong origin pin -> exit 1; wrong baseline pin -> exit 1).
2. `dataset_input.payload`: saved fitting memberships must be strictly increasing, in range, originals, pinned count and
   pinned key digest (trainer `keys_sha256` convention; parity test). Negatives: copy substitution, duplicate [0,0],
   unordered, out of range, same-count original substitution, count mismatch both ways.
3. A2 pre-fit: in-job `origin_score_check` (prepared scored rows vs retained CH-final predictions CSV via ch_pairing,
   before any fit) + independent local verifier (gate's fresh labels cut by scheduled windows vs CSV).

Touched symbols (narrow review list): ipcch_validity_pooled: FIT_LABELS, ArmData.fit_labels/__post_init__,
plan_contexts, plan_summary, plan_assertions, run_fit (guard), check_config (1 line), check_formal_contract (CH-final
branch), check_hpt_config (dispatch), hpt_prepare (ablation branch), hpt_fit (dispatch), plan_main (digests), new:
ch_recipe_view, ch_gate_view, check_origin_ablation, origin_gate, origin_score_check, origin_periods, _origin_group,
origin_comparison, origin_comparison_metrics, write_origin_comparison, origin_caveat, origin_formal, constants.
dataset_input: keys_sha256 (new), payload (title + membership check + tags).

Focused tests: test_ipcch_origin_ablation 15/15 OK; DatasetInput (origin 11 + CH + GOSIF) 16/16 passed.
Full inherited regressions on 7023d10: running (receipt to follow).

No-fit provisional gates (pre-fix code, placeholder pins): only placeholder pins differ; CH contract passed (unfiltered
build == CH-final); all origin intervention checks pass in 11 contexts; only memberships/history_overlays/fit_keys/
schedule digests change. Original-only fit rows: H0 19169/24197/28551/37759, H6 21282/22478/27134/34004,
H12 21282/25960/30784. Independent verifier `verify-provisional.json`: retained artifacts reproduce CH pins; expected
memberships/overlays/fit-keys digests (from retained CH-final outputs) == gate; A2 prepared score rows == retained CSV
(70972/61042/52027 rows, 0 mismatches). Final pins and final gates on committed code next.
