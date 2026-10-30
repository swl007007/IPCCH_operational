# Design — approved scope (implemented; see research/final/)

## Data flow
Pin CH-final retained trial data/config/predictions -> rebuild same modeling panel/context plans -> filter only fitting memberships to final original labels -> no-fit invariance checks -> fixed-parameter annual/holdout context fits -> standard keyed full-cohort scoring -> paired TUI tables + standard research MLflow publication.

## Reuse and intervention
Reuse `research_cloud.training.ipcch_validity_pooled` and its HPT-family scientific path. Do not use existing legacy `arm=original`, which removes copy scoring rows before context planning and does not preserve this feature/HPT path. Apply one explicit fit-label policy consistently in preparation and `run_contexts` replanning. Retain final CH lineage, source observations and family aliases. Existing 24-month half-life weights remain unchanged for each retained original; no normalization after copy removal.

Require score keys/truth/features/history identical to baseline, and new training keys/history/features/weights equal the baseline original-row subset. A full training-overlay hash changes with subset length; verify keyed slices rather than demand the old whole-overlay hash. Final label_kind is authoritative; unresolved/cross-country originals remain as in baseline. CH copy-only reports are not promoted to synthetic original labels.

## Evaluation
Keep inherited complete scoring contexts for exclusion safety. Pair `(context, admin_code, target_ord)` with identical truths; reject duplicates/unmatched keys instead of silently taking an inner join. Select baseline `label_kind=original` for original/matched augmented TUI groups; total uses all retained baseline scored rows. Compute primary pooled from raw predictions. Record declared and observed dates, counts, NA reasons and delta direction.

## MLflow
Existing `IPCCH dashboard` experiment (id 2), publication naming/card/DatasetInput conventions. Retain six formal metrics and existing annual/pooled/holdout/regional report standards; final TUI narrows presentation only. New identity must state original-only fitting and augmented full scoring where applicable. Do not mislabel the unchanged modeling-panel DatasetInput as the fitting subset; link actual fit membership evidence explicitly. Existing CH publication's own baseline field points to GOSIF-only predecessors and must NOT be reused as this task's comparator.

## Boundaries
No production changes. Paid/cloud actions require an execution packet with hashes, bounded resources, expected 44 scalar fits and publication identities after planning approval; prior goal's cloud preauthorization ended with that goal. Preserve existing inputs and artifacts; write new outputs separately. Exact implementation and execution workspace Git baseline to be inspected before edits.

## Accepted corner cases
No bootstrap/significance inference. Use existing metric primitives and NA reasons. Expected empty score windows remain in reports; negative R2 is not clipped. Differences require two defined values. Unexpected empty fit sets or pairing/ground-truth mismatch blocks the affected experiment, without filtering/fallback.

## Artifact retention
Retain three final holdout weight sets and all keyed annual/holdout predictions, config/parameters, membership/history and metric receipts. Verify annual model replay while temporary weights exist; only then remove task-owned temporary annual weights. Keep old baseline artifacts intact. This policy does not remove MLflow metric/report history.

## Names and outputs
Use a distinct, explicit original-training ablation identity in the existing dashboard experiment. Preserve the baseline arm/registry identities as comparison references. Final publication names/config pins are recorded before jobs run; no aliases moved. Standard full-cohort reports and original-matched TUI views must be labeled independently, never silently substitute one denominator for another.
