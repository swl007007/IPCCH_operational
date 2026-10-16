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

## Subsequent user rulings, 2026-10-16

- FEWS missing-weight disposition: "接受这份历史运行的明确例外，保留全部现存材料". This applies only to `scen-b43ef6a-v1`'s documented 18 missing regional continuation boosters and affected 3,746/22,872 rows. Preserve all extant material and migrate the incomplete historical record with explicit disclosure; do not relabel it replay-passed or retrain under that identity. The PRD/design/implementation plan now record this narrow exception.
- Spending attribution: "不是这个项目当前月份，是另一个项目的，叫manuel-remote-sensing". The earlier USD 3 is not evidence for the target project's budget.
- Target current-month actual cost: "到目前为止是0". Record USD 0 as user-supplied current-month baseline for `food-crisis-modeling-enso`. The initial missing-spend gate is resolved; billing API verification remains unavailable. Proceed with scoped cloud work after actual quote/capacity and reservation gates; the platform and training USD 100 monthly limits are unchanged.
- Second historical exception: "接受这份历史例外，保留全部现存材料" in response to the `confirm-onset-v1` question identifying 7 missing original regional models and 2,446/11,436 S0/S3 system rows. Preserve all materials, label full-system replay unavailable, and separately provide retained pooled/global download and replay. No substitution or historical retraining is authorized. This is a separate explicit ruling, not an extension inferred from the scenario exception.
- Temporary MLflow administrator: "同意使用临时迁移管理员（推荐）". Create the temporary migration administrator for account configuration and read/write acceptance; password only in Secret Manager, remove the temporary administrator and credential after acceptance, preserve existing personal accounts/passwords, and leave final personal-login verification to the user. This resolves the credential-method question; the separate automatic rejection of public Cloud Run invocation is unchanged.
- Subsequent informed invocation approval: "批准该单项 IAM 变更，保留 MLflow 登录" after disclosure of the automatic TLS/Auth Weaken rejection and review of 19 negative-access plus 33 principal checks. Authorizes only `allUsers` / `roles/run.invoker` on Cloud Run service `research-mlflow` in `food-crisis-modeling-enso`, `us-central1`, to reach the existing MLflow login layer. Model/data/API access still requires MLflow authentication and GCS remains private. Submit the explicit action through normal tool review; a renewed rejection must be reported, not bypassed. Save service IAM before/after and repeat direct-HTTPS anonymous/content and authenticated checks. No project-wide or other-service public grant is authorized.
