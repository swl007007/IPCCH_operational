# Remaining FEWS package adapter groups

Bounded read-only source scout, 2026-10-16, following existing27-run catalog. No model execution, training, hydration or cloud call. This is an implementation map, not replay acceptance.

F=`/home/swl007007/projects/food-crisis-research/sources/Food_Crisis_Cluster/FEWSNETGeoXGBExperiment`; N=its parent; A=`N/.trellis/tasks/archive/2026-10/10-01-geoxgb-shared-parameter-design/research`; R=`/mnt/c/Users/swl00/geoxgb_runs`.

## Avoid inventory and decoder mistakes

- Catalog `prediction_files=0` misses `rows_C/rows_E3/rows_FIT*.csv.gz` in D35/37/38/42/46/47/48/51/52. Do not classify these runs as reference-free from that count.
- Four-class codes are0..3, axis labels1/2/3/4-or-5; crisis hard call is argmax code>=2 (`F/src/metrics/fourclass.py:3-17,134`). Supervisor directly checked this source. Do not use code>=3.
- Feature contracts differ: supervisor freshly read **129 ordered features** in `R/scen-b43ef6a-v1/prepared/scenario/features.json`. The scout's initial claim of110 for that file was incorrect. Confirmation reports110; ordinary diagnostics use162; D51 projects78. Read each run's actual saved schema and hashes, never infer shape from related names. Earlier training note's129 statement remains correct.

## Minimal inference groups covering27 run keys

| Run keys | Reuse / saved evidence |
|---|---|
|geoxgb-d35-global-increment-20261002; geoxgb-d37-recency-root-20261002; geoxgb-d46-class-weight-root-20261002; geoxgb-d47-stump-root-20261002; geoxgb-d48-known-origin-fit-20261002|Ordinary162-column four-class `nx.from_raw`/`nx.proba`/argmax. Per-root weights respectively global_plus20, weighted_root, weighted_root, stump_root, known_root; rows_C/E3 (D48 `_known`), some FIT/S references. Weighting/known-origin training does not require a different prediction kernel.|
|geoxgb-d38-persistence-margin-root-20261002|anchored_root plus per-row base margin from hist_phase_o00; `scripts/stage1_persistence_margin_root.py:57-85`, `src/model/native_xgb.py:157-174`. Saved rows_C/E3 with p_anchored; original/posthoc controls distinct.|
|geoxgb-d51-history-calendar-root-20261002|h78_root with feature_map.json selected_names/selected_index in original order; `A/d51_history_calendar_root.py:81-114`. Saved FIT/C/E3 p_h78.|
|geoxgb-d52-binary-root-20261002|binary_root, binary:logistic scalar probability, threshold0.5; `A/d52_binary_root.py:150,218-223`. Saved p_binary/call_binary; do not feed to n-by4 helper.|
|geoxgb-d42-map-transfer-20261002; geoxgb-d43-temporal-map-refit-20261002|`scripts/stage1_map_transfer.py:155-177` route/arm_proba; region refit where eligible, root fallback for missing/s-1/insufficient support. Region JSON includes areas/eligibility/continuation and UBJ/root SHA (`340-354`); row refs and routes `402-419`. D43 uses same helpers (`stage1_temporal_map_refit.py:483-491`); preserve pairs/equivalence/search evidence.|
|geoxgb-v1-20261001; geoxgb-d26-20261001; geoxgb-d27-tb3-20261001; geoxgb-d28-rootinc-20261001; geoxgb-d29-confirm-20261001; geoxgb-d30-recent-search-20261001; geoxgb-d31-matched-search-20261001; geoxgb-d34-e1-brier-20261002|Stage1 candidate target_predictions.csv branch_id/p_partitioned, checkpoints/xgb_<branch>.ubj. Existing replay pattern `scripts/verify_fourclass.py:365-395`; general spatial routing uses s_branch (`native_xgb.py:414-422`), not training X_branch_id as a generic new-row router. v1 also has72 globals and gscreen/predictions.csv.gz.|
|scen-b43ef6a-v1|Stage1 scenario candidates/checkpoints; four actual-case system and pooled references, globals metadata; selected129-feature schema. Preserve all search/global bytes. Apply only accepted18-booster exception to documented actual rows.|
|confirm-onset-v1|S0/S3 globals, system and pooled refs, separate observations/release/extension/alignment. See unresolved system completeness below.|
|minirun-1; minirun-2; smoke-2|Fixture labels remain nonauthoritative. minirun uses normal Stage1/gscreen/globals; smoke has no demonstrated prediction reference. Preserve bytes, do not invent references.|
|d34-hard-replay-evidence; d37-fitglobal-replay-evidence; d38-fitglobal-replay-evidence|D34 saved branch references; D37 new/old boosters/records but input/reference not located; D38 new/old proba.npy but input not located. Names alone do not prove D38 margin semantics. Preserve evidence with limitations.|
|scen-b43ef6a-v1.failed_stage1|264 retained UBJs, aborted search cache; no demonstrated full inference system/reference. Preserve as cache evidence.|

## Input/hash anchors

- Normal Stage1 prepared/manifests/{features,sources,outputs,identity}.json binds ordered schema, raw inputs, prepared outputs and prepare/code/runtime. candidate.json checkpoint SHA and root.json fitting/validation-key SHA bind units/cohorts.
- Diagnostic run identity.json inputs[<root>].snapshot points to D34 prepared snapshot_hH.parquet; also binds root/fold-membership/root-target/candidate refs. D34 snapshot SHA: H4 c24ed96ff7c8b6e8cd31945c5d3c463c8f4c17695174361c822739034a8f3bf3; H8 4cc7327850206bd8df8455fceeb62aa2a5cd4db0d6e42502773827fc0d70a363; H12 2a4d1b32a7f5e514d44693f05c640fc49956a81373e0421084e4f6cd5d00b017. Keyed matrix extraction examples `R/d51_supervisor_check.py:72-115`, `d52_supervisor_check.py:105-124` (not executed).
- D51 projection schema/hash and D52 fitting-label hashes are in their root JSONs. Scenario outputs manifest binds features/parquets; global metadata includes snapshot/fit-keys/scenario/matrix/weight/label hashes. Confirm inputs_manifest.json, steps/inputs.json, predictions_frozen.json and extension_v3 manifest bind distinct inputs and saved results.

## Newly identified confirmation system gap (not an accepted exception)

Supervisor directly read original producer `N/.trellis/tasks/archive/2026-10/10-03-pooled-onset-confirmatory/research/run_confirm.py:393`: save_fold(..., False,...). `F/src/experiment/stage3.py:474-481` only retains local booster bytes when keep is true. Current S0/S3 fold.json outputs list gate/pairs/system/pooled predictions, no weights; 14 retained UBJs are global units. S0 has1609 local-model rows and S3 has837: **2446/11436** system predictions depend on local weights not demonstrated present.

Search the original local child hashes across the already inventoried cache before declaring them missing. Separate retained pooled/global replay from full system replay. The user's scen exception does not cover this run; report exact confirmed missing components for an explicit disposition if search fails. Continue other migration work. No historical retraining or pooled substitution under the old system identity.
