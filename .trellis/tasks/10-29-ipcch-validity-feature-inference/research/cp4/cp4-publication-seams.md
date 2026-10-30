# Research: CP4 publication/compat seams (existing code map)

- **Query**: map R17/R18/R36/R37/R39/R46/R47/R48/R50/R63/R66 + Final convergence corrections (FCC) onto existing publication code
- **Scope**: internal, read-only. Paths relative to `cloud_pipeline/` unless prefixed. **Date**: 2026-10-30 (HEAD 016d90d)

## 1. Pointer / release mechanism

| Item | Location | Fact |
|---|---|---|
| pointer URI | `cloud/orchestrator/delivery_run.py:98-99` | `{root}/{namespace}/current.json`; namespace = `request.release.namespace` |
| release record | `delivery_run.py:104-106` | `{root}/{namespace}/releases/{run_id}/release.json`, create-only (`if_generation_match=0`) |
| pointer body | `delivery_run.py:107` | `{run_id, release_record, release_record_generation}`, nothing else (no months, no contract id) |
| record body | `delivery_job.py:513-517` | `{run_id, request{uri,generation,sha256}, origin_month, manifest, archive, validation, [execution{scored_systems, inherited_systems}]}`; one `origin_month` for the whole release |
| order | `delivery_run.py:95-115` | legacy ns `released` refused (95-96) -> `validate()` (97) -> precheck live gen == expected else conflict stage `precheck` (100-103) -> record -> pointer CAS `if_generation_match=int(expected)` (108-110) -> on `GenerationConflict` conflict stage `pointer_write` (111-114) |
| conflict | `delivery_run.py:81-89` | writes create-only `runs/{run_id}/release_conflict.json` then raises `ReleaseConflict`; orphan release record left at pointer_write stage |
| expected generation | `delivery_manifest.py:425-437`; `pipeline.py:728-734` | request field `release.expected_pointer_generation` ("0" = first); operator captures live gen once at submission and stores it in run state |
| retry | none in `publish`; `pipeline.py:1394-1410` `_publish_resumable` repeats only the pointer CAS (same expected gen) for an interrupted promote | GCS transport retry on conditional writes: `object_store.py:120-126,181-184` (DEFAULT_RETRY 1800 s) |
| reader of current | `pipeline.py:110-125` `Cloud.latest`; stable-read pattern `cloud/ipcch/stores.py:82-92` (gen before/after) | `ObjectStore` protocol has no generation-pinned read and no `delete` (`cloud/common/object_store.py:18-36`) |
| v2 namespace | `delivery_request_v2.py:137-140` | reuses `_release`; namespace forced to smoke or production per `mode` |
| tests | `tests/cloud/test_delivery_run.py:73-121` (CAS, conflict record, race after record write); `tests/cloud/test_delivery_job.py:174,325` (publish last; failed validation never moves pointer) | |

## 2. Delivery bundle layout and inherit

- Layout `cloud/orchestrator/deliver.py:5-10`: `{fewsnet,ipcch}/{polygons.geojson,country_population_reference.csv}`, `scopes/{0,6,12}m/{system}/<5 tables>` (`delivery_bundle.py:36-39`), `inputs/` (frozen scoring inputs; IPCCH = `inputs/ipcch_origin_rows.csv`), `reports/{system}_{feature_fill_audit,diagnostic_availability}.csv`, `reports/{system}_diagnostic_declarations.json`, `reports/{system}_assembly.json` (`deliver.py:121-138`; assembly has `origin_month`, `targets`).
- Shared reports: `finalize` (`deliver.py:169-189`) byte-concatenates per-system sidecars; requires identical headers. `AVAILABILITY_COLUMNS` (`delivery_outputs.py:33-34`) has NO month column; `AUDIT_COLUMNS` (`causal_fill.py:33-50`) has `feature_month`.
- Packaging `delivery_job.py:411-439`: writes `reports/delivery.json` {origin_month, run_id, request, prepare_id, execution{scored_systems, inherited_systems, remote_update, publication}}; `reports/inherited_members.json` when inherited; installs BOTH systems' packages from the request (`delivery_bundle.py:61-74`, `model_inventory.json`); `bundle_manifest.json` with single `origin_month`, fixed horizons (0,6,12) (`delivery_bundle.py:99-102`); inventory `manifest.json` (`:366-381`); archive (`:399-426`).
- Per-system model id: IPCCH `model_package_id` column in prediction/mapping headers (`delivery_outputs.py:96-131`); FEWS `suite_version`. No per-system execution month field anywhere; months only per-row (`feature_period/target_period`, `feature_month/target_month`).
- Validation `validate_delivery` (`delivery_bundle.py:113-164`): exact 30-table inventory (124-127); exact `SEPTEMBER_HEADERS` (133-136, headers `delivery_outputs.py:41-140`); both systems' shared refs/reports/frozen inputs (141-148); `_content_checks` uses ONE `origin` from `reports/delivery.json` for BOTH systems incl. inherited ones: IPCCH `feature_period==origin`, `target_period==origin+h` (179, 208-216); `_country_consistency_checks`/`_diagnostics_regeneration_checks` skip inherited systems (269-274, 491-496) via `_inherited_identity_checks` (592-620); `_portable_member_checks` requires `ipcch/model_package` with legacy `IPCCH_SCOPE_FILES` (82-83, 338-340).
- Inherit request shape `delivery_manifest.py:168-205`: `execution.inherit.{system}` = `{source_delivery_id, origin_month, manifest, archive}`; inherit must name exactly the unscored systems (193-195); **same-origin gate** `origin_month != origin` rejected (199-200).
- `inherit_system` `delivery_job.py:346-408` checks: member regex `INHERITED_MEMBERS` (336-342, package prefix 343); each archive member sha == source inventory (373-374); create-only copy (383); **source `reports/delivery.json.origin_month == origin`** (386-387); all `SCOPE_TABLES` for 0/6/12 present (388-390); **targets fixed (0,6,12)**: `feature_period==origin`, `target_period==origin+h` (391-398); **installed-package equality**: source `*/model_package/` digests == package installed for this release (399-404). Returns record incl. `model_package`, `source_run_id`, `source_provenance` (405-408). Called in `execute` (504-509) after scoring, before packaging.
- Operator side `pipeline.py:831-840` `inherited_source`: pins refs, requires manifest `provenance.run_id == source_delivery_id`, sets `origin_month` = the run month. `verify_candidate` checks inherited sources equal request (`pipeline.py:976-989`).
- Tests asserting same-month: `tests/cloud/test_execution_selection.py:53-57` (validator), `:201-209` (origin/targets/package in `inherit_system`); bundle identity checks `tests/cloud/test_inherited_bundle_checks.py:38-85`.

## 3. Sentinels / locks (existing)

| Mechanism | Location | Key / release |
|---|---|---|
| `_RUN_ACQUIRED` | `delivery_run.py:54-78` | `{root}/runs/{run_id}/_RUN_ACQUIRED` = `{run_id, request{uri,gen,sha}}`; per run_id only; never released; dup -> original status or `running_or_abandoned`; different request -> `RunConflict` |
| dispatch claim | `deploy/workflow.yaml:84-104` | `dispatch/{run_id}/claim.json` create-only, per run_id |
| dispatch records | `delivery_job.py:629-666` | `dispatch/{run_id}/{admission,resolution}.json` create-only |
| prepare sentinels | `cloud/orchestrator/prepare.py:203,296,465-469` | `_PREPARE_ACQUIRED`/`_EXTRACT_ACQUIRED` per prepare_id |
| maintenance hold | `pipeline.py:843-849,1177-1220`; `deploy/workflow.yaml:58-83` | `maintenance/hold.json`, global, admits listed run_ids; deleted at generation on `release` (`pipeline.py:1298`) |
| store HEAD CAS | `cloud/ipcch/stores.py:109-131` | per-table HEAD generation CAS (retained stores) |

No per-system lock exists; nothing keys on system. No object delete in `ObjectStore`; only `pipeline.Cloud.delete(uri, generation)` (`pipeline.py:156-157`).

## 4. Promote / resume

- `pipeline.py:1413-1512` `promote`: requires maintenance operation phase in (`shared_changed`,`promoting`,`activation_inconsistent`) (1422-1423), run admitted (1424-1425), hold owned (1427-1429), receipt `operator-candidate-receipt-v1` passed and bound to `candidates/{run_id}/candidate.json` ref/manifest/archive (1430-1435), image == config (1436-1437); expected gen from local run state request body (1439); pointer gen precheck (1445-1447); publishes `{candidate record, candidate, verification_receipt}` via `_publish_resumable` (1487-1490). Resume = re-invoking promote with recorded `promotion` state, inspected by `_inspect` (1311-1329). No check of request schema/contract.
- `verify_candidate` `pipeline.py:923-1022`: fetches executed request (947-948) and replays with bundle `rescore` (`delivery_bundle.py:517-583`, legacy IPCCH `run_scope` from `ipcch_origin_rows.csv`, 551-556).
- Run resume `pipeline.py:679-680` (phase `submitted` -> status only). Candidate write `delivery_job.py:524-531` -> `{output_root}/candidates/{run_id}/candidate.json` (not namespaced). `download --candidate` `pipeline.py:858-866`.

## 5. Routing and current-month source

- v1 path: Eventarc -> `deploy/workflow.yaml:46-126` (filter `requests/<run_id>/run_manifest.json`; route on `execution`/`remote_update`) -> `delivery_job.main` (`:669-727`) -> `execute` (`:475-537`) -> `validate_delivery_request` (`:483-485`; `delivery_manifest.py:98-165`, `SCHEMA_VERSION` v1 at :27). Remote intents: `admit_intent`/`resolve_intent` (`delivery_job.py:543-626`) also call the v1 validator.
- v2: `delivery_request_v2.is_v2` (`:69-70`), `validate_request_v2`/`admit` (`:73-93,401-415`), runner `cloud/ipcch/run_v2.py:86-115` (returns outcomes; docstring :15 "Publication ... applied by the caller (CP4)"). No dispatch from `delivery_job.main`/`execute` to v2 exists; a v2 body has no `execution` key so the workflow routes it to `run_job` (workflow.yaml:121-124) where the v1 validator rejects it.
- Hook points for a router: `delivery_job.execute` before :483 (schema_version switch) and `_remote_intent` :543-553.
- R39 current month: `current_ipcch_execution_month` is a caller argument (`delivery_request_v2.py:81,85-86,152-160`); no code reads it from the pointer yet. Only available data: pointer -> release record `origin_month` (legacy meaning per v2 docstring :85-86) + `execution.scored_systems/inherited_systems`; for inherited IPCCH, month only in archive `reports/inherited_members.json`/scope rows.
- "Includes IPCCH" for v1: `selected_systems` (`delivery_manifest.py:208-213`; legacy without `execution` = both).

## 6. Existing "activation"

Only maintenance image cutover: `promote` phase `activated` (`pipeline.py:1510`), `_restore_activation` (`:1357-1384`), `maintenance release` (`:1281-1302`). Reversible by design (restore). No IPCCH contract activation, no contract identity in pointer/record.

## 7. Requirement -> seam / missing / minimal shape

| Req | Existing seam | Missing | Minimal change shape |
|---|---|---|---|
| R50+FCC2 lock `locks/{system}` | none; create-only pattern `delivery_run.py:58-61` | lock object, owner content, release, ops clear; `ObjectStore.delete` | create-only `{mode-root}/locks/{system}` `{run_id,...}` after `v2.admit` (`run_v2.py:89`) before system loop; on any failure release only own locks (delete at own gen); release after publication; add generation-conditioned delete to ObjectStore + LocalObjectStore |
| R63 single pointer + cross-system inherit | `publish` + `inherit_system` + `INHERITED_MEMBERS` | different-month source; per-system months in record/`delivery.json`; `_content_checks` per-system origin | relax :199-200 / :386-398 for cross-system source (check member's own recorded periods); keep hash checks :373-374; `_content_checks` skip inherited system or use its own months |
| FCC4 inherit exact current | operator picks source freely (`pipeline.py:744-754,831-840`) | binding source to release at expected gen | in validate/publish read pointer at expected gen (stable read) -> its IPCCH member; reject other sources |
| FCC4 package identity | equality to installed pkg `delivery_job.py:399-404` | preserve inherited package identity | compare to source manifest digests only (already copied per member); keep v1 rule pre-activation (FCC9) |
| R66 candidate | `delivery_job.py:524-531` | v2 candidate marker; namespaced path | record contract version in candidate.json; no pointer move already |
| FCC3 CAS no retry | `delivery_run.py:100-114` | v2 caller; retained batch reported | reuse `publish`; catch `ReleaseConflict` -> outcome `publication_failed` with batch ref |
| R37/R46 activation | none | persisted marker; publication-time recheck | derive from current release record (design.md:49): add e.g. `contracts.ipcch` / `activated` to record, copied by every later current publication; legacy v1 IPCCH publish: in `validate` reject when release at expected gen is new-contract |
| FCC9 legacy FEWS-only | v1 validator same-month :199-200; `inherit_system` checks | member-type switch | pre-activation unchanged; post-activation replace :386-404 checks with hashes + member's own periods + own package id |
| FCC5 promote reject | `promote` :1430-1437; `verify_candidate` :947 | contract check | reject when executed request is v2 / record marks new contract |
| R36/R48 smoke | v2 namespace pick `delivery_request_v2.py:137-140`; `StoreRoot` `stores.py:60-73` | `runs/`, `deliveries/`, `candidates/`, conflict records are `{root}/...` not namespaced (`delivery_run.py:50-51`, `delivery_job.py:461,527`) | separate smoke output root or namespace those prefixes |
| R18 all horizons | `score_batch` loop raises on any horizon (`batch_inference.py:186-216`); v1 30-table check `delivery_bundle.py:124-127` | v2 bundle builder | publish only when `result.inference.horizons` has 2/8/14 |
| R39 recheck | validation `delivery_request_v2.py:156-160` | publication-time read | in `publish` `validate` callback compare M with month of release at expected gen (CAS then binds it) |
| R47 provenance | headers exact `delivery_bundle.py:133-136` | per-system metadata | metadata files (new columns break `frozen_headers`) |

## Caveats / conflicts (flagged, not resolved)

1. `_content_checks` (`delivery_bundle.py:179-216`) applies the single delivery origin to inherited systems and checks `target_period == origin + h` with h in (0,6,12); new IPCCH targets are O+2+lead (`delivery_request_v2.py:170-175`). Any R63 different-month inheritance or new-contract IPCCH member fails today's validator.
2. v2 IPCCH predictions add `mode`, `batch_id`, `model_horizon_months`, `public_lead_months` (`batch_inference.py:210-211`); exact `SEPTEMBER_HEADERS` check would fail if written into `polygon_predictions.csv` (R47 allows columns; validator does not).
3. R63 "shared diagnostic_availability carries each system's months": availability has no month column; adding one changes headers, and `finalize` (`deliver.py:182-183`) rejects mixed headers between a new and an inherited legacy sidecar.
4. v1 request requires all six models + acceptance reports and installs both packages (`delivery_manifest.py:302-328`, `delivery_job.py:234-251`, `delivery_bundle.py:338-340`); a legacy FEWS-only request cannot express the new IPCCH combination package that a post-activation inherited member needs. Unverified how FCC9 "own model-package identity" coexists with `_portable_member_checks`.
5. "IPCCH member of the current release" is ambiguous when that release itself inherited IPCCH: `inherit_system` reads the archive's `reports/delivery.json.origin_month` (`delivery_job.py:386`), which would be the FEWS month.
6. Legacy `rescore`/`verify_candidate` replay rescoring IPCCH with legacy `run_scope` (`delivery_bundle.py:551-556`) cannot replay a new-contract member; only relevant if IPCCH scored in that bundle.
7. R50 lock coverage of legacy v1 runs is not specified; v1 path would not acquire `locks/{system}` without a change.
8. Conditional-write transport retry (`object_store.py:120-126`) may report `GenerationConflict` after a landed write (not verified against client version).
9. Not found: any `publish`/`inherit` CLI subcommand in `pipeline.py` (commands are init/run/status/download/models/verify/maintenance/promote, `:1622`); inherit is a `run` option (`:1661-1663`).
