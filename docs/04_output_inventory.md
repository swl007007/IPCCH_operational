# Output Inventory and Data Handover Manifest

## Workflow Output Contracts

| Workflow | Current/proposed output | Identifier | Shape | Downstream consumer |
| --- | --- | --- | --- | --- |
| EVI | `EVI_mean_extraction_results.csv`, `EVI_std_extraction_results.csv` | `region_id` mapped from ArcPy zone field | Wide monthly | Final harmonise CH/IPC combine scripts. |
| FLDAS | `FLDAS_mean_extraction_results_p*.csv`, `FLDAS_std_extraction_results_p*.csv` | `region_id` mapped from ArcPy zone field | Wide monthly-band, split by part | Final harmonise after consistent part handling. |
| GOSIF-GPP | `GOSIF_GPP_extraction_results_ch.csv`, `GOSIF_GPP_extraction_results_SD.csv` | `region_id` | Wide monthly | Final harmonise. |
| VIIRS nightlight | `nightlight_sum_extraction_results.csv`, `nightlight_std_extraction_results.csv` | `region_id` | Wide monthly, usually one target feature month for production updates | Final monthly model-input assembly. |
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
| `Outcome/ipcch_unified/features/ipcch_fixed_slow_features_by_area.csv` | Generated from `Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv` with `tools/build_ipcch_fixed_slow_features.py` | 6,227 data rows; 47 columns; unique `area_id`; SHA-256 `9a03da20298a58735ae52eafe7c3089c3e2110ed3165050dccd14fc22b7861a9`. |
| `Outcome/ipcch_unified/features/ipcch_fixed_slow_features_summary.csv` | Generated with the G-03 fixed/slow feature asset | 35 data rows; 28 features verified static in source panel and 7 slow/varying features flagged; SHA-256 `17bdff8f5e782683443a340feeb97a76a55e6854e6b745213afb770cd8af2e41`. |
| `Outcome/ipcch_unified/metadata/ipcch_fixed_slow_source_vintage_manifest.csv` | Generated with `tools/build_ipcch_source_vintage_manifest.py` from G-03 summary, IPCCH codebook, local `1.Source Data` folders, and FEWS NET paper data-section evidence | 7 data rows; one row per fixed/slow feature family; SHA-256 `4673f5baf5101fbeb97c0d28dbc7250e58730b1e084027ac93098f493bdbe204`. |
| `Outcome/ipcch_unified/metadata/variable_codebook_reorganized.csv` | Copied from `Google fund/Analysis/1.Source Data/assembled_IPCCH/metadata/variable_codebook_reorganized.csv` | 168 data rows; used by G-05 schema and feature-family contract; SHA-256 `4d917eee94119cf309fd66ff067262765a5c817d17d92d43343d2972f08194f6`. |
| `Outcome/ipcch_unified/schema/ipcch_base_panel_schema.csv` | Generated with `tools/build_ipcch_schema_contract.py` | 169 data rows; field-level schema for current raw panel columns plus derived `area_id`; SHA-256 `332d1b1d9b990270aea886aedf9eaae6293b6f558a227bcd79327349c940e57f`. |
| `Outcome/ipcch_unified/schema/ipcch_feature_family_contract.csv` | Generated with `tools/build_ipcch_schema_contract.py` | 14 data rows; feature-family contract by codebook group; SHA-256 `94d5940ede96d78c08f8155e5ed178bdeff08f60946cc0ade99bf63509da0af8`. |
| `Outcome/ipcch_unified/schema/ipcch_model_input_contract.md` | Generated with `tools/build_ipcch_schema_contract.py` | Human-readable G-05 unified long-panel contract; SHA-256 `1e30908222895fdda77bc7e1288ff409451c0c1e7aeb5afba54452d0042fda46`. |

The active G-02 handover package is `Outcome/ipcch_unified/`. Large raw and
geometry files are excluded from GitHub by `.gitignore`; they remain local
Dropbox handover assets. Legacy or ambiguous reference files were moved to
`archive/legacy_reference_assets/` and should not be used as production
contracts.

Nightlight handover note: future monthly updates should use VIIRS as the
production source. Local paths still contain `DMSP_OLS` for historical reasons,
but the current Earth Engine script exports from
`NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG`. Set its date window to the target feature
month, with `endDate` as the first day of the following month.

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
