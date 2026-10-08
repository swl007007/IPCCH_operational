# October cloud delivery integration

## Goal

Move the September manual FEWSNET and IPCCH delivery capabilities into a reproducible cloud workflow for the October release: refresh remote sensing in the cloud, let operators independently choose ACLED and WFP updates, then upload a final run manifest to trigger inference and CSV delivery.

## Planning status and authority

- Cloud scope update (2026-10-07 ET): full cloud debugging in the verified SDK project `manuel-remote-sensing`, including necessary endpoint/service registration and startup, is authorized. The user is sleeping and requests questions only for CRITICAL issues; continue supervisor checkpoints, task-scoped deployment/testing and preservation of existing consumers. See `supervision.md` for timing and verified SDK configuration. This supersedes earlier local-only scope.

- Latest scope update (2026-10-07): the user explicitly stopped historical provenance investigation: reuse fixed features directly and prioritize this repository's existing scripts for remote feature construction. This supersedes earlier historical canonical-panel/extractor/FID-lineage stop gates. Preserve current native IDs and test the selected construction; do not claim historical numerical parity or continue archaeology.

- Brainstorm and document-grill product decisions are consolidated; design and execution plan are at revision 0.5. After reviewing the planning summary, the user explicitly requested Claude Opus 5.5 1M implementation under Codex supervisor/checkpoint review. Executable model/input checks remain; historical lineage requirements are superseded by the latest scope update above.
- On 2026-10-07 the user explicitly authorized creation of a Trellis task, superseding the earlier map-only/no-task preference.
- Requested sequence: brainstorm → persist specification → grill against the documents → final alignment. Use Trellis for this task; do not use Spec Kit or Superpowers lifecycle gates. Existing documents remain evidence of scientific and delivery contracts, not workflow authority.
- `design.md` holds the technical specification and `implement.md` the execution plan. User-owned decisions G1–G3 are resolved. Implementation approval is recorded in `supervision.md`; acceptance gates remain binding.
- Current authorization covers supervised implementation and relevant local validation/replay. Training remains deferred; cloud resource mutation, production runs/deployment and release publication require their own agreed scope. The user explicitly waived additional Trellis task audit for this task; use direct supervisor–executor checkpoints instead of audit-controller enrollment/start/close.

## Requirements and confirmed decisions

### R1 — Systems, origin, and forecast horizons

Deliver both FEWSNET and IPCCH for horizons 0, 6, and 12 months. Fix origin month O to the release month, even when remote-sensing observations lag. For October 2026, targets are 2026-10, 2027-04, and 2027-10. September h5 models must not be relabeled as 0/6/12 models.

### R2 — Cloud remote-sensing refresh

Refresh all dynamic remote-sensing features required by the two September model contracts to the latest available source periods in the cloud: EVI, FLDAS, GOSIF-GPP, and nighttime lights. Establish freshness from source observations and coverage, not filenames. Record differing source vintages explicitly; the forecast origin remains O. Versioned fixed geographic assets may be reused.

Document-grill decision G1, confirmed on 2026-10-07: select only the latest provider-published completed monthly remote-sensing products available at the preparation cutoff and at or before O. Exclude unfinished current-month composites. A complete monthly product can contain masked pixels; those still follow the agreed filling/audit rules. This monthly-product restriction does not change the accepted handling of partial ACLED/WFP raw observation coverage.

### R3 — Operator control of ACLED and WFP

After remote-sensing preparation, operators independently choose whether to refresh ACLED and WFP to their latest available data or retain named prior snapshots. The final manifest must represent the actual choices and exact snapshots used. A retained snapshot must not silently become a live/latest reference.

Confirmed by the user on 2026-10-07: operators may upload compatible ACLED and WFP raw exports, like the latest local raw examples the user identifies as Sediqa's uploads. Operators need not construct model-ready feature tables. Reuse the existing conversion and assembly logic with September delivery semantics; cloud automation must validate the raw contracts, transform each selected source for the appropriate system, and assemble model inputs. Preserve original uploaded files and record their actual observational coverage and exact object versions. Additional columns in compatible exports are acceptable. Local provenance confirms example file identity, but does not independently identify the uploader.

### R4 — Causal filling with disclosure

Preserve raw observations. For each area/feature/month, use the latest observation at or before that month when filling a missing value; never use a later observation to fill an earlier month. If no prior observation exists, use the corresponding model package's existing applicable imputation rule. If none exists, fail/report unavailable rather than inventing zero values. Fill base monthly series first, then recompute calendar lags and rolling features, tracing their dependence on filled inputs.

Record observed month, staleness in months, fill method, and derived-feature impact in an audit sidecar CSV. Preserve September prediction CSV contracts. Confirmed by the user on 2026-10-07: after successfully refreshing each source to its latest available observations, apply the agreed causal filling rules and disclose staleness without a maximum-age threshold that automatically blocks release. Download or refresh failure must not be classified as normal source publication lag.

The user also confirmed that a required input with neither usable historical observations nor an applicable model imputation rule blocks the entire formal release. Retain a failure report and the previous accepted release; do not publish a partial candidate as the official release. The user reports having checked that every feature has at least one observation, so this is an exceptional fallback rather than an expected data gap. This user-provided evidence has not been independently replayed in this planning task; runtime coverage validation still follows the area/feature/month keys and temporal eligibility specified above.

### R5 — Manifest-triggered execution

Uploading the final `run_manifest` triggers Cloud Run automation to score the approved inputs and produce CSV outputs. Confirmed by the user on 2026-10-07: “serve” means batch inference followed by saving CSV outputs and terminating the job; a persistent online prediction endpoint is not required. The run must bind reproducible input, model, geometry/population, preprocessing, and diagnostic versions. The proposed trigger mechanism and compute placement are recorded in `design.md`; no deployed trigger is assumed.

### R6 — September delivery compatibility

Preserve the September v3 delivery's consumer-facing schemas and applicable scientific semantics, while producing the correct origin/horizon values and horizon-specific model results. Include polygon and country outputs and the associated delivery/diagnostic assets required by that contract. The inventory is reconciled in `design.md` against `research/release-contracts.md`; prediction CSVs alone do not prove equivalence.

Document-grill decision G2, confirmed on 2026-10-07: place each system's prediction, mapping and diagnostic CSVs under `scopes/0m`, `scopes/6m`, and `scopes/12m`. Share geometry and population-reference assets across horizons within each system and deliver one portable archive containing all scopes. Preserve the September artifact classes and CSV fields; consumers select the horizon subdirectory. Exact relative layout is specified in `design.md` section 8.

Do not copy h5 diagnostic numbers into 0/6/12 outputs. Historical evidence must be valid for the claimed model/horizon; forecast-dependent fields must be recomputed from current scores. September's FEWS fs1/4-month-lag evidence was an approved h5 proxy, not blanket approval for other horizons. IPCCH training-resubstitution diagnostics must remain labeled as such.

Confirmed by the user on 2026-10-07: when suitable historical diagnostic evidence is unavailable for a model/horizon, predictions are still delivered; the affected diagnostic values are blank and explicitly marked unavailable with a reason. Do not insert zero errors, a confidence category, or a substituted h5 proxy. Country outcomes that can be computed from current predictions remain populated. This exception concerns diagnostic support only; invalid inputs, failed scoring, corrupt supplied artifacts, or failed release integrity checks are not converted into successful runs with unavailable diagnostics.

### R7 — Preservation and reproducibility

Preserve raw data, native IDs, accepted historical releases, and scientific feature semantics. Any intentional modeling/preprocessing change must be separately visible and approved. A failed candidate run must not replace an accepted release. Reproducibility must cover data/model artifacts and numerical environment, not just source code.

Document-grill decision G3, confirmed on 2026-10-07: submission freezes the manifest and selected data versions. Preserve failed-run evidence and retry deliberately with a new `run_id`, reusing successful prepared snapshots when desired. Identical duplicate events do not repeat scoring. Do not resume or overwrite the original run in place, or re-query moving source versions during scoring.

### R8 — Accept existing models first; defer training

Confirmed by the user on 2026-10-07: first assess and accept the existing FEWSNET and IPCCH 0/6/12 model packages; training is deferred. Manifest-triggered execution loads explicitly accepted, frozen model versions and does not submit training. Existing packages are candidates, not already accepted releases. A failed acceptance check must be reported for a separate decision; it must not silently trigger retraining. This decision establishes the planned model lifecycle, without expanding the current design-only authorization into model execution.

### R9 — Operator-initiated cloud preparation

Confirmed by the user on 2026-10-07: an operator explicitly runs a preparation command; the cloud refreshes all required remote sensing and produces a coverage report. The operator then selects retained or uploaded ACLED/WFP sources and uploads the final manifest to initiate batch delivery. Scheduled preparation is not required. Raw uploads alone do not replace the final manifest as the release request.

## Evidence and current limitations

Code baseline: `4a42f1f666a4f2d5d2616069fe25ddd81f2662cb`. Existing architecture and manual/cloud comparison: `.birdview/README.md:8-34`. The maps describe observed current behavior, not this proposed integration.

| Evidence | Planning implication |
|---|---|
| `model_artifacts/launch_2026_04/model_package_manifest.json:15-32` | Existing IPCCH packages cover 0/6/12, use cumulative population-share outputs, and record an April 2026 training cutoff. Their October fitness is not established. |
| `Outcome/fewsnet_partitioned_rf/model_artifacts/local-202604-57cb3b981198-510375f58cd8/{0,6,12}m/model.joblib` | All three FEWS model files were found during this session's exploration; existence does not establish October readiness or numerical loading compatibility. |
| `fewsnet_partitioned_rf_pipeline/cli/run_latest.py:441-486` | Current FEWS cloud suite submits training; it is not a pure-scoring release entry. |
| `model_pipeline/run_operational_launch_inference.py:157-218`; `fewsnet_partitioned_rf_pipeline/core/inference.py:229-247` | Shared scoring logic exists; wrappers and date assumptions still need migration. |
| `fewsnet_partitioned_rf_pipeline/local/runner.py:74-81,531-537`; `tools/run_h5_model_delivery.py:145-179` | Existing local wrappers contain fixed April/September assumptions. |
| `cloud/orchestrator/assembly.py:33-115`; `.birdview/README.md:12-17` | Cloud preparation currently covers EVI and IPCCH assembly, not all requested sources or September country delivery. |
| `Outcome/model_delivery/202609_h5/20260923_country_confidence_v3/ipcch/model_package/scope_5m/feature_contract.csv:41-106,119-120`; `research/remote-sensing-contracts.md` | IPCCH requires 28 FLDAS bands with mean/stdDev plus EVI/GPP/nightlight features. Feature names do not establish the source reducer: the legacy GPP SD extractor averages the provider SD raster, and the nightlight extractor uses SUM/STD. Exact model-column lineage is a mandatory parity investigation. The ignored feature contract needs explicit version/hash binding. |
| `fewsnet_partitioned_rf_pipeline/core/preprocessing.py:311-347,530-564` | FEWS temporal features require calendar-aware history, including EVI lags and nightlight/WFP rolling features. Historical target lags are also required. |
| `fewsnet_partitioned_rf_pipeline/core/normalization.py:217-226` | Climate zscore code uses a whole-table rolling operation followed by per-admin statistics; extending the panel may change prior values. Training-compatible semantics require verification, not a silent algorithm correction. |
| `tools/refresh_h5_inputs.py:59-96,134-142` | FEWS and IPCCH use different WFP semantics. Preserve source-family replacement and historical-key behavior. |
| `tools/refresh_h5_inputs.py:177-201`; `docs/08_sediqa_raw_data_download_notes.md:7-77`; `research/raw-upload-contracts.md` | Existing raw conversion paths are available, but legacy readers differ from September delivery semantics. The h5 entry hard-codes raw filenames and April cutoff. Reuse requires parameterization and independent source selection, not a new conversion algorithm. |
| `Outcome/model_delivery/202609_h5/20260923_country_confidence_v3/reports/country_confidence_v3_spec.md` | Authoritative inspected local v3 diagnostic contract; SHA256 `8ea3c70e77310ed31a659b614aa72427c652ce40777f0326afc9ef84595beed6`. Ignored artifact, not fixed by Git HEAD. |
| `tools/revise_h5_country_v3.py:277-283,374-389` | Existing diagnostic replay hard-codes h5 and combines residual evidence with current scores; horizon adaptation is substantive. |
| `cloud/orchestrator/run_state.py:57-66`; `cloud/orchestrator/release.py:91-106,349-363` | Run protection and immutable release mechanisms exist, but output inventory currently targets IPCCH. |
| `research/model-and-lineage-acceptance.md`; `fewsnet_partitioned_rf_pipeline/core/validation.py:121-142`; `model_pipeline/ipcch_launch_runtime/feature_contract.py:318-345` | FEWS candidates require Python 3.12 and exact saved dependencies, unlike the old Python 3.11 image. IPCCH saves training medians and XGBoost 3.2.0 models but lacks a complete recorded training environment. Model replay remains pending. |
| `archive/notebooks/Final_harmonise/00_combine_all_ch.ipynb`, cells 24–28,32,45; `research/model-and-lineage-acceptance.md` | CH naming/reducer links are established, but canonical IPCCH/FEWS lineage and legacy zone-ID mapping remain incomplete. Global notebook fills/zero substitutions conflict with R4 and must not be reintroduced. Historical artifacts remain preserved. |

CP0 performed FEWS load/identity checks and IPCCH frozen-input diagnostic replay; see `research/cp0-acceptance-evidence.md` for limitations and saved-output clipping provenance. No live GCP deployment/IAM/source-freshness inspection, FEWS prediction replay, local/cloud numerical parity run, or complete delivery acceptance rerun has been performed. Previously saved “passed” reports are not verification for this task.

## Acceptance criteria

- AC1 (R1): both systems expose horizon 0/6/12 outputs whose target dates equal O, O+6, O+12, even when latest observed inputs precede O.
- AC2 (R2–R3): the run records all required remote-sensing families and their actual coverage, selects the latest provider-published completed monthly products, and excludes unfinished composites without changing O; all four ACLED/WFP keep/refresh combinations select reproducible snapshots.
- AC2a (R3): compatible raw uploads are transformed and assembled without operator-authored feature tables; WFP Forecast rows are excluded, FEWS/IPCCH indicator formulas remain distinct, raw files remain unchanged, and actual dates rather than filenames determine coverage. Schema/date/key errors are reported before official release.
- AC3 (R4): temporal examples demonstrate no future-to-past fill and traceable model fallback; sidecar rows identify filled inputs and affected derived features. If a required input has no eligible observation or applicable imputation rule, the entire formal release is blocked, a failure report is retained, and the previous accepted release remains current.
- AC3a (R2, R4): after a successful latest-available refresh, staleness alone does not block release and is disclosed in the sidecar; a failed refresh cannot pass as normal publication lag.
- AC4 (R5, R7): final-manifest upload starts batch scoring, saves the required CSV outputs, and terminates the job without requiring a persistent online prediction endpoint. Submitted versions remain fixed, identical duplicate events do not repeat scoring, and retry requires a new run ID while preserving the original evidence and allowing pinned prepared snapshots to be reused.
- AC5 (R6): an explicit inventory/schema/semantic comparison accounts for every required September delivery artifact across both systems and all three horizons; unsupported diagnostic claims cannot pass as validated evidence.
- AC5a (R6): absent suitable historical evidence leaves only the affected diagnostic values blank with an explicit unavailable reason; valid predictions, current-score country outcomes, and unrelated supported diagnostics are retained and may be published. Missing diagnostic support does not bypass input, scoring, or artifact-integrity failures.
- AC6 (R4, R6–R7): frozen-input local/cloud comparisons cover feature construction, predictions, country aggregation, and diagnostics, using agreed numerical tolerances and the same model/asset versions. Compare both environments under the approved causal-fill policy; isolate intentional differences from legacy cross-area/zero filling instead of requiring their reproduction.
- AC7 (R7): failed validation preserves the previous accepted release; a successful release records sufficient lineage for replay.
- AC8 (planning): PRD, technical specification, and execution plan are persisted; each confirmed decision maps to its document and acceptance criteria; document-grounded grilling resolves all blocking decisions before a final planning summary is presented.
- AC9 (R8): model acceptance records identify the exact existing packages for both systems and all three horizons; the manifest binds accepted versions, the scoring flow contains no training step, and failed acceptance does not initiate retraining.
- AC10 (R9): the operator can initiate cloud preparation and inspect its coverage report before choosing ACLED/WFP inputs; only the subsequent final manifest initiates the delivery request.

## Risks and remaining acceptance evidence

No user-owned brainstorm or G1–G3 choice remains unresolved. `design.md` section 10 and `implement.md` assign the remaining technical checks: canonical feature/region lineage, candidate-model replay, FEWS normalization extension, provider completeness and source availability, native event-trigger deployment, and numerical resource limits. Metadata inspection is complete only where the evidence table states so; these checks are not collectively passed.

The first acceptance milestone checks model loading/runtime and current input compatibility. Historical canonical-panel/extractor lineage is no longer required before adapters, per the latest user instruction. Current source versions/native IDs remain explicit, and no retraining or silent normalization change is authorized. Implementation continues under supervisor review; production readiness remains outstanding.

## Out of scope for the current implementation authorization

Model training or retraining, unrelated cloud changes, existing-consumer production cutover and changing accepted September artifacts. Task-scoped cloud debugging/deployment is now authorized as above. A persistent online prediction endpoint, new serving UI, generalized orchestration framework, or migration of unrelated historical workflows is excluded.
