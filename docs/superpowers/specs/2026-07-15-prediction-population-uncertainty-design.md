# Prediction Population and Qualitative Uncertainty Design

**Date:** 2026-07-15  
**Status:** Approved design; implementation not started  
**Scope:** Extend the existing 0m, 6m, and 12m prediction CSV contracts without
changing model weights, model features, or prediction values.

## Objective

Add two kinds of downstream context to each area-level prediction output:

1. A complete, traceable population estimate that downstream consumers can use
   to calculate country-level population percentages.
2. A qualitative uncertainty label that describes how close the prediction is
   to a model decision boundary.

Country-level aggregation, percentage calculation, statistical confidence
intervals, model retraining, and model recalibration are outside this scope.

## Existing Constraints

- The operational inference pipeline produces one prediction CSV for each of
  the 0m, 6m, and 12m horizons.
- Each scope uses four deterministic XGBoost regression scores:
  `phase2_worse_score`, `phase3_worse_score`, `phase4_worse_score`, and
  `phase5_worse_score`.
- Each score is converted to a binary boundary prediction using the threshold
  stored in the corresponding scope's model metadata.
- The current model feature contract includes `estimated_population` and
  median-imputes missing model inputs.
- For the 2026-04 monthly base input, 3,453 of 6,227 rows have missing
  `estimated_population`. Every affected area has at least one non-missing
  historical population value, and most affected areas vary over time.
- Population values added for downstream reporting must not replace or modify
  the model's `estimated_population` feature. The current scores and predicted
  phases must remain unchanged.

## Chosen Architecture

Population enrichment belongs in monthly assembly, where the historical panel
is already available. Inference receives the resulting output-only population
fields, preserves them through scoring, and writes them into every prediction
CSV.

Qualitative uncertainty belongs in inference because it depends on the four
scope-specific scores and thresholds. It is calculated after scoring and before
the prediction CSV is written.

```text
historical panel + selected-month scaffold
    -> monthly assembly
       -> preserve model feature: estimated_population
       -> add output-only population fields
    -> existing feature-contract application and model scoring
    -> add qualitative threshold-margin uncertainty
    -> write enriched 0m, 6m, and 12m prediction CSVs
```

The Vertex AI wrapper continues to localize cloud artifacts into ephemeral
container paths and run the existing operational inference entrypoint. It does
not read the full historical panel or calculate population carry-forward values.

## Population Semantics

### Selection Rule

For every `area_id` in a selected `feature_month`:

1. Use the area's non-missing `estimated_population` from the feature month
   when available.
2. Otherwise, use the area's most recent non-missing `estimated_population`
   from a month earlier than the feature month.
3. Never use a population value from a future month.
4. Do not fill from another area, a country median, or the model feature
   contract's training median.
5. Fail assembly if no current or prior population value exists for an area.

The selected feature-month population is repeated unchanged in that run's 0m,
6m, and 12m outputs. It is a launch-time population denominator, not a forecast
of population at each target horizon.

### Population Output Fields

Each prediction row must contain:

| Field | Type | Contract |
|---|---|---|
| `population_estimate` | finite number | Non-negative selected population value. |
| `population_reference_period` | string | Source month in `YYYY-MM`; must not be later than `feature_period`. |
| `population_imputation_method` | enum | `observed_feature_month` or `last_observation_carried_forward`. |

`observed_feature_month` is used only when the reference period equals the
feature month. `last_observation_carried_forward` is used only when the
reference period is earlier.

These fields are output metadata. They must not enter the model feature matrix
or overwrite `estimated_population`.

## Qualitative Uncertainty Semantics

### Interpretation

The uncertainty label describes decision stability: how close any of the four
scope-specific scores is to its own decision threshold. It is not a probability,
confidence level, calibrated prediction interval, or statistical coverage
guarantee.

### Calculation

For each phase boundary `k` in 2, 3, 4, and 5:

```text
phase_k_margin = abs(phase_k_worse_score - phase_k_threshold)
```

The row-level decision margin is:

```text
decision_margin = min(phase_2_margin, phase_3_margin,
                      phase_4_margin, phase_5_margin)
```

Thresholds must come from the loaded scope model metadata through the existing
threshold resolution logic. The implementation must not assume a universal
threshold value.

### Labels

| Rule | `prediction_uncertainty` |
|---|---|
| `decision_margin < 0.05` | `high` |
| `0.05 <= decision_margin < 0.10` | `medium` |
| `decision_margin >= 0.10` | `low` |

If two or more boundaries have exactly the same minimum margin, the critical
boundary is selected in the deterministic order phase 2, phase 3, phase 4,
then phase 5.

### Uncertainty Output Fields

Each prediction row must contain:

| Field | Type | Contract |
|---|---|---|
| `prediction_uncertainty` | enum | `high`, `medium`, or `low`. |
| `decision_margin` | finite number | Minimum absolute threshold distance; non-negative. |
| `uncertainty_critical_boundary` | enum | `phase2_worse`, `phase3_worse`, `phase4_worse`, or `phase5_worse`. |
| `uncertainty_method` | string | Fixed value `qualitative_threshold_margin_v1`. |

## Prediction Output Contract

The existing prediction fields, row universe, filenames, and three-scope
inventory remain unchanged. The seven population and uncertainty fields above
become required prediction-output fields.

For the same monthly input and model package, the enriched output must preserve
the existing values of:

- all four score columns;
- all four binary boundary prediction columns;
- `overall_phase_pred`;
- `feature_period`, `target_period`, and `scope_months`;
- identity and row-order fields.

The cloud prediction validator must reject outputs that omit or invalidate the
new required fields. Release paths and the number of released prediction files
do not change.

## Reports and Traceability

`inference_report.json` must record:

- `uncertainty_method=qualitative_threshold_margin_v1`;
- counts of `high`, `medium`, and `low` labels by scope;
- a decision-margin summary by scope;
- counts of `observed_feature_month` and
  `last_observation_carried_forward` population rows by scope.

The monthly assembly summary must record the population selection counts and
failures before inference begins. Existing image, model package, run, and
release provenance remains unchanged.

## Validation and Failure Behavior

Population validation is a hard gate:

- every prediction row has a finite, non-negative `population_estimate`;
- every population reference period is valid and no later than the feature
  month;
- every method agrees with its reference period;
- each area has identical population fields across 0m, 6m, and 12m;
- no population value is sourced from a future month;
- no area is filled from a cross-area or global statistic.

Uncertainty validation is a hard gate:

- all scores and resolved thresholds used in the calculation are finite;
- `decision_margin` matches a validator-side recomputation;
- the label matches the approved 0.05 and 0.10 boundaries;
- the critical boundary matches the minimum margin and tie-break rule;
- `uncertainty_method` has the approved fixed value.

Any failure blocks release and is recorded using the existing assembly or
inference failure-report path.

## Testing Strategy

### Population Tests

- Use feature-month population when present.
- Carry forward the latest prior value when feature-month population is
  missing.
- Reject future values and prove no future leakage.
- Keep area histories isolated from one another.
- Fail when an area has no current or historical population.
- Verify identical population fields across all three scopes.
- Verify original `estimated_population` values and model feature matrices are
  unchanged.

### Uncertainty Tests

- Test values below, exactly at, and above the 0.05 and 0.10 boundaries.
- Test scope-specific threshold resolution from model metadata.
- Test deterministic critical-boundary tie handling.
- Recompute and validate every uncertainty field independently.

### Regression and Cloud Tests

- Compare pre-change and post-change score, binary prediction, and overall phase
  values row by row for an identical fixture and model package.
- Keep prediction filenames, row counts, keys, and scope inventory unchanged.
- Extend operational inference, Vertex wrapper, prediction schema, fake-cloud
  E2E, release consumer, and gated live GCP smoke tests for the new fields.

## Out of Scope

- Country-level population aggregation or percentage calculation.
- Population forecasts for 6m or 12m target periods.
- Model retraining, new weights, ensembles, bootstrapping, quantile models, or
  conformal calibration.
- Numeric confidence intervals or probabilistic confidence claims.
- Changes to prediction maps, prediction sheets, or other delivery artifacts.
- Changes to the current cloud-only runtime architecture or model package split.

## Acceptance Criteria

The change is accepted when, for one identical input and model package:

1. Existing model scores and predictions are unchanged row by row.
2. Every 0m, 6m, and 12m prediction row contains valid and traceable population
   fields.
3. Every prediction row contains a reproducible qualitative uncertainty label,
   margin, critical boundary, and method.
4. Prediction, report, fake-cloud E2E, release, and gated smoke contracts cover
   the extended schema.
5. No country-level calculation, model retraining, or statistical confidence
   interval is introduced.
