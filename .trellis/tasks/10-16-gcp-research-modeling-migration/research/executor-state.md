# Executor state (continuation record), updated 2026-10-16 05:42 EDT by `date`

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
- **Code lineage:** native clone `/home/swl007007/projects/food-crisis-research/control-plane`, branch `gcp-research-migration`, HEAD `e513fff`. Recent commits:
  - forecasting batch/launch 81d6fb3, provenance fix 602558c;
  - somalia v2 74e00f6, job-scoped bf77ccd, oracle status 99c6588;
  - PROGRESS ledger c509a39;
  - somalia v4 e8d5160 + 7e1c391;
  - assistant guard 40f43d4 + total reconciliation 44350b6;
  - service launcher/rehearsal 2791308 + workspace roles/assistant end-to-end 733f2c0 + corrections d84dabd;
  - Somalia v1 50c2b38; window-probe comparators efdaea3 + input binding 62bc2a7;
  - role overlap fix f49520a; pop-v1 6d95905;
  - guard Gemini 3.8 contract da40998; window provenance tests afc020a; sqlimport b93429b; training harness + IPCCH adapter 418da0e;
  - pop-v1 route/support + frozen bindings 3c47cc5; harness project binding + failed-trial MLflow 7bd3921; dropbox interop retry e972207.
  - importer collision-free names + whole-table verification 643d1a4, exact numerics/stale receipts 8868583;
  - training S27 boundaries + Linux feature snapshot + portable trial package 5003e4f; code identity/full manifests/integral checks 6d0eb85;
  - FEWS scen actual packages cd88184; URI mapper + cloud reader d6bff7e; reader feature_blocks + check harness (WIP) e513fff.

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
- **Background processes:**
  - SQL import run3 (PID 2856914; code 8868583): 50 verified, 0 failed at 05:42. Log `scratch/sqlimport/run3.log`, report `scratch/sqlimport/report.json`; the final reconciliation is written when it finishes. Do not start another import.
  - The disposable PG (PID 1262386) is running. All rehearsal MLflow servers are stopped.
  - Rehearsal data:
    - `scratch/uri/artifacts-copy`: a copy of the artifact tree, served for the URI rehearsal.
    - `wsc_*` DBs: the copied stores, with roles applied and the 56 mapped tags written.
- **Registered-repo lock:** the stale 0-byte `.git/index.lock` (04:21:04, no live git) was moved to `preservation/stale-index.lock-0421`. Evidence was committed in `a99e84c`.

## Completed rounds: do not redo

Each round below is finished, with current receipts. Rerun a round only if its code or packages change.

| Round | Result | Receipts |
|---|---|---|
| GeoXGB P6 / yearly / AlphaEarth | 36/36 | `p2-packages/replay-bf3da00` |
| Forecasting batch/launch | 56/56 (supervisor round, adopted) | `p2-packages/replay-forecast-602558c-supervisor` |
| Somalia v2/v3/v4 | 55/55 | `p2-packages/replay-somalia-e8d5160` |
| Somalia v1 | 15/15 | `p2-packages/replay-somalia-v1-50c2b38` |
| Window-probe comparators (input binding) | 8/8 | `p2-packages/replay-window-probe-62bc2a7` |
| pop-v1 corrected | 24/24, 20,106 rows (supervisor full replay, adopted) | `p2-packages/replay-popv1-3c47cc5` |
| Service rehearsals | deny 50, armed 48, restart 7, assistant 9, copied roles 16 | `p2-service-d84dabd` |
| IPCCH training chain | at `5003e4f` | `p2-training-5003e4f` |

The registry ledger stands at 170 passed and 72 tracking-only.

## Status by phase

- **P1:** inventory reconciled (`ledger/README.md`).
  - 242 registry versions with exact key equality: 36 packaged and passing, 134 retained with packages pending (forecasting 126 + window-probe comparators 8, linked to P6 units), 72 tracking-only.
  - Unregistered and in scope: `pop-v1` (660 local models), and the FEWS NET bounded root (27 runs, 34,085 `.ubj` files, 59.9 GB, labelled).
  - Current ledger: **170 packaged_replay_passed, 0 pending, 72 missing tracking-only**. The unregistered pop-v1 run has 24 packages, all passing (`checkpoint-p2-packages-complete-service-corrections-20261016.md`).
  - Environment `envs/rt-popv1-x300` (scikit-learn 1.6.1) was added for pop-v1.
  - Inputs: 121 declared files, 14.87 GB, hashes match (`input-inventory.json`; agent-produced, partial).
- **P2:**
  - Store-copy rehearsal r3 passes (tracking + auth).
  - Packages: P6, yearly and AlphaEarth are done.
  - Forecasting batch/launch and Somalia v2/v3/v4 are done and committed.
  - The service (guard, launcher, workspace roles, access matrix, assistant end-to-end) is done locally; see `checkpoint-p2-service-20261016.md`.
- **P3:** preflight done (`cloud-preflight.json`, `cloud-operations.md` O-001…O-024); support APIs `cloudbilling` and `billingbudgets` enabled; SKU prices collected; the spend-information gate is resolved by user ruling (USD 0). **No paid resource has been created yet**; the final itemized quote comes next.

## Pending items and gaps

1. **Forecasting:** remaining is **somalia v1** (15 versions, `run_somalia_oracle_experiment.py`, `predictions/predictions.csv.gz` with `q*_pred`/`phase_pred`, arms A-D ensembles).
   - **Correction:** the somalia runs DO have saved predictions in their original run directories (`predictions/*.csv.gz`, `selection/*`); they were only absent from the MLflow plan members.
2. **Window-probe comparator packages (8):** these cannot alias the P6 packages. `regional_ungated` needs 77 local P6 units, which are absent from the current packages and retained in the original P6 root. Routing uses `local_fit_ok` regardless of gate adoption, on selected dates only. Keep the eight original registry identities and references (`remaining-packages-supervisor.md`).
3. **pop-v1 packages:**
   - Weights: all 660 weight basenames match 110 fold identity JSONs across six arms; the originals inventory covers the files beyond the 24 in the native clone.
   - RandomForest: reuse the saved imputer `fill_values` from each `model_identity` (do not refit).
   - Threshold and correction: the threshold is strict `>` with ±Infinity literals; the correction arm flips by persistence.
   - Pointers: `remaining-packages-supervisor.md`.
4. **FEWS NET:** run-record treatment per `ledger/README.md`; packages only for runs with a servable model and saved predictions. For `scen-b43ef6a-v1`, apply the accepted incomplete-history exception: preserve all material and label the 18 missing boosters and the 3,746 unreplayable rows.
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

## Open user question

- **FEWS NET `confirm-onset-v1`:** 7 local boosters were not retained (2,446 of 11,436 system rows); see `fews/confirm-onset-missing-local-boosters-receipt.md`.

## User rulings (recorded by the supervisor in e53de85; no longer open)

- **Spend:** the user stated current-month actual spend for `food-crisis-modeling-enso` is USD 0. This is user-supplied and not API-verified; billing-account access is still denied. The USD 3 figure belongs to `manuel-remote-sensing` and is not used.
  - The spend-information gate is resolved.
  - In-scope provisioning and jobs proceed when their technical and cost gates pass, with no repeat permission request.
  - The platform (USD 100/month) and training/HPT (USD 100/month) used-and-reserved ledgers stay separate, and each operation keeps its own receipt.
- **FEWS NET `scen-b43ef6a-v1`:** the user accepted it as an incomplete historical exception.
  - Preserve all extant material.
  - Label the 18 missing regional boosters and the 3,746 of 22,872 unreplayable rows.
  - No substitute retraining.

## Open items (in order; nothing below is accepted yet)

1. **URI check fix** (supervisor):
   - `feature_list_check` must resolve the ORIGINAL side from snapshot r1 runs' local artifact root, so the 116 `runs:/` specs are not read from the target;
   - add unit tests for the mapping, remote member extraction and cloud-local refusal;
   - then re-run against the URI rehearsal server (`scratch/svc-rehearsal/run-uri.sh`, port 55502; admin and copied non-admin credentials in `wsc-creds.json`).
2. **FEWS scen packages** (supervisor scout on cd88184; numerics and routing verified):
   - add a hash-bound accepted-exception receipt inside each package (affected keys and counts, the 7 child hashes, the search scope);
   - mark the original receipt as accepted by the user ruling;
   - document the loader input as prepared 129-column X, with raw reconstruction outside the package;
   - write a separate preservation transfer manifest covering `gate_pairs.csv.gz` and all extant scenario material, keeping Windows paths as provenance only.
   - Rebuilding only the 8 scen packages is acceptable; do not rerun other groups.
3. **Feature comparison** (supervisor): compare the SAVED artifacts. The new `keys_h03.csv.gz` decompresses to bytes identical to P6's (sha256 bc94d674…, 42,695 rows × 19 columns). `keys_identical=false` in the `features-h03-v2` audit came from comparing the in-memory frame with the deserialized one. Narrow fix plus one regression. Do NOT regenerate the features.
4. **Remaining FEWS groups** per `fews-adapter-groups-supervisor.md`: ordinary 162-column D35/37/46/47/48, D38 margin, D51 h78, D52 binary, D42/D43 map transfer, the stage1 candidate group (v1, d26-d31, d34), confirm-onset (global/pooled only; system pending user disposition), and preservation-only records (fixtures, replay evidence, failed_stage1).
5. **PostGIS:** import and round-trip the three geometry bundles, keeping their identities.
6. **SQL capacity:** after run3 reconciliation, record the sizes of all three DBs (relations, indexes, TOAST, side tables), measured WAL/temp and explicit headroom; disclose the key-profile coverage (26 of 53 profiled; gaps not invented).
7. **Images** (service plus training; Dockerfiles), then the final itemized quote (exact Gemini 3.8 Flash SKUs), then G5-G11 cloud operations with per-operation receipts.

## Next actions (in order)

1. SQL capacity: the typed import rehearsal is running (`research_cloud/sqlimport/load_inputs.py`, report `scratch/sqlimport/report.json`).
2. FEWS NET run records (`fews-adapter-groups-supervisor.md`): the `scen-b43ef6a-v1` exception record; the `confirm-onset-v1` blocker receipt (user disposition needed).
3. SQL input import rehearsal.
4. Image definitions for Cloud Build.
5. Training adapter plus HPT trial entry (`training-adapter-source-supervisor.md`).
6. Final itemized quote (`cost-inputs-supervisor.md`, exact Gemini 3.8 Flash SKUs in `gemini-exact-price-supervisor.md`) with the measured SQL capacity and download paths; then G5-G11 operations, with per-operation receipts.

Service status: launcher, workspace roles, access matrix and assistant end-to-end are done locally (`checkpoint-p2-service-20261016.md`). The remaining service items are the cloud-phase checks listed there.

Continue checkpoint commits after each step.
