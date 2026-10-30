# Execution authorization — 2026-10-30

User accepted the final planning summary after brainstorm/spec/grill and supplied execution-protocol-user.md as the active long-running goal. Codex Supervisor orchestrates and accepts checkpoints; verified Claude Opus 5.5 1M executes using Herdr. No Trellis Audit or automated audit lifecycle. Native Trellis start/finish is used for this task; this explicit instruction overrides wrapper-only local guidance.

User explicitly resolved the provider wording: retain Vertex CustomJob training -> Cloud Run-hosted MLflow, not a migration to Cloud Run Jobs. Verify Vertex jobs/logs/artifacts, Cloud Run MLflow full publication/readback, AlphaEarth Pooled-compatible cards/tags, and IPCCH Dashboard Experiments visibility. UI failure must be reported and cannot be claimed as passed. This supersedes the literal Cloud Run Job training wording in the supplied generic protocol.

Verified research-side Executor: Herdr w19:pE, Claude session a98cf837-af2f-4ff1-8a84-cbc2ec28c2c7, displayed Opus 5.5 (1M context), idle before dispatch. Reuse that existing session; operational executor w1A:p2 remains untouched.

Scope includes implementation, local validation, bounded three-horizon experimental execution and standard MLflow publication necessary to the approved spec. Before cloud mutations or paid jobs, Executor must prepare exact commands/config/input hashes, unique operation ids, resource/runtime/cost bounds and publication destinations; Supervisor reviews/releases the concrete packet. Do not inherit old task budget allocations or blindly duplicate jobs after polling timeouts. No IAM, global credentials, unrelated cleanup or production changes. Preserve existing dirty research checkout content via isolated worktree/staging; never reset it.

CP0: bind workspaces, preserve pre-existing changes, pin source/baseline/configs and commit approved spec.
CP1: implement/test fit-only policy and reporting; no-fit identities/membership/history/weight gates.
CP2: approved bounded Vertex executions; logs, predictions, final weights and verification receipts.
CP3: standard MLflow registration/cards/tags/dataset links and Dashboard visible records, independent metric reconciliation.
CP4: TUI table, all requirement evidence, final-weight retention, safe task-owned cleanup, clean commits and native closeout after Supervisor acceptance.

Do not stop for ordinary errors/checkpoints. Revalidate actual state, fix and continue within approved scope. No completion until every criterion is evidenced. No new human permission for routine in-scope recoverable work; out-of-scope scientific changes require clarification.
