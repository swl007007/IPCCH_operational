# IPCCH real E2E integration — design

Status: approved for execution under `execution-protocol.md`, 2026-10-30.
`prd.md` is authoritative for accepted D1-D5, AC1-AC9 and deferred DA1-DA2.
Implemented and accepted 2026-10-31: real full-roster publication/readback and the
normal-config finish are complete. Evidence is in `research/cp6/`; the earlier
design's prospective statements describe the agreed implementation requirements.

## Existing route to complete

```text
submit that month's complete keep/refresh choices + associated assets
    -> validate selections; freeze submission-time UTC M/O/targets and pinned request
    -> GCS v2 request (generation + model/input pins)
    -> Eventarc / oct-delivery-trigger Workflow
    -> oct-delivery Cloud Run job
    -> delivery_job run --v2-config <installed deployment JSON>
    -> entrypoint_v2 (installed accepted model + handoff, real providers)
    -> validate input/model references -> acquire required locks
    -> plan eligible climate periods and their upstream table dependencies
    -> build EE producer graphs -> submit Asset exports -> bounded wait/readback
    -> run-bound table asset map -> generation / retained updates
    -> 527-feature assembly
    -> H2 / H8 / H14 inference -> validated outputs
    -> production current -> GCS pointer and referenced artifact readback
```

The existing `monthly-prepare` job and legacy routes remain subject to compatibility
checks. The IPCCH v2 source acquisition is wired by `entrypoint_v2.real_providers`;
installing new job defaults alone will not fix Workflow's explicit argument override.

## Asset resolution and producer boundary

Create the table mapping automatically from this run's validated producer receipts
and pass it through `climate_run` to `TableRefs.asset`. Deployment config supplies
the output root and fixed historical inputs; it must not require monthly editing
of seven IDs. Keep existing resolution for dependencies outside the produced map.
Do not globally rewrite `AssetRefs` and `TableRefs` roots together.
Resolve exactly one table per family/chunk. `_wide_month_matrix` currently keeps
the first same-named column (`climate_tables.py:197`), so appending a narrow update
after an old wide table can silently lose new observations. Replace the mapped
chunk reference rather than joining both. Preserve full input history required by
the 1991-2020 fit and 1990 leading months. The supplied 2020-2026 producer recomputes
2020 raw values too; record its version instead of silently introducing a different
baseline-splicing algorithm. Saved indicator keys still must never be rewritten.

Destination root: `projects/feisty-flames-511718-d4/assets/`.
Derive a common immutable version from the execution context and unique run ID;
the current wall-clock-only `_UPDATE_YYYYMMDD` tag collides on same-day reruns and
can split a run across midnight. The table below is the 2026 example, not a fixed
year limit. Derive necessary current/prior VI years and drought chunk coverage
from eligible months/windows, preserving completed historical chunk names. The
reader and producer must agree on post-2026 chunks; test 2027 and January overlap.

| Existing basename | Producer |
|---|---|
| `S2E3_VI_CURRENT_ADMIN_TERRA_Y2026_CMG_V3` | `01_vi_prcp_et0_update.js` |
| `S2E3_VI_CURRENT_ADMIN_AQUA_Y2026_CMG_V3` | `01_vi_prcp_et0_update.js` |
| `S2C3_DROUGHT_ADMIN_PRCP_CHIRPS_Y2020_2026_V3` | `01_vi_prcp_et0_update.js` |
| `S2C3_DROUGHT_ADMIN_PRCP_PERSIANN_Y2020_2026_V3` | `01_vi_prcp_et0_update.js` |
| `S2C3_DROUGHT_ADMIN_PRCP_ERA5LAND_Y2020_2026_V3` | `01_vi_prcp_et0_update.js` |
| `S2C3_DROUGHT_ADMIN_ET0_FAO56_Y2020_2026_V3` | `01_vi_prcp_et0_update.js` |
| `S2C3_ET0_PATCH32_Y2020_2026_V2` | `02_et0_patch32_update.js` |

The scripts currently read their dependencies from `han-sandbox-505315`; copying
seven outputs does not remove this prerequisite. Validate those reads under the
identity that produces the outputs and validate all runtime dependencies under the
Cloud Run identity. User readability and public visibility are different claims.

Do not infer completed data from a year/month column alone. Inspect exports for
`evi_YYYYMMDD_mean`, `prcp_YYYYMM_mean`, and `et0_YYYYMM_mean`, units, non-null coverage,
and source cutoff. Handle both omitted and all-null fields conservatively in the
implementation/tests; real export-shape and unit checks are deferred DA2. Preserve
existing missing/unavailable/failure semantics; absence of live checks is not proof
that a month is available.

Carry explicit source/month completeness metadata from newly produced graphs into
the export/read receipt and provider availability check. Use the scripts' source
calendar completeness definition unchanged; per-polygon masked means remain valid
missingness. Incomplete source month => unavailable even if a mean column exists;
complete source month => availability does not depend on a finite pixel count.
Missing/contradictory metadata on newly produced outputs => processing failure.
Do not retrofit invented metadata to old static/historical tables. The existing
`SourceOutcome.extra` is not enough by itself: `_collect` ignores it, so ensure the
accepted source/period/receipt evidence reaches the retained/batch record. Test
incomplete-then-published recovery without first saving an all-null placeholder.

CP1 clarification: for newly produced drought chunks, completeness covers the
consuming source's actual input window (T-2..T monthly; season start minus two
months through its end). An explicitly incomplete input makes that source's
dependent result unavailable. A persistent source-calendar gap remains unavailable
under the same rule; no override is added. Other months, including fit-baseline
months, retain upstream masked/NaN fit behavior. Another source's gap does not gate
this source. Static/history tables retain their original availability contract.

The accepted D2 requires unattended production and exports. Implementation:
port the two scripts' EE calculation graphs into the existing Python runtime, using
its pinned `earthengine-api` and extending `EETransport` with a narrow table-to-Asset
path. This avoids adding Node/another EE SDK to the Python image. Preserve source
formulas, QA, reductions, scaling, buffers, and source IDs; compare graph contracts
against the supplied JS; representative real-output comparison is DA2. Keep source hashes and
the actual runtime implementation in the repository/image, with no Dropbox path
dependency in production. A wrapper around manual Code Editor tasks is insufficient.

Reuse reservation, durable task IDs, bounded polling, cancellation, and conditional
receipt writes. After completion, validate the destination asset/schema/periods
before exposing its ID to consumers. EE completion alone is not data readiness.
Keep export failures distinct from legitimate source unavailability. Do not convert
a failed export into a successful run using old IDs. Submit each needed table once
per run, not once per consuming indicator/area; derive dependencies before launching.
Duplicate events must not resubmit work. Same-day new runs use different asset IDs.
Keep the existing bounded failure/retry contract; no open-ended resubmission loop.
Reuse existing run/request reservation semantics at the v2 entry boundary, before
mutable provider execution. Legacy `run_once` is bypassed by the v2 dispatcher;
Workflow deduplication alone does not protect direct entrypoint redelivery. Preserve
request URI/generation/hash under the run ID; unchanged completed identity returns
durable status, changed content conflicts, and active/failed/indeterminate identities
cannot launch again under that ID. Operator-initiated retries use a new run ID.

For fully retained periods, routine operation may legitimately skip acquisition;
record that skip rather than running unused exports to create apparent E2E proof.
AC8 exercises the full incremental control/data path offline. Its real EE execution
and retained-consumption proof are deferred DA1-DA2, not simulated evidence of a
live incremental pass. This does not permit leaving the producer path unimplemented.

## Human input and trigger boundary

Manual channels remain those already present in `delivery_request_v2`: ACLED,
WFP, history_snapshot, and eight research families (`nino34_anom`, `bbg_staple_food`,
`bbg_oilgas`, `bbg_soybean_oil`, `bbg_global_food`, `food_price_index_WB`,
`idp_national`, `idp_local`). Each declares keep/refresh; refresh uses its existing
pinned file and declared interval/region contract. History snapshot replacement
has no interval. WFP consumes the research-prepared file, not a new operational
HDX algorithm. Fixed model/geometry/reference asset maintenance remains explicit.

Build the v2 request from those inputs plus installed configuration, generating
run ID, timestamps, immutable references, and expected current generation. Do not
silently inherit last month's refresh or choose keep when refresh fails. Accepted
D3 makes selection submission the sole start action: validate the completed choices
and asset references, then create the pinned request object as the final submission
step. The existing event route starts it immediately. Asset uploads and incomplete
selections alone do not constitute a submission. Do not add a calendar timer or
separate run button. No manual handoff of EE IDs, feature-batch IDs, inference jobs,
or publication is permitted.
If retaining operator status commands, read `v2_run_status.json` for v2 runs.
Reuse the existing CLI plus deployment/selection files, not a new UI. Resolve asset
generations/hashes automatically; users supply their source choices and associated
files/declared coverage, not raw request plumbing. Accepted D5 derives routine M
from the UTC instant captured as prepared_at when the complete choice set is
submitted. Compute O=M-2 and targets M/M+6/M+12 from that single value; persist them
with the request identity. Asset upload time, workstation timezone and delayed job
start do not change the selected month. A network redelivery reuses the original
identity/month; a deliberate new submission uses a new identity/submission instant.
Never re-evaluate M midway through exports. Existing explicit-M v2 requests remain
available for exceptional authorized reruns under current validation rules; do not
add a routine month prompt or silently alter an explicit month.

The combined v2 route already passes its generated batch directly to inference and
publishes current. Reuse it. A v2 candidate is not directly promotable under the
existing contract; an optional staged candidate would require a new inference-only
current request, which must also be automated if used. Do not add a promoter.

## Sparse PATCH32 alignment

Repair the shared matrix construction or its narrow patch-input call path, so both
monthly and seasonal providers align sparse PATCH32 on their requested admin axes.
Absent patch rows become NaN; primary tables still require the requested roster.
Keep duplicate detection and numeric parsing, and never replace a present primary
ET0 value with a patch value. Handle legitimate subset rosters without requiring
all 32 patch polygons to be selected in every consumer invocation.

Tests must exercise all four affected SPI/SPEI monthly/seasonal routes. Keep the
scientific fit, baseline period, seasonal windows, and feature naming unchanged.

## Accepted model and artifact installation

Local source references from the prior investigation:

- Envelope:
  `/home/swl007007/projects/food-crisis-research/scratch/h2h8h14-final/envelope/ipcch-combination-envelope-v2-accepted.json`
- Envelope SHA256:
  `03b938427391aa15d3786377151e922bfdb97cc161f312b72ebed9f596c89596`
- Package:
  `/home/swl007007/projects/food-crisis-research/scratch/h2h8h14-final/package-build/out-r1/package/`
- Package manifest SHA256:
  `18b91d454163ac9ff9833d8127108e731b2f9d95069fb26fd5e7e8877a115f22`
- Handoff:
  `/home/swl007007/projects/food-crisis-research/scratch/h2h8h14-final/handoff-build/out-r5-accepted-v1`

The outer accepted envelope governs acceptance; the inner package manifest's
`candidate` label is not grounds to replace the accepted combination. Fully verify
the bound bundle before installation; previous checks did not rehash every large file.

| Scientific horizon | Runtime directory | Target with O=M-2 |
|---|---|---|
| H2 | `scope_0m` | M |
| H8 | `scope_6m` | M+6 |
| H14 | `scope_12m` | M+12 |

Use the existing `installed.real` envelope/package/bundle fields and exact request
pins. Extend `cloud_pipeline/deploy/build_context.sh` to stage verified artifacts
and deployment JSON into its temporary build context, and install them at the
existing `/opt/ipcch/{envelope,package,handoff-bundle}` contract paths in the image.
Large input/model files stay outside Git; record their hashes and the resulting
image digest. Check file availability and binding in the built image before deploy.
Configure the required smoke section independently with isolated fixture paths;
never satisfy it by reusing real history. Do not add a new registry or download
unverified mutable latest artifacts at runtime. If build limits invalidate this
installation method, report the evidence and revise this design before deployment.

## Deployment configuration and identity

Existing local configuration is
`/home/swl007007/ipcch-operator/food-crisis-test/project.json`.
Expected project/region: `feisty-flames-511718-d4` / `us-central1`.
Expected runtime SA:
`monthly-runtime@feisty-flames-511718-d4.iam.gserviceaccount.com`.
Expected Workflow SA:
`monthly-workflow@feisty-flames-511718-d4.iam.gserviceaccount.com`.
These are local records, not refreshed live IAM evidence.

Separate EE asset addresses from GCS storage:
`gs://food-crisis-test-ipcch-data/` holds runtime data, while
`gs://food-crisis-test-ipcch-requests/requests/...` is the request input route.
Specify concrete real/smoke output roots, retained roots, trusted prefixes, installed
paths, EE compute project, export root, and work directory in the deployment config.
Publish through the existing checked production current flow, as accepted in D1.
Resolve the exact current object from the deployment configuration and preserve
existing consumers. A candidate may be an intermediate validation artifact, but
cannot be the task's final endpoint. No new web/dashboard surface is required.

Expected local-config target is
`gs://food-crisis-test-ipcch-data/monthly-staging/current.json`: v2
`roots.real=gs://food-crisis-test-ipcch-data` and production namespace
`monthly-staging` reproduce legacy pointer addressing. Verify against current
deployed config before applying; do not invent a different `/v2` publication root.
Read and preserve the same pointer's FEWS member byte-for-byte if present. If the
pointer is genuinely absent, existing first-publication semantics permit IPCCH-only;
do not add FEWS generation/migration to this task. A broken pointer/member is an
error, not an empty initial publication. Legacy activation protection and inheritance
must observe this same root/namespace. Real/smoke roots must not be nested; when
real is the bucket root, smoke needs another existing permitted nonnested location,
not a child prefix. Resolve that concrete location during deployment preflight.

The CP3 compatibility investigation found that the current legacy operator state,
environment and acceptance records bind image 487a2315. Replacing the shared job
image requires genuine compatibility evidence for the unchanged FEWS packages,
then a new accepted baseline and initialized operator destination through supported
commands. Preserve the old state. Use the existing maintenance/candidate/verify/
promote/release sequence, compare the candidate to the pinned current delivery, and
only then use the new destination. Temporary failure of old image-bound requests
under a maintenance hold is not final consumer compatibility. Keep the new image's
legacy IPCCH activation guards. The ordinary pre-activation legacy window remains
unchanged; no new pre-chosen v2 run-ID feature is required for this cutover.

2026-10-31 runtime probes confirm EE initialization and GCS access but deny reads
of the two known han assets; personal EE credentials can read metadata, not ACLs.
No personal credentials are deployed. This round's exact October/August retained
history produced empty demand/jobs and an explicit already-retained skip in the
actual batch manifest. Future incremental operation requires upstream-owner sharing to the
runtime account. It is a known permission gap, distinct from deferred numerical
incremental validation. Actual Cloud Run GPP probes recorded HTTP 404 for January
through August 2026; the ledger marks those months unpublished.

## Real acceptance and rollback

Current-round live acceptance links submitted choices -> real request/event/job ->
accepted retained inputs -> assembled features -> H2/H8/H14 full-roster outputs ->
production current -> bucket readback. Record actual source work and legitimate
retained-history skips. With October/August, an empty climate call list is expected
and does not fail this round. It also cannot establish incremental correctness.

The inspected initialization contract loads every accepted CSV in full and binds
the exact handoff hashes; an isolated root seeds the same August coverage. There
is no cutoff option. Monthly scheduling skips saved month keys even when values or
individual sources are missing; seasonal scheduling skips saved area/season keys.
The original envelope cannot authorize a truncated history.

D4 preserves the original accepted history/envelope and defers live incremental
acceptance. The first natural new origin is September (M=2026-11 when actually
eligible). Do not run it, schedule it, or wait for it as part of current task closure.
Do not build an earlier checkpoint. A later separately initiated run must prove
real upstream exports -> acquisition -> retained append -> feature consumption ->
current, plus actual export schema/units (DA1-DA2). No production history deletion,
manual HEAD edits, or future-date bypass is allowed.

For this round use M=2026-10/O=2026-08 if still admissible against the live current
release. If current has advanced, do not publish an older month or silently expand
into deferred incremental acceptance; report that changed prerequisite. The source
planner remains production-correct rather than adding a test-only skip flag.

Record source completeness and updates separately from inference/publication.
ACLED needs its complete origin window on first refresh; the handoff does not seed
that history. Candidate inference can persist source updates and is therefore a
state-changing cloud operation even if it does not change `current`.

Before deployment, record the old job image/config, Workflow revision, store roots,
and current pointer generation. Versioned new assets permit configuration rollback
without overwriting the prior assets. Publication uses the existing checked pointer
flow. Read back the current pointer and referenced delivery/prediction objects,
checking generations, run/model identity, target months, and contents. Merely listing
an unrelated output object in the bucket is insufficient. Keep valid retained updates
after failures; do not promise rollback of all data writes merely because the image
or pointer can be restored. Retain the existing 4-hour job limit/zero task retries;
the present v2 provider factory omits `deadline_utc`, so explicitly wire a persisted
whole-run deadline from deployment/runtime limits into producers and source acquirers.
Cap EE polling by that deadline minus its 15-minute cleanup reserve. New tasks may
not start after the reserve is reached; status/cancellation must still be recorded.
Duplicate delivery must not reset the deadline. Do not add legacy cutoff/deadline
fields to the exact v2 schema merely to reuse CLI flags. Record resource identities/
limits before launch and do not auto-escalate them.
