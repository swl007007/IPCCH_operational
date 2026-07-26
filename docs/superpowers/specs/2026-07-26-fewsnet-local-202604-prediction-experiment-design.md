# FEWSNET Local 202604 Prediction Experiment Design

**Date:** 2026-07-26

**Status:** Approved design

**Pipeline root:** `fewsnet_partitioned_rf_pipeline/`

## 1. Purpose

Add a local-only experiment path for the existing FEWSNET fixed-partition
Random Forest suite. The experiment trains the current 0-, 6-, and 12-month
models from the approved normalized FEWSNET panel, predicts the latest feature
month `2026-04`, and publishes three per-area CSVs plus reproducible local model
artifacts.

The experiment proves the model mathematics, packaging, and prediction output
locally before any Vertex AI training, Model Registry, or Batch Prediction run.
It does not replace or modify the production cloud workflow.

## 2. Confirmed source evidence

The approved raw source is:

```text
C:\Users\swl00\IFPRI Dropbox\Weilun Shi\Google fund\Analysis\1.Source Data\assembled_FEWSNET\FEWSNET_forecast_unadjusted_bm_2025_combined.csv
```

The local experiment consumes the already approved normalized panel and its
audit:

```text
C:\Users\swl00\IFPRI Dropbox\Weilun Shi\Google fund\Analysis\1.Source Data\assembled_FEWSNET\FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.csv
C:\Users\swl00\IFPRI Dropbox\Weilun Shi\Google fund\Analysis\1.Source Data\assembled_FEWSNET\FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.audit.json
```

Observed and re-verified during design:

- Raw panel: 1,120,730 rows and 88 columns.
- Normalized panel: 1,120,728 rows and 88 columns.
- Normalized panel SHA-256:
  `510375f58cd835e694b6e287cce9439bbe1b6246d752daabc8151df8ffdda61d`.
- Authoritative area universe: 5,718 unique FEWSNET administrative areas.
- Latest feature month: `2026-04`.
- Latest labeled target month: `2026-02`.
- Native binary target: `fews_ipc_crisis`.
- The panel contains `lat`, `lon`, administrative identity fields, and `pop`.
- Every `2026-04` row has missing `pop`.
- For 5,716 of the 5,718 areas, the latest non-null `pop` is from `2024-10`.
- Two areas have no non-null `pop` anywhere in the normalized panel.

The local experiment does not require a shapefile. The model consumes panel
features including `lat` and `lon`, while routing uses the approved immutable
partition map already checked into the repository. Boundary geometry remains a
production snapshot validation input and is outside this local experiment.

## 3. Scope

### 3.1 In scope

- One local CLI entrypoint for a full three-horizon experiment.
- Exact reuse of the existing Stage 3 feature contract and preprocessing.
- Exact reuse of the fixed 17-cluster partition map and pooled fallbacks.
- True 0-, 6-, and 12-month horizon alignment.
- Existing 36-month labeled training-window behavior.
- Existing six-labeled-month threshold-validation behavior.
- Existing Random Forest, SMOTE, imputer, threshold, and routing behavior.
- Three local model packages with truthful local runtime metadata.
- Three `2026-04` per-area prediction CSVs.
- Raw-population enrichment and explicit population provenance.
- A machine-readable run summary, training report, checksums, and validation.

### 3.2 Out of scope

- Vertex AI Custom Jobs, Model Registry, Batch Prediction, or GCS writes.
- Creating or changing stable Vertex parent models or aliases.
- Modifying the production `fewsnet-model-package-v1` schema.
- Modifying the existing IPCCH model, inputs, outputs, or release workflow.
- Prediction maps, Excel workbooks, or phase-specific IPCCH outputs.
- New partition discovery or spatial clustering.
- Downsampling the real-source acceptance run.
- Evaluating future target-month performance before labels exist.

## 4. Chosen architecture

The implementation adds an isolated local adapter around the existing core
model code. It must not duplicate the training or prediction mathematics.

The component boundaries are:

```text
fewsnet_partitioned_rf_pipeline/
├── local/
│   ├── __init__.py
│   ├── package.py       # truthful local package write/load and checksums
│   ├── outputs.py       # identity/population enrichment and CSV validation
│   └── runner.py        # local three-horizon orchestration
├── cli/
│   └── run_local_experiment.py
└── schemas/
    ├── local-model-package.schema.json
    └── local-prediction-record.schema.json
```

These responsibility boundaries and filenames are fixed:

- `runner` coordinates the experiment without containing model mathematics.
- `package` owns the local artifact contract and reload verification.
- `outputs` owns row enrichment, column order, and cross-scope validation.
- The CLI parses arguments, invokes the runner, and prints a JSON result.

No production Vertex module is called, and no local code pretends to be a
Vertex or GCS resource.

## 5. Input contract

The local CLI accepts explicit paths rather than hard-coding workstation
locations. The initial command contract is:

```bash
python -m fewsnet_partitioned_rf_pipeline.cli.run_local_experiment \
  --panel "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.csv" \
  --normalization-audit "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.audit.json" \
  --feature-month 2026-04 \
  --output-root Outcome/fewsnet_partitioned_rf
```

Its required logical inputs are:

- Normalized panel CSV.
- Matching normalization audit JSON.
- Feature month, initially `2026-04`.
- Output root, initially `Outcome/fewsnet_partitioned_rf`.

The fixed feature contract and partition map are loaded from their existing
repository assets.

Preflight validation requires:

1. The panel and audit both exist and are distinct from the raw source.
2. The normalization audit validates the panel checksum, size, rows, columns,
   normalization version, and latest months.
3. The panel has one row per `FEWSNET_admin_code + feature_month`.
4. The area universe has exactly 5,718 unique administrative codes.
5. The requested feature month exists once for every authoritative area.
6. The feature-contract checksum and fixed partition checksum match the
   approved repository assets.
7. The source Git commit and runtime dependency versions can be recorded.
8. Tracked source files have no staged or unstaged changes, so the recorded
   Git commit identifies the executed code exactly. Ignored output artifacts
   do not violate this check.

Any preflight failure stops before training or final-output creation.

## 6. Training and inference data flow

The local runner performs these steps in order:

1. Validate the normalized panel and audit.
2. Load the frozen feature contract and transform the panel once with
   `Stage3FeatureBuilder`.
3. Load and validate the fixed partition map.
4. For each horizon in `0`, `6`, and `12` months:
   1. Align features at month `t` to `fews_ipc_crisis` at month `t + h`.
   2. Select the 36-month target window ending at `2026-02`, which is
      `2023-03` through `2026-02` for the initial source.
   3. Train with the existing `train_horizon_model` behavior, including its
      threshold-validation split, imputer, SMOTE, partition models, and pooled
      fallback.
   4. Write and validate a local model package.
   5. Reload the package before using it for accepted prediction output.
   6. Select the complete `2026-04` inference frame and call the reloaded
      predictor.
5. Enrich predictions with area identity and population provenance.
6. Validate all three horizons together.
7. Publish final artifacts and write `run_summary.json` last.

The expected target months are:

| Horizon | Feature month | Target month |
| --- | --- | --- |
| `0m` | `2026-04` | `2026-04` |
| `6m` | `2026-04` | `2026-10` |
| `12m` | `2026-04` | `2027-04` |

## 7. Local model package contract

A pure local Python run cannot truthfully satisfy the production model-package
schema because that schema requires a digest-pinned container image. The local
experiment therefore uses a separate `fewsnet-local-model-package-v1` contract
and leaves `fewsnet-model-package-v1` unchanged.

Each horizon package contains:

```text
model.joblib
feature_contract.json
partition_map.csv
threshold_report.json
training_report.json
local_model_manifest.json
checksums.json
```

The local manifest records at least:

- Schema and suite version.
- Horizon key, horizon months, and target month.
- Source panel and audit identities.
- Feature-contract and partition checksums.
- Learned threshold.
- Training and validation target-month ranges.
- `runtime_backend: local_python`.
- Exact Python, NumPy, pandas, scikit-learn, joblib, and imbalanced-learn
  versions.
- Source Git commit.
- Exact package member list and checksums.
- Package status.

The local loader validates the manifest, file inventory, checksums, dependency
compatibility, feature contract, partition identity, threshold report, and
training report before unpickling `model.joblib`.

For reproducibility, the suite version is derived from the feature month,
source Git commit, and normalized-panel digest, for example:

```text
local-202604-{git_commit_12}-{panel_sha256_12}
```

The run ID is separately timestamped so repeated attempts can be audited
without changing the deterministic suite identity.

## 8. Population contract

Population is an output-enrichment field, not a new model prediction and not a
value generated by the model imputer.

For each authoritative `admin_code`, the local runner selects the most recent
non-null source `pop` at or before the feature month. For the approved initial
source:

- 5,716 areas receive their raw last-observed value from `2024-10`.
- Two areas remain missing because they have no non-null source value.
- Missing population is not spatially, statistically, or model-imputed.

The output fields are:

- `population`: raw last-observed value or null.
- `population_reference_period`: source month or null.
- `population_source`: `raw_last_observed` or `missing_raw`.

The two missing administrative codes are recorded explicitly in the run
summary.

## 9. Prediction semantics and output contract

The primary predictive output is one continuous crisis probability:

- `probability_crisis` is finite and in `[0, 1]`.
- It is also the direct expression of model confidence/uncertainty.
- No separate `high`, `medium`, or `low` uncertainty label is produced.
- No IPCCH `phaseX_worse_*` field is produced.

The learned horizon threshold is retained, and the binary label is:

```text
predicted_crisis = int(probability_crisis >= threshold)
```

Each prediction CSV has this ordered logical contract:

1. `admin_code`
2. `ADMIN0`
3. `ADMIN1`
4. `ADMIN2`
5. `ADMIN3`
6. `ISO3`
7. `lat`
8. `lon`
9. `population`
10. `population_reference_period`
11. `population_source`
12. `probability_crisis`
13. `predicted_crisis`
14. `threshold`
15. `cluster_id`
16. `prediction_source`
17. `feature_month`
18. `target_month`
19. `horizon_months`
20. `suite_version`
21. `model_artifact_path`
22. `source_input`

The existing fallback vocabulary remains unchanged:

- `partition_model`
- `pooled_unmapped`
- `pooled_small_partition`
- `pooled_single_class`
- `pooled_missing_partition_model`

Local predictions do not include fake Vertex model resource names or version
IDs.

## 10. Artifact layout

The user-facing prediction layout is:

```text
Outcome/fewsnet_partitioned_rf/
├── predictions/
│   └── 202604/
│       ├── fewsnet_partitioned_rf_202604_scope_0m_predictions.csv
│       ├── fewsnet_partitioned_rf_202604_scope_6m_predictions.csv
│       ├── fewsnet_partitioned_rf_202604_scope_12m_predictions.csv
│       └── run_summary.json
├── model_artifacts/
│   └── {suite_version}/
│       ├── 0m/
│       ├── 6m/
│       └── 12m/
└── reports/
    └── {suite_version}/
        ├── training_threshold_report.json
        └── run_manifest.json
```

This root is independent of `Outcome/ipcch_unified/`. The experiment must not
read from, write to, rename, or remove existing IPCCH prediction artifacts.

## 11. Publication and overwrite behavior

Training, packaging, prediction, and validation occur under a temporary local
run directory. Final paths are published only after all three horizons pass.

Rules:

- Model artifact directories are versioned and create-only. An existing local
  suite may be reused only when its manifest, member inventory, and checksums
  validate against the same source identities; otherwise the run fails.
- Prediction output refuses to overwrite existing files by default.
- An explicit overwrite option applies only to the exact
  `Outcome/fewsnet_partitioned_rf` target supplied by the operator.
- It never authorizes changes under `Outcome/ipcch_unified`.
- Publication uses copy-based behavior suitable for WSL/Dropbox paths.
- `run_summary.json` is written last.
- Consumers treat the output as accepted only when the summary has
  `status: passed` and its recorded checksums match all three CSVs and packages.

A failure may leave temporary evidence, but it must not leave a passed summary
or a mixture that can be mistaken for an accepted run.

## 12. Validation and failure handling

The local runner fails closed if any horizon fails training, packaging,
reloading, prediction, or validation. It does not publish a partial two-horizon
suite.

Each accepted prediction CSV must satisfy:

- Exactly 5,718 rows and 5,718 unique `admin_code` values.
- Identical area set and row order across all three horizons.
- Exact feature and target month semantics.
- Finite probabilities in `[0, 1]`.
- Exact threshold-to-label consistency.
- Valid cluster and prediction-source combinations.
- Exactly 5,716 `raw_last_observed` population rows and two `missing_raw` rows
  for the approved initial source.
- No phase-specific or categorical-uncertainty fields.
- A checksum recorded in the passed run summary.

The run summary records at least:

- Run ID, suite version, start/end timestamps, and status.
- Source Git commit and runtime dependency versions.
- Panel and audit paths, checksums, sizes, and row counts.
- Latest feature and label months.
- Training and validation windows.
- Per-horizon thresholds and row counts.
- Per-horizon fallback counts.
- Population provenance counts and missing administrative codes.
- Model-package and prediction checksums.

## 13. Testing strategy

### 13.1 Unit and contract tests

Tests cover:

- Local package schema, member inventory, checksums, and reload failures.
- Runtime dependency and source-identity recording.
- Latest raw-population selection and the no-imputation rule.
- Prediction column order and prohibited IPCCH fields.
- Probability range and threshold-to-label consistency.
- Target-month calculation for all three horizons.
- Duplicate, missing-area, and cross-scope identity failures.
- Default no-overwrite behavior and passed-summary-last behavior.

### 13.2 Small integration test

A checked-in fixture runs the full local orchestration boundary for all three
horizons. It trains, packages, reloads, predicts, enriches, validates, and
writes artifacts without GCP credentials or network access.

### 13.3 Real-source acceptance run

The final acceptance run uses the complete normalized panel without sampling
or changing the frozen RF parameters. Success requires:

1. Three complete local model packages.
2. Successful package reload before accepted prediction publication.
3. Three prediction CSVs with 5,718 rows each.
4. A passed run summary with matching checksums.
5. No GCP or Vertex write.
6. No modification under `Outcome/ipcch_unified/`.
7. No future-target performance claims.

This acceptance proves the FEWSNET local model chain. It does not require
FEWSNET probabilities or binary labels to match the structurally different
IPCCH model.

## 14. Compatibility and change boundaries

The implementation must preserve these boundaries:

- Existing core feature, training, inference, threshold, partition, and
  production package behavior remains unchanged unless a separately reviewed
  defect is discovered.
- The production model-package and prediction schemas remain unchanged.
- Local-only schemas and adapters are additive.
- Existing Vertex training, registry, prediction, promotion, and release code
  remains callable with its current contracts.
- Existing IPCCH tests and FEWSNET production tests must continue to pass.

## 15. Approved completion condition

The feature is complete when the implementation and tests can run the approved
full local experiment and create the independent `202604` FEWSNET prediction
tree, three reloadable local model packages, reports, and a passed summary under
`Outcome/fewsnet_partitioned_rf/`, with all validation conditions above met.
