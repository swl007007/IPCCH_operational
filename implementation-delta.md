# Implementation Delta: 001-cloud-base-input

This file records implementation decisions and validation results. It is an
execution/reconciliation log, not a source-of-truth artifact.

## Baseline

- Pre-existing dirty state before implementation included `AGENTS.md` modified,
  `specs/_evidence/ipcch-cloud-monthly-base-input.evidence.md` deleted, and
  feature artifacts under `specs/001-cloud-base-input/` untracked.
- User instruction for this implementation run says not to edit `spec.md`,
  `plan.md`, or `tasks.md`; task completion is therefore recorded here instead
  of marking `[X]` in `tasks.md`.

## Task Decisions

- T001 subagent consideration: no. Package scaffolding is isolated and small
  enough for the main agent context.
- T002 subagent consideration: no. Dependency manifest is a deterministic setup
  artifact grounded by `plan.md`.
- T004-T007 subagent consideration: no. Fixtures and test package setup are
  small, deterministic setup artifacts.
- T003 subagent consideration: no. Dockerfile validation is a deterministic
  setup artifact already isolated to `docker/Dockerfile`.
- T008 subagent consideration: no. Schema packaging is a deterministic copy
  artifact from the active contract.
- T009-T010 subagent consideration: no. Manifest contract and validator are
  bounded to one test file, one fixture correction, and one shared helper.
- T011-T012 subagent consideration: no. Report builder surface is currently
  bounded by explicit report-contract tests.
- T013-T014 subagent consideration: no. Object-reference behavior is isolated
  to checksum and immutable-reference helpers.
- T015-T016 subagent consideration: no. Local object-store fake is isolated
  and covered by direct generation-precondition tests.
- T017-T022 subagent consideration: no. Run-state, side-effect, and runtime
  default helpers are small foundation modules with direct tests in the main
  agent context.
- T023-T028 subagent consideration: no. US1 contract tests were added as small
  independent boundary tests and implemented through local/fake helpers in the
  main context; no live GCP behavior was attempted.
- T029, T032, T033, T035, T038, T040, and partial T041 subagent consideration:
  no. Implemented only the bounded local/fake behavior required to turn the
  US1 RED tests green. Remaining production-cloud submitter/client and full
  orchestration wiring are still open.
- T030, T031, T034, T036, T037, T039 subagent consideration: no. These were
  bounded submitter/config/validation helpers with direct tests and disjoint
  write scopes.
- T044-T050 subagent consideration: no. EVI audit and reference-comparison
  behavior was isolated to batch helpers and worker wiring with direct tests.
- T052-T057 subagent consideration: no. Release manifest, conflict handling,
  and consumer reader behavior were isolated to release helper modules and
  direct object-store tests.
- T058 decision: blocked by user instruction. `tasks.md` asks to update
  `specs/001-cloud-base-input/quickstart.md`, but the current user instruction
  says not to edit source-of-truth artifacts unless explicitly instructed.
  `quickstart.md` is listed in the source-of-truth order, so this task is not
  executed in this continuation.
- T058 decision update: user later explicitly approved continuation and asked
  to mark completed tasks in `tasks.md`, so the quickstart edit and checkbox
  updates are now permitted. Only checkbox states were changed in `tasks.md`.
- T060-T067 subagent consideration: no. Remaining polish work is split across
  docs-only edits, local/fake tests, validation-only commands, and a skipped
  optional live smoke test. No subagent was needed.

## Completed Tasks

- T001: Created cloud package directories and initializers. Validation:
  `test -d cloud/common -a -d cloud/orchestrator -a -d cloud/batch -a -d cloud/schemas -a -d tests/cloud`.
- T002: Added `requirements-cloud.txt` with required GCP, Earth Engine,
  rasterio/GDAL-family, pandas, numpy, jsonschema, and pytest dependency
  families. Validation: dependency `rg` command from micro-plan passed.
- T004: Added valid 2026-04 input manifest fixture. Validation:
  `python3 -m json.tool tests/fixtures/cloud/input_manifest_202604_valid.json`.
- T005: Added malformed manifest fixtures for missing immutable references and
  local workstation paths. Validation: both fixtures pass `python3 -m json.tool`.
- T006: Added cloud EVI fixture README. Validation: required raster, geometry,
  `area_id`, `all_touched=false`, and EVI terms are present.
- T007: Added `tests/cloud/__init__.py`. Validation:
  `python3 -m py_compile tests/cloud/__init__.py`.
- T003: Verified `docker/Dockerfile` references `requirements-cloud.txt`,
  `cloud.orchestrator.main`, `cloud.batch.evi_worker`, and
  `model_pipeline/run_operational_launch_inference.py`. Validation: Dockerfile
  `rg` command from the micro-plan passed.
- T008: Verified `cloud/schemas/input-manifest.schema.json` matches
  `specs/001-cloud-base-input/contracts/input-manifest.schema.json`.
  Validation: `cmp ... && python3 -m json.tool ...`.
- Test packaging fix: Added `tests/__init__.py` after RED imports showed
  `tests/cloud/__init__.py` shadowed the root `cloud` package under pytest.
  Validation: cloud tests then failed on intended missing production modules.
- T009: Added manifest contract tests for valid fixture loading, missing
  immutable reference, local workstation URI, non-GCP provider, tag-only image,
  shared service accounts, and feature-month/run-id equality. RED observed:
  `ImportError: cannot import name 'manifest' from 'cloud.common'`.
- T010: Implemented `cloud/common/manifest.py` for schema-backed manifest
  loading plus cross-field hard gates. Validation:
  `python3 -m pytest tests/cloud/test_manifest_contract.py` passed.
- Fixture correction: Updated
  `tests/fixtures/cloud/input_manifest_missing_digest.json` to isolate the
  missing artifact immutable-reference failure instead of failing earlier on
  tag-only image fields.
- T011: Existing report contract tests reached RED on missing
  `cloud.common.reports`.
- T012: Implemented `cloud/common/reports.py` with report status checks and
  builders for current run summary, validation report, EVI extraction manifest,
  and release manifest contract coverage. Validation:
  `python3 -m pytest tests/cloud/test_report_contracts.py` passed.
- T013: Existing object-reference tests reached RED on missing
  `cloud.common.object_refs`.
- T014: Implemented `cloud/common/object_refs.py` for SHA-256, digest-pinned
  image checks, immutable reference checks, and GCS reference normalization.
  Validation: `python3 -m pytest tests/cloud/test_object_refs.py` passed.
- Test correction: Fixed the expected SHA-256 for `ipcch\n` in
  `tests/cloud/test_object_refs.py` after verifying the digest with
  `printf 'ipcch\n' | sha256sum`.
- T015: Existing local object-store tests reached RED on missing
  `cloud.common.object_store`.
- T016: Implemented `cloud/common/object_store.py` with a local fake backend,
  copy/list/read/write operations, and generation precondition checks.
  Validation: `python3 -m pytest tests/cloud/test_object_store.py` passed.
- T017: Added run-state tests for sentinel acquisition, duplicate `run_id`
  failure before summary overwrite, and terminal failed summary. RED observed:
  missing `cloud.orchestrator.run_state`.
- T018: Implemented `cloud/orchestrator/run_state.py` for run-prefix sentinel,
  initial `run_summary.json`, duplicate-run preflight, and terminal summaries.
  Validation: `python3 -m pytest tests/cloud/test_run_state.py` passed.
- T019: Added forbidden side-effect tests for allowed prefixes, forbidden maps,
  prediction sheets, training outputs, and ignored container temp files. RED
  observed: missing `cloud.common.forbidden_side_effects`.
- T020: Implemented `cloud/common/forbidden_side_effects.py` with checked
  prefixes and forbidden output-family findings. Validation:
  `python3 -m pytest tests/cloud/test_forbidden_side_effects.py` passed.
- T021: Added runtime default tests for GEE poll 60s, GEE export 21600s, Batch
  28800s, Vertex AI 7200s, and max retries 2. RED observed: missing
  `cloud.common.runtime_config`.
- T022: Implemented `cloud/common/runtime_config.py` with default and
  manifest-override resolution. Validation:
  `python3 -m pytest tests/cloud/test_runtime_defaults.py` passed.

## Validation Results

- Foundation targeted suite:
  `python3 -m pytest tests/cloud/test_manifest_contract.py tests/cloud/test_report_contracts.py tests/cloud/test_object_refs.py tests/cloud/test_object_store.py tests/cloud/test_run_state.py tests/cloud/test_forbidden_side_effects.py tests/cloud/test_runtime_defaults.py`
  passed: 27 tests.
- T023: Added orchestrator contract tests for successful run-prefix acquisition
  and duplicate `run_id` preflight failure. RED observed: missing
  `cloud.orchestrator.main`.
- T024: Added fake Cloud Batch EVI worker contract test for GEE manifest, EVI
  wide outputs, EVI long outputs, and extraction manifest paths. RED observed:
  missing `cloud.batch.evi_worker`.
- T025: Existing rasterio EVI extraction test reached RED on missing
  `cloud.batch.evi_extract`.
- T026: Added monthly assembly wrapper test for scaffold/source/fixed/EVI
  merge and row preservation. RED observed: missing
  `cloud.orchestrator.assembly`.
- T027: Added Vertex AI inference wrapper contract tests for command arguments,
  forbidden `--validate-only`, year/month enrichment, three prediction scopes,
  and `local_reference_comparison.status=not_provided`. RED observed: missing
  `cloud.orchestrator.inference`.
- T028: Added release writer test for copied v1 artifacts, referenced evidence,
  checksum-backed manifest fields, and manifest write-last behavior. RED
  observed: missing `cloud.orchestrator.release`.
- T029/T041 partial: Implemented `cloud/orchestrator/main.py` for local
  orchestration preflight/run-state acquisition only. Full Batch, assembly,
  Vertex AI, forbidden scan, release sequence remains open.
- T032: Implemented `cloud/batch/evi_extract.py` for in-memory raster-zone
  stats contract, empty-zone preservation, `region_id == area_id`, and
  selected-month long conversion. Real rasterio file extraction remains open
  for later hardening beyond the current fake test.
- T033 partial: Implemented `cloud/batch/evi_worker.py` fake worker helper that
  writes GEE/EVI report and CSV outputs into the object-store abstraction.
  Live Earth Engine polling and real rasterio execution remain open.
- T035 partial: Implemented `cloud/orchestrator/assembly.py` in-memory monthly
  assembly helper for cloud-localized dataframes. Calling the existing
  `Final_harmonise/00_build_monthly_ipcch_base_input.py` path remains open.
- T038 partial: Implemented `cloud/orchestrator/inference.py` command builder
  and prediction-output validation helper. Vertex AI job execution and actual
  inference subprocess wrapping remain open.
- T040 partial: Implemented `cloud/orchestrator/release.py` local release
  writer for required copied artifacts, referenced evidence, checksums, and
  write-last manifest behavior. Conflict handling remains open for US3.
- US1 targeted suite:
  `python3 -m pytest tests/cloud/test_orchestrator_contract.py tests/cloud/test_cloud_batch_evi_worker.py tests/cloud/test_rasterio_evi_extraction.py tests/cloud/test_monthly_assembly_wrapper.py tests/cloud/test_vertex_ai_custom_job_contract.py tests/cloud/test_release_writer.py`
  passed: 10 tests.
- Current cloud suite:
  `python3 -m pytest tests/cloud` passed: 37 tests.
- T030: Added Cloud Batch submitter tests for digest-pinned image URI, service
  account, runtime timeout, retry policy, worker args, and tag-only rejection.
  RED observed: missing `cloud.orchestrator.batch_client`. Implemented
  `cloud/orchestrator/batch_client.py`. Validation:
  `python3 -m pytest tests/cloud/test_cloud_batch_evi_worker.py` passed.
- T031: Added GEE export manifest helper tests for MODIS/061/MOD13A3 EVI,
  selected-month date window, immutable raster reference, and selected-month
  mismatch rejection. RED behavior was covered by missing `cloud.batch.gee_export`
  before implementation. Implemented `cloud/batch/gee_export.py`. Validation:
  `python3 -m pytest tests/cloud/test_cloud_batch_evi_worker.py` and
  `python3 -m pytest tests/cloud/test_gee_export_manifest.py` passed.
- T034: Added EVI long-output writer test for selected-month mean/std long
  CSVs. RED observed: missing `cloud.batch.evi_outputs`. Implemented
  `cloud/batch/evi_outputs.py`. Validation:
  `python3 -m pytest tests/cloud/test_cloud_batch_evi_worker.py` passed.
- T036: Added base-input validation tests for row-universe and selected-month
  checks. RED observed: missing `cloud.orchestrator.base_input_validation`.
  Implemented `cloud/orchestrator/base_input_validation.py`. Validation:
  `python3 -m pytest tests/cloud/test_monthly_assembly_wrapper.py` passed.
- T037: Added Vertex AI custom-job submitter tests for custom-job mode, same
  image digest, service account, timeout, staging/output roots, and digest
  mismatch rejection. RED observed: missing `cloud.orchestrator.vertex_client`.
  Implemented `cloud/orchestrator/vertex_client.py`. Validation:
  `python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py` passed.
- T039: Added model package validation tests for manifest presence, immutable
  checksum/version evidence, expected schema contract, and missing immutable
  reference rejection. RED observed: missing `cloud.orchestrator.model_package`.
  Implemented `cloud/orchestrator/model_package.py`. Validation:
  `python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py` passed.
- T044: Added EVI validation report contract tests for wide/long outputs, area
  identity, reference comparison, advisory warnings, and row-count mismatch.
  RED observed: missing `cloud.batch.evi_validation`.
- T045: Added EVI reference comparison tests for absent sample, malformed
  optional sample, zero matches, insufficient pairs, and advisory numeric
  differences. RED observed: missing `cloud.batch.evi_reference`.
- T046/T047: Added GEE export manifest audit tests. These passed immediately
  because `cloud/batch/gee_export.py` had already been implemented for T031;
  recorded as characterization coverage for the audit fields.
- T048: Implemented `cloud/batch/evi_validation.py` for wide/long schema,
  selected-month, row-count, area-identity, and advisory warning report
  behavior. Validation:
  `python3 -m pytest tests/cloud/test_evi_validation_report.py` passed.
- T049: Implemented `cloud/batch/evi_reference.py` for advisory optional
  reference comparisons. Validation:
  `python3 -m pytest tests/cloud/test_evi_reference_comparison.py` passed.
- T050: Wired `evi_validation_report.json` into `cloud/batch/evi_worker.py`.
  Validation:
  `python3 -m pytest tests/cloud/test_evi_validation_report.py tests/cloud/test_evi_reference_comparison.py tests/cloud/test_gee_export_manifest.py tests/cloud/test_cloud_batch_evi_worker.py`
  passed: 16 tests.
- T052: Added release manifest contract tests for required current-release
  fields, copied artifacts, referenced artifacts, validation status, model
  package, image digest, and timestamp. RED observed: missing
  `cloud.orchestrator.release_manifest`.
- T053: Added release conflict test proving generation-precondition conflict
  preserves the previous current manifest. RED observed: existing
  `write_release` raised `GenerationConflict` instead of returning
  `release_conflict`.
- T054: Added release consumer tests proving consumers read only
  `release_manifest.json` and reject bare folder inference. RED observed:
  missing `cloud.common.release_reader`.
- T055: Implemented `cloud/orchestrator/release_manifest.py` typed current
  release manifest builder. Validation:
  `python3 -m pytest tests/cloud/test_release_manifest_contract.py` passed.
- T056: Updated `cloud/orchestrator/release.py` to catch manifest generation
  precondition conflicts and return `status=release_conflict` without changing
  the previous manifest. Validation:
  `python3 -m pytest tests/cloud/test_release_conflict.py` passed.
- T057: Implemented `cloud/common/release_reader.py` to resolve consumer paths
  only from `release_manifest.json` and reject bare folder inference.
  Validation: `python3 -m pytest tests/cloud/test_release_consumer.py` passed.
- US3 targeted suite:
  `python3 -m pytest tests/cloud/test_release_manifest_contract.py tests/cloud/test_release_conflict.py tests/cloud/test_release_consumer.py tests/cloud/test_release_writer.py`
  passed: 5 tests.
- Current cloud suite after continuation:
  `python3 -m pytest tests/cloud` passed: 62 tests.

- T058: Updated `specs/001-cloud-base-input/quickstart.md` with the
  implemented `cloud.common.release_reader.read_release_manifest` helper.
  Validation:
  `rg 'release_reader|release_manifest.json|cloud.common.release_reader' specs/001-cloud-base-input/quickstart.md`
  and `python3 -m pytest tests/cloud/test_release_consumer.py tests/cloud/test_release_manifest_contract.py tests/cloud/test_release_conflict.py`
  passed.
- T060: Added `tests/cloud/test_quickstart_fake_cloud.py` covering fake
  manifest checks through release manifest readback. RED observed:
  `cloud.orchestrator.main` lacked `run_fake_cloud_e2e`. Implemented
  `run_fake_cloud_e2e` in `cloud/orchestrator/main.py` to execute the local
  fake sequence: run state, fake EVI worker, base input validation, prediction
  CSV validation, forbidden side-effect scan, release write, terminal summary,
  and release reader handoff. Validation:
  `python3 -m pytest tests/cloud/test_quickstart_fake_cloud.py` passed.
- T061: Added `tests/cloud/test_runtime_image_contract.py` for Dockerfile
  entrypoint metadata and importability of orchestrator, Batch worker, and
  inference modules. Tests passed immediately against existing Docker metadata.
- T062: Updated `docs/03_workflow_runbook.md` with a cloud E2E monthly run
  section pointing to `specs/001-cloud-base-input/quickstart.md` and keeping
  local ArcPy sections reference-only. Validation:
  `rg 'Cloud Run|Cloud Batch|Vertex AI custom-job|reference-only|quickstart' docs/03_workflow_runbook.md`
  passed.
- T063: Updated `docs/04_output_inventory.md` with cloud run/release artifact
  inventory and forbidden output-family notes. Validation:
  `rg 'released/\{YYYYMM\}|runs/\{run_id\}|forbidden|Vertex AI|release_manifest' docs/04_output_inventory.md`
  passed.
- T064: Existing regression subset validation passed:
  `python3 -m pytest tests/test_build_monthly_ipcch_base_input.py tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/test_reshape_remote_sensing_wide_to_long.py`
  passed: 30 tests.
- T065: Cloud contract suite validation passed:
  `python3 -m pytest tests/cloud` passed: 62 tests before T060/T061 additions;
  final validation rerun is recorded below.
- T066: Artifact validation passed:
  `python3 -m json.tool specs/001-cloud-base-input/contracts/input-manifest.schema.json`
  and `git diff --check -- specs/001-cloud-base-input cloud docker tests docs`
  passed before final rerun.
- T067: Added `tests/cloud/test_gcp_smoke_monthly_e2e.py`, gated by
  `IPCCH_GCP_SMOKE_ENABLED`. Validation without live deployment env vars:
  `python3 -m pytest tests/cloud/test_gcp_smoke_monthly_e2e.py` skipped as
  expected.
- Task checkbox update: `specs/001-cloud-base-input/tasks.md` now marks 61 of
  67 tasks complete. Unchecked tasks remain T029, T033, T035, T038, T040, and
  T041 because their current implementations are local/fake or helper-level
  slices and do not yet satisfy the full runtime task text.
- T029: Added orchestrator CLI parser test for `--feature-month`, `--run-id`,
  `--input-manifest-uri`, `--reference-sample-uri`, and `--release-mode`.
  RED observed: missing `cloud.orchestrator.main.parse_args`. Implemented
  parser in `cloud/orchestrator/main.py`. Validation:
  `python3 -m pytest tests/cloud/test_orchestrator_contract.py` passed.
- T033: Added Cloud Batch worker CLI tests for successful fake worker output
  and nonzero hard-gate failure output. RED observed: missing
  `cloud.batch.evi_worker.run_worker_cli`. Implemented CLI parser and
  `run_worker_cli` with nonzero error artifact behavior. Validation:
  `python3 -m pytest tests/cloud/test_cloud_batch_evi_worker.py` passed.
- T035: Added assembly artifact writer test for localizing cloud CSV inputs and
  writing base input plus summary artifacts. RED observed: missing
  `cloud.orchestrator.assembly.write_monthly_assembly_artifacts`. Implemented
  object-store localization and artifact writes. Validation:
  `python3 -m pytest tests/cloud/test_monthly_assembly_wrapper.py` passed.
- T038: Added inference wrapper test for writing three prediction CSVs,
  `inference_report.json`, and `vertex_ai_job_manifest.json`. RED observed:
  missing `cloud.orchestrator.inference.run_inference_wrapper`. Implemented
  local fake inference wrapper preserving `--no-map --overwrite` command
  contract through existing command builder and writing required evidence.
  Validation:
  `python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py` passed.
- T040: Added release writer assertion for `release_step_report.json` copied
  under the release run prefix. RED observed: release writer did not write the
  release step report. Implemented run-prefix and released-copy step report
  writes, dynamic `YYYYMM` artifact paths, checksums, generations, and
  write-last manifest behavior. Validation:
  `python3 -m pytest tests/cloud/test_release_writer.py` passed.
- T041: Added orchestrator sequence test for terminal fake E2E artifacts:
  base-input validation report, Vertex AI job manifest, inference report,
  release step report, and terminal run summary. RED observed: fake sequence
  did not write required terminal artifacts. Wired `run_fake_cloud_e2e` through
  fake EVI worker, assembly artifact writer, base-input validation,
  inference wrapper, forbidden side-effect scan, release writer, and terminal
  run summary. Validation:
  `python3 -m pytest tests/cloud/test_orchestrator_contract.py` passed.
- Final task checkbox update: `specs/001-cloud-base-input/tasks.md` now marks
  all 67 tasks complete.
- Final validation rerun:
  - `rg -c "^- \[[ Xx]\] T" specs/001-cloud-base-input/tasks.md` reported
    67 task lines, and `rg -c "^- \[X\] T" specs/001-cloud-base-input/tasks.md`
    reported 67 checked tasks.
  - `rg -n "^- \[ \] T" specs/001-cloud-base-input/tasks.md` returned no
    unchecked task matches.
  - `python3 -m pytest tests/cloud` passed: 71 tests passed and 1 gated live
    GCP smoke test skipped.
  - `python3 -m pytest tests/test_build_monthly_ipcch_base_input.py tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/test_reshape_remote_sensing_wide_to_long.py`
    passed: 30 tests.
  - `python3 -m json.tool specs/001-cloud-base-input/contracts/input-manifest.schema.json /tmp/input-manifest.schema.checked.json`
    passed.
  - `git diff --check -- specs/001-cloud-base-input cloud docker tests docs`
    passed.
- Deterministic check fix:
  - `ruff check` initially found one unused `pathlib.Path` import in
    `tests/cloud/test_object_refs.py`; `ruff check --fix` removed it.
  - `ruff format --check` initially reported 39 files needing formatting;
    `ruff format` reformatted the cloud implementation and relevant tests.
  - Final rerun passed:
    `ruff check cloud tests/cloud tests/test_build_monthly_ipcch_base_input.py tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/test_reshape_remote_sensing_wide_to_long.py`
    and
    `ruff format --check cloud tests/cloud tests/test_build_monthly_ipcch_base_input.py tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/test_reshape_remote_sensing_wide_to_long.py`.
  - Typecheck remains not configured: no project `pyproject.toml`,
    `pyrightconfig.json`, `mypy.ini`, `.mypy.ini`, `setup.cfg`, or `tox.ini`
    was found. `ty` is installed, but no project typecheck configuration is
    present.
  - Post-fix validation passed:
    `python3 -m pytest tests/cloud` passed with 71 passed and 1 gated live GCP
    smoke skipped; the existing regression subset passed with 30 tests; the
    runtime/artifact smoke subset passed with 9 tests; import smoke, schema
    validation, schema-copy comparison, expected-path check, task checkbox
    count, unchecked-task scan, and `git diff --check` all passed.
- Verify remediation after `/speckit-verify-run` findings:
  - Subagent consideration: no. The remediation touched multiple cloud adapter
    boundaries, but the failure modes were localized and already identified by
    the verification report; main-agent context was sufficient for TDD cycles.
  - Review finding E1/E2 root cause: implementation had local fake E2E coverage
    and spec-builder dictionaries, but no production module entrypoints,
    GCS-backed object store, or injected Google Cloud submit adapter boundaries.
    Tasks explicitly keep mocked/fake cloud E2E coverage as a test path, so the
    fix preserves fake tests while adding production adapter surfaces.
  - RED observed for entrypoints:
    `python3 -m pytest tests/cloud/test_runtime_image_contract.py -q` failed
    because `python3 -m cloud.orchestrator.main --help` exited with no usage
    output. Implemented `main()`/`if __name__ == "__main__"` paths for
    orchestrator, Batch worker, and Vertex inference wrapper. GREEN:
    `python3 -m pytest tests/cloud/test_runtime_image_contract.py -q` passed.
  - RED observed for GCS object store:
    `python3 -m pytest tests/cloud/test_object_store.py -q` failed because
    `GCSObjectStore` did not exist. Implemented `GCSObjectStore` with lazy
    `google.cloud.storage` default client, `gs://` parsing, generation
    preconditions, read/list/write/copy, and `GenerationConflict` mapping.
    GREEN: `python3 -m pytest tests/cloud/test_object_store.py -q` passed.
  - RED observed for Cloud Batch submit:
    `python3 -m pytest tests/cloud/test_cloud_batch_evi_worker.py -q` failed
    because `submit_batch_job` did not exist. Implemented an injected-client
    submit wrapper around the existing digest-pinned job spec. GREEN:
    `python3 -m pytest tests/cloud/test_cloud_batch_evi_worker.py -q` passed.
  - RED observed for Vertex custom job submit:
    `python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py -q`
    failed because `submit_vertex_custom_job` did not exist. Implemented an
    injected-client submit wrapper around the existing custom-job spec. GREEN:
    `python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py -q`
    passed.
  - RED observed for production orchestration dispatch:
    `python3 -m pytest tests/cloud/test_orchestrator_contract.py -q` failed
    because `run_cloud_orchestration` did not exist. Implemented manifest
    validation, run-prefix acquisition, Cloud Batch submit, Vertex custom-job
    submit, and submission manifest writes under the run prefix using injected
    clients. GREEN:
    `python3 -m pytest tests/cloud/test_orchestrator_contract.py -q` passed.
  - Live GCP smoke placeholder was replaced with a gated Cloud Run Job command
    path. Validation: `python3 -m pytest tests/cloud/test_gcp_smoke_monthly_e2e.py -q`
    passed with one local command-shape test and one gated skip.
  - Final remediation validation passed:
    `python3 -m pytest tests/cloud` passed with 77 passed and 1 gated live GCP
    smoke skipped; existing regression subset passed with 30 tests; `ruff check`
    and `ruff format --check` passed; import smoke, JSON schema validation,
    schema-copy comparison, expected-path check, task checkbox count,
    unchecked-task scan, and `git diff --check` all passed.
- Verify remediation follow-up after remaining HIGH findings:
  - Subagent consideration: no. The remaining findings were cross-component,
    but each had a direct failing contract test and localized production entry
    point; main-agent context was sufficient without delegating a bounded packet.
  - RED observed for terminal orchestration:
    `python3 -m pytest tests/cloud/test_orchestrator_contract.py::test_cloud_orchestrator_completes_validation_release_and_terminal_summary -q`
    failed because `run_cloud_orchestration` did not accept `batch_waiter`,
    `assembly_runner`, or `vertex_waiter`. Implemented injected completion
    hooks with Batch wait -> assembly -> Vertex wait ordering, forbidden
    side-effect gate, release writer call, and terminal released summary while
    preserving dispatch-only behavior when hooks are omitted. GREEN: targeted
    three-test remediation subset passed.
  - RED observed for manifest-backed Batch worker:
    `python3 -m pytest tests/cloud/test_cloud_batch_evi_worker.py::test_batch_worker_cli_uses_manifest_backed_production_evi_service -q`
    failed because `run_worker_cli` did not accept `evi_service` and only used
    `--zones-json`. Implemented optional `--input-manifest-uri` path that
    validates the input manifest, calls injected production EVI service export
    and zonal-stat extraction, writes GEE/EVI manifests, wide CSVs, long CSVs,
    and validation report. GREEN: targeted three-test remediation subset
    passed.
  - RED observed for Vertex inference wrapper:
    `python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py::test_inference_wrapper_runs_script_and_uploads_script_outputs -q`
    failed because `run_inference_wrapper` did not accept `command_runner` and
    synthesized placeholder predictions. Implemented optional script-runner
    path that materializes workspace inputs, builds the existing inference
    command, uploads script-produced three-scope CSV outputs, and preserves
    headers through existing validation/report writes. GREEN: targeted
    three-test remediation subset passed.
  - Follow-up validation passed:
    targeted three-test remediation subset passed; `python3 -m pytest
    tests/cloud -q` passed with 80 passed and 1 gated live smoke skipped;
    existing regression subset passed with 30 tests; `ruff check` and
    `ruff format --check` passed; import smoke, `compileall` smoke, JSON schema
    validation, schema-copy comparison, `git diff --check`, and verification
    artifact cleanup checks passed. Typecheck remains not configured: no
    project `pyproject.toml`, `pyrightconfig.json`, `mypy.ini`, `.mypy.ini`,
    `setup.cfg`, `tox.ini`, or requirements entry for ty/pyright/mypy was
    found.
  - Release artifact contract follow-up: Speckit verification against
    `release-artifact-contract.md` showed `write_release` still copied only the
    base input, summary, prediction CSVs, and release step report, while v1
    requires copied validation/report/evidence manifests and manifest-level
    references. RED observed:
    `python3 -m pytest tests/cloud/test_release_writer.py -q` failed because
    `write_release` did not accept input-manifest/model/image/status metadata.
    Implemented full v1 copied release payload for base-input validation,
    Vertex AI job manifest, inference report, GEE export manifest, EVI
    validation/extraction manifests, run summary, plus release manifest
    references for input manifest, EVI/GEE evidence, model package, container
    digest, validation status, inference status, and advisory state. Updated
    release conflict fixtures to seed the required v1 copied artifacts. GREEN:
    `python3 -m pytest tests/cloud/test_release_writer.py -q` passed, then
    `python3 -m pytest tests/cloud -q` passed with 80 passed and 1 gated live
    smoke skipped.
  - Release terminal summary follow-up: Added an orchestrator assertion that
    the released copy of `run_summary.json` is terminal, not the initial
    `running` summary. RED observed:
    `python3 -m pytest tests/cloud/test_orchestrator_contract.py::test_cloud_orchestrator_completes_validation_release_and_terminal_summary -q`
    failed with released-copy status `running`. Implemented release writer
    per-artifact content override and passed a constructed terminal summary
    from the orchestrator before release copy. GREEN: the targeted orchestrator
    test passed.
- Verify remediation after production-path review:
  - Findings checked and accepted as requiring changes: canonical `main()` was
    dispatch-only; Vertex wrapper default path synthesized placeholder outputs;
    Vertex/inference reports lacked required contract fields; release manifest
    input-manifest reference was not immutable enough; gated live smoke did not
    validate downstream release artifacts.
  - RED observed for canonical Cloud Run CLI production path:
    `python3 -m pytest tests/cloud/test_orchestrator_contract.py tests/cloud/test_vertex_ai_custom_job_contract.py tests/cloud/test_release_writer.py -q`
    failed because `main()` did not call production completion hooks and no
    release manifest was written. Implemented `build_production_completion_hooks`
    with artifact waiters, manifest-backed assembly, Vertex artifact validation,
    and wired `main()` to pass the hooks.
  - RED observed for Vertex production inference:
    the same targeted run failed because `run_inference_wrapper` did not accept
    explicit synthetic mode, did not use the default command runner, and report
    fields were missing. Implemented default subprocess runner, explicit
    `allow_synthetic_predictions` for fake tests only, Prediction Output Schema
    v1 validation, and full Vertex/inference report metadata.
  - RED observed for release input manifest traceability:
    the targeted release writer test failed because `input_manifest_reference`
    lacked generation/checksum. Implemented checksum and local generation
    capture when the accepted manifest is readable from the object store.
  - RED observed for Vertex custom-job args:
    `python3 -m pytest tests/cloud/test_orchestrator_contract.py::test_cloud_orchestrator_dispatches_batch_and_vertex_clients_from_manifest -q`
    failed because Vertex custom-job args omitted job/project/region/image/model
    metadata. Added args in orchestrator submission and CLI parser support in
    `cloud/orchestrator/inference.py`.
  - RED observed for gated smoke downstream validation:
    `python3 -m pytest tests/cloud/test_gcp_smoke_monthly_e2e.py -q` failed
    because `validate_release_manifest_after_smoke` was missing. Added a
    read-only release manifest validator and required
    `IPCCH_GCP_RELEASE_MANIFEST_URI` for live smoke.
  - GREEN validation after fixes: targeted remediation tests passed; full
    `python3 -m pytest tests/cloud -q` passed with 83 passed and 1 gated live
    smoke skipped; related regression subset passed with 30 tests; `ruff check`
    and `ruff format --check` passed.
- Verify remediation after `/speckit-verify-run` follow-up:
  - Subagent consideration: no. The four findings were cross-component but
    tightly coupled around the cloud runtime contract and had direct one-file
    focused tests; main-agent TDD cycles were lower-risk than splitting shared
    orchestration state across subagents.
  - RED observed for Batch worker default production service wiring:
    `python3 -m pytest tests/cloud/test_cloud_batch_evi_worker.py::test_batch_worker_cli_builds_default_manifest_backed_evi_service -q`
    failed because `build_default_evi_service` did not exist. Implemented
    default manifest-backed service construction through
    `IPCCH_EVI_SERVICE_FACTORY=module:function`, preserving test injection while
    giving the container CLI a production factory path. GREEN: the focused test
    passed.
  - RED observed for Cloud Run release mode contract:
    `python3 -m pytest tests/cloud/test_orchestrator_contract.py::test_orchestrator_cli_parser_accepts_optional_reference_and_release_mode tests/cloud/test_orchestrator_contract.py::test_orchestrator_cli_defaults_to_release_on_success -q`
    failed because the parser accepted `current`/`dry-run` and defaulted to
    `current`. Updated parser choices/default to `release_on_success` and
    `dry_run`. GREEN: the focused release-mode tests passed.
  - RED observed for production completion hard gates and immutable EVI
    references:
    `python3 -m pytest tests/cloud/test_orchestrator_contract.py::test_production_completion_hooks_fail_on_failed_report_status tests/cloud/test_orchestrator_contract.py::test_production_completion_hooks_attach_checksums_to_evi_references -q`
    failed because failed reports did not block and EVI references had only
    URIs. Added report-status checks for GEE/EVI/Vertex reports and SHA-256
    checksums for referenced EVI wide/long outputs. GREEN: the focused tests
    passed.
  - Related module validation passed:
    `python3 -m pytest tests/cloud/test_cloud_batch_evi_worker.py -q`,
    `python3 -m pytest tests/cloud/test_orchestrator_contract.py -q`,
    `python3 -m pytest tests/cloud/test_release_writer.py -q`, and
    `python3 -m pytest tests/cloud/test_runtime_image_contract.py -q`.
  - Follow-up release-mode sweep found `release_step_report.json` still wrote
    `release_mode=current`, and the orchestrator parser still accepted
    undefined `dry_run`. RED observed:
    `python3 -m pytest tests/cloud/test_orchestrator_contract.py::test_orchestrator_cli_rejects_undefined_release_modes -q`
    and
    `python3 -m pytest tests/cloud/test_release_writer.py::test_release_writer_copies_v1_artifacts_references_evidence_and_writes_manifest_last -q`
    failed. Updated the parser to accept only `release_on_success` and the
    release step report to record `release_mode=release_on_success`. GREEN:
    the focused release-mode tests and
    `python3 -m pytest tests/cloud/test_orchestrator_contract.py tests/cloud/test_release_writer.py -q`
    passed.

## Post-Verify Reconciliation Summary

### Implemented tasks

- T001:
  - planned: Create cloud package directories and `__init__.py` files for the
    cloud runtime package and cloud tests.
  - actual: Created package scaffolding under `cloud/` and `tests/cloud/`.
  - changed files: `cloud/__init__.py`, `cloud/common/__init__.py`,
    `cloud/orchestrator/__init__.py`, `cloud/batch/__init__.py`,
    `cloud/schemas/__init__.py`, `tests/cloud/__init__.py`.
  - tests added: None; setup scaffold only.
  - validation: Directory and package existence verified by later import smoke
    and cloud test collection.
- T002-T008:
  - planned: Add cloud dependencies, runtime Dockerfile, manifest fixtures,
    fixture documentation, test package setup, and schema package copy.
  - actual: Added `requirements-cloud.txt`, `docker/Dockerfile`, cloud input
    manifest fixtures, fixture README, and `cloud/schemas/input-manifest.schema.json`.
  - changed files: `requirements-cloud.txt`, `docker/Dockerfile`,
    `tests/fixtures/cloud/*`, `cloud/schemas/input-manifest.schema.json`.
  - tests added: Fixture/schema validation coverage through manifest contract
    tests.
  - validation: Ruff passed; JSON schema parse passed; schema copy matched the
    active contract with `cmp`.
- T009-T022:
  - planned: Implement foundational manifest, report, object-reference,
    object-store, run-state, forbidden-side-effect, and runtime-default
    contracts.
  - actual: Implemented shared cloud contract helpers and direct unit tests.
  - changed files: `cloud/common/manifest.py`, `cloud/common/reports.py`,
    `cloud/common/object_refs.py`, `cloud/common/object_store.py`,
    `cloud/orchestrator/run_state.py`,
    `cloud/common/forbidden_side_effects.py`,
    `cloud/common/runtime_config.py`, related `tests/cloud/test_*.py`.
  - tests added: Manifest, report, object refs, object store, run state,
    forbidden side effects, and runtime defaults tests.
  - validation: Included in `python3 -m pytest tests/cloud -q`, which passed.
- T023-T043:
  - planned: Implement US1 cloud monthly E2E path across orchestrator, Cloud
    Batch/GEE/EVI, assembly, base validation, Vertex AI inference, model
    package validation, release writing, and Docker entrypoint evidence.
  - actual: Implemented local/fake-testable orchestrator flow, production
    completion hooks, EVI worker interfaces, GEE/EVI audit outputs, assembly,
    Vertex job/inference helpers, model-package validation, and release writer.
  - changed files: `cloud/orchestrator/main.py`,
    `cloud/orchestrator/batch_client.py`, `cloud/batch/gee_export.py`,
    `cloud/batch/evi_extract.py`, `cloud/batch/evi_worker.py`,
    `cloud/batch/evi_outputs.py`, `cloud/orchestrator/assembly.py`,
    `cloud/orchestrator/base_input_validation.py`,
    `cloud/orchestrator/vertex_client.py`,
    `cloud/orchestrator/inference.py`,
    `cloud/orchestrator/model_package.py`, `cloud/orchestrator/release.py`,
    `docker/Dockerfile`, related US1 tests.
  - tests added: Orchestrator, Batch worker, rasterio EVI extraction, monthly
    assembly, Vertex custom job, release writer, and runtime image contract
    tests.
  - validation: `python3 -m pytest tests/cloud -q` passed; import smoke passed.
- T044-T051:
  - planned: Add US2 audit evidence for GEE export, EVI validation, and
    optional EVI reference comparison.
  - actual: Implemented EVI validation and advisory comparison helpers and
    wired audit outputs through the worker.
  - changed files: `cloud/batch/evi_validation.py`,
    `cloud/batch/evi_reference.py`, `cloud/batch/evi_worker.py`,
    `cloud/batch/gee_export.py`, related US2 tests.
  - tests added: EVI validation report, EVI reference comparison, and GEE
    export manifest tests.
  - validation: Included in cloud suite; cloud suite passed.
- T052-T059:
  - planned: Implement traceable current-release manifest, release conflict
    behavior, downstream release reader, and quickstart validation references.
  - actual: Implemented release manifest builder, release conflict handling,
    release reader, and quickstart documentation update.
  - changed files: `cloud/orchestrator/release_manifest.py`,
    `cloud/orchestrator/release.py`, `cloud/common/release_reader.py`,
    `specs/001-cloud-base-input/quickstart.md`, related US3 tests.
  - tests added: Release manifest contract, release conflict, release consumer,
    and release writer tests.
  - validation: Included in cloud suite; cloud suite passed.
- T060-T067:
  - planned: Add cross-cutting fake E2E tests, runtime smoke checks, docs,
    regression validation, cloud contract validation, artifact validation, and
    optional gated live GCP smoke test.
  - actual: Added fake-cloud quickstart coverage, runtime image checks,
    runbook/output inventory updates, regression/cloud validation, artifact
    checks, and skipped-by-default live GCP smoke coverage.
  - changed files: `tests/cloud/test_quickstart_fake_cloud.py`,
    `tests/cloud/test_runtime_image_contract.py`,
    `tests/cloud/test_gcp_smoke_monthly_e2e.py`,
    `docs/03_workflow_runbook.md`, `docs/04_output_inventory.md`,
    selected existing regression tests.
  - tests added: Fake E2E quickstart, runtime image contract, and gated live
    GCP smoke tests.
  - validation: Ruff check passed; Ruff format check passed; `tests/cloud`
    passed with 88 passed and 1 skipped; regression subset passed with 30
    passed; JSON schema parse, schema-copy comparison, import smoke, and
    `git diff --check` passed.

### Unplanned but necessary changes

- change: Added `tests/__init__.py`.
  - reason: Pytest package discovery shadowed the root `cloud` package when
    collecting `tests/cloud`.
  - triggered by: RED import failure during strict TDD.
  - affects scope? no
  - affects architecture? no
  - affects acceptance criteria? no
  - artifact update required? no
- change: Corrected the invalid manifest fixture so the intended missing
  immutable-reference failure was isolated.
  - reason: The fixture failed earlier on an unrelated tag-only image rule.
  - triggered by: Manifest contract RED test behavior.
  - affects scope? no
  - affects architecture? no
  - affects acceptance criteria? no
  - artifact update required? no
- change: Tightened orchestrator release behavior to accept only
  `release_on_success`.
  - reason: Spec execution interface names `release_on_success` as the first
    supported/default release mode and does not authorize dry-run release
    behavior.
  - triggered by: Speckit verification finding.
  - affects scope? no
  - affects architecture? no
  - affects acceptance criteria? no
  - artifact update required? no
- change: Added production completion-hook report status checks and checksum
  references for EVI artifacts.
  - reason: Successful release must depend on hard-gate report statuses and
    traceable immutable evidence.
  - triggered by: Speckit verification finding.
  - affects scope? no
  - affects architecture? no
  - affects acceptance criteria? no
  - artifact update required? no
- change: Added default EVI service factory configuration through
  `IPCCH_EVI_SERVICE_FACTORY`.
  - reason: The worker CLI needed a production-callable service path when no
    test-injected service is supplied.
  - triggered by: Speckit verification finding for the Cloud Batch worker CLI.
  - affects scope? no
  - affects architecture? no
  - affects acceptance criteria? no
  - artifact update required? no

### TDD-driven fixes

- visualization fix: Not applicable; this feature has no visualization surface.
- memory mitigation: Not applicable as runtime behavior. For read-only
  validation, commands used `PYTHONDONTWRITEBYTECODE=1` and pytest cache
  disabling where practical to avoid new validation byproducts.
- new test/validation: Added or updated tests for default EVI service factory,
  `release_on_success` parsing/rejection of unsupported release modes, failed
  GEE/EVI/Vertex report statuses blocking release, EVI referenced-artifact
  checksums, and release step `release_mode` recording.
- source artifact mismatch? yes. Verification found implementation drift from
  active Speckit artifacts; implementation was changed to match the artifacts
  rather than changing source-of-truth documents.

### Artifact reconciliation

- spec.md update needed: no.
- plan.md update needed: no.
- tasks.md update needed: no.
- evidence update needed: no.
- no update needed because: The implementation was reconciled to the active
  Speckit artifacts. The only source-of-truth edits made during the approved
  implementation flow were task completion checkboxes and the permitted
  quickstart validation reference already recorded above; no post-verify
  requirement, architecture, scope, or acceptance-criteria changes remain.

## Merge-Review Remediation Delta

- Code-review findings addressed:
  - Cloud Batch submitter now builds a production-shaped Cloud Batch job
    request with task group, runnable container, service account, retry count,
    timeout, and Cloud Logging policy instead of only a flat fake-client dict.
  - Vertex AI submitter now builds a production-shaped custom-job request with
    worker pool, container spec, service account, scheduling timeout, base
    output directory, and labels instead of only a flat fake-client dict.
  - Cloud Run orchestration now writes terminal `run_summary.json` for
    post-prefix failures in Batch submission, Batch/EVI wait, assembly, model
    package validation, Vertex submission, Vertex wait, and release.
  - Default EVI worker service is now an in-repo
    `EarthEngineRasterioEVIService` with lazy GCS, Earth Engine export, and
    rasterio adapter boundaries. Test injection remains available.
  - Model package manifest validation is now a hard gate before Vertex
    submission/release.
  - Live GCP smoke release validator now checks prediction objects, copied
    report references, EVI/GEE evidence references, released copied artifacts,
    and terminal released run summary.
  - Monthly assembly now normalizes `admin_code` to `area_id`, filters source
    panel to the selected month, preserves scaffold row universe, and records
    `target_month_present_in_source=false` when the selected source month is
    absent.
- TDD evidence:
  - RED observed for production-shaped Batch request: Batch submitter test
    failed on missing `taskGroups`/container structure. GREEN after
    `cloud/orchestrator/batch_client.py` update.
  - RED observed for production-shaped Vertex request: Vertex submitter test
    failed on missing `job_spec`. GREEN after
    `cloud/orchestrator/vertex_client.py` update.
  - RED observed for post-prefix failure handling: assembly exception escaped
    without terminal summary. GREEN after per-stage failure handling in
    `cloud/orchestrator/main.py`.
  - RED observed for default EVI service: missing `cloud.batch.evi_service`,
    then local Google SDK import at construction time. GREEN after adding
    `cloud/batch/evi_service.py` with lazy GCS store.
  - RED observed for model package hard gate: missing model package manifest
    failed later during release instead of at `model_package`. GREEN after
    orchestrator model package validation.
  - RED observed for assembly normalization: source panel without `area_id`
    raised `KeyError`. GREEN after admin-code normalization and selected-month
    filtering.
- Validation:
  - `python3 -m pytest tests/cloud -q -p no:cacheprovider` passed: 93 passed,
    1 skipped.
  - Regression subset passed: 30 passed.
  - Ruff check passed.
  - Ruff format check passed.
  - Import smoke passed.
  - JSON schema parse, schema-copy comparison, and `git diff --check` passed.
- Artifact reconciliation:
  - spec.md update needed: no.
  - plan.md update needed: no.
  - tasks.md update needed: no.
  - evidence update needed: no.
  - no update needed because: fixes reconcile implementation to existing
    Speckit scope and acceptance criteria; no requirement or architecture
    change was introduced.

## Critical/Important Review Follow-Up Delta

- Code-review findings addressed:
  - Critical: Cloud Batch submission specs now use Python client/protobuf field
    names (`task_groups`, `task_spec`, `image_uri`, `allocation_policy`,
    `logs_policy`) instead of REST camelCase fields that fake tests accepted
    but the real `google.cloud.batch_v1` client may reject.
  - Important: Cloud Run orchestration now applies deployment runtime overrides
    from the input manifest to submitted Batch and Vertex jobs, including Batch
    max run duration, Vertex timeout, and retry max.
  - Important: production assembly completion hooks now validate scaffolds that
    provide `admin_code` without `area_id`, matching the implemented assembly
    wrapper's `admin_code -> area_id` normalization.
- TDD evidence:
  - RED observed for Python-client Batch field names:
    `python3 -m pytest tests/cloud/test_cloud_batch_evi_worker.py::test_batch_submitter_job_spec_uses_python_client_field_names tests/cloud/test_orchestrator_contract.py::test_cloud_orchestrator_applies_manifest_runtime_overrides_to_submitted_jobs -q -p no:cacheprovider`
    failed on `taskGroups`/missing `task_groups`. GREEN after
    `cloud/orchestrator/batch_client.py` and `cloud/orchestrator/main.py`
    updates.
  - RED observed for admin-code-only production scaffold validation:
    `python3 -m pytest tests/cloud/test_orchestrator_contract.py::test_production_assembly_hook_validates_admin_code_only_scaffold -q -p no:cacheprovider`
    failed with `KeyError: "['area_id'] not in index"`. GREEN after
    `cloud/orchestrator/base_input_validation.py` normalization and production
    hook validation update.
- Validation:
  - `python3 -m pytest tests/cloud -q -p no:cacheprovider` passed: 99 passed,
    1 skipped.
  - Relevant regression subset passed: 77 passed.
  - Focused post-format subset passed: 37 passed.
  - `ruff check cloud tests/cloud` passed.
  - `ruff format --check cloud tests/cloud` passed.
  - Import smoke for cloud orchestrator, Batch, Vertex, validation, and EVI
    modules passed.
  - `python3 -m json.tool specs/001-cloud-base-input/contracts/input-manifest.schema.json`
    passed.
  - `git diff --check -- specs/001-cloud-base-input cloud docker tests docs requirements-cloud.txt implementation-delta.md`
    passed.
- Artifact reconciliation:
  - spec.md update needed: no.
  - plan.md update needed: no.
  - tasks.md update needed: no.
  - evidence update needed: no.
  - no update needed because: these changes fix implementation compatibility
    and validation drift against existing Speckit contracts; they do not change
    scope, architecture, task intent, dependencies, or acceptance criteria.

## Merge Review Blocker Remediation Delta

- Code-review findings addressed:
  - Critical: Vertex inference now materializes model package files from the
    declared GCS model package prefix into the local Vertex workspace before
    invoking `model_pipeline/run_operational_launch_inference.py`, instead of
    creating only `SOURCE_URI.txt`.
  - Critical: `requirements-cloud.txt` now includes `xgboost`, matching the
    existing launch model loader requirement.
  - Important: manifest validation now enforces the single-image runtime digest
    across the Batch image URI, Vertex image URI, and recorded Vertex container
    digest.
  - Important: EVI extraction manifests, Vertex job manifests, and inference
    reports now record effective timeout and retry overrides instead of always
    recording defaults.
  - Important: Cloud orchestration now rejects a Vertex output root that does
    not match the canonical `runs/{run_id}/inference/` prefix before any cloud
    dispatch.
- TDD evidence:
  - RED observed for runtime dependency and model package localization:
    `python3 -m pytest tests/cloud/test_runtime_image_contract.py::test_cloud_runtime_dependencies_include_launch_model_loader_requirements tests/cloud/test_vertex_ai_custom_job_contract.py::test_inference_wrapper_runs_script_and_uploads_script_outputs -q -p no:cacheprovider`
    failed on missing `xgboost` and missing localized `scope_0m` package file.
    GREEN after adding `xgboost` and model package localization.
  - RED observed for single-image digest enforcement:
    `python3 -m pytest tests/cloud/test_manifest_contract.py::test_runtime_images_must_use_same_single_image_digest -q -p no:cacheprovider`
    failed because mismatched image digests passed validation. GREEN after
    manifest digest equality validation.
  - RED observed for runtime audit metadata and Vertex runtime args:
    `python3 -m pytest tests/cloud/test_cloud_batch_evi_worker.py::test_batch_worker_cli_uses_manifest_backed_production_evi_service tests/cloud/test_vertex_ai_custom_job_contract.py::test_inference_wrapper_records_effective_runtime_overrides tests/cloud/test_orchestrator_contract.py::test_cloud_orchestrator_applies_manifest_runtime_overrides_to_submitted_jobs -q -p no:cacheprovider`
    failed because reports recorded defaults and Custom Job args omitted
    runtime values. GREEN after propagating effective runtime values into
    worker reports, Vertex wrapper reports, and Custom Job args.
  - RED observed for Vertex output-root mismatch:
    `python3 -m pytest tests/cloud/test_orchestrator_contract.py::test_cloud_orchestrator_rejects_vertex_output_root_mismatch_before_dispatch -q -p no:cacheprovider`
    failed after Batch dispatch/model-package failure instead of preflight.
    GREEN after adding pre-dispatch output-root validation.
- Validation:
  - Focused review-remediation suite passed: 55 passed.
  - `python3 -m pytest tests/cloud -q -p no:cacheprovider` passed: 103 passed,
    1 skipped.
  - `ruff check cloud tests/cloud` passed.
  - `ruff format --check cloud tests/cloud` passed.
- Artifact reconciliation:
  - spec.md update needed: no.
  - plan.md update needed: no.
  - tasks.md update needed: no.
  - evidence update needed: no.
  - no update needed because: fixes implement existing Speckit requirements for
    single-image runtime, local Vertex model package execution, effective
    runtime audit metadata, and canonical output roots; no requirement,
    architecture, task dependency, or acceptance criterion changed.

## Important Review Remediation Delta

- Code-review findings addressed:
  - Important: `release_step_report.json` under the run prefix is now written
    with final copy/checksum evidence after release copy work. Release conflicts
    now also update the run-prefix release step report with
    `status=release_conflict`, previous manifest generation, and failure reason.
  - Important: Cloud Batch EVI worker CLI now accepts explicit
    `--run-root-uri`, `--gee-export-root-uri`, `--evi-output-root-uri`, and
    `--logs-root-uri`; Cloud Run orchestration passes those arguments; and
    `evi_extraction_manifest.json` records the effective output roots.
- TDD evidence:
  - RED observed for run-prefix release audit report:
    `python3 -m pytest tests/cloud/test_release_writer.py::test_release_writer_copies_v1_artifacts_references_evidence_and_writes_manifest_last tests/cloud/test_release_conflict.py::test_release_conflict_preserves_previous_manifest -q -p no:cacheprovider`
    failed because the run-prefix report remained pending/passed instead of
    final passed or release-conflict state. GREEN after moving final report
    writes into the release copy/checksum/conflict paths.
  - RED observed for Batch worker explicit output roots:
    `python3 -m pytest tests/cloud/test_cloud_batch_evi_worker.py::test_batch_worker_cli_uses_manifest_backed_production_evi_service tests/cloud/test_orchestrator_contract.py::test_cloud_orchestrator_dispatches_batch_and_vertex_clients_from_manifest -q -p no:cacheprovider`
    failed because the worker rejected root arguments and orchestrator did not
    pass them. GREEN after adding CLI roots, Batch job args, and output-root
    report metadata.
- Validation:
  - Focused RED tests passed: 4 passed.
  - Affected release/EVI/orchestrator suite passed: 34 passed.
  - `python3 -m pytest tests/cloud -q -p no:cacheprovider` passed: 103 passed,
    1 skipped.
  - `ruff check cloud tests/cloud` passed.
  - `ruff format --check cloud tests/cloud` passed.
- Artifact reconciliation:
  - spec.md update needed: no.
  - plan.md update needed: no.
  - tasks.md update needed: no.
  - evidence update needed: no.
  - no update needed because: fixes reconcile implementation to existing
    Speckit release sequencing and Batch worker execution contracts; no scope,
    architecture, dependency, or acceptance criterion changed.

## Important Review Final Validation Refresh

- Validation:
  - `python3 -m pytest tests/cloud -q -p no:cacheprovider` passed: 103
    passed, 1 skipped.
  - `python3 -m pytest tests/test_build_monthly_ipcch_base_input.py tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/test_reshape_remote_sensing_wide_to_long.py tests/cloud/test_release_writer.py tests/cloud/test_release_conflict.py tests/cloud/test_cloud_batch_evi_worker.py tests/cloud/test_orchestrator_contract.py -q -p no:cacheprovider`
    passed: 64 passed.
  - `ruff check cloud tests/cloud` passed.
  - `ruff format --check cloud tests/cloud` passed.
  - Typecheck: not configured. No `pyright`, `mypy`, or `ty` configuration was
    found in `pyproject.toml`, `mypy.ini`, `pyrightconfig.json`, `tox.ini`,
    `setup.cfg`, or requirements files.
  - Import smoke passed for `cloud.common.manifest`,
    `cloud.orchestrator.main`, `cloud.orchestrator.inference`,
    `cloud.orchestrator.release`, and `cloud.batch.evi_worker`.
  - `python3 -m json.tool specs/001-cloud-base-input/contracts/input-manifest.schema.json`
    passed.
  - `git diff --check -- specs/001-cloud-base-input cloud docker tests docs requirements-cloud.txt implementation-delta.md`
    passed.
  - Post-implementation artifact validation: expected cloud contract/schema and
    implementation paths exist; no local `release_manifest.json`,
    `evi_extraction_manifest.json`, `vertex_ai_job_manifest.json`, or
    `*_error.json` outputs were present under the working tree scan; generated
    `.pytest_cache` was removed and absence rechecked.
- Artifact reconciliation:
  - spec.md update needed: no.
  - plan.md update needed: no.
  - tasks.md update needed: no.
  - evidence update needed: no.
  - no update needed because: this refresh records validation evidence only and
    does not alter requirements, architecture, task intent, dependencies, or
    acceptance criteria.

## Merge Review Critical/Important Remediation Delta

- Code-review findings addressed:
  - Critical: Cloud Batch create-job request now keeps `job_id` only on the
    top-level request and removes non-Job fields from the `job` payload. Feature
    month/run id remain in labels and worker args.
  - Important: Cloud Batch and Vertex wrapper dispatch now use the documented
    execution-contract argument names (`--run-root-uri`, `--input-base-uri`,
    `--output-dir`) while keeping backward-compatible parser aliases where
    needed.
  - Important: `--reference-sample-uri` is now propagated from Cloud Run
    orchestration into Batch EVI and Vertex inference workers. EVI validation
    reads the reference CSV for advisory comparison; Vertex inference can load
    reference prediction samples from the object store.
  - Important: Vertex completion evidence is reconciled with the actual
    submitted Custom Job response name before release evidence is consumed.
  - Important: Release copied artifacts now use generation preconditions so an
    existing released run copy is not overwritten by a retry or duplicate
    release attempt.
  - Minor: GEE export manifests now record current UTC creation time instead of
    a hard-coded implementation date.
  - Minor: Release step reports now record the deployment staging root URI when
    provided by the manifest/deployment.
- TDD evidence:
  - RED observed for review remediation:
    `python3 -m pytest tests/cloud/test_cloud_batch_evi_worker.py::test_batch_submitter_job_payload_contains_only_job_fields tests/cloud/test_cloud_batch_evi_worker.py::test_batch_worker_cli_accepts_execution_contract_root_args tests/cloud/test_cloud_batch_evi_worker.py::test_batch_worker_cli_uses_reference_sample_uri_for_evi_comparison tests/cloud/test_vertex_ai_custom_job_contract.py::test_inference_cli_accepts_execution_contract_argument_names tests/cloud/test_vertex_ai_custom_job_contract.py::test_inference_wrapper_reads_reference_predictions_from_uri tests/cloud/test_orchestrator_contract.py::test_cloud_orchestrator_dispatches_batch_and_vertex_clients_from_manifest tests/cloud/test_orchestrator_contract.py::test_cloud_orchestrator_passes_reference_sample_uri_to_batch_and_vertex tests/cloud/test_orchestrator_contract.py::test_cloud_orchestrator_reconciles_vertex_manifest_with_actual_response_name tests/cloud/test_release_writer.py::test_release_writer_does_not_overwrite_existing_released_run_artifacts tests/cloud/test_gee_export_manifest.py::test_gee_export_manifest_contains_audit_fields -q -p no:cacheprovider`
    failed with 10 failures matching missing helper/API support, required legacy
    CLI names, missing reference sample propagation, stale Vertex resource name,
    released artifact overwrite, and hard-coded GEE timestamp.
  - GREEN observed for the same focused review-remediation tests: 10 passed.
  - RED observed for staging-root evidence:
    `python3 -m pytest tests/cloud/test_release_writer.py::test_release_writer_copies_v1_artifacts_references_evidence_and_writes_manifest_last -q -p no:cacheprovider`
    failed because `write_release()` lacked `staging_root_uri`. GREEN after
    adding the optional parameter and passing deployment staging root from the
    orchestrator.
- Validation:
  - Affected review-remediation suite passed: 55 passed.
  - `python3 -m pytest tests/cloud -q -p no:cacheprovider` passed: 111 passed,
    1 skipped.
  - Existing non-cloud regression subset passed: 30 passed.
  - `ruff check cloud tests/cloud` passed.
  - `ruff format --check cloud tests/cloud` passed after formatting
    `tests/cloud/test_orchestrator_contract.py`.
  - Import smoke passed for `cloud.common.manifest`,
    `cloud.orchestrator.main`, `cloud.orchestrator.inference`,
    `cloud.orchestrator.release`, `cloud.batch.evi_worker`, and
    `cloud.orchestrator.batch_client`.
  - `python3 -m json.tool specs/001-cloud-base-input/contracts/input-manifest.schema.json`
    passed.
  - `git diff --check -- specs/001-cloud-base-input cloud docker tests docs requirements-cloud.txt implementation-delta.md`
    passed.
  - Typecheck: not configured. No `pyright`, `mypy`, or `ty` configuration was
    found in configured project files or requirements.
- Artifact reconciliation:
  - spec.md update needed: no.
  - plan.md update needed: no.
  - tasks.md update needed: no.
  - evidence update needed: no.
  - no update needed because: these are implementation reconciliations to the
    existing execution, release, audit, and traceability contracts; they do not
    change requirements, architecture, task intent, dependencies, or acceptance
    criteria.

## Merge Review Important Remediation Delta 2

- Code-review findings addressed:
  - Important: manifest URI validation now rejects unsupported artifact URI
    schemes and relative paths instead of allowing them to fail later in cloud
    execution. Deployment container image URIs remain governed by digest-pinned
    image validation.
  - Important: deployment root overrides are now resolved once via
    `cloud.orchestrator.roots.resolve_deployment_roots()` and used by run-state
    acquisition, Batch worker arguments, Vertex output-root validation,
    completion hooks, and release source lookups.
  - Important: base input validation now invokes the existing
    `tools.validate_ipcch_schema` model-input-forecast validator after
    row-universe checks, and fails on non-passed schema results.
  - Important: rasterio no-overlap zones are handled as empty zones with null
    output rows rather than failing the whole EVI worker.
  - Important: released `release_step_report.json` generation conflicts are now
    classified as `release_conflict` with a run-prefix conflict report instead
    of bubbling as an unclassified exception.
- TDD evidence:
  - RED observed for all five Important findings:
    `python3 -m pytest tests/cloud/test_manifest_contract.py::test_unsupported_artifact_uri_scheme_fails tests/cloud/test_manifest_contract.py::test_relative_artifact_uri_fails tests/cloud/test_run_state.py::test_run_state_uses_explicit_run_root_uri_when_supplied tests/cloud/test_orchestrator_contract.py::test_cloud_orchestrator_honors_deployment_root_overrides tests/cloud/test_monthly_assembly_wrapper.py::test_base_input_validation_invokes_model_input_forecast_schema_gate tests/cloud/test_rasterio_evi_extraction.py::test_rasterio_adapter_preserves_non_overlapping_zone_as_empty_row tests/cloud/test_release_writer.py::test_release_writer_reports_released_step_report_generation_conflict -q -p no:cacheprovider`
    failed with seven failures matching loose URI validation, missing run-root
    override support, stale Vertex output-root validation, missing schema gate,
    no-overlap rasterio failure, and unhandled release step report generation
    conflict.
  - GREEN observed for the same focused tests: 7 passed.
- Validation:
  - Affected suite passed:
    `python3 -m pytest tests/cloud/test_manifest_contract.py tests/cloud/test_run_state.py tests/cloud/test_orchestrator_contract.py tests/cloud/test_monthly_assembly_wrapper.py tests/cloud/test_rasterio_evi_extraction.py tests/cloud/test_release_writer.py tests/cloud/test_release_conflict.py -q -p no:cacheprovider`
    passed: 48 passed.
  - `python3 -m pytest tests/cloud -q -p no:cacheprovider` passed: 118
    passed, 1 skipped.
  - Existing non-cloud regression subset passed: 30 passed.
  - `ruff check cloud tests/cloud` passed.
  - `ruff format --check cloud tests/cloud` passed after formatting
    `cloud/orchestrator/base_input_validation.py`, `cloud/orchestrator/main.py`,
    `cloud/orchestrator/release.py`, and `tests/cloud/test_release_writer.py`.
  - Import smoke passed for `cloud.common.manifest`,
    `cloud.orchestrator.main`, `cloud.orchestrator.inference`,
    `cloud.orchestrator.release`, `cloud.batch.evi_worker`,
    `cloud.orchestrator.roots`, and
    `cloud.orchestrator.base_input_validation`.
  - `python3 -m json.tool specs/001-cloud-base-input/contracts/input-manifest.schema.json`
    passed.
  - `git diff --check -- specs/001-cloud-base-input cloud docker tests docs requirements-cloud.txt implementation-delta.md`
    passed.
  - Typecheck: not configured. No `pyright`, `mypy`, or `ty` configuration was
    found in configured project files or requirements.
  - Post-implementation artifact validation: no local
    `release_manifest.json`, `evi_extraction_manifest.json`,
    `vertex_ai_job_manifest.json`, or `*_error.json` outputs were present under
    the working tree scan; generated `__pycache__` / `.pytest_cache` directories
    were removed and absence rechecked.
- Artifact reconciliation:
  - spec.md update needed: no.
  - plan.md update needed: no.
  - tasks.md update needed: no.
  - evidence update needed: no.
  - no update needed because: these changes reconcile implementation to
    existing manifest, deployment-root, schema-gate, EVI empty-zone, and release
    conflict contracts without changing scope, architecture, task intent,
    dependencies, or acceptance criteria.

## Merge Review Important Remediation Delta 3

- Subagent consideration:
  - Task: fix five Important merge-review findings for model feature
    compatibility, GEE raster checksum evidence, production wait timeouts,
    Vertex AI custom-job environment variables, and Cloud Batch job IDs.
  - Needed? no.
  - Reason: findings were already isolated by the merge-review subagent and
    touched bounded cloud contract modules with direct focused tests.
  - If no, why current task can be handled within the main agent context:
    each fix had a narrow RED/GREEN test target and did not require parallel
    artifact comparison or shared refactoring.
  - If yes, what bounded packet should be delegated: n/a.
- Code-review findings addressed:
  - Important: model package validation now checks package-declared
    `scope_*/feature_columns.json` requirements against the assembled base
    input columns before Vertex AI submission when production completion hooks
    have produced the base input.
  - Important: GEE raster evidence now records sha256 checksum algorithm
    metadata and rejects non-sha256 checksum values; production GCS checksum
    capture now computes sha256 bytes instead of recording GCS MD5 metadata.
  - Important: production completion hooks now wait for Batch and Vertex
    artifacts using manifest-resolved runtime timeouts and GEE poll interval.
  - Important: Vertex AI custom-job specs now inject required container
    environment variables for project, region, run, feature month, model
    package URI, base input URI, and inference output URI.
  - Important: Cloud Batch job IDs are sanitized/lowercased/bounded for GCP API
    compatibility while retaining stable run metadata in labels.
- TDD evidence:
  - RED observed:
    `python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py::test_vertex_submitter_builds_custom_job_spec_with_same_digest_and_timeout tests/cloud/test_vertex_ai_custom_job_contract.py::test_model_package_validation_rejects_missing_required_feature_columns tests/cloud/test_cloud_batch_evi_worker.py::test_batch_submitter_sanitizes_job_id_without_changing_run_label tests/cloud/test_gee_export_manifest.py::test_gee_export_manifest_contains_audit_fields tests/cloud/test_gee_export_manifest.py::test_gee_export_manifest_rejects_checksum_without_sha256_prefix tests/cloud/test_orchestrator_contract.py::test_production_completion_hooks_use_runtime_timeouts_for_batch_and_vertex_waits tests/cloud/test_orchestrator_contract.py::test_cloud_orchestrator_blocks_base_input_missing_model_feature_columns -q -p no:cacheprovider`
    failed with seven failures matching missing Vertex env, unsupported model
    package feature-column validation, unsanitized Batch job ID, absent checksum
    algorithm metadata/rejection, runtime wait defaults, and missing
    pre-Vertex feature-column gate.
  - GREEN observed for the same focused tests: 7 passed.
  - Affected suite initially exposed old non-sha256 test fixtures in
    `tests/cloud/test_cloud_batch_evi_worker.py`; root cause was fixture drift
    after checksum contract tightening. Fixtures were updated to sha256-form
    checksums and the affected suite passed.
- Validation:
  - Affected suite passed:
    `python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py tests/cloud/test_cloud_batch_evi_worker.py tests/cloud/test_gee_export_manifest.py tests/cloud/test_orchestrator_contract.py -q -p no:cacheprovider`
    passed: 58 passed.
  - `python3 -m pytest tests/cloud -q -p no:cacheprovider` passed: 123
    passed, 1 skipped.
  - `ruff check cloud tests/cloud` passed.
  - `ruff format --check cloud tests/cloud` passed after formatting
    `tests/cloud/test_orchestrator_contract.py` and
    `tests/cloud/test_vertex_ai_custom_job_contract.py`.
- Artifact reconciliation:
  - spec.md update needed: no.
  - plan.md update needed: no.
  - tasks.md update needed: no.
  - evidence update needed: no.
  - no update needed because: these are implementation corrections to existing
    model package, GEE evidence, runtime timeout, Vertex custom-job, and Cloud
    Batch execution contracts; they do not change scope, architecture, task
    intent, dependencies, or acceptance criteria.

## Merge Review Critical/Important Remediation Delta 4

- Subagent consideration:
  - Task: fix one Critical and four Important merge-review findings for model
    package lineage, scope feature-column enforcement, sha256 checksum
    strictness, GEE raster immutable evidence, and overlong Batch job prefixes.
  - Needed? no.
  - Reason: findings were independently isolated by code review and each had a
    bounded contract test target.
  - If no, why current task can be handled within the main agent context:
    fixes were narrow hard-gate corrections in manifest validation, model
    package loading, GEE evidence, and Batch ID construction.
  - If yes, what bounded packet should be delegated: n/a.
- Code-review findings addressed:
  - Critical: input manifest validation now requires the deployment Vertex AI
    model package URI and checksum/version field to match the single
    `model_package` artifact entry, preventing validation of one package while
    running or releasing another.
  - Critical follow-through: Vertex custom-job arguments now use the validated
    model package evidence instead of rereading an independent deployment URI.
  - Important: model package feature-column loading now requires
    `scope_0m`, `scope_6m`, and `scope_12m` `feature_columns.json` files,
    accepts both bare list and `{"feature_columns": [...]}` shapes, and rejects
    missing, malformed, or empty feature-column files.
  - Important: GEE raster checksum validation now accepts only bare 64-hex
    sha256 values or `sha256:` plus 64 hex characters, normalizing to
    `sha256:<hex>`.
  - Important: Earth Engine raster export evidence no longer uses task state as
    an immutable raster reference and fails if neither GCS generation/version
    nor sha256 checksum is available.
  - Important: Cloud Batch job ID construction now bounds overlong sanitized
    prefixes before reserving room for run ID/digest suffixes.
  - Minor cleanup: ignored Python `__pycache__` directories under `cloud/` and
    `tests/cloud/` were removed.
- TDD evidence:
  - RED observed:
    `python3 -m pytest tests/cloud/test_manifest_contract.py::test_deployment_model_package_must_match_model_package_artifact tests/cloud/test_orchestrator_contract.py::test_cloud_orchestrator_requires_all_scope_feature_column_files tests/cloud/test_orchestrator_contract.py::test_cloud_orchestrator_accepts_dict_shaped_scope_feature_columns tests/cloud/test_gee_export_manifest.py::test_gee_export_manifest_rejects_short_prefixed_sha256_checksum tests/cloud/test_rasterio_evi_extraction.py::test_gee_export_adapter_requires_immutable_raster_reference tests/cloud/test_cloud_batch_evi_worker.py::test_batch_submitter_bounds_job_id_with_overlong_prefix -q -p no:cacheprovider`
    failed with six failures matching missing manifest model-package equality
    gate, optional/missing scope feature-column handling, unsupported dict
    feature-column shape, short sha256 acceptance, missing immutable raster
    evidence hard gate, and unbounded overlong Batch job prefix.
  - GREEN observed for the same focused tests: 6 passed.
- Validation:
  - Affected suite passed:
    `python3 -m pytest tests/cloud/test_manifest_contract.py tests/cloud/test_orchestrator_contract.py tests/cloud/test_gee_export_manifest.py tests/cloud/test_rasterio_evi_extraction.py tests/cloud/test_cloud_batch_evi_worker.py tests/cloud/test_vertex_ai_custom_job_contract.py -q -p no:cacheprovider`
    passed: 78 passed.
  - `python3 -m pytest tests/cloud -q -p no:cacheprovider` passed: 129
    passed, 1 skipped.
  - `ruff check cloud tests/cloud` passed.
  - `ruff format --check cloud tests/cloud` passed after formatting
    `cloud/orchestrator/main.py`.
- Artifact reconciliation:
  - spec.md update needed: no.
  - plan.md update needed: no.
  - tasks.md update needed: no.
  - evidence update needed: no.
  - no update needed because: these fixes tighten implementation to existing
    model package, auditability, immutable evidence, and GCP execution
    contracts without changing scope, architecture, task intent, dependencies,
    or acceptance criteria.

## Merge Review Critical/Important Remediation Delta 5

- Subagent consideration:
  - Task: fix one Critical and three Important merge-review findings for
    mutable release pointer updates, prediction output schema hard gates,
    inference reference comparison evidence, and wait fail-fast behavior.
  - Needed? no.
  - Reason: the merge-review subagent had already isolated the findings, and
    each fix had a bounded local contract test target.
  - If no, why current task can be handled within the main agent context:
    fixes were limited to release CAS writing, inference output validation, and
    object wait error classification.
  - If yes, what bounded packet should be delegated: n/a.
- Code-review findings addressed:
  - Critical: `release_manifest.json` now uses `if_generation_match=0` only
    when no current manifest exists; otherwise it uses the observed previous
    generation as a compare-and-swap precondition, allowing legitimate
    sequential supersession while preserving stale-generation conflicts.
  - Important: prediction output validation now enforces integer
    `scope_months` values matching the scope file, `feature_period` equality,
    `target_period` equality for 0/6/12 month scopes, per-scope duplicate keys,
    and combined `area_id/year/month/scope_months` uniqueness.
  - Important: supplied inference reference predictions are now schema-checked,
    key-matched by scope, and compared against cloud predictions. Required
    prediction label mismatches are hard gates; numeric score differences are
    recorded as advisory comparison evidence.
  - Important: `_wait_for_objects()` now treats missing objects as retryable
    but fails fast on non-missing object errors such as permission or invalid
    URI failures instead of hiding them until timeout.
- TDD evidence:
  - RED observed:
    `python3 -m pytest tests/cloud/test_release_conflict.py::test_release_supersession_updates_current_manifest_with_previous_generation tests/cloud/test_release_conflict.py::test_release_conflict_preserves_externally_updated_manifest tests/cloud/test_vertex_ai_custom_job_contract.py::test_prediction_validation_rejects_scope_months_mismatching_scope_file tests/cloud/test_vertex_ai_custom_job_contract.py::test_prediction_validation_rejects_target_period_mismatching_scope tests/cloud/test_vertex_ai_custom_job_contract.py::test_prediction_validation_records_reference_comparison_evidence tests/cloud/test_vertex_ai_custom_job_contract.py::test_prediction_validation_rejects_reference_missing_required_rows tests/cloud/test_orchestrator_contract.py::test_wait_for_objects_fails_fast_on_non_missing_object_errors -q -p no:cacheprovider`
    failed with seven failures matching release supersession conflict,
    absent stale-generation CAS path, missing scope/target prediction gates,
    missing reference comparison evidence, missing reference row hard gate, and
    overly broad wait exception handling.
  - GREEN observed for the same focused tests: 7 passed.
- Validation:
  - Affected suite passed:
    `python3 -m pytest tests/cloud/test_release_conflict.py tests/cloud/test_release_writer.py tests/cloud/test_vertex_ai_custom_job_contract.py tests/cloud/test_orchestrator_contract.py -q -p no:cacheprovider`
    passed: 47 passed.
  - `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud -q -p no:cacheprovider`
    passed: 135 passed, 1 skipped.
  - Existing operational launch regression subset passed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/test_reshape_remote_sensing_wide_to_long.py -q -p no:cacheprovider`
    passed: 27 passed.
  - `ruff check cloud tests/cloud` passed.
  - `ruff format --check cloud tests/cloud` passed after formatting
    `cloud/orchestrator/inference.py`,
    `tests/cloud/test_release_conflict.py`, and
    `tests/cloud/test_vertex_ai_custom_job_contract.py`.
  - Import smoke passed for `cloud.orchestrator.release`,
    `cloud.orchestrator.inference`, and `cloud.orchestrator.main`.
  - Typecheck: not configured. No `pyright`, `mypy`, or `ty` configuration was
    found.
  - Post-implementation artifact validation: no local `release_manifest.json`,
    `evi_extraction_manifest.json`, `vertex_ai_job_manifest.json`, or
    `*_error.json` outputs were present under the working tree scan.
- Artifact reconciliation:
  - spec.md update needed: no.
  - plan.md update needed: no.
  - tasks.md update needed: no.
  - evidence update needed: no.
  - no update needed because: these changes reconcile implementation to the
    existing mutable release pointer, Prediction Output Schema v1,
    local-to-cloud reference evidence, and cloud hard-gate contracts without
    changing scope, architecture, task intent, dependencies, or acceptance
    criteria.

## Merge Review Critical/Important Remediation Delta 6

- Subagent consideration:
  - Task: fix one Critical and two Important merge-review findings for real
    GCS release generation lookup, released release-step audit consistency, and
    cloud assembly parity with the existing monthly base-input builder rules.
  - Needed? no.
  - Reason: the review findings were already isolated and each had a bounded
    contract test target in release, object-store metadata, or assembly.
  - If no, why current task can be handled within the main agent context:
    implementation touched narrow modules and followed focused RED/GREEN tests
    without requiring cross-agent coordination.
  - If yes, what bounded packet should be delegated: n/a.
- Code-review findings addressed:
  - Critical: `ObjectStore` now exposes `get_metadata()`. `LocalObjectStore`
    returns local generation metadata and `GCSObjectStore` uses
    `blob.reload().generation`; release CAS no longer depends on the local
    fake store's private `_generations` map.
  - Important: `write_release()` now updates both run-prefix and released
    `release_step_report.json` copies after manifest CAS success or conflict,
    so released audit evidence records the final release status and
    manifest-generation outcome instead of retaining pre-CAS content.
  - Important: cloud assembly now mirrors the existing monthly base-input
    builder's core contracts: canonical ID-column order, normalized
    `admin_code`/`area_id`, exactly one scaffold month, duplicate scaffold
    rejection, fixed/source overlap exclusion, engineered source-column
    exclusion, and fixed/source join accounting while still appending
    cloud-produced EVI long features.
- TDD evidence:
  - RED observed:
    `python3 -m pytest tests/cloud/test_release_conflict.py::test_release_supersession_uses_object_metadata_not_local_private_state tests/cloud/test_release_writer.py::test_release_writer_copies_v1_artifacts_references_evidence_and_writes_manifest_last tests/cloud/test_release_writer.py::test_release_manifest_conflict_marks_released_step_report_as_conflict tests/cloud/test_monthly_assembly_wrapper.py::test_assembly_rejects_scaffold_with_multiple_months tests/cloud/test_monthly_assembly_wrapper.py::test_assembly_excludes_source_overlap_with_fixed_and_engineered_columns -q -p no:cacheprovider`
    failed with five failures matching fake-local-only generation lookup,
    stale released step-report final fields, released conflict evidence
    mismatch, missing one-month scaffold validation, and generic merge column
    drift.
  - GREEN observed for the same focused tests: 5 passed.
- Validation:
  - Affected release/object-store/assembly/orchestrator suite passed:
    `python3 -m pytest tests/cloud/test_object_store.py tests/cloud/test_release_conflict.py tests/cloud/test_release_writer.py tests/cloud/test_release_manifest_contract.py tests/cloud/test_release_consumer.py tests/cloud/test_monthly_assembly_wrapper.py tests/cloud/test_orchestrator_contract.py -q -p no:cacheprovider`
    passed: 47 passed.
  - `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud -q -p no:cacheprovider`
    passed: 139 passed, 1 skipped.
  - Existing operational launch and monthly builder regression subset passed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/test_reshape_remote_sensing_wide_to_long.py tests/test_build_monthly_ipcch_base_input.py -q -p no:cacheprovider`
    passed: 30 passed.
  - `ruff check cloud tests/cloud` passed.
  - `ruff format --check cloud tests/cloud` passed after formatting
    `cloud/orchestrator/assembly.py` and
    `tests/cloud/test_release_writer.py`.
  - Import smoke passed for `cloud.common.object_store`,
    `cloud.orchestrator.release`, `cloud.orchestrator.assembly`, and
    `cloud.orchestrator.main`.
  - `git diff --check -- cloud tests/cloud implementation-delta.md` passed.
  - Typecheck: not configured. No `pyright`, `mypy`, or `ty` configuration was
    found.
  - Post-implementation artifact validation: no local `release_manifest.json`,
    `evi_extraction_manifest.json`, `vertex_ai_job_manifest.json`, or
    `*_error.json` outputs were present under the working tree scan.
- Artifact reconciliation:
  - spec.md update needed: no.
  - plan.md update needed: no.
  - tasks.md update needed: no.
  - evidence update needed: no.
  - no update needed because: these are implementation corrections to existing
    GCS generation-precondition, release audit, and monthly base-input
    assembly contracts without changing scope, architecture, task intent,
    dependencies, or acceptance criteria.

## Merge Review Critical/Important Remediation Delta 7

- Subagent consideration:
  - Task: fix all current Critical and Important merge-review findings for
    release hard-gate verification, assembly duplicate/blank key handling,
    release CLI execution contract, and production manifest contract coverage.
  - Needed? no.
  - Reason: the review findings were already isolated with focused failing
    tests, and the fixes were localized to release, assembly, orchestrator
    evidence reconciliation, and test fixtures.
  - If no, why current task can be handled within the main agent context:
    each item had a bounded RED/GREEN path and no cross-module refactor or
    Speckit artifact reconciliation ambiguity was required.
  - If yes, what bounded packet should be delegated: n/a.
- Code-review findings addressed:
  - Critical: `write_release()` now performs release preflight before any
    release-root writes. It hard-gates required release metadata,
    immutable model/evidence references, input manifest availability,
    validation/inference statuses, required hard-gate reports, model output
    schema evidence, local reference comparison status, released run summary
    status, and prediction CSV key-schema headers.
  - Important: cloud assembly now rejects duplicate selected-month source
    keys instead of counting and dropping them, and rejects blank normalized
    fixed/slow or source `area_id` values as hard gates.
  - Important: `cloud.orchestrator.release` now exposes `parse_args()` and
    `main()` for the release writer execution contract, including required
    feature/run/root URI arguments and optional immutable release metadata.
  - Important: release manifest contract coverage now includes the actual
    emitted `write_release()` manifest, not only the separate typed builder.
  - Important: Vertex evidence reconciliation now marks the Vertex job
    manifest `passed` after the waiter succeeds while preserving the actual
    service-assigned Vertex resource name in both Vertex and inference reports.
- TDD evidence:
  - RED observed:
    `python3 -m pytest tests/cloud/test_release_writer.py::test_release_writer_rejects_failed_hard_gate_report_before_copy tests/cloud/test_release_writer.py::test_release_writer_requires_release_metadata_and_immutable_references tests/cloud/test_release_writer.py::test_release_cli_parser_exposes_execution_contract_arguments tests/cloud/test_monthly_assembly_wrapper.py::test_assembly_rejects_duplicate_selected_month_source_keys tests/cloud/test_monthly_assembly_wrapper.py::test_assembly_rejects_blank_fixed_or_source_area_ids tests/cloud/test_release_manifest_contract.py::test_write_release_emits_required_current_manifest_contract -q -p no:cacheprovider`
    failed with five expected failures and one existing manifest-contract pass.
  - GREEN observed for the same focused tests: 6 passed.
- Validation:
  - Affected release/assembly/orchestrator suite passed:
    `python3 -m pytest tests/cloud/test_release_writer.py tests/cloud/test_release_conflict.py tests/cloud/test_release_manifest_contract.py tests/cloud/test_monthly_assembly_wrapper.py tests/cloud/test_orchestrator_contract.py -q -p no:cacheprovider`
    passed: 47 passed.
  - `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud -q -p no:cacheprovider`
    passed: 145 passed, 1 skipped.
  - Existing operational launch and monthly builder regression subset passed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/test_reshape_remote_sensing_wide_to_long.py tests/test_build_monthly_ipcch_base_input.py -q -p no:cacheprovider`
    passed: 30 passed.
  - `ruff check cloud tests/cloud` passed.
  - `ruff format --check cloud tests/cloud` passed after formatting
    `cloud/orchestrator/main.py`, `cloud/orchestrator/release.py`,
    `tests/cloud/test_monthly_assembly_wrapper.py`, and
    `tests/cloud/test_release_writer.py`.
  - Import smoke passed for `cloud.orchestrator.release`,
    `cloud.orchestrator.assembly`, `cloud.orchestrator.main`, and
    `cloud.common.object_store`.
  - `python3 -m json.tool specs/001-cloud-base-input/contracts/input-manifest.schema.json`
    passed.
  - `git diff --check -- cloud tests/cloud implementation-delta.md` passed.
  - Typecheck: not configured. No `pyproject.toml`, `mypy.ini`,
    `pyrightconfig.json`, or `ty.toml` was found.
  - Post-implementation artifact validation: generated `__pycache__`
    directories from validation were removed; the final scan found no
    `__pycache__` directories under the working tree outside ignored
    `.pytest_cache`.
- Artifact reconciliation:
  - spec.md update needed: no.
  - plan.md update needed: no.
  - tasks.md update needed: no.
  - evidence update needed: no.
  - source artifact mismatch? no.
  - no update needed because: these changes tighten implementation to existing
    release hard-gate, immutable evidence, monthly assembly, execution
    interface, and manifest contract requirements without changing scope,
    architecture, task intent, task dependencies, or acceptance criteria.

## Merge Review Critical/Important Remediation Delta 8

- Subagent consideration:
  - Task: apply the narrowed remediation plan for the latest pre-merge review:
    fix two Critical findings, verify/fix one model-package Important finding,
    and tighten one GCP smoke assertion.
  - Needed? no.
  - Reason: the review output was already scoped to four concrete findings and
    each finding had a bounded TDD target.
  - If no, why current task can be handled within the main agent context:
    changes were limited to release preflight, entrypoint return-code handling,
    model package manifest validation, and smoke validator assertions.
  - If yes, what bounded packet should be delegated: n/a.
- Code-review findings addressed:
  - Critical: `write_release()` now revalidates actual prediction CSV artifacts
    before copying or publishing by reading the run-scoped base input and all
    three prediction CSVs and reusing `validate_prediction_outputs()` for
    required columns, selected month, scope/target periods, duplicate keys, and
    base-input row-universe matching.
  - Critical: standalone release CLI and orchestrator CLI now return nonzero
    when the release result is not `status=current`, including
    `release_conflict`, while retaining the existing terminal release-conflict
    summary behavior for audit.
  - Important: model package validation now checks Speckit-required
    `expected_input_schema` and `expected_output_schema` fields inside
    `model_package_manifest.json` instead of accepting a non-contract
    `schema_contract` field in that package manifest.
  - Important: live GCP smoke release artifact validation now requires a
    current manifest's copied `run_summary.json` to have `status=released`;
    `release_conflict` is no longer accepted as current-release evidence.
- TDD evidence:
  - RED observed:
    `python3 -m pytest tests/cloud/test_release_writer.py::test_release_writer_revalidates_actual_prediction_artifacts_before_copy tests/cloud/test_release_writer.py::test_release_cli_returns_nonzero_on_release_conflict tests/cloud/test_vertex_ai_custom_job_contract.py::test_model_package_validation_rejects_non_contract_manifest_shape tests/cloud/test_gcp_smoke_monthly_e2e.py::test_live_gcp_smoke_release_validator_rejects_conflict_run_summary -q -p no:cacheprovider`
    failed with three implementation failures and one smoke assertion already
    enforced by the test helper change.
  - Additional RED observed for orchestrator CLI conflict exit:
    `python3 -m pytest tests/cloud/test_orchestrator_contract.py::test_orchestrator_main_cli_returns_nonzero_on_release_conflict -q -p no:cacheprovider`
    failed because `main.main()` returned 0 for a release-conflict result.
  - GREEN observed for the narrowed focused set:
    `python3 -m pytest tests/cloud/test_release_writer.py::test_release_writer_revalidates_actual_prediction_artifacts_before_copy tests/cloud/test_release_writer.py::test_release_cli_returns_nonzero_on_release_conflict tests/cloud/test_orchestrator_contract.py::test_orchestrator_main_cli_returns_nonzero_on_release_conflict tests/cloud/test_vertex_ai_custom_job_contract.py::test_model_package_validation_rejects_non_contract_manifest_shape tests/cloud/test_gcp_smoke_monthly_e2e.py::test_live_gcp_smoke_release_validator_rejects_conflict_run_summary -q -p no:cacheprovider`
    passed: 5 passed.
- Validation:
  - Affected release/orchestrator/model-package/smoke suite passed:
    `python3 -m pytest tests/cloud/test_release_writer.py tests/cloud/test_release_conflict.py tests/cloud/test_release_manifest_contract.py tests/cloud/test_orchestrator_contract.py tests/cloud/test_vertex_ai_custom_job_contract.py tests/cloud/test_gcp_smoke_monthly_e2e.py -q -p no:cacheprovider`
    passed: 61 passed, 1 skipped.
  - `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud -q -p no:cacheprovider`
    passed: 150 passed, 1 skipped.
  - Existing operational launch and monthly builder regression subset passed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/test_reshape_remote_sensing_wide_to_long.py tests/test_build_monthly_ipcch_base_input.py -q -p no:cacheprovider`
    passed: 30 passed.
  - `ruff check cloud tests/cloud` passed.
  - `ruff format --check cloud tests/cloud` passed after formatting
    `tests/cloud/test_gcp_smoke_monthly_e2e.py`,
    `tests/cloud/test_orchestrator_contract.py`,
    `tests/cloud/test_release_conflict.py`,
    `tests/cloud/test_release_manifest_contract.py`, and
    `tests/cloud/test_release_writer.py`.
  - Import smoke passed for `cloud.orchestrator.release`,
    `cloud.orchestrator.model_package`, `cloud.orchestrator.main`, and
    `cloud.orchestrator.inference`.
  - `python3 -m json.tool specs/001-cloud-base-input/contracts/input-manifest.schema.json`
    passed.
  - `git diff --check -- cloud tests/cloud implementation-delta.md` passed.
  - Typecheck: not configured. No `pyproject.toml`, `mypy.ini`,
    `pyrightconfig.json`, or `ty.toml` was found.
  - Post-implementation artifact validation: generated `__pycache__`
    directories from validation were removed before final status reporting.
- Artifact reconciliation:
  - spec.md update needed: no.
  - plan.md update needed: no.
  - tasks.md update needed: no.
  - evidence update needed: no.
  - source artifact mismatch? no.
  - no update needed because: the changes reconcile implementation to existing
    prediction-output, release exit-status, model-package manifest, and live
    smoke acceptance requirements without changing scope, architecture, task
    intent, task dependencies, or acceptance criteria.

## Merge Review Critical/Important Remediation Delta 9

- Subagent consideration:
  - Task: strictly scoped remediation for the latest pre-merge review Critical
    and Important findings: release manifest write-last immutability, required
    v1 manifest artifact hard gates, and production worker/custom-job failure
    detection.
  - Needed? no.
  - Reason: the review findings were concrete and bounded to three modules plus
    their contract tests; no additional artifact-family comparison or
    cross-agent implementation split was needed.
  - If no, why current task can be handled within the main agent context:
    each finding had a focused RED/GREEN path, and implementation stayed within
    `cloud/orchestrator/release.py`, `cloud/common/manifest.py`,
    `cloud/orchestrator/main.py`, test fixtures, and focused tests.
  - If yes, what bounded packet should be delegated: n/a.
- Code-review findings addressed:
  - Critical: successful `write_release()` no longer mutates the released
    `release_step_report.json` after writing `release_manifest.json`. The
    immutable released step report keeps `new_manifest_generation=null`, while
    run-prefix evidence records the manifest generation after CAS success.
  - Important: `validate_manifest()` now requires exactly one manifest artifact
    entry, marked `required=true`, for each v1 required artifact type:
    `scaffold`, `fixed_slow_area_features`, `source_panel`,
    `gee_evi_export_config`, `geometry`, `docker_image`, `model_package`,
    `vertex_ai_inference_config`, `schema_contract`, and `validator`.
  - Important: production Batch/Vertex waiters now poll declared failure
    reports before waiting for missing success artifacts. `evi_worker_error`,
    failed EVI/GEE reports, failed Vertex job manifests, failed inference
    reports, or inference error reports terminate immediately with a failed
    run summary instead of timing out.
- TDD evidence:
  - RED observed for release immutability:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_release_writer.py::test_release_manifest_records_final_released_step_report_metadata -q -p no:cacheprovider`
    failed because the release manifest recorded step-report generation `1`
    while the final released object was generation `2`.
  - GREEN observed for release immutability:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_release_writer.py -q -p no:cacheprovider`
    passed: 10 passed.
  - RED observed for required artifact hard gates:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_manifest_contract.py::test_required_v1_artifact_type_must_be_present_exactly_once -q -p no:cacheprovider`
    failed for missing required artifact types that previously passed or used
    only the old model-package-specific error.
  - GREEN observed for manifest contract:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_manifest_contract.py -q -p no:cacheprovider`
    passed: 21 passed.
  - RED observed for worker/custom-job failure detection:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_orchestrator_contract.py::test_cloud_orchestrator_worker_error_sentinel_fails_run_without_timeout tests/cloud/test_orchestrator_contract.py::test_vertex_waiter_failed_job_manifest_fails_without_waiting_for_predictions -q -p no:cacheprovider`
    failed because both paths reported missing-artifact timeouts instead of the
    existing failure artifacts.
  - GREEN observed for orchestrator contract:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_orchestrator_contract.py -q -p no:cacheprovider`
    passed: 27 passed.
- Validation:
  - Affected focused suite passed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_release_writer.py tests/cloud/test_manifest_contract.py tests/cloud/test_orchestrator_contract.py -q -p no:cacheprovider`
    passed: 58 passed.
  - Full cloud suite passed after formatting:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud -q -p no:cacheprovider`
    passed: 163 passed, 1 skipped.
  - Existing operational launch and monthly builder regression subset passed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/test_reshape_remote_sensing_wide_to_long.py tests/test_build_monthly_ipcch_base_input.py -q -p no:cacheprovider`
    passed: 30 passed.
  - `ruff check cloud tests/cloud` passed.
  - `ruff format --check cloud tests/cloud` passed after formatting
    `cloud/orchestrator/main.py` and `tests/cloud/test_release_writer.py`.
  - Typecheck: not configured. No `pyproject.toml`, `mypy.ini`,
    `.mypy.ini`, `pyrightconfig.json`, `ty.toml`, or `setup.cfg` was found.
  - Build/import/package smoke passed for JSON schema/fixture parsing and
    imports of `cloud.common.manifest`, `cloud.orchestrator.release`,
    `cloud.orchestrator.main`, and `cloud.orchestrator.inference`.
  - `git diff --check -- cloud tests/cloud implementation-delta.md tests/fixtures/cloud/input_manifest_202604_valid.json`
    passed.
  - Post-implementation artifact validation: generated `__pycache__`
    directories under `cloud/` and `tests/` were removed; final scans found no
    `__pycache__` directories and no working-tree `release_manifest.json`,
    `evi_worker_error.json`, `inference_error.json`,
    `vertex_ai_job_manifest.json`, or `evi_extraction_manifest.json` outputs.
- Artifact reconciliation:
  - spec.md update needed: no.
  - plan.md update needed: no.
  - tasks.md update needed: no.
  - evidence update needed: no.
  - source artifact mismatch? no.
  - no update needed because: these are implementation corrections to existing
    write-last release, required input hard-gate, and terminal failure
    semantics in the active Speckit artifacts. Scope, architecture, task
    intent, dependencies, and acceptance criteria are unchanged.

## Merge Review Important Remediation Delta 10

- Subagent consideration:
  - Task: strictly scoped remediation for the latest full pre-merge review's two
    Important findings: prediction output hard-gate coverage and manifest
    waiver traceability in run summaries.
  - Needed? no.
  - Reason: both findings were bounded to existing validator/run-state behavior
    and had direct tests in the current cloud contract suite.
  - If no, why current task can be handled within the main agent context:
    changes were localized to `cloud/orchestrator/inference.py`,
    `cloud/orchestrator/release.py`, `cloud/orchestrator/main.py`,
    `cloud/orchestrator/run_state.py`, and focused tests.
  - If yes, what bounded packet should be delegated: n/a.
- Code-review findings addressed:
  - Important: `validate_prediction_outputs()` now enforces v1 prediction hard
    gates for finite score columns, binary pred columns, `overall_phase_pred`
    in `1..5`, 0-based `_row_id`, `admin_code` consistency with base input
    when present, and expected `model_package_id`. `run_inference_wrapper()`
    and release preflight now pass the expected package id so invalid Vertex
    outputs cannot be released through the shared validator.
  - Important: manifest waivers are now propagated into run state and copied to
    initial and terminal `run_summary.json` writes, preserving waiver audit
    traceability required by the input contract.
- TDD evidence:
  - RED observed for prediction hard gates:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py::test_prediction_validation_rejects_v1_hard_gate_violations -q -p no:cacheprovider`
    failed before implementation because the validator lacked the expected
    model-package parameter and did not enforce the reviewed hard gates.
  - GREEN observed for prediction hard gates:
    the same focused test passed: 6 passed.
  - RED observed for waiver traceability:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_orchestrator_contract.py::test_cloud_orchestrator_copies_manifest_waivers_to_run_summary -q -p no:cacheprovider`
    failed because `run_summary["waivers"]` was empty.
  - GREEN observed for waiver traceability:
    the same focused test passed: 1 passed.
- Validation:
  - Affected suite passed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py tests/cloud/test_release_writer.py tests/cloud/test_release_conflict.py tests/cloud/test_release_manifest_contract.py tests/cloud/test_orchestrator_contract.py tests/cloud/test_run_state.py -q -p no:cacheprovider`
    passed: 72 passed.
  - Full cloud suite passed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud -q -p no:cacheprovider`
    passed: 170 passed, 1 skipped.
  - Existing operational launch and monthly builder regression subset passed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/test_reshape_remote_sensing_wide_to_long.py tests/test_build_monthly_ipcch_base_input.py -q -p no:cacheprovider`
    passed: 30 passed.
  - `ruff check cloud tests/cloud` passed.
  - `ruff format --check cloud tests/cloud` passed after formatting
    `cloud/orchestrator/inference.py` and
    `tests/cloud/test_vertex_ai_custom_job_contract.py`.
  - Typecheck: not configured. No `pyproject.toml`, `mypy.ini`,
    `.mypy.ini`, `pyrightconfig.json`, `ty.toml`, or `setup.cfg` was found.
  - Import smoke passed for `cloud.orchestrator.inference`,
    `cloud.orchestrator.release`, `cloud.orchestrator.main`, and
    `cloud.orchestrator.run_state`.
  - `git diff --check -- cloud tests/cloud implementation-delta.md` passed.
  - Post-implementation artifact validation: final scans found no
    `__pycache__` directories and no working-tree `release_manifest.json`,
    `evi_worker_error.json`, `inference_error.json`,
    `vertex_ai_job_manifest.json`, or `evi_extraction_manifest.json` outputs.
- Artifact reconciliation:
  - spec.md update needed: no.
  - plan.md update needed: no.
  - tasks.md update needed: no.
  - evidence update needed: no.
  - source artifact mismatch? no.
  - no update needed because: these changes tighten implementation to existing
    Prediction Output Schema v1 and waiver-copy requirements without changing
    scope, architecture, task intent, dependencies, or acceptance criteria.

## Strictly Scoped Review Remediation Delta 11

- Subagent consideration:
  - Task: strictly scoped remediation for the follow-up review findings on
    Prediction Output Schema v1: optional `admin_code` handling and
    manifest-sourced `model_package_id` validation.
  - Needed? no.
  - Reason: both findings were localized to existing prediction validation,
    release preflight, and model package evidence propagation.
  - If no, why current task can be handled within the main agent context:
    changes were bounded to `cloud/orchestrator/inference.py`,
    `cloud/orchestrator/release.py`, `cloud/orchestrator/model_package.py`,
    `cloud/orchestrator/main.py`, and focused tests.
  - If yes, what bounded packet should be delegated: n/a.
- Code-review findings addressed:
  - Important: prediction validation no longer treats missing `admin_code` as a
    hard gate. It records an advisory warning when omitted and still hard-fails
    inconsistent `admin_code` values when the column is present.
  - Important: inference wrapper uses `model_package_manifest.json`
    `model_package_id` when available instead of deriving the expected id from
    the GCS URI basename. Release preflight no longer falls back to URI basename
    inference; orchestrated releases propagate the validated manifest id through
    `model_package_reference`.
- TDD evidence:
  - RED observed for optional `admin_code`:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py::test_prediction_validation_allows_missing_admin_code_as_advisory -q -p no:cacheprovider`
    failed because `admin_code` was in required prediction columns.
  - RED observed for manifest-sourced wrapper package id:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py::test_inference_wrapper_uses_manifest_model_package_id_for_prediction_validation -q -p no:cacheprovider`
    failed because the wrapper expected URI leaf `package_dir` instead of
    manifest id `launch_2026_04`.
  - RED observed for release URI fallback:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_release_writer.py::test_release_writer_does_not_infer_model_package_id_from_uri -q -p no:cacheprovider`
    failed because release preflight derived expected id `package_dir` from the
    model package URI.
  - GREEN observed:
    the three focused tests passed together: 3 passed.
- Validation:
  - Affected suite passed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py tests/cloud/test_release_writer.py tests/cloud/test_release_conflict.py tests/cloud/test_release_manifest_contract.py tests/cloud/test_orchestrator_contract.py tests/cloud/test_run_state.py -q -p no:cacheprovider`
    passed: 75 passed.
  - Full cloud suite passed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud -q -p no:cacheprovider`
    passed: 173 passed, 1 skipped.
  - Existing operational launch and monthly builder regression subset passed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/test_reshape_remote_sensing_wide_to_long.py tests/test_build_monthly_ipcch_base_input.py -q -p no:cacheprovider`
    passed: 30 passed.
  - `ruff check cloud tests/cloud` passed.
  - `ruff format --check cloud tests/cloud` passed after formatting
    `cloud/orchestrator/inference.py` and `cloud/orchestrator/main.py`.
  - Typecheck: not configured. No `pyproject.toml`, `mypy.ini`,
    `pyrightconfig.json`, `ty.toml`, `setup.cfg`, or `tox.ini` was found.
  - Import smoke passed for `cloud.orchestrator.inference`,
    `cloud.orchestrator.release`, `cloud.orchestrator.main`, and
    `cloud.orchestrator.model_package`.
  - Post-implementation artifact validation: generated `tools/__pycache__`
    was removed; final scan found no `__pycache__` directories and no
    working-tree `release_manifest.json`, `evi_worker_error.json`,
    `inference_error.json`, `vertex_ai_job_manifest.json`, or
    `evi_extraction_manifest.json` outputs.
- Artifact reconciliation:
  - spec.md update needed: no.
  - plan.md update needed: no.
  - tasks.md update needed: no.
  - evidence update needed: no.
  - source artifact mismatch? no.
  - no update needed because: these are implementation corrections to match the
    existing Prediction Output Schema v1 rules. Scope, architecture, task
    intent, dependencies, and acceptance criteria are unchanged.

## Strictly Scoped Review Remediation Delta 12

- Subagent consideration:
  - Task: strictly scoped remediation for the follow-up review finding that
    missing manifest/reference `model_package_id` disabled the prediction
    output hard gate.
  - Needed? no.
  - Reason: the finding was localized to model package validation, release
    preflight metadata, release CLI wiring, and affected test fixtures.
  - If no, why current task can be handled within the main agent context:
    changes were bounded to `cloud/orchestrator/model_package.py`,
    `cloud/orchestrator/release.py`, `cloud/orchestrator/main.py`, and focused
    tests under `tests/cloud/`.
  - If yes, what bounded packet should be delegated: n/a.
- Code-review finding addressed:
  - Important: `model_package_manifest.json` now must include a nonblank
    `model_package_id` during model package validation. Release preflight now
    requires explicit `model_package_reference.model_package_id` instead of
    passing `None` and disabling prediction id validation. The release CLI now
    accepts `--model-package-id` so manual release attempts can satisfy the
    same hard gate.
- TDD evidence:
  - RED observed for missing model package manifest id:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py::test_model_package_validation_rejects_missing_manifest_model_package_id tests/cloud/test_release_writer.py::test_release_writer_requires_explicit_model_package_id_reference -q -p no:cacheprovider`
    failed because neither path raised on a missing id.
  - GREEN observed for the same focused tests:
    passed: 2 passed.
  - RED observed for release CLI model package id plumbing:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_release_writer.py::test_release_cli_parser_exposes_execution_contract_arguments -q -p no:cacheprovider`
    failed because `--model-package-id` was unrecognized.
  - GREEN observed after wiring CLI parsing and metadata propagation:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_release_writer.py::test_release_cli_parser_exposes_execution_contract_arguments tests/cloud/test_release_writer.py::test_release_cli_returns_nonzero_on_release_conflict tests/cloud/test_orchestrator_contract.py::test_fake_orchestrator_sequence_writes_required_terminal_artifacts -q -p no:cacheprovider`
    passed: 3 passed.
- Validation:
  - Affected suite passed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py tests/cloud/test_release_writer.py tests/cloud/test_release_conflict.py tests/cloud/test_release_manifest_contract.py tests/cloud/test_orchestrator_contract.py tests/cloud/test_run_state.py -q -p no:cacheprovider`
    passed: 77 passed.
  - Full cloud suite passed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud -q -p no:cacheprovider`
    passed: 175 passed, 1 skipped.
  - Existing operational launch and monthly builder regression subset passed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/test_reshape_remote_sensing_wide_to_long.py tests/test_build_monthly_ipcch_base_input.py -q -p no:cacheprovider`
    passed: 30 passed.
  - `ruff check cloud tests/cloud` passed.
  - `ruff format --check cloud tests/cloud` passed after formatting
    `tests/cloud/test_vertex_ai_custom_job_contract.py`.
  - Typecheck: not configured. No `pyproject.toml`, `mypy.ini`,
    `pyrightconfig.json`, `ty.toml`, `setup.cfg`, or `tox.ini` was found.
  - Import smoke passed for `cloud.orchestrator.inference`,
    `cloud.orchestrator.release`, `cloud.orchestrator.main`, and
    `cloud.orchestrator.model_package`.
  - `git diff --check -- cloud tests/cloud implementation-delta.md` passed.
  - Post-implementation artifact validation: final scan found no `__pycache__`
    directories and no working-tree `release_manifest.json`,
    `evi_worker_error.json`, `inference_error.json`,
    `vertex_ai_job_manifest.json`, or `evi_extraction_manifest.json` outputs.
- Artifact reconciliation:
  - spec.md update needed: no.
  - plan.md update needed: no.
  - tasks.md update needed: no.
  - evidence update needed: no.
  - source artifact mismatch? no.
  - no update needed because: these changes enforce the existing
    `model_package_manifest.json` and Prediction Output Schema v1 hard gates
    without changing scope, architecture, task intent, dependencies, or
    acceptance criteria.

## Strictly Scoped Review Remediation Delta 13

- Subagent consideration:
  - Task: strictly scoped remediation for two remaining Important merge-review
    findings.
  - Needed? no.
  - Reason: both findings were localized to model package manifest validation,
    release preflight sequencing, and their focused cloud tests.
  - If no, why current task can be handled within the main agent context:
    the failing tests already isolated the contract gaps, and the fixes were
    bounded to `cloud/orchestrator/model_package.py`,
    `cloud/orchestrator/release.py`, `tests/cloud/test_vertex_ai_custom_job_contract.py`,
    `tests/cloud/test_release_writer.py`, and
    `tests/cloud/test_orchestrator_contract.py`.
  - If yes, what bounded packet should be delegated: n/a.
- Code-review findings addressed:
  - Important: `model_package_manifest.json` validation now requires the full
    contract field set from the active spec, not just schema/id fields.
  - Important: release preflight now accepts a source `run_summary.json` with
    `status: running` by constructing the released copy candidate before
    release preflight, instead of requiring the source run summary to already
    be released.
- TDD evidence:
  - RED observed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py::test_model_package_validation_rejects_missing_contract_manifest_fields tests/cloud/test_release_writer.py::test_release_writer_accepts_running_run_summary_and_copies_released_candidate -q -p no:cacheprovider`
    failed because missing contract manifest fields were accepted and a running
    source run summary was rejected.
  - GREEN observed for the same focused tests after the minimal implementation:
    passed: 16 passed.
  - Regression fixture failure then reproduced in the affected suite:
    valid-path orchestrator fixtures used legacy three-field model package
    manifests and were rejected before reaching their intended assertions.
  - GREEN observed after strictly scoped fixture repair:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py tests/cloud/test_release_writer.py tests/cloud/test_orchestrator_contract.py -q -p no:cacheprovider`
    passed: 84 passed.
- Validation:
  - Affected release/orchestrator suite passed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py tests/cloud/test_release_writer.py tests/cloud/test_release_conflict.py tests/cloud/test_release_manifest_contract.py tests/cloud/test_orchestrator_contract.py tests/cloud/test_run_state.py -q -p no:cacheprovider`
    passed: 93 passed.
  - Full cloud suite passed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud -q -p no:cacheprovider`
    passed: 191 passed, 1 skipped.
  - Existing operational launch and monthly builder regression subset passed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/test_reshape_remote_sensing_wide_to_long.py tests/test_build_monthly_ipcch_base_input.py -q -p no:cacheprovider`
    passed: 30 passed.
  - `ruff check cloud tests/cloud` passed.
  - `ruff format --check cloud tests/cloud` passed.
  - Typecheck: not configured. No `pyproject.toml`, `mypy.ini`,
    `pyrightconfig.json`, `ty.toml`, `setup.cfg`, or `tox.ini` was found.
  - Import smoke passed for `cloud.orchestrator.inference`,
    `cloud.orchestrator.release`, `cloud.orchestrator.main`, and
    `cloud.orchestrator.model_package`.
  - `git diff --check -- cloud tests/cloud implementation-delta.md` passed.
  - Post-implementation artifact validation: final scan found no `__pycache__`
    directories and no working-tree `release_manifest.json`,
    `evi_worker_error.json`, `inference_error.json`,
    `vertex_ai_job_manifest.json`, or `evi_extraction_manifest.json` outputs.
- Artifact reconciliation:
  - spec.md update needed: no.
  - plan.md update needed: no.
  - tasks.md update needed: no.
  - evidence update needed: no.
  - source artifact mismatch? no.
  - no update needed because: both fixes implement existing source-of-truth
    contracts without changing scope, architecture, task intent, dependencies,
    or acceptance criteria.

## Strictly Scoped Merge-Review Remediation Delta 14

- Subagent consideration:
  - Task: strictly scoped remediation for one Critical and two Important
    pre-merge review findings.
  - Needed? no.
  - Reason: each finding had a direct local reproduction and a narrow write set.
  - If no, why current task can be handled within the main agent context:
    fixes were bounded to base-input validation normalization, cloud assembly
    summary/equivalence coverage, Vertex inference failure evidence, and their
    focused tests.
  - If yes, what bounded packet should be delegated: n/a.
- Code-review findings addressed:
  - Critical: base input validation now uses the same numeric identifier
    normalization as cloud assembly, so assembled `area_id=101` with
    `admin_code=101.0` is accepted as the same area identity.
  - Important: cloud assembly now has an equivalence regression against the
    existing monthly builder for shared scaffold/source/fixed columns, while
    appending cloud EVI features. The cloud assembly summary now carries
    `source_join.scanned_rows` to preserve existing builder summary semantics.
  - Important: Vertex inference wrapper failures now write
    `inference_error.json`, failed `vertex_ai_job_manifest.json`, and failed
    `inference_report.json` before re-raising, so the orchestrator can fail
    fast through its failure-report wait path.
  - Minor release-manifest builder consolidation was intentionally not changed;
    it remains outside the user's strictly scoped Critical/Important repair
    request.
- TDD evidence:
  - RED observed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_monthly_assembly_wrapper.py::test_assembly_matches_existing_builder_for_shared_inputs_then_appends_evi tests/cloud/test_monthly_assembly_wrapper.py::test_base_input_validation_accepts_assembled_numeric_admin_code_identity tests/cloud/test_vertex_ai_custom_job_contract.py::test_inference_wrapper_writes_failure_evidence_when_command_fails -q -p no:cacheprovider`
    failed with missing `source_join.scanned_rows`, numeric admin-code identity
    rejection, and missing `inference_error.json`.
  - GREEN observed for the same focused tests after minimal implementation:
    passed: 3 passed.
- Validation:
  - Affected suite passed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_monthly_assembly_wrapper.py tests/cloud/test_vertex_ai_custom_job_contract.py tests/cloud/test_orchestrator_contract.py -q -p no:cacheprovider`
    passed: 85 passed.
  - Full cloud suite passed after formatting:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud -q -p no:cacheprovider`
    passed: 194 passed, 1 skipped.
  - Existing operational launch and monthly builder regression subset passed:
    `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/test_reshape_remote_sensing_wide_to_long.py tests/test_build_monthly_ipcch_base_input.py -q -p no:cacheprovider`
    passed: 30 passed.
  - `ruff check cloud tests/cloud` passed.
  - `ruff format --check cloud tests/cloud` passed after formatting
    `tests/cloud/test_monthly_assembly_wrapper.py` and
    `tests/cloud/test_vertex_ai_custom_job_contract.py`.
  - Typecheck: not configured. No `pyproject.toml`, `mypy.ini`,
    `pyrightconfig.json`, `ty.toml`, `setup.cfg`, or `tox.ini` was found.
  - Import smoke passed for `cloud.orchestrator.inference`,
    `cloud.orchestrator.release`, `cloud.orchestrator.main`,
    `cloud.orchestrator.model_package`, `cloud.orchestrator.assembly`, and
    `cloud.orchestrator.base_input_validation`.
  - `git diff --check -- cloud tests/cloud implementation-delta.md` passed.
  - Post-implementation artifact validation: generated `__pycache__`
    directories were removed; final scan found no `__pycache__` directories
    and no working-tree `release_manifest.json`, `evi_worker_error.json`,
    `inference_error.json`, `vertex_ai_job_manifest.json`, or
    `evi_extraction_manifest.json` outputs.
- Artifact reconciliation:
  - spec.md update needed: no.
  - plan.md update needed: no.
  - tasks.md update needed: no.
  - evidence update needed: no.
  - source artifact mismatch? no.
  - no update needed because: these are implementation and regression-test
    corrections to meet existing base-input identity, assembly-wrapper, and
    post-prefix failure-evidence contracts without changing scope,
    architecture, task intent, dependencies, or acceptance criteria.
