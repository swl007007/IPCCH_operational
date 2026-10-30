# Second grilling pass — findings and disposition

2026-10-30; HEAD `69aa74a372f40581d6759a5703e7ec331ba4af63`.
User requested a renewed grilling pass, not implementation. Three read-only scouts
inspected publication continuity, operator semantics, and producer scientific/data
edges. Main checked the cited entrypoint, request schema, matrix/provider and
publication code. No cloud calls or product edits. A scout performed a small
in-memory all-null drought-provider reproduction and JS function-text comparison;
this is offline evidence only, not a live export or full test-suite result.

## Findings resolved in the technical specification

| Finding | Source evidence | Disposition |
|---|---|---|
| Whole-run EE deadline was described as effective but is not passed by v2 | `cloud_pipeline/cloud/ipcch/entrypoint_v2.py:173-175`; transport default 21600 seconds, deadline optional at `ee_transport.py:66-69,143-146`; Cloud Run 4h at `deploy/setup.py:74-75` | Wire one persisted run deadline from deployment limits through producer/transport/acquirer; preserve cleanup reserve; no mandatory manual deadline flag |
| v2 skips legacy `run_once` | `cloud_pipeline/cloud/orchestrator/delivery_job.py:1037-1046` returns directly through v2; `entrypoint_v2.py:176-191` only rejects existing workdir/writes create-only final status | Reuse reservation/identity/status patterns at v2 admission so duplicate execution is prevented before mutation; verify direct and event invocation |
| A separate `/v2` root could publish a parallel current and lose inherited FEWS/legacy activation | `publication.py:41-42,55-57`; `release_v2.py:44-54`; legacy `pipeline.py:729-733` | Match actual existing current root/namespace; local expected URI is `gs://food-crisis-test-ipcch-data/monthly-staging/current.json`; verify live config before mutation |
| Smoke may not be nested under bucket-root real | `cloud_pipeline/cloud/ipcch/run_v2.py:59-61` | Use an existing permitted nonnested smoke location; verify concrete deployment paths |
| All-null target column can be classified as published and saved permanently | `climate_tables.py:237-257`; `climate.py:241-249,286-303` | Persist/read explicit source-calendar completeness for new outputs; separate incomplete month from legitimate masked polygons; no any-finite proxy |
| Old wide table can shadow new narrow update's columns | `climate_tables.py:197` keeps first whole column | Resolve exactly one chosen asset for each source/chunk; no concatenation of old/new versions |
| User might be forced to handwrite request plumbing | legacy `pipeline.py:1711-1713` requires month/cutoff/deadline; exact v2 fields at `delivery_request_v2.py:58-59` include none of cutoff/deadline | Reuse CLI/config with automatic hashes/generations/operator/timestamps; accepted D5 uses submission-time UTC M; no new web surface |

No other-system production is added. Existing current FEWS inherits byte-for-byte;
if current is truly absent, existing first-publication code accepts IPCCH-only.
A broken old pointer is not absent (`publication.py:75-89`). Tests already cover
legacy FEWS inheritance/corruption (`tests/cloud/test_ipcch_release_v2.py:88-124,
148-178`) and activation (`test_ipcch_legacy_guards.py:23-32,91-95`); add config-level
same-pointer/nonnested-root checks rather than a new migration system.

## Producer scientific constraints

Upstream directory is the sibling `IPCCH_shared_folder/seasonal/`.
`01_vi_prcp_et0_update.js:568-717` and `02_et0_patch32_update.js:248-420` contain
equivalent daily ET0 functions after comments/whitespace removal. Same nine ERA5
inputs, FAO56 arithmetic, units and daily nonnegative clipping apply to ordinary
and 30 km buffered original polygons. Buffering a centroid instead would change
the intended spatial method. Port once and preserve both geometry branches.

New PRCP/ET0 graphs currently judge complete months by daily collection count equal
to expected calendar days. Their intermediate QA properties are not explicitly
exported as per-month table evidence (`01:424-430,451-457,767-773,793-798`; PATCH
monthly return `02:494-499`). In the inspected consumer, both a genuinely published
but spatially masked month and an unpublished all-masked placeholder can have an
existing mean column. Offline reproduction returned `published all_nan=True` for
SPI and SPEI with all-null target inputs. Saved keys then suppress future fetching.
Metadata-based availability is therefore required in the integration, not a new
scientific algorithm. Preserve complete-month versus area-missing semantics and
prove incomplete-then-available recovery. Do not change count-based scientific
definitions speculatively; no real duplicate-day source failure was established.

The fit still uses 1991-2020 plus 1990 leading observations
(`spi_spei.py:26,46-75`; `climate_tables.py:230-231`). Updated 2020-2026 raw tables
include 2020 fit inputs; refreshed source vintage may change *new* indicator values.
No live source revision was measured. Keep the delivered script computation and
record raw input identities; do not silently splice frozen 2020 values or add a
numerical train/serve equality gate. Archived 10-29 PRD R40 permits recorded method
differences for new months. Existing saved indicators remain append-only (R8).

Production demand is shared: generation creates the provider set once
(`generation.py:200-202`), but monthly and seasonal drought instances have separate
caches (`climate_run.py:93-99`). Raw ET0/PATCH32 and PRCP outputs are common to many
indicator calls. Deduplicate at run/source/period/input identity, not indicator name.
Test one raw export for repeated monthly/seasonal SPI/SPEI demand. Preserve Aqua
prior-year composite overlap and the full raw history needed for the fit.

## Product decision resolved by the user

**D5: routine execution month M.** Current v2 supports both current UTC and earlier
months, rejects future M, and rejects current publication older than the existing
IPCCH current (`delivery_request_v2.py:152-175`). It does not choose M automatically.
On 2026-10-30 the user selected "自动采用提交时的UTC当月". Routine submission
derives/fixes M from the same UTC instant as prepared_at; O and targets follow M.
Queue delays, midnight/month/year changes and redelivery cannot change that request.
Keep existing explicit-month compatibility for exceptional authorized reruns.
This resolves the last user-owned decision found by this pass. The consolidated
final planning review and subsequent implementation approval are still required.

Accepted D1-D4, particularly deferred live incremental DA1-DA2, are unchanged.
No new checkpoint, timer, retraining, web UI, or current-pointer migration is added.
