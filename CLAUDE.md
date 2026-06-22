# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository purpose

This repository contains monthly operational data-preparation workflows for IPCCH food-crisis modelling. Its final operational output is a monthly model-compatible input table. Prediction is downstream: Weilun will export the trained model weights and model pipeline separately, and those artifacts will be combined with the monthly compatible input to produce predictions.

The code is organized as source-specific scripts and notebooks that download, extract, aggregate, and harmonize raster and tabular indicators into the monthly IPCCH input surface.

A design note at `docs/superpowers/specs/2026-06-22-ipcch-handover-design.md` describes the intended handover/refactor direction: keep source-specific workflow folders, make step ordering explicit, externalize paths/configuration, and preserve the current output contracts consumed by the final harmonisation notebooks.

## Environment and dependencies

There is no project-level dependency manifest, build system, lint config, or test suite in this repository. Dependencies are script/notebook-specific:

- ArcGIS Pro Python with Spatial Analyst (`arcpy`, `arcpy.sa`) is required for raster extraction and mosaicking scripts under `EVI/`, `FLDAS/`, `GOSIF_GPP/02_*`, and `VIIRS_nightlight/02_*`/`03_*`. These scripts should normally be run on Windows with the ArcGIS Pro Python environment, not WSL.
- General Python scripts/notebooks use packages including `pandas`, `numpy`, `tqdm`, `requests`, `geopandas`, `rasterio`, `polars`, `pycountry`, and Excel support such as `openpyxl`.
- Earth Engine export snippets are stored as `.txt` JavaScript files and are intended for the Earth Engine Code Editor.
- Google Cloud downloads use `gcloud auth login` and `gsutil -m cp` commands recorded in the `01_gcs_download_*.txt` files.

## Common commands

### Syntax-check Python scripts

This is the closest repository-wide verification available and does not require ArcPy to be importable because imports are not executed:

```bash
python3 -m py_compile \
  workflow_config.py \
  tools/validate_csv_contract.py \
  tools/validate_ipcch_schema.py \
  tools/build_ipcch_schema_contract.py \
  tools/build_monthly_ipcch_scaffold.py \
  curl_IPC/00_download_ipc_api.py \
  EVI/02_arcpy_extract_evi.py \
  FLDAS/02_arcpy_extract_fldas_part1.py \
  FLDAS/02_arcpy_extract_fldas_part2.py \
  FLDAS/02_arcpy_extract_fldas_part3.py \
  FLDAS/02_arcpy_extract_fldas_part4.py \
  GOSIF_GPP/*.py \
  VIIRS_nightlight/*.py \
  ACLED/00_add_acled_features.py \
  FAO_price/00_add_fao_price_features.py \
  WB_indicator/00_add_world_bank_features.py \
  WFP_indicator/00_add_wfp_price_features.py \
  Final_harmonise/00_combine_all_ch.py \
  Final_harmonise/00_combine_all_IPC.py \
  Final_harmonise/01_CH_final_process.py \
  Final_harmonise/01_IPC_final_process.py
```

Check a single script:

```bash
python3 -m py_compile path/to/script.py
```

### Run IPC API download

`curl_IPC/00_download_ipc_api.py` downloads IPC `areas` and `analyses` year-by-year using the configured year range and writes per-year plus combined outputs to `curl_IPC/outputs/`.

```bash
IPCINFO_API_KEY='<operator-key>' python3 curl_IPC/00_download_ipc_api.py
```

### Run direct GOSIF-GPP downloads

```bash
python3 GOSIF_GPP/00_download_gosif_gpp_mean.py
python3 GOSIF_GPP/00_download_gosif_gpp_sd.py
```

The download scripts write into folders configured in `config/paths.ini`.

### Run ArcPy extraction or mosaicking scripts

Use ArcGIS Pro Python on Windows. Example pattern:

```powershell
& "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" EVI\02_arcpy_extract_evi.py
```

For FLDAS, run the four partition scripts separately (`02_arcpy_extract_fldas_part1.py` through `02_arcpy_extract_fldas_part4.py`); they point to different configured part folders and emit corresponding `p1`-style CSVs. Before running any ArcPy script, create `config/paths.ini` from `config/paths_template.ini` and check the local input/output paths and identifier fields.

### Run converted scripts or archived notebooks

The operational handover entry points are the converted `.py` scripts listed in `docs/03_workflow_runbook.md`. The original production notebooks are archived under `archive/notebooks/` and retained as references.

```bash
jupyter lab
```

To inspect or execute an archived notebook when local data paths and dependencies are available:

```bash
jupyter nbconvert --execute --to notebook --inplace 'archive/notebooks/Final_harmonise/00_combine_all_ch.ipynb'
```

### Validate unified IPCCH handover schema

The G-05 unified schema lives under `Outcome/ipcch_unified/schema/`.

```bash
python3 tools/build_monthly_ipcch_scaffold.py --year 2026 --month 4
python3 tools/validate_ipcch_schema.py --mode historical-panel --csv Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv
python3 tools/validate_ipcch_schema.py --mode forecast-scaffold --csv Outcome/ipcch_unified/interim/ipcch_scaffold_202604.csv
python3 tools/validate_ipcch_schema.py --mode fixed-slow-area --csv Outcome/ipcch_unified/features/ipcch_fixed_slow_features_by_area.csv
```

## Workflow architecture

The repository is a collection of operational workflows rather than a Python package. Folder prefixes (`00_`, `01_`, `02_`, `03_`) encode rough execution order within each data source.

### Remote-sensing raster workflows

Remote-sensing sources follow a common pattern:

1. Export monthly rasters from Earth Engine or download source GeoTIFFs.
2. Download or unzip raw rasters locally.
3. Use ArcPy zonal statistics against IPC/CH polygons.
4. Write wide CSV outputs with one row per spatial unit and one monthly column per date/band/statistic.
5. `Final_harmonise` scripts/notebooks melt/pivot and merge these wide outputs into the modelling panel.

Key folders:

- `EVI/`: MODIS MOD13A3 EVI export/download and `02_arcpy_extract_evi.py`, which calculates MEAN and STD into `EVI_mean_extraction_results.csv` and `EVI_std_extraction_results.csv`. Identifier field is configured through `config/paths.ini`.
- `FLDAS/`: Earth Engine export/download plus four parallelized ArcPy extraction scripts split by raster parts. Each script processes multi-band monthly FLDAS rasters, computes MEAN and STD per band, and writes chunked CSVs such as `FLDAS_mean_extraction_results_p1.csv` and `FLDAS_std_extraction_results_p1.csv`. Identifier field is currently `fid`.
- `GOSIF_GPP/`: direct downloads for mean and standard deviation `.tif.gz`, unzip helpers, then ArcPy mean/std extraction to CH outputs. Date columns use source keys like `YYYY.MMM`.
- `VIIRS_nightlight/`: Earth Engine export/download from VIIRS monthly DNB, `02_arcpy_mosaic_viirs_nightlight.py` groups tiled monthly rasters into mosaics, and `03_arcpy_extract_viirs_nightlight.py` calculates SUM and STD by polygon. Set the EE date window to the target feature month; `DMSP_OLS` in configured paths is a legacy folder name.

These ArcPy scripts rely heavily on `in_memory` temporary tables and Spatial Analyst checkout/check-in. Be careful when changing multiprocessing or temporary table names because ArcPy workspace collisions and memory pressure are recurring concerns.

### Tabular/scaffold feature workflows

The tabular workflows start from a monthly IPC/CH scaffold keyed by location and time, append source-derived features, and write completed CSVs used by harmonisation:

- `ACLED/00_add_acled_features.py`: aggregates conflict events by location/month and merges ACLED metrics to the scaffold. Notebook reference: `archive/notebooks/ACLED/00_add_ACLED_IPCCH.ipynb`.
- `FAO_price/00_add_fao_price_features.py`: combines FAO price workbooks, derives monthly price features, and merges by lat/lon/year/month. Notebook reference: `archive/notebooks/FAO_price/00_add_FAO_ipcch_update.ipynb`.
- `WB_indicator/00_add_world_bank_features.py`: merges World Bank country-year indicators such as CPI, GDP, governance, and interpolated Gini values into the CH scaffold. Notebook reference: `archive/notebooks/WB_indicator/00_add_WBG_ch.ipynb`.
- `WFP_indicator/00_add_wfp_price_features.py`: aggregates WFP market price trends by country/month and joins to the CH scaffold. Notebook reference: `archive/notebooks/WFP_indicator/00_add_WFP_ch.ipynb`.

### Final harmonisation

`Final_harmonise/00_combine_all_ch.py` and `Final_harmonise/00_combine_all_IPC.py` are the main integration points. They read source-specific completed CSVs, normalize identifiers, reshape wide remote-sensing tables to long monthly features, and merge everything into assembled CH/IPC panel CSVs. The matching notebooks are retained under `archive/notebooks/Final_harmonise/`.

`Final_harmonise/01_CH_final_process.py` and `Final_harmonise/01_IPC_final_process.py` then join outcome variables and write final modelling files plus numerical summaries.

When changing any upstream output schema, check the corresponding merge/melt code in `Final_harmonise` before renaming columns. Important join keys include `lat`, `lon`, `lat_fixed`, `lon_fixed`, `year`, `month`, `area_id`, `admin_code`, `region_id`, `fid`, and `title` depending on the source.

### Shared identifiers and examples

`Outcome/ipcch_unified/` is the active unified IPCCH outcome/reference handover
package:

- `raw/IPCCH_2026_completed.csv`: historical panel through 2026-04.
- `interim/ipcch_scaffold_202604.csv`: one-month production scaffold example.
- `interim/ipcch_scaffold_202501_202604.csv`: multi-month reference/batch
  scaffold, not required for monthly production.
- `spatial/ipcch_admin_geometry.*`: unified geometry shapefile package.
- `spatial/unique_area_id_lat_lon.csv`: `area_id` to coordinate lookup.
- `country_area_id_lookup.csv`: `area_id` to country lookup.
- `features/ipcch_fixed_slow_features_by_area.csv`: G-03 fixed/slow-moving
  feature handover asset generated from the historical panel.
- `metadata/ipcch_fixed_slow_source_vintage_manifest.csv`: G-04 provenance
  manifest for fixed/slow feature families.
- `metadata/variable_codebook_reorganized.csv`: copied IPCCH codebook used by
  the schema contract.
- `schema/`: G-05 unified long-panel model input contract. The canonical model
  key is `(area_id, year, month)`; current raw/scaffold assets use
  `(admin_code, lat, lon, year, month)` and derive `area_id` from `admin_code`.

For production, build or receive one target-month scaffold and append feature
families to that month. Do not require a multi-month scaffold unless running a
batch rebuild or QA comparison.

`polygons_and_identifier/` now keeps only lightweight identifier scope assets
such as `country_scope_ipcch_2026.csv`. Older combined IPC/CH reference files
were moved to `archive/legacy_reference_assets/` because they can be confused
with the current production contract.

If a future clone omits large reference files, retrieve them from the shared
data handover location recorded in `docs/04_output_inventory.md`.

## Current implementation caveats

- Local filled config files such as `config/paths.ini` and `config/ee_gcs.ini` are operator-specific. Keep templates in shared code handover and keep workstation-specific filled configs local.
- Full ArcPy, Earth Engine, and Google Cloud production runs must happen in the operator's configured Windows/GEE/GCS environment.
