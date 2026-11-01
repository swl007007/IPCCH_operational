# Supervisor checkpoint ledger

Authority: execution-protocol.md and user's spec-scoped cloud preauthorization.
No Trellis Audit. Checkpoints are technical reviews, not repeated user permissions.

## Initialization — accepted

- User goal accepts the final D1-D4 specification and appoints Herdr Opus 5.5 1M.
- Executor handshake: actual session 6a490ae1-ee00-43f9-bdfc-c887c9816c09, w1A:p8,
  same cwd, current model metadata claude-opus-5-5 and live 1M-context identity.
- Supervisor live session is 01a192d5-1f68-7641-b61e-ff157a279912 in w1A:p2.
- Prepared CSV/selection/source hashes, guarded child exits and context manifests
  verified. Raw file preserved; ACLED interval 2026-10-17..23.
- Source baseline HEAD 013a679; no product change is proposed. AGENTS.md remains
  an unrelated user change and must be excluded from scoped commits.

## CP0 — accepted for one CP1 attempt (2026-11-01 UTC)

Supervisor read cp0-report.md and key live/config/pre-snapshot artifacts, inspected
demand/ACLED/lineage/DA2 helper code and source anchors, and independently verified
all 38 SHA256SUMS entries. Product/deployment diff from 115798f is empty. Demand
guard: child 0, 2:40, RSS 1,058,488 KiB; helper checks 8 + 3 passed, child 0.
Current is 1793461128385732; store has 56 HEADs/65 versions unchanged from prior
acceptance; model/order/roster pins agree. Nonempty November demand: all 13 monthly
bases need September, seven produced tables, no seasonal append. ACLED pre v1 has
242,341 rows, zero inside the approved week, expected 470 appended modeled rows.
Live limits remain 8 CPU/32 GiB/14400 s/zero retries. Two unguarded lightweight
readbacks are disclosed; no duplicate reads were required to reconstruct guard
evidence. Ordinary JSON/AST inspection is not claimed to have guard telemetry.

CP1 released under the existing user authorization, after packet freshness checks.
Use the guard also for local submit; an interrupted response is UNKNOWN until
durable identity/status reconciliation. No second monthly run or limit expansion.
Preserve CP0 frozen artifacts; put further operation logs/helper copies under CP1/CP2.

Before CP2 live use: distinguish table-to-asset task records from raster GCS task
records (the latter have no asset_id); retain both but join producer receipts only
to asset exports. Add a mixed-record self-check. Complete actual immutable content,
old/new climate key, batch provenance and VI baseline/current/alignment witnesses;
the draft summary checks alone do not establish them. These are acceptance-helper
work within scope, not a reason to delay the authorized runtime attempt.

Read-only forensic EE reads using existing local operator credentials are within
the user's preauthorization; label identity explicitly, do not deploy credentials
or count operator reads as runtime-SA evidence. D2 only covers naturally
unobserved witnesses, not observed failures.

## CP1 — terminal failure; bounded attempt reconciled

Run ipcch-real-9eee4305db494a35 submitted exactly once. Frozen state inspected:
prepared_at 2026-11-01T01:00:20Z, M=2026-11, expected predecessor 1793461128385732;
ACLED refresh 2026-10-17..23 with 17 declared regions and all ten keeps match.
Request generation 1793494821542586, SHA256
8b346d35db6294e9785e2c4099d143e96fc62a871ccbb1a36ecbfd5478ae26c2.
ACLED upload generation 1793494819786240 has expected e660c7e8 hash.
Source: research/cp1/frozen-state.json. Supervisor verified submit CHILD-EXIT 0
(peak RSS 162,752 KiB) and inspected reservation.json: same exact request identity,
reserved_at 01:02:09Z, deadline 05:02:09Z, timeout 14400 s. Executor identifies
Cloud Run oct-delivery-4jkcj, created 01:00:23Z, running. No successful production
or publication claim at that observation. CP2 mixed-record self-check reports
9 passed, child 0.

Final: execution oct-delivery-4jkcj ran 01:00:27–01:03:38Z and failed (exit 1).
Durable status fails generation at climate: feisty output-root listAssets returned
NOT_FOUND before the first export submission. Runtime locks released cleanly.
Supervisor inspected frozen status and verified all 42 CP1 SHA256SUMS entries.
AC1 and the bounded failure-record portion of AC7 are supported; DA1 failed.

## CP2 — failure reconciliation accepted; success criteria unmet

Supervisor verified all 41 CP2 frozen hashes and inspected failure-source-checks,
root diagnostic JSON, run status, failure-report and source path. Current remains
1793461128385732, locks absent. No this-run export task records, batch, delivery,
candidate or release were found. Only ACLED v1->v2 and acceptance v3->v4 changed.
ACLED +470 rows exactly match the pinned converted interval, with outside keys and
values preserved; ten keep histories are unchanged. Other automatic histories
remain unchanged. AC6 is supported for manual inputs; feature cutoff behavior was
not exercised because assembly was never reached.

AC2/AC3/AC5 remain unmet and AC4/DA2 unproven. D2 does not turn a pre-export failure
into an accepted natural non-observation. No second attempt, reset, deletion,
credential deployment, IAM change or product fix was performed.

Root metadata/listing under local EE credentials also returned HTTP 404, but the
caller email was not established; the earlier owner attribution is withdrawn.
An absent/uninitialized root is consistent with evidence; access is not fully
excluded. Supported root-create documentation and the bounded proposed recovery
are separate in supervisor-recovery-proposal.md. They are not execution approval.

## Original CP3 boundary — recovery scope decision subsequently granted

Preserve the failed attempt and its reconciled partial work in a scoped evidence
commit. Do not archive or mark the goal complete. Current PRD R8 authorizes only
one monthly attempt and excludes deployment repair; an additional attempt or the
proposed bounded initialization job required an explicit scope extension.

## D5 approved — 2026-11-01 UTC

User: "批准上述恢复与一次重跑"; goal resumed active. Same task and verified
executor w1A:p8 / 6a490ae1 continue. Spec/plan now permit the precise recovery in
supervisor-recovery-proposal.md: one 1 CPU/512 MiB/300 s diagnostic job on the
existing image and runtime SA, conditional single project-root create and readback,
then one additional all-keep monthly request. No third attempt or broader repair.
CP3 now denotes root recovery, CP4 the additional request, CP5 its acceptance and
CP6 final closure. CP0-CP2 frozen failure evidence remains unchanged.

## CP3 technical packet accepted; runtime result pending

D5 spec committed as 06c38da. Supervisor inspected payload f1cf0b28 and job
spec 3a89b5c1, checked exact embedded args/image/SA/resources, and independently
verified all 21 pre-execution SHA256SUMS entries. Guarded tests: 19 passed,
CHILD-EXIT 0, peak RSS 57,388 KiB. Early identity/deadline/optional-RPC findings
were corrected. One diagnostic job creation/execution released under D5.
The actual 300-second Cloud Run timeout bounds execution; initialize/paging
means neither total RPC count nor a guaranteed 280-second bound was proven.
Executor must correct those packet claims and retain the prior packet snapshot.
No monthly submission is released before actual root/identity/absence readback.

## CP3 runtime root readback accepted

Execution ipcch-ee-root-check-20261101-6z5f2 succeeded once, 02:17:13.758382
to 02:18:51.183235Z. Supervisor joined the raw IPCCH_ROOT_CHECK line to result
73f3e8fc and checked execution succeededCount=1. Expected metadata SA; initial
HTTP 404; exactly one successful FOLDER create; relist assets=[]; the pinned
transport returned the deliberately absent child. Monthly job/runtime settings
and Workflow revision/source/env are unchanged. All 23 top-level and 20 execution
hashes match. The first execution-manifest verification used the wrong cwd and
reported missing files; verification from exec/ succeeded. No evidence was changed.
CP4 preflight/preparation released; monthly submission awaits its fresh packet.
Root recovery does not prove toAsset export, DA1, DA2 or publication.

## CP4 additional submission released

Supervisor verified all 30 preflight hashes, selections 8092421f (11 exact keeps),
13 nonempty September monthly bases/seven producer jobs, six CHILD-EXIT=0 logs
and 12 helper checks. Inspected lineage_readback diff: adds ACLED v2 to keep
identity checks and removes second-refresh requirements, preserving first-refresh
evidence in CP2. Current 1793461128385732 and retained post-failure state unchanged.
One D5 monthly submission released after immediate fresh checks; no third attempt.
Bounded monitoring and CP5 readbacks may proceed without repeated permission.
CP3 evidence commit: 3e67076. Actual export/DA1/DA2/publication remain pending.

## CP4 submitted once; live execution pending

Run ipcch-real-fe7282ef75e747fd, frozen 2026-11-01T02:29:33Z, M=2026-11,
all eleven keep. Request #1793500174046456, sha b0f8b507e63c25be3b660827ab521ce3d7009f14f8d2d0a522f6003c73547d78.
Supervisor rehashed frozen request and checked inputs and submit CHILD-EXIT 0.
Expected current 1793461128385732. This exhausts D5 new-run submission authority;
continue monitoring/readback or failure reconciliation, never a third run.

## CP5 witness-helper readiness corrections (cloud run unchanged)

A read-only scout, confirmed by Supervisor source spotchecks, found helper gaps:
climate new-row checks allowed incomplete rosters/duplicate old keys; links allowed
vacuous empty retained_inputs; VI empty-sample handling could fail and no explicit
comparison disposition existed; expected wholly omitted fields were invisible to
raw union-only counts; PATCH fill candidates admitted nonfinite/bool values and
did not express selected ET0. Immutable content/delivery references need hash
checks or explicit dependence on the already verified exact generic readback.
Executor is assigned minimal corrections plus guarded self-checks in new cp5
copies, preserving frozen cp4 helpers. No product/deployment/scientific change.
These corrections enforce existing AC3/AC4/AC6 and D2, not new acceptance scope.

## CP5 helper corrections accepted for live readback

Supervisor inspected the exact revised diffs and required-table mapping to
generation._write; initial nine frozen hashes verified. Added direct links tests
cover valid required refs, empty refs, missing required ref and corrupted delivery
manifest. Final helper suite: 7 passed, CHILD-EXIT 0. Old cp4 copies preserved.
Source-level PATCH witnesses remain labeled as such, not an independent SPEI replay.
GitNexus fallback note lacked an actual pre-edit tool query; that process deviation
is retained and must not be relabeled. No product symbol was changed.
Live generic/lineage/climate/links/DA2 readback still required after run success.

## CP4 monitoring and AC6 readback readiness (03:05Z)

Same Executor session 6a490ae1 and the existing poll/sampler were reverified after
compaction. Guarded progress-6 (03:03:22Z, child 0) records all seven table exports
and seven raster exports completed; ten monthly climate HEADs moved. The three
producer-table bases spi03/spei03/evi_anom and publication are not yet observed.
No new submission, process restart or cloud mutation was performed by Supervisor.

ACLED cutoff helper 8f4571b2 was source-inspected; its guarded self-check passed.
The live check will bind batch/sidecar bytes, retained ACLED v2, all observed ACLED
sections and the bound roster to O=September and A=August. This is provenance and
cutoff evidence, not a numerical feature replay. Terminal-success CP5 readbacks
remain released, including this check; no additional user approval is required.

## CP5 final acceptance

Accepted: current publication and DA1; DA2 partial under D2. The 54 CP5 final
hashes, supplement and runtime-final manifests verify. Generic 27/27, lineage
11/11, exact 13-base roster append, all eleven keeps, ACLED cutoff and literal
FEWS inheritance are supported by inspected artifacts. Final execution/logs
confirm success/exit(0), current 1793503777656101 and no observed live lock/hold
or active work. Two targeted read-only scouts compressed evidence checks; the
Supervisor spotchecked their specific findings. No Audit workflow was used.

Two DA2 overstatements were corrected without changing frozen evidence: 21 of 32
PATCH32 targets have finite saved SPEI (11 NaN), and finite-primary preservation
has zero natural samples. PERSIANN missing means follow incomplete calendar
metadata (September/August 0 days; July 2021 30/31), not failed exports. See
cp5/cp5-result-corrections.md and supervisor-acceptance.md. The source-level and
sample-only numerical limitations remain explicit. Original reports are retained.

Scope: evidence/docs/spec updates only. Deployed product 115798f/image acc3e467
and operator config unchanged. Native archive/journal follows the scoped commit;
the re-fetchable 77.8 MB cache and pre-existing AGENTS.md change are excluded.

Precommit: GitNexus staged LOW, no affected processes (index symbols are stale;
direct staged path inspection confirms no product/config changes). The full diff
whitespace check flags only a trailing tab in raw cp4/run/handles-read.log; original
log bytes are preserved. An empty index.lock dated 03:04:50Z blocked staging;
fuser and process inspection found no holder/Git writer. It was moved to the
Supervisor temporary evidence directory, then staging succeeded. User AGENTS.md
still hashes to b449b255709fec553214c7bac77e8d1a3cd1e96b0d6f2d7a38215b8cf3100389.
