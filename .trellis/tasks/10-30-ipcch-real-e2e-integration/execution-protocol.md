# Supervisor–Executor protocol and execution authorization

Authorized 2026-10-30 by the user's `/goal` attachment:
`/home/swl007007/.codex/attachments/230e3461-fb66-4bfa-8a98-87fce06d2df1/pasted-text-1.txt`.
Its exact content is preserved at `research/user-execution-protocol.md`.
This is the subsequent execution instruction after the final D1-D5 planning summary.

## Authority and lifecycle

- Codex is Supervisor: owns coordination, Trellis state, scope/spec maintenance,
  checkpoint/diff inspection, commits and final acceptance.
- The existing Herdr Claude pane is the primary Executor: owns implementation,
  tests, debugging and deliverables. Use Herdr, not a second routine implementer.
- The user's latest instruction explicitly says **do not start Trellis Audit or
  any automatic/independent Audit workflow**. It supersedes this task's earlier
  Audit-wrapper requirements and the standing repository enrollment instruction
  for this execution. Use native Trellis task state operations; never call audit
  register/start/close/boot. Supervisor review/checkpoint verification remains required.
- D1-D5, R1-R10, AC1-AC9 and deferred DA1-DA2 remain the functional scope. This
  protocol is execution authorization, not permission to retrain, rewrite accepted
  history, perform deferred incremental acceptance, change projects or publish a PR.

## Verified identities

- Supervisor pane: `w1A:p8`; Codex session
  `01a18e48-f335-7161-bc57-4c6913b92aa5`.
- Executor pane: `w1A:p2`; Claude session
  `6a490ae1-ee00-43f9-bdfc-c887c9816c09`; initially idle.
- Current session transcript's latest assistant entries identify
  `claude-opus-5-5`; pane display identifies the approximately 1M context window.
  Reconfirm the active model in the first new turn; do not silently substitute it.
- Exact Supervisor repo path:
  `/mnt/c/users/swl00/ifpri dropbox/weilun shi/ipcch_monthly_operational`.
  The Executor's mixed-case alias was verified with `os.path.samefile` as the same
  checkout. Reuse the pane/session; recover/compact it if needed instead of duplicating.
- Starting source HEAD: `69aa74a372f40581d6759a5703e7ec331ba4af63`.
  Pre-existing `AGENTS.md` changes belong to the user; preserve and do not stage them.

## Checkpoints

| Checkpoint | Executor deliverables | Supervisor gate |
|---|---|---|
| CP0 | Load current specs/context; verify local environment/artifact identities; narrow affected-file plan and test commands; no cloud calls | Confirm scope, model/session, state, and source evidence |
| CP1 | Sparse PATCH32, table mapping/completeness contracts and focused regressions | Inspect scientific/availability boundaries and red/green evidence |
| CP2 | Automatic Python EE graphs, Asset export lifecycle, deadline/receipt/duplicate protection | Inspect formulas, source-equivalence and lifecycle tests; DA1-DA2 remain deferred |
| CP3 | v2 CLI submission, UTC-month freeze, Workflow/config/image installation, current continuity | Inspect callers/config/build artifacts and integration tests |
| CP4 | Full relevant offline suite and built-image verification; concrete bounded cloud packet | Verify complete AC coverage, image/artifact pins, exact commands/resources/limits |
| CP5 | Approved current-round live prerequisite checks, deployment, full-roster retained-history run, current readback | Verify actual request/job/object/model evidence against AC1-AC9 |
| CP6 | Evidence matrix, operator handoff, final report and deferred-live statement | Supervisor final acceptance; native Trellis finish/archive only after actual acceptance |

Continue through recoverable errors and repair failed checks. Do not stop just
because one checkpoint completes; report it through Herdr and wait for Supervisor
review while preparing independent local evidence. Changes to the scientific or
user-owned scope return to Supervisor; routine implementation choices do not.

## Work ownership and evidence

- Executor reads `implement.jsonl`, PRD/design/plan and development guidelines;
  native context injection may not cross Herdr, so explicit child-side loading is
  required. Inspect exact code and GitNexus impact before symbol edits.
- Supervisor alone changes task/spec/checkpoint ledger unless delegated. Executor
  may write checkpoint evidence under `research/cpN/` and product/test changes.
  Do not overwrite others' changes or run destructive Git cleanup.
- Executor does not commit/merge/push/archive without a specific Supervisor command.
  Supervisor runs GitNexus detect_changes before commits and inspects the diff.
- No cloud call in CP0-CP3. CP4 supplies exact APIs/commands, identities/resources,
  read/write scope, limits and effects for Supervisor review before live execution.
  Approval of a bounded automatic run covers its described child work; runtime
  adds no manual interstage gates. Do not expand/retry cloud operations silently.
- Preserve existing 4-hour/zero-task-retry bounds unless a reviewed concrete packet
  expressly changes them; do not manufacture incremental work or bypass month guards.
- Persist checkpoint evidence and update `PROGRESS.md`; it is a state ledger,
  never an independent source of authorization. No acceptance claim without readback.
