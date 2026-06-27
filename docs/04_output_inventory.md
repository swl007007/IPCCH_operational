# Output Inventory and Data Handover Manifest

## Workflow Output Contracts

| Workflow | Current/proposed output | Identifier | Shape | Downstream consumer |
| --- | --- | --- | --- | --- |
| EVI | `EVI_mean_extraction_results.csv`, `EVI_std_extraction_results.csv` | `region_id` mapped from ArcPy zone field | Wide monthly | Normalize with `tools/reshape_remote_sensing_wide_to_long.py`, then merge into monthly IPCCH input assembly. |
| FLDAS | `FLDAS_mean_extraction_results_p*.csv`, `FLDAS_std_extraction_results_p*.csv` | `region_id` mapped from ArcPy zone field | Wide monthly-band, split by part | Normalize with `tools/reshape_remote_sensing_wide_to_long.py`; apply band-to-feature naming before final assembly. |
| GOSIF-GPP | `GOSIF_GPP_extraction_results_ch.csv`, `GOSIF_GPP_extraction_results_SD.csv` | `region_id` | Wide monthly | Normalize with `tools/reshape_remote_sensing_wide_to_long.py`, then merge into monthly IPCCH input assembly. |
| VIIRS nightlight | `nightlight_sum_extraction_results.csv`, `nightlight_std_extraction_results.csv` | `region_id` | Wide monthly, usually one target feature month for production updates | Normalize with `tools/reshape_remote_sensing_wide_to_long.py`, then merge into monthly IPCCH input assembly. |
| ACLED | `ch_with_merged_acled_metrics.csv` or configured equivalent | scaffold spatial/time keys | Scaffold plus features | Final harmonise. |
| FAO | `ch_with_matched_markets.csv`; `ipcch_with_matched_markets.csv` may also be written as a legacy alias | scaffold spatial/time keys | Scaffold plus features | Final harmonise. |
| World Bank | `ch_WBG_completed.csv` or configured equivalent | country/year plus scaffold keys | Scaffold plus features | Final harmonise. |
| WFP | `ch_WFP_prices.csv` or configured equivalent | country/month plus scaffold keys | Scaffold plus features | Final harmonise. |
| IPC API | `areas_*.geojson`, `analyses_*.json`, combined files | IPC API identifiers | Per-year and combined JSON/GeoJSON | IPC reference processing. |
| Unified IPCCH monthly model input | `Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_YYYYMM.csv` plus `_summary.json` | `area_id`, `year`, `month` | Long monthly base input surface | Combined with exported model weights, model pipeline, and G-07 transformations when those assets are exported. |

## Required Local Reference Files

| File | Handover location | Required check |
| --- | --- | --- |
| `polygons_and_identifier/country_scope_ipcch_2026.csv` | Generated from `Google fund/Analysis/1.Source Data/assembled_IPCCH/raw/IPCCH_2026_completed.csv` | 53 data rows; unique `ISO3`; SHA-256 `f0609280a0c89b3db01fc19cd8a6be1bb31356df613d74ea931180aef90b6d09`. |
| `Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv` | Copied from `Google fund/Analysis/1.Source Data/assembled_IPCCH/raw/IPCCH_2026_completed.csv` | 1,219,868 data rows; no duplicate `(admin_code, lat, lon, year, month)` keys; covers 2010-01 through 2026-04; SHA-256 `ae696087c3bbb280537ae269a05924133acdb51060d31290523404fa8a717673`. |
| `Outcome/ipcch_unified/interim/ipcch_scaffold_202604.csv` | Generated with `tools/build_monthly_ipcch_scaffold.py` from the multi-month reference scaffold | 6,227 data rows; one target month, 2026-04; columns `admin_code`, `lat`, `lon`, `year`, `month`; SHA-256 `199882aae1151836efd159a2a3506d9183449b5b1b39047daee6dea5a21961f4`. |
| `Outcome/ipcch_unified/interim/ipcch_scaffold_202501_202604.csv` | Copied from `Google fund/Analysis/1.Source Data/assembled_IPCCH/interim/ipcch_scaffold_202501_202604.csv` | Reference/batch scaffold, not required for monthly production; 99,632 data rows; columns `admin_code`, `lat`, `lon`, `year`, `month`; SHA-256 `e4cda142a0b3adf2dac8e31c16a3450690e42d5d61b1e79ec6c1ede4c9a8ce2e`. |
| `Outcome/ipcch_unified/spatial/unique_area_id_lat_lon.csv` | Copied from `Google fund/Analysis/1.Source Data/assembled_IPCCH/spatial/unique_area_id_lat_lon.csv` | 6,227 data rows; columns `area_id`, `lat`, `lon`; SHA-256 `3bf8f115ec70cd1e1c907031309b797410a8024cdc1d39265be123ae636d2862`. |
| `Outcome/ipcch_unified/spatial/ipcch_admin_geometry.*` | Copied from `Google fund/Analysis/1.Source Data/assembled_IPCCH/spatial/ipcch_admin_geometry.*` | Shapefile package copied with `.shp`, `.dbf`, `.shx`, `.prj`, `.cpg`; see `Outcome/ipcch_unified/MANIFEST.md` for checksums. |
| `Outcome/ipcch_unified/country_area_id_lookup.csv` | Copied from `Google fund/Analysis/1.Source Data/assembled_IPCCH/country_area_id_lookup.csv` | 6,227 data rows; SHA-256 `e2baf6ae9481b42b127db5ce81f3c53ad784bb08ae56dfa56cea74e416b44c90`. |
| `Outcome/ipcch_unified/country_region_mapping.csv` | Copied from `Google fund/Analysis/1.Source Data/assembled_IPCCH/country_region_mapping.csv` | 53 data rows; SHA-256 `40442e0de598511e1fe379335af0d65b33b02e25a5458b79170542f6c67d1e32`. |
| `Outcome/ipcch_unified/features/ipcch_fixed_slow_features_by_area.csv` | Generated from `Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv` plus the coastline distance source with `tools/build_ipcch_fixed_slow_features.py` | 6,227 data rows; 48 columns; unique `area_id`; `coastline_dist` has 0 missing rows; SHA-256 `89bbda8680b98bc6edddea3fa19f863dadb52dbb0ad88ed09e15997d006ba482`. |
| `Outcome/ipcch_unified/features/ipcch_fixed_slow_features_summary.csv` | Generated with the G-03 fixed/slow feature asset | 36 data rows; `coastline_dist` is complete for all 6,227 areas; SHA-256 `2ae4884a4e4cbfa5ff133f58a353d52249a5e248a1773f9e7b29527298ad8fb1`. |
| `Outcome/ipcch_unified/metadata/ipcch_fixed_slow_source_vintage_manifest.csv` | Generated with `tools/build_ipcch_source_vintage_manifest.py` from G-03 summary, IPCCH codebook, local `1.Source Data` folders, coastline distance source, and FEWS NET paper data-section evidence | 8 data rows; one row per fixed/slow feature family; SHA-256 `ee94d12de508651b93817c40304249e69caf25c1dec67aaef7bdac11fc09dcb6`. |
| `Outcome/ipcch_unified/metadata/variable_codebook_reorganized.csv` | Copied from `Google fund/Analysis/1.Source Data/assembled_IPCCH/metadata/variable_codebook_reorganized.csv` | 168 data rows; used by G-05 schema and feature-family contract; SHA-256 `4d917eee94119cf309fd66ff067262765a5c817d17d92d43343d2972f08194f6`. |
| `Outcome/ipcch_unified/schema/ipcch_base_panel_schema.csv` | Generated with `tools/build_ipcch_schema_contract.py` | 169 data rows; field-level schema for current raw panel columns plus derived `area_id`; SHA-256 `c2f477162bf17ea6377ff88916f58aa8e6d32c28a53ae99c110b99edd1182b90`. |
| `Outcome/ipcch_unified/schema/ipcch_feature_family_contract.csv` | Generated with `tools/build_ipcch_schema_contract.py` | 14 data rows; feature-family contract by codebook group; SHA-256 `5867106f287963f9da81b8d3043c23655f9719529474ea0f9d0ce3875d31d484`. |
| `Outcome/ipcch_unified/schema/ipcch_model_input_contract.md` | Generated with `tools/build_ipcch_schema_contract.py` | Human-readable G-05 unified long-panel contract; SHA-256 `1e30908222895fdda77bc7e1288ff409451c0c1e7aeb5afba54452d0042fda46`. |

The active G-02 handover package is `Outcome/ipcch_unified/`. Large raw and
geometry files are excluded from GitHub by `.gitignore`; they remain local
Dropbox handover assets. Legacy or ambiguous reference files were moved to
`archive/legacy_reference_assets/` and should not be used as production
contracts.

## Cloud Run and Release Artifact Inventory

Cloud monthly E2E runs write immutable run evidence under
`runs/{run_id}/...` and publish the stable consumer pointer at
`released/{YYYYMM}/release_manifest.json`.

Run-scoped required evidence:

- `runs/{run_id}/run_summary.json`
- `runs/{run_id}/gee_exports/gee_export_manifest.json`
- `runs/{run_id}/gee_exports/MOD13A3_EVI_YYYY_MM_processed.tif`
- `runs/{run_id}/evi/EVI_mean_extraction_results.csv`
- `runs/{run_id}/evi/EVI_std_extraction_results.csv`
- `runs/{run_id}/evi/EVI_mean_monthly_long.csv`
- `runs/{run_id}/evi/EVI_std_monthly_long.csv`
- `runs/{run_id}/evi/evi_extraction_manifest.json`
- `runs/{run_id}/evi/evi_validation_report.json`
- `runs/{run_id}/assembly/ipcch_monthly_base_input_YYYYMM.csv`
- `runs/{run_id}/assembly/ipcch_monthly_base_input_YYYYMM_summary.json`
- `runs/{run_id}/qa/base_input_validation_report.json`
- `runs/{run_id}/inference/vertex_ai_job_manifest.json`
- `runs/{run_id}/inference/inference_report.json`
- `runs/{run_id}/inference/ipcch_launch_YYYYMM_scope_0m_predictions.csv`
- `runs/{run_id}/inference/ipcch_launch_YYYYMM_scope_6m_predictions.csv`
- `runs/{run_id}/inference/ipcch_launch_YYYYMM_scope_12m_predictions.csv`
- `runs/{run_id}/release/release_step_report.json`

Release-scoped artifacts:

- `released/{YYYYMM}/release_manifest.json`
- copied v1 consumer artifacts under `released/{YYYYMM}/runs/{run_id}/...`
- large upstream evidence referenced from the manifest by immutable URI,
  generation, version, or checksum.

Forbidden cloud output families for v1 include prediction maps, prediction
sheets, full delivery artifacts, model training artifacts, local workstation
scoring outputs, FLDAS, GOSIF-GPP, VIIRS, and undeclared non-Vertex inference.

Nightlight handover note: future monthly updates should use VIIRS as the
production source. Local paths still contain `DMSP_OLS` for historical reasons,
but the current Earth Engine script exports from
`NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG`. Set its date window to the target feature
month, with `endDate` as the first day of the following month.

Remote-sensing normalization note: ArcPy extraction scripts emit wide CSVs
keyed by `region_id`. Use `tools/reshape_remote_sensing_wide_to_long.py` to
convert those outputs to `area_id`, `year`, `month` rows. The tool supports
`YYYY_MM`, GOSIF `YYYY.MMM`, and FLDAS-style `YYYY_MM_Bn` date columns. If
`region_id` is not already the current `area_id`, pass a two-column mapping CSV
with `region_id` and `area_id`.

## Manual Raw Input Examples and Ownership Notes

These source refresh notes complement the generated assets above. They are
operator instructions, not additional required Weilun-side model assets.

| Source | Example raw input | Current handling | Owner / handover note |
| --- | --- | --- | --- |
| ACLED | `archive/example_raw_inputs/ACLED/ACLED Data_2026-05-11_ipcch.csv` | `ACLED/00_add_acled_features.py` consumes event-level `Political violence` rows and creates battles, explosions, and violence features. | Sediqa should download only `Battles`, `Explosions/Remote violence`, and `Violence against civilians`; do not include protest rows unless the script is later extended. See `docs/08_sediqa_raw_data_download_notes.md`. |
| WFP prices | `archive/example_raw_inputs/WFP/Prices-Export-Thu Mar 27 2025 11_30_42 GMT-0400 (Eastern Daylight Time).csv` | `WFP_indicator/00_add_wfp_price_features.py` reads `Commodity`, then drops it and aggregates staged `Trend` values by country/month. | Sediqa should download from WFP Analysis Builder and stage only ALPS-compatible commodities before running the script. Do not treat commodity crosswalk logic as implemented inside the current script. See `docs/08_sediqa_raw_data_download_notes.md`. |
| FAO prices | `C:\Users\swl00\IFPRI Dropbox\Weilun Shi\Google fund\Analysis\1.Source Data\FAO\GOOGLE_FOOD_CRISIS_FAO_DATA.xlsx` | `FAO_price/00_add_fao_price_features.py` expects a normalized workbook schema; FAO exports may vary. | Soonho/Sediqa should normalize the refreshed FAO export or adjust the FAO script for the specific export. |
| Bloomberg | Not required for the current base handover. | Optional external source referenced by model-ready/codebook material, not required by G-09 base monthly assembly. | Soonho can handle if Bloomberg is included in a later production feature set. |
| Historical raw archives | Existing local `1.Source Data` folders. | Historical raw inputs do not have detailed archive manifests. | Treat existing historical raw assets as `validated_on=2026-06-22`. Future refreshes should use date-stamped folders or filenames and record source name, download date, operator, row count, filters applied, and consumed pipeline file. |

Monthly release ownership: Soonho and Sediqa download raw data and run the
pipeline; Weilun validates the final monthly model-compatible input and QA
summaries before release.

## Validation Command Examples

EVI/VIIRS wide monthly example:

```bash
python3 tools/validate_csv_contract.py --csv path/to/EVI_mean_extraction_results.csv --key region_id --required-column region_id --monthly-regex '^[0-9]{4}_[0-9]{2}$' --min-monthly-columns 1
```

FLDAS wide monthly-band example:

```bash
python3 tools/validate_csv_contract.py --csv path/to/FLDAS_mean_extraction_results_p1.csv --key region_id --required-column region_id --monthly-regex '^[0-9]{4}_[0-9]{2}_B[0-9]+$' --min-monthly-columns 1
```

GOSIF-GPP wide monthly example:

```bash
python3 tools/validate_csv_contract.py --csv path/to/GOSIF_GPP_extraction_results_ch.csv --key region_id --required-column region_id --monthly-regex '^[0-9]{4}\.M[0-9]{2}$' --min-monthly-columns 1
```

Scaffold key-only example:

```bash
python3 tools/validate_csv_contract.py --csv path/to/ch_with_merged_acled_metrics.csv --key lat --key lon --key year --key month --required-column year --required-column month
```

Add `--required-column` entries for source-specific feature columns when using
the validator to confirm that a tabular workflow appended the expected features.

Unified IPCCH G-05 schema examples:

```bash
python3 tools/build_monthly_ipcch_scaffold.py --year 2026 --month 4
python3 tools/validate_ipcch_schema.py --mode historical-panel --csv Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv
python3 tools/validate_ipcch_schema.py --mode forecast-scaffold --csv Outcome/ipcch_unified/interim/ipcch_scaffold_202604.csv
python3 tools/validate_ipcch_schema.py --mode fixed-slow-area --csv Outcome/ipcch_unified/features/ipcch_fixed_slow_features_by_area.csv
```

Unified G-09 monthly base input example:

```bash
python3 Final_harmonise/00_build_monthly_ipcch_base_input.py --year 2026 --month 4
python3 tools/validate_ipcch_schema.py --mode model-input-forecast --csv Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604.csv
```

Use `--mode model-input-training` or `--mode model-input-forecast` when a later
G-06/G-07 model-ready export is rebuilt with canonical `area_id`, `year`, and
`month` keys.
