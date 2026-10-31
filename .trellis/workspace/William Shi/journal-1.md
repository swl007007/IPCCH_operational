# Journal - William Shi (Part 1)

> AI development session journal
> Started: 2026-09-23

---



## Session 1: October cloud delivery completed
<!-- trellis-session: v=2 fp=5b4a098464455fc5 -->

**Date**: 2026-10-08
**Task**: October cloud delivery completed
**Branch**: `feat/october-cloud-delivery`

### Summary

Full remote refresh, manifest-triggered FEWSNET and IPCCH 0/6/12 delivery, 30-table offline replay exact; staging published, all jobs terminal. Close and spot audits explicitly skipped.

### Git Commits

| Hash | Message |
|------|---------|
| `b7e83f9` | feat: deliver October FEWSNET and IPCCH forecasts through cloud pipeline |

### Testing

- 644 passed across recorded runs; 9 skips; one known baseline horizon failure (not an all-green suite)
- [OK] Final cloud run and offline bundle replay passed; 33 EE exports completed

### Status

[OK] **Completed**

### Next Steps

- Production consumer cutover and training remain separate; see deploy/october_delivery/QUICKSTART.zh-CN.md


## Session 2: Local migration package and compact manual delivery
<!-- trellis-session: v=2 fp=8cba843915c1d8e9 -->

**Date**: 2026-10-08
**Task**: Local migration package and compact manual delivery
**Branch**: `feat/october-cloud-delivery`

### Summary

Built and relocated-verified 233-file migration payload and 1.10 GiB archive; isolated final September handoff at about 250 MiB; removed authorized redundant backups, reducing manual storage by 15.6 GiB; updated README/Quickstarts. 68 focused tests passed plus lint and credential-free dry-run. No cloud migration, training, repeat model replay, close audit or spot audit.

### Git Commits

| Hash | Message |
|------|---------|
| `551b3d4` | feat: package cloud migration and isolate final manual delivery |

### Status

[OK] **Completed**


## Session 3: Two-entry delivery closure
<!-- trellis-session: v=2 fp=7a6fb0a4535661bb -->

**Date**: 2026-10-08
**Task**: Two-entry delivery closure
**Branch**: `feat/october-cloud-delivery`

### Summary

Closed September manual and cloud operator handovers; added destination CLI and English operations docs; archived 690 legacy files without deletion; verified 209-member archive and relocated baseline; 465 tests passed. No cloud calls, replay, audits or push.

### Git Commits

| Hash | Message |
|------|---------|
| `4c9122d` | feat: close operator handover and archive legacy layout |

### Status

[OK] **Completed**


## Session 4: September 6m/12m with confidence; October cloud rerun with confidence
<!-- trellis-session: v=2 fp=4e15cbe963af0075 -->

**Date**: 2026-10-09
**Task**: September 6m/12m with confidence; October cloud rerun with confidence
**Branch**: `feat/october-cloud-delivery`

### Summary

Grilled 21 decisions. Built confidence evidence (FEWS Stage3 fs1/fs2/fs3 proxies for 0/6/12m; IPCCH training resubstitution 0/6/12m from original training panel), each reproducing h5 exactly. Added APPROVED_PROXY_EVIDENCE allowlist; baseline 15/15 diagnostics available. Published september_manual/scopes/{6m,12m} (origin 2026-09, data to 2026-08; IPCCH scores equal October's because inputs are identical). Real-cloud October rerun oct-confidence-20261009b on image cp5-confidence-1: predictions byte-identical to smoke output, confidence filled; offline replay passes; fallback replaced (smoke copy in legacy archive); handover archive cloud_pipeline-20261009b. Local scratch and superseded archives removed; task-owned cloud objects kept (listed in research/cloud-rerun-20261009.md).

### Git Commits

| Hash | Message |
|------|---------|
| `6da80bc` | feat: September-origin 6m/12m delivery with confidence evidence |
| `6d815bb` | feat: fill FEWS 0m confidence and rerun October delivery with confidence |
| `7ee1e84` | docs: point to final handover archive after local cleanup |

### Status

[OK] **Completed**


## Session 5: GCP research modeling migration close + A01 sqlimport precision repair
<!-- trellis-session: v=2 fp=ba97e2f87b36003b -->

**Date**: 2026-10-16
**Task**: GCP research modeling migration close + A01 sqlimport precision repair
**Branch**: `feat/october-cloud-delivery`

### Summary

Migration to food-crisis-modeling-enso completed and closed: PID-1-safe per-trial cap (timeout wrapper), HPT attempt 3 harvested and parents closed, 223 packages downloaded and replayed (accepted), revised measured quote, tested researcher runbook, SQL 53/53 + geometry + capacity, temporary admin removed (own-role cascade reconstructed to original digests), writer freeze + empty r3 delta, cutover, native merge 12a5dd7. Close audit 4b7c22cf accepted (minor A01) after a disclosed native-archive recovery (deviation 1). Repair task sqlimport-a01-precision: infer_types carries integer precision across chunks (red/green tests, PG round trip), bounded exposure scan of all 53 sources (13.76 GB, 0 candidates, 429 multi-line records tokenized; no cloud repair), merged b93f9c8; close audit 5d2c1e92 accepted, resolving A01; remaining minor audit debt sqlimport-a01-precision-A01 (native start + resume-start, deviation 2) retained.

### Git Commits

| Hash | Message |
|------|---------|
| `d9ede46` | Per-trial cap via coreutils timeout at the command prefix (replaces PID-1-ineffective SIGALRM) |
| `d58fcda` | Revised quote from measured actuals; read-only actuals collector |
| `9427f01` | Runbook: concrete, tested FEWS/IPCCH examples |
| `6ee56f5` | Runbook: smoke output path is trial/<local-job>/trial-0/ (as produced by the verbatim FEWS run) |
| `12a5dd7` | Merge native gcp-research-migration (6ee56f5) into the registered lineage |
| `841d196` | docs(gcp-migration): O-104 correction + O-105..O-114 (PID-1 cap fix d9ede46, 223 reader download, downloaded-copy replay accepted 223, HPT3 harvest + parent closing, actuals + revised quote d58fcda, runbook 9427f01, scen bytes accepted), S89 |
| `57dc770` | docs(gcp-migration): pre-close summaries current (ledger README 170/72, implement checkboxes, PRD status, task notes, executor-state final sequence), acceptance.json DRAFT, runbook command-check receipt |
| `ae64c2b` | docs(gcp-migration): G12 executed - SQL 53/53 + geometry + capacity (O-115/116), temporary admin removed with TTL proof and own-role cascade disposition (O-117), post-removal 17/17 + 31/31 (O-118), writer freeze + r3 empty delta + 3,569 artifacts re-hashed, cut over (O-119/120); acceptance.json FINAL, cutover receipt, supervisor receipts (merge, SQL, auth) |
| `1300b04` | docs(gcp-migration): PROGRESS migration status (additive, LF blob; working-copy CRLF dirt untouched), O-121 snapshot-mode correction, supervisor cutover-final receipt |
| `e0a3b45` | docs(gcp-migration): supervisor S92 final acceptance and cutover-final receipt (pending wording removed) |
| `427e12d` | docs(trellis): A01 repair task spec/plan (sqlimport cross-chunk integer precision; bounded exposure scan) |
| `8c147ea` | docs(trellis): A01 plan correction (CSV integer-field prefilter, three result classes, multi-line records checked per file) and disclosed lifecycle deviation 2 (native start + resume-start) |
| `1d9c21d` | sqlimport: carry integer precision across chunks in infer_types (A01) |
| `b93f9c8` | Merge native sqlimport-a01-precision (1d9c21d): A01 cross-chunk integer precision in infer_types |
| `dbd4e06` | docs(trellis): A01 repair evidence - red/green tests, exposure scan (script, cloud catalog, receipt, run log, decision: trigger absent, no cloud repair), supervisor acceptance, plan checkboxes |

### Status

[OK] **Completed**

### Next Steps

- None for these tasks; audit debt sqlimport-a01-precision-A01 stays recorded. Archived: .trellis/tasks/archive/2026-10/{10-16-gcp-research-modeling-migration,10-16-sqlimport-a01-precision}.


## Session 6: FEWS fixed-map retrain: all-history fit, manifest dispatch, candidate and promotion
<!-- trellis-session: v=2 fp=f586f00538742508 -->

**Date**: 2026-10-22
**Task**: FEWS fixed-map retrain: all-history fit, manifest dispatch, candidate and promotion
**Branch**: `feat/fewsnet-fixed-map-retrain`

### Summary

Refreshed FEWS labels (HDX CS, strict crosswalk), refit 0/6/12m on all eligible history with the fixed map/features/thresholds (no evaluation), built workflow-owned manifest dispatch with maintenance hold, candidate receipt and recoverable promotion, and promoted fews-candidate-20261022a (FEWS scored, IPCCH inherited, frozen October confidence) under supervisor acceptance.

### Main Changes

- Full-data runner/package path; GOSIF v3 boundary and FEWS nightlight sum; frozen_output confidence; execution selection with IPCCH inheritance and candidate publication
- Workflow: hold, run claim, admission, one snapshot gate; operator: intent-only runs, candidate download/verify, maintenance hold/gate/apply/restore/release, receipt-bound promotion
- Production: runtime sha256:487a2315, baseline b77cb29b, current.json -> fews-candidate-20261022a, fallback swapped (predecessor kept)

### Git Commits

| Hash | Message |
|------|---------|
| `ff389b1` | feat(fewsnet): full-history fixed-threshold fit path and versioned input freeze |
| `dbfc196` | fix(fewsnet): keep full-history pool job arguments picklable |
| `38c1ccb` | fix(remote): FEWS nightlight sum mapping, GOSIF mean v3 from 2025, contract v2 |
| `1dd5e70` | feat(delivery): attach frozen FEWS confidence outputs unchanged |
| `82a4a0f` | feat(delivery): retain raw Stage3 evidence and source declarations with frozen outputs |
| `f9506bc` | feat(delivery): manifest step selection, inherited systems and candidate publication |
| `9e5a375` | feat(workflow): dispatch selected steps from the pinned request |
| `0d60a4e` | fix(dispatch): gate cloud steps on claim, admission and one snapshot check |
| `48d3d1e` | feat(operator): workflow-owned runs, candidate receipt and recoverable promotion |
| `7e458e2` | fix(operator): condition restore and activation writes on inspected state |
| `53d5f87` | fix(deploy): pass --condition=None on unconditional bucket grants |
| `49ed4bb` | docs(release): reopen admission, reconcile docs/checklist, pin retained-source fixture |
| `f545eb0` | docs(task): final supervisor acceptance of the FEWS retrain release |

### Testing

- [OK] Full suite 619 passed + 4 fixture-corrected (623); in-image six-slot evidence; candidate release checks 43/43; relocated FEWS-only replay all equal; supervisor final acceptance (AC1-AC9)

### Status

[OK] **Completed**

### Next Steps

- Next monthly run uses the activated normal config; rollback via the recorded operation (OPERATIONS.md)


## Session 7: IPCCH H2/H8/H14 migration: CP4-CP6 completion, final acceptance and archive
<!-- trellis-session: v=2 fp=617e70c05a5e771d -->

**Date**: 2026-10-30
**Task**: IPCCH H2/H8/H14 migration: CP4-CP6 completion, final acceptance and archive
**Branch**: `feat/ipcch-validity-feature-inference`

### Summary

Executable v2 route, legacy v1 cutover/inheritance guards, FEWS NET v2 adapter with real deliver parity, CP5 actual-package smoke, CP6 evidence matrix/operator handoff; Supervisor final acceptance CP0-CP6 (91625df); task archived.

### Main Changes

- v2 route (entrypoint_v2 run/initialise), per-system locks, v2 publication with activation and candidates
- legacy v1 guards: R37 cutover at request/admission/publication, current-bound inheritance, FEWS-scoped remote preparation, promote/verify guards
- FEWS NET v2 adapter (D1-D3) with real deliver(fewsnet) parity incl. split refresh; exact-bytes deliveries; FEWS member validation
- CP5 smoke with the actual accepted package and fixture-only inputs; CP6 evidence matrix, operator runbook, validated examples

### Git Commits

| Hash | Message |
|------|---------|
| `e48ca51` | feat: executable v2 route (entrypoint_v2 run + delivery_job --v2-config dispatch) with installed binding, providers per mode |
| `6d8ea08` | feat: legacy v1 guards after the new IPCCH contract; FEWS member writer; exact-bytes v2 deliveries |
| `78a2aeb` | fix: legacy routes bound to the current release on every path; scoped remote preparation; consistent legacy read |
| `43c6d12` | feat: v2 FEWS NET adapter (R60, Supervisor D1-D3): scoped preparation, generation source binding, shared scorer |
| `32d4eef` | fix: residuals A-D on 78a2aeb and the 43c6d12 keep-projection P1 |
| `77cc319` | fix: residual C/D boundaries on 32d4eef (workflow error scope, CLI resolve read, lock lookup rollback) |
| `0d26d7f` | docs: R60 real deliver(fewsnet) parity on real bootstrap inputs (v2 route == existing deliver) |
| `b3b5dd2` | feat: CP5 local smoke with the actual accepted H2/H8/H14 package and fixture-only inputs; smoke evidence subset fix |
| `da1ebd0` | fix: CP5 repairs - smoke evidence identity before subset, unavailable on empty subset; stronger smoke evidence |
| `d57a3fb` | feat: CP6 evidence matrix, operator runbook/examples, store initialisation route; R53/R62 warnings in prediction metadata |
| `0d484d8` | docs: CP6 final regression receipt (957 passed at bbf21a4) and GitNexus index-count housekeeping |
| `7ed26ab` | docs: CP6 final report, PROGRESS entry and task metadata; exact final-suite warning wording |
| `53352b3` | docs: reconcile prd/implement status and executor handoff to the CP0-CP6 final acceptance |
| `b332141` | chore(task): archive 10-29-ipcch-validity-feature-inference |
| `1d2cc47` | chore(task): record final acceptance and archive location in the archived task notes |

### Testing

- [OK] whole cloud_pipeline/tests: 957 passed at bbf21a4 (research/cp6/final-tests-summary.md)
- [OK] CP5 run6 12/12 checks; FEWS parity keep/refresh/refresh-split 28/31 byte-identical + 3 modulo output root

### Status

[OK] **Completed**

### Next Steps

- Live items deferred (D-live-1..8): live EE/cloud, full-area cloud generation, real GCS init, production publication/cutover, deployed image, production rollback


## Session 8: IPCCH validity origin ablation (H0/H6/H12) — executed and accepted
<!-- trellis-session: v=2 fp=cd6b5f6738144aac -->

**Date**: 2026-10-30
**Task**: IPCCH validity origin ablation (H0/H6/H12) — executed and accepted
**Branch**: `feat/ipcch-validity-feature-inference`

### Summary

Executor (Claude b9db2dbb, w19:pE) under the Supervisor-Executor protocol: original-label fit ablation of the CH-final runs. Research worktree control-plane-origin-ablation commits 99f3ebd (CH-final source pin), 7023d10 (fit-only policy, origin contract/gates, A2 pairing, paired comparison, holdout-only package), 868db9f (smoke test). No-fit gates + independent verifier; full regressions (159 numerical + 72 tooling). Build 22176002 (image b208b132). Vertex jobs 2842603222726606848/2596031143128072192/3377405678476853248 SUCCEEDED once each (44 scalar fits); MLflow runs bd249760/eb33b087/8237e829 in IPCCH dashboard; final read-only packet final_pass (recompute, logs, readback 6/6, Dashboard UI). Annual weights cleanup (32 boosters) after verification. Reserved USD 6.81 of 7.00; compute-only ~USD 0.51. Supervisor final acceptance recorded; task archived (730f751).

### Git Commits

| Hash | Message |
|------|---------|
| `ad34381` | task 10-30: IPCCH validity origin ablation — execution evidence, final report and tool sources |
| `61667a3` | task 10-30: final preservation check receipt |
| `fc64185` | task 10-30: record Supervisor final acceptance; drop acceptance-pending status text |

### Status

[OK] **Completed**


## Session 9: IPCCH automatic E2E published to production current
<!-- trellis-session: v=2 fp=e6d9224830c90b9e -->

**Date**: 2026-10-31
**Task**: IPCCH automatic E2E published to production current
**Branch**: `feat/ipcch-real-e2e-integration`

### Summary

AC1-AC9 accepted: automatic submission through full 6226-area H2/H8/H14 inference and production current, guarded readback 27/27, normal configuration finalized; DA1/DA2 deferred and han runtime sharing still required.

### Main Changes

- Sparse PATCH32, automatic EE producers, UTC-frozen v2 submission, verified image installation and preserved FEWS compatibility.
- Real run ipcch-real-522b30030f944868; current generation 1793461128385732; release generation 1793461128307577; 527 features, targets 2026-10/2027-04/2027-10.

### Git Commits

| Hash | Message |
|------|---------|
| `12b1d68` | fix(ipcch): align sparse PATCH32 and validate produced table completeness |
| `70f9d10` | feat(ipcch): automate EE table production and bound execution lifecycle |
| `115798f` | feat(ipcch): wire v2 submission and verified runtime installation |
| `d0625b3` | docs(ipcch): accept real E2E publication and operator handoff |

### Testing

- [OK] CP1 86 focused; CP2 226 and CP3 285 guarded passes; smoke 24/24 and real 27/27 readback; final source/config/inventory reconciliation child exit 0.
- [OK] Native archive 6a17ff1 preserves 470 tracked members; 468 byte-identical, only implementation completion and task lifecycle changed. GitNexus low risk, no affected processes.

### Status

[OK] **Completed**

### Next Steps

- User-deferred incremental DA1/DA2 needs upstream han read sharing to monthly-runtime; no incremental run, scheduler, training, Audit, push or merge performed.
