# Remaining historical package exploration

Read-only scouts, 2026-10-16; these are implementation pointers, not package acceptance. No model execution/cloud call/source mutation. `N=/home/swl007007/projects/food-crisis-research`, `A=/home/swl007007/.local/share/ipcch-mlflow/artifacts`.

## Eight window-probe reused comparators

Exact registered identities and underlying units are already in `N/scratch/p1/registry_ledger.json` / `ledger_resolutions.json` and task `research/ledger/`. All eight are version 1, parent run e9cfa99f94dd4a67b0e3b6ed511708ad. `IPCCHMLflow/naming.py:216-218` maps base_global to pooled/36_month/reused_comparator, base_local to regional_ungated/36_month/reused_comparator. Preserve those identities rather than replacing them with P6 names.

Important finding: retained P6 components are not necessarily in an existing P6 inference package. Metadata comparison against all current geoxgb package manifests:

| Horizon | Comparator global units (all in pooled package) | Comparator local units including globals | Covered by existing gated package | Local units absent from all existing geoxgb packages |
|---|---:|---:|---:|---:|
| 1 | 3 | 27 | 3 | 24 |
| 3 | 3 | 24 | 4 | 20 |
| 6 | 3 | 19 | 4 | 15 |
| 12 | 2 | 20 | 2 | 18 |

All listed comparator unit record.json paths exist in the original Dropbox P6 root, but not the native source clone. This is record existence only, not a new booster-byte/hash check. **77 local units still need packaging**, not a declaration of missing weights. Frozen G/L recipes: H1 G1/L2, H3 G3/L2, H6 G4/L2, H12 G2/L2.

Authoritative original script: `A/1/e9cfa99f94dd4a67b0e3b6ed511708ad/artifacts/source/run_probe.py`. It fixes P6 BASE at line 13, validates saved identities/fit keys/Y/params/rounds/booster hashes at 49-65, reuses pool predictions at 131-141, and routes local_fit_ok rows through gate-pair local_routed raw predictions at 148-176 without final gate adoption. Thus `partitioned_gated` is not the comparator's routing contract.

Selected months in the same run's source/plan.json: H1/H3/H6 September 2023/2024/2025; H12 September 2024 and January 2025. Labels originate from P6 prepared keys (run_probe.py:103-104,127,133,172); evaluation is an exploratory selected-date comparison, not whole P6 deployment. Existing P6 packages' reference samples have broader date/component scope. Reuse low-level loader/components, but preserve comparator-specific selected keys, ungated fallback and references. A whole-package alias cannot establish these eight versions' replay.

Scout: `/root/window_comparator_mapping`. No numerical replay or booster hashing.

## Population-history pop-v1

`S=N/sources/Food_Crisis_Cluster/IPCCHPopulationHistoryExperiment`, `R=S/runs/pop-v1`.

Scout joined `N/scratch/p1/popv1_models.json` with R/main/model_identity/*.json: all **660** retained file basenames map one-to-one, no recorded hash mismatch or omitted/extra file. There are **110 nonempty main folds × six arms**, horizon fold counts 32/30/27/21 for H1/3/6/12. Native R/main/models currently contains only 24 of the 660 files; use already inventoried original-root paths for the remainder and verify bytes. Native rich561_X.npy/baseline release are absent too.

- File contract: `main/models/{fold_id}__{arm}__{config_id}.{ubj|joblib}`, paired `main/model_identity/{fold_id}.json`, `main/folds/{fold_id}.{json,csv.gz}`, folds/calendar.csv and freeze.json. S/run_pipeline.py:647-650,1688-1708 writes exact model identity, fit-key digest, counts/parameters, bytes/SHA.
- Arms: binary_history_xgb uses original93 and binary class1 probability; rich_direct_xgb and fullpool_xgb use rich561 class1 probability; correction_xgb learns disagreement with persistence and maps raw score to raw or 1-raw depending on persistence; share_xgb outputs raw q3 and clipped crisis score; rich_rf uses rich561, saved imputation and class1 probability (run_pipeline.py:84-90,292-320,468-475). All six remain in scope even though share_xgb is primary.
- RF joblib contains only estimator. **Do not refit its imputer on download.** Per-fold model_identity top-level imputer contains fitted positional fill_values, columns, fitted_rows, max_plus strategy and multiplier 100.0 (example main/model_identity/mai_h01_2023-02.json:20-589; run_pipeline.py:576-604). Existing stage_replay_models re-fits the imputer from training data at 1871-1889, so it is not itself the portable inference entry.
- Preserve inputs/feature-schema.json and data/feature_schema.csv exact order. Original93 is first 93 columns; rich561 includes generated histories. prepare_data.py:181,203,540 and its IPCCHGeoRFExperiment import at 49 are reuse anchors.
- Preserve freeze.json, folds/calendar.csv, data/keys.csv.gz. Thresholds support literal +Infinity/-Infinity and use strict `score > t_b` (run_pipeline.py:978-1000). report_results.build_scored_table:110-189 joins row_index to keys, uses arm/horizon t0/t1 for E_history, and fullpool_xgb with 0.5 for E_no_history. Persistence is a seventh, weightless comparison stream.
- Saved main/folds/*.csv.gz fields: fold_id,arm,config_id,row_index,support,raw_score,crisis_score,route. reports/main_predictions.csv.gz adds exact area/month/horizon, truths, history/cohort, decision and threshold. These supply original reference outputs; scout read headers only.
- Development has search/selection evidence, not an additional saved weight collection. The 36 parameter-readback fits were not persisted as models (run_pipeline.py:1819-1827). Keep diagnostic evidence and describe the true retained main fold/arm identities rather than inventing old registry versions for each estimator.
- Original manifest records Windows Python 3.12.10, numpy 2.2.6, pandas 2.2.3, sklearn 1.6.1, xgboost 3.0.0, scipy 1.15.2. Freeze and later persistence code hashes differ; current native run_pipeline.py matches neither recorded hash. Preserve both historical records and locate original source if possible; do not attribute current code to original fitting. The original imputer values and weights are already recorded.

Scout: `/root/population_package_mechanics`. Did not deserialize UBJ/joblib, open large matrices/full prediction tables or hydrate Dropbox. Historical replay JSONs are prior evidence, not newly verified Linux acceptance.
