# CP4 Supervisor technical gates

User preauthorization covers cloud operations within the goal; these are technical
scope/evidence checkpoints, not repeated user permission requests.

## Build accepted, 2026-10-31

- Source `115798f`. Independently rehashed all 326 context files; no extras or
  mismatches. Inventory `788a0030ce8f028be573e93a0881a1dd5587c1665c0392bd687666522e335c02`;
  cloudbuild.yaml `f6a40db524fd7a1a673f7775f30d089accb3040e86695a222040c6718107d310`.
- One Cloud Build `ea1cbe1c-d3fd-4e32-8a27-5e90c61e852e`, 13:55:35–14:03:06 UTC,
  SUCCESS; all six steps SUCCESS; 3600-second limit, no retries.
- Runtime:
  `us-central1-docker.pkg.dev/feisty-flames-511718-d4/monthly-delivery/runtime@sha256:acc3e4673fa7c133eade6e5c74b998706788e0d1af0f92b217ae74ce7e14ccf6`.
- Raw log's single SIX_SLOT_EVIDENCE equals the structured evidence. Every in-image
  verify/import/replay step's buildStepImages equals that resulting digest. All
  FEWS package/prediction, legacy IPCCH load and dependency-version checks match.
  FEWS covers 5,718 areas per horizon with full prediction hashes equal to reference.
- Evidence hashes checked: six-slot-runtime-evidence.json `0cba2744…`, build.log
  `972b92b6…`, build-record.json `0b7687b2…`. See `build/` for full values.

This accepts actual image installation/compatibility evidence. It does not accept
the shared-service cutover, compatibility delivery or full IPCCH E2E yet.

## Released operations

- Step 4: smoke bucket only, us-central1, UBLA/PAP; add monthly-runtime objectAdmin
  matching the observed data-bucket role. Executor reports created/read back.
- Step 5: new runtime baseline (only baseline.json changes), new operator config/
  work_dir, supported init with create-only uploads. Old operator state remains.
  Exact accepted digest above. Report baseline/environment/model pins before step 6.
- Step 6 candidate deadline is 4 hours, matching existing limits. No new pre-chosen
  v2 run-ID behavior; normal legacy behavior may remain until CP5 activation.
  Do not submit a legacy IPCCH request during that window.

## Step 5 accepted / step 6a–e released

Supported init completed with actual cloudop exit 0 at 14:14:24 UTC. New baseline
`f0481ca13610f9903760b0173b77d9e1628e78e4b2adc91e2ee351cf16862856`; new
initialized.json `e0bb3e7faa0973796359c466d8e415241cc020a78251faab3023090fb0e8bd13`.
Destination/runtime bind acc3e467. Environment generation `1793456025486882`,
SHA256 `35a4890a3ee40fee8bc6cf121ee332fce6a26c8ec7255b446cddf0db2de92b3b`.
Normal config still `a078f0e5…`, unchanged. Baseline diff inspected: only runtime
and each model's acceptance/environment changed; other sections are identical.

Released `step6-packet.md` 6a–e: hold/gate/functional probe/apply/one FEWS-only
candidate/download/compatibility/verify. Refresh current and active work before
mutation. Preserve 8 CPU/32 GiB and 2 CPU/8 GiB, 14400 seconds, zero retries.
Candidate uses no EE, Batch or preparation. Wrap pipeline verify and its replay
children in the existing 4 GiB/3 GiB-AS/600-second guard. Promotion still awaits
actual candidate/compatibility/receipt review.

Configuration finish: promote only copies top-level image/work_dir. CP5 uses the
reviewed new config; after final publication, back up and finalize normal v2.image_uri
and verify the routine normal-config entry. Do not alter promotion's config snapshot
between promote and maintenance release.

## Known prerequisite boundary

Runtime probe confirms han read denial; user metadata read succeeds but ACL read
fails. No user token deployment or upstream ACL mutation. Exact October/August
retained-only CP5 can continue because empty demand returns before han access;
actual run must confirm skips. Public GPP HTTPS is not yet verified from runtime.
Future incremental runs require upstream sharing. Freeze must precede November UTC
for this round; never falsify the month or delete retained history.

## Step 6 progress and CP5 evidence requirements, 14:30 UTC

- Functional hold probe execution 337d8631-1110-4c8c-ae3d-380707007669 failed
  with the intended maintenance admission error; no dispatch claim exists.
- Reviewed apply preview and result: both jobs and Workflow use acc3e467; the
  commands preserve 8 CPU/32 GiB and 2 CPU/8 GiB, four hours, zero task retries.
- Independent live job readback confirms those exact images/resources, timeout
  14400 seconds and maxRetries 0 (`step6/supervisor-jobs-readback.json`). Candidate
  execution `oct-delivery-pwlgj` is running, created 14:27:34 UTC. Both pre-init
  retained-root inventories are empty with no orphan-version tables (14:29 UTC).
- Candidate fews-compat-v2rt-20261031a submitted once at 14:27 UTC, binding
  predecessor pointer generation 1792657760445077. Actual result, compatibility
  comparison and guarded verification remain pending; 6f is not released.
- Initializer source verification confirms selected retained-root writes only,
  no current publication and no EE calls. Smoke requires an explicit acceptor.
  Acceptance and partial tables can survive interruption before final binding;
  verify successful process exit plus the final pairing and initialized HEADs.
  Proposed cloud capacity is not evidence of adequate capacity until executed.
- Successful generation status does not persist every source action list. Capture
  retained HEADs after initialization and before/after the real run, then use
  version records, GPP ledger and producer demand/skip receipts. Do not infer zero
  network calls solely from unchanged coverage. No product change is requested.
- Reuse batch and delivery validators; additionally check raw feature headers and
  full FEWS member equality against the predecessor's normalized member. All local
  verification remains guarded.

## CP5 5a-5c released, 2026-10-31

Read `cp5-packet.md` in full. Independently rehashed the four local upload sources:
envelope 03b93842, raw environment lock 2f0a7251, real country reference 0823e418,
smoke fixture country reference acbd3eac. The real reference equals the pinned
predecessor IPCCH delivery. NEW_CFG remains 3be606ea with exact acc3e467 v2 digest.

Released create-only uploads/readback, dedicated `ipcch-v2-init-20261031` creation
and one execution per mode (real then smoke), and post-init inventories/binding
checks. Exact installed entrypoint, monthly-runtime identity, 4 CPU/16 GiB,
3600 seconds, one task and zero task retries; smoke acceptor weilun.shi. Maximum
compute allocation across two full-hour executions: 8 vCPU-hours and 32 GiB-hours,
plus storage/logging. No monetary billing claim. Local guards remain unchanged.

This preparation may overlap the independent FEWS candidate: it writes only new
retained roots/shared inputs and never current or request trigger objects. Preserve
partial writes on failure and report; no unreviewed rerun/resource increase. CP5
5d-5f submissions still await C promotion/release and their technical evidence gate.

## Real initialization accepted, 14:45 UTC

Execution `ipcch-v2-init-20261031-7t4lg` completed successfully at 14:41:50 UTC,
succeededCount 1; runtime log ends `Container called exit(0)`. Actual job definition
matches 4 CPU/16 GiB/3600 seconds/zero retries and the accepted digest/identity.

Supervisor's guarded cross-check validates all 52 runtime CSV table source hashes
and row counts against the bound handoff manifest, exact 54 HEAD inventory (including
acceptance/binding), version 1, one version object each, own-root content paths,
and full package/feature/bundle/6,226-roster pairing. No orphan version tables.
`cp5/init/supervisor-real-init-check-run2.log`: CHILD-EXIT 0, peak RSS 15,888 KiB.
The first check log remains a failed local relative-path invocation under the guard's
working directory; it never reached the inventory and is not a cloud failure or
accepted validation. The second check uses absolute input paths.

Smoke initialization is running; neither this initializer success nor the local
readback-helper self-checks establish smoke dispatch or real E2E publication.

## CP5 initialization complete and accepted, 14:47 UTC

Smoke execution `ipcch-v2-init-20261031-hxz9k` completed successfully at 14:45:05 UTC,
succeededCount 1. Supervisor cross-check confirms exact 51 fixture CSV tables plus
acceptance/binding (53 HEADs), each at version 1, source SHA/actual CSV row count,
own-root content paths, no orphan tables, and the fixture's 3-area pairing. Final
`supervisor-smoke-init-check-run3.log` has CHILD-EXIT 0, RSS 15,680 KiB.

Smoke checks run1/run2 remain failed checks due to real-manifest field assumptions:
fixture entries lack `rows`, and roster hash is the fixed/roster.csv file hash rather
than a top-level manifest field. Run3 reads/hashes the actual fixture CSVs and uses
the correct roster entry. No cloud initialization was repeated for these checks.

5a-5c is accepted. Both mode stores are initialized and distinct; smoke route and
real E2E submissions still await C's verified promotion and maintenance release.

## C verification accepted; 6f/6g and subsequent smoke released, 15:00 UTC

Candidate fews-compat-v2rt-20261031a succeeded with validation passed, scored FEWS
only and inherited IPCCH. Candidate generation 1793458366099072, manifest generation
1793458301810702, archive generation 1793458365634163. Guarded compatibility check
passes all 121 required files against the pinned predecessor. Additional runtime
source and report identity differences are classified, with unchanged prediction/
model/input hashes; see step6/report-diff-classification.txt.

Guarded pipeline verify (including relocated replay) CHILD-EXIT 0, RSS 1,758,648 KiB,
all checks true; FEWS predictions equal at 5,718 rows per horizon, IPCCH inherited.
Supervisor independently rehashed local receipt
8026d65db4e4a2869c6a9988266df32b2bd8010060aa4b5ba63ed9341aac2932 and extra check
126720557ab6d3463a211f16bebbf48093a346e560b9edcd3d0ce01e09db8880. Receipt object
generation 1793458733116472. Candidate and request pins match the final status.

Released 6f guarded fallback staging/promotion and 6g maintenance release, with
fresh pointer/active-work checks, intended-state readback, and old-state preservation.
After successful release/readback, also released CP5 5d one smoke submit via NEW_CFG
and guarded readback (M 2026-10/O 2026-08, 527 features, fixture roster 3). Real 5e
submission awaits actual smoke evidence review. No additional resource/retry scope.

## C promotion/release accepted, 15:06 UTC

Promotion returned activated with pointer/config/fallback/shared-runtime reconciled.
Current generation 1793458988623055 names
releases/fews-compat-v2rt-20261031a/release.json, release generation
1793458988510572. Normal config sha 13b9deb3 changed only top-level image_uri/work_dir;
old bytes a078f0e5 are backed up, v2 section remains unchanged. Fallback manifest
a7a631f5 matches the receipt; predecessor 54dd0f14 retained.

Executor identified before execution that the packet's /home staging and /mnt/c
fallback were on different filesystems. Path.rename would fail after the pointer
CAS; the preview does not itself reject this. Executor restaged the same bytes
beside the active fallback, then verified byte equality and repeated the preview
before executing. No EXDEV/cloud mutation failure occurred. This corrects the
earlier Supervisor description of a preview refusal. No product code change.

Maintenance operation released_activated at 15:05:26 UTC, every release check true.
The live hold describe returns 404. Versioned historical holds remain; `ls -a`
is not a test of whether a live hold exists. CP5 smoke may proceed as released above.

Post-v2 recovery boundary: the old C operation cannot restore a later v2 current or
edited normal v2 config; those states are foreign. Its predecessor runtime is 487a.
No dedicated v2 pointer rollback helper exists, and reverting to the old legacy
pointer would hide activation from the guards. Final handoff must document a fresh
maintenance containment operation and forward recovery, preserving retained writes,
instead of advertising the C restore as a universal v2 rollback. Normal-config
completion must verify load_initialized directly or via models select, not maintenance
status (which does not call that validator).

Old config/initialized state/operator tree/baseline hashes after release match the
pre-step5 snapshot (step6/old-state-after-release.txt). Smoke submitted once as
ipcch-smoke-2dd1148b8c274496 at 15:07:16 UTC, M 2026-10, request generation
1793459237316215. Its pre-current snapshot is generation 0. Awaiting live results.

## Smoke accepted; real 5e-5f released, 15:19 UTC

Supervisor resumed after deliberate interruption and verified the same Executor
6a490ae1 idle, with no real submission yet. Inspected post-smoke SHA
0f5b3e2d6676fe274605018c576bdcf481f682ae0b5d6b6a29e9d5076c42457d and durable
status 19e7e8e7: succeeded, no lock-release problems, all 24 readback checks true.
M/O 2026-10/2026-08, 527 ordered features, fixture roster 3, target months
2026-10/2027-04/2027-10. Smoke current generation 1793459378587275 points to
release generation 1793459378523010; activation is null. Guarded readback CHILD-EXIT
0, peak RSS 199,868 KiB. Two earlier local invocation errors remain marked
INTERMEDIATE; final command explicitly supplies PYTHONPATH and GOOGLE_CLOUD_PROJECT.

Released one real routine submission and guarded readback (5e-5f), after fresh
inventory/current/hold/active-work checks. Expected C current generation remains
1793458988623055. Existing real selections: ACLED refresh, ten other channels keep.
Freeze actual UTC submission month; require October/August for this retained-only
acceptance. Resource bounds unchanged: 8 CPU/32 GiB/14400 seconds/zero task retries.
Require 6,226 areas per H2/H8/H14, 527 features, actual source evidence and production
current readback with literal FEWS inheritance. No resubmission/resource escalation
on failure. Normal v2 config completion 5g still awaits accepted real output.

Real request submitted once: ipcch-real-522b30030f944868, freeze 15:21:13 UTC,
M 2026-10, request generation 1793460075820847 (SHA 63057e5f). Pre-submit current
is C generation 1793458988623055; no live hold/active shared job or Workflow.
Pre-real inventory equals post-init table HEADs, 54 tables/54 versions.

## Continuity and real progress, 15:36 UTC

Current HEAD remains 115798f0572f8f99c60b033c32064e92f3578597 with no tracked
product/test/runtime/deployment differences. CP2's 20 and CP3's 19 frozen hashes
all match; their file sets are disjoint. CP3 final evidence reconciles 18 files,
285 passed, no failed/skipped, every paired exit/CHILD-EXIT 0, RSS <=489,972 KiB.
This evidence extraction did not run another test suite or an independent audit.
Offline tests substitute FakeCloud for operator adapter methods; live submit/pin
evidence is recorded separately rather than asserting per-symbol unit coverage.

Independent Cloud Run readback identifies real execution oct-delivery-t6vlm with
the exact request generation, digest, service account, v2 argv and unchanged
8 CPU/32 GiB/14400-second/zero-retry limits. Runtime remains in progress. Durable
source records show first ACLED refresh and GPP checks for 2026-01..08, each with
actual HTTPS 404 evidence; no GPP raster download. Final batch/production demand,
predictions and current publication still require the actual completion/readback.

## Real publication/readback accepted; 5g released, 15:47 UTC

One real submission ipcch-real-522b30030f944868 completed in execution
oct-delivery-t6vlm at 15:38:53 UTC, succeededCount 1 and container exit 0.
Frozen request generation 1793460075820847 and SHA 63057e5f match the reservation,
batch and release. Durable status is succeeded with no lock-release problems.

Production current generation 1793461128385732 points to this run's release
generation 1793461128307577; previous generation is the accepted C pointer
1793458988623055. Delivery manifest generation 1793461076195052, SHA
496fa8e561807bedfaa63ed6c580303300c3dd8a24268770140988a7b5c575e1, has 124 files.
Activation is present at 15:37:56 UTC. The complete normalized predecessor FEWS
member is inherited literally, including its manifest/archive references.

Inspected post-real.json, final status, guarded readback log and source receipts.
All 27 readback checks pass, including product delivery/member validation, frozen
request linkage, bound batch/roster and raw feature headers. All three horizons
cover 6,226 areas with 527 ordered features (0ef1ffec), M 2026-10/O 2026-08, and
targets 2026-10/2027-04/2027-10. Guarded readback CHILD-EXIT 0, elapsed 1:42.13,
peak RSS 992,380 KiB; no memory-limit increase. Batch manifest generation
1793460902270100 has SHA 96570af509a19d663312cd42626d8bfe728dc4ec6364de9fe7777cd6e6bf5892.

Actual source evidence: first ACLED retained version has 242,341 rows; GPP ledger
has eight unpublished month records with in-job HTTPS 404 evidence for 2026-01..08.
GPP history is unchanged. All 26 climate tables and nightlight retain their prior
versions. Producer demand is empty for monthly/seasonal EVI/SPI/SPEI, jobs/receipts
are empty, and the batch explicitly records already-retained skip. This is not
measured total EE/RPC call telemetry. WFP/history/eight research inputs are keep.
Acceptance moves from v1/57 rows to v3/66 rows. GPP_mean ending 2025-12 and
bbg_soybean_oil ending 2026-07 produce the two recorded optional-missing warnings;
their origin features remain NaN under R65. No incremental acquisition pass is claimed.

Released 5g only: byte-back up normal config, add the exact accepted v2.image_uri,
then check normal submit preview, actual run status and direct load_initialized.
No additional submission or cloud execution. CP6 final evidence/docs and native
task closure remain pending. DA1/DA2 are deferred; han runtime sharing remains a
future incremental prerequisite, not evidence supplied by this retained-only run.

## 5g and CP6 accepted, 15:51 UTC

Normal config now hashes to 3be606eaaa64cbd819c93d2024662971740316c5b58b7409649ee89f49f26110,
byte-identical to NEW_CFG. Its 13b9deb3 predecessor is backed up at
project.json.bak-5g-20261031T154715Z; the sole semantic change is v2.image_uri.
Guarded normal submit preview, actual real status and direct load_initialized each
have CHILD-EXIT 0. No new request or execution was submitted for these checks.

Supervisor final guarded reconciliation has CHILD-EXIT 0, RSS 16,524 KiB. It checks
the 27 readback assertions, request/reservation linkage, targets, configuration delta,
all 53 unchanged prior non-acceptance tables, new ACLED/GPP ledger identities, and
empty producer demand/jobs/receipts. CP2's 20 frozen files and CP3's 18 unchanged
code/test/config files match; CP3's remaining file is the reviewed OPERATIONS.md
documentation update. See research/cp6/supervisor-final-evidence.log and .exit.

Reviewed CP6 final report, AC1-AC9 matrix, operator handoff and OPERATIONS.md diff.
Corrections distinguish overlapping phases from chronology, aggregate phase-count
agreement from keyed prediction replay, upload time from UTC freeze time, and fresh
maintenance containment/release from unsupported old-pointer rollback. New asset
root/mapping and retained han inputs are explicit. All AC1-AC9 are accepted; DA1/DA2
remain deferred. The known han read prerequisite and optional-missing GPP/soybean
inputs remain disclosed. No independent Audit workflow is run or claimed.

Only scoped evidence/spec documentation commits, native archive and journal remain.
Raw task log evidence will be retained in Git; pycache and local fallback/data remain
ignored. Preserve the unrelated AGENTS.md modification; no push or merge.
