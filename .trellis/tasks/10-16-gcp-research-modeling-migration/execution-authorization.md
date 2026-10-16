# Execution authorization and supervisor protocol

The user's active goal on 2026-10-16 authorizes execution of the reviewed migration specification with a Herdr Claude Opus 5.5, 1M-context executor and Codex supervisor. The scope remains PRD R1-R14 and AC1-AC8; completion means the implemented and verified migration, not merely a written plan or partial local scaffold.

User instruction: "用herdr技能绑定另一pane的opus 5.5 1m作为执行者，你作为监督者抽查diff，checkpoint和交付物。直到完成spec前运行goal任务。除非出现CRITICAL ERROR否则保持运行。在goal完成前你有所有scope内的云操作权限。其他云权限请中断等待批准。"

This supersedes the earlier requirement to wait for separate permission for every in-scope cloud operation. Continue to identify and record individual commands/resources/effects and enforce both monthly budgets, project boundary and technical gates, but do not repeatedly ask permission for already authorized actions. Out-of-scope cloud actions require user approval. Critical errors require immediate notification and stopping the affected operation. Routine failures, fixable issues and long-running jobs do not end the goal; inspect authoritative state and continue safely.

No authorization to change unrelated projects, exceed budgets, rewrite scientific outcomes, delete original data, set Dropbox cloud-only, omit required retained-weight versions, waive audits or clear controller gates is inferred. Filesystem/tool permission mechanisms still apply. Do not use delegation to evade a supervisor-side permission rejection.

## Live executor selected

- Herdr pane: `w14:p9`, agent name `gcp-research-executor`.
- Claude session: `228d9075-d67a-41c9-9f4c-7830cdac3b87`.
- Terminal: `term_65dee2e4ca9b6a`.
- Verified header: `Opus 5.5 (1M context)`, Claude Code v2.1.280.
- Launch: `--model claude-opus-5-5[1m] --autocompact 1M --permission-mode auto`.
- Working directory / exact registered repository: `/mnt/c/users/swl00/ifpri dropbox/weilun shi/ipcch_monthly_operational`.

Verify these live values again at registration/start. Startup context hook emitted malformed JSON; the executor must explicitly read AGENTS, the task PRD/design/plan and curated manifests. Do not treat that hook failure as a completed context load. The controller has no active migration run yet at this record's creation; registration/start receipts must be appended to checkpoint evidence.

## Checkpoints and supervision

Executor owns implementation, local/cloud tests, fixes and phase evidence. Supervisor owns plan/authorization updates, binding, scoped diff and artifact spot checks, coordination and completion judgement. Keep checkpoint evidence under `research/`, append this task's progress without overwriting unrelated ledger entries, and commit relevant work at verifiable boundaries.

For each P0-P6 checkpoint record: actual source/implementation SHA and dirty scope; completed requirements; commands and outcome paths; cloud project/resource IDs/image digests; estimates/reservations; failed/skipped checks; next action and any live handle. Never put secrets in evidence. Supervisor verifies current diff and sampled artifacts directly and checks all AC coverage before completion. A process timeout is not evidence of job death; poll the same job/session and inspect status before restarting.

Do not stop at each routine checkpoint for new user permission. Continue independent in-scope work while supervisor reviews evidence; stop affected work when a critical error or explicit supervisor hold requires it. Do not close/archive the task until required evidence is complete and the supervisor has reconciled it. Close via the bound audit executor and preserve the accepted audit result; a queued review is not a pass.
