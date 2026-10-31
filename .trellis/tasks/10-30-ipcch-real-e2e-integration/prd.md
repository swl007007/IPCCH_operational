# IPCCH real E2E integration and cloud configuration

Status: **D1-D5 approved for execution under the user-provided Supervisor–Executor protocol**.
Outcome (2026-10-31): **AC1-AC9 accepted**. Real run
`ipcch-real-522b30030f944868` published to the existing production current;
27 guarded readback checks passed over 6,226 areas per horizon and 527 features.
Normal operator configuration is finalized. See `research/cp6/final-report.md`,
`research/cp6/evidence-matrix.md` and `research/cp4/supervisor-gates.md`.
DA1-DA2 remain user-deferred; runtime han sharing is a future prerequisite.

Created 2026-10-30 at source HEAD `69aa74a372f40581d6759a5703e7ec331ba4af63`.
The user authorized creating this task, integration planning, configuration changes,
and real E2E acceptance, with brainstorm -> written spec -> grilling first.
D1-D5 below are accepted. The second grilling pass's technical corrections are
included in this specification. The user's subsequent `/goal` execution protocol
authorizes implementation; see `execution-protocol.md`. No deployment or cloud run
has occurred at this authorization checkpoint.

## Goal

Complete the automatic monthly IPCCH E2E route: keep/refresh choices and associated
operator-managed assets -> validated request -> automatic upstream EE production,
export submission/wait/readback -> retained updates -> 527-feature assembly ->
accepted H2/H8/H14 inference -> production `current` publication in GCS. Routine
manual work is limited to keep/refresh choices and related asset operations. No
manual EE Tasks-panel start, result-ID copying, intermediate job launch, or final
publication action may be required. Acceptance ends at readable bucket objects and
validated contents; no web/dashboard delivery is required. This round implements
the complete automation and verifies real cloud publication using accepted retained
history. Live new-month incremental acceptance is explicitly deferred by D4; a
cached or fixture-only replay must never be reported as proof of real acquisition.

## Confirmed background

- The prior implementation is archived at
  `.trellis/tasks/archive/2026-10/10-29-ipcch-validity-feature-inference/`.
  Its accepted contracts remain the starting point; this task integrates them.
- The operational combination is `ipcch-validity-h2h8h14-final-20261030`, with
  527 features and 6,226 roster areas. H2/H8/H14 are installed under
  `scope_0m`/`scope_6m`/`scope_12m`. With `O=M-2`, targets `O+H` are M/M+6/M+12.
  The later H0/H6/H12 origin-ablation research does not replace this combination.
- Upstream scripts are in the sibling `IPCCH_shared_folder/seasonal/` directory:
  `01_vi_prcp_et0_update.js` produces six tables and
  `02_et0_patch32_update.js` produces one. They still require an output project,
  explicit export submission, and a common version suffix.
- PATCH32 is legitimately sparse: 32 selected polygons, buffered by 30 km.
  `_wide_month_matrix` currently requires every roster row in every input,
  including PATCH32 (`cloud_pipeline/cloud/ipcch/climate_tables.py:188`,
  monthly call at `:241`, seasonal call at `:367`). An in-memory sparse fixture
  reproduced failures in monthly and seasonal SPI/SPEI; the existing full-roster
  fixture hid this mismatch (`cloud_pipeline/tests/cloud/test_ipcch_climate_tables.py:87`).
- `TableRefs` uses shared templates/root (`climate_tables.py:46`);
  `climate_run.real_providers` applies its root to both static and dynamic assets
  (`cloud_pipeline/cloud/ipcch/climate_run.py:81`). Seven new exports cannot replace
  the complete historical/static asset dependency set.
- The real provider entrypoint does not pass an asset mapping
  (`cloud_pipeline/cloud/ipcch/entrypoint_v2.py:78`). Workflow argument overrides
  omit `--v2-config` (`cloud_pipeline/deploy/workflow.yaml:280`), which the v2
  dispatcher requires (`cloud_pipeline/cloud/orchestrator/delivery_job.py:1041`).
  The image does not install the deployment JSON, accepted package, envelope, or
  handoff bundle (`cloud_pipeline/deploy/Dockerfile:5`).
- Local operator configuration names project `feisty-flames-511718-d4`, region
  `us-central1`, data bucket `food-crisis-test-ipcch-data`, requests bucket
  `food-crisis-test-ipcch-requests`, and namespace `monthly-staging`.
  The latest located cloud readback is 2026-10-22; current deployment is unverified.
- The accepted handoff has monthly climate history through 2026-08. Prior local
  inference over all 6,226 areas recorded `climate_provider_calls=[]`.
  On 2026-10-30, M=2026-10 uses O=2026-08 and can therefore bypass acquisition.
- Earlier read probes established user-identity readability of one admin asset
  and one baseline, not public ACLs or runtime service-account access.
- Existing activation is an Eventarc object-finalized trigger, not a monthly clock
  (`cloud_pipeline/deploy/workflow.yaml:1`, `:52`; `deploy/setup.py:167`). The
  operator still builds v1 requests (`cloud_pipeline/pipeline.py:684`, `:805`).
  A v2 request builder and full Workflow wiring are required. Accepted D3 reuses
  this event route immediately after the operator submits that month's choices.
- The existing Python EE transport has reservation, task start, bounded polling,
  cancellation and durable receipts, but only table-to-GCS export
  (`cloud_pipeline/cloud/ipcch/ee_transport.py:148-253`). The upstream scripts use
  Code Editor globals and hard-code 2026; the runtime has Python EE API 1.7.36,
  without Node or the sibling JS scripts. See `research/automation-evidence.md`.
- All real inference must cover the bound 6,226 areas; a reduced real acceptance
  roster is not permitted (`cloud_pipeline/cloud/ipcch/batch.py:72-106`). Source
  probes may be small, but they do not replace the full final run.

## Requirements

| ID | Required behavior | Acceptance |
|---|---|---|
| R1 | Accept sparse PATCH32 by aligning its rows to the requested admin axis, leaving absent patch rows missing; fill only missing primary ET0 values. Keep primary PRCP/ET0 coverage and existing numeric/duplicate validation strict. Apply consistently to monthly and seasonal SPI/SPEI. | AC1 |
| R2 | Automatically produce and resolve the seven current table families to run-bound versioned IDs under `projects/feisty-flames-511718-d4/assets/`, with no manual monthly address replacement. Preserve static baselines, historical chunks, and required prior-year VI. Derive years/chunks from eligible periods instead of freezing the system at 2026. Validate fields, units, completeness, and PATCH32 IDs. | AC2, AC8; DA2 live follow-up |
| R3 | Carry asset configuration through deployment JSON -> entrypoint -> provider factory -> table references. Make Workflow invocation, container configuration, installed artifacts, request pins, and store initialization agree. Reuse the v2 route and existing operator surface where practical. | AC3 |
| R4 | Bind the accepted H2/H8/H14 envelope, package manifest, handoff, roster, and feature order; preserve target-month semantics and existing acceptance checks. | AC4 |
| R5 | Demonstrate submission, retained-history feature generation, full inference and real current publication this round. Record actual acquisition versus retained reuse per source. Implement incremental acquisition fully, but defer its live new-month acceptance under D4; no false acquisition claim or forced history deletion. | AC5; DA1 live follow-up |
| R6 | Publish the verified real result to production `current` and verify its pointer and referenced output objects in GCS. Preserve the real/smoke separation, source failure behavior, temporal cutoffs, locking, immutable references, and publication checks of v2. Candidate-only completion does not satisfy this task. | AC6 |
| R7 | Supply reproducible operator commands, exact deployed image/config/artifact identifiers, bounded cloud-operation records, and rollback instructions for the production current publication. | AC7 |
| R8 | Run the upstream VI/PRCP/ET0/PATCH32 production inside the automatic monthly flow. After admission and required locks, submit eligible EE jobs, retain task IDs, wait within the run deadline, validate results, and pass their resolved IDs to consumers. Processing failure or timeout blocks dependent inference/current; do not silently substitute old assets. Preserve the accepted source-unavailability policy. | AC8; DA1-DA2 live follow-up |
| R9 | Submitting complete keep/refresh choices and associated assets immediately triggers the full flow through the request-object event. Routine M is the UTC calendar month at submission, frozen with O=M-2 and targets M/M+6/M+12 for the request. Keep only the agreed manual input channels; no separate start/publication action or timer. Automate v2 request pins, run identity, batch handoff, and publication. Preserve all 11 choices; no inference-only refresh, implicit refresh-to-keep fallback, or reuse of last month's refresh request. | AC9 |
| R10 | Bind source availability to explicit producer source/month completeness evidence for newly produced tables. A target column or nonempty asset alone does not prove publication; all-area NaN alone does not prove unavailability. Preserve source-unavailable versus legitimate spatial missingness, and persist the reason/producer receipt with any saved result. | AC2, AC8 |

## Current-round acceptance criteria

- [x] **AC1:** Focused regressions cover sparse patch rows, missing patch values,
  preserved nonmissing primary ET0, duplicate/nonnumeric failures, and incomplete
  primary tables in both monthly and seasonal routes. Existing numerical fixtures
  still agree; no fitting or feature-formula change is introduced. CP1 Supervisor
  accepted: 86 focused tests pass; seven sparse regressions fail on the old reader.
- [x] **AC2:** Source-equivalence and data-contract tests verify output root/version
  mapping, preserved old dependencies, the intended 32 PATCH32 IDs, VI scaling,
  schema/numeric validation, and both omitted and all-null incomplete-month fields.
  Prove that an incomplete month with an existing all-null column is not marked
  published/saved, while a source-calendar-complete month with masked polygons
  retains legitimate spatial missingness. New-output completeness metadata absent
  or inconsistent is a processing error, not an inferred publication. Old static/
  historical inputs retain their existing contract; do not invent missing metadata.
  Verify references/access needed by this round's real run under its runtime
  identity. Newly produced live asset IDs and export/schema measurements belong to
  DA2 when those assets are actually produced; do not invent completion evidence.
- [x] **AC3:** A pinned v2 request submitted through the deployed request route
  reaches the v2 entrypoint with the intended config and installed files. Config,
  workflow, and legacy-dispatch tests pass; existing consumers are preserved.
- [x] **AC4:** Runtime verification matches the accepted envelope and package
  digests; assembled inputs have the bound 527-feature order. Prediction coverage,
  output keys, and three target months match the accepted roster and model contracts.
  Final real coverage is all 6,226 bound areas for each horizon.
- [x] **AC5:** The real run uses the original accepted handoff/envelope, records
  exact retained input versions, and links the submitted choices to generation,
  feature batches, full-roster predictions and current publication. Explicitly
  report climate periods skipped because they are already retained, and actual
  GPP/nightlight/ACLED refresh or reuse under existing contracts. No nonempty climate
  call count is required this round; report DA1 as deferred, never passed. Use an
  admissible execution month without falsifying dates or truncating history.
- [x] **AC6:** Production `current` points to the accepted run, and the pointer plus
  its referenced delivery/prediction objects can be read back from the configured
  GCS bucket. Exact generations, run/model identity, target months, and existing
  content checks agree. Bucket readback is the user-facing endpoint; no webpage
  or dashboard acceptance is required. Failed admission/generation/validation must
  not advance current; successful retained writes before failure remain accounted for.
  Publish to the existing production pointer location rather than an unrelated
  new v2 prefix, preserving the current FEWS member byte-for-byte if present and
  the legacy IPCCH activation guard. Verify old/new pointer location equality from
  deployment config; live state/readability is checked before mutation.
- [x] **AC7:** Evidence identifies code SHA, image digest, configuration checksum,
  model/handoff pins, asset IDs, request generation, cloud execution IDs, source
  updates, warnings, output references, and publication result. Local tests, source
  availability, cloud execution, publication, and independent audit are separate claims.
- [x] **AC8:** Complete producer and integration tests exercise unsaved-month
  planning -> graph construction -> task submission/wait/readback -> resolved IDs
  -> retained append/feature consumption, using controlled EE responses offline.
  The installed runtime includes this real path; no stub or manual-only fallback
  satisfies the requirement. Test completed/failed/cancelled/timed-out jobs,
  duplicate events, same-day reruns, year rollover, and legitimate already-retained
  skips. Receipts link run, producer, period, task, asset and consumer. Live proof
  of this path is DA1-DA2, explicitly deferred rather than required this round.
  Include tests for an expired run deadline reaching providers, replay of the same
  request identity without repeated work, and exactly one chosen asset per chunk
  so old null columns cannot shadow new values through join ordering.
  Supervisor evidence: accepted CP2 guarded producer/lifecycle/integration suite
  and CP4 image `acc3e467…` built from `115798f`, with verified runtime imports.
  This accepts the offline and installed path; DA1-DA2 remain deferred.
- [x] **AC9:** The operator can express the existing 11 keep/refresh choices and
  required pinned asset references through the v2 submission surface. Submission
  creates the validated request and triggers generation -> inference -> current
  without a separate start action, timer, or further human action. Preparing an
  upload alone must not trigger an incomplete request. Invalid selections fail
  before the execution-triggering request object is published.
  Keep preserves prior accepted history; refresh follows its family's replacement
  contract. A successful refresh remains the next keep baseline after downstream
  failure. Missing initial ACLED history still requires a valid first refresh.
  Keep routine submission on the existing CLI/config surface. Fill run ID, operator,
  prepared_at, reference generation/hash and expected pointer generation automatically;
  do not require users to write raw v2 JSON or legacy cutoff/deadline flags. Derive M
  from the same UTC instant used for prepared_at at actual submission; asset upload
  time, local timezone, and job start time do not select M. Freeze M/O/targets for
  redelivery across midnight/month/year boundaries. Same request identity is a
  redelivery; a deliberate new submission gets a new ID and submission instant even
  if its choices are identical. Test UTC/local-date disagreement and cross-month
  delayed execution. Preserve existing explicit-M request validation for authorized
  exceptional reruns without adding a routine manual month requirement.

## Deferred live acceptance (not current-round completion gates)

- **DA1:** At a future eligible new month, prove real producer exports -> climate
  provider reads -> retained append -> feature consumption -> full-roster inference
  -> current. Keep the original accepted bundle/envelope. Earliest natural case is
  M=2026-11/O=2026-09 once UTC permits it and source readiness is checked. No run is
  scheduled or authorized now; the task need not wait until November to complete.
- **DA2:** During that real incremental run, record destination IDs/task completion,
  runtime access, real PATCH32 row set, VI units, and actual omitted/all-null field
  behavior from export/download. Offline correctness does not prove live API data
  shape or source availability. Carry these limits into the final handoff.

## Out of scope

- Retraining, model selection, H0/H6/H12 substitution, feature redesign, and new
  scientific formulas.
- Web/dashboard presentation or a new public-access policy; the agreed endpoint
  is production current and its referenced artifacts in the existing GCS bucket.
- Copying the entire historical EE asset catalogue, making assets public, or
  changing unrelated projects, models, FEWS NET behavior, or deployment services.
- A general-purpose asset pipeline, arbitrary backfill service, unrelated source
  automation, or monthly calendar scheduler. D3 selects immediate execution upon
  choice submission. The two upstream EE producers are explicitly in scope.
- Deleting production retained history to force a refresh; editing the accepted
  bundle or falsifying a future execution month to obtain apparent E2E coverage.
- A new earlier-checkpoint bundle/envelope, or live incremental acceptance in this
  round. Deferring that acceptance does not defer any required automation code.

## Accepted decisions

- **D1 — production current, bucket endpoint (2026-10-30):** The user confirmed
  "发布到线上current，bucket上可见即可。" This task includes actual publication
  to production current and GCS readback of the referenced output artifacts.
  Candidate-only acceptance is insufficient; web/dashboard work is excluded.
- **D2 — full automatic monthly E2E (2026-10-30):** The user explicitly requires
  upstream EE export to run automatically every monthly operation; only keep/fresh
  and related asset operations remain manual. The existing API spells fresh as
  `refresh`. This supersedes the earlier manual-export proposal. Production,
  submission/wait, validation, asset mapping, generation, inference, and current
  publication must be one unattended flow after the agreed trigger. It does not
  authorize scientific retraining or automatic changes to manual input choices.
- **D3 — submission triggers execution (2026-10-30):** The user confirmed
  "提交选择即触发". Submitting the month's complete keep/refresh selection and
  associated assets creates the pinned v2 request; its finalized-object event
  starts the full automatic route. No separate run/publication button or calendar
  timer is needed. Incomplete input preparation is not a submitted request.
- **D4 — defer live incremental acceptance (2026-10-30):** The user chose the
  natural November-or-later increment and stated "目前不用进行增量验收". Preserve
  the accepted history and envelope. Implement/test the complete automated route
  now, and run the real retained-history/current-publication acceptance; DA1-DA2
  remain explicit follow-up evidence, not current completion requirements.
- **D5 — submission-time UTC month (2026-10-30):** The user confirmed
  "自动采用提交时的UTC当月". The routine submission surface derives M automatically
  from its UTC submission instant, with O=M-2 and targets M/M+6/M+12, and freezes
  them for the request. Queued execution, month rollover and network redelivery
  must not change M. Existing explicit-month v2 requests remain supported under
  their current guards for exceptional authorized reruns, not routine operator work.

## Technical constraints and execution checks

- T1: Refresh actual deployment/service identity, required EE/GCS access, installed
  artifacts and retained-store state before mutation. Historical local configuration
  is not live evidence; stop and report a prerequisite failure rather than guessing.
- T2: Port source-defined scaling unchanged and test both omitted/all-null data
  shapes; real export/unit validation is DA2. Column presence alone is insufficient
  evidence of complete observations.
- T3: Exact-bundle initialization and missing-key scheduling explain October's
  legitimate climate skip. Do not add checkpoint support. Source anchors and proof
  are retained in `research/automation-evidence.md`.
- T4: Before the real run, validate ACLED first-refresh inputs and full O-12..O
  coverage if no retained history exists. Implement v2 submission and artifact
  installation as described in `design.md`; missing assets are prerequisite failures.
- Retain existing resource bounds: deployment currently specifies 4-hour jobs and
  zero automatic task retries (`cloud_pipeline/deploy/setup.py:34-75`). EE polling
  has a deadline/15-minute-reserve mechanism, but the current v2 context does NOT
  pass that deadline (`entrypoint_v2.py:173-175`). Wire one persisted whole-run
  deadline from configured limits into producer/transport/acquirer work, preserving
  remaining budget across retries; do not restart a six-hour EE timer inside a
  four-hour job. Do not enlarge resources/retries silently. Keep runtime deadline
  configuration separate from v2's fixed request fields, which contain no cutoff
  or deadline. Disclose exact live limits/cost scope before launch.
- Current-pointer compatibility and source-completeness findings are documented in
  `research/grill-second-pass.md`. Reuse existing request/run reservation patterns
  for v2 replay protection; the v2 branch bypasses legacy `run_once` and therefore
  cannot claim that protection without wiring/testing it. A recreated workdir or
  create-only status error after mutations is not adequate duplicate prevention.
- Preserve upstream full-chunk numerical definitions and raw source identity.
  The new mapped chunk replaces the old chunk for reads; never concatenate both
  and rely on left-column precedence. The 2020 raw values in the refreshed
  2020-2026 block participate in the 1991-2020 fit. Record this input vintage;
  do not silently introduce a frozen-baseline splice, retrain, or rewrite saved
  indicators. Existing R40 permits recorded method differences for new months
  without a train/serve numerical equality gate.

## Planning and execution gates

- D1-D5 are resolved; the second grilling pass and specification convergence are
  complete. PRD, design, implementation plan and curated context manifests are
  approved by the subsequent user execution instruction. Live prerequisite checks are execution work;
  DA1-DA2 remain expressly deferred. No product behavior is marked implemented or
  verified by this specification.
- The requested spec -> grilling -> consolidated summary -> subsequent execution
  instruction sequence is complete. Bind the actual Herdr Executor and use native
  Trellis state operations under `execution-protocol.md`.
- The latest user instruction explicitly forbids Trellis Audit/automatic Audit for
  this task, superseding the earlier enrolled-repository wrapper requirement.
  Supervisor diff/checkpoint/final verification remains mandatory.
- Preserve the pre-existing `AGENTS.md` modification. On 2026-10-31 the user confirmed:
  "云权限在goal的范围内提前确认，无需单独审批". Necessary cloud reads, builds,
  compatibility verification, deployment, initialization, full-roster execution and
  current publication within this goal are preauthorized; do not request separate
  user approval. Record concrete operations, effects, resource/cost/time limits and
  rollback evidence before launch. Supervisor checkpoint verification remains;
  deferred DA1-DA2, retraining and unrelated operations remain outside this scope.
