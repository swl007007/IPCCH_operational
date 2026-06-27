# Implementation Plan: IPCCH Cloud Monthly E2E Feature Input and Inference

**Branch**: `001-cloud-base-input` | **Date**: 2026-06-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-cloud-base-input/spec.md`

## Summary

Build a GCP-only monthly production workflow for exactly one selected IPCCH
feature month. A Cloud Run Job acts as the orchestrator, validates a cloud input
manifest, acquires an immutable run prefix, submits a Cloud Batch worker for
GEE EVI export and rasterio zonal extraction, assembles and validates the
monthly model feature/base input, launches Vertex AI custom-job inference using
the immutable exported model package, validates three scope prediction CSVs, and
publishes an atomic `release_manifest.json` pointer to immutable accepted
artifacts.

The implementation preserves the existing repository contracts where possible:
EVI mean/std wide outputs, EVI long monthly outputs, the monthly base input CSV
and summary JSON, and the operational launch inference script. New work is
concentrated in cloud runtime wrappers, GCS artifact IO, manifest/report
schemas, rasterio extraction, release semantics, and cloud integration tests.

## Technical Context

**Language/Version**: Python 3.11 for the cloud runtime container. Existing
legacy ArcPy scripts remain reference-only and are not executed by this feature.

**Primary Dependencies**: Existing repo Python modules; `pandas`, `numpy`,
`rasterio`, GDAL-compatible geospatial stack, Google Cloud client libraries for
Storage, Batch, Vertex AI, IAM/service account checks as needed, Earth Engine
Python SDK, and the current operational launch inference dependencies packaged
inside one Artifact Registry image pinned by digest.

**Storage**: GCS object roots for input manifests, immutable run evidence,
staging, GEE exports, logs, immutable released copies, and the mutable
`released/{YYYYMM}/release_manifest.json` pointer. Artifact Registry stores the
single repository runtime image. Vertex AI custom-job outputs are copied or
referenced under the run inference prefix.

**Testing**: `pytest` for unit/contract tests; JSON Schema validation for
manifest/report contracts; local filesystem fake object-store tests for run
state and release behavior; mocked Google Cloud API tests for Cloud Run
orchestration, Batch submission, GEE polling, and Vertex AI custom-job
submission; optional gated GCP smoke test against a small selected month.

**Target Platform**: GCP only: Cloud Run Jobs for orchestration, Google Cloud
Batch for GEE export monitoring and rasterio EVI extraction, Vertex AI Custom
Jobs for inference, GCS for object storage, Artifact Registry for the runtime
image, and Earth Engine export to GCS.

**Project Type**: Operational data pipeline with CLI/job entrypoints and
machine-readable artifact contracts.

**Performance Goals**: One selected feature month completes within declared v1
timeouts: GEE polling every 60 seconds, GEE export timeout 6 hours, Cloud Batch
worker timeout 8 hours, Vertex AI custom-job timeout 2 hours, and at most two
retries for retryable worker/custom-job failures. Successful base input and
prediction row counts equal the selected-month scaffold row count.

**Constraints**: GCP-only runtime; no local workstation paths except
container-internal paths; EVI is the only remote-sensing family in scope; no
external tabular download automation; no model training; no prediction maps,
prediction sheets, or full delivery artifacts; single runtime image; image and
model package must be immutable; split least-privilege service accounts; run
IDs are immutable; release manifest is written last.

**Scale/Scope**: Exactly one `feature_month` and one `run_id` per run. Current
evidence month has 6,227 scaffold rows; design supports the selected-month
scaffold as the authoritative row universe. No historical replay or multi-month
backfill is included in this feature.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The repository constitution file is still a template with placeholder
principles and no enforceable project-specific gates. This plan therefore uses
the feature specification, evidence pack, and existing repository contracts as
the governing constraints.

Pre-design gate status: PASS.

Post-design gate status: PASS. Phase 1 artifacts preserve the feature scope,
do not add out-of-scope prediction delivery or non-EVI remote sensing, and
resolve planning decisions without adding new unresolved clarifications.

## Project Structure

### Documentation (this feature)

```text
specs/001-cloud-base-input/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── execution-contract.md
│   ├── input-manifest.schema.json
│   ├── report-contracts.md
│   └── release-artifact-contract.md
└── tasks.md              # Created by /speckit-tasks, not by /speckit-plan
```

### Source Code (repository root)

```text
cloud/
├── orchestrator/          # Cloud Run Job entrypoint, run state, release flow
├── batch/                 # Cloud Batch worker entrypoint for GEE/rasterio EVI
├── common/                # GCS IO, manifests, checksums, report writers
└── schemas/               # JSON schemas and schema loading helpers

docker/
└── Dockerfile             # Single repository runtime image

EVI/
├── 00_ee_export_evi.txt   # Existing EE JavaScript evidence/reference
└── 02_arcpy_extract_evi.py# Existing ArcPy reference, not cloud runtime

Final_harmonise/
└── 00_build_monthly_ipcch_base_input.py

model_pipeline/
├── run_operational_launch_inference.py
└── ipcch_launch_runtime/

tools/
├── reshape_remote_sensing_wide_to_long.py
├── validate_csv_contract.py
└── validate_ipcch_schema.py

tests/
├── test_build_monthly_ipcch_base_input.py
├── test_operational_launch_cli.py
├── test_operational_launch_input_contract.py
├── test_reshape_remote_sensing_wide_to_long.py
├── test_cloud_manifest_contract.py
├── test_cloud_orchestrator_release.py
├── test_cloud_batch_evi_worker.py
├── test_vertex_ai_custom_job_contract.py
└── test_release_artifact_contract.py
```

**Structure Decision**: Add a new `cloud/` package for cloud-native orchestration,
workers, manifest/report handling, and object-store abstractions while reusing
existing `Final_harmonise/`, `tools/`, and `model_pipeline/` logic through
container-local entrypoints. Add `docker/Dockerfile` for the single digest-pinned
runtime image. Keep existing ArcPy and EE JavaScript files as evidence/reference
only.

## Complexity Tracking

No constitution violations or unjustified complexity exceptions.
