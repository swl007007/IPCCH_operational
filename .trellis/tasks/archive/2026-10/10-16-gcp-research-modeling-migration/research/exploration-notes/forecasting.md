# P1 forecasting inference-package contract (read-only research, 2026-10-16, time-boxed 8 min)

Sources: native clone sources/IPCCH @3b04fd09; plans at ~/.local/share/ipcch-mlflow/artifacts/3/<run>/artifacts/manifests/plan.json
(identical copies in ~/.local/share/ipcch-mlflow/ipcch-forecasting/plans/<source_key>.json). Not opened: /mnt/c.

## Plan shape
plan.json keys: config, counts, cross_checks, datasets, excluded, families, files, fingerprint, importer, source_key, versions(dict keyed version_key), views.
Version: arm, family, lead, registered_model, logged_model, training_dataset, n_inputs, boosters_{new,reused,alias,total}, members[].
Member: {bundle_source, bytes, job, kind, path, role, sha256, target}; launch members lack job/target.

## Family groups (member roles of first version)
A. Compact/origin-safe batch families (compact_global/somalia_original, *_2026_extension, origin_safe_climate_idp_v1,
   origin_safe_weather_oracle_v1 [ORACLE realized-future weather]): per batch year: 4 boosters
   model_phase{2,3,4,5}_worse.ubj (cumulative share targets, forecasting_weight_decay.py:28,136), fit_keys.csv.gz,
   batch_record.json, predictions.csv; once per version: run_metadata.json (role run_metadata_feature_order).
   Extensions reuse 16 boosters from original + 4 new (2026 batch).
B. Launch (compact_global_launch, compact_somalia_launch): 4 boosters, feature_schema.json, artifact_record.json,
   fit_keys/fit_targets/fit_weights.csv.gz, inference_features.csv.gz, predictions_raw.csv (role launch_predictions).
C. Somalia oracle v1/v2_q3/v3_validity/v4_calibrated_d: per origin boosters q2,q3(_direct|_residual_delta),q4,q5
   (v4: 110 boosters/version), feature_schema.json, final_fit_ledger.csv.gz (fit_keys), model_inventory.csv,
   fit_status, selection (candidate_scores.csv); v2-v4 add calibration (fits/calibration_mappings.csv) + calibration_inputs.
   v1 has NO calibration. No saved predictions member in group C.

## Inference composition
- A/B: booster = xgb.Booster().load_model(.ubj); feature names from booster.feature_names must equal run schema
  (compact_launch.py:1012-1016, 1133-1134). 4 independent regressions on cumulative targets; clip to [0,1] seen
  compact_launch.py:481. Batch-year model chosen by target year (fit_keys define training rows; not needed for predict).
- Legacy launch predict-only path: launch_nowcasting.load_model_artifacts (launch_nowcasting.py:1355-1372) expects
  feature_columns.json + <target>_model.json (XGBRegressor JSON) -- NOT the .ubj layout in plans; predict_april
  (1375+) reindexes X to feature order with fill_value=0. Contract mismatch -> need a new .ubj loader.
- C: FittedRegressor (somalia_oracle/modeling.py:80-113) is xgboost OR constant; constant models are saved as .json
  {"kind":"constant","value":...} (pipeline.py:299-305) -- plans contain 0 such .json members (gap if any fit was constant;
  check model_inventory.csv kind column). q3 residual = baseline(frame)+raw delta (q3opt.py:239-250, baseline at :200);
  calibration none/shift/isotonic then clip [0,1] (q3opt.py:28,65-121), isotonic x/y thresholds serialized as JSON in
  calibration_mappings.csv (q3opt.py:97-99). Selection (candidate_scores) picks candidate per job.

## Non-member dependencies
- Feature construction code (src/ipcch/*, somalia_oracle/monthly_features.py, history.py) and model-ready input CSVs
  (Analysis/1.Source Data/assembled_IPCCH/model_ready/... per codebook) are NOT members.
- source.tar (MLflow run artifact) holds only cited reports/codebooks/logs (e.g. model_run_codebook CSV), 0 .ubj.
- Feature order: run_metadata.json (A/B) / feature_schema.json (B/C) are members.

## Availability gaps
- ALL plan member paths (results/...) are absent from the native clone (0/~4.5k exist) and absent from source.tar;
  staging/<key>/source.tar also has 0 .ubj. Boosters live only on the Windows/Dropbox results tree (or MLflow logged
  models -- not verified in time box).
- xgboost is NOT in pyproject.toml or uv.lock (uv.lock pins numpy 2.0.2/2.2.6/2.3.5 per python marker, pandas,
  scikit-learn, shap; requires-python >=3.9). Runtime xgboost version must be recovered from booster/record metadata.
- predictions.csv column contract not verified (files unavailable locally).
