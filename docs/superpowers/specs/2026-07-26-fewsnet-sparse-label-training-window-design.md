# FEWSNET Sparse-Label Training Window Design

**Date:** 2026-07-26

**Status:** Approved design

**Pipeline root:** `fewsnet_partitioned_rf_pipeline/`

**Supersedes:** The contiguous-calendar interpretation of the 36-month
training window in
`2026-07-26-fewsnet-local-202604-prediction-experiment-design.md`. All other
parts of that design remain unchanged.

## 1. Purpose

Correct the shared FEWSNET training-window contract so it matches the approved
source's sparse IPC label cadence. A training window means the latest 36
distinct, actually labeled `target_month` periods ending at the declared latest
label month. Those periods do not need to be consecutive calendar months.

The correction belongs in the shared core used by local and future Vertex
training. It is not a local-runner exception and does not create a second model
architecture.

## 2. Failure evidence and root cause

The first full local `2026-04` acceptance run used the approved normalized
panel:

```text
FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.csv
sha256=510375f58cd835e694b6e287cce9439bbe1b6246d752daabc8151df8ffdda61d
rows=1,120,728
areas=5,718
latest_feature_month=2026-04
latest_label_month=2026-02
```

It failed before model fitting with:

```text
training frame must contain exactly one inclusive 36-target_month window
```

The existing selector interpreted `36` as the calendar interval
`2023-03..2026-02`. After horizon alignment removed null targets, only seven
actually labeled periods remained in that interval. The trainer then required
36 consecutive calendar periods, so valid sparse-label history could never
satisfy the contract.

The approved panel has 53 distinct labeled target periods through `2026-02`.
Selecting its latest 36 labeled periods gives:

- observed-period bounds: `2014-04..2026-02`;
- 188,643 total aligned rows;
- 155,067 rows in the first 30 labeled periods, bounded by
  `2014-04..2023-06`;
- 33,576 rows in the last six labeled periods, specifically `2023-10`,
  `2024-02`, `2024-06`, `2024-10`, `2025-10`, and `2026-02`.

No model package, prediction CSV, suite version, run ID, or passed summary was
created by the failed run. `Outcome/fewsnet_partitioned_rf/` remains absent,
and `Outcome/ipcch_unified/` remained byte-identical.

## 3. Chosen semantics

For a requested window size `N` and normalized `latest_label_month`:

1. Prepare and validate the aligned frame using the existing month and row
   normalization rules.
2. Consider only rows whose `target_month` is less than or equal to
   `latest_label_month`.
3. Derive the sorted distinct target periods represented by non-null aligned
   labels.
4. Require `latest_label_month` itself to be represented.
5. Require at least `N` eligible distinct target periods.
6. Select the chronologically latest `N` periods and all aligned rows belonging
   to them.
7. Return rows using the existing deterministic sort order.

For the production constant `N = 36`, the selected frame must contain exactly
36 distinct labeled periods. Calendar gaps between those periods are valid.

The `months` parameter name remains unchanged for API compatibility, but its
operational meaning is the count of distinct labeled monthly periods, not the
width of a dense calendar interval.

## 4. Threshold selection and final fitting

The existing chronological 30/6 procedure remains unchanged:

- The first 30 of the selected 36 labeled periods fit the temporary model used
  for threshold selection.
- The last six labeled periods form the threshold-validation set.
- The threshold algorithm and tie behavior remain unchanged.
- After threshold selection, the final model is refit on all 36 labeled
  periods.

The split is based on sorted observed `target_month` values. It does not create
rows for missing calendar months, forward-fill labels, interpolate labels, or
weight longer calendar gaps differently.

## 5. Validation and failure handling

The shared trainer fails closed when any of these conditions holds:

- `months` is not a positive integer;
- `latest_label_month` or a frame month is invalid;
- `latest_label_month` has no labeled aligned rows;
- fewer than 36 distinct labeled periods exist at or before the boundary;
- the selected frame contains anything other than exactly 36 distinct target
  periods;
- existing horizon alignment, feature, target, partition coverage, or model
  validations fail.

There is no fallback to a shorter training history and no automatic movement
of the latest-label boundary. Periods after the declared boundary are ignored.

Dense monthly inputs remain valid: when the latest 36 labeled periods are
consecutive, the selected rows are the same as under the previous behavior.

## 6. Reports and artifact meaning

Existing report and package fields remain in place. No schema version or output
column is added solely for this correction.

Fields named `training_target_month_range`, `fit_target_month_range`, and
`validation_target_month_range`, and equivalent start/end fields in aggregate
reports, record the minimum and maximum observed target periods in the relevant
set. They are bounds over a sparse set and do not assert that every intervening
calendar month is labeled.

The implementation and tests must not describe these fields as contiguous
calendar windows. The exact period-count invariants remain authoritative:

- training/model-fit history: 36 distinct labeled periods in total;
- threshold-fit subset: 30 distinct labeled periods;
- threshold-validation subset: six distinct labeled periods.

The local suite version continues to include the source Git commit, so a suite
trained after this core correction receives a new deterministic identity.
Existing model packages are not mutated.

## 7. Unchanged model and output contracts

This correction does not change:

- the Stage 3 feature contract or feature checksum;
- 0m, 6m, and 12m horizon alignment;
- Random Forest parameters or fitting behavior;
- SMOTE behavior or its reviewed compatibility bridge;
- `MaxPlusImputer` behavior;
- the fixed partition map, routing, or pooled fallbacks;
- threshold search, scoring, or binary-label calculation;
- `probability_crisis` as the continuous `[0, 1]` output;
- `predicted_crisis = int(probability_crisis >= threshold)`;
- population enrichment and provenance;
- local package, prediction CSV, publication, or overwrite contracts;
- production package schemas, GCS paths, Vertex resources, or IPCCH artifacts.

No phase-specific field or separate categorical uncertainty field is added.

## 8. Implementation boundary

The correction should remain narrow:

- update the shared training-window selector to choose the latest distinct
  labeled periods at or before the boundary;
- update the exact-window validator to require 36 distinct periods without a
  contiguity requirement;
- preserve the existing chronological threshold splitter;
- add focused sparse-cadence regression tests and retain dense-cadence tests.

The likely existing symbols are
`core.horizons.select_training_window` and
`core.training._validate_exact_training_window`. Before either symbol is
edited, the implementation workflow must run GitNexus upstream impact analysis
and report its risk and callers.

No local-runner special case, source-panel rewrite, label imputation, new
configuration flag, or unrelated refactor is part of this change.

## 9. Testing strategy

### 9.1 Selector regressions

Add a synthetic frame with more than 36 labeled periods separated by calendar
gaps. Verify that selection:

- returns exactly the latest 36 distinct labeled periods;
- includes all rows from each selected period;
- excludes earlier labeled periods and periods after the boundary;
- ends exactly at the declared latest label month;
- preserves deterministic row ordering.

Keep a dense-cadence regression proving that the existing consecutive case
still selects the same 36 periods.

### 9.2 Trainer regressions

Use a synthetic 36-period sparse cadence to verify that training reaches the
unchanged threshold/model path, with the first 30 periods used for temporary
fit, the last six for validation, and all 36 for final fitting.

Add or retain fail-closed tests for:

- only 35 distinct labeled periods;
- an absent latest-label boundary;
- invalid month values;
- horizon misalignment and all existing feature/coverage failures.

Report tests must assert that start/end values are the bounds of the sparse
period sets rather than evidence of contiguity.

### 9.3 Regression scope

After focused RED/GREEN tests, run the complete FEWSNET test suite with the
approved dependency pins. No acceptance claim is made until the full suite
passes.

## 10. Clean Task 5 rerun

After the correction is independently reviewed and committed, rerun the exact
full-source local experiment from a clean commit:

- use the complete approved normalized panel without sampling;
- keep the frozen RF parameters and all dependency pins;
- confirm `Outcome/fewsnet_partitioned_rf/` is absent and do not pass
  `--overwrite`;
- create no GCP, GCS, Vertex, registry, alias, or network mutation;
- verify three reloadable horizon packages and three 5,718-row prediction
  CSVs;
- validate probabilities, thresholded labels, population provenance, reports,
  checksums, and passed-summary-last publication;
- compare before/after checksums for `Outcome/ipcch_unified/`.

The accepted run must record the actual sparse training and validation bounds
without claiming calendar contiguity.

## 11. Completion condition

This correction is complete when:

1. shared core selection accepts exactly 36 latest labeled periods with
   calendar gaps;
2. fewer than 36 periods and an absent boundary fail closed;
3. the unchanged 30/6 threshold and all-36 final-fit behavior are covered by
   tests;
4. the full FEWSNET regression passes;
5. a clean, unsampled Task 5 rerun publishes and verifies the three local
   `2026-04` prediction scopes without modifying IPCCH or cloud state.
