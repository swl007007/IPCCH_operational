# Approved training-error confidence revision

Status: approved through the user's sequential grilling confirmations, 2026-09-11.

Revise the delivered April -> September 2026 h5 model package without retraining or changing fitted models, features, inference scores, decisions, routing, geometry or population-weighted country means. Preserve the original delivery. Create `Outcome/model_delivery/202609_h5/20260911_training_confidence_v2`.

Load each existing final model and reconstruct exactly its original training rows from the delivered input panel and training-key CSV. Predict those rows with the saved preprocessing and model state. This is explicitly in-sample resubstitution, not held-out evaluation or future error probability.

Error event is unified Phase 3+ binary disagreement. FEWSNET uses its saved crisis threshold and original binary target. IPCCH uses its raw `phase3_worse` predicted cumulative share and actual sum of phase3/4/5 shares, each compared with >=0.2, as agreed during grilling. This diagnostic threshold comparison does not substitute the separate cummax overall-phase decision; the existing September output decisions remain unchanged.

For polygon a: `error_rate_a = number_of_incorrect_training_rows / number_of_training_rows`. For country c: `country_training_error_rate = mean(error_rate_a)` over its native polygons, equal weight per polygon regardless of population or row count. Export row-level predicted/truth evidence and polygon-level counts/rates. Reject missing labels, duplicate training keys, nonfinite scores, missing country mappings or unsupported polygons instead of treating them as zero error. Current expected support: FEWSNET5718 areas/188643 rows; IPCCH6227 areas/43551 rows.

Rank countries separately within FEWSNET22 and IPCCH53 by descending country error rate, ties by ISO3 ascending. Allocate `ceil(0.20*N)` low flags:5 and11 respectively. Others high. Exact quotas apply even at tied boundaries; record boundary ties and ranks. Labels are `low` and `high` in `country_confidence_flag`; their meaning is relative training fit only.

Remove IPCCH polygon fields `prediction_uncertainty`, `decision_margin`, `uncertainty_critical_boundary`, `uncertainty_method`, and disable their calculation for the revised delivery. Preserve country score SD values as dispersion: rename IPCCH `phase*_worse_score_aggregation_uncertainty` to `phase*_worse_score_area_dispersion` and `aggregation_uncertainty_method` to `area_dispersion_method`. FEWSNET dispersion already has suitable names. Append country rate, flag, rank, method, polygon/row support and error counts. Store country flag policy and evidence in the package.

Update runtime, README, inventories and application archive. Re-score from relocated exported packages and require identical retained September fields, exact model-package hashes, polygon/country support and macro arithmetic, quota/tie determinism and no legacy uncertainty columns in revised formal CSVs. Only focused tests and independent verification; no TDD or regression suite. No cloud/web application/remote push.
