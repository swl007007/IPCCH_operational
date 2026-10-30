# Implementation plan

Status: planning draft. Do not start or execute until spec/grilling convergence and explicit implementation approval. Every step below references prd.md requirements; exact file edits require GitNexus impact analysis first.

## Deliverable groups

A. Research-side training and package handoff (food-crisis-research).
B. cloud_pipeline request contract, validation and locks.
C. cloud_pipeline IPCCH collection, retained stores and feature batches.
D. cloud_pipeline inference, diagnostics and publication.
E. Smoke fixtures, tests and documentation.

Groups B-E can be developed before A completes using unit tests; the end-to-end smoke milestone waits for the candidate package from A (R42).

## Steps

1. Pin facts for training (A): hyperparameter records for H0/H6/H12 trials, final-stage cutoffs 2025-11/2025-05/2024-11, 527-column feature order without oracle columns, numerical environment, input manifest hashes. Measure eligible sample counts per horizon. Record in a research task artifact. (R4, R10, R15)
2. Training-data preparation (A): apply the GPP availability filter from the provider update log per row (R57), keep research alignment (R65), retain year dummies (R58), real inputs only (R15). Train the three final-stage contexts with mapped hyperparameters; no HPT, no refit (R12). Cloud execution only under a separately authorized packet (R30).
3. Evidence and packaging (A): recompute per-horizon resubstitution confidence evidence and maximum-phase residual evidence with the new weights (R31); convert `q2..q5.ubj` into the runtime scope layout; build the package manifest with checksums, schema hashes, evidence references, run ids and `status: candidate` (R51); bundle fixed assets (roster 6,226, geometry, static29+AE128, population reference, ACLED mapping/override/coverage-start/neighbour tables) (R32, R55). Deliver initial retained histories from the training panel (GPP v3 all years, WFP, nightlight, nino34, bbg composites, WB index, IDP national/local) and the reported-phase snapshot with acceptance records (R45, R54, R59, R62, R64).
4. Request contract v2 (B): new schema version with mode, execution month, four operations, IPCCH block (model combination, feature batch, ACLED/research-input/history/WFP choices), FEWS NET block (prepared_snapshot), publication. Validation order per design.md: structural, mode (R38), conflicts (R19), derived dates and M rules (R39, UTC), immutable references, per-system lock (R50), admission; invalid requests execute nothing (R17). Legacy v1 routing retained; post-activation rejection of IPCCH-containing v1 requests (R37).
5. Retained stores and acceptance (C): new IPCCH store layout separate from shared ACLED/WFP files; acceptance manifest reader/writer (R45); per-indicator-month persistence (R41); GPP availability ledger with 404-only unpublished classification and fill-only-unpublished exception (R9, R49); climate incremental update through ported shared scripts with method identifiers (R1, R34, R40, R43); growing-season eligibility (R33); research-prepared family and history-snapshot keep/refresh handlers (family refresh uses declared-interval replacement; history_snapshot refresh replaces the complete validated snapshot through its preparation cutoff) and coverage warnings (R59, R62); WFP converter on IPCCH rows and VIIRS append on fixed geometry (R64).
6. ACLED converter (C): port `build_acled_agg.py` conventions with delivered tables (R55); refresh validation (Saturday weeks, declared interval, declared regions, mapping, 25 km cap), week-level interval replacement, month completeness, coverage-end warning, keep rejection without saved real history, success-as-baseline and failure-preserves-history semantics (R24-R29, R44, R53, R56). Reject inference-only plus refresh before mutation (R19).
7. Feature assembly and batches (C): per-horizon assembly on the fixed roster from package feature contracts; required columns always emitted with reasons; duplicate keys and missing rows fail; immutable batch with unique id and full metadata; generation-only summary (R13, R32, R52, R65).
8. Inference and diagnostics (D): batch validation (combination identity, cutoff, schema, dummy/real, reordering, duplicates, unparseable/infinite values, extras ignored) (R19, R36); scoring through the existing path unchanged (R61); nonfinite failure (R18); model-matched diagnostics with unavailable-field handling (R31); package manifest verification with accepted/candidate rule (R51).
9. Publication (D): three-horizon atomic IPCCH release (R18); single pointer with cross-system inheritance of different-month members and per-system month metadata, keeping file names and columns (R47, R63); candidate publication without pointer move (R66); M regression recheck and legacy-cutover check immediately before the pointer compare-and-swap, activation derived from the release record (R37, R39, R46); partial success across systems (R17); per-system lock release.
10. Smoke fixtures and isolation (E): fixture store with small roster subset, synthetic histories for every family, dummy ACLED export with declared interval/regions, fixture acceptance records, fake object store and isolated namespace; mode=smoke labels; full read isolation (R14, R16, R36, R48). Smoke uses the candidate package (R42).
11. Tests (E): contract validation cases for every rule in steps 4-9; converter and store tests; inheritance tests updated for cross-system different-month inheritance; FEWS NET regression through legacy and new entrypoints without new required fields (R6, R60); end-to-end local smoke.
12. Documentation (E): operator runbook for the new manifest, monthly research-side preparation steps (snapshot export, refresh files), dummy-to-real replacement, known lags per family, GPP sparsity and year-dummy extrapolation notes (R57, R58, R65).

## Candidate validation suites

Run from cloud_pipeline with its verified numerical environment. Existing suites to extend or deliberately update: `tests/cloud/test_delivery_manifest.py`, `test_delivery_job.py`, `test_inherited_bundle_checks.py`, `test_prepare.py`, `test_retrain_source_contracts.py`, `test_delivery_outputs.py`, `test_execution_selection.py`, `test_ipcch_chunked.py`, `tests/test_refresh_h5_inputs.py`, `tests/test_operator_release.py`, `tests/test_operational_launch_feature_contract.py`, `model_pipeline` inference tests. New suites for the ACLED converter, acceptance manifest, GPP ledger, batch validation, per-system lock and smoke isolation. Exact commands are specified after implementation seams are inspected; no validation has run yet.

## Execution prerequisites

Final reviewed PRD/design/plan, populated implementation/check context manifests, repo-specific development guidelines, required GitNexus impact analysis, and applicable audit lifecycle verification. No cloud actions, training, deployment, commits or task start are authorized by writing these drafts.

## Convergence verification

Apply the final convergence corrections in prd.md to request validation, snapshot replacement, lock acquisition, all current publication paths and candidate promotion. Tests must cover each corrected boundary, including concurrent CAS failure without automatic retry, preservation of activation through legacy FEWS publication, fixture acceptance validation, and event-free covered ACLED weeks.
