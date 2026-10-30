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
CP3 commits after CP2 acceptance: bd00654 nightlight; ced8e52 batches (R52) + batch inference (R19); 8e00c8a WFP
correction A (v2 ipcch.wfp refresh {action,file,start,end}; wfp.py); 669d2c1 climate table_name history__climate_*;
f90e97b generation orchestration (cloud/ipcch/generation.py; smoke fixture tests/cloud/ipcch_smoke_fixture.py);
3e7c470 integrated FEWS preflight (v2 full fewsnet.delivery validation via shared v1 validators systems=(fewsnet,);
nested refs; delivery_request_v2.admit); 2d978d4 Supervisor review repairs (batch namespace admission, bound roster,
package re-verify, horizon metadata, strict_csv, HEAD-based init); b52387c climate_run.real_providers.
Evidence: research/cp3/{batch/,generation/,preflight/,transport/,wfp-*.md,nightlight-contract-check.md,gpp-*.md}.
Supervisor rulings: WFP = research HDX series via declared-interval refresh (A); nightlight avg_rad__sum kept; GPP IPCCH
adapter (fill mask x0.01); Supervisor owns prd/design/implement/spec WFP doc edits (do not edit them).
OPEN CP3 (next):
1. v2 runner for the four operations without publication (admit -> IPCCH generation via Generation -> IPCCH inference
   via load_batch/score_batch; FEWS generation/inference mapped onto existing prepare/deliver, R60), zero-write spy test
   for invalid mixed requests (the admit-before-anything requirement), partial-success across systems (R17).
   OPEN QUESTION to Supervisor: request ipcch.model_combination references package_manifest, but acceptance lives in the
   versioned envelope -> propose {combination_id, envelope: ref} (real must be accepted; smoke may use candidate).
2. Real-asset local integration: accepted envelope v2 + out-r5-accepted-v1 real-mode initialise/generation dry run with
   fake providers? (CP5 is smoke with small-area fixture; real-mode runtime tests use envelope v2 + accepted bundle.)
## CP3 status: implementation complete pending Supervisor acceptance; real-mode local integration 50d7ace
(research/cp3/real-integration). Commits since 4878036: d0d7567 runner R48 admission + R45 per-version receipts,
4db4fd5 provider windows factory, b257908 utf-8-sig, 016d90d receipt-failure reporting (CLOSED by Supervisor).
Open for CP3 acceptance: real provider/FEWS runtime adapter wiring evidence (FEWS adapter R60 lands with CP4 phase C/D).
## CP4 (LOCAL implementation released; acceptance needs independent review) - STATE AT COMPACTION (~94% ctx)
Plan/rulings research/cp4/cp4-plan.md; ledger + Supervisor closures research/cp4/cp4-progress.md; seams cp4-publication-seams.md.
Committed: 08c7a2b+34362d8 locks (CLOSED); 47d7c4c+b684e90 publication core (cloud/ipcch/publication.py; CLOSED: stable
record read, member mode, required verify_delivery seam); d7c3636 ipcch.country_reference (reviewed); 417c6d2 Phase B
member writer/verifier (cloud/ipcch/delivery_member.py) + provenance sidecar (cloud/ipcch/provenance.py, batch
feature_provenance.csv) - Supervisor found 5 member gaps + 2 provenance gaps (supervisor-review 8972e10).
COMMITTED 6e57972 (Phase B six findings CLOSED by Supervisor), b98f100 (inherited-source inventory blocker CLOSED:
verify_delivery checks inherited members against their PINNED source inventory, exact set + bytes), e3bb779 runner:
run_v2.Deployment(store, roots smoke/real distinct), run_request(deployment=) locks executed systems after admit through
publication, IPCCH inference publishes via release_v2.publish_ipcch_run (candidate/current), chained own generation for
two-system runs, failed publication keeps batch/predictions; member_inputs() builds member sources. Tests
test_ipcch_run_v2.py 12, release 8, member 8, publication 9. No WIP on disk. Ledger research/cp4/cp4-progress.md.
CP4 SINCE (all committed, tests green): e48ca51 executable v2 route (cloud/ipcch/entrypoint_v2.py; delivery_job
`run --v2-config` dispatch); ec7a31b per-system publication ids `<run_id>-<system>` (release_v2.publish_member_run);
6f07b2f entrypoint fixes CLOSED by Supervisor (validate before any state read, prod pointer read only for real IPCCH
inference+current; providers built only when ipcch_generation; durable+returned status keep structured report;
overall literal `partial_success`); 6d8ea08 Phase D legacy guards: delivery_job.bind_current (R37 request-time reject of
IPCCH-including v1 after activation, FCC inheritance names the current member; new-contract IPCCH inherit = own
feature_origin + archive repeats manifest ref), publication-time recheck in legacy validate(), v1 locks for executed
systems (_locked), any-v2-record + v1 FEWS-only -> _compute_fews_member (prepare_inputs on FEWS-only models,
fews_v2.write_member, publish_member_run(fewsnet) inheriting IPCCH + activation); pipeline.reject_new_contract_candidate
+ bind_promotion; ObjectStore write_bytes/read_bytes + delivery_v2 exact bytes (pickled FEWS packages; was a real defect).
Full receipt: tests/cloud + operator release/cli 750 passed.
NEXT (Supervisor D1-D3 rulings in design.md "R60 FEWS adapter wiring", implement without further permission):
(a) v2 schema: fewsnet generation requires `prepare_request` ObjectRef; admission reads its pinned bytes, validates with
validate_prepare_request (origin == derived fewsnet origin) and verifies ALL nested refs (incl. unused IPCCH
declarations) before any mutation; (b) prepare selected-systems seam (plan_prepare/_extract `systems=`, default both,
v1 bytes unchanged; FEWS-only = no IPCCH acquirer/store ops; check_prepared_snapshot FEWS-only aware); (c) FEWS keep =
FEWS-row projection of retained_family_rows (same canonical rows/cols/order) vs pinned FEWS history; refresh via existing
converters; (d) generation persists a create-only source binding beside the prepared manifest (acled/wfp choices + refs)
so gen-only -> later inf-only == gen+inf (test byte equality); inference-only refuses a snapshot without the binding;
(e) fewsnet_runner wired in entrypoint (real only; R38 smoke has no FEWS) using fews_v2.write_member +
publish_member_run; tests: gen-only / inf-only / combined, byte equality vs v1 FEWS member on same inputs, two-system
current + candidate + partial failure. Then CP5 (actual accepted package, fixture-only >=2 countries, executable
gen-only/inf-only/combined + isolated current replacement; synthetic XGB fixtures are NOT CP5), CP6.
## CP5 local small-area smoke with the ACTUAL accepted H2/H8/H14 package (envelope v2 / package 18b91d45; not synthetic
## fits), fixture-only inputs (fixture bundle subset across >=2 countries, never real retained stores);
## CP6 acceptance. Assembly parity = historical compatibility evidence only.
