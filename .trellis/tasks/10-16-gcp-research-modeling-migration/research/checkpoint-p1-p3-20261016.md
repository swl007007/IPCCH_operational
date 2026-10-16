# Checkpoint P1/P3 (interim) — 2026-10-16 02:15 EDT

Executor run `1193a92d1b0e4118a464753e548e113f`, base `99d390b`. Registered-repo HEAD is unchanged at `99d390b`; the evidence below is uncommitted until this checkpoint's commit.

## Code (native WSL control-plane, branch `gcp-research-migration`, not yet merged into the registered lineage)

| Commit | Content |
|---|---|
| `b53162c` | `research_cloud/inventory/dropbox_local.py`: Dropbox placeholder classifier with explicit `inspection_error` / batch failure; 6 mocked failure-mode tests |
| `dc5fc48` | `model_inventory.py` v1 + `roots.json`. Superseded: chose the first existing root (supervisor finding) |
| `e8315b8` | `roots.json` note correction |
| `65c0d45` | Per-member resolution across **all** declared roots; root failures propagate; `--fresh` implies hashing; classifier via UTF-8 `.ps1`; 17 tests (supervisor re-ran: pass) |

GitNexus: `impact` on `classify` in repo `IPCCH_operational` returns "Target not found". The index was built at `8feec3a` from the DrvFS path, and `research_cloud/` exists only in the native clone, created in this task. Callers were therefore verified by grep: only `research_cloud` modules and their tests import these symbols. No pre-existing symbol in the registered repo has been edited.

## P1 facts established

- **Sources:** Food_Crisis_Cluster `6c1ebf72`, IPCCH `3b04fd09`; both clean (tracked files). Native read-only clones under `/home/swl007007/projects/food-crisis-research/sources/`.
- **MLflow store** (read-only SQLite):
  - alembic `dc11669786a5` (MLflow 3.17);
  - 6 experiments, 679 runs, 109,268 metrics, 2,619 params, 20,705 tags, 1,104 datasets, 3,722 inputs;
  - 196 registered models, 242 versions, 242 logged models (116 for experiment 2 dashboard, 126 for experiment 4 forecasting);
  - Gateway: 1 endpoint, 1 model definition, 1 encrypted secret (not read); 157 traces.
  - Artifact dirs: `artifacts/` 1.3 GB, `ipcch-forecasting/` 0.7 GB. Auth DB 148 KB (not read).
- **Model members:** `model-inventory.json`, code `65c0d45`, fresh sha256.
  - Verified: P6 GeoXGB reference (6,125), yearly refit (1,267, resolved only from the preserved copy `~/ipcch-legacy-source-preservation/yearly-formal-20261007`; the Temp run root has empty hash dirs), AlphaEarth (305), and all 12 forecasting source keys (3,443). In total 11,140 members, 6.90 GB recorded.
  - Missing under every declared root: MLP residual (26,696), climate swap (5,460), maps-to-2024 (4,180), window probe (475). Their Temp roots keep empty content-hash directories, and the MLflow backups (5–9 MB each) hold no weights.
  - This **contradicts the README claim** that those four source roots no longer exist: the roots exist, but the weights are gone.
- **Inputs:** `input-inventory.json`, partial, produced by an agent. 121 unique declared files, 14.87 GB (FEWS NET 15 files / 1.67 GB; IPCCH 108 / 13.20 GB), 0 hash mismatches, 0 cloud-only, 0 missing. The tabular key-profile pass completed after the agent stopped (`scratch/p1/tmp_d/keys.jsonl`, 26 rows) and is not yet merged.
- **FEWS NET:** not yet inventoried in persisted evidence. Partial agent artifacts (scratch only) show:
  - the search boundary holds about 137k files across `/mnt/c/Users/swl00/geoxgb_runs` (193 entries, including d26–d35 stage iterations, confirm-onset, scen-*) and `FEWSNETFourClassBaseline/runs` in Dropbox;
  - 20,992 `.ubj` boosters in `scen-b43ef6a-v1` were hashed (`scratch/p1/tmp_c/hash_scen_ubj.jsonl`).

## P3 facts established

See `cloud-preflight.json` and `cloud-operations.md` (O-001…O-024).
- Project active, billing enabled.
- The executor holds every project permission the plan needs, but **no billing-account permission**.
- Support APIs `cloudbilling` and `billingbudgets` were enabled (O-014/O-015).
- Public SKU catalogs for SQL, Run, GCS, AR, Vertex, Secret Manager, Build and Logging were retrieved.
- Actual spend is not visible to the executor. The three exact administrator figures needed are listed in `cloud-operations.md`. Paid provisioning and job submission are deferred until they arrive.

## Explicit gap ledger (unresolved)

| # | Gap | Next action |
|---|---|---|
| G-1 | No version→member mapping for the 7 dashboard families (content-hash dirs), and no check of non-member dependencies (stage1 maps/partitions, calibrators, MLP transforms, feature lists) | Read each family's replay/loader code; build per-version package specs |
| G-2 | Forecasting plan members include boosters, fit keys, batch predictions and records, but feature schema/preprocessing completeness per version is unverified | Same package-spec pass |
| G-3 | FEWS NET runs: no deterministic catalog yet; scope boundary of ~137k files; 20,992 scen `.ubj` hashed but not mapped to components | Write `fews_inventory.py` over the declared boundary; classify runs by completion evidence |
| G-4 | 4 dashboard families have no retained weights: their versions (registered but no package) stay tracking-only and are disclosed. Exact per-version count pending G-1 | Count after mapping |
| G-5 | Reference prediction samples not frozen yet | After G-1/G-2/G-3 |
| G-6 | Input key-profile results not merged; no SQL/GCS layout decision per file yet | Merge `keys.jsonl`; storage map |
| G-7 | Cost quote not yet written; actual spend and EE billing status unknown | Administrator figures (supervisor requesting); write `cost-estimate.md` from SKUs + measured volumes |
| G-8 | No container runtime in WSL; images must be built by Cloud Build, a paid route deferred by G-7 | Prepare Dockerfiles and rootless crane+bwrap runner locally |
| G-9 | Agent-produced partial artifacts in scratch are not evidence until re-derived by committed code | — |

No live handles remain: all detached agent processes finished by 02:12, and v2 inventory finished at 01:56.

Next: P2 local integration (MLflow SQLite→PostgreSQL rehearsal on the user-space PG16; container/runtime contracts), interleaved with G-1/G-3 package mapping.
