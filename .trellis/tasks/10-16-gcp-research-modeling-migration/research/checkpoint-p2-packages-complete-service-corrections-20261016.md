# Checkpoint P2e: all retained registered versions packaged; service corrections (written 2026-10-16 04:21:29 EDT by `date`)

All evidence here is local Linux/WSL. No cloud resource was created and no provider was called.

## Registry ledger (`ledger/registry_ledger.json`)

242 versions; the key set equals the snapshot.

| Class | Versions |
|---|---|
| packaged_replay_passed | 170 |
| missing_weights_tracking_only | 72 |
| weights_retained_package_pending | 0 |

Replay summaries used:
- `replay-bf3da00`: GeoXGB P6/yearly and AlphaEarth, 36.
- `replay-forecast-602558c-supervisor`: forecasting, 56.
- `replay-somalia-e8d5160`: Somalia v2/v3/v4, 55.
- `replay-somalia-v1-50c2b38`: Somalia v1, 15.
- `replay-window-probe-62bc2a7`: window-probe comparators, 8 (rebuilt with the input binding below).

## Somalia-oracle v1 (native `50c2b38`; anchors from `somalia-v1-package-supervisor.md`)

- **Scope:** 15 versions (A/B/D at H0/3/6/12; C at H3/6/12; C H0 is the B alias). Each has 5 jobs × q2..q5 direct regressors `{job}_{arm}_{q}.ubj`.
- **Inference:**
  - The arm's ordered schema, cast to float32.
  - No calibration, residual, clipping or averaging.
  - Phase is the descending q5→q2 decode with `>= 0.2`, default 1 (`modeling.py:55-66` at `f576e690`).
  - Every saved row is served, including the primary=0 jobs (H3/H6 September 2025 and April 2026).
- **Dependency binding:** the matrices, predictions, schema, jobs and manifest are checked against the plan's run-level `files` records (sha256 + bytes) before reading, copied with the recorded sha, and cross-checked against the run manifest's `written` hashes.
- **Replay:** 15/15 pass, 1,980 reference rows (132 per version, all 5 jobs). Max error 2.0e-16; 0 routing mismatches; 0 phase changes; 0 stale.
- **Tests:** `test_packages_somalia_v1.py` 3 (routing, crossing decode, unserved key, non-finite refusal).

## Window-probe reused comparators (native `efdaea3` + input binding `62bc2a7`; anchors from `remaining-packages-supervisor.md`)

The eight versions keep their own identities (`reused_comparator`; original arms `base_global` / `base_local`) and have their own packages. They are not P6 aliases.

- **Served keys:** every row of the probe's selected cells:
  - H1/H3/H6: September 2023, 2024 and 2025.
  - H12: September 2024 and January 2025.
- **`pooled`:** each cell's P6 global unit.
- **`regional_ungated`:** P6 gate-pair `local_routed_provider` per mapped region (the local unit where `local_fit_ok`, else global), with unmapped rows on the global unit and no gate adoption (`run_probe.py:131-176`). The builder refuses plan records whose provider contradicts `local_fit_ok`, and saved `base_local_ok` must agree with the plan.
- **References:** the probe's saved `predictions_hHH_U.csv.gz` and `plan.json`, verified against its `artifact-hashes.json`.
- **Units:** bytes are enforced against the P6 member manifest, and each booster against its `record.json` sha. Unit counts: pooled 3/3/3/2; regional_ungated 27/24/19/20 (these include the 77 local units that no P6 package carries).
- **Input binding (supervisor S23 finding):** P6 `keys_hHH`, `X_rich561_hHH` and `feature_order.csv` are hashed before reading and must equal the probe's own `start.json` `prepared … artifacts_sha256`. The frozen map must equal `source-hashes.json`. Both records are bound by `artifact-hashes.json`, copied into `deps/probe/`, and listed in `package.json` `source.input_provenance`.
- **Serving scope, stated exactly:** keys outside the selected target months raise KeyError. Within a selected month any admin resolves through the frozen P6 map, and unknown admins take the unmapped/global route; they are not rejected.
- **Replay** (rebuilt packages): 8/8 pass, 3,096 rows, max error 2.2e-16, 0 routing mismatches, 0 phase changes, both routes covered, 186 MB.
- **Tests:** `test_packages_window_probe.py` 2.

## Service corrections (native `d84dabd`; supervisor findings on `733f2c0`)

1. **Role precondition (fail-closed, before any change):**
   - Managed roles must hold exactly their contract.
   - `ipcch-job-writers` may be assigned only to declared job identities.
   - Job and assistant identities must exist and be non-admin.
   - No ordinary reader or assistant may hold a grant beyond READ (the assistant: plus Gateway endpoint USE).
   - Conflicts are reported and nothing changes; nothing is revoked and no exception is invented.
   - The report is a keyed snapshot (users with admin flag and role ids; roles including empty ones, with permission rows and assignees). Afterwards every copied user, role, row and assignment must be unchanged.
   - Scope of the claim: the REST-visible auth model in workspace `default`. Legacy per-resource tables are covered by the full-store copier's table comparison (`checkpoint-p2-store-rehearsal-20261016.md`).
2. **Armed rehearsal uses the service's real assistant account:**
   - `users/current` shows that account, non-admin.
   - READ positives pass, and write, create and escalation negatives are refused.
   - Earlier rehearsal job identities on the same stores must be declared (`--prior-state`); the first armed attempt was correctly refused by the precondition before this was added.
3. **Assistant probes:**
   - `PROBE-DENY` requests deletion of the real probe run.
   - The listing and denial predicates parse the exact quoted tool result. A regression covers the false-pass case "Error: experiment access denied".
   - Both rehearsal CLIs exit nonzero on any failed check.

Rerun on fresh stores (`p2-service-d84dabd/`; reports checked free of the throwaway secrets):

| Report | Result |
|---|---|
| deny | 50/50 |
| armed (service assistant account) | 48/48 |
| restart | 7/7 |
| assistant end-to-end | 9/9 |
| copied-store roles (`workspace-roles-wsc.json`, `wsc_check.py`) | 16/16 |

Copied-store role results: users and roles preserved. The copied non-admin's added grants are exactly READ on `experiment:*`, `registered_model:*` and `prompt:*`. The new job writer's added grants are workspace USE and EDIT on experiment 1. The admin gets nothing added.

Tests: guard 13, start-up 11, rehearsal regressions 8, all passing. Regression 8 (`f49520a`, supervisor S23): a service assistant identity also declared as a job identity is refused before any mutation, and no API mutation is made.

**Evidence limits:** the fake Vertex upstream is local integration only. The live Vertex call, Cloud Run restart and proxy behavior remain separate later gates.

## pop-v1 population-history packages (native `6d95905`; unregistered retained run; anchors from `remaining-packages-supervisor.md`)

- **Granularity:** one package per arm × horizon (6 × 4 = 24). Each package routes a key to its main fold's frozen-config model (110 folds; 32/30/27/21 per horizon). Identity: `pop-v1/{arm}/h{HH}`, an unregistered retained research run.
- **Bindings:**
  - fold identities must name the run's keys, calendar and matrix digests (the matrix is hashed against `freeze.json`);
  - model bytes must equal both the verified inventory and the identity's sha and bytes.
- **Scoring:**
  - rich_rf uses the fold's **saved** positional fill values (OutOfRangeImputer `transform`; never refitted);
  - constant routes answer the recorded constant;
  - correction flips by persistence b, and the regressor is clipped;
  - decisions use strict `crisis > t_b` with `±Infinity` literals, and 0.5 for no-history fullpool rows.
- **Acceptance:** the current `run_pipeline.py` matches neither recorded code hash, so the loader is a thin reimplementation accepted only by replay against `reports/main_predictions.csv.gz`.
- **Runtime:** `rt-popv1-x300` (numpy 2.2.6, pandas 2.2.3, scikit-learn 1.6.1, scipy 1.15.2, xgboost 3.0.0; the original was Windows Python 3.12.10 with the same packages).
- **Replay of the `6d95905` build (superseded):** 24/24 pass, 20,106 rows. Raw and crisis scores had max error 1.5e-8, decisions were exact, and there were 0 routing mismatches (930 MB). Those receipts are not committed as current.
- **Supervisor findings on `6d95905`, fixed in `3c47cc5`:**
  - `route` (`model` / `constant_*`) and `support` are now kept apart and both checked exactly; `replay.py` gained declared `exact_columns`.
  - Before any package is started, every fold identity must bind the `freeze.json` selections and the frozen feature schema and candidate configs, and the `feature_schema.csv` order must equal the frozen rich order.
  - Regressions cover a retained route, drifted selections, a reordered schema and a changed frozen schema.
- **Status:** the 24 packages are being rebuilt at `3c47cc5`. The full replay is the supervisor's after the rebuild.
- **Tests:** `test_packages_popv1.py` 4 (saved-fill imputation, correction flip and constant route, clip with strict ±Infinity thresholds, no-history threshold and unserved key).

## FEWS NET `confirm-onset-v1`

Blocker receipt: `fews/confirm-onset-missing-local-boosters-receipt.md`.
- The producer called `save_fold(..., False)`. The gates record 9 local continuations (7 unique child sha256) whose bytes were not retained.
- These affect 2,446 of 11,436 system rows (S0 1,609 + S3 837).
- An exact-hash search of the complete 36,305-file cache found 0 of 7.
- The global/pooled path remains replayable on its own.
- User disposition is needed. The `scen-b43ef6a-v1` exception is not applied.
