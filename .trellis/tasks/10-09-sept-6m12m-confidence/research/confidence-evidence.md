# Research: September h5 confidence method and evidence for September-origin 6m/12m

- **Query**: How each September h5 confidence column was computed (FEWSNET + IPCCH); which 6m/12m model packages and evidence exist; where/why October left 0/6/12 diagnostics blank; whether the same method can be applied to 6m/12m without retraining.
- **Scope**: internal (repo + external Dropbox research/legacy dirs), read-only
- **Date**: 2026-10-09

Abbreviations used below:
- `B` = September bundle extracted (small files only) to `/tmp/sept_bundle` from `september_manual/webapp_model_bundle.tar.gz` (240,305,152 bytes, 165 members).
- `CP` = `cloud_pipeline/`
- `OCT` = `.trellis/tasks/archive/2026-10/10-07-october-cloud-delivery/`
- `D` = `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data`
- `R` = `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/2.source_code/Step5_Geo_RF_trial/food_crisis_cluster`
- `L` = `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/legacy_archive/IPCCH_monthly_operational/2026-10-08-two-entry-handover`

---

## 1. Where the method lives now

| File | Description |
|---|---|
| `B/reports/country_confidence_v3_spec.md` (sha256 `8ea3c70e…beed6`, 27,644 B) | Approved v3 spec (copy of the 09-23 task design.md). Only inside the tarball. |
| `B/reports/country_confidence_v3_policy.json` | Machine-readable policy written by `prepare()` |
| `B/runtime/tools/revise_h5_country_v3.py` (447 lines) | The full v3 implementation actually run (prepare / fewsnet / ipcch / selfcheck) |
| `B/runtime/tools/revise_h5_confidence.py` (233 lines) | v2 step that produced `ipcch/polygon_training_errors.csv` + `reports/ipcch_training_predictions.csv` (Phase3+ replay) |
| `B/runtime/tools/run_h5_model_delivery.py` (266 lines) | h5 training (`train_ipcch` :89-136, `train_fewsnet` :48-86), scoring, export |
| `CP/tools/revise_h5_country_v3.py` (126 lines) | Stripped "shared country statistics" copy: keeps `confidence_flag`, `decode_cumulative_phase`, `weighted_country_errors`, `maximum_phase_uncertainty`, `append_country_v3`, `forecast_country_fields`; the h5 prepare/replay/evaluate wrappers are gone (docstring line 1: "manual September construction stays in the legacy archive"). |
| `CP/cloud/orchestrator/delivery_outputs.py` | Cloud re-implementation of v3 diagnostics fed by supplied evidence (`area_evidence` :249, `residual_evidence` :268, `maximum_phase_diagnostics` :291, `supported_diagnostics` :321, `scope_diagnostics` :502) |
| `september_manual/reports/ipcch_four_target_training_replay.csv` | Identical to `B/reports/…` (sha256 `e82e5227…5789`, 43,551 rows) |

Constants (`B/runtime/tools/revise_h5_country_v3.py:26-30`): `HIGH,MEDIUM = 1/10, 1/5` (exact `Fraction`), `PHASE_THRESHOLD=0.2`, `CRISIS_THRESHOLD=0.5`, `SEED=20260923`, `REPLICATES=10000`, `PERCENTILES=(2.5,97.5)`, `BASIS={"fewsnet":"h5_validation_error_proxy_stage3_2021_2024","ipcch":"training_resubstitution"}`, `WEIGHTING="population_weighted_mean_of_area_error_rates"`.

## 2. FEWSNET h5 confidence columns — exact computation

Code: `evaluate_fewsnet` `B/runtime/tools/revise_h5_country_v3.py:230-274`; spec §2/§3 lines 14-23, 49.

**Evidence source (NOT the delivered model):** `R/paper_reproducibility_package/stage3_results/georf_fs1/predictions_monthly.csv` (sha256 `8c60433a…a53b8`, identical copy in `B/reports/fewsnet_stage3_source/`). 62,189 rows, 5,713 polygons, 12 test months (Feb/Jun/Oct 2021–2024), columns `FEWSNET_admin_code,month_start,partition_id,y_true,y_pred_pooled,y_pred_partitioned,y_prob_pooled,y_prob_partitioned`. Run manifest (`georf_fs1/run_manifest.json`, sha `49de1c0d…`): rolling 36-month RF fits, `forecasting_scope=1`, `active_lag_months=4` ("features from t-4 used to predict t", `R/scripts/compare_partitioned_vs_pooled_rf_k40_nc4.py:1005`), partitions learned 2018-2020, data `FEWSNET_forecast_unadjusted_bm.csv`. User decision 2026-09-23 (spec :22, :49, :133): accept this as an "h5 validation-error proxy"; "Do not use the final model to regenerate historical predictions" (:49).

Per-row: `error = int(y_pred_partitioned != y_true)` (:240) — saved `.predict()` decisions (= prob > 0.5; 469 rows at exactly 0.5 are 0), not re-thresholded at the 0.43 package threshold.

| Column (`fewsnet/polygon_confidence.csv`, 5,718 rows) | Computation |
|---|---|
| `polygon_id, ISO3, population, population_reference_period, population_source` | From `inputs/fewsnet_identity_population.csv` (delivered snapshot; population = 2024-10 `raw_last_observed`) |
| `historical_sample_count`, `historical_error_count` | count / sum of `error` per polygon over the Stage3 rows (:245) |
| `polygon_error_rate` | error_count / sample_count (null for 5 polygons without history: 216, 2786, 4375, 4511, 5500) |
| `polygon_confidence` | `1 - polygon_error_rate` (:251) |
| `country_error_eligible` | rate notna & population notna & > 0 |
| `evidence_basis`, `evidence_period` | `h5_validation_error_proxy_stage3_2021_2024`, `2021-02..2024-10` |

| Column (`fewsnet/country_confidence.csv`, 22 rows) | Computation (`weighted_country_errors` :59-94) |
|---|---|
| `country_error_rate` | exact-rational `sum(P_a * k_a/n_a) / sum(P_a)` over areas with sample_count>0 and finite P>0 |
| `country_confidence_flag` | high ≤ 0.10, medium ≤ 0.20, low > 0.20 on unrounded exact value; null if no eligible areas |
| `country_error_basis/weighting/evidence_period/thresholds` | constants above |
| `…eligible/excluded/missing_evidence/missing_population/nonpositive_population_area_count`, `…sample_count`, `…mistake_count`, `…eligible_population_sum`, `…known_population_sum`, `…known_population_coverage`, `…population_field/vintage/source` | support accounting in the same function |
| `country_outcome_crisis`, `…_threshold` | `int(population-weighted probability_crisis >= 0.5)` from current forecast (:258-261); forecast-dependent, not evidence |

Inputs needed: Stage3 saved predictions (y_true + partitioned decision), polygon→ISO3 + population snapshot, current country `probability_crisis`. No model, no panel, no replay.
Result (Sept): 62,189 rows, 10,635 errors, flags high 11 / medium 4 / low 7 (`B/reports/country_confidence_v3_verification.json`).

## 3. IPCCH h5 confidence columns — exact computation

### 3a. h5 model and training keys
`train_ipcch` (`B/runtime/tools/run_h5_model_delivery.py:89-136`): XGBRegressor (200 trees, depth 6, lr .08, subsample .9, colsample .8, seed 42) per target `phase{2..5}_worse = sum(phase{i..5}_percent, min_count)`, labels shifted by HORIZON=5, `feature_period < 2026-04` and `target_period <= 2026-04`; NaN features filled with training medians (saved as `imputation_statistics`). Panel `inputs/ipcch_panel.csv` sha256 `6ab4e447…`, which is the WFP/ACLED-refreshed version of `IPCCH_2026_completed.csv` (`B/reports/input_refresh.json` → `inputs.ipcch.source_sha256 = ae696087…`, `output_sha256 = 6ab4e447…`). Keys saved: `B/reports/ipcch_training_keys.csv` (43,551 rows, sha `d52babfc…`; targets 2014-01..2026-04, features 2013-08..2025-11).

### 3b. Country Phase3+ error / flag (basis `training_resubstitution`)
1. v2 step `load_training` (`B/runtime/tools/revise_h5_confidence.py:149-193`): reload saved `phase3_worse` model, rebuild the exact 43,551 training rows from the panel (chunked read, `apply_feature_contract` median fill), `predicted_phase3plus = score >= .2`, `actual_phase3plus = (phase3+phase4+phase5 share) >= .2`, `error = predicted != actual` → `reports/ipcch_training_predictions.csv`; per polygon `training_sample_count`, `training_error_count`, `training_error_rate` → `ipcch/polygon_training_errors.csv` (6,227 rows; columns `polygon_id,ISO3,training_sample_count,training_error_count,training_error_rate`).
2. v3 `evaluate_ipcch` (`revise_h5_country_v3.py:326-348`): join to `polygon_predictions` population (`population_estimate`, `population_reference_period`, `population_imputation_method`), ISO3 via `inputs/ipcch_april_panel.csv` country → census ISO3; same `weighted_country_errors` (pop-weighted, exact rational, 10%/20% cutoffs). Evidence period = `2014-01..2026-04`.
Sept result: 43,526 eligible training rows, 5,419 mistakes; flags 27/14/12.

### 3c. Forecast-derived fields (no evidence needed)
- `country_overall_phase` (:350-355): decode population-weighted country raw cumulative scores with the ≥0.2 cascade (`decode_cumulative_phase` :52-56: active = score ≥ .2, propagate higher active boundaries down via reversed `maximum.accumulate`, return highest active phase 2..5 else 1; no clipping/normalising). `country_overall_phase_availability` = available / nonfinite_country_score; method string "population-weighted raw cumulative scores; >=0.2 cascade; highest active boundary".
- `country_maximum_phase` = max of polygon `overall_phase_pred` over the full roster incl. zero-population polygons (:356-357).

### 3d. The "cascade / complete-month bootstrap" block (maximum-phase uncertainty)
Columns: `country_maximum_phase_error_probability_proxy`, `…_ci_lower`, `…_ci_upper`, `country_maximum_phase_history_month_count`, `country_maximum_phase_uncertainty_status`, `country_maximum_phase_uncertainty_method` (= `training_residual_transfer_complete_month_bootstrap_proxy`). Spec §6 lines 91-103, §7 lines 109-115; code `replay_ipcch` :277-323 + `evaluate_ipcch` :358-391 + `maximum_phase_uncertainty` :97-118.
1. **Four-target training replay (no fitting)**: load all four saved h5 models, rebuild exact training rows, `residual[a,k,t] = actual_cumulative_share - predicted_score` for k=2..5 → `reports/ipcch_four_target_training_replay.csv` (43,551 rows; columns `polygon_id,feature_month,target_month,phase{2..5}_worse_{actual,predicted,residual},actual_overall_phase,predicted_overall_phase,ISO3`). Phase3 column asserted equal (float32) to the v2 saved predictions (:361-367).
2. **Complete months**: a (country, target_month) is complete only if replay rows cover every polygon in the delivered country roster (:369-372) → `reports/ipcch_country_month_coverage.csv` (773 groups, 184 complete).
3. **Scenario**: for each complete month, `simulated = decode_cumulative_phase(september_scores[roster] + residual_field[month])`; mismatch = `simulated.max() != forecast_max` (:376-388) → `reports/ipcch_maximum_phase_scenarios.csv` (184 rows).
4. **Point proxy** = mean mismatch over that country's complete months. **CI**: whole-month bootstrap, `Generator(PCG64(20260923))`, 10,000 replicates of size m, percentiles 2.5/97.5 `method="linear"`, countries consumed in ISO3 order (:97-118). Status priority: `no_complete_history` (m=0; all null), `single_month` (point only), `degenerate_empirical` (all scenarios identical), `supported`.
Sept: 17 supported, 17 degenerate, 9 single_month, 10 no_complete_history (AGO,CAF,ETH,HND,LSO,MOZ,SDN,SOM,SSD,TZA).

Inputs needed for IPCCH: saved four target models + full training panel (the one the model was trained on) + training keys + roster/ISO3 map + current polygon raw scores + population snapshot. No retraining.

## 4. Model packages for 6m / 12m

### 4a. IPCCH (`CP/bootstrap/models/ipcch/`)
- Package `launch_2026_04_production_safe`, created 2026-06-26, `training_cutoff 2026-04-01`, scopes 0/6/12, 128 features each, same `feature_columns.json` sha `800e26fd…` as h5 (`baseline_feature_columns_sha256`).
- Trainer: `/mnt/c/.../Google fund/Analysis/2.source_code/Step5_Geo_RF_trial/IPCCH/scripts/modeling/train_export_operational_launch_production_safe.py` (413 lines). `build_training_frame` :298-322 = labels with all 4 targets non-null, `feature_period = target - scope`, inner join, `feature_period < cutoff`. Same XGB params as h5 (:112-118, seed 42). Medians written to metadata (:187-190). Training source: `Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv` (= `D/assembled_IPCCH/raw/IPCCH_2026_completed.csv`, sha256 `ae696087…717673` re-hashed today; archived copy `L/Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv`, same size 1,782,567,753).
- `training_export_summary.json`: 0m 40,777 rows (targets 2014-01..2026-03); 6m 43,551 (features 2013-07..2025-10, targets 2014-01..2026-04); 12m 43,551 (features 2013-01..2025-04, targets 2014-01..2026-04).
- **Missing vs h5 package**: no `training` key list, no `source_panel_sha256`, no saved training predictions in metadata.
- **Verified today** (`research/verify_ipcch_6m12m_training_keys.py` → `.json`, pandas only, 59 s wall, 5.2 GB peak RSS for both panels): re-deriving the training frame from the `ae696087` raw panel reproduces the summary row counts/month ranges and **all 128 saved medians exactly (max abs diff 0.0) for 0m, 6m and 12m**. The 6m and 12m `(area_id, target_period)` key sets are **identical to the h5 key set**. The refreshed panel (`CP/bootstrap/assets/ipcch/history_panel.csv`, sha `6ab4e447…` = h5 panel) gives 3/3/2 median mismatches (max abs diff up to 32.5), so it is **not** the 6m/12m training panel.
- Implication: training resubstitution for scope_6m/12m can be reconstructed exactly with the saved models + the `ae696087` panel. Because target keys equal h5's, the complete-month coverage for 6m/12m should be the same as h5 (773 groups / 184 complete / same 10 no-history countries), given the same 6,227-polygon roster. This is inferred from key equality; it was not recomputed.
- Same panel as h5? Same label set and feature columns, but **different feature values for refreshed WFP/ACLED rows** (h5 trained on refreshed `6ab4e447`; 6m/12m on unrefreshed `ae696087`). Refresh changed WFP for 2025-01..2026-04 and ACLED for 2025-05..07 rows (`B/reports/input_refresh.json`).
- Horizon semantics: `scope_months` = target − feature month. September-origin 6m means feature month 2026-09 → target 2027-03, and 12m means 2026-09 → 2027-09 (the October run used O=2026-10, `fallback/october_2026/reports/delivery.json` `origin_month`). The h5 delivery used feature month 2026-04 → target 2026-09.

### 4b. FEWSNET (`CP/bootstrap/models/fewsnet/{0m,6m,12m}`)
- Suite `local-202604-57cb3b981198-510375f58cd8`, trained on `D/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.csv` (sha `510375f5…`, re-hashed today; the h5 package instead used refreshed `f8ad2157…`). Thresholds 0m .48, 6m .41, 12m .45 (h5 .43).
- Training (`B/runtime/fewsnet_partitioned_rf_pipeline/core/training.py:438-593`, docstring "Select a threshold on 30 labeled periods and refit on all 36"): temporary models fit on 2014-04..2023-06, scored on validation 2023-10..2026-02 (33,576 rows) **only to pick the threshold**, then final models are **refit on all 36 periods including validation**. Temporary models and validation predictions are not saved. `training_report.json` / `threshold_report.json` / archived `L/Outcome/fewsnet_partitioned_rf/reports/local-202604-…/training_threshold_report.json` contain aggregates only (F1/precision/recall/support, class counts).
- So no package contains per-polygon out-of-sample error records for any horizon. Replaying the final 6m/12m model on 2023-10..2026-02 would be in-sample, not validation.
- **External Stage3 analogues exist for other lags.** `R/paper_reproducibility_package/stage3_results/georf_fs2` (`forecasting_scope=2`, `active_lag_months=8`; predictions sha `54d1664c…`) and `georf_fs3` (`scope=3`, `lag=12`; sha `3f988101…`). Both have the same 62,189 keys, the same 5,713 polygons, the same 12 months 2021-02..2024-10 and identical `y_true` to fs1. Their partition map `cluster_mapping_k40_nc17_general_refined_contig3.csv` = sha `4723cae5…`, which is the delivered package partition map. Decisions equal `prob > 0.5` in both. Pooled error rates: fs1 0.1710, fs2 0.1782, fs3 0.2051. Exact-0.5 rows: 469 / 421 / 534. Agreement with fs1 decisions: fs2 93.7%, fs3 89.9%. No lag-6 run exists.

## 5. October decision to leave 0/6/12 diagnostics blank

- `OCT/prd.md:57`: "Do not copy h5 diagnostic numbers into 0/6/12 outputs. Historical evidence must be valid for the claimed model/horizon… September's FEWS fs1/4-month-lag evidence was an approved h5 proxy, not blanket approval for other horizons. IPCCH training-resubstitution diagnostics must remain labeled as such."
- `OCT/prd.md:59` (user-confirmed 2026-10-07): when suitable evidence is unavailable, deliver predictions with blank diagnostics + explicit unavailable reason; no zero errors, no category, no substituted h5 proxy; current-score country outcomes stay populated.
- `OCT/design.md:156`: FEWS evidence "must identify its real model family, horizon and evaluation method. Existing h5 fs1/4-month-lag proxy is not automatically allowed for 0/6/12. Do not create historical validation by applying the final model to its training rows and labeling it held-out."
- `OCT/design.md:157`: IPCCH Phase3+ errors remain training resubstitution "for the corresponding accepted model/horizon; retain the actual fitted keys… Missing exact replay lineage means unavailable, not h5 reuse." `:158` is the per-horizon max-phase procedure, restarting the seed for each horizon.
- `OCT/research/cp3-reuse-pointers.md:18`: "Never run old historical h5 wrappers to fabricate support for another horizon." `OCT/research/release-contracts.md:15`: fs1 approval applies to h5 only.
- `OCT/research/cp4-supervisor-review.md:15`: "Historical diagnostics lack supplied evidence, so estimates are blank with explicit reasons." `OCT/implement.md:129` and `OCT/supervision.md:64,74` say no training and no historical source archaeology were in scope. So the blanks reflect evidence that was never produced or supplied, not a finding that it is impossible.
- Result: `CP/bootstrap/baseline.json` `delivery.diagnostics` lists all 15 system/horizon/family entries as `unavailable/missing_evidence`. `fallback/october_2026/reports/{fewsnet,ipcch}_diagnostic_declarations.json` have `evidence_identity: null`, and `diagnostic_availability.csv` has 36,219 unavailable rows.
- **Cloud acceptance code hard-codes evidence semantics** (`CP/cloud/orchestrator/delivery_outputs.py:178-238`):
  - `EVIDENCE_BASIS = {"fewsnet": "package_validation_split", "ipcch": "training_resubstitution"}`.
  - The comment at :178-180 says a relabelled h5 fs1 proxy for 0/6/12 "is rejected".
  - FEWS evidence period must equal the package's recorded validation split `2023-10..2026-02` (:235-237).
  - IPCCH period must end at or before the package training cutoff `2026-04` (:232-234).
  - Evidence rows must carry `model_package_id,horizon_months,basis,period`. Area evidence also needs `polygon_id,sample_count,error_count`. Residual evidence also needs `polygon_id,target_month,phase{2..5}_worse_residual`.
  - Available evidence must be a hash-pinned ref (`uri`, `generation`, `sha256`; :468-494, `deliver.py:54-76`).

## 6. Assessment per system × horizon

### IPCCH 6m and IPCCH 12m: same method possible, no retraining
What would run is the replay from `replay_ipcch`/`load_training`, adapted to scope 6 or 12:
1. Load `CP/bootstrap/models/ipcch` with `load_scope_package(root, 6|12)`.
2. Rebuild training keys with the June rule (verified above). Read the `ae696087` raw panel with the same `usecols` and default float parsing, as in the trainer.
3. Apply `apply_feature_contract` (median fill). Predict the four targets. Compute actual cumulative shares and residuals.
4. Phase3+ ≥0.2 errors per polygon give `polygon_training_errors`. The population-weighted country error/flag follows with the period label `2014-01..2026-04`.
5. The residual fields plus the September-origin current scores give the max-phase proxy. Use complete months, seed 20260923 and 10,000 replicates, restarting for each horizon.

Environment: `~/.venvs/ipcch-h5-202609` (Python 3.12.3, xgboost 3.2.0, sklearn 1.8.0, numpy 2.4.2, pandas 3.0.0) matches the bundle requirements. Cost: reading the panel takes about 0.5–1 min and ~2.5–5 GB RSS (measured above). Prediction is 43,551×128 rows × 4 models per scope, a matter of seconds. The bootstrap is trivial. Budget is under 10 min per scope.

Gaps:
- There is no saved prediction file to cross-check the replay against (h5 had the v2 Phase3 CSV). The only consistency anchor is the exact median and key match.
- The bootstrap `history_panel.csv` must not be used. It is the refreshed h5 panel and is not the 6m/12m training data.
- The evidence is still training resubstitution, which is optimistic, and must keep that label.
- Country error counts depend only on evidence + population. Max-phase fields need the September-origin 6m/12m forecasts first.

### FEWSNET 6m and FEWSNET 12m: "same method" is only possible as a new proxy decision
- Literal September method (saved Stage3 historical series, 2021-02..2024-10, `1 - error rate`, population-weighted): the evidence needs no model run. Candidates:
  - fs2 (8-month lag) or fs1 (4-month lag) for 6m. No lag-6 run exists, and fs1 reproduces the h5 numbers exactly.
  - fs3 (12-month lag) for 12m. This is the same lag count as h12, but it is still a different model family: rolling 36-month GeoRF on `FEWSNET_forecast_unadjusted_bm.csv`, not the delivered package.
- The user must approve the mapping, as on 2026-09-23 for fs1→h5. The PRD/design already say the fs1 proxy does not carry over. The cloud validator would reject any Stage3 basis or period. Accepting it needs a code/contract change, in `EVIDENCE_BASIS` and the FEWS period rule.
- The cloud-accepted alternative (`package_validation_split`, 2023-10..2026-02) has no saved evidence. Producing it means refitting the temporary fit-only models (2014-04..2023-06) for 6m/12m and scoring validation rows. That is training, although not of the delivered models. A sanity check is to reproduce `threshold_report.json` (support 33,576, positives 10,357, F1 .672/.724). Scoring the delivered final models on historical rows is resubstitution and is barred (`OCT/design.md:156`, spec :49).
- Not possible without training: true out-of-sample error for the delivered FEWS 6m/12m models.

## Caveats / Not Found

- The XGBoost replay itself was **not** run in this research (system python lacks xgboost); only key and median reconstruction was verified.
- The September h5 FEWS proxy was approved specifically as "h5"; no approval exists for fs2/fs3.
- The June IPCCH trainer read the CSV with pandas default float parsing, while the h5 replay used `float_precision="round_trip"`. The medians matched exactly under default parsing, so use default parsing for the 6m/12m replay.
- `CP/tools/revise_h5_country_v3.py` no longer contains the replay or evaluate wrappers. The full versions exist only in the tarball (`B/runtime/tools/`).
- IPCCH 0m (40,777 keys, targets to 2026-03) would have a different complete-month inventory. It was not assessed further.
