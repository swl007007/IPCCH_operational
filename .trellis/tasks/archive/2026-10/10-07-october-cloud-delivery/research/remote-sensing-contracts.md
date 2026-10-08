# Remote-sensing source and reduction evidence

Read-only source inspection on 2026-10-07 at `4a42f1f666a4f2d5d2616069fe25ddd81f2662cb`. No provider availability query, raster processing, or cloud run. These are existing extraction semantics; full lineage to each saved model feature still requires verification.

| Family | Existing source/time selection | Grid and reduction | Evidence |
|---|---|---|---|
| EVI legacy | GEE `MODIS/061/MOD13A3`, band `EVI`, monthly image timestamp | Export scale 1000, region [-180,-60,180,80]; no explicit CRS/transform; ArcPy DATA/ALL, MEAN and STD; stored raw values | `EVI/00_ee_export_evi.txt:2-40`; `EVI/02_arcpy_extract_evi.py:79-95` |
| EVI cloud | Same collection/band; calendar-month filter, `.first()` | Default scale 1000, optional CRS/region; Rasterio polygon mask, mean and population SD; no physical scaling | `cloud/batch/evi_service.py:69-114,163-181`; `cloud/batch/gee_export.py:37-43` |
| FLDAS | GEE `NASA/FLDAS/NOAH01/C/GL/M/V001`, all bands, monthly timestamps | EPSG:4326, transform [0.1,0,-180,0,-0.1,90]; bandwise ArcPy DATA/MEAN and DATA/STD, no explicit unit conversion | `FLDAS/00_ee_export_fldas_all_bands.txt:2-43`; `FLDAS/02_arcpy_extract_fldas_part1.py:53-84` (parts 2–4 use the same reducers) |
| GOSIF-GPP Mean | Provider `data.globalecology.unh.edu/data/GOSIF-GPP_v2/Monthly/Mean/GOSIF_GPP_{year}.M{month:02d}_Mean.tif.gz` | Original TIFF, ArcPy DATA/MEAN; no explicit scaling/resampling | `GOSIF_GPP/00_download_gosif_gpp_mean.py:36-49`; `GOSIF_GPP/02_arcpy_extract_gosif_gpp_mean.py:57-83` |
| GOSIF-GPP SD | Same provider under `Monthly/SD/`, suffix `_SD.tif.gz` | **Regional MEAN of the provider's SD raster**, not regional SD of the Mean raster | `GOSIF_GPP/00_download_gosif_gpp_sd.py:36-49`; `GOSIF_GPP/02_arcpy_extract_gosif_gpp_sd.py:57-83,112` |
| VIIRS nightlight | GEE `NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG`, band `avg_rad` | Bilinear reproject EPSG:4326, transform [0.0041666667*8,0,-180.00208525335,0,-0.0041666667*8,75.00208393335001]; mosaic float32/BLEND; **regional SUM and STD** | `VIIRS_nightlight/00_ee_export_viirs_nightlight.txt:1-53`; `VIIRS_nightlight/02_arcpy_mosaic_viirs_nightlight.py:72-81`; `VIIRS_nightlight/03_arcpy_extract_viirs_nightlight.py:66-92` |

## Geometry and missing values

- Legacy scripts use configured `paths.polygon_input`; example `config/paths_template.ini:4,37-66` points to IPCCH geometry. EVI zones use `admin_code`; other source extractors use `fid`. This does not establish FEWS polygon lineage.
- Cloud EVI uses `area_id` with `admin_code` fallback, rejects missing/duplicate keys, and requires geometry/scaffold ID equality (`cloud/batch/evi_service.py:150-156,304-354`).
- Cloud mask is `crop=True, all_touched=False, filled=False`; masked values and NaN are excluded. No overlap/no valid values yields an explicit row with null statistics (`:163-181,255-275`). Source CRS is transformed only when both CRS values exist and differ (`:357-366`).
- Legacy ArcPy scripts collect the rows emitted by zonal statistics and do not explicitly build a complete roster. ArcPy environment defaults and boundary-cell treatment have not been proven equal to Rasterio.

## Freshness and parity limitations

Existing download/export examples use fixed historical windows. No inspected path determines latest available complete months or distinguishes partial-month products from refresh failure. GOSIF non-200 responses only print failure (`00_download_gosif_gpp_mean.py:19-26`, same SD logic); a new preparation report cannot treat arbitrary download failure as normal publication delay.

The EVI cloud `.first()` call does not check image count/completeness. Existing reference validation defaults to EVI mean only; absent references return `not_provided`, differences are advisory, and validation may still pass with warnings (`cloud/batch/evi_reference.py:9-16,43-48`; `cloud/batch/evi_validation.py:50-62`). This is insufficient for migration parity, especially SD.

Provider units, fill sentinels, physical scaling factors, GOSIF source CRS/resolution and SD interpretation are not fully documented in the inspected code. Verify raster metadata/provider documentation and trace extraction-to-panel-to-contract transformations before freezing adapters. Preserve training-scale values; do not apply a seemingly corrective scale conversion based only on a column label.

Known feature-contract needs: IPCCH 128 features, including 28 FLDAS bands × mean/stdDev; FEWS Stage3 123 features including EVI lags 1–12, prior-12-month nightlight sum, WFP lagged 4/12-month sums, climate zscores, and historical target lags. These temporal operations are separate from spatial reducers.
