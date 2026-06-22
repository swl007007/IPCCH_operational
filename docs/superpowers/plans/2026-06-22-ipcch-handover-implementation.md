# IPC-CH Handover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a light-refactor handover package for the IPC-CH monthly operational workflows so a new operator can run, configure, and validate the copied scripts without relying on Weilun's local paths or undocumented account setup.

**Architecture:** Keep the existing source-specific workflow folders and current data logic. Add shared configuration, handover documentation, explicit file naming, notebook-to-script equivalents, and lightweight validation around the current workflow contracts. ArcPy scripts stay Python 2.x compatible and FLDAS remains split into part scripts.

**Tech Stack:** Windows paths and ArcGIS/ArcPy Spatial Analyst for raster workflows; Python 2.x-compatible standard library for ArcPy-facing scripts; Python 3 for IPC API and validation utilities; Earth Engine Code Editor JavaScript snippets; Google Cloud SDK `gcloud` and `gsutil`; Markdown handover docs; `.ini` configuration.

---

## Execution Notes

- Current workspace is not a Git repository. Do not initialize Git or create commits unless the user asks. Treat each task's verification command as the checkpoint.
- Do not run full Earth Engine exports, Google Cloud downloads, or ArcPy production extraction from WSL. Document those steps and run only syntax/config checks here.
- Preserve original notebooks as archived references when creating `.py` equivalents.
- Preserve ArcPy Python 2.x compatibility: no f-strings, no `pathlib`, no type annotations, no Python 3-only standard-library assumptions inside ArcPy scripts.
- FLDAS part scripts remain separate because local ArcPy processing can only handle a limited number of months per run.

## File Responsibilities

- `config/paths_template.ini`: local filesystem paths, identifier fields, source-specific raw/output folders, and IPC API years.
- `config/ee_gcs_template.ini`: non-secret Earth Engine and Google Cloud project, bucket, prefixes, date ranges, and small export settings.
- `workflow_config.py`: Python 2/3-compatible `.ini` reader and path resolver used by scripts.
- `docs/00_handover_overview.md`: ToR-to-workflow handover overview and owner responsibilities.
- `docs/01_environment_setup.md`: Windows, ArcPy, Python, package, and Google Cloud SDK setup.
- `docs/02_ee_gcs_account_setup.md`: new Google/Earth Engine/GCS account checklist.
- `docs/03_workflow_runbook.md`: ordered run instructions for each workflow family.
- `docs/04_output_inventory.md`: current/proposed inputs, outputs, keys, shape, downstream consumer, and large-data handover manifest.
- `tools/validate_csv_contract.py`: Python 3 CSV contract checker for row count, key uniqueness, column presence, and monthly-column summaries.
- Source folders (`EVI/`, `FLDAS/`, `GOSIF_GPP/`, `VIIRS_nightlight/`, `curl_IPC/`, `ACLED/`, `FAO_price/`, `WB_indicator/`, `WFP_indicator/`, `Final_harmonise/`): renamed scripts and converted production `.py` workflow files.

---

### Task 1: Create Handover Docs and Inventory Skeleton

**Files:**
- Create: `docs/00_handover_overview.md`
- Create: `docs/01_environment_setup.md`
- Create: `docs/02_ee_gcs_account_setup.md`
- Create: `docs/03_workflow_runbook.md`
- Create: `docs/04_output_inventory.md`

- [ ] **Step 1: Create `docs/00_handover_overview.md`**

Use this content:

```markdown
# IPC-CH Monthly Operational Handover Overview

This repository contains source-specific monthly data-preparation workflows for IPC/CH modelling. The handover goal is to let a new operator run the workflows without relying on Weilun's local paths, personal Google account, or notebook-only execution knowledge.

## Workflow Families

| Workflow family | Current folders | Primary operator after handover | Output contract |
| --- | --- | --- | --- |
| Core identifiers and polygons | `polygons_and_identifier/` | Weilun provides; new operator consumes | Reference scaffolds and geometry files. |
| EVI | `EVI/` | New operator | Wide monthly CSVs keyed by ArcPy zone identifier. |
| FLDAS | `FLDAS/` | New operator | Wide monthly-band CSVs split by processing part. |
| GOSIF-GPP | `GOSIF_GPP/` | New operator | Wide monthly CSVs for mean and standard deviation. |
| VIIRS nightlight | `VIIRS_nightlight/` | New operator | Wide monthly CSVs for sum and standard deviation. |
| ACLED | `ACLED/` | New operator | IPC-CH scaffold plus conflict features. |
| FAO prices | `FAO_price/` | New operator with Soonho-supported exports when needed | IPC-CH scaffold plus FAO price features. |
| World Bank indicators | `WB_indicator/` | New operator | IPC-CH scaffold plus country-year indicator features. |
| WFP prices | `WFP_indicator/` | New operator | IPC-CH scaffold plus WFP price features. |
| IPC API | `curl_IPC/` | New operator | Per-year and combined IPC areas/analyses outputs. |
| Final harmonise | `Final_harmonise/` | New operator | Combined CH/IPC panels and final modelling files. |

## Operator Rule

Run a workflow only after updating `config/paths.ini` and, for EE/GCS workflows, `config/ee_gcs.ini`. The `*_template.ini` files are examples; keep local filled configs out of shared code handover when they contain workstation-specific paths.
```

- [ ] **Step 2: Create `docs/01_environment_setup.md`**

Use this content:

```markdown
# Environment Setup

## Windows and ArcPy

Raster extraction and mosaicking scripts must run in the Windows ArcGIS Python environment that provides `arcpy` and Spatial Analyst.

Before running ArcPy scripts:

1. Confirm ArcGIS/ArcPy opens on Windows.
2. Confirm Spatial Analyst is licensed.
3. Confirm the operator can read local raster folders and write output CSV folders.
4. Confirm `config/paths.ini` exists and points to local data.

ArcPy-facing scripts preserve Python 2.x-compatible syntax. Do not add f-strings, `pathlib`, type annotations, or Python 3-only imports to those scripts.

## General Python

Non-ArcPy scripts use standard Python plus source-specific packages such as `pandas`, `numpy`, `requests`, `pycountry`, `polars`, `geopandas`, and `openpyxl`.

Recommended syntax-only check from WSL:

```bash
python3 -m py_compile workflow_config.py tools/validate_csv_contract.py curl_IPC/00_download_ipc_api.py
```

## Google Cloud SDK

Install Google Cloud SDK on the operator's Windows machine. Confirm these commands work after account setup:

```powershell
gcloud auth login
gsutil ls gs://operator-bucket-name
```
```

- [ ] **Step 3: Create `docs/02_ee_gcs_account_setup.md`**

Use this content:

```markdown
# Earth Engine and Google Cloud Account Setup

The new operator account is not assumed to exist yet. Complete this checklist before any production remote-sensing export.

## Account Checklist

1. Create or identify the new Google account.
2. Register or authorize the account for Google Earth Engine.
3. Create or identify the GCP project used for exports.
4. Create or identify the GCS bucket used for raster exports.
5. Grant the operator account permission to write Earth Engine exports to the bucket and read bucket contents with `gsutil`.
6. Install Google Cloud SDK on the operator's Windows machine.
7. Run `gcloud auth login`.
8. Run `gsutil ls gs://operator-bucket-name`.
9. Run one small Earth Engine test export using the date range in `config/ee_gcs_template.ini`.
10. Download the small test export with `gsutil -m cp`.

## Production Rule

Do not start a full EVI, FLDAS, or VIIRS export until one small test export has reached GCS and downloaded locally.
```

- [ ] **Step 4: Create `docs/03_workflow_runbook.md`**

Use this content:

```markdown
# Workflow Runbook

Every workflow section lists the step order, config sections, expected inputs, and expected outputs. Replace local operator settings in `config/paths.ini` and `config/ee_gcs.ini` before running.

## EVI

1. Run Earth Engine Code Editor script: `EVI/00_ee_export_evi.txt`.
2. Download exports with: `EVI/01_gcs_download_evi.txt`.
3. Run ArcPy extraction on Windows: `EVI/02_arcpy_extract_evi.py`.
4. Expected outputs: `EVI_mean_extraction_results.csv` and `EVI_std_extraction_results.csv`.
5. Output shape: wide monthly table keyed by `region_id`.

## FLDAS

1. Run Earth Engine Code Editor script: `FLDAS/00_ee_export_fldas_all_bands.txt`.
2. Download exports with: `FLDAS/01_gcs_download_fldas.txt`.
3. Run the four ArcPy part scripts separately: `02_arcpy_extract_fldas_part1.py` through `02_arcpy_extract_fldas_part4.py`.
4. Expected outputs: part-specific wide monthly-band mean and standard deviation CSVs.
5. FLDAS remains split because local ArcPy processing cannot reliably handle all months in one run.

## GOSIF-GPP

1. Run `GOSIF_GPP/00_download_gosif_gpp_mean.py`.
2. Run `GOSIF_GPP/00_download_gosif_gpp_sd.py`.
3. Run `GOSIF_GPP/01_unzip_gosif_gpp_mean.py`.
4. Run `GOSIF_GPP/01_unzip_gosif_gpp_sd.py`.
5. Run `GOSIF_GPP/02_arcpy_extract_gosif_gpp_mean.py`.
6. Run `GOSIF_GPP/02_arcpy_extract_gosif_gpp_sd.py`.

## VIIRS Nightlight

1. Run Earth Engine Code Editor script: `VIIRS_nightlight/00_ee_export_viirs_nightlight.txt`.
2. Download exports with: `VIIRS_nightlight/01_gcs_download_viirs_nightlight.txt`.
3. Run `VIIRS_nightlight/02_arcpy_mosaic_viirs_nightlight.py`.
4. Run `VIIRS_nightlight/03_arcpy_extract_viirs_nightlight.py`.

## Tabular Feature Workflows

Run the converted scripts after checking raw input filenames in `config/paths.ini`:

- `ACLED/00_add_acled_features.py`
- `FAO_price/00_add_fao_price_features.py`
- `WB_indicator/00_add_world_bank_features.py`
- `WFP_indicator/00_add_wfp_price_features.py`

Each output should preserve scaffold rows unless the source workflow documents a deliberate filter.

## IPC API

Set `IPCINFO_API_KEY`, then run:

```bash
IPCINFO_API_KEY='<operator-key>' python3 curl_IPC/00_download_ipc_api.py
```

Expected outputs are per-year files and combined areas/analyses files under `curl_IPC/outputs/`.

## Final Harmonise

Run converted final harmonise scripts after all source workflow outputs exist:

- `Final_harmonise/00_combine_all_ch.py`
- `Final_harmonise/00_combine_all_IPC.py`
- `Final_harmonise/01_CH_final_process.py`
- `Final_harmonise/01_IPC_final_process.py`
```

- [ ] **Step 5: Create `docs/04_output_inventory.md`**

Use this content:

```markdown
# Output Inventory and Data Handover Manifest

## Workflow Output Contracts

| Workflow | Current/proposed output | Identifier | Shape | Downstream consumer |
| --- | --- | --- | --- | --- |
| EVI | `EVI_mean_extraction_results.csv`, `EVI_std_extraction_results.csv` | `region_id` mapped from ArcPy zone field | Wide monthly | Final harmonise CH/IPC combine scripts. |
| FLDAS | `FLDAS_mean_extraction_results_p*.csv`, `FLDAS_std_extraction_results_p*.csv` | `region_id` mapped from ArcPy zone field | Wide monthly-band, split by part | Final harmonise after consistent part handling. |
| GOSIF-GPP | `GOSIF_GPP_extraction_results_ch.csv`, `GOSIF_GPP_extraction_results_SD.csv` | `region_id` | Wide monthly | Final harmonise. |
| VIIRS | `nightlight_sum_extraction_results.csv`, `nightlight_std_extraction_results.csv` | `region_id` | Wide monthly | Final harmonise. |
| ACLED | `ch_with_merged_acled_metrics.csv` or configured equivalent | scaffold spatial/time keys | Scaffold plus features | Final harmonise. |
| FAO | `ch_with_matched_markets.csv`; `ipcch_with_matched_markets.csv` may also be written as a legacy alias | scaffold spatial/time keys | Scaffold plus features | Final harmonise. |
| World Bank | `ch_WBG_completed.csv` or configured equivalent | country/year plus scaffold keys | Scaffold plus features | Final harmonise. |
| WFP | `ch_WFP_prices.csv` or configured equivalent | country/month plus scaffold keys | Scaffold plus features | Final harmonise. |
| IPC API | `areas_*.geojson`, `analyses_*.json`, combined files | IPC API identifiers | Per-year and combined JSON/GeoJSON | IPC reference processing. |

## Required Local Reference Files

| File | Handover location | Required check |
| --- | --- | --- |
| `polygons_and_identifier/geoidentifier_ipcch.csv` | Repository or shared data folder if too large | row count, columns, key fields. |
| `polygons_and_identifier/gdf_ipc_ch_final.geojson` | Repository or shared data folder if too large | feature count, CRS, key fields. |
| `polygons_and_identifier/gdf_ipc_ch_final_country_count.csv` | Repository or shared data folder if too large | row count and country coverage. |
| `polygons_and_identifier/IPC_scaffold_example.csv` | Repository | columns and example row count. |

Large or sensitive data should be handed over through Dropbox, SharePoint, GCS, or external drive rather than GitHub. Record storage location, file size, row count, checksum when practical, and regeneration instructions.
```

- [ ] **Step 6: Verify docs were created**

Run:

```bash
test -f docs/00_handover_overview.md
test -f docs/01_environment_setup.md
test -f docs/02_ee_gcs_account_setup.md
test -f docs/03_workflow_runbook.md
test -f docs/04_output_inventory.md
```

Expected: all commands exit 0 with no output.

---

### Task 2: Add Configuration Templates and Shared Config Loader

**Files:**
- Create: `config/paths_template.ini`
- Create: `config/ee_gcs_template.ini`
- Create: `workflow_config.py`

- [ ] **Step 1: Create `config/paths_template.ini`**

Use this content:

```ini
[paths]
project_root = C:\IPCCH_monthly_operational
source_data_root = C:\IPCCH_source_data
polygon_input = ${PROJECT_ROOT}\polygons_and_identifier\gdf_ipc_ch_final.geojson
scaffold_input = ${PROJECT_ROOT}\polygons_and_identifier\geoidentifier_ipcch.csv
output_root = C:\IPCCH_outputs

[identifiers]
ipc_area_id = area_id
ch_admin_code = admin_code
arcpy_zone_field = fid

[evi]
raw_raster_folder = C:\IPCCH_source_data\EVI\MODIS_MOD13A3_Monthly
output_folder = C:\IPCCH_source_data\EVI\output_ch
filename_pattern = MOD13A3_*.tif
zone_field = admin_code

[fldas]
part1_folder = C:\IPCCH_source_data\FEWSNET_predictors\FLDAS_Monthly\Part1
part2_folder = C:\IPCCH_source_data\FEWSNET_predictors\FLDAS_Monthly\Part2
part3_folder = C:\IPCCH_source_data\FEWSNET_predictors\FLDAS_Monthly\Part3
part4_folder = C:\IPCCH_source_data\FEWSNET_predictors\FLDAS_Monthly\Part4
output_folder = C:\IPCCH_source_data\FEWSNET_predictors\output_ch
filename_pattern = *_all_bands.tif
zone_field = fid
max_processes = 4

[gosif_gpp]
download_folder_mean = C:\IPCCH_source_data\GOSIF_GPP\downloads_mean
download_folder_sd = C:\IPCCH_source_data\GOSIF_GPP\downloads_sd
raw_raster_folder_mean = C:\IPCCH_source_data\GOSIF_GPP\downloads_mean
raw_raster_folder_sd = C:\IPCCH_source_data\GOSIF_GPP\downloads_sd
output_folder = C:\IPCCH_source_data\GOSIF_GPP\output_ch
zone_field = fid

[viirs]
raw_tile_folder = C:\IPCCH_source_data\DMSP_OLS\image\nightlight
mosaic_folder = C:\IPCCH_source_data\DMSP_OLS\image\nightlight_mosaic
output_folder = C:\IPCCH_source_data\DMSP_OLS\output_ch
zone_field = fid

[tabular]
acled_raw_file = C:\IPCCH_source_data\ACLED\ACLED Data_2026-05-11_ipcch.csv
fao_raw_file_1 = C:\IPCCH_source_data\FAO\FAO_DATA_FOR_MIGUEL.xlsx
fao_raw_file_2 = C:\IPCCH_source_data\FAO\FOOD_CRISIS_FAO_PRICE_DATA_04012026.xlsx
wb_folder = C:\IPCCH_source_data\WBG
wfp_raw_file = C:\IPCCH_source_data\WFP\Prices-Export-Tue Dec 02 2025 16_03_28 GMT-0500.csv
tabular_output_root = C:\IPCCH_source_data

[ipc_api]
output_folder = ${PROJECT_ROOT}\curl_IPC\outputs
start_year = 2017
end_year = 2026
api_key_env_var = IPCINFO_API_KEY
```

- [ ] **Step 2: Create `config/ee_gcs_template.ini`**

Use this content:

```ini
[google_cloud]
project = operator-gcp-project
bucket = operator-bucket-name
local_download_root = C:\IPCCH_source_data\downloaded_rasters

[earth_engine]
account_note = new operator account must be authorized before production export
test_start_date = 2024-01-01
test_end_date = 2024-02-01

[evi]
bucket_prefix = MODIS_MOD13A3_Monthly
export_start_date = 2010-01-01
export_end_date = 2024-12-01

[fldas]
bucket_prefix = FLDAS_Monthly
export_start_date = 2010-01-01
export_end_date = 2025-01-01

[viirs]
bucket_prefix = nightlight
export_start_date = 2012-04-01
export_end_date = 2025-01-01
```

- [ ] **Step 3: Create `workflow_config.py`**

Use this exact Python 2/3-compatible content:

```python
from __future__ import print_function

import os
import ntpath

try:
    import configparser
except ImportError:
    import ConfigParser as configparser


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


def default_config_path():
    env_path = os.environ.get("IPCCH_CONFIG")
    if env_path:
        return env_path
    return os.path.join(ROOT_DIR, "config", "paths.ini")


def load_config(path=None):
    config_path = path or default_config_path()
    parser = configparser.RawConfigParser()
    read_files = parser.read(config_path)
    if not read_files:
        template = os.path.join(ROOT_DIR, "config", "paths_template.ini")
        raise RuntimeError(
            "Could not read config file: {0}. Copy {1} to config/paths.ini "
            "or set IPCCH_CONFIG.".format(config_path, template)
        )
    return parser


def get_value(config, section, option, default=None):
    if config.has_section(section) and config.has_option(section, option):
        return config.get(section, option)
    if default is not None:
        return default
    raise RuntimeError("Missing config value [{0}] {1}".format(section, option))


def _expanded(value, project_root_hint=None):
    if project_root_hint is None:
        project_root_hint = get_project_root_hint()
    value = value.replace("${PROJECT_ROOT}", project_root_hint)
    return os.path.expandvars(value)


def get_project_root_hint():
    return os.environ.get("PROJECT_ROOT", ROOT_DIR)


def _project_root_from_config(config):
    if config.has_section("paths") and config.has_option("paths", "project_root"):
        project_root = config.get("paths", "project_root")
        return _expanded(project_root, get_project_root_hint())
    return get_project_root_hint()


def resolve_path(config, section, option, default=None):
    project_root = _project_root_from_config(config)
    raw_value = get_value(config, section, option, default)
    expanded = _expanded(raw_value, project_root)
    if os.path.isabs(expanded) or ntpath.isabs(expanded):
        return os.path.normpath(expanded)
    return os.path.normpath(os.path.join(project_root, expanded))


def require_file(path, label):
    if not os.path.isfile(path):
        raise RuntimeError("Missing required file for {0}: {1}".format(label, path))
    return path


def require_dir(path, label):
    if not os.path.isdir(path):
        raise RuntimeError("Missing required folder for {0}: {1}".format(label, path))
    return path


def ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)
    return path
```

- [ ] **Step 4: Verify config helper syntax**

Run:

```bash
python3 -m py_compile workflow_config.py
```

Expected: command exits 0 with no output.

- [ ] **Step 5: Verify missing local config produces a clear error**

Run:

```bash
python3 -c "import workflow_config; workflow_config.load_config()"
```

Expected if `config/paths.ini` does not exist: non-zero exit with message containing `Copy` and `config/paths.ini`. If the local config already exists, this command exits 0.

---

### Task 3: Rename Production Workflow Files

**Files:**
- Rename current production files according to `docs/superpowers/specs/2026-06-22-ipcch-handover-design.md`

- [ ] **Step 1: Rename EVI files**

Run:

```bash
mv EVI/00_EEscript.txt EVI/00_ee_export_evi.txt
mv EVI/01_download_bucket.txt EVI/01_gcs_download_evi.txt
mv EVI/02_extract_EVI_from_raw.py EVI/02_arcpy_extract_evi.py
```

Expected: files exist under new names and old names no longer exist.

- [ ] **Step 2: Rename FLDAS files**

Run:

```bash
mv 'FLDAS/00_export_to_bucket(all_bands).txt' FLDAS/00_ee_export_fldas_all_bands.txt
mv FLDAS/01_download_bucket.txt FLDAS/01_gcs_download_fldas.txt
mv FLDAS/02_alternative_extract_ch.py FLDAS/02_arcpy_extract_fldas_part1.py
mv FLDAS/02_alternative_extract_ch_2.py FLDAS/02_arcpy_extract_fldas_part2.py
mv FLDAS/02_alternative_extract_ch_3.py FLDAS/02_arcpy_extract_fldas_part3.py
mv FLDAS/02_alternative_extract_ch_4.py FLDAS/02_arcpy_extract_fldas_part4.py
```

Expected: four FLDAS part scripts remain separate.

- [ ] **Step 3: Rename GOSIF folder and files**

Run:

```bash
mv 'GOSIF_GPP(yearly update)' GOSIF_GPP
mv GOSIF_GPP/00_download_GOSIF_GPP.py GOSIF_GPP/00_download_gosif_gpp_mean.py
mv GOSIF_GPP/00_download_GOSIF_GPP_sd.py GOSIF_GPP/00_download_gosif_gpp_sd.py
mv GOSIF_GPP/01_extract_GOSIF_GPP_from_tarzip.py GOSIF_GPP/01_unzip_gosif_gpp_mean.py
mv GOSIF_GPP/01_extract_GOSIF_GPP_sd_from_tarzip.py GOSIF_GPP/01_unzip_gosif_gpp_sd.py
mv GOSIF_GPP/02_extract_GPP_mean_ch.py GOSIF_GPP/02_arcpy_extract_gosif_gpp_mean.py
mv GOSIF_GPP/02_extract_GPP_SD_ch.py GOSIF_GPP/02_arcpy_extract_gosif_gpp_sd.py
```

Expected: folder path has no spaces or parentheses.

- [ ] **Step 4: Rename VIIRS files**

Run:

```bash
mv 'VIIRS_nightlight/00_export_to_bucket_GEE(with_compression_and_transform).txt' VIIRS_nightlight/00_ee_export_viirs_nightlight.txt
mv VIIRS_nightlight/01_download_bucket.txt VIIRS_nightlight/01_gcs_download_viirs_nightlight.txt
mv VIIRS_nightlight/02_Mosaic.py VIIRS_nightlight/02_arcpy_mosaic_viirs_nightlight.py
mv VIIRS_nightlight/03_alternative_extract_nightlight_ch.py VIIRS_nightlight/03_arcpy_extract_viirs_nightlight.py
```

Expected: step order is `00`, `01`, `02`, `03`.

- [ ] **Step 5: Rename IPC API script**

Run:

```bash
mv curl_IPC/00_curl.py curl_IPC/00_download_ipc_api.py
```

Expected: `curl_IPC/00_download_ipc_api.py` exists.

- [ ] **Step 6: Verify renamed file set**

Run:

```bash
test -f EVI/00_ee_export_evi.txt
test -f EVI/01_gcs_download_evi.txt
test -f EVI/02_arcpy_extract_evi.py
test -f FLDAS/02_arcpy_extract_fldas_part4.py
test -f GOSIF_GPP/02_arcpy_extract_gosif_gpp_sd.py
test -f VIIRS_nightlight/03_arcpy_extract_viirs_nightlight.py
test -f curl_IPC/00_download_ipc_api.py
```

Expected: all commands exit 0 with no output.

---

### Task 4: Update EE and GCS Text Scripts for Handover

**Files:**
- Modify: `EVI/00_ee_export_evi.txt`
- Modify: `EVI/01_gcs_download_evi.txt`
- Modify: `FLDAS/00_ee_export_fldas_all_bands.txt`
- Modify: `FLDAS/01_gcs_download_fldas.txt`
- Modify: `VIIRS_nightlight/00_ee_export_viirs_nightlight.txt`
- Modify: `VIIRS_nightlight/01_gcs_download_viirs_nightlight.txt`

- [ ] **Step 1: Add explicit operator variables to each EE script**

At the top of each EE script, add a block following this pattern and replace direct bucket literals with `GCS_BUCKET` and prefix literals with `GCS_PREFIX`:

```javascript
// Handover settings. Keep in sync with config/ee_gcs.ini.
var GCS_BUCKET = 'operator-bucket-name';
var GCS_PREFIX = 'source-specific-prefix';
```

Use these prefix values:

| File | `GCS_PREFIX` |
| --- | --- |
| `EVI/00_ee_export_evi.txt` | `MODIS_MOD13A3_Monthly` |
| `FLDAS/00_ee_export_fldas_all_bands.txt` | `FLDAS_Monthly` |
| `VIIRS_nightlight/00_ee_export_viirs_nightlight.txt` | `nightlight` |

- [ ] **Step 2: Update export calls to use the variables**

For EVI, the export block should include:

```javascript
bucket: GCS_BUCKET,
fileNamePrefix: GCS_PREFIX + '/' + fileName,
```

For FLDAS, the export block should include:

```javascript
bucket: GCS_BUCKET,
fileNamePrefix: GCS_PREFIX + '/' + fileName,
```

For VIIRS, the export block should include:

```javascript
bucket: GCS_BUCKET,
fileNamePrefix: GCS_PREFIX + '/' + fileName,
```

For VIIRS, keep `cloudOptimized: true` inside `formatOptions`, but make `fileDimensions` and `shardSize` top-level `Export.image.toCloudStorage` parameters.

- [ ] **Step 3: Update GCS download command files**

Use this exact pattern:

```text
gcloud auth login
REM Expected local result: C:\IPCCH_source_data\DESTINATION\SOURCE_PREFIX\...
gsutil -m cp -n -r gs://operator-bucket-name/SOURCE_PREFIX "C:\IPCCH_source_data\DESTINATION"
```

Use these values:

| File | `SOURCE_PREFIX` | `DESTINATION` |
| --- | --- | --- |
| `EVI/01_gcs_download_evi.txt` | `MODIS_MOD13A3_Monthly` | `EVI` |
| `FLDAS/01_gcs_download_fldas.txt` | `FLDAS_Monthly` | `FEWSNET_predictors` |
| `VIIRS_nightlight/01_gcs_download_viirs_nightlight.txt` | `nightlight` | `DMSP_OLS\image` |

Examples:

```text
gcloud auth login
REM Expected local result: C:\IPCCH_source_data\EVI\MODIS_MOD13A3_Monthly\...
gsutil -m cp -n -r gs://operator-bucket-name/MODIS_MOD13A3_Monthly "C:\IPCCH_source_data\EVI"

gcloud auth login
REM Expected local result: C:\IPCCH_source_data\FEWSNET_predictors\FLDAS_Monthly\...
gsutil -m cp -n -r gs://operator-bucket-name/FLDAS_Monthly "C:\IPCCH_source_data\FEWSNET_predictors"

gcloud auth login
REM Expected local result: C:\IPCCH_source_data\DMSP_OLS\image\nightlight\...
gsutil -m cp -n -r gs://operator-bucket-name/nightlight "C:\IPCCH_source_data\DMSP_OLS\image"
```

- [ ] **Step 4: Verify no old bucket literals remain**

Run:

```bash
rg -n "modis_monthly|YOUR_BUCKET_NAME|FLDAS_monthly" EVI FLDAS VIIRS_nightlight
```

Expected: no matches in the updated EE/GCS handover files.

---

### Task 5: Refactor IPC API Script Configuration

**Files:**
- Modify: `curl_IPC/00_download_ipc_api.py`

- [ ] **Step 1: Keep IPC API script Python 3 and import config helpers**

At the top of `curl_IPC/00_download_ipc_api.py`, after imports, add:

```python
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from workflow_config import get_value, load_config, resolve_path
```

- [ ] **Step 2: Add lazy runtime settings**

Do not load `config/paths.ini` or validate secrets at module import time. Keep
`BASE_URL`, retry constants, and `ENDPOINTS` as import-time constants, but move
config/env-dependent values into `load_runtime_settings()`:

```python
DEFAULT_START_YEAR = 2017
DEFAULT_END_YEAR = 2026
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"


def parse_year(value: str, label: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise RuntimeError("Invalid {0}: {1}. Expected integer year.".format(label, value))


def load_runtime_settings() -> dict[str, Any]:
    config = load_config()
    api_key_env_var = get_value(config, "ipc_api", "api_key_env_var", "IPCINFO_API_KEY")
    api_key = os.environ.get(api_key_env_var)
    if not api_key:
        raise RuntimeError("Set {0} in the environment before running.".format(api_key_env_var))
    start_year = parse_year(get_value(config, "ipc_api", "start_year", str(DEFAULT_START_YEAR)), "ipc_api.start_year")
    end_year = parse_year(get_value(config, "ipc_api", "end_year", str(DEFAULT_END_YEAR)), "ipc_api.end_year")
    if start_year > end_year:
        raise RuntimeError("ipc_api.start_year must be <= ipc_api.end_year: {0} > {1}".format(start_year, end_year))
    return {
        "api_key": api_key,
        "start_year": start_year,
        "end_year": end_year,
        "output_dir": Path(resolve_path(config, "ipc_api", "output_folder", str(DEFAULT_OUTPUT_DIR))),
        "retrieve_date": date.today().isoformat(),
    }
```

- [ ] **Step 3: Redact API keys in error messages**

Add `safe_error_message(exc, settings)` to replace raw, percent-encoded, and
query/form-encoded forms of the active API key with `<redacted>`, and use that
sanitized text in retry logs and final `RuntimeError` messages from
`fetch_year`.

- [ ] **Step 4: Pass settings through workflow functions**

Update the IPC API functions to accept and pass `settings` instead of reading
config-derived globals:

- `fetch_year(endpoint, year, settings)` uses `settings["api_key"]`.
- `per_year_path(endpoint, year, settings)` and `save_per_year(...)` use `settings["output_dir"]`.
- `download_all_years(endpoint, settings)` uses `settings["start_year"]` and `settings["end_year"]`.
- `combine_yearly(endpoint, yearly, settings)` uses `settings["retrieve_date"]` and `settings["output_dir"]`.
- `run_endpoint(endpoint, settings)` passes settings onward.
- `main()` calls `settings = load_runtime_settings()` and passes it to both endpoints.

- [ ] **Step 5: Verify Python 3 syntax and lazy import**

Run:

```bash
python3 -m py_compile curl_IPC/00_download_ipc_api.py
```

Expected: command exits 0 with no output.

Run an import smoke test with no config file or API key:

```bash
env -u IPCCH_CONFIG -u IPCINFO_API_KEY python3 - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location('ipc_api_script', 'curl_IPC/00_download_ipc_api.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print('import_ok')
PY
```

Expected: `import_ok`.

Run a runtime settings smoke test with temporary config and dummy API key:

```bash
IPCCH_CONFIG=/tmp/ipcch_paths_test.ini IPCINFO_API_KEY=dummy python3 - <<'PY'
from pathlib import Path
Path('/tmp/ipcch_paths_test.ini').write_text('[paths]\nproject_root = C:\\ROOT\n\n[ipc_api]\noutput_folder = ${PROJECT_ROOT}\\curl_IPC\\outputs\nstart_year = 2020\nend_year = 2021\napi_key_env_var = IPCINFO_API_KEY\n')
import importlib.util
spec = importlib.util.spec_from_file_location('ipc_api_script', 'curl_IPC/00_download_ipc_api.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
settings = mod.load_runtime_settings()
print(settings['start_year'], settings['end_year'], settings['output_dir'])
PY
```

Expected: `2020 2021 C:\ROOT\curl_IPC\outputs` or normalized equivalent.

---

### Task 6: Convert Production Notebooks to `.py` Equivalents

**Files:**
- Create: `ACLED/00_add_acled_features.py`
- Create: `FAO_price/00_add_fao_price_features.py`
- Create: `WB_indicator/00_add_world_bank_features.py`
- Create: `WFP_indicator/00_add_wfp_price_features.py`
- Create: `Final_harmonise/00_combine_all_ch.py`
- Create: `Final_harmonise/00_combine_all_IPC.py`
- Create: `Final_harmonise/01_CH_final_process.py`
- Create: `Final_harmonise/01_IPC_final_process.py`
- Archive after conversion: original `.ipynb` files under `archive/notebooks/`

- [ ] **Step 1: Convert notebooks to scripts**

If `jupyter nbconvert` is available, run:

```bash
jupyter nbconvert --to script archive/notebooks/ACLED/00_add_ACLED_IPCCH.ipynb
jupyter nbconvert --to script archive/notebooks/FAO_price/00_add_FAO_ipcch_update.ipynb
jupyter nbconvert --to script archive/notebooks/WB_indicator/00_add_WBG_ch.ipynb
jupyter nbconvert --to script archive/notebooks/WFP_indicator/00_add_WFP_ch.ipynb
jupyter nbconvert --to script archive/notebooks/Final_harmonise/00_combine_all_ch.ipynb
jupyter nbconvert --to script archive/notebooks/Final_harmonise/00_combine_all_IPC.ipynb
jupyter nbconvert --to script archive/notebooks/Final_harmonise/01_CH_final_process.ipynb
jupyter nbconvert --to script archive/notebooks/Final_harmonise/01_IPC_final_process.ipynb
```

Expected: `.py` or `.txt` script outputs are generated next to each notebook. Rename them to the target filenames listed above, then archive original notebooks under `archive/notebooks/`.

If `jupyter` is not installed in the current environment, extract code cells
from notebook JSON in order, separating cells with `# %%`, and write the target
files directly. Preserve original notebooks as archived references.

- [ ] **Step 2: Add standard config header to each converted script**

Add this header after imports in each converted script:

```python
from __future__ import print_function

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from workflow_config import ensure_dir, load_config, resolve_path, require_file

CONFIG = load_config()
```

- [ ] **Step 3: Replace personal-path `os.chdir(...)` patterns**

Replace hard-coded `os.chdir(...)` calls with source-root variables. Use this pattern in tabular scripts:

```python
source_data_root = resolve_path(CONFIG, "paths", "source_data_root")
output_root = ensure_dir(resolve_path(CONFIG, "tabular", "tabular_output_root"))
```

Use this pattern in final harmonise scripts:

```python
source_data_root = resolve_path(CONFIG, "paths", "source_data_root")
output_root = ensure_dir(resolve_path(CONFIG, "paths", "output_root"))
```

For this Task 6 light conversion, configured `os.chdir(...)` calls are
acceptable. The goal is to remove personal absolute paths from the converted
scripts while preserving notebook execution order and relative file layout.

Replace any direct personal absolute read like:

```python
pd.read_csv(r"C:\Users\swl00\IFPRI Dropbox\...\Outcome\ch_scaffold_fixed.csv")
```

with:

```python
pd.read_csv(os.path.join(source_data_root, "Outcome", "ch_scaffold_fixed.csv"))
```

Do not require all relative reads to be rewritten in Task 6 if the script first
changes into a configured `source_data_root` or configured source subfolder.
That broader path normalization belongs after `docs/04_output_inventory.md`
records final harmonise inputs and join keys.

- [ ] **Step 4: Preserve production outputs**

For every converted script, keep the current output CSV basename unless `docs/04_output_inventory.md` records a new basename. Use `os.path.join(output_root, ...)` or the source-specific configured folder for output writes.

For Task 6, output writes may remain relative to the configured working root if
that preserves the notebook's existing output layout. Do not leave outputs
relative to a personal absolute `C:\Users\...` working directory.

- [ ] **Step 5: Verify converted script syntax**

Run:

```bash
python3 -m py_compile \
  ACLED/00_add_acled_features.py \
  FAO_price/00_add_fao_price_features.py \
  WB_indicator/00_add_world_bank_features.py \
  WFP_indicator/00_add_wfp_price_features.py \
  Final_harmonise/00_combine_all_ch.py \
  Final_harmonise/00_combine_all_IPC.py \
  Final_harmonise/01_CH_final_process.py \
  Final_harmonise/01_IPC_final_process.py
```

Expected: command exits 0 with no output after conversion cleanup.

---

### Task 7: Refactor ArcPy Scripts to Read Config

**Files:**
- Modify: `EVI/02_arcpy_extract_evi.py`
- Modify: `FLDAS/02_arcpy_extract_fldas_part1.py`
- Modify: `FLDAS/02_arcpy_extract_fldas_part2.py`
- Modify: `FLDAS/02_arcpy_extract_fldas_part3.py`
- Modify: `FLDAS/02_arcpy_extract_fldas_part4.py`
- Modify: `GOSIF_GPP/00_download_gosif_gpp_mean.py`
- Modify: `GOSIF_GPP/00_download_gosif_gpp_sd.py`
- Modify: `GOSIF_GPP/01_unzip_gosif_gpp_mean.py`
- Modify: `GOSIF_GPP/01_unzip_gosif_gpp_sd.py`
- Modify: `GOSIF_GPP/02_arcpy_extract_gosif_gpp_mean.py`
- Modify: `GOSIF_GPP/02_arcpy_extract_gosif_gpp_sd.py`
- Modify: `VIIRS_nightlight/02_arcpy_mosaic_viirs_nightlight.py`
- Modify: `VIIRS_nightlight/03_arcpy_extract_viirs_nightlight.py`

- [ ] **Step 1: Add Python 2-compatible config import block to each ArcPy script**

Add this block after standard imports and before path constants:

```python
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from workflow_config import ensure_dir, get_value, load_config, resolve_path, require_dir, require_file
```

If the script does not already import `sys`, add:

```python
import sys
```

- [ ] **Step 2: Replace EVI hard-coded path block**

In `EVI/02_arcpy_extract_evi.py`, replace the input parameter block with:

```python
    config = load_config()
    tif_folder = require_dir(resolve_path(config, "evi", "raw_raster_folder"), "EVI raw_raster_folder")
    shapefile = require_file(resolve_path(config, "paths", "polygon_input"), "paths polygon_input")
    output_folder = ensure_dir(resolve_path(config, "evi", "output_folder"))
    id_field = get_value(config, "evi", "zone_field", get_value(config, "identifiers", "ch_admin_code", "admin_code"))
    filename_pattern = get_value(config, "evi", "filename_pattern", "MOD13A3_*.tif")
```

Then replace the TIF selection with:

```python
    tif_files = [os.path.join(tif_folder, f) for f in os.listdir(tif_folder)
                 if f.endswith('.tif') and f.startswith(filename_pattern.replace('*', ''))]
```

- [ ] **Step 3: Replace FLDAS part path blocks**

In each FLDAS part script, set the part key:

```python
    part_folder_key = "part1_folder"
```

Use `part2_folder`, `part3_folder`, and `part4_folder` in the other part scripts. Replace the input parameter block with:

```python
    config = load_config()
    tif_folder = require_dir(resolve_path(config, "fldas", part_folder_key), "FLDAS " + part_folder_key)
    shapefile = require_file(resolve_path(config, "paths", "polygon_input"), "paths polygon_input")
    output_folder = ensure_dir(resolve_path(config, "fldas", "output_folder"))
    id_field = get_value(config, "fldas", "zone_field", get_value(config, "identifiers", "arcpy_zone_field", "fid"))
    max_processes_config = int(get_value(config, "fldas", "max_processes", "4"))
```

Replace the process-count line with:

```python
    num_processes = max(1, min(num_cpus - 1, max_processes_config))
```

- [ ] **Step 4: Replace GOSIF download and unzip paths**

In `GOSIF_GPP/00_download_gosif_gpp_mean.py`, set:

```python
    config = load_config()
    destination_folder = ensure_dir(resolve_path(config, "gosif_gpp", "download_folder_mean"))
```

In `GOSIF_GPP/00_download_gosif_gpp_sd.py`, set:

```python
    config = load_config()
    destination_folder = ensure_dir(resolve_path(config, "gosif_gpp", "download_folder_sd"))
```

In unzip scripts, replace `os.chdir(...)` with:

```python
config = load_config()
input_folder = require_dir(resolve_path(config, "gosif_gpp", "download_folder_mean"), "GOSIF mean download folder")
os.chdir(input_folder)
```

Use `download_folder_sd` for the SD unzip script.

- [ ] **Step 5: Replace GOSIF ArcPy extraction path blocks**

For mean extraction:

```python
    config = load_config()
    tif_folder = require_dir(resolve_path(config, "gosif_gpp", "raw_raster_folder_mean"), "GOSIF mean raster folder")
    shapefile = require_file(resolve_path(config, "paths", "polygon_input"), "paths polygon_input")
    output_folder = ensure_dir(resolve_path(config, "gosif_gpp", "output_folder"))
    id_field = get_value(config, "gosif_gpp", "zone_field", get_value(config, "identifiers", "arcpy_zone_field", "fid"))
```

For SD extraction, use `raw_raster_folder_sd`.

- [ ] **Step 6: Replace VIIRS mosaic and extraction path blocks**

In `VIIRS_nightlight/02_arcpy_mosaic_viirs_nightlight.py`:

```python
config = load_config()
workspace = require_dir(resolve_path(config, "viirs", "raw_tile_folder"), "VIIRS raw_tile_folder")
mosaic_folder = ensure_dir(resolve_path(config, "viirs", "mosaic_folder"))
arcpy.env.workspace = workspace
```

Set `output_location=mosaic_folder` when calling `MosaicToNewRaster_management`.

In `VIIRS_nightlight/03_arcpy_extract_viirs_nightlight.py`:

```python
config = load_config()
tif_folder = require_dir(resolve_path(config, "viirs", "mosaic_folder"), "VIIRS mosaic_folder")
shapefile = require_file(resolve_path(config, "paths", "polygon_input"), "paths polygon_input")
output_folder = ensure_dir(resolve_path(config, "viirs", "output_folder"))
id_field = get_value(config, "viirs", "zone_field", get_value(config, "identifiers", "arcpy_zone_field", "fid"))
```

- [ ] **Step 7: Syntax-check ArcPy scripts without importing ArcPy execution**

Run:

```bash
python3 -m py_compile \
  EVI/02_arcpy_extract_evi.py \
  FLDAS/02_arcpy_extract_fldas_part1.py \
  FLDAS/02_arcpy_extract_fldas_part2.py \
  FLDAS/02_arcpy_extract_fldas_part3.py \
  FLDAS/02_arcpy_extract_fldas_part4.py \
  GOSIF_GPP/*.py \
  VIIRS_nightlight/*.py
```

Expected: command exits 0 with no output.

---

### Task 8: Add CSV Contract Validation Utility

**Files:**
- Create: `tools/validate_csv_contract.py`

- [ ] **Step 1: Create validation utility**

Use this content:

```python
from __future__ import print_function

import argparse
import csv
import re
import sys


def parse_args():
    parser = argparse.ArgumentParser(description="Validate simple IPC-CH CSV contracts.")
    parser.add_argument("--csv", required=True, help="CSV file to validate")
    parser.add_argument("--key", action="append", default=[], help="Key column. Repeat for composite keys.")
    parser.add_argument("--required-column", action="append", default=[], help="Required column. Repeat as needed.")
    parser.add_argument("--monthly-regex", default="", help="Regex used to count monthly columns")
    parser.add_argument("--min-monthly-columns", type=int, default=0)
    return parser.parse_args()


def read_header_and_rows(path):
    with open(path, "r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return reader.fieldnames or [], rows


def fail(message):
    print("FAIL: " + message)
    return 1


def main():
    args = parse_args()
    header, rows = read_header_and_rows(args.csv)
    header_set = set(header)

    if not rows:
        return fail("CSV has no data rows: {0}".format(args.csv))

    for column in args.required_column:
        if column not in header_set:
            return fail("Missing required column: {0}".format(column))

    for column in args.key:
        if column not in header_set:
            return fail("Missing key column: {0}".format(column))

    if args.key:
        seen = set()
        duplicates = 0
        for row in rows:
            key = tuple(row.get(column, "") for column in args.key)
            if key in seen:
                duplicates += 1
            seen.add(key)
        if duplicates:
            return fail("Duplicate key rows: {0}".format(duplicates))

    if args.monthly_regex:
        pattern = re.compile(args.monthly_regex)
        monthly_columns = [column for column in header if pattern.match(column)]
        if len(monthly_columns) < args.min_monthly_columns:
            return fail(
                "Monthly column count {0} is less than required {1}".format(
                    len(monthly_columns), args.min_monthly_columns
                )
            )
        print("Monthly columns: {0}".format(len(monthly_columns)))

    print("PASS: rows={0} columns={1}".format(len(rows), len(header)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify validation utility syntax**

Run:

```bash
python3 -m py_compile tools/validate_csv_contract.py
```

Expected: command exits 0 with no output.

- [ ] **Step 3: Run validation utility against a known reference CSV**

Run:

```bash
python3 tools/validate_csv_contract.py \
  --csv polygons_and_identifier/IPC_scaffold_example.csv \
  --key row_id \
  --required-column lat \
  --required-column lon \
  --required-column year \
  --required-column month
```

Expected: output begins with `PASS:`.

---

### Task 9: Update README and Local Agent Guidance

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Replace minimal README with handover entry points**

Use this content for `README.md`:

```markdown
# IPCCH Operational

This repository contains monthly operational data-preparation workflows for IPC/CH modelling.

Start here:

1. `docs/00_handover_overview.md`
2. `docs/01_environment_setup.md`
3. `docs/02_ee_gcs_account_setup.md`
4. `docs/03_workflow_runbook.md`
5. `docs/04_output_inventory.md`

Design and plan:

- `docs/superpowers/specs/2026-06-22-ipcch-handover-design.md`
- `docs/superpowers/plans/2026-06-22-ipcch-handover-implementation.md`

Local filled config files such as `config/paths.ini` and `config/ee_gcs.ini` are operator-specific. Share templates, not secrets.
```

- [ ] **Step 2: Update `CLAUDE.md` renamed paths**

Replace old path references with new renamed paths:

| Old | New |
| --- | --- |
| `EVI/02_extract_EVI_from_raw.py` | `EVI/02_arcpy_extract_evi.py` |
| `FLDAS/02_alternative_extract_ch.py` | `FLDAS/02_arcpy_extract_fldas_part1.py` |
| `GOSIF_GPP(yearly update)` | `GOSIF_GPP` |
| `VIIRS_nightlight/02_Mosaic.py` | `VIIRS_nightlight/02_arcpy_mosaic_viirs_nightlight.py` |
| `VIIRS_nightlight/03_alternative_extract_nightlight_ch.py` | `VIIRS_nightlight/03_arcpy_extract_viirs_nightlight.py` |
| `curl_IPC/00_curl.py` | `curl_IPC/00_download_ipc_api.py` |

- [ ] **Step 3: Verify no stale renamed script paths remain in docs**

Run:

```bash
rg -n "02_extract_EVI_from_raw|02_alternative_extract_ch|GOSIF_GPP\\(yearly update\\)|02_Mosaic|03_alternative_extract_nightlight_ch|00_curl.py" README.md CLAUDE.md docs
```

Expected: no matches, except inside historical migration-map sections if those sections intentionally mention current-to-proposed old paths.

---

### Task 10: Smoke Test and Verification Checklist

**Files:**
- Modify: `docs/03_workflow_runbook.md`
- Modify: `docs/04_output_inventory.md`

- [ ] **Step 1: Add smoke test section to `docs/03_workflow_runbook.md`**

Append:

```markdown
## Smoke Tests

Run these before a full monthly update.

| Workflow | Small input | Expected check |
| --- | --- | --- |
| EVI | One MOD13A3 raster month | Mean/std CSVs exist and include `region_id` plus one month column. |
| FLDAS | One part folder with a small month subset | Part-specific mean/std CSVs exist and include `region_id` plus band columns. |
| GOSIF-GPP | One mean file and one SD file | Wide CSVs exist and include `region_id` plus source month column. |
| VIIRS | One month of exported tiles | Mosaic exists, then sum/std CSVs exist. |
| ACLED | Small scaffold and raw ACLED sample | Output row count matches scaffold unless documented otherwise. |
| FAO | Small scaffold and FAO workbook sample | Output contains appended FAO feature columns. |
| World Bank | Small scaffold and WBG indicator sample | Output contains expected country-year features. |
| WFP | Small scaffold and WFP price sample | Output contains appended WFP feature columns. |
| IPC API | One year | Per-year areas/analyses files and combined files are written. |
| Final harmonise | Small source outputs from each family | Final schema includes keys, outcomes, and at least one column from each critical feature family. |
```

- [ ] **Step 2: Add validation command examples to `docs/04_output_inventory.md`**

Append:

```markdown
## Validation Command Examples

Remote-sensing wide table example:

```bash
python3 tools/validate_csv_contract.py --csv path/to/EVI_mean_extraction_results.csv --key region_id --required-column region_id --monthly-regex '^[0-9]{4}_[0-9]{2}$' --min-monthly-columns 1
```

Scaffold output example:

```bash
python3 tools/validate_csv_contract.py --csv path/to/ch_with_merged_acled_metrics.csv --key lat --key lon --key year --key month --required-column year --required-column month
```
```

- [ ] **Step 3: Run local verification commands**

Run:

```bash
python3 -m py_compile workflow_config.py tools/validate_csv_contract.py curl_IPC/00_download_ipc_api.py
python3 - <<'PY'
from pathlib import Path
bad = ["TB" + "D", "TO" + "DO", "FIX" + "ME", "??" + "?"]
paths = [p for root in ["docs", "config"] for p in Path(root).rglob("*") if p.is_file()]
paths += [Path("README.md"), Path("CLAUDE.md")]
hits = []
for path in paths:
    text = path.read_text(encoding="utf-8", errors="ignore")
    for token in bad:
        if token in text:
            hits.append((str(path), token))
if hits:
    for path, token in hits:
        print("%s contains %s" % (path, token))
    raise SystemExit(1)
PY
```

Expected: `py_compile` exits 0. The inline Python scan exits 0 with no reported token hits in newly created handover docs/config files.

---

## Completion Criteria

- Handover docs exist and cover overview, environment, EE/GCS account setup, runbook, output inventory, and smoke tests.
- Config templates exist and contain sections for paths, identifiers, EVI, FLDAS, GOSIF-GPP, VIIRS, tabular workflows, and IPC API.
- `workflow_config.py` compiles under Python 3 and uses Python 2-compatible syntax.
- Production files are renamed according to the migration map.
- IPC API script reads year/output/API key settings from config/environment.
- Production notebooks have `.py` equivalents while originals are archived under `archive/notebooks/`.
- ArcPy scripts read local paths and zone fields from config while preserving Python 2.x-compatible syntax.
- `tools/validate_csv_contract.py` runs on at least one existing CSV.
- Documentation states that full ArcPy/GEE/GCS production runs must happen on the operator's configured Windows/GEE/GCS environment.
