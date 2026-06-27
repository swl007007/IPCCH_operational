# Feature Specification: IPCCH Cloud Monthly E2E Feature Input and Inference

**Feature Branch**: `001-cloud-base-input`
**Created**: 2026-06-26
**Status**: Draft
**Input**: User description: "Patch the current Feature Specification for 001-cloud-base-input to become plan-ready for a fully cloud-native GCP monthly E2E run with EVI processing, monthly feature/base input assembly, Vertex AI custom-job inference, machine-checkable output contracts, and traceable release artifacts."

## Clarifications

### Session 2026-06-26

- Q: What v1 default timeout and retry policy should govern GEE export polling, Cloud Batch worker execution, and Vertex AI custom-job inference? → A: A - GEE poll 60s; GEE export timeout 6h; Cloud Batch timeout 8h; Vertex AI custom job timeout 2h; max 2 retries.
- Q: What v1 pixel inclusion rule should rasterio use for EVI zonal statistics? → A: B - `all_touched=false`; only pixels whose centers fall inside the polygon are included.
- Q: What v1 service-account permission model should the cloud workflow require? → A: A - split least-privilege service accounts for Cloud Run, Cloud Batch, and Vertex AI custom job.
- Q: Which accepted artifacts must be copied into the immutable released run prefix versus referenced from immutable run evidence or model package locations? → A: A - copy base input, summary, prediction CSVs, validation reports, inference reports, release step report, and manifests; reference GEE raster, EVI evidence, logs, and model package by immutable URI/generation/checksum.

## Scope Boundaries

This feature defines one fully cloud-native monthly run for one selected feature
month. It starts from cloud-declared inputs, exports and processes EVI in GCP,
assembles the monthly model feature/base input, runs Vertex AI custom-job
inference using exported weights and inference code, and releases a traceable
artifact set.

### In Scope

- One cloud run for exactly one selected feature month.
- Cloud-only workflow dispatch through Cloud Run.
- Cloud Run orchestrator/control plane.
- Cloud Batch worker job using the repository Docker image.
- Artifact Registry Docker image built from this repository and pinned by digest.
- Google Earth Engine processed EVI raster export to GCS.
- Rasterio extraction of EVI mean and EVI standard deviation from exported raster(s).
- EVI wide and long feature artifacts for the selected feature month.
- Monthly model feature/base input CSV and summary JSON.
- Vertex AI custom-job inference using an immutable model package with exported
  weights and inference code/reference.
- Vertex AI inference output CSVs, inference report, and job metadata.
- Local-to-cloud inference evidence or explicit `not_provided` reference status.
- Validation reports.
- Immutable run evidence under a run-specific cloud object prefix.
- Atomic release manifest for the selected feature month.

### Out of Scope

- FLDAS extraction.
- GOSIF-GPP extraction.
- VIIRS extraction.
- Full external tabular download automation.
- Model training.
- Vertex AI Batch Prediction in v1.
- Registered Vertex AI Model deployment in v1.
- Model registration automation.
- Prediction maps.
- Prediction sheets.
- Full prediction delivery or publication outside the release artifact set.
- Any local workstation execution path.

## Deployment Contract

Provider for this spec version is GCP. The run MUST be executable without local
filesystem state outside the container. Runtime inputs MUST be `gs://` URIs,
Earth Engine source identifiers, Vertex AI Custom Job resource names, Artifact
Registry image URIs, or container-internal paths bundled inside the Docker image.
Local repo paths such as `Outcome/...`, `Final_harmonise/...`, and
`model_artifacts/...` are evidence examples only unless they are explicitly
container-internal paths packaged into the Docker image.

### Required Deployment Fields

The input manifest or deployment manifest MUST define:

| Field | Rule |
| --- | --- |
| `provider` | MUST be `gcp`. |
| `project_id` | GCP project for orchestration and object access. |
| `region` | Region for Cloud Run and Cloud Batch unless component-specific region overrides it. |
| `object_store_root_uri` | GCS root, for example `gs://.../ipcch/monthly_e2e`. |
| `run_root_uri` | Defaults to `{object_store_root_uri}/runs/{run_id}/`. |
| `staging_root_uri` | Defaults to `{object_store_root_uri}/staging/{run_id}/`. |
| `release_root_uri` | Defaults to `{object_store_root_uri}/released/{YYYYMM}/`. |
| `gee_export_root_uri` | Defaults to `{run_root_uri}/gee_exports/`. |
| `logs_root_uri` | Defaults to `{run_root_uri}/logs/`. |
| `artifact_registry_image_uri` | Repository runtime image URI pinned by digest for release runs. |
| `repo_git_commit` | Git commit SHA or equivalent source revision used to build the image. |
| `cloud_run_orchestrator_name` | Canonical Cloud Run Job name: `ipcch-monthly-e2e-orchestrator`. |
| `cloud_run_service_account` | Execution identity for the orchestrator. |
| `cloud_batch_service_account` | Execution identity for the Batch worker. |
| `cloud_batch_job_name_prefix` | Prefix for generated worker job names. |
| `earth_engine_project_id` | Earth Engine project used for export tasks. |
| `vertex_ai_region` | Region for Vertex AI custom-job inference. |
| `vertex_ai_inference_mode` | MUST be `vertex_ai_custom_job` in v1. |
| `vertex_ai_model_package_uri` | GCS URI for exported weights/inference package. Required in v1. |
| `vertex_ai_model_package_checksum_or_version` | Required immutable checksum, generation, or version for the model package. |
| `vertex_ai_custom_job_container_image_uri` | Artifact Registry image URI used by the Vertex AI Custom Job. |
| `vertex_ai_custom_job_container_digest` | Required digest. In single-image v1 this MUST equal the repository runtime image digest. |
| `vertex_ai_custom_job_service_account` | Execution identity for Vertex AI Custom Job. |
| `vertex_ai_custom_job_staging_root_uri` | GCS staging root for Vertex AI Custom Job. |
| `vertex_ai_custom_job_output_root_uri` | GCS output root for Vertex AI Custom Job outputs. |

`vertex_ai_model_resource_name` is not supported in v1. A registered Vertex AI
Model resource is a future extension only and MUST NOT be required for v1.

### Execution Identity and Permissions v1

v1 MUST use split least-privilege execution identities:

| Identity | Required permission boundary |
| --- | --- |
| `cloud_run_service_account` | Read input manifest and deployment config; create run sentinel, run summaries, validation reports, staging metadata, release step report, immutable released copies, and release manifest under declared GCS roots; submit and inspect Cloud Batch jobs; submit and inspect Vertex AI custom jobs; read Artifact Registry image metadata; pass only the declared Cloud Batch and Vertex AI custom-job service accounts. |
| `cloud_batch_service_account` | Pull the digest-pinned repository image; read declared scaffold, geometry, EVI export config, schema/validator, and staging inputs; use the declared Earth Engine project for EVI export; read processed raster evidence; write only declared `gee_exports/`, `evi/`, and `logs/` run prefixes. |
| `vertex_ai_custom_job_service_account` | Pull the digest-pinned repository image; read the released or run-scoped base input and immutable model package; write only declared `inference/` and `logs/` run prefixes; read required schema/validator assets. |

The deployment manifest MUST declare all three service accounts and their
permission model as `split_least_privilege`. A missing identity, a shared
identity in v1, inability to pass the declared worker identities, or permission
failure against any required declared cloud resource is a hard gate. Secret keys
MUST NOT be stored in the image or input manifest.

Hard gates:

- Missing required deployment field.
- Non-GCP provider.
- Runtime input path that is a local workstation path and not explicitly
  container-internal.
- Release run image not pinned by digest.
- Runtime use of local workstation code outside the image.
- Deployment manifest does not use split least-privilege service accounts.

## Docker Runtime Contract

v1 uses a **single-image runtime**. One repository Docker image is used for Cloud
Batch, monthly assembly/validation, release writing, and Vertex AI custom-job
inference. The image MUST expose separate entrypoints for EVI/GEE worker,
assembly/validation, and inference. Release requires one image digest recorded
as `container_image_digest`.

Required image metadata:

- Artifact Registry image URI.
- Image digest.
- Git commit SHA or source revision.
- Build timestamp.
- Build provenance or build ID when available.
- Included entrypoints:
  - manifest validation
  - Cloud Batch GEE export/rasterio worker
  - EVI validation
  - monthly feature/base input assembly
  - base input validation
  - Vertex AI custom-job inference
  - release manifest writer

Hard gates:

- Release run image reference is tag-only.
- `container_image_digest` missing from manifest or run summary.
- Runtime uses code from a local workstation path outside the image.
- Required runtime entrypoint is missing from image metadata or fails to run.

Container-internal code paths are allowed and SHOULD be recorded as image
provenance, not as input artifacts.

## Execution Interface

The canonical dispatch is a Cloud Run Job execution:

```bash
gcloud run jobs execute ipcch-monthly-e2e-orchestrator \
  --region ${REGION} \
  --args="--feature-month=YYYY-MM,--run-id=RUN_ID,--input-manifest-uri=gs://.../input_manifest.json"
```

An equivalent Cloud Run service HTTP dispatch MAY be added later, but this spec
uses the Cloud Run Job contract as the authoritative v1 entry point.

### Required Parameters

| Parameter | Required? | Rule |
| --- | --- | --- |
| `feature_month` | Required | Format `YYYY-MM`. |
| `run_id` | Required | Unique under `object_store_root_uri`. |
| `input_manifest_uri` | Required | MUST be a `gs://` URI. |
| `reference_sample_uri` | Optional | Advisory EVI and/or inference reference comparison only. |
| `release_mode` | Optional | First supported value: `release_on_success`; default is `release_on_success`. |

### Execution Behavior

1. Cloud Run orchestrator validates parameters and manifest.
2. Cloud Run acquires the immutable run prefix by creating a sentinel object
   under `runs/{run_id}/` with generation precondition.
3. Cloud Run writes initial `run_summary.json` with status `running`.
4. Cloud Run submits a Cloud Batch worker job for GEE export monitoring and
   rasterio extraction.
5. Cloud Batch worker exports processed EVI raster(s) from Earth Engine to GCS,
   records task metadata, and extracts EVI mean/std by area using rasterio.
6. Cloud Batch writes EVI evidence under `runs/{run_id}/evi/`, GEE export
   evidence under `runs/{run_id}/gee_exports/`, and logs under declared logs root.
7. Cloud Run verifies EVI artifacts and assembles monthly model feature/base
   input using the Dockerized repository code.
8. Cloud Run validates base input schema, row universe, keys, and forbidden side effects.
9. Cloud Run submits Vertex AI custom-job inference.
10. Cloud Run validates Vertex AI prediction outputs and local-to-cloud evidence.
11. Cloud Run stages release artifacts.
12. Cloud Run writes `release_step_report.json`.
13. Cloud Run updates `release_manifest.json` last.
14. Cloud Run writes terminal `run_summary.json`.

### Exit Behavior and Run Status

- Successful released E2E run exits `0` and terminal status is `released`.
- Any hard gate failure exits nonzero.
- Pre-run-prefix failures MUST be caller-visible in Cloud Run job status/logs.
- Post-prefix failures MUST write terminal `run_summary.json` with status
  `failed`, `release_failed`, or `release_conflict`.
- Duplicate `run_id` fails before modifying the existing run prefix.
- Terminal run statuses are `running`, `failed`, `released`, `release_failed`,
  and `release_conflict`. Use `passed` for validation reports, not terminal run status.

## Input Manifest Schema

The input manifest MUST be JSON and MUST use RFC 3339 / ISO-8601 UTC timestamps.

### Top-Level Fields

| Field | Required? | Rule |
| --- | --- | --- |
| `manifest_version` | Required | First supported version: `ipcch-monthly-e2e-v1`. |
| `feature_month` | Required | MUST equal execution parameter `feature_month`. |
| `run_id` | Required | MUST equal execution parameter `run_id`. |
| `created_at_utc` | Required | UTC timestamp. |
| `deployment` | Required | Object containing every required deployment field. |
| `artifacts` | Required | Nonempty array of artifact entries. |
| `waivers` | Optional | Array of explicit integrity waivers copied into `run_summary.json`. |

### Artifact Entry Fields

Each artifact entry MUST include:

| Field | Rule |
| --- | --- |
| `artifact_id` | Stable unique ID within the manifest. |
| `artifact_type` | One of the enum values below. |
| `required` | Boolean. Missing required artifacts are hard gates. |
| `uri` | Required for GCS or mounted artifacts; not used for pure source identifiers. |
| `source_family` | Source family such as `scaffold`, `fixed_slow`, `source_panel`, `EVI`, `spatial`, `schema`, `docker`, `model`, or `vertex_ai`. |
| `feature_month` or `vintage` | Required. Use `feature_month` for month-specific entries and `vintage` for fixed/reference entries. |
| `schema_contract` or `schema_version` | Required. |
| `checksum`, `generation`, `version_id`, `image_digest`, or `model_version` | Required immutable reference for required entries unless waived. |
| `checksum_algorithm` | Required when `checksum` is supplied; MUST be `sha256`. |

Artifact type enum:

- `scaffold`
- `fixed_slow_area_features`
- `source_panel`
- `gee_evi_export_config`
- `geometry`
- `evi_reference_sample`
- `schema_contract`
- `docker_image`
- `model_package`
- `vertex_ai_inference_config`
- `spatial_boundary`
- `validator`

For GCS artifacts, `uri` plus checksum or GCS generation/version is required
unless waived. For Docker images, Artifact Registry image URI plus digest is
required. For the model package, GCS URI plus immutable version/checksum is
required.

Waivers MUST include `artifact_id`, `waiver_type`, `reason`, `approved_by`,
`approved_at_utc`, and `expires_at_utc` when applicable. Waivers MUST be copied
to `run_summary.json`.

## Required Input Contract

Missing or malformed required inputs are hard gates. Local `Outcome/...` paths
listed here are evidence examples; runtime equivalents MUST be cloud URIs or
container-internal paths.

| Artifact | Required? | Runtime rule | Required keys/schema | Immutable reference rule | Failure behavior |
| --- | --- | --- | --- | --- | --- |
| One-month scaffold, evidence example `Outcome/ipcch_unified/interim/ipcch_scaffold_YYYYMM.csv` | Required | Cloud URI for selected feature month | `admin_code`, `lat`, `lon`, `year`, `month`; optional `area_id` must equal normalized `admin_code`; selected-month `(area_id, year, month)` unique | checksum or GCS generation/version | Hard gate |
| Combined fixed/slow area features, evidence example `Outcome/ipcch_unified/features/ipcch_fixed_slow_features_by_area.csv` | Required | Cloud URI | Must satisfy `fixed-slow-area` contract; `area_id`, `admin_code`, `lat`, `lon`, fixed/slow feature columns; `area_id` unique and nonblank | checksum or GCS generation/version | Hard gate |
| Prepared source panel, evidence example `Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv` | Required | Cloud URI | `admin_code`, `lat`, `lon`, `year`, `month`; no duplicate normalized `(admin_code as area_id, year, month)` for selected month | checksum or GCS generation/version | Hard gate for missing/malformed; selected-month rows may be absent only if recorded as missingness with `target_month_present_in_source=false` |
| GEE EVI export configuration | Required | Manifest object, not pre-exported raster input | See GEE Processed Raster Export Contract | source collection version label or immutable source version when available | Hard gate |
| Area geometry for EVI aggregation, evidence example `Outcome/ipcch_unified/spatial/ipcch_admin_geometry.*` | Required | Cloud URI | Geometry zone identifier MUST be canonical `area_id`; all zone IDs nonblank and unique | checksum or GCS generation/version for geometry package | Hard gate |
| Optional EVI reference sample | Optional | Cloud URI when supplied | Comparable `area_id`, month, EVI mean/std values | checksum or GCS generation/version recommended | Advisory warning when malformed unless it blocks required EVI contract validation |
| Docker image | Required | Artifact Registry image URI | Single repository runtime image with required entrypoints | image digest | Hard gate |
| Model package | Required | GCS URI | See Model Package Contract | package checksum, GCS generation/version, or immutable object version | Hard gate |
| Vertex AI custom-job inference config | Required | Manifest entry | `vertex_ai_custom_job` fields from Vertex AI contracts | immutable image/model references | Hard gate |
| Schema/validator contracts | Required | Container-internal path or cloud URI | Monthly input, EVI, and prediction output contracts | source revision, checksum, or image provenance | Hard gate |

## Model Package Contract

The v1 model package is a GCS package, not a registered Vertex AI Model. It MUST
contain exported weights, inference code or a code reference, model package
manifest, dependency metadata, and expected input/output schema.

Required package files/metadata:

- `model_package_manifest.json`
- exported weights file(s)
- inference code package or code reference
- dependency lock or runtime dependency metadata
- expected base input schema version
- expected prediction output schema version
- package checksum or immutable object generation/version
- local validation evidence reference, if available

`model_package_manifest.json` MUST include:

- `schema_version`
- `model_package_id`
- `model_version`
- `created_at_utc`
- `source_git_commit`
- `weights_files`
- `weights_checksums`
- `inference_entrypoint`
- `inference_code_version`
- `dependency_manifest`
- `expected_input_schema`
- `expected_output_schema`
- `local_validation_status`
- `local_validation_artifact_reference`
- `status`

Rules:

- Local validation status may be `passed`, but cloud release still requires a
  Vertex AI custom-job run.
- Model package checksum/version is a hard gate.
- Missing package manifest is a hard gate.
- Mismatch between model package expected input schema and base input validation
  schema is a hard gate.
- v1 local evidence uses `model_pipeline/run_operational_launch_inference.py`
  and `model_artifacts/launch_2026_04/model_package_manifest.json` as repository
  examples; runtime package MUST be cloud-addressable.

## GEE Processed Raster Export Contract

The workflow owns EVI export for the selected feature month. Processed EVI
rasters are output evidence artifacts, not required input artifacts.

### EVI Processing Parameters v1

| Parameter | v1 value |
| --- | --- |
| Earth Engine collection | `MODIS/061/MOD13A3` |
| Band | `EVI` |
| Date window rule | Start is first day of `feature_month`; end is first day of following month, exclusive. |
| Scale factor rule | Preserve raw MOD13A3 EVI scaled integer values; do not multiply by `0.0001` in v1. |
| Mask/nodata rule | Preserve Earth Engine image mask; rasterio ignores raster nodata and NaN values during zonal statistics. |
| Output dtype | Native EVI signed integer dtype unless Earth Engine export requires compatible GeoTIFF dtype; actual dtype recorded in `gee_export_manifest.json`. |
| Output CRS | Native MOD13A3 EVI band projection recorded in the export metadata. |
| Output resolution | 1000 meters. |
| Export region source | Manifest `processing_params.export_region`, which MUST cover the area geometry. Evidence example uses rectangle `[-180, -60, 180, 80]`. |
| Raster filename pattern | `MOD13A3_EVI_YYYY_MM_processed.tif`. |
| Pixel value unit after processing | MODIS scaled EVI integer unit. |
| Clipped to region | Yes, clipped/exported to declared export region. |
| Band count | Single-band raster. |

### Manifest Artifact Type: `gee_evi_export_config`

Required fields:

- `artifact_id`
- `artifact_type=gee_evi_export_config`
- `source_family=EVI`
- `earth_engine_collection=MODIS/061/MOD13A3`
- `band=EVI`
- `feature_month`
- `date_window`
- `processing_params`
- `schema_contract`
- `version_id` or source collection version label when available

### GEE Output Evidence

Required files:

- `runs/{run_id}/gee_exports/MOD13A3_EVI_YYYY_MM_processed.tif`
- `runs/{run_id}/gee_exports/gee_export_manifest.json`

The processed raster MUST have at least one immutable reference: GCS
generation/version OR sha256 checksum. If checksum is unavailable, GCS
generation/version is required. If generation/version is unavailable, checksum is
required.

## Cloud Batch Worker Contract

Cloud Batch worker runs the single repository image and may use ephemeral local
disk inside the job only. Ephemeral local disk is not released evidence. Every
required output MUST be copied to declared GCS run roots.

Required fields in `evi_extraction_manifest.json`:

- `cloud_batch_job_id`
- `cloud_batch_job_resource_name`
- `worker_entrypoint`
- `worker_container_image_uri`
- `worker_container_image_digest`
- `gee_export_task_id`
- `gee_poll_interval_seconds`
- `gee_export_timeout_seconds`
- `batch_job_timeout_seconds`
- `retry_policy`
- `ephemeral_workspace_path`
- `output_roots`
- `log_uri`

v1 default timing and retry values:

- `gee_poll_interval_seconds=60`.
- `gee_export_timeout_seconds=21600`.
- `batch_job_timeout_seconds=28800`.
- `retry_policy.max_retries=2`, meaning at most two retries after the first
  attempt for retryable Cloud Batch worker failures.

The deployment manifest MAY override these defaults. Effective values MUST be
recorded in `evi_extraction_manifest.json`. Nonpositive timeout or poll values
are hard gates. Retry exhaustion is a hard gate. Duplicate `run_id`, invalid
input manifest, output contract failure, release conflict, and forbidden
side-effect failures MUST NOT be retried as transient worker failures.

Rules:

- Partial files from failed attempts MUST either be absent from contract paths or
  marked as failed in report metadata.
- GEE task timeout is a hard gate.
- Batch retry exhaustion is a hard gate.
- Worker logs MUST be under `logs_root_uri`.

## EVI Processing Contract

The Cloud Batch worker MUST use rasterio to read the selected-month processed
EVI raster from GCS or a downloaded ephemeral copy.

Required behavior:

- Read selected-month processed EVI raster.
- Read area geometry from cloud URI.
- Reproject geometry to raster CRS if needed.
- Use canonical `area_id` as the zone identifier.
- Use v1 pixel inclusion rule `all_touched=false`: only raster pixels whose
  centers fall inside the polygon are included in EVI mean/std zonal statistics.
- Compute area-level EVI mean and standard deviation.
- Preserve one output row per scaffold area.
- Empty zones produce blank/null metric values but still produce rows.
- `region_id` in wide EVI outputs MUST equal canonical `area_id`.
- Long EVI outputs MUST contain exactly the selected feature month.
- Duplicate, blank, missing, or many-to-many area IDs are hard gates.

Required EVI evidence files:

- `runs/{run_id}/evi/EVI_mean_extraction_results.csv`
- `runs/{run_id}/evi/EVI_std_extraction_results.csv`
- `runs/{run_id}/evi/EVI_mean_monthly_long.csv`
- `runs/{run_id}/evi/EVI_std_monthly_long.csv`
- `runs/{run_id}/evi/evi_validation_report.json`
- `runs/{run_id}/evi/evi_extraction_manifest.json`

`evi_extraction_manifest.json` MUST record
`pixel_inclusion_rule=all_touched_false_center_inside`. Any other pixel
inclusion rule in v1 is a hard gate unless the input manifest declares an
explicit approved waiver and the waiver is copied to `run_summary.json`.

Hard gates:

- Cloud Batch job failure.
- Missing rasterio extraction manifest.
- Missing any required EVI output.
- Invalid EVI wide/long schema.
- Selected month mismatch.
- EVI long row count not equal to scaffold row count.
- Any `region_id` not equal to canonical `area_id`.

Advisory only:

- Numeric differences against optional local/reference EVI sample when the
  required cloud EVI output contract is valid.
- Reference sample absent.
- Zero matched reference observations or fewer than 3 matched non-missing pairs
  for correlation.

## Area Identity Contract

- The canonical area identifier is `area_id`.
- The one-month scaffold MAY omit `area_id`; when absent, `area_id` MUST be
  derived by normalizing `admin_code`. If present, `area_id` MUST equal
  normalized `admin_code`.
- Every selected-month scaffold row MUST map to exactly one `area_id`.
- Fixed/slow features join to scaffold by `area_id`.
- Prepared source panel values join by normalized `admin_code` as `area_id`,
  plus `year` and `month`.
- EVI `region_id` MUST equal canonical `area_id` in this feature.
- Missing IDs, blank IDs, duplicate IDs, or many-to-many mappings are hard gates.
- No duplicate `area_id`/`year`/`month` rows are allowed after assembly, EVI long
  generation, or prediction output validation.

## Row Universe and Coverage Contract

- The one-month scaffold is the row universe for the monthly model feature/base input.
- Successful base input row count MUST equal selected-month scaffold row count.
- Successful EVI long outputs MUST each contain exactly one row per scaffold area.
- v1 prediction outputs MUST contain exactly one row per base input row for each
  scope file; filtered outputs are not allowed.
- Missing joins for non-key feature values are recorded as missingness.
- Missing scaffold rows, extra area-month rows, or dropped scaffold rows are hard gates.
- This feature requires 100% scaffold row coverage for release.

## Monthly Feature/Base Input Assembly

Required outputs:

- `runs/{run_id}/assembly/ipcch_monthly_base_input_YYYYMM.csv`
- `runs/{run_id}/assembly/ipcch_monthly_base_input_YYYYMM_summary.json`
- `runs/{run_id}/qa/base_input_validation_report.json`

Rules:

- Exactly one selected feature month.
- One row per scaffold area.
- Row count equals scaffold row count.
- No duplicate `area_id`/`year`/`month`.
- Required keys are nonblank.
- EVI feature columns come from cloud-produced EVI long outputs.
- Fixed/slow features and prepared source panel are consumed from cloud URIs
  declared in manifest.
- Absence of selected-month prepared source panel rows is allowed only if
  recorded as missingness and `target_month_present_in_source=false`.
- Base input validation happens before Vertex AI inference.

## Vertex AI Inference Contract

`vertex_ai_custom_job` is the only supported v1 inference mode. v1 does not
require and MUST NOT require a registered Vertex AI Model resource. The v1 custom
job consumes an immutable model package containing exported weights, inference
code or code reference, package manifest, dependency metadata, and expected
input/output schema. Local inference validation is evidence only; it does not
satisfy the cloud inference gate by itself.

Required manifest/deployment fields:

- `vertex_ai_region`
- `vertex_ai_job_name_prefix`
- `vertex_ai_custom_job_service_account`
- `vertex_ai_model_package_uri`
- `vertex_ai_model_package_checksum_or_version`
- `vertex_ai_custom_job_container_image_uri`
- `vertex_ai_custom_job_container_digest`
- `vertex_ai_custom_job_staging_root_uri`
- `vertex_ai_custom_job_output_root_uri`

Vertex AI input:

- `runs/{run_id}/assembly/ipcch_monthly_base_input_YYYYMM.csv`

Vertex AI outputs:

- `runs/{run_id}/inference/vertex_ai_job_manifest.json`
- `runs/{run_id}/inference/inference_report.json`
- `runs/{run_id}/inference/ipcch_launch_YYYYMM_scope_0m_predictions.csv`
- `runs/{run_id}/inference/ipcch_launch_YYYYMM_scope_6m_predictions.csv`
- `runs/{run_id}/inference/ipcch_launch_YYYYMM_scope_12m_predictions.csv`

Hard gates:

- Vertex AI job submission failure.
- Vertex AI job terminal failure.
- Missing prediction output.
- Prediction output unreadable.
- Prediction row count not equal to base input row count.
- Prediction output missing required keys or required result columns.
- Prediction selected month mismatch.
- Duplicate `area_id`/`year`/`month` in a prediction output.
- Model package missing checksum/version.
- Custom job container not pinned by digest.
- Local validation present but cloud custom job missing.

Allowed inference side effects:

- Vertex AI job metadata.
- Three prediction tables.
- Inference report.
- Logs under declared run log prefix.

Forbidden inference side effects:

- Prediction maps.
- Prediction sheets.
- Full prediction delivery artifacts.
- Any local or non-Vertex inference process not declared in run manifest.

## Vertex AI Custom Job Runtime Contract

v1 custom-job inference uses the same single repository image digest as the rest
of the run and a different entrypoint. The exact repository script executed after
cloud inputs are localized inside the container is:

```bash
python3 model_pipeline/run_operational_launch_inference.py \
  --input /workspace/input/ipcch_monthly_base_input_YYYYMM.csv \
  --model-package /workspace/model_package \
  --output-dir /workspace/inference \
  --feature-month YYYY-MM \
  --no-map \
  --overwrite
```

Required custom job behavior:

- The custom job MUST localize `input_base_uri` and `vertex_ai_model_package_uri`
  from GCS to the container-internal paths shown above.
- The custom job MUST copy the three required prediction CSVs and
  `run_summary.json` from `/workspace/inference` to
  `runs/{run_id}/inference/`.
- If the repository inference script emits `feature_period` but not explicit
  `year` and `month` columns, the Vertex AI wrapper MUST add `year` and `month`
  to each prediction CSV from the validated base input before writing the
  contract outputs.
- The custom job MUST NOT pass `--validate-only`.
- The custom job MUST pass `--no-map`.
- The custom job MAY pass `--overwrite` only inside its ephemeral workspace.
- The custom job MUST not read or write local workstation paths.

Required arguments at the Vertex AI job wrapper level:

- `--input-base-uri`
- `--model-package-uri`
- `--feature-month`
- `--output-dir`
- `--run-id`

Optional arguments:

- `--reference-output-uri` for local-to-cloud parity comparison.
- `--log-level`.

Required environment variables:

- `PROJECT_ID`
- `VERTEX_AI_REGION`
- `RUN_ID`
- `FEATURE_MONTH`
- `MODEL_PACKAGE_URI`
- `INPUT_BASE_URI`
- `INFERENCE_OUTPUT_URI`

Credentials MUST come from `vertex_ai_custom_job_service_account`; secret keys
MUST NOT be baked into the image.

Input URI rules:

- `--input-base-uri` MUST be a `gs://` URI under `run_root_uri` or immutable
  released copy.
- `--model-package-uri` MUST be a `gs://` URI with checksum/generation/version.

Output URI rules:

- `--output-dir` MUST resolve to `runs/{run_id}/inference/`.
- Custom job outputs outside the declared inference output root are hard gates.

Exit-code behavior:

- Exit code `0` means all required prediction CSVs were written locally and
  copied to the declared GCS output root.
- Nonzero exit is a hard gate.
- Exit `0` with missing required files is a hard gate.

Logging, retry, and timeout behavior:

- Logs MUST be written to Vertex AI job logs and copied or referenced under
  `logs_root_uri`.
- Retry policy MUST be declared in the manifest. v1 default
  `retry_policy.max_retries=2`, meaning at most two retries after the first
  attempt for retryable Vertex AI custom-job submission or transient runtime
  failures.
- Retried attempts MUST not leave partial files in contract paths unless marked
  failed in report metadata.
- Custom job timeout MUST be declared or default to
  `vertex_ai_custom_job_timeout_seconds=7200`. Timeout is a hard gate.
- The effective timeout and retry policy MUST be recorded in
  `vertex_ai_job_manifest.json` and `inference_report.json`.

Hard gates:

- Missing custom job command.
- Missing or non-cloud input URI.
- Missing model package.
- Missing model package immutable reference.
- Missing custom job image digest.
- Custom job exits nonzero.
- Custom job completes but required output files are missing.
- Custom job logs indicate fallback to local workstation paths.
- Custom job writes output outside declared inference output root.

## Prediction Output Schema v1

v1 produces three scope-specific prediction CSVs:

- `ipcch_launch_YYYYMM_scope_0m_predictions.csv`
- `ipcch_launch_YYYYMM_scope_6m_predictions.csv`
- `ipcch_launch_YYYYMM_scope_12m_predictions.csv`

Each file MUST contain exactly one row per base input row and MUST satisfy this
schema:

| Column | Type | Nullable? | Allowed range / rule | Role | Missing behavior |
| --- | --- | --- | --- | --- | --- |
| `area_id` | string | No | Nonblank; equals base input `area_id` | key | Hard gate |
| `year` | integer | No | Four-digit selected feature year; equals base input `year` | key | Hard gate |
| `month` | integer | No | 1-12 selected feature month; equals base input `month` | key | Hard gate |
| `admin_code` | string | Yes only if absent from base input | If present, must match base input `admin_code` for same `area_id` | metadata | Advisory if absent; hard gate if inconsistent |
| `_row_id` | integer | No | 0-based row id from validated base input | diagnostic | Hard gate |
| `phase2_worse_score` | float | No | Finite numeric; no hard 0-1 bound in v1 | prediction | Hard gate |
| `phase2_worse_pred` | integer | No | 0 or 1 | prediction | Hard gate |
| `phase3_worse_score` | float | No | Finite numeric; no hard 0-1 bound in v1 | prediction | Hard gate |
| `phase3_worse_pred` | integer | No | 0 or 1 | prediction | Hard gate |
| `phase4_worse_score` | float | No | Finite numeric; no hard 0-1 bound in v1 | prediction | Hard gate |
| `phase4_worse_pred` | integer | No | 0 or 1 | prediction | Hard gate |
| `phase5_worse_score` | float | No | Finite numeric; no hard 0-1 bound in v1 | prediction | Hard gate |
| `phase5_worse_pred` | integer | No | 0 or 1 | prediction | Hard gate |
| `overall_phase_pred` | integer | No | Integer 1-5 | prediction | Hard gate |
| `feature_period` | string | No | `YYYY-MM`; equals selected `feature_month` | metadata | Hard gate |
| `target_period` | string | No | `YYYY-MM`; equals package target period for scope | metadata | Hard gate |
| `scope_months` | integer | No | One of 0, 6, 12 and matches filename | metadata | Hard gate |
| `model_package_id` | string | No | Equals package manifest `model_package_id` | metadata | Hard gate |
| `source_input` | string | No | References base input path used by custom job | metadata | Hard gate |

Rules:

- Duplicate `area_id`/`year`/`month` rows within a scope file are hard gates.
- Duplicate `area_id`/`year`/`month`/`scope_months` rows in the combined
  three-scope prediction inventory are hard gates.
- Missing required prediction/result columns are hard gates.
- Extra columns are allowed only if recorded in `inference_report.json`.
- Filtered outputs are not allowed in v1.

## Local-to-Cloud Inference Evidence

Existing local validation proves only that exported weights and the local
inference pipeline can produce required results from a base input. It does not
prove Vertex AI runtime compatibility. The first cloud implementation MUST
include a custom-job smoke/parity validation before release.

Preferred gate when a local reference output is available:

- Run Vertex AI custom job against the same small or full base input.
- Compare cloud output to the local reference output for the same input.
- Required keys and required result columns MUST match exactly.
- Numeric score differences are advisory unless the model output contract later
  declares hard numeric tolerances.
- Missing rows, duplicate keys, missing required result columns, unreadable
  outputs, or selected-month mismatch are hard gates.

Fallback gate when no local reference output is available:

- Run Vertex AI custom job against the production base input.
- Validate required output schema, row universe, selected month, nonblank keys,
  and required result columns.
- Record `local_reference_comparison.status=not_provided`.
- Release MAY proceed only if all cloud output contract gates pass.

`inference_report.json` MUST include:

- `local_reference_comparison`
- `cloud_runtime_validation_status`
- `model_package_validation_status`
- `custom_job_command`
- `custom_job_exit_code`
- `custom_job_log_uri`

## Forbidden Side Effect Check Contract

`run_summary.json` MUST include a `forbidden_side_effect_check` object with:

- `checked_prefixes`
- `allowed_prefixes`
- `forbidden_filename_patterns`
- `forbidden_artifact_families`
- `observed_forbidden_artifacts`
- `observed_forbidden_invocations`
- `status`

Rules:

- Allowed inference outputs are limited to Vertex AI job metadata, the three
  prediction tables, inference report, and logs under declared run log prefix.
- Prediction maps, prediction sheets, full delivery artifacts, model training
  artifacts, non-EVI remote-sensing artifacts, and undeclared non-Vertex scoring
  artifacts are hard gates.
- Container temporary files are ignored only if they are not copied to GCS
  artifact roots and not referenced by reports.

## Output Artifact Contract

| Artifact | Required location | Required? | Validation rule |
| --- | --- | --- | --- |
| Immutable run sentinel | `runs/{run_id}/_RUN_PREFIX_ACQUIRED` or equivalent | Required after prefix acquisition | Created with generation precondition before run evidence is written. |
| Initial and terminal run summary | `runs/{run_id}/run_summary.json` | Required after prefix acquisition | Must satisfy Report Schemas. |
| GEE processed raster | `runs/{run_id}/gee_exports/MOD13A3_EVI_YYYY_MM_processed.tif` | Required | Must satisfy GEE Processed Raster Export Contract. |
| GEE export manifest | `runs/{run_id}/gee_exports/gee_export_manifest.json` | Required | Must satisfy Report Schemas. |
| EVI mean wide output | `runs/{run_id}/evi/EVI_mean_extraction_results.csv` | Required | Must satisfy EVI Processing Contract. |
| EVI standard-deviation wide output | `runs/{run_id}/evi/EVI_std_extraction_results.csv` | Required | Must satisfy EVI Processing Contract. |
| EVI mean long output | `runs/{run_id}/evi/EVI_mean_monthly_long.csv` | Required | Must satisfy EVI Processing Contract. |
| EVI standard-deviation long output | `runs/{run_id}/evi/EVI_std_monthly_long.csv` | Required | Must satisfy EVI Processing Contract. |
| EVI extraction manifest | `runs/{run_id}/evi/evi_extraction_manifest.json` | Required | Must satisfy Report Schemas. |
| EVI validation report | `runs/{run_id}/evi/evi_validation_report.json` | Required | Must satisfy Report Schemas. |
| Monthly base input CSV | `runs/{run_id}/assembly/ipcch_monthly_base_input_YYYYMM.csv` | Required | Must satisfy Monthly Feature/Base Input Assembly rules. |
| Monthly base input summary JSON | `runs/{run_id}/assembly/ipcch_monthly_base_input_YYYYMM_summary.json` | Required | Must satisfy Report Schemas. |
| Base input validation report | `runs/{run_id}/qa/base_input_validation_report.json` | Required | Must satisfy Report Schemas. |
| Vertex AI job manifest | `runs/{run_id}/inference/vertex_ai_job_manifest.json` | Required | Must satisfy Vertex AI contracts and Report Schemas. |
| Inference report | `runs/{run_id}/inference/inference_report.json` | Required | Must satisfy Vertex AI contracts and Report Schemas. |
| Prediction output tables | `runs/{run_id}/inference/ipcch_launch_YYYYMM_scope_{0,6,12}m_predictions.csv` | Required | Must satisfy Prediction Output Schema v1. |
| Release step report | `runs/{run_id}/release/release_step_report.json` | Required for any release attempt | Must satisfy Atomic Release Semantics. |
| Immutable released copy | `released/{YYYYMM}/runs/{run_id}/...` | Required for successful release | Contains copied v1 release artifacts listed in Atomic Release Semantics; large/upstream evidence is referenced by immutable URI/generation/checksum. |
| Mutable pointer manifest | `released/{YYYYMM}/release_manifest.json` | Required for current release | Authoritative stable entry point and written last. |

Bare aliases such as `released/{YYYYMM}/ipcch_monthly_base_input_YYYYMM.csv` are
optional convenience aliases only, not authoritative, unless an object-store-safe
update mechanism is explicitly implemented.

## Validation Gates

| Validation | Classification | Release behavior | Required evidence |
| --- | --- | --- | --- |
| Missing or invalid required deployment field | Hard gate | Blocks release | Manifest validation report and `run_summary.json` |
| Non-cloud runtime input path | Hard gate | Blocks release | Manifest validation report |
| Docker image digest missing | Hard gate | Blocks release | Docker image metadata |
| Cloud Run orchestrator failure | Hard gate | Blocks release | Cloud Run job status/logs |
| Duplicate `run_id` | Preflight hard gate | Fails before modifying existing run prefix | Cloud Run job status/logs |
| Missing required input | Hard gate | Blocks release | `run_summary.json` |
| Required input missing immutable reference without waiver | Hard gate | Blocks release | Manifest validation report |
| Model package manifest/checksum/version failure | Hard gate | Blocks release | Model package validation status |
| Selected feature month mismatch | Hard gate | Blocks release | Validation report naming expected and observed month |
| Cloud Batch worker failure | Hard gate | Blocks release | Batch job status and `run_summary.json` |
| GEE export timeout or failure | Hard gate | Blocks release | `gee_export_manifest.json` |
| Missing processed GEE raster | Hard gate | Blocks release | `gee_export_manifest.json` |
| Processed raster generation/checksum missing | Hard gate | Blocks release | `gee_export_manifest.json` |
| Rasterio extraction failure | Hard gate | Blocks release | `evi_extraction_manifest.json` |
| Batch retry exhaustion | Hard gate | Blocks release | Cloud Batch worker report |
| Missing EVI extraction manifest | Hard gate | Blocks release | Artifact inventory |
| Invalid EVI output contract | Hard gate | Blocks release | `evi_validation_report.json` |
| Base input model schema compatibility failure before inference | Hard gate | Blocks release | `base_input_validation_report.json` |
| Scaffold/base/EVI row universe failure | Hard gate | Blocks release | Validation reports |
| Missing or blank required key columns | Hard gate | Blocks release | Validation reports |
| Duplicate `area_id`/`year`/`month` rows | Hard gate | Blocks release | Validation reports |
| Forbidden side effects | Hard gate | Blocks release | `forbidden_side_effect_check` |
| Vertex AI custom job submission or terminal failure | Hard gate | Blocks release | `vertex_ai_job_manifest.json` and `inference_report.json` |
| Custom job command/image/input/output contract failure | Hard gate | Blocks release | `inference_report.json` |
| Missing inference report | Hard gate | Blocks release | Artifact inventory |
| Missing prediction output | Hard gate | Blocks release | `inference_report.json` |
| Prediction output schema/key/month/row-universe failure | Hard gate | Blocks release | `inference_report.json` |
| Missing release step report for release attempt | Hard gate | Blocks release | Artifact inventory |
| Manifest generation-precondition conflict | Hard gate | Run status `release_conflict`; previous current release unchanged | `release_step_report.json` |
| Manifest write failure | Hard gate | Run status `release_failed`; previous current release unchanged | `release_step_report.json` |
| EVI numerical differences versus optional reference sample | Advisory gate | Does not block release when EVI contract is valid | `evi_validation_report.json` |
| Local-to-cloud numeric score differences when required keys/result columns match | Advisory gate unless output contract later defines hard numeric tolerance | Does not block release | `inference_report.json` |
| Correlation insufficient pairs | Advisory gate | Does not block release | EVI or inference report |
| Non-key missingness metrics | Record-only metric | Does not block release | Summary and validation reports |
| Distribution summaries | Record-only metric | Does not block release | EVI and inference reports |

## Forbidden Side Effects

The run MUST NOT produce or invoke:

- FLDAS extraction.
- GOSIF-GPP extraction.
- VIIRS extraction.
- External tabular download automation.
- Model training.
- Prediction maps.
- Prediction sheets.
- Full prediction delivery artifacts.
- Any local workstation scoring process.
- Any undeclared non-Vertex inference/scoring process.

The run MAY produce:

- Vertex AI custom-job metadata.
- Three Vertex AI prediction tables.
- Vertex AI inference report.
- Model input/base input artifacts.
- EVI extraction artifacts.
- GEE export artifacts.

## Atomic Release Semantics

Release uses immutable-versioned released objects plus a mutable pointer
manifest. Released data objects are not overwritten as the source of truth.

Storage model:

- Immutable run evidence under `runs/{run_id}/...`.
- Immutable released copy under `released/{YYYYMM}/runs/{run_id}/...`.
- Mutable pointer manifest at `released/{YYYYMM}/release_manifest.json`.

Consumer contract:

- `release_manifest.json` is the authoritative stable entry point.
- Consumers MUST read base input, summary, EVI evidence references, GEE evidence,
  Vertex AI job metadata, inference report, and prediction output paths from the
  manifest.

v1 release materialization:

- The release process MUST copy these accepted artifacts into
  `released/{YYYYMM}/runs/{run_id}/`: monthly base input CSV, monthly summary
  JSON, all three prediction CSVs, base input validation report, inference
  report, Vertex AI job manifest, release step report, GEE export manifest, EVI
  validation report, EVI extraction manifest, terminal run summary, and the
  accepted input manifest reference or manifest copy.
- The release process MUST reference these artifacts by immutable
  URI/generation/checksum instead of copying them by default: processed GEE
  raster, EVI wide outputs, EVI long outputs, Cloud Run/Batch/Vertex logs, and
  model package.
- Released copies and immutable references MUST both have checksums,
  generations, versions, or equivalent immutable identifiers recorded in
  `release_manifest.json`.
- Consumers MUST NOT infer release completeness from bare folder listings; they
  MUST use `release_manifest.json`.

Release sequence:

1. Verify all hard gates passed, including Vertex AI custom-job inference.
2. Write candidate release metadata under `staging/{run_id}/...`.
3. Copy required v1 accepted artifacts to `released/{YYYYMM}/runs/{run_id}/...`
   and record immutable references for non-copied evidence.
4. Verify checksums and object generations.
5. Write `runs/{run_id}/release/release_step_report.json`.
6. Write `release_manifest.json` last using object generation precondition or
   equivalent compare-and-swap guard.
7. If manifest write fails, previous release manifest remains current.
8. If no previous release exists and manifest write fails, no current release exists.
9. Concurrent passing runs for the same feature month MUST use generation
   precondition, lock, or first-writer-wins rule. A losing release attempt MUST
   end as `release_failed` or `release_conflict` without changing current release.

`release_step_report.json` MUST include:

- `schema_version`
- `feature_month`
- `run_id`
- `release_mode`
- `staging_root_uri`
- `release_root_uri`
- `accepted_artifacts`
- `copy_results`
- `checksum_verification`
- `manifest_generation_precondition`
- `previous_manifest_generation`
- `new_manifest_generation`
- `status`
- `failure_reason`

`release_manifest.json` MUST include:

- `schema_version`
- `feature_month`
- `accepted_run_id`
- `status=current`
- `base_input_path`
- `base_input_checksum`
- `summary_path`
- `summary_checksum`
- `evi_evidence_references`
- `gee_export_manifest_reference`
- `input_manifest_reference`
- `base_input_validation_report_reference`
- `vertex_ai_job_manifest_reference`
- `inference_report_reference`
- `prediction_output_paths`
- `prediction_output_checksums`
- `model_package_reference`
- `model_version_or_checksum`
- `container_image_digest`
- `validation_status`
- `inference_status`
- `advisory_warning_state`
- `release_timestamp_utc`
- `released_copied_artifacts`
- `released_referenced_artifacts`

## Report Schemas

### Report Classes

Validation reports MUST include common fields:

- `schema_version`
- `feature_month`
- `run_id`
- `status`
- `hard_gates`
- `advisory_warnings`
- `record_only_metrics`
- `artifact_paths`
- `checksums`

Manifest/evidence reports MAY omit advisory and record-only fields only when
explicitly marked below. They MUST still include `schema_version`,
`feature_month`, `run_id`, `status`, and either `artifact_paths` or direct
artifact URI fields.

Allowed gate item statuses are `passed`, `failed`, `warning`, `skipped`, and
`not_applicable`.

| Report | Class | Required top-level fields | Allowed `status` values |
| --- | --- | --- | --- |
| `run_summary.json` | Manifest/evidence | `schema_version`, `feature_month`, `run_id`, `status`, `input_manifest_uri`, `deployment`, `container_image_digest`, `cloud_run_job`, `cloud_batch_job`, `vertex_ai_job`, `hard_gates`, `advisory_warnings`, `record_only_metrics`, `artifact_paths`, `checksums`, `waivers`, `release_attempted`, `released`, `release_manifest_path`, `forbidden_side_effect_check` | `running`, `failed`, `released`, `release_failed`, `release_conflict` |
| `gee_export_manifest.json` | Manifest/evidence | `schema_version`, `feature_month`, `run_id`, `earth_engine_project_id`, `earth_engine_collection`, `band`, `date_window`, `processing_params`, `export_task_id`, `export_status`, `processed_raster_uri`, `processed_raster_generation_or_version`, `processed_raster_checksum`, `created_at_utc`, `status`, `artifact_paths`, `checksums`; advisory fields may be omitted | `passed`, `failed` |
| `evi_extraction_manifest.json` | Manifest/evidence | `schema_version`, `feature_month`, `run_id`, `worker_type`, `cloud_batch_job_id`, `cloud_batch_job_resource_name`, `worker_entrypoint`, `worker_container_image_uri`, `worker_container_image_digest`, `gee_export_task_id`, `gee_poll_interval_seconds`, `gee_export_timeout_seconds`, `batch_job_timeout_seconds`, `retry_policy`, `ephemeral_workspace_path`, `output_roots`, `source_raster_uri`, `source_raster_generation_or_version`, `geometry_uri`, `geometry_version_or_checksum`, `rasterio_version`, `gdal_version`, `pixel_inclusion_rule`, `nodata_rule`, `zone_count`, `empty_zone_count`, `log_uri`, `status`, `artifact_paths`, `checksums`; advisory fields may be omitted | `passed`, `failed` |
| `evi_validation_report.json` | Validation | common fields plus `output_contract_status`, `wide_outputs`, `long_outputs`, `area_identity`, `reference_comparison` | `passed`, `failed`, `passed_with_warnings` |
| `ipcch_monthly_base_input_YYYYMM_summary.json` | Validation | common fields plus `input_lineage`, `row_count`, `column_count`, `scaffold_row_count`, `key_columns`, `join_coverage`, `missingness`, `evi_feature_sources`, `source_join`, `fixed_slow_join` | `passed`, `failed` |
| `base_input_validation_report.json` | Validation | common fields plus `scaffold_row_count`, `base_input_row_count`, `row_universe_match`, `key_columns`, `duplicate_key_count`, `missing_key_counts`, `schema_result`, `join_coverage`, `missingness` | `passed`, `failed` |
| `vertex_ai_job_manifest.json` | Manifest/evidence | `schema_version`, `feature_month`, `run_id`, `vertex_ai_project_id`, `vertex_ai_region`, `vertex_ai_job_id`, `vertex_ai_job_resource_name`, `inference_mode`, `model_package_uri`, `model_version_or_checksum`, `vertex_ai_custom_job_container_image_uri`, `vertex_ai_custom_job_container_digest`, `container_image_digest`, `input_base_uri`, `output_uri`, `job_status`, `created_at_utc`, `completed_at_utc`, `status`, `artifact_paths`, `checksums`; advisory fields may be omitted | `passed`, `failed` |
| `inference_report.json` | Validation | common fields plus `vertex_ai_job_id`, `input_base_path`, `prediction_output_paths`, `prediction_row_counts`, `base_input_row_count`, `row_universe_match`, `key_columns`, `duplicate_key_count`, `missing_key_counts`, `model_output_schema`, `local_reference_comparison`, `cloud_runtime_validation_status`, `model_package_validation_status`, `custom_job_command`, `custom_job_exit_code`, `custom_job_log_uri`, `extra_columns` | `passed`, `failed` |
| `release_step_report.json` | Manifest/evidence | fields listed in Atomic Release Semantics; advisory fields may be omitted | `passed`, `failed`, `release_conflict` |
| `release_manifest.json` | Manifest/evidence | fields listed in Atomic Release Semantics; advisory fields may be omitted | `current` |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run Cloud E2E Monthly Production (Priority: P1)

As an IPCCH pipeline operator, I want one cloud-only dispatch to produce EVI
features, the monthly model feature/base input, Vertex AI custom-job inference
outputs, and the current release manifest for one feature month.

**Why this priority**: This is the main operational value of the feature. The run
must prove that monthly production no longer depends on a local workstation.

**Independent Test**: Execute the canonical Cloud Run Job command with a valid
input manifest and verify Cloud Run, Cloud Batch, GEE export, EVI extraction,
base input assembly, Vertex AI custom-job inference, and release artifacts.

**Acceptance Scenarios**:

1. **Successful cloud E2E release**
   - **Given** a valid manifest with GCP deployment fields, digest-pinned image,
     EVI export config, cloud input URIs, model package, and Vertex AI custom-job
     inference config.
   - **When** the Cloud Run Job is executed for `feature_month=YYYY-MM` and a
     new `run_id`.
   - **Then** Cloud Run dispatch is accepted, Cloud Batch completes, GEE export
     manifest exists, processed raster exists in GCS, rasterio EVI artifacts
     exist, monthly base input exists, Vertex AI custom job completes, all three
     prediction CSVs satisfy Prediction Output Schema v1, and
     `release_manifest.json` points to the accepted run.

2. **Hard gate failure**
   - **Given** any required cloud deployment field, digest, model package, GEE
     export, EVI artifact, base input validation, Vertex AI output, or release
     precondition fails.
   - **When** the run reaches the gate.
   - **Then** the run exits nonzero, records a hard-gate failure if the run
     prefix was acquired, and does not update the current release manifest.

3. **Duplicate run id**
   - **Given** `runs/{run_id}/` already exists.
   - **When** the Cloud Run Job is executed with that `run_id`.
   - **Then** the job fails before modifying the existing run prefix.

---

### User Story 2 - Audit EVI Export and Rasterio Extraction (Priority: P2)

As a pipeline reviewer, I want GEE export and rasterio extraction evidence, so I
can audit the EVI cloud replacement before trusting the model input and
inference output.

**Why this priority**: EVI is the only remote-sensing family in scope and the
highest-risk workstation replacement.

**Independent Test**: Inspect one successful run's GEE export manifest,
processed raster evidence, Cloud Batch worker metadata, EVI extraction manifest,
EVI wide/long outputs, EVI validation report, and optional advisory reference
comparison.

**Acceptance Scenarios**:

1. **EVI audit package**
   - **Given** a successful run.
   - **When** the reviewer opens the run evidence.
   - **Then** the evidence includes GEE task metadata, processed raster URI and
     generation/version or checksum, rasterio extraction metadata, EVI wide/long
     outputs, Cloud Batch worker metadata, and EVI validation report.

2. **Reference comparison advisory**
   - **Given** an optional EVI reference sample is supplied.
   - **When** cloud EVI values differ from the reference but required EVI output
     contracts pass.
   - **Then** differences are advisory only and release may proceed if all hard
     gates pass.

---

### User Story 3 - Consume Traceable E2E Release (Priority: P3)

As a downstream model user, I want one stable release manifest for the selected
feature month, so I can find the accepted model input, prediction outputs, and
lineage without browsing intermediate folders.

**Why this priority**: The release manifest is the stable handoff surface, while
run evidence remains immutable for audit.

**Independent Test**: Verify that `released/{YYYYMM}/release_manifest.json`
contains references to base input, summary, EVI evidence, GEE export evidence,
Vertex AI job manifest, inference report, prediction outputs, model package,
Docker image digest, validation status, and release timestamp.

**Acceptance Scenarios**:

1. **Traceable release**
   - **Given** a successful run.
   - **When** `release_manifest.json` is inspected.
   - **Then** it points to immutable accepted artifacts under
     `released/{YYYYMM}/runs/{run_id}/...` and records all required lineage and
     checksums.

2. **Release conflict**
   - **Given** two passing runs for the same feature month attempt release.
   - **When** one loses the generation-precondition or lock.
   - **Then** the losing run ends as `release_conflict` or `release_failed`
     without changing the current release manifest.

### Edge Cases

- Invalid `feature_month` format.
- Duplicate `run_id`.
- Manifest uses local workstation paths.
- Docker image is tag-only.
- Model package manifest missing or schema mismatch.
- GEE export succeeds but raster lacks generation/version and checksum.
- Cloud Batch succeeds but required EVI file is missing.
- EVI long row count differs from scaffold row count.
- Base input passes schema but prediction output row universe fails.
- Vertex AI job completes but prediction output is unreadable.
- Local reference output unavailable.
- Custom job writes output outside declared inference root.
- Forbidden maps, sheets, delivery artifacts, training artifacts, or non-EVI
  remote-sensing artifacts appear.
- Release manifest write loses a concurrency guard.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST run the monthly workflow entirely in GCP through the canonical Cloud Run Job dispatch.
- **FR-002**: The system MUST use Cloud Run as orchestrator/control plane and Cloud Batch as the heavy worker runtime for GEE export monitoring and rasterio EVI extraction.
- **FR-003**: The system MUST use a single repository Docker image pinned by digest for release runs.
- **FR-004**: The system MUST export the selected-month processed EVI raster from Earth Engine to GCS and record `gee_export_manifest.json`.
- **FR-005**: The system MUST extract area-level EVI mean and standard deviation with rasterio and produce the required EVI evidence files.
- **FR-006**: The system MUST assemble the monthly model feature/base input using cloud-declared inputs and cloud-produced EVI features.
- **FR-007**: The system MUST validate base input row universe, key, selected month, schema, and forbidden side effects before inference.
- **FR-008**: The system MUST run Vertex AI custom-job inference using exported inference weights/code and immutable image/model references.
- **FR-009**: The system MUST validate all three prediction CSVs against Prediction Output Schema v1.
- **FR-010**: The system MUST record local-to-cloud inference comparison evidence or `local_reference_comparison.status=not_provided`.
- **FR-011**: The system MUST release a traceable artifact set only after all hard gates pass.
- **FR-012**: The system MUST use immutable run evidence, immutable released run copies, and a mutable `release_manifest.json` pointer written last.
- **FR-013**: The system MUST keep prediction maps, prediction sheets, full prediction delivery, model training, external tabular downloads, FLDAS, GOSIF-GPP, VIIRS, local workstation execution, and undeclared non-Vertex inference out of scope.
- **FR-014**: The system MUST write all required reports using the Report Schemas in this spec.

### Key Entities

- **Feature Month**: One production month in `YYYY-MM` and `YYYYMM` forms.
- **Cloud Run Orchestrator**: Control-plane job that validates inputs, owns state
  transitions, submits Cloud Batch and Vertex AI jobs, and releases artifacts.
- **Cloud Batch Worker**: Heavy worker that runs the repository Docker image for
  GEE export monitoring and rasterio EVI extraction.
- **Docker Runtime Image**: Single immutable Artifact Registry image built from
  this repository and pinned by digest.
- **Model Package**: Immutable GCS package containing exported weights,
  inference code/reference, manifest, dependencies, and schemas.
- **GEE Export Evidence**: Processed raster plus export manifest for selected
  feature month.
- **EVI Evidence Package**: Rasterio extraction manifest, wide/long EVI outputs,
  and EVI validation report.
- **Monthly Model Feature/Base Input**: Model-ready monthly CSV plus summary JSON.
- **Vertex AI Custom Job**: Cloud inference job that runs the repository image
  inference entrypoint and writes three scope prediction CSVs.
- **Release Manifest**: Mutable current pointer for a feature month.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A run either fails before run-prefix acquisition with caller-visible Cloud Run status/log evidence, fails after run-prefix acquisition with terminal `run_summary.json` containing at least one hard-gate failure, or completes all required cloud E2E artifacts and releases successfully.
- **SC-002**: Each successful run produces a GEE export manifest, processed raster reference, two EVI wide tables, two EVI long tables, one EVI extraction manifest, and one EVI validation report.
- **SC-003**: 100% of successful base inputs match the selected-month scaffold row universe.
- **SC-004**: 100% of successful base inputs pass key, month, row-universe, and schema checks before inference.
- **SC-005**: 100% of successful runs complete Vertex AI custom-job inference and produce prediction tables satisfying Prediction Output Schema v1, row-universe equality, selected-month equality, required keys, and required result columns.
- **SC-006**: 100% of failed hard-gate, `release_failed`, or `release_conflict` runs leave the previous current release manifest unchanged.
- **SC-007**: 100% of releases are traceable through `release_manifest.json` to run id, input manifest, Docker image digest, GEE export manifest, EVI artifacts, base input, Vertex AI job, model package, inference report, prediction outputs, validation status, and release timestamp.
- **SC-008**: 100% of release runs use cloud-only runtime inputs and immutable image/model/package references.
- **SC-009**: 100% of successful release runs include a model package manifest, model package checksum/version, custom job command, custom job image digest, Vertex AI job manifest, inference report, and prediction output checksums.
- **SC-010**: 100% of release runs either provide local-to-cloud reference comparison evidence or explicitly record `local_reference_comparison.status=not_provided` while passing all cloud output contract gates.
- **SC-011**: 100% of failed preflight runs are caller-visible in Cloud Run status/logs, and 100% of post-prefix failures produce terminal `run_summary.json`.

## Evidence Mapping

| Requirement group | Grounding references | Support status |
| --- | --- | --- |
| EVI-only remote sensing scope and wide/long output names | `specs/001-cloud-base-input/evidence.md`; `docs/03_workflow_runbook.md`; `docs/04_output_inventory.md` | Grounded by existing repo evidence |
| Monthly base input schema, scaffold row universe, and fixed/slow/source panel contracts | `Final_harmonise/00_build_monthly_ipcch_base_input.py`; `tools/validate_ipcch_schema.py`; `docs/04_output_inventory.md` | Grounded by existing repo evidence |
| Local inference pipeline using base input and exported weights | `model_pipeline/run_operational_launch_inference.py`; `model_artifacts/launch_2026_04/model_package_manifest.json`; `Outcome/ipcch_unified/predictions/202604/*_predictions.csv` | Grounded by local validation evidence |
| Prediction output schema v1 | `model_pipeline/ipcch_launch_runtime/inference.py`; `model_pipeline/ipcch_launch_runtime/outputs.py`; local prediction CSV headers; monthly base input key contract | Required result columns derived from local outputs; `area_id`/`year`/`month` keys fixed as cloud release contract |
| Vertex AI custom-job runtime | User-selected target architecture in this patch | New implementation target; must produce cloud custom-job evidence |
| Cloud Run orchestrator, Cloud Batch worker, Docker image, GEE export ownership, rasterio extraction | User-selected target architecture and prior EVI cloud planning | New implementation target selected by product decision |
| Immutable run/release evidence and atomic release manifest | Prior Spec Kit spec plus user patch requirements | Product decision; implementation still new |
| Prediction maps, prediction sheets, full delivery, training, non-EVI remote sensing, external tabular downloads excluded | User patch requirements and prior scope boundaries | Product decision |
| Local path examples | `docs/03_workflow_runbook.md`; `docs/04_output_inventory.md` | Evidence examples only; not runtime inputs unless container-internal |

## Assumptions

- Exact GCP project ID, bucket, service account names, Artifact Registry image
  URI, and Vertex AI model package URI are deployment-time values, not unresolved
  specification decisions.
- `vertex_ai_custom_job` is the only v1 inference mode.
- Single-image v1 is used for all cloud runtime entrypoints.
- Prediction output tables follow the existing three-scope launch output naming.
- The combined fixed/slow feature file remains the first implementation contract.
- EVI `region_id` equals canonical `area_id`.
- Optional EVI and inference reference comparisons are advisory when required
  output contracts pass.

## Deployment-Time Values

The following values are required in the runtime/deployment manifest but are not
open specification decisions:

- Exact project ID.
- Exact bucket/object-store root.
- Exact service account names.
- Exact Artifact Registry image URI and digest.
- Exact Vertex AI model package URI and checksum/version.
- Exact optional EVI or inference reference sample URI.

## References

- `specs/001-cloud-base-input/evidence.md`
- `docs/superpowers/specs/2026-06-26-ipcch-cloud-monthly-base-input-design.md`
- `docs/03_workflow_runbook.md`
- `docs/04_output_inventory.md`
