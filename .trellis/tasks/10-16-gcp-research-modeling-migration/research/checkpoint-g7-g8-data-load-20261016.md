# Checkpoint: data staging and MLflow store load (executor, 2026-10-16 ≈08:20 EDT)

## 1. MLflow stores in Cloud SQL (O-045): complete and verified

`load_mlflow_stores` ran at native b97ddcd as `mlflow_app` through the Auth Proxy (PID 4174282). Exit 0. Fresh schemas were created by MLflow 3.17's own initializers, so there was no pre-existing schema.

| Store | Source sha256 (= snapshot r1) | Revision | Tables | Rows (source = target) | Copy | Verify |
|---|---|---|---|---|---|---|
| tracking → `mlflow` | 54aa6898…dcd9 | dc11669786a5 | 64 | 361,026 | complete, 187.45 s | every table digest equal |
| auth → `mlflow_auth` | 3797d7d0…5b6b | f1a2b3c4d5e6 | 11 | 10 | complete, 8.34 s | every table digest equal |

Independent cross-check: the source sha256, the table set and every cloud target digest equal the local rehearsal r3 verify reports (`p2-rehearsal/r3-*-verify.json`). The reports contain no credentials. Copies are in `g8-g9-data-load/mlflow-store-load/`.

Not yet done for MLflow: the service deploy, workspace roles, `feature_list_map --apply` through the deployed service, and the access matrix.

## 2. GCS transfer: per-stage identity (S54)

The driver `ledger/transfer/run-all.sh` (sha256 799a3f7c…, PID 25168, started 08:04:23) runs `set -u` only. It continues past a failing stage and prints DONE unconditionally. It has no `--expect-files` and no final `--verify`, and it imports from the mutable native checkout. **Its DONE line therefore proves nothing about completeness.** Acceptance comes only from the per-source fresh `--verify` reports with `--expect-files` equal to the independent counts below, plus exact receipt/set reconciliation.

Code identity per stage (`transfer.py` git blob at the stage's process start):

| Stage | Process start | HEAD then | transfer.py blob | Receipts carry `bucket` |
|---|---|---|---|---|
| pilot actual-inputs (O-044) | 08:02:07 | a3eb433 | 9779e818 | no |
| mlflow-artifacts | 08:04:24 | df4bd6b (transfer.py identical to a3eb433) | 9779e818 | no |
| packages | 08:06:44 | a524e51 | 94474814 | yes |
| inputs, FEWS roots | later | b97ddcd | 94474814 | yes |

`transfer.py` will not be changed in the native checkout until the driver has finished. That fixes the code identity of the remaining stages at blob 94474814 (sha256 da78b474…).

The pre-a524e51 receipts (pilot, mlflow-artifacts) lack `bucket`. The final fresh `--verify` re-binds them, reading the bucket, generation, md5, crc32c and declared sha256 of every object.

### Independent expected sets for acceptance

| Source | Expected set | Files | Bytes |
|---|---|---|---|
| MLflow artifact tree | `scratch/preservation/mlflow-artifacts-r1.json` (frozen r1) | 3,569 | 1,321,922,679 |
| Packages | 223 package dirs, each with package.json (= the 223 passing receipts); files = Σ(files in package.json) + 223 | 15,477 | from package.json |
| Declared inputs | `scratch/p1/input-inventory.json`: 123 entries, 122 unique paths (one shared between namespaces, transferred once) | 122 | from inventory |
| FEWS run archive | `scratch/preservation/gate.json`: 29/29 roots passed | 136,927 | 76,973,948,308 |

MLflow artifacts (S54 scout): the 3,569 receipts equal the frozen r1 set and its hashes. The older count of 3,573 files / 1,321,950,132 bytes is explained by four `__pycache__` files written at 02:19, before that count was committed at 03:23. That is a supported reconstruction, not an exact old-set proof, because no keyed 3,573 list exists.

## 3. Image identity vs current host code

The five images were built from contexts at native **36bde42**. Native commits since then change, in `research_cloud`:
- the operator-only deploy modules: `provision_secrets`, `db_roles`, `transfer`, `load_mlflow_stores` and their tests;
- **df4bd6b**: `sys.dont_write_bytecode = True` added to `images/selfcheck.py`, `packages/fews_scen.py`, `training/{fews_features,fews_fourclass,ipcch_features,ipcch_quartet}.py`, plus `tests/test_readonly_sources.py`.

What follows:
- The images' recorded identities (commit 36bde42, digests in `g9-images-36bde42/`) stay valid for exactly what they contain.
- Current host adapter hashes (`adapter_identity` at b97ddcd or later) are **not** equal to the image's. The training-module source bytes differ from 36bde42 by the df4bd6b guard line. No record will claim they are equal.
- Cloud training provenance comes from the image's baked `IPCCH_SOURCE_COMMIT=36bde42` and digest. Host-built feature snapshots keep their own recorded host identity.
- df4bd6b changes no numerical code, and the deploy changes run only on the operator workstation, so the five images are **not** rebuilt for them.
- Inside the image the bytecode concern does not arise in the same way, because the source tree is not an original artifact store. The image self-check at 36bde42 ran without the guard.

## 4. Disclosure: bytecode written into the original MLflow artifact store

Executor replay/training processes imported P6 `source_code` modules directly from the original local MLflow artifact store. Python wrote **14 `.pyc` files** (plus their `__pycache__` directories) under run `bdbafe393d…`'s `source_code/`: 4 at 02:19 and 10 at 04:43–04:54 EDT.
- **Observed:** the current tree is exactly the frozen r1 set (3,569 files, 1,321,922,679 bytes, equal to the transferred set) plus these 14 cache files.
- **Inferred, not proven:** that no pre-existing file changed before r1 was frozen. No keyed pre-work list exists to prove it.
- **Prevention:** df4bd6b, plus `test_readonly_sources`.
- **Transfer:** the files are excluded from the r1 manifest and were not transferred.
- **Current state:** they have **not been deleted**.

**Ruling (supervisor, 2026-10-16):** leave the 14 files in place and disclose them. Cleanup is outside scope and not required for the migration; no deletion and no approval flow. The 3,573-file reconciliation is an observed-versus-inferred statement: no pre-work keyed list of 3,573 artifacts exists.
