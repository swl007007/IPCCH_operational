# Automatic monthly E2E integration evidence

2026-10-30, local read-only inspection at source HEAD
`69aa74a372f40581d6759a5703e7ec331ba4af63`. Three independent scouts inspected
producers/transport, trigger/operator, and retained initialization. Main session
spot-checked transport, scheduling, binding and initialization. No cloud calls,
product edits, tests, or large history key scans were performed in this inspection.
Paths below are repository-relative unless explicitly given.

Subsequent scope decision D4 defers live incremental acceptance and rejects building
an earlier checkpoint for this round. The feasibility findings below explain that
decision; they do not authorize a new bundle or make November a task-close gate.
Current acceptance is defined only by the latest `prd.md` AC1-AC9 and DA1-DA2.

## Producer/runtime boundary

Upstream directory:
`/mnt/c/users/swl00/ifpri dropbox/weilun shi/IPCCH_shared_folder/seasonal/`.

- `01_vi_prcp_et0_update.js:143-150,881-889`: Code Editor `Export.table.toAsset`
  creates tasks; final message says "Review and start the required tasks in the
  Tasks panel." `02_et0_patch32_update.js:659-716` checks target counts in an
  `.evaluate` callback, then creates its export with the same manual start boundary.
- `01:23-25` and `02:39` fix current VI/chunks to 2026 and 2020-2026.
  `01:22` says "Keep the 2020-2026 block intact: existing downstream loaders expect
  it." Reader `cloud_pipeline/cloud/ipcch/climate_tables.py:37,213` also ends at
  2026; producer and reader need coordinated rollover.
- Both scripts independently generate date-only `_UPDATE_YYYYMMDD` tags (`01:11`,
  `02:16`). These conflict on same-day reruns and can diverge across midnight.
- `cloud_pipeline/deploy/Dockerfile:3-17` is Python-only; the pinned EE Python API
  is in `cloud_pipeline/requirements.lock.txt:12`. There is no installed Node/EE
  JS SDK or copied sibling script. Python graph port fits the current runtime;
  retaining JS instead would require another runtime, initialization and replacement
  of Code Editor globals. This is implementation evidence, not scientific approval
  to alter the upstream formulas.
- `cloud_pipeline/cloud/ipcch/ee_transport.py:148-192` provides conditional receipt
  writes, bounded status polling, cancellation and deadline reserve. `:194-253`
  reserves, starts, persists task ID, waits and pins one CSV, but calls
  `toCloudStorage` at `:218`. No table-to-Asset path exists in the inspected pipeline.
- `01:163-164` explicitly specifies no additional VI scaling and comparison with
  V3 units. Precipitation ERA5LAND is multiplied by 1000 (`01:336-354`); ET0 is daily
  FAO56 then monthly sum (`01:581-698`). PATCH32 is 32 buffered polygons at 30 km
  (`02:31-85,131-170,659-665`). Preserve these choices when porting.
- Complete-month checks compare collection count with expected days; they do not
  prove per-pixel daily completeness. All-masked property representation after real
  export remains unverified. Intermediate image QA properties are not established
  as final table columns. An EE COMPLETED task is not a complete-observation test.

## Trigger and manual input boundary

- `cloud_pipeline/deploy/workflow.yaml:1-4,52-61` filters object-finalized events
  to `requests/<run_id>/run_manifest.json`; `deploy/setup.py:167-185` creates this
  Eventarc trigger. No monthly clock/request-creation implementation was found in
  the searched executable/config source. Cloud-only extra schedulers are unverified.
- Workflow `:280-300` overrides the full argv and omits `--v2-config`; the dispatcher
  rejects v2 without it (`cloud/orchestrator/delivery_job.py:1030-1044`).
- `cloud_pipeline/pipeline.py:641-643,684-699,805-820,1711-1727` generates run IDs
  but builds/validates the old request. Its status reader uses `run_status.json`
  (`:592-594`); v2 writes `v2_run_status.json` (`cloud/ipcch/entrypoint_v2.py:190`).
- `cloud_pipeline/cloud/orchestrator/delivery_request_v2.py:206-213,258-323`
  requires all 11 keep/refresh choices for generation: ACLED, WFP, history snapshot
  and eight research inputs. Exact research keys: `nino34_anom`, `bbg_staple_food`,
  `bbg_oilgas`, `bbg_soybean_oil`, `bbg_global_food`, `food_price_index_WB`,
  `idp_national`, `idp_local`. Refresh pins URI/generation/SHA; history snapshot is a
  full replacement, while research/WFP refresh uses declared intervals. Keep reads
  saved history, not a guessed latest upload. First ACLED keep without history fails
  (`cloud/ipcch/generation.py:236-239`).
- `cloud_pipeline/cloud/ipcch/run_v2.py:80-101,175-183` already chains this run's
  generated batch into inference and current publication. No manual batch-ID handoff
  is necessary. Candidate publication is not later promotable directly: archived
  10-29 PRD R66 requires a new inference-only current request.

## Why October cannot prove incremental climate with the existing bundle

- `cloud_pipeline/cloud/ipcch/binding.py:302-312` binds exact handoff manifest,
  roster and acceptance-entry hashes. `initial.py:181-208` verifies and loads entire
  tables; a different already-initialized source hash is rejected. There is no
  cutoff/truncation option. `binding.py:384-388,420-435` also binds store pairing.
- `cloud_pipeline/cloud/ipcch/climate.py:241-249,286-303` fetches only unsaved whole
  months. Saved rows with missing values or late individual sources do not trigger
  reads. `:252-259` prohibits overwriting saved keys. Seasonal scheduling similarly
  removes saved area/year/season keys (`:348-385`). An isolated root initialized
  from the same bundle has the same coverage and therefore the same skip behavior.
- Handoff `handoff-build/out-r5-accepted-v1/handoff_manifest.json` beneath
  `/home/swl007007/projects/food-crisis-research/scratch/h2h8h14-final/` declares
  871,640 rows per monthly table (6,226 x 140), 149,424 per seasonal table
  (6,226 x 24), and calendar years 2015-2026 (`:134-262,693-722`). Previous inspection
  established monthly coverage through 2026-08; this pass did not rescan large CSVs.
- With O=M-2, October uses saved August. The natural next missing origin is September
  when M=November is actually allowed. Earlier-checkpoint acceptance instead needs
  a separate derived bundle and new accepted envelope, retaining the same model
  package/roster; no existing bootstrap option bypasses this requirement.
- `cloud_pipeline/tools/ipcch_finalize_acceptance.py:43-74` accepts an already built
  bundle into a new directory/envelope, but does not derive a cutoff checkpoint.
  Such derivation changes retained input lineage and requires a scope decision.
- Genuine proof links saved-period reports, table HEAD/version changes, preserved
  old keys, assembly's retained re-read (`generation.py:353-355`), batch retained
  versions (`:381-418`) and source version provenance (`provenance.py:100-139`).
  A detached acquisition comparison does not establish downstream consumption.
- Full real roster is mandatory, not a test-size preference:
  `cloud_pipeline/cloud/ipcch/batch.py:72-106` binds exact roster size/hash and all
  row keys; `batch_inference.py:99-107,126-129` repeats those checks.

## Verification scope to retain

Existing targeted tests: `test_ipcch_climate_tables`, `test_ipcch_climate`,
`test_ipcch_ee_transport`, `test_delivery_request_v2`, `test_ipcch_entrypoint_v2`,
`test_ipcch_run_v2`, `test_workflow_dispatch`, `test_delivery_workflow`,
`test_deploy_setup`, `test_operator_cli`, and `test_operator_release`.
Add focused producer/Asset-export and recurrent-month tests alongside these.
Live access, newest source coverage, runtime limits and the final export schema
remain to be checked in the bounded real execution phase.
