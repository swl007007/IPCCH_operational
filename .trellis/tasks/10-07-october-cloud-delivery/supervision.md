# Supervisor–executor agreement

## Authority and scope

Following the v0.4 planning summary, the user explicitly requested: use Herdr to communicate with another Claude Opus 5.5 1M, have it implement this spec, and have Codex review checkpoints and supervise; no additional Trellis task audit. This is the subsequent implementation approval. It supersedes earlier design-only and automatic audit-controller lifecycle requirements for this task. Do not start/register/close a trellis-audit run or modify unrelated existing audit enrollment.

Continue normal Trellis task/context tracking with native `task.py start`, implementation checks and eventual supervised finish. Code changes and relevant local validation/model replay are authorized. Training remains deferred. Cloud deployment/resource mutation, production runs and release-pointer changes are not authorized by this handoff.

## Verified session binding

- Supervisor: Codex, Herdr pane `wR:p1`, session `01a11908-591c-7bf0-8a46-1bf09c6019f9`.
- Executor: Claude Code v2.1.280, Opus 5.5 (1M context), Herdr pane `wR:p3`, session `e8ac76ab-3486-4e51-b70c-ed09b2846fc7`.
- Shared cwd: `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational`.
- Initial source HEAD: `4a42f1f666a4f2d5d2616069fe25ddd81f2662cb`.
- Existing changes to `.trellis/.template-hashes.json`, AGENTS.md/CLAUDE.md index counts, untracked skill/config directories and `.birdview/` are not executor-owned. Preserve them. Task documents belong to the supervisor; implementation, tests and repository `PROGRESS.md` belong to the executor. Coordinate changes rather than overwrite shared work.

Re-verify pane/session identity on resume. Do not use model self-report alone: the live Claude welcome banner and model selector both showed Opus 5.5 1M. A startup hook reported malformed JSON; do not repair unrelated hooks as part of this task or assume missing hook context was loaded. Read explicit task/spec context.

## Communication and checkpoint protocol

Use Herdr agent prompt/read/wait against explicit pane IDs. Executor reports completion in its pane and, when possible, sends a short checkpoint notification to supervisor `wR:p1` using the Herdr skill. Supervisor reviews files/diffs/evidence before responding with acceptance, revision requests or a scope-limited go-ahead. Do not treat prompt submission, a terminal Done badge, or self-reported pass as review acceptance.

Executor maintains `PROGRESS.md`: current checkpoint, changed paths, commands/results, evidence paths, unresolved constraints, and the supervisor's latest disposition. It is an operational ledger, never authority to widen scope. Work not affecting a blocked scientific contract may continue only within the checkpoint scope agreed by supervisor.

| Checkpoint | Executor deliverable | Supervisor gate |
|---|---|---|
| CP0 | Read spec/research; model/environment/lineage evidence; proposed exact file/impact list; local environment and validation plan | Resolve or bound T1–T3 before affected adapters; no product edits until response |
| CP1 | Manifest/raw choices/calendar filling contracts and focused tests (M2 and relevant M5 contract pieces) | Causal semantics, native IDs, four source choices, provenance and no training |
| CP2 | Remote preparation adapters and source/geometry contracts (M3) | Verified reducer/scale/key lineage, latest complete month, failure vs lag, local reference evidence |
| CP3 | Six-package scoring, country/optional diagnostics, output/package compatibility (M4) | Correct horizons, output schemas, null diagnostics, immutable assets, relocation/replay evidence |
| CP4 | Event/job/run-state/release composition and deployment definitions (M5) | Generation binding, duplicate no-op, new-ID retry, CAS preservation; local/mock tests only |
| CP5 | Integrated local validation, scoped diff, documentation, reproducibility and remaining cloud pilot plan | Supervisor final review; distinguish implemented/tested from unrun cloud acceptance |

Milestones can be reordered only by explicit supervisor response, with requirement mappings retained. The baseline acceptance evidence and approved task documents should be committed separately before product implementation after GitNexus detect_changes; never stage unrelated changes. GitNexus impact is mandatory before symbol edits, and HIGH/CRITICAL results must be surfaced before proceeding. Do not fabricate a clean baseline or silently omit existing changes.

## Status

Binding re-verified against live Herdr state. Native Trellis task status is `in_progress`, branch `feat/october-cloud-delivery`. No additional task audit or cloud execution has started.

### CP0 disposition — 2026-10-07

Accepted as bounded investigation evidence, not production model acceptance. Supervisor checked the persisted replay JSON and environment-freeze hashes against the report, and the original clipping correction summary (hash and 85/8,013 phase4/phase5 totals). All IPCCH decisions agree; saved April score exports are postprocessed and cannot establish unclipped raw-score parity. FEWS has passed load/identity checks only. T1, FEWS replay, October compatibility and T3 remain open.

After the task-document baseline commit, CP1 may implement: cutoff/schema validation in `tools/refresh_h5_inputs.py`, independent source-family replacement preserving the old combined wrapper, a delivery-specific manifest validator using existing object-reference helpers, and same-area past-only base-series fill with audit. Focused tests must cover all four source choices, malformed/ambiguous dates and keys, Forecast exclusion, missing previous calendar month, future/cross-area fill prevention, and invalid manifest identities. Existing converter symbols have LOW upstream impact as recorded in `PROGRESS.md`; affected callers are the refresh/audit/focus-check tools. No affected remote adapter or scoring pipeline is approved by this checkpoint.

Keep the frozen scoring environment unchanged. For CP1 pure contract/conversion tests the existing system Python/pytest may be used with an explicit dependency record; this does not qualify as model-runtime acceptance. If an isolated pinned test environment becomes necessary, create it under `/tmp` or the repository with exact numerical pins; do not modify the existing venv. Defer rasterio selection until raster work; verify NumPy ABI compatibility rather than preselecting 1.3.9. Report CP1 diff, runnable tests and unresolved issues, then wait for review. No commits by executor without supervisor coordination.
