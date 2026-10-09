# Monthly delivery input contracts

## 1. Scope / trigger

Applies to the dual-system October delivery path. Keep the IPCCH-only manifest and September callers compatible. Full product contract: `.trellis/tasks/archive/2026-10/10-07-october-cloud-delivery/design.md`. Historical lineage investigation is explicitly waived; fixed features are reused and current repository remote scripts are the construction baseline.

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

## 8. Scoring, delivery and replay

The delivery origin is fixed independently of provider lag: October 2026 emits 0/6/12-month targets October 2026, April 2027 and October 2027. Reuse the six saved packages without fitting. FEWS scores the necessary calendar window while retaining full-history identity/population observations; IPCCH partitions assembly by native area with unchanged calendar/fill arithmetic. Streaming changes must preserve the unpartitioned output and audit semantics.

The bundle contains exactly 30 scope CSVs, two population references, both native geometries, six packages, frozen scoring inputs, runtime and dependency lock. Unsupported diagnostic estimates stay blank with explicit availability reasons; country current outcomes remain populated. Supported diagnostic evidence is package/horizon-specific: FEWS uses its recorded validation period, IPCCH training resubstitution ends at its package training cutoff. IPCCH raw scores remain unclipped.

Diagnostic evidence binding (2026-10-09):
- Evidence CSVs live in `bootstrap/evidence/` with `provenance.json`; `baseline.json` lists them in `files` and declares each family available.
- Changing evidence changes the baseline ID, so use a fresh work_dir/init. Model package members never carry evidence.
- Current status: all 15 declarations are available. IPCCH 0/6/12 use `training_resubstitution`: area counts plus phase2..5 residuals, replayed from the original training panel (sha `ae696087…`), not the refreshed bootstrap panel.
- FEWS 0m/6m/12m use user-approved Stage3 research-run proxies, accepted only through `delivery_outputs.APPROVED_PROXY_EVIDENCE`. The exact (horizon → basis, period) pairs are 0m → `h0_validation_error_proxy_stage3_fs1_lag4_2021_2024` (a 4-month-lag proxy, more pessimistic than true 0m error), 6m → `h6_validation_error_proxy_stage3_fs2_lag8_2021_2024` and 12m → `h12_validation_error_proxy_stage3_fs3_lag12_2021_2024`, all with period `2021-02..2024-10`.
- The runtime image must contain this allowlist. The baseline runtime and the six acceptance records bind `runtime:cp5-confidence-1@sha256:7e6133f3…`, accepted on 2026-10-09 because its real-cloud October rerun reproduced every prediction of the earlier image. The Cloud Run job image and the workflow `DELIVERY_IMAGE_URI` must name the same digest; the job rejects a request whose runtime differs.
- A rerun that reuses a release namespace must use the current pointer generation as the expected generation. A copied `0` fails at release after scoring.
- Any other FEWS basis or period, a proxy on another horizon, and the h5 basis are all rejected. The basis string is the disclosure.
- Evidence builders are one-time offline scripts in `.trellis/tasks/archive/2026-10/10-09-sept-6m12m-confidence/research/`. They must reproduce the accepted h5 evidence (fs1 counts; h5 resubstitution counts and residuals) before emitting new evidence.

Wrong: relabel a proxy as `package_validation_split`, or score historical rows with the final FEWS model. Correct: add the exact pair to the allowlist only after an explicit user decision, with tests for wrong-horizon/period rejection.

Validate native keys, identities, dates, scope inventory, country aggregation, package contents and diagnostic consistency before archiving. Regenerate diagnostic tables and availability from frozen evidence. Seal every inventoried file before create-only archive upload. Offline relocated replay uses the bundled runtime and frozen inputs without repository or cloud access, comparing all 30 tables and the availability table; IDs/discrete values and blank masks are exact, continuous tolerance is at most `atol=1e-12, rtol=0`.

## 9. Automatic entry and operations

Storage finalized events are filtered to the exact request path. Workflows submits Cloud Run with the event generation plus all deployment-configured arguments and does not poll the operation; durable run status is authoritative. Container overrides replace the entire argv. Task retries are zero. An identical request returns its original status; changed content under the same run ID conflicts. Failed attempts are retained and retried only with a new ID.

The entry verifies prepared status, origin, current extraction contract, roster and geometry, and consumes the operator's keep/refresh choices. Keep binds the actual retained history-family projection. Package member conflicts fail before scoring. Artifacts upload create-only; transient GCS failures have a bounded retry budget, with existing-object recovery limited to matching size and CRC32C transport checks. Immutable release record and pointer generation CAS are written last. The October deployment uses `oct-staging`; production consumer cutover is separate.

Operational commands and the actual staging resource names are documented in `deploy/october_delivery/README.md`. Fixed assets are reused; do not introduce historical provenance investigations. Source lag, filled features and unavailable diagnostics are disclosed in delivery reports. Checkpoint evidence distinguishes smoke from full-roster preparation and records actual event/job results. Use Windows Git for repository operations when WSL Git encounters the observed DrvFS I/O failure.
