# CP2 — real H2/H8/H14 combination package (CANDIDATE) and relocated runtime parity

Package worktree `control-plane-h2h8h14-pkg` @ ca3f14a (training modules features e56ccf41 / pooled 4a4dd377 / dataset_input c7aadb13 = trained shas). Recipes `research/cp1/recipes/config-final-hHH.json` byte-equal to the uploaded job configs (sha e7ce52a9 / dfaeab34 / 076090e6). RUNS.json from the three harvest receipts (09-harvest-h0{2,8}/h14.json, all ok).

Build: `package-check/build.sh` (copy) -> R/scratch/h2h8h14-final/package-build/out-r1, exit 0 (`package-build-r1.log`): per H the final gates passed (15,317 scored rows, 13 digests, keys unique), `replay_fit` verified the rebuilt fit against each trial's fit ledger and backbone membership (fit rows H2 128,090 / H8 121,096 / H14 110,762; evidence areas 6,178 / 6,144 / 6,017), run identities bound to publication.json.
- package_manifest.json sha256 **18b91d454163ac9ff9833d8127108e731b2f9d95069fb26fd5e7e8877a115f22**, 28 files, combination_id ipcch-validity-h2h8h14-final-20261030, contract ipcch-final-h2h8h14-v1, **status candidate** (acceptor/accepted_at empty — preserved until explicit research acceptance). Supervisor independently hashed all 28 files.

Relocated runtime check (`package-check/run_check.sh` -> `run_check-r1.log`, exit 0):
- stage 0: `verify_combination` = [] on the built package and on a byte copy at a different path (check-r1/relocated-package).
- stage 1 (`probe_real.py`, research env): per H rebuilt the final fit (replay_fit verified again), probes = 2,000 random fit rows + 2,000 random scored (2026) rows with the harvested UBJ boosters' raw quartet scores.
- stage 2 (`runtime_check_real.py`, exact-lock operational env, model_pipeline.ipcch_launch_runtime on the RELOCATED copy): `runtime_check_real.json` ok=true.

| H (scope) | rows | features | raw scores == UBJ (q2..q5) | NaN cells in -> matrix | filled | thresholds / monotonicity |
|---|---|---|---|---|---|---|
| H2 (0m) | 4,000 | 527 | all True (bit-equal) | 108,355 -> 108,355 | 0 | 0.2 x4 / cummax |
| H8 (6m) | 4,000 | 527 | all True | 111,072 -> 111,072 | 0 | 0.2 x4 / cummax |
| H14 (12m) | 4,000 | 527 | all True | 118,888 -> 118,888 | 0 | 0.2 x4 / cummax |

Receipt repair (Supervisor review of r1): r1's script read the package id from a non-existent key (score summary id "None") and used target_month 2026-10 for every scope. `runtime_check_real_r2.py` (stage 2 only; same stage-1 probes, same relocated package; no rebuild/refit) uses `combination_id` and the operational mapping M = 2026-10 -> O = 2026-08, target = M + scope (2026-10 / 2027-04 / 2027-10), and asserts summary/output identity and dates (scope, feature/target month, row count, package id, periods). `runtime_check_real_r2.json` ok=true: combination_id ipcch-validity-h2h8h14-final-20261030, status candidate, all 8 identity/date assertions true per scope, q2..q5 raw scores bit-equal again. r1 files are kept unchanged. Evidence scope: historical feature probes for raw-score parity only — NOT current-month generation/scoring; real current-month features with target dummies are CP5.

Still required before CP2 acceptance (Supervisor): the complete handoff of fixed assets, initial histories and R45 acceptance records with exactly the 6,226 roster — in progress (`research_cloud/packages/ipcch_handoff_inputs.py`, build r2 running; r1 stopped on my lat/lon invariance check: the raw panel repeats one coordinate per area up to float formatting, max spread 5e-11; check now tolerance 1e-9, latest-month value used).
