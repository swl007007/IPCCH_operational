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

Out of scope:

- Rewriting the full pipeline as a production CLI.
- Changing the underlying feature engineering logic.
- Combining FLDAS parts into a single large extraction run.
- Running Earth Engine exports, Google Cloud downloads, or ArcPy extraction in
  this environment.

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

`config/ee_gcs_template.ini` should contain non-secret Earth Engine and Google
Cloud settings such as:

- GCP project name.
- bucket name.
- source-specific bucket prefixes.
- local download destinations.
- export date range.
- small test-export settings.

Secrets and account credentials should not be committed or embedded in scripts.

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

For tabular workflows, validation should check:

- scaffold input exists.
- required raw file exists.
- expected appended feature column or columns are present.
- output row count still matches the intended scaffold contract unless the
  original logic intentionally filters rows.

For Google Cloud download steps, documentation should require a small `gsutil ls`
or `gsutil cp` test before full transfer.

## Implementation Phases

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

## Acceptance Criteria

- A new operator can identify which script to run for each ToR workflow and in
  what order.
- Local user-specific paths are no longer hidden inside the main script body;
  they are either in `.ini` templates or explicitly called out in documentation.
- Earth Engine and Google Cloud handover is documented without pretending the
  new account already exists.
- Notebooks that perform production workflow steps have `.py` equivalents unless
  a notebook is intentionally retained as an exploratory reference.
- FLDAS remains split into part scripts with documented rationale.
- ArcPy scripts remain Python 2.x compatible.
- Remote-sensing final outputs are documented as wide monthly tables keyed by
  `admin_code` or `area_id`.
- ACLED, FAO, World Bank, and WFP workflows are documented as scaffold plus
  appended feature-column outputs.
- Final harmonise expectations are reflected in the output inventory.

