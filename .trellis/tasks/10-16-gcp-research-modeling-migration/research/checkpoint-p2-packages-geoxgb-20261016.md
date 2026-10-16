# Checkpoint P2b: GeoXGB historical inference packages (written 2026-10-16 02:32:04 EDT by `date`)

## Result

All **20** registered GeoXGB versions are `complete` and pass Linux replay. These are the 8 `geoxgb_reference` (P6) versions and the 12 `geoxgb_yearly_refit` versions. Per-package reports and `summary.json` are in `p2-packages/geoxgb-a2e4a0d/`.

- Reference rows: 13,638 frozen keyed rows. Every route of every version is covered (up to 19 routes per version). Every sampled row has missing features, so the NaN path is exercised throughout.
- Maximum absolute error over raw and projected shares: 2.22e-16. Routing mismatches: 0. Phase changes: 0. Key/order, shape, finiteness and decode checks all pass.
- Runtime: Linux Python 3.12.3, xgboost 3.0.0, numpy 2.2.6, pandas 2.2.3 (`envs/rt-geoxgb-x300`). The original runtime was Windows Python 3.12.10 with the same numerical package versions. The Linux replay is a declared platform deviation judged by the D11 tolerance, which it meets at machine precision.
- Package bytes: 825 MB total, under native `/home/swl007007/projects/food-crisis-research/packages/`. GCS upload is pending G7/G9 and therefore the spend gate.

## Code and contract (native branch `gcp-research-migration`, commit `a2e4a0d`)

### Builders and loader

- `research_cloud/packages/common.py`:
  - package paths are confined (relative, no `..`, no escaping symlinks) on write and verify;
  - every source file is read fresh and hash-checked against the member manifest;
  - Dropbox sources are classified before they are opened;
  - the capped reference sample covers every route.
- `research_cloud/packages/geoxgb.py` with family specs for P6 and yearly. Arm resolution was verified against the saved predictions:
  - P6 pooled → `global_identity`; P6 gated → `provider`;
  - yearly pooled → `pool_provider`;
  - yearly gated → `local_provider` on `route=local`, else `pool_provider` (equals `geo_` exactly);
  - yearly ungated → `local_provider`, local-eligible keys only.
  - Unit completeness requires `q2..q5.ubj` and `record.json`, with record `booster_sha256` equal to the copied bytes and a fit record per target. A truncated manifest or a digest mismatch becomes `retained_weights_missing_dependencies`.
- The keyed loader (`loader/entry.py`) resolves each `(admin_code, target_ord)` through the frozen map and `deps/routing.csv` to exactly one unit and route. A key without a frozen model in that arm (e.g. ungated ineligible keys) raises `KeyError`; no fallback is synthesized.
- The vendored loader code comes from each family run's MLflow `source_code/` artifact (`ipcch_geoxgb` / `ipcch_yearly_xgb`), with file hashes recorded in `package.json`.

### Replay and build CLI

- `research_cloud/packages/replay.py` checks, in order:
  1. integrity, with unlisted or altered files reported;
  2. exact keys/order, shape, finiteness and feature count against the declared feature order;
  3. routing equality;
  4. every value against `abs ≤ 1e-3 + 1e-3·|ref|` (declared before comparison for both raw and projected shares);
  5. phase, which must decode from the new projected vector; drift is accepted only at crossings within that reference's tolerance.
- `research_cloud/packages/build_geoxgb.py` builds from the read-only snapshot r1 identities.

### Tests

`research_cloud/tests/test_packages_geoxgb.py` has 12 behavioral tests on synthetic runs (real xgboost boosters):
- build, load and replay through gated, pooled and ungated arms;
- route resolution, including unknown-key and ungated-unavailable keys;
- reordered or wrong-key output and wrong phase near a threshold fail;
- reference cap with route coverage;
- a truncated manifest or record-digest mismatch is not complete;
- member hash mismatch is refused;
- unsafe paths are refused;
- tampered package files are detected.

Run with: `PYTHONPATH=control-plane envs/rt-geoxgb-x300/bin/python -m unittest research_cloud.tests.test_packages_geoxgb`.

GitNexus: these modules exist only in the native clone, which is not indexed (index at `8feec3a`, DrvFS path). No existing registered-repo symbol was edited. Callers are within `research_cloud` (checked by grep).

## FEWS NET

See `fews/missing-local-boosters-receipt.md`. Eighteen local continuation boosters of `scen-b43ef6a-v1` are absent from the bounded searched scope (exact sha256 search, complete, no errors). The run stays `retained_weights_missing_dependencies` and awaits user disposition. The remaining FEWS NET boundary catalog (G-3) is still open.

## Remaining package work

| Family | Versions | Next |
|---|---|---|
| AlphaEarth supervised partition | 16 | Builder bound to `runs:/9939…/source_code` (uncommitted code identity); B2/G coefficients from `predict/contexts_hXX.json`; Linux lock xgboost 3.2.0 |
| IPCCH forecasting (12 source keys) | 126 | Recover xgboost version from booster metadata; somalia_oracle families have no saved predictions (reference gap to resolve); constant-model fits to check against `model_inventory.csv` |
| FEWS NET | n/a | G-3 catalog; disposition for `scen-b43ef6a-v1` |
| Missing-weight families (80 versions) | 80 | Tracking-only records, disclosed |

## Update 2026-10-16 02:51:43 EDT: AlphaEarth packages and identity-bound receipts

- **Code:** native commit `bf3da00`.
  - `research_cloud/packages/alphaearth.py` (+ `build_alphaearth.py`) adds AlphaEarth packages.
    - Arms: B0 on compact296; B1 on 296 + 128 descriptors attached by admin_code under the frozen descriptor contract; B2/G as `CorrectionFit.from_record` of the B1 raw output per block.
    - G is `b2_reuse` at every lead; no map was selected. A selected map would remain an explicit gap.
    - Unit resolution requires exactly one distinct request-ledger identity per serving arm/block, and agreement with the saved predictions' own `B0_identity`/`B1_identity` on every served row. Reference units are taken from the saved predictions.
    - The loader is vendored from `runs:/9939…/source_code` (recorded code identity: uncommitted 57ca2ef1 + 385a8db8).
    - Runtime: Linux xgboost 3.2.0 / numpy 2.4.4 / pandas 3.0.3, the same as the original lock.
    - All saved h01–h12 prediction rows are routable. No non-routable row exists to sample, so that path is validated by the loader's contract tests, not by historical reference rows.
  - Replay receipts now record the `package.json` sha256. `research_cloud/packages/summarize.py` and the registry ledger accept a pass only when it matches the current package (`packaged_replay_stale` otherwise; tested).
  - Tests: `test_packages_alphaearth.py` (6: conflicting/mismatched identities, descriptor contract) and the stale-receipt test in `test_registry_ledger.py`.
- **Replay round `replay-bf3da00/`:**

| Family | Packages | Status |
|---|---|---|
| GeoXGB P6 | 8 | complete, pass |
| GeoXGB yearly | 12 | complete, pass |
| AlphaEarth | 16 | complete, pass |

  In total 36 packages, **36 pass, 0 stale**, 15,558 reference rows, maximum error ≤ 2.2e-16, 0 routing mismatches, 0 phase changes, 1.89 GB of packages.
- **Ledger** (`ledger/registry_ledger.json`, regenerated against these receipts): 36 packaged_replay_passed, 134 weights_retained_package_pending (forecasting 126 + window-probe comparators 8), 72 missing_weights_tracking_only.
- All of this is local Linux/WSL evidence. Cloud-pinned container replay and download acceptance are still pending.
