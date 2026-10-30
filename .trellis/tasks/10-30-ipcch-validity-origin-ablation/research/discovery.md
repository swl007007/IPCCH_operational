# Read-only discovery, 2026-10-30

Research root: /home/swl007007/projects/food-crisis-research. Actual implementation root: control-plane/research_cloud.

## Correct retained baseline
CH-final runs H0 298c4718b4d64e6f8a5c315e8c22d25d; H6 00d4e94c824343bf86a0c2b79d5b9ed0; H12 f436da15c71c469199784db065f3b63b. Retained predictions/publication: scratch/ch-validity-20261028/harvest/formal-h{00,06,12}/trial-0/. The old CH task baseline.json describes its preceding GOSIF-only baseline, NOT this ablation baseline.

## Minimal intervention
training/ipcch_validity_pooled.py plan_contexts:516-535 determines score/family exclusions before fit rows. Existing original arm:459-466 filters the whole label panel and changes scoring, so do not reuse it blindly. run_contexts:1396-1402 replans; preflight and real fitting need the same fit-only filter. fit_weights:396-406 uses 24-month half-life without normalization; retain each surviving row weight unchanged. History obs comes independently from raw reported phases (ipcch_validity_features.py:707-715,1313-1339); retain source-family and alias exclusion from complete scored contexts, and match retained original training-row histories plus all scored histories to baseline. No synthetic originals for CH copy-only source events (features:424-427,633-639).

Baseline original/copy labels: 44,446/102,822; three horizon workflows have 4/4/3 context quartets, total 44 scalar fits (not three scalar fits). Frozen schemas 527/539/539, same corrected GPP, optional oracle features inherited from this research family; do not substitute operational schema.

## Existing MLflow standard
publication.py:218-341 publishes full run/LoggedModel/registry version/cards/finite metrics/DatasetInput/model output and checks FINISHED/READY. Experiment IPCCH dashboard (id 2). Six formal metrics: binary_f1, phase3plus_r2, macro_f1, binary_f2, binary_precision, binary_recall (pooled.py:137-146), with annual/pooled/holdout/regional reports. TUI narrowing does not shrink this schema. Dataset arm_rows index currently includes original+copy rows for HPT arm (dataset_input.py:24-31,70-79); metadata must distinguish modeling/scoring panel from actual original-only fit memberships. New identities must link CH-final runs, never overwrite baseline aliases.

No cloud access, fits or evaluation was performed in discovery. Exact source/config/prediction pins to be persisted before execution; no live registry assertions yet.
