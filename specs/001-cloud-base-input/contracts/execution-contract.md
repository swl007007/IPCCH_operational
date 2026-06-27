# Execution Contract

## Canonical Cloud Run Dispatch

```bash
gcloud run jobs execute ipcch-monthly-e2e-orchestrator \
  --region ${REGION} \
  --args="--feature-month=YYYY-MM,--run-id=RUN_ID,--input-manifest-uri=gs://.../input_manifest.json"
```

Required parameters:

| Parameter | Rule |
| --- | --- |
| `--feature-month` | Required `YYYY-MM`; exactly one month. |
| `--run-id` | Required immutable run identifier; duplicate fails before modifying existing prefix. |
| `--input-manifest-uri` | Required `gs://` URI. |
| `--reference-sample-uri` | Optional advisory EVI and/or inference reference sample. |
| `--release-mode` | Optional; first supported value `release_on_success`. |

Exit behavior:

- Success exits `0` and terminal `run_summary.json.status=released`.
- Hard gate failure exits nonzero.
- Pre-run-prefix failure may only appear in Cloud Run status/logs.
- Post-prefix failure must write terminal `runs/{run_id}/run_summary.json`.

## Cloud Batch Worker Entrypoint

The implementation must provide one container entrypoint for EVI/GEE/rasterio
work. Logical command shape:

```bash
python3 -m cloud.batch.evi_worker \
  --feature-month YYYY-MM \
  --run-id RUN_ID \
  --input-manifest-uri gs://.../input_manifest.json \
  --run-root-uri gs://.../runs/RUN_ID/ \
  --gee-export-root-uri gs://.../runs/RUN_ID/gee_exports/ \
  --evi-output-root-uri gs://.../runs/RUN_ID/evi/ \
  --logs-root-uri gs://.../runs/RUN_ID/logs/
```

Required behavior:

- Export selected-month processed EVI raster from Earth Engine to GCS.
- Poll every 60 seconds by default.
- Fail after 21,600 seconds by default if GEE export is not complete.
- Run rasterio extraction with `all_touched=false`.
- Preserve one row per scaffold area.
- Write required GEE and EVI evidence artifacts.
- Exit nonzero on missing raster, invalid schema, timeout, or retry exhaustion.

Required outputs:

- `gee_exports/MOD13A3_EVI_YYYY_MM_processed.tif`
- `gee_exports/gee_export_manifest.json`
- `evi/EVI_mean_extraction_results.csv`
- `evi/EVI_std_extraction_results.csv`
- `evi/EVI_mean_monthly_long.csv`
- `evi/EVI_std_monthly_long.csv`
- `evi/evi_extraction_manifest.json`
- `evi/evi_validation_report.json`

## Monthly Assembly Entrypoint

The implementation may call the existing assembly script after localizing cloud
inputs into the container workspace:

```bash
python3 Final_harmonise/00_build_monthly_ipcch_base_input.py \
  --year YYYY \
  --month M \
  --scaffold /workspace/input/ipcch_scaffold_YYYYMM.csv \
  --historical-panel /workspace/input/source_panel.csv \
  --fixed-slow-features /workspace/input/ipcch_fixed_slow_features_by_area.csv \
  --output /workspace/assembly/ipcch_monthly_base_input_YYYYMM.csv \
  --summary-output /workspace/assembly/ipcch_monthly_base_input_YYYYMM_summary.json
```

The cloud wrapper must merge cloud-produced EVI long outputs according to the
implementation design before the final base input is validated. Required output
paths in GCS are:

- `runs/{run_id}/assembly/ipcch_monthly_base_input_YYYYMM.csv`
- `runs/{run_id}/assembly/ipcch_monthly_base_input_YYYYMM_summary.json`
- `runs/{run_id}/qa/base_input_validation_report.json`

## Vertex AI Custom Job Entrypoint

The Vertex AI wrapper must localize `input_base_uri` and model package contents
to container-internal paths and execute:

```bash
python3 model_pipeline/run_operational_launch_inference.py \
  --input /workspace/input/ipcch_monthly_base_input_YYYYMM.csv \
  --model-package /workspace/model_package \
  --output-dir /workspace/inference \
  --feature-month YYYY-MM \
  --no-map \
  --overwrite
```

Wrapper-level required arguments:

| Argument | Rule |
| --- | --- |
| `--input-base-uri` | `gs://` URI under run root or immutable released copy. |
| `--model-package-uri` | `gs://` URI with immutable checksum/generation/version. |
| `--feature-month` | `YYYY-MM`, must equal run feature month. |
| `--output-dir` | Must resolve to `runs/{run_id}/inference/`. |
| `--run-id` | Must equal run id. |

Required environment:

- `PROJECT_ID`
- `VERTEX_AI_REGION`
- `RUN_ID`
- `FEATURE_MONTH`
- `MODEL_PACKAGE_URI`
- `INPUT_BASE_URI`
- `INFERENCE_OUTPUT_URI`

Rules:

- Must not pass `--validate-only`.
- Must pass `--no-map`.
- Must add `year` and `month` columns to prediction CSVs when the local script
  emits only `feature_period`.
- Must copy three prediction CSVs, `vertex_ai_job_manifest.json`, and
  `inference_report.json` to the declared inference prefix.
- Default timeout is 7,200 seconds.
- Default retry max is 2 for retryable custom-job submission or transient
  runtime failures.

## Release Writer Contract

Logical command shape:

```bash
python3 -m cloud.orchestrator.release \
  --feature-month YYYY-MM \
  --run-id RUN_ID \
  --input-manifest-uri gs://.../input_manifest.json \
  --run-root-uri gs://.../runs/RUN_ID/ \
  --staging-root-uri gs://.../staging/RUN_ID/ \
  --release-root-uri gs://.../released/YYYYMM/
```

Rules:

- Verify all hard gates passed before release attempt.
- Copy v1 consumer artifacts and reports to
  `released/{YYYYMM}/runs/{run_id}/`.
- Reference processed GEE raster, EVI wide/long outputs, logs, and model package
  by immutable URI/generation/checksum.
- Write `runs/{run_id}/release/release_step_report.json`.
- Write `released/{YYYYMM}/release_manifest.json` last using a generation
  precondition or equivalent compare-and-swap guard.
