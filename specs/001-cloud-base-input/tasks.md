# Tasks: IPCCH Cloud Monthly E2E Feature Input and Inference

**Input**: Design documents from `specs/001-cloud-base-input/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: Included because the specification requires machine-checkable validation gates, report schemas, artifact contracts, and independent acceptance scenarios.

**Organization**: Tasks are grouped by user story so each story can be implemented and validated independently after shared foundations are complete.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create cloud runtime structure, dependency declarations, and test scaffolding without changing existing local contracts.

- [X] T001 [Req: FR-001, FR-002, FR-014, SC-001] Create cloud package directories and `__init__.py` files in `cloud/`, `cloud/common/`, `cloud/orchestrator/`, `cloud/batch/`, `cloud/schemas/`, and `tests/cloud/`
- [X] T002 [Req: FR-002, FR-003, FR-004, FR-005, FR-008, SC-008] Add cloud runtime dependency manifest in `requirements-cloud.txt` for Google Cloud clients, Earth Engine Python SDK, rasterio/GDAL-compatible geospatial stack, pandas, numpy, jsonschema, and pytest helpers
- [X] T003 [Req: FR-003, FR-008, SC-008, SC-009] Add single-image runtime Dockerfile in `docker/Dockerfile` that installs repo code plus `requirements-cloud.txt` and exposes Python entrypoints (depends on T002)
- [X] T004 [P] [Req: FR-001, FR-014, SC-008] Add sample cloud input manifest fixture in `tests/fixtures/cloud/input_manifest_202604_valid.json`
- [X] T005 [P] [Req: FR-001, FR-003, FR-013, FR-014, SC-008] Add sample invalid cloud manifest fixtures in `tests/fixtures/cloud/input_manifest_missing_digest.json` and `tests/fixtures/cloud/input_manifest_local_path.json`
- [X] T006 [P] [Req: FR-005, SC-002] Add small EVI raster and geometry fixture plan stub in `tests/fixtures/cloud/README.md` documenting generated test fixture expectations
- [X] T007 [P] [Req: FR-014, SC-001] Add cloud test package initializer in `tests/cloud/__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Implement shared schema, object-store, report, checksum, and runtime primitives that all user stories depend on.

**CRITICAL**: No user story work can begin until this phase is complete.

- [X] T008 [Req: FR-014, SC-008] Add input manifest JSON schema package copy in `cloud/schemas/input-manifest.schema.json` from `specs/001-cloud-base-input/contracts/input-manifest.schema.json` (depends on T001)
- [X] T009 [P] [Req: FR-001, FR-003, FR-013, FR-014, SC-008] Add manifest contract tests in `tests/cloud/test_manifest_contract.py` for valid fixture, missing immutable reference, local workstation URI, non-GCP provider, tag-only image, and shared service account failures (depends on T004, T005, T007, T008)
- [X] T010 [Req: FR-001, FR-003, FR-013, FR-014, SC-008] Implement manifest loader and cross-field validator in `cloud/common/manifest.py` for feature month/run id equality, required artifact immutable references, cloud URI rules, digest pinning, and `split_least_privilege` (depends on T008, T009)
- [X] T011 [P] [Req: FR-014, SC-001, SC-007, SC-009, SC-011] Add report schema tests in `tests/cloud/test_report_contracts.py` for required top-level fields and allowed statuses in run, GEE, EVI, base input, Vertex AI, inference, release step, and release manifest reports (depends on T001)
- [X] T012 [Req: FR-014, SC-001, SC-007, SC-009, SC-011] Implement report builders and status enums in `cloud/common/reports.py` for all report classes in `specs/001-cloud-base-input/contracts/report-contracts.md` (depends on T011)
- [X] T013 [P] [Req: FR-003, FR-008, FR-011, FR-012, SC-007, SC-008, SC-009] Add checksum and object reference tests in `tests/cloud/test_object_refs.py` for sha256, GCS generation/version metadata, and missing immutable references (depends on T001)
- [X] T014 [Req: FR-003, FR-008, FR-011, FR-012, SC-007, SC-008, SC-009] Implement checksum and immutable object reference helpers in `cloud/common/object_refs.py` (depends on T013)
- [X] T015 [P] [Req: FR-011, FR-012, SC-006, SC-007] Add local fake object-store tests in `tests/cloud/test_object_store.py` for read/write/copy/list/generation-precondition behavior (depends on T001)
- [X] T016 [Req: FR-011, FR-012, SC-006, SC-007] Implement object-store abstraction in `cloud/common/object_store.py` with local fake backend and GCS backend interface boundaries (depends on T014, T015)
- [X] T017 [P] [Req: FR-001, FR-011, FR-012, SC-001, SC-011] Add run state tests in `tests/cloud/test_run_state.py` for sentinel acquisition, duplicate `run_id`, pre-prefix failure, terminal summary, and immutable run prefix behavior (depends on T012, T016)
- [X] T018 [Req: FR-001, FR-011, FR-012, SC-001, SC-011] Implement run state manager in `cloud/orchestrator/run_state.py` for sentinel creation, initial/terminal `run_summary.json`, and duplicate run preflight handling (depends on T012, T016, T017)
- [X] T019 [P] [Req: FR-007, FR-013, SC-005] Add forbidden side-effect inventory tests in `tests/cloud/test_forbidden_side_effects.py` for allowed prefixes, forbidden output families, and ignored container temp files (depends on T016)
- [X] T020 [Req: FR-007, FR-013, SC-005] Implement forbidden side-effect scanner in `cloud/common/forbidden_side_effects.py` using checked prefixes, allowed prefixes, forbidden filename patterns, and observed invocation metadata (depends on T016, T019)
- [X] T021 [P] [Req: FR-002, FR-004, FR-008, SC-001] Add cloud runtime config defaults tests in `tests/cloud/test_runtime_defaults.py` for GEE poll 60s, GEE export 21600s, Batch 28800s, Vertex AI custom job 7200s, and max retries 2 (depends on T010)
- [X] T022 [Req: FR-002, FR-004, FR-008, SC-001] Implement runtime defaults and retry policy resolver in `cloud/common/runtime_config.py` (depends on T010, T021)

**Checkpoint**: Foundation ready. Manifest validation, object-store operations, report writers, run state, forbidden side-effect scanning, and runtime defaults are available.

---

## Phase 3: User Story 1 - Run Cloud E2E Monthly Production (Priority: P1) - MVP

**Goal**: One cloud-only dispatch produces EVI features, monthly model feature/base input, Vertex AI custom-job inference outputs, and current release manifest for one feature month.

**Independent Test**: Execute the Cloud Run orchestrator entrypoint with a valid manifest against mocked/fake cloud services and verify Cloud Run orchestration, Cloud Batch worker completion, GEE export evidence, EVI artifacts, base input, Vertex AI custom-job inference, prediction CSVs, release step report, and release manifest.

### Tests for User Story 1

- [X] T023 [P] [US1] [Req: FR-001, FR-002, FR-011, FR-012, SC-001, SC-006, SC-011] Add orchestrator contract test in `tests/cloud/test_orchestrator_contract.py` for successful end-to-end fake run and duplicate `run_id` preflight failure (depends on T018, T020, T022)
- [X] T024 [P] [US1] [Req: FR-002, FR-004, FR-005, FR-014, SC-002] Add Cloud Batch worker contract test in `tests/cloud/test_cloud_batch_evi_worker.py` for GEE export manifest, processed raster reference, EVI wide outputs, EVI long outputs, and extraction manifest paths (depends on T012, T016, T022)
- [X] T025 [P] [US1] [Req: FR-005, SC-002] Add rasterio zonal statistics test in `tests/cloud/test_rasterio_evi_extraction.py` for `all_touched=false`, empty zone preservation, `region_id == area_id`, and selected-month long row count (depends on T006)
- [X] T026 [P] [US1] [Req: FR-006, FR-007, SC-003, SC-004] Add monthly assembly wrapper test in `tests/cloud/test_monthly_assembly_wrapper.py` for cloud-localized scaffold/source/fixed/EVI inputs and model-input-forecast validation report output (depends on T010, T016)
- [X] T027 [P] [US1] [Req: FR-008, FR-009, FR-010, SC-005, SC-009, SC-010] Add Vertex AI custom job wrapper test in `tests/cloud/test_vertex_ai_custom_job_contract.py` for command arguments, `--no-map`, no `--validate-only`, year/month enrichment, three prediction CSVs, and `local_reference_comparison` cases for reference absent, reference provided, advisory numeric differences, and `status=not_provided` (depends on T012, T016)
- [X] T028 [P] [US1] [Req: FR-011, FR-012, SC-006, SC-007] Add release writer test in `tests/cloud/test_release_writer.py` for copied v1 artifacts, referenced large evidence, checksum verification, and manifest write-last behavior (depends on T012, T016)

### Implementation for User Story 1

- [X] T029 [US1] [Req: FR-001, FR-002, SC-001, SC-011] Implement Cloud Run orchestrator CLI in `cloud/orchestrator/main.py` with `--feature-month`, `--run-id`, `--input-manifest-uri`, optional `--reference-sample-uri`, and optional `--release-mode` (depends on T010, T018, T022, T023)
- [X] T030 [US1] [Req: FR-002, FR-003, SC-001, SC-008] Implement Cloud Batch submitter interface in `cloud/orchestrator/batch_client.py` for job name prefix, image digest, service account, timeout, retry policy, and worker arguments (depends on T022, T024)
- [X] T031 [US1] [Req: FR-004, SC-002] Implement Earth Engine EVI export helper in `cloud/batch/gee_export.py` for `MODIS/061/MOD13A3`, `EVI`, selected-month date window, raw scaled integer export, and GCS raster evidence metadata (depends on T024)
- [X] T032 [US1] [Req: FR-005, SC-002] Implement rasterio EVI extraction in `cloud/batch/evi_extract.py` for geometry reprojection, `all_touched=false`, mean/std computation, empty zone rows, and `region_id == area_id` enforcement (depends on T025, T031)
- [X] T033 [US1] [Req: FR-002, FR-004, FR-005, FR-014, SC-001, SC-002] Implement Cloud Batch worker CLI in `cloud/batch/evi_worker.py` to run GEE export, poll with defaults, execute rasterio extraction, write required EVI/GEE reports, and exit nonzero on hard gates (depends on T012, T016, T022, T031, T032)
- [X] T034 [US1] [Req: FR-005, SC-002] Implement EVI wide-to-long writer in `cloud/batch/evi_outputs.py` producing `EVI_mean_monthly_long.csv` and `EVI_std_monthly_long.csv` with exactly selected-month rows (depends on T032)
- [X] T035 [US1] [Req: FR-006, SC-003] Implement monthly assembly wrapper in `cloud/orchestrator/assembly.py` that localizes cloud inputs, calls or reuses `Final_harmonise/00_build_monthly_ipcch_base_input.py`, merges cloud-produced EVI long outputs, and writes assembly artifacts (depends on T026, T034)
- [X] T036 [US1] [Req: FR-007, SC-004] Implement base input validation wrapper in `cloud/orchestrator/base_input_validation.py` using `tools/validate_ipcch_schema.py --mode model-input-forecast` semantics and row-universe checks (depends on T012, T035)
- [X] T037 [US1] [Req: FR-003, FR-008, SC-005, SC-008, SC-009] Implement Vertex AI custom job submitter in `cloud/orchestrator/vertex_client.py` for custom-job mode, same image digest, service account, timeout, retry policy, staging/output roots, and job metadata capture (depends on T022, T027)
- [X] T038 [US1] [Req: FR-008, FR-009, FR-010, FR-013, SC-005, SC-009, SC-010] Implement Vertex AI inference wrapper in `cloud/orchestrator/inference.py` that localizes base input/model package, runs `model_pipeline/run_operational_launch_inference.py --no-map --overwrite`, forbids `--validate-only`, enriches `year`/`month`, validates three prediction CSVs, and writes `local_reference_comparison` with reference-match evidence or `status=not_provided` (depends on T027, T037)
- [X] T039 [US1] [Req: FR-008, SC-008, SC-009] Implement model package validation in `cloud/orchestrator/model_package.py` for manifest presence, immutable checksum/version, expected schema match, and local validation evidence recording (depends on T010, T014)
- [X] T040 [US1] [Req: FR-011, FR-012, FR-014, SC-006, SC-007] Implement release writer in `cloud/orchestrator/release.py` to stage copied artifacts, reference large evidence, verify checksums/generations, write `release_step_report.json`, and update `release_manifest.json` last (depends on T028, T036, T038, T039)
- [X] T041 [US1] [Req: FR-001, FR-002, FR-007, FR-011, FR-013, SC-001, SC-011] Wire orchestrator execution sequence in `cloud/orchestrator/main.py` from manifest validation through Batch, assembly, Vertex AI, forbidden side-effect scan, release, and terminal run summary (depends on T029, T030, T033, T036, T038, T040, T020)
- [X] T042 [US1] [Req: FR-003, FR-008, SC-008, SC-009] Add Docker image entrypoint commands in `docker/Dockerfile` documentation comments or labels for orchestrator, Batch worker, and Vertex AI custom-job wrapper (depends on T003, T029, T033, T038)
- [X] T043 [US1] [Req: FR-001, FR-002, FR-004, FR-005, FR-006, FR-007, FR-008, FR-009, FR-010, FR-011, FR-012, FR-013, FR-014, SC-001, SC-002, SC-003, SC-004, SC-005, SC-006, SC-007, SC-008, SC-009, SC-010, SC-011] Run US1 targeted tests with `python3 -m pytest tests/cloud/test_orchestrator_contract.py tests/cloud/test_cloud_batch_evi_worker.py tests/cloud/test_rasterio_evi_extraction.py tests/cloud/test_monthly_assembly_wrapper.py tests/cloud/test_vertex_ai_custom_job_contract.py tests/cloud/test_release_writer.py` and record results in `specs/001-cloud-base-input/tasks.md` notes (depends on T041, T042)

**Checkpoint**: User Story 1 is independently functional as the MVP cloud E2E run using mocked/fake cloud services.

---

## Phase 4: User Story 2 - Audit EVI Export and Rasterio Extraction (Priority: P2)

**Goal**: A reviewer can audit GEE task metadata, processed raster evidence, rasterio extraction metadata, EVI wide/long outputs, EVI validation report, and optional advisory reference comparison.

**Independent Test**: Inspect a successful run's EVI evidence package and verify the GEE export manifest, processed raster URI and immutable reference, Cloud Batch worker metadata, extraction manifest, EVI wide/long tables, validation report, and optional advisory comparison fields.

### Tests for User Story 2

- [X] T044 [P] [US2] [Req: FR-005, FR-014, SC-002] Add EVI validation report contract test in `tests/cloud/test_evi_validation_report.py` for output contract status, wide outputs, long outputs, area identity, reference comparison, and advisory warning statuses (depends on T033, T034)
- [X] T045 [P] [US2] [Req: FR-005, SC-002] Add EVI reference comparison test in `tests/cloud/test_evi_reference_comparison.py` for absent sample, malformed optional sample, zero matched observations, insufficient correlation pairs, and advisory numeric differences (depends on T033, T034)
- [X] T046 [P] [US2] [Req: FR-004, FR-014, SC-002] Add GEE export manifest audit test in `tests/cloud/test_gee_export_manifest.py` for task id, export status, date window, processing params, raster generation/checksum, and selected-month mismatch failure (depends on T031)

### Implementation for User Story 2

- [X] T047 [US2] [Req: FR-004, FR-014, SC-002] Implement GEE export manifest builder in `cloud/batch/gee_export.py` with all required audit fields and selected-month validation (depends on T031, T046)
- [X] T048 [US2] [Req: FR-005, FR-014, SC-002] Implement EVI validation report builder in `cloud/batch/evi_validation.py` for wide schema, long schema, area identity, row count, empty zone count, and advisory warning state (depends on T034, T044)
- [X] T049 [US2] [Req: FR-005, SC-002] Implement optional EVI reference comparison in `cloud/batch/evi_reference.py` with advisory-only differences, zero-match handling, insufficient-pair handling, and correlation summaries (depends on T045)
- [X] T050 [US2] [Req: FR-004, FR-005, FR-014, SC-002] Wire EVI audit outputs into `cloud/batch/evi_worker.py` so `evi_extraction_manifest.json`, `evi_validation_report.json`, and `gee_export_manifest.json` contain all US2 audit fields (depends on T047, T048, T049)
- [X] T051 [US2] [Req: FR-004, FR-005, FR-014, SC-002] Run US2 targeted tests with `python3 -m pytest tests/cloud/test_evi_validation_report.py tests/cloud/test_evi_reference_comparison.py tests/cloud/test_gee_export_manifest.py` and record results in `specs/001-cloud-base-input/tasks.md` notes (depends on T050)

**Checkpoint**: User Story 2 provides complete EVI audit evidence without changing US1 release eligibility when only advisory EVI numeric differences occur.

---

## Phase 5: User Story 3 - Consume Traceable E2E Release (Priority: P3)

**Goal**: Downstream consumers can use one stable release manifest to locate accepted base input, summary, EVI evidence, GEE evidence, Vertex AI job manifest, inference report, prediction outputs, model package reference, Docker image digest, validation status, and release timestamp.

**Independent Test**: Read `released/{YYYYMM}/release_manifest.json` after a successful fake run and verify it points to immutable accepted artifacts, copied v1 release payloads, referenced evidence, checksums, and current release status; verify release conflicts leave the previous manifest unchanged.

### Tests for User Story 3

- [X] T052 [P] [US3] [Req: FR-011, FR-012, SC-006, SC-007] Add release manifest contract test in `tests/cloud/test_release_manifest_contract.py` for all required fields, `status=current`, copied artifact entries, referenced artifact entries, and checksum fields (depends on T040)
- [X] T053 [P] [US3] [Req: FR-012, SC-006] Add release conflict test in `tests/cloud/test_release_conflict.py` for generation-precondition loss, `release_conflict` status, and previous manifest unchanged behavior (depends on T040)
- [X] T054 [P] [US3] [Req: FR-011, SC-007] Add downstream consumer smoke test in `tests/cloud/test_release_consumer.py` that reads only `release_manifest.json` to locate base input, summary, prediction outputs, and evidence references (depends on T040)

### Implementation for User Story 3

- [X] T055 [US3] [Req: FR-011, FR-012, FR-014, SC-007] Implement release manifest typed builder in `cloud/orchestrator/release_manifest.py` with required copied/referenced artifact fields, validation status, inference status, advisory warning state, timestamp, and immutable references (depends on T052)
- [X] T056 [US3] [Req: FR-012, SC-006] Implement release conflict handling in `cloud/orchestrator/release.py` for generation-precondition failure, `release_conflict` status, unchanged previous manifest, and no-current-release case (depends on T053, T055)
- [X] T057 [US3] [Req: FR-011, SC-007] Implement downstream manifest reader helper in `cloud/common/release_reader.py` that resolves consumer paths only from `release_manifest.json` and rejects bare folder inference (depends on T054, T055)
- [X] T058 [US3] [Req: FR-011, FR-014, SC-007] Update quickstart validation examples in `specs/001-cloud-base-input/quickstart.md` with the implemented release manifest reader command or helper path (depends on T057)
- [X] T059 [US3] [Req: FR-011, FR-012, SC-006, SC-007] Run US3 targeted tests with `python3 -m pytest tests/cloud/test_release_manifest_contract.py tests/cloud/test_release_conflict.py tests/cloud/test_release_consumer.py` and record results in `specs/001-cloud-base-input/tasks.md` notes (depends on T056, T057, T058)

**Checkpoint**: User Story 3 provides traceable release consumption and safe concurrent release semantics.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validate integration, update documentation, and harden cross-cutting behavior after selected user stories are complete.

- [X] T060 [P] [Req: FR-001, FR-011, FR-012, FR-014, SC-001, SC-007, SC-011] Add end-to-end fake cloud quickstart test in `tests/cloud/test_quickstart_fake_cloud.py` covering manifest validation through release manifest readback (depends on T041, T050, T056)
- [X] T061 [P] [Req: FR-003, FR-008, SC-008, SC-009] Add dependency and Docker smoke checks in `tests/cloud/test_runtime_image_contract.py` for single-image digest metadata and required entrypoint availability (depends on T042)
- [X] T062 [P] [Req: FR-013, FR-014, SC-007, SC-008] Update `docs/03_workflow_runbook.md` with a cloud E2E monthly run section pointing to `specs/001-cloud-base-input/quickstart.md` and keeping local ArcPy workflow as reference-only (depends on T041, T050, T056)
- [X] T063 [P] [Req: FR-011, FR-013, FR-014, SC-007] Update `docs/04_output_inventory.md` with cloud run/release artifact inventory and forbidden output family notes (depends on T040, T055)
- [X] T064 [Req: FR-006, FR-007, FR-008, FR-009, FR-013, SC-003, SC-004, SC-005] Run existing regression tests with `python3 -m pytest tests/test_build_monthly_ipcch_base_input.py tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/test_reshape_remote_sensing_wide_to_long.py` and record results in `specs/001-cloud-base-input/tasks.md` notes (depends on T043)
- [X] T065 [Req: FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-009, FR-010, FR-011, FR-012, FR-013, FR-014, SC-001, SC-002, SC-003, SC-004, SC-005, SC-006, SC-007, SC-008, SC-009, SC-010, SC-011] Run cloud contract tests with `python3 -m pytest tests/cloud` and record results in `specs/001-cloud-base-input/tasks.md` notes (depends on T009, T043, T051, T059, T060, T061)
- [X] T066 [Req: FR-014, SC-007, SC-008, SC-011] Run artifact validation checks with `python3 -m json.tool specs/001-cloud-base-input/contracts/input-manifest.schema.json` and `git diff --check -- specs/001-cloud-base-input cloud docker tests docs` (depends on T062, T063, T064, T065)
- [X] T067 [Req: FR-001, FR-002, FR-004, FR-005, FR-006, FR-008, FR-009, FR-010, FR-011, FR-012, FR-013, FR-014, SC-001, SC-002, SC-005, SC-006, SC-007, SC-008, SC-009, SC-010, SC-011] Add optional gated live GCP smoke test in `tests/cloud/test_gcp_smoke_monthly_e2e.py` for one small selected month, skipped unless explicit GCP smoke environment variables are present, covering Cloud Run dispatch, Cloud Batch/GEE/rasterio completion, Vertex AI custom-job completion, release manifest creation, and forbidden side-effect absence (depends on T065, T066)

---

## Execution Wave DAG

Tasks in the same wave can run in parallel after their listed dependencies are satisfied.

- **Wave 1**: T001, T002, T004, T005, T006, T007
- **Wave 2**: T003, T008, T011, T013, T015, T025
- **Wave 3**: T009, T012, T014
- **Wave 4**: T010, T016
- **Wave 5**: T017, T019, T021, T026, T027, T028, T039
- **Wave 6**: T018, T020, T022
- **Wave 7**: T023, T024, T037
- **Wave 8**: T029, T030, T031, T038
- **Wave 9**: T032, T046
- **Wave 10**: T033, T034, T047
- **Wave 11**: T035, T042, T044, T045
- **Wave 12**: T036, T048, T049, T061
- **Wave 13**: T040, T050
- **Wave 14**: T041, T051, T052, T053, T054
- **Wave 15**: T043, T055
- **Wave 16**: T056, T057, T063, T064
- **Wave 17**: T058, T060, T062
- **Wave 18**: T059
- **Wave 19**: T065
- **Wave 20**: T066
- **Wave 21**: T067

## Requirement Traceability Matrix

| Requirement ID | Covered by tasks | Coverage note |
| --- | --- | --- |
| FR-001 | T001, T004, T005, T009, T010, T017, T018, T023, T029, T041, T043, T060, T065, T067 | GCP-only dispatch, manifest preflight, run-state handling, orchestrator CLI, E2E orchestration tests, final cloud contract gate, and optional live GCP smoke. |
| FR-002 | T001, T002, T021, T022, T023, T024, T029, T030, T033, T041, T043, T065, T067 | Cloud Run/Cloud Batch structure, runtime defaults, worker contracts, submitter, worker CLI, orchestration wiring, cloud tests, and optional live GCP smoke. |
| FR-003 | T002, T003, T005, T009, T010, T013, T014, T030, T037, T042, T061, T065 | Single-image dependency/Docker setup, digest validation, object references, worker/custom-job image use, entrypoint labels, and image smoke tests. |
| FR-004 | T002, T021, T022, T024, T031, T033, T043, T046, T047, T050, T051, T065, T067 | Earth Engine export dependencies/defaults, GEE export helper, manifest tests/builders, worker wiring, US1/US2 tests, cloud test gate, and optional live GCP smoke. |
| FR-005 | T002, T006, T024, T025, T032, T033, T034, T043, T044, T045, T048, T049, T050, T051, T065, T067 | Rasterio/GDAL setup, raster/geometry fixtures, raster extraction, EVI wide/long outputs, EVI validation/reference reports, tests, and optional live GCP smoke. |
| FR-006 | T026, T035, T043, T064, T065, T067 | Monthly assembly wrapper tests/implementation, US1 targeted tests, regression tests, cloud test gate, and optional live GCP smoke. |
| FR-007 | T019, T020, T026, T036, T041, T043, T064, T065 | Forbidden side-effect scanner, base-input validation wrapper, orchestration placement before inference, targeted/regression/cloud tests. |
| FR-008 | T002, T003, T013, T014, T021, T022, T027, T037, T038, T039, T042, T043, T061, T064, T065, T067 | Vertex custom-job dependencies/image/object refs/defaults, wrapper tests, submitter, inference wrapper, model package validation, Docker smoke, regression/cloud tests, and optional live GCP smoke. |
| FR-009 | T027, T038, T043, T064, T065, T067 | Prediction schema tests, inference wrapper validation, US1 targeted tests, regression tests, cloud test gate, and optional live GCP smoke. |
| FR-010 | T027, T038, T043, T065, T067 | Local-to-cloud inference comparison and `not_provided` cases in wrapper tests/implementation plus targeted, cloud, and optional live GCP smoke tests. |
| FR-011 | T013, T014, T015, T016, T017, T018, T023, T028, T040, T041, T043, T052, T054, T055, T057, T058, T059, T060, T063, T065, T067 | Traceable release inputs, object-store/run-state foundations, release writer, manifest builder/reader, docs, US3 tests, quickstart, cloud gate, and optional live GCP smoke. |
| FR-012 | T013, T014, T015, T016, T017, T018, T023, T028, T040, T043, T052, T053, T055, T056, T059, T060, T065, T067 | Immutable run/release evidence, generation preconditions, release conflict handling, release tests, E2E quickstart, cloud gate, and optional live GCP smoke. |
| FR-013 | T005, T009, T010, T019, T020, T038, T041, T043, T062, T063, T064, T065, T067 | Invalid manifest fixtures, forbidden side-effect scanner, no local/non-Vertex inference, orchestration scan, docs, regression tests, cloud gate, and optional live GCP smoke. |
| FR-014 | T001, T004, T005, T007, T008, T009, T010, T011, T012, T024, T033, T040, T043, T044, T046, T047, T048, T050, T051, T055, T058, T060, T062, T063, T065, T066, T067 | Report/schema foundations, report writers, GEE/EVI/release report tests/builders, documentation, cloud tests, JSON schema validation, diff checks, and optional live GCP smoke. |
| SC-001 | T001, T007, T011, T012, T017, T018, T021, T022, T023, T029, T030, T033, T041, T043, T060, T065, T067 | Run status, preflight/post-prefix failure evidence, runtime defaults, orchestrator/worker behavior, quickstart, cloud tests, and optional live GCP smoke. |
| SC-002 | T006, T024, T025, T031, T032, T033, T034, T043, T044, T045, T046, T047, T048, T049, T050, T051, T065, T067 | GEE manifest/raster evidence, two EVI wide tables, two EVI long tables, extraction and validation reports, EVI/cloud tests, and optional live GCP smoke. |
| SC-003 | T026, T035, T043, T064, T065 | Scaffold row-universe assembly tests/implementation, targeted tests, regression tests, and cloud gate. |
| SC-004 | T026, T036, T043, T064, T065 | Base input key/month/schema validation wrapper, targeted tests, regression tests, and cloud gate. |
| SC-005 | T019, T020, T027, T037, T038, T043, T064, T065, T067 | Vertex custom-job prediction validation, forbidden output family checks, targeted tests, regression tests, cloud gate, and optional live GCP smoke. |
| SC-006 | T015, T016, T023, T028, T040, T043, T052, T053, T056, T059, T065, T067 | Object-store generation behavior, release writer, conflict tests/handling, US1/US3 tests, cloud gate, and optional live GCP smoke. |
| SC-007 | T011, T012, T013, T014, T015, T016, T028, T040, T043, T052, T054, T055, T057, T058, T059, T060, T062, T063, T065, T066, T067 | Traceability through reports, checksums, release manifest, release reader, docs, quickstart, cloud tests, artifact validation, and optional live GCP smoke. |
| SC-008 | T002, T003, T004, T005, T008, T009, T010, T013, T014, T030, T037, T039, T042, T043, T061, T062, T065, T066, T067 | Cloud-only runtime inputs, immutable image/model refs, manifest/object validation, Docker smoke, docs, cloud tests, diff checks, and optional live GCP smoke. |
| SC-009 | T003, T011, T012, T013, T014, T027, T037, T038, T039, T042, T043, T061, T065, T067 | Model package manifest/checksum, custom-job command/image digest, Vertex manifest/report, prediction checksums, smoke/cloud tests, and optional live GCP smoke. |
| SC-010 | T027, T038, T043, T065, T067 | Local-to-cloud reference comparison or explicit `not_provided` status in wrapper tests/implementation, cloud gates, and optional live GCP smoke. |
| SC-011 | T011, T012, T017, T018, T023, T029, T041, T043, T060, T065, T066, T067 | Failed preflight/post-prefix reporting, run summary status, orchestration tests, quickstart/cloud gates, final artifact validation, and optional live GCP smoke. |

## No-Orphan Task Check

- All T001-T067 tasks have `[Req: ...]` tags containing at least one FR or SC requirement ID.
- All task dependencies reference existing task IDs.
- All tasks appear exactly once in the Execution Wave DAG.
- No required task is detached from final validation: task paths flow into T064, T065, or documentation tasks T062/T063, and T066 depends on those terminal gates. Optional gated live GCP smoke coverage is explicitly isolated in T067 after T066.
- Terminal validation includes cloud contract tests, existing regression tests, docs/output inventory updates, JSON schema validation, diff checks, and optional gated live GCP smoke when credentials/environment variables are supplied.

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup and blocks all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational and is the MVP.
- **User Story 2 (Phase 4)**: Depends on EVI worker/output components from US1; adds audit evidence and advisory comparisons.
- **User Story 3 (Phase 5)**: Depends on release writer components from US1; adds traceable consumer semantics and release conflict handling.
- **Polish (Phase 6)**: Depends on selected user stories.

### User Story Dependencies

- **US1 Run Cloud E2E Monthly Production**: Starts after Foundational; MVP.
- **US2 Audit EVI Export and Rasterio Extraction**: Starts after US1 EVI worker/output base is available; independently validates EVI audit package.
- **US3 Consume Traceable E2E Release**: Starts after US1 release writer base is available; independently validates release consumption and conflict behavior.

### Parallel Opportunities

- Setup fixture and directory tasks T004-T007 can run in parallel after T001 where applicable.
- Foundational tests T009, T011, T013, T015, T017, T019, and T021 are parallel by file once prerequisites are ready.
- US1 test tasks T023-T028 can run in parallel before implementation.
- US2 test tasks T044-T046 can run in parallel after the US1 EVI base exists.
- US3 test tasks T052-T054 can run in parallel after the US1 release writer base exists.
- Documentation tasks T062 and T063 can run in parallel after implementation stabilizes.
- Optional gated live GCP smoke task T067 runs only after local/cloud contract validation and artifact validation pass.

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 setup.
2. Complete Phase 2 foundational contracts and shared helpers.
3. Complete Phase 3 US1 tasks.
4. Stop and validate with T043 before adding richer EVI audit or release consumer enhancements.

### Incremental Delivery

1. US1 produces a complete mocked/fake cloud E2E run and validates the core release.
2. US2 strengthens EVI auditability and reference-comparison evidence.
3. US3 strengthens downstream release consumption and concurrent release safety.
4. Polish verifies regression tests, cloud contract tests, docs, JSON schema, and whitespace.
5. Optional T067 runs a gated live GCP smoke only when cloud credentials and smoke-test environment variables are supplied.

### Test-First Guidance

- For each user story, write the listed test tasks before implementation tasks.
- Confirm new tests fail for missing behavior before implementing the behavior.
- Keep existing local workflow tests passing; do not modify ArcPy reference behavior unless explicitly required by a task.

## Notes

- `[P]` tasks use separate files and can run in parallel once dependencies are satisfied.
- `[US1]`, `[US2]`, and `[US3]` labels map to the user stories in `spec.md`.
- Every release-related task must preserve the out-of-scope boundaries: no FLDAS, GOSIF-GPP, VIIRS, external tabular download automation, model training, prediction maps, prediction sheets, full delivery artifacts, local workstation scoring, or undeclared non-Vertex inference.
