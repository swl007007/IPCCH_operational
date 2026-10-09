# Research: cloud diagnostics path, evidence binding, September-origin feasibility

- **Query**: How cloud delivery populates (or blanks) confidence/diagnostic columns; where per-horizon evidence would live and how it binds to accepted packages; whether an O=2026-09 6m/12m run is feasible with existing code; where September 6m/12m output would be organised.
- **Scope**: internal (cloud_pipeline runtime, bootstrap, fallback, september_manual bundle, archived task evidence, legacy archive, external IPCCH trainer repo)
- **Date**: 2026-10-09

Paths below are relative to `cloud_pipeline/` unless they start with `.trellis/`, `september_manual/` or `../`.

---

## 1. Diagnostics code path in cloud delivery

### 1.1 Call chain

| Step | Location | What it does |
|---|---|---|
| Baseline declarations | `bootstrap/baseline.json` -> `delivery.diagnostics` (15 entries) | All 15 (fewsnet 2 families x 3 h; ipcch 3 families x 3 h) are `{"status":"unavailable","evidence":null,"reason":"missing_evidence"}` today. |
| Init | `pipeline.py:355 initialize()`, lines ~421-436, 469-475 | Available entries carry `evidence.local_path` (must be in `baseline.files`, prefix allowlist `assets/ models/ evidence/` at `pipeline.py:377`); on `--execute` rewritten to the uploaded GCS ref `{uri,generation,sha256}`. `_diagnostics()` validates. Saved into `initialized.json` `delivery.diagnostics` and per-model `model_versions/<sha>.json` `diagnostics`. |
| Run request | `pipeline.py:618 run()` | `request = copy.deepcopy(init["delivery"])` -> diagnostics copied verbatim into `run_manifest.json`. |
| Request validation | `cloud/orchestrator/delivery_manifest.py:260 _diagnostics()` | Requires every (system,horizon,family). Available: exact keys `system,horizon_months,family,status,evidence,evidence_model_package_id,evidence_horizon_months`; `evidence` is a gs:// pinned ref; `evidence_horizon_months == horizon`; `evidence_model_package_id == models[(system,h)].package_id`. Unavailable: `evidence: null`, reason in `UNAVAILABLE_REASONS` (line 48). |
| Ref hash check | `delivery_manifest.py:151 iter_object_refs` / `:173 verify_reference_identities` (called in `delivery_job.py prepare_inputs`) | Every available evidence object must exist at its generation with matching sha256. |
| Bytes into deliver | `cloud/orchestrator/deliver.py:54 request_diagnostics()`; called from `delivery_job.py run_system()` (~line 299) | Reads pinned bytes (`read_pinned`) per system -> `{horizon: {family: {status, ref, evidence_model_package_id, evidence_horizon_months, evidence_bytes}}}`. |
| Per-scope | `deliver.py:352 _write_scopes()` lines 376-388 | `do.normalise_declarations(...)` then `do.scope_diagnostics(...)` with `accepted_period=results["validation_periods"][h]` (FEWS) / `training_cutoff=results["training_cutoff"]` (IPCCH). Then `freeze_diagnostic_evidence()` (`deliver.py:337`) writes `inputs/evidence/{system}_{h}m_{family}.csv` and `reports/{system}_diagnostic_declarations.json`. |
| Offline replay | `cloud/orchestrator/delivery_bundle.py:424 frozen_declarations`, `:442 regenerate_diagnostics`, used by `rescore()` and `_diagnostics_regeneration_checks()` | Re-runs the same `scope_diagnostics` from frozen declaration JSON + frozen evidence bytes. |

### 1.2 `delivery_outputs.py` (all in `cloud/orchestrator/delivery_outputs.py`)

- `DIAGNOSTIC_FAMILIES` (line 36): fewsnet `polygon_confidence`(polygon), `country_confidence`(country); ipcch `polygon_training_errors`(polygon), `country_confidence`(country), `maximum_phase`(country).
- `normalise_declarations` (line 468): absent family -> `unavailable/missing_evidence`; available requires `ref.{uri,generation,sha256}` and `evidence_model_package_id` + `evidence_horizon_months == horizon`.
- `scope_diagnostics` (line 502): each family loaded independently; `load()` checks `sha256(bytes) == ref.sha256`, parses CSV (`dtype polygon_id,target_month = str`).
- Evidence identity `_evidence_identity` (line 200): every evidence CSV must carry constant columns `EVIDENCE_IDENTITY = (model_package_id, horizon_months, basis, period)` (line 173):
  - `(model_package_id, horizon_months)` must equal the scored package id AND the declaration.
  - `basis` must equal `EVIDENCE_BASIS` (line 181): fewsnet `package_validation_split`, ipcch `training_resubstitution`.
  - `period` = `YYYY-MM..YYYY-MM`, end <= origin.
  - FEWS: period must equal the package's `training_report.json` `validation_target_month_range` (`fewsnet_validation_period`, line 191). For all three accepted FEWS packages this is `2023-10..2026-02`.
  - IPCCH: period end <= package `training_cutoff` month (`ipcch_training_cutoff_month`, line 185). Accepted package: `training_cutoff = 2026-04-01` -> `2026-04`.
- Accepted evidence CSV formats:
  - Area families (FEWS `polygon_confidence`, both `country_confidence`, IPCCH `polygon_training_errors`): `area_evidence` (line 249). Columns `polygon_id, sample_count, error_count` (`AREA_EVIDENCE_COLUMNS`, line 174) + 4 identity columns. Non-negative integers, `error_count <= sample_count`, unique `polygon_id`, every `polygon_id` must be in the current roster (`_roster_ids`, line 241). Polygons absent from the evidence stay blank (left merge, no zero fill, line ~337).
  - IPCCH `maximum_phase`: `residual_evidence` (line 268). Columns `polygon_id, target_month, phase2_worse_residual, phase3_worse_residual, phase4_worse_residual, phase5_worse_residual` + identity. `(polygon_id,target_month)` unique, roster-only IDs, finite values, `target_month` inside the declared period.
- Country and polygon families are independent. `country_confidence` uses its own area evidence file (line 539-542); it can be available while the polygon family is not.
- Rows written into `reports/diagnostic_availability.csv`: status `available` / `limited` / `unavailable`. `MAXIMUM_PHASE_STATUS` is at line 497. Polygons with `sample_count == 0` or with no row become `unavailable/no_eligible_area_history`.

### 1.3 Which columns come from current scores and which from evidence

`country_tables` (line 393) first sets every `country_confidence` column to `pd.NA` (line 415). It then overlays the evidence-derived fields and recomputes the forecast-derived fields.

- **Recomputed from current scores (populated today in October output):**
  - FEWS: `country_outcome_crisis` (population-weighted `probability_crisis >= 0.5`) and `country_outcome_crisis_threshold`, via `forecast_country_fields` in `tools/revise_h5_country_v3.py:107`.
  - IPCCH: `country_overall_phase`, `country_overall_phase_availability`, `country_overall_phase_method`, and `country_maximum_phase` (roster max of `overall_phase_pred`).
  - All country prediction aggregates and dispersions.
  - Verified in `fallback/october_2026/scopes/6m/ipcch/country_confidence.csv`: these fields are filled and all error/max-phase-proxy fields are blank.
- **Need historical evidence (blank today):**
  - All `country_error_*` columns, `country_confidence_flag` and `country_confidence_thresholds`. These come from `weighted_country_errors` in `tools/revise_h5_country_v3.py:32`, which uses exact Fraction arithmetic and population weights (FEWS `population`, IPCCH `population_estimate`). Thresholds: high <= .10 and medium <= .20.
  - FEWS `polygon_confidence.csv` fields `historical_sample_count`, `historical_error_count`, `polygon_error_rate`, `polygon_confidence = 1 - rate`, `country_error_eligible`, `evidence_basis` and `evidence_period`.
  - IPCCH `polygon_training_errors.csv` fields `training_sample_count`, `training_error_count` and `training_error_rate`.
  - IPCCH `country_maximum_phase_error_probability_proxy`, `_ci_lower`, `_ci_upper`, `_history_month_count`, `_uncertainty_status` and `_uncertainty_method`. These come from `maximum_phase_diagnostics` (line 291): complete-month residual transfer onto the current raw scores, then the >=0.2 cascade, then a PCG64(20260923) bootstrap with 10,000 replicates (`maximum_phase_uncertainty`, `revise_h5_country_v3.py:70`).

### 1.4 What is and isn't implemented

- The "IPCCH maximum-phase residual transfer is still unimplemented" remark is in `.trellis/tasks/archive/2026-10/10-07-october-cloud-delivery/research/cp3-supervisor-review.md:74`. It is a mid-CP3 statement and is now superseded: `maximum_phase_diagnostics` exists, and the same review at line 96 confirms it was implemented. `tests/cloud/test_delivery_outputs.py:206 test_maximum_phase_residual_transfer_reproduces_v3_exactly` reproduces the September v3 numbers from `tests/fixtures/september/reports/ipcch_four_target_training_replay.csv`.
- What actually does not exist anywhere in `cloud_pipeline/`: **no evidence producer**. No code computes FEWS validation-split errors, IPCCH resubstitution counts or residual fields for the accepted 0/6/12 packages. All 15 baseline declarations are `missing_evidence`.
- The FEWS September (h5) basis `h5_validation_error_proxy_stage3_2021_2024` (from `september_manual/fewsnet/polygon_confidence.csv`, built by `../legacy_archive/.../tools/revise_h5_country_v3.py evaluate_fewsnet` from Stage3 fs1 4-month-lag decisions) is **explicitly rejected** by `_evidence_identity`, because the basis must be `package_validation_split` with the period equal to the package's own validation split. Design rule: `.trellis/tasks/archive/2026-10/10-07-october-cloud-delivery/design.md` §7 lines 155-158. The September FEWS method therefore cannot be relabelled for the cloud path.

### 1.5 Existing hooks for per-horizon evidence

1. **Baseline descriptor (supported, intended)**: put the CSV under `bootstrap/evidence/...`, list it in `baseline.json files` with size/sha256, and set the `delivery.diagnostics` entry to `status: available`, `evidence: {"local_path": "evidence/..."}`, `evidence_model_package_id` and `evidence_horizon_months`. Covered by `tests/test_operator_cli.py:105-109`.
2. **`models register` with `operator-model.json` `diagnostics`** (`pipeline.py:821`; OPERATIONS.md:144-163): the entries must already be gs:// pinned refs (register uploads no evidence). The record path is `version_path(system, horizon, package_id)`. Re-registering an **already registered** package id with different diagnostics fails with `immutable model version already exists` (`pipeline.py:876`), so this route only fits new package ids.
3. **Offline bundle replay**: `delivery_bundle.rescore` replays whatever `reports/{system}_diagnostic_declarations.json` + `inputs/evidence/*.csv` say. Changing them in an extracted bundle would repopulate diagnostics on unchanged predictions, but that is no longer the sealed accepted bundle.

---

## 2. Where evidence lives, and acceptance/hash binding

- **Model package identity** (`pipeline.py:206 validate_model`):
  - `acceptance.package_manifest_sha256 == sha256(json.dumps(manifest, sort_keys=True))`.
  - Every `manifest.files` member is hashed, and the member set must **exactly** equal the required set (`seen != required` -> "incomplete package members ... extra", line 282). FEWS uses `LOCAL_PACKAGE_FILES`; IPCCH uses `model_package_manifest.json`, `training_export_summary.json` and seven `scope_{h}m/*` files.
  - `feature_schema_sha256` is also checked, as is the runtime image digest plus `requirements.lock.txt`.
  - **Adding evidence files inside a model directory or its manifest would therefore break package acceptance.** Evidence under `bootstrap/evidence/` sits outside `models/` and leaves package identity, acceptance reports and feature schema untouched.
- **Baseline identity**:
  - `baseline_id = sha(bootstrap/baseline.json)` (`pipeline.py:439`). Editing `baseline.json` (new `files` entries and changed diagnostics) changes `baseline_id`.
  - An existing initialized work dir then refuses it: `work directory belongs to another baseline` (line 444). A new work dir/init is needed, and baseline objects are uploaded under `baselines/<new id>/`.
  - `bootstrap/` and `fallback/` are members of the handover archive (`deploy/handover_package.py MEMBERS`), so the sealed handover archive/receipt from the closure task would no longer match.
- **Package ids that evidence must declare** (from `bootstrap/baseline.json models`; `score_*` in `delivery_scoring.py` produces the same strings):
  - FEWS `local-202604-57cb3b981198-510375f58cd8/{0m,6m,12m}` = `f"{suite_version}/{horizon_key}"`.
  - IPCCH `launch_2026_04_production_safe/scope_{0,6,12}m` = `model_package_id + "/scope_{h}m"`.
- **Spec rules**:
  - `.trellis/spec/guides/cloud-handover-layout.md:10`: compatible registration requires a complete package, matching schema, original environment and real package-specific acceptance.
  - `.trellis/spec/backend/monthly-delivery-contracts.md:18,62`: diagnostics must cover every system/horizon/family. Supported evidence is package/horizon-specific; FEWS uses its recorded validation period and IPCCH resubstitution ends at the training cutoff.
  - OPERATIONS.md:155: "old model diagnostics cannot be reused".

### Evidence availability for the accepted 6m/12m packages (no files found)

- **FEWS**: `fewsnet_partitioned_rf_pipeline/core/training.py:444-560` fits temporary models on 30 periods (`fit_target_month_range 2014-04..2023-06`) and predicts the 6 validation periods (`2023-10..2026-02`, 33,576 rows) only to select a threshold. `validation_probability` is **not persisted**, and the final model is refit on all 188,643 rows, validation included.
  - No saved validation predictions exist in `bootstrap/models/fewsnet/*`, in `../legacy_archive/.../Outcome/fewsnet_partitioned_rf/{reports,predictions}` or in the package files list.
  - Producing `package_validation_split` evidence means re-running the temporary fit. `RF_PARAMS.random_state=5` (`fewsnet_partitioned_rf_pipeline/config.py:14`) makes that deterministic in principle, but it is a fit.
  - Scoring the validation rows with the final model would be in-sample, which design §7 forbids.
- **IPCCH**: training keys/rows for `launch_2026_04_production_safe` are not saved in the package.
  - `training_export_summary.json` records only counts and ranges: 6m 43,551 rows, features 2013-07..2025-10, targets 2014-01..2026-04; 12m 43,551 rows, features 2013-01..2025-04.
  - The deterministic frame builder is in the external trainer `../../Google fund/Analysis/2.source_code/Step5_Geo_RF_trial/IPCCH/scripts/modeling/train_export_operational_launch_production_safe.py` (`build_training_frame`, `add_targets`). Its `training_source` is `Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv`, now legacy; `bootstrap/assets/ipcch/history_panel.csv` is the delivered equivalent and is unverified as byte-identical.
  - A replay with no fitting, analogous to legacy `replay_ipcch` / `evaluate_ipcch` (`../legacy_archive/.../tools/revise_h5_country_v3.py:277-410`), could produce counts and residuals. Period would be `2014-01..2026-04`, which passes the `<= training_cutoff 2026-04` rule.
  - Evidence rows for polygons outside the current 6,227 roster must be dropped, or `_roster_ids` rejects the file.

---

## 3. Feasibility of a September-origin run (O=2026-09, h6 -> 2027-03, h12 -> 2027-09)

### 3.1 Origin is a free parameter

- `pipeline.py run --month` sets the origin; it becomes the prepare `origin_month` (`preparation()` ~line 568) and the request `origin_month`.
- `deliver(origin=...)` is a plain argument. Targets come from `add_calendar_months(origin, h)`.
- `HORIZONS_MONTHS` is fixed to `(0,6,12)` (`delivery_manifest.py:29`; `_exact_sequence`), so a run always also emits 0m (target 2026-09).
- The `--deadline` value must still be in the future; `--cutoff` fixes the discovery vintage.

### 3.2 G1 (observations <= O)

- `last_eligible_month(O, cutoff) = min(O, last month ended before the cutoff's month)` (`cloud/batch/remote_sources.py:148`).
- `_history` (`prepare.py:411`) rejects history months after the limit. `ipcch_base_series` / `fewsnet_base_panel` (`delivery_inputs.py:130,404`) drop panel rows after O (`rows_after_origin_dropped`).
- Bootstrap baseline latest months, measured:

| Source | Month range | Latest observed month |
|---|---|---|
| `assets/{fewsnet,ipcch}/history/{evi,fldas,viirs}.csv` | 2024-01..2026-04 | 2026-04 |
| `history/gosif_*` | 2024-01..2026-04 | 2024-12 |
| `retained_acled.csv` | to 2026-04 | 2025-07 |
| `retained_wfp.csv` | to 2026-04 | 2026-04 |
| `fewsnet/history_panel.csv` | 2010-01..2026-04 | label `fews_ipc` 2026-02 |
| `ipcch/history_panel.csv` | 2010-01..2026-04 | — |

  Everything is <= 2026-09, so the baseline needs no cutting for O=2026-09.
- October prepared snapshot `full-window-20261008c` (`fallback/october_2026/replay_evidence/oct-final-disclosures.json`):
  - `provider_latest_completed_month` is EVI/FLDAS/VIIRS 2026-08 and GOSIF 2024-12, with refresh months from 2025-10. Its content is already <= 2026-09.
  - Its manifest `origin_month` is `2026-10`, so the cloud path rejects it for O=2026-09: `pipeline.py run` (line ~699) and `delivery_job.prepare_inputs` (line 181) require a matching origin. A cloud Sept run needs a fresh prepare (`run --month 2026-09 --cutoff >= 2026-10-01T00:00:00Z`, limit 2026-09). Live discovery may now also pick up 2026-09 products.
  - Local `deliver()` does not check the manifest origin; it consumes `prepared_families` / `prepared_features` directly.
  - The prepared per-family CSVs exist only in `gs://manuel-remote-sensing-oct-delivery-debug/prepared/full-window-20261008c/`. The `/tmp/oct-prepared-cache` is gone, and the compact fallback does not retain them. Whether those GCS objects survive was not verified, since it needs a cloud call.

### 3.3 Local entry points

- `.trellis/tasks/archive/2026-10/10-07-october-cloud-delivery/research/cp3_evidence/run_local_delivery.py` and `run_final_local_delivery.py` are **stale**:
  - `REPO = parents[5]` now resolves to `.trellis/tasks`, because the task was archived one level deeper.
  - Imports assume `cloud/` at repo root; it now lives in `cloud_pipeline/`.
  - Inputs are hardcoded to the moved `Outcome/model_delivery/202609_h5/...`, `model_artifacts/launch_2026_04` and `Outcome/fewsnet_partitioned_rf/...`, none of which exist in the repo now.
  - `origin="2026-10"` is hardcoded (line 41; final runner line 56), and the runner needs the `/tmp` prepared cache.
  - The pattern still works: per-system `deliver(...)`, then `finalize`, `install_runtime_and_models`, `write_inventory`, `build_archive` and relocated `rescore`.
- The supported per-system function is `delivery_job.run_system()` (`delivery_job.py` ~line 284). It maps `ipcch_panel` to `assets/ipcch/history_panel.csv`, `ipcch_template` to `assets/ipcch/fixed_features.csv`, `fewsnet_raw` to `assets/fewsnet/history_panel.csv`, `census` to `population.csv` and `geometry` to `geometry.geojson`. All of these are present in `bootstrap/`.
- Memory/runtime evidence (`PROGRESS.md`):

| Run | Wall time | Peak RSS | Outcome |
|---|---|---|---|
| IPCCH unchunked run d (line 241) | 6:54 | 7.09 GB | ok |
| IPCCH chunked run i (line 163, current code) | 8:06 | 2.54 GB | ok |
| FEWS full run d (line 244) | — | 7.42 GB | exit 137 (OOM) with ~5 GB host free |
| FEWS resume f (line 207) | 5:17 | 4.56 GB | ok (resumed run) |
| FEWS product window replay (cp3 review) | 1:07 | 1.55 GB | ok |
| Relocated rescore (line 68) | 12.7 s | 1.52 GB | ok |
| Cloud job | — | 32 GiB configured | — |

  The host now shows 23 GB total, ~17 GB available (`free -g` at research time).

### 3.4 Why September h5 used feature_month 2026-04

`september_manual` bundle `reports/approved_spec.md` (2026-09-09), §1 table:
- Prediction input month 2026-04; feature observation cutoff 2026-04; training-label cutoff 2026-04; sole horizon 5 (`X(t)->Y(t+5)`); target 2026-09.
- "月份 cutoff 约束观测和标签所指月份，并不证明这些数据在 4 月当时已经发布" ("the month cutoff constrains the months observations and labels refer to; it does not prove those data had been published in April").
- Line 147: "本次没有附带 0/6/12m 预测产物" ("this delivery includes no 0/6/12m prediction outputs").

The assembled history panels end at 2026-04, the same 2026-04 panel end seen in bootstrap. The documented reason is the agreed cutoff/assembled-panel end, not a stated provider lag. September h5 packages are distinct from cloud packages: FEWS `local-202604-55f48ee97abb-f8ad21577275` and IPCCH `20260909_refresh_v1-ipcch-404ee6eebcc7` `scope_5m`.

---

## 4. september_manual machinery and natural output location

- `september_manual/README.md` describes an accepted, replay-only delivery. `inventory.json` (`compact-manual-delivery-v1`, 20 files) records retained bytes.
- The bundle runtime `runtime/tools/run_h5_model_delivery.py:19` hardcodes `FEATURE_MONTH, TARGET_MONTH, HORIZON = "2026-04", "2026-09", 5`. It contains `train_fewsnet` / `train_ipcch` / `score` / `export` for h5 only, and `revise_h5_country_v3.py` (legacy copy, 447 lines) holds `evaluate_fewsnet`, `replay_ipcch` and `evaluate_ipcch`. **No machinery for new horizons or origins.**
- Specs:
  - `.trellis/spec/guides/cloud-handover-layout.md:3,11`: `september_manual/` is an accepted result/offline replay handover; preserve accepted result/archive bytes.
  - `.trellis/spec/backend/local-migration-package.md:38-45` "Output organization" still lists `Outcome/...` paths that were moved to `../legacy_archive/` by the closure task. It is stale relative to the current two-entry layout.
- The existing precedent for a non-monthly retained result with 0/6/12 scopes is `cloud_pipeline/fallback/october_2026/` (`compact-october-fallback-v1`): `scopes/{0m,6m,12m}/{fewsnet,ipcch}/`, `shared/`, `reports/`, `replay_evidence/`, the bundle and `retained_inventory.json`. Both `fallback/` and `bootstrap/` are handover archive members.
- No spec names a location for an extra September-origin 6m/12m result. Not found: `september_manual/scopes/` or any sibling convention.

## Caveats / Not Found

- GCS survival of the `full-window-20261008c` prepared objects and of `deliveries/oct-final-20261008a/` large inputs was not checked (no cloud calls).
- Byte equality of `bootstrap/assets/ipcch/history_panel.csv` with the IPCCH trainer's `training_source` was not checked.
- No persisted FEWS validation-split predictions or IPCCH 6m/12m training keys/residuals were found for the accepted packages.
- The legacy archive's `Outcome/manual_delivery/*/inputs` was not found at the expected depth.
