# Research: CP0 climate scripts, ACLED aggregate converter, research feature derivation

- **Query**: Inventory shared-folder climate scripts (monthly/seasonal/climate_feature_sample), the research ACLED aggregate converter and its fixed tables, the research derivation of compact296/ACLED/IDP/history features, and where research-prepared families come from. READ-ONLY.
- **Scope**: internal (shared Dropbox folder + research checkout); no network/GEE/cloud
- **Date**: 2026-10-30
- Path abbreviations: `S=/mnt/c/users/swl00/ifpri dropbox/weilun shi/IPCCH_shared_folder`; `R=/home/swl007007/projects/food-crisis-research`; `CP=$R/sources/Food_Crisis_Cluster/IPCCHAlphaEarthExperiment/ipcch_alphaearth/compact.py` (byte-identical to the copies in `$R/scratch/multilayer-20261026/context-f31d604-tag/...` and `acledagg-hpt-verify-1/context-5e94e12/...`); `VF=$R/control-plane/research_cloud/training/ipcch_validity_features.py`; `BA=$R/staging/ipcch-update-202610/tools/build_acled_agg.py`; `AW=$R/staging/ipcch-update-202610/sources/acled_agg/work`.

## 1. Shared folder inventory (S)

11 nonempty scripts + `S/test.ipynb` (0 bytes). Folder is not a git repo. All JS scripts run in the Earth Engine Code Editor against GEE project `projects/han-sandbox-505315/assets/`; both .py files are Colab exports (`from google.colab import drive`, `ee.Initialize(project="han-sandbox-505315")`) and cannot run locally as-is.

Common to all: admin polygons = `IPCCH_ADMIN_STATIC_CALENDAR_CROPFRAC_V1_G00..G24` (25 GEE FeatureCollections, `EXPECTED_ADMINS = 6227`, key `admin_code`/`admin_idx`), e.g. `monthly/rainfall.js:107-119`. Missing sentinel -9999. Spatial method "pixel metric then pixelArea-weighted admin mean" over the whole polygon, no crop mask (`climate_crop_mask_used: 0`, `crop_fraction_multiplied: 0`), e.g. `monthly/rainfall.js:274-298, 519-524`; `monthly/temperature.js:398-401`; `seasonal/rainfall.js` (spatial_method in output props near 2280). Outputs are `Export.table.toAsset` per admin block (no CSV export), with resumable task bookkeeping (`monthly/rainfall.js:850-960`).

### 1a. Monthly scripts

| Script | Bases produced (per-source column) | Providers / GEE inputs | End-month config | Notes |
|---|---|---|---|---|
| `monthly/rainfall.js` (1023 l.) | `prcp_anom_month_{src}`, `prcp_z_month_{src}` (family ANOM_Z); `rainy_days_month_{src}`, `cdd_month_{src}` (family RAIN_CDD) (`:568-569, 735-736`) | one of CHIRPS `UCSB-CHC/CHIRPS/V3/DAILY_RNL`, PERSIANN `NOAA/PERSIANN-CDR`, ERA5LAND `ECMWF/ERA5_LAND/DAILY_AGGR` x1000 (`:23-45`), selected by `RUN_SOURCE` (`:5`); baselines `STAGE2A_PRCP_BASELINE_1991_2020_{SRC}_M01..12` (`:153-167`) | `TARGET_YEAR` (`:8`), `LAST_MONTH = TARGET_YEAR===2026 ? 8 : 12` (`:61`) | prcp_anom = sum of daily anomalies over valid days; prcp_z = (monthly total - baseline mean)/baseline SD, masked unless all days observed (`:256-264`); rain threshold 1 mm (`:19`); `qa_abs_prcp_z_gt6_warning` flag only, value kept (`:557-559`); per-admin coverage/status fields (`:530-560`). Task name `RAIN_MONTHLY_{ANOM_Z|RAIN_CDD}_{SRC}_Y{yyyy}_B..` (`:783-801`) |
| `monthly/rainfall_chucked.js` (708 l.) | same 4 bases in one task (`:593-596`) | PERSIANN, ERA5LAND only (`:17-32`); multi-year `PRODUCTION_PLANS` 2015-2026 (`:36-72`) | `lastMonth(year)` 2026->8 (`:107-111`) | `VERSION='V2_MONTHLY_ALL4_CHUNKED_N1000'`; prints "PERSIANN 2022-2026: not rerun" (`:707`) |
| `monthly/temperature.js` (822 l.) | `tmean_anom, tmax_anom, hot_days_p95, gdd, edd` as `{metric}_month_{src}` (`:24-30, 484`) | ERA5LAND or CPC `NOAA/CPC/Temperature` (`:5, 121-150`); daily baselines `STAGE2B_TEMP_BASELINE_1991_2020_{SRC}_M..` (`:160-171`) | `LAST_MONTH` 2026->8 (`:46`) | GDD base 10/cap 30, EDD crit 30 (`:20-22, 246-257`); hot day = tmax > calendar-day p95 1991-2020 (`:228-244`); anomalies mean over valid days, counts sum over valid days (`:427-438`) |
| `monthly/soil_moisture.js` (733 l.) | `sm_z_month_{src}` (`:429`) | ERA5LAND `volumetric_soil_water_layer_1` or GLDAS21 `NASA/GLDAS/V021/NOAH/G025/T3H` (`:26-44`); baselines `STAGE2D_SOIL_BASELINE_2001_2020_{SRC}_M..` (`:160-176`) | `LAST_MONTH` 2026->8 (`:60`) | z = (monthly mean - baseline mean)/baseline SD with any sample (`:208-225`), `complete_month_required: 0` (`:395`); `qa_abs_sm_z_gt6_warning` flag only (`:418-419`) |
| `monthly/ndvi_evi.js` (617 l.) | `ndvi_anom_month_{terra|aqua}_{yyyymm}`, `evi_anom_month_{sensor}_{yyyymm}` wide (`:500-525`) | Inputs are already admin-level 16-day tables: `S2E3_VI_BASE_ADMIN_2003_2020_{TERRA|AQUA}_CMG_P01..04_V3` (`:284-300`), `S2E3_VI_CURRENT_ADMIN_{SENSOR}_Y{yyyy}_CMG_V3` (`:345-366`) | `lastMonth = year===2026 ? 8 : 12` (~`:206`); four tasks terra/aqua x 2015-2020/2021-2026 (`:29-50`) | overlap-day-weighted mean of 16-day anomalies; exported -9999 unless full month coverage (`:376-436`). No pixel step here; spatial weighting of the S2E3 tables is UNVERIFIED (producer not in folder) |
| `monthly/spi_monthly.py` (3244 l., Colab) | `spi03_month_{chirps,persiann,era5land}`, `spei03_month_{...}` + `_ensmean/_n_sources/_ens_sd` (`:2844-2900`) | Downloads GEE admin tables `S2C3_DROUGHT_ADMIN_PRCP_{SRC}_Y{a}_{b}_V3`, `S2C3_DROUGHT_ADMIN_ET0_FAO56_Y{a}_{b}_V3`, `S2C3_ET0_PATCH32_Y{a}_{b}_V2` (`:522-560`), year chunks 1990-2026 (`:84-91`) | `ALL_MONTHS` to `2026-08-01`, `TARGET_MONTHS 2015-01..2026-08`, hard asserts 140 months / 871,780 rows (`:110-136, 2950-2960`) | Computation is pure numpy/scipy after download (3-month rolling sum requiring all 3 finite `:1224-1272`; SPI gamma zero-corrected; SPEI UB-PWM GLO strict 30-year baseline `:1563-1700`); method strings `:2419-2465` (`SPEI_UBPWM_GLO_STRICT_SUPPORT_V3`, `STRICT_1991_2020_NO_29_YEAR_FALLBACK`, ET0 = ERA5LAND FAO56). Ensemble `add_dynamic_ensemble` `:2266-2371`, called `:2374, 2380`. Output Drive parquet `SPI_SPEI03_MONTHLY_2015_2026_FINAL.parquet` + QA CSVs/manifest (`:2987-3035`) |

### 1b. Seasonal scripts

All seasonal JS use per-admin WorldCereal two-season calendar properties `s1_/s2_ sos/eos month/day, calendar_valid, cross_year` from the static admin assets (`seasonal/rainfall.js:1836-1860, 337-430`); season_year = EOS/harvest year, cross-year seasons start in year-1 (`seasonal/rainfall.js:380-430`; `seasonal/soil_moisture.js:9-11`). Output roots `{base}_gs_{src}` per season s1/s2.

| Script | Bases | Year window / data cutoff |
|---|---|---|
| `seasonal/rainfall.js` (2612 l.) | `prcp_anom_gs_`, `prcp_z_gs_`, `rainy_days_gs_`, `cdd_gs_` + `{src}` (`:984-986, 1096, 1348, 1713`) for chirps/persiann/era5land (`:43-64`) | `RUN_YEARS=[2019]` (`:21`), `CURRENT_DATA_END_EXCLUSIVE='2022-01-01'` (`:29, 640-650`) |
| `seasonal/temperature.js` (1508 l.) | 5 temperature bases `_gs_{cpc|era5land}` (`:835-840`) | `START_YEAR 2015`, `END_YEAR 2021`, `DATA_END_EXCLUSIVE '2022-01-01'` (header `:15-25`) |
| `seasonal/soil_moisture.js` (798 l.) | `sm_z_gs_{era5land|gldas21}` (`:340, 359`), monthly z then overlap-day weighted (`:346`), `qa_extreme_sm_z` abs>6 flag (`:352`) | YEARS 2015-2021, cutoff 2022-01-01 (`:9-20`) |
| `seasonal/ndvi.js` (1792 l.) | `{ndvi|evi}_anom_gs_{terra|aqua}` (`:122`), inputs S2E3 tables (`:669, 735`) | OUTPUT_YEARS ..2021, CURRENT_END_YEAR 2021 (`:31-49`) |
| `seasonal/spi&spei.py` (11314 l., Colab) | `spi03_gs_{src}`, `spei03_gs_{src}` via `aggregate_gs` (overlap-day-weighted monthly index, requires full season support else NaN with reason) `:5369-5640`; ensemble `add_ensemble` `:5750-5863`, called `:5866, 5871` | `OUTPUT_YEARS = range(2015, 2022)` (`:245-250`); index cutoff Dec 2021 (`:3485`); output `SPI_SPEI03_GS_2015_2021_FINAL.parquet` (`:6833`) |

- Seasonal scripts in the folder cover output years 2015-2021 only. The 2022-2026 seasonal rows present in the delivered tables were produced by script versions NOT in this folder (UNVERIFIED / not located).
- Separate final QA/merge step referenced, not located: `seasonal/temperature.js:1505-1508`, `seasonal/ndvi.js:1785-1787`, `seasonal/soil_moisture.js:748` ("Next: Colab full source QA").

### 1c. Ensemble logic location

- Only SPI/SPEI ensembles exist in code (monthly `spi_monthly.py:2266-2371`, seasonal `spi&spei.py:5750-5863`): equal-weight mean of finite sources, `n_sources` int8, population SD only when n>=2 else NaN; seasonal also writes `{family}_gs_status` THREE/TWO/ONE_SOURCE/MISSING_ALL_SOURCES.
- Ensembles for prcp/rain/temperature/soil/vegetation were done in the not-located Colab QA/merge. The delivered monthly table encodes an exclusion rule: `*_excluded_abs_ge6` flags exist for prcp_z (3 sources) and sm_z (2 sources); for every flagged row the source value is blank (verified for CHIRPS: 1,797 flagged, 0 retain a value), and `n_sources` equals the count of finite source columns in every row for prcp_z, sm_z, tmean_anom, spei03, evi_anom, rainy_days. Single-source rows have `ens_sd` NaN (never 0) in the monthly file. This differs from the source scripts, which only flag abs(z)>6 and keep the raw value.
- Seasonal delivered table audit (`S/audit_2015_2026_report.md`, 2026-09-30, SHA f024a66c...) reports implicit source exclusion without QA columns, and 15 single-source rows with `ens_sd = 0` in 2021 (section 4.1).

### 1d. Delivered tables = the training-panel climate inputs (verified by sha256)

| File in S | sha256 | Research role |
|---|---|---|
| `climate_monthly_2015_2026_MODELING_READY.csv` (1.08 GB, 95 cols, 871,780 rows, 6,227 admins, 2015-01..2026-08, no dup keys) | `8082b72e...c89` | `climate_monthly` in `$R/staging/ipcch-update-202610/merged/manifest-local.json` and the acledagg tuning manifest |
| `climate_2015_2026_MODELING_READY.csv` (187 MB, 92 cols, 149,448 rows, admin x season_year 2015-2026 x s1/s2) | `f024a66c...58e` | `climate_seasonal` (same manifests) |
| `climate_2022_2026_FINAL_MODEL_READY{,_V2}.csv` (104/123 cols with exclusion/QA columns) | not hashed | not a training role (earlier versions) |

Monthly header (fixture interface for monthly ensembles): keys `admin_code, admin_idx, group_id, crop_fraction, month, year, season_year, month_id, season, aggregation_start_date, aggregation_end_date_inclusive, aggregation_end_exclusive, month_duration_days, temporal_unit`; per base `{base}_month_{src}`, `{base}_month_ensmean`, `{base}_month_n_sources`, `{base}_month_ens_sd` for prcp_anom/prcp_z/rainy_days/cdd (chirps, persiann, era5land), 5 temperature bases (cpc, era5land), sm_z (era5land, gldas21), spi03/spei03 (3 precip sources), ndvi_anom/evi_anom (terra, aqua); plus 5 `*_excluded_abs_ge6` flags. Seasonal header: `admin_code, season_year, season, admin_idx, group_id, gs_sos, gs_eos, gs_cross_year, gs_duration_calendar_days, gs_calendar_valid, gs_calendar_quality, gs_duration_recalculated_days, gs_available_window_days, gs_start_date, gs_end_date_exclusive, crop_fraction` + `{base}_gs_{src}/_ensmean/_n_sources/_ens_sd` for 14 bases.

Per-base coverage end in the monthly table (count of non-missing ensmean): prcp_anom/prcp_z/rainy_days/cdd/5 temperature/sm_z through 2026-08 (6,189-6,225 admins); **spi03, spei03, evi_anom end 2026-07 (0 non-missing in 2026-08)**. spei03 has 5,717-5,961 non-missing per 2026 month (vs 6,225 for spi03).

Seasonal table: `gs_available_window_days = max(0, min(end, 2026-09-01) - start)`; 4,968 rows of 2026 are only partly observed (audit section 1, item 5).

### 1e. climate_feature_sample/

Not a production-shape interface: January-2022 WorldCereal GS-overlap TEST files with `_test` suffixes, crop-weighted overlap days, `admin_id`/`target_year` keys and -9999 sentinels (`PRCP_Z_GS_3sources_WorldCereal_JAN2022_TEST.csv` 15 cols; `SM_Z_GS_2sources_..._TEST.csv` 20 cols; `final_climate_features_202201.csv` 54 cols with `country, admin_id, year, month, season`). `climate_rain_temperature_sm_vegetation_spi_spei_2022_2026_model_ready.csv` (87 cols) is the seasonal schema without gs_start/end dates. The fixture shape that matches what research consumes is the two top-level MODELING_READY headers above. `workload documentation.docx` section 9 states the equal-weight / population-SD / SD only with >=2 sources rule; section 6 states soil abs(z)>20 exclusion; paragraph 26 describes crop-mask weighting while paragraph 6 says whole polygon (internal inconsistency in the doc).

### 1f. Can it run locally?

- All 9 JS scripts: GEE only (ee ImageCollections + private assets).
- `spi_monthly.py` / `spi&spei.py`: download step needs GEE (`ee.FeatureCollection` paging) and Colab Drive paths; SPI/SPEI math is portable numpy/scipy once admin monthly PRCP/ET0 tables are available (requires 1990-11 onward history for 1991-2020 baseline).
- External prepared assets referenced but not produced by any script in S: `IPCCH_ADMIN_STATIC_CALENDAR_CROPFRAC_V1_G*`, `STAGE2A_PRCP_BASELINE_*`, `STAGE2B_TEMP_BASELINE_*`, `STAGE2D_SOIL_BASELINE_*`, `S2E3_VI_BASE_ADMIN_*`, `S2E3_VI_CURRENT_ADMIN_*`, `S2C3_DROUGHT_ADMIN_PRCP_*`, `S2C3_DROUGHT_ADMIN_ET0_FAO56_*`, `S2C3_ET0_PATCH32_*`. Existence/access UNVERIFIED.
- Admin count 6,227 hard-coded across scripts.

## 2. Research ACLED aggregate converter (BA)

- Dependencies: geopandas, shapely 2, scipy.sparse, numpy, pandas (`BA:59-66`); imports sibling modules `boundaries_acled_agg` and `coverage_acled_agg` at runtime (`BA:227-228, 429-430`). Recorded runtime: python 3.12.3, pandas 3.0.3, numpy 2.4.4, geopandas 1.1.3, shapely 2.1.2 (`sources/acled_agg/harmonization.json` `runtime`). Tool sha `b78e60fd...a776`. Run via `~/.venvs/ipcch-geo/bin/python -B tools/build_acled_agg.py`.
- Inputs (`BA:3-17, 70-104`): three ACLED Data Export Tool weekly admin1 CSVs (header `week,region,country,admin1,event_type,sub_event_type,events,fatalities,population_exposure,disorder_type,centroid_latitude,centroid_longitude`) + `exports_manifest.json` (per-file sha/role f1/f2/f3, `f3_region_filter.kept_regions_f1_f2`); `work/admin1_layer.gpkg` (layer `admin1`, 1,465 polygons, cols `poly_id, iso3, name, source, source_id, role, area_km2, clipped_km2`); `work/admin1_overrides.csv`; `work/admin1_population.csv` (`pop_denominator`); `work/coverage_start.csv`; `work/cgaz_country_borders.csv`; raw CGAZ ADM1 gpkg (sha-checked, for the D28 gate, `BA:409-431`); unit geometry `/home/swl007007/ipcch-alphaearth-runs/p0-local-20261010b/sources/geometry/ipcch_admin_geometry_repaired.shp` (`BA:94`); raw panel `merged/IPCCH_202610_completed.csv` (sha-pinned, key set and ISO3, `BA:778-794`); `contract/admin_keys.csv` (6,188 current units).
- Constants: Saturday weeks 2009-12-26..2026-10-10, 877 weeks (`BA:114, 190-195`); window 2010-01..2026-09 (`BA:103`); exposure from 2015-01 (`BA:104`); sliver 0.001 (`BA:112`); nearest cap 25 km (`BA:113`); neighbour tolerances 1 km same source / 3.5 km cross source (`BA:106`).
- Method anchors: event types Battles/ERV/VAC and region filter (`BA:200-203`); mapping order in code = override table first, then centroid-in-polygon (contains wins, ties lowest poly_id), else nearest same-country polygon with 25 km assert (`BA:254-289`) -- note the override is applied before the centroid result, not after; polygon-week sum/sum/max (`BA:566-569`); week->month split `x d_m/7`, exposure max over overlapping weeks (`BA:578-596`); coverage NaN before country start or outside regions, covered no-event = 0 (`BA:604-623`); exposure share (`BA:636-655`); spillover (`BA:697-735`); unit weights (`unit_weights` `BA:351-386`, renormalised, `W_FILE`); unit value = partial-NaN renormalised weighted mean (`BA:832-845`); unit-country coverage start blanking (`BA:856-861`); gates incl. `admin1_all_mapped` (`BA:900-921`) -- unmapped admin1 is a failing gate (exit 1, `BA:1069`) but the CSV is still written before exit (`BA:926-928`); rows of countries outside the layer are dropped and only reported (`BA:241-245`).
- Output `sources/acled_agg/processed/acled_agg_monthly.csv` (220 MB, 1,250,808 rows, sha `539746f5...1f20`): `area_id,month,year` + 18 columns `acled_agg_{events,fatalities,exposure,exposure_share,spill_events,spill_fatalities}_{battles,erv,vac}` (`BA:98-100`). Panel months 2010-01..2026-04 have 6,227 admins; new months 2026-05..09 have only the 6,188 current units (`harmonization.json new_family`).
- Merged into training interim by `tools/merge_panels.py --add-family` -> `merged/IPCCH_202610_interim_acledagg.csv` (2.3 GB, sha `52b0a48a...7249`); 2026-10 rows blank (`merged/merge_report_acledagg.json`).

Fixed tables in `AW` (sizes in bytes):

| File | Size | Rows | Content |
|---|---|---|---|
| `acled_admin1_to_poly.csv` | 209,027 | 1,302 | ACLED (country, admin1) -> `poly_ids` (pipe), method, nearest_km, name_check |
| `admin1_overrides.csv` | 5,857 | 13 | `acled_country,admin1,iso3,kind(polygon|group),target_names,target_poly_ids,reason,source` |
| `coverage_start.csv` | 19,199 | 89 | per ISO3 `effective_start_ym`, `in_f1f2_regions`, `determined` |
| `admin1_neighbours.csv` | 529,706 | 7,488 | `poly_id,neighbour_poly_id,distance_m,same_source,tolerance_m,cross_border` |
| `unit_admin1_weights.csv` | 1,503,402 | 12,280 | `admin_code,poly_id,...,weight,method,n_polys` |
| `admin1_population.csv` | 220,043 | 1,465 | `pop_denominator` per poly |
| `cgaz_country_borders.csv` | 3,244 | 173 | `iso3_a,iso3_b,distance_m,shares_border` |
| `unit_iso3.csv` | 127,064 | 6,227 | `admin_code,iso3,rule` |
| `admin1_layer.gpkg` | 57,507,840 | 1,465 | polygon layer |
| raw CGAZ for D28 gate | 144,470,016 | - | `raw/boundaries/cgaz/geoBoundariesCGAZ_ADM1.gpkg` (raw/boundaries total 359 MB) |

## 3. Research feature derivation (for reproduction from retained ensembles)

Source selection: `VF:793-841` reads `interim` (keys + `INTERIM_SOURCES[:7]` + bbg members + optional 18 acled_agg), `climate_monthly` (`{base}_month_ensmean` for 13 bases) via complete grid `Grid.from_long(require_complete=True)` (`VF:817-818`, `CP:186-206`), `climate_seasonal` (`admin_code, season_year, season, gs_start_date, gs_end_date_exclusive` + 13 `{base}_gs_ensmean`) (`VF:824-825`), raw panel lat/lon, static29, `idp_admin0_monthly`, AE descriptors.

- 13 bases: `CP:48-51, 72-73` (ndvi_anom excluded). Only `_ensmean` consumed.
- Ordinary stems (24 sources = 11 interim + 13 climate): `value_at_origin`, `ma3/ma6/ma12` trailing means with min periods 2/3/6, `sd12` sample SD (ddof 1) min 6 (`CP:82-84, 118-119, 328-348, 376-381`). Trailing windows are calendar-month columns of the grid; NaN months count against min_periods.
- Same-month z (14 sources: GPP, nightlight, WFP, WB index, ENSO + 9 climate bases excluding prcp_z, sm_z, spi03, spei03) `CP:75-77`: for each calendar month, z of year y uses ALL prior years in the grid (expanding, from the grid's first month) with >=2 prior non-NaN values, non-constant, sd>0, sample SD (`CP:351-373`); then ma3/ma6/ma12 of z (`CP:384-389`). Consequence: reproduction needs the full history from the grid start (climate grid starts 2015-01).
- Stress stems (`CP:53-60, 78-80, 293-304, 404-409`): spi03 <= -1; tmean_anom >= 1; evi_anom <= -0.015; GPP < 0.9 x value 12 months earlier; event_count_violence > 0 (dropped in ACLED-agg arm); WFP (x - x[t-12])/x[t-12] > 0.10; ENSO abs > 0.5. Each yields share12 (trailing mean, min 6), months_since (`CP:231-239`), longest_run12 (min 6, `CP:242-255`), any12 (trailing max, min 6).
- Gathered at O = T - H by calendar month (`CP:426-435`).
- Growing seasons `completed_seasons` (`CP:457-501`): seasons per admin sorted by end then start; eligible if `gs_end_date_exclusive <= first day of O+1`; pick latest (pos) and pos-1; features `gs_last{1,2}__{base}_gs_ensmean__at_origin`, `gs_last{k}__months_since_end_at_origin = O - month(end_exclusive - 1 day)`; `gs_last1__is_major_at_origin` from `season_major_flags` (s1 vs s2 duration in same season_year, ties NaN; `CP:441-454`). Ledger check `CP:504-527`.
- Aggregated ACLED (`VF:1007-1070`): 18 sources x (value, ma3, ma6, ma12, sd12) + 6 event series x nonzero stress (share12, months_since, longest_run12, any12) = 114 columns named `{src}__{stat}_at_origin_lag1`, gathered at A = O - 1 (`ACLED_AGG_LAG = 1`). Signal x>0 keeps NaN as NaN (`VF:1055-1058`). Replaces 14 OLD columns (`VF:1023-1024`, `feature_order` `VF:849-863`).
- National IDP (`CP:627-678` / `VF:878-895`): latest observed `idp_ind` with report month <= O, plus age O - report.
- Local IDP (`VF:898-993`): `idp_ffill6` from `idp_ipcch_monthly.parquet` at O, strict MA3/MA6 (all months required).
- Outcome history (`VF:703-758`): latest three `reported_phase` (raw panel `overall_phase` 1-5, original reports only, `VF:143-190, 707-715`) with report month <= bound, bound = T-1 at H0 else O (`VF:718-720`); changes h1-h2, h1-h3. Selection is by report month, not by an availability month.
- Identifiers `CP:708-733`: lat/lon at target key, month_1..12, year_2014..2026 (raises outside 2014-2026).
- Horizons in this file are (0, 6, 12) (`VF:40, 52`): 424 base + 3 local IDP + 100 net ACLED = 527 at H0; H6/H12 add 12 oracle columns (539). No H2/H8/H14 code path found in `VF` (UNVERIFIED whether it exists elsewhere).

## 4. Research-prepared families: where they come from

| Family | Research source | Format/location |
|---|---|---|
| `nino34_anom` | column of interim panel (`INTERIM_SOURCES`, `CP:63, 70-71`); delta updates by `tools/build_nino34.py` | `sources/nino34/processed/nino34_monthly.csv` (`area_id,month,year,nino34_anom`, new months only, 627,939 B); history only inside `merged/IPCCH_202610_interim*.csv` |
| 4 bbg composites | composite = row mean (skipna) of member columns per group (`CP:276-290, 310-316`); members pinned in compact manifest `commodity_members` (staple_food 5, oilgas 3, soybean_oil 2, global_food 9) | members are 19 `bbg_*` interim columns; `sources/bloomberg/processed/bloomberg_monthly.csv` (whole-history replacement, 273.9 MB) |
| `food_price_index_WB` | interim column; `tools/build_wb_rtp.py` | `sources/wb_rtp/processed/wb_rtp_monthly.csv` (51.5 MB, also inflation/match-distance columns) |
| IDP national | `idp_admin0_monthly.csv` (cols `admin0Pcode, year, month, idp_ind, observed, reportingDate, ...`) | `/home/swl007007/ipcch-alphaearth-runs/p1-formal-d30-20261014/sources/idp_admin0_monthly__idp_admin0_monthly.csv` (193,702 B, sha `a1ebb82a...`) |
| IDP local | `idp_ipcch_monthly.parquet` (cols `admin_code, iso3, year, month, idp, ..., idp_ffill6, pct_area_ffill6, n_dtm_units_ffill6, months_since_round_mean/max`; 1,251,627 rows, 6,227 admins, 2010-01..2026-09) | `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Processed_Dataset/IDP_DTM/output/idp_ipcch_monthly.parquet` (sha `8b2ba299...`) |
| Outcome history (5) | raw panel `overall_phase` via `build_label_ledger` / `history_observations` | `merged/IPCCH_202610_completed.csv` (1.8 GB, sha `09002869...`); build output `merged/build-new/history_observations.csv.gz` |
| GPP / nightlight / WFP (context) | interim columns; staged deltas `sources/{gosif_gpp,viirs_nightlight,wfp_price}/processed/*.csv` | |

## Caveats / Not Found (UNKNOWN / UNVERIFIED)

1. UNVERIFIED: the final multi-family Colab QA/merge code that produced the delivered monthly/seasonal ensembles (and their abs(z)>=6 blanking) was not located; seasonal 2022-2026 producer scripts not in S.
2. UNVERIFIED: existence/access of all referenced GEE assets (section 1f) and how the S2E3 VI and S2C3 PRCP/ET0 admin tables were spatially aggregated.
3. Method divergence: source scripts flag abs(z)>6 and keep values; delivered monthly table blanks abs(z)>=6 prcp_z/sm_z source values before ensembling; workload doc says soil abs(z)>20; seasonal audit reports ens_sd=0 for some single-source rows.
4. Admin roster counts differ by artifact: 6,227 (GEE scripts, climate tables, IDP local, ACLED panel months, unit_iso3), 6,188 (ACLED new months / admin_keys), 6,226 (design.md training roster). Not reconciled here.
5. spi03, spei03 and evi_anom have no 2026-08 values in the delivered monthly table.
6. R55 order note: research code applies the override table before the centroid rule; an unmapped-admin1 condition fails the `admin1_all_mapped` gate but the output CSV is written first; countries outside the layer are dropped and reported, not failed.
7. UNVERIFIED: whether an H2/H8/H14 feature builder exists; `VF` supports only H in (0, 6, 12).
8. The outcome-history selection uses report month, not an availability month (relevant to R62 snapshot fields).
