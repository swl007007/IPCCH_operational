# GeoXGB reference (P6) + yearly refit: minimal inference-package contract

Read-only research, 2026-10-16. Code: native clone Food_Crisis_Cluster @ 6c1ebf72.
G = IPCCHGeoXGBExperiment/ipcch_geoxgb, YR = IPCCHYearlyGeoXGBExperiment/ipcch_yearly_xgb.
REF = ~/.local/share/ipcch-mlflow/artifacts/1/bdbafe393d694439a1c35ccec4d5816a/artifacts
YC  = ~/ipcch-legacy-source-preservation/yearly-formal-20261007

## Registry facts
- 8 versions per family (arm in {pooled, partitioned_gated} x lead {1,3,6,12}) for geoxgb_reference;
  12 for geoxgb_yearly_refit (adds regional_ungated). All version 1.
- Tags: family, arm, lead_months ("03"), seed=42, feature_set=rich561,
  zz_prov.projection_key (p6_geoxgb/p6-formal-20261004b/H3/geo/seed42;
  yearly_geoxgb/yearly-formal-20261007/H3/geo/seed42), zz_prov.family_run_id
  (ref bdbafe39...; yearly a6dc32cd...), zz_prov.model_bundle_uri runs:/<run>/models.tar,
  zz_prov.member_manifest_uri, inference='not loadable (external descriptor)'.
- Card text: "Weights stay in the family run's models.tar; files are not exclusive to this arm."

## 1. Mapping to model dirs
- No index file. Dir = models/<digest[:2]>/<digest>/ where digest = sha256(canonical(identity))
  (G/modelstore.py:56 identity_digest, :205-206 _dir; YR/modelstore.py:223-224).
- Identity -> digest is resolved by the saved per-row provider columns, which ARE the index:
  - ref: stage3/hXX/predictions.csv.gz `global_identity` (pooled) and `provider` (geo/routed)
    (G/stage3.py:37-39 PREDICTION_COLUMNS, :193, :261, :279).
  - yearly: predict/hXX/predictions.csv.gz `pool_provider`, `local_provider`, route.
  - Ledgers: stage3/model_requests.jsonl (ref, 3926 lines: H, fold, fitting_origin, purpose,
    use=current|gate, identity_sha256, booster_sha256) and YC/predict/model_requests.jsonl
    (747 lines: H, block, fit_origin, role, use, identity_sha256).
- Unit files: ref = q2.ubj q3.ubj q4.ubj q5.ubj record.json (5 files; 6125 members = 1225 dirs).
  yearly = same + fit_rows.npy, fit_keys.npy (7 files; 181 dirs in YC/models).
  record.json holds identity, booster_sha256, fit_records (base_score, resolved_config,
  parent digests for local). No gate or calibrator file in a unit.

## 2. Non-member dependencies
Inference = route row to region, pick pooled or regional quartet, predict q2..q5, monotone projection,
decode phase. No learned calibrator: projection is deterministic PAVA isotonic (G/projection.py:57,71,79,91;
YR/projection.py:59,73,81,93). The gate is NOT stored as a model; it is a decision logged per row/fold.
- Feature order: prepared/feature_order.csv (REF/source/prepared, present; YC/inputs/run/prepared, present).
  config/feature-schema.json in source_code.
- Region routing: stage1/frozen_map_hXX.csv + frozen_hXX.json (+ stage1-summary.json, hXX/selection.json;
  checked by G/predict.py:26-70 load_frozen). Present in REF/source/stage1 and YC/inputs/run/stage1.
- Gate outcomes: stage3/hXX/gate_decisions.jsonl (ref) / predict/hXX/gate_decisions.jsonl (yearly), plus the
  per-row `route` column. Present in both.
- Preprocessing: none at predict time beyond check_X (float64, 2-D, no inf, NaN kept; G/quartet.py:49).
  Features must already be rich561 values; prepared/X_rich561_hXX.npy + keys_hXX.csv.gz.
- NOT in members list: everything above (members list is models/ only). X_rich561_hXX.npy is EXCLUDED from
  the ref MLflow run (manifests/excluded.json, ~192 MB each, Dropbox source path) but IS present in
  YC/inputs/run/prepared (sha matches staging-manifest.json).
- The ref models.tar itself is not in the local artifacts dir (only manifests/models.tar.members.json and
  models.tar.tar.json); bytes must come from the tar store / Dropbox run root.
- YC top level: inputs/{run/{prepared,stage1,stage3}, source/IPCCHGeoXGBExperiment/config, staging-manifest.json},
  models/ (181 dirs), predict/{h01,h03,h06,h12, model_requests.jsonl, predict-summary.json}, preflight/preflight.json,
  replay/{predict,replay.json,report}, report/. All dependencies present.

## 3. Units per version
- ref pooled H: one global quartet per fold (origin month) = n_folds(H). H03: 34.
- ref partitioned_gated H: globals + distinct local providers actually routed = |distinct `provider`|. H03: 47 (34+13).
- yearly pooled H: one global per annual block = n_blocks(H). H03: 4.
- yearly partitioned_gated / regional_ungated H: 4 globals + local providers (H03: 28 distinct local_provider values;
  gated uses only rows with route=='local'; ungated uses local wherever local_eligible).
- Local units are continuations of the global booster; record.json binds the parent digest but the local .ubj
  is self-contained for prediction (full tree set).
- All referenced digests for H03 exist (0 missing) in both stores.

## 4. Reference predictions
- ref: REF/source/stage3/hXX/predictions.csv.gz. Keys admin_code, target_month, target_ord, horizon_months,
  origin_ord, fold_id, period, region, route, provider, global_identity. Pred: geo_q{2..5}_{raw,star},
  pool_q{2..5}_{raw,star}, geo_phase, pool_phase (+ truth, persistence). One file covers both arms:
  pooled -> pool_* via global_identity; partitioned_gated -> geo_* via provider. Version-identifiable via (H, arm).
- yearly: YC/predict/hXX/predictions.csv.gz (+ replay/predict copy). Adds block_id, annual_anchor_ord,
  fit_origin_ord, pool_provider, local_provider, local_* columns. pooled->pool_*, regional_ungated->local_*,
  partitioned_gated->geo_*.

## 5. Minimal loader (Linux-capable, numerics only)
from_raw G/quartet.py:74 (YR :111); check_X :49 (YR :60); dmatrix :58 (YR :76); predict_scalar :115 (YR :152);
Quartet.predict_raw :225 (YR :266); stage3.predict G/stage3.py:138; projection.project_and_decode
G/projection.py:91. Integrity: ModelStore._load G/modelstore.py:212 (sha256 vs record.booster_sha256).
Deps: xgboost 3.0.0, numpy 2.2.6, pandas 2.2.3. config/runtime-lock.json says Windows-only Python 3.12.10
for "numerical artifacts"; YR/runtime.py:35-38 probe flags platform != Windows. A Linux replay is a
deviation that needs tolerance-based parity vs saved *_raw columns, not bitwise claims.

## 6. retained_weights_missing_dependencies triggers
- models.tar bytes absent (ref: not under local artifacts); features X_rich561 absent (ref MLflow excluded);
  frozen maps/gate logs absent; provider digest without dir; record.json sha mismatch; xgboost != 3.0.0
  unable to load UBJ; no per-version member subset (members shared across arms).
