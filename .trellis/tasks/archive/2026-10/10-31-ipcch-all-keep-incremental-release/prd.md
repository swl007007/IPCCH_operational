# IPCCH incremental release with ACLED refresh and DA1/DA2 acceptance

Status: **Accepted under D2/D5 on 2026-11-01 UTC. Root recovery and the single
additional all-keep attempt succeeded; current publication and DA1 are verified.
DA2 has observed results plus explicit unobserved cases, not a full pass.
First-attempt failure and every superseding evidence correction are retained.**

## Goal

Achieve the approved real, natural-month IPCCH incremental publication to existing
online current. The first attempt refreshed ACLED and kept ten inputs; D5 permits
root recovery followed by exactly one additional attempt with all eleven kept. Establish
the han-sandbox input connection through automatic production, feature generation, full-roster
inference and bucket publication. Complete the agreed DA1/DA2 acceptance scope.

The initial request called for all keep and used G1/G2. D1-D4 correct the names
and select one-week ACLED refresh. D5 preserves that successful retained refresh
and restores all-keep choices for the explicitly approved second attempt.

## Confirmed background

- The user completed spec/grilling and subsequently supplied execution-protocol.md
  as the active goal. This authorizes execution of the final planning summary.
- The preceding publication was M=2026-10 / O=2026-08, with 527 features and 6,226
  areas per H2/H8/H14. Climate demand was empty; DA1/DA2 remained deferred.
- On 2026-11-01 UTC the actual monthly-runtime service account read 151/151
  enumerated han assets; G00 returned 250 rows and CHIRPS M01 returned 33 bands.
  This supersedes the historical denial for that scope. The probe used the older
  preflight image, not the v2 production pipeline, and did not export any asset.
  Evidence: research/access-preflight/ and research/facts.md.
- UTC is now November. A November freeze selects M=2026-11, O=2026-09, and
  targets 2026-11 / 2027-05 / 2027-11. The task's local October creation date does
  not select M; an actual later freeze still follows the UTC-month contract.
- Keep applies to manual inputs. Automatic climate/GPP/nightlight work still runs.
  The 114 ACLED features use A=O-1, which is August for this run. The live retained
  ACLED HEAD and its hash-matched source export cover 2016-12-31..2026-10-16;
  the last observed Saturday week label is 2026-10-10. The earlier August coverage
  report was capped by the previous run's O, not the raw data's actual tail.
  See research/acled-date-check/result.json and cloud/ipcch/acled.py:231-238.

## Requirements

| ID | Required behavior | Acceptance |
|---|---|---|
| R1 | Real CLI/event submission with generation, inference and current publication. First attempt: pinned ACLED refresh and ten keep. D5 second attempt: all eleven keep, including retained ACLED v2; no other refresh or hidden input change. | AC1, AC6 |
| R2 | Freeze actual submission-time UTC M, O=M-2 and M/M+6/M+12 targets. Preserve the accepted ipcch-validity-h2h8h14-final-20261030 envelope/package, 527-feature order and 6,226-area roster. | AC1, AC5 |
| R3 | Read han static/history inputs under the runtime SA. Automatically export demanded VI/PRCP/ET0/PATCH32 tables under projects/feisty-flames-511718-d4/assets/ with new run-specific IDs mapped to consumers. Preserve automatic climate/GPP/nightlight contracts. | AC2, AC3 |
| R4 | Require genuinely unsaved, nonempty demand and actual consumption for incremental acceptance. No retained deletion, bundle edits or fabricated month to force work. Compute actual demand; do not assume exactly seven jobs. | AC2, AC3 |
| R5 | Preserve existing availability behavior: no published source for a climate base at O blocks generation; processing/export/schema errors block dependent publication; optional missing sources and legitimate spatial NaN are disclosed. Keep does not promise every source is current. | AC4, AC7 |
| R6 | Record task/destination identity, source-calendar completeness, actual PATCH32 IDs/sparse alignment, VI units/scaling and observed omitted/all-null fields against existing contracts. Distinguish incomplete sources from complete sources with masked areas; unobserved cases are not passed observations. | AC4 |
| R7 | Publish all three horizons to the existing production current and verify referenced objects. Inherit the predecessor FEWS member literally. Bucket visibility and content verification are the endpoint. | AC5 |
| R8 | First attempt is terminal failed. D5 authorizes one bounded root initialization/check job and exactly one further new-ID monthly attempt after it passes. No automatic third attempt, monthly resource expansion, other deployment repair or scientific change. Reconcile uncertain responses with frozen identity/status; preserve saved retained progress and all failure evidence. | AC7 |
| R9 | No product edits or cloud mutations in planning; read-only evidence checks are allowed. Complete grilling and obtain subsequent approval of the latest plan before execution; record concrete operations, live limits and fresh predecessor state before launch. | AC1, AC7 |

The ten keep keys are wfp, history_snapshot, nino34_anom, bbg_staple_food,
bbg_oilgas, bbg_soybean_oil, bbg_global_food, food_price_index_WB, idp_national and
idp_local; each carries only action=keep. ACLED carries action=refresh, its pinned
file, Saturday start/Friday end and declared regions for the first attempt. D4 fixes
that interval. Under D5 the second attempt's ACLED choice is only action=keep.

## Acceptance criteria

- [x] **AC1 — Bound submission:** preserve the first request/reservation's verified
  ACLED refresh plus ten keeps. The D5 second request/reservation must declare all
  eleven keep, real mode, pinned runtime/models and actual M/O/targets; only one
  additional run admitted after the root check succeeds.
- [x] **AC2 — Real production:** nonempty pre-run demand, completed actual exports
  and readable validated run-specific destinations; no manual Tasks-panel action.
- [x] **AC3 — Consumption:** produced IDs link to consuming saved climate versions,
  this run's batch inputs, inference and current member. Generic readback success
  or retained-only replay does not satisfy this criterion.
- [x] **AC4 — Live data contract (D2 partial-observation disposition):** PATCH32 row/ID evidence, VI units, completeness
  and actual null/omitted shapes have explicit results; unexercised cases remain
  incomplete. Apply D2 to naturally unobserved cases without declaring full DA2
  passed. Availability and processing failures are classified correctly.
- [x] **AC5 — Publication:** current/release/delivery/member refs identify this run;
  527-feature order, 6,226 rows per horizon and targets validate; FEWS equals the
  predecessor member in full.
- [x] **AC6 — Source actions:** the ten kept histories retain content/version;
  ACLED appends a version matching the validated refresh and preserves saved rows
  outside the agreed interval/regions. Report accepted/dropped export rows and
  coverage; October-only additions must not enter the August feature cutoff.
  For D5, verify ACLED v2 and all ten other kept histories remain unchanged from
  the fresh recovery pre-snapshot; preserve the first attempt's refresh evidence.
  Measure automatic updates/reuse separately, with actual coverage and warnings.
- [x] **AC7 — Honest bounded outcome:** resource/status/operation records and all
  intermediate failures are preserved. A failed or blocked attempt is not passed
  acceptance. Reconcile partial progress or uncertain publication before more work.

Acceptance evidence: `research/cp5/`, with Supervisor disposition in
`research/supervisor-acceptance.md`. Current generation is 1793503777656101 for
`ipcch-real-fe7282ef75e747fd-ipcch`; M=2026-11/O=2026-09, 527 features and 6,226
areas per horizon. DA2 pending: per-row omitted keys in otherwise-present fields,
finite-primary preservation (zero natural samples), and unseen field shapes.
PATCH32 candidates do not establish a numerical SPEI replay; saved O values among
32 targets are 21 finite/11 NaN. The original CP5 report's contrary wording is
superseded by the recorded correction, while its frozen bytes remain preserved.

## Out of scope

Retraining; model/feature/availability-policy changes; manual refresh other than ACLED;
forced history deletion/backfill or store reinitialization; full-catalogue copies;
public sharing or personal credentials; new images/builds or deployments except
the D5 diagnostic job; broad IAM; FEWS rescoring; schedulers/dashboard work;
unrelated fixes; automatic fresh retries beyond the one D5 additional attempt.

## Accepted decisions

**D1 — Keep the existing DA1/DA2 names.** The user corrected the original wording:
"对，就是DA1，DA2，不用改名，沿用这个名称，是我记错了。" No G1/G2 aliases are introduced.

- **DA1:** real producer exports -> climate reads -> retained append -> feature
  consumption -> full-roster inference -> current. AC2, AC3 and AC5 establish
  this chain, with AC1/AC6/AC7 supplying identity and operational evidence.
- **DA2:** the same live run's destination IDs/task completion, runtime access,
  actual PATCH32 rows, VI units and omitted/all-null export/download behavior.
  AC2 and AC4 cover this evidence; offline tests do not replace live observations.

Definitions retain the archived 10-30 PRD:182-190.

**D2 — Naturally unobserved DA2 cases may remain pending.** The user accepted the
recommendation with "采用". If DA1 and all observed data checks pass, this bounded
attempt may conclude with successful current publication and DA1, while individual
DA2 field-shape cases not naturally encountered remain explicitly pending. Never
label the entire DA2 passed in that case, fabricate source missingness, or force a
second monthly run to obtain a witness. Observed data-contract failures and runtime
publication checks are not waived.

**D3 — ACLED refresh, other ten inputs keep.** In response to the scope question,
the user said "可以。最近两周的ACLED我放在downloads里面了，你复制一份就可以。"
The supplied CSV was copied byte-for-byte to the operator input directory with
SHA256 b480d2654f69a5aa27ff50207e3fdcfdaec3b5a5de0ebcf6767ca0020f17ea90.
The full paths and inventory are in research/acled-input/copy-receipt.json.
The original all-keep request is superseded only for ACLED; the task ID/path remain
stable. This manual-input test is additional to DA1/DA2, not a substitute for EE
production evidence. New October weeks remain outside this run's August cutoff.

**D4 — Refresh the available new week only.** The user accepted the recommendation
with "采用": refresh 2026-10-17..2026-10-23, excluding all 209 overlapping
2026-10-10 rows. Preserve the original download and raw copy. The input contains no
2026-10-24 week, so neither declare coverage through 2026-10-30 nor infer an
event-free missing week. This supersedes the provisional Q4 interval choice.

**D5 — Root recovery and one additional all-keep attempt approved.** The user said
"批准上述恢复与一次重跑" and resumed the goal. The approved recovery plan is
research/supervisor-recovery-proposal.md. Use the existing acc3e467 image and
monthly-runtime identity for one short diagnostic job (1 CPU, 512 MiB, 300 s,
one task, zero task retries). Read the exact feisty project root; if HTTP 404,
perform at most one supported create-folder operation, never overwrite, then
verify listing and the pinned transport's absent-child behavior. Other errors
stop before monthly submission; no IAM/registration/billing change is authorized.
After successful verification, submit exactly one new monthly run with all eleven
keep and existing 8 CPU/32 GiB/14400 s/zero-retry limits. Preserve failed run
ipcch-real-9eee4305db494a35 and retained ACLED v2 (+470 verified rows). No third
attempt is authorized. D2 and every scientific/publication acceptance rule remain.

## Prepared input and validation (first attempt)

- Submission CSV contains the 617 source rows for week 2026-10-17 with every field
  value unchanged. SHA256: e660c7e8eb126c102145069441805bf55314914cb6297601bd5a150a87e47e8a.
- Existing parse_export validation passes: 470 modeled rows retained, 147 rows from
  countries outside the accepted mapping dropped under the unchanged contract.
- The selection declares the 17 regions represented in the supplied export, which
  include the 12 required mapped regions. Ten other choices are keep. Selection
  SHA256: 7ab733d8c0e22bc866ae0ddb8cdfce63b3c5621e749b6ec2316f8fdaf58af4a7.
- Full paths and hashes: research/acled-input/prepared-input.json; exact selection:
  research/acled-input/selections.json. Guarded validation and local submit preview
  passed with CHILD-EXIT 0; no cloud calls, upload, request freeze or run occurred.
- Structural validation and the user-selected source interval do not independently
  prove every upstream event has been published. Live evidence remains required
  for DA1/DA2; the preview's M and reference values remain provisional until freeze.

## Final review gate

No unresolved product-choice question remains. D1-D4 governed the first attempt;
D5 explicitly extends the scope to root recovery and one additional all-keep
attempt. Failure preserves partial progress and stops without a third attempt or
further deployment repairs. D2 defines the allowed partial DA2 outcome.

The user's new execution protocol explicitly prohibits Trellis Audit and automatic
audit workflows (execution-protocol.md:11,44-50), superseding the enrolled-repository
wrapper rule for this task. Use native Trellis start/archive and Supervisor checks;
do not register/start/close an audit run or manipulate existing controller state.
Verify the actual live Opus 5.5 1M executor through Herdr before delegating work.

The user additionally confirmed: "spec范围内的云端操作预授权". Necessary cloud
preflight reads, the approved submissions, their automatic source/retained writes,
inference/current publication and evidence readback are preauthorized. Do not ask
again per operation. Record concrete scope, resource limits and effects. D5's
diagnostic job/root initialization and second attempt are now included; other
deployment/IAM/model work and a fresh-ID third attempt remain outside this spec.
Ordinary preparation/check errors may be repaired and retried; an uncertain live
submission is reconciled before any resend. Do not invent a successful outcome.
