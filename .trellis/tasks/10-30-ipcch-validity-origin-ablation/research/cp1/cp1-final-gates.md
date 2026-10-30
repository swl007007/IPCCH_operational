# CP1 final no-fit gates — receipt

Code: worktree commit 7023d10 (pooled d2c07d7d…, dataset_input 2b74098a…, features eace18fd…); test-only commit 868db9f on top.
Recipes: `staging/ipcch-origin-ablation-20261030/candidate/final-r2/formal-origin-hXX.json` (final pins from the measured provisional gates; r2 differs from r1 only in the metadata `provenance.input_manifest` and `training_window` texts, which were inherited false statements: baseline_predictions is now the CH-final run's predictions; copies are not fitted). Local manifests = the CH local manifests with baseline_predictions -> the retained CH-final predictions.
Gates: `check/gates-r2/final-hXX` (r2 recipes) and `check/gates/final-hXX` (r1 recipes), both on 7023d10 code; all rc 0.

| H | passed | differing | in-job A2 score pairing (matched rows) | contexts: original-only fit rows |
|---|---|---|---|---|
| H0 | True | [] | True (70972) | h00_main_2023 19169 (removed 55741), h00_main_2024 24197 (removed 69931), h00_main_2025 28551 (removed 82756), h00_supp_2026 37759 (removed 91391) |
| H6 | True | [] | True (61042) | h06_main_2023 21282 (removed 57059), h06_main_2024 22478 (removed 64301), h06_main_2025 27134 (removed 77220), h06_supp_2026 34004 (removed 87890) |
| H12 | True | [] | True (52027) | h12_main_2024 21282 (removed 57059), h12_main_2025 25960 (removed 70978), h12_supp_2026 30784 (removed 83606) |

Independent verifier `verify-final-r2.json`: passed=True — retained CH-final artifacts reproduce the CH pins; expected original-only memberships/history-overlays/fit-keys digests derived from the retained job outputs equal the gate; A2 prepared score rows equal the retained predictions CSV with 0 key/truth/kind/family/country/period mismatches; gate score pairing passed.
Digests changed by fit membership (all horizons): fit_keys, history_overlays, memberships, schedule; all other 9 equal the CH-final pins.
Checksums: SHA256SUMS-cp1.
