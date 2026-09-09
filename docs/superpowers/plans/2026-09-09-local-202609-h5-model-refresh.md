# Local September 2026 h5 model refresh implementation plan

> Execute inline with executing-plans. User directs subagents to exploration/independent verification only, skips TDD, and requests focused checks only (no regression suites).

**Goal:** Refresh WFP/ACLED, retrain both native polygon models at h5, deliver September predictions, portable packages, routing, boundaries and country tables.

**Architecture:** Keep the existing cloud/default three-horizon orchestration unchanged. A bounded local runner composes existing FEWSNET core/package/output APIs, IPCCH launch fitting/runtime and single-frame country aggregators. Source refresh is a separate local data preparation step with explicit identity and coverage evidence.

**Tech stack:** Existing Python/pandas/NumPy/scikit-learn/imbalanced-learn/GeoPandas/pyarrow; XGBoost 3.2.0 matches the current IPCCH model serialization version. Isolated runtime under /tmp, exact installed versions recorded.

**Spec:** `docs/superpowers/specs/2026-09-09-local-202609-h5-model-refresh-design.md` (approved).

## Global constraints

- Feature cutoff 2026-04, label cutoff 2026-04, sole target 2026-09, sole horizon 5.
- Preserve feature/model math, RF sparse 36/30/6 split, XGB fixed threshold and native polygon sets.
- WFP comparison at overlapping country-month keys before updates; do not infer conversions from range alone.
- New outputs only under `Outcome/model_delivery/202609_h5/{run_id}`; preserve baseline artifacts.
- Main agent owns edits and final verification. Symbol edits require upstream impact first; commits require detect_changes.
- No TDD or regression suites. Focused executable checks plus independent real-artifact verification.
- No cloud, web app, remote push or production release changes.

## Task 1: Source snapshot and scale audit

Files: new run-scoped `sources/`, `reports/source_manifest.json`, `reports/wfp_scale_audit.json`; `tools/refresh_h5_inputs.py` owns reproducible preparation.

- [x] Resolve default branch SHA with `gh api repos/IFPRI/MTI-GOOGLE-FOOD-CRISIS-MODEL/commits/main`; fetch exact-SHA WFP/ACLED blobs to exclusive output files, record bytes/hash and metadata.
- [x] Read date/type/Trend schemas, exclude post-April observations before aggregation; compare WFP country-month aggregates with each baseline panel, report multivalue baseline keys and distributions.
- [x] Establish matching indicator/units from source processing and paired values. Save no-conversion evidence or source-supported conversion formula; unresolved semantics stops dependent data use.
- [x] Capture baseline file hashes and source identities before building new inputs.

## Task 2: Versioned panel refresh

Files: `tools/refresh_h5_inputs.py`; generated `inputs/{fewsnet,ipcch}_panel.csv`, normalization audit, April input CSVs, refresh report.

- [x] Read current ACLED aggregation/matching functions and WFP country mapping end to end; reuse these math functions without invoking their top-level configured output writes.
- [x] Aggregate model-specific WFP indicators (FEWS price change mean+100/SD; IPCCH Trend mean+100/SD) to country-month, conflict indicators to their existing admin levels and nearest-point rule. Replace covered source keys as a complete feature group and preserve uncovered baseline history.
- [x] Preserve IDs/labels/non-updated sources, truncate panels through April, recompute dependent frozen features and FEWS normalization audit. Reject ambiguous identity/duplicate keys with examples.
- [x] Check retained keys, changed columns, unmatched sources, missingness and historical coverage on real inputs; focused check proves an uncovered historical key survives and post-cutoff source rows do not affect aggregate values.

## Task 3: Local h5 model path

Files: new `tools/run_h5_model_delivery.py`; narrowly adapt horizon validators in `fewsnet_partitioned_rf_pipeline/core/{horizons,training,inference,validation}.py`, local output validator and two local package/prediction schemas. Avoid modifying default `HORIZON_MONTHS/HORIZON_KEYS` suite constants or the three-horizon runner.

Interfaces reused:

```python
align_horizon(feature_frame, labels, horizon_months=5)
select_training_window(aligned_frame, latest_label_month, months=36)
train_horizon_model(...)  # existing imputer, threshold, RF and refit core
write_local_model_package(output_dir, predictor, metadata, reports)
load_local_model_package(package_dir, expected_panel_sha256=...)
```

Exact call signatures are read before implementation; single-horizon validators accept 5 while cloud suite membership remains unchanged.

- [x] Add only h5 acceptance at single-model boundaries, retain suite-wide expected 0/6/12 sets. Run focused h5 train/package/reload example with keyed missing-calendar-month alignment.
- [x] Port the narrow existing IPCCH production-safe export functions into the local runner with provenance, reuse local runtime contract validation, add explicit label cutoff and scope5 while preserving fitted feature order/hyperparameters/thresholds.
- [x] Train FEWS latest36/30/6 with full source, and four IPCCH regressors with eligible full source; record actual periods/counts/parameters. Load exported packages for final April scoring.

## Task 4: Portable model delivery and country tables

Files: `tools/run_h5_model_delivery.py`; generated model subdirectories, `polygon_predictions.csv`, `polygon_model_mapping.csv`, `polygons.geojson`, `country_predictions.csv`, portable runtime, README and manifest.

- [x] Reuse `build_identity_population_frame`, `enrich_local_predictions`, IPCCH runtime scoring/enrichment and existing country single-frame APIs:

```python
aggregate_country_probabilities(predictions, country_scope, census_population)
aggregate_country_scores(predictions, area_lookup, census_population)
```

- [x] Export each native ID as string; FEWS routes show actual partition/pooled fallback, IPCCH routes show shared four-target scope5 package. Join geometry without duplication/loss or simplification.
- [x] Retain original country aggregation math/Census reference and explain dispersion versus confidence intervals and distinct model semantics.
- [x] Include runtime code/dependencies and April scoring inputs; package-relative references support a relocated checkout with no external source tree.

## Task 5: Focused checks and independent acceptance

Files: new `tools/verify_h5_model_delivery.py` (standalone artifact verifier); run-scoped verification reports and README.

- [x] Check cutoff/h5 alignment on actual training keys; FEWS training periods and split; model/feature/partition hashes; full polygon identity equality across input/results/routes/geometry.
- [x] Recompute country weighted mean/SD and population coverage independently from final CSVs, compare at strict numeric tolerance.
- [x] Relocate delivery to /tmp, reload all models, rescore delivered April inputs; require exact classes and continuous predictions `rtol=0, atol=1e-12`.
- [x] Independently audit artifact coverage through read-only subagents and inspect cited exceptions personally. Resolve material discrepancies.
- [x] Verify baseline hashes unchanged, write passed manifest last with all artifact hashes, update this task ledger with actual commands/results and report deliverable paths. Do not declare success from process activity or preliminary reports.

## Execution evidence (2026-09-09)

- Source commit: `92b4fb20fc4f4b0a3fa69c89b2382ffd4b2b1ab6`; actual ACLED coverage 2025-05-01..2025-07-22 (partial July). WFP Aggregated only, observation cutoff April; no fitted scaler.
- Training implementation commit `55f48ee97abb` for FEWSNET; IPCCH trained after country matching fix at `404ee6e`. The missing baseline CIV ISO3 is resolved from country_en only for WFP keys; raw identity remains preserved. Superseded intermediate IPCCH artifacts are isolated outside final delivery.
- `/tmp/ipcch-h5-py312/bin/python -B tools/check_h5_delivery_focus.py`: passed calendar h5, price-series gaps, covered-group overwrite, historical preservation and CIV resolution.
- `tools/audit_h5_inputs.py --root Outcome/model_delivery/202609_h5/20260909_refresh_v1`: passed actual saved CSV non-source preservation, normalization numeric preservation, country-month ranges/paired differences and separate multivalue keys.
- `tools/run_h5_model_delivery.py train-fewsnet`: completed 188,643 samples, 36 observed labels (2014-04..2026-02), 30/6 threshold split, full refit, 123 frozen features, threshold0.43.
- `tools/run_h5_model_delivery.py train-ipcch`: completed four regressors, 43,551 samples,128 frozen features, max training feature2025-11/label2026-04. Original median/parameters/cumulative decoding retained.
- `score` loads both exported packages; `export` produced 5,718/6,227 polygons and22/53 countries. Geometry/routes/predictions retain full native sets.
- `tools/verify_h5_model_delivery.py`: passed actual training keys, routes, population/Census checks, independently recomputed country means/SD/counts, and relocated subprocess reload of all output fields (rtol0,atol1e-12).
- Read-only independent agents checked source aggregation against original (5,787 ACLED admin3 rows exactly equal), model methods, actual April WFP, code/input hashes and all native geometry coordinates. IPCCH253 invalid geometries were inherited unchanged; documented, not repaired.
- No TDD or regression suite ran. No remote push, cloud operation or web application implementation occurred.
- Packaging/integrity is finalized by `tools/package_h5_delivery.py`; only the final root manifest with passed status certifies archive member hash verification and unchanged baseline fingerprints.
