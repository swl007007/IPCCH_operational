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

- [ ] Resolve default branch SHA with `gh api repos/IFPRI/MTI-GOOGLE-FOOD-CRISIS-MODEL/commits/main`; fetch exact-SHA WFP/ACLED blobs to exclusive output files, record bytes/hash and metadata.
- [ ] Read date/type/Trend schemas, exclude post-April observations before aggregation; compare WFP country-month aggregates with each baseline panel, report multivalue baseline keys and distributions.
- [ ] Establish matching indicator/units from source processing and paired values. Save no-conversion evidence or source-supported conversion formula; unresolved semantics stops dependent data use.
- [ ] Capture baseline file hashes and source identities before building new inputs.

## Task 2: Versioned panel refresh

Files: `tools/refresh_h5_inputs.py`; generated `inputs/{fewsnet,ipcch}_panel.csv`, normalization audit, April input CSVs, refresh report.

- [ ] Read current ACLED aggregation/matching functions and WFP country mapping end to end; reuse these math functions without invoking their top-level configured output writes.
- [ ] Aggregate model-specific WFP indicators (FEWS price change mean+100/SD; IPCCH Trend mean+100/SD) to country-month, conflict indicators to their existing admin levels and nearest-point rule. Replace covered source keys as a complete feature group and preserve uncovered baseline history.
- [ ] Preserve IDs/labels/non-updated sources, truncate panels through April, recompute dependent frozen features and FEWS normalization audit. Reject ambiguous identity/duplicate keys with examples.
- [ ] Check retained keys, changed columns, unmatched sources, missingness and historical coverage on real inputs; focused check proves an uncovered historical key survives and post-cutoff source rows do not affect aggregate values.

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

- [ ] Add only h5 acceptance at single-model boundaries, retain suite-wide expected 0/6/12 sets. Run focused h5 train/package/reload example with keyed missing-calendar-month alignment.
- [ ] Port the narrow existing IPCCH production-safe export functions into the local runner with provenance, reuse local runtime contract validation, add explicit label cutoff and scope5 while preserving fitted feature order/hyperparameters/thresholds.
- [ ] Train FEWS latest36/30/6 with full source, and four IPCCH regressors with eligible full source; record actual periods/counts/parameters. Load exported packages for final April scoring.

## Task 4: Portable model delivery and country tables

Files: `tools/run_h5_model_delivery.py`; generated model subdirectories, `polygon_predictions.csv`, `polygon_model_mapping.csv`, `polygons.geojson`, `country_predictions.csv`, portable runtime, README and manifest.

- [ ] Reuse `build_identity_population_frame`, `enrich_local_predictions`, IPCCH runtime scoring/enrichment and existing country single-frame APIs:

```python
aggregate_country_probabilities(predictions, country_scope, census_population)
aggregate_country_scores(predictions, area_lookup, census_population)
```

- [ ] Export each native ID as string; FEWS routes show actual partition/pooled fallback, IPCCH routes show shared four-target scope5 package. Join geometry without duplication/loss or simplification.
- [ ] Retain original country aggregation math/Census reference and explain dispersion versus confidence intervals and distinct model semantics.
- [ ] Include runtime code/dependencies and April scoring inputs; package-relative references support a relocated checkout with no external source tree.

## Task 5: Focused checks and independent acceptance

Files: new `tools/verify_h5_model_delivery.py` (standalone artifact verifier); run-scoped verification reports and README.

- [ ] Check cutoff/h5 alignment on actual training keys; FEWS training periods and split; model/feature/partition hashes; full polygon identity equality across input/results/routes/geometry.
- [ ] Recompute country weighted mean/SD and population coverage independently from final CSVs, compare at strict numeric tolerance.
- [ ] Relocate delivery to /tmp, reload all models, rescore delivered April inputs; require exact classes and continuous predictions `rtol=0, atol=1e-12`.
- [ ] Independently audit artifact coverage through read-only subagents and inspect cited exceptions personally. Resolve material discrepancies.
- [ ] Verify baseline hashes unchanged, write passed manifest last with all artifact hashes, update this task ledger with actual commands/results and report deliverable paths. Do not declare success from process activity or preliminary reports.
