# CP0 model/environment/lineage evidence

Executor: Claude Opus 5.5 (1M), Herdr `wR:p3`, session `e8ac76ab-3486-4e51-b70c-ed09b2846fc7`; supervisor Codex `wR:p1`. Date 2026-10-07. Branch `feat/october-cloud-delivery` (set by supervisor), HEAD `4a42f1f666a4f2d5d2616069fe25ddd81f2662cb`. No product code changed, no training, no cloud operation.

Status: factual findings for supervisor review. Nothing here accepts a model, a runtime or a lineage.

## 1. Runtime environment (T2)

| Candidate | Python | Pins vs FEWS manifests + XGBoost 3.2.0 | Notes |
|---|---|---|---|
| `~/.venvs/ipcch-h5-202609` | 3.12.3 | Exact: numpy 2.4.2, pandas 3.0.0, scikit-learn 1.8.0, joblib 1.5.3, imbalanced-learn 0.14.0, xgboost 3.2.0, scipy 1.17.0, geopandas 1.1.1, pyarrow 20.0.0 | Equals September v3 `requirements.txt`; created 2026-09-23. No pytest and no rasterio. Freeze in `cp0_evidence/ipcch-h5-202609.freeze.txt` (44 pkgs, sha256 `2561e8e9…28f5`). |
| `ipcch-xgb`, `ipcch-xgboost` | 3.12.3 | Same core pins but **no imbalanced-learn** | FEWS loader `assert_runtime_compatible` would refuse them. |
| `ipcch-geo`, `ipcch-mlflow` | 3.12.3 | Newer numpy/pandas/sklearn | Incompatible with FEWS manifest pins. |
| system `python3` | 3.12.3 | pandas 3.0.0, numpy 2.4.2, pytest 7.4.4 | Not a pinned environment. |

**imblearn import failure (exact cause).** A bare `import imblearn` fails in the frozen venv. imbalanced-learn 0.14.0 `imblearn/utils/_sklearn_compat.py:256-259` imports the private `sklearn.utils.validation._is_pandas_df`, which scikit-learn 1.8.0 exposes only as public `is_pandas_df`. Its declared requirement `scikit-learn<2,>=1.4.2` does not exclude 1.8.0. This pinned pair is what trained the packages, per the manifests and `run_summary.json`.

Existing handling: `fewsnet_partitioned_rf_pipeline/core/training.py` `_load_smote_type()` adds `_is_pandas_df` and an AdaBoost `algorithm` bridge on the main thread only, imports SMOTE, then restores both. It was present at package source commit `57cb3b9`. Importing `fewsnet_partitioned_rf_pipeline.local.package` in the frozen venv succeeds, and afterwards `_is_pandas_df` is absent again. Inference does not use imblearn. The loader's `assert_runtime_compatible` compares installed distribution versions only.

Options:
1. (Recommended) Use `ipcch-h5-202609` unchanged for model load/scoring/replay. Nothing is patched, the runtime checks stay enabled, and no version is substituted.
2. Tests need pytest, which the frozen venv lacks. Proposed task-scoped venv `~/.venvs/ipcch-october-cloud`: Python 3.12.3 plus the exact September v3 `requirements.txt` pins (numpy 2.4.2, pandas 3.0.0, scipy 1.17.0, scikit-learn 1.8.0, imbalanced-learn 0.14.0, joblib 1.5.3, xgboost 3.2.0, geopandas 1.1.1, pyarrow 20.0.0, pycountry 26.2.16, jsonschema 4.26.0, google-cloud-storage 3.13.0) + pytest 7.4.4. Add rasterio 1.3.9 only when CP2 raster tests need it. Record its freeze diff against the frozen venv. Not created; awaiting approval.
3. Not proposed: upgrading imbalanced-learn or scikit-learn, patching site-packages, or disabling `assert_runtime_compatible`.

## 2. Bounded candidate-package diagnostic (not a passing validator)

Script `cp0_replay_candidates.py`. It always exits 0, and the counts must be read from `cp0_evidence/cp0_replay_report.json` (sha256 `9ecb9171…9e85`). Environment: frozen venv above.

**FEWS (`local-202604-57cb3b981198-510375f58cd8`)**: load/identity only, per the supervisor timebox. All three packages pass `load_local_model_package(..., expected_panel_sha256=510375f5…)`: checksums, manifest, contract, partition, reports, runtime pins, `PartitionedRFPredictor` identity. They contain 123 features and a `MaxPlusImputer`, with feature month 2026-04 and latest label 2026-02. Package-specific thresholds: 0m 0.48, 6m 0.41, 12m 0.45, so h5's 0.43 does not apply. model.joblib sha256: 0m `63703184…d08f`, 6m `aa5f80be…bc8`, 12m `47cba49d…1e0e`. **No frozen-input prediction replay yet.** The 773 MB panel replay is deferred.

**IPCCH (`launch_2026_04_production_safe`)**: scored with `run_scope`, the production path, on input `Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604.csv`. Its sha256 `bc96b23d…ec92d` equals the input hash recorded in `run_summary.json`. Results across scopes 0/6/12:
- 6,227 rows per scope, `area_id` order identical.
- Phase2/phase3 scores: all values within atol 1e-12 (rtol 0).
- Every binary `phaseN_worse_pred` and `overall_phase_pred` is identical (0 mismatches).
- Phase4 and phase5 differ only where the replay is negative and the saved value is exactly 0. There are no other differences (`unexplained_mismatches` = 0).

Saved-file provenance for that difference: `Outcome/ipcch_unified/predictions/202604/nonnegative_score_correction_summary.json` (sha256 `70fd86a3…a621`) records `operation: negative_phase_worse_scores_clipped_to_zero` and `area_changed_by_column` phase4 = 85, phase5 = 8,013, total 8,098. Its inventory hashes equal the current saved CSVs. The replay's negative counts reproduce those totals per column: phase4 41+34+10 = 85, phase5 2,058+1,973+3,982 = 8,013. The recorded preclip backup `/tmp/ipcch-predictions-202604-preclip.GpjtMr` no longer exists, so a byte-level raw comparison is not possible.

Implication: saved April IPCCH area CSVs, and the country outputs rebuilt from them, are a **post-processed** baseline. The October raw-score semantics stay unchanged (no clipping), so those clipped files cannot serve as a raw-score parity reference. The IPCCH run summary does not record its Python/library environment. Exact replay in the frozen venv supports, but does not by itself establish, environment acceptance.

Saved baseline identities:

| File | sha256 |
|---|---|
| FEWS `predictions/202604/…scope_0m_predictions.csv` | `7c21f94485a5fdcab7088828ded2269dd25d706cd4b25957af4194552071dcb6` |
| FEWS `…scope_6m_predictions.csv` | `1961d0cfc01d5352dfedcc158e395e1a8ec2c0b7d698aa1ba48ca3ac22fceb68` |
| FEWS `…scope_12m_predictions.csv` | `e9f53600dab0cad14674b40e4586caf6d3a5a8e71874d6f4c18102b64458b3d1` |
| FEWS `run_summary.json` | `e574aac26fa2630dd46e9efad95bdc428dd91b9230de42dd9f34de4eba7abb1e` |
| FEWS panel (external and `Outcome/fewsnet_partitioned_rf/raw/` copy, not rehashed at CP0) | recorded `510375f58cd835e694b6e287cce9439bbe1b6246d752daabc8151df8ffdda61d` |
| IPCCH `ipcch_launch_202604_scope_0m_predictions.csv` | `d69cd9dc354b5e61096ef87615bcc93390211464b69d30f2b128aaed64f68cd8` |
| IPCCH `…scope_6m_predictions.csv` | `89a96ea235533f20198ed22481a37ad59061f178ec5692af70595ae630ad35d6` |
| IPCCH `…scope_12m_predictions.csv` | `764514928447754f6c47cf42d3bfce6d2da02d4e720a52a47e52875c6497ff70` |
| IPCCH `run_summary.json` | `9a09db2b7078cc6c47ef52dbe1d0989ad5627a7475fb14aee000f512d8d3bcd9` |
| IPCCH input `ipcch_monthly_base_input_202604.csv` | `bc96b23d74c22d9e2e55fcb7e8d693b2dc978cb63a0a3e0fe92ec946443ec92d` |

Per-file IPCCH package hashes for every scope are in the JSON report.

## 3. Lineage (T1): unchanged, precise blockers

No new lineage evidence was collected at CP0; `model-and-lineage-acceptance.md` §§3–4 still applies. Blocked adapter branches:
- IPCCH FLDAS, GOSIF-GPP mean/SD and VIIRS SUM/STD: legacy extractors key on `fid`, while the current geometry has only `admin_code,lat,lon`, and no verified crosswalk exists. CH naming/reducer is proven, but the canonical write into `IPCCH_2026_completed.csv` and the IPC-branch intermediates are not traced.
- All FEWS remote-sensing branches (EVI, climate, `gpp_mean`, `nightlight`, `nightlight_sd`): there is no keyed link from the training panel to any extractor. The FEWS geometry is a separate universe (5,718 `admin_code`, `FEWS_Admin_LZ_v3`).
- IPCCH EVI: keyed on `admin_code` in both legacy and cloud paths, so less blocked, but numerical parity is unverified, especially for SD.

Independent of T1, and therefore safe to implement: the versioned dual-system request contract; ACLED/WFP raw validation and independent keep/refresh; a generic area-scoped past-only fill engine with its audit sidecar; run-state/duplicate/release (CP4); and diagnostic-unavailable and output-inventory contracts (CP3, scoring-dependent parts later).

## 4. Remaining model/lineage acceptance (staged, not done)

1. FEWS frozen-input replay on the 773 MB panel: expect byte-identical April CSVs (hashes above). Bounded rerun is permitted later.
2. FEWS normalization extension through O (T3): quantify the change in historical zscores from the whole-table rolling operation when history is extended.
3. October feature compatibility for both systems: categorical vocabulary, calendar windows, target-lag months.
4. IPCCH environment record: freeze the replay environment as the accepted IPCCH scoring runtime, or provide other evidence.
5. External normalization audit `…normalized-v1.audit.json` (sha `1c372326…1166`) bound into model acceptance.
6. T1 canonical lineage and native-ID crosswalk, per branch, before the M3 adapters.
7. T4/T5 (provider availability, event/deploy) belong to M3/M5–M6.
