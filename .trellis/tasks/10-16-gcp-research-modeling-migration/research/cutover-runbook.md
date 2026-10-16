# Cutover and fallback runbook (executor draft, 2026-10-16 ≈11:25 EDT; not executed)

This is the reviewed plan for G12. Stopping the local service or changing the Cloudflare tunnel/DNS is a separately reviewed final operation (design: "Cutover and rollback"). Nothing below has been run unless marked **done**.

## 1. Current delta evidence (done)

- **Local store vs migrated snapshot r1:** a consistent read-only backup r2 of the live local stores (SQLite online backup from `mode=ro` connections, 11:24) compared table by table with r1 (rows ordered by every column, sha256 of the row stream):
  - `mlflow.db`: 65 tables / 361,027 rows, **0 differing tables**;
  - `basic_auth.db`: 12 tables / 11 rows, **0 differing tables**.

  Evidence: `scratch/mlflow-snapshot-r2/delta-vs-r1.json`. The live file bytes differ from r1 (`30f1bc5d…` vs `54aa6898…`) only because r1 is a backup-API copy; the logical content is identical.
- **Artifact tree vs the frozen r1 set:** 3,583 files now = 3,569 frozen (none missing, none changed in size) + the 14 disclosed executor-written `.pyc` files.
- **Consequence:** no delta import is needed today. `copy_store` is **not** a delta importer. It binds the r1 source sha and would reject or overwrite the cloud's additions, so it must never be rerun or its journal reset against the live cloud.

## 2. Cloud-only state that must be preserved

None of it exists locally, and none of it is touched by any step below:
- experiments 6 `cloud-acceptance-access-matrix`, 7 `cloud-training-acceptance`, 8 `historical-packages` (223 package runs) and 9 (Gateway endpoint experiment);
- 29 `FEWS NET | …` registered models;
- reverse-link tags on 170 registered model versions and 170 source runs;
- 56 `card.feature_list.cloud` logged-model tags;
- users `ipcch-jobwriter`, `ipcch-reader`, `ipcch-assistant` and roles `ipcch-readers` / `ipcch-job-writers`;
- Gateway endpoint `ipcch-assistant-gemini-enso`, the guard ledger (database `guard`) and the temporary migration admin (removed after acceptance, see §6).

## 3. Writer freeze and final delta (proposed; requires the user's go)

1. Announce the freeze. The local service stays readable until step 2.
2. Stop the local writer and prevent restart: `systemctl --user stop ipcch-mlflow.service` and `systemctl --user disable ipcch-mlflow.service`. Note that `manage.sh stop` stops only the API, and `import.lock` excludes only the importer.
3. Take snapshot r3 with the same read-only backup method under `umask 077` (directory 700, databases 600, like r1/r2), and compute the same keyed table delta versus r1. Then re-hash **every** one of the 3,569 frozen artifacts against the r1 manifest sha256 (r2 compared sizes only). The 14 disclosed `.pyc` files are the only allowed extras and are not deleted.
4. **Decision:**
   - **Empty delta (only the 14 `.pyc` files may differ in the artifact tree):** cut over; nothing is imported.
   - **Non-empty delta:** stop. Enumerate the changed keys and prepare a keyed, additive delta for review. Never rerun `copy_store`, never reset its journal, and never overwrite cloud rows.
5. Point users to `https://research-mlflow-76571749286.us-central1.run.app` (Basic auth; existing accounts unchanged). Changing `ipcch-cloudflared.service` or DNS is a separate reviewed operation.

## 4. Read-only fallback

- **Before the user's go:** the local service remains the writable authority (design).
- **After cutover:** restart the local service only for reads. Re-enable the unit with the local auth `default_permission` unchanged, and do not write to it. Any rollback that would make local writable again first exports the cloud's new writes (the keyed delta from r1 to the cloud) and never overwrites them with an old snapshot.

## 5. Archives eligible for cloud-only (exact verified roots only)

Eligible means every file was transferred create-only with a fresh sha256 equal to its frozen manifest, and a final fresh `--verify` re-read every local file and remote object (bucket, generation, md5, crc32c, declared sha256). For the accepted-exception archives, every byte was also downloaded and re-hashed. Eligibility does not delete anything; deleting or making Dropbox cloud-only is the user's separate decision.

| Local root (exact) | Cloud prefix | Files | Bytes | Fresh verify | Byte download |
|---|---|---|---|---|---|
| `/mnt/c/Users/swl00/geoxgb_runs/confirm-onset-v1` (accepted exception; full-system replay unavailable; pooled models packaged) | `gs://food-crisis-modeling-enso-research-inputs/fews-runs/confirm-onset-v1/` | 65 | 62,541,229 | ok | **ok 65/65** |
| `/mnt/c/Users/swl00/geoxgb_runs/scen-b43ef6a-v1` (accepted exception) | `…/fews-runs/scen-b43ef6a-v1/` | 55,899 | per manifest | pending (running) | **pending (running)** |
| The other 27 roots in `scratch/preservation/gate.json`: the d34/d37/d38 evidence roots, geoxgb-d26 … d52, geoxgb-v1, minirun-1/2, smoke-2, scen-b43ef6a-v1.failed_stage1, scen-b43ef6a-v1.actual-inputs-v1, the geoxgb_runs top-level files | `…/fews-runs/<root>/` | per gate (29 roots total 136,927 files, 76,973,948,308 bytes) | per gate | per root in `ledger/verify/fews-*.json` (to be completed) | not required (metadata + hash verify) |

**Declared inputs:** only the 122 exact inventory paths in `scratch/p1/input-inventory.json`, verified 122/122. These are **individual files**, not their parent trees.

**Explicitly not eligible:** whole trees such as `1.Source Data`, `assembled_FEWSNET`, `assembled_IPCCH`, `Food_Crisis_Cluster` or `IPCCH`, since subset inventories do not cover them. Also not eligible:
- the monthly workflows (`cloud_pipeline/…`, `september_manual`) and their inputs. The monthly FEWS manifest uses `combined.normalized-v1.csv`, which is not the inventoried `combined.csv`.
- the native `sources/` clones and the local `ipcch-mlflow` store, which are not Dropbox objects.

## 6. After acceptance (temporary admin removal)

1. Run `temp_admin remove`. It requires this task's receipt, the task-labelled secret and an authenticating credential. It deletes exactly that user (before/after diff) and destroys its secret versions.
2. Re-run the access matrix to show nothing else changed.
3. The user then confirms their own login, which was already done at 10:35.
