# Cutover and fallback runbook (executor draft, 2026-10-16 ≈11:25 EDT; not executed)

This is the plan for G12, which the active approved goal authorizes; there is no additional user-go gate. Supervisor-reviewed: stop and disable `ipcch-mlflow.service` after all remaining ACs pass, provided the unit points at the inventoried local store. This is a reversible writer freeze within the migration. Cloudflare tunnel and DNS stay unchanged. Nothing below has been run unless marked **done**.

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

## 3. Writer freeze and final delta (after all remaining ACs pass)

1. Confirm the unit's identity: `systemctl --user cat ipcch-mlflow.service` must point at `~/.local/share/ipcch-mlflow` (the inventoried `mlflow.db`, `auth/basic_auth.db` and `artifacts/`).
2. Stop the local writer and prevent restart: `systemctl --user stop ipcch-mlflow.service` and `systemctl --user disable ipcch-mlflow.service`. Note that `manage.sh stop` stops only the API, and `import.lock` excludes only the importer.
3. Take snapshot r3 with the same read-only backup method under `umask 077` (directory 700, databases 600, like r1/r2), and compute the same keyed table delta versus r1. Then re-hash **every** one of the 3,569 frozen artifacts against the r1 manifest sha256 (r2 compared sizes only). The 14 disclosed `.pyc` files are the only allowed extras and are not deleted.
4. **Decision:**
   - **Empty delta (only the 14 `.pyc` files may differ in the artifact tree):** cut over; nothing is imported.
   - **Non-empty delta:** stop. Enumerate the changed keys and prepare a keyed, additive delta for review. Never rerun `copy_store`, never reset its journal, and never overwrite cloud rows.
5. Point users to `https://research-mlflow-76571749286.us-central1.run.app` (Basic auth; existing accounts unchanged). The Cloudflare tunnel and DNS are not changed.

## 4. Fallback

- The original local service stays **stopped and disabled**, and the store is not written. Snapshots r1, r2 and r3 (private: directory 700, databases 600) and the untouched local store remain for read-only, offline inspection. No new read-only web server is created.
- Any later writable rollback first preserves the cloud's additions: export the keyed delta from r1 to the cloud, then decide. Cloud writes are never overwritten with an old snapshot.

## 5. Archives eligible for cloud-only (exact verified roots only)

Eligible means every file was transferred create-only with a fresh sha256 equal to its frozen manifest, and a final fresh `--verify` re-read every local file and remote object (bucket, generation, md5, crc32c, declared sha256). For the accepted-exception archives, every byte was also downloaded and re-hashed. Eligibility does not delete anything; deleting or making Dropbox cloud-only is the user's separate decision.

| Local root (exact) | Cloud prefix | Files | Bytes | Fresh verify | Byte download |
|---|---|---|---|---|---|
| `/mnt/c/Users/swl00/geoxgb_runs/confirm-onset-v1` (accepted exception; full-system replay unavailable; pooled models packaged) | `gs://food-crisis-modeling-enso-research-inputs/fews-runs/confirm-onset-v1/` | 65 | 62,541,229 | ok | **ok 65/65** |
| `/mnt/c/Users/swl00/geoxgb_runs/scen-b43ef6a-v1` (accepted exception) | `…/fews-runs/scen-b43ef6a-v1/` | 55,899 | per manifest | pending (running) | **pending (running)** |
| The other 27 roots in `scratch/preservation/gate.json`: the d34/d37/d38 evidence roots, geoxgb-d26 … d52, geoxgb-v1, minirun-1/2, smoke-2, scen-b43ef6a-v1.failed_stage1, scen-b43ef6a-v1.actual-inputs-v1, the geoxgb_runs top-level files | `…/fews-runs/<root>/` | per gate (29 roots total 136,927 files, 76,973,948,308 bytes) | per gate | **ok: all 29 roots, 136,927 / 76,973,948,308 exact** (`ledger/verify/fews-*.json`, 11:25) | not required (metadata + hash verify) |

**Declared inputs:** only the 122 exact inventory paths in `scratch/p1/input-inventory.json`, verified 122/122. These are **individual files**, not their parent trees.

**Explicitly not eligible:** whole trees such as `1.Source Data`, `assembled_FEWSNET`, `assembled_IPCCH`, `Food_Crisis_Cluster` or `IPCCH`, since subset inventories do not cover them. Also not eligible:
- the monthly workflows (`cloud_pipeline/…`, `september_manual`) and their inputs. The monthly FEWS manifest uses `combined.normalized-v1.csv`, which is not the inventoried `combined.csv`.
- the native `sources/` clones and the local `ipcch-mlflow` store, which are not Dropbox objects.

## 6. After acceptance (temporary admin removal)

1. Run `temp_admin remove`. It requires this task's receipt, the task-labelled secret and an authenticating credential. It deletes exactly that user directly in the auth store (before/after diff) and destroys its secret versions.
2. **Credential-cache proof:** the restart was already done (revision 00007-hld), so no new revision is needed. After the 60 s cache TTL, the old credential must get 401. It is checked in memory only, never persisted or logged.
3. **Post-removal access checks without the temporary admin:** `staging_access --direct` (anonymous) and `cloud_access --without-admin` (bec579d; never reads `mlflow-temp-admin`), using reader, job writer and assistant only.
4. The user's personal login was already accepted (10:35); it is not asked again absent a regression.

## 7. Gate status (honest, at writing)

- **Done:** UI acceptance; access matrices; restart persistence (00006 → 00007: armed, guard rows kept, query settled); publish verify 223; reverse links 170 keyed; FEWS registry 29; FEWS archive verify 29 roots / 136,927 files / 76,973,948,308 bytes; confirm-onset bytes 65/65; AC8 both families; trials and provenance.
- **Pending:** full 223 reader download + 4-image replay; scen archive bytes; SQL import 53/53 + geometry + capacity; HPT 2-trial retry; temporary-admin removal + post-removal checks; writer freeze + r3 keyed delta + artifact re-hash; native commit merge; close.
