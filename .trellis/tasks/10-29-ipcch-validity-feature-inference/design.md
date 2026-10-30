# IPCCH operational migration design

Status: planning draft, not execution approval. Requirements and accepted decisions are in prd.md (R1-R66 plus the recorded defaults). This document maps them onto the existing `cloud_pipeline` runtime and the research workspace; exact edits still require GitNexus impact analysis before implementation.

## Boundaries

- Train H2/H8/H14 in food-crisis-research from real historical data, using H0/H6/H12 target-specific hyperparameters respectively, without HPT or oracle inputs. Deliver final evaluation-stage weights; no extra production refit or performance release gate. Train only the final target window 2026-01..2026-10 with H2/H8/H14 label cutoffs 2025-11/2025-05/2024-11.
- Transfer one fixed three-model combination with matching feature schemas into the standalone cloud_pipeline runtime. The research checkout must not become a runtime dependency (.trellis/spec/guides/cloud-handover-layout.md:3-7); converters and tables are ported or delivered as assets.
- Inference consumes weights and prepared features only. CH reference periods and reported-phase snapshots are prepared offline on the research side (R2, R62). No historical replay, rollback or deactivation interface (R20, R46).

## Facts established by inspection (2026-10-29)

- The production IPCCH package in `cloud_pipeline/bootstrap/models/ipcch/scope_{0m,6m,12m}/feature_contract.csv` has 128 features from the legacy wide panel (EVI/FLDAS bands, nightlight, event-level ACLED counts, WFP, WB, static). The new models use the 527-column schema: compact296 + 128 AlphaEarth-2017 descriptors + 114 aggregated-ACLED columns (replacing 14 legacy ones) + 3 local-IDP columns; H6/H12 additionally carried 12 oracle columns, removed for H2/H8/H14, so all three new horizons share one 527-column schema (`control-plane/research_cloud/training/ipcch_validity_features.py:844-863`).
- Schema families and alignment (`ipcch_alphaearth/compact.py`): 13 climate bases (`prcp_anom, prcp_z, rainy_days, cdd, tmean_anom, tmax_anom, hot_days_p95, gdd, edd, sm_z, spi03, spei03, evi_anom`) as `{base}_month_ensmean` at O with trailing ma3/ma6/ma12/sd12, same-month z and stress stems, plus `{base}_gs_ensmean` for the two latest completed seasons; `GPP_mean`, `nightlight_mean`, `WFP_Price`, `food_price_index_WB`, `nino34_anom`, four `bbg_*__composite_mean` composites at O; aggregated ACLED at O-1; national IDP latest report <= O with age; local IDP windows ending at O; five outcome-history features from reports <= O; static29; identifier block (lat, lon, month and year_2014..2026 dummies at the target month). Only ensemble means are consumed; no ensemble SD or source-count column enters the model.
- Research ACLED converter `staging/ipcch-update-202610/tools/build_acled_agg.py`: Saturday weeks labelled by start date, d_m/7 proportional split, exposure max, centroid-to-polygon with override table and 25 km cap, area-weighted overlay, per-country coverage start, hard failure for unmapped admin1, neighbour completeness gate.
- Runtime GPP contract `cloud_pipeline/cloud/batch/remote_sources.py:103-114`: mean from the v3 directory from 2025-01, SD from v2; `http_published_months()` treats 404 as unpublished and everything else as retrieval failure; `prepare.py` records `not_published_months` and `source_coverage.csv`. Provider update log (verified 2026-10-29): annual batches released 2019-12-01, 2021-03-15, 2022-04-29, 2023-04-02, 2024-05-13, 2025-03-30, 2026-08-16 (v3, to 2025-12).
- Runtime manifest `cloud/orchestrator/delivery_manifest.py`: `SCHEMA_VERSION = "fewsnet-ipcch-delivery-request-v1"`, `systems` must equal both systems, `horizons_months` fixed to (0, 6, 12), `acled`/`wfp` keep|refresh with retained_snapshot/raw_upload refs, `execution` block with `inference_systems`, `inherit` and `publication` candidate|current; no wall-clock or current-month comparison exists.
- Runtime publication `cloud/orchestrator/delivery_run.py`: immutable release record plus compare-and-swap write of `current.json`; `_RUN_ACQUIRED` create-only sentinel per run id; the legacy IPCCH-only release root is preserved and never republished. `delivery_job.py:inherit_system()` copies the unscored system byte-for-byte but requires the same origin month and all horizons.
- Runtime inference `model_pipeline/ipcch_launch_runtime/inference.py`: raw scores unclipped, NaN/inf raise, monotonicity policy from package metadata (cummax on binary `_pred` columns), overall phase decode, `[1,5]` integrity gate; packages are per-scope `phase{2..5}_worse_model.json` files, no MLflow at runtime.
- Diagnostics `cloud/orchestrator/delivery_outputs.py`: `maximum_phase_diagnostics()` with seed 20260923, 10,000 replicates, 2.5/97.5 percentiles; missing evidence yields status unavailable/reason missing_evidence; evidence bytes are hash-verified.
- Retained stores today: `bootstrap/assets/retained_acled.csv` and `retained_wfp.csv` hold both systems keyed by `system`; `assets/ipcch/{fixed_features.csv, history_panel.csv, population.csv, roster.csv (6,227 rows), geometry.geojson, history/{evi,fldas,gosif_mean,gosif_sd,viirs}.csv}`. The training roster is 6,226 admin_codes.
- Shared-folder climate scripts implement source processing and SPI/SPEI ensembles (equal valid-source means, population SD, SD missing below two sources); method identifiers are not recorded in the research repo either (R40).

## Model combination package

- Research output per horizon: `weights/h{02,08,14}_supp_2026/{q2..q5}.ubj` with calibration and record files, `deps/feature_order.csv`, resubstitution and residual evidence. A research-side packaging step converts this into the runtime layout: `scope_0m` = H2, `scope_6m` = H8, `scope_12m` = H14, each with `phase{2..5}_worse_model.json`, `feature_contract.csv` (527 rows, identical order per horizon), `model_metadata.json` (`monotonicity_policy: cummax`, thresholds, `model_horizon_months`, `public_lead_months`, `feature_origin_offset: -2`).
- Package manifest (R51): sha256 of every file, per-horizon schema hash, diagnostic evidence references (`polygon_training_errors`, `maximum_phase` residuals per horizon, R31), training run ids and cutoffs, `status: candidate|accepted`, acceptor, date. Fixed assets travel with the package: roster (6,226), geometry, static29 and AE128 fixed features, population reference, ACLED mapping/override/coverage-start/neighbour tables (R55). Real mode requires `accepted` and verified checksums; smoke accepts `candidate`.
- The existing equal-schema replacement gate (`pipeline.py` ~1515-1530, `operator-model.json feature_schema_sha256`) is replaced by package-manifest verification: a combination is selected explicitly by reference (R11) and must match the installed package; schema equality with the previous package is no longer required.

## Request contract (new version)

- New `schema_version` value; legacy v1 requests keep the existing validator and runtime path (R37).
- Fields: `run_id`; `mode` (smoke|real, required, no default); `execution_month` M; `operations` with the four booleans (at least one); `ipcch` block: `model_combination`, `feature_batch` (inference-only), `acled` keep|refresh{file ref, start, end, regions}, `research_inputs` per family keep|refresh{file ref, start, end} (R59), `history_snapshot` keep|refresh{file ref} (R62), `wfp` keep|refresh (R64); `fewsnet` block: `prepared_snapshot` (inference-only, R60), existing `acled`/`wfp` choices; `publication` candidate|current (R66); `operator`, `prepared_at`, existing cutoff/deadline fields.
- Validation order, all before any collection, store mutation or inference (R17): structural; mode rules (R38: smoke selects no FEWS NET operation; smoke never `publication: current` to production); operation conflicts (R19: generation plus inference with a batch reference, inference-only without a batch, inference-only with any IPCCH input refresh: ACLED, research_inputs, history_snapshot or WFP); derived dates (R23) and M rules (R39: M later than the UTC calendar month; real IPCCH inference with `publication: current` and M earlier than the IPCCH execution month in the current release); immutable reference identity for every referenced file/batch/package; per-system lock (R50); admission.
- After formal activation, v1 requests that include IPCCH (including mixed) are rejected with a migration message; FEWS NET-only v1 requests remain valid; their required `inherit.ipcch` must name the current release's IPCCH member, and a new-contract member is checked under R63 instead of the v1 same-month, (0, 6, 12) target-period and installed-package checks (prd.md, Final convergence corrections).

## Run mode

- Smoke: isolated namespace with its own pointer and stores (R36, R48); all source inputs, acceptance records, mapping subsets and the roster subset come from the fixture store; the only shared input is the model package. Prediction tables and run summaries carry `mode=smoke`. Validation code paths are identical.
- Real: production namespace; rejects dummy-marked inputs, batches and candidate packages; `publication: candidate` writes an immutable delivery without moving the pointer (R66); generation-only never touches prediction current.

## Monthly flow

1. Operator submits the manifest; validation and admission as above; lock acquired per selected system.
2. IPCCH feature generation (real): ACLED keep/refresh (R27-R29, R44, R53, R55, R56); research-prepared family and history-snapshot keep/refresh (R59, R62); WFP keep/refresh through the existing converter on IPCCH rows (R64); climate incremental update through the ported shared scripts for every completed month not yet saved, with per-indicator-month persistence (R8, R34, R41, R43), method identifiers recorded (R40); GPP v3 append with availability ledger and fill-only-unpublished exception (R9, R49, R54); nightlight VIIRS append on the fixed geometry (R64); growing-season eligibility (R33).
3. Feature assembly on the fixed roster (R32) for each horizon using the package feature contracts; required columns are always emitted, with NaN and a recorded reason where a family is optional-missing (R65); duplicate keys and missing rows fail.
4. Batch write (R52): immutable, unique id bound to the run id; metadata records M, O, mode, model combination, method identifiers, per-family coverage end months, source-level gaps, missingness counts, acceptance records consumed, retained-input references (R28); summary file for generation-only.
5. IPCCH inference: batch validation (R19, R32, R36); scoring through the existing inference path (R61); diagnostics from model-matched evidence (R31); nonfinite scores fail the run (R18).
6. Publication: all three horizons together (R18); single pointer with cross-system inheritance of the other system's members and their own months (R63); M regression recheck and legacy-cutover check immediately before the pointer compare-and-swap (R37, R39); candidate skips the pointer move (R66). Activation is derived from the current release record, so it cannot diverge from publication.
7. FEWS NET: generation = existing prepare producing a prepare_id; inference = existing deliver with an explicit prepared_snapshot; scientific logic unchanged (R6, R60).

## Retained stores and acceptance

- New IPCCH stores, separate from the shared `retained_acled.csv`/`retained_wfp.csv`: climate monthly and growing-season ensembles per base, `gpp_mean` with availability ledger, `nightlight_mean`, `wfp_price`, `acled_agg_weekly` with coverage metadata, `nino34`, `bbg_composites`, `food_price_index_wb`, `idp_national`, `idp_local`, `history_snapshot`. Legacy IPCCH rows in the shared files remain untouched for the legacy entrypoint.
- Acceptance manifest (R45): one append-only record per accepted file (path, sha256, source description, acceptor, date, kind delivered|runtime). Real generation refuses unrecorded or mismatched historical inputs; runtime-saved months append `runtime` records. Smoke uses the fixture store's own records.
- Initial history for GPP, WFP, nightlight and the R59 families is delivered from the training panel (R54, R59, R64); ACLED starts from the first validated real refresh (R44); the reported-phase snapshot is delivered by the research label scripts (R62).

## ACLED

- Reject IPCCH inference-only plus any IPCCH input refresh (ACLED, research_inputs, history_snapshot, WFP) before mutating source data; refresh belongs to IPCCH generation.
- Converter ported from `build_acled_agg.py` with its fixed tables delivered in the package (R55). Validation: Saturday week labels, all weeks within the declared interval, declared regions covering the mapping table's regions, rows outside interval/regions rejected, unmapped or >25 km admin1 rejected (R26, R56). Replacement of the declared interval at week level, outside history preserved (R25). Month completeness requires declared interval/region coverage of every overlapping week, not event-row presence (R56); first refresh must cover the R44 lookback through O; subsequent short coverage is recorded and warned under R53. Failed refresh leaves history intact; successful refresh becomes the keep baseline even if downstream fails (R27-R29). FEWS NET retains its event-level ingestion and retention semantics.

## GPP

- Operational: v3 mean contract append; 404 or absence from the authoritative listing is `unpublished` in the ledger; other errors block (R49). Published months fill earlier unpublished gaps without overwriting (R9). SD is not fetched for IPCCH.
- Training preparation: per-row availability filter from the provider update log with GPP unavailable for simulated run dates before 2019-12-01 (not a permanent exclusion of earlier source months) and correction entries recorded as caveats (R57). Resulting sparsity documented.

## Single-source ensemble contract and seasonal eligibility

- With one valid source the ensemble mean equals that source, n_sources=1, between-source SD missing (R34). Only completed seasons by the end of O are eligible, selecting the two most recent (R33).

## Geographic coverage

- Fixed roster of 6,226 training admin_codes pinned in the package; the production roster file is not reused. Real batches must contain every roster area; unknown ids and duplicate keys fail; the smoke subset is declared explicitly (R32).

## Concurrency

- Per-system create-only lock object at the fixed namespace key locks/{system}, shared across run ids with owner run_id in its content, released at run end, cleared only by an operations action (R50); existing `_RUN_ACQUIRED` and pointer compare-and-swap guards remain. Different systems may run concurrently.

## Training work (research side)

- Final-stage contexts only, with the accepted cutoffs and H0->H2, H6->H8, H12->H14 hyperparameter mapping (R4, R10); oracle features removed (R7); alignment unchanged (R65); year dummies retained (R58); GPP filter (R57); real inputs only (R15). Outputs: weights, feature order, resubstitution confidence evidence and residual evidence per horizon (R31), packaged as one candidate combination (R51). Cloud execution requires a separately authorized packet (R30).

## Initial verification

- Local smoke with fixtures and fake object store, isolated namespace, declared small roster subset across at least two countries, candidate or accepted real package (R42), both IPCCH operations separately and combined, isolated current replacement and failure preservation, mode=smoke labels, no retained real store access (R14, R16, R48). FEWS NET regression through the legacy entrypoint and the new manifest's FEWS NET operations.

## Compatibility changes authorized in requirements

- Global remote preparation coupled across systems, H0-only IPCCH source-column selection, equal-schema model replacement gate, same-month inheritance gate, initialization-only ACLED keep, fixed `systems`/`horizons_months` request shape, absence of mode and wall-clock checks, and shared retained ACLED/WFP files for IPCCH require targeted migration. FEWS NET scientific logic, its request shape and retained results stay intact.

## Final QA/merge excluded

- Upstream final Colab QA/merge is out of scope and not a publication prerequisite (R35). Baseline climate assets use runnable smoke placeholders until replaced by real inputs; delivered scripts' methods are used as-is with identifiers recorded (R40).

## Convergence verification

Apply the final convergence corrections in prd.md to request validation, snapshot replacement, lock acquisition, all current publication paths and candidate promotion. Tests must cover each corrected boundary, including concurrent CAS failure without automatic retry, preservation of activation through legacy FEWS publication, fixture acceptance validation, and event-free covered ACLED weeks.
