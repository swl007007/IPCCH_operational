# Climate EE script specs (porting grade) — 7 JS scripts + 2 Python locators

Source folder: `S = /mnt/c/users/swl00/ifpri dropbox/weilun shi/IPCCH_shared_folder`
Read-only extraction, 2026-10-30. Line numbers are those of the files as of the
extraction date (`cat -n`). `ROOT = 'projects/han-sandbox-505315/assets/'` in every
script. Note (from `research/cp3/climate-ee-readonly/ee_probe_ro.json`): none of
the private `ROOT` assets can be read from the current EE project
(`food-crisis-modeling-enso`); every private asset below is currently a missing
prerequisite. The public collections can be read.

Common conventions used in all JS scripts (not repeated per script):

- Admin universe: 25 FeatureCollections
  `ROOT + 'IPCCH_ADMIN_STATIC_CALENDAR_CROPFRAC_V1_G' + pad2(g)` for g = 00..24,
  merged and then `.sort('admin_idx')`. Expected 6227 rows, unique `admin_idx`
  and `admin_code`. The primary key is `admin_code`.
- Safe-value helper `number(v, fb)` = `ee.Number(If(IsEqual(v,null), fb, v))`;
  `flag(c)` = `ee.Number(If(c,1,0))`.
- Output geometry is always `feature.geometry().centroid(100)` (maxError 100 m).
  The full polygon is used only for the reduction.
- `MISSING = -9999` (named `MISSING_VALUE` in some scripts).
- "seed" pattern: `ee.Image.constant(0).rename(b).toFloat().setDefaultProjection(PROJ).selfMask()`.
  This is a fully masked image merged into a collection. It guarantees the band
  exists when the filtered collection is empty. It adds no data: `count()` stays
  the same and `sum()`/`mean()` ignore it.
- Pixel-area weighting: `ee.Image.pixelArea().setDefaultProjection(PROJ)`, with
  reduction `crs: PROJ, scale: PROJ.nominalScale()` (native grid of the source).

---------------------------------------------------------------------------------

## 0. Structural summary and porting hazards

| Script | EE structure | Season/month window | Completeness rule for value |
|---|---|---|---|
| monthly/temperature | `reduceRegions` per month over 100-admin blocks | calendar month | none (any valid day) |
| monthly/soil_moisture | `reduceRegions` per month over 200-admin blocks | calendar month, all sub-daily samples averaged | none (any sample) |
| monthly/ndvi_evi | **no rasters**: arithmetic on S2E3 admin×16-day tables; wide output | 16-day overlap-day weights | full coverage ≥0.999999 |
| seasonal/rainfall | **paint() calendar rasters** (relative-day images), daily collection masked per pixel, ONE `reduceRegions` over all 6227 admins | per-pixel painted s1/s2 calendar | pixel coverage ≥0.999999 |
| seasonal/temperature | `FeatureCollection.map`: per-feature `filter(time_start)` + per-feature `reduceRegion` (2 per admin) | exact vector calendar per feature, capped at 2022-01-01 | none |
| seasonal/soil_moisture | `admins.iterate`: per-feature overlap-weighted sum of 24 cached monthly z images + ONE `reduceRegion` per admin (s1+s2 bands) | exact vector calendar, monthly overlap days, capped at 2022-01-01 | none (status only) |
| seasonal/ndvi | **no rasters**: `FeatureCollection.map` arithmetic on S2E3 tables | exact vector calendar × 16-day overlap days | full coverage ≥0.999999 |

Hazards and surprises:
1. Every seasonal JS script is capped to season_year 2015-2021 (`DATA_END_EXCLUSIVE`/`CURRENT_DATA_END_EXCLUSIVE = '2022-01-01'`, rainfall RUN_YEAR is hard-limited to 2015..2021, NDVI joins current tables 2014..2021 only). Every monthly JS script has `LAST_MONTH = 2026 ? 8 : 12`.
2. The source key differs for GLDAS: monthly `sm_z_month_gldas21`, seasonal `sm_z_gs_gldas`.
3. The seasonal rainfall paint() calendar gives each pixel one admin's calendar (overlap/edge collisions). The "exact collision patch" stage named in `calendar_method` is not in this folder. Rainfall also has no Feb-29→Feb-28 clamp (non-leap Feb 29 → Mar 1), while the other EE scripts clamp any day to month end and the Python `exact_date` only maps Feb 29 → Feb 28 (other bad days are invalid).
4. `prcp_anom_gs` is a seasonal **sum** of daily anomalies (mm). `prcp_z_gs` is an overlap-day-weighted mean of **complete-month** monthly-total z. Seasonal temperature anomalies are pixel means over valid days.
5. Seasonal rainfall `gs_duration_calendar_days` is set to the recalculated duration, not the static asset value (the static value is in `gs_duration_static_asset_days`).
6. The NDVI/EVI (monthly and seasonal) and SPI/SPEI scripts consume precomputed admin-level tables (`S2E3_VI_*`, `S2C3_DROUGHT_ADMIN_*`, `S2C3_ET0_PATCH32_*`). None of their producer code is in the shared folder. The same is true of all `STAGE2A/2B/2D` baseline images. None are readable from the current EE project.
7. Status vocabularies differ: seasonal NDVI has no `PARTIAL_DATA` (partial → `MISSING_DATA`); seasonal soil adds `INVALID_GEOMETRY`; monthly scripts have no `INVALID_CALENDAR`.
8. Output naming differs: monthly NDVI is wide (`ndvi_anom_month_{sensor}_{YYYYMM}`). Seasonal temperature writes both `{m}_gs` and `{m}_gs_{src}`. Coverage/status for `hot_days_p95` use the stem `hot_days`. The rainfall value columns are `{root}` with the season in a `season` column.

---------------------------------------------------------------------------------

## 1. `S/monthly/temperature.js` (823 lines)

### 1.1 Settings / sources
- L5 `RUN_SOURCE = 'ERA5LAND'` ('ERA5LAND' | 'CPC'). L8 `TARGET_YEAR` (2015..2026, checked L37).
- L13-18: `EXPECTED_ADMINS=6227`, `ADMINS_PER_TASK=100`, `TASKS_PER_RUN=100`, `TILE_SCALE=8`, `MAX_PIXELS_PER_REGION=1e10`, `MISSING=-9999`.
- L20-22: `GDD_BASE_C=10`, `GDD_CAP_C=30`, `EDD_CRITICAL_C=30`.
- L24-30: `METRICS = ['tmean_anom','tmax_anom','hot_days_p95','gdd','edd']`.
- L45: `LAST_MONTH = TARGET_YEAR === 2026 ? 8 : 12` (hard-coded cutoff), months 1..LAST_MONTH.
- L49-50: `VERSION = 'V1_MONTHLY_' + TARGET_YEAR + '_ALL6227'`.
- L127-151 sources:
  - CPC: `ee.ImageCollection('NOAA/CPC/Temperature').select(['tmin','tmax'])`, already in deg C; `SOURCE_KEY='cpc'`, `SOURCE_LABEL='CPC'`; `PROJ = first().select('tmax').projection()`.
  - ERA5LAND: `ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR').select(['temperature_2m','temperature_2m_min','temperature_2m_max'])`, in Kelvin; `SOURCE_KEY='era5land'`, `SOURCE_LABEL='ERA5LAND'`; `PROJ = first().select('temperature_2m').projection()`.
  - One image per day for both sources (daily products). No sub-daily aggregation is done in this script.

### 1.2 Private assets
- Admin FC (common).
- Baselines L159-173: `ROOT + 'STAGE2B_TEMP_BASELINE_1991_2020_' + SOURCE_LABEL + '_M' + pad2(m)` for m=1..12, each `.set('calendar_month', m)`.
  Band names (selected by calendar day, L175-195 `dailyBaseline`): `'tmean_normal_d' + DD`, `'tmax_normal_d' + DD`, `'tmax_p95_d' + DD`, where `DD = ee.Number(date.get('day')).format('%02d')`, from the image whose `calendar_month == date.get('month')`.
  So each monthly baseline image holds up to 31 day-bands for each of the 3 prefixes.
  Feb 29: band `..._d29` of M02 is used. Whether that band exists is unknown.
- Admin properties read: `admin_code`, `admin_idx`, `group_id` (+ geometry).

### 1.3 Pixel computation (`dailyMetrics` L198-271), per daily image
- CPC: `tmin=tmin`, `tmax=tmax`, `tmean=(tmin+tmax)/2`.
- ERA5: `tmean=temperature_2m-273.15`, `tmin=temperature_2m_min-273.15`, `tmax=temperature_2m_max-273.15`.
- `tmean_anom = tmean - tmean_normal_dDD`
- `tmax_anom = tmax - tmax_normal_dDD`
- `hot_days_p95 = tmax.gt(tmax_p95_dDD)` (0/1)
- `gdd = tmax.min(30).add(tmin.max(10)).divide(2).subtract(10).max(0)`
- `edd = tmax.subtract(30).max(0)`
- `.toFloat()`; copies `system:time_start`. Masks: the EE mask of each band is the intersection of the source band mask and the baseline band mask.

### 1.4 Temporal aggregation (`makeMonthlyImage` L274-311)
- Window `[fromYMD(y,m,1), advance(1,'month'))`, `SOURCE.filterDate(start,end).map(dailyMetrics)`. No seed is used here.
- `observed = daily.select(METRICS).count()` renamed `[tmean_anom_obs, tmax_anom_obs, hot_days_p95_obs, gdd_obs, edd_obs]`.
- `tmean_anom`, `tmax_anom` = `.mean()` over the month's daily images (per pixel, valid days only).
- `hot_days_p95`, `gdd`, `edd` = `.sum()` over valid days.
- No completeness requirement at pixel level.

### 1.5 Spatial reduction
- `makeReductionImage` L314-349: for each metric, `usable = obs.gt(0)`, `value = value.updateMask(usable)`; bands
  `{metric}_num = value*pixelArea`, `{metric}_area = pixelArea.updateMask(value.mask())`, `{metric}_obs_num = obs.updateMask(usable)*pixelArea`; `.toDouble()`.
- `reduceRegions` L362-369: `reducer: ee.Reducer.sum(), crs: PROJ, scale: PROJ.nominalScale(), tileScale: 8, maxPixelsPerRegion: 1e10`, over a block of 100 admins (one call per month).
- Per-feature post-processing L444-496, for each metric:
  - `area = number(get(m+'_area'),0)`; `present = area.gt(0)`
  - `value = present ? number(get(m+'_num'),0)/area.max(1e-12) : -9999`
  - `observedDays = present ? number(get(m+'_obs_num'),0)/area.max(1e-12) : 0`
  - `coverage = (observedDays/duration.max(1)).clamp(0,1)`, where `duration = end.difference(start,'day').toInt()`
  - `status = !present ? 'MISSING_DATA' : (observedDays >= duration-1e-6 ? 'COMPLETE' : 'PARTIAL_DATA')`
  - `valid_area_km2 = present ? area/1e6 : -9999`
- QA L498-523: `qa_hot_above_month_duration = hot != -9999 && hot > duration+1e-6`; `qa_negative_gdd = gdd != -9999 && gdd<0`; `qa_negative_edd` likewise.

### 1.6 Output columns (L377-496)
Keys: `admin_code, admin_idx, group_id, year=TARGET_YEAR, season_year=TARGET_YEAR, month, month_id='mMM', season='mMM'`.
Window: `aggregation_start_date` (yyyy-MM-dd), `aggregation_end_date_inclusive`, `aggregation_end_exclusive`, `month_duration_days`.
Values: `{metric}_month_{src}` (src = `cpc` | `era5land`), `{metric}_observed_days_area_weighted`, `{metric}_coverage_fraction`, `{metric}_status`, `{metric}_valid_area_km2`, `qa_hot_above_month_duration`, `qa_negative_gdd`, `qa_negative_edd`.
Verbatim literals:
- `temporal_unit: 'calendar_month'`, `temporal_window_method: 'day1_to_next_month_day1_exclusive'`
- `source: SOURCE_KEY`, `source_label: SOURCE_LABEL`, `variable_family: 'temperature'`, `baseline_period: '1991_2020'`
- `climate_crop_mask_used: 0`, `crop_fraction_multiplied: 0`
- `spatial_method: 'pixel_metric_then_pixelarea_weighted_admin_mean'`, `temperature_unit: 'degrees_C'`
- `cpc_tmean_method: CPC ? '(tmax+tmin)/2' : 'NOT_APPLICABLE'`
- `era5_kelvin_conversion: ERA5 ? 'subtract_273.15' : 'NOT_APPLICABLE'`
- `hot_day_threshold: 'source_calendar_day_tmax_p95_1991_2020'`
- `gdd_formula: 'max(0,(min(tmax,30)+max(tmin,10))/2-10)'`, `gdd_base_c`, `gdd_cap_c`, `edd_critical_c`
- `coverage_used_as_filter: 0`, `observation_policy: 'any_valid_observation_within_calendar_month'`
- `missing_day_policy: 'observed_days_only_no_imputation_no_rescaling'`
- `tmean_anom_temporal_aggregation: 'mean_over_valid_days'`, `tmax_anom_temporal_aggregation: 'mean_over_valid_days'`
- `hot_days_temporal_aggregation: 'sum_over_valid_days'`, `gdd_temporal_aggregation: 'sum_over_valid_days'`, `edd_temporal_aggregation: 'sum_over_valid_days'`
- `stage3_version: VERSION`, `production_block`, `production_offset`, `production_admin_count`

### 1.7 Not algorithm
L533-566 `buildTask` (merges months 1..LAST_MONTH for a block of `ALL_ADMINS.toList(count, offset)`); L569-586 `taskName` = `'TEMP_MONTHLY_ALL5_'+LABEL+'_Y'+year+'_B'+pad2+'_OFF'+pad4+'_N'+pad3+'_M'+pad2(MONTH_COUNT)+'_'+VERSION`; L589-605 job list; L611-800 asset/task inventory, resume and `Export.table.toAsset`; L803-823 preview of one admin in January.

---------------------------------------------------------------------------------

## 2. `S/monthly/soil_moisture.js` (733 lines)

### 2.1 Settings / sources
- L5 `RUN_SOURCE = 'ERA5LAND'` ('ERA5LAND' | 'GLDAS21'); L8 `TARGET_YEAR` 2015..2026.
- L13-18 `EXPECTED_ADMINS=6227, ADMINS_PER_TASK=200, TASKS_PER_RUN=100, TILE_SCALE=8, MAX_PIXELS_PER_REGION=1e10, MISSING=-9999`.
- L21-23 `BASELINE_START_YEAR=2001, BASELINE_END_YEAR=2020, BASELINE_PERIOD='2001_2020'` (baseline is loaded, not recomputed).
- L26-44 `SOURCE_CONFIGS`:
  - ERA5LAND: `key 'era5land'`, label `'ERA5LAND'`, `'ECMWF/ERA5_LAND/DAILY_AGGR'`, band `'volumetric_soil_water_layer_1'`, `expectedImagesPerDay: 1`, unit `'m3_m3'`.
  - GLDAS21: `key 'gldas21'`, label `'GLDAS21'`, `'NASA/GLDAS/V021/NOAH/G025/T3H'`, band `'SoilMoi0_10cm_inst'`, `expectedImagesPerDay: 8`, unit `'kg_m2'`.
  - No unit conversion is applied. Sub-daily GLDAS 3-hourly samples are **not** aggregated to days: the monthly mean is taken directly over all samples in the month.
- L60 `LAST_MONTH = TARGET_YEAR === 2026 ? 8 : 12`. L64-69 `VERSION = 'V1_MONTHLY_SOIL_' + C.label + '_Y' + TARGET_YEAR + '_ALL6227'`.
- L145-150 `SOURCE = ImageCollection(C.collection).select(C.band)`; `PROJ = first().select(C.band).projection()`.

### 2.2 Private assets
- Baselines L160-176: `ROOT + 'STAGE2D_SOIL_BASELINE_' + '2001_2020' + '_' + C.label + '_M' + pad2(m)`, `.set('calendar_month', m)`. Bands `sm_monthly_mean`, `sm_monthly_sd`. Indexed by calendar month.
- Admin properties read: `admin_code`, `admin_idx`, `group_id`.

### 2.3 Pixel computation (`makeMonthlySoilImage` L179-250)
1. `daysInMonth = end.difference(start,'day')`; `expectedSamples = daysInMonth * C.expectedImagesPerDay`.
2. `raw = SOURCE.filterDate(start,end).map(img -> img.rename('sm').toFloat())`.
3. `target = fromImages([seed]).merge(raw).reduce(ee.Reducer.mean().combine({reducer2: ee.Reducer.count(), sharedInputs: true}))` → bands `sm_mean`, `sm_count`.
4. `currentMean = sm_mean`; `sampleCount = sm_count.unmask(0, false)`.
5. `monthlyZ = (currentMean - sm_monthly_mean) / sm_monthly_sd`, `.updateMask(sampleCount.gt(0)).updateMask(baselineSd.gt(0))`, renamed `sm_z`.
6. Output bands: `sm_z`, `sample_count`, `current_monthly_sm_mean`, `baseline_monthly_mean`, `baseline_monthly_sd`, `expected_sample_count` (constant).
- No completeness requirement: the mean of whatever samples are available is used.

### 2.4 Spatial reduction
- `makeReductionImage` L253-279: `sm_z_num = z*pixelArea`; `sm_z_area = pixelArea.updateMask(z.mask())`; `sample_count_num = count.updateMask(z.mask())*pixelArea`; `monthly_sm_mean_num = currentMean.updateMask(z.mask())*pixelArea`; `.toDouble()`.
- `reduceRegions` L294-301: sum, `crs PROJ`, `scale nominalScale`, `tileScale 8`, `maxPixelsPerRegion 1e10`; block of 200 admins, one call per month.
- Post-processing L306-350:
  - `area = number(sm_z_area,0)`, `hasValue = area>0`, `safeArea = area.max(1e-12)`
  - `value = hasValue ? sm_z_num/safeArea : -9999`
  - `observedSamples = hasValue ? sample_count_num/safeArea : 0`
  - `rawMonthlyMean = hasValue ? monthly_sm_mean_num/safeArea : -9999`
  - `sampleFraction = (observedSamples/expectedSamples.max(1)).clamp(0,1)`
  - `status = !hasValue ? 'MISSING_DATA' : (observedSamples >= expectedSamples-1e-6 ? 'COMPLETE' : 'PARTIAL_DATA')`
  - `qa_abs_sm_z_gt6_warning = flag(hasValue && |value|>6)`

### 2.5 Output columns (L355-429)
Keys and window fields are the same as temperature (`admin_code, admin_idx, group_id, year, season_year, month, month_id, season, aggregation_start_date, aggregation_end_date_inclusive, aggregation_end_exclusive, month_duration_days`).
Value: `'sm_z_month_' + C.key` → `sm_z_month_era5land` | **`sm_z_month_gldas21`**.
Other fields: `expected_samples_per_pixel`, `observed_samples_area_weighted`, `sample_coverage_fraction`, `sm_z_status`, `valid_area_km2`, `monthly_sm_mean_admin`, `qa_abs_sm_z_gt6_warning`, `missing_data_sentinel`.
Verbatim literals: `temporal_unit: 'calendar_month'`, `temporal_window_method: 'day1_to_next_month_day1_exclusive'`, `source_native_unit: C.unit`, `variable_family: 'soil_moisture'`, `variable_requested: 'sm_z'`, `baseline_period: '2001_2020'`,
`soil_z_method: 'pixel_monthly_mean_z_then_pixelarea_weighted_admin_mean'`,
`baseline_sd_policy: 'original_sd_gt_zero_only_no_new_threshold'`, `climate_crop_mask_used: 0`, `crop_fraction_multiplied: 0`,
`spatial_method: 'pixel_metric_then_pixelarea_weighted_admin_mean'`, `coverage_used_as_filter: 0`, `complete_month_required: 0`,
`incomplete_month_policy: 'monthly_mean_of_available_samples_no_imputation'`,
`missing_sample_policy: 'available_samples_only_no_imputation_no_rescaling'`, `stage_version: VERSION` (note: `stage_version`, not `stage3_version`), `production_block`, `production_offset`, `production_admin_count`.

### 2.6 Not algorithm
L439-472 `buildTask`; L475-492 `taskName` `'SOIL_MONTHLY_SMZ_'+label+'_Y'+year+'_B..'+'_OFF..'+'_N..'+'_M..'+'_'+VERSION`; L495-511 jobs; L526-711 inventory/resume/export; L714-733 preview.

---------------------------------------------------------------------------------

## 3. `S/monthly/ndvi_evi.js` (617 lines) — **TABLE-ONLY: no raster reduction**

The script computes nothing from MODIS rasters (L616: "No new MODIS raster reduceRegions is performed").
It does overlap-day arithmetic on precomputed admin × 16-day-composite mean tables (S2E3 V3 CMG). The code that produces those tables is **not in this folder**.

### 3.1 Settings
- L7-8 `STATIC_PREFIX`; L10 `ADMIN_ID='admin_code'`; L11 `EXPECTED_ADMINS=6227`; L12 `MISSING=-9999`; L13 `FULL_COVERAGE_TOLERANCE=0.999999`; L14 `DAY_MS=86400000`.
- L16-19 `SENSOR_FIRST_DOY = {terra: 1, aqua: 9}`; L21-24 `SENSOR_LABELS = {terra:'TERRA', aqua:'AQUA'}`.
- L26 `VERSION = 'V1_MONTHLY_WIDE_ADMIN16D_CMG'`.
- L30-51 `TASK_DEFINITIONS`: terra 2015-2020, terra 2021-2026, aqua 2015-2020, aqua 2021-2026 (4 tasks). L206 per year `lastMonth = year === 2026 ? 8 : 12`.

### 3.2 Nominal 16-day intervals (`observationInterval` L78-105, client-side JS)
- `startDoy = firstDoy + (slot-1)*16`; `start = Date.UTC(year, 0, startDoy)` (slot 1..23).
- `end = start + 16 days` for slot < 23; slot 23: `end = Date.UTC(year+1, 0, firstDoy)`. For Aqua this means DOY 1-8 belong to the previous year's slot 23.
- `tag = YYYYMMDD` of the nominal start (UTC).

### 3.3 Private assets and property names
- Baseline: `ROOT + 'S2E3_VI_BASE_ADMIN_2003_2020_' + SENSOR_LABEL + '_CMG_P' + pad2(part) + '_V3'`, part 1..4 merged (L285-303). Property per slot: `{index}_base_s{SS}_mean` (L108-115), index ∈ {ndvi, evi}, SS = 01..23.
- Current: `ROOT + 'S2E3_VI_CURRENT_ADMIN_' + SENSOR_LABEL + '_Y' + year + '_CMG_V3'` for every calendar year needed (L350-364). Property per composite: `{index}_{YYYYMMDD}_mean`, where YYYYMMDD is the nominal interval start tag (L117-126).
- Join (L247-282): `ee.Join.saveFirst('_right_row')` on `admin_code == admin_code`. The right-hand properties are combined onto the left with `combine(..., false)`, so left values win on key collision. Applied as static ⨝ baseline ⨝ current[Y-1] ⨝ ... ⨝ current[Y].
- Admin properties read: `admin_code, admin_idx, group_id, crop_fraction`.
- QA provenance strings (the QA itself is applied upstream): `vi_qa_rule: 'SUMMARYQA_0_OR_1_AND_PIXEL_1KM_GT_0'`, `spatial_product: 'CMG_0P05_DEG'`.

### 3.4 Monthly computation (`buildMonthPlan` L129-195 + `calculateMonthlyIndex` L391-452)
- Month `[Date.UTC(y,m-1,1), Date.UTC(y,m,1))`. Plan parts are every (calendarYear ∈ {y-1, y}, slot 1..23) whose interval overlaps the month by `overlapDays > 0` (fractional days in ms/DAY_MS). The script throws if Σ part days ≠ month duration (L171).
- For each part: `current` = property `{index}_{tag}_mean` and `baseline` = `{index}_base_s{slot}_mean`. A null property gives value 0 and valid 0 (`safePropertyNumber` L370-388).
  `valid = cur.valid*base.valid`; `anomaly = cur - base`; `validDays = part.days*valid`;
  `weightedSum += anomaly*validDays`; `coveredDays += validDays`; `contributingComposites += valid`.
- `coverage = (coveredDays/max(duration,1)).max(0).min(1)`; `complete = coverage >= 0.999999`;
  `anomalyMean = weightedSum/max(coveredDays,1)`; `value = complete ? anomalyMean : -9999`.
  This requires full support: every overlapping composite must be present.

### 3.5 Output (wide, one row per admin per task, L455-534)
- Per month `ym = YYYYMM`: `ndvi_anom_month_{sensor}_{YYYYMM}`, `ndvi_valid_days_{sensor}_{YYYYMM}`, `ndvi_coverage_{sensor}_{YYYYMM}`, and the same for `evi_`. sensor = `terra` | `aqua`.
  So this is **wide**, not long `{base}_month_{src}`; it has to be melted downstream.
- Literals (L460-482): `sensor`, `sensor_label`, `block_start_year`, `block_end_year`, `baseline_period: '2003_2020'`,
  `baseline_method: 'SENSOR_SPECIFIC_SAME_16DAY_SLOT_ADMIN_MEAN'`, `temporal_unit: 'CALENDAR_MONTH'`,
  `temporal_method: '16DAY_ANOMALY_OVERLAP_DAY_WEIGHTED_MONTHLY_MEAN'`,
  `input_level: 'ADMIN_16DAY_MEAN_FROM_S2E3_V3_CMG_TABLES'`, `spatial_product: 'CMG_0P05_DEG'`,
  `vi_qa_rule: 'SUMMARYQA_0_OR_1_AND_PIXEL_1KM_GT_0'`, `climate_crop_mask_used: 0`,
  `crop_fraction_role: 'STATIC_FEATURE_ONLY'`, `complete_month_required: 1`, `missing_data_sentinel: -9999`,
  `missing_data_policy: 'NO_IMPUTATION_NO_TEMPORAL_RESCALING'`, `stage_version: VERSION`.
- Collection properties L550-560 (`output_format: 'WIDE_ONE_ROW_PER_ADMIN'`, ...).

### 3.6 Not algorithm
L305-318 `currentYearsNeeded`; L537-561 `buildTaskCollection`; L568-606 export with task name `'VI_MONTHLY_WIDE_NDVI_EVI_'+LABEL+'_Y'+start+'_'+end+'_'+VERSION`; prints.

---------------------------------------------------------------------------------

## 4. `S/seasonal/rainfall.js` (2612 lines) — **RASTERIZED CALENDAR (paint) design**

### 4.1 Settings / sources
- L21 `RUN_YEARS=[2019]`; L23 `RUN_SOURCE='chirps'`; L25 `RUN_FAMILIES=['ANOM_Z']` ('ANOM_Z' | 'RAIN_CDD').
- L29 `CURRENT_DATA_END_EXCLUSIVE = '2022-01-01'`; L31 `RAIN_THRESHOLD_MM = 1.0`; L32 `MISSING_VALUE=-9999`; L34 `ANOM_Z_TILE_SCALE=8`; L35 `RAIN_CDD_TILE_SCALE=16`; L37 `MAX_PIXELS_PER_REGION=1e9`.
- L173-180: RUN_YEAR must be 2015..2021 (hard limit).
- L44-66 `SOURCE_CONFIGS`:
  - chirps: `'UCSB-CHC/CHIRPS/V3/DAILY_RNL'`, band `'precipitation'`, `multiplierToMm 1`, label `'CHIRPS'`
  - persiann: `'NOAA/PERSIANN-CDR'`, `'precipitation'`, ×1, `'PERSIANN'`
  - era5land: `'ECMWF/ERA5_LAND/DAILY_AGGR'`, `'total_precipitation_sum'`, ×1000 (m → mm), `'ERA5LAND'`
- Daily raw (L673-705): `filterDate(bounds.start, bounds.end).select(band).map(img*multiplier .max(0) .rename('prcp_mm').toFloat())`, sorted by time. One image per day.
- `projection = first().projection()` (L276-286).
- L143-149 `coverageIsUsable(c) = c.gte(0.999999)`.

### 4.2 Private assets and admin properties
- Admin FC. L213-242 add `s1_calendar_valid_num = If(get('s1_calendar_valid'),1,0)` and the same for s2. This is a truthy test, so `s*_calendar_valid` may be boolean or number.
- Baselines (L856-866 and L1408-1422): `ROOT + 'STAGE2A_PRCP_BASELINE_1991_2020_' + config.label + '_M' + pad2(m)`, `.set('calendar_month', m)`. Bands used:
  `daily_normal_dDD` (anomaly, selected by calendar day of the observation date) and `monthly_total_mean_mm`, `monthly_total_sd_mm` (z).
- Calendar properties painted (L337-437): `{s}_calendar_valid_num`, `{s}_sos_month`, `{s}_sos_day`, `{s}_eos_month`, `{s}_eos_day`, `{s}_cross_year`.
- `REDUCTION_PROPERTIES` (L1831-1861) kept on the output: `admin_code, admin_idx, group_id, admin_area_km2, crop_fraction`, and for s1 and s2: `_sos, _eos, _sos_month, _sos_day, _eos_month, _eos_day, _duration_days, _cross_year, _calendar_valid, _calendar_valid_num, _calendar_quality`.

### 4.3 How the per-admin season window is implemented (item 8)
The calendar is a **per-pixel raster**, not a per-feature filterDate:
- `propertyImage(p) = ee.Image(0).toFloat().paint(staticAdmins, p).setDefaultProjection(projection)` (L288-301). All 6227 admins are painted into one image. Pixels outside any admin are 0, so they are invalid.
  Where polygons overlap or share a pixel, a pixel holds **only one admin's calendar** (paint order). The output literal `calendar_method: 'V6_FAST_BASE_FIXED_ADMIN_CALENDAR_THEN_EXACT_COLLISION_PATCH'` refers to a later "exact collision patch" stage, which is **not in this folder**.
- Relative-day coordinates: origin = Jan 1 of RUN_YEAR (L707-712). `monthDayOffset(monthImg, dayImg, year)` (L303-335) = `day-1 + daysBeforeMonth(year, month)` via 12 `where(monthImage.eq(m), ...)` (JS `daysBeforeMonth` uses Date.UTC, so it is leap-aware).
- `calendarImages(season, year)` (L337-437):
  `sameYearStart = offset(sos, year)`; `previousYearStart = offset(sos, year-1) - daysInYear(year-1)`;
  `start = sameYearStart.where(cross_year==1, previousYearStart)`; `end = offset(eos, year) + 1` (exclusive);
  `duration = end - start`; `valid = calendar_valid_num==1 && duration>0 && duration<=367`.
  No Feb-29 clamp: Feb 29 in a non-leap year maps to Mar 1 (offset arithmetic). This differs from the `use_Feb28` rule in the other seasonal scripts.
- `activeOnDate(cal, relDay) = valid && start <= relDay && end > relDay` (L439-454), with `relDay = date.difference(origin,'day').floor()`.
- `overlapDays(cal, a, b) = (min(end,b) - max(start,a)).max(0).updateMask(valid)` (L456-484).
- Date range loaded (L491-658 `requiredDateBounds`): over all valid admins and both seasons, `start = fromYMD(year-cross, sos_month, sos_day)`, `endExcl = fromYMD(year, eos_month, eos_day)+1d`.
  The range is `[first day of month(min start), first day of month after (max endExcl-1d))`, then `end = min(that, CURRENT_DATA_END_EXCLUSIVE)`.
- season_year = RUN_YEAR = EOS year. A cross-year season starts in RUN_YEAR-1.

### 4.4 Metrics (pixel level)
- `finishDailySum(prepared, season, cal, name)` L768-840: `withSeed = prepared.merge(seed(season+'_value'))`; `validDays = count()`;
  `coverage = (validDays/cal.duration).clamp(0,1).unmask(0).updateMask(cal.valid)`; `usable = coverage>=0.999999 && valid`;
  `value = sum().updateMask(usable).updateMask(valid)`. Output bands `name`, `name+'_coverage_fraction'`.
- **prcp_anom** (L847-1018): per day, `anomaly = prcp_mm - daily_normal_dDD` (baseline M=date month, DD=date day);
  bands `s1_value = anomaly.updateMask(activeOnDate(s1))` and the same for s2. Then finishDailySum gives the **seasonal SUM of daily anomalies (mm)**.
  Root `'prcp_anom_gs_' + key`.
- **rainy_days** (L1025-1129): `rainy = prcp_mm.gte(1.0).toFloat()`, masked by active, then the finishDailySum sum (count of rainy days). Root `'rainy_days_gs_' + key`.
- **cdd** (L1137-1392, pixel-first longest dry spell, array-based):
  per day: `dayImage = constant(relDay).toInt16()`; `observed = prcp_mm.mask().gt(0) && active`;
  `dry = prcp_mm.lt(1.0).unmask(0) && active && observed`;
  `reset_day = (cal.start-1).where(dry.not(), dayImage)` (Int16).
  `sequence.toArray()` per band gives [date,1] arrays. `latestReset = resetArray.arrayAccum(0, Reducer.max())`;
  `run = (dayArray - latestReset) * dryArray`; `max = run.arrayReduce(Reducer.max(),[0]).arrayGet([0,0])`.
  `observedDays = sum(observed)`; coverage and usable as above; value = max masked by usable and valid. Root `'cdd_gs_' + key`.
  Caveat: a date with *no image at all* creates no reset, so the gap counts as dry. Masked pixels reset (observed=0). The full-coverage rule protects against this in practice.
- **prcp_z** (L1400-1745): for calendarYear ∈ {RUN_YEAR-1, RUN_YEAR} × month 1..12 (24 months):
  `subset = raw.filterDate(month)`; `observedDays = (subset+seed).count()`; `completeMonth = observedDays.eq(daysInMonth)`;
  `total = sum()`; `z = (total - monthly_total_mean_mm)/monthly_total_sd_mm`, `.updateMask(sd>0).updateMask(completeMonth)`;
  `w_s = overlapDays(cal_s, relMonthStart, relMonthEnd).updateMask(z.mask()).unmask(0)`; `num_s += z.unmask(0)*w_s`; `den_s += w_s`.
  `coverage_s = (den_s/duration).clamp(0,1).unmask(0).updateMask(valid)`; `z_s = Σnum/Σden`, masked by usable (≥0.999999) and valid.
  This is a **monthly-total z weighted by season-overlap days** (whole months only). Root `'prcp_z_gs_' + key`.
- Family selection L1759-1798: ANOM_Z → [prcp_anom, prcp_z], tileScale 8, `coverageMetricRoot = 'prcp_anom_gs_'+key`, asset label `PRCP_ANOM_Z`. RAIN_CDD → [rainy_days, cdd], tileScale 16, `coverageMetricRoot='rainy_days_gs_'+key`, label `RAIN_CDD`.
- `metricImage.set('source_last_observation_in_requested_window', max time_start formatted 'YYYY-MM-dd' or 'NO_OBSERVATION')` (L728-752, L1814-1824).

### 4.5 Spatial reduction (L1863-2507)
- Bands `{s}_{root}` and `{s}_{root}_coverage_fraction` for s ∈ {s1,s2}. Reduction image:
  `{band}_area_sum = band*pixelArea` and `{band}_valid_area = band.mask()*pixelArea`, `.toDouble()`.
- **Exactly one** `reduceRegions` per task over all 6227 admins (`staticAdmins.select(REDUCTION_PROPERTIES)`), `Reducer.sum()`, `crs projection`, `scale nominalScale`, `tileScale 8|16`, `maxPixelsPerRegion 1e9` (L1938-1959).
- Per-feature, per-season rows (`makeSeasonRows`, L1961-2498). Two rows per admin (s1, s2):
  - `calendarValid = {s}_calendar_valid_num == 1`. Safe sos/eos: 1 if invalid. `gsStart = fromYMD(RUN_YEAR-cross, sos_m, sos_d)`, `gsEndIncl = fromYMD(RUN_YEAR, eos_m, eos_d)`, `gsEndExcl = +1d`, `recalculatedDuration = difference().toInt()`.
  - Per root: `hasValue = valid_area != null && >0`; `value = calendarValid && hasValue ? area_sum/valid_area : -9999` (no 1e-12 guard);
    `coverage = calendarValid && hasCoverage ? (cov_area_sum/cov_valid_area).clamp(0,1) : -9999`;
    `status = !calendarValid ? 'INVALID_CALENDAR' : (!hasValue ? 'MISSING_DATA' : (coverage>=0.999999 ? 'COMPLETE' : 'PARTIAL_DATA'))`;
    `{root}_valid_area_km2 = valid ? valid_area/1e6 : -9999`.
    The admin coverage is the mean of pixel coverage over valid-calendar pixels. The value is the mean over pixels with full coverage only.
  - `season_coverage_fraction = {coverageMetricRoot}_coverage_fraction`; `season_cover_pct = valid && cov>=0 ? cov*100 : -9999`.
- No abs(z) QA flag in this script.

### 4.6 Output columns
Row keys: `admin_code, admin_idx, group_id, admin_area_km2, crop_fraction, year=RUN_YEAR, season_year=RUN_YEAR, season ('s1'|'s2')`.
Values: `prcp_anom_gs_{src}`, `prcp_z_gs_{src}`, `rainy_days_gs_{src}`, `cdd_gs_{src}` (src = `chirps|persiann|era5land`), each with `_status`, `_coverage_fraction`, `_valid_area_km2`. The value columns have **no** s1_/s2_ prefix; the season is in the `season` column.
Other: `gs_sos, gs_eos, gs_duration_calendar_days` (**set to recalculatedDuration, not the static duration**), `gs_duration_recalculated_days`, `gs_duration_static_asset_days`, `qa_duration_static_mismatch`, `gs_start_date`, `gs_end_date_inclusive`, `gs_end_date_exclusive` ('YYYY-MM-dd' or `'INVALID_CALENDAR'`), `gs_cross_year, gs_calendar_valid, gs_calendar_quality`,
`source_last_observation_in_requested_window`, `requested_data_start_inclusive`, `requested_data_end_exclusive`, `historical_data_cap_exclusive: '2022-01-01'`, `season_coverage_fraction`, `season_cover_pct`.
Verbatim literals: `source: key`, `source_label: label`, `variable_family: 'precipitation'`, `variable_requested: 'prcp_anom|prcp_z'` or `'rainy_days|cdd'`,
`baseline_period: ANOM_Z ? '1991_2020_FOR_ANOM_AND_Z' : 'NOT_APPLICABLE'`, `target_year_is_partial_by_design: 0`, `target_year_data_scope: 'FULL_TARGET_YEAR'`,
`missing_data_sentinel: -9999`, `climate_crop_mask_used: 0`, `crop_fraction_multiplied: 0`,
`spatial_method: 'pixel_metric_then_pixelarea_weighted_admin_mean'`,
`calendar_method: 'V6_FAST_BASE_FIXED_ADMIN_CALENDAR_THEN_EXACT_COLLISION_PATCH'`, `rain_threshold_mm_day: 1.0`,
`reduce_regions_calls_per_task: 1`, `output_geometry: 'ADMIN_CENTROID_POINT'`, `stage3_version: 'V6_1_FAST_BASE_' + RUN_FAMILY + '_ONE_REDUCTION'`.

### 4.7 Not algorithm
L2517-2536 export `'STAGE3A_' + familyAssetLabel + '_BASE_ADMIN_' + label + '_Y' + year + '_V6_1'`; L2538-2612 prints and the year × family task loop.

---------------------------------------------------------------------------------

## 5. `S/seasonal/temperature.js` (1508 lines) — **per-feature vector calendar, map + reduceRegion**

### 5.1 Settings / sources
- L13 `RUN_SOURCE='ERA5LAND'` (or 'CPC'); L17 `TASKS_PER_RUN=10`; L18 `ADMINS_PER_TASK=100` (both enforced, L49); L21-22 `START_YEAR=2015, END_YEAR=2021`.
- L25 `DATA_END_EXCLUSIVE='2022-01-01'`; L27-29 `MISSING=-9999, TILE_SCALE=8, MAX_PIXELS=1e10`; L31-33 GDD/EDD constants as monthly (10/30/30).
- L35 `VERSION='V1_EXACT_ALL6227_VALIDOBS'`; L37-43 METRICS as monthly.
- Sources L170-209: identical to monthly temperature (CPC tmin/tmax in deg C; ERA5 DAILY_AGGR in K, minus 273.15; PROJ from tmax / temperature_2m).

### 5.2 Private assets
- Baselines L216-262: `STAGE2B_TEMP_BASELINE_1991_2020_{LABEL}_M{MM}`, same day-band names as monthly (`tmean_normal_dDD`, `tmax_normal_dDD`, `tmax_p95_dDD`, by calendar month and day of the observation date).
- Admin properties read: `admin_code, admin_idx, group_id, {s}_cross_year, {s}_sos_month, {s}_sos_day, {s}_eos_month, {s}_eos_day, {s}_duration_days, {s}_calendar_valid, {s}_sos, {s}_eos, {s}_calendar_quality`.

### 5.3 Calendar (`calendarDate` L94-116, `adminCalendar` L269-358)
- `calendarDate(y,m,d)` = `fromYMD(y,m,1).advance(min(d, lastDayOfMonth)-1, 'day')`. Any day past month end is clamped to the last day (Feb 29 non-leap → Feb 28, literal `'use_Feb28'`).
- `crossYear = number(cross_year,0)`; `start = calendarDate(seasonYear-crossYear, number(sos_month,1), number(sos_day,1))`;
  `endInclusive = calendarDate(seasonYear, number(eos_month,1), number(eos_day,1))`; `endExclusive = +1 day`; `duration = endExcl.difference(start,'day').toInt()`;
  `staticDuration = number(duration_days, duration)`; `valid = number(calendar_valid,0).eq(1) && duration>0`; `leapAdjustment = duration - staticDuration`.

### 5.4 Pixel / temporal computation (`calculate` L454-1001)
1. `permittedEnd = min(cal.endExclusive, DATA_END_EXCLUSIVE)`; `hasTime = permittedEnd > start` (L469-478).
2. **Per-feature window**: `raw = SOURCE.filter(system:time_start >= start.millis()).filter(system:time_start < permittedEnd.millis())` (L480-492).
3. `daily = fromImages([5-band masked seed]).merge(raw.map(dailyMetrics))`; `totals = sum()`, `counts = count()` (L494-514).
   `dailyMetrics` L365-447 is identical to monthly.
4. Per metric: `usable = counts.gt(0) && constant(cal.valid && hasTime)`. For `tmean_anom`/`tmax_anom`: `value = totals/counts.max(1)` (pixel mean over valid days); other metrics keep the seasonal sums.
   `value.updateMask(usable)`; bands `{m}_num = value*pixelArea`, `{m}_area = pixelArea.updateMask(value.mask())`, `{m}_obs = counts.updateMask(usable)*pixelArea`.
   There is **no minimum coverage**: a value is produced if any day was observed.
5. `reduceRegion({reducer: sum, geometry: feature.geometry(), crs: PROJ, scale: PROJ.nominalScale(), maxPixels: 1e10, tileScale: 8})` (L569-580).
6. Post-processing L746-874 per metric: `validArea = number(_area,0)`, `present = >0`, `value = present ? _num/validArea.max(1e-12) : -9999`,
   `observed = present ? _obs/validArea.max(1e-12) : 0`, `coverage = (observed/duration.max(1)).clamp(0,1)`,
   `status = !valid ? 'INVALID_CALENDAR' : (!present ? 'MISSING_DATA' : (observed >= duration-1e-6 ? 'COMPLETE' : 'PARTIAL_DATA'))`.
   Here `duration` is the full calendar duration, not the cap-truncated one.
7. QA L897-990: `qa_hot_above_duration` (hot > duration+1e-6), `qa_hot_above_observed` (hot > observed+1e-6), `qa_negative_gdd`, `qa_negative_edd`, `qa_gdd_above_duration_x20_warning` (gdd > 20*duration+1e-6), `qa_failed_semantic = max(hotAboveDuration, hotAboveObserved, negGdd, negEdd)`.

### 5.5 Item 8 — EE structure
`buildTask` L1027-1106: `admins = ALL_ADMINS.toList(100, offset)`; `s1 = admins.map(f -> calculate(f,'s1',year,block))`; the same for s2; `s1.merge(s2)`.
So the code is a server-side **`FeatureCollection.map` over features, and each feature builds its own `filter(time_start)` collection and runs its own `reduceRegion`** on its own polygon. There are 2 reduceRegions per admin (one per season), with no painting and no collision.

### 5.6 Output columns (L582-874)
Keys: `admin_code, admin_idx, group_id, year=seasonYear, season_year, season`.
Values: both `{metric}_gs` **and** `{metric}_gs_{src}` (same value), `{metric}_observed_days_area_weighted`, `{metric}_observed_days_on_metric_support`, `{metric}_valid_area_km2`, `{stem}_coverage_fraction`, `{stem}_status`. Here `stem = 'hot_days'` for `hot_days_p95`, otherwise the metric name.
Generic: `observed_days_area_weighted` (= gdd), `valid_area_km2` (gdd), `metric_status` (gdd), `metric_status_reference: 'gdd_only_use_individual_metric_statuses'`.
Calendar: `gs_sos, gs_eos, gs_cross_year, gs_calendar_valid (flag), gs_calendar_quality, gs_duration_calendar_days (static), gs_duration_recalculated_days, leap_day_adjustment, aggregation_start_date, aggregation_end_date_inclusive, aggregation_actual_end_exclusive (permittedEnd), aggregation_has_time`.
Verbatim literals: `variables_requested: 'tmean_anom_tmax_anom_hot_days_p95_gdd_edd'`, `baseline_period: '1991_2020'`, `requested_data_end_exclusive` and `source_data_end_exclusive: '2022-01-01'`,
`target_year_is_partial_by_design: 0`, `target_year_data_scope: 'FULL_GROWING_SEASON'`, `calendar_method: 'exact_admin_specific_vector_calendar'`, `calendar_feb29_nonleap_rule: 'use_Feb28'`, `temperature_unit: 'degrees_C'`,
`cpc_tmean_method`, `era5_kelvin_conversion` (as monthly), `climate_crop_mask_used: 0`, `crop_fraction_multiplied: 0`, `spatial_method: 'pixel_metric_then_pixelarea_weighted_admin_mean'`,
`hot_day_threshold: 'pixel_source_calendar_day_tmax_p95_1991_2020'`, `gdd_formula: 'max(0,(min(tmax,30)+max(tmin,10))/2-10)'`, `gdd_base_c, gdd_cap_c, edd_critical_c`, `coverage_used_as_filter: 0`,
`observation_policy: 'any_valid_observation_within_exact_gs'`, `missing_day_policy: 'observed_days_only_no_imputation_no_rescaling'`, the five `*_temporal_aggregation` strings as monthly,
`missing_data_sentinel: -9999`, `stage3_version: VERSION`, `production_scope: 'all_6227_admins_both_seasons'`, `production_block`, `production_admin_limit`.

### 5.7 Not algorithm
L1008-1025 `blockAdmins`; L1027-1106 collection-level properties (`block_assignment: 'all_static_admins_sorted_admin_idx_chunks_100'`, ...); L1115-1152 job names `'STAGE3B_TEMP_ALL5_EXACT_'+LABEL+'_Y'+year+'_B'+pad2+'_N'+pad3+'_V1_ALL6227_GEE'`; L1154-1503 inventory, resume and export planner; L1505-1508 note that ensembles happen later in Colab.

---------------------------------------------------------------------------------

## 6. `S/seasonal/soil_moisture.js` (798 lines) — **monthly z cache images + per-feature overlap weighting**

### 6.1 Settings / sources
- L8 `RUN_SOURCE='GLDAS21'`; L10 `YEARS=[2015..2021]`; L12 `CACHE_YEARS=[2014..2021]`; L13-15 `EXPECTED_ADMINS=6227, ADMINS_PER_TASK=100, MAX_NEW_TASKS=100`.
- L20 `DATA_END_EXCLUSIVE='2022-01-01'`; L21-24 `MISSING=-9999, TILE_SCALE=8, MAX_PIXELS=1e10, DAY_MS=86400000`.
- L25 `VERSION='V2_EXACT_ALL6227_ONE_REDUCE_ADMIN_N100'`; L27 `CACHE_VERSION='SM_MONTHLY_EXACT_2014_2021_QPACK_V1'`.
- L30-37 `SOURCE_CONFIGS`: ERA5LAND `key 'era5land'`, `ECMWF/ERA5_LAND/DAILY_AGGR`, `volumetric_soil_water_layer_1`, `samplesPerDay 1`, `m3_m3`;
  GLDAS21 **`key 'gldas'`** (monthly script uses `'gldas21'`), `NASA/GLDAS/V021/NOAH/G025/T3H`, `SoilMoi0_10cm_inst`, `samplesPerDay 8`, `kg_m2`.
- L48-50 `SOURCE = select(C.band)`; `PROJ = first().projection()`; `PIXEL_AREA = pixelArea().setDefaultProjection(PROJ)`.

### 6.2 Private assets
- Baselines L90-95: `ROOT + 'STAGE2D_SOIL_BASELINE_2001_2020_' + C.label + '_M' + pad2(m)` in a JS array indexed `[month-1]`. Bands `sm_monthly_mean`, `sm_monthly_sd` (checked in preflight L501).
- **Cache images** L175-179: `ROOT + 'STAGE2D_SM_ZCACHE1521_' + C.label + '_Y' + year + '_Q' + quarter + '_V1_GEE'`. One image per year-quarter has 3 months × 5 bands named `m{MM}_numerator, m{MM}_days, m{MM}_incomplete, m{MM}_excess, m{MM}_sample_count` (L132-133, L191-201).
  Cache properties (L203-210): `cache_version, source, source_label, source_id, source_band, source_native_unit, expected_samples_per_day, baseline_period:'2001_2020', year, quarter, months, requested_data_end_exclusive, complete_month_required:0, coverage_used_as_filter:0, value_definition:'monthly_mean_z_available_samples', grid_crs, grid_transform`.
  Export L645-671: `Export.image.toAsset({region: Rectangle([-180,-90,180,90],'EPSG:4326',false), crs: grid.crs, crsTransform: grid.transform (native), pyramidingPolicy {'.default':'sample'}, shardSize 128, maxPixels 1e9})`.
  The cache is an optimisation only. `rawMonthly` can be computed on the fly instead.
- Admin properties read: all, via `feature.toDictionary()` into the bundle. Used: `admin_code, admin_idx, group_id, {s}_cross_year, {s}_sos_month, {s}_sos_day, {s}_eos_month, {s}_eos_day, {s}_duration_days, {s}_calendar_valid, {s}_sos, {s}_eos, {s}_calendar_quality`.

### 6.3 Pixel monthly z (`rawMonthly(year, month)` L141-172)
- `SOURCE.filterDate(monthStart, monthEnd)` (JS ISO dates) `.select([0]).rename('sm').toFloat()`, plus a seed, then `reduce(mean.combine(count, sharedInputs))`.
  All samples in the month are averaged (GLDAS 3-hourly averaged directly, no daily step).
- `sampleCount = sm_count.unmask(0,false)`; `monthlyZ = (sm_mean - sm_monthly_mean) / sm_monthly_sd.updateMask(sd>0)`, `.updateMask(sampleCount.gt(0))`.
- `support = monthlyZ.mask().gt(0).unmask(0,false)`; `expectedSamples = daysInMonth*samplesPerDay`.
- Bands: `numerator = monthlyZ.unmask(0,false)*support`, `days = support`, `incomplete = (sampleCount < expected)*support`, `excess = (sampleCount > expected)*support`, `sample_count`; `.toDouble()`.
- DATA_END_EXCLUSIVE is not applied here. It is applied in the overlap step through `availableEnd`.

### 6.4 Season window + temporal aggregation (`adminCalendar` L106-129, `buildSeasonBands` L241-266)
- `calendarDate` L98-105: same clamp as temperature (use_Feb28). start, endInclusive, endExclusive, duration, staticDuration and `valid = number(calendar_valid,0).eq(1) && duration>0`, as in temperature.
- `availableEnd = min(endExclusive, DATA_END_EXCLUSIVE)`; `hasTime = valid && availableEnd > start`; `availableDays = hasTime ? availableEnd-start (days, >=0) : 0`;
  `monthCount = (lastIncluded.year - start.year)*12 + (lastIncluded.month - start.month) + 1` (or 0).
- `monthlyCollectionForYear(year)` L226-238: 24 cached months, (year-1, 1..12) and (year, 1..12). Each image has `month_start_millis`, `month_end_millis` (L213-223).
- Per feature, per season: for each month image, `overlapDays = hasTime ? max(0, min(availableEnd, monthEnd) - max(start, monthStart))/DAY_MS : 0` (a **feature-specific number**, since `calendar` comes from the feature). Then `image.select(CACHE_BANDS).multiply(overlapDays)`.
- `sums = (zero image + weighted).sum()`; `supportedDays = sums.days`; `pixelZ = sums.numerator / supportedDays.max(1)`; `validPixelArea = PIXEL_AREA.updateMask(supportedDays>0)`.
  This gives the **pixel-level overlap-day-weighted mean of monthly z**, over months with z support.
- Bands per season `{s}_z_area = pixelZ*validPixelArea`, `{s}_area = validPixelArea`, `{s}_days_area = supportedDays*validPixelArea`, `{s}_incomplete_area`, `{s}_excess_area`.

### 6.5 Item 8 — EE structure (`calculateAdminBundle` L269-318, `buildTable` L372-390)
`admins.iterate(fn, ee.List([]))` over 100 admins (an iterate, not a map). For each feature, s1 and s2 band stacks are built from the 24 cached monthly images, weighted by that feature's own overlap days. Then **one `reduceRegion`** of `cat(s1.bands, s2.bands)` runs over `feature.geometry()` (sum, crs PROJ, scale nominalScale, maxPixels 1e10, tileScale 8).
The bundle holds `_s1_*` and `_s2_*` and is split into 2 rows by `bundleToSeasonRow`. Calendar literal: `'exact_admin_specific_vector_calendar_no_calendar_raster'`.

### 6.6 Post-processing (`summarizeSeason` L277-302)
- `area = number({s}_area,0)`; `safeArea = area>0 ? area : 1`; `value = area>0 ? z_area/safeArea : -9999`; `support = days_area/safeArea`; `incomplete`, `excess` the same way.
- `coverage = valid ? (support/duration.max(1)).clamp(0,1) : -9999`. `duration` is the full gs duration, so coverage < 1 if the cap truncates the window.
- `status = !valid ? 'INVALID_CALENDAR' : (geometryArea<=0 ? 'INVALID_GEOMETRY' : (area<=0 ? 'MISSING_DATA' : (support >= duration-1e-6 && incomplete <= 1e-6 ? 'COMPLETE' : 'PARTIAL_DATA')))`, where `geometryArea = feature.geometry().area(100)`.
- The value is not masked by completeness (`complete_month_required: 0`).

### 6.7 Output columns (`bundleToSeasonRow` L321-361)
Keys: `admin_code, admin_idx, group_id, year, season_year, season`.
Value: `'sm_z_gs_' + C.key` → `sm_z_gs_era5land` | **`sm_z_gs_gldas`**, plus `sm_z_gs`, `metric_name: 'sm_z_gs_'+key`, `metric_value`, `metric_status`, `sm_z_status`.
Diagnostics: `sm_z_supported_overlap_days_area_weighted`, `sm_z_incomplete_month_overlap_days_area_weighted`, `sm_z_excess_sample_count_overlap_days_area_weighted`, `season_coverage_fraction`, `season_cover_pct (valid ? cov*100 : -9999)`, `valid_area_km2`, `admin_geometry_area_km2`, `gs_available_window_days`, `monthly_intervals_used`, `gs_start_date, gs_end_date_inclusive, gs_end_date_exclusive`, `gs_sos, gs_eos, gs_calendar_valid, gs_calendar_quality, gs_cross_year, gs_duration_calendar_days (static), gs_duration_recalculated_days, leap_day_adjustment`.
QA: `qa_support_above_available = support > available+1e-4`, `qa_excess_sample_count = excess > 1e-6`, `qa_geometry_no_area = geomArea_km2 <= 0`, `qa_extreme_sm_z = area>0 && |value|>6`.
Verbatim literals: `source_native_unit`, `variable_family: 'soil_moisture'`, `variable_requested: 'sm_z'`, `baseline_period: '2001_2020'`, `climate_crop_mask_used: 0`, `crop_fraction_multiplied: 0`, `coverage_used_as_filter: 0`, `complete_month_required: 0`,
`spatial_method: 'pixel_metric_then_pixelarea_weighted_admin_mean'`, `temporal_method: 'pixel_monthly_mean_z_then_gs_overlap_day_weighted_mean'`,
`calendar_method: 'exact_admin_specific_vector_calendar_no_calendar_raster'`, `calendar_feb29_nonleap_rule: 'use_Feb28'`,
`missing_month_policy: 'omit_no_support_months_mean_over_supported_overlap'`, `incomplete_month_policy: 'monthly_mean_of_available_samples_no_imputation'`,
`coverage_definition: 'monthly_z_supported_overlap_days_divided_by_full_gs_days'`, `supported_days_are_actual_daily_observation_counts: 0`,
`missing_data_sentinel: -9999`, `requested_data_end_exclusive: '2022-01-01'`, `target_year_is_partial_by_design: 0`, `target_year_data_scope: 'FULL_GROWING_SEASON'`, `stage3_version: VERSION`,
`max_admins_per_task: 100`, `block_assignment: 'all_static_admins_sorted_admin_idx_chunks_100'`, `execution_method: 'one_reduceRegion_per_admin_both_seasons_monthly_cache'`, `execution_driver: 'V2_ALL6227_2015_2021'`, `monthly_cache_version: CACHE_VERSION`.

### 6.8 Not algorithm
L364-369 `taskAdmins`, `tableName` `'STAGE3D_SM_Z_EXACT_ALL6227_'+label+'_Y'+year+'_B'+pad2+'_N'+pad3+'_V2_ONE_REDUCE_GEE'`; L393-417 job lists; L420-481 inventory; L484-525 preflight (source image exists, baseline band names, native grid); L528-549 `alignedGrid`; L555-642 cache validation; L645-671 cache export; L674-768 table conflicts and export; L771-798 driver.

---------------------------------------------------------------------------------

## 7. `S/seasonal/ndvi.js` (1792 lines) — **TABLE-ONLY, per-feature arithmetic**

### 7.1 Settings
- L10 `RUN_INDEX='ndvi'` ('ndvi'|'evi'); L11 `RUN_SENSOR='aqua'` ('terra'|'aqua'). One index × sensor per run, 4 runs in total.
- L32-40 `OUTPUT_YEARS=[2015..2021]`; L44-49 `CURRENT_START_YEAR=2014`, `CURRENT_END_YEAR=2021`; L52 `SEASONS=['s1','s2']`; L58 `MISSING_VALUE=-9999`; L62 `FULL_COVERAGE_TOLERANCE=0.999999`.
- L66-86 sensor labels and `SENSOR_FIRST_DOY {terra:1, aqua:9}`; L120-123 `METRIC_ROOT = RUN_INDEX + '_anom_gs_' + RUN_SENSOR`; L126 `VERSION='V2_EXACT_CALENDAR_2015_2021'`.
- There is no DATA_END constant. The cutoff is implicit: only current tables 2014..2021 are joined.

### 7.2 Private assets / properties
- Baseline `S2E3_VI_BASE_ADMIN_2003_2020_{LABEL}_CMG_P{01..04}_V3` (L656-693). Properties `{index}_base_s{SS}_mean`.
- Current `S2E3_VI_CURRENT_ADMIN_{LABEL}_Y{2014..2021}_CMG_V3` (L722-757). Properties `{index}_{YYYYMMDD}_mean` (YYYYMMDD = nominal interval start, same `observationInterval` as monthly, L273-351).
- Join `saveFirst('_right_match')` on `admin_code`; right properties combined with `combine(..., false)` (L543-649).
- Admin properties read: `admin_code, admin_idx, group_id, admin_area_km2, {s}_cross_year, {s}_sos_month, {s}_sos_day, {s}_eos_month, {s}_eos_day, {s}_duration_days, {s}_calendar_valid, {s}_sos, {s}_eos, {s}_calendar_quality`.

### 7.3 Computation
- `preparedAdmins` (L827-962): for year 2014..2021 and slot 1..23: `valid = cur.valid*base.valid`, `anomaly = cur - base` (nulls → 0).
  Stored as `_vi_anomaly_value_{year}_s{SS}` and `_vi_anomaly_valid_{year}_s{SS}`. `_last_valid_vi_date` = numeric YYYYMMDD tag of the last valid composite.
- `adminCalendar` L969-1128: same as temperature (calendarDate clamp L174-239; valid = calendar_valid==1 && duration>0). It has no data-cap field.
- `makeSeasonRow` L1182-1646: for calendarYear ∈ {seasonYear-1, seasonYear} and slot 1..23:
  `overlap = max(0, min(intervalEnd, cal.endExclusive) - max(intervalStart, cal.start))/86400000` (L1135-1175);
  `validWeight = overlap*valid`; `weightedSum += anomaly*validWeight`; `coveredDays += validWeight`; `contributingComposites += (overlap>0)*valid`.
  `coverageFraction = (coveredDays/max(duration,1)).max(0).min(1)`; `fullCoverage = >= 0.999999`; `usable = valid && fullCoverage`;
  `value = usable ? weightedSum/max(coveredDays,1) : -9999`; `exportedCoverage = valid ? coverageFraction : -9999`.
  `status = !valid ? 'INVALID_CALENDAR' : (coveredDays==0 ? 'MISSING_DATA' : (fullCoverage ? 'COMPLETE' : 'MISSING_DATA'))`. There is no PARTIAL_DATA: a partial season is MISSING_DATA.
- Port hazard: `ee.Number(feature.get(_vi_anomaly_value_{Y-1}_sSS))` has no null guard (L1250-1277). seasonYear-1 must be inside the prepared year range, or EE errors.

### 7.4 Item 8 — EE structure
`OUTPUT_YEARS.forEach(year -> SEASONS.forEach(season -> outputRows.merge(preparedAdmins.map(f -> makeSeasonRow(f, year, season)))))` (L1653-1684). This is a server-side `FeatureCollection.map` with purely numeric property arithmetic: no images and no reduceRegion. It is one export of 87,178 rows (6227 × 7 × 2).

### 7.5 Output columns (L1413-1644)
Keys: `admin_code, admin_idx, group_id, admin_area_km2, year, season_year, season`.
Value: `{index}_anom_gs_{sensor}` (e.g. `ndvi_anom_gs_aqua`), `{root}_season_coverage_fraction`, `{root}_season_cover_pct`, `{root}_status`.
Other: `source: RUN_SENSOR`, `source_label`, `variable_family: RUN_INDEX + '_anomaly'`, `baseline_period: '2003_2020'`, gs calendar fields (as temperature, plus `aggregation_end_date_exclusive`), `source_last_complete_composite_date`, `vi_contributing_composites`, `vi_supported_overlap_days`, `season_coverage_fraction`, `season_cover_pct`, `source_row_status`.
Verbatim literals: `target_year_is_partial_by_design: 0`, `target_year_data_scope: 'FULL_GROWING_SEASON'`, `missing_data_sentinel: -9999`,
`incomplete_season_value_rule: 'HISTORICAL_FULL_16DAY_SUPPORT_REQUIRED'`, `climate_crop_mask_used: 0`, `crop_fraction_role: 'static_feature_only'`,
`calendar_method: 'exact_admin_specific_vector_calendar'`, `calendar_feb29_nonleap_rule: 'use_Feb28'`, `season_year_definition: 'EOS_HARVEST_YEAR'`,
`input_level: 'admin_16day_mean_from_S2E3_V3_CMG_tables'`, `spatial_product: 'CMG_0P05_DEG'`, `vi_qa_rule: 'SummaryQA_0_OR_1_AND_Pixel_1km_GT_0'`,
`gs_temporal_method: '16day_anomaly_exact_overlap_day_weighted_mean'`, `baseline_method: 'sensor_specific_same_composite_slot_mean_2003_2020'`, `stage3_version: VERSION`.

### 7.6 Not algorithm
L1691-1731 preflight prints; L1738-1763 export `'STAGE3E_' + RUN_INDEX.toUpperCase() + '_ANOM_EXACT_ADMIN_' + LABEL + '_Y2015_2021_V2'`.

---------------------------------------------------------------------------------

## 8. Python locators (no math paraphrase)

### 8.1 `S/monthly/spi_monthly.py` (3244 lines, Colab)
Module constants (CELL 2, L60-194): `GCP_PROJECT="han-sandbox-505315"` (L48), `ASSET_ROOT` (L67), `ADMIN_ID="admin_code"` (L69), `STATIC_PREFIX` (L71-74), `EXPECTED_ADMINS=6227` (L76), `YEAR_CHUNKS=[(1990,1995),(1996,2001),(2002,2007),(2008,2013),(2014,2019),(2020,2026)]` (L84-91), `SOURCES={"chirps":"CHIRPS","persiann":"PERSIANN","era5land":"ERA5LAND"}` (L94-98), `BASELINE_START_YEAR=1991`, `BASELINE_END_YEAR=2020` (L103-104), `ALL_MONTHS=pd.date_range("1990-01-01","2026-08-01",freq="MS")` (L110-114), `TARGET_MONTHS=pd.date_range("2015-01-01","2026-08-01",freq="MS")` (L119-123), `EXPECTED_TARGET_MONTHS=140` (L126), `EXPECTED_FINAL_ROWS` (L131), `EE_PAGE_SIZE=500`, `MAX_DOWNLOAD_ATTEMPTS=4` (L143-144), `CACHE_DIR`, `OUTPUT_DIR`, `SAVE_CSV` (L149-173).

(a) GEE admin-table download:
- `clean_downloaded_frame` L201-229; `download_asset_dataframe(asset_id, cache_name, properties)` L230-378 (paged `ee.FeatureCollection(...).select(...)`); `validate_unique_admin` L379-408.
- CELL 4 L409-516 (module level): static admins `STATIC_PREFIX + f"{g:02d}"`, g 0..24, all properties; sorted by `admin_idx`; `admin_ids`.
- CELL 5 L517-673: `precipitation_asset(label,a,b)` L522-536 → `S2C3_DROUGHT_ADMIN_PRCP_{LABEL}_Y{a}_{b}_V3`; `et0_asset(a,b)` L537-549 → `S2C3_DROUGHT_ADMIN_ET0_FAO56_Y{a}_{b}_V3`; `et0_patch_asset(a,b)` L550-562 → `S2C3_ET0_PATCH32_Y{a}_{b}_V2`; `months_in_chunk` L563-598; `month_property_names(prefix,a,b)` L599-621 → `[admin_code] + f"{prefix}_{YYYY}{MM}_mean"` (prefix `prcp` / `et0`); `normalize_monthly_table` L622-673 (absent → NaN).
- CELL 6 `load_precipitation_wide(source_key)` L683-793 (outer-merge chunks on admin_code).
- CELL 7 L797-1122 (module level): original ET0 L804-903, PATCH32 download L904-993, patch applied L994-1122 (fill-only, `assert overwrite_count == 0`; `ET0_MONTH_COLUMNS` L1010).
(b) Pure numpy/scipy path:
- `wide_to_matrix(wide, prefix)` L1128-1218 (CELL 8); `rolling_three_month_sum(values)` L1224-1274 (CELL 9); `normal_from_probability(probability)` L1275-1297 (clip 1e-6);
  `compute_spi03_monthly(prcp_matrix)` L1304-1556 (CELL 10, zero-corrected gamma, `scipy.special.gammainc`, strict 1991-2020 baseline);
  `compute_spei03_monthly(prcp_matrix, et0_matrix)` L1563-1872 (CELL 11, UB-PWM GLO, inner `pwm(power)`, `special.gamma`).
  Constants used: `ALL_MONTHS, TARGET_MONTHS, BASELINE_START_YEAR, BASELINE_END_YEAR, EXPECTED_ADMINS, ADMIN_ID`.
- Panel build CELL 12 L1873-2077 (`month_lookup`, `target_positions`, `BASE_COLUMNS` L1904); per-source driver CELL 13 L2078-2259 → columns `spi03_month_{source}` (L2182), `spei03_month_{source}` (L2189).
(c) Ensembles: `add_dynamic_ensemble(df, family)` L2266-2413 (CELL 14; equal-weight mean of available sources; population SD when ≥2) → `{family}_month_ensmean`, `{family}_month_n_sources` (L2392/2405), SD column.
Method metadata CELL 15 L2414-2473: `spi03_method="GAMMA_ZERO_CORRECTED"`, `spei03_method="SPEI_UBPWM_GLO_STRICT_SUPPORT_V3"`, `index_window_method="CURRENT_MONTH_PLUS_PREVIOUS_2_CALENDAR_MONTHS"`, `et0_method="FAO56_PENMAN_MONTEITH_DAILY_THEN_MONTHLY_SUM"`, `calendar_method="COMMON_CALENDAR_MONTH"`, `historical_coverage_rule="FULL_MONTHLY_INDEX_SUPPORT_NOT_DAILY_COMPLETENESS"`, `missing_data_policy="SOURCE_SPECIFIC_MISSINGNESS_NO_IMPUTATION"`, `baseline_policy="STRICT_1991_2020_NO_29_YEAR_FALLBACK"`, `et0_patch32_used=1`.
(d) There is no seasonal aggregation in this file. QA/selection/save: CELL 16-18 L2474-3244 (`KEY` L2479, `VALUE_COLUMNS` L2625, `FINAL_COLUMNS` L2844, output paths L2987-3029).
Note: SPI/SPEI run on **admin-level monthly totals** (precomputed S2C3 tables), not on pixels.

### 8.2 `S/seasonal/spi&spei.py` (11314 lines, Colab)
Module constants (CELL 1 §3-4, L174-400): `GCP_PROJECT` (L147), `ROOT` (L177), `ADMIN_ID` (L184), `STATIC_PREFIX` (L189), `SOURCES` (L196), `YEAR_CHUNKS` (L211, same 6 chunks), `OUTPUT_YEARS=list(range(2015,2022))` (L246), `SEASONS=['s1','s2']` (L254), `BASELINE_START_YEAR=1991` (L261), `BASELINE_END_YEAR=2020` (L265), `N_ADMINS=6227` (L270), `EXPECTED_ROWS=87178` (L275), `MISSING_SENTINEL=-9999.0` (L296), `EE_PAGE_SIZE=500` (L301), `MAX_DOWNLOAD_ATTEMPTS=4` (L306), `FORCE_REDOWNLOAD=False` (L312), `FORCE_RECOMPUTE_INDICES=False` (L318), `ENS_SD_DDOF=0` (L323), `NORMAL_PROB_EPS=1e-6` (L328), `FULL_COVERAGE_TOLERANCE=0.999999` (L333), `SPEI_METHOD='SPEI_UBPWM_GLO_STRICT_SUPPORT_V3'` (L338), `ALL_MONTHS='1990-01-01'..'2021-12-01'` (L350, 384 months), `INDEX_MONTHS='2014-01-01'..'2021-12-01'` (L370, 96 months), `RAW_START`, `RAW_END` (L387-391), Drive/cache dirs L465-477.
CELL 2 constants: `INDEX_GLOBAL_POSITIONS` L3487-3505; reason codes L3507-3511 `REASON_VALID=0, REASON_INPUT_MISSING=1, REASON_FIT_INVALID=2, REASON_OUTSIDE_SUPPORT=3, REASON_NUMERICAL=4`.

(a) GEE admin-table download (CELL 1 L11-3409):
- `clean_frame` L514-567; `validate_admins` L568-645; `download_asset` L646-865; `month_properties` L866-948; `expected_month_columns` L949-991; `prcp_asset` L992-1020; `et0_asset` L1021-1044; `et0_patch_asset` L1045-1075 (same asset patterns as monthly); `add_absent_columns_as_nan` L1076-1164.
- Static admins load §12 L1165-1365 (25 groups, all properties; requires `admin_idx`, `group_id`; the calendar columns `{s}_calendar_valid, _cross_year, _sos_month, _sos_day, _eos_month, _eos_day, _duration_days, _sos, _eos, _calendar_quality` are used later).
- `load_prcp_wide` L1371-1508; `load_et0_wide` L1509-1633; `load_et0_patch_wide` L1634-1750; `normalize_monthly_frame` L1754-1898; module-level reads/patch/QA §17-31 L1899-3409 (PATCH32 application §22 L2250-2301, no-overwrite check §23 L2302-2412).
(b) Pure numpy/scipy (CELL 2 L3410-4865):
- `rolling_three_month_sum(values)` L3421-3464; `normal_from_probability(probability)` L3465-3485;
  `compute_spi03(prcp_matrix, source)` L3518-3845 (zero-corrected gamma, calls L3524/L3746);
  `fit_glo_ubpwm(baseline)` L3849-4172; `glo_probability_strict(values, xi, alpha, k)` L4173-4364;
  `compute_spei03(prcp_matrix, et0_matrix, source)` L4365-4661 (calls fit L4438, strict probability L4474, normal L4503).
  Uses `ALL_MONTHS, INDEX_MONTHS, INDEX_GLOBAL_POSITIONS, BASELINE_START_YEAR, BASELINE_END_YEAR, N_ADMINS, NORMAL_PROB_EPS, REASON_*`.
- Driver "CALCULATE / CACHE ALL 3 SOURCES" L4662-4865 (`monthly_indices`, `fit_diagnostics`, cache tag `UBPWM_STRICT_V4`, `FORCE_RECOMPUTE_INDICES`; calls L4758/L4768).
(d) Seasonal aggregation (CELL 3 L4866-5948):
- `truthy` L4874-4897; `int_or_none` L4898-4914; `exact_date(year, month, day)` L4915-4958 (only Feb 29 → Feb 28 in a non-leap year; any other out-of-range day → None → invalid calendar. This differs from the EE clamp-to-month-end).
- "BUILD EXACT SEASON PLAN" L4962-5364 (module level): per admin × OUTPUT_YEARS × SEASONS → `_month_positions`, `_overlap_days` (calendar-month overlaps; `assert sum == duration`), `season_plan` DataFrame L5341 (87,178 rows).
- `aggregate_gs(monthly, monthly_reason, metric_name)` L5369-5746 (overlap-day-weighted; full coverage ≥ `FULL_COVERAGE_TOLERANCE` required; status literals include `COMPLETE`, `INVALID_CALENDAR`, `MISSING_DATA`, `NO_VALID_INDEX_MONTH`, `INPUT_MONTH_MISSING`, `BASELINE_FIT_INVALID`, `SPEI_OUTSIDE_FITTED_SUPPORT`, `PARTIAL_MONTHLY_INDEX_SUPPORT` — the last two are written as adjacent Python string literals in the source). Per-source driver L5673-5745 (calls L5692 spi, L5710 spei) → `{family}_gs_{source}`.
(c) Ensembles: `add_ensemble(frame, family)` L5750-5865 → `{family}_gs_ensmean` (L5834), `{family}_gs_n_sources` (L5838), `{family}_gs_ens_sd` (L5844, ddof `ENS_SD_DDOF`), `{family}_gs_status` (L5848; ensemble status literals `MISSING_ALL_SOURCES`, `ONE_SOURCE`, `TWO_SOURCES`, `THREE_SOURCES`); calls L5866 (spi03), L5871 (spei03). Metadata literals in the same block (`GAMMA_ZERO_CORRECTED`, `EXACT_ADMIN_VECTOR_CALENDAR`, `MONTHLY_INDEX_EXACT_OVERLAP_DAY_WEIGHTED_MEAN`, `FULL_MONTHLY_INDEX_SUPPORT_NOT_DAILY_COMPLETENESS`, `USE_FEB28`, ...).
- CELL 4 L5949-7040: validation only (ensemble arithmetic re-check L6046-6678, `KEYS` L5954, final core columns L6679+, save).
- Optional/out-of-band (not core algorithm): REPAIR A L7041-7895 and REPAIR B L7896-9035 (PERSIANN 1992-02 from asset `S2C3_DROUGHT_ADMIN_PRCP_PERSIANN_Y1992_M02_REPAIR_V1`; sets `FORCE_RECOMPUTE_INDICES=True` L7882/L8942); QA A L9036-10349; QA B L10350-11314.
