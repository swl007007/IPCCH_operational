# Implementation Micro-Plan: IPCCH Cloud Monthly E2E Feature Input and Inference

Generated from the active Spec Kit artifacts for `001-cloud-base-input`.
This document is an execution guide only. It does not change scope,
architecture, acceptance criteria, task order, or dependencies.

## Artifact Inputs

| Artifact | Path | Status | Notes |
|---|---|---|---|
| `spec.md` | `specs/001-cloud-base-input/spec.md` | present | Source for FR-001 through FR-014, SC-001 through SC-011, cloud-only scope, GCP architecture, EVI-only remote sensing, Vertex AI custom-job v1, release semantics, report schemas, and non-goals. |
| `plan.md` | `specs/001-cloud-base-input/plan.md` | present | Source for Cloud Run Job, Cloud Batch, single repository image, GCS object roots, Vertex AI custom job, pytest/JSON-schema testing, and `cloud/` plus `docker/` structure. |
| `tasks.md` | `specs/001-cloud-base-input/tasks.md` | present | Source of task IDs, requirements, dependencies, execution waves, and terminal validation path. |
| Analyze findings / resolutions | current conversation analyze report | present | I1-I3 and U1 are resolved. Remaining C1 is LOW: plan test tree names are flat, while tasks use `tests/cloud/...`. Treat `tasks.md` paths as authoritative. |
| Evidence pack | `specs/001-cloud-base-input/evidence.md` | present | Evidence says cloud runtime is new, local EVI/base/inference contracts are grounded, Vertex AI custom job must produce cloud evidence, and live GCP behavior is not yet proven. |
| Contracts | `specs/001-cloud-base-input/contracts/` | present | Execution, manifest schema, report schemas, and release artifact contracts. |
| Supplementary docs | `research.md`, `data-model.md`, `quickstart.md`, `docs/03_workflow_runbook.md`, `docs/04_output_inventory.md` | present | Design decisions, data model, expected operator flow, existing local workflow contracts, and output inventory. |
| Existing test config | repo root | warning | No `pytest.ini`, `pyproject.toml`, `tox.ini`, `Makefile`, or CI config found. Use commands explicitly listed in `tasks.md`: `python3 -m pytest ...`, `python3 -m json.tool ...`, and `git diff --check ...`. |

## Source-of-Truth Order

1. Resolved analyze findings / human resolution notes.
2. `specs/001-cloud-base-input/tasks.md`.
3. `specs/001-cloud-base-input/plan.md`.
4. `specs/001-cloud-base-input/spec.md`.
5. `specs/001-cloud-base-input/evidence.md` and repo evidence.
6. Contracts, data model, quickstart, and supplementary docs.
7. This `implementation-micro-plan.md`.

If this micro-plan conflicts with a higher-priority artifact, stop and report
the conflict. Do not silently resolve conflicts by inventing behavior.

## Scope Guardrails

- MUST preserve GCP-only runtime.
- MUST preserve Cloud Run Job orchestrator and Cloud Batch heavy worker.
- MUST preserve single-image v1 unless Speckit artifacts are changed first.
- MUST preserve EVI-only remote sensing.
- MUST preserve Vertex AI `vertex_ai_custom_job` v1, not Batch Prediction.
- MUST NOT add FLDAS, GOSIF-GPP, VIIRS, external tabular download automation,
  model training, prediction maps, prediction sheets, full delivery artifacts,
  local workstation scoring, or undeclared non-Vertex inference.
- Runtime inputs MUST be cloud URIs, Earth Engine identifiers, Artifact
  Registry image references, Vertex AI resources, or container-internal paths.

## Conflict Policy

Use `sdd-superpower-micro-plan/references/conflict-policy.md`:

- Scope, architecture, task dependency, stale artifact, missing required
  artifact, or impossible validation conflicts stop affected tasks.
- Evidence conflicts block affected tasks only; unaffected tasks may continue.
- Missing deployment-time values are warnings for local/fake implementation and
  blockers for live GCP release or T067 execution.

## TDD Policy Summary

`superpowers:test-driven-development` is available and was read. Apply it as
the execution policy:

- Behavior-changing implementation requires strict TDD.
- Test-authoring tasks complete at RED: write the failing test and confirm the
  expected failure; the dependent implementation task later makes it GREEN.
- Refactors require existing coverage or characterization tests first.
- CLI/API behavior requires contract or smoke tests first.
- Data/artifact behavior requires schema, path, row-count, fixture, metadata,
  or deterministic artifact checks first.
- Docs-only tasks may use validation-only checks when there is no runtime
  behavior change.
- Runtime config/build changes are treated as behavior-affecting unless the task
  is only documentation or deterministic metadata; use a static/smoke check
  before editing.

## Blocked Status

- Status: not blocked for local/fake implementation planning.
- Required artifacts present: `spec.md`, `plan.md`, `tasks.md`.
- Blocking conflicts: none.
- Required human input before live GCP release or non-skipped T067:
  deployment project, bucket/object roots, service account names, Artifact
  Registry digest-pinned image URI, Vertex AI model package URI/version, and
  smoke-test environment variables.

## Warnings and Degraded Confidence

- Missing live cloud evidence: GEE service-account authorization, Cloud Batch,
  GCS generation preconditions, and Vertex AI custom-job runtime have not been
  proven. Mitigation: mocked/fake contract tests first; T067 optional gated live
  GCP smoke only when explicit environment variables and credentials are present.
- Missing exact deployment-time values: not a planning blocker; blocks actual
  live run/release.
- Geometry packaging detail is not fixed beyond manifest-declared cloud
  geometry with canonical `area_id`. Mitigation: T006/T024/T025 must make
  fixture expectations and geometry reader behavior explicit before extractor
  implementation.
- Analyze C1: plan test tree lists flat test filenames, tasks use
  `tests/cloud/...`. Mitigation: use `tasks.md` paths as authoritative.
- Existing dirty repository state before this file was written:
  `AGENTS.md` modified; `specs/_evidence/ipcch-cloud-monthly-base-input.evidence.md`
  deleted; `.specify/feature.json`, `specs/001-cloud-base-input.zip`, and
  `specs/001-cloud-base-input/` untracked. Do not attribute these to
  implementation micro-planning.

## Execution Waves

Preserve the wave DAG from `tasks.md`; do not run a task before its listed
dependencies.

| Wave | Safe parallelism | Tasks |
|---|---|---|
| 1 | Yes, independent setup artifacts | T001, T002, T004, T005, T006, T007 |
| 2 | Yes after wave 1 prerequisites | T003, T008, T011, T013, T015, T025 |
| 3 | Yes | T009, T012, T014 |
| 4 | Yes | T010, T016 |
| 5 | Yes | T017, T019, T021, T026, T027, T028, T039 |
| 6 | Yes | T018, T020, T022 |
| 7 | Yes | T023, T024, T037 |
| 8 | Yes only where dependencies allow | T029, T030, T031, T038 |
| 9 | Yes | T032, T046 |
| 10 | Yes | T033, T034, T047 |
| 11 | Yes | T035, T042, T044, T045 |
| 12 | Yes | T036, T048, T049, T061 |
| 13 | Yes | T040, T050 |
| 14 | Yes | T041, T051, T052, T053, T054 |
| 15 | Yes | T043, T055 |
| 16 | Yes | T056, T057, T063, T064 |
| 17 | Yes | T058, T060, T062 |
| 18 | No | T059 |
| 19 | No | T065 |
| 20 | No | T066 |
| 21 | Optional gated live cloud | T067 |

## Global Execution Rules

- For each task, inspect listed files before editing.
- Use `rg`/`rg --files` for discovery.
- Use `apply_patch` for manual edits.
- Do not edit `spec.md`, `plan.md`, or `tasks.md` unless the user explicitly
  asks; task-result notes in `tasks.md` require explicit implementation-time
  decision because this micro-plan is not a source-of-truth artifact.
- Test tasks that create failing tests should not include production code in
  the same task.
- If a RED test passes immediately, classify it as characterization only and
  confirm whether another missing behavior test is needed before implementation.
- If a task cannot be validated with the listed command, do not mark it done.

## Task Micro-Plans

### Wave 1: Setup

#### T001 - Create cloud package directories
- Source: `[Req: FR-001, FR-002, FR-014, SC-001]`; depends on none.
- Inspect: `plan.md` project structure; existing root with `rg --files cloud tests/cloud`.
- Edit: `cloud/`, `cloud/common/`, `cloud/orchestrator/`, `cloud/batch/`, `cloud/schemas/`, `tests/cloud/`.
- TDD classification: artifact/path check.
- RED: run `test -d cloud/common -a -d cloud/orchestrator -a -d cloud/batch -a -d cloud/schemas -a -d tests/cloud`; expect missing-directory failure.
- GREEN: create directories and minimal `__init__.py` files where package imports require them.
- Refactor/check: keep empty initializers minimal.
- Validation: rerun the RED command.
- Done: directories exist, no unrelated files changed.
- Commit suggestion: `chore: scaffold cloud runtime packages`.

#### T002 - Add cloud runtime dependency manifest
- Source: `[Req: FR-002, FR-003, FR-004, FR-005, FR-008, SC-008]`; depends on none.
- Inspect: `plan.md` Technical Context, `research.md`, imports in existing `model_pipeline/`, `Final_harmonise/`, `tools/`.
- Edit: `requirements-cloud.txt`.
- TDD classification: deterministic dependency manifest check.
- RED: run `test -f requirements-cloud.txt && rg 'google-cloud-storage|google-cloud-batch|google-cloud-aiplatform|earthengine-api|rasterio|jsonschema|pandas|numpy' requirements-cloud.txt`; expect missing file or missing dependency names.
- GREEN: add cloud dependency manifest with GCP clients, Earth Engine SDK, rasterio/GDAL-compatible stack, pandas, numpy, jsonschema, pytest helpers.
- Refactor/check: keep pins or ranges consistent with repo conventions if discovered.
- Validation: rerun RED command.
- Done: manifest contains required dependency families; no Dockerfile yet unless T003.
- Commit suggestion: `chore: add cloud runtime dependencies`.

#### T004 - Add valid input manifest fixture
- Source: `[Req: FR-001, FR-014, SC-008]`; depends on none.
- Inspect: `contracts/input-manifest.schema.json`, `data-model.md` InputManifest/Deployment/ArtifactEntry.
- Edit: `tests/fixtures/cloud/input_manifest_202604_valid.json`.
- TDD classification: data fixture validation.
- RED: run `python3 -m json.tool tests/fixtures/cloud/input_manifest_202604_valid.json`; expect file missing.
- GREEN: add a valid JSON fixture for feature month `2026-04` with required deployment fields and artifact entries using fake immutable GCS generations/digests.
- Refactor/check: avoid real project secrets or local workstation paths.
- Validation: `python3 -m json.tool tests/fixtures/cloud/input_manifest_202604_valid.json`.
- Done: valid JSON fixture exists and uses cloud URIs/digest-pinned image references.
- Commit suggestion: `test: add valid cloud manifest fixture`.

#### T005 - Add invalid manifest fixtures
- Source: `[Req: FR-001, FR-003, FR-013, FR-014, SC-008]`; depends on none.
- Inspect: `contracts/input-manifest.schema.json`, spec hard gates for local paths and tag-only images.
- Edit: `tests/fixtures/cloud/input_manifest_missing_digest.json`, `tests/fixtures/cloud/input_manifest_local_path.json`.
- TDD classification: data fixture validation.
- RED: run `test -f tests/fixtures/cloud/input_manifest_missing_digest.json -a -f tests/fixtures/cloud/input_manifest_local_path.json`; expect missing files.
- GREEN: add malformed fixtures with one missing immutable reference and one local workstation path.
- Refactor/check: keep JSON syntactically valid so validator failures are semantic.
- Validation: `python3 -m json.tool tests/fixtures/cloud/input_manifest_missing_digest.json && python3 -m json.tool tests/fixtures/cloud/input_manifest_local_path.json`.
- Done: fixtures parse as JSON and target intended hard gates.
- Commit suggestion: `test: add invalid cloud manifest fixtures`.

#### T006 - Add EVI raster/geometry fixture plan stub
- Source: `[Req: FR-005, SC-002]`; depends on none.
- Inspect: `docs/03_workflow_runbook.md` EVI section, `docs/04_output_inventory.md` remote-sensing normalization note, `spec.md` EVI Processing Contract.
- Edit: `tests/fixtures/cloud/README.md`.
- TDD classification: documentation-only validation exception.
- TDD exception: no runtime behavior; validation is content review plus `rg`.
- RED: run `test -f tests/fixtures/cloud/README.md && rg 'raster|geometry|area_id|all_touched=false|EVI' tests/fixtures/cloud/README.md`; expect missing file or terms.
- GREEN: document generated fixture requirements, not real large fixture data.
- Refactor/check: keep it a stub; do not add large binary data.
- Validation: rerun RED command.
- Done: fixture expectations are explicit for T025.
- Commit suggestion: `test: document cloud EVI fixture expectations`.

#### T007 - Add cloud test package initializer
- Source: `[Req: FR-014, SC-001]`; depends on none.
- Inspect: existing `tests/` layout.
- Edit: `tests/cloud/__init__.py`.
- TDD classification: artifact/path check.
- RED: run `test -f tests/cloud/__init__.py && python3 -m py_compile tests/cloud/__init__.py`; expect missing file.
- GREEN: add minimal initializer.
- Refactor/check: keep empty unless package setup requires otherwise.
- Validation: rerun RED command.
- Done: `tests/cloud` is import/compile safe.
- Commit suggestion: `test: initialize cloud test package`.

### Wave 2-6: Foundations

#### T003 - Add single-image runtime Dockerfile
- Source: `[Req: FR-003, FR-008, SC-008, SC-009]`; depends on T002.
- Inspect: `plan.md` Docker structure, `quickstart.md` runtime image entrypoints, `requirements-cloud.txt`.
- Edit: `docker/Dockerfile`.
- TDD classification: build-config artifact check.
- RED: run `test -f docker/Dockerfile && rg 'requirements-cloud.txt|cloud.batch.evi_worker|cloud.orchestrator.main|run_operational_launch_inference' docker/Dockerfile`; expect missing file or missing entrypoint references.
- GREEN: add a minimal single-image Dockerfile that installs repo code and `requirements-cloud.txt` and documents entrypoint modules.
- Refactor/check: do not split into a second image.
- Validation: rerun RED command; full image smoke is deferred to T061.
- Done: Dockerfile references required dependencies and entrypoints.
- Commit suggestion: `chore: add single-image cloud Dockerfile`.

#### T008 - Add input manifest schema package copy
- Source: `[Req: FR-014, SC-008]`; depends on T001.
- Inspect: `specs/001-cloud-base-input/contracts/input-manifest.schema.json`.
- Edit: `cloud/schemas/input-manifest.schema.json`.
- TDD classification: deterministic generated/copy artifact check.
- RED: run `python3 -m json.tool cloud/schemas/input-manifest.schema.json`; expect missing file.
- GREEN: copy the contract schema exactly or with an explicit note if packaging requires no path changes.
- Refactor/check: avoid changing schema behavior.
- Validation: `cmp specs/001-cloud-base-input/contracts/input-manifest.schema.json cloud/schemas/input-manifest.schema.json && python3 -m json.tool cloud/schemas/input-manifest.schema.json`.
- Done: packaged schema matches source contract.
- Commit suggestion: `chore: package input manifest schema`.

#### T009 - Add manifest contract tests
- Source: `[Req: FR-001, FR-003, FR-013, FR-014, SC-008]`; depends on T004, T005, T007, T008.
- Inspect: input manifest schema, fixtures, `spec.md` Deployment/Input Manifest sections.
- Edit/test: `tests/cloud/test_manifest_contract.py`.
- TDD classification: strict contract RED task.
- RED: write tests for valid fixture, missing immutable reference, local workstation URI, non-GCP provider, tag-only image, and shared service account; run `python3 -m pytest tests/cloud/test_manifest_contract.py`; expect failures because `cloud.common.manifest` validator is absent.
- GREEN: deferred to T010; do not add production validator here.
- Refactor/check: keep tests behavior-focused, not implementation-internal.
- Validation: RED command fails for missing validator or hard-gate behavior.
- Done: expected RED failure observed and recorded.
- Commit suggestion: `test: add cloud manifest contract tests`.

#### T010 - Implement manifest loader and validator
- Source: `[Req: FR-001, FR-003, FR-013, FR-014, SC-008]`; depends on T008, T009.
- Inspect: `tests/cloud/test_manifest_contract.py`, packaged schema, fixtures.
- Edit: `cloud/common/manifest.py`.
- TDD classification: strict TDD GREEN for T009.
- RED: rerun `python3 -m pytest tests/cloud/test_manifest_contract.py`; confirm failures are validator/behavior failures.
- GREEN: implement loader and cross-field validator for feature month/run id equality, required immutable refs, cloud URI rules, digest pinning, provider, and split service accounts.
- Refactor/check: keep cross-field checks separate from JSON schema loading where useful.
- Validation: `python3 -m pytest tests/cloud/test_manifest_contract.py`.
- Done: manifest tests pass without weakening fixtures.
- Commit suggestion: `feat: validate cloud input manifests`.

#### T011 - Add report schema tests
- Source: `[Req: FR-014, SC-001, SC-007, SC-009, SC-011]`; depends on T001.
- Inspect: `contracts/report-contracts.md`, `spec.md` Report Schemas.
- Edit/test: `tests/cloud/test_report_contracts.py`.
- TDD classification: strict contract RED task.
- RED: write tests for required top-level fields and allowed statuses in all report classes; run `python3 -m pytest tests/cloud/test_report_contracts.py`; expect missing `cloud.common.reports`.
- GREEN: deferred to T012.
- Refactor/check: assert fields from contract, not incidental Python object internals.
- Validation: RED command fails for expected missing report builders/status enums.
- Done: expected RED failure observed.
- Commit suggestion: `test: add report contract tests`.

#### T012 - Implement report builders and status enums
- Source: `[Req: FR-014, SC-001, SC-007, SC-009, SC-011]`; depends on T011.
- Inspect: `tests/cloud/test_report_contracts.py`, `contracts/report-contracts.md`.
- Edit: `cloud/common/reports.py`.
- TDD classification: strict TDD GREEN for T011.
- RED: `python3 -m pytest tests/cloud/test_report_contracts.py`; confirm expected failures.
- GREEN: implement report builder helpers and enums for run, GEE, EVI, base input, Vertex AI, inference, release step, and release manifest reports.
- Refactor/check: avoid broad framework; keep serializable dicts and schema constants simple.
- Validation: `python3 -m pytest tests/cloud/test_report_contracts.py`.
- Done: report tests pass.
- Commit suggestion: `feat: add cloud report builders`.

#### T013 - Add checksum and object reference tests
- Source: `[Req: FR-003, FR-008, FR-011, FR-012, SC-007, SC-008, SC-009]`; depends on T001.
- Inspect: `spec.md` immutable reference rules, `data-model.md` ArtifactEntry, `research.md` GCS generation/checksum decision.
- Edit/test: `tests/cloud/test_object_refs.py`.
- TDD classification: strict contract RED task.
- RED: test sha256, GCS generation/version metadata, image digest/model version checks, and missing immutable references; run `python3 -m pytest tests/cloud/test_object_refs.py`; expect missing helper.
- GREEN: deferred to T014.
- Refactor/check: use small temp files only.
- Validation: RED command fails for expected missing helper/behavior.
- Done: expected RED failure observed.
- Commit suggestion: `test: add immutable object reference tests`.

#### T014 - Implement checksum and immutable object reference helpers
- Source: `[Req: FR-003, FR-008, FR-011, FR-012, SC-007, SC-008, SC-009]`; depends on T013.
- Inspect: object ref tests, manifest validator needs.
- Edit: `cloud/common/object_refs.py`.
- TDD classification: strict TDD GREEN for T013.
- RED: `python3 -m pytest tests/cloud/test_object_refs.py`.
- GREEN: implement sha256, immutable GCS metadata normalization, digest/model reference validators.
- Refactor/check: keep helpers pure and storage-client independent.
- Validation: `python3 -m pytest tests/cloud/test_object_refs.py`.
- Done: object reference tests pass.
- Commit suggestion: `feat: add immutable object reference helpers`.

#### T015 - Add fake object-store tests
- Source: `[Req: FR-011, FR-012, SC-006, SC-007]`; depends on T001.
- Inspect: release artifact contract and research GCS generation decision.
- Edit/test: `tests/cloud/test_object_store.py`.
- TDD classification: strict contract RED task.
- RED: write read/write/copy/list/generation-precondition tests; run `python3 -m pytest tests/cloud/test_object_store.py`; expect missing object store abstraction.
- GREEN: deferred to T016.
- Refactor/check: fake backend must model generation conflict deterministically.
- Validation: RED command fails for expected missing abstraction.
- Done: expected RED failure observed.
- Commit suggestion: `test: add object-store contract tests`.

#### T016 - Implement object-store abstraction
- Source: `[Req: FR-011, FR-012, SC-006, SC-007]`; depends on T014, T015.
- Inspect: object-store tests, object ref helpers.
- Edit: `cloud/common/object_store.py`.
- TDD classification: strict TDD GREEN for T015.
- RED: `python3 -m pytest tests/cloud/test_object_store.py`.
- GREEN: implement local fake backend plus GCS backend interface boundaries for read/write/copy/list/generation preconditions.
- Refactor/check: do not require live GCS for unit tests.
- Validation: `python3 -m pytest tests/cloud/test_object_store.py`.
- Done: fake object-store tests pass.
- Commit suggestion: `feat: add object-store abstraction`.

#### T017 - Add run state tests
- Source: `[Req: FR-001, FR-011, FR-012, SC-001, SC-011]`; depends on T012, T016.
- Inspect: `data-model.md` Run, `execution-contract.md` duplicate run/pre-prefix rules.
- Edit/test: `tests/cloud/test_run_state.py`.
- TDD classification: strict contract RED task.
- RED: test sentinel acquisition, duplicate `run_id`, pre-prefix failure, terminal summary, immutable run prefix; run `python3 -m pytest tests/cloud/test_run_state.py`; expect missing run state manager.
- GREEN: deferred to T018.
- Refactor/check: use fake object store.
- Validation: RED command fails for expected missing manager.
- Done: expected RED failure observed.
- Commit suggestion: `test: add run state contract tests`.

#### T018 - Implement run state manager
- Source: `[Req: FR-001, FR-011, FR-012, SC-001, SC-011]`; depends on T012, T016, T017.
- Inspect: run state tests and report builders.
- Edit: `cloud/orchestrator/run_state.py`.
- TDD classification: strict TDD GREEN for T017.
- RED: `python3 -m pytest tests/cloud/test_run_state.py`.
- GREEN: implement sentinel creation, initial/terminal `run_summary.json`, duplicate preflight handling.
- Refactor/check: keep terminal status enum aligned with report contracts.
- Validation: `python3 -m pytest tests/cloud/test_run_state.py`.
- Done: run state tests pass.
- Commit suggestion: `feat: manage immutable run state`.

#### T019 - Add forbidden side-effect tests
- Source: `[Req: FR-007, FR-013, SC-005]`; depends on T016.
- Inspect: release artifact contract forbidden families, spec Forbidden Side Effects.
- Edit/test: `tests/cloud/test_forbidden_side_effects.py`.
- TDD classification: strict contract RED task.
- RED: test allowed prefixes, forbidden output families, observed invocation metadata, ignored container temp files; run `python3 -m pytest tests/cloud/test_forbidden_side_effects.py`; expect missing scanner.
- GREEN: deferred to T020.
- Refactor/check: use fake object store inventories.
- Validation: RED command fails for expected missing scanner.
- Done: expected RED failure observed.
- Commit suggestion: `test: add forbidden side-effect tests`.

#### T020 - Implement forbidden side-effect scanner
- Source: `[Req: FR-007, FR-013, SC-005]`; depends on T016, T019.
- Inspect: forbidden side-effect tests.
- Edit: `cloud/common/forbidden_side_effects.py`.
- TDD classification: strict TDD GREEN for T019.
- RED: `python3 -m pytest tests/cloud/test_forbidden_side_effects.py`.
- GREEN: implement checked prefixes, allowed prefixes, filename/family patterns, observed invocation metadata, and report object.
- Refactor/check: keep allowed Vertex AI prediction CSVs distinct from forbidden maps/sheets/full delivery.
- Validation: `python3 -m pytest tests/cloud/test_forbidden_side_effects.py`.
- Done: scanner tests pass.
- Commit suggestion: `feat: scan forbidden cloud side effects`.

#### T021 - Add runtime defaults tests
- Source: `[Req: FR-002, FR-004, FR-008, SC-001]`; depends on T010.
- Inspect: clarifications in `spec.md`, `data-model.md` Deployment defaults.
- Edit/test: `tests/cloud/test_runtime_defaults.py`.
- TDD classification: strict contract RED task.
- RED: test GEE poll 60s, GEE export 21600s, Batch 28800s, Vertex AI 7200s, max retries 2; run `python3 -m pytest tests/cloud/test_runtime_defaults.py`; expect missing resolver.
- GREEN: deferred to T022.
- Refactor/check: test explicit overrides and defaults separately.
- Validation: RED command fails for expected missing resolver.
- Done: expected RED failure observed.
- Commit suggestion: `test: add cloud runtime default tests`.

#### T022 - Implement runtime defaults and retry policy resolver
- Source: `[Req: FR-002, FR-004, FR-008, SC-001]`; depends on T010, T021.
- Inspect: runtime defaults tests and manifest deployment fields.
- Edit: `cloud/common/runtime_config.py`.
- TDD classification: strict TDD GREEN for T021.
- RED: `python3 -m pytest tests/cloud/test_runtime_defaults.py`.
- GREEN: implement default/override resolver for GEE, Batch, Vertex AI, and retry policy.
- Refactor/check: avoid coupling to cloud clients.
- Validation: `python3 -m pytest tests/cloud/test_runtime_defaults.py`.
- Done: runtime default tests pass.
- Commit suggestion: `feat: resolve cloud runtime defaults`.

### Wave 7-15: User Story 1 MVP

#### T023 - Add orchestrator contract test
- Source: `[Req: FR-001, FR-002, FR-011, FR-012, SC-001, SC-006, SC-011]`; depends on T018, T020, T022.
- Inspect: execution contract, run state manager, fake object store.
- Edit/test: `tests/cloud/test_orchestrator_contract.py`.
- TDD classification: strict contract RED task.
- RED: test successful fake E2E orchestration and duplicate run preflight; run `python3 -m pytest tests/cloud/test_orchestrator_contract.py`; expect missing orchestrator CLI/clients.
- GREEN: deferred to T029-T041.
- Refactor/check: keep cloud services mocked/faked; no live GCP.
- Validation: expected RED failure observed.
- Done: RED contract in place.
- Commit suggestion: `test: add cloud orchestrator contract tests`.

#### T024 - Add Cloud Batch worker contract test
- Source: `[Req: FR-002, FR-004, FR-005, FR-014, SC-002]`; depends on T012, T016, T022.
- Inspect: execution contract Cloud Batch Worker Entrypoint, report contracts.
- Edit/test: `tests/cloud/test_cloud_batch_evi_worker.py`.
- TDD classification: strict contract RED task.
- RED: test GEE manifest, processed raster reference, EVI wide/long outputs, extraction manifest paths; run `python3 -m pytest tests/cloud/test_cloud_batch_evi_worker.py`; expect missing worker/export/extraction code.
- GREEN: deferred to T030-T034/T050.
- Refactor/check: fake Earth Engine and object store.
- Validation: expected RED failure observed.
- Done: RED worker contract in place.
- Commit suggestion: `test: add Cloud Batch EVI worker contract tests`.

#### T025 - Add rasterio zonal statistics test
- Source: `[Req: FR-005, SC-002]`; depends on T006.
- Inspect: fixture README, `spec.md` EVI Processing Contract.
- Edit/test: `tests/cloud/test_rasterio_evi_extraction.py` and small generated fixtures if needed.
- TDD classification: strict data/artifact RED task.
- RED: test `all_touched=false`, empty zone preservation, `region_id == area_id`, selected-month long row count; run `python3 -m pytest tests/cloud/test_rasterio_evi_extraction.py`; expect missing extractor or fixture generator.
- GREEN: deferred to T032.
- Refactor/check: use tiny deterministic raster/geometry fixtures only.
- Validation: expected RED failure observed.
- Done: RED rasterio semantics tests exist.
- Commit suggestion: `test: add rasterio EVI extraction tests`.

#### T026 - Add monthly assembly wrapper test
- Source: `[Req: FR-006, FR-007, SC-003, SC-004]`; depends on T010, T016.
- Inspect: existing assembly script, schema validator, data model MonthlyModelFeatureInput.
- Edit/test: `tests/cloud/test_monthly_assembly_wrapper.py`.
- TDD classification: strict contract RED task.
- RED: test cloud-localized scaffold/source/fixed/EVI inputs and model-input-forecast validation report output; run `python3 -m pytest tests/cloud/test_monthly_assembly_wrapper.py`; expect missing wrapper.
- GREEN: deferred to T035-T036.
- Refactor/check: use tiny CSV fixtures, not large local assets.
- Validation: expected RED failure observed.
- Done: RED assembly wrapper tests exist.
- Commit suggestion: `test: add monthly assembly wrapper tests`.

#### T027 - Add Vertex AI custom job wrapper test
- Source: `[Req: FR-008, FR-009, FR-010, SC-005, SC-009, SC-010]`; depends on T012, T016.
- Inspect: execution contract Vertex AI Custom Job Entrypoint, model pipeline CLI, prediction schema in spec.
- Edit/test: `tests/cloud/test_vertex_ai_custom_job_contract.py`.
- TDD classification: strict contract RED task.
- RED: test command args, `--no-map`, no `--validate-only`, year/month enrichment, three prediction CSVs, local reference absent/provided/advisory/not_provided; run `python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py`; expect missing Vertex AI wrapper/submitter/model package helpers.
- GREEN: deferred to T037-T039.
- Refactor/check: mock Vertex AI; run local inference only against tiny fixtures or stubbed command runner.
- Validation: expected RED failure observed.
- Done: RED custom job contract tests exist.
- Commit suggestion: `test: add Vertex AI custom-job contract tests`.

#### T028 - Add release writer test
- Source: `[Req: FR-011, FR-012, SC-006, SC-007]`; depends on T012, T016.
- Inspect: release artifact contract, report contracts.
- Edit/test: `tests/cloud/test_release_writer.py`.
- TDD classification: strict contract RED task.
- RED: test copied v1 artifacts, referenced large evidence, checksum verification, manifest write-last; run `python3 -m pytest tests/cloud/test_release_writer.py`; expect missing release writer.
- GREEN: deferred to T040.
- Refactor/check: fake object store generation preconditions.
- Validation: expected RED failure observed.
- Done: RED release writer tests exist.
- Commit suggestion: `test: add release writer contract tests`.

#### T029 - Implement Cloud Run orchestrator CLI
- Source: `[Req: FR-001, FR-002, SC-001, SC-011]`; depends on T010, T018, T022, T023.
- Inspect: `tests/cloud/test_orchestrator_contract.py`, `contracts/execution-contract.md`.
- Edit: `cloud/orchestrator/main.py`.
- TDD classification: strict TDD GREEN for T023 CLI/preflight subset.
- RED: run `python3 -m pytest tests/cloud/test_orchestrator_contract.py -k 'cli or preflight or duplicate'`; confirm expected missing CLI failures.
- GREEN: implement `--feature-month`, `--run-id`, `--input-manifest-uri`, optional reference/release mode parsing, manifest validation, and run-state acquisition hooks.
- Refactor/check: keep cloud clients injectable.
- Validation: same focused pytest command.
- Done: focused orchestrator CLI/preflight tests pass.
- Commit suggestion: `feat: add Cloud Run orchestrator CLI`.

#### T030 - Implement Cloud Batch submitter interface
- Source: `[Req: FR-002, FR-003, SC-001, SC-008]`; depends on T022, T024.
- Inspect: `tests/cloud/test_cloud_batch_evi_worker.py`, runtime defaults.
- Edit: `cloud/orchestrator/batch_client.py`.
- TDD classification: strict TDD.
- RED: run `python3 -m pytest tests/cloud/test_cloud_batch_evi_worker.py -k 'submitter or job_name or image_digest or service_account or retry'`; confirm missing submitter behavior.
- GREEN: implement injectable Batch submitter interface for job prefix, digest image, service account, timeout, retry policy, worker args.
- Refactor/check: do not call live Batch in unit tests.
- Validation: focused pytest command.
- Done: submitter contract tests pass.
- Commit suggestion: `feat: add Cloud Batch submitter interface`.

#### T031 - Implement Earth Engine EVI export helper
- Source: `[Req: FR-004, SC-002]`; depends on T024.
- Inspect: `EVI/00_ee_export_evi.txt`, `spec.md` EVI Processing Parameters v1, worker tests.
- Edit: `cloud/batch/gee_export.py`.
- TDD classification: strict TDD.
- RED: run `python3 -m pytest tests/cloud/test_cloud_batch_evi_worker.py -k 'gee or export or raster'`; confirm missing helper/manifest behavior.
- GREEN: implement MODIS/061/MOD13A3 EVI selected-month export helper with manifest metadata and immutable raster reference handling; keep Earth Engine client injectable.
- Refactor/check: separate task construction from polling.
- Validation: focused pytest command.
- Done: GEE export helper tests pass with fake EE/GCS.
- Commit suggestion: `feat: add Earth Engine EVI export helper`.

#### T032 - Implement rasterio EVI extraction
- Source: `[Req: FR-005, SC-002]`; depends on T025, T031.
- Inspect: rasterio tests, fixture README, ArcPy reference script for output names only.
- Edit: `cloud/batch/evi_extract.py`.
- TDD classification: strict TDD GREEN for T025.
- RED: `python3 -m pytest tests/cloud/test_rasterio_evi_extraction.py`.
- GREEN: implement geometry reprojection, center-inside pixel inclusion, mean/std, empty zone rows, `region_id == area_id` enforcement.
- Refactor/check: keep raster IO isolated from output CSV formatting where useful.
- Validation: `python3 -m pytest tests/cloud/test_rasterio_evi_extraction.py`.
- Done: rasterio tests pass.
- Commit suggestion: `feat: extract EVI zonal stats with rasterio`.

#### T033 - Implement Cloud Batch worker CLI
- Source: `[Req: FR-002, FR-004, FR-005, FR-014, SC-001, SC-002]`; depends on T012, T016, T022, T031, T032.
- Inspect: worker contract tests, execution contract.
- Edit: `cloud/batch/evi_worker.py`.
- TDD classification: strict TDD GREEN for T024 worker path.
- RED: `python3 -m pytest tests/cloud/test_cloud_batch_evi_worker.py`.
- GREEN: implement worker CLI, GEE export polling defaults, rasterio extraction orchestration, required reports, nonzero hard gate exits.
- Refactor/check: inject fake EE/object store in tests.
- Validation: `python3 -m pytest tests/cloud/test_cloud_batch_evi_worker.py`.
- Done: worker contract tests pass.
- Commit suggestion: `feat: add Cloud Batch EVI worker`.

#### T034 - Implement EVI wide-to-long writer
- Source: `[Req: FR-005, SC-002]`; depends on T032.
- Inspect: `tools/reshape_remote_sensing_wide_to_long.py`, worker/rasterio tests.
- Edit: `cloud/batch/evi_outputs.py`.
- TDD classification: strict TDD.
- RED: run `python3 -m pytest tests/cloud/test_cloud_batch_evi_worker.py tests/cloud/test_rasterio_evi_extraction.py -k 'long or EVI_mean_monthly_long or EVI_std_monthly_long'`; confirm missing long writer.
- GREEN: implement selected-month long outputs for mean/std with exact filenames and row count.
- Refactor/check: reuse existing reshape logic if it preserves contract.
- Validation: focused pytest command.
- Done: long output tests pass.
- Commit suggestion: `feat: write selected-month EVI long outputs`.

#### T035 - Implement monthly assembly wrapper
- Source: `[Req: FR-006, SC-003]`; depends on T026, T034.
- Inspect: existing assembly script, assembly wrapper tests, source panel/EVI merge rules.
- Edit: `cloud/orchestrator/assembly.py`.
- TDD classification: strict TDD GREEN for T026 assembly subset.
- RED: `python3 -m pytest tests/cloud/test_monthly_assembly_wrapper.py -k 'assembly or evi or row_universe'`.
- GREEN: localize cloud inputs, call/reuse existing assembly script, merge cloud EVI long outputs, write assembly artifacts.
- Refactor/check: preserve existing local script behavior; wrapper handles cloud staging.
- Validation: focused pytest command.
- Done: assembly wrapper tests pass for row universe and EVI feature injection.
- Commit suggestion: `feat: assemble monthly base input from cloud inputs`.

#### T036 - Implement base input validation wrapper
- Source: `[Req: FR-007, SC-004]`; depends on T012, T035.
- Inspect: `tools/validate_ipcch_schema.py`, assembly tests.
- Edit: `cloud/orchestrator/base_input_validation.py`.
- TDD classification: strict TDD GREEN for T026 validation subset.
- RED: `python3 -m pytest tests/cloud/test_monthly_assembly_wrapper.py -k 'validation or model_input_forecast or duplicate'`.
- GREEN: wrap `model-input-forecast` semantics, row-universe checks, report output.
- Refactor/check: avoid duplicating validator logic unless wrapper translation is required.
- Validation: focused pytest command.
- Done: base input validation report tests pass.
- Commit suggestion: `feat: validate cloud monthly base input`.

#### T037 - Implement Vertex AI custom job submitter
- Source: `[Req: FR-003, FR-008, SC-005, SC-008, SC-009]`; depends on T022, T027.
- Inspect: Vertex contract tests and runtime defaults.
- Edit: `cloud/orchestrator/vertex_client.py`.
- TDD classification: strict TDD.
- RED: `python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py -k 'submitter or custom_job or digest or service_account or timeout'`.
- GREEN: implement injectable Vertex AI custom-job submitter with same image digest, service account, timeout, retry, staging/output roots, metadata capture.
- Refactor/check: no registered model or Batch Prediction path in v1.
- Validation: focused pytest command.
- Done: Vertex submitter tests pass.
- Commit suggestion: `feat: add Vertex AI custom-job submitter`.

#### T038 - Implement Vertex AI inference wrapper
- Source: `[Req: FR-008, FR-009, FR-010, FR-013, SC-005, SC-009, SC-010]`; depends on T027, T037.
- Inspect: `model_pipeline/run_operational_launch_inference.py`, prediction schema, Vertex contract tests.
- Edit: `cloud/orchestrator/inference.py`.
- TDD classification: strict TDD GREEN for T027.
- RED: `python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py -k 'wrapper or prediction or local_reference or no_map or validate_only'`.
- GREEN: localize base/model package, call inference with `--no-map --overwrite`, forbid `--validate-only`, enrich `year`/`month`, validate three prediction CSVs, write `local_reference_comparison`.
- Refactor/check: keep command construction explicit and reportable.
- Validation: focused pytest command.
- Done: inference wrapper tests pass.
- Commit suggestion: `feat: wrap operational inference for Vertex AI custom jobs`.

#### T039 - Implement model package validation
- Source: `[Req: FR-008, SC-008, SC-009]`; depends on T010, T014.
- Inspect: model package contract in spec, object ref helpers, Vertex tests.
- Edit: `cloud/orchestrator/model_package.py`; test additions in `tests/cloud/test_vertex_ai_custom_job_contract.py` if not already covered.
- TDD classification: strict TDD.
- RED: add/confirm tests for package manifest presence, immutable checksum/version, expected schema match, local validation evidence recording; run `python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py -k 'model_package'`; expect missing validator.
- GREEN: implement model package validation helper.
- Refactor/check: do not require registered Vertex AI Model resource.
- Validation: focused pytest command.
- Done: model package validation tests pass.
- Commit suggestion: `feat: validate immutable model package`.

#### T040 - Implement release writer
- Source: `[Req: FR-011, FR-012, FR-014, SC-006, SC-007]`; depends on T028, T036, T038, T039.
- Inspect: release writer tests, release artifact contract, report contracts.
- Edit: `cloud/orchestrator/release.py`.
- TDD classification: strict TDD GREEN for T028.
- RED: `python3 -m pytest tests/cloud/test_release_writer.py`.
- GREEN: stage copied artifacts, reference large evidence, verify checksums/generations, write `release_step_report.json`, update manifest last.
- Refactor/check: keep generation precondition behavior testable with fake store.
- Validation: `python3 -m pytest tests/cloud/test_release_writer.py`.
- Done: release writer tests pass.
- Commit suggestion: `feat: write immutable cloud release artifacts`.

#### T041 - Wire orchestrator execution sequence
- Source: `[Req: FR-001, FR-002, FR-007, FR-011, FR-013, SC-001, SC-011]`; depends on T029, T030, T033, T036, T038, T040, T020.
- Inspect: orchestrator contract tests and all orchestrator/batch wrappers.
- Edit: `cloud/orchestrator/main.py`.
- TDD classification: strict TDD GREEN for full T023.
- RED: `python3 -m pytest tests/cloud/test_orchestrator_contract.py`; confirm missing sequence behavior.
- GREEN: wire manifest validation, Batch, assembly, base validation, Vertex AI, forbidden side-effect scan, release, terminal run summary.
- Refactor/check: keep orchestration dependency-injected for fake services.
- Validation: `python3 -m pytest tests/cloud/test_orchestrator_contract.py`.
- Done: full orchestrator contract tests pass.
- Commit suggestion: `feat: orchestrate monthly cloud e2e run`.

#### T042 - Add Docker image entrypoint commands
- Source: `[Req: FR-003, FR-008, SC-008, SC-009]`; depends on T003, T029, T033, T038.
- Inspect: Dockerfile and implemented entrypoints.
- Edit: `docker/Dockerfile`.
- TDD classification: build-config artifact check.
- RED: run `rg 'cloud.orchestrator.main|cloud.batch.evi_worker|cloud.orchestrator.inference|container_image_digest' docker/Dockerfile`; expect missing labels/comments/entrypoint metadata.
- GREEN: add entrypoint labels/comments or command metadata for orchestrator, Batch worker, and Vertex AI wrapper.
- Refactor/check: do not add a second image.
- Validation: RED command plus `python3 -m pytest tests/cloud/test_runtime_image_contract.py -k 'entrypoint'` once T061 exists; before T061, use static `rg`.
- Done: entrypoints are discoverable in Dockerfile metadata.
- Commit suggestion: `chore: document cloud image entrypoints`.

#### T043 - Run US1 targeted tests
- Source: all US1 FR/SC listed in task; depends on T041, T042.
- Inspect: all US1 test files.
- Edit: no product code; optionally implementation-time task notes only if user accepts.
- TDD classification: validation-only.
- RED: not applicable; this is a terminal validation task.
- GREEN: run `python3 -m pytest tests/cloud/test_orchestrator_contract.py tests/cloud/test_cloud_batch_evi_worker.py tests/cloud/test_rasterio_evi_extraction.py tests/cloud/test_monthly_assembly_wrapper.py tests/cloud/test_vertex_ai_custom_job_contract.py tests/cloud/test_release_writer.py`.
- Refactor/check: fix failures through the owning implementation task using TDD.
- Validation: same command must pass.
- Done: command passes; results recorded per project convention.
- Commit suggestion: `test: validate US1 cloud e2e contracts`.

### Wave 9-14: User Story 2 EVI Audit

#### T044 - Add EVI validation report contract test
- Source: `[Req: FR-005, FR-014, SC-002]`; depends on T033, T034.
- Inspect: report contracts, EVI output contract.
- Edit/test: `tests/cloud/test_evi_validation_report.py`.
- TDD classification: strict contract RED task.
- RED: write tests for output contract status, wide/long outputs, area identity, reference comparison, advisory warning statuses; run `python3 -m pytest tests/cloud/test_evi_validation_report.py`; expect missing validation report builder.
- GREEN: deferred to T048.
- Validation: expected RED failure observed.
- Done: RED EVI report tests exist.
- Commit suggestion: `test: add EVI validation report tests`.

#### T045 - Add EVI reference comparison test
- Source: `[Req: FR-005, SC-002]`; depends on T033, T034.
- Inspect: spec EVI advisory comparison rules.
- Edit/test: `tests/cloud/test_evi_reference_comparison.py`.
- TDD classification: strict contract RED task.
- RED: test absent sample, malformed optional sample, zero matches, insufficient correlation pairs, advisory numeric differences; run `python3 -m pytest tests/cloud/test_evi_reference_comparison.py`; expect missing comparison helper.
- GREEN: deferred to T049.
- Validation: expected RED failure observed.
- Done: RED EVI reference tests exist.
- Commit suggestion: `test: add EVI reference comparison tests`.

#### T046 - Add GEE export manifest audit test
- Source: `[Req: FR-004, FR-014, SC-002]`; depends on T031.
- Inspect: report contracts and GEE export contract.
- Edit/test: `tests/cloud/test_gee_export_manifest.py`.
- TDD classification: strict contract RED task.
- RED: test task id, export status, date window, processing params, raster generation/checksum, selected-month mismatch failure; run `python3 -m pytest tests/cloud/test_gee_export_manifest.py`; expect missing manifest builder detail.
- GREEN: deferred to T047.
- Validation: expected RED failure observed.
- Done: RED GEE manifest audit tests exist.
- Commit suggestion: `test: add GEE export manifest audit tests`.

#### T047 - Implement GEE export manifest builder
- Source: `[Req: FR-004, FR-014, SC-002]`; depends on T031, T046.
- Inspect: GEE tests, `cloud/batch/gee_export.py`.
- Edit: `cloud/batch/gee_export.py`.
- TDD classification: strict TDD GREEN for T046.
- RED: `python3 -m pytest tests/cloud/test_gee_export_manifest.py`.
- GREEN: add required audit fields and selected-month validation.
- Refactor/check: keep manifest generation deterministic.
- Validation: `python3 -m pytest tests/cloud/test_gee_export_manifest.py`.
- Done: GEE manifest tests pass.
- Commit suggestion: `feat: build GEE export manifest`.

#### T048 - Implement EVI validation report builder
- Source: `[Req: FR-005, FR-014, SC-002]`; depends on T034, T044.
- Inspect: EVI report tests and report contracts.
- Edit: `cloud/batch/evi_validation.py`.
- TDD classification: strict TDD GREEN for T044.
- RED: `python3 -m pytest tests/cloud/test_evi_validation_report.py`.
- GREEN: implement wide schema, long schema, area identity, row count, empty zone count, advisory warning report.
- Refactor/check: keep numeric comparisons separate from contract failures.
- Validation: `python3 -m pytest tests/cloud/test_evi_validation_report.py`.
- Done: EVI validation report tests pass.
- Commit suggestion: `feat: build EVI validation reports`.

#### T049 - Implement optional EVI reference comparison
- Source: `[Req: FR-005, SC-002]`; depends on T045.
- Inspect: reference comparison tests.
- Edit: `cloud/batch/evi_reference.py`.
- TDD classification: strict TDD GREEN for T045.
- RED: `python3 -m pytest tests/cloud/test_evi_reference_comparison.py`.
- GREEN: implement advisory-only differences, zero-match handling, insufficient-pair handling, correlations.
- Refactor/check: ensure malformed optional sample is reported according to tests/spec.
- Validation: `python3 -m pytest tests/cloud/test_evi_reference_comparison.py`.
- Done: EVI reference tests pass.
- Commit suggestion: `feat: compare EVI outputs to optional reference`.

#### T050 - Wire EVI audit outputs into worker
- Source: `[Req: FR-004, FR-005, FR-014, SC-002]`; depends on T047, T048, T049.
- Inspect: `cloud/batch/evi_worker.py`, GEE/EVI report tests.
- Edit: `cloud/batch/evi_worker.py`.
- TDD classification: strict TDD integration.
- RED: `python3 -m pytest tests/cloud/test_evi_validation_report.py tests/cloud/test_evi_reference_comparison.py tests/cloud/test_gee_export_manifest.py tests/cloud/test_cloud_batch_evi_worker.py`.
- GREEN: wire `evi_extraction_manifest.json`, `evi_validation_report.json`, and `gee_export_manifest.json` into worker outputs.
- Refactor/check: maintain advisory-only EVI numeric comparison.
- Validation: same pytest command.
- Done: all US2 EVI audit tests pass.
- Commit suggestion: `feat: wire EVI audit evidence into worker`.

#### T051 - Run US2 targeted tests
- Source: `[Req: FR-004, FR-005, FR-014, SC-002]`; depends on T050.
- Inspect: US2 tests.
- Edit: no product code; optional task notes only.
- TDD classification: validation-only.
- RED: not applicable.
- GREEN/validation: run `python3 -m pytest tests/cloud/test_evi_validation_report.py tests/cloud/test_evi_reference_comparison.py tests/cloud/test_gee_export_manifest.py`.
- Refactor/check: fix failures through owning tasks with TDD.
- Done: command passes.
- Commit suggestion: `test: validate US2 EVI audit contracts`.

### Wave 14-18: User Story 3 Release Consumption

#### T052 - Add release manifest contract test
- Source: `[Req: FR-011, FR-012, SC-006, SC-007]`; depends on T040.
- Inspect: release artifact contract, report contracts.
- Edit/test: `tests/cloud/test_release_manifest_contract.py`.
- TDD classification: strict contract RED task.
- RED: test required fields, `status=current`, copied/referenced entries, checksums; run `python3 -m pytest tests/cloud/test_release_manifest_contract.py`; expect missing typed builder.
- GREEN: deferred to T055.
- Done: expected RED failure observed.
- Commit suggestion: `test: add release manifest contract tests`.

#### T053 - Add release conflict test
- Source: `[Req: FR-012, SC-006]`; depends on T040.
- Inspect: release writer and fake object-store generation preconditions.
- Edit/test: `tests/cloud/test_release_conflict.py`.
- TDD classification: strict contract RED task.
- RED: test generation-precondition loss, `release_conflict`, previous manifest unchanged; run `python3 -m pytest tests/cloud/test_release_conflict.py`; expect missing conflict handling.
- GREEN: deferred to T056.
- Done: expected RED failure observed.
- Commit suggestion: `test: add release conflict tests`.

#### T054 - Add downstream consumer smoke test
- Source: `[Req: FR-011, SC-007]`; depends on T040.
- Inspect: release artifact consumer rules.
- Edit/test: `tests/cloud/test_release_consumer.py`.
- TDD classification: strict contract RED task.
- RED: test reader locates base input, summary, predictions, evidence only through manifest; run `python3 -m pytest tests/cloud/test_release_consumer.py`; expect missing reader.
- GREEN: deferred to T057.
- Done: expected RED failure observed.
- Commit suggestion: `test: add release consumer smoke tests`.

#### T055 - Implement release manifest typed builder
- Source: `[Req: FR-011, FR-012, FR-014, SC-007]`; depends on T052.
- Inspect: release manifest tests and report contracts.
- Edit: `cloud/orchestrator/release_manifest.py`.
- TDD classification: strict TDD GREEN for T052.
- RED: `python3 -m pytest tests/cloud/test_release_manifest_contract.py`.
- GREEN: implement copied/referenced artifact fields, validation/inference status, advisory warning state, timestamp, immutable refs.
- Refactor/check: keep manifest serializable and stable.
- Validation: pytest command passes.
- Done: release manifest contract tests pass.
- Commit suggestion: `feat: build release manifests`.

#### T056 - Implement release conflict handling
- Source: `[Req: FR-012, SC-006]`; depends on T053, T055.
- Inspect: release conflict tests and `cloud/orchestrator/release.py`.
- Edit: `cloud/orchestrator/release.py`.
- TDD classification: strict TDD GREEN for T053.
- RED: `python3 -m pytest tests/cloud/test_release_conflict.py`.
- GREEN: handle generation-precondition failure, `release_conflict`, unchanged previous manifest, no-current-release case.
- Refactor/check: share status writing with run state if already tested.
- Validation: pytest command passes.
- Done: release conflict tests pass.
- Commit suggestion: `feat: handle release manifest conflicts`.

#### T057 - Implement downstream manifest reader helper
- Source: `[Req: FR-011, SC-007]`; depends on T054, T055.
- Inspect: release consumer tests.
- Edit: `cloud/common/release_reader.py`.
- TDD classification: strict TDD GREEN for T054.
- RED: `python3 -m pytest tests/cloud/test_release_consumer.py`.
- GREEN: implement helper that resolves consumer paths from `release_manifest.json` and rejects bare folder inference.
- Refactor/check: keep it read-only.
- Validation: pytest command passes.
- Done: release consumer tests pass.
- Commit suggestion: `feat: read release artifacts from manifest`.

#### T058 - Update quickstart validation examples
- Source: `[Req: FR-011, FR-014, SC-007]`; depends on T057.
- Inspect: `quickstart.md`, release reader helper.
- Edit: `specs/001-cloud-base-input/quickstart.md`.
- TDD classification: docs-only validation exception.
- TDD exception: no runtime behavior; validation is docs grep plus helper tests.
- RED: run `rg 'release_reader|release_manifest.json|cloud.common.release_reader' specs/001-cloud-base-input/quickstart.md`; expect missing implemented helper reference.
- GREEN: update quickstart with implemented release manifest reader command/helper path.
- Refactor/check: do not alter product scope.
- Validation: `python3 -m pytest tests/cloud/test_release_consumer.py && rg 'release_manifest.json' specs/001-cloud-base-input/quickstart.md`.
- Done: quickstart references implemented release reader.
- Commit suggestion: `docs: update release consumption quickstart`.

#### T059 - Run US3 targeted tests
- Source: `[Req: FR-011, FR-012, SC-006, SC-007]`; depends on T056, T057, T058.
- Inspect: US3 tests and quickstart.
- Edit: no product code; optional task notes only.
- TDD classification: validation-only.
- RED: not applicable.
- GREEN/validation: run `python3 -m pytest tests/cloud/test_release_manifest_contract.py tests/cloud/test_release_conflict.py tests/cloud/test_release_consumer.py`.
- Refactor/check: fix failures through owning tasks with TDD.
- Done: command passes.
- Commit suggestion: `test: validate US3 release consumption`.

### Wave 12-21: Polish, Regression, and Final Gates

#### T060 - Add end-to-end fake cloud quickstart test
- Source: `[Req: FR-001, FR-011, FR-012, FR-014, SC-001, SC-007, SC-011]`; depends on T041, T050, T056.
- Inspect: quickstart, orchestrator fake services, release reader.
- Edit/test: `tests/cloud/test_quickstart_fake_cloud.py`.
- TDD classification: integration characterization/contract test.
- RED: write fake cloud quickstart test covering manifest validation through release readback; run `python3 -m pytest tests/cloud/test_quickstart_fake_cloud.py`. If it fails, fix through owning behavior tasks using strict TDD; if it passes immediately, record it as characterization coverage.
- GREEN: no production code in this task unless a missing behavior is exposed; then create a focused RED in the owning module first.
- Refactor/check: keep fixture small.
- Validation: pytest command passes.
- Done: fake quickstart test exists and passes or exposes a bug routed to owning task.
- Commit suggestion: `test: add fake cloud quickstart coverage`.

#### T061 - Add dependency and Docker smoke checks
- Source: `[Req: FR-003, FR-008, SC-008, SC-009]`; depends on T042.
- Inspect: Dockerfile, requirements, entrypoint modules.
- Edit/test: `tests/cloud/test_runtime_image_contract.py`.
- TDD classification: smoke/contract test.
- RED: write tests for single-image digest metadata and entrypoint availability; run `python3 -m pytest tests/cloud/test_runtime_image_contract.py`; expect missing metadata/import issues if T042 incomplete.
- GREEN: adjust Dockerfile metadata only if required; behavior code changes must use focused TDD.
- Refactor/check: avoid requiring a live Docker daemon unless explicitly guarded.
- Validation: pytest command passes.
- Done: runtime image contract tests pass.
- Commit suggestion: `test: add runtime image contract checks`.

#### T062 - Update workflow runbook
- Source: `[Req: FR-013, FR-014, SC-007, SC-008]`; depends on T041, T050, T056.
- Inspect: `docs/03_workflow_runbook.md`, quickstart, non-goals.
- Edit: `docs/03_workflow_runbook.md`.
- TDD classification: docs-only validation exception.
- TDD exception: no runtime behavior; validation is text contract check.
- RED: run `rg 'Cloud Run|Cloud Batch|Vertex AI custom-job|reference-only|quickstart' docs/03_workflow_runbook.md`; expect missing cloud E2E runbook section.
- GREEN: add cloud E2E monthly run section pointing to quickstart and keeping local ArcPy workflow reference-only.
- Refactor/check: do not remove existing local workflow docs.
- Validation: rerun `rg` command and `git diff --check -- docs/03_workflow_runbook.md`.
- Done: docs reflect implemented cloud workflow and non-goals.
- Commit suggestion: `docs: add cloud e2e runbook section`.

#### T063 - Update output inventory
- Source: `[Req: FR-011, FR-013, FR-014, SC-007]`; depends on T040, T055.
- Inspect: `docs/04_output_inventory.md`, release artifact contract.
- Edit: `docs/04_output_inventory.md`.
- TDD classification: docs-only validation exception.
- TDD exception: no runtime behavior; validation is text contract check.
- RED: run `rg 'released/\\{YYYYMM\\}|runs/\\{run_id\\}|forbidden|Vertex AI|release_manifest' docs/04_output_inventory.md`; expect missing cloud release inventory detail.
- GREEN: add cloud run/release artifact inventory and forbidden output family notes.
- Refactor/check: keep existing local inventory intact.
- Validation: rerun `rg` command and `git diff --check -- docs/04_output_inventory.md`.
- Done: output inventory documents cloud artifacts and forbidden families.
- Commit suggestion: `docs: add cloud release artifact inventory`.

#### T064 - Run existing regression tests
- Source: `[Req: FR-006, FR-007, FR-008, FR-009, FR-013, SC-003, SC-004, SC-005]`; depends on T043.
- Inspect: existing regression tests.
- Edit: no product code unless a regression fails; then use TDD in owning module.
- TDD classification: validation-only.
- RED: not applicable.
- GREEN/validation: run `python3 -m pytest tests/test_build_monthly_ipcch_base_input.py tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/test_reshape_remote_sensing_wide_to_long.py`.
- Refactor/check: route failures to the responsible previous task; do not patch tests to match broken behavior.
- Done: command passes.
- Commit suggestion: `test: run existing IPCCH regressions`.

#### T065 - Run cloud contract tests
- Source: all FR/SC listed in task; depends on T009, T043, T051, T059, T060, T061.
- Inspect: full `tests/cloud/`.
- Edit: no product code unless failures require TDD fixes.
- TDD classification: validation-only.
- RED: not applicable.
- GREEN/validation: run `python3 -m pytest tests/cloud`.
- Refactor/check: if failures appear, return to owning task and use strict TDD.
- Done: all cloud contract tests pass.
- Commit suggestion: `test: run cloud contract suite`.

#### T066 - Run artifact validation checks
- Source: `[Req: FR-014, SC-007, SC-008, SC-011]`; depends on T062, T063, T064, T065.
- Inspect: schema, git diff.
- Edit: no product code unless validation failure requires owning-task fix.
- TDD classification: validation-only.
- RED: not applicable.
- GREEN/validation: run `python3 -m json.tool specs/001-cloud-base-input/contracts/input-manifest.schema.json` and `git diff --check -- specs/001-cloud-base-input cloud docker tests docs`.
- Refactor/check: route whitespace/schema failures to owning task.
- Done: both commands pass.
- Commit suggestion: `chore: validate cloud artifacts`.

#### T067 - Add optional gated live GCP smoke test
- Source: `[Req: FR-001, FR-002, FR-004, FR-005, FR-006, FR-008, FR-009, FR-010, FR-011, FR-012, FR-013, FR-014, SC-001, SC-002, SC-005, SC-006, SC-007, SC-008, SC-009, SC-010, SC-011]`; depends on T065, T066.
- Inspect: quickstart, execution contract, test env var conventions.
- Edit/test: `tests/cloud/test_gcp_smoke_monthly_e2e.py`.
- TDD classification: optional gated smoke test.
- RED: write smoke test that skips unless explicit GCP smoke env vars are present; run `python3 -m pytest tests/cloud/test_gcp_smoke_monthly_e2e.py`. Without env vars, expected result is skipped; with env vars, expected result before live infrastructure is caller-visible cloud failure.
- GREEN: no production code unless smoke exposes a bug; route bug to owning task with strict TDD.
- Refactor/check: do not hardcode project IDs, buckets, or secrets.
- Validation: `python3 -m pytest tests/cloud/test_gcp_smoke_monthly_e2e.py`; with credentials, it must cover Cloud Run dispatch, Batch/GEE/rasterio, Vertex AI custom job, release manifest, and forbidden side-effect absence.
- Done: test is present, safely skipped without env vars, and ready for live run when deployment values exist.
- Commit suggestion: `test: add gated live GCP smoke test`.

## Global Validation

- Focused foundation tests: `python3 -m pytest tests/cloud/test_manifest_contract.py tests/cloud/test_report_contracts.py tests/cloud/test_object_refs.py tests/cloud/test_object_store.py tests/cloud/test_run_state.py tests/cloud/test_forbidden_side_effects.py tests/cloud/test_runtime_defaults.py`
- US1 targeted tests: `python3 -m pytest tests/cloud/test_orchestrator_contract.py tests/cloud/test_cloud_batch_evi_worker.py tests/cloud/test_rasterio_evi_extraction.py tests/cloud/test_monthly_assembly_wrapper.py tests/cloud/test_vertex_ai_custom_job_contract.py tests/cloud/test_release_writer.py`
- US2 targeted tests: `python3 -m pytest tests/cloud/test_evi_validation_report.py tests/cloud/test_evi_reference_comparison.py tests/cloud/test_gee_export_manifest.py`
- US3 targeted tests: `python3 -m pytest tests/cloud/test_release_manifest_contract.py tests/cloud/test_release_conflict.py tests/cloud/test_release_consumer.py`
- Existing regression tests: `python3 -m pytest tests/test_build_monthly_ipcch_base_input.py tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/test_reshape_remote_sensing_wide_to_long.py`
- Full cloud contracts: `python3 -m pytest tests/cloud`
- JSON schema check: `python3 -m json.tool specs/001-cloud-base-input/contracts/input-manifest.schema.json`
- Diff check: `git diff --check -- specs/001-cloud-base-input cloud docker tests docs`
- Optional live GCP smoke: `python3 -m pytest tests/cloud/test_gcp_smoke_monthly_e2e.py`

No separate lint, typecheck, build, or CI command was discovered in repo root.

## Final Self-Audit

- Every micro-plan entry maps to an existing task ID T001-T067.
- No new product requirement, architecture change, or remote-sensing family was
  introduced.
- Behavior-changing implementation tasks have RED/GREEN/validation commands.
- Test-authoring tasks are RED gates and defer GREEN to dependent implementation
  tasks.
- Docs-only tasks have per-task validation-only exception statements.
- Unknown live deployment values are warnings/blockers for live run only, not
  invented facts.
- The execution waves preserve `tasks.md` dependencies.
- The plan treats missing live cloud evidence as warning and T067 blocker unless
  credentials/env vars are provided.

## Implementation Constraint Prompt

Paste this before implementation:

```text
Read specs/001-cloud-base-input/implementation-micro-plan.md first. Use it only
as an execution guide. If it conflicts with Speckit artifacts, stop and report
the conflict.

Use this active feature source-of-truth order:
1. resolved analyze findings / human resolution notes
2. active feature tasks.md
3. active feature plan.md
4. active feature spec.md
5. active feature evidence.md / repo evidence
6. contracts / data model / quickstart / supplementary active feature docs
7. implementation-micro-plan.md

Do not edit spec.md, plan.md, or tasks.md unless explicitly instructed.

For behavior-changing tasks, follow TDD:
1. write or update the failing test first,
2. run it and confirm the expected failure,
3. implement the smallest change,
4. run the relevant test until it passes,
5. refactor only after green.

For test-authoring tasks, complete the task at RED only after observing the
expected failure. Do not add production code in the same test-authoring task.

For docs-only validation exceptions, state the exception before editing and run
the listed validation command after editing.

Do not change scope, architecture, task intent, acceptance criteria, or task
dependencies without updating the Speckit artifacts first.

Do not add FLDAS, GOSIF-GPP, VIIRS, external tabular download automation, model
training, prediction maps, prediction sheets, full delivery artifacts, local
workstation scoring, Vertex AI Batch Prediction, or registered Vertex AI Model
deployment for v1.

Run validation before marking work complete. If validation is not run, do not
mark the task complete; state Validation Status: Not Executed and why.
```
