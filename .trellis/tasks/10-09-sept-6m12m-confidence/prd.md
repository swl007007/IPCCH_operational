# September 6m/12m delivery with confidence and cloud confidence compatibility

## Goal

Produce September-origin 6m and 12m FEWSNET + IPCCH results (targets 2027-03 and 2027-09) with confidence diagnostics populated using the same method as the accepted September h5 manual delivery. Make the cloud pipeline populate the same confidence columns instead of leaving them blank.

## Source request (user, 2026-10-09)

> manuel 9月份需要同时用相同方法生成6m和12m的结果（即target 2027年3月和2027年9月，同时也要所有的confidence行等），可能得重新run一下model并且整理一下output。cloud pipeline这边，需要和manuel的output兼容，也就是manuel output的column里面新增的confidence等。

## Observed baseline (2026-10-09)

- `september_manual/` is the accepted h5 delivery (feature_month 2026-04 → target 2026-09). Its confidence columns are populated:
  - FEWS `polygon_confidence.csv` / `country_confidence.csv`, basis `h5_validation_error_proxy_stage3_2021_2024`.
  - IPCCH `country_confidence.csv` (basis `training_resubstitution`, plus the maximum-phase bootstrap block) and `polygon_training_errors.csv`.
- `cloud_pipeline/fallback/october_2026/scopes/{0m,6m,12m}/` has CSV headers identical to September's (the population reference lives under `shared/`). Every evidence-derived confidence column is blank. All 15 `bootstrap/baseline.json` diagnostic declarations are `unavailable/missing_evidence`.
- The cloud code can already compute every confidence column from supplied evidence (`delivery_outputs.scope_diagnostics`). It lacks the evidence files and a basis for the FEWS proxy evidence. Compatibility therefore means populated values under the existing columns, not new columns.
- Research: `research/confidence-evidence.md`, `research/cloud-diagnostics-and-origin.md`, `research/verify_ipcch_6m12m_training_keys.{py,json}`.

## Confirmed decisions (user, 2026-10-09)

| ID | Decision |
|---|---|
| D1 | "manuel" means the accepted `september_manual/` delivery. |
| D2 | Origin O = 2026-09; horizon 6 targets 2027-03 and horizon 12 targets 2027-09. Inputs follow the October cloud rules: O is fixed, only observations ≤ O are used, and approved causal fill applies. Reuse the October prepared snapshot `full-window-20261008c` (content ≤ 2026-08) and the October ACLED=keep / WFP=keep retained snapshots. |
| D3 | "Re-run model" means inference/replay only with the accepted model scopes. No retraining; accepted package identities stay unchanged. |
| D4 | **FEWS 6m/12m evidence** is a Stage3 research-run proxy, computed as in September h5: per polygon, saved partitioned decision ≠ `y_true` over 2021-02..2024-10. 6m uses `georf_fs2` (8-month lag); 12m uses `georf_fs3` (12-month lag).<br>**IPCCH 0m/6m/12m evidence** is `training_resubstitution`: replay the saved scope models on training rows rebuilt from the original training panel `IPCCH_2026_completed.csv` (sha `ae696087…`), not the refreshed bootstrap panel. Includes the maximum-phase complete-month residual block. |
| D5 | September outputs go to `september_manual/scopes/{6m,12m}/{fewsnet,ipcch}/`. Accepted h5 root files stay byte-identical. The new files get their own inventory and the README gains a section. |
| D6 | Scoring runs locally through the cloud delivery code with origin 2026-09. October prepared and retained inputs are downloaded read-only from GCS and their identity is verified. |
| D7 | The cloud pipeline populates confidence for FEWS 6m/12m and IPCCH 0m/6m/12m. FEWS 0m stays `unavailable/missing_evidence`. |
| D8 | Evidence is bound as `cloud_pipeline/bootstrap/evidence/*.csv` with available declarations in `baseline.json`, giving a new baseline ID. A newly named create-only handover archive is built; the old archive is kept. |
| D9 | FEWS proxy evidence is accepted only through an explicit allowlist keyed by horizon → (basis, period): 6m → fs2 basis, 12m → fs3 basis, period 2021-02..2024-10. Any other basis/period is still rejected. The basis string discloses that it is a proxy. |
| D10 | The accepted October fallback stays byte-identical; October is not rescored. |
| D11 | The September deliverable exposes only the 6m and 12m scopes. The run's 0m output remains working-directory evidence only. |
| D12 | One code path: September results are produced by the cloud delivery code (`deliver`) using the same bound evidence that future cloud runs use. |
| D13 | The one-time evidence builders live in this task's `research/` (they read external sources). `bootstrap/evidence/` ships only the output CSVs plus `provenance.json`. The runtime never reads external or legacy paths. |
| D14 | FEWS proxy basis labels: `h6_validation_error_proxy_stage3_fs2_lag8_2021_2024` and `h12_validation_error_proxy_stage3_fs3_lag12_2021_2024`. |
| D15 | No trellis-audit. Commit only this task's code, spec, doc and task files on `feat/october-cloud-delivery`. Exclude the pre-existing CRLF-only working-tree changes. No push. Data travels in the archive, not Git. |
| D16 | No portable replay bundle for September 6m/12m. The deliverable is the scope CSVs, shared references, reports and inventory. |
| D17 | Per-scope directories only; no combined cross-horizon table. |

## Requirements

- R1 — **September-origin results:** FEWSNET and IPCCH predictions for O = 2026-09 at horizons 6 and 12, scored by the six accepted packages through the cloud delivery code with the D2 inputs.
- R2 — **Same confidence method:**
  - FEWS polygon and country confidence come from the D4 Stage3 proxies, with the h5 error definition, population weighting and 10%/20% flag thresholds.
  - IPCCH Phase3+ polygon training errors, country error/flag and the maximum-phase residual-transfer bootstrap (seed 20260923, 10,000 replicates, restarted per horizon) come from D4 resubstitution evidence.
  - Forecast-dependent fields are recomputed from the September-origin scores.
- R3 — **Builder correctness:** before producing 6m/12m evidence, each builder must reproduce the accepted h5 evidence from h5 inputs.
- R4 — **Cloud compatibility:**
  - The cloud validator accepts the D9 allowlist and the IPCCH evidence. `baseline.json` binds evidence per D7/D8. The cloud delivery path writes populated confidence columns with unchanged headers.
  - Missing evidence still yields an explicit unavailable reason, never zero or a copied number.
- R5 — **Organization:**
  - The D5 layout mirrors the October fallback: `scopes/{6m,12m}/{system}/`, `scopes/shared/{system}/`, `scopes/reports/` and `scopes/inventory.json`.
  - The September README section explains h5 (root) versus 6m/12m (`scopes/`), the origin and the evidence bases.
- R6 — **Preservation:** the September h5 root files, the October fallback, the old handover archive and the accepted model packages stay byte-identical.
- R7 — **Documentation and specs:** update the cloud docs (diagnostic evidence status) and the specs (proxy allowlist, evidence binding, September `scopes/` layout).

## Acceptance criteria

- [ ] **AC1 (R1):** `september_manual/scopes/{6m,12m}/{fewsnet,ipcch}/` contain the same per-system file set and headers as the October scopes.
  - Feature month is 2026-09. 6m rows target 2027-03 with horizon 6; 12m rows target 2027-09 with horizon 12.
  - Each table has the full roster (FEWS 5,718 polygons / 22 countries; IPCCH 6,227 polygons / 53 countries).
  - Model package IDs match `bootstrap/baseline.json`.
- [ ] **AC2 (R2):** in both scopes, populated confidence matches the evidence coverage.
  - FEWS polygon confidence is populated for every roster polygon present in the proxy (expected 5,713; the rest are blank with reasons). Country error/flag are populated wherever eligible areas exist.
  - IPCCH polygon training errors and country error/flag are populated per coverage. Maximum-phase fields follow their status rules (`no_complete_history` stays blank).
  - Basis and period strings equal D4/D14.
  - `reports/diagnostic_availability.csv` contains no 6m/12m `missing_evidence` rows.
- [ ] **AC3 (R3):**
  - The FEWS builder applied to `georf_fs1` reproduces September h5 `historical_sample_count` / `historical_error_count` exactly per polygon.
  - The IPCCH builder applied to the h5 scope_5m model and its panel/keys reproduces September `polygon_training_errors.csv` counts exactly, and the four-target residuals within `atol=1e-6`.
  - Results are recorded in `bootstrap/evidence/provenance.json`.
- [ ] **AC4 (R4):**
  - Validator tests show: the allowlisted FEWS 6m/12m proxy is accepted; a proxy on the wrong horizon or with the wrong period, the h5 basis and an unknown basis are all rejected; IPCCH 0/6/12 resubstitution is accepted.
  - `baseline.json` has 13 available declarations and 2 unavailable (FEWS 0m).
  - `python -m pytest tests/cloud tests/test_refresh_h5_inputs.py tests/test_operator_cli.py` passes. Any pre-existing failure is reported with its output, not hidden.
- [ ] **AC5 (R4/R6):**
  - A new archive `dist/cloud_pipeline-20261009.tar.gz` is built and passes `handover_package.py verify`.
  - The old `dist/cloud_pipeline.tar.gz` is unchanged.
  - The October fallback files match `retained_inventory.json`, and the September root files match `inventory.json`.
- [ ] **AC6 (R5/R7):** README, OPERATIONS and the specs are updated, and the D15 commit is made after `detect_changes`.

## Out of scope

- Retraining or refitting any model, including temporary FEWS validation fits.
- Rescoring the October fallback, live cloud deployment, cutover or push.
- A FEWS 0m proxy; a portable September bundle; combined cross-horizon tables.
