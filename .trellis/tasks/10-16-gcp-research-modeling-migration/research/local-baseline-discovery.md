# Local baseline discovery before cloud migration

Evidence was inspected read-only in this conversation on 2026-10-15/16. This file records findings, not a baseline selection or cloud verification. Large input/weight hashes below were read from existing manifests unless explicitly stated otherwise.

## Shared MLflow

- Database: `/home/swl007007/.local/share/ipcch-mlflow/mlflow.db`; queried through SQLite `mode=ro`, `query_only=ON` and read transactions. No auth or gateway-secret tables were inspected.
- Current inventory: 196 registered names, 242 model versions and 242 logged models. Registered project tags: IPCCH 84 names / 116 versions, IPCCH forecasting 112 names / 126 versions. No registered-model aliases.
- FEWS searches across names/tags and relevant source metadata returned no matches. Do not infer FEWS absence from the whole filesystem: local FEWS runs exist outside this registry.
- All logged models have `mlflow.model.isExternal=true`. Training/evaluation dataset descriptors and their digests do not themselves store all model weights or full training matrices.
- Some historical weight archives were intentionally removed. The relevant live policy is in `Food_Crisis_Cluster/IPCCHMLflow/README.md:21-44` and its `AGENTS.md:60-97`, under the research root below.
- Source lookup root: `/mnt/c/users/swl00/ifpri dropbox/weilun shi/google fund/analysis/2.source_code/step5_geo_rf_trial`.
- Family declarations: `Food_Crisis_Cluster/IPCCHMLflow/sources.json`, `Food_Crisis_Cluster/IPCCHMLflow/model_cards.json`, `IPCCH/IPCCHMLflow/sources.json`. These have historical families and multiple input variants; registration order is not fit order or baseline preference.
- Existing assistant evidence: `Food_Crisis_Cluster/IPCCHMLflow/README.md:96-116` documents a Gemini/Vertex AI Gateway assistant billed to the old `manuel-remote-sensing` project. It uses the read-only `assistant` identity and a version-specific MLflow 3.17 patch restricting commands. The new project's assistant/provider availability and cloud compatibility have not been checked. No gateway credentials or secret values were read.

## IPCCH shared input evidence

- Data root: `/mnt/c/users/swl00/ifpri dropbox/weilun shi/google fund/analysis/1.Source Data`.
- `Food_Crisis_Cluster/IPCCHGeoXGBExperiment/config/inputs.json:10-15` binds `assembled_IPCCH/raw/IPCCH_2026_completed.csv`, 1,782,567,753 bytes, recorded SHA256 `ae696087c3bbb280537ae269a05924133acdb51060d31290523404fa8a717673`.
- `Food_Crisis_Cluster/IPCCHAlphaEarthExperiment/config/inputs.json:9-36` binds the same raw panel plus interim inputs, monthly/seasonal climate and IDP data. Additional AlphaEarth descriptors are part of that family. The raw panel alone does not reproduce every registered family's inputs.
- `Food_Crisis_Cluster/IPCCHMLflow/model_cards.json:70-85` describes the rich561 reference recipe, cumulative phase-share targets and forecast-origin restrictions. Other forecasting families include compact296, origin-safe and realized-future-weather/oracle configurations; keep their target and availability definitions distinct.

## FEWS NET research candidate

- Run: `/mnt/c/Users/swl00/geoxgb_runs/scen-b43ef6a-v1`.
- Completion evidence: `Food_Crisis_Cluster/.trellis/tasks/archive/2026-10/10-02-exogenous-transition-forecast-design/PROGRESS.md:631-648`; `scen-actual` completed 2026-10-03 21:09, with exactly H4/H8 x June/October 2025, four actual cases. Later evaluation did not refit models.
- `/mnt/c/Users/swl00/geoxgb_runs/scen-b43ef6a-v1/prepared/manifests/sources.json:3-39` binds:
  - `FEWSNET_forecast_unadjusted_bm.csv`: 716,303,754 bytes; SHA256 `611f9e776380e28da3fc845888d66a117626f91b37868e236ce849d44bc8f651`.
  - `Outcome/FEWSNET_IPC/FEWSNET.csv`: 51,422,500 bytes; SHA256 `8fdd4cca6f6ba26b84efc209c8eb36492e1257d51e24edd2c2ad4962df7b38d0`.
  - Coordinate CSV and `FEWS_Admin_LZ_v3` shapefile/sidecars.
- `/mnt/c/Users/swl00/geoxgb_runs/scen-b43ef6a-v1.actual-inputs-v1/extension_manifest.v2.json:2-31` binds the additional `covariate_extension_2024-12_2025-06.csv`, SHA256 `0d6b78ca2fda21f73b8bfaeb6b916dd72fcb250f020fbea7be54299be9038b05`. It combines a pinned overlap month and 2025 combined-panel rows; source data is revised/latest, not verified historical real-time vintages.
- At least the global H4/H8 UBJ models are present. Complete availability of all regional models has not been established; do not promise full model portability yet.
- This was the latest run with explicit fit-completion evidence among the inspected candidates, not proof of global latest/unique accepted baseline across all workspaces.

## FEWS NET operational package alternative

- Repository-local manifests: `cloud_pipeline/bootstrap/models/fewsnet/{0m,6m,12m}/local_model_manifest.json`.
- Suite: `local-202604-57cb3b981198-510375f58cd8`; retained model files and metadata exist for all three scopes.
- `0m/local_model_manifest.json:33-38` binds `assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.csv`, 1,120,728 rows, 773,553,094 bytes, SHA256 `510375f58cd835e694b6e287cce9439bbe1b6246d752daabc8151df8ffdda61d`.
- October delivery `oct-confidence-20261009b` reused unchanged model packages. `feature_month=2026-04` and delivery timestamps are not fitting timestamps. Reports distinguish fit data through 2023-06 from validation through 2026-02.
- This deployment source differs from the research source. D9 selects GeoXGB research inputs as the default; operational inputs remain historical evidence rather than the active baseline.

## Migration implications and recorded decisions

- Two dataset entry points can each comprise a main panel, spatial references and required supplemental inputs. They do not imply every historical model used one identical CSV.
- D1 includes all retained-weight research versions; D9 selects FEWS NET research inputs and D10 selects IPCCH base data plus per-experiment features. Inventory the concrete versions/dependencies before calculating capacity or promising portability.
- Preserve source model/data identity during migration; a retrained replacement is a new model, not recovery of missing historical weights.
- Verify the selected workflow in cloud/native WSL without Dropbox path access before declaring the cloud-only archival cutover ready.
- No target-project permissions, enabled APIs, resources, costs, network paths or cloud authentication have been checked yet.

## IPCCH input-layer clarification (2026-10-16)

- `Food_Crisis_Cluster/IPCCHGeoXGBExperiment/config/inputs.json:10-15` assigns the shared raw panel the roles of population targets and original93 covariates; lines 17-99 bind identity, geometry and adjacency assets. The common raw panel alone is not the rich561 feature matrix.
- `Food_Crisis_Cluster/IPCCHAlphaEarthExperiment/config/inputs.json:9-37` uses the same raw-panel hash for population-derived truth and target-key coordinates, but obtains ordinary predictors and reported-phase histories from a separate interim table, with separate monthly/seasonal climate and IDP inputs. Lines 45-73 also require existing compact tables for static features and overlap checks. Do not assume every feature recipe can be rebuilt from the raw panel alone.
- `Food_Crisis_Cluster/IPCCHMLflow/model_cards.json:76-94` describes rich561 as original93 plus 468 history features. Lines 13-25 describe the AlphaEarth family's compact296 recipe, with the retained 128-column embedding descriptors used by its additional arms. These are different recipes and dependency sets, not interchangeable versions of one flat table.
- `Food_Crisis_Cluster/IPCCHMLflow/model_cards.json:117-139` distinguishes origin-safe compact inputs from realized-future-weather oracle additions. A common cloud input catalog must preserve this distinction and the original target definitions.
- The workspace AGENTS reference to `specs/001-cloud-base-input/plan.md` could not be read at that path (file not found). It was not used as current migration design evidence.
