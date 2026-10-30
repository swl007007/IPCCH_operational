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
