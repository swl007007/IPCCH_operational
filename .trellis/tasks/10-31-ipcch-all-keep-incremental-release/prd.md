# IPCCH incremental release with ACLED refresh and DA1/DA2 acceptance

Status: **D1-D4 and final planning summary approved for execution under the user's
Supervisor-Executor goal protocol. All acceptance criteria remain unverified.**

## Goal

Attempt one real, natural-month IPCCH incremental publication to the existing
online current with ACLED refresh and the other ten manual choices kept. Establish
the han-sandbox input connection through automatic production, feature generation, full-roster
inference and bucket publication. Complete the agreed DA1/DA2 acceptance scope.

The initial request called for all keep and used G1/G2. The subsequent accepted
decisions below correct the names to DA1/DA2 and select one-week ACLED refresh.

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
| R1 | One real CLI/event submission with generation, inference and current publication; explicitly select ACLED refresh and keep for the other ten manual inputs. Pin the supplied export and the agreed complete-week interval/regions; no other refresh or hidden input change. | AC1, AC6 |
| R2 | Freeze actual submission-time UTC M, O=M-2 and M/M+6/M+12 targets. Preserve the accepted ipcch-validity-h2h8h14-final-20261030 envelope/package, 527-feature order and 6,226-area roster. | AC1, AC5 |
| R3 | Read han static/history inputs under the runtime SA. Automatically export demanded VI/PRCP/ET0/PATCH32 tables under projects/feisty-flames-511718-d4/assets/ with new run-specific IDs mapped to consumers. Preserve automatic climate/GPP/nightlight contracts. | AC2, AC3 |
| R4 | Require genuinely unsaved, nonempty demand and actual consumption for incremental acceptance. No retained deletion, bundle edits or fabricated month to force work. Compute actual demand; do not assume exactly seven jobs. | AC2, AC3 |
| R5 | Preserve existing availability behavior: no published source for a climate base at O blocks generation; processing/export/schema errors block dependent publication; optional missing sources and legitimate spatial NaN are disclosed. Keep does not promise every source is current. | AC4, AC7 |
| R6 | Record task/destination identity, source-calendar completeness, actual PATCH32 IDs/sparse alignment, VI units/scaling and observed omitted/all-null fields against existing contracts. Distinguish incomplete sources from complete sources with masked areas; unobserved cases are not passed observations. | AC4 |
| R7 | Publish all three horizons to the existing production current and verify referenced objects. Inherit the predecessor FEWS member literally. Bucket visibility and content verification are the endpoint. | AC5 |
| R8 | One new monthly attempt; no automatic new-ID rerun, resource expansion, deployment repair or scientific change after failure. Reconcile uncertain responses with frozen identity/status; preserve saved retained progress and all failure evidence. | AC7 |
| R9 | No product edits or cloud mutations in planning; read-only evidence checks are allowed. Complete grilling and obtain subsequent approval of the latest plan before execution; record concrete operations, live limits and fresh predecessor state before launch. | AC1, AC7 |

The ten keep keys are wfp, history_snapshot, nino34_anom, bbg_staple_food,
bbg_oilgas, bbg_soybean_oil, bbg_global_food, food_price_index_WB, idp_national and
idp_local; each carries only action=keep. ACLED carries action=refresh, its pinned
file, Saturday start/Friday end and declared regions. D4 fixes the approved interval.

## Acceptance criteria

- [ ] **AC1 — Bound submission:** frozen request/reservation declares ACLED refresh
  plus ten keep choices, exact file/interval/regions, real mode, runtime/model
  references and M/O/targets; one new run admitted.
- [ ] **AC2 — Real production:** nonempty pre-run demand, completed actual exports
  and readable validated run-specific destinations; no manual Tasks-panel action.
- [ ] **AC3 — Consumption:** produced IDs link to consuming saved climate versions,
  this run's batch inputs, inference and current member. Generic readback success
  or retained-only replay does not satisfy this criterion.
- [ ] **AC4 — Live data contract:** PATCH32 row/ID evidence, VI units, completeness
  and actual null/omitted shapes have explicit results; unexercised cases remain
  incomplete. Apply D2 to naturally unobserved cases without declaring full DA2
  passed. Availability and processing failures are classified correctly.
- [ ] **AC5 — Publication:** current/release/delivery/member refs identify this run;
  527-feature order, 6,226 rows per horizon and targets validate; FEWS equals the
  predecessor member in full.
- [ ] **AC6 — Source actions:** the ten kept histories retain content/version;
  ACLED appends a version matching the validated refresh and preserves saved rows
  outside the agreed interval/regions. Report accepted/dropped export rows and
  coverage; October-only additions must not enter the August feature cutoff.
  Measure automatic updates/reuse separately, with actual coverage and warnings.
- [ ] **AC7 — Honest bounded outcome:** resource/status/operation records and all
  intermediate failures are preserved. A failed or blocked attempt is not passed
  acceptance. Reconcile partial progress or uncertain publication before more work.

## Out of scope

Retraining; model/feature/availability-policy changes; manual refresh other than ACLED;
forced history deletion/backfill or store reinitialization; full-catalogue copies;
public sharing or personal credentials; new images/builds/deployments; broad IAM;
FEWS rescoring; schedulers/dashboard work; unrelated fixes; automatic fresh retries.

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

## Prepared input and validation

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

No unresolved product-choice question remains. The final summary and D1-D4 are
approved by the subsequent user goal instruction. One monthly attempt is authorized under the existing runtime
limits; failure preserves partial progress and stops without fresh-ID retries or
deployment repairs. D2 defines the allowed partial DA2 outcome.

The user's new execution protocol explicitly prohibits Trellis Audit and automatic
audit workflows (execution-protocol.md:11,44-50), superseding the enrolled-repository
wrapper rule for this task. Use native Trellis start/archive and Supervisor checks;
do not register/start/close an audit run or manipulate existing controller state.
Verify the actual live Opus 5.5 1M executor through Herdr before delegating work.

The user additionally confirmed: "spec范围内的云端操作预授权". Necessary cloud
preflight reads, the one approved submission, its automatic source/retained writes,
inference/current publication and evidence readback are preauthorized. Do not ask
again per operation. Record concrete scope, resource limits and effects; expanded
deployment/IAM/model work or a fresh-ID second attempt remains outside this spec.
Ordinary preparation/check errors may be repaired and retried; an uncertain live
submission is reconciled before any resend. Do not invent a successful outcome.
