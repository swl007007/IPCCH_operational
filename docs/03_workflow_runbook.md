# Workflow Runbook

Every workflow section lists the step order, config sections, expected inputs, and expected outputs. Replace local operator settings in `config/paths.ini` and `config/ee_gcs.ini` before running.

This runbook uses post-refactor/proposed paths and should be used after the rename, conversion, and config tasks have landed.

## EVI

1. Run Earth Engine Code Editor script: `EVI/00_ee_export_evi.txt`.
2. Download exports with: `EVI/01_gcs_download_evi.txt`.
3. Run ArcPy extraction on Windows: `EVI/02_arcpy_extract_evi.py`.
4. Default template path alignment: downloads land under `EVI/MODIS_MOD13A3_Monthly`, and extraction writes under `EVI/output_ch`.
5. Expected outputs: `EVI_mean_extraction_results.csv` and `EVI_std_extraction_results.csv`.
6. Output shape: wide monthly table keyed by `region_id`.

## FLDAS

1. Run Earth Engine Code Editor script: `FLDAS/00_ee_export_fldas_all_bands.txt`.
2. Download exports with: `FLDAS/01_gcs_download_fldas.txt`.
3. Split or copy downloaded `FLDAS_*_all_bands.tif` files from `FEWSNET_predictors/FLDAS_Monthly` into the configured `Part1` through `Part4` folders.
4. Run the four ArcPy part scripts separately: `02_arcpy_extract_fldas_part1.py` through `02_arcpy_extract_fldas_part4.py`.
5. Expected outputs: part-specific wide monthly-band mean and standard deviation CSVs under `FEWSNET_predictors/output_ch`.
6. FLDAS remains split because local ArcPy processing cannot reliably handle all months in one run.

## GOSIF-GPP

1. Run `GOSIF_GPP/00_download_gosif_gpp_mean.py`.
2. Run `GOSIF_GPP/00_download_gosif_gpp_sd.py`.
3. Run `GOSIF_GPP/01_unzip_gosif_gpp_mean.py`.
4. Run `GOSIF_GPP/01_unzip_gosif_gpp_sd.py`.
5. Run `GOSIF_GPP/02_arcpy_extract_gosif_gpp_mean.py`.
6. Run `GOSIF_GPP/02_arcpy_extract_gosif_gpp_sd.py`.
7. Default template path alignment: unzip writes `.tif` files back into the download folders, those folders are the extraction input folders, and extraction writes final harmonise inputs under `GOSIF_GPP/output_ch`.

## VIIRS Nightlight

1. Set the target feature month in `VIIRS_nightlight/00_ee_export_viirs_nightlight.txt`. For 2026-04, use `startDate = '2026-04-01'` and exclusive `endDate = '2026-05-01'`.
2. Run Earth Engine Code Editor script: `VIIRS_nightlight/00_ee_export_viirs_nightlight.txt`.
3. Download exports with: `VIIRS_nightlight/01_gcs_download_viirs_nightlight.txt`.
4. Run `VIIRS_nightlight/02_arcpy_mosaic_viirs_nightlight.py`.
5. Run `VIIRS_nightlight/03_arcpy_extract_viirs_nightlight.py`.
6. Default template path alignment: downloads land under `DMSP_OLS/image/nightlight`, mosaics are written under `DMSP_OLS/image/nightlight_mosaic`, and extraction writes under `DMSP_OLS/output_ch`. `DMSP_OLS` is a legacy folder name; the production source is VIIRS.

## Tabular Feature Workflows

Run the converted scripts after checking raw input filenames in `config/paths.ini`.
For production, `scaffold_input` should point to one target-month scaffold, not
the multi-month reference scaffold.

Build the current example scaffold with:

```bash
python3 tools/build_monthly_ipcch_scaffold.py --year 2026 --month 4
```

- `ACLED/00_add_acled_features.py`
- `FAO_price/00_add_fao_price_features.py`
- `WB_indicator/00_add_world_bank_features.py`
- `WFP_indicator/00_add_wfp_price_features.py`

Each output should preserve scaffold rows unless the source workflow documents a deliberate filter.

Archived notebook references for converted tabular and final harmonise workflows
are listed in `archive/notebooks/MANIFEST.md`.

## IPC API

Create `config/paths.ini` from `config/paths_template.ini`, confirm its `[ipc_api]`
settings, and set `IPCINFO_API_KEY` before running:

```bash
IPCINFO_API_KEY='<operator-key>' python3 curl_IPC/00_download_ipc_api.py
```

Expected outputs are per-year files and combined areas/analyses files under `curl_IPC/outputs/`.

## Final Monthly IPCCH Assembly

Production uses one unified IPCCH monthly assembly path. It does not produce
separate CH and IPC model inputs.

For the current handover month:

```bash
python3 Final_harmonise/00_build_monthly_ipcch_base_input.py --year 2026 --month 4
python3 tools/validate_ipcch_schema.py --mode model-input-forecast --csv Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604.csv
```

Expected outputs:

- `Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604.csv`
- `Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604_summary.json`

The output is a long monthly table keyed by `area_id`, `year`, and `month`.
It starts from the one-month scaffold, joins fixed/slow area features, and
joins same-month source-level fields from the unified historical panel when
the target month exists there.

Legacy split CH/IPC final harmonise scripts are archived under
`archive/legacy_final_harmonise/`. They are compatibility references, not the
production monthly IPCCH input path.

## Smoke Tests

Run these before a full monthly update. For tabular and final harmonise smoke
tests, stage fixtures under the exact filenames and relative locations currently
read by each converted script; some scripts still expect auxiliary reference
files under `source_data_root`.

| Workflow | Small input | Expected check |
| --- | --- | --- |
| EVI | One MOD13A3 raster month | Mean/std CSVs exist and include `region_id` plus one month column. |
| FLDAS | One part folder with a small month subset | Part-specific mean/std CSVs exist and include `region_id` plus band columns. |
| GOSIF-GPP | One mean file and one SD file | Wide CSVs exist and include `region_id` plus source month column. |
| VIIRS | One month of exported tiles | Mosaic exists, then sum/std CSVs exist. |
| ACLED | Small scaffold and raw ACLED sample staged at the expected configured paths | Output row count matches scaffold unless documented otherwise. |
| FAO | Small scaffold and FAO workbook sample staged with required auxiliary references | Output contains appended FAO feature columns. |
| World Bank | Small scaffold and WBG indicator sample staged with required country/year references | Output contains expected country-year features. |
| WFP | Small scaffold and WFP price sample staged at the expected configured paths | Output contains appended WFP feature columns. |
| IPC API | One year | Per-year areas/analyses files and combined files are written. |
| Final monthly IPCCH assembly | One-month scaffold plus fixed/slow fixture and a small historical-panel slice | Unified monthly base input has one row per `area_id`, `year`, `month`; summary JSON reports join coverage and missingness. |
