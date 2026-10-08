# October cloud delivery — execution plan draft

Revision 0.4, 2026-10-07. **Authorized for implementation under the Herdr supervisor–executor agreement in `supervision.md`.** Read `prd.md`, `design.md`, and the four research notes. Product decisions G1–G3 are aligned; technical acceptance gates remain. Cloud deployment and production execution remain outside current authorization.

## 1. Planning and lifecycle gates

- [x] Persist the user's confirmed decisions in PRD, including diagnostic unavailability allowing prediction delivery.
- [x] Inspect September output contracts, existing conversion/assembly paths, source reducers, and cloud release mechanics; persist evidence.
- [x] Draft the specification and this ordered plan; distinguish current behavior from proposed deployment.
- [x] Resolve G1: only provider-published completed monthly remote-sensing products; preserve fixed O and causal filling.
- [x] Resolve G2: horizon-specific CSV directories, shared per-system geometry/population references, and one portable archive.
- [x] Resolve G3: submitted versions are fixed, failed runs retain evidence, retries use new run IDs, and identical duplicate events do not repeat scoring.
- [x] Scope T1–T5 with evidence status, owning milestones and stop conditions in design §10; model/lineage evidence is in `research/model-and-lineage-acceptance.md`. This does not mark the technical gates passed.
- [x] Perform the lossless PRD convergence pass: all R1–R9 and 13 acceptance IDs retained; resolved G1–G3 folded into their owning requirements; source anchors preserved; consolidated PRD read end to end. Technical evidence gaps remain explicit rather than being marked passed.
- [x] Present final planning summary and receive a subsequent explicit implementation request: Claude Opus 5.5 1M executor, Codex supervisor, checkpoint communication, no additional Trellis task audit. See `supervision.md` for session identities and scope.
- [ ] Commit the approved task documents separately before product implementation, after GitNexus detect_changes. Use native Trellis task activation and supervisor checkpoints for this task; the user's explicit no-additional-audit instruction supersedes the prior controller register/start/close plan. Do not alter unrelated audit state.
- [x] Curated `implement.jsonl` and `check.jsonl` validate (seven entries each). Follow the repository's active dispatch instructions at execution time. Present GitNexus upstream impact for every function/class/method to change; warn on HIGH/CRITICAL findings. CP0 is reviewed and CP1 is authorized after the task-document baseline commit; see `supervision.md`.

Keep one task while the common input/output contract is converging. The stages below are ordered milestones under one acceptance contract, not speculative independent child projects. Split into child tasks only if implementation later yields independently reviewable releases with explicit dependencies. Preserve a repository-local progress ledger during authorized implementation; it records evidence, not authorization.

## 2. Ordered implementation milestones

### M1 — Freeze reusable model and feature contracts

Inputs: candidate April 0/6/12 packages, September v3 headers/spec, baseline source histories/rosters, research notes.

- [ ] Inspect hashes, horizon metadata, ordered columns, imputation, thresholds, routing, fitted-key provenance and Python/library requirements of all six packages. Determine an accepted environment; do not change fitted values to fit a convenient container.
- [ ] Trace each remote feature from provider/grid/reducer through intermediate panel transformation to model column for both native universes. Explicitly resolve GPP SD and VIIRS SUM/STD lineage.
- [ ] Obtain keyed canonical-panel lineage and a verified native-ID crosswalk for unresolved IPC/FEWS/legacy-FID branches. CH notebook mapping alone is insufficient. Do not reproduce the notebook's cross-area fills or zero substitutions; preserve historical artifacts and validate the explicitly approved new missing-value policy separately.
- [ ] Freeze calendar dependencies, FEWS normalization and label-history missingness behavior. Verify O=2026-10 while future targets can be in 2027; do not add dummy input years unnecessarily.
- [ ] Version the accepted feature/output contracts and model acceptance report format, including schema hashes and the allowed unavailable-diagnostics contract.
- [ ] Under the current supervised local-validation authorization, load and replay accepted candidates on frozen input in the exact environment. Check semantics/operational compatibility; do not claim future forecast accuracy from this replay.

Stop condition: unexplained lineage, numerical environment mismatch or package incompatibility → report and return to design. Do not auto-train. Current unknowns are not evidence that any package is invalid.

Likely code touched only after impact review: package loaders, date-bound wrappers, contract validation. Reuse shared scoring functions rather than copying model algorithms.

### M2 — Parameterize existing conversion and assemble fixed-O inputs

- [ ] Adapt the September raw conversion functions to explicit cutoff/source references. Add independent keep/refresh handling without changing WFP formulas, ACLED matching or historical replacement semantics.
- [ ] Validate uploaded raw columns/dates/series keys; record actual observed coverage and preserve input hashes/bytes.
- [ ] Assemble system-specific histories and O inputs using existing builders/core preprocessing. Introduce only the agreed causal filling and feature audit; keep truth labels distinct.
- [ ] Support the four ACLED/WFP choices; verify non-source columns/native IDs remain unchanged, covered families replace together, and uncovered history remains available.
- [ ] Remove fixed April/September and source-filename assumptions from the new entrypoint. Preserve old h5 replay compatibility where old tools remain callable.

Likely files: `tools/refresh_h5_inputs.py`, existing monthly builders, `cloud/orchestrator/assembly.py`, FEWS normalization/preprocessing only where proven necessary, and small composition code under `cloud/orchestrator/`. Do not replace the old WFP reader wholesale or globally change source formulas.

### M3 — Cloud preparation for four remote-sensing families

- [ ] Add source-specific discovery/export/download for EVI, FLDAS, GOSIF Mean/SD and VIIRS using existing products and verified extraction contracts.
- [ ] Retain Batch/GEE/rasterio machinery; add explicit reducers needed by the contracts rather than a plugin framework. Pin grid/CRS/scale/mask/mosaic rules.
- [ ] Extract to both geometry universes; retain required history and missing-region rows. Distinguish provider lag/completeness from failed acquisition.
- [ ] Produce immutable prepared/source manifests and coverage reports; include source cutoffs, periods, versions and every relevant generation/hash.
- [ ] Implement operator-initiated prepare command and result location. No scheduler or UI is required.

Numerical validation must compare legacy/accepted reference extraction for both mean and dispersion, GPP SD and VIIRS sum on representative normal/boundary/nodata cases. Existing advisory EVI mean checks alone cannot pass this gate. Determine tolerances from the frozen accepted numerical contract; do not relax them simply to pass a drifted result.

### M4 — Batch scoring, country outputs, optional diagnostics and bundle

- [ ] New delivery composition loads prepared/source snapshots and six accepted packages, scores O/0, O/6, O/12 without training, and invokes existing country aggregators.
- [ ] Adapt reusable v3 diagnostic arithmetic to model/horizon-specific evidence. Preserve thresholds, population weighting and complete-month residual semantics.
- [ ] Implement explicit unavailable diagnostics: blank estimates, correct support accounting, sidecar reasons, predictions/current country outcomes retained. Do not turn corrupt referenced evidence or unexpected exceptions into silent nulls.
- [ ] Emit all artifact classes in design §8, including native mapping/geometry, shared population references, frozen inputs and reusable runtime.
- [ ] Adapt portable archive metadata and validators to all scopes; eliminate h5 dates and external research paths. Prove score/export equivalence after relocation, including unavailable diagnostics.

Likely files: small delivery entrypoint, existing shared loaders/scorers, `tools/build_*_country_level_predictions.py`, relevant v3 diagnostic/verification functions, and `tools/package_h5_delivery.py`. Read exact functions and run impact before modifying them. Do not copy September diagnostic values into new forecasts.

### M5 — Manifest event binding, duplicate handling and immutable release

- [ ] Add a versioned dual-system manifest contract and explicit generation-bound request reads, reusing object-store/reference helpers.
- [ ] Add Eventarc/Workflows deployment definition as a thin request-path filter and Cloud Run Jobs invocation. Verify current platform API/region/identity requirements against official docs before creating resources.
- [ ] Bind run sentinel to request identity; identical duplicates return original status without recomputation, different content under one ID conflicts. Failed/abandoned runs require a new ID; no new lease/recovery service.
- [ ] Extend release inventory to the full package; use immutable artifacts and pointer CAS last. Keep the previous accepted pointer on failure/conflict.
- [ ] Preserve the old IPCCH release root during migration; document the proposed dual-system consumer pointer and explicit cutover step.

Likely files: `cloud/common/manifest.py` or an adjacent delivery-specific validator/schema, `cloud/orchestrator/run_state.py`, `cloud/orchestrator/release.py`, new minimal workflow/deployment definitions and runtime packaging. Existing tests must continue to cover old contract behavior.

### M6 — Authorized staging pilot, review, and production handoff

- [ ] Verify actual GCP project, buckets, regions, service accounts, Earth Engine access, configured images and supported Cloud Run resource/time limits. Do not invent deployment identifiers from examples.
- [ ] Obtain the required execution/deployment scope before cloud mutations. Run preparation and scoring in an isolated staging namespace with pinned fixtures first; do not change current production consumers.
- [ ] Demonstrate upload-triggered scoring, exact duplicate-event handling, an intentional failed input, null diagnostics, and release conflict/preservation. Persist execution IDs, hashes, statuses and resource usage.
- [ ] Repeat frozen-input local/cloud comparisons, then run latest-data preparation under the agreed monthly eligibility rule. Distinguish compatibility parity from forecast values legitimately changing with new data.
- [ ] Complete the supervisor's independent checkpoint/final review; do not initiate an additional Trellis task audit. Only then request/perform a specifically authorized production cutover.

## 3. Focused verification

Use existing pytest infrastructure and the accepted environment, not a newly installed arbitrary interpreter. The following are repository-local commands to run during authorized implementation; none has run for this design task:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_manifest_contract.py tests/cloud/test_run_state.py tests/cloud/test_release_writer.py tests/cloud/test_release_conflict.py tests/cloud/test_release_manifest_contract.py tests/cloud/test_release_consumer.py -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_monthly_assembly_wrapper.py tests/test_build_monthly_ipcch_base_input.py tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/test_reshape_remote_sensing_wide_to_long.py -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/fewsnet_partitioned_rf/test_horizons.py tests/fewsnet_partitioned_rf/test_preprocessing.py -q -p no:cacheprovider
```

Substitute the accepted environment's Python executable; record its full version/library manifest. Add focused cases to the existing test modules or one small delivery test module only where needed:

| Case | Required observation |
|---|---|
| October with latest observations in August/September | Targets remain Oct/Apr/Oct; correct observation-month audit |
| Provider offers a completed September product and unfinished October composite | Select September; exclude the unfinished product and fill October with disclosed lineage |
| Later observation exists but earlier month is missing | No future backfill; derived calendar features show the eligible source |
| No history and no applicable imputation | Whole formal release blocked, prior release intact |
| Old but valid latest source | Staleness disclosed, no age-based release block |
| WFP Forecast rows / missing previous calendar month / duplicate series-month | Forecast excluded; no bridged price change; duplicate rejected |
| Four keep/refresh combinations | Each family uses exactly the chosen snapshot and preserves unrelated inputs |
| Missing diagnostic bundle or no support | Affected estimates blank with reason; prediction outputs still released |
| Corrupt supplied diagnostic artifact | Integrity failure, not silently unavailable |
| Threshold and population edge cases | Exact .5/.2/.10/.20 semantics; no zero-filled population/errors |
| Zero/one/multiple complete residual months | Correct null/point/CI and status behavior, reproducible bootstrap |
| Same event twice / conflicting manifest / interrupted original | No duplicate work; visible original state/conflict; new-ID retry policy |
| Concurrent publication or failed artifact validation | Pointer CAS conflict/failure preserves accepted release |
| Extracted portable bundle | Score/export reproduces delivered outputs without external checkout/credentials |

For fixed inputs/models in a pinned environment, preserve September's baseline comparison of exact IDs/dates/discrete decisions and continuous `rtol=0, atol=1e-12` where the existing artifact contract applies. Compare schemas/nulls separately. Raster migration requires its own justified numerical checks; a mismatch needs investigation before widening tolerances. No blanket claim of parity from equal row counts or feature names.

The old `tools/check_h5_delivery_focus.py` uses h5 while the current horizon tests restrict 0/6/12; inspect/parameterize before treating it as a valid check. Do not execute an apparently convenient old command without confirming its current contract.

## 4. Evidence and rollback

Acceptance evidence includes immutable source/model/runtime inventories, feature lineage/parity reports, six prediction comparisons, independent country arithmetic, diagnostic support/reasons, relocated bundle verification, event/run IDs, and release pointer generations. Reports identify checks actually run and mark absent evidence incomplete.

Rollback preserves all raw/prepared/model inputs and accepted releases. Failed candidates stay in their own run prefixes. Restore a previously accepted consumer pointer only through a deliberate generation-checked operation with the approved deployment scope; never delete sentinels or overwrite artifacts to force success. No automatic training or scientific-method fallback is permitted.

Before any commit, run GitNexus `detect_changes` for the intended scope and `git diff --check`; do not include pre-existing unrelated Trellis/skill changes. Before finish, ensure relevant code/artifacts are committed and the supervisor has accepted the final checkpoint. No additional Trellis task audit is used for this task. Planning documents alone do not mark implementation complete.
