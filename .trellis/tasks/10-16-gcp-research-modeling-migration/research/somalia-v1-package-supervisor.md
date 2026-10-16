# Somalia v1 retained-package source mapping

Read-only bounded scout, 2026-10-16; supervisor directly checked historical modeling source at `f576e69023f3651f6fd4182087ed46f75d91ac2d`. These are implementation anchors, not a replay/hash pass. No model was loaded or trained.

Paths:
- SRC: `/home/swl007007/projects/food-crisis-research/sources/IPCCH`
- RUN: `/mnt/c/users/swl00/ifpri dropbox/weilun shi/google fund/analysis/2.source_code/step5_geo_rf_trial/IPCCH/results/experiments/somalia_oracle/v1`
- PLAN: `/home/swl007007/.local/share/ipcch-mlflow/ipcch-forecasting/plans/somalia_oracle_v1.json`
- Existing adapter: native control-plane `research_cloud/packages/somalia.py`; registered ledger: task `research/ledger/registry_ledger.json`.

## Historical identity and composition

- RUN manifest records source `f576e69023f3651f6fd4182087ed46f75d91ac2d`, only task.json dirty, Python3.12.3/XGBoost3.2.0/NumPy2.4.4/pandas3.0.3/sklearn1.8.0. PLAN fingerprint `21a0b32c58ab344a4286c6db25e28612fed8f8691cde9e2e1bea783dea67e548`.
- Exactly 15 registered version-1 identities, source key `somalia_oracle_v1`, family `somalia_oracle_information`. Version key template `somalia_oracle_information/{arm}/{HH}@somalia_oracle_v1`.
- Arms: `existing_predictors` A, `seasonal_climate` B, `weather_oracle` C, `weather_oracle_with_share_history` D. A/B/D each H0/3/6/12; C H3/6/12 only. H0 C is a view alias of B, not a separate registry version (`pipeline.py:323-364`).
- Each registered version has 5 jobs × four targets q2/q3/q4/q5 =20 UBJ weights; 300 unique weights total. Inventory320 rows includes H0 C aliases, not additional fitted components. PLAN members bind job/target/path/hash/bytes.
- `modeling.py` at historical commit:102-110 calls four regressors and column-stacks results. No across-job/arm/seed averaging. Seed42 is training provenance, and decay weights are fit sample weights only.

## Inputs, references and decoding

- Runner `run_somalia_oracle_experiment.py:64-71` saves `features/feature_matrix_hHH.csv.gz` with keys area_id,target_ord and full D schema. Select each arm's exact ordered schema from `feature_schema.json[hHH_A|B|C|D]`.
- Historical modeling:167 converts features to float32; :238-245 predicts directly. No inference imputer/scaler/calibration/residual baseline/clipping/monotonic repair.
- `predictions/predictions.csv.gz` contains area_id,target_ord,origin_ord,job_id,arm,selected_candidate,q2_pred,q3_pred,q4_pred,q5_pred,phase_pred,horizon,test_year,target_month.
- Historical modeling:55-66 rejects nonfinite cumulative output and decodes unrounded q5→q2 with >=0.2, default phase1. The crisis decision is not reducible to q3>=0.2 when cumulative outputs cross. Supervisor read this exact source.
- Five target months per version: 2025-04 (904), 2025-07 (64), 2025-09 (4), 2025-10 (904), 2026-04 (904), total2,780 keys. Job routing uses target month/horizon with origin=target-horizon; exact job IDs in ledgers/jobs.csv.
- Do not filter package/reference availability to primary evaluation rows. H3/H6 September2025 and April2026 jobs have primary=0 but saved predictions and retained components. Need reference coverage for all five stems/four targets. `pipeline.py:284-293` predicts valid_score keys; :392-419 applies evaluation cohorts later.
- RUN manifest records prediction SHA `124a701a83954df257a6413aa89487f9442a0212bb42935aa318a6a79dca223f` and four matrix hashes (:146-149,:161-164,:176-179,:191-194). These dependencies are absent from PLAN per-version members; verify their separate original manifest binding before package use. Recorded hashes were not fresh-rehashed by the scout.
- Actual schema determines oracle status: D inherits C weather offsets 1..min(H,6); H0 D has no future weather. Retain revised-vintage limitations.

## Reuse boundaries

Existing somalia.py has feature/oracle/locality/hash helpers and predict_target, but v2/v3/v4 build/entry expect calibration/residual/q3_final. V1 needs original q2-q5 direct-output handling and D mapping, not their q3 calibration path. Existing build CLI version/registry dispatch and common path/hash/reference helpers remain reusable. Keep source identity and original runtime separate from tested Linux loader. Weight bytes, full saved inputs and numerical replay remain pending.
