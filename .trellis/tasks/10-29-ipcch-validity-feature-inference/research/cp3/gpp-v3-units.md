# Research: GOSIF-GPP v3 `GPP_mean`: delivered history vs operational contract (units, fills, zonal rule)

- **Query**: How was the delivered IPCCH `GPP_mean` history (task 10-27 GOSIF v3 correction) produced, and would a month appended through the operational contract have the same scale and nodata semantics?
- **Scope**: internal (two repos). R = `/home/swl007007/projects/food-crisis-research`, O = this repo
- **Date**: 2026-10-30

## 1. Research production (located: R/staging/ipcch-gosif-v3-20261027/tools/)
- **Source**: `https://data.globalecology.unh.edu/data/GOSIF-GPP_v3/Monthly/{Mean,SD}/GOSIF_GPP_{YYYY}.M{MM}_{Mean,SD}.tif.gz`, 2010-01..2025-12, 192 months x 2 = 384 files. Each file is SHA-checked against the manifest (R/.trellis/tasks/10-27-ipcch-gosif2025-retrain/research/source-and-rerun-preparation.md:5; research/preparation/raw-download-manifest.json:10,23; extract_gpp_v3.py:75-81,110).
- **Raster encoding**: uint16, EPSG:4326, 3600x7200, 0.05 deg, `nodata=None`, scale 1, no tags. The script asserts this grid (extract_gpp_v3.py:83-85; local-data-and-region-evidence.md:56). Provider Readme: monthly scale 0.01, fills 65535 (water) and 65534 (permanent snow/ice), units g C m-2 mo-1 (source-and-rerun-preparation.md:11-17,23).
- **Scale and fills**: `GPP_mean = sum(x for valid cells) / n_valid * 0.01`, where valid means x not in {65534, 65535}. True zeros are kept. `n_valid == 0` gives NaN, with no fallback (extract_gpp_v3.py:5-8,31-32,123-133; design.md:9; prd.md:14 R4).
- **Zonal rule**: unweighted mean of cells whose centre falls in the polygon. No area weighting and no all_touched. Memberships come from ArcGIS Desktop 10.8 `PolygonToRaster_conversion(..., "CELL_CENTER", ...)`, run on one polygon at a time over the full source grid (snap = source TIF), so overlaps stay independent (arcpy_memberships.py:4-10,69,110; design.md:11). This was sample-checked against single-polygon ArcPy ZonalStatisticsAsTable (tools/arcpy_zonal_check.py, check/comparison-summary.json).
- **Geometry**: `C:/Users/swl00/gosif_staging/geometry/ipcch_polygons.shp`, GCS_WGS_1984. It has 6,227 ids: 6,188 current plus 39 historical (research/preparation/geometry-inventory.json). 136 polygons are always NaN, mostly polygons with zero member cells (extracted/extraction-summary.json).
- **Into history**: `merge_gpp_interim.py:1-7,115` copies the extraction values into the interim panel unchanged (repr; NaN written as blank). The handoff then reads the interim as-is (`method_id = delivered:interim@<sha12>`, R/control-plane-h2h8h14-pkg/research_cloud/packages/ipcch_handoff_inputs.py:301-306).

## 2. Delivered history: R/scratch/h2h8h14-final/handoff-build/out-r5/history/GPP_mean.csv (computed 2026-10-30)
- 1,168,776 rows, 6,090 admin_codes, months 2010-01..2025-12 (192). The file has no NaN rows (blanks are absent). One method_id: `delivered:interim@b2d5d2ce6bd6`. There are no 2026 rows.
- Value statistics: min 0.0 (601 exact zeros), p1 1.26, **median 81.7**, p99 296.4, **max 403.29**, mean 109.2. Yearly medians run 74-90 and yearly maxima 375-403.
- Every row joins to R/staging/.../extracted/gosif_gpp_v3_monthly.csv. Max abs difference 5.7e-14; 97.8% of rows are bit-equal. Example: admin 1 gives 104.61 (2010-01), 66.18 (2010-07), 76.78 (2025-12) in both files.
- **Implied unit**: physical g C m-2 month-1 (raw x 0.01), not raw scaled integers.

## 3. Operational contract (O)
- `SOURCE_CONTRACTS["gosif_mean"]`: the URL is `GOSIF_V3_BASE_URL + "/Mean/GOSIF_GPP_{year}.M{month:02d}_Mean.tif.gz"`, starting 2025-01. This is the same product and file pattern as the research run (cloud_pipeline/cloud/batch/remote_sources.py:52,103-109).
- Acquisition: download, `gzip.decompress`, then write the raw TIF bytes unchanged. No nodata tag is set and no rescale is done (cloud_pipeline/cloud/orchestrator/prepare.py:611-631, decompress at 623, write at 629).
- Zonal step: `rasterio.mask.mask(..., crop=True, all_touched=False, filled=False)` per polygon, then `np.ma.compressed` with a finite-only filter, then an unweighted `values.mean()` (remote_sources.py:269-305, mask at 294; 386-397).
- The docstring states "No unit scaling is applied" (remote_sources.py:14-17). Mapping `GPP_mean <- GPP_Mean__mean` is identity (remote_sources.py:64). No `GPP_Mean__mean` scaling exists anywhere else in cloud_pipeline/ or research_cloud/ (grep, non-test code).
- Masking depends on the dataset nodata. The v3 TIF has `nodata=None`, so `filled=False` masks only cells outside the geometry. **65534/65535 cells are therefore averaged in as valid values.**
- Legacy script `GOSIF_GPP/02_arcpy_extract_gosif_gpp_mean.py` was deleted from HEAD in commit 4c9122d. In `git show 4c9122d^:...`, line 67 is `ZonalStatisticsAsTable(shapefile, id_field, tif_file, tmp, "DATA", "MEAN")`. It has no SetNull, fill mask or x0.01. "DATA" ignores only NoData, and with `nodata=None` the fill codes count as data. Zone field defaults to `fid` (line 41).
- Operational bootstrap asset O/cloud_pipeline/bootstrap/assets/ipcch/history/gosif_mean.csv (`GPP_Mean__mean`, v2, values only in 2024-01..2024-12, 3,038 areas) is on the raw-integer scale: median 10,440, max 35,496. Against the delivered v3 history on 17,659 shared keys, the median ratio is 100.7 (p5 0, p95 200, max 149,105). This is consistent with x100 plus a v2/v3 and geometry difference; it is not an exact match.

## 4. Answer: same scale and nodata semantics? **No**, on two counts. The zonal rule matches.
| Aspect | Delivered history (research) | Operational new month | Same? |
|---|---|---|---|
| Product / URL | v3 Monthly Mean .tif.gz | v3 Monthly Mean .tif.gz (remote_sources.py:108) | yes |
| Scale | x0.01 -> g C m-2 mo-1, ~0-403 | none, raw uint16 -> expected ~0-40,000 (remote_sources.py:16, prepare.py:623-629) | **no (100x)** |
| Fill 65534/65535 | masked before mean (extract_gpp_v3.py:123-125) | not masked, raster nodata=None (remote_sources.py:294,386-390) | **no** |
| Inclusion | cell centre, per polygon, unweighted | all_touched=False, per polygon, unweighted | yes in rule |
| Empty zone | NaN | NaN (remote_sources.py:394-395) | yes |
| Geometry | ipcch_polygons.shp, 6,227 ids, WGS84 | roster GeoJSON keyed by admin_code, EPSG:4326 (remote_sources.py:251-266) | not verified identical |

## Caveats / not found
- I did not run the operational extraction on a v3 raster. The ~0-40,000 range is inferred from the code path and the v2 bootstrap asset, not observed for v3.
- Cell-centre parity between rasterio and ArcGIS PolygonToRaster on boundary-exact centres or invalid geometries is unverified. The research run found that geometry flagged by CheckGeometry was sensitive to the processing extent (arcpy_memberships.py:7-9).
- Whether the operational roster geometry equals ipcch_polygons.shp was not checked. The 6,090 delivered areas versus the 6,188 roster is also not reconciled here.
- Polygons that mix fill and valid cells are where the fill-mask difference changes values the most (water bodies, coasts, snow/ice). Their count per month is in R/staging/.../extracted/raster_support.csv and was not re-tabulated here.
