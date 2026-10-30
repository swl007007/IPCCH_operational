# IPCCH validity H2/H8/H14 migration - final report (Executor, 2026-10-30)

Status: CP0, CP1, CP2 accepted earlier; CP3 and CP4 accepted by the Supervisor within the execution-protocol local
scope; CP5 accepted; CP6 implementation/evidence/operator gates accepted - this report and the clean committed state
are the remaining CP6 deliverable. Final acceptance, native finish and archive are the Supervisor's; no Audit, PR,
merge or deployment was performed.

## What was delivered

- Research side (CP1/CP2, `food-crisis-research`): oracle-free H2/H8/H14 final-stage models (cutoffs 2025-11 /
  2025-05 / 2024-11), model-matched evidence, accepted combination envelope v2 03b93842... binding package 18b91d45...,
  feature order 0ef1ffec... (527), roster 9ff2c420... (6,226) and the accepted handoff bundle (`cp1/`, `cp2/`).
- Operational side (this repository, `cloud_pipeline`): the v2 four-operation request contract and executable route
  (`cloud/ipcch/entrypoint_v2.py` run + initialise; `delivery_job run --v2-config`); IPCCH retained stores, ACLED
  regional aggregates, climate (EE transport, ensembles, SPI/SPEI, seasons), GPP v3, nightlight, WFP, research
  families, assembly, immutable batches, batch inference, delivery member with system provenance, v2 publication
  (single pointer, per-system members, activation, candidates, CAS without retry), per-system locks; FEWS NET v2
  adapter on the existing prepare/deliver; legacy v1 cutover guards, current-bound inheritance, scoped remote
  preparation, promote/verify guards.
- Scale: 98 task commits (174381f..HEAD); `cloud_pipeline` 94 files changed, +19,096 / -133 lines.

## Evidence and receipts

| Item | Where | Result |
|---|---|---|
| requirement matrix | `research/cp6/cp6-evidence-matrix.md` | AC1-40, R1-R66, FCC1-10 = 116 rows, each once; every test reference resolves (`check_matrix.py`) |
| test inventory | `research/cp6/test-index.md` / `.json` (`test_index.py`) | 524 test functions in 60 suites |
| final regression | `research/cp6/final-tests-summary.md` | whole `cloud_pipeline/tests`: `957 passed, 1015 warnings` at bbf21a4 (code == d57a3fb), exit 0; py_compile clean |
| CP5 smoke | `research/cp5/cp5-smoke.md`, `cp5-results.json` | actual package, fixture-only 2 countries, executable gen-only / inf-only / combined, isolated current replacement, 3 failure-preservation runs, zero real touch (calibrated spy); 12/12 checks |
| FEWS parity | `research/cp4/fews-parity/fews-parity.md`, `parity-results.json`, `parity-inputs-manifest.json` | real deliver(fewsnet) on 12 real areas: keep / refresh / refresh-split - 28/31 byte-identical incl. all 15 scope tables, 3 identical modulo output root |
| real-mode local integration | `research/cp3/real-integration/` | accepted package + handoff, 6,226 rows per horizon (local, not cloud) |
| operator handoff | `research/cp6/operator-handoff.md`, `examples/` (validated by `operator_examples.py`) | config, initialisation, requests, activation/legacy rules, recovery, known data limits |
| source recovery | `rollback-baseline.md` | pre-refactor commit 422f9212, tag, verified bundle |
| Supervisor reviews | `research/cp0-supervisor-review.md`, `cp1/`, `cp2/`, `cp3-supervisor-review.md`, `cp4/supervisor-review.md` | closures per finding |

Receipts are committed as lean summaries/hashes; bulky logs stay local (`*.log` is gitignored).

## Defects found and fixed late (all with regressions that fail on the prior commit)

Exact-bytes deliveries (pickled FEWS packages); FEWS member validation and package checksum rules; legacy routes
bound to the current release on every path (operator, remote admission, delivery) with scoped remote preparation and
consistent legacy pointer reads; lock adoption race and owner cleanup on every terminal path; FEWS keep projection
of the shared retained file; smoke evidence restricted to the fixture roster (identity validated first, empty subset
unavailable); R53/R62 warnings carried into prediction metadata.

## Deferred - not run, not claimed (cp6-evidence-matrix.md "Deferred")

Live EE/cloud exports and private-asset access; full-area cloud generation; real GCS store initialisation; production
publication, activation and live cutover; the deployed image/environment; real FEWS provider data through the adapter;
production rollback; Google Workflows execution itself. These are not blocking for this local acceptance.
