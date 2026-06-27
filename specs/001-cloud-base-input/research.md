# Research: IPCCH Cloud Monthly E2E Feature Input and Inference

## Decision: Use Cloud Run Job as v1 orchestrator

**Rationale**: The feature has one explicit monthly dispatch, a bounded run
interface, and no interactive UI. Cloud Run Jobs match the canonical command in
the spec, support containerized orchestration, and can call Batch, Vertex AI,
and GCS APIs using a split least-privilege service account.

**Alternatives considered**:
- Cloud Run service HTTP endpoint: useful later, but adds request/auth surface
  not required by the first implementation.
- Workflows/Airflow: better for larger DAGs, but heavier than this single-month
  orchestrator and not selected in the spec.

## Decision: Use Cloud Batch for GEE export monitoring and rasterio EVI worker

**Rationale**: EVI export monitoring plus rasterio/GDAL zonal extraction is the
heavy geospatial part. Batch isolates longer-running compute from the Cloud Run
control plane and allows a single repository image to run GDAL/rasterio with an
ephemeral workspace.

**Alternatives considered**:
- Cloud Run performs extraction directly: simpler deployment, but weaker fit
  for heavy geospatial processing and long-running GDAL work.
- Earth Engine direct polygon reduction: previously rejected by user feedback
  as too slow and less precise for this use case.

## Decision: Keep v1 as single-image runtime

**Rationale**: One Artifact Registry image digest reduces provenance complexity
and makes release validation clear: the same immutable repository image provides
orchestrator helpers, Batch worker, assembly validation, inference wrapper, and
release writer. The Vertex AI custom job uses a different entrypoint in the same
image.

**Alternatives considered**:
- Separate inference image: useful if dependency conflicts appear, but v1
  planning assumes no proven dependency split yet.
- Local repository execution: explicitly out of scope and hard-gated.

## Decision: Use Vertex AI Custom Job, not Batch Prediction

**Rationale**: The existing model has been validated locally as exported weights
plus repository inference code. v1 does not require a registered Vertex AI Model
resource. A custom job can localize the model package and base input, run
`model_pipeline/run_operational_launch_inference.py`, enforce `--no-map`, and
copy three prediction CSVs to the declared run prefix.

**Alternatives considered**:
- Vertex AI Batch Prediction: requires a registered model-style interface that
  is not the current evidence.
- Local/non-Vertex scoring: explicitly forbidden by the spec.

## Decision: Wrap existing local scripts instead of rewriting assembly and inference first

**Rationale**: `Final_harmonise/00_build_monthly_ipcch_base_input.py`,
`tools/validate_ipcch_schema.py`, `tools/reshape_remote_sensing_wide_to_long.py`,
and `model_pipeline/run_operational_launch_inference.py` already encode key row,
schema, and output semantics. Cloud wrappers should localize cloud inputs to an
ephemeral container workspace, call or reuse the existing logic, and copy
contract outputs back to GCS.

**Alternatives considered**:
- Rewrite all assembly and inference logic into new cloud modules: higher risk
  and more revalidation burden.
- Keep local path-only scripts: violates cloud-only runtime requirement.

## Decision: Implement manifest/report contracts as JSON Schema plus typed helpers

**Rationale**: The spec requires machine-checkable validation, hard gates, and
immutable evidence. JSON Schema provides a stable artifact contract for input
manifests and reports; typed Python helpers can add cross-field checks that JSON
Schema cannot express, such as feature-month equality, object generation
presence, row-universe equality, and forbidden output family checks.

**Alternatives considered**:
- Ad hoc dictionaries only: faster initially, but weaker testability and less
  useful for release evidence.
- Database-backed state: unnecessary for one-run immutable object storage.

## Decision: Use GCS generation/checksum as the immutable object evidence model

**Rationale**: GCS is the common artifact store for inputs, run evidence,
staging, release copies, GEE exports, and logs. Recording object URI plus
generation/version or sha256 checksum satisfies the spec's immutability and
traceability requirements.

**Alternatives considered**:
- Local checksums only: insufficient for cloud overwrite protection.
- Overwriting released objects as source of truth: rejected by the immutable
  release design.

## Decision: Materialize only v1 consumer artifacts in released run prefix

**Rationale**: The released prefix should be stable and useful to downstream
consumers without duplicating large or upstream-owned evidence. v1 copies base
input, summary, prediction CSVs, validation reports, inference reports, release
step report, and manifests; it references GEE raster, EVI evidence, logs, and
model package by immutable URI/generation/checksum.

**Alternatives considered**:
- Copy every artifact: simpler browsing but expensive and redundant for rasters
  and logs.
- Copy only base input and predictions: insufficient audit trail.

## Decision: Use `all_touched=false` for v1 EVI zonal statistics

**Rationale**: Center-inside pixel inclusion is reproducible, common for zonal
statistics defaults, and was clarified as the v1 rule. Differences against an
optional ArcPy/local sample remain advisory when the output contract is valid.

**Alternatives considered**:
- `all_touched=true`: includes boundary pixels more broadly and may inflate
  zones; not selected.
- Manifest-selected rule: more flexible, but less deterministic for v1 tests.

## Decision: Use split least-privilege service accounts

**Rationale**: Cloud Run, Batch, and Vertex AI have distinct responsibilities and
write prefixes. Separate service accounts make permission failures easier to
diagnose and reduce blast radius.

**Alternatives considered**:
- Single broad runtime service account: simpler setup, but weaker audit and
  security posture.

## Decision: Treat deployment-time project/bucket/service-account values as manifest inputs

**Rationale**: The spec should be implementation-ready without hardcoding a real
GCP project or bucket. Exact project ID, bucket, image URI, model package URI,
and service account names are required runtime/deployment manifest fields, not
open spec decisions.

**Alternatives considered**:
- Hardcode IFPRI project values in the plan: not portable and not available in
  the repo.
- Leave values as unresolved decisions: would block `/speckit-tasks`.
