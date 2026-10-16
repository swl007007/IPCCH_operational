# Checkpoint P2a — MLflow store copy rehearsal (written 2026-10-16 02:05:44 EDT by `date`)

Scope: tracking and basic-auth **row copy** from SQLite into a disposable local PostgreSQL 16, plus the artifact-URI survey. This is not AC2/AC4 completion. Pending items are listed at the end.

## Code

Native control-plane branch `gcp-research-migration`, commit `a16b9d5`: `research_cloud/mlflow_migrate/copy_store.py` and `research_cloud/tests/test_copy_store.py`. The supervisor independently ran the 28 tests with `RC_TEST_PG` against the disposable server: all pass.

Copier contract:
- the target schema comes from MLflow 3.17's own initializer at the same alembic revision;
- one transaction per table, in foreign-key order;
- the journal is bound to the source snapshot sha256 and revision; a changed snapshot is refused before any write;
- typed, length-delimited, order-independent digests over all columns, including generated ones, compared between source and target;
- `--verify-only` runs in a read-only session;
- serial sequences are advanced to max(id);
- no row values or secrets are logged.

## Source snapshot r1

Taken with SQLite online backup (the same method as `IPCCHMLflow/backup_restore.py`) at 2026-10-16T02:00:14-0400, from the live store, which kept running. See `p2-rehearsal/snapshot.json`.

| File | Bytes | sha256 |
|---|---|---|
| `mlflow.db` | 156,655,616 | `54aa68980b25df0a07be313d471e51c226ffc7245ae455679aaadb4242e4dcd9` |
| `auth/basic_auth.db` | 135,168 | `3797d7d06c0c1ff1a81727b29a000cbc90f06028870bc939b5faa4cbfebc5b6b` |

Snapshot copies are at `/home/swl007007/projects/food-crisis-research/scratch/mlflow-snapshot-r1/` (auth copy mode 600).

## Target identity

- Disposable cluster: PostgreSQL 16.10 (conda-forge) with PostGIS 3.5.0 in the `research` database.
- `system_identifier` 7697141375592551152.
- Data dir `/home/swl007007/projects/food-crisis-research/scratch/pg-rehearsal/data`; unix socket only (`listen_addresses=''`), port 55432.
- Databases `mlflow` (202,969,571 bytes after load) and `mlflow_auth` (8,294,883 bytes). Both were dropped and recreated before r3.
- Schemas: tracking alembic `dc11669786a5`, 65 tables, column sets identical to SQLite. Auth uses `alembic_version_auth`, 11 data tables.

## r3 results (reports in `p2-rehearsal/`)

| Step | Report | sha256 | Outcome |
|---|---|---|---|
| tracking load, interrupted after 20 tables | `r3-tracking-interrupted.json` | `25dbb76a…272f` | stopped before `evaluation_dataset_tags` |
| tracking resume | `r3-tracking-resume.json` | `bc47db2e…f13f2` | complete; 64 data tables / 361,026 rows; `spans.duration_ns` (generated) recomputed and compared; sequences `experiments.experiment_id`=5, three empty rollup sequences reset |
| tracking verify-only | `r3-tracking-verify.json` | `aea74cf4…f363` | every table: source digest = target digest and equal row counts |
| auth copy | `r3-auth-copy.json` | `67b66d7b…26d4` | complete |
| auth verify-only | `r3-auth-verify.json` | `0ca43212…a8a2` | verified: users 2, roles 2, role_permissions 4, user_role_assignments 2; all per-object permission tables 0 |

To re-run verification independently (read-only):

```
W=/home/swl007007/projects/food-crisis-research
$W/envs/mlflow-svc/bin/python -m research_cloud.mlflow_migrate.copy_store --verify-only \
  --source $W/scratch/mlflow-snapshot-r1/mlflow.db \
  --target "host=$W/scratch/pg-rehearsal/sock port=55432 user=postgres dbname=mlflow" --report /tmp/verify.json
```

Run it from `$W/control-plane`. For the auth store, use `--version-table alembic_version_auth` with dbname `mlflow_auth`.

## Artifact URI survey (snapshot r1)

- All stored artifact locations are portable: experiments 6/6, runs 679/679, logged models 242/242 and model-version storage 242/242 are `mlflow-artifacts:/…`, and model-version sources 242/242 are `models:/…`. The local server serves them from `~/.local/share/ipcch-mlflow/artifacts/{1,2,3,4}` (1.28 GB, via `--artifacts-destination`). A cloud server with `--artifacts-destination gs://<artifact-bucket>/<prefix>` and the same relative tree resolves them without rewriting.
- `~/.local/share/ipcch-mlflow/ipcch-forecasting/{staging,plans,cache}` (0.7 GB) is importer working space, not referenced by stored URIs. It is not part of the served store; whether to archive it is a separate decision.
- Local-path-bearing values (80):
  - `card.feature_list` on 56 logged models embeds `/home/swl007007/.local/share/ipcch-mlflow/artifacts/3/<run>/artifacts/source.tar!…`. This maps one-to-one to `mlflow-artifacts:/3/<run>/artifacts/source.tar!…`. The plan is to keep the original tag and add a mapped cloud reference, with the feature-list reader resolving it. The other 116 `card.feature_list` values already use `runs:/` forms.
  - `zz_prov.source_root` (7 params), `zz_prov.bundle.models.tar.local_source` (1 tag) and `mlflow.note.content` (16 logged-model tags) are historical provenance, preserved unchanged.

## Explicitly pending (row copy alone does not complete AC2/AC4)

- Feature-list URI mapping and the reader adaptation (`ipcch_model.py` feature-list resolution) for the 56 local references.
- Artifact transfer to GCS with per-file hashes and SDK download checks.
- MLflow-level functional comparison (runs, metric histories, registry/logged-model/dataset links through the MLflow API against both stores).
- Cloud Run service: auth enforcement (owner/job/reader/anonymous), assistant read-only gate and smoke, restart persistence.
- Gateway secret handling: the encrypted old-project credential row is copied as ciphertext only in the rehearsal. The cloud cutover replaces it with a target-project credential (decision pending at G10).
- Final writer freeze and delta snapshot at cutover; the rehearsal ran against a live, writable source snapshot.
- Paid cloud steps remain deferred by the spend gate (`cloud-operations.md`).
