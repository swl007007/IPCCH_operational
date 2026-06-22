# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository purpose

This repository contains monthly operational data-preparation workflows for IPC/CH food-crisis modelling. The code is organized as source-specific scripts and notebooks that download, extract, aggregate, and harmonize raster and tabular indicators into IPC and Cadre Harmonisé monthly panels.

A design note at `docs/superpowers/specs/2026-06-22-ipcch-handover-design.md` describes the intended handover/refactor direction: keep source-specific workflow folders, make step ordering explicit, externalize paths/configuration, and preserve the current output contracts consumed by the final harmonisation notebooks.

## Environment and dependencies

There is no project-level dependency manifest, build system, lint config, or test suite in this repository. Dependencies are script/notebook-specific:

- ArcGIS Pro Python with Spatial Analyst (`arcpy`, `arcpy.sa`) is required for raster extraction and mosaicking scripts under `EVI/`, `FLDAS/`, `GOSIF_GPP(yearly update)/02_*`, and `VIIRS_nightlight/02_*`/`03_*`. These scripts should normally be run on Windows with the ArcGIS Pro Python environment, not WSL.
- General Python scripts/notebooks use packages including `pandas`, `numpy`, `tqdm`, `requests`, `geopandas`, `rasterio`, `polars`, `pycountry`, and Excel support such as `openpyxl`.
- Earth Engine export snippets are stored as `.txt` JavaScript files and are intended for the Earth Engine Code Editor.
- Google Cloud downloads use `gcloud auth login` and `gsutil -m cp` commands recorded in the `01_download_bucket.txt` files.

## Common commands

### Syntax-check Python scripts

This is the closest repository-wide verification available and does not require ArcPy to be importable because imports are not executed:

```bash
python3 -m py_compile \
  curl_IPC/00_curl.py \
  EVI/02_extract_EVI_from_raw.py \
  FLDAS/02_alternative_extract_ch.py \
  FLDAS/02_alternative_extract_ch_2.py \
  FLDAS/02_alternative_extract_ch_3.py \
  FLDAS/02_alternative_extract_ch_4.py \
  'GOSIF_GPP(yearly update)'/*.py \
  VIIRS_nightlight/*.py
```

Check a single script:

```bash
python3 -m py_compile path/to/script.py
```

### Run IPC API download

`curl_IPC/00_curl.py` downloads IPC `areas` and `analyses` year-by-year for 2017-2026 and writes per-year plus combined outputs to `curl_IPC/outputs/`.

```bash
cd curl_IPC
IPCINFO_API_KEY='<key-if-overriding-default>' python3 00_curl.py
```

### Run direct GOSIF-GPP downloads

```bash
cd 'GOSIF_GPP(yearly update)'
python3 00_download_GOSIF_GPP.py
python3 00_download_GOSIF_GPP_sd.py
```

The download scripts write into a local `downloads/` folder unless edited.

### Run ArcPy extraction or mosaicking scripts

Use ArcGIS Pro Python on Windows. Example pattern:

```powershell
& "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" EVI\02_extract_EVI_from_raw.py
```

For FLDAS, run the four partition scripts separately (`02_alternative_extract_ch.py` through `_4.py`); they point to different `Part*` folders and emit corresponding `p1`-style CSVs. Before running any ArcPy script, inspect and update the hard-coded Windows input/output paths and identifier field near the top or inside the `if __name__ == "__main__"` block.

### Run notebooks

The tabular feature engineering and final harmonisation workflows are notebooks. Launch interactively:

```bash
jupyter lab
```

Or execute a single notebook non-interactively when local data paths and dependencies are available:

```bash
jupyter nbconvert --execute --to notebook --inplace 'Final_harmonise/00_combine_all_ch.ipynb'
```

## Workflow architecture

The repository is a collection of operational workflows rather than a Python package. Folder prefixes (`00_`, `01_`, `02_`, `03_`) encode rough execution order within each data source.

### Remote-sensing raster workflows

Remote-sensing sources follow a common pattern:

1. Export monthly rasters from Earth Engine or download source GeoTIFFs.
2. Download or unzip raw rasters locally.
3. Use ArcPy zonal statistics against IPC/CH polygons.
4. Write wide CSV outputs with one row per spatial unit and one monthly column per date/band/statistic.
5. `Final_harmonise` notebooks melt/pivot and merge these wide outputs into the modelling panel.

Key folders:

- `EVI/`: MODIS MOD13A3 EVI export/download and `02_extract_EVI_from_raw.py`, which calculates MEAN and STD into `EVI_mean_extraction_results.csv` and `EVI_std_extraction_results.csv`. Identifier field is `admin_code` in the current script.
- `FLDAS/`: Earth Engine export/download plus four parallelized ArcPy extraction scripts split by raster parts. Each script processes multi-band monthly FLDAS rasters, computes MEAN and STD per band, and writes chunked CSVs such as `FLDAS_mean_extraction_results_p1.csv` and `FLDAS_std_extraction_results_p1.csv`. Identifier field is currently `fid`.
- `GOSIF_GPP(yearly update)/`: direct threaded downloads for mean and standard deviation `.tif.gz`, unzip helpers, then ArcPy mean/std extraction to CH outputs. Date columns use source keys like `YYYY.MMM`.
- `VIIRS_nightlight/`: Earth Engine export/download, `02_Mosaic.py` groups tiled monthly rasters into mosaics, and `03_alternative_extract_nightlight_ch.py` calculates SUM and STD by polygon.

These ArcPy scripts rely heavily on `in_memory` temporary tables and Spatial Analyst checkout/check-in. Be careful when changing multiprocessing or temporary table names because ArcPy workspace collisions and memory pressure are recurring concerns.

### Tabular/scaffold feature workflows

The tabular workflows start from a monthly IPC/CH scaffold keyed by location and time, append source-derived features, and write completed CSVs used by harmonisation:

- `ACLED/00_add_ACLED_IPCCH.ipynb`: aggregates conflict events by location/month and merges ACLED metrics to the scaffold.
- `FAO_price/00_add_FAO_ipcch_update.ipynb`: combines FAO price workbooks, derives monthly price features, and merges by lat/lon/year/month.
- `WB_indicator/00_add_WBG_ch.ipynb`: merges World Bank country-year indicators such as CPI, GDP, governance, and interpolated Gini values into the CH scaffold.
- `WFP_indicator/00_add_WFP_ch.ipynb`: aggregates WFP market price trends by country/month and joins to the CH scaffold.

### Final harmonisation

`Final_harmonise/00_combine_all_ch.ipynb` and `Final_harmonise/00_combine_all_IPC.ipynb` are the main integration points. They read source-specific completed CSVs, normalize identifiers, reshape wide remote-sensing tables to long monthly features, and merge everything into assembled CH/IPC panel CSVs.

`Final_harmonise/01_CH_final_process.ipynb` and `Final_harmonise/01_IPC_final_process.ipynb` then join outcome variables and write final modelling files plus numerical summaries.

When changing any upstream output schema, check the corresponding merge/melt code in `Final_harmonise` before renaming columns. Important join keys include `lat`, `lon`, `lat_fixed`, `lon_fixed`, `year`, `month`, `area_id`, `admin_code`, `region_id`, `fid`, and `title` depending on the source.

### Shared identifiers and examples

`polygons_and_identifier/` contains reference geometries/scaffolds and identifier examples:

- `IPC_scaffold_example.csv`: monthly IPC-style scaffold with `lat`, `lon`, `area_id`, `year`, `month`, and `row_id`.
- `geoidentifier_ipcch.csv`: lat/lon to geometry reference sample.
- `gdf_ipc_ch_final.geojson` and country-count CSVs: combined IPC/CH geometry references.

## Current implementation caveats

- Many scripts and notebooks contain hard-coded absolute Windows paths from the original workstation. Treat path changes as an expected part of running workflows in a new environment.
- Some `.txt` files are misnamed relative to their contents; for example, an Earth Engine script and a `gsutil` download command may be swapped between `00_*` and `01_*` files. Inspect the file content before executing.
- There are no Cursor rules, Copilot instructions, README, or existing CLAUDE.md at the time this file was created.
