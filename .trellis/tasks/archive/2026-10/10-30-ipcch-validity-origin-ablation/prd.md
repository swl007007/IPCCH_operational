# IPCCH validity period versus origin ablation

## Status
Execution approved after final summary (user: 采用) and execution-protocol-user.md. See execution-authorization.md for provider clarification and checkpoint gates.

## Goal
Isolate the effect of validity-copy training labels using three new H0/H6/H12 experiments compared with the retained CH-validity models. Preserve the existing scientific pipeline and report paired performance rather than conflating a model change with a population change.

## Requirements
- R1 — Baseline: `Validity-augmented pooled (GOSIF v3 + CH validity 20261028) | validity_augmented_idp_202610_acledagg_lag1_uncal_hpt`. Reuse retained baseline predictions, not earlier GOSIF-only runs; never refit/overwrite baseline.
- R2 — Three new horizon experiments H0/H6/H12. Origin means original-only fitting: retain rows whose FINAL CH-corrected `label_kind == original`, omit copy fitting labels. This does not mean source month alignment, raw nonempty labels or newly reconstructed source labels.
- R3 — Single intervention: preserve selected horizon/target hyperparameters, seed, per-row time weights, features, preprocessing, history rules, projection, phase threshold and calibration policy. No HPT or extra seeds; no new source exclusions, synthetic originals or original-weight renormalization. Restrict fitting membership after existing context cutoffs/family exclusions.
- R4 — Retain full baseline scoring contexts and their source-family/alias exclusions, including copy families, for fitting labels and fitting/scoring histories. The new model scores the full inherited cohort for standard artifacts; TUI selects the agreed original subset. Preserve history observations independently of fitting-label filtering.
- R5 — Calendar: H0 full 2023/2024/2025; H6 July–December 2023 then full 2024/2025; H12 no 2023 rows (NA), full 2024/2025. Holdout all horizons 2026-01..10. Preserve original context-specific fitting cutoffs and earliest training boundary. Do not extend windows to populate H12/2023.
- R6 — TUI: five rows per horizon: 2023, 2024, 2025, primary pooled (inherited historical windows), holdout 2026. Three groups: (a) original = new original-only-trained model on baseline-original evaluation rows; (b) matched augmented = retained augmented model on those EXACT keys/truths; (c) augmented total = retained augmented model on all inherited original+copy evaluation rows. Include F1 (phase >= 3), phase3plus-share R2 and N. Comparable delta = matched augmented minus original. Total versus matched is descriptive population contrast, not isolated model gain.
- R7 — Pooled metrics recomputed from concatenated keyed predictions, not mean yearly metrics; never include holdout in primary pooled. Preserve negative R2. Empty windows are NA, not zero; report actual temporal support. Undefined metrics and uncertainty follow R10/R11.
- R8 — MLflow follows the existing research standard in `IPCCH dashboard`, not reduced TUI metrics: full standard metrics/reports, run, LoggedModel, registry version, cards and DatasetInput/model links. Distinct new identity per horizon and explicit linkage to correct baseline; no old aliases/records changed. Modeling/scoring panel and actual fitting subset must be truthfully distinguished in metadata.
- R9 — Long-term retain only H0/H6/H12 final holdout model weights, plus ALL annual/holdout keyed predictions, parameters/config/source pins, fit memberships/history evidence and machine-readable comparison tables. Annual-context temporary weights may be removed only after their necessary replay/verification succeeds and evidence is saved. Cleanup is limited to this task's new artifacts; baseline assets are untouched. No production packaging or blanket archival.
- R10 — Point estimates and paired differences only; no new bootstrap, confidence intervals, significance tests or extra seed repeats.
- R11 — Expected empty evaluation windows: NA, N=0 and reason. Undefined metrics use existing functions with explicit reasons; retain negative R2. A difference is NA if either operand is NA. Unexpected empty fitting sets, duplicate/unmatched paired keys or unequal truths stop the affected experiment; no silent filtering, synthetic labels or fallback models.

## Acceptance criteria
- A1: baseline predictions/config/parameters/input lineage are pinned for all three horizons; original/copy classification is the CH-final classification.
- A2: no-fit preparation proves exact original-only fitting subsets, unchanged per-row weights/features/histories on shared rows, identical scoring keys/truths and full-family leakage exclusions.
- A3: three workflows complete their existing annual/holdout contexts with fixed parameters; no independent tuning or baseline refits.
- A4: TUI and machine-readable tables implement R5–R7, have exact paired keys/truths/counts, reproduce baseline metrics and disclose all undefined cells; no performance-improvement gate.
- A5: all standard MLflow publications/readbacks and package replay checks pass with new identities and accurate cohort descriptions; preserve baseline records.
- A6: final three weight sets and all required keyed evidence are retained; any removed annual weights have completed verification receipts and explicit task-owned cleanup records.

## Scope boundaries
Research implementation belongs to `/home/swl007007/projects/food-crisis-research/control-plane/research_cloud`; this task records cross-workspace planning. Operational H2/H8/H14 migration, production current, source refreshes, new label repair, feature ablation, regional model fitting and deployment are out of scope. Inherited nominal-availability/oracle limitations are disclosed, not repaired by this ablation.

## Execution gate
No unresolved scientific scope decision remains. Final planning summary explicitly approved. Before paid/cloud execution, pin the concrete input/config/code identities and record resource bounds, estimated cost and publication destinations in a bounded packet; approval of planning does not authorize unbounded retries or unrelated cloud changes. This task's subsequent execution protocol provides its own scoped authorization; no old budget reservations are reused.

## Evidence
See research/discovery.md. Baseline source specification: food-crisis-research/.trellis/tasks/10-28-ipcch-ch-validity-refits/{prd,design}.md. Three experiments contain 4/4/3 existing context quartets (44 scalar fits total), not three scalar fits.
