# Weilun Deliverable Gap Audit

Audited on: 2026-06-22

Scope: this audit separates Weilun-owned deliverable blockers from delegated
operational risks. `IPCCH` is treated as one unified production input/output
contract. Legacy `IPC` and `CH` names are compatibility artifacts unless a
downstream consumer explicitly asks for split exports.

The repo's intended product is a monthly model-compatible IPCCH input table.
Model prediction itself is downstream and remains dependent on later exported
model weights, model pipeline, and model-specific feature engineering.

## Audit Evidence

Sources checked:

- `structured_TOR_from_variable_note.xlsx`, especially `Deliverables` and
  `Open Issues & Risks`.
- `docs/00_handover_overview.md` through `docs/05_weilun_handover_gap_list.md`.
- `docs/07_handover_email_archive.md` for the requested team-repo and
  SharePoint handover schedule.
- `docs/08_sediqa_raw_data_download_notes.md` and
  `archive/example_raw_inputs/` for compatible ACLED and WFP raw export
  examples.
- `config/paths_template.ini` `[handover]` section for final code repo,
  SharePoint URL/local sync folder, and local-only exclusion list.
- `Outcome/ipcch_unified/` assets, manifests, schema files, and model-input
  smoke output.
- Converted scripts under source workflow folders and `tools/`.
- `git status --short`.

Validation commands run:

```bash
python3 -m unittest discover -s tests -v
python3 tools/validate_ipcch_schema.py --mode forecast-scaffold --csv Outcome/ipcch_unified/interim/ipcch_scaffold_202604.csv
python3 tools/validate_ipcch_schema.py --mode fixed-slow-area --csv Outcome/ipcch_unified/features/ipcch_fixed_slow_features_by_area.csv
python3 tools/validate_ipcch_schema.py --mode model-input-forecast --csv Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604.csv
python3 tools/validate_ipcch_schema.py --mode historical-panel --csv Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv
python3 -m py_compile ACLED/00_add_acled_features.py FAO_price/00_add_fao_price_features.py WB_indicator/00_add_world_bank_features.py WFP_indicator/00_add_wfp_price_features.py Final_harmonise/00_build_monthly_ipcch_base_input.py workflow_config.py tools/validate_ipcch_schema.py tools/build_monthly_ipcch_scaffold.py tools/build_ipcch_fixed_slow_features.py tools/build_ipcch_schema_contract.py tools/build_ipcch_source_vintage_manifest.py tools/reshape_remote_sensing_wide_to_long.py curl_IPC/00_download_ipc_api.py
```

Observed validation results:

- Unit tests: 11 passed.
- Historical panel: `PASS`, 1,219,868 rows, 143 columns, 2010-01 through
  2026-04.
- One-month scaffold: `PASS`, 6,227 rows, 5 columns, 2026-04.
- Fixed/slow area asset: `PASS`, 6,227 rows, 48 columns.
- G-09 monthly base input: `PASS`, 6,227 rows, 148 columns, 2026-04.
- Syntax check passed for non-ArcPy scripts and converted tabular scripts.

## Weilun Deliverable Status

| ToR deliverable | Current status | Evidence | Remaining gap |
| --- | --- | --- | --- |
| D-01 Geoidentifier schema | Complete | `Outcome/ipcch_unified/schema/ipcch_model_input_contract.md`, `ipcch_base_panel_schema.csv`, validator pass for historical panel and scaffold; `structured_TOR_from_variable_note.xlsx` now records the evidence path. | No current Weilun-side gap. |
| D-02 Geoidentifier-polygon link file | Complete as local handover asset | `Outcome/ipcch_unified/spatial/ipcch_admin_geometry.*`, `unique_area_id_lat_lon.csv`, `country_area_id_lookup.csv`, `Outcome/ipcch_unified/MANIFEST.md`. | Large geometry is ignored by Git; final handover channel must include the team repo for code and MS Teams/SharePoint for data assets. |
| D-03 Fixed and slow-moving variable inputs | Complete for currently identified fixed/slow variables | `ipcch_fixed_slow_features_by_area.csv`, `ipcch_fixed_slow_features_summary.csv`, `ipcch_fixed_slow_source_vintage_manifest.csv`. | `coastline_dist` has been added from the coastline-distance source and has complete coverage for 6,227 areas. |
| D-10 Processing templates | Complete for this repo scope | Refactored workflow scripts, archived notebooks, validators, config templates, `Final_harmonise/00_build_monthly_ipcch_base_input.py`, `tests/test_tabular_config_paths.py`, and `tools/reshape_remote_sensing_wide_to_long.py`. | No current Weilun-side gap for producing monthly model-compatible input. Prediction artifacts and model-specific transformations belong to the downstream prediction pipeline with D-11/G-06/G-07. |
| D-11 Model assets | Deferred by decision | `docs/05_weilun_handover_gap_list.md` records G-06/G-07 as deferred. | Later export model weights, model pipeline, model-specific feature engineering, version labels, and compatibility notes. |

## Weilun Blockers / Gaps

| ID | Severity | Owner | Status | Evidence | Why it matters | Proposed next action |
| --- | --- | --- | --- | --- | --- | --- |
| WDG-01 | High | Weilun | Open for final handover packaging | This local repo is currently experimental/private. The requested final code handover is to merge runnable monthly-model code into the IFPRI private repo `https://github.com/IFPRI/MTI-GOOGLE-FOOD-CRISIS-MODEL.git` on `main`, with a detailed README. The requested data/documentation handover is to MS Teams/SharePoint: `https://cgiar.sharepoint.com/:f:/r/sites/IFPRI-MTI-foodcrisis/Shared%20Documents/1.%20Modeling?csf=1&web=1&e=G4fpyi`, locally synced at `C:\Users\swl00\CGIAR\IFPRI-MTI-foodcrisis - 1. Modeling`. See `docs/07_handover_email_archive.md` and `config/paths_template.ini` `[handover]`. | `git status --short` is not itself a local blocker because this repo is a staging workspace. Local-only agent/runtime files such as `AGENTS.md`, `CLAUDE.md`, `.agents/`, `.claude/`, `.codex/`, `docs/superpowers/`, `__pycache__/`, and `*.pyc` are explicitly excluded from final handover. | Prepare a clean final delivery package: code/docs/config templates/README for the IFPRI team repo, and data tables plus step-by-step collection documentation for SharePoint. Do not rely on this experimental working tree state as the final deliverable. |
| WDG-02 | Resolved | Weilun | Closed on 2026-06-22 | `coastline_dist` now appears in `ipcch_fixed_slow_features_by_area.csv`, `ipcch_fixed_slow_features_summary.csv`, `ipcch_fixed_slow_source_vintage_manifest.csv`, and schema validation. Source is `1.Source Data/Coastline_distance_NOAA/IPCCH_2026_price_completed_unique_lat_lon_coastline_dist.csv`, SHA-256 `a7e5b13c027c7c9b0ab5ee51930842de9f64f49daac5973283e60c5ddcf4d5be`. | D-03 now covers the ToR/codebook coastline-distance variable. | No immediate action. Rebuild with `python3 tools/build_ipcch_fixed_slow_features.py` if the coastline source changes. |
| WDG-03 | Resolved by scope decision | Weilun + downstream prediction pipeline owner | Closed on 2026-06-22 | The repo's final product is the monthly model-compatible IPCCH input table. Prediction artifacts are produced later by a downstream prediction pipeline that consumes the monthly input plus exported model weights and model pipeline. `Final_harmonise/00_build_monthly_ipcch_base_input.py`, WDG-06 config-driven tabular scripts, and WDG-07 remote-sensing reshape smoke tests cover this repo's input-production boundary. | This prevents the handover repo from being judged against prediction-pipeline responsibilities that require model weights and model-specific feature engineering. | No action in this repo. When D-11/G-06/G-07 assets are exported, implement prediction artifact generation in the downstream model prediction pipeline. |
| WDG-04 | Resolved | Weilun | Closed on 2026-06-22 | `archive/notebooks/MANIFEST.md` now separates active converted tabular workflows from legacy final harmonise references. The legacy split CH/IPC scripts are listed under `archive/legacy_final_harmonise/`, and production users are pointed to `Final_harmonise/00_build_monthly_ipcch_base_input.py`. | New operators should no longer be directed from the notebook archive to the old split CH/IPC final harmonise path. | No immediate action. Keep legacy final harmonise scripts archived unless a downstream compatibility requirement is confirmed. |
| WDG-05 | Resolved | Weilun | Closed on 2026-06-22 | `structured_TOR_from_variable_note.xlsx` now records evidence paths for D-01/D-02/D-03/D-10, defers D-11/model assets, reclassifies OI-01 through OI-10, and clarifies the unified one-month IPCCH production target. | The workbook is now consistent with the repo docs: resolved/delegated/deferred items no longer appear as unqualified open issues. | No immediate action. Refresh only if final packaging or deferred model-asset decisions change. |
| WDG-06 | Resolved | Weilun | Closed on 2026-06-22 | `ACLED/00_add_acled_features.py`, `FAO_price/00_add_fao_price_features.py`, `WB_indicator/00_add_world_bank_features.py`, and `WFP_indicator/00_add_wfp_price_features.py` now read raw inputs, scaffold/reference files, and outputs from `[tabular]` config keys in `config/paths_template.ini`. `tests/test_tabular_config_paths.py` prevents reintroducing the legacy fixed filenames. | Operators can point scripts at refreshed source exports without editing Python files. Missing configured inputs fail early through `require_file`. | No immediate action. Source-format issues still follow the operational notes: WFP raw export must be ALPS-compatible, and FAO/Bloomberg variations remain delegated/optional as documented. |
| WDG-07 | Resolved | Weilun + Sediqa | Closed on 2026-06-22 | Added `tools/reshape_remote_sensing_wide_to_long.py` and `tests/test_reshape_remote_sensing_wide_to_long.py`. The fixture test maps `region_id` to `area_id`, handles `YYYY_MM` EVI/VIIRS columns, GOSIF `YYYY.MMM` columns, and FLDAS `YYYY_MM_Bn` band columns. | A fresh ArcPy wide extraction output now has a tested path into `area_id`, `year`, `month` keyed monthly rows. | No immediate action. If FLDAS band numbers need final model feature names, include that mapping in downstream model-specific feature engineering. |
| WDG-08 | Deferred | Weilun | Accepted deferred | G-06 and G-07 in `docs/05_weilun_handover_gap_list.md`; model input contract says model-ready files under source `assembled_IPCCH/model_ready` are references only. | Prediction cannot run until model weights, pipeline, and model-specific feature engineering are exported. | Later create a versioned model asset package with expected input columns, feature ordering, preprocessing pipeline, weights, and compatibility date. |

## Covered / Not A Current Weilun Gap

| Item | Status | Evidence / note |
| --- | --- | --- |
| 53-country scope | Covered | `polygons_and_identifier/country_scope_ipcch_2026.csv`, 53 rows, unique `ISO3`. |
| Core unified IPCCH raw panel | Covered as local handover asset | `Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv`, validator pass, 2010-01 through 2026-04. Ignored by Git because it is large; it belongs in the SharePoint/MS Teams data handover package. |
| One-month scaffold rule | Covered | `Outcome/ipcch_unified/interim/ipcch_scaffold_202604.csv`; `tools/build_monthly_ipcch_scaffold.py`; docs state production needs one target month only. |
| Political/admin identifiers | Mostly covered | `ipcch_fixed_slow_features_by_area.csv` includes `area_id`, `admin_code`, `ISO3`, `country`, `country_code`, `country_en`, and `state`. Reopen only if "political identifiers" means extra covariates beyond these fields. |
| Fixed/slow source/vintage evidence | Covered for current G-03 families | `Outcome/ipcch_unified/metadata/ipcch_fixed_slow_source_vintage_manifest.csv` covers AEZ, ASAP land cover, river distance, terrain, ISRIC SoilGrids, market access, population context, and coastline distance. |
| Nightlight coverage decision | Covered | Use VIIRS as production source; DMSP_OLS is legacy folder naming. G-08 documents raw panel coverage through 2026-04 and VIIRS target-month export settings. |
| IPC API workflow inclusion | Covered | `curl_IPC/00_download_ipc_api.py`, `docs/03_workflow_runbook.md`, and `config/paths_template.ini` include IPC API settings. |
| ArcPy Python 2.x syntax rule | Covered in docs | `docs/01_environment_setup.md` says ArcPy scripts must preserve Python 2.x-compatible syntax. |

## Delegated / Non-Weilun Operational Risks

These should stay visible in handover, but they are not Weilun blockers unless
the team asks Weilun to own the operational run.

| ID | Severity | Owner | Status | Evidence | Required handover instruction |
| --- | --- | --- | --- | --- | --- |
| OPR-01 | High | Sediqa / Google account owner | Not yet executed | `docs/02_ee_gcs_account_setup.md`; `config/ee_gcs_template.ini`; EE scripts use placeholder `operator-bucket-name`. | Create/authorize the new Earth Engine/GCP account, grant bucket permissions, run a small test export, then replace placeholders in local `config/ee_gcs.ini` and EE scripts. |
| OPR-02 | High | Sediqa | Runtime dependency | ArcPy extraction scripts require Windows ArcGIS Python and Spatial Analyst. | Confirm ArcPy and Spatial Analyst license on the operator machine before running raster extraction. Keep ArcPy scripts Python 2.x-compatible. |
| OPR-03 | Medium | Sediqa | Resolved by operator rule | WFP script drops `Commodity` before aggregation; docs now say raw export must be pre-filtered to ALPS-compatible commodities. | Download/stage only ALPS-compatible WFP commodities before running `WFP_indicator/00_add_wfp_price_features.py`. |
| OPR-04 | Medium | Soonho / Sediqa | Delegated | FAO workbook formats vary; Bloomberg is optional and Soonho-supported. | Normalize FAO exports or adjust the FAO script per refresh. Include Bloomberg only if the later model feature set requires it. |
| OPR-05 | Medium | Soonho / Sediqa / Weilun validates | Partially documented | `docs/03_workflow_runbook.md` and `docs/04_output_inventory.md` now state Soonho/Sediqa run/download and Weilun validates. | Convert this into a monthly release checklist if routine production starts. |
| OPR-06 | Medium | All leads | Historical limitation accepted | Existing raw source folders do not have detailed archive manifests. | Treat historical raw assets as `validated_on=2026-06-22`; future raw refreshes should be date-stamped and record source, operator, row count, filters, and consumed file. |
| OPR-07 | Medium | Sediqa | Needs runtime discipline | EVI and FLDAS EE scripts still use historical batch date windows; VIIRS is target-month oriented. | For routine monthly runs, set each EE export window to the target feature month or document when historical backfill is intentional. |

## Recommended Resolution Order

1. Close WDG-01 by preparing the final team-repo code package and SharePoint
   data/documentation package, instead of treating this local experimental repo
   as the final delivery target.
2. Keep WDG-08 deferred until model weights, model pipeline, and
   model-specific feature engineering are exported.
