# AlphaEarth supervised partition: minimal inference-package contract (read-only research, 2026-10-16)

Code: sources/Food_Crisis_Cluster/IPCCHAlphaEarthExperiment @6c1ebf72 (pkg `ipcch_alphaearth/`).
Run root R=/home/swl007007/ipcch-alphaearth-runs/p1-formal-d30-20261014. MLflow family run 9939ac69809949e9923821fa692a7b2a (artifacts under ~/.local/share/ipcch-mlflow/artifacts/1/9939ac.../artifacts).

## 0. Registered versions (16, all v1, seed 42; mlflow.db read-only)
Name pattern `IPCCH AlphaEarth supervised partition | <arm> | <H>-month`, H in {1,3,6,12}. Tag `zz_prov.projection_key` = `alphaearth_partition/p1-formal-d30-20261014/H<h>/<code>/seed42`:
- pooled -> B0 (compact296, n_features 296)
- pooled_plus_alphaearth -> B1 (compact296+ae128, 424)
- shared_calibration -> B2 (B1 raw + shared ridge correction)
- regional_calibration -> G (B2 + map deviations; at every lead no map selected, G_route=b2_reuse, outputs == B2)
Tags: `inference`='not loadable (external descriptor)', `zz_prov.model_bundle_uri`='' (weights not uploaded), `zz_prov.member_manifest_uri`=runs:/9939.../manifests/models.tar.members.json, `card.feature_list`=runs:/9939.../source/prepared/feature_order_296.csv.gz#name. No `zz_original_arm` tag set.

## 1. Model store layout
backbone.py:1-10 docstring + :108-109 `_dir`: `models/<digest[:2]>/<digest>/{q2,q3,q4,q5}.ubj + record.json`, digest = sha256 of canonical fit identity (backbone.py:63-84: arm, horizon, block_id, role, fit_origin, fit rows/keys/X/y/weights digests, features sha, params, env, source).
No index file in models/. Mapping (lead, arm, block/fit origin) -> digest lives in `R/{develop,predict}/request_ledger.csv.gz` (cols identity, purpose, action, seconds, arm, horizon, block_id, role, fit_origin, n_rows), and per-row in predictions (`B0_identity`, `B1_identity`) and contexts JSON `block`.
Counts: 61 identities x 5 files = 305 members (manifest lists only `models/**`). develop ledger 27 rows (per H: B0 2 dev, B1 5 [4 for H12] historical providers); predict ledger 34 rows (per H: B0 4 [3 for H12], B1 5 [4]: bridge? + main 2023/24/25 + supplement 2026).
Block ids e.g. `h06_main_2023` (fit_origin 2023-01, targets 2023-07..12), `h06_supplement_2026`. B2/G have no boosters: they are coefficients in `R/predict/contexts_hXX.json` (list of contexts; keys context, block, fit_origin, pool_rows, correction{transform{p_mean,p_sd,p_active,z_mean,z_sd,z_active,flag_active...}, beta_b2, b2_objective, g_kind, beta_g, leaf_ids, u, g_objective, unsupported_leaves, slots}, support, map_frozen). Maps: `R/maps/final_map_hXX.json` + MAP_FREEZE.json.

## 2. Non-member dependencies (all outside models.tar members)
| dependency | run root | MLflow artifact |
|---|---|---|
| feature order 296 | prepared/feature_order_296.csv.gz (col `name`; runinputs.py:34) | runs:/9939.../source/prepared/feature_order_296.csv.gz |
| 424 order | order296 + descriptors.ae_names(contract) (runinputs.py:38,47; descriptors.py:21) | via source_code/config/experiment-contract.json |
| AE 128 descriptor table | descriptors/descriptor_table.csv.gz (+COMPLETE.json sha) | source/descriptors/descriptor_table.csv.gz |
| row descriptor routing | descriptors.row_descriptors (descriptors.py:78) by admin_code | code |
| shared calibration (B2) + G coeffs | predict/contexts_hXX.json | source/predict/contexts_hXX.json |
| maps | maps/final_map_hXX.json | source/maps/ |
| projection/decoding | projection.py:75 project, :83 decode, :95 project_and_decode | code |
| correction apply | correction.py:298 correct(P,V,coef); Z = X296[:, core_idx] (pipeline.py:42-48) | code |
| X296 matrices | prepared/X296_hXX.npy (101 MB each) | EXCLUDED (manifests/excluded.json), as are sources/* raw panels |
| keys | prepared/keys_hXX.csv.gz | source/prepared/keys_hXX.csv.gz |
| contract/runtime lock | source_code config | runs:/9939.../source_code/IPCCHAlphaEarthExperiment/config |

## 3. Required units per registered version
Deployable blocks per H: main years (H1/3/6: 2023,2024,2025; H12: 2024,2025) + supplement 2026 => k_H = 4 (H1,3,6) / 3 (H12). E.g. H6 predict ledger: B0+B1 at h06_main_2023 (fit_origin ord 24276), _2024, _2025, h06_supp_2026, plus B1 h06_bridge_2023.
- B0 version: k_H quartets x 5 files (4 ubj + record) = 20 files (H12: 15) + feature_order_296.
- B1 version: k_H B1 quartets = 20 (15) files + feature_order_296 + descriptor_table (128 cols) + ae_names.
- B2 version: B1 units + contexts_hXX.json (transform, beta_b2 per block) + core_idx (3 X296 cols) + projection code.
- G version: B2 units + final_map_hXX.json + beta_g/leaf_ids; current outputs == B2 (G_route=b2_reuse).
Replay-from-scratch of B2/G coefficients (not plain inference) additionally needs all historical/bridge B1 providers (develop+predict ledgers; full 61 identities), X296_hXX.npy and keys.
Family total for whole-family replay: 61 dirs / 305 files (models.tar.members.json, each with sha256+bytes).

## 4. Reference prediction samples
`R/predict/predictions_hXX.csv.gz` (also runs:/9939.../source/predict/): keys row, admin_code, country_key, target_ord, target_month (YYYY-MM), origin_month, period (main/supplement), block_id, routable; truth phase_truth, q2..q5 (cumulative population shares 0-1), persistence_*; per arm {B0,B1,B2,G}_q{2..5}_raw (raw booster/corrected share), _q*_star (projected monotone share in [0,1]), _phase (int 1-5, q>=0.20 rule); G_route; B0_identity/B1_identity (store digests). Also develop/development_predictions_hXX.csv.gz and providers_all_hXX.csv.gz (row, target_ord, provider_block, provider_fit_origin, provider_identity, p_q2..p_q5). Inference input for a sample = X296_hXX.npy[row] (+ descriptor of admin_code for B1) -> needs the excluded npy or a rebuild via prepare.py.

## 5. Minimal loader + pins
- backbone.ModelStore(root, read_only=True) backbone.py:102-106; load_by_digest :177-178 -> _load :150-175 (checks record.json digest, booster sha256, resolved config, base_score, rounds).
- booster_from_raw :44-49; predict_booster :52-60 (DMatrix float64, missing=NaN); predict_quartet :181-182.
- pipeline.HorizonInputs.X(arm) pipeline.py:50-55 (B0=X296, B1=hstack[X296, D128]).
- runinputs.load_run_inputs runinputs.py:17-47; descriptors.row_descriptors descriptors.py:78.
- correction.correct correction.py:298; projection.project_and_decode projection.py:95.
- Runtime lock config/runtime-lock.json:3-14: Linux, Python 3.12.3, numpy 2.4.4, pandas 3.0.3, scikit-learn 1.8.0, xgboost 3.2.0, scipy 1.17.1 (geo pkgs only for prepare). n_jobs from contract backbone.fixed.

## 6. Gaps
1. Weights not in MLflow (model_bundle_uri empty; retention policy): only path+sha256 manifest; local WSL run folder is single copy.
2. No model-store index: (H, arm, block) -> digest only via request_ledger/predictions; registered versions do not name their digests or block set.
3. X296_hXX.npy and sources/* excluded from MLflow -> reference samples cannot be replayed from MLflow alone; need run folder or prepare rerun (needs 2+ GB raw panels).
4. B2/G versions have no artifact of their own: coefficients embedded in contexts JSON, applied by package code (correct/project); not a standalone model file.
5. Code provenance: 'uncommitted; frozen inventory 57ca2ef1 + amendment 385a8db8'; source_code/ artifact is the authoritative copy, not git HEAD 6c1ebf72 (not diffed here).
6. Tag `inference`='not loadable (external descriptor)'; `zz_original_arm` absent for this family.
7. Not verified (time box): sha256 of on-disk members vs manifest; bridge-block role in serving; exact core_idx names.
