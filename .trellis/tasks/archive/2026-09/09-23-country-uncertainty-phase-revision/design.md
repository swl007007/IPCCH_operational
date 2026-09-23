# Country uncertainty and phase — specification for final review

Date: 2026-09-23. Status: APPROVED FOR EXECUTION by the user on 2026-09-23; execution plan in implement.md.
Task: `country-uncertainty-phase-revision`.

## 1. Scope and intended result

Use `Outcome/model_delivery/202609_h5/20260911_training_confidence_v2` as the immutable parent (D below). USER APPROVED DESTINATION: `Outcome/model_delivery/202609_h5/20260923_country_confidence_v3`. Preserve v2, saved models and September 2026 polygon forecasts. Deliver revised country tables, traceable row/area evidence, uncertainty metadata, and a consistent reloadable package in v3.

Treat three quantities separately: historical classification error, a country outcome decoded from aggregated scores, and stability or predictive uncertainty of the maximum area phase. None is automatically interchangeable with another.

## 2. Verified current state and source inventory

### FEWSNET

- Current output: 22 countries and 5,718 polygons. Area forecasts are binary Phase3+ with probability score; saved area threshold is 0.43. Country `probability_crisis` is a population-weighted mean of area scores, not a calibrated country-event probability or the fraction of positive area labels.
- Historical candidate: `paper_reproducibility_package/stage3_results/georf_fs1/predictions_monthly.csv` beneath `/mnt/c/users/swl00/ifpri dropbox/weilun shi/google fund/analysis/2.source_code/step5_geo_rf_trial/food_crisis_cluster` (R below).
- Candidate has 62,189 rows, 5,713 distinct `FEWSNET_admin_code`, and 12 target/test months: February, June and October of 2021–2024. Fields include `month_start`, `y_true`, `y_pred_partitioned`, `y_prob_partitioned` and pooled alternatives. Polygon/month keys are unique. Do not mix pooled and partitioned predictions.
- All candidate rows match D's 2021–2024 training-evidence keys and labels, but their predicted values come from separate rolling historical fits. The historical candidate is NOT the final delivered model's training replay.
- Candidate manifest: 36-month training window, `forecasting_scope=1`, `active_lag_months=4`, 17 fixed partitions learned in 2018–2020. Manifest polygon count 5,716 differs from actual prediction coverage 5,713; use observed support.
- Historical decisions are saved classifier `.predict()` outputs: in this CSV they equal probability strictly greater than 0.5. There are 469 exact-0.5 rows, all classified zero. Do not silently replace these labels with either >=0.5 or the delivered 0.43 threshold.
- Same historical partition source is referenced by delivered runtime assets; exact h5 feature/target equivalence is not demonstrated. USER DECISION (2026-09-23, meeting agreement): use this saved Stage3 historical series as the **h5 validation-error proxy**, with polygon-level confidence calculated from historical observations. Preserve source fs1/4-month-lag metadata without relabeling it as an exact-horizon validation run.
- Identity/population join: D/inputs/fewsnet_identity_population.csv. Five delivered polygons lack this historical candidate: 216, 2786, 4375, 4511, 5500. All historical rows map to ISO3. Delivered population is 2024-10 last-observed for 5,716 polygons; two are missing. This is not a historical per-test-month weight series.

### IPCCH and current diagnostic policy

- Current output: 53 countries, 6,227 polygons, four raw cumulative-share scores (`phase2_worse_score` through `phase5_worse_score`). These are not mutually exclusive probabilities; do not normalize their sum to one.
- Area decoder thresholds each raw cumulative score at >=0.2, propagates active higher boundaries downward, then returns the highest active phase (otherwise Phase1). Raw scores are not clipped or made monotonic. Current polygon phases are 1–4; no polygon is Phase5.
- Country tables currently contain population-weighted raw scores and spatial dispersion, but no decoded country overall phase or country maximum phase.
- Existing country error is an EQUAL-AREA mean for BOTH systems, not population weighted: `tools/revise_h5_confidence.py:26-41`. Existing flags force ceil(20% of countries) to low.
- IPCCH saved row evidence D/reports/ipcch_training_predictions.csv compares raw Phase3+ score >=0.2 with actual cumulative Phase3+ share >=0.2. This differs from evaluating the full decoded phase. Evidence is training resubstitution, not held-out prediction.
- IPCCH area weights are `population_estimate`, dated 2018-06 through 2026-04: 2,774 observed in feature month and 3,453 carried forward. Country Census reference population (2026) is a separate reporting field, not the aggregation weight denominator.
- FEWSNET offers only binary Phase3+ output; a five-level `country_maximum_phase` cannot be recovered from this model. USER CONFIRMED (2026-09-23): five-level country phase metrics, including `country_maximum_phase` and its uncertainty, apply only to IPCCH. FEWSNET retains the requested country crisis0/1 flag.

### Source pointers

- R/paper_reproducibility_package/stage3_results/georf_fs1/run_manifest.json:4-27 — historical scope, parameters and evaluation years.
- R/scripts/compare_partitioned_vs_pooled_rf_k40_nc4.py:369-395,1218-1233,1303-1309 — historical prediction rule, rolling evaluation and saved keys.
- D/runtime/fewsnet_partitioned_rf_pipeline/assets/partitions/partition_manifest.json:3-5 — historical family/partition lineage.
- `tools/run_h5_model_delivery.py:69-84,97-130` — h5 alignment, IPCCH target definitions and runtime policy.
- `tools/build_fewsnet_country_level_predictions.py:340-371`; `tools/build_ipcch_country_level_predictions.py:365-387` — existing country aggregation.
- `model_pipeline/ipcch_launch_runtime/inference.py:60-79,213-243` — area threshold/cascade/decode.
- `fewsnet_partitioned_rf_pipeline/local/outputs.py:263-309`; `model_pipeline/ipcch_launch_runtime/population.py:100-151` — population provenance.

## 3. Agreed error definitions

For each observed area a and evaluation row t, define binary error d_at = 1(predicted class differs from actual class). Area error e_a = sum(d_at) / n_a. Country error aggregates area rates, not pooled rows; areas with more observations do not silently receive more weight.

FEWSNET approved source: the saved partitioned Stage3 2021–2024 series is the h5 validation-error proxy. USER CONFIRMED (2026-09-23): `polygon_confidence = 1 - polygon_error_rate`, retaining historical sample and error counts. This is historical accuracy used as a proxy, not calibrated September correctness probability. Preserve saved historical decisions unless another policy is approved. USER CONFIRMED: FEWSNET country errors use population-weighted area error rates, as required for IPCCH: `E_c = sum(P_a * e_a) / sum(P_a)` over eligible areas. Use the existing delivered polygon population snapshot, retaining its dates and provenance; apply the approved missing-support rule below. Do not use the final model to regenerate historical predictions.

IPCCH requirement: E_c = sum(P_a * e_a) / sum(P_a) over areas with valid errors and positive valid populations. USER CONFIRMED (2026-09-23): use the existing delivered area population snapshot for both models, retaining population dates and sources, without reconstructing historical-month populations or substituting country Census totals. USER CONFIRMED AS A MEETING DECISION: retain saved Phase3+ training-resubstitution error events, comparing raw predicted and actual cumulative Phase3+ shares at >=0.2. Keep the `training_resubstitution` evidence label. Do not change to held-out errors or full-phase mistakes; do not re-open this agreed source decision during grilling.

USER CONFIRMED (2026-09-23): retain every polygon record, but exclude polygons lacking an error rate or a valid positive population from country error aggregation. Do not impute zero or automatically downgrade confidence for incomplete coverage. Compute and classify using eligible records; if none exist, country error rate and confidence flag are null. Keep all available positive-sample area error evidence without adding a minimum-sample or coverage cutoff. Export eligible/total area counts, excluded counts, eligible/known population sums, known-population coverage, missing-population area counts, evidence period/source and weighting vintage. Unknown population is not included as zero in a supposed full-population coverage denominator; label known-population coverage explicitly. Preserve a polygon's error/confidence when its historical evidence exists even if its population is missing. Maximum-phase uncertainty has the separate complete-roster support rule below.

Use `country_error_rate`, `country_error_basis`, `country_error_weighting` and support fields. Remove prior `country_training_*` diagnostic columns and stale quota/rank/boundary fields from revised formal country tables; v2 retains the prior schema and values. IPCCH's evidence basis remains `training_resubstitution`; FEWSNET uses `h5_validation_error_proxy_stage3_2021_2024`. Do not remove unrelated forecast, population or dispersion columns.

## 4. Country outcome definitions for final review

Implement the requested FEWSNET country0.5 threshold as `country_outcome_crisis = int(existing population-weighted probability_crisis >= 0.5)`. This is a decision from an aggregate score;0.5 is separate from historical area classification and the saved deployment area threshold0.43. Missing aggregate score produces a null flag, not zero. Do not change area forecasts.

Implement the requested IPCCH country20% rule using the existing population-weighted country cumulative scores, then the existing >=0.2 cascade/decode. Return `country_overall_phase` (1–5). Do not take a modal area phase, average phase codes, or normalize cumulative scores to sum to one. Preserve the existing raw-score semantics and report inherited out-of-range/nonmonotonic values; introduce no clipping. Missing/nonfinite required country scores yield a null country phase with an availability reason.

USER CONFIRMED SCOPE: IPCCH only. `country_maximum_phase = max(area overall_phase_pred)` across the full delivered country roster, including zero-population areas. Population does not affect this literal maximum or eligibility for its uncertainty. Require valid Phase1–5 predictions and unique identities for the full current roster; an invalid/missing current phase is an integrity failure, not silently excluded. Do not create five-level maximum phase or its uncertainty for FEWSNET.

## 5. Agreed confidence flags

USER CONFIRMED (2026-09-23): replace the quota rule with THREE confidence categories, `high`, `medium`, `low`, using the SAME fixed cutoffs for both models: high when E_c <= 0.10, medium when 0.10 < E_c <= 0.20, low when E_c > 0.20. Classify unrounded error rates on eligible records without an additional coverage downgrade. If no eligible records exist, return null error and null flag. No country quota or rank breaks ties.

The user-approved cutoffs and inclusive boundaries are operational choices, not universally justified statistical thresholds. Support and unavailable-case handling follow the approved rule in section3. The same numerical cutoff across Stage3 held-out errors and IPCCH training errors does not make their empirical confidence comparable. Bootstrap precision of an error estimate also does not remove training optimism.

### Read-only threshold comparison, 2026-09-23

Calculated directly from approved evidence sources and delivered positive population weights, without changing delivery files. FEWSNET uses saved historical partitioned decisions; IPCCH uses saved area training errors (checked against error_count/sample_count). Countries remain equally counted in the following category totals; within-country error aggregation is population weighted. The subsequently approved missing-support rule does not add a coverage or sample-size gate to these counts.

| Error cutoffs a / b | FEWSNET high / medium / low (22) | IPCCH high / medium / low (53) |
| --- | --- | --- |
| 10% / 20% | 11 / 4 / 7 | 27 / 14 / 12 |
| 15% / 30% | 14 / 6 / 2 | 35 / 16 / 2 |
| 20% / 30% | 15 / 5 / 2 | 41 / 10 / 2 |
| 20% / 40% | 15 / 7 / 0 | 41 / 11 / 1 |
| 25% / 40% | 18 / 4 / 0 | 50 / 2 / 1 |

USER APPROVED: common cutoffs 10% / 20%, meaning high at >=90% historical/training accuracy proxy, medium at >=80% but <90%, low below80%. These are interpretable operational tolerances, not data-fitted optimal thresholds or calibrated confidence levels. Distribution counts illustrate impact and must not be used to force balanced categories. No country lies exactly on a candidate cutoff; classify using unrounded values.

FEWSNET weighted errors range 0.5864%–35.4529%, median9.7928%. Eligible support:5,706 of5,718 delivered polygons,62,111 historical rows. Seven historically evaluated polygons have zero population (ETH1407/1469/1551; COD3761/3798/3883/3984). Five delivered polygons have no historical predictions: ZWE4375, MWI4511, UGA5500 with known positive population; SOM216 and KEN2786 with missing population. Known-positive-population coverage is ZWE94.4599%, UGA98.2541%, MWI99.3142%, otherwise100% of known population (not proof of complete population coverage for missing-population polygons). Historical polygon sample counts range1–12. Under10%/20%, low countries are AFG,GTM,HTI,MWI,SDN,SOM,ZWE.

IPCCH weighted errors range0%–42.1821%, median9.2741%. Eligible support:6,221 of6,227 polygons,43,526 training rows,5,419 mistakes. Six SDN polygons have zero population (3320,3359,3368,3373,3378,3570); all positive population is covered. No missing joins. Country training samples range19–6,549;216 polygons have only one training row, including two zero-population polygons. Under10%/20%, low countries are BGD,COD,DJI,LSO,MDG,MWI,PAK,SOM,TLS,UGA,ZAF,ZMB.

Separate read-only agents computed the two distributions. Main-agent spot checks independently reconstructed FEWSNET GTM error0.20225959445061248 (353 areas) from raw historical decisions, and IPCCH SOM error0.20045722834594323 (905 areas) from counts and weights. SOM and UGA IPCCH rates are slightly above20%; never round before classification. Final implementation still requires full independent verification.

## 6. Maximum-phase uncertainty: predictive correctness selected

USER CONFIRMED WEIGHTING/SAMPLING DISTINCTION (2026-09-23): population weighting remains mandatory for the country error rate. Maximum-phase uncertainty instead resamples complete country historical months, keeping all polygons and their within-month joint errors together; do not sample polygons by population or weight a literal maximum. This supersedes the initial population-weighting preference specifically for maximum-phase uncertainty. It preserves empirical within-month spatial dependence, not automatically dependence between historical months. The user has adopted the residual-transfer method and bootstrap settings below.

### Approved residual-transfer method (2026-09-23)

After approval for execution, load the four saved models and reconstruct predictions on the exact training rows without fitting. For every complete country/month, save the joint residual matrix `r[a,k,t] = actual_cumulative_share[a,k,t] - predicted_score[a,k,t]` for all fixed country polygons a and thresholds k=2..5. Apply one whole month's residual matrix to the September raw score matrix: `simulated_actual_score[a,k,t] = september_score[a,k] + r[a,k,t]`. Use the existing raw-score >=0.2 cascade to decode simulated phases, with no new clipping or sum-normalization. Compute the simulated country's maximum and compare it with the fixed September maximum. All polygons, including zero-population polygons, remain in this literal maximum. The adopted method transfers historical training residual patterns to the current forecast under a stationarity/exchangeability assumption; describe its result as a training-residual-based maximum-phase error-probability proxy, not a calibrated future probability.

Compute the point proxy exactly as the fraction of complete-month residual scenarios whose simulated maximum differs from the fixed forecast maximum. Resample complete months with replacement to quantify sampling variability of that fraction, preserving each month's entire polygon/threshold residual matrix. Historical months are equally weighted. USER CONFIRMED SETTINGS (2026-09-23):10,000 replicates, each drawing the original number of complete months, fixed random seed (implementation value20260923), percentile95% interval for the proxy (not a95% prediction interval for phase). With only one complete month, retain the scenario-based point proxy, leave interval bounds null and report that month-to-month variability cannot be estimated. With zero complete months, both point proxy and interval are null. For multiple months with identical scenario outcomes, report empirical degeneracy; zero bootstrap spread does not establish certainty. Keep sampling reproducible with stable country/date order and record seed, replicate count and percentile convention in metadata.

The adopted maximum-phase proxy is separate from the approved population-weighted Phase3+ country error/confidence metric. Do not replace one with the other. Do not substitute polygon composition stability, independent polygon phase flips, or spatial weighted SD for the chosen residual-field method. Full-phase training replay belongs to implementation after the spec/plan approval and audit start; it has not run during planning.

Reproducibility convention: use the pinned NumPy runtime with `Generator(PCG64(20260923))`, process countries in ISO3 order and scenarios in chronological target-month order, and compute2.5/97.5 percentiles using `method="linear"`. Record library versions alongside these settings. Stable support field `country_maximum_phase_uncertainty_status` uses `no_complete_history`, `single_month`, `degenerate_empirical`, or `supported` (in that priority order); the label `supported` refers to empirical support for the chosen procedure, not calibration.

## 7. Delivery and verification boundaries

### Read-only maximum-phase evidence investigation, 2026-09-23

All43,551 saved IPCCH training feature/target keys match the delivered panel uniquely; all128 saved feature columns and all five phase-share labels are available. Four cumulative targets use the same training rows, with target dates2014-01 through2026-04, strictly five months after features. Four saved model JSON files exist (128 features,200 trees each, XGBoost3.2.0). Source inspection (`tools/run_h5_model_delivery.py:97-134`, `tools/revise_h5_confidence.py:149-181`, `model_pipeline/ipcch_launch_runtime/model_package.py:59-71`) supports extending saved-model replay to all four targets without fitting. This investigation did not invoke the models. No saved full-phase paired training table was found in directly inspected delivery CSVs; the existing table contains only Phase3+ predictions.

USER CONFIRMED (2026-09-23): derive actual full phase from actual cumulative population shares using the same >=0.2 cascading rule as predictions: activate each Phase2+ through Phase5+ boundary, propagate higher active boundaries downward, and take the highest active phase; none active means Phase1. Do not use the panel's `overall_phase` as the error target or silently substitute it for share-decoded truth. Under the approved definition, actual counts are Phase1=9,154; Phase2=16,502; Phase3=15,191; Phase4=2,658; Phase5=46. The panel's alternative `overall_phase` field has133 missing values and627 invalid codes (0:523,9:102,6:2); of42,791 valid codes,452 disagree with the share decoder. Its official-label provenance has not been verified. Record inherited share anomalies without introducing an unapproved normalization policy:2,290 rows have total five shares>1.000001,63 have at least one cumulative target>1.000001,one has an individual share>1,none have negative shares.

Historical coverage limits joint country-error fields:773 country/target-month groups exist, only184 cover every delivered polygon in that country. Ten countries have no complete dates: AGO,CAF,ETH,HND,LSO,MOZ,SDN,SOM,SSD,TZA. Forty-three have at least one complete date, many only1–3 (ECU has only one date in total; TLS has two). Never join different dates into an apparent observed full-country maximum. A full-roster residual-field bootstrap therefore cannot be uniformly supported directly from existing observations.

USER CONFIRMED SUPPORT RULE (2026-09-23): an eligible historical month must cover every polygon in the country's delivered roster. With zero complete months, maximum-phase uncertainty is null; with at least one, prefer an estimate and disclose the number of complete months. Current inventory gives43 eligible countries and10 with null uncertainty (AGO,CAF,ETH,HND,LSO,MOZ,SDN,SOM,SSD,TZA); country_maximum_phase itself remains available. Do not impose an additional minimum-month cutoff or fill missing areas. A single eligible month cannot support a nondegenerate empirical temporal bootstrap; explicitly flag this limitation instead of interpreting zero variation as certainty. Apply the approved residual-transfer method in section6.

USER APPROVED PRESERVATION: create the sibling `20260923_country_confidence_v3`, with parent linkage and original hashes; do not overwrite v2. Record inherited versus newly generated evidence clearly. Parent reports must not masquerade as current validation. The new archive and manifests describe the final v3 contents.

### Export contract

- Both country tables: `country_error_rate`, `country_confidence_flag`, evidence basis/weighting and support/coverage fields; retain existing country prediction values and population references.
- FEWSNET country table: `country_outcome_crisis`. Export polygon error/confidence with observation/error counts on all5,718 delivered polygons; absent historical evidence yields null rate/confidence.
- IPCCH country table: `country_overall_phase`, `country_maximum_phase`, `country_maximum_phase_error_probability_proxy`, `country_maximum_phase_error_probability_ci_lower`, `country_maximum_phase_error_probability_ci_upper`, `country_maximum_phase_history_month_count`, and a support status distinguishing no complete history, single month, empirical degeneracy and supported intervals. The high/medium/low flag remains based on the separate Phase3+ country error, not this maximum-phase proxy.
- Persist row-level FEWSNET historical errors, IPCCH four-target training predictions/truth, and complete-month residual-scenario maxima/mismatch evidence keyed to country, polygon and dates as appropriate. Store method, seed, replicates, source hashes, date ordering and interval convention in accompanying metadata. Retain anomaly counts and month-coverage inventories.
- Revised README, reload/export behavior, country CSVs, standalone diagnostic tables and `webapp_model_bundle.tar.gz` must agree. Keep historical parent evidence explicitly separated from active v3 diagnostics.

Reuse existing aggregation, diagnostic and packaging code after impact analysis. Update country schemas and any reload/export path together so rerunning the package cannot silently restore old flags. Retain unchanged model files, polygon outputs, maps and native identities. Update README, diagnostic evidence, manifests/checksums and archive only after validation.

Focused verification: independently recompute historical joins/errors and weighted country arithmetic; check missing-population/support handling, exact 0.5/0.2/confidence boundaries, cascading phases and maxima; check bootstrap reproducibility and interpretation on tied maxima, a rare extreme area and one-area countries. Independently verify unchanged model/retained polygon data and final packaged schemas. No TDD or regression suite.

## 8. Decision register and final review

1. RESOLVED: user accepts the saved fs1 Stage3 historical series as the h5 validation-error proxy per meeting agreement. Polygon confidence is confirmed as one minus historical error rate, with sample/error counts retained.
2. RESOLVED: both models use population-weighted area rates and delivered polygon populations with provenance. Retain all polygon records, aggregate eligible ones, disclose exclusions/coverage without downgrading, and return null country error/flag if none are eligible. Preserve saved historical area decisions unless separately changed.
3. Country outcome implementation presented for final written-spec review: FEWSNET applies >=0.5 to the existing population-weighted probability mean; IPCCH applies >=0.2 cascade to the existing population-weighted cumulative scores. See section4 for exact boundaries and invalid-score handling.
4. RESOLVED BY MEETING DECISION: IPCCH retains saved binary Phase3+ training-resubstitution errors. Delivered population snapshot is also approved. Do not seek repeated confirmation.
5. RESOLVED: both models use high at error<=10%, medium at 10%<error<=20%, low at error>20%, on unrounded rates. Missing-support handling is approved in section3; retain evidence-source distinctions.
6. RESOLVED SCOPE: five-level country overall/maximum phase and maximum-phase uncertainty are IPCCH only; FEWSNET uses country crisis0/1. Section4 states the exact implementation for final review.
7. RESOLVED METHOD AND SETTINGS: transfer complete country/month joint training residual fields to fixed September scores, decode using the same >=0.2 cascade, and estimate the fraction of residual scenarios changing the maximum. Bootstrap whole months without population weighting; country error remains population weighted. Use10,000 replicates, a fixed seed and95% percentile intervals. Zero complete months gives null point/interval; one gives a point and null interval with limitation disclosure.
8. RESOLVED DESTINATION: preserve v2 and create `Outcome/model_delivery/202609_h5/20260923_country_confidence_v3`.

The consolidated written spec now awaits final approval. An execution plan and verified audit start follow; no production calculations or delivery modifications have run during planning.

## 9. Lifecycle state

Created `.trellis/tasks/09-23-country-uncertainty-phase-revision` with status `planning`; no native start was run. Repository audit registration succeeded for exact path `/mnt/c/users/swl00/ifpri dropbox/weilun shi/ipcch_monthly_operational`, bound to Claude pane `wC:p2`, session `10dce206-1397-4689-8998-6e8121e56959`, terminal `term_65c2911a3725f8`. Controller boot reported running true.

Executor refreshed at the user's request on2026-09-23: the same pane/terminal now hosts Claude session `fce0831a-4ef8-458b-b0c4-c2b930504dd5`, replacing the stale session above. Its live cwd was verified as this repository. `register --executor wC:p2` succeeded on the exact existing registered path; a subsequent durable `status` confirmed the new session, controller running and no active runs. Task remains planning. The new window visibly reported a SessionStart hook JSON-parse error; its cause was not investigated or repaired during this binding update. Recheck live identity before the later start.

Approved spec and subsequent execution plan must be committed before the bound executor runs `trellis-audit --repo '<registered path>' start country-uncertainty-phase-revision`. Record actual run ID, executor, base SHA and in_progress status then; none exists yet for this task. Do not create a historical baseline or mark planning as implementation. Completion requires close from that executor and an accepted audit result, not merely a queued review.
