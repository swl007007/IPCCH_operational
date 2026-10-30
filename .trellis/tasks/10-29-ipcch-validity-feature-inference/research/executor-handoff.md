# Executor durable handoff — READ FIRST after compaction (SAME session 6a490ae1; do not restart)

Identity: Claude Opus 5.5 1M, session 6a490ae1-ee00-43f9-bdfc-c887c9816c09, Herdr w1A:p2; Supervisor Codex w1A:p1 (report via
`herdr agent prompt w1A:p1 "..."`). Single executor owner; ignore observer peer sessions (no cross-session messaging).
CONSTRAINTS: NO Trellis Audit; NO production deployment / live-current change; NO additional cloud writes or EE compute/export
(read-only metadata only; any EE compute needs a Supervisor packet); NO retraining/new fits; frozen training worktree
R/control-plane-h2h8h14 stays clean at 9aa9e54; preserve Supervisor-owned files (research/cp1|cp2/supervisor-review.md,
research/cp3-supervisor-review.md, research/cp3-release.md, cp2/c6c7-implementation.md edits) — never stage/commit them;
do not commit AGENTS.md/CLAUDE.md GitNexus stat lines; GitNexus impact before editing existing symbols, detect_changes before
commits (warn on HIGH/CRITICAL). Commit trailer: Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>.
Paths: OP=/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational (branch feat/ipcch-validity-feature-inference);
R=/home/swl007007/projects/food-crisis-research; T=OP/.trellis/tasks/10-29-ipcch-validity-feature-inference; PKGWT=R/control-plane-h2h8h14-pkg
(branch task/ipcch-h2h8h14-package). Tests: `cd OP/cloud_pipeline && PYTHONDONTWRITEBYTECODE=1 ~/.venvs/fewsnet-test-lock-20261022/bin/python -m pytest <files> -q -p no:cacheprovider`.

## RUNNING: nothing. Parity r2 FINISHED (exit 0; stage2 DIFFERS rc2 x2 float64 lat/lon + ACLED parse ulp; stage3
EFFECTIVE_IDENTICAL rc0 x2: float32 inputs and raw q2..q5 identical all 3 horizons). Recorded df83cbc in
research/cp3/cp3d-assembly-initial.md; Supervisor accepted as historical compatibility evidence (not CP5/target-date proof).

## CP2 - ACCEPTED/CLOSED (Supervisor explicit acceptance 2026-10-30; c9c080a)
- Accepted envelope v2 R/scratch/h2h8h14-final/envelope/ipcch-combination-envelope-v2-accepted.json sha256
  03b938427391aa15d3786377151e922bfdb97cc161f312b72ebed9f596c89596 (Codex Supervisor, 2026-10-30): package 18b91d45...,
  feature order 0ef1ffec..., handoff manifest e6e3ebc6..., roster 9ff2c420.../6226, finalized entries cb14a956...
  (57) in R/scratch/h2h8h14-final/handoff-build/out-r5-accepted-v1. Originals (package candidate status field, r5,
  draft entries 3621c350) unchanged. Readback evidence research/cp2/binding/{cp2-binding.md, acceptance-readback.json}.
- Runtime binding: cloud/ipcch/binding.py (verify_combination real/smoke(fixture_root), verify_handoff real only,
  verify_fixture_bundle smoke only lexical admission + lstat/symlink refusal incl. root), store pairing table;
  initial.initialise(..., binding), install_acceptance, read_assembly_inputs(store, root, binding), read_population.
  geography.py (roster_geometries, restrict_to_roster, population_snapshot via PopulationSnapshotBuilder).
  Commits e3a438b, 89b0e02, ec5bd53 (R48), d3130e7 (finalize tool), c9c080a.
- Smoke uses the candidate/accepted envelope with mode="smoke" + a declared fixture_root; never the real bundle.

## CP3 (operational v2 runtime, local) — open
Committed (operational branch): b9e333e FEWS crlf; 6ebfb63 request v2; 9270192+557515f stores/retained; c65e43d+b3035ad ACLED;
dab5bc9 climate core+SPI/SPEI; 27a50be; 1123bcf seasonal SPI/SPEI; 4ebb7d0 EE monthly; fe362c3 table providers; b8ea796 seasonal
providers + climate_run; c090c4e climate review fixes; ad931c2 assembly + initial (+vendored research formulas); bd06bdf residual
fixes (Supervisor verified hashes). Latest regression receipt T/research/cp3/cp3d-residual-fixes-tests-run1.log: 99 passed.
Evidence: T/research/cp3/{cp3c2-acled.md, cp3c3-climate-core.md (parts 1-6), cp3d-assembly-initial.md}.
Accepted review findings already fixed: all CP3 adapter findings (GLDAS slots, drought baseline axes, strict tables, progress
reports, seasonal bounds/availability), assembly/initial batch (empty optional sources NaN, IDP dup, integral ids, whole-bundle
preflight, snapshot metadata), residuals (S2E3 coverage before join, strict field validators).
Known limitations (stated): no live EE run; han-sandbox private assets unreadable; baselines/S2E3/S2C3 producers not delivered;
rainfall exact-collision patch not delivered.
Since compaction (CP3): 8d031db + 72f8cd8 concrete EE/GCS transport cloud/ipcch/ee_transport.py (EEBackend+TableBackend;
_list_images; definitive absence via parent listing; reserve-before-submit create-only task record; IPCCH bounded wait
cancel on timeout; exact-generation reads; computeFeatures asset tables; from_environment). f1af645 cloud/ipcch/gpp.py
(IPCCH-only research-equivalent GPP v3: fills 65534/65535 masked, sum/n_valid*0.01, cell-centre; ledger; fill-only-
unpublished; FEWS raw zonal unchanged). Climate output filter strict (declared_extra only; rain paint full calendar).
OPEN CP3 work (next, in order):
1. Feature batch writer (R52): immutable unique batch per generation bound to run id, records M, O, mode, combination ref,
   generation time, method ids (R40), per-family coverage ends + source-level gaps, missingness counts, acceptance records,
   retained-input refs; summary file for generation-only. Real batch = full 6,226 roster, duplicate keys fail (R32).
2. Inference validation (R19/R18/R51/R61): batch reference + combination exact match, cutoff/schema/real-dummy checks,
   missing required column -> fail, duplicate names -> fail, reorder by model names, extras ignored, unparseable/inf in required
   -> fail with area/column; nonfinite outputs fail with area/horizon/field; real requires package status accepted + checksums,
   smoke accepts candidate; per-scope training cutoffs from package manifest; post-processing unchanged (cummax, thresholds).
3. Generation orchestration: climate_run.update_all (transport + declared_extra), GPP (gpp.update_gpp DONE), nightlight VIIRS
   append via existing export/zonal contract on roster_geometries (R64), WFP manual raw_upload -> refresh_h5_inputs.wfp_aggregates
   ipcch rows only (no new fetcher) (R64), research families/history_snapshot refresh (R59/R62), ACLED refresh/keep -> monthly_series, initial
   store from accepted bundle, assembly per horizon (T = O + H), population from population_reference via no-future builder.
4. Integrated preflight (Supervisor 6ebfb63 note): validate the ENTIRE FEWS delivery + all nested refs before any IPCCH
   mutation; mixed invalid-FEWS request -> zero writes/calls test.
## CP4 publication/compat (after CP3): v2 routing; per-system lock locks/{system} (R50/FCC2); single pointer with cross-system
inheritance (R63/FCC4); candidate publication (R66); CAS no retry (FCC3); activation from current release; legacy v1
cutover/inherit exact current (R37/FCC9); promote/resume reject new candidates (FCC5); smoke isolation (R36/R48); all three
horizons or none (R18).
## CP5 local small-area smoke E2E with the real 3 models (M 2026-10, O 2026-08; distinct from historical parity evidence);
## CP6 acceptance. Assembly parity = historical compatibility evidence only.
