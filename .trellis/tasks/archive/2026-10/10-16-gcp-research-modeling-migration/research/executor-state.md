# Executor state (continuation record), updated 2026-10-16 11:46 EDT

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
- **Code lineage:** native clone `/home/swl007007/projects/food-crisis-research/control-plane`, branch `gcp-research-migration`, HEAD `34a83ca`; a separate worktree `control-plane-inputs-fix` (branch `transfer-inventory-status`, 760e763) holds the corrected transfer.py and must be merged after the driver ends. Recent commits:
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
  - FEWS scen actual packages cd88184; URI mapper + cloud reader d6bff7e; reader feature_blocks + check harness e513fff; URI original-side fix 697d33c;
  - scen accepted-exception receipt binding 1a7e207; saved-artifact feature comparison e4a20e2; preservation manifest 3c39f64;
  - PostGIS geometry import c1dc977 + identities/PG tests e280fde; capacity record f93bfa1;
  - FEWS ordinary (D35/37/38/46/47/48/51/52) 4ba91e3 + 6577476, completion binding/loader length 066a09a; D42/D43 map
    transfer 066a09a (+cap scope 8d779ff); stage-1 candidates 617de73 + completion binding/root coverage 8d779ff;
    confirm-onset pooled 3bee169; summarize 1c6c977;
  - cost ledger ccd1fd2 + atomic transitions/validation e79ccad;
  - stage-1 explicit system/root 78ae83f; v1 globals 78ae83f + horizon validation 1cde8f6; shared scen/confirm loader
    width + NaN-safe builders 22150fe; preservation --no-recurse 991e27a; FEWS training adapter 713e350;
  - training label/horizon/identity checks aeec007, MLflow tag fallback b49ccc7; images e24de64; quote 3aec3ab;
  - images writable HOME + self-check ff90981, provider pin 36bde42, replay images b24dfd1; quote bindings 7180734 /
    6d4a9b6 / b24dfd1; preservation gate 50e9a6c; provisioner b497503 → 253a6b2 → b32038d; db_roles 3c8dbad;
    ledger note 6f9cbda; transfer a3eb433 → a524e51; bytecode guards df4bd6b (NOT in the 36bde42 images; see
    `checkpoint-g7-g8-data-load-20261016.md` §3); MLflow store loader b97ddcd; URI driver fix 0624d03 + a408376; staging access 344a857; input-import wrapper 779a5c1; image sandbox replay 9a04ded; cloud job specs edb0989 (+disableRetries de1a116); quote f45426e/7d83228; replay freshness gate 4a0080c; temp admin de1a116/e0a18d7; identities/access e0a18d7/7f09313; IAM proxy de1a116; URI map paging 600a932; Vertex launcher 3f0a8e5 + digest env c63e436; guarded admission e646fa7/2f2743d; credential cache 468a155 (image) / 1cc5cd7 (comment) + live check; package publish/download 5700b95 → da4f3ce/90a1409; transfer merge bc618c5; base manifests 51e7804; AC8 clean run 8727a46/5ce0243; G10 15edaba/6242aec/56d1008.
  - **Do not change `research_cloud/deploy/transfer.py` until the transfer driver has finished** (its stages import from this checkout).

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
- **Live handles at 12:58:** Cloud SQL Auth Proxy PID 4174282 and loopback IAM proxy PID 570218 (operator tooling; may be stopped after close). No import, download, replay or Vertex job is running. Earlier list, for history:
  - Cloud SQL Auth Proxy PID 4174282 (127.0.0.1:5433); loopback IAM proxy PID 570218 (127.0.0.1:8091).
  - Cloud SQL input import PID 220361 (`ledger/sql-import/run.log`; 51/53 verified, no failures; geometry + capacity follow in the same process).
  - Downloaded-copy replay of the remaining families, **supervisor-owned**: `scratch/pkg-download-all-replay-supervisor/{training-fews,replay-x320}` (forecast 56/56 done). training-ipcch 28/28 was done by the executor (`ledger/image-replays-downloaded/training-ipcch`, accepted).
  - Runbook FEWS smoke check (`/tmp/rb-smoke.log`, output `scratch/smoke-fews-*`).
  - Cloud Run research-mlflow revision **00007-hld** (armed).
  - Finished since 11:46:
    - scen archive bytes 55,899/55,899 (accepted);
    - full 223 reader download (15,477 files / 12,578,866,404 B);
    - HPT attempt 3 SUCCEEDED and harvested (`g11-vertex/ipcch-hpt2-3/`); HPT parents closed with true outcomes;
    - per-trial cap fix d9ede46 (submission hold lifted);
    - actuals collector + revised quote d58fcda;
    - researcher runbook (native `research_cloud/RUNBOOK.md`).
- **Operator ledger and receipts:**
  - `ledger/spend.sqlite`: platform 2026-10 reserved USD 76.31 (15 operations: incl. G10 allocation 10, exception archive 5.16, package downloads 1.47, publish copies 0.33), training pool 6 operations (FEWS trial 1 failed + 2 ok, IPCCH trial ok, HPT failed, HPT probe cancelled), no actuals. The ledger balance is not plan headroom.
  - Sanitized receipts: `ledger/provision-receipt.json`, `ledger/db-roles-receipt.json`, `ledger/uri-rebind-receipt.json`, `ledger/temp-admin-receipt.json`, `ledger/mlflow-identities-receipt.json`, `ledger/g10-assistant-receipt.json`, `ledger/vertex/*/`, `scratch/ac8/run-*/report.json`, `scratch/trial-packages/{download,replays,provenance}.json`.
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
| IPCCH training chain | at `5003e4f`; saved-artifact comparison e4a20e2 (keys byte-identical, X 12,576 cells ≤1.7e-16) | `p2-training-5003e4f` |
| URI mapping check2 | 172/172, 56 mapped, 115,658 ordered features (supervisor-verified) | `p2-uri-697d33c` |
| FEWS scen amended (receipt-bound) | 8/8, 3,200 rows; system arms carry receipt 6ea45411… | `p2-packages/replay-fews-scen-1a7e207` |
| SQL CSV import run3 | 53/53 verified, 0 stale/failed | `p2-sql-postgis-f93bfa1/csv-import-report.json` |
| PostGIS geometry | 3/3 verified, WKB byte-equal (identity-bound reload after deliberate metadata reset) | `p2-sql-postgis-f93bfa1/geometry` |
| SQL capacity | 10.98 GiB data; quote carries 30 GiB | `p2-sql-postgis-f93bfa1/capacity.json` |
| FEWS ordinary 8 runs (066a09a) | 8/8, 10,752 rows, 168 units; 0 non-finite source probabilities | `p2-packages/replay-fews-ordinary-066a09a` |
| FEWS map D42/D43 (8d779ff) | 2/2, 11,356 rows | `p2-packages/replay-fews-map-8d779ff` |
| FEWS stage-1 8 runs (78ae83f) | 8/8, 12,912 rows, 1,614 units all covered | `p2-packages/replay-fews-stage1-78ae83f` |
| FEWS v1 globals (1cde8f6) | 1/1, 1,152 rows | `p2-packages/replay-fews-globals-1cde8f6` |
| FEWS scen 8 (22150fe) | 8/8, 3,200 rows (supersedes 1a7e207) | `p2-packages/replay-fews-scen-22150fe` |
| FEWS confirm-onset pooled S0/S3 (22150fe) | 2/2, 800 rows; system arm NOT packaged (pending) | `p2-packages/replay-fews-confirm-22150fe` |
| FEWS training adapter (713e350) | features equal original cohorts/digests; 2 trials + refusal; package replay | `p2-training-fews-713e350` |
| FEWS MLflow linkage (b49ccc7) | FINISHED run, reader download replay 200/200 | `p2-training-fews-b49ccc7` |
| Images (e24de64) | locks verified in fresh venvs; trials byte-identical | `checkpoint-p2-images-quote-20261016.md` |
| Final quote (3aec3ab) | platform 81.07/mo + 0.85; training 0.78 | `quote-3aec3ab/` |
| Preservation manifests | scen 55,899 files; actual-inputs 6; failed_stage1 670 | `p2-preservation/` |

The registry ledger stands at 170 passed and 72 tracking-only.

## Status by phase

- **P1/P2 (local): complete.**
  - All 223 packages have current replay receipts (registry 170 passed + 72 tracking-only; pop-v1 24; FEWS 29 + confirm 2 + scen 8, etc.).
  - SQL/PostGIS rehearsal and capacity are done.
  - Training adapters for both families: features, trials, packages and MLflow linkage.
  - Five pinned images are built.
  - Preservation gate: 29/29 roots.
- **P3 (cloud), current at 12:28:**
  - **G5–G8:** APIs, SAs and scoped grants, 18 secret versions, buckets, AR, `research-pg` (PostGIS) with scoped roles: done.
  - **Data:**
    - MLflow stores in Cloud SQL (64 tables / 361,026 rows and 11 / 10, digests equal);
    - GCS transfer verified (all 29 FEWS roots: 136,927 files / 76,973,948,308 B; inputs 122/122; artifacts 3,569; packages 15,477);
    - scen and confirm-onset bytes downloaded and verified (accepted exceptions; incomplete full-system status unchanged);
    - research-input SQL import 51/53 and running (then geometry + capacity).
  - **G9:**
    - Cloud Run `research-mlflow` revision 00007-hld (public invoker, user-approved; Basic auth gates content);
    - access 17/17 + 32/32; credential cache 18/18; UI accepted by the user;
    - URI map 56; publish 223 / 15,477 verified; reverse links 170; FEWS registry 29 READY;
    - images: 7 digests.
  - **G10:** assistant armed on Gemini endpoint `ipcch-assistant-gemini-enso` (target-bound); guard ledger keyed proof (5 rows, USD 0.04063650); deny probe (model self-refused; allowlist not exercised live).
  - **G11:**
    - FEWS and IPCCH trials: provenance equals submission; packages replayed.
    - HPT attempt 3 SUCCEEDED and harvested; parents closed with true outcomes.
    - The per-trial cap was ineffective for attempt 3 (disclosed). Corrected in d9ede46 and required by admission.
  - **AC8:** clean WSL runs, both families ok. All 223 packages downloaded through the reader and replayed in the pinned images: accepted (97,928 rows, 0 phase changes; 219 complete + 4 approved incomplete).
  - **G12 (pending):** temporary-admin removal, post-removal checks, writer freeze, r3 + keyed delta + artifact re-hash, acceptance.json / cutover receipt.
- **Quote** (`quote-d58fcda`, supersedes the older quotes): platform USD 79.97/month, first month 92.18 (gross list; scoped to this migration; no billing actuals). Training: 7 submitted jobs, reservation estimates 1.06. Ledger: platform 77.10 reserved over 16 operations, actual NULL.

## Resolved since the earlier pending list

Somalia v1, window-probe comparators, pop-v1, FEWS NET coverage, the URI map, service hardening, the SQL input import rehearsal, training adapters, containers and the cost estimate are all done. Their receipts are in the completed-rounds table above and in the checkpoints.

## Acceptance status at 11:10 (what is done vs open)

- **Done with evidence:** user UI acceptance (personal login/navigation/speed); access 17/17 anonymous + 32/32 principals direct; credential-cache invalidation 18/18; publish `--verify` 223/15,477; image sandbox replays 223/223 of local packages; AC8 clean WSL runs FEWS + IPCCH ok; FEWS/IPCCH Vertex trials with emitted provenance = submissions and downloaded-package replays (200 / 48 rows); G10 armed, query settled (USD 0.0146), deny probe (model self-refused; allowlist not exercised live, rehearsal + startup marker only); legacy largest artifact download; confirm-onset archive bytes 65/65.
- **Open (12:25):** remaining downloaded-copy replays (training-fews 53, replay-x320 86; supervisor-owned); SQL 53/53 + geometry + capacity; temporary-admin removal, then post-removal checks on revision 00007; writer freeze, then r3 + keyed delta + full artifact re-hash; merge the native commits into the registered lineage (`research_cloud/` only; dirty files preserved); supervisor reconciliation; close.

## Open user questions

None open at this refresh. Rulings recorded by the supervisor (473467b, f5b6fa1):
- **confirm-onset-v1:** accepted as a narrow historical exception. Preserve all material, label the full system arm unreplayable (7 missing regional models; S0/S3 2,446 of 11,436 rows) and separately provide the extant global/pooled download/replay. No substitute retraining and no full-system pass.
- **Temporary migration admin:** approved. Password only in Secret Manager; removed after acceptance (guarded removal); the owner's account is untouched; the user does their own final login.
- **Public invoker:** approved as a single IAM change on research-mlflow only (O-062). MLflow Basic auth gates all content.

## User rulings (recorded by the supervisor in e53de85; no longer open)

- **Spend:** the user stated current-month actual spend for `food-crisis-modeling-enso` is USD 0. This is user-supplied and not API-verified; billing-account access is still denied. The USD 3 figure belongs to `manuel-remote-sensing` and is not used.
  - The spend-information gate is resolved.
  - In-scope provisioning and jobs proceed when their technical and cost gates pass, with no repeat permission request.
  - The platform (USD 100/month) and training/HPT (USD 100/month) used-and-reserved ledgers stay separate, and each operation keeps its own receipt.
- **FEWS NET `scen-b43ef6a-v1`:** the user accepted it as an incomplete historical exception.
  - Preserve all extant material.
  - Label the 18 missing regional boosters and the 3,746 of 22,872 unreplayable rows.
  - No substitute retraining.

## Open items and next actions (current at 12:58; supersedes earlier lists)

All execution steps are done:
- SQL 53/53 + geometry 3/3 + capacity (O-115/O-116; supervisor-accepted);
- temporary-admin removal with TTL proof and own-role cascade disposition (O-117; accepted);
- post-removal checks 17/17 + 31/31 (O-118);
- writer freeze (O-119);
- r3: empty delta, 3,569/3,569 artifacts equal, cut over (O-120);
- native merge 12a5dd7 (accepted);
- `acceptance.json` FINAL and `g12-cutover/cutover-receipt.json`.

Remaining:
1. Supervisor reconciliation.
2. `trellis-audit close` from this bound session, after all relevant evidence is committed. Success is claimed only on an accepted audit result.

**Disclosed, no action:** the 14 executor-written `.pyc` files stay in the original MLflow artifact store. **Flag:** the default compute SA holds Editor (automatic; O-030).
