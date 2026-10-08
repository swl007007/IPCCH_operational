# Supervisor–executor agreement

## Authority and scope

**Latest authorization deadline (user, 2026-10-08):** pre-authorized cloud-debugging window extended through **2026-10-08 17:00 ET (21:00 UTC)**. This renewal supersedes the earlier 10:30 ET/14:30 UTC end time and restores task-scoped cloud work. Begin final inspection/wind-down by **16:45 ET (20:45 UTC)**. Preserve prior failed attempts and partial objects; retries use new immutable IDs. Continue authorized task-scoped work within the window, reserve time to stop only task-owned jobs/exports before expiry, and preserve evidence and accepted pointers. No new cloud-debugging actions after expiry without renewed authority. Local implementation/review remains authorized; training and unrelated resources remain excluded.

**Latest cloud authorization (2026-10-07 ET):** the user granted full cloud-debugging authority in the current Google SDK project `manuel-remote-sensing`, mentioned 2026-10-08 09:00 ET, and then explicitly authorized attempting to register/enable/start missing endpoints/services while they sleep, asking to be interrupted only for CRITICAL issues. Supervisor announced continuing now under that follow-up instruction and treating 09:00 ET as a progress checkpoint. SDK live config confirms project `manuel-remote-sensing`, account `weilun.shi@cgiar.org`, compute region `us-central1` (zone `us-east1-b`; do not assume these form one location). This supersedes earlier no-cloud-debug/deployment scope in these documents. Necessary service enablement, task-scoped IAM/resource setup, image/job deployment, live preparation/scoring and cloud debugging are authorized. Use isolated task/staging namespaces and preserve existing accepted consumer releases. Model training, unrelated cloud changes, and consumer production cutover remain outside this task. No extra task audit. Supervisor continues checkpoint control and escalates only issues that cannot safely be resolved within this authority.

Following the v0.4 planning summary, the user explicitly requested: use Herdr to communicate with another Claude Opus 5.5 1M, have it implement this spec, and have Codex review checkpoints and supervise; no additional Trellis task audit. This is the subsequent implementation approval. It supersedes earlier design-only and automatic audit-controller lifecycle requirements for this task. Do not start/register/close a trellis-audit run or modify unrelated existing audit enrollment.

Continue normal Trellis task/context tracking with native `task.py start`, implementation checks and eventual supervised finish. Code changes and relevant local validation/model replay are authorized. Training remains deferred. The initial local-only handoff has been superseded by the cloud authorization above; existing-consumer production cutover remains separate.

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
| CP4 | Event/job/run-state/release composition and deployment definitions (M5) | Generation binding, duplicate no-op, new-ID retry, CAS preservation; local/mock and authorized staging validation |
| CP5 | Integrated validation, scoped diff, documentation, reproducibility and staging pilot evidence | Supervisor final review; distinguish implemented/tested from unrun cloud acceptance |

Milestones can be reordered only by explicit supervisor response, with requirement mappings retained. The baseline acceptance evidence and approved task documents should be committed separately before product implementation after GitNexus detect_changes; never stage unrelated changes. GitNexus impact is mandatory before symbol edits, and HIGH/CRITICAL results must be surfaced before proceeding. Do not fabricate a clean baseline or silently omit existing changes.

## Status

Binding re-verified against live Herdr state. Native Trellis task status is `in_progress`, branch `feat/october-cloud-delivery`. CP0–CP2 accepted and committed through `516c75e`; CP3 and authorized task-scoped cloud setup are in progress. No additional task audit.

### CP0 disposition — 2026-10-07

Accepted as bounded investigation evidence, not production model acceptance. Supervisor checked the persisted replay JSON and environment-freeze hashes against the report, and the original clipping correction summary (hash and 85/8,013 phase4/phase5 totals). All IPCCH decisions agree; saved April score exports are postprocessed and cannot establish unclipped raw-score parity. FEWS has passed load/identity checks only. T1, FEWS replay, October compatibility and T3 remain open.

After the task-document baseline commit, CP1 may implement: cutoff/schema validation in `tools/refresh_h5_inputs.py`, independent source-family replacement preserving the old combined wrapper, a delivery-specific manifest validator using existing object-reference helpers, and same-area past-only base-series fill with audit. Focused tests must cover all four source choices, malformed/ambiguous dates and keys, Forecast exclusion, missing previous calendar month, future/cross-area fill prevention, and invalid manifest identities. Existing converter symbols have LOW upstream impact as recorded in `PROGRESS.md`; affected callers are the refresh/audit/focus-check tools. No affected remote adapter or scoring pipeline is approved by this checkpoint.

Keep the frozen scoring environment unchanged. For CP1 pure contract/conversion tests the existing system Python/pytest may be used with an explicit dependency record; this does not qualify as model-runtime acceptance. If an isolated pinned test environment becomes necessary, create it under `/tmp` or the repository with exact numerical pins; do not modify the existing venv. Defer rasterio selection until raster work; verify NumPy ABI compatibility rather than preselecting 1.3.9. Report CP1 diff, runnable tests and unresolved issues, then wait for review. No commits by executor without supervisor coordination.

### CP1 disposition and user scope update — 2026-10-07

CP1 accepted after corrections. Supervisor independently ran 137 focused new/existing manifest, fill, converter, run-state and release tests: all passed (3.65s). Executor's expanded regression: 375 passed, one live-GCP skip, one pre-existing horizon assertion failure reproduced from baseline `1fa71a3`. The four review findings and real raw converter parity are recorded in `research/cp1-supervisor-review.md`. AST comparison confirms only three existing converter functions changed; HIGH GitNexus detect_changes also includes line-shift-identical functions and unrelated dirty documentation, which remain excluded from commit.

The user explicitly stopped historical provenance investigation and directed reuse of fixed features and current repository scripts for remote construction. Design/plan v0.5 supersedes earlier T1 gates and research stop recommendations. No further canonical writer/FID crosswalk archaeology. Use explicit current native IDs, selected current-script reducers/grid/scaling and local fixtures; do not claim historical equivalence. Model loading/replay and actual input correctness remain required.

After CP1 commit, proceed to CP2 current-script remote preparation for all four source families and both rosters. Read the updated documents, inspect existing helpers, run required upstream impact, then implement the smallest composition/adapters and focused tests. Report HIGH/CRITICAL impact before editing affected existing symbols. Preserve completed-month eligibility, failure-vs-lag distinction, immutable source coverage, explicit operator preparation and current fixed assets. No cloud mutations/live production execution. Report checkpoint and wait before CP3.

### CP2 disposition — 2026-10-08 UTC

CP2 accepted after the five corrections detailed in `research/cp2-supervisor-review.md`; supervisor final 39-test run passed. Existing Batch launcher change is a default-preserving worker module field; upstream impact LOW, diff detection MEDIUM. Broader regression retains the known baseline horizon failure and dependency deprecation warnings. This is current-script/local/mock acceptance, not live cloud acceptance.

After the CP2 commit, the executor may proceed with CP3 pure scoring/assembly, country outputs, optional diagnostics and portable bundle, and perform the authorized task-scoped cloud setup/smoke debugging needed to make CP2 executable. Project is verified `manuel-remote-sensing`; required APIs have been enabled successfully by the supervisor. Read `research/cp3-reuse-pointers.md` and `research/cp4-platform-references.md`. Use a bounded cloud smoke run before full extraction, record actual resource/image/job IDs and source coverage, and preserve existing unrelated resources/accepted consumer pointers. No training or extra Trellis audit. Report failures and corrections through Herdr; ordinary setup issues are within authority, CRITICAL unresolved issues return to user. Supervisor still reviews each checkpoint before claiming acceptance.

### CP3 interim evidence — 2026-10-08

Frozen April FEWS 0/6/12 replay accepted with exact scores/decisions/keys in the pinned environment; only source-input path metadata differs. See `research/cp3-supervisor-review.md` and its persisted evidence. October assembly, exports, portable bundle and cloud execution remain pending. Successful discovery of GOSIF latest 2024-12 is permitted lag, but preparation must not confuse later filled baseline rows with actual new provider observations. Executor is correcting this integration before the bounded live smoke. No further historical provenance investigation.

Supervisor authorized full remote dependency-window refresh after the executor observed all-area April 2026 EVI/nightlight zeros in both September panels. EVI/FLDAS/VIIRS refresh from 2025-10 through each actual latest completed product; add explicit pinned per-family `refresh_from` request/plan semantics. GOSIF uses actual latest 2024-12 with staleness. Preserve original panels and steady historical zeros outside the refreshed window; no zero-removal heuristic or historical investigation. All-source bounded smoke and resource checks precede full-window execution. Cloud authority covers this task-scoped refresh. The 09:00 ET checkpoint reports actual progress, not presumed completion.

### Final delivery disposition — 2026-10-08

CP3 scoring/bundle and CP4 automatic final entry accepted after direct supervisor verification of run `oct-delivery-qlb42`, immutable succeeded status, staging pointer and actual relocated replay. Final output `deliveries/oct-final-20261008a/` reproduces all 30 tables and diagnostic availability exactly; full remote preparation is `full-window-20261008c`. Duplicate/failure/conflict staging checks retain the original release. Product code and final image match; Windows Git is used for closeout. See `research/cp4-supervisor-review.md` for exact evidence and limitations. No additional task audit, training, source archaeology, push or consumer cutover.
