# Research: CP0 training inventory for H2/H8/H14 final-stage retraining

- **Query**: inventory of the 10-28 H0/H6/H12 training (entrypoint, cloud, MLflow, hyperparameters, horizon/cutoff/origin parameterization, 527/539 schema, GPP, inputs, counts, evidence, rules, blockers) for planning H2/H8/H14 (targets 2026-01..10; cutoffs 2025-11/2025-05/2024-11; H0->H2, H6->H8, H12->H14 params; no oracle; no HPT/refit)
- **Scope**: internal (two repos), read-only
- **Date**: 2026-10-29/30
- **Status**: stopped early on Supervisor directive. Items not checked are marked UNVERIFIED/UNKNOWN.

Abbreviations: `R=/home/swl007007/projects/food-crisis-research`; `T10=R/.trellis/tasks/10-28-ipcch-ch-validity-refits`; `VF=R/control-plane/research_cloud/training/ipcch_validity_features.py`; `VP=R/control-plane/research_cloud/training/ipcch_validity_pooled.py`; `CP=R/sources/Food_Crisis_Cluster/IPCCHAlphaEarthExperiment/ipcch_alphaearth/compact.py`; `HV=R/scratch/ch-validity-20261028/harvest/formal-hHH/trial-0`; `JP=R/staging/ipcch-ch-validity-20261028/job-packet-ch`; `OP=` this operational repo.

Git note: `R` is on `task/ipcch-multilayer-h0-h6`; `R/control-plane` is a separate git repo on `task/ipcch-acledagg-hpt` (HEAD `5e94e12`). The 10-28 job did not run that HEAD as-is: it ran an image built from a three-module overlay (`dataset_input.py`, features, pooled; `JP/operation-packet.md:42`, `T10/research/final/final-report.md:20`). Overlay match VERIFIED by Executor at CP0 (2026-10-30, sha256sum): CPL working-tree `dataset_input.py` `a6d05b24759e60f4dd3e26f94c3258352ac8580b13c6f14b16571978159ece9c`, `ipcch_validity_features.py` `eace18fd6b6bdfd1304cbe9c50d034fc9f5fcc770b2edc14b5a109b000d9c0a6`, `ipcch_validity_pooled.py` `d7f78e3a8a10fd832669b67f44da9f5e5658b58147b727038961e35423030c28` are byte-identical to `R/staging/ipcch-ch-validity-20261028/image-overlay-ch/*.py` and to the hashes in `image-overlay-ch.context-record.json` (overlay manifest `3fa26b4a…`).

## 1. Entrypoint, cloud submission, MLflow, local execution, cost

- Trainer module: `python -m research_cloud.training.ipcch_validity_pooled --manifest M.json --config C.json --output DIR|gs://... [--mlflow-experiment NAME]` (`VP:27-31`, `VP:3286-3299` -> `common.run_trial`). No-fit commands: `plan` (`VP:3167`), `gate` (`VP:3234`). Dataset build: `python -m research_cloud.training.ipcch_validity_features --manifest --out [--horizon H]` (`VF:1427-1441`).
- Arm used: `validity_augmented_idp_202610_acledagg_lag1_uncal_hpt` (`VP:71`); formal path `fit -> hpt_fit -> ch_formal` when `ch_correction` is in the config (`VP:3079-3093`).
- Cloud backend: Vertex AI CustomJob (not Cloud Run Job); MLflow hosted on Cloud Run (`T10/execution-authorization.md:11`). Spec `JP/specs/spec-formal-h00.json`: project `food-crisis-modeling-enso`, region `us-central1` (RUNBOOK:3), `n1-standard-16` x1, 100 GiB pd-standard, timeout 7200 s, `disableRetries`, SA `research-trainer@food-crisis-modeling-enso.iam.gserviceaccount.com`, entry `/usr/local/bin/train-entry` with an inline launcher that reads secret `mlflow-jobwriter/versions/1`, image `us-central1-docker.pkg.dev/food-crisis-modeling-enso/research/training-ipcch-validity@sha256:2b18cf721cb09af0d1633a20087874155e8af49aa822979c0554507bcb68ccc3` (Cloud Build `3a577f07-…`, tag `gosifv3-chvalidity-20261028`; `T10/PROGRESS.md:62-65`).
- Buckets: inputs `gs://food-crisis-modeling-enso-research-inputs/training-jobs/ipcch-ch-validity-refits/r1/inputs/{manifest,config}-formal-hHH.json`; outputs `gs://food-crisis-modeling-enso-research-artifacts/trials/ipcch_validity_pooled/<job>/trial-0` (`JP/operation-packet.md:45,124`).
- Submission: `python -m research_cloud.training.vertex_submit submit --spec … --kind custom --operation … --out $W/ledger/vertex/<op>`, then `poll` (`JP/operation-packet.md:96-98`); budget ledger `$W/ledger/spend.sqlite` via packet `reserve_job.py`.
- MLflow: `MLFLOW_TRACKING_URI=MLFLOW_REGISTRY_URI=https://mlflow.weilunshi.com`, experiment `IPCCH dashboard`, `IPCCH_REQUIRE_REGISTRATION=1` (spec env). Runs: H0 `298c4718b4d64e6f8a5c315e8c22d25d` (LoggedModel `m-698519b8…`, Vertex `6867303963549499392`), H6 `00d4e94c824343bf86a0c2b79d5b9ed0` (`m-46beb4c7…`, `3518877640599535616`), H12 `f436da15c71c469199784db065f3b63b` (`m-9da8be7f…`, `8594997370599505920`); registered model `IPCCH Validity-augmented pooled (GOSIF v3 + CH validity 20261028) | …_hpt | H-month` v1 (`T10/research/final/final-report.md:30-36`). GOSIF-v3 parents: 8e076863…/ac709d28…/0bc109fa… (`T10/research/baseline.json`).
- Local execution: supported without MLflow (omit `--mlflow-experiment`, local `--output`, manifest of local paths or gs:// with generation) per RUNBOOK §10 (`control-plane/research_cloud/RUNBOOK.md:301-310`); "~15-40 min per arm/H on 16 threads". Python `~/.venvs/ipcch-geo` or `~/.venvs/ipcch-validity-idp` (the 10-28 packet used the latter as `$SCI`, `JP/operation-packet.md:28`). Whether local outputs are acceptable for the R30/R51 package handoff: UNKNOWN (policy question).
- Cost/resources (10-28): reservations USD 6.9119 of 8.00 cap: build 0.19, platform 1.00, training 3 x 1.9073 (n1-standard-16 0.8739954 USD/h x 7,800 s + PD). Provider windows H0 19.6 min, H6 15.6 min, H12 10.6 min; in-trial elapsed 1,030.9/635.0/502.3 s for ALL contexts (4/4/3 contexts, 16/16/12 regressors). Billed actuals not asserted (`T10/research/final/final-report.md:117-121`). Final-context fit seconds q2..q5: H0 84.4/16.2/60.9/34.6; H6 27.4/16.2/24.2/19.5; H12 16.7/18.6/13.8/10.3 (`HV/package/weights/hHH_supp_2026/record.json`).

## 2. Selected hyperparameters (H0->H2, H6->H8, H12->H14)

Source of truth: freeze records `R/.trellis/tasks/10-27-ipcch-gosif2025-retrain/research/cp3/frozen-objects/freeze-h{00,06,12}.json` (sha256 dc152d4e… / fe6be936… / b094e059…; index `index.json` d85582b3…), `winner.params`; copied into config `fixed.*` (`JP/objects/config-formal-hHH.json`), `T10/research/baseline.json` and each `record.json`.

| key | H0 (trial 37) | H6 (trial 18) | H12 (trial 16) |
|---|---|---|---|
| other_n_estimators | 428 | 398 | 158 |
| other_learning_rate | 0.06530548333101606 | 0.027538515460387113 | 0.08104665643788728 |
| other_max_depth | 11 | 5 | 7 |
| other_min_child_weight | 32.0 | 23.072391682325758 | 24.92787946513128 |
| other_subsample | 1.0 | 0.6716682260833845 | 0.5456882086669544 |
| other_colsample_bytree | 0.9885187931643816 | 0.7269756250210765 | 0.6405545857296321 |
| q3_n_estimators | 357 | 346 | 313 |
| q3_learning_rate | 0.05697472381385549 | 0.08536359461483287 | 0.0493494477600518 |
| q3_max_depth | 4 | 4 | 7 |
| q3_min_child_weight | 0.0 | 18.162407873411354 | 26.42570144490502 |
| q3_subsample | 0.7526468149269783 | 0.8118788081985475 | 0.7932250149956435 |
| q3_colsample_bytree | 0.4 | 0.4327978267528363 | 0.6556143377414937 |

Common fixed: seed 42, n_threads 16, half_life 24, untuned gamma 0.1 (q3)/0 (other), reg_alpha 0, reg_lambda 1, `xgb_fixed` reg:squarederror/hist/cpu/gbtree, no early stopping, identity calibration. Mapping into the trainer: `tuned_values` (`VP:1988`) -> `hpt_values` validation (`VP:1959`) -> `hpt_quartet` (q3 group vs q2/q4/q5 group, `VP:1980`) -> `fit_quartet`/`xgb_params` (`VP:1067-1087`). `check_hpt_config` requires `frozen.params_sha256 == digest(values)` (`VP:2083-2130`); `verify_freeze_inputs` requires `freeze.horizon == config.horizon` and an index listing exactly horizons {0,6,12} (`VP:2524-2550`).

## 3. Horizon / target / cutoff / origin parameterization

- `VF:40 HORIZONS=(0,6,12)`; `base_features` raises unless `h in HORIZONS` (`VF:1086-1087`). `VF:52 EXPECTED_FEATURES={0:424,6:436,12:436}` keyed by horizon; `expected_features` (`VF:910`).
- `VP:83 HORIZONS=(0,6,12)`; `MAIN_FIRST` keyed 0/6/12 (`VP:85`), `PROVIDER_FIRST` (`VP:88`); `schedule_from_config` requires `main_first` for every horizon in HORIZONS (`VP:279`) and a non-empty main window (`VP:350`); `check_hpt_config` requires horizon in HORIZONS and the fixed calendar `MAIN_FIRST/MAIN_LAST/ACLED_SUPPLEMENT(2026-01..10)/blocks` (`VP:2083-2100`); `plan_main --horizon choices=HORIZONS`.
- `CP:43 HORIZONS=(1,3,6,12)` and `validate_horizon` (`CP:99-102`), used by `label_cutoff`/`build_safe_history`/`build_idp_features` (`CP:105,550,651`). The validity path uses `cp.monthly_block` (`CP:426`, no horizon validation) and `vf.history_block`/`vf.idp_block` (own implementations), so CP's validator is not on the validity path (UNVERIFIED for every call site).
- Origin: `origin = target - h` (`VF:1092`; `CP:430`). H0 origin = target month T itself. Cutoff: `fit_cutoff` = T0-1 at H0 else T0-H (`VP:210-213`). With T0=2026-01 this yields 2025-11/2025-05/2024-11 for H=2/8/14, equal to R4. History bound `T - max(H,1)` (`VF:718-720`) = O for H>=1.
- Eligibility rule per context: `target <= cutoff & avail <= cutoff & not in S_E` (`VP:500-540`).
- Conclusion: no existing parameter accepts 2/8/14; 0/6/12 are hardcoded in VF, VP, the freeze index check and recipes. Code changes are required.

## 4. Schema 527/539

- Order files: `HV/package/deps/feature_order.csv` (= `HV/dataset/feature_order_hHH.csv`); H0 527 rows sha256 `b6c7f2f8…`; H6 and H12 539 rows, byte-identical (sha256 `b02af20f…`).
- Verified: H6 order with the 12 `oracle_*` names removed equals H0 order exactly (same order). Oracle columns (H6/H12 positions 410-421): `oracle_{prcp_anom,tmean_anom}_month_ensmean_o{1..6}`, realized at O+1..O+min(H,6) (`VF:45-46,844-846,866-875`). Construction: compact296 + AE128 + oracle, then drop 14 old conflict columns, append 114 ACLED-agg, append 3 local IDP (`VF:849-863`).
- Families in the 527 (counted from H0 order): static29; GPP_mean 13; nightlight 9; WFP_Price 13; food_price_index_WB 9; nino34 13; bbg composites 20; climate13 monthly 113; growing-season 29; identifier 27; outcome history 5; national IDP 2; AlphaEarth 128; ACLED-agg 114; local IDP 3.
- Alignment relative to O under the existing code (O=T-H): monthly interim/climate arrays use source months <= u and are gathered at O (`CP:412-438`); seasons completed by first day of O+1 (`CP:457-531`); ACLED at A=O-1 (`VF:1062-1070`); national IDP report <= O (`VF:878-900`); local IDP windows end at O (`VF:980-993`); history <= O for H>=1 (`VF:718-760`); identifier lat/lon from raw panel at the target key and month/year dummies at T (`CP:708-733`); AE2017 and static29 static. Under this reading, no non-oracle column in the 527 uses a calendar month after O. Caveat: inputs are retrospective vintages (revisions/publication timing not modeled), and CH copies use nominal reference-start availability (`T10/research/final/final-report.md:63-77`).
- `identifier_block` raises when a target year is >2026 or lat/lon is missing at the target key (`CP:724-727`); R58 expects all-zero year dummies for 2027+. Training targets (2026-01..10) are unaffected; inference and package replay for 2027 targets would hit this check if they reuse CP.

## 5. GPP in the 10-28 training data

- No availability filter: GPP_mean comes from the corrected interim (`b2d5d2ce…`, 2010-01..2025-12, 2026 blank) and is read in full (`VF:793-808`, `CP:319`). The 13 GPP features come from `monthly_feature_arrays` (full-grid arrays, value at u uses months <= u, `CP:376-438`) and `stress_signal` (`x < 0.9 * x(t-12)`, `CP:293-305`). No code mentions GPP publication or update logs (grep of training code: none).
- Where an R57 filter would act: the shared full-grid computation means one array serves every row; a per-row run-date filter would need the GPP grid masked by availability vintage before `ordinary_arrays/z_arrays/stress_arrays`, with rows gathered from their vintage's arrays (seam: `vf.load_sources`/`vf.base_features` -> `cp.monthly_block`). This is a structural observation, not a design recommendation; the exact implementation is UNKNOWN.

## 6. Input data references and numerical environment

From `JP/objects/manifest-formal-h00.json` (all `gs://food-crisis-modeling-enso-research-inputs/inputs/...`; generations pinned there):

| role | sha256 |
|---|---|
| raw_panel IPCCH_202610_completed.csv | 09002869ecc25667d78d972185c8ea24340eabc4d6e1f8a6d560ebda214e1373 |
| interim IPCCH_202610_interim_acledagg_gosifv3_20261027.csv (incl. 18 acled_agg series, GPP v3) | b2d5d2ce6bd6a78da7caac2c070fcc2ced55aa4c4e7bd5725df0ce514e902b62 |
| climate_monthly climate_monthly_2015_2026_MODELING_READY.csv | 8082b72ea5fa5c30a7b975b89c1fbbb4530f27a9ce6c5ba4d0e1a4f923320c89 |
| climate_seasonal climate_2015_2026_MODELING_READY.csv | f024a66c8979fb4a8c66fba1f04e7e69355fa75b499793d29001a146d8c2958e |
| static29 static29_by_admin.csv.gz | 229d593ef8fc96b3747cfffd82ffd6a294217ae3f0442888872abe3c0ed668d4 |
| descriptors (AE128) descriptor_table.csv.gz | 362c58b0f3396fd8ecc3bd42fe0257f979dd371780f70af6edd3a59f633e26d4 |
| idp_admin0_monthly.csv | a1ebb82a8e14fc0fb8103d6086217b93da351fc4a8f7fcfbe9eaa44a9df602e1 |
| idp_ipcch_monthly.parquet | 8b2ba29988178a78dc42087134ef307d10a2b10778f83d0fa3a96018e911d703 |
| areas_combined_2026-10-19.geojson | 200f5dcaad88e18babbc9a4882a2ca920231702f6d5bcb11969af82742fa5ee6 |
| analyses_combined_2026-10-19.json | 1c7dfb786a8f82476542437445931fc5ab1ffdb5329aadc570616357f449b4b6 |
| ch_links.csv.gz | ac4ad6aaa8dc9e0efad6a7ba95456c536355d66ad0f3fa4225b811307aeb5153 |
| country_area_id_lookup.csv | e2baf6ae9481b42b127db5ce81f3c53ad784bb08ae56dfa56cea74e416b44c90 |
| compact manifest | 456360536a3929e1571d96ba9f16e2f0de54bc1b20019f797bbe62c0c89732ca |
| freeze h00 / index | dc152d4e… / d85582b3… |
| region_mapping / report_region_mapping | 18ab5099… / 5d1fd7f8… |
| baseline_predictions (GOSIF-v3 h00 copy) | 009caf29… |

ACLED monthly aggregate provenance `acled_agg_monthly.csv` sha256 539746f5… (2010-01..2026-09, export 2026-10-20) (config `provenance_tags`). No separate ACLED file role; ACLED enters through the interim.
Numerical environment: Python 3.12.3, numpy 2.4.4, pandas 3.0.3, scikit-learn 1.8.0, scipy 1.17.1, xgboost 3.2.0, mlflow-skinny 3.17.0; lock `R/control-plane/research_cloud/images/training-ipcch-validity/requirements.lock.txt` (sha256 ce0b23ad…), Dockerfile base `python:3.12.3-slim@sha256:afc139a0…`. Local venvs `~/.venvs/ipcch-geo` and `~/.venvs/ipcch-validity-idp` report the same versions (checked). `R/envs/` holds tooling (`mlflow-svc`) and historical replay runtimes (`rt-*`). AE source pinned commit `6c1ebf72` (RUNBOOK:293); `compact.py` sha256 82423316… is identical across all local copies.

## 7. Eligible sample counts (10-28 final context `hHH_supp_2026`)

Measured in the job and saved as `record.json` and `contexts/fit_ledger.csv`:

| H | cutoff | train_rows | copies | families | excluded families | n_eff | scored |
|---|---|---|---|---|---|---|---|
| 0 | 2025-12 | 129,150 | 91,391 | 721 | 60 | 82,616.7 | 15,317 |
| 6 | 2025-07 | 121,894 | 87,890 | not read | 60 | 80,468.1 | 15,317 |
| 12 | 2025-01 | 114,390 | 83,606 | not read | 60 | 77,317.4 | 15,317 |

Method: `plan_contexts` eligibility (`VP:500-540`) plus `plan_assertions` (`VP:553-588`); no-fit counts were pinned at CP2 (`T10/research/cp2/cp2-checkpoint.*`, not read in detail). Labels total 147,268 (44,446 original / 102,822 copy). Counts for cutoffs 2025-11/2025-05/2024-11 at origins T-2/T-8/T-14: UNKNOWN (need a no-fit `plan`/`gate` run). Rows whose origin-dependent features are missing are not removed by eligibility (XGBoost NaN routing). The H2/H8/H14 cutoffs fall between the H0/H6/H12 cutoffs, so counts will differ.

## 8. Evidence generation and package layout

- 10-28 package (`HV/package/`): `package.json` (identity, fixed params, file sha256s, `content_sha256`), `deps/feature_order.csv`, `deps/routing.csv` (context, role, target_lo/hi, cutoff, calibration_status), `weights/<context>/{q2..q5}.ubj, record.json, calibration.json` (identity `identity_no_support`, 8 zero slots), `loader/entry.py` + vendored `ipcch_alphaearth/{__init__,correction,errors,projection}.py`, `reference/{inputs.npy, expected.csv}`. All annual contexts are packaged (H0/H6: main_2023/2024/2025 + supp_2026; H12: main_2024/2025 + supp_2026). Other trial outputs: `predictions.csv.gz` (scored rows only), `dataset/*`, `contexts/*`, `gcs-only/history_overlays.npz`; base_X matrices stayed in GCS and were not harvested (`JP/operation-packet.md:108`).
- No resubstitution or residual evidence exists in the 10-28 outputs (search of `R` for polygon/resubstitution/maximum_phase: none).
- The existing resubstitution builder is in this repo: `OP/.trellis/tasks/archive/2026-10/10-09-sept-6m12m-confidence/research/build_ipcch_resubstitution_evidence.py` (337 lines). It rebuilds the training frame of the legacy launch trainer (`train_export_operational_launch_production_safe.py`; 128-feature package `cloud_pipeline/bootstrap/models/ipcch`; median fill), replays the four regressors, and writes `area` (polygon_id, sample_count, error_count; error = `(phase3_worse score >= 0.2) != (actual >= 0.2)`) and `residual` (actual - predicted for phase2..5_worse per polygon_id, target_month). Outputs: `OP/cloud_pipeline/bootstrap/evidence/ipcch_{0,6,12}m_resubstitution_{area,residual}.csv` + `provenance.json`. It is tied to the legacy trainer/panel and does not apply to the validity-pooled package without new code.
- Runtime consumer: `OP/cloud_pipeline/cloud/orchestrator/delivery_outputs.py:174-182` (`AREA_EVIDENCE_COLUMNS`, `RESIDUAL_COLUMNS`, method `training_residual_transfer_complete_month_bootstrap_proxy`, basis `training_resubstitution`), `maximum_phase_diagnostics` at `:393`, period-end check against package `training_cutoff` (`:196, :335`). Details of the 0.10/0.20 thresholds and population weighting: not re-read (UNVERIFIED line anchors).

## 9. Existing exclusion and fitting rules

- Sample weights `2**(-(C-U)/24)` (halving24) on every eligible row, originals and copies (`VP:396-407`); scoring unweighted.
- Family exclusion: families (and CH aliases) of the context's scored rows (S_E) are removed from fitting labels and both fitting and scoring histories (`VP:469-540`; `VF:723-758`). In the 10-28 final context, 60 families were excluded.
- Selection-only exclusions CF 2025-09 / MZ 2025-10 (`VP:148`) apply only in tuning mode (`VP:2033-2037`).
- Training starts 2014-01 (min_train_target), expanding scheme, no providers, identity calibration (config `training.*`). Years: year dummies 2014..2026 at T (`CP:94`). Arm row selection keeps all labels (originals and copies) (`VP:459-466`). No country filter in the arm; CAF is excluded from the CH path upstream (`T10/prd.md:27`). Label QC: exact-decimal share QC (`VF:1-15`).

## 10. Implementation work items and ambiguities (planned in cp1-plan.md §3; not user blockers)

1. Horizon hardcoding: `VF:40,52,1086`; `VP:83,85,88,279,2083ff`; `verify_freeze_inputs` index check {0,6,12} (`VP:2541-2545`); freeze records carry `horizon` 0/6/12. Using H0/H6/H12 params at H2/H8/H14 conflicts with the `freeze.horizon == config.horizon` check unless that contract changes.
2. Oracle removal needs code: `oracle_names(h)` returns 4 columns at H2 and 12 at H8/H14 (`min(H,6)`, `VF:844-846`), and `feature_order` asserts `expected_features(h)` (`VF:860-862`). No flag disables the oracle block.
3. Final-stage-only training: the HPT_ARM contract requires the full main calendar plus the supplement (`VP:2093-2097`); `schedule_from_config` rejects an empty main window (`VP:350`). Training only the 2026-01..10 context needs a calendar or contract change. The 10-28 jobs fitted all 11 contexts (44 regressors).
4. Formal contract coupling: `check_formal_contract`/`check_ch_correction` pin GOSIF-v3 baseline run ids, cohort counts, comparison inputs and self-consistency digests (`VP:2045-2081, 2210-2272`). A new H2/H8/H14 recipe needs a new contract kind or re-pinned values (form UNKNOWN).
5. GPP R57 filter: not implemented; per-row vintage logic conflicts with the shared full-grid feature arrays (section 5).
6. 2027 identifier: `CP:724-727` raises for target years > 2026 (affects H8/H14 inference, not training).
7. Evidence: no resubstitution or residual builder exists for the validity-pooled package; training-row matrices (base_X) are in GCS only.
8. CH/IPC label availability is nominal (reference-start) and data vintages are retrospective; documented as limitations in 10-28.
9. (Resolved at CP0: working-tree modules equal the 10-28 overlay — see Git note.) Still UNVERIFIED: `cp2-checkpoint` count details; MLflow live state (not read; local records only); whether the IDP/ACLED/climate sources cover the months O needed for 2014+ rows at O=T-14 (for example, climate starts 2015 per the file name, so early rows may be NaN).
