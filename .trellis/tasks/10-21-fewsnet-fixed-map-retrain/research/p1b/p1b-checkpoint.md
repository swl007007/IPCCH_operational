# P1b/P2 checkpoint: input freeze, runtime, full-data code (2026-10-22 05:53Z)

Executor session bfb1fb18. No production-data model has been fitted; no production pointer/default/fallback or
shared runtime changed. Staging `S=/home/swl007007/projects/food-crisis-research/staging/fewsnet-fixed-map-retrain-20261022`.

## 1. Frozen fit input (`input-freeze.json`)

- Normalized panel `S/panel/v1/FEWSNET_versioned_panel_20261022.normalized-v1.csv` sha
  `e2ddba022aa0…` (1,149,318 rows = 5,718 areas × 2010-01..2026-09; latest label 2026-06),
  audit `c5b83faf…`, produced by the unchanged `normalize_panel` from source panel `4e6b93f2…`.
- Base: bootstrap `history_panel.csv` `ddcd30f2…`. Provenance (`bootstrap_vs_training.json`): equal to
  the April training panel `510375f5…` on every key and on 66/88 columns; differs only in ACLED
  2025-05..07 (16,061 rows) and WFP 2025-02..2026-04 (55,834 rows) = the September
  `refresh_h5_inputs` overlay from `wfp_data_7.22.26.csv` and `ACLED Data_2026-07-22.csv`
  (events 2025-05-01..2025-07-22; archive `10-07-october-cloud-delivery/research/raw-upload-contracts.md`).
- Change ledger `change_ledger.csv.gz` `0fe55eaa…`/586,031 keyed cell changes; builder verifies zero
  base cells changed without a ledger entry (`panel_build_report.json`).

| Family | Applied | Kept / reported (not applied) |
| --- | --- | --- |
| Labels | cleared 2,632 proven fills; attached 5,109 (2024-10 350, 2025-10 351, 2026-02 369, 2026-06 4,039) | other label columns untouched |
| EVI | +22,864 cells (2026-05..08) | 2025-10..2026-04 overlap: 40,012 cells, 2025-10..03 ≈99% exact; 2026-04 differs (kept). **2026-09 pending** (EE has 2026_09_01) |
| FLDAS Rainf/Tair | +20,524 each (2026-05..08); **2026-04 proven carry-forward replaced** for 5,131 areas (every area's 2026-04 = 2026-03); 587 uncovered areas unchanged | Tair overlap p90 |Δ| 0.46 |
| VIIRS | nightlight (= VIIRS **sum**, see §4) and sd +22,476 (2026-05..08) | nightlight overlap median |Δ| 0.24 |
| GOSIF | v3 2025-01..12: +65,928 cells (5,494 areas/month), v2 history kept | snapshot v2 2024-12 vs panel: 123/5,494 exact, median |Δ| 0.31 |
| WFP (FEWS MoM, HDX 2026-10-19 → existing `wfp_aggregates`) | +36,785 cells (MoM era ≥2025-02 gaps + 2026-05..09) | 64,661 overlap cells vs VAM-derived: median |Δ| 2.79; pre-2025-02 gaps (589,425 cells / 2,719 country-months) **not filled**: historical values there are a different level-type definition (April training panel: ETH 2450.9, SSD 1943.4, YEM 551.0, ZWE 4591.9) |
| ACLED (API 2026-10-22, all provider timestamps ≤ 2026-10-21 per supervisor receipt) | 2025-01..06 gap rows filled 4,862 (Apr 2,140); 2025-07 truncated month replaced (5,381 matched); 2025-08/09 appended (10,476) | 26,658 existing rows kept (battle counts 87.5% exact); ≤2024-12 outside pull; ≥2025-10 incomplete/unavailable |

Eligibility (`eligibility_preview.json`, existing builder + `align_horizon`, no fitting):
0m 273,353 rows / 54 target months (2010-01..2026-06; 224,570 vs 48,783); 6m 264,005 / 52;
12m 254,291 / 50. Exclusions are only absent/null targets.

## 2. Runtime

- Fitting env `~/.venvs/fewsnet-fit-lock-20261022` (Python 3.12.3): all 57 lock pins match,
  `pip check` clean; supervisor receipt `supervisor-fit-runtime-verification.json`. Operator venv
  untouched. Test env `~/.venvs/fewsnet-test-lock-20261022` = same lock + pytest only.
- Clean source snapshot: worktree `S/fit-source-ff389b1` at commit `ff389b1`, checked out with a
  process-scoped attribute (`GIT_CONFIG_*` → `core.attributesFile` = `S/runtime/fit-checkout.gitattributes`,
  `eol=crlf` for the partition map only). Reason: the committed map is LF (`4d94772f…`), while the
  approved asset hash `4723cae5…` is the CRLF bytes. Result: map `4723cae5…`, contract `3779c6bc…`,
  lock `2f0a7251…`, `git diff` clean. No repo config written; the 73 pre-existing files untouched.
- Runner preflight (no fit) passed: suite `full-202610-ff389b11af93-e2ddba022aa0`
  (`S/runtime/fit-preflight-ff389b1.json`).

## 3. Full-data code (commit `ff389b1`)

`core/training.train_full_history_model` (all rows, fixed threshold, no split/search, reports
`fit_mode=all_eligible_history`, `evaluation=none`); `core/validation` schema-dispatched full-data
training report and fixed-threshold report (legacy branches unchanged, shared checks extracted);
`local/package` full-data manifest schema `local-model-package-full-data.schema.json`
(`full-` suite prefix, no validation range); `local/runner.run_full_history_fit` (+ fit keys per horizon,
optional spawn pool across horizons). GitNexus impact: CRITICAL upstream for both validators
(delivery scoring, pipeline initialize/models, offline bundle) — mitigated by additive dispatch.
Tests: `tests/fewsnet_partitioned_rf/` guarded suite 10 passed (RF.fit/SMOTE forbidden; supervisor
reran). An earlier 49-pass run executed real RF/SMOTE fits on synthetic fixtures inside unit tests;
superseded, not production fitting. Remaining consumers needing the full-data variant (P3):
`delivery_outputs.fewsnet_validation_period`, `delivery_bundle` 326/452.

Prepared fit command (not run):
`cd S/fit-source-ff389b1/cloud_pipeline && GIT_CONFIG_* … fewsnet-fit-lock python -c "run_full_history_fit(FullHistoryFitConfig(<frozen panel/audit>, origin 2026-10, label 2026-06, output S/fit, max_workers=3))"`.

## 4. Decisions / escalations

1. **Nightlight contract defect (pre-existing, release-relevant).** The FEWS panel/model history uses
   VIIRS zonal **sum** (panel/avg_rad__sum median 1.000, 35–41% exact on 2025-10..03), but
   `cloud/batch/remote_sources.MODEL_COLUMN_MAPPING["fewsnet"]["nightlight"] = "avg_rad__mean"` (≈44× smaller).
   The delivery overlay therefore fed mean-scale nightlight to FEWS for months after the history
   vintage in the accepted October run. Panel assembly here uses sum. Fixing the mapping for the new
   release needs a decision (contract change + new snapshot).
2. Inference snapshot: needs EVI 2026-09 and GOSIF v3 vintage 2025-12 (otherwise `remote_overlay`
   clears 2025 GOSIF and EVI 2026-09); plan a real preparation run under a v3-aware contract after (1).
3. WFP pre-2025-02 gaps and FLDAS 2026-04 carry-forward replacement as above — confirm.
