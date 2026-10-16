# Inference-package specs and version ledger (written 2026-10-16 02:11:45 EDT by `date`)

Inputs to this document:
- `model-inventory.json`: member-level, fresh hashes, code `65c0d45`;
- the r1 MLflow snapshot (`54aa6898…`);
- four time-boxed read-only exploration notes in `exploration-notes/`, each about 2–3 minutes, all returned within the cap. These notes are model output. Only the items marked **verified** below were checked by the executor against the source at the cited anchors.

## Version ledger (registered versions, snapshot r1)

| Family (experiment 2/4 tag) | Versions | Weights | Package status |
|---|---|---|---|
| geoxgb_reference | 8 | retained (6,125 members verified) | to build |
| geoxgb_yearly_refit | 12 | retained (1,267, from the preserved copy only) | to build |
| alphaearth_supervised_partition | 16 | retained (305) | to build |
| forecasting: compact_climate_global 14, compact_climate_somalia 14, compact_launch_global 5, compact_launch_somalia 5, origin_safe_climate_global 12, origin_safe_weather_global 6 (oracle realized-future weather; label kept), somalia_oracle_information 15, somalia_q3_optimization 23, somalia_validity_observed 12, somalia_validity_augmented 12, somalia_calibrated_observed 4, somalia_calibrated_augmented 4 | 126 | retained (3,443 members verified, Dropbox IPCCH root) | to build |
| mlp_residual_fixed_maps | 48 | **missing** | tracking-only, disclosed |
| geoxgb_window_probe | 16 | **missing** | tracking-only, disclosed |
| geoxgb_climate_swap | 8 | **missing** | tracking-only, disclosed |
| geoxgb_maps_2024 | 8 | **missing** | tracking-only, disclosed |

That gives 162 retained-weight registered versions and 80 tracking-only versions; all 242 stay in the acceptance ledger.

FEWS NET has no registered versions. In `scen-b43ef6a-v1`, the global boosters are retained but the local continuation boosters were never persisted (below). Its proposed versions are **retained_weights_missing_dependencies**.

## Per-family contracts

### GeoXGB reference (P6) and yearly refit

- **Store:** content-addressed `models/<d[:2]>/<d>/` with `q2..q5.ubj` and `record.json`; yearly units add `fit_rows.npy` and `fit_keys.npy`. There is no index. Saved predictions carry provider/identity columns, and `model_requests.jsonl` ledgers map rows to units. (Exploration note; anchors `IPCCHGeoXGBExperiment/ipcch_geoxgb/modelstore.py:56,205`, `stage3.py:37-39,193,261,279`.)
- **Non-member dependencies:** `prepared/feature_order.csv`, `prepared/X_rich561_hXX.npy` with `keys_hXX.csv.gz`, `stage1/frozen_map_hXX.csv` and `frozen_hXX.json`, `stage3/hXX/gate_decisions.jsonl` and the saved predictions.
  - **Verified present and local** in the P6 Dropbox run root: 195 files, 0.81 GB, `dropbox_local` status all `local` (2026-10-16 ~02:10).
  - The yearly preserved copy contains `inputs/run/{prepared,stage1,stage3}`, `predict`, `replay` and `report` (exploration note; to be re-checked by the builder).
- **Runtime:** original lock is Windows Python 3.12.10 / xgboost 3.0.0 / numpy 2.2.6 / pandas 2.2.3, and `runtime.py` refuses other platforms. Linux replay is a declared platform deviation judged by the D11 tolerance against the saved `*_raw` columns.
- **Projection:** a fixed isotonic step, not a fitted calibrator (`projection.py:91`, exploration note).

### AlphaEarth supervised partition

- **Store:** `models/<d[:2]>/<d>/{q2..q5.ubj,record.json}`, 61 identities. Digest mapping is through `predict/request_ledger.csv.gz` or the `B0_identity`/`B1_identity` prediction columns.
- **Arms:** B0 compact296; B1 296+128 descriptors; B2 and G are coefficient corrections in `predict/contexts_hXX.json`. G falls back to B2 because no map was selected.
- **Dependencies:** feature order, `descriptors/descriptor_table.csv.gz`, `predict/contexts_hXX.json`, `maps/final_map_hXX.json`, and `prepared` X matrices (`predict/`, `prepared/`, `descriptors/` and `maps/` are present in the run root by `ls`).
- **Runtime:** Linux Python 3.12.3 / xgboost 3.2.0 lock, so no platform deviation.
- **Caveat:** recorded code identity is uncommitted (57ca2ef1 + 385a8db8). The MLflow `source_code/` artifact is the code copy to package, not HEAD.

### IPCCH forecasting (12 source keys)

- **Members per version are in `plan.json`:** boosters, fit keys, batch records/predictions, feature schema or run metadata, calibration and selection.
- **Loader:** the existing predict-only loader expects a different layout, so a new loader is needed (`launch_nowcasting.py:1355-1372`, exploration note).
- **Missing references:** somalia_oracle families have **no saved predictions**, so reference samples need another source (gap). Possible constant-model `.json` fits are not in the members list and must be checked against `model_inventory.csv` kinds (gap).
- **Runtime:** xgboost is not pinned in `pyproject.toml`/`uv.lock` and must be recovered from booster metadata (gap).
- **Correction to the exploration note:** members are **not** missing on Linux/WSL. They are in the Dropbox IPCCH repository `results/` tree, which is gitignored and therefore absent from the native clone. They were verified there with fresh hashes.

### FEWS NET GeoXGB research

- **Model-bearing completed run within the boundary:** `scen-b43ef6a-v1` (`frozen.json`, accepted `actual.json`; completion evidence `PROGRESS.md:631-648`). `confirm-onset-v1` is a second candidate still to be classified.
- **Verified:**
  - `scripts/run_experiment.py:368-389` writes fold boosters only when `keep_boosters` is set.
  - The run contains 682 `.ubj` under `scenario_globals/` and 20,310 under `stage1_scenario/` (stage-1 checkpoints), and **no `models/` directory in any fold**.
  - `scenario_actual/h4/2025-06/gate.json` `locals` hold continuation fit records only (parent sha, 200+20 rounds, params).
  - `fold.json` routes for H4 2025-06: `local_model` 1,912, `global_fallback:gate_gain_not_above_0.01` 3,432, `unmapped_area_global` 208, `global_fallback:gate_metric_undefined` 166 (5,718 rows).
- **Consequence:** only global-routed rows can be replay-checked against saved predictions. The version stays incomplete with this reason. A refit of local continuations would be a new model and cannot stand in for the originals.
- **Runtime:** Python 3.12.10, xgboost 3.0.0 and others (`prepare_fourclass.py:60-62`).
- **Scientific guard:** `plan.py` `DOWNSTREAM_ALIGNED=False` stays untouched.

## Common package layout (to implement)

```
package.json      identity (registered name/version, logged-model id, family, arm, lead),
                  source run and code identity, original runtime record, Linux runtime pin,
                  file list with sha256, status and gaps, loader entry, tolerance contract
weights/          the fitted units the version needs (copied bytes, hash-verified)
deps/             feature order, maps/gates/contexts/descriptors, calibration
reference/        frozen keyed sample: inputs for those rows + original saved predictions
loader/           minimal loader modules copied from the source commit (path + sha recorded)
```

The download command verifies every sha256. Reference samples are frozen before any Linux comparison and the tolerance comes from `design.md`. A family-level failure is never shrunk into a pass.
