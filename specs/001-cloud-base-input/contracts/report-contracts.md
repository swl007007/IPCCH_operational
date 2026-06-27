# Report Contracts

All report timestamps use RFC 3339 / ISO-8601 UTC. Validation reports include
common fields unless explicitly stated otherwise:

- `schema_version`
- `feature_month`
- `run_id`
- `status`
- `hard_gates`
- `advisory_warnings`
- `record_only_metrics`
- `artifact_paths`
- `checksums`

Manifest/evidence reports may omit advisory and record-only fields only when the
spec allows it. They must still include `schema_version`, `feature_month`,
`run_id`, `status`, and artifact path or URI fields.

## Status Enums

Run terminal statuses:

- `running`
- `failed`
- `released`
- `release_failed`
- `release_conflict`

Validation report statuses:

- `passed`
- `failed`
- `passed_with_warnings`, only where declared

Release manifest status:

- `current`

Gate item statuses:

- `passed`
- `failed`
- `warning`
- `skipped`
- `not_applicable`

## Required Reports

| Report | Class | Required location |
| --- | --- | --- |
| `run_summary.json` | Manifest/evidence | `runs/{run_id}/run_summary.json` |
| `gee_export_manifest.json` | Manifest/evidence | `runs/{run_id}/gee_exports/gee_export_manifest.json` |
| `evi_extraction_manifest.json` | Manifest/evidence | `runs/{run_id}/evi/evi_extraction_manifest.json` |
| `evi_validation_report.json` | Validation | `runs/{run_id}/evi/evi_validation_report.json` |
| `ipcch_monthly_base_input_YYYYMM_summary.json` | Validation | `runs/{run_id}/assembly/` |
| `base_input_validation_report.json` | Validation | `runs/{run_id}/qa/base_input_validation_report.json` |
| `vertex_ai_job_manifest.json` | Manifest/evidence | `runs/{run_id}/inference/vertex_ai_job_manifest.json` |
| `inference_report.json` | Validation | `runs/{run_id}/inference/inference_report.json` |
| `release_step_report.json` | Manifest/evidence | `runs/{run_id}/release/release_step_report.json` |
| `release_manifest.json` | Manifest/evidence | `released/{YYYYMM}/release_manifest.json` |

## `run_summary.json`

Required top-level fields:

- `schema_version`
- `feature_month`
- `run_id`
- `status`
- `input_manifest_uri`
- `deployment`
- `container_image_digest`
- `cloud_run_job`
- `cloud_batch_job`
- `vertex_ai_job`
- `hard_gates`
- `advisory_warnings`
- `record_only_metrics`
- `artifact_paths`
- `checksums`
- `waivers`
- `release_attempted`
- `released`
- `release_manifest_path`
- `forbidden_side_effect_check`

## `gee_export_manifest.json`

Required top-level fields:

- `schema_version`
- `feature_month`
- `run_id`
- `earth_engine_project_id`
- `earth_engine_collection`
- `band`
- `date_window`
- `processing_params`
- `export_task_id`
- `export_status`
- `processed_raster_uri`
- `processed_raster_generation_or_version`
- `processed_raster_checksum`
- `created_at_utc`
- `status`
- `artifact_paths`
- `checksums`

## `evi_extraction_manifest.json`

Required top-level fields:

- `schema_version`
- `feature_month`
- `run_id`
- `worker_type`
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
- `source_raster_uri`
- `source_raster_generation_or_version`
- `geometry_uri`
- `geometry_version_or_checksum`
- `rasterio_version`
- `gdal_version`
- `pixel_inclusion_rule`
- `nodata_rule`
- `zone_count`
- `empty_zone_count`
- `log_uri`
- `status`
- `artifact_paths`
- `checksums`

`pixel_inclusion_rule` must equal `all_touched_false_center_inside` in v1.

## `evi_validation_report.json`

Required top-level fields:

- common validation report fields
- `output_contract_status`
- `wide_outputs`
- `long_outputs`
- `area_identity`
- `reference_comparison`

## Monthly base input summary JSON

Required top-level fields:

- common validation report fields
- `input_lineage`
- `row_count`
- `column_count`
- `scaffold_row_count`
- `key_columns`
- `join_coverage`
- `missingness`
- `evi_feature_sources`
- `source_join`
- `fixed_slow_join`

## `base_input_validation_report.json`

Required top-level fields:

- common validation report fields
- `scaffold_row_count`
- `base_input_row_count`
- `row_universe_match`
- `key_columns`
- `duplicate_key_count`
- `missing_key_counts`
- `schema_result`
- `join_coverage`
- `missingness`

## `vertex_ai_job_manifest.json`

Required top-level fields:

- `schema_version`
- `feature_month`
- `run_id`
- `vertex_ai_project_id`
- `vertex_ai_region`
- `vertex_ai_job_id`
- `vertex_ai_job_resource_name`
- `inference_mode`
- `model_package_uri`
- `model_version_or_checksum`
- `vertex_ai_custom_job_container_image_uri`
- `vertex_ai_custom_job_container_digest`
- `container_image_digest`
- `input_base_uri`
- `output_uri`
- `job_status`
- `created_at_utc`
- `completed_at_utc`
- `retry_policy`
- `vertex_ai_custom_job_timeout_seconds`
- `status`
- `artifact_paths`
- `checksums`

## `inference_report.json`

Required top-level fields:

- common validation report fields
- `vertex_ai_job_id`
- `input_base_path`
- `prediction_output_paths`
- `prediction_row_counts`
- `base_input_row_count`
- `row_universe_match`
- `key_columns`
- `duplicate_key_count`
- `missing_key_counts`
- `model_output_schema`
- `local_reference_comparison`
- `cloud_runtime_validation_status`
- `model_package_validation_status`
- `custom_job_command`
- `custom_job_exit_code`
- `custom_job_log_uri`
- `retry_policy`
- `vertex_ai_custom_job_timeout_seconds`
- `extra_columns`

## `release_step_report.json`

Required top-level fields:

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

## `release_manifest.json`

Required top-level fields:

- `schema_version`
- `feature_month`
- `accepted_run_id`
- `status`
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
