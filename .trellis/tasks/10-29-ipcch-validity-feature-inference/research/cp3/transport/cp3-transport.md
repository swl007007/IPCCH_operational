# CP3 concrete EE/GCS transport for the climate providers (Executor, 2026-10-30)

Supervisor seam finding: EEBackend/TableBackend were protocol + test mocks only. `cloud/ipcch/ee_transport.py` now
implements both on the existing production patterns (no live EE compute run; private-asset live limit stays deferred):

| method | implementation | failure semantics |
|---|---|---|
| `image_times` | `CloudSourceAcquirer._list_images` (prepare.py: one listing call, time_start + id) - not `gee_published_months` (rejects daily multiplicity) | listing error / malformed entry -> `EETransportError` |
| `missing_assets` | `ee.data.getAsset`; the ambiguous "does not exist or doesn't allow" message is resolved ONLY by a successful `ee.data.listAssets(parent)` that omits the id | listed-but-unreadable, unlistable parent, 403/permission/auth/timeout/any other error -> `EETransportError` (never "absent") |
| `export_table` | `Export.table.toCloudStorage` CSV under `<output_root>/ipcch_exports/<run_id>/tables/<description>` (prefix must be empty), task record create-only, `evi_service._wait_for_ee_task`, deadline cleanup reserve (prepare.py pattern) | start/FAILED/CANCELLED/timeout/!=1 CSV object -> `EETransportError` |
| `read_table` | exact generation (`prepare.GcsPinnedReader`), sha256 receipt | not found / unreadable CSV -> error |
| `read_asset_table` | `ee.data.computeFeatures(PANDAS_DATAFRAME)` of properties without geometry; integral admin_code normalised | any error, empty, non-integral id -> error |
| `from_environment` | `storage.Client()` + `ee.Initialize(project=...)` + `GCSObjectStore` (prepare.py worker pattern) | - |

`EETransportError` subclasses `ClimateProcessingFailure`: it blocks generation; climate_tables reports a current table as
unavailable only for definitive absence (test: listed-but-unreadable current S2E3 table -> failure).

Tests `tests/cloud/test_ipcch_ee_transport.py` (10): real offline client builds the graphs; only `ee.List.getInfo`,
`ee.data`, export tasks and storage (FakeGcs from test_prepare) are faked. Daily multiplicity accepted; definitive vs
ambiguous absence (listing never consulted for 403/timeout/auth); inaccessible current table is a failure; create-only
export pinned by generation, later overwrite does not change the pinned read; export failures; deadline reserve; asset
tables; MonthlyEEProvider -> transport -> update_monthly saves the exact roster (declared 6227 dropped), receipts order
image_times/missing_assets/export/read, exported collection is the ported reduceRegions graph.
Regression: `transport-tests-run1.log` test_ipcch_*.py + test_prepare.py 150 passed rc 0.

## Supervisor review fixes (8d031db)
- Reserve before submit: the `<run>/tasks/<description>.json` record is written create-only (state `reserved`) BEFORE
  `Export.table.toCloudStorage`/`start`; a second call for the same run/description (e.g. after FAILED or no output) is
  refused with no second submission. After start the task id is persisted (state `submitted`); if that write fails the
  started task is cancelled and the error raised. Submit failures and terminal states are recorded
  (`submit_failed`, `FAILED`/`CANCELLED`, `timeout` + cancel outcome, `completed` + uri/generation).
- IPCCH wait loop (`EETransport._wait`; the shared FEWS `evi_service._wait_for_ee_task` is untouched): budget =
  min(timeout, authorization deadline - cleanup reserve); every sleep = min(poll, remaining); on budget exhaustion
  `task.cancel()` and the cancellation recorded; all outcomes are `EETransportError` (processing failure).
- Tests (13 in test_ipcch_ee_transport.py): no second submit after completion or FAILED; fake-clock timeout with
  timeout 100/poll 60 -> sleeps [60, 40], task cancelled, record `timeout`/`cancelled`; deadline 930 s - reserve 900 s ->
  sleeps [30]; task id persistence failure -> started task cancelled. `transport-fix-tests-run1.log`.

## Second review residuals (72f8cd8) + GPP retry (f1af645)
- Deadline re-checked immediately before submission (after reservation/prefix check): exhausted -> record
  `deadline_before_submit`, nothing submitted.
- Creation failure (no task object) -> `create_failed`, nothing submitted. `start()` failure is ambiguous (response may
  be lost): the known task id is kept, a best-effort single `cancel()` is attempted, the record (`start_failed`, task id,
  cancel outcome) is written once best-effort (no retry) and the receipt + exception carry the id.
- Task-id persistence failure: cancel attempted; the exception and the `export_untracked` receipt carry the task id and
  the cancel outcome even when cancel also fails. No automatic resubmission (the reservation refuses a second submit).
- GPP: the adapter's saved rows (`method_id`) are the authoritative evidence that a month was published and saved; a
  retry after an interrupted ledger write repairs the ledger to `published` without re-fetching, so saved no-valid-pixel
  NaN rows are never refilled; adapter-saved months lacking a `published` record are retry candidates.
- Tests: deadline consumed during reservation -> no task; lost start response -> T0 kept, cancelled, recorded, never
  resubmitted; persist + cancel failure -> T0 in exception and receipt; GPP injected ledger-write failure (previously
  unpublished and fresh month) -> retry downloads nothing, ledger repaired, NaN rows identical.
  `transport-gpp-repair-tests-run1.log`: 79 passed (transport, gpp, prepare, climate_ee, climate_tables).
