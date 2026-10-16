# FEWS NET `scen-b43ef6a-v1`: missing local continuation boosters (blocker receipt)

Written 2026-10-16 02:28:59 EDT (by `date`). Status: **retained_weights_missing_dependencies**. This needs a user disposition; it does not block independent work.

## What is missing

Run: `/mnt/c/Users/swl00/geoxgb_runs/scen-b43ef6a-v1`, completed `scen-actual` (`Food_Crisis_Cluster/.trellis/tasks/archive/2026-10/10-02-exogenous-transition-forecast-design/PROGRESS.md:631-648`).

`scripts/run_experiment.py:368-389` (`save_fold`) writes fold boosters only when `keep_boosters` is set. No fold in the run has a `models/` directory. Each case's `gate.json` `locals` records the local continuation boosters' fit records (parent sha256, rounds, params and the child `booster_sha256`) but not their bytes. The global boosters (682 `.ubj` under `scenario_globals/`) and 20,310 stage-1 checkpoint boosters are present.

| Case (horizon/target) | Rows | Rows routed `local_model` | Missing local boosters (child sha256) |
|---|---|---|---|
| h4/2025-06 | 5718 | 1912 | region 15: `44afd1f3f96f504cf1bbf1de0092979a13edc959164accfc275f506ab2539766` (parent `2b4d561151b26e76…`, 220 rounds)<br>region 16: `4877bbc53c76ddd7ccce813ab0c9b760e7da252b3485c79f64e7773707fa33b9`<br>region 2: `6c387822d38c33a5c79c48a21fffa8c387c22384804788d200036f93ea9d3ce1`<br>region 3: `1f50180c3a8f3b913e738497e478079df7c1c8fa335f2f72fc48c163a7ba849c`<br>region 4: `82eec07945b0e33f36e177bdb08bb77f2eafbc9f25653718605b88b8c468d9c4`<br>region 5: `3226840b436a143bc59369b957e26727a201ec4911d969aaca7adfaaf417e492`<br>region 7: `fda9b20b6633c43799197330965774790d50da74ef0392531a2b12c7c023e1c8` |
| h4/2025-10 | 5718 | 810 | region 10: `ce5e7732ec7307ebacdbaa391cfc7f7891c706c9c8932f5be0539ac0fd703d33` (parent `c50cbe2c9662de33…`, 220 rounds)<br>region 14: `1b6841390efd9988f2270a8849097c2a103132dc4c800eaa74e0656db009f1ff`<br>region 2: `a0599d5eea1f387d1f7a68eb1f1a7ba84cb6dab6484a15a6e588adc2fc76d1a2`<br>region 3: `b77f7999773692670f3f47b3747af5d088ce4b642aa0572b03a8e57572a985e0`<br>region 5: `48dcdeb10775a300be113f775cb775a9efda00e3f8c5b5545e7dac21ca86e7ec` |
| h8/2025-06 | 5718 | 841 | region 10: `0a135c2fda611063bb8ac115cf7ea6316eed2def0903e52df5003dce7c33c5df` (parent `8f540d8e3598079c…`, 420 rounds)<br>region 3: `d4f8444ad26a03802d258a79ef91b07a5365924c2cfa60f226362317b023076a`<br>region 4: `be48d2d3147d47cb718b76020938f4dcb4ef5f043e861d674e0ec22d0d058e54`<br>region 5: `02b048c0e9f89be1a8f7110d507d9d4ff3bb63f2379810fa4ea406e23759d3a8` |
| h8/2025-10 | 5718 | 183 | region 3: `e2b015795be6cd5d8f2bba879dfcb0dfaada29c688a82af63fde8ebd5679bf1d` (parent `92a57314e16cda15…`, 420 rounds)<br>region 5: `fa0bf86fa7f452ca2f95558f929c06363eff8f2f9fcf3651dcd8c1b1764a3f26` |

In total, 18 local boosters are missing, affecting 3,746 of 22,872 actual-case prediction rows. Target list: `local_targets.json` (sha256 `8653b68e…0b6b`).

## Searched scope (exact-content search by sha256, not by filename)

- **Tool:** `research_cloud/inventory/booster_search.py` at native commit `200e5bd`. It records traversal and read errors and does not follow symlinks.
- **Report:** `local_booster_search.json` (sha256 `29f58412…8d4a`), generated 2026-10-16T02:24:18-0400.
- **Roots:** `/mnt/c/Users/swl00/geoxgb_runs` (all runs, not just this one) and `/home/swl007007` (whole WSL home, including the MLflow store, backups, preserved copies, native clones and task workspaces); pattern `*.ubj`.
- **Result:** 36,305 files hashed; `complete=true`, `errors=[]`; **0 of 18 found**.
  - 1,648 symlinks were skipped. All resolve inside the searched roots: tool caches, venvs, bun/go caches and `lib64→lib`. None points to an unsearched model root.
- **Also inspected:**
  - FEWS NET experiment folders in the Dropbox Food_Crisis_Cluster checkout (`FEWSNETGeoXGBExperiment`, `FEWSNETFourClassBaseline`, `FEWSNETCleanPersistenceExperiment`): 0 `.ubj` files.
  - Windows `%TEMP%`: 0 `.ubj`.
  - Archives: none under `geoxgb_runs`. Archives under the WSL home are unrelated (Go module caches, IPCCH `source.tar` importer artifacts, the GeoRF release zip, this task's preservation tarball).
- **Not searched:**
  - other Dropbox folders outside the declared FEWS NET experiment directories;
  - other machines, external drives and cloud buckets;
  - non-`.ubj` encodings (e.g. JSON boosters).

**Conclusion (bounded):** the 18 local boosters do not exist as `.ubj` files with those exact bytes anywhere in the searched scope. This is not a claim of global absence.

## Consequence and options (user disposition)

The historical identity of each actual-case version requires all its components. Global-routed rows (19,126 of 22,872) can be replay-checked against saved predictions; local-routed rows cannot. The version therefore stays **retained_weights_missing_dependencies**. It is not registered as a replayable package, and no global-only substitute is presented as the historical model.

Possible dispositions (no default is taken):

1. **Locate originals** elsewhere (another machine, drive or bucket); the exact sha256 values above allow verification.
2. **Register as incomplete:** migrate the retained global boosters, maps, gate records and saved predictions as a disclosed incomplete historical record (tracking plus partial package), with local-route rows marked unreplayable.
3. **New version:** a separate, clearly new model version (e.g. a rerun with `keep_boosters`) that is never labelled as the historical `scen-b43ef6a-v1` result. This would be future research work, not part of recovering the original.

Pending under P1/G-3: the other FEWS NET model-bearing runs in the bounded boundary (diagnostic, aborted and test-labelled runs included) still need their deterministic catalog. This receipt covers only `scen-b43ef6a-v1`'s actual cases.
