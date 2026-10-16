# Executor state (continuation record), updated 2026-10-16 03:22 EDT by `date`

This file is kept current by the executor so work continues unchanged across context compaction. It is not a source of approval; see `execution-authorization.md`.

## Identity and lifecycle

| Item | Value |
|---|---|
| Executor | Claude session `228d9075-d67a-41c9-9f4c-7830cdac3b87`, pane `w14:p9`, terminal `term_65dee2e4ca9b6a` |
| Supervisor | Codex in `w14:p1`; owns `supervisor-log.md` |
| trellis-audit run | `1193a92d1b0e4118a464753e548e113f`, base `99d390b7df536ba8d2661b94a80f29d5abac09fd`, task in_progress |
| Registered repo | `/mnt/c/users/swl00/ifpri dropbox/weilun shi/ipcch_monthly_operational` (exact spelling) |

There must be no restart or reset of the run or executor.

The registered-repo evidence commits so far are e19b2c5, 1115e49, 7b449f6, c90cab1, 0d9b1b4, ed1c6de, 0a0d135 and cd95cdf (plus the next checkpoint), all on `feat/october-cloud-delivery`. Only this task's directory has been committed. The 73 pre-existing dirty paths are untouched.

- **Preservation:** `refs/preserve/gcp-migration-predirty-20261016` and the tarball in `/home/swl007007/projects/food-crisis-research/preservation/`. The close-time stash/restore plan is in `p0-receipt.md`: no bulk tar extraction, verified per-file restore only.
- **Code lineage:** native clone `/home/swl007007/projects/food-crisis-research/control-plane`, branch `gcp-research-migration`, HEAD `bf77ccd` (forecasting batch/launch 81d6fb3, provenance fix 602558c, somalia v2 74e00f6, somalia v2/v3 job-scoped bf77ccd). These commits **must be merged into the registered repo lineage before close.**

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
- **Packages:** `packages/`. P6 8, yearly 12 and AlphaEarth 16 all pass (`p2-packages/replay-bf3da00/`). Forecasting batch/launch: 56 built with the corrected provenance code, replay running. Somalia v2 23 + v3 24 are being rebuilt with job-scoped calibration (previous build: 47/47 pass). Replay round `scratch/replay/fc-bf77ccd/` comes from background PID 2114182 (`/tmp/round_fc.sh`, log `scratch/replay/round-fc.log`).
- **Inventories:**
  - `scratch/p1/model_inv_v2` (member-level, fresh hashes);
  - `scratch/p1/registry_ledger.json` (+ `ledger_resolutions.json`);
  - `scratch/p1/fews/` (hash cache, catalog, search report);
  - `scratch/p1/popv1_models.json`.
- **SKU catalogs:** `scratch/p3/skus/*.json`.
- **Background processes:** PID 2114182 (somalia rebuild + forecasting/somalia replay), started 03:21:24.

## Status by phase

- **P1:** inventory reconciled (`ledger/README.md`).
  - 242 registry versions with exact key equality: 36 packaged and passing, 134 retained with packages pending (forecasting 126 + window-probe comparators 8, linked to P6 units), 72 tracking-only.
  - Unregistered and in scope: `pop-v1` (660 local models), and the FEWS NET bounded root (27 runs, 34,085 `.ubj` files, 59.9 GB, labelled).
  - Inputs: 121 declared files, 14.87 GB, hashes match (`input-inventory.json`; agent-produced, partial).
- **P2:**
  - Store-copy rehearsal r3 passes (tracking + auth).
  - Packages: P6, yearly and AlphaEarth are done.
  - **In progress:** forecasting batch/launch builder (`research_cloud/packages/forecast_batch.py`, uncommitted). It covers compact global/somalia original and 2026 extensions, origin-safe climate IDP, origin-safe weather ORACLE (label kept) and launch. The dataset comes from the manifest chain with sha verification; the decode is `classify_cumulative`.
- **P3:** preflight done (`cloud-preflight.json`, `cloud-operations.md` O-001…O-024); support APIs `cloudbilling` and `billingbudgets` enabled; SKU prices collected. **No paid resource has been created.**

## Pending items and gaps

1. **Forecasting:**
   - Batch/launch (56) and somalia v2/v3 (47) builders are done; the replay round is running.
   - Remaining: **somalia v4** (8 versions, commit a787257: per-job recipe, history-override feature rows saved in `features/final_override_features.csv.gz`, residual support via `_v4_matrix`/`v4_fit_predict`) and **somalia v1** (15 versions, `run_somalia_oracle_experiment.py`, `predictions/predictions.csv.gz` with `q*_pred`/`phase_pred`).
   - **Correction:** the somalia runs DO have saved predictions in their original run directories (`predictions/*.csv.gz`, `selection/*`); they were only absent from the MLflow plan members.
2. **Window-probe comparator packages (8):** link to P6 units; a builder is needed.
3. **pop-v1 packages:** XGBoost plus RandomForest (`joblib`) loader; version granularity proposal.
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

1. Commit and finish forecasting batch/launch packages, then replay them.
2. Somalia-oracle reference source.
3. Comparator and pop-v1 packages.
4. Service rehearsal.
5. SQL import rehearsal.
6. Training adapter.
7. Cost estimate.

Continue checkpoint commits after each step.
