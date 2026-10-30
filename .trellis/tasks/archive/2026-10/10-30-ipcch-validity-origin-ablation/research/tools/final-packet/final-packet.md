# Final recompute / logs / readback / Dashboard UI packet r1 — task 10-30 (NOT released; no live call made)

Runs once, after all three formal jobs are harvested (`research/cp3/jobs/06-harvest-hXX.json` ok) and BOTH packages of
every horizon are replayed (`07-replay-hXX.json`, `07-replay-annual-hXX.json`). Every identity is read from the actual
receipts at run time (job: `ledger/vertex/ipcch-origin-ablation-r1-formal-hXX/final.json` == submit receipt; run / LoggedModel
/ registered model / version: harvest receipt == harvested publication.json); nothing is typed in. Adapted from the accepted
task 10-28 final-packet tools (bases in `base-10-28/`, diffs in `diffs/`), with the two CH r3 verifier defects fixed up front
and exercised on REAL CH success artifacts (`logs/job-logs-real-success-exercise.json`,
`logs/readback-dataset-vs-render-real-exercise.json`).

One command from the workspace root: `bash staging/ipcch-origin-ablation-20261030/final-packet/run_final.sh > "<task>/research/cp4/run_final.log" 2>&1; echo $? > "<task>/research/cp4/run_final.rc"`.
Receipts only under `<task>/research/cp4/final/` (must be absent).

Preconditions (local; any failure stops before a live call): every harvested publication journal complete; every harvest
receipt ok; `replay_check.py` binds each replay receipt (passed, no integrity problems) to the CURRENT harvested holdout /
annual package (path + package.json sha256).

0. `identity_chain.py --stage pre --receipts <task>/research/cp3/jobs` (fixtures 8/8 as expected).
0b. `tools/recompute_origin.py` (independent; task 10-27 metric primitive, no training-code import): strict one-to-one pairing
    with the CH-final retained predictions; five periods x three groups + delta; reconciles every cell (metrics, n, declared /
    observed windows, original/copy counts, NA presence) with the job's origin_comparison.json and origin.* scalars, the new
    run's metrics.json scopes and scalars, and augmented_total with the CH-final run's metrics.json scopes and scalars (A4).
    Writes `recompute/tui.md` / `tui.csv` (F1, phase-3+ share R2, N, windows, NA reasons). Refusal stops before any live call.
1. `job_logs.py` — THREE Cloud Logging reads, one per actual job (job-filtered, limit 2000): no non-zero exit / Job failed /
   traceback / worker JSON with a non-null error or failed status; every complete `/runs/<segment>` token == the harvested run id.
2. `readback_origin.py` — ONE `mlflow-reader` access; read-only MLflow REST:
   - origin runs (formal:hHH): FINISHED / READY / READY in `IPCCH dashboard`; run → LoggedModel → version 1; names == the
     final render; every render-final tag on run/LoggedModel/version; baseline.* == the CH-final run; provenance.data_version,
     fit_labels, origin_ablation, ch_links, code_overlay, image digest and composite source id; live model-card.md bytes ==
     the card regenerated from the harvested record and its recipe-derived sections == the render; exactly ONE DatasetInput
     == the harvested payload (3 GCS generation GETs) and == the render on every non-job-output field; model Dataset metric;
     metrics/params exact; downloaded `models:/` package == local and routes ONLY the 2026 holdout context; report.* and
     origin.* metrics present, no common.*; `gcs-only` / annual package absent from MLflow.
   - CH-final baselines (baseline:hHH, anchors = task 10-28 supplemental readback receipts, all_checks_pass true): run /
     LoggedModel / version / card unchanged; run metric values and params == the retained CH-final trial.
3. `ui_targets_origin.py` (local): per origin run — run page (names, dataset, tags incl. fit_labels / origin_ablation,
   origin.* and report.* metric rows), artifacts (origin_comparison.csv/.json, origin_tui.csv, report tables, maps),
   dataset details, LoggedModel page; shared — Dashboard Experiments tab ("Model training") listing all SIX run names
   (CH-final + origin H0/H6/H12) and the Models table binding all six identities. sha256 recorded before step 4.
4. The unchanged task 10-20 harness `browser_check.py` (pins `ui-dependencies.sha256`, identical to the CH-pinned set plus
   `browser_rules.cjs`): ONE `mlflow-reader` access via the caller's ADC, identity passed to a headless, non-persistent
   Chromium child over stdin (never argv/env/URL/file/log).
5. `verify_run_rows.py` on the SAME targets.json (sha re-checked) → `ui-pass.json`.
6. `identity_chain.py --stage post` (logs-check job/run ids and readback run/LoggedModel/version == the chain) and
   `final-verdict.json`: final_pass = identity chain AND recompute AND logs (3 reads) AND readback (6 items) AND 6 identities
   AND 3 run-metric targets AND ui_pass.

Live footprint: 3 log reads, 2 reader-secret accesses, read-only MLflow REST/UI requests, 9 GCS metadata GETs. No MLflow,
GCS or ledger write; no fit, build, recovery, tag/card change, alias move or cleanup. Within the held job platform line.

Separate later packet: `cleanup_annual_weights.py` (annual weights only; source bound to this task's job record; dry run
first) after the Supervisor accepts the replays and the final verdict.
