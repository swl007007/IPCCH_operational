# Executor state (continuation record), updated 2026-10-16 03:45 EDT by `date`

This file is kept current by the executor so work continues unchanged across context compaction. It is not a source of approval; see `execution-authorization.md`.

## Identity and lifecycle

| Item | Value |
|---|---|
| Executor | Claude session `228d9075-d67a-41c9-9f4c-7830cdac3b87`, pane `w14:p9`, terminal `term_65dee2e4ca9b6a` |
| Supervisor | Codex in `w14:p1`; owns `supervisor-log.md` |
| trellis-audit run | `1193a92d1b0e4118a464753e548e113f`, base `99d390b7df536ba8d2661b94a80f29d5abac09fd`, task in_progress |
| Registered repo | `/mnt/c/users/swl00/ifpri dropbox/weilun shi/ipcch_monthly_operational` (exact spelling) |

There must be no restart or reset of the run or executor.

The registered-repo evidence commits so far are e19b2c5, 1115e49, 7b449f6, c90cab1, 0d9b1b4, ed1c6de, 0a0d135, cd95cdf and b4c9052 (plus the next checkpoint), all on `feat/october-cloud-delivery`.
- Commits so far contain this task's directory plus one authorized append to `PROGRESS.md` (supervisor request; staged as HEAD + LF section, see `p0-receipt.md` amendment). **Correction:** an earlier version of this file said "only task-dir committed, all 73 untouched"; that was stale after the `PROGRESS.md` append.
- The other 72 pre-existing dirty paths are untouched. `PROGRESS.md`'s close-time check uses `expected-after-executor-appends.txt`.

- **Preservation:** `refs/preserve/gcp-migration-predirty-20261016` and the tarball in `/home/swl007007/projects/food-crisis-research/preservation/`. The close-time stash/restore plan is in `p0-receipt.md`: no bulk tar extraction, verified per-file restore only.
- **Code lineage:** native clone `/home/swl007007/projects/food-crisis-research/control-plane`, branch `gcp-research-migration`, HEAD `44350b6`. Recent commits:
  - forecasting batch/launch 81d6fb3, provenance fix 602558c;
  - somalia v2 74e00f6, job-scoped bf77ccd, oracle status 99c6588;
  - PROGRESS ledger c509a39;
  - somalia v4 e8d5160 + 7e1c391;
  - assistant guard 40f43d4 + total reconciliation 44350b6.

  All code is committed; there is no uncommitted forecasting or somalia code. (**Correction** of the earlier "forecast code uncommitted" statement.) These commits **must be merged into the registered repo lineage before close.**

## Native workspace handles (`/home/swl007007/projects/food-crisis-research`)

- **Source clones:** `sources/Food_Crisis_Cluster` (`6c1ebf72`) and `sources/IPCCH` (`3b04fd09`), read-only.
- **Environments:**
  - `envs/mlflow-svc`: MLflow 3.17.0, psycopg2, google-cloud-storage.
  - `envs/pg16`: PostgreSQL 16.10 + PostGIS 3.5.
  - `envs/rt-geoxgb-x300`: xgboost 3.0.0 / numpy 2.2.6 / pandas 2.2.3.
  - `envs/rt-alphaearth-x320`: xgboost 3.2.0 / numpy 2.4.4 / pandas 3.0.3.
  - `envs/rt-ipcchgeo-x320`: xgboost 3.2.0 / numpy 2.4.4 / pandas 3.0.3 / scikit-learn 1.8.0, matching the somalia-oracle runs' recorded runtime.
  - `envs/rt-forecast-x320`: xgboost 3.2.0 + IPCCH-lock numpy 2.3.5 / pandas 3.0.3 / scikit-learn 1.9.0 / scipy 1.17.1. **Correction (supervisor finding):** an earlier note said forecasting boosters "embed 3.2.0". That came from re-serializing through the current xgboost, which reports the loader's version, not the original bytes'. Original xgboost versions are known only where run metadata records them; otherwise they are unknown.
- **Disposable PG:** `scratch/pg-rehearsal` (data dir; socket `scratch/pg-rehearsal/sock`; port 55432; DBs mlflow, mlflow_auth, research). It is running, started with `pg_ctl`; stop with `envs/pg16/bin/pg_ctl -D scratch/pg-rehearsal/data stop`.
- **MLflow snapshot r1:** `scratch/mlflow-snapshot-r1` (`mlflow.db` sha `54aa6898…`, auth copy mode 600).
- **Packages:** `packages/`. All built packages pass:
  - P6 8, yearly 12 and AlphaEarth 16 (`p2-packages/replay-bf3da00/`);
  - forecasting 56 (supervisor round adopted, `p2-packages/replay-forecast-602558c-supervisor/`);
  - Somalia v2/v3/v4 55 (`p2-packages/replay-somalia-e8d5160/`, from `scratch/replay/somalia-final/`).

  Do not repeat the forecast round unless the forecast code or packages change.
- **Inventories:**
  - `scratch/p1/model_inv_v2` (member-level, fresh hashes);
  - `scratch/p1/registry_ledger.json` (+ `ledger_resolutions.json`);
  - `scratch/p1/fews/` (hash cache, catalog, search report);
  - `scratch/p1/popv1_models.json`.
- **SKU catalogs:** `scratch/p3/skus/*.json`.
- **Background processes:** none.
  - The executor's `/tmp/round_fc.sh` (PID 2122191) and `/tmp/round_som.sh` were stopped or had finished; they had overlapped (`rm -rf` + rebuild) and duplicated the supervisor's forecast replay.
  - `/tmp/round_som2.sh` (PID 2200404) finished with 55/55.
  - The disposable PG (`pg_ctl` PID 1262386) is running.

## Status by phase

- **P1:** inventory reconciled (`ledger/README.md`).
  - 242 registry versions with exact key equality: 36 packaged and passing, 134 retained with packages pending (forecasting 126 + window-probe comparators 8, linked to P6 units), 72 tracking-only.
  - Unregistered and in scope: `pop-v1` (660 local models), and the FEWS NET bounded root (27 runs, 34,085 `.ubj` files, 59.9 GB, labelled).
  - Current ledger: 147 packaged_replay_passed, 23 package pending (Somalia v1 15 + window-probe comparators 8), 72 missing tracking-only (`checkpoint-p2-forecast-somalia-guard-20261016.md`).
  - Inputs: 121 declared files, 14.87 GB, hashes match (`input-inventory.json`; agent-produced, partial).
- **P2:**
  - Store-copy rehearsal r3 passes (tracking + auth).
  - Packages: P6, yearly and AlphaEarth are done.
  - Forecasting batch/launch and Somalia v2/v3/v4 are done and committed.
  - The assistant spend guard is committed with 12 tests; the launcher and HTTP rehearsal are next.
- **P3:** preflight done (`cloud-preflight.json`, `cloud-operations.md` O-001…O-024); support APIs `cloudbilling` and `billingbudgets` enabled; SKU prices collected. **No paid resource has been created.**

## Pending items and gaps

1. **Forecasting:** remaining is **somalia v1** (15 versions, `run_somalia_oracle_experiment.py`, `predictions/predictions.csv.gz` with `q*_pred`/`phase_pred`, arms A-D ensembles).
   - **Correction:** the somalia runs DO have saved predictions in their original run directories (`predictions/*.csv.gz`, `selection/*`); they were only absent from the MLflow plan members.
2. **Window-probe comparator packages (8):** these cannot alias the P6 packages. `regional_ungated` needs 77 local P6 units, which are absent from the current packages and retained in the original P6 root. Routing uses `local_fit_ok` regardless of gate adoption, on selected dates only. Keep the eight original registry identities and references (`remaining-packages-supervisor.md`).
3. **pop-v1 packages:**
   - Weights: all 660 weight basenames match 110 fold identity JSONs across six arms; the originals inventory covers the files beyond the 24 in the native clone.
   - RandomForest: reuse the saved imputer `fill_values` from each `model_identity` (do not refit).
   - Threshold and correction: the threshold is strict `>` with ±Infinity literals; the correction arm flips by persistence.
   - Pointers: `remaining-packages-supervisor.md`.
4. **FEWS NET:** run-record treatment per `ledger/README.md`; packages only for runs with a servable model and saved predictions; `scen-b43ef6a-v1` 18 missing local boosters recorded in `fews/missing-local-boosters-receipt.md`.
5. **URI map:** 56 `card.feature_list` logged-model tags embed the local store path. The plan is to keep the original tag, add a mapped cloud reference and adapt the `ipcch_model.py` reader.
6. **Service (Cloud Run):** follow `service-readiness-supervisor.md`:
   - provider `vertex_ai` with ADC (`auth_config` project/location);
   - keep uvicorn/FastAPI permission middleware;
   - `MLFLOW_BASIC_AUTH_FAIL_CLOSED`;
   - stable KEK and Flask secret from Secret Manager;
   - explicit fail-closed assistant gate (the existing `.pth` patch only logs failures).
   Local rehearsal against PG first; test owner, job, reader and anonymous access, plus assistant allow/deny.
7. **SQL input import:** raw tables verbatim with a source row number. No dedup, drop or date coercion. Record the FEWSNET.csv null key and `0000-00` sentinel, and the 2 duplicate keys in the 2025 combined panel. Shapefiles go to PostGIS plus the original bytes in GCS. Max width is 897 columns (under PG's 1,600).
8. **Training adapters + HPT trial entry** (AC5) and Linux training images.
9. **Containers:** no Docker or sudo in WSL. Images will be built by Cloud Build (paid, deferred), and exact digests run locally rootless via `crane export` + `bwrap`.
10. **Cost estimate (G4/AC6):** `cost-estimate.md` from SKUs plus measured volumes.
    - Package volume is about 1.9 GB so far plus forecasting/somalia packages; FEWS NET retained weights are 59.9 GB.
    - Historical MLflow artifacts are 3,573 files / 1.32 GB (max `source.tar` 130 MB; 9 files over 32 MiB).
    - Transport: per-file/directory via the MLflow proxy (`artifact-transport-supervisor.md`); no signing infrastructure. The final freeze must include the artifact tree, not only the DB.

## Open user questions (no answer yet; do not assume)

- **Spend:** the actual current-month spend for `food-crisis-modeling-enso` (service breakdown preferred). This is required before paid provisioning or job submission.
- **FEWS NET:** the disposition of the 18 missing `scen-b43ef6a-v1` local continuation boosters (locate originals / register as incomplete / separate new version).

## Next actions (in order)

1. Service launcher plus local HTTP access and assistant rehearsal (guard done).
2. Somalia v1 packages.
3. Comparator and pop-v1 packages.
4. Remaining service items (Secret Manager wiring, image).
5. SQL import rehearsal.
6. Training adapter.
7. Cost estimate.

Continue checkpoint commits after each step.
