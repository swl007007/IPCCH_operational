# IPCCH real E2E integration — execution plan

Status: D1-D5 approved by the subsequent user `/goal` protocol. Implementation and cloud
execution have not started at this checkpoint. This single task keeps the shared runtime/dispatch and
current-publication changes together; deferred incremental evidence is not a child
implementation task or a reason to leave this task unfinished after its agreed checks.

## 1. Converge planning and establish lifecycle

- [x] Record D1: publish to production current; GCS bucket readback is the endpoint,
  with no web/dashboard acceptance required (user decision, 2026-10-30).
- [x] Record D2: all monthly EE production/export/wait/consumption is automatic;
  manual work is limited to keep/refresh and associated assets (2026-10-30).
- [x] Record D3: submission of monthly choices/assets immediately triggers the
  complete event-driven run; no separate start or timer (2026-10-30).
- [x] Record D4: preserve original history/envelope; defer live incremental acceptance
  until a natural eligible month in November or later, outside this round's gates.
- [x] Resolve T3 locally: the original accepted handoff cannot be partially seeded;
  an isolated root alone does not trigger new climate work. Full real roster=6,226.
- [x] Separate current AC1-AC9 from deferred live DA1-DA2, retaining full producer
  implementation and offline verification. Preserve existing resource/retry limits.
- [x] Record D5: routine execution month is submission-time UTC month; freeze M/O/
  targets across queue delays and redelivery. Complete the PRD convergence pass.
  Second review findings are in `research/grill-second-pass.md`.
- [x] Present the consolidated final summary and receive the subsequent explicit
  Supervisor–Executor execution instruction; preserved in `execution-protocol.md`.
- [ ] Preserve unrelated `AGENTS.md` changes. Commit the approved specification
  on the intended task branch after checking expected changes.
- [ ] Verify/bind the actual Claude Executor through Herdr and start the native
  Trellis task. Follow the latest no-Audit instruction in `execution-protocol.md`;
  do not call any audit lifecycle command.

## 2. Repair local integration

- [ ] Load project development contracts and inspect exact code before edits.
  Run GitNexus impact for each edited symbol; report callers/processes/risk.
- [ ] Add the sparse PATCH32 regression to existing fixtures, implement the shared
  alignment fix, and verify monthly and seasonal primary/patch behavior.
- [ ] Port the two upstream producer graphs into the pinned Python EE runtime,
  preserving formulas/QA/scaling, and add the narrow table-to-Asset transport path.
  Reuse task reservation, task IDs, bounded polling/cancel, and durable receipts.
- [ ] Derive required tables/periods before submission. Automate output IDs/version,
  submit/wait/readback, and run-bound asset mapping into consumer providers. Preserve
  old baseline/history addresses; never use a manual monthly mapping file.
- [ ] Resolve one asset per family/chunk; prevent old all-null columns from shadowing
  new outputs. Preserve upstream full-chunk formula/input scope and record its vintage.
- [ ] Persist explicit producer month-completeness evidence and consume it before
  published/unavailable classification. Test incomplete all-null vs complete-but-masked
  data and later missing-month recovery; persist receipt identity beyond SourceOutcome.extra.
- [ ] Add source-equivalence and lifecycle tests; exercise failed/timed-out exports,
  duplicate events, same-day reruns, and 2027/prior-year VI support in both producers
  and consumers. Do not reconstruct static baselines or automate manual research inputs.
- [ ] Provide v2 submission for all 11 keep/refresh choices. Validate selections
  and associated assets before publishing the pinned request object, whose event
  immediately triggers the run. Asset uploads alone must not start it. Chain all
  operations through current automatically, with no timer/separate start action.
  Ensure invalid requests fail before producer mutations and valid runs hold locks.
- [ ] Derive routine M and prepared_at from one UTC submission instant, freeze O/
  targets in the request, and populate identity/pins automatically. Distinguish
  redelivery from a new submission; test local-vs-UTC disagreement and cross-month
  delayed starts/redeliveries. Preserve explicit-M request compatibility, without
  adding routine month or legacy cutoff/deadline prompts.
- [ ] Reuse existing run reservation patterns for v2 admission/replay protection;
  test direct-entry and event duplicate paths, not merely the existing Workflow guard.
- [ ] Persist and thread the configured whole-run deadline to producer/transport/
  acquirer calls, including cancellation reserve; test deadline expiry and no reset
  on redelivery. Existing deadline code is not currently wired through v2 context.
- [ ] Install the accepted model/envelope/handoff and deployment config through
  the supported build/deployment path. Wire Workflow's overridden arguments to
  `--v2-config`; update the operator v2 submission surface only as necessary.
- [ ] Verify real/smoke configuration separation and existing legacy compatibility.

Expected affected files and existing tests:

| Responsibility | Code/config | Validation |
|---|---|---|
| Patch and asset references | `cloud_pipeline/cloud/ipcch/climate_tables.py` | `test_ipcch_climate_tables.py` |
| Provider/producer ordering | `cloud_pipeline/cloud/ipcch/climate_run.py`, `entrypoint_v2.py`, `generation.py` as needed | `test_ipcch_climate_run.py`, `test_ipcch_entrypoint_v2.py`, generation tests |
| Asset export lifecycle | `cloud_pipeline/cloud/ipcch/ee_transport.py` and a narrow producer module | `test_ipcch_ee_transport.py`, producer equivalence/lifecycle checks |
| Cloud dispatch/install | `cloud_pipeline/deploy/workflow.yaml`, `Dockerfile`, `build_context.sh`, concrete deployment config | `test_workflow_dispatch.py`, delivery tests, image installation/binding checks |
| Operator v2 request/trigger/status | `cloud_pipeline/pipeline.py`, existing request helpers, deployment setup | Existing request/admission/operator/deploy tests; submit-to-trigger and invalid-input no-trigger checks |
| Runtime contracts | Existing binding/generation/assembly/run/publication modules; modify only if needed | Existing binding, generation, assembly, run, publication tests |
| Producer calculation graphs | Owned Python implementation of the two upstream JS scripts, with source hashes | Source/formula equivalence and controlled-response integration now; actual new exports/readback deferred DA1-DA2 |

Cloud tests are under `cloud_pipeline/tests/cloud/`; operator/deploy tests are
under `cloud_pipeline/tests/`.
Use the validated environment initially:
`/home/swl007007/.venvs/fewsnet-test-lock-20261022/bin/python`.
Example focused check from `cloud_pipeline/`, after changes:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/swl007007/.venvs/fewsnet-test-lock-20261022/bin/python -m pytest -q -p no:cacheprovider tests/cloud/test_ipcch_climate_tables.py tests/cloud/test_ipcch_climate_run.py tests/cloud/test_ipcch_entrypoint_v2.py tests/cloud/test_workflow_dispatch.py
```

Run the related integration suites once the wiring is complete. Earlier 82-test
offline success predates these changes and did not cover the real sparse patch.
Passing offline tests is not real E2E acceptance.

## 3. Prepare and execute bounded cloud operations

- [ ] Present concrete deployment/run commands, identities, resources, read/write
  scope, expected effects, retry/time/cost limits, and existing state to retain.
  Retain the existing 4-hour job cap and zero automatic task retries, bounded by
  the run deadline and 15-minute EE cleanup reserve. This round does not authorize
  a forced incremental export workload. No manual interstage gate is added to the
  runtime; future approved incremental runs include their declared EE child jobs.
- [ ] Refresh job/Workflow/Eventarc/config and IAM/EE/GCS access evidence as needed.
- [ ] Verify references/access needed by this round's real run; do not substitute
  user-identity access for runtime-identity evidence. Live new-asset production and
  incremental readback are deferred, not required prerequisite jobs this round.
- [ ] Upload/install pinned artifacts and configure the immutable runtime image.
- [ ] Initialize only the approved retained roots; validate ACLED origin coverage.
- [ ] Deploy the reviewed job/Workflow config, then read it back against the plan.
- [ ] Verify v2 and legacy resolve the exact same production current URI; preserve
  its FEWS member and activation guards. Treat corrupt existing members as failures.
  Check real/smoke roots are nonnested; do not place smoke beneath a real bucket root.
- [ ] Run the full 6,226-area real route using the original accepted history/binding,
  from choice submission through generation, inference and current. Use October's
  execution month if live publication admission still permits it. Record exact
  retained versions, any actual source work, and expected climate skips. Do not
  falsify dates, alter history or add an acquisition bypass to force a pass.
- [ ] Publish through the existing checked production current flow, then read back
  its pointer and referenced delivery/prediction objects from GCS. Verify exact
  generations, run/model identity, target months, and content checks. Candidate-only
  or mere object-listing evidence does not satisfy the accepted D1 endpoint.

## 4. Verify, report, and close

- [ ] Collect only necessary evidence: pinned code/image/config/model/asset IDs,
  actual request and execution records, source/retained receipts, feature schema,
  coverage/output checks, and publication readback. Avoid redundant data archives.
- [ ] Evaluate AC1-AC9 explicitly; distinguish pass, fail, and incomplete. Record
  DA1-DA2 as user-deferred, never passed. Preserve error/warning evidence and any
  partially successful retained updates. Do not wait for November or run incremental
  acceptance as a task-close requirement.
- [ ] Record reproducible operator instructions and scoped rollback commands.
- [ ] Run relevant final checks and GitNexus `detect_changes()` before committing.
- [ ] Supervisor commits relevant implementation/evidence without unrelated changes,
  performs final acceptance against AC1-AC9, then closes through native Trellis.
  Do not invoke Trellis Audit or an independent automatic audit stage.

## Deferred follow-up, not work to execute this round

At a later separately initiated eligible-month submission, verify DA1-DA2 from
real EE production through retained append, feature consumption and current. Keep
the accepted initialization package and model binding; no new checkpoint is planned.
The final report must state that new-month incremental behavior has offline evidence
only until this future live acceptance is performed.

## Current limitations

The task has not started. No product/configuration edits, deployment, exports,
retained initialization, or real E2E run have occurred in this planning step.
The `specs/001-cloud-base-input/plan.md` pointer in AGENTS was not found in this
checkout; use the existing v2 archive/contracts and report this stale pointer
without inventing a replacement foundational plan.
