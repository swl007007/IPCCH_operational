# Implementation plan

Status: execution authorized on 2026-10-22; initialization in progress. `prd.md` is the requirement authority; `design.md` resolves the integration details. Use the user's Supervisor–Executor protocol recorded in `research/execution-authority.md`; no Trellis Audit or independent audit workflow.

## 0. Establish the approved execution context

- [ ] Reconcile Git and the approved plan; preserve the unrelated pre-existing tracked changes. Use a proper implementation branch/base pair rather than repeating `branch == base_branch`.
- [ ] Read applicable development specs and run impact analysis before changing symbols. The existing GitNexus index was stale during discovery; disclose limitations and verify callers in current source as needed.
- [ ] Commit the approved task documents, bind the actual verified Herdr Claude executor, and activate the existing task with native Trellis under the user's explicit no-audit override. Verify executor/session, branch/base SHA and task status; do not invoke audit registration, start, close or independent audit.
- [x] Record execution progress in the existing repository `PROGRESS.md` without overwriting unrelated entries. Keep a compact task evidence record. (P1a: `research/p1/p1a-checkpoint.md`.)
- [ ] Verify the local operational runtime/lock and source confidence hashes. Resolve the accepted same-origin IPCCH source delivery manifest/archive, required inherited members and rollback refs before release work. (P1a: runtime/lock (certifi exception) and six confidence hashes verified; IPCCH inherited source/rollback refs pending.)

## 1. Assemble and freeze the data refresh (R1-R3, AC1)

- [ ] Inventory local operational history, research staging raw candidates, fixed roster/geometry/map/schema and pinned GCS remote sources. GCS read-only work within this task is already authorized for this conversation.
- [x] Check HDX-registered FEWS CS resources for all 22 countries and download their actual latest content, recording resource IDs/URLs, retrieval times and raw hashes. Freeze the fetched versions; keep assessment months no later than October 2026. Do not rely on stale HDX catalog coverage dates. (Freeze `hdx-cs-20261022T043937Z`, supervisor-verified; content to 2026-06.)
- [ ] Build the unambiguous production-code crosswalk and added-label ledger. Preserve nulls and disclose partial gaps/conflicts by country/month; stop before fitting if there are no credible added labels. Present revisions to complete old labels separately. (P1a: strict crosswalk candidates 4,039 for 2026-06 + gap/imputed-fill findings; awaiting supervisor acceptance.)
- [ ] Assemble WFP from raw HDX files and ACLED from the event-level API using existing FEWS definitions. Record available complete months; do not substitute IPCCH processed features.
- [ ] Resolve actual remote provider availability through September at most. Reuse compatible FEWS cloud extracts, obtain approved EE/extraction operations where needed, and extract 2025 GOSIF v3 for FEWS while preserving historical v2.
- [ ] Append/fill gaps under the frozen definitions and causal rules. Present proposed revisions to complete history separately. Freeze source hashes, cutoff evidence, keyed changes, coverage and exclusions.
- [ ] Complete and pin the intended inference remote snapshot before release invocation. Verify its vintage/refresh metadata and source provenance preserve the planned added months, including GOSIF 2025, through the existing overlay. Skipping release-time preparation does not skip this data-building work.
- [ ] Preserve the IPCCH panel/assets/preparation metadata and regenerate combined retained WFP/ACLED snapshots for `keep` from the new FEWS plus unchanged IPCCH panels.

## 2. Adapt and run local full-data fitting (R4, AC2-AC3)

- [ ] Add the explicit full-data path to the existing runner, reusing horizon alignment, imputer, RF/SMOTE and routing primitives. Remove rolling-window and hardcoded April/February assumptions from this path. Supply fixed thresholds.
- [ ] Extend training reports, validators, package schemas, writer/loader and callers to truthfully express no evaluation while preserving old-package support.
- [ ] Run focused software checks of alignment, exclusions, fit-key accounting, fixed-threshold routing and package compatibility; do not add model evaluation or synthetic fitting experiments.
- [ ] Fit horizons 0/6/12 locally on all eligible labeled history in the locked environment. Save new packages and input/fit/runtime/threshold provenance. Confirm exact feature/map identities and package loading.

## 3. Integrate frozen confidence and cloud manifest dispatch (R5-R7, AC4-AC9)

- [ ] Add the frozen-output diagnostic declaration/loader and preserve old source evidence identity separately from new scored package identity. Copy all historical confidence fields and availability disclosures; update only current prediction outcomes.
- [ ] Update online delivery and portable bundle paths together, including consumers of validation-period metadata. Retain existing five-table headers and keyed coverage.
- [ ] Add manifest step selection to the initial workflow intent: remote update on/off and selected inference systems. Keep legacy stage defaults, existing preparation semantics and the singular completed-snapshot shape. Separate immutable initial intent from its bound resolved delivery request.
- [ ] Extend the existing cloud Workflow to read the exact manifest generation, dispatch selected jobs and wait for durable preparation success/compatible snapshot after Batch completes. Local submission must not own this progression. Handle prepare-only, skips, terminal failure, bounded wait and duplicate events without recursive dispatch or extra steps.
- [ ] Update operator submission/status/resume and workflow setup/configuration. Prepare scoped workflow read/write/prepare-job execution permissions for approval; do not assume current IAM. Bind new choices/refs to the existing run intent.
- [ ] Run only selected system subprocesses. Carry forward a skipped system's complete scientific members from a compatible pinned accepted delivery; reject missing dependencies, mismatched origin/targets/model identities and empty selections without auto-enabling steps.
- [ ] Preserve complete finalization, 30 result tables and bundle inventory, but separate immutable candidate export from current-pointer publication. Enable downloading a pinned candidate before promotion and bind verification/promotion receipts to exact artifacts and the expected predecessor.
- [ ] Record inherited versus newly computed provenance. Adapt offline replay/diagnostic checks so this release does not invoke IPCCH inference or recalculate retained diagnostics.
- [ ] Run focused checks in the existing workflow/delivery/operator suites: cloud stage selection, prepare-job versus Batch readiness, duplicate events, skipped steps, inherited members, identity/date failures, frozen fields/null masks, FEWS replay parity, failed checks preventing promotion and interrupted/competing activation. These are software integrity checks, not model tests against labels.

## 4. Prepare and execute the candidate (R6-R7, AC6-AC9)

- [ ] Assemble the candidate baseline, three new FEWS packages, three unchanged IPCCH packages, frozen confidence sources, pinned assets and separate operator state. Preserve rollback references.
- [ ] Record each cloud operation's exact command/API, project, purpose, read/write scope and effects. Necessary task-scoped operations are preapproved until 2026-10-22T13:00:00Z; check the clock before consequential actions. After expiry, return to individual approval for non-GCS operations; conversation-scoped GCS reads remain authorized. Do independently authorized local preparation first.
- [ ] Build/publish the new runtime digest and record fresh loading/runtime/package-identity evidence for all six slots. Do not reuse old-image acceptance as proof for the new image.
- [ ] Before changing shared job/workflow settings, record their predecessor identities, establish the candidate-bound hold on other monthly computations, and reconcile already-running work. Keep accepted outputs readable; prepare recovery/reopen steps without adding a temporary candidate job.
- [ ] Publish/select packages in candidate state. Submit the October cloud workflow manifest with remote update off, FEWS inference on and IPCCH inference off, using the completed snapshot and inherited October IPCCH source. Record actual dispatch, consumed packages, image and immutable refs; do not change active release/defaults/fallback on candidate completion.

## 5. Verify candidate, then promote and reconcile (AC4-AC9)

- [ ] Verify 5,718 unique FEWS areas/22 countries per horizon and exact target months. Check current prediction identity and country outcome consistency.
- [ ] Compare frozen historical confidence fields/blanks by key to the six source files and inventory. Retain original proxy provenance; do not derive new confidence from counts.
- [ ] Verify inherited IPCCH result/input/model/diagnostic members match the same-origin source and retain its computation provenance. Confirm selected FEWS portable replay matches cloud exports without a labeled evaluation; verify IPCCH is not scored by this replay.
- [ ] Download/verify the exact candidate and stage its fallback separately. Save the bound successful integrity/replay receipt; on any failure retain the old active version. Preserve the current accepted confidence-bearing predecessor and its runtime/configuration, not only the older smoke archive.
- [ ] Prepare the concrete promotion/rollback operation from the checked candidate and predecessor refs. After the required operation approval, CAS-promote the cloud release, activate the actual normal operator config/state/image and new default FEWS weights, and activate the staged fallback. Record partial steps for safe recovery; do not overwrite a concurrent newer release.
- [ ] Reconcile cloud current release, normal-operation default package/image identities and active fallback. Reopen monthly computation only after successful activation, or after verifying full restoration on failure. Only then report the corresponding outcome. Update fallback README/inventory/reports and retain rollback instructions.
- [ ] Commit relevant implementation/evidence after required scope checks; complete Supervisor verification against every acceptance criterion and then the native Trellis lifecycle. Do not start Trellis Audit or an independent audit workflow. Keep unresolved findings explicit.

## Evidence to retain

Keep raw HDX/source references, compact data-change/coverage records, per-horizon fitting keys/counts and package hashes, frozen-confidence checks, initial/resolved workflow request identities and step status, candidate verification/promotion receipts, active runtime/package/fallback inventories and recovery refs. Reuse existing report formats where possible. No new benchmark archive, performance dashboard, model registry platform or unrelated cleanup is part of this task.
