# Acceptance ledger reconciliation (written 2026-10-16 02:43:09 EDT by `date`)

Code: native branch `gcp-research-migration` at `a217127` (`research_cloud/inventory/{registry_ledger,fews_catalog,run_files}.py`, with tests). The snapshot is r1 (`mlflow.db` sha256 `54aa6898…`). All counts below are reproducible from the files in this directory.

## 1. Registered versions: `registry_ledger.json`

- **Construction:** driven from every `model_versions` row with a LEFT JOIN to logged models, so an unresolved source would be kept as `unresolved_registry_identity` (none occur). The (name, version) key set **equals the snapshot exactly** (asserted; a tested failure mode). That gives 242 rows, including MLP seeds v1/v2/v3, the diagnostic local arms and the oracle/realized-future-weather forecasting arms.
- **Each row carries:** logged-model id, source and parent run, identity tags (logged-model tags plus the run-level `zz_prov.arm_kind` / `zz_prov.original_arm`), member scope and statuses, and the package and replay reference.
  - Forecasting rows use their own plan-version members.
  - Dashboard rows use the family member manifest, because members are shared across a family's versions.

| Class | Versions |
|---|---|
| packaged_replay_passed | 20 (GeoXGB P6 8, yearly 12) |
| weights_retained_package_pending | 150 (AlphaEarth 16, forecasting 126, window-probe comparators 8) |
| missing_weights_tracking_only | 72 (MLP 48, window-probe own fits 8, climate swap 8, maps-to-2024 8) |
| needs_resolution / unresolved | 0 |

- **Missing-weight versions:** every member of the family's own manifest is verified not-found under all declared roots. The weights each version fitted are a subset of those members.
- **Window-probe reused comparators** (8 versions, `zz_prov.arm_kind=reused_comparator`, original arms `base_global` / `base_local`): resolved in `ledger_resolutions.json`.
  - `runs:/e9cfa99f…/source/run_probe.py` loads P6 `global_identity` units via `check_saved(BASE/models/<gid>)` and asserts its base predictions equal P6's saved `pool_` raw values. `base_local` uses P6 `local_identity` units from the P6 gate pairs.
  - The underlying units per lead (`window_probe_comparator_units.json`) are H1 3 global + 24 local, H3 3 + 21, H6 3 + 16, H12 2 + 18. All are **verified** retained P6 members.
  - These versions link to the P6 units and do not duplicate them. Their packages are pending.
  - The probe's own new fits (`exp_*`) remain missing.

## 2. Forecasting constant-model dependencies

All four `somalia_oracle/*/models/model_inventory.csv` files (classified local before reading) list only `kind=xgboost` `.ubj` models:

| Run | Rows | Unique paths |
|---|---|---|
| v1 | 320 | 300 (rows reuse boosters across arms) |
| v2_q3 | 400 | 400 |
| v3_validity | 524 | 524 |
| v4_calibrated_d | 626 | 626 |

Every listed path is a plan member, so no constant-JSON dependency exists outside the UBJ members.

## 3. Identified unregistered IPCCH run: `IPCCHPopulationHistoryExperiment/runs/pop-v1`

- The run records 660 fitted models (`stage_main`: 110 folds × 6 model families). `stage_replay-models` reports `all_checked_reproduce=true`, 660 checked, 0 absent.
- git tracks only 24 model files (`main/models`), with none ever deleted. The Dropbox working tree holds all **660** (550 `.ubj`, 110 `.joblib` random forests): all local, 556.6 MB, freshly hashed (`popv1_models.json`, complete, no walk errors).
- It is in scope as an identified unregistered IPCCH research run with retained weights. Version granularity (proposed: model family × horizon, grouping its fold-origin models) and packaging are pending. It needs a RandomForest/joblib loader as well as XGBoost.

## 4. FEWS NET runs within the bounded root `/mnt/c/Users/swl00/geoxgb_runs`: `fews_run_catalog.json`

- **Scope:** 27 run directories hold fitted weights: 34,085 `.ubj` files, 59.88 GB. Counts come from the deduplicated exact-hash cache, which is `.ubj`-only and therefore provisional for other encodings. 0 walk errors.
- **Labels** (provenance and completeness only; no run is excluded):

| Label | Runs |
|---|---|
| completed_frozen_actual | `scen-b43ef6a-v1` |
| candidate | `confirm-onset-v1` |
| development | `geoxgb-v1-20261001` |
| diagnostic | 17 (`geoxgb-d26` … `geoxgb-d52`) |
| replay_evidence | 3 |
| aborted | `scen-b43ef6a-v1.failed_stage1` |
| test_fixture | `minirun-1`, `minirun-2`, `smoke-2` |

- **Treatment (proportionate):** each run is one research-run record. Its immutable weight artifacts (including stage-1 candidate checkpoints) are grouped under the original run, byte-preserved with their hash manifest. They are not split into a separate registered version per candidate booster.
- **Replay:** inference packages and replay apply only where the run defines a servable model and saved reference predictions exist. Runs without saved predictions stay explicitly "no reference sample"; no references are generated and nothing is retrained.
- **`scen-b43ef6a-v1`:** stays `retained_weights_missing_dependencies` (18 local boosters missing; see `../fews/missing-local-boosters-receipt.md`). User disposition is pending.

## Open items carried forward

- Packages: AlphaEarth (16); forecasting (126); window-probe comparators (8, linked to P6 units); pop-v1; FEWS NET servable runs.
- FEWS NET run-level preservation manifests and the GCS layout, pending G7/G9 and the spend gate.
- User dispositions pending: FEWS NET 18 missing boosters, and the current-month actual spend figure.
