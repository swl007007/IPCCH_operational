# Planned keep/move/archive map

This is the approved-scope planning map; enumerate exact files and collision-free destinations immediately before execution. Do not run directory moves solely from name matching.

| Current path | Planned destination / rule |
|---|---|
| Outcome/manual_delivery/202609_h5/20260923_country_confidence_v3 | september_manual; accepted content bytes retained |
| Outcome/model_delivery/october_cloud_delivery/oct-final-20261008a | cloud_pipeline/fallback/october_2026; no rescore |
| Outcome/migration_packages/october_cloud_delivery/assets, models | cloud_pipeline/bootstrap; preserve one required baseline copy |
| Other current migration package source/reference/metadata | use needed descriptors/evidence; superseded packaging copies/archives go to external legacy archive; generate new closed handover under cloud_pipeline/dist |
| cloud, fewsnet_partitioned_rf_pipeline, model_pipeline, tools | move supported cloud/model/converter dependency closure to cloud_pipeline; archive unrelated old CLIs/training/debug paths with their files |
| deploy/october_delivery | cloud_pipeline/deploy; replace hidden-source operations with unified public CLI and correct build paths |
| tests | retain supported cloud/model/converter/CLI tests and fixtures under cloud_pipeline/tests; archive legacy-only tests with old workflow dependencies |
| ACLED, EVI, FAO_price, FLDAS, GOSIF_GPP, VIIRS_nightlight, WB_indicator, WFP_indicator, curl_IPC, polygons_and_identifier | external legacy_archive preserving original paths, once supported closure no longer reads them |
| Outcome/ipcch_unified, Outcome/fewsnet_partitioned_rf, model_artifacts, archive | external archive; required frozen operational assets already staged/verified in new bootstrap |
| Final_harmonise, config, workflow_config.py, docker, old requirements files | external archive after checking active dynamic imports/tests; preserve needed behavior inside supported closure first |
| Old docs/specs, implementation-delta.md, structured_TOR_from_variable_note.xlsx | external archive except current development controls or needed contracts; operator docs rewritten into two entrypoints |
| Root README, LICENSE, .gitignore, .gitattributes, .dockerignore | keep/update navigation and tooling; no separate operator workflow |
| .git, .trellis, agent controls, AGENTS.md, CLAUDE.md, PROGRESS.md and active hidden metadata | keep in place; not included in operational handover and not required by it; preserve unrelated dirty content |
| caches / desktop.ini / empty stale folders | archive only when inactive and outside retained developer controls; no user-data deletion |

Archive root: ../legacy_archive/IPCCH_monthly_operational/<cleanup-id>/. Do not overwrite any existing destination. Record original-relative-path -> destination, tracked/ignored status and verification result. Recheck worktrees and relevant active filesystem users before any control-adjacent move. Do not change remote repo or push without task scope.
