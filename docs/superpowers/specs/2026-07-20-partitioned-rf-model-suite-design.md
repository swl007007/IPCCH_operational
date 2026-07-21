# FEWSNET Partitioned RF Model Suite Design

**Date:** 2026-07-20

**Status:** Approved design; bootstrap normalization amendment approved

**Pipeline root:** `fewsnet_partitioned_rf_pipeline/`

## 1. Purpose

Add an independent FEWSNET model suite to the operational repository. The new
pipeline implements only the fixed-partition Stage 3 Random Forest behavior
needed for production training and inference. It trains three binary crisis
models for 0-, 6-, and 12-month horizons, registers them in Vertex AI Model
Registry, runs Vertex AI Batch Prediction for the latest valid feature month,
and publishes one internally consistent production suite.

The existing IPCCH pipeline remains unchanged. The research checkout
`Food_Crisis_Cluster` is a reference implementation and provenance source only;
the production runtime must not import it or invoke it through an absolute
Windows path.

## 2. Confirmed source evidence

The initial source data is:

```text
C:\Users\swl00\IFPRI Dropbox\Weilun Shi\Google fund\Analysis\1.Source Data\assembled_FEWSNET\FEWSNET_forecast_unadjusted_bm_2025_combined.csv
```

Observed on 2026-07-20:

- 1,120,730 panel rows.
- 5,718 unique FEWSNET areas.
- Latest feature month: `2026-04`.
- Latest month with non-null `fews_ipc_crisis`: `2026-02`.
- Native binary target: `fews_ipc_crisis`.

The raw combined CSV contains two duplicate normalized
`FEWSNET_admin_code + month` groups, both for admin `2996`:

- `2025-10`: two rows differ only in the already-derived
  `Tair_zscore` and `Rainf_zscore` values.
- `2026-02`: two rows are identical across every audited column.

The approved bootstrap normalization collapses those two groups before the
notebook-compatible climate rolling/z-score calculation. The expected cleaned
panel has 1,120,728 rows, 5,718 areas, latest feature month `2026-04`, and
latest label month `2026-02`. The raw combined CSV is retained byte-for-byte;
the normalized result and its audit are written as new versioned files, for
example:

```text
FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.csv
FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.audit.json
```

The initial spatial source is:

```text
C:\Users\swl00\IFPRI Dropbox\Weilun Shi\Google fund\Analysis\1.Source Data\Outcome\FEWSNET_IPC\FEWS NET Admin Boundaries\FEWS_Admin_LZ_v3.shp
```

Observed spatial contract:

- 5,718 polygons.
- Join key: `admin_code`.
- CRS: EPSG:4326.

These local paths are bootstrap/provenance inputs. Vertex AI runtime jobs must
consume immutable GCS object references rather than local workstation paths.

## 3. Scope

### 3.1 In scope

- A new top-level `fewsnet_partitioned_rf_pipeline/` namespace.
- Fixed general partition routing with 17 clusters.
- One pooled fallback RF and cluster-specific RFs for each horizon.
- True 0-, 6-, and 12-month feature-to-target alignment.
- Rolling 36-month labeled training windows.
- Per-partition SMOTE when valid.
- One global class-1 probability threshold per horizon selected on the latest
  six labeled target months.
- One Vertex AI Custom Job that trains the complete three-horizon suite.
- Three stable Vertex AI parent models, one per horizon.
- A new Model Version under each parent for each successful retraining run.
- One shared, digest-pinned custom container image for training and prediction.
- Vertex AI Batch Prediction only; no persistent online endpoints.
- Immutable model packages, prediction CSVs, reports, and suite manifests in
  GCS.
- Candidate validation, alias promotion, rollback, and an authoritative
  production suite pointer.

### 3.2 Out of scope

- Stage 1 or Stage 2 partition discovery and optimization.
- Recomputing partitions from spatial geometry during routine runs.
- Month-specific partition maps.
- Pooled-model benchmark publication.
- The legacy 1/4/8/12-month schedule.
- Online Vertex AI endpoints.
- Prediction maps or Excel workbooks.
- Performance metrics for future target months that do not yet have labels.
- Dropbox API integration or recurring Dropbox-to-GCS synchronization.
- Runtime dependencies on the external `Food_Crisis_Cluster` checkout.
- Refactoring or changing the existing IPCCH model and release pipeline.

## 4. Chosen architecture

```text
fewsnet_partitioned_rf_pipeline/
├── cli/
│   ├── normalize_panel.py       # one-time/versioned bootstrap normalization
│   ├── stage_snapshot.py        # optional administrative bootstrap only
│   ├── train.py
│   ├── infer.py
│   └── run_latest.py
├── core/
│   ├── data.py
│   ├── normalization.py
│   ├── horizons.py
│   ├── partitions.py
│   ├── preprocessing.py
│   ├── training.py
│   ├── thresholds.py
│   ├── inference.py
│   ├── package.py
│   └── validation.py
├── vertex/
│   ├── training_job.py
│   ├── predictor_server.py
│   ├── registry.py
│   ├── batch_prediction.py
│   └── promotion.py
├── assets/
│   └── partitions/
├── schemas/
└── tests/
```

The modules are separated by contract:

- `core/` contains platform-independent model behavior.
- `vertex/` contains Google Cloud and Vertex AI adapters.
- `cli/` contains entrypoints and orchestration commands.
- `assets/` holds the fixed partition asset and its provenance.
- `schemas/` defines machine-readable input, normalization-audit, package,
  prediction, report, and suite manifest contracts.

The new pipeline uses an environment-configured GCS root whose final path
component is reserved for this suite, for example:

```text
gs://food-crisis-modeling-artifacts/fewsnet_partitioned_rf/
```

No artifacts are mixed with the IPCCH pipeline's model or release roots.

## 5. Fixed partition contract

The canonical partition source is:

```text
Food_Crisis_Cluster/
paper_reproducibility_package/stage3_results/georf_fs1/refined/
cluster_mapping_k40_nc17_general_refined_contig3.csv
```

The same named asset under `georf_fs1`, `georf_fs2`, and `georf_fs3` is byte
identical. The production copy must preserve this evidence:

- SHA-256:
  `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- 5,365 mapped FEWSNET areas.
- Cluster IDs `0` through `16`.
- 17 total clusters.

The production asset is copied into the new pipeline and then included in each
model package. Its manifest records the original reference path, source Git
commit (`1ecf180669568bbf9eb2129683108162902a415a` at design time), checksum,
row count, cluster count, and expected coverage.

Prediction routing is an `admin_code` lookup. Vertex prediction workers do not
perform geometry joins. The normalized spatial snapshot is used to validate
the area universe and enrich administrative identity, not to derive a new
partition.

For the initial 5,718-area snapshot, 353 areas are intentionally unmapped and
use the pooled RF. A coverage decrease of more than two percentage points from
the packaged baseline blocks production release by default. This detects a
material boundary-system change while retaining explicit pooled fallback for
the known unmapped areas.

## 6. GCS-first input contract

The recurring model workflow begins with an immutable GCS snapshot, not a
local file path:

```text
inputs/snapshots/{snapshot_id}/
├── assembled_fewsnet.normalized.csv
├── panel_normalization_audit.json
├── admin_boundaries.parquet
├── admin_universe.csv
└── source_manifest.json
```

The original shapefile component files may also be archived for provenance.
Runtime validation uses normalized GeoParquet and `admin_universe.csv`.

`source_manifest.json` includes at least:

- Snapshot ID and creation timestamp.
- Exact GCS URI and generation for every object.
- SHA-256, size, and row count for the normalized assembled panel.
- Exact normalization-audit object reference. The referenced audit records the
  normalization version, raw input checksum/row count, cleaned output
  checksum/row count, duplicate-group evidence, and removed-row count.
- Unique area count.
- Spatial feature count and CRS.
- Source identity fields and canonical `admin_code` mapping.
- Latest valid feature month.
- Latest non-null target month.
- Schema version.

The producer that synchronizes new source data into the GCS landing area is a
separate concern. Before the initial snapshot is staged, an administrative
normalization command writes a new versioned CSV and audit JSON without
overwriting the raw source. It performs these operations in order:

1. Read the raw CSV while preserving source column order and original row
   identity.
2. Normalize the admin identity and month key, then stably sort by
   `FEWSNET_admin_code`, `date`, and original row order, matching the reference
   notebook's admin/date ordering.
3. For every duplicate area-month group, compare all source columns with
   missing values treated as equal, excluding only `Tair_zscore` and
   `Rainf_zscore` from the equality check.
4. Collapse the group to its first stably sorted row only when every compared
   field is equal. If any other field conflicts, fail before writing either
   output.
5. Recompute the notebook's climate derivations after deduplication: global
   continuous 12-row rolling means with `min_periods=1` for
   `Tair_f_tavg_mean` and `Rainf_f_tavg_mean`, followed by within-admin sample
   z-scores for `Tair_zscore` and `Rainf_zscore`. The temporary `_m12` columns
   are not retained.
6. Write the cleaned CSV with the original source-column order and write an
   audit JSON containing raw/output checksums and sizes, raw/output row counts,
   duplicate keys, compared/excluded columns, removed rows, and the exact
   derivation parameters.

Snapshot staging accepts only the normalized CSV plus its matching audit. It
verifies that the audit's output checksum and row count match the supplied
panel, uploads the audit as an immutable snapshot member, and includes the
audit checksum in `snapshot_content_sha256`. An optional administrative staging
command can then bootstrap the initial snapshot from the approved local
sources, but monthly Vertex training and inference do not depend on that
workstation.

`run_latest` selects the newest valid snapshot. If its feature month and input
checksum already correspond to a successful production suite, the run is an
idempotent no-op. A newer feature month triggers retraining. A corrected input
with the same feature month requires an explicit revision mode and produces a
new suite version; it never overwrites the previous suite.

## 7. Horizon alignment and training window

For horizon `h`, samples follow the explicit relationship:

```text
features at month t -> fews_ipc_crisis at month t + h
```

The horizons are `0`, `6`, and `12` months. All three use the same latest
labeled target month and the same 36-month target-month window. Feature months
are shifted backward by the selected horizon.

For the initial snapshot:

| Horizon | Inference feature month | Prediction target month |
| --- | --- | --- |
| 0m | 2026-04 | 2026-04 |
| 6m | 2026-04 | 2026-10 |
| 12m | 2026-04 | 2027-04 |

The latest labeled target month is `2026-02`, so the current 36-month training
target window is `2023-03` through `2026-02`. Missing aligned rows are dropped
with counts and reasons recorded by horizon; rows must never be aligned by
unkeyed positional shifting.

Panels are sorted and keyed by canonical area identity plus month before
alignment. The narrow bootstrap normalizer is the only component allowed to
collapse approved derived-only duplicates. `inspect_panel`, snapshot staging,
feature preparation, and horizon alignment continue to reject every duplicate
area-month row as a hard input failure.

## 8. Feature and preprocessing contract

Each horizon stores an ordered, immutable feature allowlist. Training, local
inference, custom-container inference, and Batch Prediction must all enforce
the same order and numeric types. They consume only a snapshot whose normalized
panel and normalization audit passed the GCS-first input contract; runtime
feature code never performs implicit deduplication.

The initial allowlist is materialized as a versioned asset such as
`assets/feature_contracts/fewsnet_stage3_v1.json`. It is generated from the
approved initial snapshot using the parity feature-preparation path and checked
against the reference repository's recorded feature order. New source columns
never enter the model automatically. Adding, removing, or reordering a model
feature requires an explicit new feature-contract version and therefore a new
model suite version.

To preserve the approved Stage 3 behavior, variables explicitly present in the
frozen reference feature list remain predictors, including
`FEWSNET_admin_code`, `lat`, `lon`, and `month`. Canonical `admin_code` remains a
separate row identity and partition-routing field even when the reference
administrative code is also retained as a numeric predictor.

Preprocessing rules are:

1. Coerce declared feature columns to numeric values.
2. Convert positive and negative infinity to missing values.
3. Fit the reference-compatible `max_plus` imputer with multiplier `100.0` on
   the permitted fit slice only.
4. Transform validation and inference data with the fitted imputer.
5. Do not scale features; RF does not require scaling.
6. Reject missing required features, duplicate feature names, non-coercible
   values, or a feature schema checksum mismatch.

The imputer is serialized inside the model package so preprocessing cannot
drift between training and prediction. Fitting the imputer on the entire panel
before temporal validation is prohibited.

## 9. Random Forest and fallback behavior

The fixed RF parameters are:

```text
n_estimators = 100
max_depth = None
random_state = 5
n_jobs = 1
```

For each horizon:

1. Train one pooled RF on all aligned training observations.
2. For each mapped cluster, inspect the cluster-specific training subset.
3. Use pooled fallback when the cluster has fewer than 50 samples.
4. Use pooled fallback when the cluster contains only one target class.
5. Otherwise apply SMOTE within that cluster when both classes are present and
   the minority class has at least two samples.
6. Set SMOTE `k_neighbors` to `min(5, minority_count - 1)`.
7. If SMOTE is unavailable, invalid for the subset, or fails, train the
   partition RF on the original cluster sample and record the reason.

SMOTE is never applied to the temporal threshold-validation rows or inference
rows. The pooled model is not a published benchmark; it exists solely as an
internal fallback model.

Every cluster has a recorded final state, sample count, class distribution,
SMOTE status, and fallback reason.

## 10. Threshold selection

Each horizon selects one global threshold for its partition-routed class-1
probabilities.

1. Hold out the latest six target months from the 36-month training window.
2. Fit temporary pooled and partition models on the earlier 30 target months.
3. Generate partition-routed crisis probabilities for the six held-out months.
4. Search thresholds from `0.05` through `0.95` inclusive in increments of
   `0.01`.
5. Maximize class-1 F1.
6. If multiple thresholds share the maximum F1, choose the highest threshold.
7. If threshold selection is impossible because there are no valid validation
   observations, no positive validation cases, or no finite metric, use `0.50`
   and record the fallback reason.
8. Refit the pooled and partition models on the complete 36-month window after
   selecting the threshold.

Only this historical validation performance is reported. The pipeline does
not invent metrics for unlabeled 2026-04, 2026-10, or 2027-04 targets.

## 11. Model package format

Each horizon is stored under an immutable artifact URI:

```text
model_artifacts/{suite_version}/{0m|6m|12m}/
├── model.joblib
├── model_manifest.json
├── feature_contract.json
├── partition_map.csv
├── threshold_report.json
├── training_report.json
└── checksums.json
```

`model.joblib` serializes one `PartitionedRFPredictor` containing:

- Fitted `max_plus` imputer.
- Pooled fallback RF.
- Cluster-to-model mapping.
- Cluster fallback states.
- Fixed `admin_code` partition routing map.
- Ordered feature list.
- Selected threshold.
- Horizon and schema metadata.

The separate JSON and CSV files make the package inspectable without
unpickling it. `checksums.json` covers every package member.

The manifest pins at least:

- Python version.
- scikit-learn version.
- NumPy version.
- joblib version.
- imbalanced-learn version or explicit absence.
- Source Git commit.
- Shared container image URI and digest.
- Input snapshot ID and checksums.
- Feature schema checksum.
- Partition checksum.
- Training and validation target-month ranges.
- Selected threshold.

The custom container must reject a package whose schema, dependency contract,
or checksum validation fails.

## 12. Shared Vertex container

One digest-pinned Artifact Registry image supplies both runtime modes:

- Vertex AI Custom Job training entrypoint.
- Vertex AI custom prediction HTTP server.

Different commands select the mode. Using the same image guarantees that the
class definitions and serialization dependencies used to write `model.joblib`
are present when it is loaded.

The prediction server follows the Vertex custom-container contract:

- Listen on `AIP_HTTP_PORT`.
- Implement `AIP_HEALTH_ROUTE`.
- Implement `AIP_PREDICT_ROUTE`.
- Resolve the registered artifact from `AIP_STORAGE_URI`.
- Localize and validate the artifact once at startup.
- Report healthy only after the model, partition map, feature contract, and all
  checksums pass.

The server is stateless after startup and supports batches of standard Vertex
instances. The model resource fixes the horizon, so prediction requests do not
accept a horizon parameter.

Example request shape:

```json
{
  "instances": [
    {
      "admin_code": "123",
      "feature_month": "2026-04",
      "feature_a": 1.2
    }
  ]
}
```

Each prediction contains at least:

```json
{
  "admin_code": "123",
  "probability_crisis": 0.73,
  "predicted_crisis": 1,
  "threshold": 0.41,
  "cluster_id": 7,
  "prediction_source": "partition_model"
}
```

## 13. Vertex Model Registry contract

The registry has three stable parent models:

```text
fewsnet-partitioned-rf-0m
fewsnet-partitioned-rf-6m
fewsnet-partitioned-rf-12m
```

One Vertex AI Custom Job trains all horizons against one immutable input
snapshot and one code/image version. It writes all three candidate artifacts.
Registration begins only after all three packages pass offline validation.

The suite version is immutable and includes the feature month plus code and
data identity, for example
`fewsnet-prf-202604-{git8}-{datahash8}-{runstamp}`. Vertex version IDs use the
same identity after applying Vertex's identifier character rules; the complete
unsanitized suite version remains in the manifests.

Each package is uploaded as a new Model Version under its horizon's stable
parent model. All three versions reference the same serving image digest but a
different immutable `artifactUri`.

The Model Version metadata records or references:

- Suite version.
- Feature and latest-label month.
- Horizon and target month.
- Git commit and image digest.
- Input snapshot checksum.
- Partition and feature schema checksums.
- Threshold.
- Training window.
- Fallback cluster count.

Low-cardinality values may be duplicated into Vertex labels. Full metadata is
authoritative in the model and suite manifests to avoid Vertex label length or
character restrictions.

New versions first receive candidate lifecycle metadata in the suite manifest
and Vertex labels where allowed. A shared `candidate` alias is not required.
Batch Prediction always references the exact candidate version resource name,
never an alias.

## 14. Vertex Batch Prediction contract

There are three Batch Prediction Jobs per suite, one per horizon. No persistent
Vertex Endpoint is created.

The latest feature-month panel is converted to GCS JSONL with one instance per
area. Raw Vertex JSONL outputs are retained as run evidence and normalized into
one formal CSV per horizon.

Each formal CSV contains at least:

- `admin_code`
- `feature_month`
- `target_month`
- `horizon_months`
- `probability_crisis`
- `predicted_crisis`
- `threshold`
- `cluster_id`
- `prediction_source`
- `suite_version`
- `vertex_model_resource_name`
- `vertex_model_version_id`

Allowed `prediction_source` values are:

- `partition_model`
- `pooled_unmapped`
- `pooled_small_partition`
- `pooled_single_class`
- `pooled_missing_partition_model`

SMOTE skip or failure is training metadata and does not by itself change
`prediction_source` when a partition-specific RF was successfully trained.

Output validation requires:

- Exactly one row per area in the authoritative snapshot universe.
- 5,718 unique rows for the current initial snapshot.
- No missing or out-of-range probabilities.
- `predicted_crisis == (probability_crisis >= threshold)`.
- Valid cluster and prediction-source combinations.
- Fallback counts that reconcile to the full row count.
- Exact model version, input generation, and suite identity.

## 15. Suite promotion and release

Vertex does not provide one transaction across aliases on three parent models.
The pipeline therefore uses a two-phase suite promotion:

1. Train and validate all three packages.
2. Register all three candidate Model Versions.
3. Run and validate all three Batch Prediction Jobs.
4. Capture the previous production version of each parent model.
5. Under the generation-safe promotion lease, re-read the authoritative
   production pointer and repeat the same-month digest/revision authorization.
6. Move each horizon's `production` alias to its validated candidate.
7. If any alias operation fails, restore every alias already changed.
8. Write the immutable suite manifest.
9. Write the production suite pointer last.

The authoritative cross-model production state is the production suite
manifest, not the eventual state of any one alias in isolation.

The current pointer, feature-month pointer, and promotion lease are optional
state during an initial release. At those explicit optional-read boundaries,
both local `FileNotFoundError` and production GCS
`google.api_core.exceptions.NotFound` mean that no prior object exists and its
captured generation is zero. Permission, checksum, generation, and every other
storage failure remain hard errors.

Candidate versions and evidence from failed runs are retained and are not
automatically deleted. Only versions known not to be live production may be
marked `failed` or `abandoned`. If publication is indeterminate, or the
authoritative pointer may already reference the suite, lifecycle labels remain
unchanged until production state is reconciled.

## 16. GCS run and release layout

```text
runs/{run_id}/
├── input_snapshot_ref.json
├── inputs/
│   └── selected_source_manifest.json # exact-generation bytes copied immutably
├── training/
├── registry/
├── batch_prediction/
│   ├── 0m/
│   ├── 6m/
│   └── 12m/
├── predictions/
├── training_threshold_report.json
├── run_manifest.json
└── error.json                    # failed runs only

suites/{suite_version}/
├── models/
│   ├── 0m/
│   ├── 6m/
│   └── 12m/
├── predictions/
├── training_threshold_report.json
└── suite_manifest.json

released/{feature_month}/production_suite_manifest.json
released/current.json
```

The four primary v1 deliverable families are:

1. One versioned three-model package.
2. Three per-area prediction CSVs.
3. One aggregate training and threshold report.
4. One run/suite manifest.

Raw Batch Prediction data, service logs, and API responses are retained as
operational evidence but are not primary delivery artifacts.

## 17. Run states and failure handling

Deployment/source validation and snapshot discovery are preflight operations.
The formal run identity begins only after discovery has selected schema-valid,
exact-generation snapshot evidence and the pipeline can derive `run_id` and
`suite_version`. A preflight failure returns and logs a structured error and
causes a nonzero CLI exit, but does not create `error.json` or
`run_manifest.json`, invent placeholder snapshot evidence, or allocate a fake
run identity.

The run manifest records a monotonic state transition such as:

```text
DISCOVERED
INPUT_VALIDATED
TRAINING
PACKAGED
REGISTERED_CANDIDATE
BATCH_PREDICTING
OUTPUT_VALIDATED
PROMOTING
RELEASED
```

Terminal non-success states are `NOOP` and `FAILED`.

Failure rules are:

- After formal run identity exists, every terminal failure writes `error.json`
  and attempts a terminal `run_manifest.json` using generation preconditions.
  An ambiguous manifest write may be adopted only after an advanced generation
  is read exactly and its bytes match the intended canonical payload.
- If an ambiguous `run_manifest.json` readback is mismatched or unreadable, the
  pipeline must not adopt or overwrite that unknown generation. It returns a
  structured formal-run `FAILED` result with `preflight: false`,
  `evidence_indeterminate: true`, `run_id`, `suite_version`, the original
  failure, and an explicit terminal-manifest evidence warning/error. It must
  not claim that the terminal manifest was persisted, and the CLI still exits
  nonzero without reclassifying the established run as preflight.
- Invalid schema, checksum, duplicate area-month rows, or invalid area identity
  fails before training.
- A raw duplicate group with a conflict outside `Tair_zscore` and
  `Rainf_zscore` fails bootstrap normalization before any cleaned panel or audit
  is published.
- A missing, mismatched, or unverifiable normalization audit fails snapshot
  staging; raw unnormalized panels are not accepted as runtime snapshots.
- Any horizon training or package failure prevents suite registration.
- Any candidate registration failure prevents Batch Prediction and promotion.
- Any Batch Prediction or output-validation failure prevents all promotion.
- Partial alias promotion triggers rollback and leaves the prior production
  pointer unchanged.
- A model-load or checksum failure keeps the prediction container unhealthy and
  fails the Vertex job.
- Missing required prediction features fail the request/job rather than being
  silently filled outside the serialized preprocessing contract.
- Retries are limited to transient cloud/API failures and must reuse the exact
  same input generation, image digest, artifact URI, and candidate model
  version.
- Training and Batch submission retries reconcile a deterministic operation
  identity through the production adapter: reuse one exact matching created
  job, submit only when none exists, and fail closed on multiple or mismatched
  matches after an ambiguous commit-then-raise response.
- No retry silently switches to another model or source snapshot.
- A failure before promotion may mark only definitively non-production
  candidates abandoned. `PromotionIndeterminate`, or an evidence-write failure
  after `RELEASED`, must preserve candidate lifecycle labels and surface the
  indeterminate/evidence-warning state without destructive recovery.

Row-level pooled fallback is an expected model behavior and must remain visible
in outputs; it is not treated as an infrastructure failure.

## 18. Testing strategy

### 18.1 Data and horizon tests

- Derived-only duplicate collapse before rolling/z-score recomputation.
- Conflict outside the two approved z-score columns fails closed.
- Raw-source non-overwrite, deterministic cleaned row/column order, and audit
  checksum/row reconciliation.
- Notebook-order rolling/z-score parity on a frozen small fixture.
- Snapshot identity includes the immutable normalization audit, and staging
  rejects a cleaned panel whose bytes or row count do not match that audit.
- True 0/6/12-month alignment by area and calendar month.
- 36-month target-window boundaries.
- Latest-six-month threshold split.
- Non-contiguous months and missing aligned targets.
- Duplicate area-month rejection.
- Latest feature and target month discovery.
- Idempotent no-op and explicit same-month revision behavior.

### 18.2 Model behavior tests

- Imputer fit occurs only on the fit slice.
- SMOTE sees only permitted cluster training rows.
- Dynamic SMOTE neighbor count.
- Small, single-class, unmapped, and missing-partition fallback paths.
- Threshold search bounds, step, metric, tie-breaking, and `0.50` fallback.
- Probability-to-class consistency.
- Fixed-seed reproducibility.
- Serialization round trip for the composite predictor.

### 18.3 Reference parity tests

On the same already-prepared feature matrix, targets, groups, RF parameters,
and random seed, compare the new implementation with the reference functions:

- `train_partitioned_model`
- `predict_partitioned_probability`

Partition/fallback routing and predicted classes must match exactly;
probabilities must match within a strict numeric tolerance. The deliberate
production corrections—0/6/12 alignment and fit-slice-only imputation—are
tested against their own explicit contracts rather than against the legacy
schedule or leakage-prone preprocessing order.

Bootstrap climate normalization has its own parity fixture. On the same sorted,
deduplicated rows, the new implementation must reproduce the reference
notebook's global 12-row rolling means and within-admin z-scores within a strict
numeric tolerance. This test does not permit general duplicate suppression in
the recurring runtime path.

### 18.4 Package and Vertex contract tests

- JSON Schema validation for all manifests and reports.
- Artifact checksum and dependency compatibility failures.
- Prediction-container health and prediction routes.
- Exact model-version references in Batch Prediction requests.
- Stable parent model and new-version upload behavior.
- Candidate alias handling and rollback.
- Confirmation that no online Endpoint is created.
- Fake/local GCS tests and mocked Vertex API tests.

### 18.5 Live GCP smoke test

An optional gated smoke test uploads or references a small immutable snapshot,
registers disposable candidate versions, runs Batch Prediction, validates the
normalized outputs, and leaves production aliases untouched.

## 19. Initial production acceptance criteria

The first complete production run is accepted only when:

1. The raw panel remains byte-identical to its pre-normalization checksum.
2. The versioned normalized panel contains exactly 1,120,728 rows and 5,718
   areas, with two recorded duplicate groups and two removed rows.
3. The normalization audit proves that only derived-only-compatible duplicates
   were collapsed and that the cleaned panel checksum/row count match the
   snapshot panel object.
4. The cleaned panel passes the unchanged duplicate area-month hard gate, and a
   real-boundary local-store staging run completes without any GCP write.
5. The input manifest resolves to the approved immutable current snapshot and
   includes the exact normalization-audit generation.
6. The fixed partition checksum matches the approved checksum.
7. One Custom Job produces all three valid model packages.
8. Three new Vertex Model Versions are registered under the expected parent
   models.
9. All versions use the expected custom serving image digest and artifact URI.
10. All three candidate Batch Prediction Jobs succeed.
11. Each current output CSV contains 5,718 unique areas.
12. Local composite-predictor, local container, and Vertex Batch outputs agree
   on a fixed sample.
13. All prediction probabilities, classes, routes, and fallback totals validate.
14. No online Endpoint, map, workbook, or future-target performance artifact is
    created.
15. The three production aliases and final suite manifest refer to the same
    suite version.
16. `released/current.json` is written last and points to the accepted immutable
    production suite manifest.

## 20. Repository safety and implementation gate

This document approves the design only. It does not authorize implementation
inside the brainstorming phase.

The implementation plan must preserve the existing dirty-worktree changes and
keep the IPCCH pipeline unchanged. Before modifying any existing function,
class, or method, the implementer must run GitNexus upstream impact analysis
and report the blast radius. Before any commit, the implementer must run
GitNexus `detect_changes()` and verify the affected scope. New isolated files
are preferred where they satisfy the design without changing existing
execution flows.
