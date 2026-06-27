# Data Model: IPCCH Cloud Monthly E2E Feature Input and Inference

## FeatureMonth

Represents one selected production month.

Fields:
- `feature_month`: string, `YYYY-MM`.
- `yyyymm`: string, `YYYYMM`, derived from `feature_month`.
- `year`: integer, four digits.
- `month`: integer, 1-12.

Validation:
- Exactly one feature month per run.
- Every month-bearing input, output, report, and prediction table must match
  the selected feature month unless it is a fixed/vintage artifact.

## Run

Immutable execution attempt for one `FeatureMonth`.

Fields:
- `run_id`: string, unique under `object_store_root_uri`.
- `feature_month`: `FeatureMonth`.
- `status`: one of `running`, `failed`, `released`, `release_failed`,
  `release_conflict`.
- `input_manifest_uri`: cloud URI.
- `run_root_uri`: `gs://.../runs/{run_id}/`.
- `staging_root_uri`: `gs://.../staging/{run_id}/`.
- `release_root_uri`: `gs://.../released/{YYYYMM}/`.
- `logs_root_uri`: `gs://.../runs/{run_id}/logs/`.
- `container_image_digest`: immutable image digest.
- `hard_gates`, `advisory_warnings`, `record_only_metrics`.

State transitions:
- Preflight failure before sentinel: no run prefix modification; evidence is
  Cloud Run job status/logs only.
- `running` after run sentinel and initial `run_summary.json`.
- `failed` after any post-prefix hard gate before release.
- `release_failed` after release write failure that is not a concurrency loss.
- `release_conflict` after manifest generation-precondition or lock loss.
- `released` only after all hard gates pass and release manifest is current.

Validation:
- Duplicate `run_id` fails before modifying existing prefix.
- Terminal post-prefix run must have `run_summary.json`.

## Deployment

Cloud runtime configuration declared in the input manifest.

Fields:
- `provider`: must be `gcp`.
- `project_id`, `region`, `earth_engine_project_id`, `vertex_ai_region`.
- `object_store_root_uri`, `run_root_uri`, `staging_root_uri`,
  `release_root_uri`, `gee_export_root_uri`, `logs_root_uri`.
- `artifact_registry_image_uri`, `repo_git_commit`.
- `cloud_run_orchestrator_name`, `cloud_run_service_account`.
- `cloud_batch_service_account`, `cloud_batch_job_name_prefix`.
- `vertex_ai_inference_mode`: must be `vertex_ai_custom_job`.
- `vertex_ai_model_package_uri`.
- `vertex_ai_model_package_checksum_or_version`.
- `vertex_ai_custom_job_container_image_uri`.
- `vertex_ai_custom_job_container_digest`.
- `vertex_ai_custom_job_service_account`.
- `vertex_ai_custom_job_staging_root_uri`.
- `vertex_ai_custom_job_output_root_uri`.
- `permission_model`: must be `split_least_privilege`.

Validation:
- Required fields missing: hard gate.
- Non-GCP provider: hard gate.
- Shared service account in v1: hard gate.
- Tag-only image reference: hard gate.

## InputManifest

Machine-readable fact source for a run.

Fields:
- `manifest_version`: first supported value `ipcch-monthly-e2e-v1`.
- `feature_month`.
- `run_id`.
- `created_at_utc`: RFC 3339 / ISO-8601 UTC timestamp.
- `deployment`: `Deployment`.
- `artifacts`: array of `ArtifactEntry`.
- `waivers`: optional array of `Waiver`.

Validation:
- `feature_month` and `run_id` must equal execution parameters.
- Required artifact entries need immutable reference: checksum, generation,
  version id, image digest, or model version unless explicitly waived.
- Runtime paths must be `gs://`, Earth Engine identifiers, Vertex AI resource
  names, Artifact Registry image URIs, or container-internal paths.

## ArtifactEntry

Declared input or config artifact.

Fields:
- `artifact_id`: unique within manifest.
- `artifact_type`: enum from the spec (`scaffold`,
  `fixed_slow_area_features`, `source_panel`, `gee_evi_export_config`,
  `geometry`, `evi_reference_sample`, `schema_contract`, `docker_image`,
  `model_package`, `vertex_ai_inference_config`, `spatial_boundary`,
  `validator`).
- `required`: boolean.
- `uri`: required for GCS or mounted artifacts.
- `source_family`.
- `feature_month` or `vintage`.
- `schema_contract` or `schema_version`.
- `checksum`, `generation`, `version_id`, `image_digest`, or `model_version`.
- `checksum_algorithm`: `sha256` when checksum is supplied.

Validation:
- Missing required artifact: hard gate.
- Required artifact without immutable reference and without waiver: hard gate.
- Malformed schema/keys: hard gate.

## Waiver

Explicit waiver for an immutable-reference gap.

Fields:
- `artifact_id`.
- `waiver_type`.
- `reason`.
- `approved_by`.
- `approved_at_utc`.
- `expires_at_utc`, when applicable.

Validation:
- Waiver must be copied into `run_summary.json`.
- Waiver cannot bypass required row-universe, prediction schema, forbidden side
  effect, or release atomicity hard gates.

## Area

Canonical spatial unit.

Fields:
- `area_id`: canonical identifier.
- `admin_code`.
- `lat`, `lon`.
- Geometry record with `area_id`.

Validation:
- Every selected-month scaffold row maps to exactly one `area_id`.
- EVI `region_id` equals canonical `area_id` in v1.
- Fixed/slow features are unique by `area_id`.
- Missing, blank, duplicate, or many-to-many mappings are hard gates.

## Scaffold

One-month row universe for assembly.

Fields:
- `admin_code`, `lat`, `lon`, `year`, `month`.
- Optional `area_id`, which must equal normalized `admin_code`.

Validation:
- Exactly one selected feature month.
- No duplicate selected-month `(area_id, year, month)`.
- Successful base input row count equals scaffold row count.

## FixedSlowAreaFeatures

Area-level fixed/slow features.

Fields:
- `area_id`, `admin_code`, `lat`, `lon`.
- Fixed/slow columns defined by the `fixed-slow-area` schema contract.

Validation:
- Unique nonblank `area_id`.
- Joined to scaffold by `area_id`.

## SourcePanel

Prepared source panel values used for monthly assembly.

Fields:
- `admin_code`, `lat`, `lon`, `year`, `month`.
- Feature columns consumed by assembly.

Validation:
- Selected-month duplicate normalized `(admin_code as area_id, year, month)` is
  a hard gate.
- Selected-month rows may be absent only when recorded as missingness with
  `target_month_present_in_source=false`.

## GEEEVIExportConfig

Earth Engine source configuration for v1 EVI export.

Fields:
- `earth_engine_collection`: `MODIS/061/MOD13A3`.
- `band`: `EVI`.
- `date_window`: selected month start to first day of next month, exclusive.
- `processing_params`: scale handling, mask/nodata, dtype, CRS/resolution,
  export region.
- `feature_month`.
- `schema_contract`.
- source collection version label or immutable source version when available.

Validation:
- Processed raster is output evidence, not required input.
- Missing or malformed config: hard gate.

## GEEExportEvidence

Evidence for Earth Engine export.

Fields:
- `processed_raster_uri`.
- `processed_raster_generation_or_version` or `processed_raster_checksum`.
- `gee_export_manifest.json` fields from the spec.
- `export_task_id`, `export_status`, `created_at_utc`.

Validation:
- Export failure, missing raster, selected-month mismatch, or missing immutable
  raster reference: hard gate.

## EVIEvidencePackage

Rasterio extraction outputs.

Fields:
- `EVI_mean_extraction_results.csv`.
- `EVI_std_extraction_results.csv`.
- `EVI_mean_monthly_long.csv`.
- `EVI_std_monthly_long.csv`.
- `evi_validation_report.json`.
- `evi_extraction_manifest.json`.

Validation:
- Wide outputs keyed by `region_id`.
- `region_id` equals `area_id`.
- Long outputs contain exactly selected feature month.
- Long row count equals scaffold row count.
- `pixel_inclusion_rule=all_touched_false_center_inside`.

## MonthlyModelFeatureInput

Model-ready monthly base input.

Fields:
- `ipcch_monthly_base_input_YYYYMM.csv`.
- `ipcch_monthly_base_input_YYYYMM_summary.json`.
- Key columns `area_id`, `year`, `month`.
- EVI features from cloud-produced EVI long outputs.
- Fixed/slow and source panel features from manifest-declared cloud URIs.

Validation:
- One row per scaffold area.
- No duplicate `area_id/year/month`.
- Required keys nonblank.
- Passes `model-input-forecast` style validation before inference.

## ModelPackage

Immutable GCS model package for Vertex AI custom-job inference.

Fields:
- `model_package_manifest.json`.
- exported weights files.
- inference code package or code reference.
- dependency metadata.
- expected input/output schema versions.
- checksum, generation, version, or equivalent immutable reference.
- optional local validation evidence reference.

Validation:
- Missing manifest: hard gate.
- Missing immutable reference: hard gate.
- Expected input schema mismatch with base input validation schema: hard gate.
- Local validation does not satisfy cloud inference gate by itself.

## VertexAICustomJob

Cloud inference job.

Fields:
- `vertex_ai_job_manifest.json`.
- `inference_report.json`.
- command wrapper arguments and environment variables.
- custom job service account and image digest.
- timeout/retry settings.

Validation:
- Mode must be `vertex_ai_custom_job`.
- Registered Vertex AI Model resource is not required in v1.
- Custom job must use `--no-map` and must not use `--validate-only`.
- Custom job timeout default is 7200 seconds unless overridden.

## PredictionOutput

Three scope-specific prediction CSVs.

Files:
- `ipcch_launch_YYYYMM_scope_0m_predictions.csv`.
- `ipcch_launch_YYYYMM_scope_6m_predictions.csv`.
- `ipcch_launch_YYYYMM_scope_12m_predictions.csv`.

Required columns:
- `area_id`, `year`, `month`, `admin_code`, `_row_id`.
- `phase2_worse_score`, `phase2_worse_pred`.
- `phase3_worse_score`, `phase3_worse_pred`.
- `phase4_worse_score`, `phase4_worse_pred`.
- `phase5_worse_score`, `phase5_worse_pred`.
- `overall_phase_pred`, `feature_period`, `target_period`, `scope_months`,
  `model_package_id`, `source_input`.

Validation:
- One row per base input row in each scope file.
- No filtered outputs in v1.
- Duplicate `area_id/year/month` within scope or
  `area_id/year/month/scope_months` across inventory: hard gate.
- Extra columns allowed only if recorded in `inference_report.json`.

## Release

Accepted artifact set for a feature month.

Fields:
- Immutable released run prefix: `released/{YYYYMM}/runs/{run_id}/...`.
- Mutable pointer: `released/{YYYYMM}/release_manifest.json`.
- `released_copied_artifacts`.
- `released_referenced_artifacts`.

Validation:
- All hard gates must pass before release attempt.
- Release step report required for any release attempt.
- Manifest written last with generation precondition or equivalent guard.
- Previous current release remains unchanged on `release_failed` or
  `release_conflict`.
