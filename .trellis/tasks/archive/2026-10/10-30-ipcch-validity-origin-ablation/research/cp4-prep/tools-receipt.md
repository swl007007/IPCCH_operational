# Post-job tool preparation receipt (local; nothing run against cloud)

## recompute_origin.py (independent TUI/metric recompute) — repaired per Supervisor review of 634e94ad
sha256 72871f96e7405434a32a1c11ac9c801fecb0561aab6b1c0327e10d22f1236bd7. Reporting-only changes (no metric definition changed; the
task 10-27 primitive is still imported unchanged):
1. NA reasons: `reasons()` reads each undefined metric's cause off the quantities the primitive itself tests (tp+fp=0,
   tp+fn=0, tp+fp+fn=0, 5tp+4fn+fp=0, four-class levels absent from truth and prediction, n<2, constant q3 truth, empty
   declared window); delta reasons name which side is undefined.
2. Windows: declared_from/to (cell) and observed_from/to, original_rows, copy_rows (group) reconciled against the job's
   origin_comparison.json; tui.md shows declared and observed windows (H6 2023 = 2023-07..2023-12; H12 2023 empty with reason).
3. Baseline (A4): augmented_total now reconciles the CH-final trial metrics.json `scopes` (six metrics, n/original/copy
   rows, NA presence) AND its MLflow scalars; the new run's whole-population scopes reconcile its own metrics.json and
   scalars; docstring narrowed to exactly these checks.
Tests: `tools/test_recompute_origin.py` 15/15 (consistent H6/H12 pass; observed, declared, copy_rows, CH metrics.json
count/value/missing scope and new metrics.json mutations each reported; primitive NA reasons; CLI Markdown windows).
Real self-validation (`--no-job`, CH-final vs itself, x3): passed incl. the CH metrics.json reconciliation; deltas 0.
Pairing negatives (dropped row, perturbed truth 1e-12, label kind, duplicate) refused (`check/recompute-negatives.log`).

## final-packet (draft, not pinned for release yet)
- readback_origin.py (from readback_ch.py; diff in diffs/): origin title/render/CH-final baselines (anchors = task 10-28
  supplemental readback receipts, all_checks_pass true); fit_labels/origin tags; origin.* metrics present, no common.*;
  published package routes only the holdout context; gcs-only/annual-package absent from MLflow; `idp_ledger.sha256`
  treated as a job-output field (gzip mtime; CH r3 defect) — replayed on the REAL CH-final trials vs the CH render: the raw
  sha differs, nothing else differs (`logs/readback-dataset-vs-render-real-exercise.json`).
- job_logs.py: worker error = non-null error or failed status (CH r3 `"error": null` defect); exercised on the REAL
  successful CH-final logs (pass; original CH verifier failed them) and a real-format failure line is caught
  (`logs/job-logs-real-success-exercise.json`).
- identity_chain.py (+ fixtures 8/8 as expected, `logs/test_identity_chain.log`), ui_targets_origin.py (negative dry run
  on non-origin receipts refused with the exact missing origin tags/artifacts/metrics), run_final.sh (all paths quoted;
  local recompute step before live calls), cleanup_annual_weights.py (deletes only annual weights/*/q*.ubj after a passed
  annual replay; generation-pinned; dry-run default).
- UI: unchanged task 10-20 harness (browser_check.py fc7803aa…, headless Chromium, mlflow-reader via ADC→stdin).

## Supervisor review of cleanup 9b26fe2b / run_final 8967ee9d — fixed
- HIGH cleanup source binding: `cleanup_annual_weights.py` (26eb5d2392d52f71…) derives the trial
  prefix only from this task's own ledger record (final.json SUCCEEDED == submit.json name; display name; task/horizon labels)
  as `<artifacts>/trials/ipcch_validity_pooled/<job id>/trial-0`; refuses CH-final job ids, a harvest receipt whose
  job/source/trial_dir differ, listing objects outside the prefix; the annual replay is bound via replay_check.
- MEDIUM run_final.sh (c9c789cf02141ec0…): both replay receipts per horizon must pass `replay_check.py`
  (3d30a801ee7e5c19…): passed, no integrity problems, exactly the current harvested holdout / annual
  package directory and its current package.json sha256.
- Tests `test_cleanup_and_replay.py` 13/13 (`logs/test_cleanup_and_replay.log`): valid plan; CH-baseline source with an
  otherwise valid replay refused (scout case); baseline job id in the ledger, harvest job mismatch, failed job, other task
  label, listing outside prefix, replay of another package, stale package.json, unpassed replay, missing receipt refused.
