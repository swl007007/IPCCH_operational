# Weilun Handover Gap List

This file tracks the Weilun-owned handover assets identified from
`structured_TOR_from_variable_note.xlsx` and the current repository contracts.

## Production Scope Clarification

The future production model should treat `IPCCH` as one unified input/output
contract. Current script names and some intermediate files still contain `CH`
or `IPC` labels because they came from earlier split workflows. Those labels
should be treated as transitional implementation details unless a downstream
consumer explicitly requires separate files.

The repository's final operational product is a monthly model-compatible input
table. Prediction is downstream: Weilun will export the trained model weights
and model pipeline separately, and those artifacts will be combined with the
monthly compatible input to produce predictions. Therefore production only
needs a one-month scaffold for the target month.

## Gap Status

| ID | Gap | Status | Current resolution / next action |
| --- | --- | --- | --- |
| G-01 | Authoritative 53-country scope and country identifiers | Resolved | Created `polygons_and_identifier/country_scope_ipcch_2026.csv` from `IPCCH_2026_completed.csv`. |
| G-02 | Core outcome/reference files required by final harmonise | Resolved for handover | Replaced legacy split CH/IPC references with unified `Outcome/ipcch_unified/` assets. Final monthly model-input assembly refactor is tracked separately as G-09. |
| G-03 | Fixed and slow-moving model-ready assets | Resolved for handover | Generated `Outcome/ipcch_unified/features/ipcch_fixed_slow_features_by_area.csv` from the unified historical panel, with a feature-level stability summary. Final monthly model-input assembly refactor is tracked separately as G-09. |
| G-04 | Fixed-variable source/vintage metadata | Resolved for handover | Generated `Outcome/ipcch_unified/metadata/ipcch_fixed_slow_source_vintage_manifest.csv` covering source folders, processed files, checksums, source-family vintage, units, aggregation notes, codebook evidence, and FEWS NET paper data-section evidence. |
| G-05 | Unified standardized IPCCH monthly model input schema | Resolved for handover | Created `Outcome/ipcch_unified/schema/`, one-month scaffold tooling, and a 2026-04 production scaffold example. Legacy CH/IPC files are compatibility artifacts only. |
| G-06 | Model weights and model pipeline | Deferred | Weilun will export these later; prepare with version/date labels and compatibility notes against the monthly model-compatible input schema. |
| G-07 | Downstream feature engineering / production model transformations | Deferred | Not currently available; prepare later so the monthly IPCCH input exactly matches the exported model pipeline's expected columns. |
| G-08 | Nightlight temporal coverage / fallback source | Resolved for handover | Use VIIRS as the production monthly source. Historical assembled panel already contains `nightlight_mean/std` through 2026-04; legacy `DMSP_OLS` path names are folder history, not the production source decision. |
| G-09 | Final monthly model-input assembly refactor | Resolved for base assembly | Added unified monthly IPCCH base input builder that starts from the one-month scaffold, joins fixed/slow features and same-month source-level fields, and writes one long IPCCH monthly table plus QA summary. G-06 model weights/pipeline and G-07 model-specific transformations remain deferred. |
| OI-07 | WFP commodity overlap / ALPS commodity mapping | Resolved by operator instruction | Current script aggregates by country/month and drops `Commodity`; Sediqa should download or stage only ALPS-compatible commodities before running the WFP workflow. |
| OI-08 | FAO/Bloomberg export specification | Delegated / not Weilun blocker | Bloomberg data is optional and can be handled by Soonho. FAO exports can vary by format and should be normalized or script-adjusted by Soonho/Sediqa when refreshed. |
| OI-09 | QA ownership and monthly release checks | Resolved by role assignment | Soonho/Sediqa download raw data and run the pipeline; Weilun validates monthly outputs before release. |
| OI-10 | Model asset versioning | Deferred | Same deferred scope as G-06/G-07: model weights, pipeline, and model-specific feature engineering will be exported later. |

## G-01 Resolution: Country Scope

Source:

`C:\Users\swl00\IFPRI Dropbox\Weilun Shi\Google fund\Analysis\1.Source Data\assembled_IPCCH\raw\IPCCH_2026_completed.csv`

Generated asset:

`polygons_and_identifier/country_scope_ipcch_2026.csv`

Checks:

| Check | Result |
| --- | --- |
| Source row count scanned | 1,219,868 |
| Country count | 53 |
| CSV validator | `PASS: rows=53 columns=19` |
| Unique key | `ISO3` |
| Year range | 2010-2026 |
| Last year-month in source | 2026-04 |
| SHA-256 | `f0609280a0c89b3db01fc19cd8a6be1bb31356df613d74ea931180aef90b6d09` |

Notes:

- The source CSV had blank `ISO3` for Côte d'Ivoire but `country_code=CI`.
  The generated asset resolves this row to `ISO3=CIV` and records
  `iso3_resolution=country_code_lookup`.
- The asset keeps both source country naming fields: `country` and
  `country_en`.
- The asset includes counts useful for handover QA: `row_count`,
  `admin_code_count`, `lat_lon_count`, `state_count`,
  `year_month_count`, and `overall_phase_nonmissing_rows`.

## G-02 Resolution: Unified Outcome/Reference Assets

Legacy final harmonise scripts currently reference separate CH and IPC files:

- `Outcome/geoidentifier_ch.csv`
- `Outcome/ch_scaffold_fixed.csv`
- `Outcome/gdf_ch.geojson`
- `Outcome/IPC_2017_2025/geoidentifier.csv`
- `Outcome/IPC_2017_2025/ipc_outcome.csv`

Those legacy files are not the future production contract. They have been
superseded for handover by the unified IPCCH asset package:

| File | Role | Check |
| --- | --- | --- |
| `Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv` | Unified historical panel with keys, features, and outcome columns through 2026-04. | 1,219,868 data rows; no duplicate `(admin_code, lat, lon, year, month)` keys; SHA-256 `ae696087c3bbb280537ae269a05924133acdb51060d31290523404fa8a717673`. |
| `Outcome/ipcch_unified/interim/ipcch_scaffold_202604.csv` | One-month production scaffold example keyed by `admin_code`, `lat`, `lon`, `year`, `month`. | 6,227 data rows; SHA-256 `199882aae1151836efd159a2a3506d9183449b5b1b39047daee6dea5a21961f4`. |
| `Outcome/ipcch_unified/interim/ipcch_scaffold_202501_202604.csv` | Multi-month reference/batch scaffold retained for QA and rebuilding one-month scaffolds. | 99,632 data rows; SHA-256 `e4cda142a0b3adf2dac8e31c16a3450690e42d5d61b1e79ec6c1ede4c9a8ce2e`. |
| `Outcome/ipcch_unified/spatial/unique_area_id_lat_lon.csv` | `area_id` to coordinate lookup. | 6,227 data rows; SHA-256 `3bf8f115ec70cd1e1c907031309b797410a8024cdc1d39265be123ae636d2862`. |
| `Outcome/ipcch_unified/spatial/ipcch_admin_geometry.*` | Unified IPCCH geometry shapefile package. | `.shp`, `.dbf`, `.shx`, `.prj`, and `.cpg` copied; checksums in `Outcome/ipcch_unified/MANIFEST.md`. |
| `Outcome/ipcch_unified/country_area_id_lookup.csv` | `area_id` to country lookup. | 6,227 data rows; SHA-256 `e2baf6ae9481b42b127db5ce81f3c53ad784bb08ae56dfa56cea74e416b44c90`. |
| `Outcome/ipcch_unified/country_region_mapping.csv` | Country to region mapping. | 53 data rows; SHA-256 `40442e0de598511e1fe379335af0d65b33b02e25a5458b79170542f6c67d1e32`. |

Potentially misleading legacy assets were moved from `polygons_and_identifier/`
to `archive/legacy_reference_assets/polygons_and_identifier/`:

- `IPC_scaffold_example.csv`
- `geoidentifier_ipcch.csv`
- `gdf_ipc_ch_final.geojson`
- `gdf_ipc_ch_final_country_count.csv`

Next code-facing decision is tracked as G-09: update final monthly assembly so
it consumes the unified IPCCH contract directly, rather than recreating separate
CH and IPC reference files.

## G-03 Resolution: Fixed/Slow-Moving Feature Asset

Source:

`Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv`

Generated assets:

| File | Role | Check |
| --- | --- | --- |
| `Outcome/ipcch_unified/features/ipcch_fixed_slow_features_by_area.csv` | One row per `area_id` / `admin_code`, with AEZ, ASAP mask, river distance, terrain, ISRIC SoilGrids, market access, population-context, and coastline-distance columns. | 6,227 data rows; 48 columns; unique `area_id`; `coastline_dist` has 0 missing rows; SHA-256 `89bbda8680b98bc6edddea3fa19f863dadb52dbb0ad88ed09e15997d006ba482`. |
| `Outcome/ipcch_unified/features/ipcch_fixed_slow_features_summary.csv` | Feature-level source checksum, output checksum, missingness, and within-area stability report. | 36 data rows; SHA-256 `2ae4884a4e4cbfa5ff133f58a353d52249a5e248a1773f9e7b29527298ad8fb1`. |
| `tools/build_ipcch_fixed_slow_features.py` | Rebuild script for the G-03 asset from the big panel plus coastline source. | SHA-256 `73dd73b926006e9df9ff7019742db6978482154ab3e9bb971aac9e79fc43994a`. |

Feature-family coverage:

| Family | Columns | Status |
| --- | --- | --- |
| AEZ | 21 `AEZ_*` columns | Verified static in the source panel. |
| ASAP land cover / masks | `crop`, `range` | Verified static in the source panel. |
| River distance | `distance_to_river` | Included; varies within 16 areas, so the output uses latest nonmissing source value. |
| Terrain | `elevation`, `ruggedness`, `slope` | Verified static in the source panel. |
| ISRIC SoilGrids | 5 `sg_*_5-15cm` columns | Included; varies within 300-345 areas depending on column, so the output uses latest nonmissing source value. |
| Market access | `market_access`, `market_distance` | `market_access` verified static; `market_distance` varies and is missing for 141 areas. |
| Population context | `popdensity` | Included as slow-moving context; present for 1,308 of 6,227 areas. |
| Coastline distance | `coastline_dist` | Joined from `Coastline_distance_NOAA/IPCCH_2026_price_completed_unique_lat_lon_coastline_dist.csv`; present for all 6,227 areas. |

The unified source panel does not expose separate `ESA_*` columns. Under the
current handover decision, the old ESA-specific output files remain superseded
by the unified panel. If a downstream consumer explicitly needs raw ESA fields,
reopen G-03 as a source-specific exception.

## G-04 Resolution: Source/Vintage Metadata

Generated asset:

| File | Role | Check |
| --- | --- | --- |
| `Outcome/ipcch_unified/metadata/ipcch_fixed_slow_source_vintage_manifest.csv` | Family-level provenance manifest for G-03 fixed/slow feature families. | 8 data rows; 25 columns; unique `family`; SHA-256 `ee94d12de508651b93817c40304249e69caf25c1dec67aaef7bdac11fc09dcb6`. |
| `tools/build_ipcch_source_vintage_manifest.py` | Rebuild script for the G-04 manifest. | SHA-256 `d0232b6cc0aeacbd1b94bad5a7146f3b44fccc5405d279e3bb81b381b17b9eaf`. |

Evidence used:

- G-03 summary: `Outcome/ipcch_unified/features/ipcch_fixed_slow_features_summary.csv`.
- IPCCH codebook:
  `Outcome/ipcch_unified/metadata/variable_codebook_reorganized.csv`, copied
  from `assembled_IPCCH/metadata/variable_codebook_reorganized.csv`.
- Local source folders under `1.Source Data`: `AEZ`, `ASAP_land_cover`,
  `Distance_to_rivers`, `Elevation`, `ISRIC`, `Market_access`,
  `Populationdensity`, `Ruggedness`, `Slope`, `FAO`, and
  `Coastline_distance_NOAA`.
- PDF reference:
  `C:\Users\swl00\Downloads\Forecasting_FEWS_NET_Food_Security_Crises_Using_a_Geo_Aware_Spatial_Clustering_Model.pdf`.
  `pdftotext` extraction succeeded and relevant evidence is in the data section
  and Appendix Table A10.

Feature-family coverage:

| Family | Source/vintage summary |
| --- | --- |
| `aez` | Agricultural Ecological Zones; paper Appendix Table A10 cites Tricht et al. (2023); local AEZ processed files dated 2025. |
| `asap_land_cover` | FAO ASAP crop/rangeland masks, local `asap_mask_*_v02.tif` and processed CSVs; paper reference retrieved 2024. |
| `river_distance` | World Bank / Andreadis et al. (2013) river layers; local processed distance files dated 2025. |
| `terrain` | Elevation/slope from ESA or ERA5-derived processed outputs depending on field, ruggedness from Nunn and Puga (2012); local processed files dated 2025. |
| `isric_soilgrids` | ISRIC SoilGrids; IPCCH field names and codebook use 5-15 cm depth; local processed files dated 2025. |
| `market_access` | `market_access` from Weiss et al. travel-time-to-cities layer; `market_distance` from FAO market matching; local processed files dated 2025. |
| `population_context` | Local population-density processed outputs; provider vintage is not explicit in available metadata, but local processed files are recorded. |
| `coastline_distance` | Local NOAA coastline-distance raster/extraction source; `coastline_dist` matched by rounded lat/lon and is complete for the current 6,227 areas. |

## G-05 Resolution: Unified IPCCH Model Input Schema

Generated assets:

| File | Role | Check |
| --- | --- | --- |
| `Outcome/ipcch_unified/metadata/variable_codebook_reorganized.csv` | Copied IPCCH variable codebook used to classify schema fields and feature families. | 168 data rows; SHA-256 `4d917eee94119cf309fd66ff067262765a5c817d17d92d43343d2972f08194f6`. |
| `Outcome/ipcch_unified/schema/ipcch_base_panel_schema.csv` | Field-level schema for current raw panel columns plus the derived canonical `area_id`. | 169 data rows; 14 columns; SHA-256 `c2f477162bf17ea6377ff88916f58aa8e6d32c28a53ae99c110b99edd1182b90`. |
| `Outcome/ipcch_unified/schema/ipcch_feature_family_contract.csv` | Feature-family contract by codebook group, including current raw-panel coverage and fixed/slow area-asset coverage. | 14 data rows; SHA-256 `5867106f287963f9da81b8d3043c23655f9719529474ea0f9d0ce3875d31d484`. |
| `Outcome/ipcch_unified/interim/ipcch_scaffold_202604.csv` | One-month production scaffold example generated from the multi-month reference scaffold. | 6,227 data rows; SHA-256 `199882aae1151836efd159a2a3506d9183449b5b1b39047daee6dea5a21961f4`. |
| `Outcome/ipcch_unified/schema/ipcch_model_input_contract.md` | Human-readable contract for the unified IPCCH monthly model-compatible input. | SHA-256 `1e30908222895fdda77bc7e1288ff409451c0c1e7aeb5afba54452d0042fda46`. |
| `tools/build_ipcch_schema_contract.py` | Rebuild script for G-05 schema artifacts. | SHA-256 `87103afc33870998b5051911895ba1e1c691e31c06d92534049ca61077d0175b`. |
| `tools/build_monthly_ipcch_scaffold.py` | Builds one target-month scaffold from the reference scaffold or area lookup. | SHA-256 `406131fbd31851f45131b71d0f7ea97ae97fb0d63e103961af49ec0d60fed7d0`. |
| `tools/validate_ipcch_schema.py` | Streaming schema validator for the large raw panel, forecast scaffold, fixed/slow area asset, and future model-ready exports. | SHA-256 `b5d402782e3b749211d9dfdf4c3e964f3cab9dfb445241af42b49f606a907c81`. |

Canonical contract:

- The standardized production output of this repo is one long monthly
  model-compatible input row per
  `(area_id, year, month)`.
- In the current handover assets, `area_id = admin_code`. The raw historical
  panel and one-month forecast scaffold still validate on
  `(admin_code, lat, lon, year, month)` because that is their current stored
  shape.
- Production only needs one target-month scaffold. The multi-month scaffold is
  retained as a reference/batch asset, not as the required monthly production
  input.
- Remote-sensing workflow outputs remain wide monthly extraction tables at the
  source-workflow stage, but they must be melted into the long IPCCH contract
  before entering a model input.
- Outcome columns are `overall_phase`, `phase1_percent` through
  `phase5_percent`, and `estimated_population`. They are required for observed
  training/evaluation rows when available, but not required for forecast
  scaffold rows.
- Legacy `IPC` and `CH` files/scripts are compatibility artifacts, not the
  future production contract. Only generate split exports if a downstream
  consumer explicitly requires them.
- Model weights and the model pipeline remain G-06. Downstream
  lag/rolling/model-specific feature engineering remains G-07. Current
  `assembled_IPCCH/model_ready` files are references, not the final production
  contract until G-06/G-07 are exported.

Validation checks:

| Asset | Command | Result |
| --- | --- | --- |
| Historical panel | `python3 tools/validate_ipcch_schema.py --mode historical-panel --csv Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv` | `PASS: mode=historical-panel rows=1219868 columns=143`; date coverage 2010-01 through 2026-04. |
| One-month forecast scaffold | `python3 tools/build_monthly_ipcch_scaffold.py --year 2026 --month 4` then `python3 tools/validate_ipcch_schema.py --mode forecast-scaffold --csv Outcome/ipcch_unified/interim/ipcch_scaffold_202604.csv` | `PASS: mode=forecast-scaffold rows=6227 columns=5`; date coverage 2026-04 through 2026-04. |
| Fixed/slow area asset | `python3 tools/validate_ipcch_schema.py --mode fixed-slow-area --csv Outcome/ipcch_unified/features/ipcch_fixed_slow_features_by_area.csv` | `PASS: mode=fixed-slow-area rows=6227 columns=48`. |

Historical outcome nonmissing counts:

| Column | Nonmissing rows |
| --- | ---: |
| `overall_phase` | 43,713 |
| `phase1_percent` | 43,829 |
| `phase2_percent` | 43,829 |
| `phase3_percent` | 43,722 |
| `phase4_percent` | 43,636 |
| `phase5_percent` | 43,551 |
| `estimated_population` | 43,892 |

## G-08 Resolution: Nightlight Coverage and Production Source

Decision:

- Use VIIRS as the production source for future monthly nightlight features.
- The folder name `DMSP_OLS` remains a legacy local path label in current
  configs and source-data folders. It should not be interpreted as the
  production source choice.
- For monthly production, export only the needed target feature month. The
  current handover target is 2026-04, so
  `VIIRS_nightlight/00_ee_export_viirs_nightlight.txt` uses
  `startDate = '2026-04-01'` and `endDate = '2026-05-01'`. Earth Engine
  `filterDate` treats `endDate` as exclusive.

Evidence:

| Asset | Check | Result |
| --- | --- | --- |
| `Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv` | Streaming scan of `nightlight_mean` and `nightlight_std` coverage | Both columns have 1,219,841 nonmissing rows; 196 covered months; coverage is 2010-01 through 2026-04. |
| `C:\Users\swl00\IFPRI Dropbox\Weilun Shi\Google fund\Analysis\1.Source Data\DMSP_OLS\output_ch\nightlight_sum_extraction_results.csv` | Header scan of local extraction output | 152 monthly columns; coverage is 2012-04 through 2024-12. |
| `C:\Users\swl00\IFPRI Dropbox\Weilun Shi\Google fund\Analysis\1.Source Data\DMSP_OLS\output_ch\nightlight_std_extraction_results.csv` | Header scan of local extraction output | 152 monthly columns; coverage is 2012-04 through 2024-12. |
| `VIIRS_nightlight/00_ee_export_viirs_nightlight.txt` | Source collection and date window | Uses `NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG`; set to the 2026-04 monthly feature window. |
| `config/ee_gcs_template.ini` | Handover config template | `[viirs]` now records `target_feature_month = 2026-04`, `export_start_date = 2026-04-01`, and exclusive `export_end_date = 2026-05-01`. |

Operational note:

For a later target month, update the VIIRS Earth Engine `startDate` to the
first day of the target month and `endDate` to the first day of the following
month, then run the normal GCS download, mosaic, and ArcPy extraction steps.
The downstream monthly model-compatible input should use the extracted
`nightlight_mean/std` fields after final monthly assembly.

## G-09 Resolution: Final Monthly Base Input Assembly

Generated assets after running the 2026-04 smoke test:

| File | Role |
| --- | --- |
| `Final_harmonise/00_build_monthly_ipcch_base_input.py` | Unified monthly base input builder. |
| `Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604.csv` | One-month IPCCH base input surface keyed by `area_id`, `year`, and `month`. |
| `Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604_summary.json` | QA summary with row counts, join coverage, duplicate counts, and missingness. |

Smoke test checks:

| Check | Result |
| --- | --- |
| Output rows | 6,227, matching the one-month scaffold. |
| Output columns | 148 columns: 6 identifier columns, 44 fixed/slow columns, and 98 same-month source-level columns. |
| Schema validation | `PASS: mode=model-input-forecast rows=6227 columns=148`; coverage is 2026-04 through 2026-04. |
| Fixed/slow join | 6,227 matched rows; 0 unmatched rows. |
| Same-month source join | 6,188 matched rows; 39 unmatched rows. |
| Source coverage note | The raw panel has 6,188 rows for 2026-04 while the scaffold has 6,227 rows. The 39 unmatched areas are reported as a soft warning and keep scaffold rows with blank same-month source fields. |

The builder is intentionally conservative. It does not copy
`assembled_IPCCH/model_ready/*`, does not create lag/rolling/scope-specific
model features, and does not require model weights or the exported model
pipeline. Those remain G-06 and G-07.

Legacy split CH/IPC final harmonise scripts are archived under
`archive/legacy_final_harmonise/` as compatibility references only.

## ToR Open Issue Reclassification

These items are not additional Weilun-side model-input gaps after G-09. They
are operational handover notes for the raw-data refresh and monthly release
process.

| ToR issue | Decision | Handover instruction |
| --- | --- | --- |
| WFP commodity mapping | Resolved by raw-export rule | The current WFP script reads `Commodity`, then drops it and aggregates all staged commodities by country/month. Therefore the raw WFP export must already be filtered to ALPS-compatible commodities before running the workflow. Use Sediqa's download instruction to restrict the export to ALPS commodities, for example vegetable oil, wheat, sorghum, maize, and rice where those names are available in the WFP UI. Example raw input: `C:\Users\swl00\IFPRI Dropbox\Weilun Shi\Google fund\Analysis\1.Source Data\WFP\Prices-Export-Thu Mar 27 2025 11_30_42 GMT-0400 (Eastern Daylight Time).csv`. |
| FAO/Bloomberg export spec | Delegated / optional | Bloomberg is optional for the current handover and can be handled by Soonho. FAO export formats can vary, so Soonho/Sediqa should either normalize the refreshed workbook to the script's expected columns or update the FAO script for the specific export. Example raw input: `C:\Users\swl00\IFPRI Dropbox\Weilun Shi\Google fund\Analysis\1.Source Data\FAO\GOOGLE_FOOD_CRISIS_FAO_DATA.xlsx`. |
| QA ownership | Resolved by role assignment | Soonho and Sediqa are responsible for raw-data downloads and running the pipeline. Weilun is responsible for validating the produced monthly model-compatible input and QA summaries before release. |
| Raw archive convention | Historical limitation accepted | Previous raw inputs do not have detailed archive manifests. For handover, existing historical raw assets should be treated as `validated_on=2026-06-22`. Future raw refreshes should use date-stamped folders or filenames and should record at minimum source name, download date, operator, row count, filters applied, and output file consumed by the pipeline. |

## Remaining Assets To Collect Next

G-06 model weights/model pipeline and G-07 model-specific feature engineering
remain deferred. G-09 is resolved for base monthly assembly.
