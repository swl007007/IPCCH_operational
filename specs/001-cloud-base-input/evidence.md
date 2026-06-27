# Repository Evidence: IPCCH Cloud Monthly E2E Feature Input and Inference

## Feature Request

Ground the current Spec Kit feature `001-cloud-base-input` after the scope changed
from cloud monthly base-input production plus downstream validate-only checking to
a fully cloud-native GCP monthly E2E run. The current scope includes Cloud Run
orchestration, Cloud Batch EVI/GEE/rasterio work, monthly model feature/base input
assembly, Vertex AI custom-job inference, prediction CSV validation, immutable
run evidence, and atomic release artifacts for exactly one selected feature
month.

This evidence file supersedes the earlier draft evidence for current planning
and task grounding. Historical pre-scope-change evidence should be treated as
source-scan context only when available; its validate-only and no-prediction
scope conclusions are stale for the current feature.

## Evidence Status

- Status: Ready for planning and task grounding; not evidence of implementation
  completion.
- Draft slug: ipcch-cloud-monthly-e2e-feature-input-inference
- Final Speckit feature directory: `specs/001-cloud-base-input/`
- Feature directory: `specs/001-cloud-base-input/`
- Evidence artifact path: `specs/001-cloud-base-input/evidence.md`
- Last updated: 2026-06-26
- Scope inspected: current `spec.md`, `plan.md`, `tasks.md`, previous evidence
  pack, runbook/output inventory, EVI export/extraction scripts, remote-sensing
  reshape utility, monthly base-input assembly, schema validator, operational
  launch inference CLI/runtime, local prediction output headers, and existing
  tests listed by the previous evidence scan.
- Major unknowns: exact deployment-time GCP project, bucket, service-account
  names, Artifact Registry image URI/digest, Vertex AI model package URI,
  optional EVI or inference reference sample URI, and live cloud behavior for GEE,
  Cloud Batch, GCS generation preconditions, and Vertex AI custom jobs.

## Validation Status

- Status: Not Executed
- Tests executed by this pass: None.
- Commands executed: Read-only file/list/search/header-inspection commands only.
- Commands not executed: Unit tests, schema validators, inference CLI, Docker
  build, Earth Engine export, GCS commands, Cloud Run jobs, Cloud Batch jobs,
  Vertex AI jobs, and release artifact checks.
- Artifact outputs inspected: File presence, documentation, source contracts, and
  prediction CSV headers only.
- Artifact outputs not inspected: Full CSV row counts, shapefile geometry
  contents, model package internals beyond referenced manifest evidence, cloud
  object metadata, checksums, and generated report bodies.
- Validation evidence source: Repository docs/source/tests/manifests, current
  Spec Kit artifacts, and local output headers.
- Remaining validation unknowns: Actual cloud credentials/IAM, service-account
  Earth Engine authorization, rasterio numeric agreement with ArcPy, GCS
  read/write/generation behavior, Vertex AI runtime compatibility, and atomic
  release behavior.

## Acceptance Readiness

- Status: Not Applicable
- Reason: Implementation has not started; all tasks in `tasks.md` are unchecked.
- Blocking issues: None for planning/task grounding after this evidence refresh.
- Non-blocking risks: The GCP runtime layer is new to this repo and must be
  validated by implementation tasks and cloud smoke evidence.
- Required follow-up before final acceptance: Complete the tasks, run the targeted
  and regression tests listed in `tasks.md`, inspect generated report/artifact
  contracts, and run any required gated GCP smoke test.

## Search Coverage

| Search Term / Method | Purpose | Result | Notes |
|---|---|---|---|
| `find specs/001-cloud-base-input -maxdepth 2 -type f` | Inventory current feature artifacts | Found spec, plan, tasks, contracts, data model, quickstart, checklist; no feature-local `evidence.md` before this refresh | Feature-local evidence was missing. |
| `git status --short` | Inspect uncommitted feature state | `AGENTS.md` modified; `.specify/feature.json` and `specs/001-cloud-base-input/` untracked | Treat feature artifacts as provisional until committed. |
| `validate-only`, `Vertex AI`, `custom-job`, `prediction output`, `ipcch_launch_*_predictions` | Detect scope conflicts between evidence and current artifacts | Previous evidence supports validate-only/no-prediction; current spec/plan/tasks require Vertex AI custom-job inference and prediction CSVs | This refresh resolves that mismatch by marking old scope historical. |
| `Cloud Run`, `Cloud Batch`, `rasterio`, `Earth Engine`, `Dockerfile`, `requirements-cloud.txt`, `release_manifest` | Locate existing cloud runtime implementation | Current repo has no executable cloud package, Dockerfile, or cloud dependency manifest before tasks | Cloud runtime is new implementation target, not existing behavior. |
| Operational launch inference source and local prediction headers | Ground v1 prediction schema and wrapper behavior | Found local CLI, score/pred columns, scope filename pattern, and local headers | Supports prediction schema derivation and the need for wrapper-added `year`/`month`. |

## Negative Evidence / Not Found

| Searched For | Search Method / Terms | Result | Implication |
|---|---|---|---|
| Feature-local evidence artifact | `find specs/001-cloud-base-input ... evidence.md` | Not found before this refresh | Spec references needed updating from `_evidence` to feature-local evidence. |
| Cloud Run implementation | `Cloud Run`, `gcloud run`, `cloud/orchestrator` | No executable package found | Tasks T029-T041 create a new subsystem. |
| Google Cloud Batch implementation | `Cloud Batch`, `google.cloud.batch`, `batch_client` | No executable implementation found | Batch worker/submission code is new. |
| Earth Engine Python SDK implementation | `import ee`, `ee.Initialize`, `earthengine` | No executable Python GEE export implementation found | Current EVI export is JavaScript evidence; Python export is new. |
| rasterio EVI extraction implementation | `rasterio`, `rasterstats`, `evi_extract` | No EVI rasterio extraction code found | ArcPy replacement must be implemented and validated. |
| Container/dependency manifest | `Dockerfile`, `requirements-cloud.txt`, cloud dependency files | None found before tasks | Tasks T002-T003 introduce project cloud runtime packaging. |
| GCS run/release artifact writer | `release_manifest`, `runs/{run_id}`, `released/{YYYYMM}` | Only Spec Kit artifacts mention this | Release model is new implementation scope. |

## Files Inspected

| Path | Symbols / Sections | Type | Why Inspected | Relevant Finding | Implication | Confidence |
|---|---|---|---|---|---|---|
| `specs/001-cloud-base-input/spec.md:17-57` | Scope Boundaries | Spec | Current scope authority | In scope now includes cloud-only dispatch, Cloud Run, Cloud Batch, GEE EVI export, rasterio extraction, base input, and Vertex AI custom-job inference; out of scope excludes maps/sheets/full delivery/training/non-EVI remote sensing/local workstation execution | Evidence must support E2E inference as current scope and not preserve old validate-only boundary | High |
| `specs/001-cloud-base-input/spec.md:536-740` | Vertex AI, runtime, prediction schema | Spec | Current inference contract | v1 uses `vertex_ai_custom_job`, same repository image digest, localizes GCS inputs, runs `model_pipeline/run_operational_launch_inference.py --no-map --overwrite`, forbids `--validate-only`, and validates three prediction CSVs | Tasks T027/T037/T038 are scoped by spec; cloud runtime remains unimplemented | High |
| `specs/001-cloud-base-input/spec.md:1202-1215` | Evidence Mapping | Spec | Grounding status | Spec already marks Vertex AI custom-job runtime and Cloud Run/Batch/rasterio as new implementation targets | Evidence should preserve this distinction | High |
| `specs/001-cloud-base-input/plan.md:7-22` | Summary | Plan | Architecture decision | Plan chooses Cloud Run orchestrator, Cloud Batch worker, GEE export/rasterio extraction, base input, Vertex AI custom job, and atomic release | Plan authorizes new cloud subsystem tasks | High |
| `specs/001-cloud-base-input/plan.md:88-152` | Project Structure | Plan | File layout | Plan adds `cloud/`, `docker/Dockerfile`, new cloud tests, and preserves existing EVI/assembly/model pipeline code | New files in tasks match plan | High |
| `specs/001-cloud-base-input/tasks.md:15-146` | T001-T066 | Tasks | Traceability | Tasks are all unchecked and cover setup, foundations, US1 E2E, US2 EVI audit, US3 release consumption, and validation | No implementation claims are currently complete | High |
| Historical previous evidence scan notes | Previous scope evidence | Historical evidence | Detect stale conclusions | Earlier evidence said first phase ended at monthly base input and used validate-only compatibility | Historical only; conflicts with current E2E inference scope | High |
| Historical previous evidence scan notes | Validate-only CLI/test evidence | Historical evidence/source scan | Reusable source facts | Correctly identified validate-only behavior in existing CLI/tests | Still useful to ensure v1 custom job does not pass `--validate-only` | High |
| Historical previous evidence scan notes | Implications for Spec | Historical evidence | Stale instruction | Said prediction generation should remain out of scope | Superseded by user-selected Vertex AI custom-job inference | High |
| `docs/03_workflow_runbook.md:8-18` | EVI workflow | Runbook | Existing remote-sensing contract | Current EVI flow is Earth Engine Code Editor, GCS download, ArcPy extraction, wide mean/std CSVs keyed by `region_id`, then reshape | Cloud EVI should preserve output shape/names while replacing runtime | High |
| `docs/03_workflow_runbook.md:137-159` | Final Monthly IPCCH Assembly | Runbook | Existing monthly base input | Current command builds `ipcch_monthly_base_input_YYYYMM.csv` and summary JSON as long monthly table keyed by `area_id`, `year`, `month` | Cloud assembly wrapper should preserve this output contract | High |
| `docs/03_workflow_runbook.md:161-178` | Operational launch inference | Runbook | Existing inference path | Existing operator guidance says run `--validate-only` first, then without it to generate six primary delivery files | Current cloud spec uses full inference but excludes maps/sheets/full delivery | High |
| `docs/04_output_inventory.md:5-16` | Workflow output contracts | Inventory | Existing artifact shapes | EVI output is wide mean/std; unified monthly model input is long base input | Supports EVI output contract and base input contract | High |
| `docs/04_output_inventory.md:20-36` | Required local reference files | Inventory | Current local artifacts | Documents scaffold, geometry, fixed/slow features, schemas, row counts, and checksums | Cloud manifest should carry equivalent URI plus immutable reference | High |
| `docs/04_output_inventory.md:50-55` | Remote-sensing normalization note | Inventory | ID mapping | Wide outputs use `region_id`; reshape can map to `area_id` if needed | Current spec's `region_id == area_id` rule is a v1 cloud contract, not old ArcPy proof | High |
| `EVI/00_ee_export_evi.txt:9-40` | EE JavaScript export | Source snippet | EVI source contract | Uses `MODIS/061/MOD13A3`, band `EVI`, GeoTIFF export to Cloud Storage, scale 1000, filename `MOD13A3_YYYY_MM` | Python GEE export should preserve collection/band/resolution/naming unless spec changes | High |
| `EVI/02_arcpy_extract_evi.py:41-47` | Config inputs | Source | Current extraction inputs | Reads raster folder, polygon shapefile, output folder, zone field, and filename pattern from config | Cloud worker needs analogous manifest-driven inputs | High |
| `EVI/02_arcpy_extract_evi.py:77-129` | Zonal extraction and output | Source | Current statistic semantics | ArcPy uses `ZonalStatisticsAsTable(..., "DATA", "ALL")` and writes `EVI_mean_extraction_results.csv` and `EVI_std_extraction_results.csv` | Rasterio implementation must define comparable, testable semantics; numeric differences should be advisory when output contract passes | High |
| `tools/reshape_remote_sensing_wide_to_long.py:10-31` | Month parsers | Source | Wide-date contract | Supports `YYYY_MM`, `YYYY.MMM`, and `YYYY_MM_Bn` | EVI cloud wide output should use `YYYY_MM` | High |
| `tools/reshape_remote_sensing_wide_to_long.py:34-116` | ID mapping and reshape | Source | Wide-to-long behavior | Converts `region_id` wide rows to `area_id`, `year`, `month`; duplicate/unmatched mappings fail | Cloud EVI long writers should preserve or explicitly implement these rules | High |
| `Final_harmonise/00_build_monthly_ipcch_base_input.py:46-73` | CLI parser | Source | Base input command | Existing CLI accepts year/month/config/scaffold/historical-panel/fixed-slow/output/summary-output local paths | Cloud wrapper should localize GCS inputs or adapt IO narrowly | High |
| `Final_harmonise/00_build_monthly_ipcch_base_input.py:232-282` | `load_scaffold` | Source | Row universe | Scaffold must contain exactly one target month, nonblank admin code, no duplicate keys, and at least one row | Supports hard gates for scaffold row universe | High |
| `Final_harmonise/00_build_monthly_ipcch_base_input.py:285-344` | `load_fixed_slow`, `load_source_slice` | Source | Join inputs | Fixed/slow requires unique nonblank `area_id`; source slice filters selected month and records `target_month_present_in_source` | Cloud summary should preserve missingness and source availability semantics | High |
| `Final_harmonise/00_build_monthly_ipcch_base_input.py:376-461` | `build_monthly_base_input` | Source | Output and summary | Writes output CSV plus JSON summary with row/column count, key columns, join metrics, and missingness | Cloud assembly should wrap or extend this summary | High |
| `tools/validate_ipcch_schema.py:56-104` | `MODE_CONFIG` | Source | Schema validation | `model-input-forecast` requires nonblank unique `area_id`, `year`, `month` | Supports base input hard gate before inference | High |
| `model_pipeline/run_operational_launch_inference.py:65-69` | Validate-only branch | Source | Inference behavior | `--validate-only` writes summary and returns before scoring | v1 custom job must not pass `--validate-only` when predictions are required | High |
| `model_pipeline/run_operational_launch_inference.py:204-216` | CLI parser | Source | Inference command | CLI requires input, model package, output dir, feature month and supports `--validate-only`, `--overwrite`, `--no-map` | Supports spec's explicit local command shape inside Vertex AI wrapper | High |
| `model_pipeline/ipcch_launch_runtime/inference.py:9-17` | `REQUIRED_TARGETS`, score/pred columns | Source | Prediction schema | Required targets are phase2 through phase5 worse, with score and pred columns | Supports required prediction/result columns | High |
| `model_pipeline/ipcch_launch_runtime/inference.py:39-58` | `score_scope` output columns | Source | Prediction schema | Output includes identity columns, scores, preds, `overall_phase_pred`, `feature_period`, `target_period`, `scope_months`, `model_package_id`, `source_input` | Supports v1 prediction schema except cloud-added `year`/`month` | High |
| `model_pipeline/ipcch_launch_runtime/inference.py:99-105` | `_identity_frame` | Source | Identity output | Local predictions include `area_id`, optional `admin_code`, and `_row_id` from monthly rows | Cloud wrapper must add explicit `year`/`month` for release contract | High |
| `model_pipeline/ipcch_launch_runtime/outputs.py:21-28` | `scope_primary_paths` | Source | Prediction filenames | Prediction CSV naming is `ipcch_launch_YYYYMM_scope_{0,6,12}m_predictions.csv`; maps only when `include_map` is true | Supports prediction filenames and map exclusion via `--no-map` | High |
| `Outcome/ipcch_unified/predictions/202604/*_predictions.csv` headers | Local outputs | Local artifact | Required-result evidence | Headers include local prediction/result columns but not explicit `year` or `month` | Confirms local validation evidence is not identical to cloud release schema | Medium |

## Existing Similar Behavior

| Behavior / Pattern | Source | How It Works | Relevance | Implication |
|---|---|---|---|---|
| EVI wide mean/std extraction | `docs/03_workflow_runbook.md:8-18`; `EVI/02_arcpy_extract_evi.py:77-129` | Existing flow exports MOD13A3 EVI rasters, runs ArcPy zonal stats, and writes two wide CSVs keyed by `region_id` | Directly relevant to Cloud Batch/rasterio replacement | Preserve names/shape; treat numeric ArcPy parity as advisory unless output contract fails. |
| Remote-sensing wide-to-long conversion | `tools/reshape_remote_sensing_wide_to_long.py:65-153` | Converts supported monthly columns into `area_id`, `year`, `month`, feature value rows | Required for EVI long monthly outputs | Reuse or match this behavior in cloud EVI output writer. |
| Monthly base input assembly | `Final_harmonise/00_build_monthly_ipcch_base_input.py:376-461` | Joins one-month scaffold, fixed/slow area features, and target-month source panel slice; writes CSV and summary JSON | Required for cloud assembly | Localize GCS inputs to container paths or add narrow wrapper/adapters. |
| Model-input forecast validation | `tools/validate_ipcch_schema.py:98-104` | Requires nonblank unique `area_id`, `year`, `month` | Hard gate before Vertex AI inference | Wrap validator semantics in cloud base-input validation report. |
| Local operational launch inference | `model_pipeline/run_operational_launch_inference.py`; `model_pipeline/ipcch_launch_runtime/` | Consumes monthly input plus exported model package and writes scope prediction CSVs when not validate-only | Basis for Vertex AI custom-job entrypoint | Cloud custom job must prove runtime compatibility; local validation alone is not enough. |
| Atomic local inference output handling | `model_pipeline/ipcch_launch_runtime/outputs.py:67-108` | Writes JSON atomically and commits temp outputs with rollback | Similar safety concern to release manifest update | Cloud release writer should use object-store preconditions and manifest-write-last semantics. |

## Related Tests

| Test Path | Behavior Covered | Test Pattern | Missing Coverage | Implication |
|---|---|---|---|---|
| `tests/test_reshape_remote_sensing_wide_to_long.py` | EVI `YYYY_MM`, region-to-area mapping, duplicate mapping failure, CLI writing | Pandas/temp-file fixtures | No rasterio extraction or GCS URI behavior | Add cloud EVI worker and rasterio tests as tasks T024-T025/T044-T046. |
| `tests/test_build_monthly_ipcch_base_input.py` | Base-input assembly, future month with missing source slice, duplicate scaffold failure | Temp CSV fixtures | No cloud manifest, GCS localization, or EVI cloud feature injection | Add assembly wrapper tests as T026. |
| `tests/test_operational_launch_cli.py` | Validate-only, no-map scoring, output collision, failed summaries, help | Mocked/local file tests | No Vertex AI custom job wrapper, GCS localization, or year/month enrichment | Add Vertex AI wrapper tests as T027. |
| `tests/test_operational_launch_input_contract.py` | Monthly input ID/month/null/duplicate contract | Pandas fixtures | No full cloud base input release artifact validation | Combine with schema validator and cloud report tests. |
| `tests/test_tabular_config_paths.py` | Tabular scripts use configured paths | Static/source assertions | No cloud input manifest equivalent | Manifest schema and loader tests should cover cloud indirection. |

## Existing APIs / Contracts / Schemas

| Item | Source | Current Behavior | Compatibility Concern | Implication |
|---|---|---|---|---|
| EVI wide CSV contract | `EVI/02_arcpy_extract_evi.py:124-129`; `docs/04_output_inventory.md:5-10` | Writes mean/std wide monthly CSVs keyed by `region_id` | Rasterio all-touched/nodata/CRS semantics can differ from ArcPy | Define and test v1 rasterio rules; advisory reference comparison records numeric differences. |
| EVI long shape | `tools/reshape_remote_sensing_wide_to_long.py:65-116` | Produces `area_id`, `year`, `month`, feature value columns | Existing tool does not enforce selected-month-only unless caller inputs one month | Cloud output writer must filter/validate selected feature month. |
| Monthly base input | `Final_harmonise/00_build_monthly_ipcch_base_input.py:46-73` | Local-file CLI builds CSV and summary JSON | Current CLI does not read `gs://` directly and does not explicitly merge separate EVI long artifacts | Cloud wrapper must stage inputs and merge EVI features as implementation work. |
| Model-input forecast schema | `tools/validate_ipcch_schema.py:98-104` | Requires unique nonblank model forecast keys | Validator reads local CSV path | Cloud validator can run after localizing artifacts or use an equivalent wrapper. |
| Operational launch inference CLI | `model_pipeline/run_operational_launch_inference.py:204-216` | Local CLI accepts input/model package/output dir/feature month and optional no-map/overwrite/validate-only | Vertex AI custom job must provide cloud localization, report contracts, and forbidden side-effect checks | Use as container-internal command, not as evidence that cloud inference works. |
| Prediction output names | `model_pipeline/ipcch_launch_runtime/outputs.py:21-28` | Writes `ipcch_launch_YYYYMM_scope_{scope}m_predictions.csv` | Local script may also write maps if not `--no-map` | v1 custom job must always pass `--no-map`. |
| Prediction output columns | `model_pipeline/ipcch_launch_runtime/inference.py:39-58`; local 202604 headers | Local predictions include scores/preds/metadata but not explicit `year`/`month` | Cloud release schema requires `year` and `month` keys | Wrapper-added `year`/`month` is a new cloud contract. |

## Data Models / Persistence

| Model / Storage Area | Source | Current Pattern | Migration / Compatibility Concern | Implication |
|---|---|---|---|---|
| One-month scaffold | `docs/04_output_inventory.md:24`; `Final_harmonise/00_build_monthly_ipcch_base_input.py:232-282` | Local 2026-04 scaffold has 6,227 rows; scaffold is the row universe | Cloud manifest must identify immutable scaffold object for selected month | Row count equality is a hard gate. |
| Fixed/slow area features | `docs/04_output_inventory.md:30`; `Final_harmonise/00_build_monthly_ipcch_base_input.py:285-307` | Local asset has unique `area_id` and fixed/slow feature columns | Cloud run needs immutable object reference/checksum or generation | Missing/duplicate area IDs are hard gates. |
| Historical/source panel | `docs/04_output_inventory.md:23`; `Final_harmonise/00_build_monthly_ipcch_base_input.py:310-344` | Large local CSV covers 2010-01 to 2026-04 and is filtered by target month | Downloading full object in Cloud Run may be expensive | Assumption: cloud wrapper may localize full panel or selected slice according to manifest. |
| Geometry | `docs/04_output_inventory.md:27`; `docs/04_output_inventory.md:50-55` | Shapefile package used for spatial/admin areas; remote-sensing output uses `region_id` | Cloud Batch/rasterio needs cloud-readable geometry and canonical `area_id` | Prefer immutable GeoPackage/zipped shapefile manifest entry. |
| Model package | `model_artifacts/launch_2026_04/model_package_manifest.json` per previous evidence | Exported weights/package exists locally for launch inference | v1 model package must be immutable GCS package, not registered Vertex AI Model | Cloud model package manifest/checksum/version are hard gates. |
| Run/release artifacts | Current spec/plan only | No existing GCS `runs/`, `staging/`, or `released/` writer | New persistence model | Implement object-store abstraction and release writer before acceptance. |

## Auth / Validation / Error Handling / Observability Patterns

| Concern | Source | Existing Pattern | Required Follow-up |
|---|---|---|---|
| Earth Engine/GCS auth | `docs/02_ee_gcs_account_setup.md` per previous evidence | Operator account, `gcloud auth login`, `gsutil`, and manual EE authorization | Define and verify service-account Earth Engine/GCS permissions in deployment manifest and smoke test. |
| Local config failure | `workflow_config.py` per previous evidence | Missing config raises actionable runtime errors | Cloud manifest parser should produce similarly actionable hard-gate failures. |
| Base-input hard failures | `Final_harmonise/00_build_monthly_ipcch_base_input.py:221-282`, `285-307`, `427-428` | Missing files/columns, bad scaffold month, duplicate keys fail | Cloud reports must record these as hard gates. |
| Missing source month | `Final_harmonise/00_build_monthly_ipcch_base_input.py:339-344`, `448-455` | Source target-month presence is recorded in summary | Cloud contract should preserve `target_month_present_in_source` missingness behavior. |
| Local inference expected errors | `model_pipeline/run_operational_launch_inference.py` per previous evidence | Expected errors write failed run summary; validate-only exits before scoring | Vertex AI wrapper must translate custom-job failures into `inference_report.json` and terminal run summary. |
| Forbidden output families | Current spec/tasks | No existing scanner | Implement machine-checkable prefix/pattern scanner in T019-T020. |

## Architecture Constraints

| Constraint | Source | Implication | Risk |
|---|---|---|---|
| Current scope is GCP-only E2E inference | `specs/001-cloud-base-input/spec.md:17-57`, `:1151-1164` | Do not preserve old "validate-only only" conclusion as active scope | Stale evidence can mislead implementation. |
| Cloud runtime is new | Previous evidence negative search; no `cloud/`, `docker/`, or `requirements-cloud.txt` before tasks | Plan/tasks must introduce structure, tests, and packaging | High integration risk until tested. |
| Single image v1 | `specs/001-cloud-base-input/spec.md:130-162`; `plan.md:147-152` | Same digest is used for Cloud Batch, assembly/validation, release writing, and Vertex custom job | Dependency conflicts may appear between geospatial and inference stacks. |
| EVI-only remote sensing | `specs/001-cloud-base-input/spec.md:25-57`; runbook output shapes | Do not add FLDAS/GOSIF/VIIRS implementation tasks | Forbidden side-effect scanner should fail non-EVI outputs. |
| Prediction maps/sheets/full delivery excluded | `specs/001-cloud-base-input/spec.md:44-57`, `:590-595` | Vertex AI inference may produce prediction CSVs only | Existing local inference can produce maps if not `--no-map`; wrapper must prevent that. |
| Local workstation paths forbidden at runtime | `specs/001-cloud-base-input/spec.md:59-68` | Local paths in docs are examples only unless container-internal | Manifest validation must reject workstation paths. |

## Task Traceability Snapshot

| Task(s) | Checked? | Expected Trace | Evidence / Plan Source | Support Level | Issue | Severity | Recommended Action |
|---|---|---|---|---|---|---|---|
| T001-T003 | No | Add `cloud/`, `requirements-cloud.txt`, and single-image Dockerfile | `plan.md:88-152`; negative evidence shows no current cloud/Docker files | Partially Supported | Authorized by plan, not existing repo convention | Medium | Treat as new subsystem setup; keep scope isolated. |
| T004-T007 | No | Cloud fixtures/test package | `tasks.md:18-21`; spec manifest/report contracts | Supported | Test scaffolding is planned, not existing evidence | Low | Proceed during setup. |
| T008-T022 | No | Manifest/report/object-store/run-state/forbidden/defaults foundations | `spec.md` contracts; `plan.md:41-45`; `tasks.md:31-45` | Supported by spec/plan | No implementation evidence yet | Medium | Implement with tests before user-story work. |
| T023-T028 | No | US1 contract tests | `tasks.md:59-64`; acceptance scenarios in `spec.md` | Supported by spec/plan | Tests will define fake cloud behavior | Medium | Ensure tests assert exact artifact/report fields. |
| T029-T041 | No | Cloud Run orchestration, Batch, GEE/rasterio, assembly, Vertex AI, release | `spec.md`; `plan.md`; existing local EVI/base/inference code | Partially Supported | Repo evidence supports local contracts; cloud runtime is new target | Medium | Implement wrappers with clear report evidence and mocked cloud tests. |
| T031-T034 | No | GEE export and rasterio EVI extraction | `EVI/00_ee_export_evi.txt`; `EVI/02_arcpy_extract_evi.py`; reshape tool | Partially Supported | Supports source/names/shape, not rasterio implementation | Medium | Validate rasterio output contract and optional ArcPy/reference differences. |
| T035-T036 | No | Monthly assembly wrapper and validation | `Final_harmonise/...`; `tools/validate_ipcch_schema.py` | Partially Supported | Existing assembly does not directly consume `gs://` or separate EVI long outputs | Medium | Localize inputs and explicitly test EVI feature merge. |
| T037-T039 | No | Vertex AI custom job and model package validation | Local inference CLI/runtime and local prediction headers | Partially Supported | Local inference evidence does not prove Vertex AI runtime compatibility | Medium | Require custom-job manifest/report and local-to-cloud evidence. |
| T040-T057 | No | Release writer, conflict handling, release reader | Current spec/plan only | Partially Supported | New release model; no existing writer | Medium | Use fake object-store generation tests before cloud smoke. |
| T058-T063 | No | Quickstart/docs updates | Plan/tasks | Supported by plan | Documentation should follow implementation details | Low | Update after implementation names are stable. |
| T064-T066 | No | Regression/cloud/artifact validation commands | `tasks.md:144-146` | Not Verifiable Without Execution | Commands not run in this evidence pass | Medium | Execute only after implementation; record results in task notes. |

## Risks

| Risk | Evidence | Severity | Mitigation / Follow-up |
|---|---|---|---|
| Stale validate-only evidence could conflict with current Vertex AI inference scope | Previous evidence says keep prediction generation out of scope, while current spec requires prediction CSVs | High | Treat previous evidence as historical and use this file as feature-local grounding. |
| Cloud platform layer has no current implementation | Negative evidence found no `cloud/`, Dockerfile, GCP clients, Batch, GEE Python, or release writer | High | Implement foundation tasks and mocked/fake cloud tests before live cloud smoke. |
| Rasterio output may differ from ArcPy | Current ArcPy uses `ZonalStatisticsAsTable(..., "DATA", "ALL")`; spec uses rasterio with explicit v1 rules | High | Make output contract hard, numeric comparison advisory unless contract fails. |
| Inference dependencies and geospatial dependencies share one image | Spec/plan choose single-image v1 | Medium | Docker smoke tests should verify entrypoints and dependency import compatibility. |
| Local prediction schema lacks explicit `year`/`month` | Local headers include `feature_period` but not `year`/`month` | Medium | Wrapper must enrich and tests must assert output schema v1. |
| Base assembly does not yet directly consume EVI long cloud outputs | Existing assembly joins scaffold, fixed/slow, and historical/source panel | Medium | Implement cloud assembly wrapper or staged augmented source panel with explicit tests. |
| GCS atomic release semantics are new | No current release writer exists | Medium | Use generation-precondition fake tests and release conflict tests. |

## Open Questions

| Question | Why It Matters | Who / What Can Resolve It | Blocking? |
|---|---|---|---|
| What exact GCP project, bucket, service-account names, image URI/digest, and model package URI will be used? | Needed for live deployment and smoke test | Deployment manifest/operator | No for implementation planning; yes for live run. |
| Will EVI and inference reference samples be supplied for advisory comparison? | Determines whether comparison status is populated or `not_provided` | User/operator | No; spec allows `not_provided` if cloud output contract passes. |
| What cloud-readable geometry packaging will v1 use: zipped shapefile, GeoPackage, or another declared geometry object? | Affects Batch rasterio implementation and checksums | Implementation planning/operator | No if manifest schema allows declared geometry URI; yes before live run. |
| Should monthly assembly merge EVI long outputs into the historical/source panel or append them after base assembly? | Affects T035 implementation shape | Implementation planning | Yes before coding T035. |

## Assumptions

| Assumption | Basis | Confidence | How To Validate |
|---|---|---|---|
| Cloud wrappers will localize GCS inputs to container-internal paths before calling current local-file scripts | Existing scripts are local-path CLIs | Medium | T026/T027 wrapper tests and cloud fake object-store tests. |
| EVI Python export should preserve MOD13A3 collection, EVI band, 1000m scale, and month naming | Existing EE JS export and runbook | High | T046 GEE export manifest tests. |
| `region_id == area_id` is a v1 cloud contract, not a current ArcPy guarantee | Output inventory says mapping may be needed | High | T025/T044 area identity tests. |
| Local inference output headers define required result columns, while cloud release adds `year`/`month` | Local runtime source and prediction headers | High | T027/T038 tests and inference report validation. |

## Implications for Spec

- Current spec should reference this feature-local evidence artifact first.
- Previous `_evidence` artifact should remain historical source evidence only.
- The spec's "new implementation target" labels for Cloud Run, Batch, Docker,
  rasterio, GEE Python, Vertex AI custom job, and release writer are correct.
- Do not reintroduce "validate-only only" or "prediction generation out of scope"
  language for the current feature; only prediction maps, sheets, full delivery,
  model training, non-EVI remote sensing, and external tabular download automation
  remain out of scope.

## Implications for Plan

- The plan is consistent with current spec scope and should be treated as adding a
  new cloud subsystem around existing local contracts.
- Keep local ArcPy and EE JavaScript files as reference/evidence, not runtime.
- Keep cloud IO and release semantics isolated in `cloud/` wrappers to avoid broad
  changes to existing local pipeline scripts.
- Plan validation should distinguish mocked/fake cloud tests from live GCP smoke
  evidence.

## Implications for Tasks

- T031-T034 must preserve EVI output names/shape and explicitly test selected
  month, `region_id == area_id`, empty zones, and immutable raster evidence.
- T035 needs a concrete implementation choice for injecting cloud-produced EVI
  long features into assembly.
- T038 must not pass `--validate-only`, must pass `--no-map`, and must add
  `year`/`month` to prediction CSVs if the local script omits them.
- T043/T051/T059/T064-T066 remain not verifiable until their commands are
  executed after implementation.
- No task is currently checked complete, so there are no unsupported completed
  task claims.

## Suggested References

| Path | Why Include | Reference Type | Needed For |
|---|---|---|---|
| `specs/001-cloud-base-input/evidence.md` | Main current feature evidence artifact | Evidence | plan/tasks/implement/analyze |
| `docs/03_workflow_runbook.md` | Stable workflow contracts and operator sequence | Runbook | EVI/base-input/inference compatibility |
| `docs/04_output_inventory.md` | Stable output inventory, local assets, checksums, remote-sensing shape | Inventory | Manifest and artifact contracts |

## Copy into spec.md

```markdown
## References

- `specs/001-cloud-base-input/evidence.md`
- `docs/03_workflow_runbook.md`
- `docs/04_output_inventory.md`
```
