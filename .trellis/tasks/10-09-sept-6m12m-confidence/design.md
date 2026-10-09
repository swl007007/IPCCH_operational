# Design — September 6m/12m with confidence; cloud confidence compatibility

Requirements and decisions D1–D17 are in `prd.md`. Paths are relative to the repo root unless prefixed `CP/` (`cloud_pipeline/`). External sources are read-only:
- `STAGE3` = `../../Google fund/Analysis/2.source_code/Step5_Geo_RF_trial/food_crisis_cluster/paper_reproducibility_package/stage3_results/`
- `RAWIPCCH` = `../../Google fund/Analysis/1.Source Data/assembled_IPCCH/raw/IPCCH_2026_completed.csv` (sha256 `ae696087…717673`)
- `TRAINER` = `../../Google fund/Analysis/2.source_code/Step5_Geo_RF_trial/IPCCH/scripts/modeling/train_export_operational_launch_production_safe.py`

## 1. Data flow

```
STAGE3 fs1/fs2/fs3 ─┐                         ┌─ regression vs september_manual h5 (fs1, scope_5m)
RAWIPCCH + TRAINER ─┼─ research/build_*_evidence.py ─┤
saved scope models ─┘                         └─ CP/bootstrap/evidence/*.csv + provenance.json
                                                   │
                       CP/bootstrap/baseline.json (13 available declarations) ── new baseline id
                                                   │
October prepared snapshot + retained ACLED/WFP (GCS, read-only, sha-verified)
                                                   │
          research/run_september_delivery.py → delivery_job-style per-system deliver(origin=2026-09)
                                                   │  (workdir outside Dropbox)
                  finalize + bundle validation in workdir (not shipped)
                                                   │
          september_manual/scopes/{6m,12m}/{fewsnet,ipcch}, scopes/shared, scopes/reports, scopes/inventory.json
```

## 2. Evidence contracts (consumed unchanged by `CP/cloud/orchestrator/delivery_outputs.py`)

Every evidence CSV carries constant identity columns: `model_package_id, horizon_months, basis, period`.

| File (`CP/bootstrap/evidence/`) | Families it serves | Payload columns | Identity |
|---|---|---|---|
| `fewsnet_6m_stage3_fs2_area.csv` | fewsnet 6m `polygon_confidence`, `country_confidence` | `polygon_id, sample_count, error_count` | `local-202604-57cb3b981198-510375f58cd8/6m`, 6, `h6_validation_error_proxy_stage3_fs2_lag8_2021_2024`, `2021-02..2024-10` |
| `fewsnet_12m_stage3_fs3_area.csv` | fewsnet 12m, same families | same | `…/12m`, 12, `h12_validation_error_proxy_stage3_fs3_lag12_2021_2024`, `2021-02..2024-10` |
| `ipcch_{0,6,12}m_resubstitution_area.csv` | ipcch `polygon_training_errors`, `country_confidence` | same | `launch_2026_04_production_safe/scope_{h}m`, h, `training_resubstitution`, `2014-01..2026-03` (0m) / `2014-01..2026-04` (6m/12m) |
| `ipcch_{0,6,12}m_resubstitution_residual.csv` | ipcch `maximum_phase` | `polygon_id, target_month, phase{2..5}_worse_residual` | same as the area file |
| `provenance.json` | — | Source paths and sha256; builder script sha256; interpreter and package versions; row/drop counts; regression results; previous baseline sha256 | — |

Exact package IDs and the actual period bounds are read from `baseline.json` / the replayed keys at build time, not hardcoded. If the observed bounds differ from the table, use the observed bounds and record them in provenance.

### 2.1 FEWS proxy builder (`research/build_fewsnet_proxy_evidence.py`)

- Input `STAGE3/georf_fs{k}/predictions_monthly.csv`. Per row, `error = int(y_pred_partitioned != y_true)`. This is the h5 rule: saved decisions, no re-thresholding.
- Group by `FEWSNET_admin_code` to get `sample_count` and `error_count`. FEWS `polygon_id == admin_code` in the delivered roster (verified at 5,718/5,718).
- Keep roster IDs only; record any dropped IDs. Polygons absent from Stage3 stay absent, and the cloud marks them `no_eligible_area_history`.
- Regression: with fs1, the counts must equal `september_manual/fewsnet/polygon_confidence.csv` `historical_sample_count` / `historical_error_count` for every polygon. A mismatch stops the task before any 6m/12m evidence is written.

### 2.2 IPCCH resubstitution builder (`research/build_ipcch_resubstitution_evidence.py`)

- Interpreter: `~/.venvs/ipcch-h5-202609` (pins equal `CP/requirements.lock.txt` numerics).
- For scope h ∈ {0, 6, 12}:
  1. Rebuild the training frame from `RAWIPCCH` with the `TRAINER` rules (`build_training_frame`/`add_targets`). Use pandas default float parsing.
  2. Assert row counts and medians equal `training_export_summary.json` and the saved package medians (already verified in `research/verify_ipcch_6m12m_training_keys.json`).
  3. Apply the saved feature contract and medians, then predict the four targets with the saved `scope_{h}m` models.
  4. Area evidence per polygon: `sample_count` = training rows; `error_count` = rows where `(phase3_worse score ≥ 0.2) != (actual phase3+ share ≥ 0.2)`.
  5. Residual evidence: `actual cumulative share − predicted score` for phase2..5 per `(polygon_id, target_month)`.
- Restrict to the delivered 6,227-polygon roster (`polygon_id == area_id`); record drops.
- Regression: rerun the same code path with h5 inputs: September bundle scope_5m models, the refreshed panel `6ab4e447…` and the saved `ipcch_training_keys.csv`, extracted to `/tmp`.
  - Counts must equal `september_manual/ipcch/polygon_training_errors.csv` exactly.
  - Residuals must match `september_manual/reports/ipcch_four_target_training_replay.csv` within `atol=1e-6`.
- Memory: read the panel with `usecols` (~5 GB peak measured); run scopes sequentially.

## 3. Cloud validator change (`CP/cloud/orchestrator/delivery_outputs.py`)

Run GitNexus `impact` on `_evidence_identity` (and its callers `area_evidence` and `residual_evidence`) before editing.

```python
# Explicitly approved FEWSNET proxies (user decision 2026-10-09): saved Stage3 research-run errors whose
# active lag approximates the horizon. Only these exact (horizon -> basis, period) pairs are accepted.
APPROVED_PROXY_EVIDENCE = {
    ("fewsnet", 6): ("h6_validation_error_proxy_stage3_fs2_lag8_2021_2024", "2021-02..2024-10"),
    ("fewsnet", 12): ("h12_validation_error_proxy_stage3_fs3_lag12_2021_2024", "2021-02..2024-10"),
}
```

- In `_evidence_identity`, a FEWS identity whose `(system, horizon)` is in the allowlist passes when its basis and period equal the allowlisted pair exactly. The existing origin bound still applies.
- Otherwise the existing rules apply unchanged: FEWS `package_validation_split` with the recorded validation period; IPCCH `training_resubstitution` ending at or before the training cutoff.
- Rejection messages name the allowlisted value.
- The basis string flows unchanged into `evidence_basis` / `country_error_basis` and into `reports/*_diagnostic_declarations.json`. That is the proxy disclosure; no new column is added.
- The offline replay (`delivery_bundle.regenerate_diagnostics`) shares this validator, so frozen bundles re-validate identically.
- Tests (`CP/tests/cloud/test_delivery_outputs.py`):
  - Accepted: allowlisted 6m and 12m.
  - Rejected: fs2 basis at 12m; correct basis with the wrong period; the h5 basis at 6m; any proxy at 0m; an unknown basis.
  - Unchanged: IPCCH accepted, and the existing `package_validation_split` path.

## 4. Baseline binding (`CP/bootstrap/baseline.json`)

- `baseline.json` has no builder. Edit it with a small script, `research/bind_baseline_evidence.py`. Before writing, the script records the old sha256 and checks that only `files` (append evidence entries with size/sha256) and the 13 `delivery.diagnostics` entries change.
- An available entry has the shape `{"system", "horizon_months", "family", "status": "available", "evidence": {"local_path": "evidence/<file>"}, "evidence_model_package_id", "evidence_horizon_months"}`, matching what `pipeline.initialize` validates (`pipeline.py` ~421-436).
- FEWS 0m keeps both families `unavailable/missing_evidence`.
- Validate locally through the existing operator CLI tests and a fake-service `initialize` (the `tests/test_operator_cli.py` pattern). The new baseline must pass `_diagnostics()`.

## 5. September-origin run (`research/run_september_delivery.py`)

- **Workdir:** `~/work/sept-6m12m-20261009/`, on the Linux filesystem, to avoid Dropbox EIO.
- **Inputs:**
  - Download `prepared/full-window-20261008c/` (prepared manifest, features and families it references) and the October retained ACLED/WFP snapshots with `gcloud storage cp`. Verify each sha256 against `prepared_manifest.json` and the October run manifest refs.
  - Models, assets, census, geometry and evidence come from `CP/bootstrap` (verified against `baseline.json`).
- **Request:** build a local request equivalent to `pipeline.run` from the new baseline. Set `origin_month=2026-09`, run_id `sept-6m12m-20261009a`, ACLED/WFP keep, and diagnostics from the new baseline as local pinned refs.
  - Structural validation (`validate_delivery_request`) and `verify_reference_identities` must pass, through a `LocalPinnedReader` index.
  - The prepared manifest's origin label (2026-10) differs from 2026-09; the content is ≤ 2026-08. Local `deliver` does not check origin. Record the label difference explicitly in `reports/september_run.json`, and do not edit the prepared manifest.
- **Execution:** one process per system through `delivery_job.run_system` (bounded memory), then `finalize` and the `package_delivery` validation/inventory/archive build inside the workdir. The archive is a validation gate only; it is not shipped (D16).
  - If `package_delivery` cannot run without cloud-only parameters, use `finalize` plus `write_inventory` validation and record which steps ran.
- **Expected outputs:** for horizons 0/6/12, targets 2026-09 / 2027-03 / 2027-09; 15 scope tables per system. Only 6m/12m are published.

## 6. Publication (`september_manual/scopes/`)

```
september_manual/
  README.md            # + "September-origin 6m/12m" section (git-tracked)
  inventory.json       # unchanged (h5)
  ...h5 root files unchanged...
  scopes/
    6m/{fewsnet,ipcch}/*.csv      # same file set as October scopes/6m
    12m/{fewsnet,ipcch}/*.csv
    shared/{fewsnet,ipcch}/country_population_reference.csv, polygons.geojson
    reports/  delivery.json, september_run.json, diagnostic_availability.csv (6m/12m rows only),
              {system}_diagnostic_declarations.json, {system}_assembly.json, fewsnet_normalization_audit.json
    inventory.json                # sha256/size of every scopes/ file + run provenance
```

- Copy with a script that writes to a temporary sibling, verifies hashes, then renames into place.
- Root h5 files are checked against `september_manual/inventory.json` before and after.
- `diagnostic_availability.csv` is filtered to horizons 6/12 (D11). The unfiltered original stays in the workdir.
- If the feature-fill audit CSVs are large (> ~50 MB), keep them in the workdir; the inventory records their hash and location.

## 7. Handover archive and docs

- `python deploy/handover_package.py build --archive dist/cloud_pipeline-20261009.tar.gz`, then `verify`. The old archive is untouched.
- Run with the frozen environment from `CP/`.
- Docs:
  - `CP/OPERATIONS.md`: diagnostic evidence status per system/horizon and the FEWS proxy allowlist.
  - `CP/README.md`: one line in the bootstrap description.
  - `september_manual/README.md`: new section.
- Specs:
  - `.trellis/spec/backend/monthly-delivery-contracts.md` §8: proxy allowlist and evidence binding.
  - `.trellis/spec/guides/cloud-handover-layout.md`: `september_manual/scopes/` and the archive naming.
  - `.trellis/spec/backend/local-migration-package.md`: September layout.

## 8. Compatibility and rollback

- Model packages are not touched, so their identity and acceptance are unchanged.
- The baseline ID changes by design (D8). No destination work_dir has been initialised from the old baseline (handover not deployed).
- **Rollback:** restore `baseline.json` from the old archive (its old sha256 is in provenance), delete `bootstrap/evidence/` and `september_manual/scopes/`, and revert the commit.
- The October fallback and the old archive remain the accepted references throughout.

## 9. Risks

| Risk | Mitigation |
|---|---|
| IPCCH replay mismatch (float parsing, column order) | Builder regression on h5 must pass exactly before 6m/12m; medians assertion per scope |
| FEWS OOM | Per-system process; 15 GB available vs 7.4 GB measured peak; use the `fewsnet_checkpoint` if needed |
| Dropbox EIO during writes | Workdir on the Linux FS; staged copy plus hash verification; retry reads |
| GCS objects changed | Generation and sha256 verification; fail closed |
| WSL git DrvFS errors | Use Windows Git per spec if WSL git fails |
