# Workflow Runbook

Every workflow section lists the step order, config sections, expected inputs, and expected outputs. Replace local operator settings in `config/paths.ini` and `config/ee_gcs.ini` before running.

This runbook uses the current handover paths after the rename, conversion, and
config cleanup.

## EVI

Config sections: `[paths]`, `[identifiers]`, `[evi]`.

1. Run Earth Engine Code Editor script: `EVI/00_ee_export_evi.txt`.
2. Download exports with: `EVI/01_gcs_download_evi.txt`.
3. Run ArcPy extraction on Windows: `EVI/02_arcpy_extract_evi.py`.
4. Default template path alignment: downloads land under `EVI/MODIS_MOD13A3_Monthly`, and extraction writes under `EVI/output_ch`.
5. Expected outputs: `EVI_mean_extraction_results.csv` and `EVI_std_extraction_results.csv`.
6. Output shape: wide monthly table keyed by `region_id`.
7. Normalize refreshed wide outputs with `tools/reshape_remote_sensing_wide_to_long.py` before monthly IPCCH assembly.

## FLDAS

Config sections: `[paths]`, `[identifiers]`, `[fldas]`.

1. Run Earth Engine Code Editor script: `FLDAS/00_ee_export_fldas_all_bands.txt`.
2. Download exports with: `FLDAS/01_gcs_download_fldas.txt`.
3. Split or copy downloaded `FLDAS_*_all_bands.tif` files from `FEWSNET_predictors/FLDAS_Monthly` into the configured `Part1` through `Part4` folders.
4. Run the four ArcPy part scripts separately: `02_arcpy_extract_fldas_part1.py` through `02_arcpy_extract_fldas_part4.py`.
5. Expected outputs: part-specific wide monthly-band mean and standard deviation CSVs under `FEWSNET_predictors/output_ch`.
6. FLDAS remains split because local ArcPy processing cannot reliably handle all months in one run.
7. Normalize refreshed wide outputs with `tools/reshape_remote_sensing_wide_to_long.py`; FLDAS columns use `YYYY_MM_Bn` date-band names.

## GOSIF-GPP

Config sections: `[paths]`, `[identifiers]`, `[gosif_gpp]`.

1. Run `GOSIF_GPP/00_download_gosif_gpp_mean.py`.
2. Run `GOSIF_GPP/00_download_gosif_gpp_sd.py`.
3. Run `GOSIF_GPP/01_unzip_gosif_gpp_mean.py`.
4. Run `GOSIF_GPP/01_unzip_gosif_gpp_sd.py`.
5. Run `GOSIF_GPP/02_arcpy_extract_gosif_gpp_mean.py`.
6. Run `GOSIF_GPP/02_arcpy_extract_gosif_gpp_sd.py`.
7. Default template path alignment: unzip writes `.tif` files back into the download folders, those folders are the extraction input folders, and extraction writes final harmonise inputs under `GOSIF_GPP/output_ch`.
8. Expected outputs: `GOSIF_GPP_extraction_results_ch.csv` for mean and `GOSIF_GPP_extraction_results_SD.csv` for standard deviation.
9. Output shape: wide monthly table keyed by `region_id`, with GOSIF month columns like `YYYY.MMM`.
10. Normalize refreshed wide outputs with `tools/reshape_remote_sensing_wide_to_long.py` before monthly IPCCH assembly.

## VIIRS Nightlight

Config sections: `[paths]`, `[identifiers]`, `[viirs]`.

1. Set the target feature month in `VIIRS_nightlight/00_ee_export_viirs_nightlight.txt`. For 2026-04, use `startDate = '2026-04-01'` and exclusive `endDate = '2026-05-01'`.
2. Run Earth Engine Code Editor script: `VIIRS_nightlight/00_ee_export_viirs_nightlight.txt`.
3. Download exports with: `VIIRS_nightlight/01_gcs_download_viirs_nightlight.txt`.
4. Run `VIIRS_nightlight/02_arcpy_mosaic_viirs_nightlight.py`.
5. Run `VIIRS_nightlight/03_arcpy_extract_viirs_nightlight.py`.
6. Default template path alignment: downloads land under `DMSP_OLS/image/nightlight`, mosaics are written under `DMSP_OLS/image/nightlight_mosaic`, and extraction writes under `DMSP_OLS/output_ch`. `DMSP_OLS` is a legacy folder name; the production source is VIIRS.
7. Expected outputs: `nightlight_sum_extraction_results.csv` and `nightlight_std_extraction_results.csv`.
8. Output shape: wide monthly table keyed by `region_id`; production updates usually add one target feature month.
9. Normalize refreshed wide outputs with `tools/reshape_remote_sensing_wide_to_long.py` before monthly IPCCH assembly.

## Tabular Feature Workflows

Config sections: `[paths]`, `[production]`, `[tabular]`.

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

| Script | Required config inputs | Config output |
| --- | --- | --- |
| `ACLED/00_add_acled_features.py` | `acled_raw_file`, `acled_scaffold_file` | `acled_output_file` |
| `FAO_price/00_add_fao_price_features.py` | `fao_raw_file_1`, `fao_raw_file_2`, `fao_scaffold_file` | `fao_output_file`, plus `fao_legacy_output_file` if needed |
| `WB_indicator/00_add_world_bank_features.py` | `wb_cpi_file`, `wb_gdp_file`, `wb_cc_percentile_file`, `wb_scaffold_file`, `wb_pip_file`, `wb_esa_completed_file`, `wb_country_lookup_file` | `wb_output_file` |
| `WFP_indicator/00_add_wfp_price_features.py` | `wfp_raw_file`, `wfp_scaffold_file`, `wfp_esa_lookup_file` | `wfp_output_file` |

Each output should preserve scaffold rows unless the source workflow documents a deliberate filter.
Before running, set the corresponding `[tabular]` file entries in
`config/paths.ini`. The ACLED, FAO, WFP, and WB scripts now read their raw
inputs, scaffold/reference files, and outputs from config rather than requiring
operators to rename files to legacy notebook filenames.

Operational notes:

- ACLED: download event-level rows for `Political violence` with event types
  `Battles`, `Explosions/Remote violence`, and `Violence against civilians`.
  Do not include `Protests` or `Riots`; the current script does not generate
  protest-specific features. See `docs/08_sediqa_raw_data_download_notes.md`
  and the archived example under `archive/example_raw_inputs/ACLED/`.
- WFP: the current script keeps the scaffold, reads `Commodity`, then drops it
  before aggregating prices by country/month. The raw export must therefore be
  pre-filtered to ALPS-compatible commodities before the script runs. Download
  from WFP Analysis Builder and keep the `Trend` column. See
  `docs/08_sediqa_raw_data_download_notes.md` and the archived example under
  `archive/example_raw_inputs/WFP/`.
- FAO: workbook exports can vary. If the refreshed file does not match the
  expected FAO script columns, normalize the workbook first or adjust
  `FAO_price/00_add_fao_price_features.py` for that export. The handover
  example is
  `C:\Users\swl00\IFPRI Dropbox\Weilun Shi\Google fund\Analysis\1.Source Data\FAO\GOOGLE_FOOD_CRISIS_FAO_DATA.xlsx`.
- Bloomberg: optional for the current handover and can be supplied or adapted
  by Soonho outside this repo's required monthly base-input contract.
- Ownership: Soonho/Sediqa download raw data and run the pipeline; Weilun
  validates the monthly model-compatible input and QA summaries before release.
- Archive convention: existing historical raw inputs are accepted as
  `validated_on=2026-06-22`. Future refreshes should use date-stamped raw
  exports or folders and record source name, download date, operator, row
  count, filters applied, and the file consumed by the pipeline.

Archived notebook references for converted tabular and final harmonise workflows
are listed in `archive/notebooks/MANIFEST.md`.

## IPC API

Config sections: `[ipc_api]` and environment variable named by
`api_key_env_var`, currently `IPCINFO_API_KEY`.

Create `config/paths.ini` from `config/paths_template.ini`, confirm its `[ipc_api]`
settings, and set `IPCINFO_API_KEY` before running:

```bash
IPCINFO_API_KEY='<operator-key>' python3 curl_IPC/00_download_ipc_api.py
```

Expected outputs are per-year files and combined areas/analyses files under `curl_IPC/outputs/`.

## Final Monthly IPCCH Assembly

Config sections: `[paths]`, `[production]`, `[schema]`.

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

### Operational launch inference

Use this only after the fixed model package has been exported from the research
IPCCH repository and copied into `model_artifacts/launch_2026_04`.

Run `--validate-only` first:

```bash
python3 model_pipeline/run_operational_launch_inference.py \
  --input Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_YYYYMM.csv \
  --model-package model_artifacts/launch_2026_04 \
  --spatial-path Outcome/ipcch_unified/spatial/ipcch_admin_geometry.shp \
  --output-dir Outcome/ipcch_unified/predictions/YYYYMM \
  --feature-month YYYY-MM \
  --validate-only
```

Then run without `--validate-only` to generate the six primary delivery files.

Legacy split CH/IPC final harmonise scripts are archived under
`archive/legacy_final_harmonise/`. They are compatibility references, not the
production monthly IPCCH input path.

## Smoke Tests

Run these before a full monthly update. For tabular workflows, stage fixtures
at the paths configured in `config/paths.ini`; some scripts still expect
auxiliary reference files configured under `[tabular]`.

| Workflow | Small input | Expected check |
| --- | --- | --- |
| EVI | One MOD13A3 raster month | Mean/std CSVs exist and include `region_id` plus one month column; `tools/reshape_remote_sensing_wide_to_long.py` converts the wide output to `area_id`, `year`, `month`, `EVI_mean` or `EVI_std`. |
| FLDAS | One part folder with a small month subset | Part-specific mean/std CSVs exist and include `region_id` plus band columns; reshape smoke test handles `YYYY_MM_Bn` columns. |
| GOSIF-GPP | One mean file and one SD file | Wide CSVs exist and include `region_id` plus source month column; reshape smoke test handles GOSIF `YYYY.MMM` columns. |
| VIIRS | One month of exported tiles | Mosaic exists, then sum/std CSVs exist; reshape smoke test converts the target month into `area_id`, `year`, `month`, and nightlight feature columns. |
| ACLED | Small scaffold and raw ACLED sample staged at the expected configured paths | Output row count matches scaffold unless documented otherwise. |
| FAO | Small scaffold and FAO workbook sample staged with required auxiliary references | Output contains appended FAO feature columns. |
| World Bank | Small scaffold and WBG indicator sample staged with required country/year references | Output contains expected country-year features. |
| WFP | Small scaffold and WFP price sample staged at the expected configured paths | Output contains appended WFP feature columns. |
| IPC API | One year | Per-year areas/analyses files and combined files are written. |
| Final monthly IPCCH assembly | One-month scaffold plus fixed/slow fixture and a small historical-panel slice | Unified monthly base input has one row per `area_id`, `year`, `month`; summary JSON reports join coverage and missingness. |

Example remote-sensing normalization command:

```bash
python3 tools/reshape_remote_sensing_wide_to_long.py \
  --input-csv path/to/EVI_mean_extraction_results.csv \
  --output-csv path/to/EVI_mean_monthly_long.csv \
  --feature-name EVI_mean
```

Add `--mapping-csv path/to/region_to_area.csv` when ArcPy `region_id` differs
from the current `area_id`.
