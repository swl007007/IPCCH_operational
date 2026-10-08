# September output inventory and cloud reuse evidence

Read-only inspection on 2026-10-07; baseline `4a42f1f666a4f2d5d2616069fe25ddd81f2662cb`. Let V3 be `Outcome/model_delivery/202609_h5/20260923_country_confidence_v3`. No tests, models, or cloud operations were executed. Source-defined behavior and saved verification reports are not new acceptance results.

## Existing files and diagnostic schema

Both systems deliver `polygon_predictions.csv`, `country_predictions.csv`, `polygon_model_mapping.csv`, `country_confidence.csv`, `country_population_reference.csv`, `polygons.geojson`, and `model_package/`. FEWS additionally has `polygon_confidence.csv`; IPCCH has `polygon_training_errors.csv`. Evidence: V3 `manifest.json:82-142,187-247` and actual CSV header lines.

Both country tables carry `country_error_rate`, `country_confidence_flag`, `country_error_basis`, `country_error_weighting`, `country_error_evidence_period`, and support/population fields. FEWS polygon confidence includes `historical_sample_count`, `historical_error_count`, `polygon_error_rate`, `polygon_confidence`, `country_error_eligible`, `evidence_basis`, and `evidence_period`. IPCCH polygon training errors contain only `polygon_id,ISO3,training_sample_count,training_error_count,training_error_rate`; there is no existing status field.

IPCCH country outputs also carry `country_overall_phase`, its availability/method, `country_maximum_phase`, its error-probability proxy and interval bounds, history-month count, uncertainty status, and method. Polygon prediction CSVs do not contain these historical diagnostic fields.

Existing null error/flag behavior is supported by `tools/revise_h5_country_v3.py:44-49` and `tools/verify_h5_country_v3.py:59-60`. Existing maximum-phase statuses are `no_complete_history`, `single_month`, `degenerate_empirical`, and `supported` (`tools/revise_h5_country_v3.py:103-117`). A general literal `unavailable` status is not already established. Use the proposed separate availability CSV to explain unavailable diagnostics without silently changing prediction headers or claiming an old status means something new.

Historical evidence includes `reports/fewsnet_stage3_historical_errors.csv`, `reports/ipcch_four_target_training_replay.csv`, `reports/ipcch_maximum_phase_scenarios.csv`, and coverage/policy metadata. Appropriate model/horizon lineage is required before reuse; September fs1 proxy approval applies to h5 only.

## Bundle behavior

`tools/package_h5_delivery.py:15-27` requires passed verifications and preservation checks. `:30-33` includes system directories, runtime, reports, README/requirements, and three named scoring inputs; raw/history remain outside the portable archive. `:34-38` hard-codes April→September/h5. `:39-50` creates the tar archive exclusively and checks member hashes. `:55-57` writes the full root inventory separately. Adapt the packaging contract to O and three horizons; never reuse the old names/month metadata unchanged.

V3 README `:89-103` defines string IDs, model-specific keys, UTF-8 CSV/blank nulls, month columns, score meanings, and population weighting. `:107-123` records the September Python 3.12.3 environment and exact-discrete/continuous `rtol=0, atol=1e-12` replay comparison. Candidate April model packages require their own environment acceptance; do not assume the old cloud Python 3.11 image or September environment is automatically valid.

## Trigger, duplicate handling, and release

The current documented Cloud Run Job dispatch is manual (`README.md:69-75`). `cloud/orchestrator/main.py:33-68` accepts month/run ID/manifest URI, not a CloudEvent or generation-bound event contract. No tracked Eventarc/GCP Workflows object-finalized deployment or HTTP receiver was found in the focused source/config search; this does not prove absence from live GCP.

`cloud/orchestrator/run_state.py:58-64` acquires `_RUN_PREFIX_ACQUIRED` with `if_generation_match=0`; duplicates raise `DuplicateRunError`, then preflight fails (`cloud/orchestrator/main.py:99-100`). Current behavior is neither successful duplicate acknowledgment nor resumption. Terminal summaries are written at `run_state.py:77-104`; failed prefixes remain reserved. Operator retry currently requires a new run ID.

The existing release writer uses immutable accepted artifacts and a final generation-CAS pointer, but its inventory is IPCCH-specific (`cloud/orchestrator/release.py:91-106,349-363`). Extend inventory handling to the complete dual-system delivery; keep the preservation/concurrency mechanism.

## Existing checks to reuse, not previously executed here

- Manifest: `tests/cloud/test_manifest_contract.py`.
- Run state: `tests/cloud/test_run_state.py`.
- Orchestration/release: `tests/cloud/test_orchestrator_contract.py`, `test_release_writer.py`, `test_release_conflict.py`, `test_release_manifest_contract.py`, `test_release_consumer.py`.
- Input assembly: `tests/cloud/test_monthly_assembly_wrapper.py`, `tests/test_build_monthly_ipcch_base_input.py`.
- FEWS calendar/preprocessing: `tests/fewsnet_partitioned_rf/test_horizons.py`, `test_preprocessing.py`.
- `tools/revise_h5_country_v3.py` exposes a `selfcheck` action (`:440`); full v3 verification requires a root artifact set.
- Do not assume `tools/check_h5_delivery_focus.py` works unchanged: it calls `align_horizon(...,5)` at `:15`, whereas current `tests/fewsnet_partitioned_rf/test_horizons.py:153-155` asserts accepted horizons 0/6/12. Investigate the active API before selecting this checker.
