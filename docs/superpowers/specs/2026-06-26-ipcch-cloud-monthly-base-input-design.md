# IPCCH Cloud Monthly Base Input Design

Status: approved design for a future full SDD phase.
Date: 2026-06-26

## Purpose

This design defines the first cloud end-to-end phase for the
`IPCCH_monthly_operational` repository. The target is a cloud-run monthly data
pipeline that produces a model-compatible monthly base input CSV, not a full
prediction delivery system.

The first phase should prove that a service-account-driven cloud workflow can
produce:

- EVI cloud extraction evidence.
- EVI wide and long intermediate outputs.
- A monthly `ipcch_monthly_base_input_YYYYMM.csv`.
- A monthly base input summary JSON.
- A released artifact set that remains compatible with the existing fixed-model
  inference CLI.

The phase intentionally stops before running the `launch_2026_04` model package
for full prediction delivery.

## Selected Approach

The selected approach is a monthly base input cloud pipeline:

1. A Cloud Run Job acts as the monthly orchestration entry point.
2. Google Earth Engine Python SDK exports preprocessed EVI rasters to GCS using
   a service account.
3. A GCP Batch worker performs the rasterio/GDAL EVI zonal extraction.
4. Low-risk assembly steps consume versioned cloud inputs and produce the
   monthly base input.
5. GCS stores both immutable run evidence and a stable released version.

This approach is broader than an EVI-only extraction insert because it proves
cloud production of the base input. It is narrower than a full production DAG
because it does not yet automate every external data source, all
remote-sensing families, production monitoring, approval workflows, or model
prediction delivery.

## Decisions

- Scope boundary: monthly data pipeline cloud end-to-end, ending at the base
  input artifact.
- Control plane: Cloud Run Jobs for monthly orchestration.
- Heavy remote-sensing compute: GCP Batch container worker.
- First remote-sensing source: EVI only.
- Tabular/source automation: low-risk assembly and consumption of versioned
  inputs, not full external source download automation.
- Sample depth: 1 to 3 months.
- Authentication: service account for Earth Engine, Cloud Run, Batch, and GCS.
- Artifact layout: immutable `runs/` evidence plus stable `released/` outputs.
- EVI validation: advisory thresholds, not exact ArcPy replication and not
  hard failure for reasonable rasterio/ArcPy differences.
- Base input validation: hard gates because the base input is the direct
  contract for downstream model inference.

## Goals

The future implementation should prove that the cloud workflow can:

- Run without interactive user credentials after service account setup.
- Export selected monthly EVI rasters from Earth Engine to GCS.
- Extract EVI zonal mean and standard deviation without ArcPy.
- Preserve the current EVI wide CSV contract.
- Produce long EVI outputs compatible with monthly assembly.
- Consume versioned fixed, slow, scaffold, and uploaded tabular inputs.
- Build the monthly IPCCH base input in the same contract as the current local
  workflow.
- Store complete run evidence under a run-specific GCS prefix.
- Promote or copy accepted outputs into a stable released prefix.
- Validate the released base input with the existing inference CLI in
  `--validate-only` mode.

## Non-Goals

- No full model inference delivery in this phase.
- No prediction maps, prediction sheets, or delivery package generation.
- No automation of all external tabular downloads such as ACLED, WFP, and FAO.
- No migration of FLDAS, GOSIF-GPP, or VIIRS cloud extraction.
- No hard requirement that rasterio EVI values exactly match ArcPy values.
- No production monitoring, alerting, approval UI, or backfill console.
- No historical replay beyond the 1 to 3 month pilot sample.
- No direct Earth Engine polygon reduction as the main extraction path.

## Architecture

The architecture has three execution units and one artifact store:

```text
Cloud Run Job
    |
    +--> Earth Engine Python export for selected EVI months
    |
    +--> GCP Batch EVI extraction worker
    |       |
    |       +--> reads EVI GeoTIFFs and IPCCH geometry from GCS
    |       +--> writes EVI wide, long, and validation artifacts
    |
    +--> low-risk monthly assembly
            |
            +--> reads versioned tabular/fixed/scaffold inputs
            +--> writes monthly base input and summary

GCS
    |
    +--> runs/<feature_month>/<run_id>/
    |
    +--> released/<feature_month>/
```

Cloud Run owns orchestration, configuration interpretation, job submission,
lightweight validation, release decisioning, and final manifest writing. Cloud
Run should not perform the heavy raster extraction itself.

GCP Batch owns EVI extraction. Its interface should stay narrow: it receives an
explicit manifest or config object, reads raster and geometry inputs, writes
declared artifacts, and exits with a clear status. It should not know about
model inference or prediction delivery.

GCS is the durable evidence store. The `runs/` prefix is append-only for each
run id. The `released/` prefix exposes the currently accepted artifacts for a
feature month.

## Configuration and Manifest

The workflow should be driven by an explicit cloud run manifest. The manifest
is the fact source for a run and should include:

- `feature_month`, such as `2026-04`.
- `run_id`, such as a timestamp or externally supplied release id.
- selected EVI months, with a first-phase range of 1 to 3 months.
- GCS bucket and run/release prefixes.
- Earth Engine collection, band, export region, scale, and output prefix.
- versioned IPCCH geometry object and zone id field.
- versioned fixed/slow features, scaffold, and tabular/source input objects.
- validation threshold settings for EVI advisory checks.
- base input schema expectations.
- release policy, including whether warnings are allowed.

The manifest should avoid local filesystem assumptions. Local paths may remain
in the existing repo for current handover workflows, but the cloud design should
express inputs as GCS URIs plus checksums, vintages, or version labels where
available.

## EVI Cloud Remote-Sensing Flow

The first cloud remote-sensing source is EVI because it is the smallest useful
ArcPy replacement pilot. The current local workflow uses Earth Engine export,
GCS or local download, and `EVI/02_arcpy_extract_evi.py` to write:

- `EVI_mean_extraction_results.csv`
- `EVI_std_extraction_results.csv`

The cloud workflow should preserve those wide outputs while replacing the
ArcPy backend.

The EVI flow is:

1. Cloud Run reads the manifest and starts Earth Engine Python exports for the
   selected EVI months.
2. Earth Engine writes preprocessed monthly GeoTIFFs to the configured GCS
   raster prefix.
3. Cloud Run waits for or polls the export completion state.
4. Cloud Run submits a GCP Batch job with the EVI extraction manifest.
5. Batch reads the selected GeoTIFFs and the versioned IPCCH geometry object.
6. Batch computes zonal mean and standard deviation with rasterio/GDAL and
   geospatial Python libraries.
7. Batch writes EVI wide CSVs, EVI long CSVs, and an advisory validation report
   to the run prefix.

The extraction semantics should be explicit:

- Reproject polygons to the raster CRS before extraction.
- Ignore raster nodata and NaN values.
- Use center-based pixel inclusion by default.
- Keep rows for empty zones and record missing values.
- Sort output rows by id and monthly columns chronologically.
- Use the existing `YYYY_MM` month column convention for EVI wide CSVs.

The long outputs should use the current monthly assembly shape:

```text
area_id,year,month,EVI_mean
area_id,year,month,EVI_std
```

## Low-Risk Monthly Assembly Flow

The first phase should not automate every external source download. Instead, it
should consume already uploaded and versioned input objects for source families
that are still manually refreshed or externally supplied.

The cloud assembly layer should cover low-risk automation:

- target-month scaffold selection or construction.
- fixed and slow area feature loading.
- historical/source panel selection for the target month when available.
- inclusion of cloud-produced EVI long outputs.
- schema validation and QA summary writing.
- monthly base input CSV writing.

The target output remains:

```text
ipcch_monthly_base_input_YYYYMM.csv
ipcch_monthly_base_input_YYYYMM_summary.json
```

The resulting CSV must keep the current contract used by the existing
operational launch inference CLI. In the first phase, a successful cloud run
should end by running the inference CLI in `--validate-only` mode against the
released or run-prefix base input. It should not run full scoring or prediction
delivery.

## Artifact Layout

All artifacts should first be written under an immutable run prefix:

```text
gs://<bucket>/ipcch-cloud/runs/<feature_month>/<run_id>/
```

Recommended run-prefix contents:

```text
manifest.json
inputs/
  input_manifest.json
evi/
  rasters_manifest.json
  EVI_mean_extraction_results.csv
  EVI_std_extraction_results.csv
  EVI_mean_monthly_long.csv
  EVI_std_monthly_long.csv
  evi_validation_report.json
assembly/
  ipcch_monthly_base_input_YYYYMM.csv
  ipcch_monthly_base_input_YYYYMM_summary.json
qa/
  base_input_validation_report.json
  inference_validate_only_report.json
run_summary.json
```

After hard gates pass, accepted artifacts should be copied to or registered
under:

```text
gs://<bucket>/ipcch-cloud/released/<feature_month>/
```

Recommended released-prefix contents:

```text
release_manifest.json
ipcch_monthly_base_input_YYYYMM.csv
ipcch_monthly_base_input_YYYYMM_summary.json
evi_validation_report.json
EVI_mean_monthly_long.csv
EVI_std_monthly_long.csv
```

The released manifest should point back to the immutable run prefix and record
any advisory warnings that were accepted.

## Validation

EVI validation uses advisory thresholds. The report should include:

- expected and observed zone row counts.
- unique id checks for `region_id` and mapped `area_id`.
- missing-rate summaries overall and by month.
- ArcPy sample comparison for matched month and zone pairs where available.
- distribution comparisons using min, p5, p25, median, p75, p95, and max.
- Pearson and Spearman correlations for matched non-missing observations.
- largest absolute and relative differences.
- a list of zones needing manual review.

EVI advisory warnings should not automatically fail the run unless the output
contract itself is broken. Examples of advisory warnings are moderate
distribution shifts, localized missingness changes, or outlier polygons that
can be reviewed.

Base input validation uses hard gates. The run should fail and not update the
released prefix if:

- the target scaffold is missing or has duplicate keys.
- required base input columns are missing.
- `area_id`, `year`, and `month` are not unique.
- the output has no rows.
- the monthly summary JSON is missing.
- schema validation fails.
- inference CLI `--validate-only` rejects the output.

The base input validation should record row counts, required-column coverage,
missingness summaries, input vintages, and join coverage.

## Error Handling

The workflow should distinguish retryable failures, contract failures, and
advisory warnings.

Retryable failures include:

- Earth Engine export tasks still running.
- transient GCS read or write failures.
- transient Batch startup or worker failure.

Contract failures include:

- missing GCS input objects.
- ambiguous raster matches for a selected month.
- unreadable geometry.
- missing or duplicated zone ids.
- unsupported or unparseable EVI month columns.
- empty EVI wide or long output.
- base input schema failure.

Advisory warnings include:

- EVI values differing from ArcPy sample beyond suggested review thresholds.
- explainable missingness differences.
- outlier zones that need human review.

Contract failures should fail the run and leave the released prefix unchanged.
Advisory warnings may still allow release if the release policy allows warnings
and the run manifest records them clearly.

## Security and Operations

The target runtime identity is a service account. After one-time setup, the
pipeline should not depend on a personal Earth Engine or GCP token.

The service account should have the least permissions needed to:

- run the Cloud Run Job.
- create or monitor Earth Engine export tasks.
- submit and monitor GCP Batch jobs.
- read configured GCS input prefixes.
- write configured run and released prefixes.
- write logs.

Secrets should not be baked into container images. Runtime settings should come
from Cloud Run job arguments, environment variables, or a GCS manifest object.

## Testing Strategy

Testing should happen in three layers.

### Unit and Contract Tests

These tests should cover:

- manifest parsing.
- month parsing and `YYYYMM` or `YYYY-MM` normalization.
- GCS URI validation.
- EVI wide-to-long conversion.
- duplicate id detection.
- required-column checks.
- release manifest structure.

### Container Smoke Tests

The EVI Batch container should run against a small raster fixture and a small
geometry fixture without ArcPy. The smoke test should prove that it can write
mean and standard deviation wide CSVs, long CSVs, and a validation report.

The assembly container or Cloud Run image should run against small CSV fixtures
and produce a valid monthly base input plus summary JSON.

### Cloud Pilot Test

The pilot cloud test should run with a service account for 1 to 3 months. It
should write all evidence to `runs/<feature_month>/<run_id>/`, produce EVI
advisory validation, produce the base input and summary, and update
`released/<feature_month>/` only when hard gates pass.

The final pilot check should run the existing inference CLI in
`--validate-only` mode against the cloud-produced base input. Full prediction
generation remains out of scope.

## Acceptance Criteria

The phase is complete when:

- Cloud Run Job can run non-interactively with the service account.
- Earth Engine Python export writes selected EVI rasters to GCS.
- GCP Batch extraction writes EVI wide and long outputs without ArcPy.
- EVI advisory validation report is written and linked from the run summary.
- Versioned fixed, slow, scaffold, and tabular/source inputs are consumed from
  the manifest.
- The cloud workflow writes `ipcch_monthly_base_input_YYYYMM.csv` and
  `ipcch_monthly_base_input_YYYYMM_summary.json`.
- Hard validation gates pass for the base input.
- The released prefix is updated only after hard gates pass.
- The released manifest points back to the run prefix and records advisory
  warning state.
- The existing inference CLI accepts the base input in `--validate-only` mode.

## Future Phases

After this phase, the project can consider separate specs for:

- full model inference and prediction delivery in cloud.
- VIIRS cloud extraction, including mosaic and tile semantics.
- FLDAS and GOSIF-GPP cloud extraction.
- automated ACLED, WFP, FAO, and other external source refresh.
- production monitoring, notifications, approval, and rollback.
- historical replay and backfill controls.
