# Monthly delivery input contracts

## 1. Scope / trigger

Applies to the dual-system October delivery path. Keep the IPCCH-only manifest and September callers compatible. Full product contract: `.trellis/tasks/10-07-october-cloud-delivery/design.md`. Historical lineage investigation is explicitly waived; fixed features are reused and current repository remote scripts are the construction baseline.

## 2. Signatures

- `tools.refresh_h5_inputs.wfp_aggregates(path, cutoff="2026-04")` and `conflict_aggregates(path, cutoff="2026-04")` return aggregates and coverage reports.
- `apply_source_choices(frame, system, wfp, acled)` uses `None` to retain the corresponding pinned family; WFP aggregates are selected by system.
- `carry_forward_base_series(observations, *, system, id_column, month_column, feature_columns, roster, months, source_ref)` returns a filled base grid and base audit.
- `bind_model_features(base_audit, dependencies, *, feature_month, horizon_months, model_package_id, final_missing, imputation_rules)` records final-feature provenance. Dependencies map final feature to `(source_feature, lag_months)`; `final_missing` is the actual pre-imputation feature-matrix missingness indexed by native polygon ID.
- `validate_delivery_request(data, *, request_uri, request_generation, expected_release_namespace=None)` performs structural validation only. `verify_reference_identities(request, resolve)` separately checks exact generation/checksum via the resolver.
- CP2 `python -m cloud.orchestrator.prepare plan` reads a version-pinned preparation request, freezes discovery/history into a plan and submits Batch; `prepare extract` consumes exact plan URI/generation/hash. Existing `BatchJobConfig.worker_module` defaults to the old EVI worker; the new extraction sets its module explicitly and task retries to zero.

## 3. Contracts

Object refs require `uri`, positive-string `generation` and lowercase `sha256`. The request path is `requests/{run_id}/run_manifest.json`; request generation comes from the event. Systems are exactly fewsnet/ipcch, horizons integer 0/6/12. Models and diagnostics cover every required system/horizon/family. Unavailable diagnostics use explicit `evidence: null`, status and reason. `prepared_at` contains date, time and UTC `Z`. A structurally valid manifest is not accepted model/preparation/runtime evidence.

Native IDs stay strings, including leading zeros. Fill only within the same ID from observations at or before the dependency month. Entirely absent features return missing values and `no_eligible_history`, not an as-of join error. Base gaps stay missing until existing builders compute final features; the saved model imputer acts only on those final features. Audit carries source URI/generation/hash, package ID, base fill method and final `feature_value_method` independently.

Preparation binds immutable history per source/system, geometry/roster and discovered provider identity. History and new observations obey min(origin, last month completed by cutoff). EE acquisition uses the discovered image ID, with explicit named FLDAS bands; GOSIF retains raw compressed bytes/hash. Raster mosaics preserve real masks and valid zero values by setting an explicit floating NaN destination nodata on merge. Current mappings are FEWS nightlight mean, IPCCH nightlight sum, and regional mean of provider GOSIF SD. Both native rosters remain separate.

Latest-source discovery is independent of the baseline's first/last rows: search to the product's catalog start and fetch the actual latest eligible product even when baseline rows extend later. Later history rows are excluded from observation coverage and recorded as `history_beyond_provider_vintage_excluded`; preserved input bytes are unchanged. No age cap rejects successful discovery of an old latest product. Delivery must apply the same exclusions when combining pinned history with new observations. `SYSTEM_FAMILIES` includes only consumed source families; FEWS does not require a GOSIF SD snapshot.

## 4. Validation and error matrix

| Condition | Behavior |
|---|---|
| Malformed raw/date/key or unknown system | `ValueError`; no output release |
| Unknown/duplicate native IDs, duplicate month keys, Inf observation | `ValueError` |
| Missing final feature without applicable saved rule | `RequiredInputUnavailable` |
| Bad manifest shape/type/null policy | `DeliveryManifestError` |
| Referenced generation missing or checksum differs | `ReferenceIdentityError`; never convert to unavailable diagnostics |
| Missing base history with valid final-feature rule | Keep base observation date null; record final model imputation |
| History after completed-month cutoff or unknown raster CRS | Fail preparation |
| Batch submission/provider/extraction failure | Preserve failed status and existing evidence; retry under new prepare ID |
| Duplicate preparation/extraction ID | Create-only sentinel prevents repeated work |

## 5. Good / base / bad cases

- Good: September EVI carries to October for the same polygon with one-month staleness; target origin remains October.
- Base: keep/keep preserves both families exactly. Existing September cutoff defaults preserve caller behavior.
- Bad: January and March WFP prices must not imply a March monthly change without February; future EVI must not backfill earlier months. A float horizon or date-only preparation cutoff is rejected.

## 6. Required checks

Use `tests/test_refresh_h5_inputs.py`, `tests/cloud/test_causal_fill.py`, `tests/cloud/test_delivery_manifest.py` and existing manifest/run-state/release regressions. Assert four source choices, unchanged unrelated columns, Forecast exclusion, exact calendar matching, no cross-area/future fill, whole-column absence, final-feature rule identity, explicit null diagnostics and reference failures. Real v3 converter equivalence is separately recorded in task research. Do not claim live GCP or model acceptance from these tests.

CP2 adds `tests/cloud/test_remote_sources.py` and `test_prepare.py`: real tiny GeoTIFFs including a valid zero and a separately masked cell, named multiband reductions, duplicate/failed preparation, historical cutoff, pinned generation/request hash and production-acquirer SDK mocks. `test_cloud_batch_evi_worker.py` protects the old launcher default. Live cloud evidence is a separate checkpoint.

Provider-vintage regressions cover successful latest discovery before the baseline start, re-extraction of the latest month despite a later baseline, exclusion of later filled rows, and per-area fallback when the new raster has no valid pixel. The production HTTP fake verifies that discovery actually reaches the older published URL.

## 7. Wrong vs correct

Wrong: substitute a saved `EVI_lag3` imputation value into base EVI, recompute a lag and label it observed. Correct: leave missing base EVI with no observation date, build `EVI_lag3`, then apply and record that package's saved rule for `EVI_lag3` if needed. No fallback invents raw measurements.
