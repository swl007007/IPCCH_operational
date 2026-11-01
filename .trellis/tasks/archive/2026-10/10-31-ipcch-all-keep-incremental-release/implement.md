# Execution plan: real increment and approved D5 recovery

Status: **Approved by the user's goal execution protocol and cloud preauthorization.**

P0-P2 record the first attempt, which failed before export and was reconciled.
D5 recovery below is now approved; historical one-attempt instructions do not
cancel this explicit extension. Preserve CP0-CP2 frozen files.

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
- [x] Commit the approved plan through the native workflow (17fe954), preserve
  unrelated changes, then enter execution and maintain the progress ledger.

## P1 — Execution preflight (read-only)

- [x] Verify config/initialized state, job/Workflow/image, envelope/package/roster,
  active holds and active executions; capture fresh current/release/member refs.
- [x] Inventory retained state and source coverage; ensure kept histories exist.
- [x] Calculate actual M/O and nonempty unsaved demand with existing planning
  helpers. Record exact expected families/jobs and bounded resource/cost scope.
- [x] Stop if there is no increment; do not delete history or fabricate a month.
- [x] Recheck required runtime access as needed. The prior access probe does not
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

- [x] Record concrete command/API effects and live limits. Last accepted monthly
  limits were 8 CPU / 32 GiB / 14400 s / 0 task retries; verify without expanding.
  Approved execution-scope operations do not require repeated per-call consent.
- [x] Add --execute once; persist frozen choices/M/O, run ID, request refs,
  reservation, deadline and cloud execution identity.
- [x] Observe durable status within the budget; preserve EE request/operation/task
  IDs, destinations, completed siblings, failures and cleanup state.
- [x] For response loss, inspect durable state before same-ID submission resume.
  Do not create another monthly run automatically.
- [x] On failure stop the attempt, inventory partial changes, reconcile current
  and report. Do not silently deploy a fix or submit a fresh retry.

## D5 / CP3 — Root initialization and runtime verification

- [x] Record user approval: "批准上述恢复与一次重跑"; keep the same task/executor.
- [x] Commit updated approved spec and plan before recovery execution (06c38da).
- [x] Prepare the bounded diagnostic payload and one small guarded offline check
  for listing-success, HTTP-404/create, already-exists reconciliation and other
  error/timeout stop branches. No creation on permission errors; no overwrite.
- [x] Supervisor inspect payload/resource/identity packet. This is a technical
  check under existing approval, not another user cloud-permission gate.
- [x] Create/execute ipcch-ee-root-check-20261101 on acc3e467, monthly-runtime,
  1 CPU/512 MiB/300 s/one task/zero retries. Read root; at most one creation on
  HTTP 404; verify root listing and absent-child semantics via pinned transport.
  If job already exists, inspect/reconcile instead of overwriting or duplicating.
- [x] Save logs/execution/results and accept only actual runtime-identity proof.
  No further mutation or monthly request if the diagnostic fails.

## D5 / CP4 — Exactly one additional all-keep monthly attempt

- [x] Prepare a separate all-eleven-keep selection; preserve the first selection.
- [x] Revalidate config/image/current/no hold/no active work, retained state and
  nonempty unsaved climate demand. ACLED v2 and acceptance v4 are the expected
  prior partial progress; any other change needs reconciliation.
- [x] Guarded preview and submit once, using actual UTC freeze and unchanged
  8 CPU/32 GiB/14400 s/zero-retry limits. Save new frozen request and reservation.
- [x] Monitor durable execution and export handles; no automatic third attempt.
  The second attempt returned succeeded at the 03:30:37Z poll; CP5 readback pending.
- [x] On failure reconcile current and partial writes under the existing rules.
  Not triggered for the D5 attempt (terminal succeeded); first-attempt reconciliation
  remains preserved in CP2.

## P3 / CP5 — Acceptance of the successful recovery run

- [x] Save recovery-run final execution/status/logs and post-run inventories.
- [x] Reuse parameterized generic readback for actual M/O, 527 features, 6,226
  areas and all three targets; verify predecessor and full FEWS-member equality.
- [x] Cross-check nonempty production and the complete consumed-ID/version/batch/
  publication chain. Generic passed=true does not prove incremental acceptance.
- [x] Verify actual PATCH32 IDs/rows, VI units, completeness and observed null/
  omitted shapes; retain unexercised cases as incomplete.
- [x] Verify the ACLED interval refresh and outside-interval preservation, then
  the ten kept histories' content/version equality; report each automatic
  source's update/reuse, availability and warnings separately.
  The first refresh evidence is already accepted. For the D5 run, require all
  eleven kept histories, including ACLED v2, to equal its fresh pre-snapshot.
- [x] Update DA1 and DA2 dispositions separately and only from evidence; apply
  the user-approved D2 boundary to any naturally unobserved field case.

Local checks/readbacks use
.trellis/tasks/archive/2026-10/10-30-ipcch-real-e2e-integration/research/cp2/guarded.sh,
with explicit PYTHONPATH=cloud_pipeline and
GOOGLE_CLOUD_PROJECT=feisty-flames-511718-d4 when needed. Preserve 4 GiB cgroup /
3 GiB address-space / no swap / 600 s limits and require CHILD-EXIT evidence.
No full test rerun is needed for this documentation-only planning change.

## P4 — Outcome

- [x] Report run/current refs, source actions, DA1/DA2 results, limitations
  and any separate recovery decision. Update operational claims only from proof.
- [x] Finish the applicable lifecycle only when the agreed outcome is fulfilled;
  D2 permits naturally unobserved DA2 cases to remain explicitly pending after
  successful DA1/publication. Failed checks cannot be relabeled successful.
  Native task.py archive completed with CHILD-EXIT 0 after acceptance commit
  e9b5f87; no Audit. Archived in local month 2026-10 (UTC evidence 2026-11-01).
