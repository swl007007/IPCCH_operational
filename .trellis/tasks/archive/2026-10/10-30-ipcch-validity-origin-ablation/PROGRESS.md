# Progress — IPCCH validity origin ablation (task 10-30)

## 2026-10-30 Executor (Claude b9db2dbb, w19:pE)
- CP0 done: research/cp0/cp0-receipt.md, cp0-pins.json. Isolated worktree control-plane-origin-ablation (snapshot 99f3ebd).
- CP1: implementation 7023d10 (fit-only policy, origin contract/gates, paired comparison, holdout-only package);
  Supervisor WIP findings 1-3 fixed in the same commit; focused tests pass; provisional no-fit gates + independent
  verifier pass (research/cp1/). Next: final recipes/gates on 7023d10, full regressions, CP1 checkpoint, then the
  bounded build/job packet (no cloud action until Supervisor release).

## 2026-10-30 (cont.) Executor
- CP1 closed by Supervisor: final no-fit gates (research/cp1/cp1-final-gates.md), WIP fixes 1-3 (7023d10), smoke test 868db9f.
- Full pinned-code regression on 868db9f: all suites pass (research/cp1/regression/regression-receipt.md); pre-change
  baseline on 99f3ebd also all pass.
- CP2 build released and executed once: build 22176002 SUCCESS, image training-ipcch-validity@sha256:b208b132…,
  USD 0.19 reserved (not billed); receipts research/cp2/build/. Lineage proof accepted.
- Job packet r1 prepared (staging/ipcch-origin-ablation-20261030/job-packet, SHA256SUMS f1b0d7c2…), reviewed by the
  Supervisor; awaiting Vertex release. Platform pool headroom after the job line would be USD 0.01.
- Post-job tools prepared and exercised (research/cp4-prep/tools-receipt.md): independent recompute (repaired, 15/15),
  readback/job-log verifiers with CH r3 defects fixed and checked on real CH success artifacts, identity chain, UI targets,
  run_final.sh, annual-weight cleanup.

## 2026-10-30 job packet r1 execution (Executor)
- Steps 1-3: reservations (platform 99.09->99.99, training 146.58->152.30), 9 create-only uploads read back equal, final
  render ok x3, occupancy ok. Receipts research/cp3/jobs/.
- H0 customJobs/2842603222726606848 SUCCEEDED (provider end 18:35:07Z): run bd24976069ee4530bb97343c1ec6e730,
  LoggedModel m-055654f09a78436593ce720f4c52be10, v1; harvest 17/17; fits 19169/24197/28551/37759, 0 copies; replays holdout
  32 + annual 96 passed and bound; trial 721 s.
- H6 customJobs/2596031143128072192 SUCCEEDED (18:30:55Z): run eb33b087fe314237ad1c6432bcfe140f, LoggedModel
  m-daad991238a5430eb504eaacd4046d36, v1; harvest 17/17; fits 21282/22478/27134/34004, 0 copies; replays 32 + 96 passed; 484 s.
- H12 gate: GO 18:32:54Z, fresh reads 18:33:19Z, ONE submit 18:33:29Z customJobs/3377405678476853248; poller running.
- H12 customJobs/3377405678476853248 SUCCEEDED (18:46:10Z): run 8237e829dc4b42169ccb3136c19aafb2, LoggedModel
  m-9f73aac99f444c91b8022ec9f6e41df3, v1; harvest 17/17; fits 21282/25960/30784, 0 copies; replays 32 + 64 passed; 413 s.
- Final read-only packet r1 run ONCE: rc 0, final_pass true (research/cp4/final/final-verdict.json; SHA256SUMS-final):
  identity pre/post ok; independent recompute passed (pairing 70972/61042/52027, 0 mismatches; CH-final metrics.json
  reproduced); 3 log reads ok; readback 6/6 (3 origin runs, 3 CH-final baselines unchanged); UI 14 targets, 6 identities,
  3 run-metric targets, Dashboard Experiments tab lists all six run names, ui_pass true; 2 reader accesses.
- Pending: annual-weight cleanup packet (separate release), final report, requirements evidence, commits, Supervisor acceptance.
- Cleanup packet r1 executed once (fresh plan == reviewed dry run a0b255c8…): 32 annual booster objects deleted with
  generation match, absent on readback, local copies removed; post-verify ok (research/cp4/cleanup/). R9/A6 met.
- Final report / requirements map finalized (research/final/); stale status headings of design/implement updated (contracts
  unchanged); reproducible tool sources copied to research/tools/ (MANIFEST.tsv).
- Supervisor final acceptance recorded (research/final/supervisor-final-acceptance.md): R1-R11/A1-A6 met. Native finish/archive follows.
