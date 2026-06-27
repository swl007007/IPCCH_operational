# Release Artifact Contract

## Immutable Run Evidence

Run evidence is stored under:

```text
runs/{run_id}/...
```

Required evidence includes:

- run sentinel
- initial and terminal `run_summary.json`
- GEE processed raster and `gee_export_manifest.json`
- EVI wide outputs, long outputs, validation report, extraction manifest
- monthly base input CSV and summary JSON
- base input validation report
- Vertex AI job manifest
- inference report
- three prediction CSVs
- release step report for any release attempt
- logs under declared logs root

Run evidence must not be modified after terminal status.

## Immutable Released Run Prefix

Accepted release artifacts are stored under:

```text
released/{YYYYMM}/runs/{run_id}/...
```

v1 must copy these artifacts into the immutable released run prefix:

- `ipcch_monthly_base_input_YYYYMM.csv`
- `ipcch_monthly_base_input_YYYYMM_summary.json`
- `ipcch_launch_YYYYMM_scope_0m_predictions.csv`
- `ipcch_launch_YYYYMM_scope_6m_predictions.csv`
- `ipcch_launch_YYYYMM_scope_12m_predictions.csv`
- `base_input_validation_report.json`
- `inference_report.json`
- `vertex_ai_job_manifest.json`
- `release_step_report.json`
- `gee_export_manifest.json`
- `evi_validation_report.json`
- `evi_extraction_manifest.json`
- terminal `run_summary.json`
- accepted input manifest reference or manifest copy

v1 references these artifacts by immutable URI/generation/checksum instead of
copying them by default:

- processed GEE raster
- EVI mean wide output
- EVI standard-deviation wide output
- EVI mean long output
- EVI standard-deviation long output
- Cloud Run logs
- Cloud Batch logs
- Vertex AI logs
- model package

## Mutable Release Pointer

The current release pointer is:

```text
released/{YYYYMM}/release_manifest.json
```

Rules:

- It is the authoritative stable entry point for consumers.
- It is written last.
- It must use GCS generation precondition, lock, or equivalent guard.
- Previous current release remains unchanged on hard gate failure,
  `release_failed`, or `release_conflict`.
- If no previous release exists and manifest write fails, no current release
  exists.

## Consumer Rules

Consumers must:

- read `release_manifest.json` first
- follow paths/checksums recorded in the manifest
- treat bare aliases under `released/{YYYYMM}/` as convenience only unless a
  later implementation explicitly defines safe alias updates
- not infer completeness from folder listings

## Forbidden Released Artifact Families

Release must hard-fail if any of these appear in run/release artifact inventory:

- FLDAS extraction outputs
- GOSIF-GPP extraction outputs
- VIIRS extraction outputs
- external tabular download automation artifacts
- model training artifacts
- prediction maps
- prediction sheets
- full delivery/publication artifacts
- local workstation scoring outputs
- undeclared non-Vertex inference/scoring outputs
