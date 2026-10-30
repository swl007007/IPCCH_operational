# CP2 harvest + MLflow readback — H2, H8 (2026-10-30)

Harvest script `/home/swl007007/projects/food-crisis-research/staging/ipcch-h2h8h14-20261030/receipts/../job-packet/harvest_final.py` sha256 eb329e17b1ba3ee504cb2c73029151ab80910680a2ed66cc2fa46fa5a05f2caf (Supervisor-pinned) verified before running; training worktree clean 9aa9e54. One run per horizon, rc=0 each; receipts `/home/swl007007/projects/food-crisis-research/staging/ipcch-h2h8h14-20261030/receipts/09-harvest-h0{2,8}.json` (+ .stdout).

| H | job | files/bytes | run_id | model_id | registered v1 | elapsed s | checks |
|---|---|---|---|---|---|---|---|
| 2 | 1262877692496183296 | 47 / 28,949,425 | f55ddf45198f427eade6d68c2a3a04f2 | m-4c46295486bc4d28af8cfca561cdf4ce | READY | 545.9 | 11/11 true |
| 8 | 6328301373381148672 | 47 / 21,084,863 | 0f7e584fccc549a28cf6fe9519b94da2 | m-e7976e74421a4d75b8462291101c8918 | READY | 456.9 | 11/11 true |

Harvest checks (each true): publication, trial, recipe_equal, image_ok, source_commit_composite, adapter_module_sha, package_verifies, rows, gate_passed, fits, registered_v1_and_dataset. Trials at R/scratch/h2h8h14-final/harvest/final-h0{2,8}/trial-0.

Live MLflow readback (GET only, mlflow-reader secret in memory, identity ipcch-reader): `mlflow-readback/cp2_mlflow_read.py` → `mlflow-readback/readback-h02-h08.json`, rc=0. Both runs FINISHED/active in experiment "IPCCH dashboard"; model version 1 READY with run_id bound and source models:/<model_id>; logged model LOGGED_MODEL_READY with source_run_id bound; dataset input "… | H0x | modeling panel index" digest dba329f9b115d4de10e294133bf91d41.

H14 7189333327139045376: RUNNING since 02:13:33 local (poller bzj3ynkbp). Harvest/readback/package follow on SUCCEEDED.
