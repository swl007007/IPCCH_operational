# Training-error confidence Implementation Plan

> Execute inline with executing-plans; subagents provide read-only independent reviews. User overrides TDD and regression suites.

**Goal:** Replace delivered uncertainty with approved area error rates and country macro confidence.
**Architecture:** Reuse trained-package loaders and exact historical feature/label contracts. A narrow revision tool produces training diagnostics and augments country tables; optional runtime switch disables old IPCCH margin calculations only in revised delivery. Preserve original artifacts in place.
**Tech Stack:** Existing pinned Python3.12.3/pandas/scikit-learn/XGBoost runtime; stdlib packaging.
**Spec:** `docs/superpowers/specs/2026-09-11-training-confidence.md`.

## Global constraints
- No model fit, threshold selection, source refresh or forecast change.
- Unified Phase3+ binary training errors; polygon-equal country mean; separate20% ceil quotas5/11, ISO3 ties.
- Main agent owns edits and final validation; impact before existing symbols; detect_changes before commits.
- New version directory, exact old model/input hashes; focused checks only.

## Steps
- [x] Add `include_uncertainty` default-true switch to `model_pipeline/ipcch_launch_runtime/inference.py:score_scope` and `model_pipeline/run_operational_launch_inference.py:run_scope`. `tools/run_h5_model_delivery.py:score` disables it when revision policy exists; `export_tables` applies saved country confidence fields.
- [x] Add `tools/revise_h5_confidence.py`: reconstruct exact training rows, load existing RF/XGB packages, save row evidence, polygon counts and country macro rates/flags; create immutable revision and update docs/runtime.
- [x] Focused synthetic checks: unequal area sample counts, exact quota ceiling, boundary ties, Phase3 threshold. Independent check of actual rows/area/country aggregates and model provenance.
- [x] Adapt `tools/verify_h5_model_delivery.py` for renamed dispersion/policy relocation, preserve every original scientific check. Gate `tools/package_h5_delivery.py` on revision verification when policy exists.
- [ ] Execute full training rescore (no fitting), independently verify saved results, run relocated scoring and compare unchanged predictions/model bytes, update manifest/archive and report final paths.

## Verified execution evidence

- `revise_h5_confidence.py selfcheck`: passed equal-area macro, ceil quota, ISO3 boundary ties, row-order invariance and Phase3 threshold.
- Saved final models re-scored exactly188643 FEWSNET and43551 IPCCH training rows; zero fitting. All5718/6227 native polygons represented. Errors7/5419.
- `verify_h5_confidence.py`: passed independent truth extraction, binary errors, dictionary-based area counts, exact macro rates,5/11 quota, country identity and source/model byte preservation (27 protected members). Original parent manifest inventory rehashed unchanged.
- `verify_h5_model_delivery.py`: passed country population-weighted means/dispersion, geometry/routing identities and relocated runtime scoring with every retained prediction field identical at rtol0/atol1e-12.
- Actual loaded IPCCH focused check replaces the old uncertainty callback with a failure: revised scoring passes without invoking it, retains numerical scores/classes.
- Independent read-only agents verified code paths and actual tables. Boundary tie field corrected to require multiple countries; neither model has a real cutoff tie.16 inherited IPCCH cumulative labels above1 and230 training scores outside[0,1] retained/documented. FEWS near-zero in-sample error is explicitly not a generalization estimate.
- New delivery directory: `Outcome/model_delivery/202609_h5/20260911_training_confidence_v2`. Original `20260909_refresh_v1` untouched. New manifest/archive gate runs after code commit; no cloud, remote push, TDD or regression suite.
