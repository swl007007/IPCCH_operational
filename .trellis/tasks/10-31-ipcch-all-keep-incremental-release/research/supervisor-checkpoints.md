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
