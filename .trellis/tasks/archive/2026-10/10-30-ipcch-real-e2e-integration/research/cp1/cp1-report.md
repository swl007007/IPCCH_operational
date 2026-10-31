# CP1 — sparse PATCH32 + produced-table mapping/completeness contract (Executor, 2026-10-30)

No cloud work, commits, branch changes or Audit. Product scope:
- `cloud_pipeline/cloud/ipcch/climate_tables.py` (diff `climate_tables.diff`, sha `6aefd477…`);
- new `cloud_pipeline/tests/cloud/test_ipcch_produced_tables.py` (sha `781d5be1…`).

Not touched: AGENTS.md, PROGRESS.md, task.json, implement.md, specs.

## Baseline status
- Rerun result: `cp0/baseline-tests-full.log`, **957 passed, exit 0** (`cp0/baseline-tests-exit.txt`), at HEAD 1faa6ae.
- The rerun overlapped my edits. The first CP1 edit was at 19:26:09 with the run at about 45% (`baseline-overlap.txt`).
- Test modules had already been collected and imported, so the in-process tests used pre-edit code. Subprocess-launched tests could have re-imported after 19:26, but none of them imports `climate_tables`.
- It is labelled "pre-CP1 baseline (collection before edits)", not a frozen-tree baseline.

## GitNexus impact (before edits)
- `_wide_month_matrix`: risk LOW. Direct callers are `DroughtProvider._compute` and `SeasonalDroughtProvider.fetch_season`. Processes: `fetch_season` → `missing_assets`/`read_asset_table`/`asset`.
- `TableRefs`: LOW. Its only production caller is `climate_run.real_providers`, plus tests.
- `detect_changes(all)` reports MEDIUM because it includes the user's AGENTS.md and the Supervisor's PROGRESS.md. For the product file, the only affected processes are the three `fetch_season` flows.

## Changes
1. **Sparse PATCH32.**
   - `_wide_month_matrix(..., sparse=False)`. Patch reads on all four routes (monthly SPI/SPEI in `_compute`, seasonal SPI/SPEI in `fetch_season`) pass `sparse=True`.
   - Absent patch rows become NaN, and patch rows outside the requested admins are ignored.
   - The primary tables still `require_admins`. Duplicate `admin_code`, non-numeric values and a missing `admin_code` column still fail.
   - `apply_et0_patch` is unchanged, so the patch fills only NaN primary cells.
2. **`ProducedTable(asset_id, periods)` and `TableRefs.produced`** (keyed by the existing basename).
   - `asset()` returns the run's asset for a mapped name, so the produced asset replaces the old chunk instead of being joined with it. Unmapped names resolve exactly as before.
   - Validation rejects:
     - unknown names and VI baselines;
     - a non-`projects/` id, or an id equal to the old canonical id;
     - two names sharing one asset;
     - empty or non-bool metadata;
     - drought chunk metadata that does not declare exactly every month of the chunk;
     - VI metadata other than published dates of that table's year.
3. **`check_produced` on read** (`_read_checked`).
   - Each family has its own required field: PRCP needs `prcp_*`, ET0/PATCH32 need `et0_*`, VI needs the consuming index (`evi`).
   - A foreign field in a month table, a column for an undeclared period, a declared-complete period without its required field, or a declared-incomplete period carrying finite values is a `ClimateProcessingFailure`.
   - NaN cells within a complete period are valid (spatially masked).
   - A produced asset that is absent is a failure, never `unavailable` (`_absent_unproduced`, and the drought `_read_all` path).
4. **Availability.** Static/history chunks keep the column-presence rule on the target month.
   - **Produced chunks:** every produced input month the index consumes must be declared complete. That is T-2..T for monthly, and from the season's first month minus 2 through its end for seasonal (the 3-month accumulation in `rolling_three_month_sum`); otherwise the period is `unavailable`.
     - Complete-but-masked months are published, with no finite-count proxy.
   - **SPEI:** once either ET0 family is produced, both the primary ET0 and PATCH32 must be complete. In the static-only case the old rule is unchanged: the patch column alone can make the target month published.
   - **Only the consuming source's inputs gate availability.** Other months of a produced chunk, including fit-baseline months on or before 2020-12, keep the upstream masked/NaN missingness, which the unchanged 1991-2020 fits handle (R40).
     - An earlier draft rejected any incomplete produced baseline month; the Supervisor removed it as an unapproved policy.
     - A calendar-count gap in an old month is not contradictory metadata, and one source's gap must never fail another source's fetch.
     - The test asserting that gate was replaced by `test_produced_gaps_outside_the_consumed_inputs_keep_upstream_missingness`.

## Contract interpretation to confirm
- Gating interior and lookback input months changes no numeric definition. The upstream scripts mask incomplete months to NaN, which would make every area NaN for that period.
- Classifying such periods `unavailable` maps "not yet published" onto the accepted source-unavailability contract (`climate.py` docstring), instead of saving an all-NaN row forever.
- **Consequence:** if a produced source month were permanently incomplete (a real missing day), then for that source:
  - the monthly periods that read it (T, T+1, T+2) stay unavailable;
  - the seasons spanning it stay unavailable;
  - if no source publishes the origin O, the existing `ClimateSourceMissing` rule stops the run.

  This has not been observed (grill pass); I am surfacing it rather than adding an override.

## Tests (full logs and exit codes kept)
- **Green, focused.** `green-focused.log` and `green-focused-exit.txt`: **86 passed, exit 0** (final tree), covering:
  - the new file;
  - climate_tables, climate_run, ee_transport, spi_spei, spi_spei_seasonal, climate and generation.
- **Red, HEAD reader** (`run_red.py` loads `climate_tables_HEAD.py`, i.e. 1faa6ae, in place of the edited module):
  - `red-head-sparse.log`, exit 1: **7 failed, 1 passed** (`-k "sparse or stays_missing"`). Every failure is HEAD rejecting the sparse patch table with `et0 table: table lacks 1 required admins`. The failures cover:
    - monthly SPI+SPEI;
    - seasonal full and subset rosters;
    - strictness in both routes (the duplicate check is never reached on HEAD);
    - patch-NaN/absent-row in both routes.
    - The one HEAD pass is the subset roster `["2"]`, which contains only the patch polygon itself.
    - A collection-only placeholder `ProducedTable` is set only in this sparse-only run.
  - `red-head.log`, exit 2: the produced-contract tests cannot collect on HEAD (`ProducedTable` is absent).
- **Regressions in the new file:**
  - sparse monthly SPI/SPEI: exact values; primary values and the admin-1 primary preserved over a patch row; `et0_patch_filled`; admin 2 computable only through the patch;
  - seasonal SPI/SPEI on rosters ADMINS, `["1","3"]` and `["2"]`;
  - primary-coverage, duplicate and numeric strictness, each on both the monthly and seasonal routes;
  - primary ET0 NaN with no patch row (admin 3) or a NaN patch value (admin 2) stays missing on both routes (monthly also asserts exact values and `et0_patch_filled` reduced by one);
  - produced chunk replaces the old one (the old id is never read);
  - static all-null hazard documented vs produced incomplete → unavailable; complete-masked and complete-all-null → published;
  - contradictory metadata (complete without field, incomplete with values, undeclared column, absent produced asset);
  - 10 mapping-validation cases;
  - wrong-prefix PRCP schema and a stray foreign field; NDVI-only VI fails for an `evi` consumer;
  - interior incomplete month (monthly T-1, seasonal interior, seasonal T-2 lookback);
  - an incomplete produced baseline month (2020-03) is NaN and the fit proceeds (published, exact values); 2020-04, whose window reads it, is unavailable; another source's produced gap does not affect CHIRPS;
  - SPEI with a static vs incomplete vs complete produced patch;
  - produced VI table contract;
  - incomplete-then-published recovery through `climate.update_monthly`: no placeholder saved, then saved with finite values and 3 sources.
- Compile check: `py_compile` on both files returned exit 0. No full-suite rerun, per Supervisor.

## Remaining CP2 work (not done here)
1. **Python port** of `01_vi_prcp_et0_update.js` and `02_et0_patch32_update.js` (source shas `b0d64ac0…`/`841ae7f8…`), keeping the producer graphs:
   - QA, ×1000 ERA5 PRCP, daily FAO56 ET0 and nonnegative clip, buffered-polygon PATCH32 and the 32-target check, the reducer and compactGeometry;
   - a graph-contract comparison against the JS source.
2. **Producer-side completeness.**
   - Daily `size == days` per source month, computed client-side and carried as `ProducedTable.periods`.
   - VI: the composite dates present in the year's collection.
   - The producer must validate its exported schema before exposing an id (same field rules as `check_produced`).
3. **`EETransport.export_table_to_asset`**: `toAsset` plus the existing reservation, durable task id, bounded wait, cancel and deadline reserve, then post-completion asset/schema/period readback. Failures stay distinct from unavailability.
4. **Run planning.**
   - Required VI years (current and prior for January/Aqua overlap) and drought chunks, derived from eligible months/windows.
   - Post-2026 chunk rollover agreed between producer and reader (`YEAR_CHUNKS`/`TableRefs.family`), tested for 2027 and January overlap.
   - Each table submitted once per run, deduplicated across the monthly/seasonal providers.
   - Versioned output ids from run ID and context, not the date-only `_UPDATE_YYYYMMDD` tag.
5. **Wiring.**
   - `climate_run.real_providers`/`real_provider_factory` accept the run-bound `produced` map.
   - `entrypoint_v2.real_providers` builds it, and passes `deadline_utc` (currently dropped, `entrypoint_v2.py:173-175`).
   - Producer receipts reach the retained/batch record (`_collect` ignores `SourceOutcome.extra`).
6. Duplicate-event, same-day-rerun, failed/timed-out export and deadline tests. v2 admission reservation, Workflow, image and smoke work belongs to CP3.
