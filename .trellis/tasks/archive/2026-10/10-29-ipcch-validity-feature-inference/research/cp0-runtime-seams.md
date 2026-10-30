# Research: CP0 runtime seams for implement.md steps 4-11

- **Query**: Map implement.md steps 4-11 onto concrete `cloud_pipeline/` code seams (request contract, publication, prepare, inference, diagnostics, package/asset layout, locks/object store, test suites); flag hard-coded 6,227 roster / (0,6,12) horizons / H0-only assumptions.
- **Scope**: internal (read-only inspection; no tests executed, only `pytest --collect-only`)
- **Date**: 2026-10-30
- **Base**: branch `feat/ipcch-validity-feature-inference`, HEAD `ace3e12`; all paths below are relative to `cloud_pipeline/` unless prefixed.

## Findings

### Files Found

| File Path | Lines | Role for this task |
|---|---|---|
| `cloud/orchestrator/delivery_manifest.py` | 510 | v1 request contract, structural validators, ref identity check |
| `cloud/orchestrator/delivery_job.py` | 731 | Cloud Run job: execute/prepare_inputs/inherit_system/package/upload/admit/resolve |
| `cloud/orchestrator/delivery_run.py` | 115 | `_RUN_ACQUIRED` sentinel (`run_once`), release record + `current.json` CAS (`publish`) |
| `cloud/orchestrator/prepare.py` | 809 | Cross-system remote-sensing preparation (plan -> Batch extract) |
| `cloud/batch/remote_sources.py` | 416 | Source contracts (GOSIF v3/v2), `http_published_months`, `SYSTEM_FAMILIES` |
| `cloud/orchestrator/deliver.py` | 425 | Per-system assembly + scoring + diagnostics + scope tables |
| `cloud/orchestrator/delivery_scoring.py` | 178 | `score_ipcch` / `score_fewsnet`; HORIZONS (0,6,12) |
| `cloud/orchestrator/delivery_inputs.py` | 469 | IPCCH base series, origin rows, chunked assembly |
| `cloud/orchestrator/delivery_outputs.py` | 743 | Diagnostics (confidence, maximum phase), evidence validation, `validate_ipcch_phases` |
| `cloud/orchestrator/delivery_bundle.py` | 690 | Bundle validation/inventory/archive/rescore, inherited identity checks |
| `cloud/orchestrator/causal_fill.py` | 279 | Carry-forward + `bind_model_features` (horizon (0,6,12) gate) |
| `cloud/common/object_store.py` | ~215 | `ObjectStore` protocol, `LocalObjectStore` fake, `GCSObjectStore` |
| `model_pipeline/ipcch_launch_runtime/inference.py` | 242 | Scoring, nonfinite check, monotonicity, phase decode |
| `model_pipeline/ipcch_launch_runtime/model_package.py` | 100 | `load_scope_package` (scope_{n}m, XGBRegressor JSON) |
| `model_pipeline/ipcch_launch_runtime/feature_contract.py` | 501 | `apply_feature_contract` (ordering, categories, coercion) |
| `model_pipeline/run_operational_launch_inference.py` | 325 | `run_scope`, `add_calendar_months`, `SCOPES=(0,6,12)` |
| `tools/revise_h5_country_v3.py` | ~100+ | SEED/REPLICATES/PERCENTILES, confidence thresholds, `maximum_phase_uncertainty` |
| `tools/refresh_h5_inputs.py` | - | `wfp_aggregates`, `conflict_aggregates` (CP1 converters, both systems) |
| `pipeline.py` | 1715 | Operator CLI: init/run/status/download/models/verify/maintenance/promote |
| `deploy/workflow.yaml` | 345 | Eventarc -> Workflows routing (hold, claim, admit/resolve/run) |
| `bootstrap/baseline.json`, `bootstrap/models/ipcch/`, `bootstrap/assets/`, `bootstrap/evidence/` | - | Current package/asset/evidence layout |
| `OPERATIONS.md:139-170` | - | Operator doc for `operator-model.json` and evidence |

### Step 4 - Request contract v2 (B)

Current v1 contract (`cloud/orchestrator/delivery_manifest.py`):
- `SCHEMA_VERSION = "fewsnet-ipcch-delivery-request-v1"` (:27); `SYSTEMS=("fewsnet","ipcch")` (:28); `HORIZONS_MONTHS=(0,6,12)` (:29); `SOURCE_ACTIONS=("keep","refresh")` (:30); `RAW_CONVERTER_CONTRACT_VERSION="september-h5-raw-converter-v1"` (:31); `LEGACY_RELEASE_NAMESPACE="released"` (:54); `TOP_LEVEL_FIELDS` (:55-72), `execution` optional (:112-113).
- `validate_delivery_request(data, *, request_uri, request_generation, expected_release_namespace)` (:98-165): exact-keys, schema_version equality (:114-115), run_id regex + path binding (:117-127), `origin_month` (:129), `systems` exact (:130), `horizons_months` exact (0,6,12) (:131), resolved-request rules (:133-141), `prepared_snapshot` origin equality (:142-148), `acled`/`wfp` `_source_choice` (:150-151), `_models` (:153), `_assets`, `_diagnostics`, `_contracts`, `_runtime`, `_release`, operator, `prepared_at` (:154-160). Returns `validation_level="structural"` (:164).
- `_execution` (:173-205): fields `remote_update, inference_systems, prepare_request, inherit, publication` (:168); `inherit` must name exactly the unscored systems (:193-195); **same-origin gate** `execution.inherit.{system}.origin_month != origin` -> error (:199-200); `publication in ("candidate","current")` (:170, :203-204). No mode field, no wall-clock/current-M comparison anywhere in the module.
- `_source_choice` (:289-299): `keep -> retained_snapshot`, `refresh -> raw_upload`, plus `converter_contract.version` pinned.
- `_models` (:302-328): requires exactly 6 entries covering SYSTEMS x HORIZONS_MONTHS (:321-323), each with `feature_schema_sha256`, distinct package ids per system (:324-327).
- `_diagnostics` (:339-407): all (system,horizon,family) required (:398-407); `available` evidence must name `models[(system,horizon)]` package id (:391-392); `frozen_output` FEWS-only, `APPROVED_PROXY_EVIDENCE` (:372-385).
- `_release` (:425-437): namespace label, rejects `released` (:430-431), `expected_pointer_generation` "0" or integer.
- `iter_object_refs` (:216-249) and `verify_reference_identities(request, resolve)` (:252-272): every ref checked at pinned generation/sha256 via an injected resolver.
- `selected_systems` (:208-213): legacy (no execution) = both.

Where requests are routed / validated:
- `deploy/workflow.yaml`: event filter on `^requests/<run_id>/run_manifest.json$` (:46-51), maintenance hold read (:58-83), create-only `dispatch/<run_id>/claim.json` (:84-104), parse intent (:105-117), route on `execution == null` or `not execution.remote_update` -> `run_job` (:118-126), else `admit` -> prepare job -> `resolve` (:127-244), `run_job` invokes `delivery_job run` (:245-255). **Routing keys on presence of `execution` / `remote_update`, not on `schema_version`.**
- `delivery_job.execute(...)` (:475-537): calls `validate_delivery_request` (:483-485) then `run_once` (:537). `delivery_job.main` subcommands `run|admit|resolve|system` (:669-727).
- `delivery_job._remote_intent` (:543-553) and `admit_intent` (:556-578) also call `validate_delivery_request`; admit cross-checks the prepare request per system roster/geometry (:570-573).
- `pipeline.py submit_intent` (:769-828) builds the request and validates it locally (:814-819) before `put_json` to `requests/<run_id>/run_manifest.json` (:813, :825). `pipeline.delivery_request` (:684-735) fills `assets`, `acled`/`wfp` (keep -> `refs["assets/retained_{family}.csv"]`, refresh -> uploaded raw) (:716-727) and `release.expected_pointer_generation` from current pointer (:728-734). `execution_options` (:738-766) default = both systems, remote on, `publication: current`.
- `pipeline.py` CLI `run` args (:1653-1669): `--month --cutoff --deadline --run-id --remote-update --infer --prepared-manifest --inherit --inherit-manifest --inherit-archive --publication --acled/--acled-raw --wfp/--wfp-raw`.
- Prepare-request validator `prepare.validate_prepare_request` (:142-190) reuses `_exact_keys/_month/_ref/_text/_timestamp` from delivery_manifest and requires `systems` == both (:169-178).

Seam notes for step 4:
- A version router would sit at the top of `validate_delivery_request` (:114) or in a wrapper called from `delivery_job.execute` (:483), `_remote_intent` (:547), and `pipeline.submit_intent` (:814). The workflow (`deploy/workflow.yaml:118-126`) reads `execution.remote_update` from the raw JSON, so a v2 shape without that field would route to `run_job` unless the workflow is changed (UNVERIFIED how the team intends to route v2 in Workflows).
- The v1 FEWS-only path's `execution.inherit.ipcch` requires `origin_month == origin` at validation (:199-200) and again at `inherit_system` (see step 9).

### Step 9 - Publication (D)

- `delivery_run.request_from_event` (:38-47) exact event generation.
- `delivery_run.run_once` (:54-78): create-only `runs/<run_id>/_RUN_ACQUIRED` with `{run_id, request{uri,generation,sha256}}`; identical replay returns original status; different content -> `RunConflict`; failed -> `run_status.json` with `status: failed`, re-raised; no resume.
- `delivery_run.publish` (:92-115): rejects `namespace == "released"` (:95-96); `validate()` first (:97); precheck pointer generation vs expected -> `_record_conflict(... stage="precheck")` (:100-103); create-only `{root}/{namespace}/releases/{run_id}/release.json` (:104-106); pointer `{root}/{namespace}/current.json` written with `if_generation_match=int(expected)` (:107-110); `GenerationConflict` -> `release_conflict.json` + `ReleaseConflict` (:111-114). No automatic retry exists. The pointer body is `{run_id, release_record, release_record_generation}` (:107) - activation identity is not currently part of the pointer or record.
- Release record built in `delivery_job.execute` (:513-517): `run_id, request, origin_month, manifest, archive, validation`, optional `execution{scored_systems, inherited_systems}`. Single `origin_month` for the whole release.
- Candidate path `delivery_job.execute` (:524-531): writes create-only `{output_root}/candidates/{run_id}/candidate.json`, no pointer move.
- `delivery_job.inherit_system(out, system, source, downloader, *, origin, package_dirs)` (:346-408): copies members matching `INHERITED_MEMBERS[system]` regex (:336-342) plus `INHERITED_PACKAGE_PREFIX` (:343) byte-for-byte with inventory hash check (:372-374); **same-origin gate** `source_delivery["origin_month"] != origin` (:386-387); requires all (0,6,12) scope tables (:388-390); checks `feature_period == origin` and `target_period == origin+h` (IPCCH) for h in (0,6,12) (:391-398); **installed-package equality** `package != installed` (:399-404).
- `delivery_job.package_delivery` (:411-439): writes `reports/delivery.json` with single `origin_month` and `execution` block (:418-425), `reports/inherited_members.json` (:426-428), installs runtime/models, inventory, archive.
- `delivery_bundle._content_checks` (:171-217) reads one `origin_month` from `reports/delivery.json` (:179) and requires every IPCCH scope table to have `feature_period == origin` and `target_period == origin+h` (:209-216) for both systems, including inherited ones. `rescore` (:517-585) and `_diagnostics_regeneration_checks` (:471+) also use that single origin. `_inherited_identity_checks` (:592-620) compares inherited members to recorded digests.
- Promote / resume entrypoints:
  - `pipeline.promote(args, cfg, ...)` (:1413-1512): requires maintenance operation phase and hold (:1422-1429), a passed verification receipt for the run's `candidates/<run_id>/candidate.json` (:1430-1435), pointer equals the run's recorded `expected_pointer_generation` (:1438-1447), then `_publish_resumable` (:1394-1410) re-uses an identical release record and repeats the pointer CAS; then config/fallback renames. Uses `status(...)["candidate"]` (:598). No contract-version discrimination exists.
  - `pipeline.run` resume (:679-680): returns status when `phase == "submitted"`; never resubmits.
  - `pipeline.verify_candidate` (:923+) and `download --candidate` (:852+) read candidate records.
  - `deliver.py` checkpoint "resume" (:242-313) is a FEWS assembly checkpoint, unrelated to publication.
- Legacy IPCCH release root: reserved namespace `released` rejected in three places: `delivery_manifest._release` (:430-431), `delivery_run.publish` (:95-96), `pipeline.config` (:81-85).

### Step 4/9 - Locks and sentinels (R50)

Existing create-only mechanisms (no per-system lock exists; `grep locks/` finds nothing):
- `runs/<run_id>/_RUN_ACQUIRED` (`delivery_run.py:58-61`).
- `prepared/<prepare_id>/_PREPARE_ACQUIRED` and `_EXTRACT_ACQUIRED` (`prepare.py:203`, `:296`, `_acquire_sentinel` :465-469 -> `PreparationConflict`).
- `dispatch/<run_id>/claim.json` (`deploy/workflow.yaml:84-104`), `dispatch/<run_id>/{admission,resolution}.json` (`delivery_job.dispatch_step` :633-666).
- `maintenance/hold.json` (`pipeline.py:19`, `require_admission` :843-849; workflow :58-83) - admission allowlist, not a per-system lock.
- `resolved_requests/<run_id>/run_manifest.json` create-only (`delivery_job.resolve_intent` :617-624).
- `candidates/<run_id>/candidate.json` create-only (`delivery_job.py:527`).
All use `store.write_text(..., if_generation_match=0)` against the `ObjectStore` protocol, so a `locks/{system}` object would fit the same primitive; deletion-by-generation exists only on `pipeline.Cloud.delete` (:156-157), not on the `ObjectStore` protocol.

### Object store abstraction and fakes

- `cloud/common/object_store.py`: `ObjectStore` Protocol (`write_text`, `read_text`, `get_metadata`, `list`, `copy`) (:18-35); `GenerationConflict` (:8); `LocalObjectStore` filesystem fake with GCS-like generation preconditions (:38-99; generations kept in memory per instance, `gs://` URIs only); `GCSObjectStore` (:102+). No `delete` on the protocol.
- Test fakes: `tests/test_operator_release.py:119` `StoreCloud` ("Operator cloud fake on LocalObjectStore: create-only puts, generations, CAS, deletes"); `tests/cloud/test_delivery_job.py:21,32` `FakeBlob`/`FakeClient` (GCS client fake for `PinnedDownloader`); `tests/cloud/test_object_store.py:14-55` `FakeBlob/FakeBucket/FakeStorageClient`; `tests/cloud/test_prepare.py:72-80` `FakeBucket/FakeBlob`; `tests/cloud/test_cloud_batch_evi_worker.py:13` `FakeBatchClient`. `delivery_job.LocalPinnedReader` (:98-106) is a local pinned reader. `tests/test_operator_cli.py` uses a fake cloud with `fail_request` (:233).

### Step 5 - Prepare coupling / GPP (C)

- `prepare.plan_prepare` (:199-288) loads rosters for **both** SYSTEMS (:209) and iterates `FAMILIES=("evi","fldas","gosif_mean","gosif_sd","viirs")` (:75, :211), with per-family systems from `SYSTEM_FAMILIES` (:212). One `prepare_id`, one plan, one Batch job covers both systems. `validate_prepare_request` requires both systems' geometry/roster/history (:169-178).
- `_extract` (:309-403) writes `features/{system}/{family}.csv`, `source_coverage.csv` (:383-384), `area_latest_observation.csv`, `prepared_manifest.json` (:387-402); `not_published_months` recorded per family (:270, :338-341, :379) with coverage status `not_published`.
- `delivery_job.check_prepared_snapshot` (:182-199) requires roster/geometry sha for every system in `request["assets"]` and every `SYSTEM_FAMILIES[system]` output.
- `remote_sources.py`: `EXTRACTION_CONTRACT_VERSION="current-repo-remote-scripts-v2"` (:38), accepted v1/v2 (:41); `GOSIF_V3_BASE_URL` (:52); `MODEL_COLUMN_MAPPING["ipcch"]` incl. `GPP_mean <- GPP_Mean__mean`, `GPP_std <- GPP_SD__mean`, `nightlight_mean <- avg_rad__sum` (:61-68); `SOURCE_CONTRACTS["gosif_mean"]` v3 mean URL, `first_month="2025-01"` (:103-109); `gosif_sd` v2 SD from 2000-03 (:110-114); `SYSTEM_FAMILIES` derived from mapping (:123-127) -> IPCCH consumes gosif_sd, FEWS does not.
- `http_published_months(head, url_template, candidate_months)` (:207-228): 200 -> published, 404 -> omitted (unpublished), any other status or exception -> `SourceRetrievalError`. `CloudSourceAcquirer.latest_published` walks back month by month with HEAD (`prepare.py:574-585`); `published_months` (:587-593).
- No GPP availability ledger exists; "not published" lives only in the prepared manifest/coverage CSV per preparation.

### Step 7/8 - Inference seams (D)

- `deliver._ipcch` (:195-221): **H0-only source-column selection** `contract = pd.read_csv(package_root / "scope_0m/feature_contract.csv")` (:203); `wanted = IPCCH_IDENTITY | contract["source_column"]` (:205); single `origin` feature month for all scopes (:208-215); `ds.score_ipcch(rows, package_root, origin=origin, ...)` (:215); `training_cutoff` from root `model_package_manifest.json` (:221 -> `delivery_outputs.ipcch_training_cutoff_month` :195-198, one value for all scopes).
- `deliver.deliver` (:106-139): `targets = {h: origin+h for h in HORIZONS}` (:120).
- `delivery_scoring.score_ipcch` (:155-178): loops `HORIZONS=(0,6,12)` (:43, :160); `final_missing` from contract source columns (:165-167); `run_scope(... feature_month=origin, scope_months=scope, target_month=origin+scope ...)` (:170-173); dependencies are `(source, (0,))` only (:177).
- `run_operational_launch_inference.run_scope` (:157-196): `load_scope_package` -> `apply_feature_contract` -> `inference.score_scope` with `monotonicity_policy` from metadata (default `cummax`) (:179).
- `inference.score_scope` (:33-99): raw scores unclipped; `_predict_scores` (:163-186) raises `InferenceError` on NaN/inf (message names target only, not area); thresholds from metadata (`thresholds.default=0.2` in current package); `_apply_monotonicity_policy` cummax on `_pred` columns (:213-218); `_decode_overall_phase` (:233-242); writes `feature_period`, `target_period`, `scope_months`, `model_package_id`, `source_input` (:80-84).
- [1,5] gate: `delivery_outputs.validate_ipcch_phases` (:482-492), called from `scope_diagnostics` when maximum_phase available (:697-698) and from `delivery_bundle._content_checks` (:210).
- `model_package.load_scope_package(package_root, scope_months)` (:21-79): requires `scope_{n}m/{feature_columns.json, feature_contract.csv, model_metadata.json, phase{2..5}_worse_model.json}`; loads with `xgboost.XGBRegressor().load_model` (JSON). `.ubj` would need conversion or a loader change (research-side conversion is planned in design.md).
- `feature_contract.apply_feature_contract` (:13-163): reorders to `feature_columns` order (:163); rejects duplicate feature names (:35-36) and duplicate contract rows (:66-75); categories `required` (NaN passthrough; **synthesizes an all-NA column when source absent and not required_in_input** :189-191), `static_join`/`carry_forward`, `median_impute` (:208-217), `derived` unsupported (:219-222); `_numeric_series` rejects unparseable text (:372-385); **no explicit +/-inf rejection in feature_contract.py** (no isinf/isfinite found); missing-rate tolerance gate (:130-135). Current IPCCH contracts: all 128 rows `median_impute`, `required_in_input=True`, `missing_tolerance=0.0`.
- `adapters.validate_monthly_input` (:21+) rejects duplicate `area_id` (:133-135) and validates feature month.
- Equal-schema replacement gate: `pipeline.models(... register)` reads `package/operator-model.json` (:1520), `validate_model(..., load=True)` (:1523; body :183-281), then `if old["feature_schema_sha256"] != model["feature_schema_sha256"]: raise "replacement feature schema is incompatible"` (:1529-1530). `validate_model` IPCCH required members (:240-251), schema via `delivery_job.package_schema_sha256` = sha256 of `scope_{h}m/feature_contract.csv` bytes (`delivery_job.py:134-139`). `shared_members` (:284-292) and `materialize_package` (`delivery_job.py:126-129`) require byte-identical shared IPCCH root members across scopes.
- `operator-model.json` format (`OPERATIONS.md:144-155`, structure = a `bootstrap/baseline.json` `models[]` entry): `system, horizon_months, package_id, feature_schema_sha256, manifest{schema_version: delivery-package-manifest-v1, files[{path, sha256}]}, environment{image_uri, requirements_lock_sha256}, acceptance{delivery-model-acceptance-v1 ...}, diagnostics` (optional).
- Acceptance checks at delivery time: `delivery_job.check_acceptance` (:147-159), `check_environment` (:162-168), `materialize_package` (:109-131), schema re-check after all scopes materialized (:246-251).

### Step 8 - Diagnostics and evidence format (for research-side compatibility)

- Declarations: request `diagnostics[]` -> `deliver.request_diagnostics` (:54-84) reads `evidence_bytes` at pinned generation; `deliver._write_scopes` (:370-425) per horizon calls `delivery_outputs.scope_diagnostics(...)` (:403-408) with `package_id = summary.model_package_id + "/scope_{h}m"` (:393).
- `scope_diagnostics` (:616-731): sha256 of evidence bytes must equal ref (:634-635); families `polygon_training_errors` + `country_confidence` (both parsed with `area_evidence`) and `maximum_phase` (`residual_evidence`) for IPCCH.
- Evidence self-identity `_evidence_identity` (:295-340): constant columns `model_package_id, horizon_months, basis, period` (:173); must equal scored package/horizon and the declaration (:314-319); IPCCH basis must be `training_resubstitution` (:182, :326-329); `period` `YYYY-MM..YYYY-MM` ending <= origin (:330-333) and <= package `training_cutoff` month (:334-336).
- Area evidence (`area_evidence` :351-367): columns `polygon_id, sample_count, error_count` (:174) non-negative integers, `error_count <= sample_count`, unique roster ids (`_roster_ids` :343-348: polygon ids must be in roster; roster subset allowed).
- Residual evidence (`residual_evidence` :370-390): `polygon_id, target_month, phase2_worse_residual..phase5_worse_residual` (:176), unique (polygon_id,target_month), target months within period, finite values.
- Maximum phase (`maximum_phase_diagnostics` :393-420): residual field added to current raw scores, decoded with `decode_cumulative_phase` (>=0.2 cascade, `tools/revise_h5_country_v3.py:25-29`), complete months only (:413), `np.random.PCG64(SEED)`; `SEED, REPLICATES, PERCENTILES = 20260923, 10000, (2.5, 97.5)` (`tools/revise_h5_country_v3.py:9`); `maximum_phase_uncertainty` statuses no_complete_history / single_month / degenerate_empirical / supported (:70-91).
- Country confidence: `weighted_country_errors` (`tools/revise_h5_country_v3.py:32-67`) exact Fraction arithmetic; thresholds `HIGH=1/10`, `MEDIUM=1/5` (:7, :17-22). Note `BASIS["ipcch"]` there is overwritten by evidence basis (`delivery_outputs.py:441`).
- Current evidence files (examples): `bootstrap/evidence/ipcch_0m_resubstitution_area.csv` header `polygon_id,sample_count,error_count,model_package_id,horizon_months,basis,period` (6,227 data rows; `model_package_id=launch_2026_04_production_safe/scope_0m`, `period=2014-01..2026-03`); `ipcch_0m_resubstitution_residual.csv` header `polygon_id,target_month,phase2_worse_residual,...,phase5_worse_residual,model_package_id,horizon_months,basis,period` (40,777 data rows). Provenance in `bootstrap/evidence/provenance.json`; builders in `.trellis/tasks/archive/2026-10/10-09-sept-6m12m-confidence/research/` (per spec).
- Research-side compatibility constraints implied by code: evidence `model_package_id` must equal `model_metadata.model_package_id + "/scope_{h}m"`; `horizon_months` equals the runtime scope key (0/6/12), not 2/8/14; IPCCH period end <= root `model_package_manifest.json` `training_cutoff` month (single value shared by all scopes, `delivery_outputs.py:195-198`).

### bootstrap layout

- `bootstrap/baseline.json`: `schema_version: operator-baseline/v1`; keys `delivery{contracts, diagnostics[15], horizons_months [0,6,12], schema_version fewsnet-ipcch-delivery-request-v1, systems}`, `files` (74 entries, `{sha256,size_bytes}`), `models` (6 entries: keys `acceptance, environment, feature_schema_sha256, horizon_months, manifest, manifest_sha256, package_id, system`), `runtime{image_uri (sha256:7e6133f3...), requirements_lock_sha256 2f0a7251...}`, `sources{acled,wfp: september-h5-raw-converter-v1}`. Consumed by `pipeline.initialize` (:342-491), which enforces exactly six slots (:355-358), allowlisted prefixes `assets/ models/ evidence/` (:364-365), and required assets (:389-407).
- `bootstrap/models/ipcch/`: root `model_package_manifest.json` (package_id `launch_2026_04_production_safe`, `training_cutoff 2026-04-01`, `scopes [0,6,12]`, target_periods), `training_export_summary.json`; `scope_{0m,6m,12m}/{feature_columns.json, feature_contract.csv (128 rows; columns feature_name,scope_months,category,source_column,dtype,required_in_input,missing_tolerance,fill_method,fill_value_or_stat_key,lookup_asset,derive_function,as_of_policy,notes), model_metadata.json (monotonicity_policy cummax, thresholds{default:0.2}, imputation_statistics[128], model_package_id), phase{2..5}_worse_model.json}`. Feature names/source columns identical across scopes; contract bytes differ (scope_months column), so schema hashes differ: 0m `ed49866a...`, 6m `44ab914d...`, 12m `f0cd5801...`.
- `bootstrap/assets/`: `retained_acled.csv` (`system,admin_code,month,` + conflict columns), `retained_wfp.csv` (`system,admin_code,month,WFP_Price,WFP_Price_std`), `fewsnet/{geometry.geojson, history/, history_panel.csv, population.csv, roster.csv}`, `ipcch/{fixed_features.csv (6,227 rows), geometry.geojson, history/{evi,fldas,gosif_mean,gosif_sd,viirs}.csv, history_panel.csv (~1.78 GB), population.csv, roster.csv (6,227 rows + header)}`.

### Hard-coded assumptions inventory

- **6,227 roster**: not hard-coded in Python/YAML/MD under `cloud_pipeline/` (grep `\b622[67]\b` excluding bootstrap/dist/fallback: no hits). Roster flows from `assets/ipcch/roster.csv` (prepare) and `fixed_features.csv` template (`deliver._ipcch` :206; `delivery_inputs._origin_rows` :164-170); bundle checks use the delivered roster (`delivery_bundle._content_checks` :180-196). Count appears only in data (roster/fixed_features/evidence).
- **(0,6,12) horizons**: `delivery_manifest.HORIZONS_MONTHS` (:29); `pipeline.HORIZONS` (:18); `delivery_job.inherit_system` literals (:388, :391) and `INHERITED_MEMBERS` regex `(0|6|12)` (:337); `causal_fill.bind_model_features` (:190); `delivery_bundle.HORIZONS` (:27) and `PORTABLE_INPUTS` regex (:34); `delivery_scoring.HORIZONS` (:43) -> `deliver.HORIZONS` (:33); `run_operational_launch_inference.SCOPES` (:27); FEWS `fewsnet_partitioned_rf_pipeline/config.py:3`, `local/outputs.py:83`; `tools/build_fewsnet_country_level_predictions.py:23`. Directory names `scope_{h}m`, `scopes/{h}m/` keyed by these values.
- **origin == feature month, target = origin + h**: `deliver.deliver` (:120), `delivery_scoring.score_ipcch` (:170-172), `delivery_job.inherit_system` (:391-398), `delivery_bundle._content_checks` (:190, :214-215), `delivery_bundle.rescore` (:540-541), `package_delivery` single `origin_month` (:418-419). New contract needs O=M-2 for features and targets M, M+6, M+12 (R23) - these sites currently tie both to one month.
- **H0-only**: `deliver.py:203` (`scope_0m/feature_contract.csv` used for all scopes' source columns); single shared `training_cutoff` (`delivery_outputs.py:195-198`, `deliver.py:221`).

### Existing test suites (candidate validation suites)

Counts from `pytest --collect-only -q` (612 collected, 1 collection error) using `~/.venvs/fewsnet-test-lock-20261022/bin/python` (pytest 9.1.1, Python 3.12.3). `~/.venvs/ipcch-cloud-operator` exists (Python 3.12.3, built from `requirements.lock.txt`) but **has no pytest installed**; prior accepted runs used an "exact-lock test env" = lock + pytest + pyyaml (archive task notes).

| Suite (implement.md) | Path exists | Tests |
|---|---|---|
| `tests/cloud/test_delivery_manifest.py` | yes | 46 |
| `tests/cloud/test_delivery_job.py` | yes | 29 |
| `tests/cloud/test_inherited_bundle_checks.py` | yes | 5 |
| `tests/cloud/test_prepare.py` | yes | 31 |
| `tests/cloud/test_retrain_source_contracts.py` | yes | 8 |
| `tests/cloud/test_delivery_outputs.py` | yes | 75 |
| `tests/cloud/test_execution_selection.py` | yes | 17 (same-origin asserts at :53-56, :206 `targets differ`) |
| `tests/cloud/test_ipcch_chunked.py` | yes | 10 |
| `tests/test_refresh_h5_inputs.py` | yes | 22 |
| `tests/test_operator_release.py` | yes | 27 |
| `tests/test_operational_launch_feature_contract.py` | yes | 15 |
| model_pipeline inference tests | `tests/test_operational_launch_input_contract.py` (14), `test_population_contract.py` (5), `test_population_output.py` (6), `test_prediction_uncertainty.py` (7) | `tests/test_operational_launch_inference.py` cited in PROGRESS.md **does not exist** in the current tree |

Other related: `test_delivery_run.py` (7), `test_delivery_bundle.py` (49), `test_deliver.py` (7), `test_delivery_scoring.py` (7), `test_workflow_dispatch.py` (23), `test_delivery_workflow.py` (1), `test_remote_sources.py` (19), `test_causal_fill.py` (21), `test_operator_cli.py` (11), `test_object_store.py` (4), `test_frozen_confidence.py` (5).

Command pattern used historically (PROGRESS.md and archived tasks), run from `cloud_pipeline/`:

```bash
cd cloud_pipeline
PYTHONDONTWRITEBYTECODE=1 <exact-lock-python-with-pytest> -m pytest tests -q -p no:cacheprovider
# focused example
PYTHONDONTWRITEBYTECODE=1 <python> -m pytest tests/cloud/test_delivery_manifest.py tests/cloud/test_delivery_job.py \
  tests/cloud/test_execution_selection.py tests/cloud/test_inherited_bundle_checks.py tests/test_operator_release.py -q -p no:cacheprovider
```

Candidate interpreter: `~/.venvs/fewsnet-test-lock-20261022/bin/python` (has pytest; whether its pins equal `requirements.lock.txt` sha `2f0a7251...` is UNVERIFIED here). Alternative: add pytest/pyyaml to a copy of `~/.venvs/ipcch-cloud-operator`.

### Related Specs

- `.trellis/spec/backend/monthly-delivery-contracts.md` - v1 signatures, error matrix, evidence binding, required checks (sections 2, 4, 6, 8, 9).
- `.trellis/spec/guides/cloud-handover-layout.md` - runtime root is `cloud_pipeline/`; module names fixed; tests use fake services; research checkout must not be a runtime dependency.

## Caveats / Not Found

- **Collection error (pre-existing, environment)**: `tests/fewsnet_partitioned_rf/test_full_history_fit.py` fails at import: partition asset `fewsnet_partitioned_rf_pipeline/assets/partitions/cluster_mapping_k40_nc17_general_refined_contig3.csv` hashes `4d94772f...` (LF, equals the HEAD blob) while `config.py:35-37` expects `4723cae5...`, which equals the CRLF form of the same file. Not investigated further; affects full-suite runs from this WSL checkout.
- `deploy/october_delivery/` (referenced by the spec and by `delivery_job.lock_sha256` fallback :142-144) does not exist; deployment files live directly in `deploy/`.
- No per-system lock, GPP availability ledger, acceptance manifest, feature-batch store, mode field, wall-clock check or activation record exists in the current code (searched for `locks/`, `ledger`, `activation`, `mode`).
- `inference._predict_scores` reports nonfinite by target only; R18's area/horizon/field reporting is not present (description only).
- `feature_contract.py` has no +/-inf rejection and can synthesize an all-NA column for non-required absent sources (`:189-191`); relevant to R19 (description only).
- Whether H2/H8/H14 packages will use `median_impute` (current) or NaN passthrough (`required` category) is not determined by this inspection (UNVERIFIED; research-side packaging decision).
- Workflow routing for a v2 shape is not determined by code today (UNVERIFIED intent): `deploy/workflow.yaml` reads `execution.remote_update` from raw JSON.
- GitNexus MCP tools were not used; findings come from direct source reads and grep. Line numbers are against the working tree at the time of inspection.
