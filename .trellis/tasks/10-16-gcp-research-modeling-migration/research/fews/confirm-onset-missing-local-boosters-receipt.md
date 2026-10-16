# FEWS NET `confirm-onset-v1`: local continuation boosters not retained (blocker receipt)

Written 2026-10-16 04:38:11 EDT (by `date`). Status: **retained_weights_missing_dependencies** for the full gated system. This needs a user disposition; it does not block independent work. The `scen-b43ef6a-v1` exception the user accepted does **not** extend to this run.

## Producer evidence

`Food_Crisis_Cluster/.trellis/tasks/archive/2026-10/10-03-pooled-onset-confirmatory/research/run_confirm.py:393` calls `rx.save_fold(d / "fold", res["system"], identity, False, extra=...)`. The `False` is `keep_boosters`, so fold boosters were not written.

Each `S0/fold/gate.json` and `S3/fold/gate.json` `locals` entry records a local continuation's fit record:
- parent sha256 `727d0a2c77bf2c83…` (a retained global);
- 200 + 20 rounds;
- params;
- the child sha256.

The child bytes themselves are not recorded. The run holds 14 `.ubj` files, all of them globals.

## Rows affected

Counts are from `fold.json` `routes`.

| System | Rows | `local_model` | Global fallback / unmapped |
|---|---|---|---|
| S0 | 5,718 | 1,609 | 3,735 + 166 + 208 |
| S3 | 5,718 | 837 | 4,507 + 166 + 208 |
| Total | 11,436 | **2,446** | 8,990 |

## Missing local units

There are 9 gate entries and 7 unique child sha256 values (regions 4 and 14 recur across S0 and S3). Machine-readable copy: `confirm_onset_local_targets.json`.

| System | Region | Child sha256 | Parent | Rounds |
|---|---|---|---|---|
| S0 | 4 | `3858733d0fd0e56f12988ad9dce9be590b3d4c1548f48877dcfde3237eb1d0f0` | `727d0a2c77bf2c83…` | 220 |
| S0 | 5 | `c2c9c0f9a994ae40f282a84b93e1fde3a35d462b24ad63d3c2427fdd0cf7e581` | `727d0a2c77bf2c83…` | 220 |
| S0 | 8 | `a7bae7b5a0a3801947d9b9e5dfb983b5b70e3943012e893c3e3db8033e3b4e3d` | `727d0a2c77bf2c83…` | 220 |
| S0 | 14 | `ff8c9428f6579ebe8093a92382ef198f4353e6efe48ccdaa6e69efcbc55c6f99` | `727d0a2c77bf2c83…` | 220 |
| S0 | 16 | `d2f8c147f646b5d8d9c5d8c1eb909b08e4405a211928671fc0cbd75276c49f94` | `727d0a2c77bf2c83…` | 220 |
| S3 | 3 | `5c28aba2fefa18d50bade10d2628096fb371caadb52ff2aae4595bdb2a124693` | `727d0a2c77bf2c83…` | 220 |
| S3 | 4 | (same as S0 region 4) | | 220 |
| S3 | 9 | `55dd58ac743f8109a19ebc52dc275b9d8664c3bcba0fb2c61596dd4fc8f07f2a` | `727d0a2c77bf2c83…` | 220 |
| S3 | 14 | (same as S0 region 14) | | 220 |

## Searched scope

The search was by exact content (sha256), not by filename.

- **Hash cache:** `scratch/p1/fews/ubj-hash-cache.jsonl`, 36,305 `.ubj` files with sha256, from the complete search recorded in `local_booster_search.json`:
  - report sha256 prefix `29f58412…`; `complete=true`, `errors=[]`;
  - roots `/mnt/c/Users/swl00/geoxgb_runs` (all runs) and `/home/swl007007` (whole WSL home).
- **Result:** 0 of 7 unique child sha256 found.
- **Also already established** (`missing-local-boosters-receipt.md`):
  - the FEWS NET experiment folders in the Dropbox Food_Crisis_Cluster checkout hold 0 `.ubj`;
  - Windows `%TEMP%` holds 0 `.ubj`.
- **Not searched:** other Dropbox folders, other machines, external drives, cloud buckets, and non-`.ubj` encodings.

**Conclusion (bounded):** the local boosters do not exist as `.ubj` with those bytes in the searched scope. This is not a claim of global absence.

## What remains replayable

The retained globals and `pooled_predictions.csv.gz` allow a pooled/global replay of the global path. The full gated system cannot be replayed on its 2,446 local-routed rows. No global substitute is presented as the system's local outcome, and no local unit is retrained.

## Disposition needed (no default taken)

1. **Locate originals** elsewhere; the hashes above allow verification.
2. **Register as incomplete:** a disclosed incomplete historical record that preserves all material, labels the 7 units and 2,446 rows unreplayable, and packages only the pooled/global path as itself.
3. **New version:** a separately identified rerun with `keep_boosters`, never labelled as the historical `confirm-onset-v1`.
