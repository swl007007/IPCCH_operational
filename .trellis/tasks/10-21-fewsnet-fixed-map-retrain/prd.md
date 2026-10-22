# FEWS NET fixed-map retraining and production refresh

## Status and goal

Approved execution specification, updated on 2026-10-22 after the final grill and the user's Supervisor–Executor instruction. Refresh the FEWS NET dataset from HDX-registered latest CS resources, fit new operational binary Random Forest weights on all eligible history, and make those weights the production default after candidate acceptance. Target project: `feisty-flames-511718-d4` (food crisis modelling test). HDX label versions are frozen at actual retrieval; the other source-vintage and observation-month limits below remain unchanged.

The user's latest decisions supersede the earlier rolling-window proposal: **no last-36-period restriction, no validation/test split, no model evaluation, no threshold search, and no confidence recalculation**. Existing confidence outputs are retained directly. Implementation and local fitting are authorized; cloud operations follow the time-bounded authorization below.

## Requirements

### R1. Preserve the operational model contract

- Keep the binary partitioned RF at horizons 0, 6 and 12 months, the existing 17-partition map, and all 123 features in their existing order with unchanged definitions/transformations.
- Keep all 5,718 prediction areas and 22 countries. The map covers 5,365 areas; retain existing pooled/local routing and fallback for the rest. Do not redefine the roster from mapped or labeled areas.
- Keep RF hyperparameters (100 trees, unlimited depth, seed 5, `n_jobs=1`), SMOTE behavior, minimum partition sample rule (50), fallback rules and `MaxPlusImputer(multiplier=100.0)`; refit fitted preprocessing and estimators on the eligible fitting rows.
- Retain thresholds: 0m = 0.48, 6m = 0.41, 12m = 0.45. No tuning or repartitioning. Do not substitute the research four-class XGBoost adapter.

### R2. Pin the refresh vintage and geographic alignment

- Prediction origin is `2026-10`; targets are `2026-10`, `2027-04`, `2027-10`.
- For non-label source releases, retain the agreed availability cutoff `2026-10-21`; monthly exogenous observations must be completed months no later than `2026-09`. Do not silently advance these limits. Record publication/retrieval evidence and any inability to establish availability at the cutoff.
- FEWS labels must come from HDX-registered FEWS NET Current Situation (CS) resources. Follow their registered official download URLs, freeze actual retrieval versions/timestamps/raw hashes, and admit assessment months no later than origin. This label-specific decision supersedes the earlier October 21 availability cutoff for labels. Preserve raw phase labels and derive the existing binary target only for nonmissing valid labels; missing labels stay missing.
- Join labels to the fixed production areas with an auditable, unambiguous crosswalk. Keep source IDs, country and geometry during reconciliation. Name alone is insufficient. Duplicate, unmatched or changed-boundary records stay in a gap report unless resolved unambiguously; do not invent labels or resize the prediction roster.
- Check HDX source coverage for all 22 target countries. Partial missing/unmatched new labels are allowed with country/month coverage and failure disclosure; fit all reliable additions. If the refresh yields no credible newly added labels after reconciliation, stop before fitting and resolve the source/mapping problem. A directory timestamp, unchanged old labels or an unverified download does not satisfy the refresh.
- Preserve complete historical observations. Append new months and fill historical gaps/truncation; present differences separately before replacing a provider's revised values in already complete history. Retain source snapshots and a compact keyed change/coverage record.

### R3. Refresh the existing feature families

| Source | Required behavior |
| --- | --- |
| FEWS NET | Discover HDX-registered CS resources for the target countries, download the actual content and reconcile it to the fixed geography. Record dataset/resource IDs and both HDX and download URLs. Verify latest assessment months in the data, not the catalog date; the latter was stale in the Nigeria/Somalia samples. Local labels through 2026-02 are only a baseline. |
| WFP | Reuse the local 2026-10-19 HDX raw annual files where suitable; reproduce existing FEWS month-over-month definitions. Do not reuse IPCCH processed YoY/centred-filter columns. |
| ACLED | Use the event-level API and existing FEWS aggregations. User accepts account delay of about one year. Use the latest obtainable complete month and retain existing subsequent fill/disclosure. `_w5` means admin2 and `_w10` means admin1; retain nearest-admin3 matching within 500 km. |
| EVI, FLDAS, VIIRS | Reuse pinned FEWS cloud extracts where they cover the required history; check actual provider availability and fill eligible missing/new months through September at most using existing extraction definitions. Report provider lag and area coverage. |
| GOSIF mean | Keep historical v2 values. Extend newly available 2025 months with v3 using FEWS geometry and the existing FEWS extraction method; disclose the v2/v3 break. IPCCH processed tables are not substitutes. |

Keep the existing causal fill rules; disclose raw availability, filled values and remaining missingness by family/month. A recent upload date is not an observation month or proof of freshness.

The second grill confirmed that skipping preparation during release does not cancel this data-building work. Complete necessary remote-data additions beforehand and pin the intended inference inputs; do not let an older reused snapshot silently erase new GOSIF/history values during overlay.

### R4. Fit all eligible history, without model evaluation

- Per horizon, align each feature row at month `t` with its observed label at `t+h`, subject to R2. Use every eligible labeled historical row; exclude absent targets and document exclusions. No artificial holdout or rolling training cap.
- Fit the existing pooled/local recipe in the frozen operational environment locally. Preserve feature and map hashes. Save new fitted weights/imputers and per-horizon fit months, row counts/keys, exclusions, routing, threshold provenance, runtime and input identities.
- Model packages must explicitly represent all-data fitting with no evaluation. Do not fabricate validation ranges, metrics, validation predictions or new confidence evidence to satisfy the old package schema. Existing packages remain readable.

### R5. Retain confidence outputs directly

- Freeze the six existing FEWS confidence CSV sources listed in `research/confidence-source-inventory.json`, from delivery `oct-confidence-20261009b`.
- Copy polygon confidence values, counts, population metadata, eligibility, historical basis/period and missing-value masks unchanged; all 5,718 polygons remain represented, including five without history.
- Copy the 19 historical country fields unchanged, including flags, historical error/coverage/population statistics and provenance. Do not recalculate ratios, weighted means, categories or availability from historical counts.
- **Current prediction fields still update.** In `country_confidence.csv`, refresh `country_outcome_crisis` from the new predictions and retain its configured threshold 0.5. Attach the frozen historical fields to the new `country_predictions.csv`. Never copy old crisis predictions as part of confidence reuse.
- Preserve Stage3 proxy lineage (2021-02 through 2024-10; fs1/lag4, fs2/lag8, fs3/lag12 for the three horizons) and original evidence references. Identify the new scored package separately from the old evidence/source package. These confidence values do not measure the new weights' performance.
- Apply the same direct-attachment behavior online and in the offline bundle. Keep the existing CSV column contract.

### R6. Release new FEWS weights and results

- Rebuild the operational runtime image for `us-central1` in `feisty-flames-511718-d4`, publish/select the three new FEWS packages, run the October production delivery and export its results after the required operation approvals.
- Do not run IPCCH inference for this release. Preserve its three weight packages and inherit its accepted October results, frozen inputs, assets and necessary dependencies by immutable reference. The complete two-system, six-slot delivery contract remains. A new image needs fresh package loading/runtime identity evidence for all six slots; loading the retained IPCCH packages does not require rerunning their inference or measuring performance.
- Preserve the prior accepted release/fallback for rollback. Use versioned candidate baseline/environment/operator state for the new image, and only update the usable local fallback from the completed new delivery.
- Generate and export a candidate first. Download/inventory verification and FEWS-only relocated replay must pass before changing production `current.json`, normal-operation default weights/configuration or the active local fallback. Candidate failure leaves the accepted predecessor active; no automatic promotion immediately after cloud scoring.
- Reuse the shared jobs under a bounded maintenance operation: pause admission of other monthly computations before changing their runtime/workflow configuration, reconcile any already-running work, and continue serving the accepted outputs. Reopen admission only after successful activation or verified restoration of the prior configuration. The user chose this approach instead of a temporary candidate job.
- Bind promotion to the exact checked candidate and expected predecessor. Record the affected cloud pointer, operator config/state/runtime and fallback identities so an interrupted switch can be detected and recovered without rerunning successful fitting/inference or overwriting a concurrent newer release. Do not claim completion while these active identities disagree.
- Keep cloud output, downloadable offline bundle and local fallback consistent: new FEWS predictions/weights, frozen FEWS confidence, explicit source and package identities.

### R7. Select execution steps through the manifest

- Express remote-sensing update, FEWS inference and IPCCH inference as independently selectable logical steps. Reuse the existing preparation and delivery Cloud Run jobs and their per-system inference entrypoints. Keep the current preparation step's extraction scope; selective remote extraction by system and a new workflow platform are outside this change.
- The existing **cloud Workflow** must read the pinned manifest and perform the selected cloud dispatch; local CLI flags or scorer branches alone do not satisfy this requirement. Once submitted, preparation-to-inference progression must not depend on a local polling process staying alive.
- When remote update is selected, wait for the durable succeeded preparation state and compatible immutable snapshot before inference. Successful completion of the preparation Cloud Run job alone only confirms task submission. Keep the initial intent immutable and bind any resolved delivery request/snapshot to it.
- For this release, select **remote update = off, FEWS inference = on, IPCCH inference = off**. Reference the already completed input snapshot from R3 and the accepted October IPCCH release. Training/data construction precede this release invocation.
- With remote update off, inference requires an explicit pinned, succeeded and compatible prepared snapshot. Missing/failed/incompatible inputs stop execution with an actionable error; never automatically enable a skipped step.
- An unselected inference system is carried into the complete release from a pinned accepted delivery, including required inputs, model members, diagnostic evidence and reports. Its origin and all horizon target months must match the new delivery exactly. Without a compatible same-origin source, stop and require a different explicit step selection; do not relabel older predictions.
- Preparation-only execution may produce a snapshot without publishing a new prediction release. Reject an empty step selection. Legacy manifests keep their original prepare-plus-both-systems behavior.
- Record selected/executed/reused steps and inherited provenance, and bind these choices to run identity/resume behavior. Validate the complete exported package while replaying only selected systems; this run must not invoke IPCCH inference indirectly through offline verification.

## Acceptance criteria

- [x] AC1: HDX source checks cover all 22 target countries; the inventory records registered resources, actual retrieval/version hashes, content-derived CS months, credible added labels, crosswalk decisions and gaps. No credible additions prevents fitting. Other inputs retain their cutoff/coverage records; no unexplained historical revisions or missing-to-zero targets. (Supervisor S5/S10/S11; `research/p1a-acceptance.md`, `research/p1b-fit-acceptance.md` and source/overlay receipts.)
- [x] AC2: Three new packages use the unchanged map/schema/recipe/thresholds and all eligible horizon-aligned labeled history. Saved fit-key/count evidence accounts for exclusions. No evaluation split, performance metrics or threshold search was generated. (Supervisor S12; `research/supervisor-fit-key-verification.json`, `research/supervisor-fit-package-verification.json`.)
- [x] AC3: Packages load in the locked operational environment; old package formats remain readable. Full-data reports truthfully omit evaluation information and scoring does not require a fabricated validation period. (Supervisor S13/S14; `research/supervisor-image-runtime-verification.json`, `research/supervisor-clean-fixture-checks.json`; final deployment identity remains subject to AC6/AC9.)
- [ ] AC4: Each horizon exports 5,718 unique prediction areas and 22 countries. New FEWS package IDs/weight hashes are consumed by this delivery and fallback and are selected as the production default for subsequent normal runs; predictions need not differ numerically to prove package identity.
- [ ] AC5: Frozen confidence fields, historical provenance and blank masks match the source inventory by key. Country current-outcome fields agree with the new country predictions. Online and offline attachment agree without recalculation.
- [ ] AC6: New-image loading/identity evidence covers all six slots. Inherited IPCCH predictions, package members, assets, frozen origin inputs and diagnostic members match the pinned October source; no IPCCH inference is executed online or during this release's offline replay. Old result-production provenance remains distinct from the new assembly runtime.
- [ ] AC7: Production export, portable bundle and local fallback have matching inventories/identities; the previous release remains recoverable. Required software/data integrity checks pass, with no model evaluation added.
- [ ] AC8: The cloud Workflow reads the pinned manifest and dispatches prepare-only, either inference system or combined runs using the existing jobs without local polling dependence. A completed prepare job with pending/failed Batch output never starts inference. This release launches no preparation job and scores only FEWS. Invalid dependencies, inherited identities/dates or changed resume intent fail without silently adding steps. Final content retains all 30 result tables and dependencies.
- [ ] AC9: Candidate export/download and FEWS-only replay finish before promotion. Other monthly computations are held while shared runtime settings change; old published outputs stay readable. Failure leaves previous release/defaults/fallback active and restores prior job/workflow settings before reopening admission. Promotion checks the candidate identity and prior pointer generation; completed activation has matching cloud/operator/fallback identities and concrete interruption recovery information.

## Execution boundary

Latest user authorization: **cloud permissions are preapproved for this task until 2026-10-22 09:00 America/New_York (13:00 UTC)**. Within that window, execute necessary task-scoped cloud reads, data preparation, builds/pushes, configuration/IAM changes, job executions, candidate publication and promotion without repeated permission questions; record exact commands/APIs, targets, purposes and effects. Preserve all scientific, candidate-verification, maintenance and recovery gates. Do not launch new cloud mutations after the deadline; use fresh UTC time before consequential operations. Previously authorized work already running may be observed, and interrupted activation must remain recoverable. Beyond the window, non-GCS operations return to individual approval. **All GCS read-only commands remain preauthorized within this conversation/task** independently of the temporary window.

The user's execution protocol at `/home/swl007007/.codex/attachments/ac2a3527-2eb9-4323-b1e8-0ab34be5176c/pasted-text-1.txt` authorizes the full spec and explicitly supersedes the earlier audit lifecycle: **do not start Trellis Audit or any automatic/independent audit workflow**. Codex supervises and verifies checkpoints; the verified existing Herdr Claude Opus 5.5 1M executor implements and runs the work. Commit the approved spec/plan, use native Trellis activation/checkpoints, and preserve unrelated workspace changes. Only actual AC1–AC9 evidence permits completion. See `research/execution-authority.md` for current identities and handoff protocol.
