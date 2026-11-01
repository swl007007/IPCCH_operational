# Execution plan: one real increment with ACLED refresh

Status: **Approved by the user's goal execution protocol and cloud preauthorization.**

## P0 — Converge

- [x] Create a separate planning task and write the specification.
- [x] Inspect DA1/DA2, keep semantics, UTC freeze and receipt boundaries.
- [x] Preserve the prior successful runtime-account asset-access recheck.
- [x] Confirm the user's correction: retain the original DA1/DA2 names and scope.
- [x] Record D2: naturally unobserved DA2 cases may remain pending after DA1 passes.
- [x] Record D3: ACLED refresh plus ten keep choices; copy the user export intact.
- [x] Inventory the file and run guarded provisional parse validation; no upload.
- [x] Record D4: use only 2026-10-17..23; preserve/exclude overlapping old-week rows.
- [x] Consolidate the PRD and verify D1-D4/context consistency.
- [x] Present final summary; user supplies Supervisor-Executor goal and cloud preauthorization.
- [x] Read-only Trellis audit status: enrolled, controller running, no active run
  for this repository. Recorded registration is historical, not a live identity.
- [x] Verify/bind the actual live Opus 5.5 1M executor via Herdr (w1A:p8,
  session 6a490ae1-ee00-43f9-bdfc-c887c9816c09). The NEW user
  protocol explicitly forbids Trellis Audit for this task, superseding wrappers;
  use native task.py start/archive and do not mutate the controller's old state.
- [ ] Commit the approved plan through the native workflow, preserve
  unrelated changes, then enter execution and maintain the progress ledger.

## P1 — Execution preflight (read-only)

- [ ] Verify config/initialized state, job/Workflow/image, envelope/package/roster,
  active holds and active executions; capture fresh current/release/member refs.
- [ ] Inventory retained state and source coverage; ensure kept histories exist.
- [ ] Calculate actual M/O and nonempty unsaved demand with existing planning
  helpers. Record exact expected families/jobs and bounded resource/cost scope.
- [ ] Stop if there is no increment; do not delete history or fabricate a month.
- [ ] Recheck required runtime access as needed. The prior access probe does not
  prove feisty destination creation or live export/readback.
- [x] Prepare a separately pinned CSV limited to the approved complete-week
  interval; preserve the raw copy, excluded-overlap evidence and selected regions.
- [x] Prepare ACLED-refresh/ten-keep selections and run the existing local submit preview;
  a preview is structural validation, not source-readiness evidence.

Existing operator command, without --execute for preview:

    cd cloud_pipeline
    /home/swl007007/.venvs/ipcch-cloud-operator/bin/python pipeline.py submit \
      --config /home/swl007007/ipcch-operator/food-crisis-test/project.json \
      --selections /home/swl007007/ipcch-operator/food-crisis-test/v2-inputs/incremental-20261101/prepared/selections.json

Selections schema: ipcch-v2-selections-v1; mode: real; operations:
ipcch_generation and ipcch_inference; publication: current; exactly the PRD's
11 choices: acled action=refresh with file/start/end/regions; the other ten each
containing only action=keep. Never submit the unfiltered overlapping raw export.
Prepared input and selections hashes are pinned in research/acled-input/prepared-input.json.
Rehash both before execute; preview has not frozen M or any cloud reference.

## P2 — One bounded submission

- [ ] Record concrete command/API effects and live limits. Last accepted monthly
  limits were 8 CPU / 32 GiB / 14400 s / 0 task retries; verify without expanding.
  Approved execution-scope operations do not require repeated per-call consent.
- [ ] Add --execute once; persist frozen choices/M/O, run ID, request refs,
  reservation, deadline and cloud execution identity.
- [ ] Observe durable status within the budget; preserve EE request/operation/task
  IDs, destinations, completed siblings, failures and cleanup state.
- [ ] For response loss, inspect durable state before same-ID submission resume.
  Do not create another monthly run automatically.
- [ ] On failure stop the attempt, inventory partial changes, reconcile current
  and report. Do not silently deploy a fix or submit a fresh retry.

## P3 — Acceptance

- [ ] Save final execution/status/logs and post-run inventories.
- [ ] Reuse parameterized generic readback for actual M/O, 527 features, 6,226
  areas and all three targets; verify predecessor and full FEWS-member equality.
- [ ] Cross-check nonempty production and the complete consumed-ID/version/batch/
  publication chain. Generic passed=true does not prove incremental acceptance.
- [ ] Verify actual PATCH32 IDs/rows, VI units, completeness and observed null/
  omitted shapes; retain unexercised cases as incomplete.
- [ ] Verify the ACLED interval refresh and outside-interval preservation, then
  the ten kept histories' content/version equality; report each automatic
  source's update/reuse, availability and warnings separately.
- [ ] Update DA1 and DA2 dispositions separately and only from evidence; apply
  the user-approved D2 boundary to any naturally unobserved field case.

Local checks/readbacks use
.trellis/tasks/archive/2026-10/10-30-ipcch-real-e2e-integration/research/cp2/guarded.sh,
with explicit PYTHONPATH=cloud_pipeline and
GOOGLE_CLOUD_PROJECT=feisty-flames-511718-d4 when needed. Preserve 4 GiB cgroup /
3 GiB address-space / no swap / 600 s limits and require CHILD-EXIT evidence.
No full test rerun is needed for this documentation-only planning change.

## P4 — Outcome

- [ ] Report run/current refs, source actions, DA1/DA2 results, limitations
  and any separate recovery decision. Update operational claims only from proof.
- [ ] Finish the applicable lifecycle only when the agreed outcome is fulfilled;
  D2 permits naturally unobserved DA2 cases to remain explicitly pending after
  successful DA1/publication. Failed checks cannot be relabeled successful.
