# CP1 checkpoint — research data preparation and training packet (Executor; ready for Supervisor review)

Executor: Claude Opus 5.5 1M, session 6a490ae1-ee00-43f9-bdfc-c887c9816c09, Herdr w1A:p2. Operational branch feat/ipcch-validity-feature-inference @ e41a11b (CP0 accepted, implementation released; native task in_progress). No Trellis Audit.
Hold: no paid fits, image build or cloud writes until the Supervisor reviews this packet.

## 1. Research isolation (done)
- Capture before and after: control-plane HEAD 5e94e12, tracked diff sha256 3879ba2e…, 9 file hashes unchanged (`capture-manifest.json`, `capture/`). mlruns and research-root changes are excluded; PROGRESS/RUNBOOK hunks are kept in the patch only.
- Worktree `R/control-plane-h2h8h14`, branch `task/ipcch-h2-h8-h14-final`, baseline commit 4cb493f (3 modules + 4 tests; post-apply hashes equal the manifest). The original dirty tree is untouched (still 10 entries).

## 2. Environments (exact)
- Research numeric: `~/.venvs/ipcch-validity-idp`, Python 3.12.3, 61/62 pins of the image lock `images/training-ipcch-validity/requirements.lock.txt` (sha256 ce0b23ad…), with the explicit certifi exception (2026.10.19 vs 2026.7.22). Used for every unittest, discovery gate and pinned gate.
- Tooling (supplementary only, NOT numeric-lock parity: numpy 2.5.3 / pandas 3.0.6 / mlflow 3.17.0): `~/.venvs/ipcch-mlflow` for the pytest integration suites.
- Cloud image (CP2): base `training-ipcch-validity@sha256:fd921dd7…` (439a488) plus three overlaid modules. Between 439a488 and 5e94e12 only `ipcch_hpt_control.py`, its test and the RUNBOOK differ under research_cloud.

## 3. Code changes C1–C5 (committed 9aa9e54 on task/ipcch-h2-h8-h14-final; tracked diff 4cb493f..9aa9e54 sha256 621267e6… = the bytes the regression ran on)
- `ipcch_validity_features.py`: FINAL_HORIZONS (2, 8, 14) are oracle-free only (`check_horizon`); `expected_features(..., oracle)` gives 527; R57 log constants and `gpp_available_through` / `gpp_availability_block`, which mask the series per vintage before the compact ordinary/z/stress recipes; build/CLI flags `--ch-links --no-oracle --gpp-availability`; per-H GPP availability summary.
- `ipcch_validity_pooled.py`: FINAL_ARM `validity_augmented_idp_202610_acledagg_lag1_uncal_ch_final`; Schedule `main_window` (default True and not recorded); supplement-only scoring blocks; `check_final_config`, `verify_final_freeze` (mapped H0→H2, H6→H8, H12→H14), `final_prepare` (input pins, order pin, key multiplicity, cohort, digests; equivalence.json before refusal), `final_fit`, `final_scope_metrics` (reported only), CLI/objective wiring; `oracle_completeness(oracle=False)` on the final arm.
- `dataset_input.py`: FINAL_ARM in ALL_LABEL_ARMS; CH-link tags for the final arm; 10-28 tags unchanged.
- compact.py is not edited (caller map: `caller-map.md`).

## 4. Tests
- Baseline 4cb493f: 121 tests OK, exit 0 (`tests/baseline-4cb493f.txt`, log sha 94aaa993…).
- Focused `test_ipcch_final_stage` (18): run 1 had 2 errors, run 2 failed at import (IndentationError), run 3 OK (`tests/final-stage-history.md`). Route tests mock `vf.build_dataset`, so they are route/unit tests and not real-builder E2E.
- Regression in the numeric env (5 baseline modules + the new module): Ran 139 tests in 1381.683 s, OK, exit 0 (`tests/regression-unittest.log`). The 121 baseline tests are unchanged and the 18 new tests pass.
- Direct four-class (numeric env `ipcch-validity-idp`, unittest; external caller of the changed functions with defaults): Ran 21 tests in 61.1 s, OK, exit 0 (`tests/direct-fourclass-unittest.log`).
- SUPPLEMENTARY, tooling env `ipcch-mlflow` (numpy 2.5.3 / pandas 3.0.6, NOT numeric-lock parity): test_training_validity_integration 27 passed, exit 0 (incl. the ARMS == ALL_LABEL_ARMS assertion); test_ipcch_hpt_control: first run in `ipcch-mlflow` gave 67 passed + 40 setup ERRORS, exit 1, all `ModuleNotFoundError: No module named 'google.api_core'` (missing in that venv; log preserved `tests/supplementary-hpt-control-pytest-ipcch-mlflow-env-FAILED-setup.log`). Rerun in the existing tooling env `R/envs/mlflow-svc` (Python 3.12.3, mlflow 3.17.0, pytest 9.1.1, google.api_core importable; numpy 2.5.3 / pandas 3.0.6, also NOT numeric-lock parity): 107 passed, exit 0 (`tests/supplementary-hpt-control-pytest-mlflow-svc-env.log`). No environment was modified and no product workaround was made.

## 5. Real unmocked no-fit discovery builds (placeholder pins; discovery only)
Inputs: 17 roles staged on native disk `R/scratch/h2h8h14-cp1/inputs/`, asserted (each role once, independent re-hash == manifest sha256, no extra files). These are the same bytes as the 10-28 formal manifests' generation-pinned objects.

| H | cutoff | matrix | order sha256 (= retained H0 schema b9f234c9…) | train rows (copies) | scored | excluded families | dup keys train/score | overlap | refusal |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 2025-11 | 147,268 × 527 | yes | 128,090 (90,331) | 15,317 | 60 | 0 / 0 | 0 | placeholder cohort only |
| 8 | 2025-05 | 147,268 × 527 | yes | 121,096 (87,588) | 15,317 | 60 | 0 / 0 | 0 | placeholder cohort only |
| 14 | 2024-11 | 147,268 × 527 | yes | 110,762 (81,950) | 15,317 | 60 | 0 / 0 | 0 | placeholder cohort only |

GPP (R57) on all 147,268 rows: `value_at_origin` and `hist_same_month_z_at_origin` are all-NaN (the origin month is never published by O+2), and the derived columns are sparse. H2 rows by availability cutoff: none 29,973; through 2018-12 18,908; 2020-12 14,681; 2021-12 19,106; 2022-12 19,148; 2023-12 13,818; 2024-12 27,977; 2025-12 3,657. H8: none 37,049; 2018-12 16,816; 2020-12 15,952; 2021-12 20,301; 2022-12 19,006; 2023-12 13,266; 2024-12 24,878; no row reaches 2025-12. H14: none 44,719; 2018-12 17,527; 2020-12 20,422; 2021-12 17,746; 2022-12 19,384; 2023-12 15,267; 2024-12 12,203. Rows with any GPP value: H2 115,189, H8 108,213, H14 100,621; `ma12_at_origin` nonmissing: 25,662 / 45,809 / 27,794.

## 6. Pinned recipes
`recipes/config-final-h{02,08,14}.json`, created by `pin_recipe.py` from each discovery `equivalence.json` (refuses unless the only failure is the placeholder cohort, the order passed, keys are unique and the plan checks are true). H02 sha256 e7ce52a9…, H08 dfaeab34…, H14 076090e6….

## 6b. Final pinned gates (real unmocked builder; committed code 9aa9e54, clean worktree)
Command per H: `cd control-plane-h2h8h14 && IPCCH_AE_SRC=… PYTHONDONTWRITEBYTECODE=1 ~/.venvs/ipcch-validity-idp/bin/python -m research_cloud.training.ipcch_validity_pooled gate --manifest recipes/manifest-local-hHH.json --config recipes/config-final-hHH.json --out R/scratch/h2h8h14-cp1/gate-pinned-hHH` (runner `gates/gates-pinned.status`; the first launch failed with exit 126 because the derived runner script lacked its execute bit, nothing ran, and it was relaunched with `bash`).

| H | exit | wall / max RSS | gate passed | differing digests | cohort | digests identical to discovery build | 527-name order == retained H0 package deps/feature_order.csv |
|---|---|---|---|---|---|---|---|
| 2 | 0 | 3:44 / 3.18 GB | yes | none | 15,317 | yes | yes |
| 8 | 0 | 3:36 / 3.17 GB | yes | none | 15,317 | yes | yes |
| 14 | 0 | 2:19 / 3.24 GB | yes | none | 15,317 | yes | yes |

Evidence copies: `gates/{unpinned,pinned}-hHH/{gate.json,equivalence.json,dataset-summary.json,feature_order_hHH.csv,gate.log}`. The rebuild is deterministic: two independent builds per horizon give identical 13-digest sets.

## 7. Paid packet (not released)
`cp1-packet.md`; packet tree `R/staging/ipcch-h2h8h14-20261030/` (SHA256SUMS + `verify_packet.sh` preflight). Image build context from 9aa9e54 (record c9575d08…). The in-image check differs from r1 by one line (`overlay_check-vs-r1.diff`), and the local overlay/selfcheck simulations are recorded. Plan sha256 9e36cb19… (USD 6.9119 reservation estimate, not a billing cap). At most two concurrent jobs, with fresh occupancy before each wave.

## 8. Remaining risks / open items
- C6 evidence builder and C7 runtime packaging are CP2 work (after fits); the CP1 measurements show unique fit keys at all three horizons (no aggregation needed).
- The selfcheck simulation stops at the local certifi lock difference; the in-image run is the authority.
- The platform pool headroom is tight (98.90/100 after this packet). A month rollover (2026-11) requires a re-rendered plan.
- Two GPP origin columns are all-NaN by construction (R57); this is documented, not imputed.
- D6 (FEWS partition CRLF) and S1 port remain CP3 items.
