# C6/C7 local implementation (Executor, 2026-10-30)

Location: separate worktree `R/control-plane-h2h8h14-pkg`, branch `task/ipcch-h2h8h14-package`, commit f6822b5 (on 9aa9e54). The frozen training worktree `control-plane-h2h8h14` (9aa9e54, clean) is untouched while jobs run.
Module: `research_cloud/packages/operational_ipcch.py` (research-side handoff tool; not a runtime dependency). Tests: `research_cloud/tests/test_operational_ipcch.py`.

## Semantics (checked against R31/R61 and the original builder)
- Scores: RAW backbone quartet `vp.predict_quartet` (DMatrix, missing=NaN). No projection, clipping or calibration (identity); `q*_star` is not used. The test compares replayed scored-row predictions to the trial's raw `q*_backbone` columns (bit equality).
- Fit matrix: `vp.prepare` (pinned recipe + local byte-verified inputs; gates prove equality with the cloud pins) then `vp.materialize(d, train, train_excluded or S_E)`, as `run_contexts` does for the backbone. Must equal fit_ledger `train_keys_sha256`, `X_train_sha256` and `y_sha256` and the harvested `memberships.npz` backbone rows; else refuse.
- Error rule = original builder `build_ipcch_resubstitution_evidence.py:56,135-153`: per fit row `(q3 raw score >= 0.20) != (q3 share >= 0.20)` (inclusive, no cummax); per polygon `sample_count = size`, `error_count = sum`, unweighted. Residual = actual − raw score for phase2..5.
- Rows: every fit row of the single final context, including CH/IPC copies; key (polygon_id, target_month) must be unique (duplicate → refuse; never aggregated). Weights (halving24) are kept in the audit sidecar only.
- Identity: `model_package_id = <package>/scope_{0,6,12}m`, `horizon_months` = runtime scope key, basis `training_resubstitution`, period = fit-target min..max ≤ the per-H cutoff (2025-11 / 2025-05 / 2024-11).
- Conversion: `phase{2..5}_worse_model.json` saved from the UBJ boosters; `XGBRegressor.load_model` scores must equal the booster on the full fitted matrix (bit equality, else refuse) and on an all-NaN row. 527-row contract: category required, missing_tolerance 1.0, no fill, no `imputation_statistics`. Metadata: cummax, thresholds default 0.20, model horizon, public lead, origin offset −2, per-scope cutoff, R58 year-dummy note. Root `model_package_manifest.json` has per-scope `training_cutoffs` and NO single `training_cutoff` (CP3 C6b reader change); `package_manifest.json` (R51) has status candidate and acceptor null.

## Tests (numeric env `~/.venvs/ipcch-validity-idp`)
- Run 1: Ran 6, FAILED (failures=1), exit 1. The scored-row comparison read predictions.csv.gz with pandas' default float parser (5.6e-17 differences; the test's CSV round-trip, not the replay). Log `c6c7-tests-run1-FAILED.log`.
- Run 2 (test reads with float_precision="round_trip"): Ran 6, OK, exit 0. Log `c6c7-tests-run2-ok.log`.

## Next (after harvest)
`python -m research_cloud.packages.operational_ipcch --trials H2=… H8=… H14=… --recipes research/cp1/recipes --manifests research/cp1/recipes --runs RUNS.json --package-id <id> --out <new dir>` → evidence + runtime package; then the operational CP3 loads it through the runtime loader.

## Fixture-only full-scale dry run (2026-10-30; NOT a new model; never a substitute for H2/H8/H14 artifacts)
- `fixture-dryrun/dryrun_convert.py` (research env, package worktree f6822b5) applied the retained 10-28 H0 `h00_supp_2026` boosters (same 527 order, asserted) to the real rebuilt H2 final fit matrix (`vp.prepare` on the pinned H02 recipe, 128,090 rows). Exit 0, 126 s: `convert_scope` JSON == UBJ scores on all 128,090 rows; evidence frames built (6,178 areas). Output `R/scratch/h2h8h14-final/fixture-dryrun/run1/`.
- `fixture-dryrun/runtime_load_check.py` (OPERATIONAL exact-lock env `~/.venvs/fewsnet-test-lock-20261022`, unchanged `model_pipeline.ipcch_launch_runtime`): `load_scope_package` → `apply_feature_contract` → `score_scope` on 2,000 real rows. Run 1 and run 2 exited 1 on fixture-input gaps (score_scope needs population identity columns; then the population contract needs reference period ≤ feature month with a matching method); logs preserved. Run 3 exit 0: contract status passed, 0 features filled, NaN cells 50,059 in = 50,059 in the matrix (passthrough), runtime raw scores == booster scores bit for bit for phase2..5, unclipped (min −0.0249), thresholds 0.20, cummax.
- Implication for CP3: the existing runtime loader/contract/scoring path accepts the new-format scope without code change. Still needed in CP3: per-scope cutoffs (C6b), R19 inf/unparseable rejection, and new-contract metadata routing.

## CP2 review fixes (Supervisor finding on f6822b5) — commit see below
- Evidence area/residual CSVs are now written INSIDE `package/evidence/` (`write_evidence`), referenced as `evidence/<name>` and hashed in `package_manifest.json` `files`; audit sidecars go to a sibling `audit/` (not runtime inputs; sha256 recorded).
- `verify_combination(package_root)`: every listed file present and re-hashed under the (relocated) root, nothing outside the root, no unlisted file, and every scope evidence reference resolves to a listed file with that sha256. `main` refuses if it reports any problem.
- `load_boosters`: the whole source package must pass `verify_package` (all listed files re-hashed, no unlisted file), and each q2..q5 weight must have its own listed sha256 (a missing entry refuses; it is not skipped).
- `publication_identity`/`bind_run`: publication.json must be complete and bound to this package.json (`package.json_sha256`); the supplied run identity must equal run_id/model_id/registered_model/model_version, and the full identity incl. package content sha256 enters the scope metadata and manifest.
- Tests: run 3 had 3 ERRORS (test-fixture lifetime: the first class's teardown removed the shared trial; log `c6c7-tests-run3-FAILED-fixture-lifetime.log`); run 4 after moving the fixture to module scope: Ran 9 tests, OK, exit 0 (`c6c7-tests-run4-ok.log`). New tests: relocation with no siblings, tamper/missing/unlisted detection, unlisted weight entry, altered other source file, run binding mismatch and unbound publication.
