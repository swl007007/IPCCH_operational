# IPC-CH Monthly Operational Handover Design

Date: 2026-06-22

## Purpose

This design defines a light refactor and handover package for the IPC-CH monthly
operational data-preparation scripts copied into this workspace. The goal is to
make the workflows transferable from Weilun's local setup to a new operator
without changing the core data logic.

The handover must support the Terms of Reference workbook and the current
workflow families:

- Earth Engine export -> Google Cloud Storage download -> ArcPy extraction:
  EVI and FLDAS.
- Direct download or local raw raster preparation -> ArcPy extraction:
  GOSIF-GPP mean and standard deviation.
- Local raw tabular inputs -> scaffold plus feature columns:
  ACLED, FAO prices, World Bank indicators, WFP indicators.
- IPC API download -> per-year JSON/GeoJSON files -> combined IPC areas and
  analyses outputs: `curl_IPC`.
- Earth Engine export -> Google Cloud Storage download -> mosaic -> ArcPy
  extraction: VIIRS nightlight.
- Final harmonisation notebooks/scripts that consume the source-specific outputs.

## Scope

In scope:

- Add handover documentation and workflow runbooks.
- Convert notebooks to `.py` scripts where practical while preserving the
  existing logic.
- Move local paths, raw filenames, bucket names, and operator-specific settings
  into editable configuration templates.
- Rename scripts so the execution order is clear.
- Keep ArcPy scripts compatible with the current Python 2.x ArcPy environment.
- Document Google Earth Engine and Google Cloud account migration steps without
  assuming the new account already exists.
- Document large-data handover for files that are required locally but should
  not necessarily be committed to a code repository.

Out of scope:

- Rewriting the full pipeline as a production CLI.
- Changing the underlying feature engineering logic.
- Combining FLDAS parts into a single large extraction run.
- Running Earth Engine exports, Google Cloud downloads, or ArcPy extraction in
  this environment.

## Current State Inventory

The current copied workspace contains these production-oriented workflow files:

| Workflow | Current files | Current role |
| --- | --- | --- |
| EVI | `EVI/00_EEscript.txt`, `EVI/01_download_bucket.txt`, `EVI/02_extract_EVI_from_raw.py` | Earth Engine export, GCS download, ArcPy zonal extraction. |
| FLDAS | `FLDAS/00_export_to_bucket(all_bands).txt`, `FLDAS/01_download_bucket.txt`, `FLDAS/02_alternative_extract_ch*.py` | Earth Engine all-band export, GCS download, split ArcPy zonal extraction. |
| GOSIF-GPP | `GOSIF_GPP(yearly update)/*.py` | Download, unzip, and ArcPy extraction for mean and standard deviation products. |
| VIIRS nightlight | `VIIRS_nightlight/*.txt`, `VIIRS_nightlight/02_Mosaic.py`, `VIIRS_nightlight/03_alternative_extract_nightlight_ch.py` | Earth Engine export, GCS download, mosaic, ArcPy extraction. |
| Raw tabular features | `archive/notebooks/ACLED/*.ipynb`, `archive/notebooks/FAO_price/*.ipynb`, `archive/notebooks/WB_indicator/*.ipynb`, `archive/notebooks/WFP_indicator/*.ipynb` | Archived production notebooks that append source-specific features to an IPC-CH scaffold. |
| IPC API | `curl_IPC/00_curl.py` | Downloads IPC areas and analyses by year and writes combined outputs. |
| Final harmonise | `archive/notebooks/Final_harmonise/*.ipynb` | Archived notebooks that consume source-specific outputs and create combined/final panels. |
| Identifiers | `polygons_and_identifier/*` | Local reference identifiers, scaffolds, and geometry inputs. |

Phase 0 must turn this high-level inventory into a file-level contract table:
current filename, source inputs, outputs, hard-coded paths, downstream
references, output shape, and whether the file is production or exploratory.

## Design Constraints

ArcPy compatibility is a hard constraint. ArcPy-facing scripts must avoid
Python 3-only syntax and libraries: no f-strings, no `pathlib`, no type
annotations, and no assumptions that packages unsupported by the ArcPy Python
2.x environment are available. Script names and configuration files should also
avoid characters that are awkward on Windows command lines.

FLDAS must remain split across multiple part scripts. The current four-part
layout reflects local processing limits where only several months can be handled
per run. The refactor can standardize naming and configuration, but it should
not imply that FLDAS is expected to run in one pass.

Earth Engine and Google Cloud handover must be documented as a checklist because
the new account has not been created yet. The checklist should cover Earth
Engine registration/authorization, GCP project or bucket ownership, IAM roles,
`gcloud auth login`, `gsutil` access tests, and a small test export before a
full monthly backfill or update.

## Output Contracts

Remote-sensing workflows produce wide monthly tables. Each output row is one
spatial unit, keyed by `admin_code` or `area_id` depending on the downstream
final harmonise input. Each monthly feature is stored as a separate column, for
example `YYYY_MM`, `YYYY.MMM`, or a source-specific date-band key already used
by the current scripts. For variables with multiple statistics, separate wide
tables may be produced, such as mean and standard deviation outputs.

Tabular/raw-data workflows produce a scaffold plus one or more feature columns.
The scaffold is the monthly IPC-CH template panel, and the workflow appends the
required derived feature columns for the matching month or spatial unit. This
applies to ACLED, FAO price, World Bank indicator, and WFP indicator workflows.

Final harmonise scripts are the consumer contract. They define which source
outputs are expected, which identifier field is used, and whether an input is a
wide monthly remote-sensing table or a scaffold-with-features table.

The implementation inventory should make the current contract explicit in this
form:

| Workflow | Output shape | Current identifier | Date columns | Statistics/features | Downstream consumer |
| --- | --- | --- | --- | --- | --- |
| EVI | Wide monthly CSVs | `region_id`, mapped from ArcPy zone field such as `admin_code` | `YYYY_MM` from `MOD13A3_YYYY_MM.tif` | Mean and standard deviation in separate CSVs | `Final_harmonise/00_combine_all_ch.py`; archived notebook reference under `archive/notebooks/Final_harmonise/`. |
| FLDAS | Wide monthly-band CSVs, split by processing part | `region_id`, mapped from ArcPy zone field such as `fid` | `YYYY_MM_Bn` | Mean and standard deviation, with part-specific outputs | Final harmonise after part outputs are assembled or read consistently. |
| GOSIF-GPP | Wide monthly CSVs | `region_id`, mapped from ArcPy zone field such as `fid` | Current script uses `YYYY.MXX` from `GOSIF_GPP_YYYY.MXX_*` filenames | Mean and standard deviation in separate CSVs | Final harmonise. |
| VIIRS nightlight | Wide monthly CSVs | `region_id`, mapped from ArcPy zone field such as `fid` | `YYYY_MM` from `nightlight_VIIRS_YYYY_MM*` filenames | Sum and standard deviation in separate CSVs | Final harmonise. |
| ACLED | Scaffold plus appended feature columns | Scaffold keys such as latitude, longitude, year, and month | Long monthly scaffold | Event-distance or event-count metrics from ACLED | Final harmonise. |
| FAO prices | Scaffold plus appended feature columns | Scaffold keys plus matched market/country fields | Long monthly scaffold | Price-market matching features | Final harmonise. |
| World Bank indicators | Scaffold plus appended feature columns | Country/year or scaffold country mapping | Long annual/monthly scaffold after carry-forward or merge logic | GDP, CPI, Gini, corruption percentile, infrastructure indicators | Final harmonise. |
| WFP prices | Scaffold plus appended feature columns | Country/market/month mapping plus scaffold keys | Long monthly scaffold | Market-level price features for selected commodities | Final harmonise. |
| IPC API | Per-year files plus combined JSON/GeoJSON outputs | IPC API area and analysis identifiers | Yearly API requests | Areas GeoJSON and analyses JSON | Source/reference data for downstream IPC processing. |

The exact join keys and required columns for final harmonise must be read from
the current final harmonise notebooks/scripts before any rename or conversion.

## Final Harmonise Contract

The final harmonise step is the binding consumer of the source workflows. The
handover must document every file read by final harmonise, including:

- source workflow and current/proposed path.
- required identifier columns and join keys.
- whether the input is wide monthly, wide monthly-band, long scaffold, or a
  reference geometry/scaffold file.
- required feature columns or feature-column prefixes.
- expected row count relationship to the scaffold.
- output files written by final harmonise and their required key/outcome columns.

Final harmonise validation should check unique keys, row counts, required
outcome columns, required feature-family presence, and basic numerical summaries.

## Proposed Directory and Naming Pattern

Keep the source-specific workflow folders, but make the step order explicit:

```text
config/
  paths_template.ini
  ee_gcs_template.ini

docs/
  00_handover_overview.md
  01_environment_setup.md
  02_ee_gcs_account_setup.md
  03_workflow_runbook.md
  04_output_inventory.md

EVI/
  00_ee_export_evi.txt
  01_gcs_download_evi.txt
  02_arcpy_extract_evi.py

FLDAS/
  00_ee_export_fldas_all_bands.txt
  01_gcs_download_fldas.txt
  02_arcpy_extract_fldas_part1.py
  02_arcpy_extract_fldas_part2.py
  02_arcpy_extract_fldas_part3.py
  02_arcpy_extract_fldas_part4.py

GOSIF_GPP/
  00_download_gosif_gpp_mean.py
  00_download_gosif_gpp_sd.py
  01_unzip_gosif_gpp_mean.py
  01_unzip_gosif_gpp_sd.py
  02_arcpy_extract_gosif_gpp_mean.py
  02_arcpy_extract_gosif_gpp_sd.py

VIIRS_nightlight/
  00_ee_export_viirs_nightlight.txt
  01_gcs_download_viirs_nightlight.txt
  02_arcpy_mosaic_viirs_nightlight.py
  03_arcpy_extract_viirs_nightlight.py

curl_IPC/
  00_download_ipc_api.py
```

Notebook-derived scripts should follow the same convention:

```text
ACLED/00_add_acled_features.py
FAO_price/00_add_fao_price_features.py
WB_indicator/00_add_world_bank_features.py
WFP_indicator/00_add_wfp_price_features.py
Final_harmonise/00_combine_all_ch.py
Final_harmonise/01_final_process_ch.py
```

Exact file renames can be adjusted during implementation if an existing file is
needed as a reference copy.

## Current-to-Proposed Migration Map

The implementation should use this map as the starting point. The map is based
on current file content, not only current filenames.

| Current file | Proposed file | Notes |
| --- | --- | --- |
| `EVI/00_EEscript.txt` | `EVI/00_ee_export_evi.txt` | Current content is Earth Engine export JavaScript. |
| `EVI/01_download_bucket.txt` | `EVI/01_gcs_download_evi.txt` | Current content is a `gsutil` download command. |
| `EVI/02_extract_EVI_from_raw.py` | `EVI/02_arcpy_extract_evi.py` | Keep Python 2.x ArcPy compatibility; move paths and `id_field` to config. |
| `FLDAS/00_export_to_bucket(all_bands).txt` | `FLDAS/00_ee_export_fldas_all_bands.txt` | Earth Engine all-band export. |
| `FLDAS/01_download_bucket.txt` | `FLDAS/01_gcs_download_fldas.txt` | GCS download command. |
| `FLDAS/02_alternative_extract_ch.py` | `FLDAS/02_arcpy_extract_fldas_part1.py` | Preserve part split because of local processing limits. |
| `FLDAS/02_alternative_extract_ch_2.py` | `FLDAS/02_arcpy_extract_fldas_part2.py` | Preserve part split. |
| `FLDAS/02_alternative_extract_ch_3.py` | `FLDAS/02_arcpy_extract_fldas_part3.py` | Preserve part split. |
| `FLDAS/02_alternative_extract_ch_4.py` | `FLDAS/02_arcpy_extract_fldas_part4.py` | Preserve part split. |
| `GOSIF_GPP(yearly update)/00_download_GOSIF_GPP.py` | `GOSIF_GPP/00_download_gosif_gpp_mean.py` | Folder rename requires checking downstream references. |
| `GOSIF_GPP(yearly update)/00_download_GOSIF_GPP_sd.py` | `GOSIF_GPP/00_download_gosif_gpp_sd.py` | Folder rename requires checking downstream references. |
| `GOSIF_GPP(yearly update)/01_extract_GOSIF_GPP_from_tarzip.py` | `GOSIF_GPP/01_unzip_gosif_gpp_mean.py` | Current name says extract; content unzips `.tif.gz`. |
| `GOSIF_GPP(yearly update)/01_extract_GOSIF_GPP_sd_from_tarzip.py` | `GOSIF_GPP/01_unzip_gosif_gpp_sd.py` | Current name says extract; content unzips `.tif.gz`. |
| `GOSIF_GPP(yearly update)/02_extract_GPP_mean_ch.py` | `GOSIF_GPP/02_arcpy_extract_gosif_gpp_mean.py` | Keep Python 2.x ArcPy compatibility. |
| `GOSIF_GPP(yearly update)/02_extract_GPP_SD_ch.py` | `GOSIF_GPP/02_arcpy_extract_gosif_gpp_sd.py` | Keep Python 2.x ArcPy compatibility. |
| `VIIRS_nightlight/00_export_to_bucket_GEE(with_compression_and_transform).txt` | `VIIRS_nightlight/00_ee_export_viirs_nightlight.txt` | Earth Engine export JavaScript. |
| `VIIRS_nightlight/01_download_bucket.txt` | `VIIRS_nightlight/01_gcs_download_viirs_nightlight.txt` | GCS download command. |
| `VIIRS_nightlight/02_Mosaic.py` | `VIIRS_nightlight/02_arcpy_mosaic_viirs_nightlight.py` | Keep Python 2.x ArcPy compatibility if run in the ArcPy environment. |
| `VIIRS_nightlight/03_alternative_extract_nightlight_ch.py` | `VIIRS_nightlight/03_arcpy_extract_viirs_nightlight.py` | Keep Python 2.x ArcPy compatibility. |
| `curl_IPC/00_curl.py` | `curl_IPC/00_download_ipc_api.py` | This script is not ArcPy-bound and may remain Python 3 if documented separately. |
| `archive/notebooks/ACLED/00_add_ACLED_IPCCH.ipynb` | `ACLED/00_add_acled_features.py` | Converted because it writes production intermediate/final CSVs. |
| `archive/notebooks/FAO_price/00_add_FAO_ipcch_update.ipynb` | `FAO_price/00_add_fao_price_features.py` | Converted because it writes production intermediate/final CSVs. |
| `archive/notebooks/WB_indicator/00_add_WBG_ch.ipynb` | `WB_indicator/00_add_world_bank_features.py` | Converted because it writes production intermediate/final CSVs. |
| `archive/notebooks/WFP_indicator/00_add_WFP_ch.ipynb` | `WFP_indicator/00_add_wfp_price_features.py` | Converted because it writes production intermediate/final CSVs. |
| `archive/notebooks/Final_harmonise/*.ipynb` | `Final_harmonise/*.py` equivalents | Converted production combine/final-process notebooks; original notebooks archived as references. |

## Configuration Design

Use `.ini` templates instead of YAML so ArcPy Python 2.x scripts can read the
configuration with `ConfigParser`.

`config/paths_template.ini` should contain local path settings such as:

- project root or source-data root.
- polygon/scaffold inputs.
- raw raster folders.
- raw tabular export files.
- output folders.
- identifier fields such as `admin_code`, `fid`, or `area_id`.

Minimum section shape:

```ini
[paths]
project_root = C:\path\to\IPCCH_monthly_operational
source_data_root = C:\path\to\source_data
polygon_input = ${PROJECT_ROOT}\polygons_and_identifier\gdf_ipc_ch_final.geojson
scaffold_input = ${PROJECT_ROOT}\polygons_and_identifier\geoidentifier_ipcch.csv
output_root = C:\path\to\outputs

[identifiers]
ipc_area_id = area_id
ch_admin_code = admin_code
arcpy_zone_field = fid

[evi]
raw_raster_folder = C:\path\to\EVI\raw_rasters
output_folder = C:\path\to\EVI\output_ch
filename_pattern = MOD13A3_*.tif

[fldas]
part1_folder = C:\path\to\FLDAS\Part1
part2_folder = C:\path\to\FLDAS\Part2
part3_folder = C:\path\to\FLDAS\Part3
part4_folder = C:\path\to\FLDAS\Part4
output_folder = C:\path\to\FEWSNET_predictors\output_ch
max_processes = 4

[ipc_api]
output_folder = ${PROJECT_ROOT}\curl_IPC\outputs
start_year = 2017
end_year = 2026
api_key_env_var = IPCINFO_API_KEY
```

`config/ee_gcs_template.ini` should contain non-secret Earth Engine and Google
Cloud settings such as:

- GCP project name.
- bucket name.
- source-specific bucket prefixes.
- local download destinations.
- export date range.
- small test-export settings.

Minimum section shape:

```ini
[google_cloud]
project = operator-gcp-project
bucket = operator-bucket-name
local_download_root = C:\path\to\downloaded_rasters

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

Configuration rules:

- Relative paths are allowed and should resolve relative to `project_root`.
- Windows backslashes can be written normally in `.ini` files because they are
  read as strings; scripts should not require Python raw-string syntax in config.
- Environment variables are allowed. ArcPy Python 2.x scripts should read config
  with `RawConfigParser`, then apply `os.path.expandvars` and absolute-path
  normalization.
- Secrets and account credentials should not be committed or embedded in
  scripts. `IPCINFO_API_KEY` and any future secret should come from environment
  variables.

## Notebook Conversion Criteria

A notebook requires a `.py` equivalent when it writes a production final or
intermediate CSV/GeoJSON used by another workflow or final harmonise. A notebook
can remain notebook-only when it is inspection, EDA, or a one-off diagnostic
that does not define the production data contract.

Converted scripts should read `.ini` configuration rather than relying on
`os.chdir` and hard-coded local paths. For this light refactor, `.py` scripts do
not need a full CLI if the runbook names the config file and section they use.
Original production notebooks are retained as archived references under
`archive/notebooks/`. Any notebook-generated summaries or plots should be
migrated only if final harmonise or the handover runbook depends on them.

## Data Handover and Large Files

The code handover must distinguish between code/config templates and local data
artifacts. Large or sensitive files should not be assumed to travel through Git
or GitHub.

`docs/04_output_inventory.md` or a companion data manifest must list:

- file path and proposed handover location.
- whether the file is committed, stored in Dropbox/SharePoint, stored in a GCS
  bucket, or transferred through an external drive.
- file size, row count, schema/key fields, and checksum when practical.
- source workflow or generation step.
- how the new operator obtains or regenerates the file.

The manifest must include local reference data that downstream scripts require,
including:

- `polygons_and_identifier/geoidentifier_ipcch.csv`.
- `polygons_and_identifier/gdf_ipc_ch_final.geojson`.
- `polygons_and_identifier/gdf_ipc_ch_final_country_count.csv`.
- `polygons_and_identifier/IPC_scaffold_example.csv`.

## Documentation Design

`docs/00_handover_overview.md` explains the ToR mapping, owners, workflow
families, and what the new operator is expected to run.

`docs/01_environment_setup.md` documents Windows, ArcGIS/ArcPy, Python package,
Google Cloud SDK, and folder prerequisites. It must clearly state that ArcPy
scripts are Python 2.x compatible.

`docs/02_ee_gcs_account_setup.md` documents the new-account checklist for Earth
Engine and Google Cloud. It should include manual validation steps because the
new account does not exist yet.

`docs/03_workflow_runbook.md` gives the ordered commands or manual steps for
EVI, FLDAS, GOSIF-GPP, VIIRS, ACLED, FAO, World Bank, WFP, and final harmonise.

`docs/04_output_inventory.md` lists every workflow's expected input, output,
identifier field, output shape, and downstream final harmonise consumer.

## Error Handling and Validation

Each converted or renamed script should fail early when configured inputs are
missing. The failure message should name the missing file or folder and the
configuration key that supplied it.

For remote-sensing outputs, validation should check:

- output file exists.
- identifier column exists.
- monthly columns are present and sorted or documented.
- row count is plausible against the scaffold or polygon input.
- ArcPy Spatial Analyst license checkout succeeds before extraction.
- raster CRS matches the documented expectation or is explicitly reprojected.
- raster filenames parse into the expected year/month or year/month/band keys.
- date coverage is complete for the configured start and end months.
- identifier values are unique in the output.
- NoData/null rate is summarized and reviewed.
- output column count matches expected months times bands or statistics for that
  workflow, accounting for separate mean/std/sum files.

For tabular workflows, validation should check:

- scaffold input exists.
- required raw file exists.
- expected appended feature column or columns are present.
- output row count still matches the intended scaffold contract unless the
  original logic intentionally filters rows.
- duplicate keys are checked for the intended join key, such as latitude,
  longitude, year, month, `area_id`, or country-year.
- merge diagnostics are produced, including unmatched rate or `_merge`
  distribution where applicable.
- missing-rate summaries are produced for appended features.
- country-code and commodity/market mappings are checked for coverage, especially
  for World Bank, WFP, and FAO workflows.

For final harmonise, validation should check:

- final panel row count.
- unique key integrity.
- required outcome columns exist.
- required critical feature families each contribute at least one column.
- numerical summary output is created or documented.

For Google Cloud download steps, documentation should require a small `gsutil ls`
or `gsutil cp` test before full transfer.

## Implementation Phases

Phase 0: Inventory current workflows and data contracts. Before renaming files,
record current filename, current inputs, current outputs, hard-coded paths,
downstream references, output shape, and production/exploratory status.

Phase 1: Create documentation and configuration templates.

Phase 2: Rename scripts to the ordered step pattern and update documentation
references.

Phase 3: Convert notebooks to `.py` scripts with configuration-based paths while
preserving the current feature logic.

Phase 4: Lightly refactor ArcPy scripts to read paths and identifiers from
configuration while preserving Python 2.x compatibility and current extraction
logic.

Phase 5: Add lightweight validation helpers or documented manual checks for each
workflow output.

Phase 6: Run smoke tests on small samples. Full Earth Engine, Google Cloud, and
ArcPy production runs are not required in this environment, but the handover
should define and, where possible, execute small-sample checks.

## Smoke Test Strategy

Smoke tests should use the smallest data needed to prove schema and path
contracts:

- EVI: one raster month through ArcPy extraction.
- FLDAS: one part folder with a small number of months.
- GOSIF-GPP: one mean file and one standard deviation file.
- VIIRS: one month through mosaic and extraction.
- ACLED, FAO, World Bank, and WFP: small raw samples merged onto a small
  scaffold sample.
- IPC API: one year for areas and analyses, using `IPCINFO_API_KEY` from the
  environment.
- Final harmonise: sample source outputs sufficient to prove join keys, required
  columns, and final schema.

## Acceptance Criteria

- `docs/03_workflow_runbook.md` contains one ordered run section per workflow
  family, with script path, command/manual step, required config section,
  expected inputs, and expected outputs.
- Local user-specific paths are no longer hidden inside the main script body;
  they are either in `.ini` templates or explicitly called out in documentation.
- Earth Engine and Google Cloud handover is documented without pretending the
  new account already exists.
- Notebooks that write production intermediate or final outputs have `.py`
  equivalents; notebooks retained only as exploratory references are listed as
  such.
- FLDAS remains split into part scripts with documented rationale.
- ArcPy scripts remain Python 2.x compatible.
- Remote-sensing final outputs are documented as wide monthly tables keyed by
  `admin_code` or `area_id`.
- ACLED, FAO, World Bank, and WFP workflows are documented as scaffold plus
  appended feature-column outputs.
- `docs/04_output_inventory.md` lists every file read by final harmonise
  notebooks/scripts, including path, required columns, join keys, wide/long
  shape, and source workflow.
- The current-to-proposed migration map covers every production workflow file
  before files are renamed.
- The large-data handover manifest lists required local reference files, storage
  location, row count or schema, and retrieval/regeneration instructions.
- Smoke test instructions exist for each workflow family, including the smallest
  sample input and expected output schema.
