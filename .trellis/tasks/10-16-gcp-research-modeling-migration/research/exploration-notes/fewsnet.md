# FEWS NET GeoXGB research runs: catalog rules + inference-package contract (P1 draft)

Read-only research, 2026-10-16. Source clone: sources/Food_Crisis_Cluster @ 6c1ebf72 (paths below relative to
FEWSNETGeoXGBExperiment/ unless stated). Run root: /mnt/c/Users/swl00/geoxgb_runs.

## 1. Layout of a completed scenario run (scen-b43ef6a-v1)
Top level: prepared/ (snapshot_h{4,8,12}.parquet, manifests/{alignment,features,geometry,identity}.json,
ledgers/, geometry/, scenario/), stage1_scenario/ (candidates/ 648, checkpoints/<cand>/xgb_<branch>.{ubj,json},
roots/, ledger.jsonl), scenario_maps/<map_id>/ (14 maps; consensus.json, candidate_ledger.csv, plan_weights.csv,
experiment/knn_sparsification_results/cluster_mapping_k40_nc17_general.csv + cluster_mapping_manifest.json,
experiment/linked_tables/partitions/*.csv), scenario_globals/h{H}/{G}/O<origin>[_<digest16>].{ubj,json}
(h4/G1 360 files, h8/G4 322 files; path rule stage3.py:242-244,262-264), scenario_development/{A,B}/h{H}/k{0,1,2}/<target>/
+ selection.json, scenario_final/frozen.json, scenario_historical/A/h{H}/... + historical.json,
scenario_actual/h{4,8}/{2025-06,2025-10}/ + actual.json, scenario_evaluation/evaluation.json, scenario_report/report.json.
No H12 in the scenario phases (frozen recipe only has "4","8").
Fold dir contents: fold.json, gate.json, gate_pairs.csv.gz, predictions.csv.gz, pooled_predictions.csv.gz;
`models/*.ubj` only when keep_boosters (run_experiment.py:368-389). scen-b43ef6a-v1 has ZERO .ubj outside
scenario_globals and stage1_scenario/checkpoints => local/regional boosters of scenario_actual were NOT persisted.
Completion markers: each phase record written by finish() (run_experiment.py:103) with code/runtime/outputs sha;
frozen.json (run_experiment.py:836), actual.json (912), fold.json status "fitted" + outputs sha; external evidence
PROGRESS.md:631-648 (actual.json sha c896a583..., 4 cases x 5,718 rows).

## 2. Catalog rules (geoxgb_runs, 193 entries)
- Scenario run (model-bearing candidate): dir `scen-*` with scenario_final/frozen.json AND scenario_actual/actual.json.
  -> scen-b43ef6a-v1 only.
- Sibling evidence of a run: `<run>.*` files/dirs (logs *.log/*.nohup.log, *.pid, *.ledger.jsonl, *_review.{py,json},
  reconcile.json, stage1_acceptance.json, .failed_stage1* (aborted stage1 checkpoints, 264 ubj - exclude),
  .truth-release-v{1,2}, .actual-inputs-v1). Attach as provenance, never register.
- Development pipeline runs `geoxgb-v1-20261001`, `geoxgb-d26-20261001` (prepared/stage1/gscreen[/globals]): research
  stage1 only, no frozen recipe -> diagnostic, not inference.
- Decision-experiment dirs `geoxgb-dNN-*` (d27..d54) + `dNN-*evidence|diagnostic|executor_check|supervisor*`,
  `dNN_*.py/json`, `dNN-*.log`, `v1-*.log`, `d26..d35 *.log`: diagnostics; classify by completion.json/summary.json.
- `confirm-onset-v1` (+ .predict*.log/.pid): separate persistence/onset confirmation (predictions_frozen.json,
  evaluation.json, 14 ubj) - candidate #2, needs its own contract check.
- `minirun-*`, `smoke-*` (INTEGRATION_FIXTURE.json): test fixtures -> exclude. `stop-*.txt`: process kill log.
Deterministic rule: model_bearing = frozen.json present AND actual.json accepted AND every case fold.json status
"fitted"; replayable = additionally models/ present in each fold (currently FALSE for scen-b43ef6a-v1).

## 3. Inference contract per run x horizon
Recipe from frozen.json: strategy A, map_id 8965af6d6a724ba5d61d, route learned_map, G1 (H4) / G4 (H8), local L1.
Needed: (a) global booster scenario_globals/h{H}/{G}/O<origin>_<digest>.ubj + .json identity (sha-checked
stage3.py:262-271); (b) cluster map scenario_maps/<map_id>/.../cluster_mapping_*.csv (area->cluster_id);
(c) per-cluster local boosters + gate.json (regions/locals/global; gate rule stage3.py:362-366, gain > STAGE3_GAIN);
(d) feature order feature-schema.json "ordered_features" (verify_fourclass.py:368); (e) proba() fixed 4-class
axis, base_margin guard (native_xgb.py:157-177); (f) decoder: argmax -> y_pred_code, crisis = code>=3
(plan.py:14-16, DOWNSTREAM_ALIGNED=False). Replay pattern: verify_fourclass.py:365-392 (per branch_id
booster -> proba -> np.array_equal vs p_partitioned_*).
Reference predictions: scenario_actual/h{H}/{2025-06,2025-10}/predictions.csv.gz key (area,target_month,horizon),
cols area,target_month,origin_month,horizon,y_true_code,y_pred_code,cluster_id,route,p_1,p_2,p_3,p_4或5,country,
scenario_k,persistence_*; routes local_model / global_fallback:<reason> / unmapped_area_global.
GAP: (c) not on disk -> cannot replay local_model rows; only global rows replayable.

## 4. Registration granularity
One version per run x horizon x origin (actual case), bundling global + all local components + map + gate + schema:
`fewsnet-geoxgb/<run>/h<H>/O<origin>` e.g. fewsnet-geoxgb/scen-b43ef6a-v1/h4/O2025-02. Arm fixed by frozen recipe
(A); pooled_predictions = diagnostic artifact, not a separate version.

## 5. Runtime pins / GeoRF
PINNED_RUNTIME prepare_fourclass.py:60-62 (py 3.12.10, numpy 2.2.6, pandas 2.2.3, sklearn 1.6.1, scipy 1.15.2,
geopandas 1.0.1, shapely 2.1.0, polars 1.27.1, xgboost 3.0.0), enforced with drift error at 155-169; recorded in
frozen.json runtime. GeoRF is vendored in-tree (src/model/GeoRF.py, app/main_model_GF.py:48); src/feature/feature.py:10
inserts the parent dir on sys.path. Code identity: frozen.json code.sha256 fd25e2f7... (65 files).

## Addendum
gate.json "locals" (7 clusters for h4/2025-06) holds fit RECORDS only (kind "continuation", parent_sha256 of the
global, 200+20 rounds, depth-1 local params), not booster bytes. Local boosters are continuations of the global
booster; they could be refit deterministically from global + fit pool + record, but that is a refit, not a load.
confirm-onset-v1 stores globals at S0/globals/h4/G1/O<origin>_<digest>.ubj (same GlobalStore layout).
