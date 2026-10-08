# CP3 current-code reuse pointers

Read-only scout findings, 2026-10-07. These are callable/code pointers for the supervisor and executor to inspect, not runtime acceptance or historical provenance requirements. User v0.5 scope applies: no historical archaeology.

## Pure scoring

- FEWS `local/package.py:658` `load_local_model_package` preserves runtime/hash checks; use its saved predictor/feature contract. `core/preprocessing.py:420` `Stage3FeatureBuilder.transform(panel, contract)` builds features without fit, requiring full temporal history. `core/horizons.py:258` `select_latest_inference_frame(feature_frame, latest_feature_month, horizon_months)` selects O and validates the native universe. `core/inference.py:205` `predict_frame` applies the saved imputer/models and horizon metadata.
- FEWS `local/outputs.py:223` `build_identity_population_frame(panel, feature_month)` selects cutoff-bounded population; `:357` `enrich_local_predictions(..., model_artifact_path, source_input)` and `:465` `validate_local_prediction_frame` preserve output schema/identity.
- IPCCH `model_pipeline/run_operational_launch_inference.py:157` `run_scope(monthly_rows, model_package_root, feature_month, scope_months, target_month, source_input, include_uncertainty=True)` is already parameterized pure inference. `ipcch_launch_runtime/adapters.py:21` validates O rows; `feature_contract.py:13` applies ordered columns/saved medians. It rejects unsupported derived contract rules at :219–222; inspect actual package requirements rather than assuming every derivative is constructed by the runtime.
- `cloud/orchestrator/assembly.py:33` and `Final_harmonise/00_build_monthly_ipcch_base_input.py:398` are month-parameterized base assembly, not proof of complete engineered feature construction. Check overlapping EVI source/overlay columns to avoid merge suffixes.
- Reuse CP1 causal-fill and final-feature audit functions; do not fit a contract or imputer. FEWS needs historical 4/8/12 label lags, EVI lag1..12, prior WFP4/12 and nightlight12; only O rows are insufficient.

## Country outputs and missing diagnostics

- Call pure `tools/build_fewsnet_country_level_predictions.py:247` `aggregate_country_probabilities(predictions, country_scope, census_population)` and IPCCH counterpart `:248` `aggregate_country_scores(predictions, area_lookup, census_population)` directly. Their file-level wrappers require old filenames; FEWS file wrapper can overwrite source predictions with clipping corrections (:459–460), so it is inappropriate here.
- `tools/revise_h5_country_v3.py` has reusable `decode_cumulative_phase` (:52), `maximum_phase_uncertainty` (:97), `append_country_v3` (:121), `forecast_country_fields` (:134), `check_forecast_fields` (:149). Preserve current outcomes even with missing diagnostics.
- `weighted_country_errors` (:59) hardcodes h5 evidence basis in `BASIS`; parameterize if used for other horizons. Do not fabricate zero counts to produce a missing-evidence table: unknown counts/basis/status remain blank.
- Missing entire evidence uses sidecar unavailable/missing_evidence, not the old no_complete_history status. Corrupt supplied evidence remains a failure. Never run old historical h5 wrappers to fabricate support for another horizon.

## Portable archive

- `tools/run_h5_model_delivery.py` hardcodes April/September/5m at :19, score-input names :145–156, mapping :175–179, country lookup :189 and census paths :232. Reuse pure helpers only after explicit scope/path adaptation; do not run its training entries.
- `tools/package_h5_delivery.py:30–38` excludes `scopes/` and includes only three April-named inputs. Its create-only tar/member-hash verification :39–57 is useful, but old training report/pass flags do not validate this delivery.
- Existing runtime copy pattern in `tools/revise_h5_country_v3.py:189–193` copies the model pipelines and `tools/*h5*.py`; a new portable runtime must include actual imports including both country builders, new entrypoint/contract modules and shared helpers. Test after extraction outside checkout with cloud credentials/PYTHONPATH removed.
- September headers are the first lines of ten tables under `Outcome/model_delivery/202609_h5/20260923_country_confidence_v3/{fewsnet,ipcch}/`. Freeze column order rather than copying old rows or fixed counts. Three scopes must each contain both systems' five tables, plus shared geometry/population and six packages.

## Verification hooks

Existing suites: `tests/test_build_{fewsnet,ipcch}_country_level_predictions.py`; FEWS `test_local_package.py`, `test_local_outputs.py`, `test_horizons.py`, `test_preprocessing.py`; IPCCH `test_operational_launch_{feature_contract,inference,cli}.py`; `tests/cloud/test_monthly_assembly_wrapper.py`. `revise_h5_country_v3.selfcheck()` tests arithmetic without a model. `verify_h5_model_delivery.py:121–156` shows relocated score/export, but its h5 assumptions must not become new acceptance requirements.
