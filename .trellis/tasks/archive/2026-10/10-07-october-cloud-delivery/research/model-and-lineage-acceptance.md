# Candidate model environment and feature lineage acceptance

Read-only investigation on 2026-10-07; code baseline `4a42f1f666a4f2d5d2616069fe25ddd81f2662cb`. No model deserialization, training, prediction, raster computation, or cloud operation. Main-agent checks directly inspected the runtime validator, climate normalization, IPCCH median application and selected notebook source cells. Notebook references below use zero-based cell indices and one-based lines within the cell.

## 1. Candidate environments and imputers

FEWS candidate root: `Outcome/fewsnet_partitioned_rf/model_artifacts/local-202604-57cb3b981198-510375f58cd8`.

All three `{0,6,12}m/local_model_manifest.json:2-8` specify:

| Dependency | Required version |
|---|---|
| Python | 3.12 (major.minor comparison) |
| numpy | 2.4.2 |
| pandas | 3.0.0 |
| scikit-learn | 1.8.0 |
| joblib | 1.5.3 |
| imbalanced-learn | 0.14.0 |

`fewsnet_partitioned_rf_pipeline/local/package.py:683-685` validates the runtime before `joblib.load`; `core/validation.py:121-142` checks exact recorded dependency versions. The existing `docker/Dockerfile.fewsnet-partitioned-rf:1` uses Python 3.11 and is incompatible with that loader contract. Preserve the compatibility check; build the proposed delivery runtime for accepted packages instead of suppressing it. `requirements-fewsnet-partitioned-rf.txt:1-5` agrees with the five package versions.

FEWS inference uses the saved `PartitionedRFPredictor.imputer` and its `transform` (`core/inference.py:176-186,249-251`). `MaxPlusImputer.fit` records per-column values: all-missing → 0, maximum zero → 100, otherwise maximum ×100 (`core/preprocessing.py:643-670`); transform treats infinities as missing and uses those saved values (`:672-690`). This is an existing model rule, not permission to add a generic zero fallback to cloud assembly. Actual saved values remain unverified without loading the package.

All twelve IPCCH JSON models under `model_artifacts/launch_2026_04/scope_{0,6,12}m` declare model JSON `version=[3,2,0]`. Metadata records training-median imputation, including saved `median:<feature>` values (`model_metadata.json:36-38` onward). No complete Python/numpy/pandas training environment was found in those metadata. Runtime applies saved medians through `model_pipeline/ipcch_launch_runtime/feature_contract.py:318-345`. XGBoost serialization version alone is not a complete executable environment acceptance.

A common proposed runtime is Python 3.12 with the FEWS exact dependencies and XGBoost 3.2.0, subject to IPCCH numerical replay and geospatial-library compatibility. Do not claim this environment is tested, or automatically fork environments before demonstrating a conflict. Candidate manifests point to an external normalization audit; its exact content/hash must be included in model acceptance rather than silently using a newer audit with the same filename.

## 2. FEWS calendar and normalization facts

- `core/normalization.py:20-30` names `deduplicate-before-global-rolling-zscore-v1`, source climate columns, window 12, min_periods 1, ddof 1.
- Stable order is admin/date/source-row (`:171-173`); after duplicate collapse, `.rolling(12)` runs over the entire table and then per-admin mean/SD is calculated over those rolling values (`:217-226`). It can cross admin boundaries and is not a saved train-time scaler. Extending the panel can change historical normalized values. Preserve the named operation for an explicit, cutoff-bounded snapshot and assess its compatibility; changing to grouped causal climate normalization is a separate scientific change.
- Package feature contracts include year_2026 and month_10 (`0m/feature_contract.json:82-110`); `core/preprocessing.py:476-485` rejects unseen input years/months. O=2026-10 is supported by the saved categorical vocabulary. Future target years do not require inserting 2027 input rows; target calculation is `feature_month + horizon` (`core/inference.py:233-247`).
- `Stage3FeatureBuilder` requires raw columns and unique normalized admin/month keys (`core/preprocessing.py:420-461`), and rejects unseen ISO (`:468-471`). The raw numeric `month` predictor must agree with parsed `date`; existing source does not itself prove that equality (`:71-84,514-524`). Add it to input acceptance.
- Target-derived lags use exact calendar joins at 4/8/12 months (`:48,311-325,530-543`), without forward/back filling of the label column. For O=2026-10 these source months are 2026-06, 2026-02 and 2025-10. Missing labels remain missing until the saved feature imputer acts. The October true target is not required as an observed predictor, though raw label columns must exist.
- Prior WFP 4-month window needs 2026-06..09; WFP/nightlight 12-month windows need 2025-10..2026-09. Rolling uses reindexed calendar months, shift(1), and a complete window (`:329-364`). EVI lag1..12 needs 2026-09..2025-10 (`:50,558-563`). No sparse-row substitutes.

## 3. Proven CH branch mapping

Notebook: `archive/notebooks/Final_harmonise/00_combine_all_ch.ipynb`.

| Saved feature name | Proven CH input and transformation |
|---|---|
| `GPP_mean` | `GOSIF_GPP_extraction_results_ch.csv` loaded cell 0:28, melted to `GPP_mean` cell 45:3; provider Mean raster region MEAN. |
| `GPP_std` | `GOSIF_GPP_extraction_results_SD.csv` loaded cell 0:29, melted to `GPP_std` cell 45:46; `GOSIF_GPP/02_arcpy_extract_gosif_gpp_sd.py:67,71` takes MEAN of the provider SD raster. |
| `nightlight_mean` | `nightlight_sum_extraction_results.csv` loaded cell 0:14; melted to `nightlight_mean` cell 24:2. `VIIRS_nightlight/03_arcpy_extract_viirs_nightlight.py:67,122` produces SUM, despite the resulting feature name. |
| `nightlight_std` | `nightlight_std_extraction_results.csv` loaded cell 0:13; melted to `nightlight_std` cell 32:2; regional STD in VIIRS extractor `:70,123`. |

The relevant CH cells show no area division, log or physical-unit scaling. They do show additional transformations:

- GPP columns sorted by region/year/month, whole-column forward-filled, zero-filled, negative-clipped, deduplicated and `region_id` renamed to `admin_code` (cell 45:19-29,57-67). After keyed merge, another whole-column fill occurs (:37-43,73-77).
- Nightlight SUM follows whole-column fill/zero fill (cell 24:12-18), negative clipping and ID rename (cell 25:3-5), coordinate lookup/rounding and lat/lon/month merge (cells 26–28). SD uses an ID/month merge (cell 32:11-24). Cell 72:3-4 again forward-fills both columns globally.

**Do not copy these global fills/zero substitutions into the new pipeline.** They conflict with the user's approved area-specific causal fill policy. Preserve historical artifacts, isolate the intentionally changed missing-value behavior in validation, and compare local/cloud results using the same newly approved inputs. Pure equality with these old notebook fill outputs is not an acceptance target. Negative clipping is a separate upstream transformation that requires canonical lineage evidence; it is not the same as IPCCH output-score clipping (which remains prohibited).

## 4. Canonical lineage gaps and zone-key risk

- CH outputs `chcountries_final_v12022025.csv` (cell 77:2), processed by `01_CH_final_process.ipynb` into `CH_final_v12102025.csv` (cells 1:2,17:2). The raw-to-CH column mapping is established; the write path combining final IPC/CH outputs into canonical `Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv` was not found.
- IPC branch `00_combine_all_IPC.ipynb` cell 0:13,19 instead reads `DMSP_OLS/old_methods/IPC_nightlight_completed_final.csv` and `GOSIF_GPP/old_methods/IPC_GPP_complete.csv`; its final processing retains `nightlight,nightlight_sd,gpp_sd,gpp_mean`. Generation/standardization of those intermediates was not found in this bounded investigation.
- FEWS saved contracts name `gpp_mean,nightlight,nightlight_sd`, but no keyed evidence connects the FEWS training panel to the repository's current extraction scripts. The shared names alone do not prove the source/reducer.
- The template uses current `ipcch_admin_geometry.shp` and `zone_field=fid` for GOSIF/VIIRS (`config/paths_template.ini:4,59,66`). Bounded DBF inspection found 6,227 records and only persistent fields `admin_code,lat,lon`; first admin codes were `0,1,10`. An ArcGIS implicit FID is not proven equivalent to these native IDs.
- The CH notebook renames `region_id` rather than showing a crosswalk. `tools/reshape_remote_sensing_wide_to_long.py:40-61` supports explicit mapping and rejects unmatched IDs, but use of that helper to build the saved canonical panel is unproven.

Do not treat geometry record order as model identity. New extraction should key on explicit accepted native IDs, or a verified crosswalk with complete/unique coverage. The mapping and reducer gaps are acceptance blockers for the affected cloud adapters; report them precisely instead of guessing, training around them, or labeling a schema match as numerical equivalence.

## 5. Gate disposition

Model environment requirements and October calendar needs are now evidenced. Runtime/model replay remains execution-time verification. CH feature naming is evidenced, but canonical IPCCH/FEWS lineage and the historical zone mapping remain incomplete. Further investigation may use pinned upstream exports, build manifests or keyed paired reference rows; absent such evidence, affected extraction must stop and return to design. No choice to change predictors or silently accept a different scientific definition has been delegated to an implementer.
