# Quickstart: IPCCH Cloud Monthly E2E Feature Input and Inference

This quickstart describes the expected v1 operator/developer flow after the
implementation tasks are complete. It is not an implementation script.

## 1. Prepare Deployment Values

Create a deployment/input manifest that supplies GCP runtime values:

- `provider=gcp`
- `project_id`
- `region`
- `object_store_root_uri`
- `artifact_registry_image_uri` pinned by digest
- `repo_git_commit`
- `cloud_run_orchestrator_name=ipcch-monthly-e2e-orchestrator`
- `cloud_run_service_account`
- `cloud_batch_service_account`
- `vertex_ai_custom_job_service_account`
- `earth_engine_project_id`
- `vertex_ai_region`
- `vertex_ai_model_package_uri`
- `vertex_ai_model_package_checksum_or_version`
- `vertex_ai_custom_job_container_image_uri`
- `vertex_ai_custom_job_container_digest`
- `permission_model=split_least_privilege`

Exact project, bucket, service account, image, and model package values are
deployment-time inputs, not hardcoded in the spec.

## 2. Stage Required Cloud Inputs

Required cloud artifacts include:

- one-month scaffold for the selected feature month
- combined fixed/slow area features
- prepared source panel
- area geometry with canonical `area_id`
- GEE EVI export config
- schema/validator contracts
- immutable model package
- optional EVI or inference reference sample

Every required GCS artifact must have either a checksum plus
`checksum_algorithm=sha256` or an immutable generation/version reference unless
a waiver is explicitly declared.

## 3. Build and Publish the Runtime Image

Build the single repository runtime image and push it to Artifact Registry. A
release run must use a digest-pinned image reference.

The image must expose entrypoints for:

- manifest validation
- Cloud Batch GEE/rasterio EVI worker
- EVI validation
- monthly base input assembly
- base input validation
- Vertex AI custom-job inference
- release manifest writing

## 4. Dispatch One Monthly Run

Canonical dispatch:

```bash
gcloud run jobs execute ipcch-monthly-e2e-orchestrator \
  --region ${REGION} \
  --args="--feature-month=YYYY-MM,--run-id=RUN_ID,--input-manifest-uri=gs://.../input_manifest.json"
```

Expected behavior:

1. Cloud Run validates parameters and manifest.
2. Cloud Run acquires `runs/{run_id}/` with a sentinel generation precondition.
3. Cloud Run submits Cloud Batch for GEE export monitoring and rasterio EVI
   extraction.
4. Cloud Batch writes GEE and EVI evidence to the run prefix.
5. Cloud Run assembles and validates the monthly model feature/base input.
6. Cloud Run submits Vertex AI custom-job inference.
7. Cloud Run validates prediction outputs and forbidden side effects.
8. Cloud Run stages accepted release artifacts.
9. Cloud Run writes `release_step_report.json`.
10. Cloud Run writes `released/{YYYYMM}/release_manifest.json` last.

## 5. Inspect Successful Release

Read the release manifest first:

```text
released/{YYYYMM}/release_manifest.json
```

The release manifest is the authoritative stable entry point. Consumers should
read paths and checksums for the base input, summary, prediction outputs, EVI
evidence references, GEE export manifest, Vertex AI job manifest, inference
report, model package reference, and validation status from this manifest.

For local/fake validation or downstream tooling, use the release reader helper
rather than listing the release folder:

```python
from cloud.common.release_reader import read_release_manifest

release = read_release_manifest(store, "gs://.../released/YYYYMM/release_manifest.json")
```

The helper rejects bare release folders so consumers cannot infer completeness
from object listings instead of `release_manifest.json`.

## 6. Inspect Failure Evidence

Failure before run-prefix acquisition:

- inspect Cloud Run Job status/logs
- the existing `runs/{run_id}/` prefix must remain unmodified

Failure after run-prefix acquisition:

- inspect `runs/{run_id}/run_summary.json`
- inspect report files named in `artifact_paths`
- previous `released/{YYYYMM}/release_manifest.json` must remain unchanged

Release conflict:

- inspect `runs/{run_id}/release/release_step_report.json`
- run status should be `release_conflict` or `release_failed`
- previous current release remains authoritative

## 7. Expected Contract Artifacts

Successful run evidence:

- `runs/{run_id}/gee_exports/MOD13A3_EVI_YYYY_MM_processed.tif`
- `runs/{run_id}/gee_exports/gee_export_manifest.json`
- `runs/{run_id}/evi/EVI_mean_extraction_results.csv`
- `runs/{run_id}/evi/EVI_std_extraction_results.csv`
- `runs/{run_id}/evi/EVI_mean_monthly_long.csv`
- `runs/{run_id}/evi/EVI_std_monthly_long.csv`
- `runs/{run_id}/evi/evi_extraction_manifest.json`
- `runs/{run_id}/evi/evi_validation_report.json`
- `runs/{run_id}/assembly/ipcch_monthly_base_input_YYYYMM.csv`
- `runs/{run_id}/assembly/ipcch_monthly_base_input_YYYYMM_summary.json`
- `runs/{run_id}/qa/base_input_validation_report.json`
- `runs/{run_id}/inference/vertex_ai_job_manifest.json`
- `runs/{run_id}/inference/inference_report.json`
- `runs/{run_id}/inference/ipcch_launch_YYYYMM_scope_0m_predictions.csv`
- `runs/{run_id}/inference/ipcch_launch_YYYYMM_scope_6m_predictions.csv`
- `runs/{run_id}/inference/ipcch_launch_YYYYMM_scope_12m_predictions.csv`
- `runs/{run_id}/release/release_step_report.json`
- `runs/{run_id}/run_summary.json`

Current release:

- `released/{YYYYMM}/release_manifest.json`
- copied v1 release artifacts under `released/{YYYYMM}/runs/{run_id}/`

## 8. Non-Goals to Verify

The run must not produce or invoke:

- FLDAS extraction
- GOSIF-GPP extraction
- VIIRS extraction
- external tabular download automation
- model training
- prediction maps
- prediction sheets
- full prediction delivery artifacts
- local workstation scoring
- undeclared non-Vertex inference/scoring
