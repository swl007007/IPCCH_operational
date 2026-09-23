# Execution plan — country confidence v3

Spec: `design.md` (approved for execution by the user on 2026-09-23 via "按照落盘的spec执行"). Requirements: `prd.md`.
Validation scope: focused executable checks and independent verification only; no TDD/regression suite.

## Global constraints

- Parent `P = Outcome/model_delivery/202609_h5/20260911_training_confidence_v2` is read-only; its manifest hashes must still verify at the end.
- Output `V = Outcome/model_delivery/202609_h5/20260923_country_confidence_v3` (fresh, create-only).
- Saved models, polygon predictions, inputs, geometry, mapping and Census references are byte-identical to P.
- Runtime: `~/.venvs/ipcch-h5-202609` (Python 3.12.3, pinned `requirements.txt` of P). Record versions in metadata.
- Historical FEWSNET source `R = .../food_crisis_cluster/paper_reproducibility_package/stage3_results/georf_fs1/predictions_monthly.csv`; use `y_pred_partitioned` only, keep saved decisions (no re-thresholding). Record its SHA-256 and copy manifest.
- Symbol edits require GitNexus upstream impact first; commit requires `detect_changes`.

## Files

- New `tools/revise_h5_country_v3.py`: `prepare`, `fewsnet`, `ipcch`, `selfcheck` actions; pure functions
  `weighted_country_errors`, `confidence_flag`, `decode_cumulative_phase`, `maximum_phase_uncertainty`, `append_country_v3`.
- New `tools/verify_h5_country_v3.py`: independent recomputation (dict/Fraction arithmetic, separate decoder), preservation checks.
- Edit `tools/run_h5_model_delivery.py`: `score` include_uncertainty gate and `export_tables` country append recognise the v3 policy, so re-export reproduces v3 schema instead of v2 flags.
- Edit `tools/verify_h5_model_delivery.py`: treat v3 as revised (dispersion naming, relocation policy copy).
- Edit `tools/package_h5_delivery.py`: require passed v3 verification when v3 policy exists.

## Steps

1. [x] Lifecycle: mark spec approved, write manifests, commit `.trellis/` spec+plan; `trellis-audit --repo '<registered path>' start country-uncertainty-phase-revision`; verify run/executor/base_sha/in_progress.
2. [x] Impact analysis on edited symbols (`score`, `export_tables`, `verify`, `package`), report risk.
3. [x] Implement `tools/revise_h5_country_v3.py`; run `selfcheck` (exact 0.1/0.2 flag boundaries, 0.5 crisis boundary, missing-support nulls, cascade decode incl. nonmonotonic, max-phase statuses no/single/degenerate/supported, seed reproducibility).
4. [x] `prepare`: verify P manifest, copy P to V excluding manifests/archive/final reports; move v2 confidence artifacts (`{model}/country_training_confidence.csv`, `fewsnet/polygon_training_errors.csv`, v2 policy/summary/verification, v2 spec) into `reports/parent_v2/`; strip `country_training_*`, rank, tie fields from country tables; record parent hashes; copy runtime tools and spec.
5. [x] `fewsnet`: join R to delivered identity; export `reports/fewsnet_stage3_historical_errors.csv`, `fewsnet/polygon_confidence.csv` (all 5,718 polygons), `fewsnet/country_confidence.csv`; add `country_outcome_crisis`; join into `country_predictions.csv`.
6. [x] `ipcch`: replay four saved models on exact training rows (no fitting); assert phase3 equals P's saved predictions (atol 1e-12); export `reports/ipcch_four_target_training_replay.csv`, complete-month inventory, scenario table; compute weighted Phase3+ country error (from P's saved area errors), flags, `country_overall_phase`, `country_maximum_phase`, maximum-phase proxy + bootstrap; export `ipcch/country_confidence.csv` and join.
7. [x] Write `reports/country_confidence_v3_policy.json` / `_summary.json` (method, seed 20260923, B=10000, PCG64, percentile linear, library versions, source hashes, anomaly counts).
8. [x] Code edits to runtime/verify/package tools; re-copy runtime tools into V.
9. [x] Run `tools/verify_h5_country_v3.py` and `tools/verify_h5_model_delivery.py` on V (relocated rescoring); independent read-only review subagent recomputes key numbers.
10. [x] README v3 section; `tools/package_h5_delivery.py --root V` (bundle, archive, manifest); confirm P manifest still verifies.
11. [x] Spec update (`.trellis/spec` if a reusable convention emerged), `detect_changes`, commit code + task artifacts; `trellis-audit close` from this executor; verify job queued via `status`/`show`.

## Rollback

Delete V (never P) and revert tool edits via git. No other state is modified.

## Execution record (2026-09-23)

- Audit run `dd4a0e7dafcd41f9ab638241eb9debc2`, base `4c21195`, executor Claude session `fce0831a-4ef8-458b-b0c4-c2b930504dd5` (pane wC:p2). The unstarted `00-bootstrap-guidelines` task was set back to planning so this task could start.
- Code commit `af3cb46`; v3 delivery manifest `passed` (171 files, code_commit af3cb46); archive 165 members; v2 parent manifest still verifies (153 files).
- Focused checks: `revise_h5_country_v3.py selfcheck`, `check_h5_delivery_focus.py`, `verify_h5_country_v3.py` (independent recomputation), `verify_h5_model_delivery.py` (relocated rescoring equal). An independent read-only reviewer reproduced items 1–5 from raw sources with no blocker. Its minor findings were fixed: the export guard now rejects stale forecast-derived country fields, IPCCH replay source hashes are recorded, the code was committed before packaging, and the README states the CI/degeneracy caveat and marks the v2-era docs.
- Results: FEWSNET 11/4/7 high/medium/low; country_outcome_crisis=1 for 6/22 countries. IPCCH 27/14/12; overall phase {2:35,3:17,4:1}; maximum phase {2:21,3:29,4:3}; uncertainty status no_complete_history 10, single_month 9, degenerate_empirical 17, supported 17.
- Spec update (3.3): no `.trellis/spec` change. The spec files are still unfilled bootstrap placeholders owned by `00-bootstrap-guidelines`; the v3 conventions live in the delivery policy JSON and README.
