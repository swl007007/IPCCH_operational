# IPCCH H2/H8/H14 + FEWS NET v2 route - operator runbook and recovery (CP6, Executor 2026-10-30)

Scope: how an operator configures, initialises and submits the v2 route, how the legacy v1 route behaves around the
new contract, and how to recover from failures. Everything here was exercised locally (fakes, fixtures, the actual
package in smoke, a 12-area real FEWS parity); **nothing was deployed or run against production** - see the deferred
list in `cp6-evidence-matrix.md`. Examples in `examples/` are generated AND validated by `operator_examples.py` (the
production validators; exit 1 if any example is invalid).

## 1. Components

| Component | Entry point | Purpose |
|---|---|---|
| v2 request contract | `cloud/orchestrator/delivery_request_v2.py` (`fewsnet-ipcch-delivery-request-v2`) | four operations (IPCCH generation/inference, FEWS NET generation/inference), smoke/real mode, admission |
| v2 executable route | `python -m cloud.ipcch.entrypoint_v2 run ...` (also `delivery_job run --v2-config` for a v2 body) | admit -> locks -> IPCCH generation/batch/inference -> FEWS NET adapter -> publication -> run status |
| store initialisation | `python -m cloud.ipcch.entrypoint_v2 initialise --config ... --mode real` | one-time retained-store initialisation of a mode from the installed binding |
| FEWS NET v2 adapter | `cloud/ipcch/fews_adapter.py` (built by the route when a FEWS operation is selected) | existing prepare (FEWS scope) + generation source binding + existing deliver(fewsnet) + v2 member publication |
| legacy v1 route | `delivery_job run/admit/resolve/release`, `deploy/workflow.yaml`, `pipeline.py` | unchanged request shape; R37 cutover guards; current-bound inheritance; shared locks |
| acceptance tool | `tools/ipcch_finalize_acceptance.py` | finalize handoff acceptance entries + accepted envelope (used at CP2) |

## 2. Deployment configuration

`examples/deployment.example.json` (validated by `entrypoint_v2.load_config`). Keys:

- `roots.{real,smoke}`: delivery roots (pointer `<root>/<namespace>/current.json`, deliveries, releases, candidates,
  conflicts, `locks/<system>`, `runs/<run_id>/v2_run_status.json`, `prepared/<prepare_id>/`). Distinct, not nested.
  `roots.real` is the same bucket root as the legacy `DELIVERY_OUTPUT_ROOT` (shared pointer and locks).
- `store_roots.{real,smoke}`: retained IPCCH stores (must end with `/real` / `/smoke`).
- `namespaces.production` / `.smoke`; `trusted_prefixes.{real,smoke}`: every request reference except the shared
  envelope/environment manifest must lie under these (lexical admission before any read, R48). Real needs the operator
  input prefix, the FEWS NET prepare-request prefix (`gs://<bucket>/prepare_requests/` - the existing path rule) and
  `<roots.real>/prepared/` (snapshots a v2 FEWS generation writes; an inference-only request names one of these);
  smoke lists fixture inputs only.
- `installed.real`: accepted envelope v2 (`ipcch-combination-envelope-v2-accepted.json`, sha256 03b93842...), the
  package directory (manifest 18b91d45...), the accepted handoff bundle; `installed.smoke`: the same envelope/package
  plus a fixture bundle inside a declared `fixture_root`.
- `providers.real = cloud.ipcch.entrypoint_v2:real_providers` (EE transport + GCS/HTTP acquirer; built only when IPCCH
  generation is selected); `providers.smoke` = a fixture factory (never the real providers - refused by the config).
- `earth_engine_project`, `export_root`, `work_dir`; `fewsnet.image_uri` = the delivery job image (needed for FEWS).

## 3. One-time initialisation (per mode)

```
python -m cloud.ipcch.entrypoint_v2 initialise --config deployment.json --mode real
python -m cloud.ipcch.entrypoint_v2 initialise --config deployment.json --mode smoke --acceptor ops@example.org
```
Real installs the envelope-bound finalized acceptance entries (R45), then initialises every table of the accepted
bundle; smoke admits only the fixture bundle and records fixture acceptance (R48, FCC10). Atomicity, precisely: the
TABLES and the combination PAIRING are two-phase (`initial.initialise`: the whole bundle is validated before any table
commit, the pairing is written last, a store paired with another combination is refused); the ACCEPTANCE records are
appended first and stay if a later bundle validation fails (they only record accepted inputs; nothing reads tables
without the pairing). A rerun is idempotent: no duplicate acceptance entry, every table `unchanged`.
Tests: `ipcch_entrypoint_v2::smoke_store_initialisation_route_then_a_request_runs`,
`::real_store_initialisation_route_installs_the_bound_acceptance_entries` (incl. the idempotent rerun);
table atomicity `ipcch_initial::preflight_rejects_a_malformed_later_file_before_any_write`.

## 4. Requests (examples/)

| Example | Operations | Notes |
|---|---|---|
| `real-ipcch-generation-inference-current.json` | IPCCH gen + inf, publication current | ACLED refresh (declared Saturday..Friday interval covering the R44 lookback through O, declared regions), keep for research families / snapshot / WFP; country reference for inference |
| `real-ipcch-generation-only.json` | IPCCH generation | writes an immutable batch; never publishes |
| `real-ipcch-inference-only-named-batch.json` | IPCCH inference | exactly the named batch (manifest ref under `<store root>/feature_batches/`); no refresh allowed (FCC1) |
| `real-fewsnet-generation-inference.json` | FEWS gen + inf | `prepare_request` (existing schema; run with FEWS scope); keep/refresh choices bound to the produced snapshot |
| `real-fewsnet-inference-only-prepared-snapshot.json` | FEWS inference | exactly the referenced snapshot; uses the choices bound at its generation (refused if unbound) |
| `smoke-ipcch-generation-inference.json` | smoke IPCCH | smoke may select IPCCH only (R38); smoke root/store/namespace only |

Rules an operator must respect (enforced; see the matrix for tests): `execution_month` M is not later than the UTC
month and, for real IPCCH current, not earlier than the current release's IPCCH month (R39; candidate exempt from the
older-M rule); `release.expected_pointer_generation` = the generation of `<root>/<namespace>/current.json` read just
before submission (a moved pointer fails publication - no retry/rebase - FCC3); all references are pinned
`{uri, generation, sha256}` and verified before anything runs (R17). `publication: candidate` writes an immutable
candidate record without moving the pointer and is never promotable (R66); to publish, submit a new inference-only
request with `publication: current`.

Run: `python -m cloud.ipcch.entrypoint_v2 run --config deployment.json --request-uri gs://<bucket>/requests/<run_id>/run_manifest.json --request-generation <N>`.
Outcome: `<root>/runs/<run_id>/v2_run_status.json` (create-only; per-system status, failing step/operation, the
structured generation report incl. saved updates and warnings) and the returned status; exit 0 only when `succeeded`.
Overall status `partial_success` when one selected system fails (R17).

## 5. Activation and the legacy v1 route

- Activation (R37) = the first successful REAL current publication of a new-contract IPCCH member; it is recorded in
  the release record, carried by every later publication and never cleared (R46).
- After activation, any v1 request scoring IPCCH (alone or mixed) is rejected with the migration message at request
  time, at remote admission (before any collection) and again at publication (cutover mid-run).
- v1 FEWS NET-only stays supported. Its `execution.inherit.ipcch` must name the current release's IPCCH member by
  its exact delivery manifest: a new-contract member with its own feature origin and - v2 deliveries have no archive -
  `archive` repeating the member's manifest ref (`pipeline.py --inherit-archive` = `--inherit-manifest`); a member of a
  legacy v1 delivery keeps its real archive and the same-origin rule (also when carried into a v2 record). Against a v2
  record the FEWS member is published as a v2 member inheriting IPCCH and the activation.
- v1 remote-update after activation: the preparation is scoped to FEWS NET (admission `prepare_scope`; the workflow
  passes `prepare --systems fewsnet`); before activation the existing both-system preparation is unchanged.
- Locks (R50): v1 and v2 share `<root>/locks/<system>` for the systems actually collected/scored. A remote-update run
  holds them from admission through preparation, resolution and delivery.
- Promote/verify (`pipeline.py`) reject new-contract candidates; a legacy candidate binds at promotion to the pointer it
  replaces.

## 6. Recovery

| Situation | What happened | Operator action |
|---|---|---|
| request rejected at admission | nothing ran (R17) | fix the request; resubmit (new run id if the request object changed) |
| publication failed (pointer moved) | batch/predictions/delivery kept and reported; pointer unchanged | submit inference-only with the reported batch and the current `expected_pointer_generation` |
| IPCCH generation failed after saved updates | saved months/refreshes kept (R29/R41), reported in the run status; no batch | resolve the cause (e.g. missing climate source at O); rerun - only unsaved months are computed |
| inference failed | batch kept (R5/R52); current unchanged | rerun inference-only on the batch once the cause is fixed |
| one system failed (`partial_success`) | the other system's member is published; failed system keeps its previous member | rerun the failed system only |
| stale lock (crashed job) | the lock blocks that system (R50); never auto-evicted | verify the owning run is dead, then `cloud.ipcch.locks.clear_lock(store, root, system, expected_run_id=..., generation=...)` (owner + generation must still match) |
| failed remote preparation | the workflow runs `delivery_job release` (owner cleanup); a timed-out wait keeps the locks (job may run) | after confirming the job ended, clear with `clear_lock` as above |
| wrong current release published | activation is one-way (R46); no deactivation/rollback interface (R20) | same-M rerun replaces current (R39); otherwise the next month's run |
| source/code recovery | - | `T/rollback-baseline.md`: pinned pre-refactor commit 422f9212, tag `backup/ipcch-pre-refactor-20261030`, verified bundle a177b912...; non-destructive `git worktree add` / bundle clone. A source checkout does not roll back cloud services or retained stores: mutable-state recovery needs a separately reviewed execution packet (pin image digest, current release/model/input refs). |

## 7. Known data limits (operator-facing)

- GPP (R57/R49/R9): GOSIF GPP v3 is published with a lag; at run time only a definitive not-found is recorded as
  unpublished (ledger), so recent months - often including O - are NaN features with a coverage warning (R65
  optional-missing), filled later only into still-unpublished months, never rewriting saved values. The provider
  update-log filter (pre-log months unavailable, keyed on the simulated run date) is a TRAINING-side rule (CP1); it
  says nothing about operational availability.
- Year dummies (R58): the model has `year_2014..year_2026`; targets in 2027 or later have all year dummies 0 (no
  2027 column) - expected, documented in `cp3/cp3d-assembly-initial.md`.
- WFP (R64, `cp3/wfp-price-provenance.md`, `cp3/wfp-contract-correction.md`): the IPCCH training column `WFP_Price` is
  the research HDX year-on-year nearest-market rebuild, NOT the old WFP `Trend` formula; an IPCCH WFP refresh is a
  research-prepared HDX interval file `{action, file, start, end}`. FEWS NET keeps its own raw-export converter.
- Research-only families (R59): `nino34_anom`, `bbg_*`, `food_price_index_WB`, `idp_national`, `idp_local` are
  refreshed only from research-prepared interval files; keep is the default; coverage ending before O gives NaN
  features at O plus a warning, not a block (R65).
- Reported-phase `history_snapshot` (R62): refreshed only as a full atomic research-prepared snapshot; keep is the
  default. A snapshot prepared before O is NOT blanked: the reported-phase features use the latest available reported
  history <= O from that snapshot, and a stale-snapshot warning is recorded.
- All these warnings and coverage ends (incl. the snapshot preparation cutoff) are carried into the published
  prediction metadata (`system_provenance.json` / release member `batch`) as well as the run summary.
- Private Earth Engine inputs: the climate scripts' private assets/tables (baselines, computeFeatures tables) are
  `cloud/ipcch/climate_ee.AssetRefs` with the default root `climate_ee.DEFAULT_ROOT =
  projects/han-sandbox-505315/assets/`; they are checked read-only before any compute (unreadable -> processing
  failure listing them). The deployment config does not expose an override: `climate_run.real_provider_factory(...,
  asset_root=...)` accepts one, `entrypoint_v2.real_providers` uses the default. Live access is DEFERRED (D-live-1).
- The 13 climate bases are the only sources REQUIRED at O (R65); a missing one blocks generation with the base named.

## 8. Deferred live limits

Live EE/cloud exports, full-area cloud generation, real GCS store initialisation, production publication/activation
and live cutover, deployed image/environment, real FEWS provider data through the adapter, production rollback and
Google Workflows execution itself are DEFERRED (matrix "Deferred" D-live-1..8). They were not run and are not claimed.
