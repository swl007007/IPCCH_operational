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

## RUNNING (do NOT start again; inspect durable outputs on resume)
- Assembly parity r2 effective check: `bash T/research/cp3/assembly-parity/run_r2_effective.sh` (bash PID 3490312, started ~07:25Z;
  log T/research/cp3/assembly-parity/run-r2.log, ends with `SUMMARY ...` and `exit=N`). Steps: stage2 exact -> stage3 exact ->
  stage2 research-parse -> stage3 research-parse (each ~25 min). Outputs (new files, never overwritten) in
  R/scratch/h2h8h14-final/assembly-parity/: r2_exact.json (+ r2_exact_assembled_hHH.npy), r2_exact_effective.json,
  r2_research_parse.json (+ arrays), r2_research_parse_effective.json. Stage2 exit 0 EXACT / 2 DIFFERS; stage3 verdict
  EFFECTIVE_IDENTICAL rc0 / EFFECTIVE_DIFFERS rc2 (float32 effective inputs + raw q2..q5 through the operational runtime).
  On resume: `ps -o pid,etime,cmd -C python,bash | grep -E "run_r2|stage2_op|stage3_eff"`; when finished, record verdicts+rc in
  T/research/cp3/cp3d-assembly-initial.md and report to Supervisor (Supervisor wants per-family causes, ORIGINAL diffs and
  the machine verdicts; r1 JSON has no verdict key and is NOT a pass).

## CP2 (training/package/handoff) — open, not accepted
- Fits done: H2 run f55ddf45198f427eade6d68c2a3a04f2 / m-4c46295486bc4d28af8cfca561cdf4ce; H8 0f7e584fccc549a28cf6fe9519b94da2 /
  m-e7976e74421a4d75b8462291101c8918; H14 a4bf0a5d2bef4418b31503d679ac3194 / m-c8efb3bd8157451295f15960fb3654ff. Harvest receipts
  R/staging/ipcch-h2h8h14-20261030/receipts/09-harvest-h0{2,8}|h14.json; MLflow readback T/research/cp2/mlflow-readback.
- Package CANDIDATE R/scratch/h2h8h14-final/package-build/out-r1/package, manifest 18b91d454163ac9ff9833d8127108e731b2f9d95069fb26fd5e7e8877a115f22,
  combination_id ipcch-validity-h2h8h14-final-20261030 (keep unchanged until explicit research acceptance). Relocated runtime raw-score
  parity: T/research/cp2/package-check/runtime_check_real_r2.json (historical probes only). Evidence T/research/cp2/cp2-package.md.
- Handoff bundle r5 (PKGWT dac4a0a builder research_cloud/packages/ipcch_handoff_inputs.py): R/scratch/h2h8h14-final/handoff-build/out-r5,
  58 files, manifest e6e3ebc6…, acceptance_entries 3621c350… (57 entries, acceptor/accepted_at EMPTY — needs explicit acceptance act).
  r5 adds iso3_reference (pycountry 26.2.16 table; training iso3 lineage kept, 31 CI blank -> CIV reference only, no IDP effect),
  population_reference.csv, fixed/geometry byte copy, roster_policy, 1315 fixed-source exception, 103 imported SD=0 seasonal rows.
  Evidence T/research/cp2/cp2-handoff-inputs.md (+ handoff-inputs-r5/). r4 (out-r4) still used by parity harness.
- Remaining for CP2 acceptance: Supervisor review of r5; explicit acceptance (package + bundle entries) is a research-side act.
- BINDING REQUIREMENT (Supervisor, design.md:27/R32/R55): fixed geometry/roster/ACLED/static/population must be checksum-bound to
  the selected combination. Plan: keep candidate 18b91d45 INTACT as evidence; build an explicitly versioned ACCEPTANCE ENVELOPE
  (new file, e.g. ipcch-combination-envelope-v1.json) binding combination package_manifest sha 18b91d45… + handoff_manifest sha
  (r5 e6e3ebc6… or successor) + roster sha 9ff2c420… + feature order sha, with acceptor/date fields; runtime (package load,
  initial.initialise, assembly inputs) must verify the envelope and REJECT any other bundle/package pairing even if the 527
  schema matches (tests). Include binding verification in the CP2 acceptance packet.

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
OPEN CP3 work (next, in order):
1. Feature batch writer (R52): immutable unique batch per generation bound to run id, records M, O, mode, combination ref,
   generation time, method ids (R40), per-family coverage ends + source-level gaps, missingness counts, acceptance records,
   retained-input refs; summary file for generation-only. Real batch = full 6,226 roster, duplicate keys fail (R32).
2. Inference validation (R19/R18/R51/R61): batch reference + combination exact match, cutoff/schema/real-dummy checks,
   missing required column -> fail, duplicate names -> fail, reorder by model names, extras ignored, unparseable/inf in required
   -> fail with area/column; nonfinite outputs fail with area/horizon/field; real requires package status accepted + checksums,
   smoke accepts candidate; per-scope training cutoffs from package manifest; post-processing unchanged (cummax, thresholds).
3. Generation orchestration: climate_run.update_all, GPP v3 append + ledger (R9/R49/R54), nightlight VIIRS append (R64), WFP
   keep/refresh (R64), research families/history_snapshot refresh (R59/R62), ACLED refresh/keep -> monthly_series, initial
   store from accepted bundle, assembly per horizon (T = O + H), population from population_reference via no-future builder.
4. Integrated preflight (Supervisor 6ebfb63 note): validate the ENTIRE FEWS delivery + all nested refs before any IPCCH
   mutation; mixed invalid-FEWS request -> zero writes/calls test.
## CP4 publication/compat (after CP3): v2 routing; per-system lock locks/{system} (R50/FCC2); single pointer with cross-system
inheritance (R63/FCC4); candidate publication (R66); CAS no retry (FCC3); activation from current release; legacy v1
cutover/inherit exact current (R37/FCC9); promote/resume reject new candidates (FCC5); smoke isolation (R36/R48); all three
horizons or none (R18).
## CP5 local small-area smoke E2E with the real 3 models (M 2026-10, O 2026-08; distinct from historical parity evidence);
## CP6 acceptance. Assembly parity = historical compatibility evidence only.
