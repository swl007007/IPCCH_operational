# Execution authority and checkpoint protocol

The user's 2026-10-22 `/goal` instruction authorizes execution of this task's full approved spec through actual acceptance. Source: `/home/swl007007/.codex/attachments/ac2a3527-2eb9-4323-b1e8-0ab34be5176c/pasted-text-1.txt`, SHA256 `5dea2bd935af89cd22495fc96c8c5c91d9cc9acfbc491379b7fe239f7a7e757c`.

## Roles and lifecycle

- Supervisor: current Codex goal thread `01a16167-c7f6-7fa2-bbe3-bf1451082c94`, Herdr pane `w1B:p1`.
- Primary executor: existing Claude Opus 5.5 1M, xhigh, pane `w1B:p2`, terminal `term_65e647d9fe2bea`, session `bfb1fb18-3db6-4d5a-898b-5f4f86719ec9`. Identity/cwd/idle state verified before dispatch; recheck after any disconnect.
- Exact working repository: `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational`.
- Base before execution: `8970523e917e269585008222436ae3588290ac3b`, branch `feat/october-cloud-delivery`. Implementation branch: `feat/fewsnet-fixed-map-retrain`.
- Explicit override: do not start Trellis Audit, invoke audit wrappers, or launch automatic/independent audit workflows. Use native Trellis task activation and checkpoints. The supervisor's own diff, test and artifact verification remains required.
- `.trellis/config.yaml` contains no enabled lifecycle hooks; native task start therefore has no configured audit hook. The executor's startup hook JSON parse warning is nonblocking: load Trellis context manually, without unrelated hook repair.
- Preserve all 73 pre-existing tracked changes. `preexisting-worktree.json` records their raw hashes and external byte backups. Stage explicit task paths/hunks only. Never reset, bulk-stage or stash unrelated state without a concrete preservation plan.

## Authorization boundaries

Implementation, public HDX/official resource retrieval, local data assembly/fitting and necessary software/data/package integrity checks are authorized. All GCS read-only commands within this conversation/task are preauthorized. The user subsequently explicitly stated: `云端权限预批准开放到10/22 09:00 ET`. This grants necessary task-scoped cloud operations through **2026-10-22T13:00:00Z**, superseding individual cloud approval during that window. Record concrete operations/results, check fresh UTC time before consequential actions and retain spec acceptance/recovery gates. After expiry, do not launch new cloud mutations; non-GCS operations again require individual approval. Long-running submitted work may be observed; do not use preapproval to expand task scope.

No model evaluation/test split, backtest, threshold search, confidence recalculation or IPCCH inference. Respect PRD source cutoffs, all-history fitting, fixed map/features/recipe and frozen-confidence rules. Do not fabricate mapping, preparation or acceptance evidence.

## Working loop

Read spec → delegate bounded work → executor implements/verifies → supervisor samples diff/tests/artifacts → feedback → checkpoint → continue. Executor owns routine implementation and test/debug work; supervisor owns decisions, task authority, checkpoint acceptance and final verification. Do not start a parallel audit or substitute a Codex implementation agent.

Maintain `PROGRESS.md` and compact task evidence. At each checkpoint report changed files/commits, exact verification commands/results, produced artifacts, requirement coverage, unresolved data gaps and the next concrete cloud operation if needed. A checkpoint is not full-task acceptance. Continue independent local work while a cloud permission is pending. Mark ACs complete only when their deliverables are verified.

Initial checkpoint: confirm frozen runtime/assets/confidence and local histories; retrieve HDX-registered latest CS for all 22 countries with raw hashes and content dates; establish credible geographic crosswalk/additions and honest gaps; inventory WFP/ACLED/GOSIF/remote input needs. Report before fitting; zero credible new labels blocks fitting while independent implementation can continue. Then implement the existing full-data runner/package compatibility path and the manifest/delivery/candidate changes in bounded checkpoints.
