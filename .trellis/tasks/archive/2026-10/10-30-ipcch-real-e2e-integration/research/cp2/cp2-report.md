# CP2 — automatic producers, Asset export lifecycle, deadline, replay, receipts (Executor report for gate)

**Executor.** Opus 5.5 (`claude-opus-5-5[1m]`), session 6a490ae1, pane w1A:p8 (see `executor-identity.md`).
- Live process: PID 4905, `claude --resume 6a490ae1…`.
- Herdr's `8086f8e0…` is the claude-mem observer session, not a second executor.

**Scope boundaries.**
- No cloud calls, commits, Audit, task-state or branch changes.
- Not edited: AGENTS.md, PROGRESS.md, specs, task.json, implement.md.
- DA1 and DA2 remain user-deferred and are not passed; everything here is offline, controlled-response evidence.

## 1. Memory incident: root cause and fix (tests only)

**Reproduced mechanism.** A test scenario defect causes unbounded event-list growth and is consistent with the earlier Python OOM. The original killed PID has not been conclusively mapped to that test; the controlled reproduction establishes the mechanism, not exact incident attribution.

**Proof** comes from a guarded, capped diagnostic: `memory/diag-poll-loop-run2-capped.log`, child exit 0, peak RSS 245 MB.
- **Failed-sibling test:** tasks other than T2 were scripted to stay `RUNNING` forever. Waits run in submission order, so the wait on T0 never ends:
  - T0 was polled 200,001 times and T2 was never reached;
  - with `poll_seconds=0` and the default 21,600 s timeout on the real monotonic clock, the loop would continue for hours;
  - each poll appended to the test-only `WorldEE.events` list (about 28 MB per 200k polls).
- **Timeout test:** with `poll_seconds=0` the fake clock advanced 0.0 s.
- **Retry behaviour:** ordinary `status()` exceptions are retried until the budget, as designed (third scenario in the same log).

**Run history.**
- `memory/diag-poll-loop-run1-INTERRUPTED-swallowed-cap.*` was stopped by the Supervisor. Its launcher rc 0 is not child success; `Capped(Exception)` was swallowed by `_wait`.
- The incident report's PID-attribution caveat still stands: the killed PID and test identity are not proven. This diagnostic only shows that the scenario grows without bound.

**Fix.**
- **Failed-sibling test:** T0 and T1 complete, T2 fails, and T3–T6 are still running. Their cancellation, polls and durable receipt states are now asserted.
- **Timeout test:** `poll_seconds=1`, so fake time advances.
- **`WorldEE` guard:** a 1,000-poll cap per task raises `RunawayPoll(BaseException)`, which `_wait` cannot swallow.
- After the fix: the failed-sibling node takes 2.5 s at 189 MB.

**Runner.** `guarded.sh` runs one transient user service per invocation:
- limits: MemoryMax=4G, MemorySwapMax=0, RuntimeMaxSec=600, plus inner `prlimit --as=3 GiB` and `/usr/bin/time -v`;
- `.exit` is the child's exit code, taken from a `CHILD-EXIT` marker written inside the service;
- a missing marker is recorded as `INTERRUPTED`.

## 2. Product changes (final hashes in `final/SHA256SUMS`, tracked diff in `final/tracked.diff`)

### `cloud/ipcch/table_producers.py` (new, sha `881107ec…`)

**Graphs.** Both upstream scripts are ported once to the pinned Python EE client (1.7.36), with shared formula functions:
- `daily_fao56_et0`, `monthly_et0`, `monthly_precipitation`, `prepare_vi`, `stats_reducer`, `reduce_to_points`;
- 01: original admin polygons with `admin_area_km2`;
- 02: the 32 targets selected by numeric or string `admin_code`, distinct, buffered 30 km (maxError 100), with a 32-row / 32-distinct check before submission;
- 02's PATCH32 monthly ET0 keeps its final `toFloat`, which 01 does not have.

**Completeness.** Measured inside the same export graph as the masks: `days_present_YYYYMM` for each chunk month and `composite_dates` for each VI year, written as table properties.

**Planning (`demand` / `required_tables`).**
- Uses the same scheduling as the climate update (`months_to_update`, `pending_seasons`).
- VI years come from `month_plan`; January Aqua also reads the prior year's table.
- Drought chunks from 2020 on that hold a demanded rolling or seasonal input month; chunks after 2026 follow `climate_tables.year_chunks`.
- 1990–2019 chunks and the VI baselines are never produced.

**IDs.** `{producer_asset_root}{basename}__M{YYYYMM}_{runid}_{sha8}`. An existing ID is never reused.

**Lifecycle.**
- Every table is submitted before any wait, one export per table per run.
- Any failure, interrupt or timeout cancels unfinished siblings.
- Readback checks identity properties and units, admin codes (PATCH32 must equal the 32 targets), numeric and finite means, `days_present` counts, and `composite_dates`.
  - `composite_dates`: absent, null or mixed values fail; only an exact empty string means no published composite.
- Then `check_produced` runs before the IDs are exposed through `TableRefs.produced`.
- An already-retained period produces nothing; the skip is reported.

### `cloud/ipcch/ee_transport.py` (sha `b0906ed0…`)

**Export lifecycle.**
- `_reserve` and `_submit` are factored out of `export_table` with unchanged behaviour.
- New `submit_asset_export`, `wait_asset_export` and `cancel_asset_export` (toAsset):
  - the destination must not exist before export, and COMPLETED also requires the asset to exist;
  - a wait that ends non-terminally (for example an interrupt) leaves the handle cancellable.
- New `evaluate`.

**`_bounded`: every synchronous request is bounded under the run deadline.** This covers metadata, listing pages, read pages, evaluate, `task.start`, status and cancel.
- A request is refused before the cleanup reserve; cancel may use the reserve but never goes past the deadline.
- SDK retries are disabled (`setMaxRetries(0)`).
- Each request is capped at `RPC_TIMEOUT_SECONDS=60` or the remaining budget, whichever is smaller.
- The previous SDK settings are restored afterwards, including on failure.

**Explicit paging.**
- `computeFeatures` is paged explicitly (`pageSize` / `pageToken`, no `fileFormat` auto-paging), with the budget rechecked before every page.
- `listAssets` is paged the same way, so "definitively absent" covers every page.
- `MAX_PAGES=1000`: exceeding it is a failure, never a truncated read.

**Submission identity.**
- Submission receipts persist `request_id`, `task_id` and `operation_name` (`ee.batch.Task` learns its operation only from a successful response).
- A lost start response records `not cancellable: no operation known (request id …)`; no cancellation is claimed.
- A start refused by the budget records `the start request was not sent`.

### `cloud/ipcch/climate_tables.py` (sha `8fcaa3d0…`)
- `year_chunks(through_year)`: the existing blocks, then 6-year blocks from 2027.
- `season_span`, shared by planning and `SeasonalDroughtProvider`.
- An empty VI completeness mapping is valid (VI only).
- Providers report `produced_tables` (the produced assets behind each published value).

### `cloud/ipcch/climate.py` (sha `bcd83d90…`)
- `pending_seasons` is extracted from `update_seasonal`, with unchanged behaviour.
- `_collect` stores each source's `produced_tables` in the version record of the saved month or season, i.e. retained evidence.

### `cloud/ipcch/climate_run.py` (sha `47f1de7a…`)
- `real_provider_factory(producer=, tables=)` runs production first, then builds providers whose `TableRefs` carry `year_chunks(O.year)` and the produced map.
- `_Readback` serves the frames read back by the producer, so they are validated once and never read twice.
- `ClimateProviders.production` feeds the run report.

### `cloud/ipcch/generation.py` (sha `7402e9d4…`)
- The batch manifest carries `generation.climate_production`: version, scripts and their SHA-256s, demand, jobs, per-table receipts (task, asset, state, complete periods), or the skip.

### `cloud/ipcch/entrypoint_v2.py` (sha `71f801c7…`) and `cloud/ipcch/run_v2.py` (sha `da52b0e3…`)

**Replay.**
- A read-only identity check (URI, generation, sha256) runs before any state read or admission.
- A completed identity returns its durable status, even after current has advanced (no R39 re-admission).
- A changed request under the same run ID is a conflict.
- A run reserved without a final status is never relaunched.

**Reservation.**
- `run_request(reserve=)` reserves after admission and before any lock or mutation, so an invalid fresh request still writes nothing (R17).
- A failure after the reservation writes a durable `failed` status.

**Deadline.**
- Entry time + `run_timeout_seconds`. The default 14,400 s is the cap; any value must exceed the 900 s cleanup reserve.
- The deadline is persisted in the reservation and the final status, and is never reset.
- It is passed to the provider factory: EE transport, `TableProducer`, and the GPP/VIIRS acquirer.

**`real_providers`.** Requires `producer_asset_root`, the deadline, the store root and the execution month.

## 3. Source equivalence (formulas)

**Method.**
- The upstream functions are extracted verbatim from the vendored, sha-checked `01_vi_prcp_et0_update.js` / `02_et0_patch32_update.js` and run in Node on a minimal pixel mock (`run_js_reference.js`, test-only).
- The Python port runs on the mirror mock.
- Both mocks implement only the operations those functions use.

**Results.** Exact equality (max |diff| 0.0) and identical masks for:
- daily FAO56 ET0: 58 days × 6 pixels, against both scripts;
- monthly ET0: 01 plain, and 02 with the cast; 02 equals `float32(01)`, so the cast matters;
- PRCP: CHIRPS, PERSIANN and ERA5-Land (×1000), negative values floored;
- VI QA masks across every SummaryQA / Pixel_1km case;
- completeness flags across complete, missing-last-day, full-month and zero-image months.

**Structure.** Offline serializer checks cover IDs, bands, constants, the reducer, tileScale 8, maxPixelsPerRegion 1e9, centroid(100), the 30 km buffer, the 32 codes, the 84 chunk bands plus `days_present`, and `composite_dates`.

**Not covered here.** Real export shapes, units and asset readback are DA2.

## 4. Final focused suite (final source; one guarded unit per file; `final/runs/*.log`, `*.exit`)

| File | Result | Child exit | Peak RSS (kB) |
|---|---|---|---|
| test_ipcch_table_producers | 29 passed (incl. Node regeneration; PATH includes nvm node) | 0 | 216728 |
| test_ipcch_production_e2e | 2 passed | 0 | 463048 |
| test_ipcch_ee_transport | 24 passed | 0 | 193728 |
| test_ipcch_entrypoint_v2 | 21 passed | 0 | 403708 |
| test_ipcch_run_v2 | 13 passed | 0 | 405404 |
| test_ipcch_produced_tables (CP1) | 28 passed | 0 | 152276 |
| test_ipcch_climate_tables | 9 passed | 0 | 151140 |
| test_ipcch_climate_run | 4 passed | 0 | 131288 |
| test_ipcch_climate | 8 passed | 0 | 131432 |
| test_ipcch_climate_ee | 14 passed | 0 | 159356 |
| test_ipcch_climate_ee_seasonal | 13 passed | 0 | 165496 |
| test_ipcch_generation | 11 passed | 0 | 419924 |
| test_ipcch_spi_spei / _seasonal | 4 / 4 passed | 0 / 0 | 139588 / 157740 |
| test_delivery_job | 29 passed | 0 | 228228 |
| test_fews_adapter | 13 passed (300 rasterio warnings) | 0 | 492772 |

- **Total:** 226 passed, 0 failed, 0 skipped (16 files).
- **Checks:** `py_compile` exit 0; `git diff --check` exit 0.
- **GitNexus `detect_changes`: risk HIGH.**
  - 12 changed files, including the user's AGENTS.md and the Supervisor's PROGRESS.md.
  - 12 affected processes: the climate `update_monthly` / `update_seasonal` flows, `export_table` and `fetch_season`.
  - Every one is exercised by the suites above (`final/gitnexus-detect-changes.txt`).

**Intermediate runs (kept, not final evidence).**
- `final/runs/test_ipcch_ee_transport.INTERMEDIATE-stale-message.*`: 1 failed / 23 passed.
  - The old regex expected `start failed (task T0; cancelled)`; the message now also carries the request ID, which is part of the requested durable identity.
  - Behaviour is unchanged. The regex was updated (sha `364d41bc…`) and the rerun gives 24 passed.
- `final/runs/test_ipcch_{table_producers,production_e2e}.INTERMEDIATE-pre-composite-dates-fix.*`: these ran before the Supervisor's `composite_dates` correction.
  - The producer file showed 28 passed + 1 skipped, the skip being the Node test (Node absent from the service PATH).
  - Both files were rerun on final source.
- `nodes/*`: single-node bring-up runs. They include a stale-assertion timeout run, harness world fixes, and pre-RPC-cap runs, each labelled in its filename.

## 5. AC8 / R10 lifecycle coverage

**Generation level** (`test_ipcch_production_e2e`). The smoke world (roster 11/12/13) runs with M=2027-03, so O=2027-01:
- Real `TableProducer` → `EETransport` → table providers over the controlled EE world.
- 13 exports: Aqua 2026 prior-year VI, plus the 2020–2026 and 2027–2032 chunks.
- Readback is mapped into the consumers.
- The saved 2027-01 versions record `produced_tables` for each source, the batch manifest receipts link the run, tasks and assets, and `retained_inputs` point at the new versions.
- A second run of the same month exports nothing and reports the skip.
- A 2027 VI year with an explicitly empty composite listing makes O unavailable (`ClimateSourceMissing`; drought months still saved). A later run with a new ID recovers, producing VI only.

**Lifecycle cases (`test_ipcch_table_producers`, `test_ipcch_ee_transport`).**
- Completed, FAILED, cancelled-after-failure, interrupted wait, timeout with bounded cancel, start failure, and lost start response with a real `ee.batch.Task`.
- Destination already exists; duplicate reservation; same-day new run ID; PATCH32 count; malformed output (wrong prefix, Inf, values in an incomplete month); COMPLETED without the asset.
- Expired deadline: no EE call; expiry between read pages; per-request cap with settings restored, including on failure.
- Paginated listing with an unreadable asset on a later page.

**Entrypoint (`test_ipcch_entrypoint_v2`).**
- An October real request redelivered after current reports November returns its durable status with no admission, no current read, no provider build and no writes. The same body under a new run ID is rejected by R39 with no reservation written.
- Changed request conflict; reserved-without-status refusal; durable failed status after reservation.
- The persisted deadline reaches the provider factory; the config caps the budget; `real_providers` wiring is checked.

## 6. Choices to confirm at the gate
1. **Post-2026 chunks** are 6-year blocks from 2027 (2027–2032, 2033–2038, …). This is not defined upstream; the reader and producer share `year_chunks`.
2. **Completeness as table properties.** `days_present_*` and `composite_dates` are extra columns added to the upstream output schema. The consumers ignore them; they exist so completeness comes from the same graph that applies the masks.
3. **Scope of re-production.**
   - Every demanded VI year is re-produced, including the prior year in January.
   - A demanded drought chunk is re-produced in full, which recomputes the 2020 fit-input months (design: record the version; no splicing).
4. **Production failure.** Production runs at provider construction, before any climate save in that run. A production failure therefore blocks the whole climate step for that run, including the raster bases.
   - Completed sibling assets of a failed run stay unexposed orphans.
5. **Budgets.** RPC cap 60 s; SDK retries 0. Status exceptions remain retried by the bounded waiter; other RPC failures stop the run without automatic export resubmission. Run budget = entry time + up to 4 h.
6. **Inputs.** `real_providers` uses the default `AssetRefs()` (`projects/han-sandbox-505315/assets/` partitions). Readability under the runtime identity is a CP5 check.

## 7. Remaining CP3 wiring (CP2 additions to `research/cp3-supervisor-seams.md`)
- Deployment JSON must add `producer_asset_root` (e.g. `projects/feisty-flames-511718-d4/assets/`) and may add `run_timeout_seconds` (≤ 14400, consistent with `setup.py --task-timeout 4h`).
- Workflow `run_job` must pass `--v2-config`; the image installs the config and the accepted artifacts.
- Runtime smoke provider factory: it must accept the new kwargs `root`, `deadline_utc` and `execution_month`. The test fixture now takes `**_`.
- Operator v2 submission: UTC-month freeze; the status reader must read `v2_run_status.json` and may surface `v2_reservation.json` and the `deadline_utc` field.
- CP5: verify han-sandbox partition reads and EE asset-root write access under the runtime identity before any live export. DA1 and DA2 remain deferred.
