# Repository Evidence: IPCCH Cloud Monthly Base Input

## Summary

This evidence pack grounds the design in
`docs/superpowers/specs/2026-06-26-ipcch-cloud-monthly-base-input-design.md`.
The current repository already has a local monthly IPCCH base-input workflow,
remote-sensing wide-table contracts, schema validation, source-specific
configuration, fixed-model inference validation, and tests for the main local
contracts. It does not yet contain executable Cloud Run, GCP Batch, Earth Engine
Python SDK, container, GCS run/release manifest, or rasterio/GDAL EVI extraction
implementation.

## Evidence Status

- Status: Ready
- Draft slug: ipcch-cloud-monthly-base-input
- Final Speckit feature directory: Not created yet.
- Feature directory: `specs/_evidence/`
- Evidence artifact path: `specs/_evidence/ipcch-cloud-monthly-base-input.evidence.md`
- Last updated: 2026-06-26
- Scope inspected: cloud monthly base input design, current remote-sensing EVI
  contract, monthly base-input assembly, operational launch validate-only
  contract, config templates, handover docs, tests, schema assets, current model
  artifact package.
- Major unknowns: exact GCP project/bucket/service account names, final cloud
  manifest schema, container/dependency strategy, ArcPy comparison sample
  locations, release approval policy, and whether cloud assembly should reuse
  current scripts directly or wrap/refactor them.

## Validation Status

- Status: Not Applicable
- Tests executed by this pass: None.
- Commands executed: Read-only file/list/search commands only.
- Commands not executed: Unit tests, schema validators, inference CLI,
  Earth Engine exports, GCS commands, GCP Batch, and Cloud Run jobs.
- Artifact outputs inspected: File presence and documentation/manifests only.
- Artifact outputs not inspected: CSV headers/row counts beyond documented
  manifests; prediction outputs; shapefile content; model feature contract
  contents.
- Validation evidence source: Repository docs, source, tests, manifests, and
  user-approved design spec.
- Remaining validation unknowns: Actual cloud credentials, cloud runtime,
  raster extraction numeric agreement, and GCS artifact write/read behavior.

## Acceptance Readiness

- Status: Not Applicable
- Reason: This is a pre-spec evidence pass. Implementation acceptance is not in
  scope.
- Blocking issues: None for evidence grounding.
- Non-blocking risks: The cloud platform layer is new to this repo; no current
  executable pattern exists for containers, GCS manifests, Cloud Run, or Batch.
- Required follow-up before final acceptance: Create Speckit `spec.md`, then a
  plan that explicitly covers the new cloud/runtime artifacts and tests.

## Search Coverage

| Search Term / Method | Purpose | Result | Notes |
|---|---|---|---|
| `find` excluding `.git`, `.agents`, `.codex`, `.worktrees` | Inventory current repo files | Found source workflows, docs, tests, `Outcome/ipcch_unified`, model package, and no top-level Speckit directory | `specs/` and `.specify/` did not exist before this artifact. |
| `Cloud Run`, `GCP Batch`, `rasterio`, `earthengine`, `import ee`, `service account`, `Dockerfile`, `container`, `manifest`, `released/` | Find cloud-platform implementations or docs | Only design docs mention Cloud Run/GCP Batch/rasterio extraction; current executable code has no cloud runtime implementation | `model_pipeline/.../visualization.py` imports `geopandas`, but not for raster extraction. |
| `ipcch_monthly_base_input`, `validate-only`, `model-compatible`, `schema`, `scaffold`, `fixed` | Locate base-input and validation contracts | Found README command, runbook, final assembly CLI, schema validator, inference CLI, and tests | Current base-input target is one monthly CSV plus summary JSON. |
| `EVI`, `ArcPy`, `toCloudStorage`, `gsutil`, `region_id`, `YYYY_MM` | Locate EVI remote-sensing contract | Found EE Code Editor JS, GCS download command, ArcPy extraction script, reshape tool, runbook, output inventory, and tests | Existing EVI extraction writes wide CSVs keyed by `region_id`. |
| `ACLED`, `FAO`, `WFP`, `WB_indicator`, `[tabular]` | Locate tabular source boundaries | Found converted scripts, config template keys, runbook ownership notes, and config-path tests | External downloads remain manual/operator-owned. |

## Negative Evidence / Not Found

| Searched For | Search Method / Terms | Result | Implication |
|---|---|---|---|
| Speckit feature directory | `ls specs`, `ls .specify` | Neither existed | This is Mode 1 pre-spec evidence; draft artifact belongs under `specs/_evidence/`. |
| Cloud Run implementation | `Cloud Run`, `gcloud run`, `run job` | Only design/spec references | Cloud Run orchestration is new scope. |
| GCP Batch implementation | `GCP Batch`, `google.cloud.batch`, `batch_v1` | Only design/spec references | Batch worker and job submission are new scope. |
| Earth Engine Python SDK implementation | `import ee`, `ee.Initialize`, `earthengine` | No executable Python implementation found | Current EE exports are JavaScript snippets for Code Editor. |
| rasterio/GDAL EVI extraction implementation | `rasterio`, `rasterstats`, `shapely`, `geopandas` | No EVI rasterio extraction code found; `geopandas` appears in map rendering/docs/archives | ArcPy replacement must be newly implemented. |
| Container/dependency manifest | `Dockerfile`, `requirements*.txt`, `pyproject.toml`, `environment*.yml`, `cloudbuild*.yaml` | None found in repo scan | Plan must create a dependency/container strategy rather than reuse one. |
| GCS run/release artifact writer | `runs/<feature_month>`, `released/`, `run_id`, `release_manifest` | Only the new design spec mentions these paths | Run/release manifest model is new. |

## Files Inspected

| Path | Symbols / Sections | Type | Why Inspected | Relevant Finding | Implication | Confidence |
|---|---|---|---|---|---|---|
| `docs/superpowers/specs/2026-06-26-ipcch-cloud-monthly-base-input-design.md:8-24` | Purpose | Design spec | Feature source | First phase ends at monthly base input and explicitly excludes full prediction delivery | Keep cloud scope bounded to base input plus validate-only compatibility | High |
| `docs/superpowers/specs/2026-06-26-ipcch-cloud-monthly-base-input-design.md:44-59` | Decisions | Design spec | Feature constraints | Cloud Run, GCP Batch, EVI-only, service account, `runs/` plus `released/`, advisory EVI validation, hard base-input validation | Plan must preserve these decisions unless later clarified | High |
| `README.md:1-5` | Repository purpose | Governance doc | Repo boundary | Repo produces monthly model-compatible IPCCH inputs; prediction step uses weights and model pipeline later | Cloud feature should not redefine repo output as prediction delivery | High |
| `README.md:19-34` | Operational Launch Inference | CLI doc | Existing downstream interface | Fixed model inference command consumes `ipcch_monthly_base_input_YYYYMM.csv`; command writes six delivery files when not validate-only | Cloud base input must remain compatible with this CLI | High |
| `CLAUDE.md:13-20` | Environment and dependencies | Governance doc | Runtime constraints | No project-level dependency manifest; ArcPy required for raster extraction; EE exports are JS snippets; GCS uses `gsutil` | Cloud work introduces new dependency/container conventions | High |
| `CLAUDE.md:115-132` | Remote-sensing raster workflows | Architecture doc | Current raster pattern | Remote sensing follows export/download/ArcPy/wide CSV/final harmonise pattern; EVI writes mean/std CSVs | Cloud replacement should preserve wide contract first | High |
| `CLAUDE.md:151-175` | Shared identifiers and examples | Architecture doc | Active data assets | `Outcome/ipcch_unified` contains active raw/scaffold/spatial/fixed/schema assets; canonical model key is `(area_id, year, month)` | Cloud manifest should version these assets | High |
| `docs/03_workflow_runbook.md:8-18` | EVI | Runbook | Current EVI command/interface | EVI sequence is EE Code Editor, GCS download, ArcPy extraction; outputs are `EVI_mean_extraction_results.csv` and `EVI_std_extraction_results.csv`; normalize with reshape tool | Batch worker should emit same wide outputs and long outputs | High |
| `docs/03_workflow_runbook.md:61-91` | Tabular Feature Workflows | Runbook | Tabular boundaries | Tabular scripts read config-driven raw/scaffold/output paths; external raw inputs must be staged | First cloud phase can consume versioned inputs without automating downloads | High |
| `docs/03_workflow_runbook.md:137-159` | Final Monthly IPCCH Assembly | Runbook | Base-input command | Current command builds `ipcch_monthly_base_input_202604.csv` and summary JSON; output is long monthly table keyed by `area_id`, `year`, `month` | Cloud assembly should keep this output contract | High |
| `docs/03_workflow_runbook.md:161-178` | Operational launch inference | Runbook | Validate-only boundary | `--validate-only` is recommended before full inference | Cloud phase can use validate-only without generating predictions | High |
| `docs/04_output_inventory.md:5-16` | Workflow output contracts | Output contract | Data shape inventory | EVI/FLDAS/GOSIF/VIIRS are wide remote-sensing outputs; unified monthly model input is long keyed by `area_id`, `year`, `month` | Spec/plan should distinguish wide intermediate vs long final base input | High |
| `docs/04_output_inventory.md:20-36` | Required local reference files | Data manifest | Existing assets | Historical panel, scaffold, geometry, fixed/slow features, schemas have documented rows/checksums | Cloud input manifest should carry object paths/checksums/vintages | High |
| `docs/04_output_inventory.md:50-55` | Remote-sensing normalization note | Contract doc | Reshape rules | Wide CSVs keyed by `region_id`; reshape supports `YYYY_MM`, `YYYY.MMM`, `YYYY_MM_Bn`; mapping CSV needed when `region_id` differs from `area_id` | EVI cloud output must decide `region_id` to `area_id` handling | High |
| `config/paths_template.ini:1-41` | `[paths]`, `[production]`, `[identifiers]`, `[schema]`, `[evi]` | Config template | Current local config | Local paths define polygon, scaffold, historical panel, fixed/slow features, model input output, schema, EVI raster/output folder, `zone_field=admin_code` | Cloud manifest can mirror these semantic keys but should use GCS URIs | High |
| `config/paths_template.ini:68-90` | `[tabular]` | Config template | Tabular inputs | ACLED/FAO/WB/WFP raw/scaffold/output paths are configurable | Versioned cloud input manifest should cover these paths if consumed | High |
| `config/ee_gcs_template.ini:1-26` | GCS/EE settings | Config template | Current EE/GCS handoff | Current model assumes operator project/bucket, EE authorization, EVI prefix/date range, VIIRS target month | Service-account cloud config is a new replacement for this operator-local shape | High |
| `docs/01_environment_setup.md:3-14` | Windows and ArcPy | Setup doc | Runtime boundary | ArcPy scripts require Windows ArcGIS Python and Spatial Analyst; preserve Python 2.x-compatible syntax | New rasterio worker can be Python 3, but existing ArcPy files should not be altered casually | High |
| `docs/02_ee_gcs_account_setup.md:1-20` | Account checklist | Setup doc | Current auth model | Current setup uses operator Google account, `gcloud auth login`, `gsutil`, and small test export before production | Cloud service-account auth is new and must be specified/tested separately | High |
| `EVI/00_ee_export_evi.txt:1-40` | EE Code Editor JS | Source snippet | EVI export contract | MODIS/061/MOD13A3 `EVI` band exported to Cloud Storage as `MOD13A3_YYYY_MM` GeoTIFF at scale 1000 | Python SDK implementation should preserve collection, band, naming, scale unless explicitly changed | High |
| `EVI/02_arcpy_extract_evi.py:41-47` | Config loading | Source | Current inputs | Reads EVI raster folder, polygon shapefile, output folder, zone field, filename pattern from config | Batch worker should take equivalent inputs via manifest | High |
| `EVI/02_arcpy_extract_evi.py:77-129` | Zonal extraction and output | Source | ArcPy semantics/output | Uses `ZonalStatisticsAsTable(..., "DATA", "ALL")`, reads `MEAN` and `STD`, writes sorted `region_id` plus `YYYY_MM` columns to two CSVs | Rasterio implementation must define compatible semantics and output shape | High |
| `tools/reshape_remote_sensing_wide_to_long.py:10-31` | Month parsers | Source | Wide-date contract | Supports EVI/VIIRS `YYYY_MM`, GOSIF `YYYY.MMM`, FLDAS `YYYY_MM_Bn` | EVI cloud wide output should use `YYYY_MM` | High |
| `tools/reshape_remote_sensing_wide_to_long.py:34-62` | `_prepare_area_ids` | Source | ID mapping contract | Requires id column, optional mapping, duplicate mapping failure, unmatched mapping failure | Cloud long-output step should reuse or match these error rules | High |
| `tools/reshape_remote_sensing_wide_to_long.py:65-153` | `reshape_wide_table`, CLI args | Source/CLI | Existing interface | Converts wide to `area_id`, `year`, `month`, feature rows; CLI takes `--input-csv`, `--output-csv`, `--feature-name`, mapping args | Cloud pipeline can wrap this tool or port its behavior | High |
| `Final_harmonise/00_build_monthly_ipcch_base_input.py:46-73` | CLI args | Source/CLI | Base-input command interface | Accepts year/month/config/scaffold/historical-panel/fixed-slow/output/summary-output | Cloud assembly can call or adapt this CLI with GCS-localized staging | High |
| `Final_harmonise/00_build_monthly_ipcch_base_input.py:232-307` | `load_scaffold`, `load_fixed_slow` | Source | Hard validation | Scaffold must be one month, no duplicate keys; fixed/slow requires unique `area_id` | These are current hard gates to preserve | High |
| `Final_harmonise/00_build_monthly_ipcch_base_input.py:310-344` | `load_source_slice` | Source | Source slicing | Historical/source panel filtered by target year/month; engineered columns are excluded | Cloud assembly must handle missing target month and exclusions consistently | High |
| `Final_harmonise/00_build_monthly_ipcch_base_input.py:376-461` | `build_monthly_base_input` | Source | Output and summary | Joins scaffold, fixed/slow, source slice; writes CSV and JSON with join/missingness summaries | Cloud output summary should include at least these fields or link to them | High |
| `model_pipeline/run_operational_launch_inference.py:204-216` | CLI parser | Source/CLI | Validate-only interface | CLI requires input/model-package/output-dir/feature-month; has `--validate-only`, `--no-map`, `--overwrite` | Cloud final check can run validate-only and avoid full scoring | High |
| `model_pipeline/run_operational_launch_inference.py:55-69` | validate-only branch | Source | Behavior | Validate-only reads/hash input, validates monthly input, writes run summary, returns before scoring | Confirms validate-only does not generate predictions | High |
| `model_pipeline/ipcch_launch_runtime/adapters.py:21-53` | `validate_monthly_input` | Source | Inference input contract | Requires one feature month and `area_id` or `admin_code`; returns report | Cloud base input must pass this contract | High |
| `model_pipeline/ipcch_launch_runtime/adapters.py:83-143` | Month/id validation | Source | Hard validation | Exactly one feature month, IDs nonmissing, duplicate `area_id` fails, area/admin mismatch fails | Include as acceptance/validation criteria | High |
| `tools/validate_ipcch_schema.py:56-105` | `MODE_CONFIG` | Source/CLI | Schema modes | `model-input-forecast` requires `area_id`, `year`, `month`, nonblank keys, unique key | Cloud hard gate should use this mode | High |
| `tests/test_reshape_remote_sensing_wide_to_long.py:10-107` | reshape tests | Tests | Existing coverage | Tests mapping, EVI `YYYY_MM`, GOSIF, FLDAS bands, CLI writing, duplicate mapping failure | Expand with cloud EVI worker tests rather than replacing this coverage | High |
| `tests/test_build_monthly_ipcch_base_input.py:156-251` | base-input tests | Tests | Existing coverage | Tests observed month, future month with missing source slice, duplicate scaffold failure | Cloud assembly tests should preserve these cases | High |
| `tests/test_operational_launch_cli.py:134-167` | validate-only test | Tests | Existing coverage | Validate-only writes summary and no primary predictions/maps | Supports using validate-only as cloud compatibility check | High |
| `tests/test_operational_launch_input_contract.py:11-199` | input contract tests | Tests | Existing coverage | Covers ID creation, leading zeros, month mismatch, duplicates, missing fields, null tokens | Cloud output must satisfy these constraints | High |
| `tests/test_tabular_config_paths.py:8-91` | config path tests | Tests | Existing coverage | Tabular scripts must use configured file paths and template exposes required options | Cloud manifest should preserve config-driven source indirection | High |
| `model_artifacts/launch_2026_04/model_package_manifest.json:1-32` | package manifest | Artifact | Downstream compatibility | Package is for feature month 2026-04, scopes 0/6/12, package id `launch_2026_04_production_safe` | First cloud phase can validate compatibility but should not own model delivery | Medium |
| `Outcome/ipcch_unified/MANIFEST.md:15-31` | Files table | Manifest | Active asset inventory | Documents historical panel, scaffold, spatial geometry, fixed/slow features, schemas, row counts, checksums | Cloud input object manifest should version these same assets | High |
| `Outcome/ipcch_unified/MANIFEST.md:44-71` | Validation notes | Manifest | Current data constraints | Historical panel covers 2010-01 to 2026-04; scaffold is one target month; schema defines final repo output target | Use as grounding for sample month and asset contracts | High |

## Existing Similar Behavior

| Behavior / Pattern | Source | How It Works | Relevance | Implication |
|---|---|---|---|---|
| Source-specific ordered workflow folders | `CLAUDE.md:111-123`, `docs/03_workflow_runbook.md:8-59` | `00_`, `01_`, `02_` prefixes encode source workflow order; remote sensing produces wide CSVs | Cloud implementation should keep clear step boundaries | Prefer separate Cloud Run orchestration, EVI export, Batch extraction, and assembly modules. |
| Config-driven paths | `workflow_config.py:15-67`, `config/paths_template.ini:1-103` | Scripts load `config/paths.ini` or `IPCCH_CONFIG`, resolve `${PROJECT_ROOT}`, and use named sections | Cloud manifest should be analogous to config, but GCS-based | Avoid hard-coded bucket/object paths in code. |
| Wide remote-sensing to long monthly rows | `tools/reshape_remote_sensing_wide_to_long.py:65-153` | Converts `region_id` wide monthly columns to `area_id/year/month` feature rows | Directly relevant to EVI cloud long outputs | Reuse this utility where possible or preserve exact behavior. |
| Base-input hard gate summary | `Final_harmonise/00_build_monthly_ipcch_base_input.py:430-461` | Summary records input paths, row/column count, key columns, join coverage, missingness | Cloud run summary should include or wrap this summary | Preserve machine-readable QA output. |
| Validate-only downstream compatibility | `model_pipeline/run_operational_launch_inference.py:55-69` and `tests/test_operational_launch_cli.py:134-167` | Inference CLI validates input and writes summary without scoring/prediction outputs | Matches spec non-goal of no prediction delivery | Use validate-only as final compatibility check. |
| Atomic-ish output handling for inference | `model_pipeline/run_operational_launch_inference.py:52-130`, `tests/test_operational_launch_cli.py:286-316` | Writes temp outputs then commits or rolls back primary outputs | Relevant to cloud release safety | Release prefix update should avoid partial published outputs. |

## Related Tests

| Test Path | Behavior Covered | Test Pattern | Missing Coverage | Implication |
|---|---|---|---|---|
| `tests/test_reshape_remote_sensing_wide_to_long.py` | EVI/VIIRS `YYYY_MM`, GOSIF, FLDAS band parsing, `region_id` to `area_id` mapping, CLI output, duplicate mapping failure | Pandas fixtures and temp output files | No raster extraction, no GCS URI handling | Add cloud worker tests for raster-to-wide and manifest-to-reshape integration. |
| `tests/test_build_monthly_ipcch_base_input.py` | Base input assembly, future month with missing source slice, duplicate scaffold failure, summary JSON | Temp CSV fixtures | No GCS manifest, no EVI long injection from cloud output | Add cloud assembly wrapper tests preserving existing behavior. |
| `tests/test_operational_launch_cli.py` | Validate-only behavior, no-map scoring, output collision handling, failed summaries, help command | Mocked scoring and temp files | No cloud-produced input fixture, no GCS paths | Use validate-only as contract test after localizing cloud base input. |
| `tests/test_operational_launch_input_contract.py` | Monthly input ID/month/null/duplicate contract | Pandas fixtures | No full base input schema test | Combine with schema validator in cloud hard gates. |
| `tests/test_tabular_config_paths.py` | Tabular scripts use config keys, not hard-coded filenames | Static source assertions | No cloud manifest equivalent | Add manifest/schema tests for versioned tabular inputs. |

## Existing APIs / Contracts / Schemas

| Item | Source | Current Behavior | Compatibility Concern | Implication |
|---|---|---|---|---|
| EVI wide CSV contract | `EVI/02_arcpy_extract_evi.py:124-129`, `docs/03_workflow_runbook.md:12-18` | Writes `EVI_mean_extraction_results.csv` and `EVI_std_extraction_results.csv` keyed by `region_id` with `YYYY_MM` columns | rasterio semantics may differ from ArcPy | Preserve shape/name; validate numeric differences separately. |
| Remote-sensing long shape | `tools/reshape_remote_sensing_wide_to_long.py:65-116`, `docs/03_workflow_runbook.md:203-213` | Produces `area_id`, `year`, `month`, feature column rows | Mapping is needed if `region_id` differs from `area_id` | Cloud EVI long output should be produced through this contract. |
| Monthly base input CLI | `Final_harmonise/00_build_monthly_ipcch_base_input.py:46-73` | Builds one target month from scaffold, historical panel, fixed/slow features, explicit output and summary paths | Current code reads local paths, not GCS | Cloud wrapper needs staging/localization or refactor to GCS-aware IO. |
| Schema validator | `tools/validate_ipcch_schema.py:98-104` | `model-input-forecast` requires nonblank unique `area_id/year/month` keys | Validator reads local CSV only | Cloud hard gate can run after localizing/downloading run artifact. |
| Inference input contract | `model_pipeline/ipcch_launch_runtime/adapters.py:21-53` | Validates monthly input, feature month, IDs, null tokens, duplicate ids | Full inference expects local CSV path | Cloud validate-only check likely needs local staging path inside job. |
| Model package | `model_artifacts/launch_2026_04/model_package_manifest.json:1-32` | Feature month 2026-04; scopes 0/6/12; selected numeric features by scope | First phase does not own full scoring | Keep as downstream compatibility artifact only. |

## Data Models / Persistence

| Model / Storage Area | Source | Current Pattern | Migration / Compatibility Concern | Implication |
|---|---|---|---|---|
| Active IPCCH package | `Outcome/ipcch_unified/MANIFEST.md:15-31` | Local assets with documented row counts and SHA-256 hashes | Cloud version must preserve asset identity and checksums | GCS input manifest should include object URI plus checksum/version. |
| Historical panel | `Outcome/ipcch_unified/MANIFEST.md:17`, `Final_harmonise/00_build_monthly_ipcch_base_input.py:310-344` | Large local CSV, 2010-01 through 2026-04, filtered by target month | Large object staging into Cloud Run may be costly | Plan should decide whether to pre-slice or stage full object. |
| One-month scaffold | `Outcome/ipcch_unified/MANIFEST.md:18`, `docs/03_workflow_runbook.md:65-73` | Current example 2026-04; can be generated by scaffold tool | Cloud phase must support 1-3 months while base input remains one month per output | Define per-feature-month scaffold artifact(s). |
| Geometry | `Outcome/ipcch_unified/MANIFEST.md:24`, `docs/04_output_inventory.md:27` | Shapefile package with sidecar checksums | Batch worker needs cloud-readable geometry package | Prefer versioned zipped shapefile or GeoPackage in manifest. |
| Released prediction outputs | `Outcome/ipcch_unified/predictions/202604/*` from file inventory | Local prediction outputs already exist | First cloud phase excludes prediction delivery | Avoid treating predictions as required outputs for this feature. |

## Auth / Validation / Error Handling / Observability Patterns

| Concern | Source | Existing Pattern | Required Follow-up |
|---|---|---|---|
| Auth | `docs/02_ee_gcs_account_setup.md:5-16` | Human/operator account, Earth Engine authorization, `gcloud auth login`, `gsutil ls`, small test export | Define service account IAM and Earth Engine authorization path. |
| Local config failure | `workflow_config.py:22-40` | Missing config raises a RuntimeError naming `config/paths_template.ini` and `IPCCH_CONFIG` | Cloud manifest parser should fail with similarly actionable messages. |
| Base-input hard failures | `Final_harmonise/00_build_monthly_ipcch_base_input.py:207-224`, `232-307`, `427-428` | Missing files/columns, bad scaffold month, duplicate keys fail via `SystemExit` | Preserve as hard gates in cloud run. |
| Base-input warnings | `Final_harmonise/00_build_monthly_ipcch_base_input.py:491-502` | Source/fixed-slow unmatched rows print warnings after output writes | Cloud summary should encode warnings as machine-readable status. |
| Inference expected errors | `model_pipeline/run_operational_launch_inference.py:132-153`, `307-315` | Expected errors write failed run summary; unexpected errors include traceback | Cloud orchestrator should write run summary on both expected and unexpected failures. |
| Validation docs | `docs/04_output_inventory.md:74-117` | Provides example CSV/schema validation commands | Speckit plan should choose which validations become automated gates. |

## Architecture Constraints

| Constraint | Source | Implication | Risk |
|---|---|---|---|
| Current repo final product is monthly model-compatible input, not predictions | `README.md:3-5`, `CLAUDE.md:5-9`, `docs/06_weilun_deliverable_gap_audit.md:10-12` | Keep first cloud phase ending at base input plus validate-only | Scope creep into delivery maps/predictions. |
| ArcPy scripts require Windows ArcGIS/Spatial Analyst | `docs/01_environment_setup.md:3-14`, `CLAUDE.md:17` | Cloud EVI worker must not depend on ArcPy | Numeric behavior must be revalidated. |
| No dependency/container manifest exists | `CLAUDE.md:15`, repo file inventory | Container/dependency setup is new | Plan must introduce dependency lock/build/test strategy. |
| Existing EE scripts are Code Editor JavaScript | `CLAUDE.md:19`, `EVI/00_ee_export_evi.txt:1-54` | GEE Python SDK implementation is new | Need verify equivalent export naming/date/scale behavior. |
| Tabular raw refresh is operationally manual | `docs/03_workflow_runbook.md:93-118`, `docs/04_output_inventory.md:57-72` | First cloud phase should consume versioned inputs, not scrape/download all sources | Missing versioned upload convention could block cloud assembly. |
| Large raw and geometry assets are local handover assets | `Outcome/ipcch_unified/MANIFEST.md:70-71`, `docs/04_output_inventory.md:38-42` | Cloud pilot needs explicit GCS staging and checksums | Missing cloud data staging may block pilot. |

## Risks

| Risk | Evidence | Severity | Mitigation / Follow-up |
|---|---|---|---|
| Cloud platform layer has no existing implementation pattern | Negative search found no Cloud Run, Batch, Dockerfile, dependency manifest | High | Plan a small scaffold first: manifest parser, local fixture tests, container smoke before cloud pilot. |
| EVI rasterio results may differ from ArcPy | Spec chooses advisory validation; ArcPy code uses `ZonalStatisticsAsTable(..., "DATA", "ALL")` | High | Define pixel inclusion, CRS, nodata, scaling, and ArcPy sample comparison report. |
| Current assembly reads local files only | `Final_harmonise/00_build_monthly_ipcch_base_input.py:46-73`, `151-204` | Medium | Cloud job should stage GCS inputs locally or introduce narrow IO adapters. |
| External tabular data may lack cloud versioning convention | Runbook notes manual downloads/filters and ownership | Medium | Create upload manifest requirements before relying on versioned tabular inputs. |
| Historical panel is large | `Outcome/ipcch_unified/MANIFEST.md:17` | Medium | Consider target-month slice artifact rather than full-object download in Cloud Run. |
| Service account Earth Engine setup is not documented in current repo | Current docs are operator-account based | Medium | Add setup docs/tests for service account authorization and bucket IAM. |

## Open Questions

| Question | Why It Matters | Who / What Can Resolve It | Blocking? |
|---|---|---|---|
| What GCP project, bucket, and service account will be used? | Required for manifest schema, IAM, and pilot | User/GCP admin | Yes for implementation; no for evidence |
| Where are ArcPy comparison EVI samples stored and which months should be used? | Required for advisory validation report | User/current data owner | Yes for validation design |
| Should the cloud assembly run current scripts after localizing GCS inputs, or refactor IO to support GCS directly? | Determines task shape and blast radius | Plan decision | Yes for implementation plan |
| Should the cloud pipeline produce one base input per feature month or one run with multiple feature-month outputs? | Spec says 1-3 sample months and monthly base input; execution layout needs precision | Speckit clarify/spec | Yes |
| What are the advisory threshold defaults for EVI validation? | Needed for warnings/release manifest | User/domain review | No for initial scaffolding, yes for pilot acceptance |
| How should `released/` be updated atomically in GCS? | Avoid partial published outputs | Plan/design | Yes for release tasks |

## Assumptions

| Assumption | Basis | Confidence | How To Validate |
|---|---|---|---|
| Cloud execution will stage large GCS inputs to local scratch before calling current local-file scripts | Current scripts use local paths; no GCS IO adapters exist | Medium | Prototype with small fixture and decide in plan |
| EVI GeoTIFF export naming should stay `MOD13A3_YYYY_MM` | Existing JS export and ArcPy parser depend on this | High | Compare Python SDK export object names to current filename parser |
| `region_id` should remain the EVI wide-table id column even if sourced from `admin_code` | Current ArcPy output writes `region_id`; reshape defaults to `region_id` | High | Confirm downstream mapping needs for current geometry |
| The first cloud pilot can use 2026-04 as one sample month | Existing scaffold/base input/model package use 2026-04 | Medium | User chooses exact sample months |

## Implications for Spec

- The Speckit `spec.md` should reference the existing superpowers design and
  this evidence artifact.
- Functional requirements should preserve existing output contracts:
  `EVI_mean_extraction_results.csv`, `EVI_std_extraction_results.csv`,
  EVI long `area_id/year/month` outputs, `ipcch_monthly_base_input_YYYYMM.csv`,
  and `_summary.json`.
- Requirements should explicitly state that Cloud Run, Batch, GEE Python,
  service-account IAM, GCS run/release manifests, and rasterio extraction are
  new implementation areas.
- Requirements should keep prediction generation out of scope, while requiring
  `--validate-only` compatibility.

## Implications for Plan

- Plan must introduce a dependency/container strategy because none exists.
- Plan should prefer narrow adapters around existing local-file scripts unless
  GCS-native IO is deliberately chosen.
- Plan must include fixture-based tests for manifest parsing, GCS URI handling,
  EVI raster fixture extraction, wide-to-long compatibility, base-input schema
  validation, and validate-only CLI compatibility.
- Plan must include an explicit data staging story for large `Outcome` assets
  and IPCCH geometry.

## Implications for Tasks

- Add tasks to define the cloud manifest schema before implementing Cloud Run
  orchestration.
- Add tasks to create/validate a versioned cloud geometry package.
- Add tasks to implement EVI EE Python export with current collection/band/name
  contract.
- Add tasks to implement the Batch EVI worker and compare outputs to ArcPy
  samples.
- Add tasks to wrap or adapt monthly assembly with localized cloud inputs.
- Add tasks to generate run and release manifests and avoid partial release
  updates.
- Add tasks to run existing unit/contract tests plus new cloud fixture tests.

## Suggested References

| Path | Why Include | Reference Type | Needed For |
|---|---|---|---|
| `specs/_evidence/ipcch-cloud-monthly-base-input.evidence.md` | Main feature evidence artifact | Evidence | plan/tasks/implement |
| `docs/superpowers/specs/2026-06-26-ipcch-cloud-monthly-base-input-design.md` | User-approved design and scope decisions | Design | spec/plan |
| `docs/03_workflow_runbook.md` | Current commands, workflow steps, expected outputs, smoke tests | Runbook | spec/plan/tasks |
| `docs/04_output_inventory.md` | Output contracts, active assets, checksums, validation examples | Contract | spec/plan/tasks |
| `Final_harmonise/00_build_monthly_ipcch_base_input.py` | Current base-input CLI and validation behavior | Source contract | plan/tasks |
| `tools/reshape_remote_sensing_wide_to_long.py` | Existing remote-sensing wide-to-long contract | Source contract | plan/tasks |
| `model_pipeline/run_operational_launch_inference.py` | Existing validate-only compatibility interface | Source contract | plan/tasks |
| `tests/test_reshape_remote_sensing_wide_to_long.py` | Existing remote-sensing contract tests | Tests | tasks |
| `tests/test_build_monthly_ipcch_base_input.py` | Existing base-input assembly tests | Tests | tasks |
| `tests/test_operational_launch_cli.py` | Existing validate-only/no-output behavior tests | Tests | tasks |

## Copy into spec.md

```markdown
## References

- specs/_evidence/ipcch-cloud-monthly-base-input.evidence.md
- docs/superpowers/specs/2026-06-26-ipcch-cloud-monthly-base-input-design.md
- docs/03_workflow_runbook.md
- docs/04_output_inventory.md
```

Expected final path after `/speckit.specify`, when applicable:
`specs/<feature>/evidence.md`.
