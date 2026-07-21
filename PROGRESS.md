# FEWSNET Partitioned RF Model Suite Progress

## Authority

- Approved design: `docs/superpowers/specs/2026-07-20-partitioned-rf-model-suite-design.md`
- Implementation plan: `docs/superpowers/plans/2026-07-20-fewsnet-partitioned-rf-model-suite.md`
- Design base commit: `e6afd2cebde02e14501dca52e959e395c54c30b7`
- Initial plan SHA-256: `46688dbc82ecd99169a0e63aedfbbb1f7451b2a6e23a9fa187c23f24d630937c`
- Current approved design SHA-256: `44ef7a355ff16fc953b663d1770312da2200ff040e9129b9e9f203082aae346a`
- Current normalized plan SHA-256: `981c6508f6fd182a3deca2e4186a19db4a36caa65bf6616f27232466a4fcbf3e`

## Execution Context

- Worktree: `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.worktrees/fewsnet-partitioned-rf-suite`
- Branch: `features/fewsnet-partitioned-rf-suite`
- Current task: Task 18 third narrow independent-review fix wave
- Current state: Tasks 1-17 are complete; the formal-run evidence-indeterminate and production GCS missing-pointer contracts are synchronized, with Phase B strict RED/GREEN implementation pending
- Blockers: none for local/fake implementation; every real GCP/GCS/Vertex/Registry/Batch/alias/release-pointer mutation remains unauthorized
- Cloud mutation status: no GCP, GCS, Vertex AI, Model Registry, Batch Prediction, alias, or release-pointer write has been attempted

## Task Status

| Task | Status |
| --- | --- |
| 1. Establish the isolated runtime package and immutable partition asset | complete |
| 2. Define shared types and machine-readable contracts | complete; controller review clean |
| 3. Add binary-safe local and GCS artifact storage | complete; independent review clean |
| 4. Stage and validate immutable FEWSNET input snapshots | complete; independent review clean |
| 5. Build the frozen Stage 3 feature contract and leak-free feature frame | complete; independent review clean |
| 6. Normalize the bootstrap panel and bind its audit into snapshots | complete; independent review clean through `d403c1e` |
| 7. Implement keyed horizon alignment and temporal windows | complete; independent re-review clean through `8ff2847`; one Minor deferred |
| 8. Validate and route the fixed partition map | complete; independent re-review clean through `20a6e0e` |
| 9. Implement fit-slice-only max-plus imputation and threshold selection | complete; independent review clean through `b91e24a`; one Minor deferred |
| 10. Train partitioned RF models and produce formal local predictions | complete; independent re-review clean through `891b0f9` |
| 11. Freeze reference Stage 3 parity evidence | complete; independent re-review clean through `932cfd5` |
| 12. Write and validate Vertex-compatible model packages | complete; independent re-review approved through `27742aa`; two Minor findings deferred |
| 13. Build the three-horizon training worker and Vertex Custom Job spec | complete; independent re-review clean through `f0da32a`; controller verification clean |
| 14. Serve registered packages with a shared custom prediction container | complete; independent re-review clean through `6ea5873`; controller verification clean |
| 15. Register three stable parent models and immutable candidate versions | complete through `4d9f009`; independent re-review and controller verification clean |
| 16. Run exact-version Batch Prediction and normalize formal CSVs | complete through `35b96c5`; final independent review and controller verification clean |
| 17. Validate three-horizon outputs and implement alias rollback publication | complete through `751ad4d`; final independent review 0 Critical/0 Important/0 Minor and controller verification clean |
| 18. Orchestrate discover -> train -> register -> Batch -> promote | third narrow review authority synchronized; Phase B implementation and independent re-review pending |
| 19. Add runbook, gated GCP smoke coverage, and full acceptance verification | pending |

## Task 1 Evidence

- Baseline: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests -q -p no:cacheprovider` -> `297 passed, 1 skipped`
- RED: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/fewsnet_partitioned_rf/test_runtime_foundation.py -q -p no:cacheprovider` -> `2 failed`; both failures were the expected `FileNotFoundError` for the absent requirements file and partition CSV.
- GREEN: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_runtime_foundation.py -q -p no:cacheprovider` -> `2 passed in 0.12s`.
- Full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `299 passed, 1 skipped, 24 subtests passed in 14.82s`.
- Final fresh full regression before commit: the same command -> `299 passed, 1 skipped, 24 subtests passed in 17.12s`.
- Dependency validation: `.venv/bin/python -m pip check` -> `No broken requirements found.`
- Partition validation: copied asset is byte-identical to the approved source, SHA-256 `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`, with 5,365 mapped rows plus the header.
- Plan validation: SHA-256 remained `46688dbc82ecd99169a0e63aedfbbb1f7451b2a6e23a9fa187c23f24d630937c`.
- Staged-scope review: GitNexus `detect_changes(scope="staged", repo="IPCCH_operational", worktree="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.worktrees/fewsnet-partitioned-rf-suite")` failed with the known index error: `LadybugDB unavailable for /mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.gitnexus/lbug. Another process may be rebuilding the index. Retry later. (Runtime exception: Couldn't replay shadow pages under read-only mode. Please re-open the database with read-write mode to replay shadow pages.)`
- Plain `git diff --cached --check`: exit `2` because Git treated the approved CSV's CRLF terminators as trailing whitespace on all 5,366 lines. The asset was not normalized because byte identity and the approved SHA-256 are mandatory.
- Git fallback staged-scope review: `git -c core.whitespace=cr-at-eol diff --cached --check` -> exit `0`; `git diff --cached --name-status` showed exactly `PROGRESS.md`, the unchanged implementation plan, the requirements file, the package/config/partition files, and the two foundation test files.
- Implementation commit: `e1f1977d81e83159d006bbd62483fe94fb32f48a` (`e1f1977 feat: establish FEWSNET partitioned RF runtime`).

### Task 1 Environment Note

- `.venv/bin/python -m pip install --upgrade pip` failed on the Dropbox/DrvFs worktree after beginning pip's self-uninstall: `ERROR: Could not install packages due to an OSError: [Errno 13] Permission denied: 'commands'`.
- The failed rename left `pip/`, `~ip/`, and `~ip-24.0.dist-info` under `site-packages`, removed `.venv/bin/pip`, and made `.venv/bin/python -m pip` fail with `ModuleNotFoundError: No module named 'pip._internal.cli'`.
- A fresh ext4 control venv at `/tmp/fewsnet-pip-probe-task1` had the same Python symlink layout and upgraded from pip 24.0 to pip 26.1.2 successfully with the identical command.
- Approved workaround: rebuild `.venv` with `python3 -m venv --clear .venv`, retain bundled pip 24.0, and install the exact pinned requirements. The pinned install completed successfully; no repository code or configuration was changed for this local filesystem limitation.

## Task 2 Evidence

- RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_contracts.py -q -p no:cacheprovider` -> collection exit `2` with the expected `ModuleNotFoundError: No module named 'fewsnet_partitioned_rf_pipeline.core'` before any Task 2 implementation or fixture existed.
- GREEN: the same focused command -> `4 passed in 0.47s`.
- Schema coverage: `Draft202012Validator.check_schema(...)` loaded and validated all seven contracts: `source-snapshot`, `deployment`, `model-package`, `training-report`, `prediction-record`, `run-manifest`, and `suite-manifest`.
- Full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `303 passed, 1 skipped, 24 subtests passed in 14.95s`.
- Contract coverage: immutable GCS object generations and SHA-256 identities, digest-pinned deployment images with exact cross-field digest matching, model package/runtime metadata, aggregate training and threshold evidence, the twelve formal prediction fields, monotonic run phases including candidate-only `candidate_validated`, and exact three-horizon suite release identities.
- Staged-scope review: GitNexus `detect_changes(scope="staged", repo="IPCCH_operational", worktree="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.worktrees/fewsnet-partitioned-rf-suite")` -> LOW risk, 14 changed files, 4 indexed documentation symbols, and 0 affected execution processes.
- Blockers: none.
- Implementation commit: `93d49b929d4f7578e905116e9eb3b95665bf04fb` (`93d49b9 feat: define FEWSNET suite contracts`).

### Task 2 Review Fix Evidence

- Systematic reproduction: candidate-only run manifests with the wrong phase/empty evidence, training reports with empty fixed-cluster maps, invalid source/release timestamps, contradictory package horizons, and map-key/model-horizon mismatches were all accepted by the committed contracts.
- GitNexus upstream impact for `validate_payload` returned `UNKNOWN`/target not found because the main-branch index does not contain Task 2; current-tree caller search found only `validate_deployment` and the focused contract tests, so the present blast radius is low.
- Review RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_contracts.py -q -p no:cacheprovider` -> `15 failed, 10 passed in 1.39s`; every failure was the expected `Failed: DID NOT RAISE ValueError` for an accepted-invalid payload.
- Review-focused GREEN: the same file with `-k "candidate_validated or early_run_manifest or training_report or invalid_date_time or horizon_identity"` -> `21 passed, 4 deselected in 0.59s`.
- All Task 2 tests: the full contract-test file -> `25 passed in 0.56s`.
- Schema audit: all seven Draft 2020-12 schemas pass metaschema validation; fixed-object `additionalProperties: false` coverage is clean; cluster-state and SMOTE maps require exact keys `0..16`; the RFC 3339 `date-time` `FormatChecker` is registered.
- Full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `324 passed, 1 skipped, 24 subtests passed in 15.55s`.
- First staged-scope gate: GitNexus `detect_changes(scope="staged", repo="IPCCH_operational", worktree="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.worktrees/fewsnet-partitioned-rf-suite")` -> LOW risk, 7 changed files, 4 indexed documentation symbols, and 0 affected execution processes.
- Review-fix commit: `d65a615815c0aad956c2942c7f263e9ab830ed5b` (`d65a615 fix: harden FEWSNET suite contracts`).
- Controller re-review: clean; Task 3 may proceed from frozen `ObjectRef` and strict contracts.
- Second ledger-only staged-scope gate: GitNexus `detect_changes(scope="staged", repo="IPCCH_operational", worktree="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.worktrees/fewsnet-partitioned-rf-suite")` -> LOW risk, exactly 1 changed file (`PROGRESS.md`), 3 indexed documentation symbols, and 0 affected execution processes.

### Task 2 RFC3339 Follow-up Evidence

- Systematic reproduction: public `validate_payload("source-snapshot", ...)` accepted `2026-07-20T00:00:00+00:60` because `datetime.fromisoformat` normalized it to offset `+01:00`; `+24:00` was already rejected, while `Z`, `+05:30`, and boundary `-23:59` remained valid and timezone-aware.
- GitNexus upstream impact for `_is_rfc3339_date_time` returned `UNKNOWN`/target not found because the main-branch index predates the review-fix symbol; current-tree search shows the helper is registered only on the local `FORMAT_CHECKER`, which is consumed by `validate_payload`, so the current blast radius is narrow and low.
- RFC3339 RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_contracts.py -q -p no:cacheprovider -k "rfc3339_numeric_offsets or valid_rfc3339_timezone_offsets"` -> `1 failed, 6 passed, 25 deselected in 1.03s`; only `+00:60` produced the expected `Failed: DID NOT RAISE ValueError`.
- RFC3339 GREEN: the same focused command -> `7 passed, 25 deselected in 0.50s`.
- All Task 2 tests: the full contract-test file -> `32 passed in 0.56s`.
- Full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `331 passed, 1 skipped, 24 subtests passed in 18.03s`.
- Direct public-validator audit: `+00:60` and `+24:00` reject; `Z`, `+05:30`, `-04:00`, `+23:59`, and `-23:59` validate.
- First RFC3339 staged-scope gate: GitNexus `detect_changes(scope="staged", repo="IPCCH_operational", worktree="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.worktrees/fewsnet-partitioned-rf-suite")` -> LOW risk, exactly 3 changed files (`PROGRESS.md`, the schema validator, and Task 2 contract tests), 3 indexed documentation symbols, and 0 affected execution processes.
- RFC3339 fix commit: `7dc06276e38ce666441d8630a2cd655cd6f9138e` (`7dc0627 fix: enforce FEWSNET RFC3339 offsets`).
- Controller re-review: clean; no remaining Task 2 gate blocks Task 3.
- Second RFC3339 ledger-only staged-scope gate: GitNexus `detect_changes(scope="staged", repo="IPCCH_operational", worktree="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.worktrees/fewsnet-partitioned-rf-suite")` -> LOW risk, exactly 1 changed file (`PROGRESS.md`), 3 indexed documentation symbols, and 0 affected execution processes.

## Task 3 Evidence

- Start state: Task 2 controller review is clean through `32d7e7908758ad7c67da766467c23c199dccd3ce`; Task 3 started with no blocker.
- RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_storage.py -q -p no:cacheprovider` -> collection exit `2` with the expected `ModuleNotFoundError: No module named 'fewsnet_partitioned_rf_pipeline.vertex'` before storage implementation existed.
- Mandated GREEN: the same focused command -> `6 passed in 0.77s` after the six plan tests.
- Prefix regression RED/GREEN: a behavior audit found trailing-slash GCS-style list prefixes were rejected; the focused regression first failed `1 failed, 6 deselected in 1.38s`, then passed `1 passed, 6 deselected in 0.64s`; final storage coverage is `7 passed in 0.58s`.
- GCS adapter audit: exact `upload_from_string`, `upload_from_filename`, `download_as_bytes`, and `download_to_filename` generation arguments; byte identity; SHA-256 custom metadata; immutable/mutable retry behavior; missing-checksum hard failure; and non-`gs://` rejection all passed against a behavior-preserving storage double.
- Full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `338 passed, 1 skipped, 24 subtests passed in 14.49s`.
- Preservation: implementation-plan SHA-256 remains `46688dbc82ecd99169a0e63aedfbbb1f7451b2a6e23a9fa187c23f24d630937c`; partition-asset SHA-256 remains `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Preliminary staged-scope gate: GitNexus `detect_changes(scope="staged", repo="IPCCH_operational", worktree="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.worktrees/fewsnet-partitioned-rf-suite")` -> LOW risk, exactly 4 changed files, 5 indexed documentation symbols, and 0 affected execution processes; the new storage symbols are not present in the main-branch index.
- Preliminary Git staged checks: `git diff --cached --check` -> exit `0`; `git diff --cached --name-status` showed exactly `PROGRESS.md`, the two new `vertex` files, and `test_storage.py`.
- Final implementation staged gate repeated the same LOW-risk, 4-file, 0-process GitNexus scope; `git diff --cached --check` remained clean and staged paths remained exact.
- Implementation commit: `05682609f35cda2a7cf0f75c143d024c34222426` (`0568260 feat: add FEWSNET artifact storage`).
- Blockers: none. Controller review is pending before Task 4 starts.

### Task 3 Review Fix Evidence

- Review scope: make each local generation check plus filesystem read/write/copy/reference operation atomic, confine all local URI mappings below the resolved bucket root across platforms and symlinks, and replace the ad hoc GCS audit with durable stateful adapter tests.
- GitNexus upstream impact for `LocalArtifactStore`, `_parse_gs_uri`, and every existing local-store method returned `UNKNOWN`/target not found because the main-branch index predates Task 3; each result reported zero indexed impacts. Current-tree callers are limited to the Task 3 tests, the three storage retry helpers, package exports, and the future Task 4 recording-store test subclass, so no HIGH or CRITICAL warning applies.
- Review RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_storage.py -q -p no:cacheprovider` -> `6 failed, 17 passed in 1.48s`. The failures proved both create-only writers could succeed, an exact-generation reader could return replacement bytes, backslash object/bucket and drive-style bucket identities were accepted, and an existing symlink could write outside the bucket root. Valid `//`, `.`/`..`, bucket-root/trailing-prefix, and durable GCS behavior controls already passed.
- Minimal fix: one shared `threading.RLock` per `LocalArtifactStore` now encloses generation check plus read/write/copy plus generation/reference completion for put/read/upload/download/get-ref/list paths; `RLock` permits list-to-get-ref nesting. URI parsing rejects backslashes, NULs, unsafe bucket identities, and exact unsafe components, while local path resolution requires every candidate to remain below the resolved bucket root.
- GCS compatibility RED/GREEN: self-review caught an over-broad colon rejection; the valid RFC3339-style object-name test first failed `1 failed, 23 deselected in 1.23s`, then passed `1 passed, 23 deselected in 0.60s` after narrowing validation. Existing GCS object-name behavior remains intact apart from the required unsafe-identity rejection.
- All storage tests: `24 passed in 3.75s`, including durable stateful fake-GCS coverage for SHA metadata persistence, exact byte/file upload and download generation arguments, reference listing, non-`gs://` rejection, `PreconditionFailed` conversion, missing-checksum hard failure, and valid colon-bearing object names.
- Full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `355 passed, 1 skipped, 24 subtests passed in 17.84s`.
- Preservation: implementation-plan SHA-256 remains `46688dbc82ecd99169a0e63aedfbbb1f7451b2a6e23a9fa187c23f24d630937c`; partition-asset SHA-256 remains `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Preliminary review-fix staged gate: GitNexus `detect_changes(scope="staged", repo="IPCCH_operational", worktree="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.worktrees/fewsnet-partitioned-rf-suite")` -> LOW risk, exactly 3 changed files, 6 indexed documentation symbols, and 0 affected execution processes; the Task 3 Python symbols remain absent from the main-branch index.
- Preliminary Git staged checks: `git diff --cached --check` -> exit `0`; `git diff --cached --name-status` showed exactly `PROGRESS.md`, `vertex/storage.py`, and `test_storage.py`.
- Final review-fix staged gate repeated the same LOW-risk, 3-file, 0-process GitNexus scope; `git diff --cached --check` remained clean and staged paths remained exact.
- Original implementation commit: `05682609f35cda2a7cf0f75c143d024c34222426` (`0568260 feat: add FEWSNET artifact storage`).
- Review-fix commit: `5b8df8008a486e8a1ed6ceb0eea41b1032c20842` (`5b8df80 fix: make FEWSNET storage atomic and confined`).
- Controller re-review: clean through ledger commit `0b09ff199e8feed9c959b615a13af6657546db1b`; Task 4 may consume the frozen storage interfaces.
- Blockers: none.

## Task 4 Evidence

- Start state: Task 3 independent review is clean through `0b09ff199e8feed9c959b615a13af6657546db1b`; Task 4 started with no blocker and consumes the frozen `SnapshotManifest`, source-snapshot schema, `ArtifactStore`, and immutable upload helpers without modifying them.
- Pre-edit GitNexus scope: Task 4 adds new files only. The `IPCCH_operational` index is on `main` and predates the new FEWSNET package symbols; concept query found no existing snapshot-staging execution flow to modify, so no existing function/class/method required an upstream impact call.
- RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_snapshot_staging.py -q -p no:cacheprovider` -> collection exit `2` with the expected `ModuleNotFoundError: No module named 'fewsnet_partitioned_rf_pipeline.core.data'` before Task 4 production files existed (`1 error in 4.61s`).
- First GREEN run: `11 passed, 1 failed in 6.64s`; the only failure was a test-side GeoParquet CRS string assumption because GeoPandas read standards-compliant PROJJSON instead of the literal authority string. The assertion was corrected to `crs.to_epsg() == 4326` without changing production code.
- Focused GREEN: the mandated snapshot command -> `12 passed in 4.66s`.
- CLI help: `.venv/bin/python -m fewsnet_partitioned_rf_pipeline.cli.stage_snapshot --help` -> exit `0` and `usage:` with exactly `--panel`, `--boundaries`, `--destination-root`, and `--created-at-utc` plus standard help.
- Snapshot coverage: streaming three-column panel reads; normalized monthly duplicate detection across chunks; latest feature/label discovery; integer-like admin-code normalization; exact panel/spatial area equality; strict EPSG:4326 input; one non-null geometry per unique normalized boundary code; sorted GeoParquet/admin universe; canonical content SHA/snapshot ID; schema-valid manifest; manifest-last ordering; byte-identical immutable retry/no-op; and CLI success/error behavior.
- Full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `367 passed, 1 skipped, 24 subtests passed in 18.78s`.
- Final fresh pre-commit regression: the same full-suite command -> `367 passed, 1 skipped, 24 subtests passed in 18.03s`; CLI help and `py_compile` also repeated with exit `0`.
- Static/environment checks: `py_compile` completed for all three new production files and the snapshot test; `.venv/bin/python -m pip check` -> `No broken requirements found.`
- Preservation: implementation-plan SHA-256 remains `46688dbc82ecd99169a0e63aedfbbb1f7451b2a6e23a9fa187c23f24d630937c`; partition-asset SHA-256 remains `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Preliminary staged-scope gate: GitNexus `detect_changes(scope="staged", repo="IPCCH_operational", worktree="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.worktrees/fewsnet-partitioned-rf-suite")` -> LOW risk, exactly 5 changed files, 4 indexed documentation symbols, and 0 affected execution processes; the new Task 4 Python symbols are absent from the main-branch index. `git diff --cached --check` exited `0`, and `git diff --cached --name-status` showed exactly `PROGRESS.md`, the two new `cli` files, `core/data.py`, and `test_snapshot_staging.py`.
- Final implementation staged gate repeated the same LOW-risk, 5-file, 0-process GitNexus scope; `git diff --cached --check` remained clean and staged paths remained exact.
- Implementation commit: `c7bd125f5e969fd6d699b368cdb038872d8370f2` (`c7bd125 feat: stage immutable FEWSNET snapshots`).
- Blockers: none.

### Task 4 Content-No-Op Follow-up Evidence

- Root cause: `snapshot_content_sha256` and `snapshot_id` correctly excluded `created_at_utc`, but a later restage with identical source content and a new administrative timestamp constructed different manifest bytes. The byte-exact immutable helper therefore raised `GenerationConflict` instead of reusing the already-authoritative snapshot manifest.
- GitNexus upstream impact for `stage_snapshot` returned `UNKNOWN`/target not found with `0` indexed impacts because the main-branch index predates Task 4. Current-tree caller search found only the new staging CLI and Task 4 tests, so no HIGH or CRITICAL warning applies.
- Follow-up RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_snapshot_staging.py -q -p no:cacheprovider -k "only_created_at_changes"` -> `1 failed, 12 deselected in 6.55s`; the exact failure was `GenerationConflict: immutable object already exists with different bytes` for `source_manifest.json`.
- Minimal fix: before manifest creation, reuse an existing schema-valid manifest only when its snapshot/content identity, object URIs/checksums/sizes, counts, CRS, months, source types, and admin mapping match. Creation timestamp, bootstrap paths, and object generations are excluded consistently with the approved content identity. A concurrent manifest-create loser performs the same validation after its generation conflict; all substantive drift still fails closed.
- Follow-up GREEN: the focused regression -> `1 passed, 12 deselected in 4.86s`; all Task 4 snapshot tests -> `13 passed in 4.88s`.
- Follow-up full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `368 passed, 1 skipped, 24 subtests passed in 18.96s`; `py_compile` for the modified production/test files exited `0`.
- Preliminary follow-up staged gate: GitNexus `detect_changes(scope="staged")` -> LOW risk, exactly 3 changed files, 3 indexed documentation symbols, and 0 affected execution processes; the Task 4 Python symbols remain absent from the main index. `git diff --cached --check` exited `0`, and staged paths were exactly `PROGRESS.md`, `core/data.py`, and `test_snapshot_staging.py`.
- Final follow-up staged gate repeated the same LOW-risk, 3-file, 0-process GitNexus scope; `git diff --cached --check` remained clean and staged paths remained exact.
- Follow-up fix commit: `86937a961a87eb50711a70daf723cdebb73f500f` (`86937a9 fix: preserve FEWSNET snapshot restaging no-op`).
- Blockers: none.

### Task 4 Independent-Review Fix Evidence

- Review findings: existing-manifest reuse did not prove that each recorded artifact generation remained exactly readable; panel inspection preceded the later hash/upload and could describe different bytes; default pandas NA parsing and manual CSV construction did not preserve valid identifiers such as `NA` and `A,B`.
- GitNexus upstream impact for `inspect_panel`, `_reuse_existing_manifest`, and `stage_snapshot` returned `UNKNOWN`/target not found with `0` indexed impacts because the main-branch index predates Task 4. Current-tree callers are limited to the Task 4 CLI, tests, and internal calls, so no HIGH or CRITICAL warning applies.
- Exact-generation RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_snapshot_staging.py -q -p no:cacheprovider -k "stale_exact_artifact_generation or unreadable_generation_in_existing_manifest"` -> `2 failed, 16 deselected in 6.09s`; both failures were `Failed: DID NOT RAISE GenerationConflict` for stale generation `1` after an identical-byte generation `2` replacement and schema-valid generation `999`.
- Captured-panel RED: the same test file with `-k "one_captured_panel_version"` -> `1 failed, 17 deselected in 6.23s`; the uploaded CSV contained the appended `2026-05` fifth row even though the manifest still recorded four rows through `2026-04`.
- Identifier REDs: `-k "preserves_na_admin_identifier"` -> `1 failed, 17 deselected in 6.09s` because `NA` became missing; `-k "quotes_admin_universe_csv_identifiers"` -> `1 failed, 17 deselected in 6.23s` because the output contained unquoted `A,B`.
- Minimal fixes: capture the bootstrap panel with `shutil.copyfile` into the task temp directory before inspection, then inspect/hash/upload only that captured path; preserve identifier strings with `keep_default_na=False` while treating blank target cells as unlabeled; write the sorted one-column admin universe with `csv.writer(..., lineterminator="\\n")`; and before manifest reuse stream-download all three artifact refs at their recorded generations and verify recorded SHA-256 plus size.
- Focused GREEN: exact-generation selection -> `2 passed, 16 deselected in 4.02s`; captured-panel selection -> `1 passed, 17 deselected in 3.94s`; `NA` selection -> `1 passed, 17 deselected in 3.51s`; CSV quoting selection -> `1 passed, 17 deselected in 3.28s`.
- Complete Task 4 GREEN: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_snapshot_staging.py -q -p no:cacheprovider` -> `18 passed in 5.24s`.
- Full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `373 passed, 1 skipped, 24 subtests passed in 18.35s`.
- CLI/static/environment checks: stage-snapshot `--help` exited `0` with the same four required options; `py_compile` exited `0`; `.venv/bin/python -m pip check` -> `No broken requirements found.`
- Preservation: implementation-plan SHA-256 remains `46688dbc82ecd99169a0e63aedfbbb1f7451b2a6e23a9fa187c23f24d630937c`; partition-asset SHA-256 remains `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Fresh controller pre-commit verification: the complete snapshot suite -> `18 passed in 6.55s`; the full repository suite -> `373 passed, 1 skipped, 24 subtests passed in 22.12s`; CLI help, `py_compile`, `pip check`, both preserved SHA-256 identities, and `git diff --check` all passed.
- Preliminary independent-review staged gate: GitNexus `detect_changes(scope="staged")` -> LOW risk, exactly 3 changed files, 3 indexed documentation symbols, and 0 affected execution processes; `git diff --cached --check` exited `0`; staged paths were exactly `PROGRESS.md`, `core/data.py`, and `test_snapshot_staging.py`; `.superpowers/` remained untracked and unstaged.
- Final independent-review staged gate repeated the same LOW-risk, 3-file, 0-process GitNexus scope; `git diff --cached --check` remained clean, staged paths remained exact, and `.superpowers/` remained unstaged.
- Independent-review fix commit: `55866bb846f957d783680d400ac9954081a9a5b6` (`55866bb fix: harden FEWSNET snapshot identity`).
- Controller re-review: clean through ledger commit `f0abf6b785bc005e5f3d63bec590b879fb09fcc2`; Task 5 may proceed from the frozen snapshot interfaces.
- Blockers: none.

## Task 5 Evidence

- Start state: Task 4 controller re-review is clean through `f0abf6b785bc005e5f3d63bec590b879fb09fcc2`; Task 5 started from that exact reviewed HEAD with no blocker.
- Pre-edit GitNexus scope: Task 5 adds new production/test/asset paths and does not modify an existing function, class, or method. The `IPCCH_operational` index remains on `main` and predates the Task 5 symbols, so no indexed execution flow existed to modify.
- RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_preprocessing.py -q -p no:cacheprovider` -> collection exit `2` with the expected `ModuleNotFoundError: No module named 'fewsnet_partitioned_rf_pipeline.core.preprocessing'` before any Task 5 production code existed (`1 error in 4.19s`).
- RED coverage: approved reference predictors and exclusions, calendar-keyed target lags and rolling/EVI features across a missing month, exact frozen output order, sorted ISO/year/month encodings, ignored undeclared raw columns, missing raw input rejection, duplicate/unknown/missing contract names, checksum drift, unseen categories, numeric coercion, infinity-to-NaN handling, explicit no-scaling behavior, and duplicate area-month rejection.
- Focused GREEN: the mandated preprocessing command -> `9 passed in 4.41s`.
- AEZ missing-value self-review RED: the focused `-k normalizes_aez` selection failed `1 failed, 8 deselected in 5.66s` because pandas nullable boolean masks converted a missing AEZ value to `0.0`.
- GitNexus upstream impact for the new `_normalize_aez` helper returned `UNKNOWN`/target not found with `0` indexed impacts because the main-branch index predates Task 5. Current-tree scope is one internal caller (`Stage3FeatureBuilder.transform`) plus the focused tests, so no HIGH or CRITICAL warning applies.
- AEZ regression GREEN: the same focused selection -> `1 passed, 8 deselected in 3.92s`; the complete preprocessing file then returned `9 passed in 4.41s`.
- Fragmentation self-review RED: an 80-column frozen-source regression emitted pandas `PerformanceWarning` records and failed `1 failed, 9 deselected in 5.83s`; a 500-row slice of the approved panel reproduced the warnings during per-column dummy/group insertion even though values were correct.
- GitNexus upstream impact for the new `Stage3FeatureBuilder.transform` method returned `UNKNOWN`/target not found with `0` indexed impacts because the main-branch index predates Task 5. Current-tree callers are limited to the new preprocessing tests, so no HIGH or CRITICAL warning applies.
- Fragmentation regression GREEN: numeric, calendar-dummy, AEZ-group, and final predictor columns are assembled in consolidated DataFrames; the focused selection -> `1 passed, 9 deselected in 3.92s`, and the complete preprocessing file -> `10 passed in 4.40s`.
- Actual-panel transform smoke: a 500-row approved-panel slice transformed with pandas `PerformanceWarning` promoted to an error, producing `500` rows, `123` ordered `float64` predictors, period-month identity, and zero infinities without warnings.
- Actual-panel contract generation: the exact approved command read `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.csv` and printed `feature_count=123`, `required_feature_checks=passed`, and `excluded_feature_checks=passed` before writing the local JSON asset. The contract has `76` required raw columns, `22` sorted ISO codes, all `float64` feature dtypes, source-column SHA-256 `6060b8643eac62d21d67141d9cca17a2361b2b3af9d893f6fd8f7e9d5a4b1d25`, and feature-schema SHA-256 `6e6f0bdc2df7bb40ec37f2d44926d2a24fbb746bc5272ed9b93a7ae4047d891b`.
- Frozen-asset determinism: regenerating from the approved panel preserved byte-identical JSON SHA-256 `3779c6bcde70560c0e1514c563ced6e7bd559c6d352689398c3cecb93d44a67b`.
- JSON/static/environment checks: `python3 -m json.tool` parsed the checked-in contract; `py_compile` passed for production and tests; `.venv/bin/python -m pip check` reported `No broken requirements found.`
- Full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `383 passed, 1 skipped, 24 subtests passed in 19.97s`.
- Final fresh pre-commit verification: the complete preprocessing file -> `10 passed in 4.46s`; the full repository suite -> `383 passed, 1 skipped, 24 subtests passed in 19.38s`; JSON parsing and `py_compile` both exited `0`.
- Preservation: implementation-plan SHA-256 remains `46688dbc82ecd99169a0e63aedfbbb1f7451b2a6e23a9fa187c23f24d630937c`; partition-asset SHA-256 remains `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Contract boundaries: runtime transform uses only the checked-in allowlist and mapping, ignores undeclared extra raw source columns, performs no fit-time statistics, scaling, standardization, or imputation, and creates no dynamic horizon-specific `*_lag{horizon}m` columns. No cloud write or external `Food_Crisis_Cluster` runtime import/invocation was added.
- Implementation commit: `8ce39cd56f567a416f20deb0e60b77d0b0cd722d` (`8ce39cd feat: freeze FEWSNET Stage 3 features`).
- Independent review: Approved with no Critical or Important findings. One Minor is deferred to final whole-branch review: add a direct regression that loads the checked-in feature-contract asset and asserts its schema SHA-256 identity.
- Cross-task blocker at Task 5 completion: the approved raw panel has duplicate normalized `FEWSNET_admin_code + month` keys for admin `2996` at `2025-10` and `2026-02`. Task 4 `inspect_panel` hard-fails first at `duplicate FEWSNET_admin_code + date month: 2996 + 2025-10`. The `2025-10` pair differs only in `Tair_zscore` and `Rainf_zscore`; the `2026-02` pair is identical for those audited fields. The user subsequently approved the narrow Task 6 normalization policy recorded below; this blocker is resolved at design level but not yet implemented.

## Bootstrap Normalization Design and Plan Synchronization

- User-approved policy: preserve the raw combined CSV; deduplicate after stable admin/date ordering and before the reference notebook's climate derivations; collapse a duplicate group only when all columns except `Tair_zscore` and `Rainf_zscore` are equal; fail closed on every other conflict; recompute the global 12-row climate rolling means and within-admin sample z-scores; write a new versioned normalized CSV and audit JSON.
- Approved real-source expectations: raw `1,120,730` rows; normalized `1,120,728` rows; `5,718` areas; two duplicate groups and two removed rows; latest feature month `2026-04`; latest label month `2026-02`.
- Snapshot contract decision: Task 6 adds `normalization_audit: ObjectRef`, bumps the source snapshot contract to `fewsnet-source-snapshot-v2`, includes the audit in snapshot identity/exact-generation validation, and leaves Task 4's duplicate hard gate unchanged.
- Implementation order decision: docs-only synchronization and commit must finish before any Task 6 production/test implementation. Task 6 then follows TDD, GitNexus upstream impact for every existing symbol changed, full regression, real normalized-file generation, and real shapefile/local-store staging with no GCP write.
- Design SHA-256 after synchronization: `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`.
- Plan SHA-256 after inserting Task 6 and renumbering the former Tasks 6-18 to Tasks 7-19: `977a88cd4b00e0bd9c560ffc2bb9aa752a0f76adaff59128d63b66a6745f176f`.
- Fixed partition SHA-256 remains `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Feature schema SHA-256 remains `6e6f0bdc2df7bb40ec37f2d44926d2a24fbb746bc5272ed9b93a7ae4047d891b`; checked-in feature-contract JSON SHA-256 remains `3779c6bcde70560c0e1514c563ced6e7bd559c6d352689398c3cecb93d44a67b`.
- No implementation file or external source artifact was changed during this synchronization step.
- Cross-artifact consistency gate: PASS. The design and plan SHA-256 values match this ledger; plan headings and status rows are sequential `1..19`; the approved raw/normalized counts, area count, duplicate keys, excluded z-score columns, snapshot-v2 audit interface, and no-cloud-write boundary are present in all three artifacts.
- Placeholder/contradiction scan: no `TBD`, `TODO`, `implement later`, `fill in details`, or `similar to Task` residue in the synchronized design, plan, or FEWSNET ledger.
- Git whitespace/scope gate: `git diff --check` and `git diff --cached --check` both exited `0`; the staged set contains exactly `PROGRESS.md`, the FEWSNET implementation plan, and the FEWSNET design; `.superpowers/` remains untracked and unstaged.
- GitNexus staged gate: LOW risk, three changed documentation files, 38 indexed documentation sections, and zero affected execution processes. The index is based on the pre-amendment headings, but no code symbol or execution flow is affected.

## Task 6 Evidence

- Start state: the docs-only normalization amendment is committed at `7e961b3815a39b5089f10b1f8005b108501078b5`; the raw assembled FEWSNET CSV was preserved and neither approved normalized-v1 artifact existed.
- Normalization RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_panel_normalization.py tests/fewsnet_partitioned_rf/test_contracts.py -q -p no:cacheprovider` -> collection exit `2` with the expected `ModuleNotFoundError: No module named 'fewsnet_partitioned_rf_pipeline.cli.normalize_panel'` before production normalization code or schema existed (`1 error in 4.12s`).
- Core normalization GREEN: the same focused command -> `42 passed in 4.29s`; `.venv/bin/python -m fewsnet_partitioned_rf_pipeline.cli.normalize_panel --help` exited `0` and printed the three required arguments.
- Exact-worktree GitNexus impact gate after refreshing the feature index: `SnapshotManifest` MEDIUM (`16` impacted, `8` direct); `_snapshot_semantic_payload` HIGH (`14` impacted, `1` direct caller, `2` affected process groups, `3` modules); `_manifest_from_payload` HIGH with the same counts; `_validate_exact_artifact_references` HIGH with the same counts; `stage_snapshot` MEDIUM (`16` impacted, `12` direct, `1` affected process group); CLI `_parser` LOW (`5` impacted, `1` direct); CLI `main` LOW (`4` impacted, `3` direct). The three HIGH results all converge on the single direct caller `_reuse_existing_manifest` and the intended FEWSNET snapshot/CLI/test chain. Work stopped before snapshot edits, the controller independently reproduced and reviewed the blast radius, and explicit GO authorization was recorded before implementation continued.
- Snapshot integration RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_contracts.py tests/fewsnet_partitioned_rf/test_snapshot_staging.py -k 'normalization_audit or audit_for_different_panel or duplicate_panel_hard_gate' -q -p no:cacheprovider` -> `4 failed, 52 deselected in 6.89s`; failures were the expected source-snapshot-v1 mismatch and missing `normalization_audit_path` interface.
- Snapshot integration GREEN: the same selection -> `4 passed, 52 deselected in 5.15s`. The audit is validated against the captured panel before `inspect_panel`; the duplicate area-month hard gate remains active; snapshot identity and exact-generation reuse include the audit; normalized panel, audit, boundaries, and admin universe are written before `source_manifest.json`.
- Mandated focused Task 6 regression: normalization, contracts, snapshot staging, and preprocessing -> `77 passed in 6.23s`.
- First full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `400 passed, 1 skipped, 24 subtests passed in 22.00s`.
- Raw source SHA-256 before and after normalization: `41f02be985d86fbf64ae5d16cec262f9f11ec525fa1c013240f31299995e6178`; the raw file remained byte-identical.
- Approved normalized CSV: `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.csv`; SHA-256 `510375f58cd835e694b6e287cce9439bbe1b6246d752daabc8151df8ffdda61d`.
- Approved normalization audit: `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.audit.json`; SHA-256 `1c37232629dd11f657e77c361a033f9a30e910441e5d8c73ea703f3b22ef1166`.
- Real-source audit contract: `1,120,730` raw rows, `1,120,728` normalized rows, `88` columns, `2` duplicate groups, `4` duplicate rows, `2` removed rows, `0` conflict groups, latest feature month `2026-04`, and latest label month `2026-02`. Duplicate group `2996/2025-10` uses source data rows `587406` and `587407` and differs only in `Tair_zscore` and `Rainf_zscore`; `2996/2026-02` uses rows `587411` and `587412` and is exact across the excluded fields.
- Real local-store staging acceptance used the approved normalized pair, the real `FEWS_Admin_LZ_v3.shp`, destination identity `gs://local-only/fewsnet_partitioned_rf`, and `LocalArtifactStore` rooted at `/tmp/fewsnet-normalized-v1-local-store.VerJNk`. It produced `1,120,728` rows across `5,718` areas, snapshot ID `fewsnet-202604-8511bf5e`, and snapshot content SHA-256 `8511bf5e2e6ea63cf85ffdc37bfd7a3bd44715bb35b59b43eac344aab781c76a`.
- Self-review RED: mixed-source warning and concurrent-audit cleanup selection -> `2 failed, 8 deselected in 5.99s`; the real root causes were pandas chunked mixed-type inference emitting `DtypeWarning` and cleanup treating any audit at the target path as self-created.
- Self-review GREEN: a whole-file type inference read removes the warning; exclusive output/audit handles mark ownership before writing and cleanup unlinks only self-created artifacts. The concurrent-audit regression -> `1 passed, 9 deselected in 3.86s`; the mixed-source warning regression -> `1 passed, 9 deselected in 4.49s`.
- Real-source post-fix parity: a fresh `/tmp` normalization rerun produced normalized SHA-256 `510375f58cd835e694b6e287cce9439bbe1b6246d752daabc8151df8ffdda61d`; `cmp` reported `byte_identical=true` against the approved normalized-v1 CSV.
- Final fresh focused verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_panel_normalization.py tests/fewsnet_partitioned_rf/test_contracts.py tests/fewsnet_partitioned_rf/test_snapshot_staging.py tests/fewsnet_partitioned_rf/test_preprocessing.py -q -p no:cacheprovider` -> `79 passed in 6.83s`.
- Final fresh full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `402 passed, 1 skipped, 24 subtests passed in 21.25s`.
- Final static/environment gates: `git diff --check`, `py_compile`, JSON parsing, Draft 2020-12 metaschema validation for all eight FEWSNET schemas, both CLI help commands, and `.venv/bin/python -m pip check` all exited `0`; pip reported `No broken requirements found.`
- Staged-scope gate: the required named-repository call `detect_changes(scope="staged", repo="IPCCH_operational", worktree=<feature worktree>)` reported LOW risk, `13` changed files, `3` indexed documentation symbols, and `0` affected processes because the duplicate repository name resolved to the main index. The authoritative exact-worktree-index call reported HIGH risk, `94` changed symbols, `12` affected processes, and the same `13` changed files. Every affected process is within the explicitly reviewed Task 6 normalization CLI, snapshot staging/reuse, audit validation, and local tests; there is no unrelated pipeline spread.
- External artifacts are evidence only and are not added to Git. No `GCSArtifactStore`, GCP, GCS, Vertex AI, Model Registry, Batch Prediction, model registration, alias, or release-pointer mutation was performed.

### Task 6 Independent-Review Fix Evidence

- Review findings: (1) source checksum/size was collected after parsing and output publication, so a raw-file mutation could make the audit attest bytes different from those parsed; (2) the CLI audit checksum read occurred outside the JSON error boundary, so its `OSError` escaped.
- Exact-worktree GitNexus upstream gate before edits: `normalize_panel` MEDIUM risk (`7` direct, `11` total, `1` affected CLI process, `2` modules); normalization CLI `main` LOW risk (`3` direct, `4` total, `0` affected processes). No HIGH or CRITICAL result occurred.
- Raw-provenance RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_panel_normalization.py -q -p no:cacheprovider -k 'raw_source_drift'` -> `1 failed, 10 deselected in 5.88s`; exact failure was `Failed: DID NOT RAISE ValueError` after the test changed the raw file immediately after the parse used for output.
- Raw-provenance GREEN: the same command -> `1 passed, 10 deselected in 3.77s`; the normalizer now captures raw checksum/size before parsing, rechecks both immediately after parsing, fails before artifact creation on drift, and writes the captured identity into the audit. The complete normalization test file then reported `11 passed in 4.67s`.
- CLI audit-hash RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_panel_normalization.py -q -p no:cacheprovider -k 'audit_hash_error'` -> `1 failed, 11 deselected in 5.59s`; the injected `OSError: cannot hash panel.normalized-v1.audit.json` escaped from CLI `main`.
- CLI audit-hash GREEN: the same command -> `1 passed, 11 deselected in 3.83s`; the success summary, including audit hashing, is now inside the existing `(OSError, ValueError)` JSON error boundary. The complete normalization test file then reported `12 passed in 4.47s`.
- Fresh focused Task 6 verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_panel_normalization.py tests/fewsnet_partitioned_rf/test_contracts.py tests/fewsnet_partitioned_rf/test_snapshot_staging.py tests/fewsnet_partitioned_rf/test_preprocessing.py -q -p no:cacheprovider` -> `81 passed in 5.98s`.
- Fresh full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `404 passed, 1 skipped, 24 subtests passed in 19.05s`.
- Fresh real-source parity used `/tmp/fewsnet-normalization-review.W3PrKd`: raw SHA-256 before and after was identical at `41f02be985d86fbf64ae5d16cec262f9f11ec525fa1c013240f31299995e6178`; the regenerated normalized SHA-256 was `510375f58cd835e694b6e287cce9439bbe1b6246d752daabc8151df8ffdda61d`; `cmp` against the approved normalized-v1 CSV returned byte-identical. Audit validation confirmed `2` duplicate groups, `4` duplicate rows, `2` removed rows, `0` conflicts, keys `2996/2025-10` and `2996/2026-02`, latest feature month `2026-04`, and latest label month `2026-02`.
- Static and staged-scope gates: `py_compile` for the two production files and normalization tests, `git diff --check`, and `git diff --cached --check` exited `0`. Exact-worktree `detect_changes(scope="staged")` reported MEDIUM risk, `4` staged files, `11` changed symbols, and `4` affected processes; all four are the expected normalization CLI paths (`main` to `_sha256_file`, `_validate_paths`, `_source_columns`, and `_values_equal`). The staged paths are exactly `PROGRESS.md`, `core/normalization.py`, `cli/normalize_panel.py`, and `test_panel_normalization.py`; `.superpowers/` and external artifacts remain unstaged.
- No external approved artifact was overwritten, no cloud adapter was instantiated, and no Task 7 file or behavior was entered.
- Review-fix commit: `d403c1e6cb873eaa6e0b8c05b4543b1db0e6c97f` (`d403c1e fix: harden FEWSNET normalization provenance`).
- Independent Task 6 re-review: approved with no Critical, Important, or Minor findings; both original Important findings are closed. The reviewer independently ran the two focused regressions -> `2 passed, 10 deselected in 3.87s`.
- Controller fresh focused gate: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_panel_normalization.py tests/fewsnet_partitioned_rf/test_contracts.py tests/fewsnet_partitioned_rf/test_snapshot_staging.py tests/fewsnet_partitioned_rf/test_preprocessing.py -q -p no:cacheprovider` -> `81 passed in 7.49s`.
- Controller fresh full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `404 passed, 1 skipped, 24 subtests passed in 20.69s`.
- Controller real-artifact acceptance revalidated raw SHA-256 `41f02be985d86fbf64ae5d16cec262f9f11ec525fa1c013240f31299995e6178`, normalized SHA-256 `510375f58cd835e694b6e287cce9439bbe1b6246d752daabc8151df8ffdda61d`, audit SHA-256 `1c37232629dd11f657e77c361a033f9a30e910441e5d8c73ea703f3b22ef1166`, the exact `1,120,730 -> 1,120,728` row contract, `5,718` areas, the two approved duplicate keys, and unchanged raw bytes before/after validation.
- Controller repeated real-boundary staging with `LocalArtifactStore` rooted at `/tmp/fewsnet-task6-controller-store.Rk2RzP`; it reproduced snapshot ID `fewsnet-202604-8511bf5e` and content SHA-256 `8511bf5e2e6ea63cf85ffdc37bfd7a3bd44715bb35b59b43eac344aab781c76a`. No `GCSArtifactStore` or cloud client was instantiated.
- Task 6 final status: complete and independently reviewed. Task 7 is now unblocked.

## Task 7 Evidence

- Start state: reviewed Task 6 head plus ledger consistency commit `16233d8da342efe28ad4107c07d93e7ce267f5ed`; Task 7 adds only `core/horizons.py` and `test_horizons.py` and modifies this ledger, so no existing function, class, or method required pre-edit GitNexus impact analysis.
- Keyed-alignment RED: the focused Task 7 command exited `2` during collection with the expected `ModuleNotFoundError: No module named 'fewsnet_partitioned_rf_pipeline.core.horizons'` (`1 error in 3.99s`). Keyed-alignment GREEN: the same command -> `1 passed in 2.82s`.
- Duplicate-key RED: the duplicate-area-month selection failed because pandas reached merge validation and emitted `Merge keys are not unique...` instead of the required explicit pre-merge duplicate contract (`1 failed, 1 deselected in 4.42s`). Duplicate-key GREEN: the complete focused file -> `2 passed in 2.73s` after explicit normalized-key rejection before merge.
- Input-contract RED: missing/blank admin identities, invalid/missing feature months, missing required columns, and unsupported horizons produced `8 failed, 2 deselected` (`4.68s`). Input-contract GREEN: the focused file -> `10 passed in 4.09s` with canonical admin normalization, monthly `Period` normalization, clear required-column errors, and exact horizon validation for `0`, `6`, and `12`.
- Window/split RED: collection exited `2` with the expected missing `select_training_window` import (`1 error in 5.44s`). Window/split GREEN: after correcting one test fixture's pandas datetime assignment, the focused file -> `22 passed in 4.14s`; the inclusive target window is `2023-03..2026-02`, and validation is the final six distinct target periods `2025-09..2026-02`, never a row percentage.
- Inference RED: collection exited `2` with the expected missing `select_latest_inference_frame` import (`1 error in 5.69s`). The first universe-message check then failed `1` test with `25` passing because the error did not identify the missing authoritative area directly; GREEN -> `26 passed in 3.94s` with the complete-frame canonical admin set enforced at the exact latest feature month and no future-label merge.
- Pandas missing-month RED: an object-typed `pd.NA` feature month raised `TypeError: boolean value of NA is ambiguous` (`1 failed, 26 deselected in 5.23s`). GREEN: explicit missing-value detection now converts it to the required clear `ValueError`; the focused file -> `27 passed in 4.38s`.
- Final fresh Task 7 verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_horizons.py -q -p no:cacheprovider` -> `27 passed in 3.96s`.
- Relevant Task 5 preprocessing regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_preprocessing.py -q -p no:cacheprovider` -> `10 passed in 4.26s`.
- Fresh full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `431 passed, 1 skipped, 24 subtests passed in 21.98s`.
- Self-review probes: a wholly absent `2026-04` selection fails with the authoritative-area error; an empty 36-month selection remains a typed empty frame and the threshold split fails with the required minimum of seven distinct target periods; shuffled input reproduces byte-equivalent aligned rows and deterministic `{'missing_target_row': 1, 'null_target_value': 1}` counts.
- Preservation: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; normalized plan SHA-256 remains `977a88cd4b00e0bd9c560ffc2bb9aa752a0f76adaff59128d63b66a6745f176f`; feature schema SHA-256 remains `6e6f0bdc2df7bb40ec37f2d44926d2a24fbb746bc5272ed9b93a7ae4047d891b`; checked-in feature-contract JSON SHA-256 remains `3779c6bcde70560c0e1514c563ced6e7bd559c6d352689398c3cecb93d44a67b`.
- Preliminary staged-scope gate: exact-worktree GitNexus `detect_changes(scope="staged")` reported LOW risk, `3` changed files, `5` indexed documentation symbols, and `0` affected execution processes; the two new Python files are not yet represented as symbols in the feature index. `git diff --cached --check` exited `0`, and staged paths were exactly `PROGRESS.md`, `core/horizons.py`, and `test_horizons.py`; `.superpowers/` remained unstaged.
- No `GCSArtifactStore`, GCP/GCS client, Vertex AI job, Model Registry operation, Batch Prediction, alias mutation, release-pointer write, external data mutation, Task 8 file, or Task 8 behavior was entered.
- Task 7 final implementation status: complete; independent review is required before Task 8 starts.

### Task 7 Independent-Review Fix Evidence

- Review findings: blocking Important — `select_latest_inference_frame` accepted a completely empty but correctly shaped `feature_frame` because both authoritative and selected admin sets were empty; non-blocking Minor — `_prepare_feature_frame` does not literally sort before alignment, although keyed correctness is unaffected and aligned output is sorted after the merge.
- Pre-edit exact-worktree GitNexus gate supplied by the independent review: `select_latest_inference_frame` LOW risk (`4` direct callers, all Task 7 tests, `0` affected processes, `1` module); `align_horizon` MEDIUM risk (`6` direct callers, all Task 7 tests, `0` affected processes) and was not edited by this fix.
- Empty-universe RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_horizons.py -q -p no:cacheprovider -k empty_authoritative_universe` -> `1 failed, 27 deselected in 5.45s`; exact failure was `Failed: DID NOT RAISE ValueError`, confirming the zero-row return.
- Empty-universe GREEN: the same command -> `1 passed, 27 deselected in 3.65s` after the smallest change in `select_latest_inference_frame`: reject an empty authoritative admin universe with a clear `ValueError`. Public signatures and all alignment behavior remain unchanged.
- Fresh complete Task 7 file: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_horizons.py -q -p no:cacheprovider` -> `28 passed in 3.81s`.
- Fresh relevant preprocessing regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_preprocessing.py -q -p no:cacheprovider` -> `10 passed in 4.35s`.
- Fresh full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `432 passed, 1 skipped, 24 subtests passed in 20.06s`.
- Deferred Minor for final whole-branch triage: `_prepare_feature_frame` validates normalized keys without first sorting the working frame. No keyed result is wrong, `align_horizon` sorts its returned frame deterministically, and this review-fix commit intentionally does not modify the MEDIUM-impact `align_horizon` path.
- Preliminary review-fix staged gate: exact-worktree GitNexus `detect_changes(scope="staged")` reported MEDIUM risk, `3` changed files, `10` changed indexed symbols, and `1` affected process (`Select_latest_inference_frame -> _normalize_month_values`, with the reviewed function as changed step 1). `git diff --cached --check` exited `0`; staged paths were exactly `PROGRESS.md`, `core/horizons.py`, and `test_horizons.py`. Unrelated `AGENTS.md`, `CLAUDE.md`, `.claude/`, and `.superpowers/` changes remained unstaged.
- No Task 8 behavior, cloud adapter, GCP/GCS/Vertex operation, external artifact mutation, public-signature change, positional shift, or design/plan change was introduced.
- Implementation commit: `5f1ea50d02e88c0b8a9bce63690d6bd847145302` (`5f1ea50 feat: align FEWSNET forecast horizons`).
- Independent-review fix commit: `8ff2847546dc666c989b9f2371f557f0b9822098` (`8ff2847 fix: reject empty FEWSNET inference universe`).
- Independent Task 7 re-review: approved with no Critical or Important findings. The empty authoritative-universe defect is closed at its root with direct regression coverage. The only remaining Minor is the literal pre-alignment sorting invariant; keyed correctness and deterministic returned order are preserved, and the Minor is retained for final whole-branch triage.
- Controller fresh focused verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_horizons.py -q -p no:cacheprovider` -> `28 passed in 4.04s`.
- Controller fresh preprocessing regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_preprocessing.py -q -p no:cacheprovider` -> `10 passed in 4.58s`.
- Controller fresh full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `432 passed, 1 skipped, 24 subtests passed in 21.41s`.
- Controller consistency gate: `git diff --check 16233d8..8ff2847` exited `0`; approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; approved plan SHA-256 remains `977a88cd4b00e0bd9c560ffc2bb9aa752a0f76adaff59128d63b66a6745f176f`.
- Task 7 final status: complete and independently reviewed. Task 8 is unblocked; no cloud write is authorized at this stage.

## Task 8 Evidence

- Start state: reviewed Task 7 head plus ledger consistency commit `43677cfb7b8ce2a25cbebfdf67bcfbeff5862c64`; Task 8 creates only `core/partitions.py` and `test_partitions.py` and modifies this ledger, so no existing function, class, or method required pre-edit GitNexus impact analysis.
- Baseline full regression before Task 8 edits: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `432 passed, 1 skipped, 24 subtests passed in 20.19s`.
- RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_partitions.py -q -p no:cacheprovider` exited `2` during collection with the expected `ModuleNotFoundError: No module named 'fewsnet_partitioned_rf_pipeline.core.partitions'` (`1 error in 3.76s`).
- GREEN: the same focused command -> `13 passed in 4.20s`.
- Public method signatures: `PartitionMap.load(path: str | Path, expected_sha256: str) -> PartitionMap`; `PartitionMap.from_frame(frame: pandas.DataFrame) -> PartitionMap`; `route(admin_codes: Iterable[object]) -> pandas.Series`; `coverage(admin_codes: Iterable[object]) -> float`; `assert_release_coverage(admin_codes: Iterable[object], *, baseline_pct: float = 5365 / 5718 * 100, max_drop_percentage_points: float = 2.0) -> float`.
- Map validation: SHA-256 is computed and compared before CSV parsing; the source `FEWSNET_admin_code` is normalized through the shared `normalize_admin_code`; missing/blank map identities, duplicates after normalization, and non-integer cluster values fail closed; the stored mapping is read-only.
- Real fixed-asset acceptance: SHA-256 `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`, `5,365` unique normalized admin-code mappings, and sorted cluster IDs exactly `0..16`.
- Routing contract: input order and duplicate rows are preserved; identities are normalized at lookup time; mapped values are Python integers and unmapped, missing, or blank identities return `None`, including the required exact `.tolist()` behavior.
- Coverage contract: the return value is `100 * mapped_unique_normalized_admin_codes / unique_normalized_admin_codes`; repeated valid identities are counted once after normalization, while an empty iterable or any identity that normalizes to blank raises `ValueError` before deduplication.
- Release gate: default baseline is exactly `5365 / 5718 * 100`; default maximum drop is `2.0` percentage points; the implementation raises only when `baseline_pct - current_pct > max_drop_percentage_points`. Direct tests prove an exact `2.0`-point drop passes and `2.0001` points fails.
- Relevant runtime/data regression: partitions, runtime foundation, panel normalization, snapshot staging, preprocessing, and horizons -> `88 passed in 6.76s`.
- Fresh full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `445 passed, 1 skipped, 24 subtests passed in 19.96s`.
- Preservation: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; approved plan SHA-256 remains `977a88cd4b00e0bd9c560ffc2bb9aa752a0f76adaff59128d63b66a6745f176f`; fixed partition SHA-256 remains `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Preliminary staged gate: `git diff --cached --check` exited `0`; staged paths were exactly `PROGRESS.md`, `core/partitions.py`, and `test_partitions.py`. Exact-worktree GitNexus `detect_changes(scope="staged")` reported LOW risk, `3` changed files, `3` indexed documentation sections, and `0` affected execution processes; the two new Python files are not yet represented as symbols in the current index.
- Scope boundary: no Task 9 file or behavior, GCP/GCS/Vertex operation, Model Registry call, Batch Prediction, alias mutation, release-pointer write, or external artifact mutation was introduced.
- Task 8 final implementation status: complete; independent review is required before Task 9 starts.

### Task 8 Independent-Review Fix Evidence

- Blocking Important: `coverage()` normalized identities inside `dict.fromkeys`, so multiple `None`, empty-string, and whitespace authoritative identities collapsed into one blank denominator entry. The malformed universe returned `50.0`, and `assert_release_coverage(..., baseline_pct=52.0, max_drop_percentage_points=2.0)` also returned `50.0` instead of failing closed.
- Controller-resolved exact-worktree GitNexus pre-edit gate after index repair: `PartitionMap.coverage` LOW risk (`6` total impacted, `3` direct, `1` affected `assert_release_coverage` process, `1` module); `PartitionMap.assert_release_coverage` LOW risk (`3` direct test callers, `0` affected processes, `1` module). No HIGH or CRITICAL result occurred.
- Review RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_partitions.py -q -p no:cacheprovider -k invalid_authoritative_identities` -> `2 failed, 13 deselected in 5.43s`; both direct real-behavior regressions failed with `Failed: DID NOT RAISE ValueError`.
- Smallest fix: materialize the normalized authoritative sequence once, preserve the existing empty-iterable error, reject `""` before `dict.fromkeys`, and deduplicate only valid normalized identities. Public signatures and valid unique-area percentage semantics are unchanged.
- Review GREEN: the same focused selection -> `2 passed, 13 deselected in 3.62s`.
- Complete Task 8 verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_partitions.py -q -p no:cacheprovider` -> `15 passed in 3.77s`.
- Related runtime/data regression: partitions, runtime foundation, panel normalization, snapshot staging, preprocessing, and horizons -> `90 passed in 6.71s`.
- Fresh full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `447 passed, 1 skipped, 24 subtests passed in 20.19s`.
- Preserved valid behavior: repeated nonblank identities still deduplicate after normalization; routing still returns `None` for unmapped/missing requested rows; the default baseline remains `5365 / 5718 * 100`; an exact `2.0`-point drop still passes and only a strictly larger drop fails.
- Preservation: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; approved plan SHA-256 remains `977a88cd4b00e0bd9c560ffc2bb9aa752a0f76adaff59128d63b66a6745f176f`; fixed partition SHA-256 remains `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Preliminary fix staged gate: `git diff --cached --check` exited `0`; staged paths were exactly `PROGRESS.md`, `core/partitions.py`, and `test_partitions.py`. Exact-worktree GitNexus `detect_changes(scope="staged")` reported LOW risk, `3` changed files, `3` indexed documentation sections, and `0` affected execution processes; the modified Python symbols were not surfaced in this staged result despite the controller's successful symbol-specific pre-edit impact checks.
- Scope remains limited to `coverage()` validation, two direct regressions, this ledger, and the uncommitted Task 8 report. No Task 9 or cloud behavior was entered.
- Implementation commit: `656429f4d2c9d5c994be522ebe19b9515971b732` (`656429f feat: add fixed FEWSNET partition routing`).
- Independent-review fix commit: `20a6e0e7cda67b0b9ca04177fa43d7d86ad2d410` (`20a6e0e fix: reject invalid FEWSNET coverage universe`).
- Independent Task 8 re-review: approved with no Critical, Important, or Minor findings. The malformed-authoritative-universe defect is closed before denominator deduplication, with direct coverage and release-guard regressions; valid routing, percentage, checksum-before-parse, and strict release-boundary behavior remain unchanged.
- Controller fresh Task 8 verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_partitions.py -q -p no:cacheprovider` -> `15 passed in 3.90s`.
- Controller fresh related regression: the six-file runtime/data selection -> `90 passed in 6.81s`.
- Controller fresh full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `447 passed, 1 skipped, 24 subtests passed in 20.44s`.
- Controller fixed-asset acceptance: configured and actual SHA-256 both equal `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`; the asset has exactly `5,365` data rows and cluster IDs exactly `0..16` (`17` clusters).
- Controller consistency gate: `git diff --check 43677cf..20a6e0e` exited `0`; approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; approved plan SHA-256 remains `977a88cd4b00e0bd9c560ffc2bb9aa752a0f76adaff59128d63b66a6745f176f`.
- Task 8 final status: complete and independently reviewed. Task 9 is unblocked; no cloud write is authorized at this stage.

## Task 9 Evidence

- Base: `edab524` (`docs: record FEWSNET task 8 review`).
- RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_imputer_thresholds.py -q -p no:cacheprovider` -> `13 failed in 5.80s`; all failures were the expected missing Task 9 APIs (`MaxPlusImputer` absent and `core.thresholds` absent) before any production implementation.
- Sklearn-style keyword RED: the focused `-k sklearn_style` selection -> `1 failed, 13 deselected in 5.62s` with the expected `TypeError` for the absent `X=` keyword contract; only the new Task 9 method parameter names were then corrected.
- Focused GREEN: the complete Task 9 file -> `14 passed in 7.06s`.
- Imputer contract: `fit` replaces both infinities with missing values and alone records `n_features_in_`, `feature_mins_`, `feature_maxs_`, and `impute_values_`; all evidence arrays are deterministic `float64`. All-missing columns use `0.0`, zero maxima use `100.0`, other maxima use `max * 100.0` including negative maxima, and `transform` never derives imputation values from transform rows.
- Transform contract: inputs and outputs are two-dimensional `float64` NumPy arrays; transform-time infinities are imputed from the stored fit-slice values; a different feature count fails closed; `fit(X, y=None)`, `transform(X)`, and `fit_transform(X, y=None)` accept the minimal sklearn-style signatures.
- Threshold contract: finite probabilities alone define support and positive-case counts; the shared exact `THRESHOLD_GRID` is scored with `probability >= threshold`; sklearn precision, recall, and F1 use `zero_division=0`; `(f1, threshold)` maximization selects the higher threshold on ties.
- Fallback coverage: exact reasons `no_validation_observations`, `no_validation_positive_cases`, and `no_finite_validation_f1` all return threshold `0.50` with `None` metrics and finite-slice counts. The nonfinite-F1 branch requires a narrow `f1_score` monkeypatch because valid binary labels with sklearn `zero_division=0` cannot naturally produce a nonfinite F1; every other metric, grid, tie, filtering, and fallback test uses real sklearn behavior.
- Related regression: preprocessing, horizons, partitions, and Task 9 -> `67 passed in 7.75s`.
- Fresh full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `461 passed, 1 skipped, 24 subtests passed in 23.36s`.
- Preservation: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; approved plan SHA-256 remains `977a88cd4b00e0bd9c560ffc2bb9aa752a0f76adaff59128d63b66a6745f176f`; fixed partition SHA-256 remains `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Staged-scope gate: `git diff --cached --check` exited `0`; staged paths were exactly `PROGRESS.md`, `core/preprocessing.py`, `core/thresholds.py`, and `test_imputer_thresholds.py`; no tracked Task 9 unstaged remainder existed. Exact-worktree GitNexus `detect_changes(scope="staged")` reported LOW risk, `4` changed files, `3` indexed documentation sections, and `0` affected execution processes. The index surfaced only existing `PROGRESS.md` sections, not the new Python symbols, so this is staged file/process evidence rather than call-graph coverage for the new APIs; no HIGH or CRITICAL result occurred.
- Scope boundary: no existing function, class, or method was changed; no Task 10 training/inference code, GCP/GCS/Vertex operation, Model Registry call, Batch Prediction, alias mutation, release-pointer write, or external artifact mutation was introduced.
- Independent Task 9 review: approved with no Critical or Important findings. The reviewer confirmed fit-slice-only imputation, deterministic edge rules and stored-state transforms, finite-probability threshold support, exact fallback reasons, shared-grid scoring, and higher-threshold tie-breaking.
- Deferred Task 9 Minor: transform-before-fit raises a generic `RuntimeError` rather than sklearn's conventional `NotFittedError`, and that branch lacks a focused regression test. This does not violate the approved minimal interface and is retained for final whole-branch triage.
- Controller fresh focused verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_imputer_thresholds.py -q -p no:cacheprovider` -> `14 passed in 7.66s`.
- Controller fresh related regression: preprocessing, horizons, partitions, and Task 9 -> `67 passed in 7.76s`.
- Controller fresh full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `461 passed, 1 skipped, 24 subtests passed in 24.69s`.
- Task 9 final status: complete and independently reviewed. Task 10 is unblocked; no cloud write is authorized at this stage.

## Task 10 Evidence

- Base: `06941e4ba2101c4be26782cfb13a80198699c94b` (`docs: record FEWSNET task 9 review`).
- Pre-change related baseline: preprocessing, horizons, partitions, and Task 9 -> `67 passed in 8.07s`.
- Initial RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_training_inference.py -q -p no:cacheprovider` -> `9 failed in 6.65s`; every failure was the expected `ModuleNotFoundError` for the absent `core.training` API before production implementation.
- Pooled/partition contract: every fit uses `RandomForestClassifier(**RF_PARAMS)`; the pooled model receives every supplied row; nullable/unmapped cluster IDs are excluded only from the partition loop; eligible partitions use dynamic SMOTE neighbors; small and single-class partitions use their exact pooled fallback states; failed SMOTE records the exception class/message and trains the partition RF on original rows.
- Threshold/refit contract: the aligned input must contain one contiguous inclusive 36-target-month window; a temporary imputer and temporary models see only the first 30 target months; partition-routed probabilities select the shared global threshold on the final six target months; a new imputer and new pooled/partition models are then fitted on all 36 months.
- Formal inference contract: `PartitionedRFPredictor` is pickle-serializable, preserves input row order, applies the frozen feature order and stored imputer, derives or validates the target month from its fixed horizon, routes every fallback source explicitly, handles single-column `predict_proba` by inspecting `classes_`, and emits exactly the twelve formal prediction columns with empty pre-registration identity fields.
- Exact pinned-stack compatibility finding: `imbalanced-learn==0.14.0` and `scikit-learn==1.8.0` pass package metadata and `pip check`, but a normal `imblearn` import fails because sklearn 1.8 removed private `validation._is_pandas_df` and the `AdaBoostClassifier(algorithm=...)` argument still used while importing imbalanced-learn. The new Task 10 module applies a temporary import-only bridge for those two exact API removals, imports the real `imblearn.over_sampling.SMOTE`, and restores both sklearn globals immediately.
- Import-restoration mutation RED: after temporarily suppressing both restoration statements, `-k smote_import_bridge` -> `1 failed, 9 deselected in 12.15s`; the fresh-interpreter regression detected the leaked sklearn global. Restoring the implementation produced `1 passed, 9 deselected in 9.91s`.
- First focused GREEN after the compatibility bridge: the complete Task 10 file -> `10 passed in 16.95s`.
- Self-review boundary RED: formal inference without a supplied `target_month` and with a contradictory supplied target produced `2 failed, 9 deselected in 12.09s`; the predictor now derives the fixed-horizon target when absent and rejects a mismatch. Focused boundary GREEN -> `2 passed, 9 deselected in 8.45s`.
- Final focused GREEN: the complete Task 10 file -> `11 passed in 15.79s`.
- Final related regression: Task 2 contracts plus Tasks 5, 7, 8, 9, and 10 -> `114 passed in 17.14s`.
- Final fresh full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `472 passed, 1 skipped, 24 subtests passed in 32.56s`.
- Static/API audit: all three Task 10 Python files parse with `ast`; the public signatures match the frozen brief; `.venv/bin/python -m pip check` reports `No broken requirements found.`
- GitNexus: the exact-worktree index was refreshed at base `06941e4`; exact-worktree query/context confirmed Task 2/5/7/8/9 consumers. No existing function, class, or method was modified, so no pre-edit symbol impact gate was triggered. Exact-worktree staged `detect_changes` reported LOW risk, four changed files, three indexed `PROGRESS.md` documentation sections, and zero affected execution processes; the new Python symbols were not surfaced in the staged symbol list.
- Preservation: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; approved plan SHA-256 remains `977a88cd4b00e0bd9c560ffc2bb9aa752a0f76adaff59128d63b66a6745f176f`; fixed partition SHA-256 remains `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Scope boundary: only the two additive core modules, the Task 10 focused test, and this ledger are tracked Task 10 changes. The pre-existing `AGENTS.md`, `CLAUDE.md`, `.claude/`, and `.superpowers/` changes remain unstaged. No Task 11 parity fixture/tool, GCP/GCS/Vertex operation, Model Registry call, Batch Prediction, alias mutation, release-pointer write, IPCCH pipeline edit, or external artifact mutation was introduced.
- Implementation commit: `dc627331942536ca5dd084e83a24cd6f41e40f5d` (`dc62733 feat: train partitioned FEWSNET RF models`).
- Task 10 implementation status after the first review: complete but blocked by two Important findings before Task 11.

### Task 10 Important Review Fix

- Independent review result: `Needs fixes`; no Critical or Minor findings and exactly two Important findings: the supplied `PartitionMap` was not bound to the checksum-approved asset, and the sklearn/imblearn compatibility bridge was not protected from its first mutation or from post-thread startup use.
- Pre-edit exact-worktree GitNexus impact supplied by the controller: `_assert_partition_asset_identity` -> LOW, one direct caller (`train_horizon_model`), one affected training process; `_load_smote_type` -> LOW, module-import caller only, zero affected processes; `train_horizon_model` -> LOW, zero upstream callers/processes. No HIGH or CRITICAL result occurred.
- Exact RED command: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_training_inference.py -q -p no:cacheprovider -k 'restores_after_first_mutation_failure or rejects_after_worker_threads_start or accepts_map_loaded_from_approved_asset or rejects_same_count_high_coverage_unrelated_map'` -> `3 failed, 1 passed, 11 deselected in 12.38s`.
- Expected RED reasons: injected signature inspection failure leaked `_is_pandas_df`; a live worker thread did not block the process-global bridge; an unrelated map with the same mapped count, the same cluster set, and 100% training-frame coverage was accepted; the map loaded from the explicit checksum-approved synthetic asset was accepted.
- Fixed partition binding: production reloads `PARTITION_ASSET_PATH` through `PartitionMap.load(..., PARTITION_ASSET_SHA256)`, then requires the supplied immutable map to match the approved mapped count, sorted cluster set, deterministic normalized mapping SHA-256, and exact normalized mapping dictionary. The existing release-coverage gate remains unchanged and runs before this identity gate; training and predictor serialization begin only after both pass.
- Bridge safety: `_load_smote_type` now requires the main thread with no live worker threads before any mutation, protects the first `_is_pandas_df` assignment inside `try/finally`, and restores the exact prior `_is_pandas_df` and `AdaBoostClassifier` objects on every success/failure path. The real `imblearn.over_sampling.SMOTE` remains in use and dependency requirements are unchanged.
- Targeted GREEN for the four review regressions: `4 passed, 11 deselected in 7.96s`.
- Fresh focused Task 10 GREEN: `15 passed in 15.86s`.
- Fresh related Task 2/5/7/8/9/10 GREEN: `118 passed in 19.63s`.
- Fresh full repository GREEN: `476 passed, 1 skipped, 24 subtests passed in 32.74s`.
- Static/dependency/preservation audit: both changed Python files parse with `ast`; `.venv/bin/python -m pip check` reports `No broken requirements found.`; approved design, plan, and fixed partition SHA-256 values remain unchanged.
- Scope boundary: only `PROGRESS.md`, `core/training.py`, and `test_training_inference.py` are intended for the separate fix commit. No `PartitionMap`, inference, frozen design/plan, Task 11, cloud, alias, release-pointer, IPCCH pipeline, or external artifact change was made.
- Fix commit: `891b0f928f07f08f6930b8d148564c2fda1c55bf` (`891b0f9 fix: bind FEWSNET partition identity`).
- Independent Task 10 re-review: approved with no Critical, Important, or Minor findings. The supplied map is now bound to the checksum-loaded approved asset by mapped count, cluster set, deterministic normalized digest, and exact content before fit/serialization; the sklearn bridge rejects non-main/post-worker startup before mutation and restores every process-global change from the first assignment onward.
- Reviewer focused re-review: the four original-finding regressions -> `4 passed, 11 deselected`.
- Controller fresh focused verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_training_inference.py -q -p no:cacheprovider` -> `15 passed in 18.20s`.
- Controller fresh related regression: Task 2 contracts plus Tasks 5, 7, 8, 9, and 10 -> `118 passed in 18.60s`.
- Controller fresh full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `476 passed, 1 skipped, 24 subtests passed in 33.83s`.
- Task 10 final status: complete and independently re-reviewed. Task 11 is unblocked; no cloud write is authorized at this stage.

## Task 11 Evidence

- Base: `b802ace01ef67dca1350f50c0c79af35b7983b01` (`docs: record FEWSNET task 10 review`). The exact worktree and branch were `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.worktrees/fewsnet-partitioned-rf-suite` and `features/fewsnet-partitioned-rf-suite`.
- Independent review of `b802ace..cc97b4b` returned two Important findings: NumPy's default relative tolerance made the parity assertion weaker than the design's strict numeric contract, and importing the external reference module could write bytecode into that checkout. No Critical or Minor findings were reported.
- Human authority resolution: use `np.allclose(..., atol=1e-12, rtol=0.0)` and require the generator itself to suppress bytecode writes before external import and restore the prior interpreter state on both success and failure. The frozen design and plan remain byte-identical; this explicit resolution governs the stale example call in the Task 11 brief/plan.
- Controller RED reproduction: `np.allclose([1.000005], [1.0], atol=1e-12)` returned `True`, while the same probe with `rtol=0.0` returned `False`. Running the committed generator without caller bytecode controls against fresh temporary clone `/tmp/fewsnet-task11-pyc-red-KTu61P/reference` created exactly `12` `.pyc` files; the approved source checkout remained Git-clean.
- Exact-worktree GitNexus was force-rebuilt after an incremental FTS inconsistency (`3,206` nodes, `6,485` edges, `195` flows). Upstream impact for `_reference_functions` is LOW and confined to `_build_payload -> main` in the developer generator; upstream impact for `test_partition_training_matches_frozen_reference_fixture` is LOW with no callers.
- Scope: Task 11 adds only `tools/build_fewsnet_stage3_parity_fixture.py`, `tests/fixtures/fewsnet_partitioned_rf/stage3_reference_parity.json`, and `tests/fewsnet_partitioned_rf/test_reference_parity.py`, plus this ledger. No existing function, class, or method was modified, so no pre-edit GitNexus symbol-impact gate was required.
- TDD RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_reference_parity.py -q -p no:cacheprovider` -> `1 failed in 11.57s`; the expected failure was `FileNotFoundError` for the absent checked-in `stage3_reference_parity.json`, before the generator or fixture existed.
- Reference identity: the read-only provenance checkout resolved to exact commit `1ecf180669568bbf9eb2129683108162902a415a` on clean `main`. GitNexus context confirmed the required reference symbols in `scripts/compare_partitioned_vs_pooled_rf_k40_nc4.py`: `train_pooled_model`, `train_partitioned_model`, and `predict_partitioned_probability`, with the probability router calling `predict_class1_probability`.
- Commit guard: running the generator against this Task worktree intentionally observed `b802ace01ef67dca1350f50c0c79af35b7983b01`, exited `1` with the exact expected/observed mismatch, and left the requested output absent. The approved commit check occurs before output-path creation or writing.
- Developer dependency preparation: the first reference import failed on missing `polars`. `polars==1.41.2` was installed only into the existing untracked Task worktree `.venv`, matching the reference checkout's `polars>=0.19.0` developer requirement; no tracked or production requirement changed. A fresh requirements-only FEWSNET runtime venv can run the checked-in parity test without Polars or the external checkout, but regenerating the developer fixture requires installing the reference checkout's import dependencies first; the generator emits a direct missing-dependency error.
- Generator command: `.venv/bin/python tools/build_fewsnet_stage3_parity_fixture.py --reference-root "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/2.source_code/Step5_Geo_RF_trial/Food_Crisis_Cluster" --output tests/fixtures/fewsnet_partitioned_rf/stage3_reference_parity.json` -> exit `0`, printed exact reference commit `1ecf180669568bbf9eb2129683108162902a415a`, and wrote only the local checked-in fixture.
- Frozen fixture: SHA-256 `2d5e17c3addc573e11fabb6ca26076abe4c39f52ab6ae6ec1bcf12900e9fdd27`; `15` deterministic training rows, `6` test rows, `2` features, `min_samples=5`, threshold `0.50`, RF parameters `{n_estimators: 100, max_depth: null, random_state: 5, n_jobs: 1}`, probabilities `[0.04, 1.0, 0.85, 1.0, 1.0, 0.7]`, classes `[0, 1, 1, 1, 1, 1]`, model-presence flags `{0: true, 1: false, 2: false}`, and statuses `{0: partition_model, 1: pooled_small_partition, 2: pooled_single_class}`. Test groups also exercise pooled fallback for unseen group `99` and reference-unmapped sentinel `-1`.
- Parity construction: the eligible partition is class-balanced, so reference SMOTE availability does not change its training matrix. In the pinned local Task environment the reference module reports SMOTE unavailable after its guarded import, while the Task 10 implementation uses its reviewed compatibility bridge; direct exploratory comparison and the checked-in runtime test both produced zero probability delta.
- Fixture determinism: a second `PYTHONDONTWRITEBYTECODE=1` generation into `/tmp` was byte-identical by `cmp` and reproduced SHA-256 `2d5e17c3addc573e11fabb6ca26076abe4c39f52ab6ae6ec1bcf12900e9fdd27`.
- Focused GREEN with Task 10: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_reference_parity.py tests/fewsnet_partitioned_rf/test_training_inference.py -q -p no:cacheprovider` -> `16 passed in 15.82s`.
- Related FEWSNET regression: Task 2 contracts plus Tasks 5, 7, 8, 9, 10, and 11 -> `119 passed in 17.92s`.
- Fresh full repository regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `477 passed, 1 skipped, 24 subtests passed in 32.92s`.
- Static/dependency audit: both new Python files parse with `ast`; the fixture parses as JSON and contains the exact source commit, RF parameters, model-presence flags, and status vocabulary; `.venv/bin/python -m pip check` -> `No broken requirements found.`
- Preservation: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; approved plan SHA-256 remains `977a88cd4b00e0bd9c560ffc2bb9aa752a0f76adaff59128d63b66a6745f176f`.
- External-checkout hygiene concern: a dependency-diagnosis probe executed the ignored external `.venv-geodt-diagnostic/bin/python` and refreshed/created ignored `.pyc` caches inside that external virtual environment. Per controller direction, no cleanup or further mutation was attempted because deletion would be less safe. Normal external Git status remains clean, exact HEAD remains approved, and no recent non-venv/source `.pyc` was found; every later reference invocation used `PYTHONDONTWRITEBYTECODE=1`.
- GitNexus: the exact worktree index was refreshed successfully at the Task 11 checkout (`3,205` nodes, `6,484` edges, `195` flows). Exact-worktree staged `detect_changes(scope="staged")` reported MEDIUM risk, exactly `4` changed files, `22` changed symbols, and `3` affected processes; all three are the isolated developer-generator flows `Main -> _reference_functions`, `Main -> _synthetic_matrix`, and `Main -> _expected_partition_status`. Context confirmed generator `main` is entered only by its own file and calls only its parser, commit verifier, and payload builder; no existing FEWSNET runtime or IPCCH process is affected.
- Scope boundary: the runtime parity test reads only the checked-in JSON fixture and local Task 10 APIs. No runtime absolute import of `Food_Crisis_Cluster`, existing IPCCH-pipeline edit, Task 12 file or behavior, GCP/GCS/Vertex operation, Model Registry call, Batch Prediction, alias mutation, or release-pointer write was introduced.

### Task 11 Independent-Review Fix Evidence

- Pre-edit exact-worktree GitNexus was refreshed to `3,206` nodes, `6,485` edges, `134` clusters, and `195` flows. `_reference_functions` is LOW risk with one direct caller (`_build_payload`) and propagation only to generator `main`; `test_partition_training_matches_frozen_reference_fixture` is LOW risk with no callers or affected runtime flows.
- Strict-tolerance RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_reference_parity.py -q -p no:cacheprovider -k default_relative_tolerance_gap` -> `1 failed, 5 deselected in 18.47s`; exact failure was `Failed: DID NOT RAISE AssertionError`, proving `1.000005` versus `1.0` still passed the actual parity assertion contract.
- Generator-hygiene RED: the same file with `-k 'reference_import_suppresses or reference_import_restores'` -> `2 failed, 2 passed, 2 deselected in 11.90s`. With prior state `False`, a fresh isolated reference package created two `.pyc` files, and the exception probe raised `AssertionError: bytecode writes were not disabled before import` instead of its intended `RuntimeError`.
- Minimal fixes: the shared parity assertion now uses `np.allclose(..., atol=1e-12, rtol=0.0)`. `_reference_functions` captures `sys.dont_write_bytecode`, sets it to `True` before the external import, and restores the exact prior value in `finally`; public generator inputs, output schema, reference functions, and fixture bytes are unchanged.
- Strict-tolerance GREEN: the focused tolerance selection -> `1 passed, 5 deselected in 5.85s`. Generator-hygiene GREEN -> `4 passed, 2 deselected in 6.11s`, covering no bytecode creation plus exact `False`/`True` restoration on both success and exception paths.
- Focused Task 11 plus Task 10 verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_reference_parity.py tests/fewsnet_partitioned_rf/test_training_inference.py -q -p no:cacheprovider` -> `21 passed in 16.40s`.
- Related FEWSNET verification across contracts, preprocessing, horizons, partitions, imputer/thresholds, training/inference, and reference parity -> `124 passed in 18.47s`.
- Fresh full repository verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `482 passed, 1 skipped, 24 subtests passed in 34.28s`.
- Real regeneration explicitly unset caller `PYTHONDONTWRITEBYTECODE`; the fresh interpreter reported `caller_dont_write_bytecode=False`. The generator still left the approved checkout's non-venv `.pyc` snapshot byte-identical before/after, preserved clean `main` at `1ecf180669568bbf9eb2129683108162902a415a`, and reproduced the checked-in fixture byte-for-byte at SHA-256 `2d5e17c3addc573e11fabb6ca26076abe4c39f52ab6ae6ec1bcf12900e9fdd27`.
- Static/dependency/preservation gates: both changed Python files parse with `ast`; the fixture parses as JSON; `.venv/bin/python -m pip check` reports `No broken requirements found.`; approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; approved plan SHA-256 remains `977a88cd4b00e0bd9c560ffc2bb9aa752a0f76adaff59128d63b66a6745f176f`.
- Final staged gate: `git diff --cached --check` exited `0`; staged paths are exactly `PROGRESS.md`, the parity test, and the generator. Exact-worktree GitNexus `detect_changes(scope="staged")` reported MEDIUM risk, `3` changed files, `10` changed indexed symbols, and one affected process (`Main -> _reference_functions`, changed at its terminal import step); no FEWSNET runtime or IPCCH process is affected.
- Existing ignored bytecode inside the external diagnostic virtual environment remains untouched. No fixture-content change, production dependency change, Task 12 behavior, cloud operation, external source edit, or deferred Task 7/9 Minor was introduced.

### Task 11 Controller Acceptance

- Independent re-review of the complete two-commit range `b802ace..932cfd5` approved Task 11 with no Critical, Important, or Minor findings. It confirmed strict `atol=1e-12, rtol=0.0`, internal bytecode suppression/restoration, fail-before-write commit verification, deterministic fixture output, runtime isolation from the external checkout, and exact Task 11 scope.
- Fresh controller focused verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_reference_parity.py tests/fewsnet_partitioned_rf/test_training_inference.py -q -p no:cacheprovider` -> `21 passed in 15.91s`.
- Fresh controller related verification across contracts, preprocessing, horizons, partitions, imputer/thresholds, training/inference, and reference parity -> `124 passed in 17.95s`.
- Fresh controller full repository verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `482 passed, 1 skipped, 24 subtests passed in 33.71s`.
- At Task 11 acceptance, authority was design SHA-256 `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`, then-current plan SHA-256 `977a88cd4b00e0bd9c560ffc2bb9aa752a0f76adaff59128d63b66a6745f176f`, and fixture SHA-256 `2d5e17c3addc573e11fabb6ca26076abe4c39f52ab6ae6ec1bcf12900e9fdd27`; the user-approved Task 12 amendment below subsequently updates only the plan authority.

## Task 12 Authority Amendment

- Conflict found before implementation: design section 11 requires `model_manifest.json` to pin the shared container image URI/digest and training/validation target-month ranges, while the closed `model-package.schema.json` omitted `container_image_uri`, `training_target_month_range`, and `validation_target_month_range`.
- User resolution: option A, design contract governs. Task 12 now explicitly modifies `fewsnet_partitioned_rf_pipeline/schemas/model-package.schema.json`; the design remains unchanged at SHA-256 `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`.
- Plan amendment: require the three manifest fields, require the image URI suffix to equal `@{container_image_digest}`, copy the two ranges from the horizon `training_report.json`, reject range mismatches during loading, and include schema plus existing contract-fixture modification in the Task 12 commit. Updated plan SHA-256: `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`.
- Existing-test scope consequence: expanding the closed schema makes `tests/fewsnet_partitioned_rf/test_contracts.py::_model_package()` invalid until its fixture includes the three required fields. Exact-worktree upstream impact is LOW, limited to the two model-package schema tests in that file, with no affected execution process; the plan now authorizes this narrow fixture update.
- Shape resolution retained: package `training_report.json` remains the Task 10 horizon-level `fewsnet-horizon-training-report-v1` report and `threshold_report.json` remains the per-horizon threshold dictionary. The existing suite-level `training-report.schema.json` is reserved for Task 13's separate aggregate `training_threshold_report.json`; Task 12 does not change it.
- The amended plan, regenerated Task 12 brief, and both progress ledgers are synchronized before implementation resumes. No cloud write is authorized.

## Task 12 Evidence

- Authority-consistent base: `aaa55599647163c6d8890e99059df2bff8597dee`; approved design SHA-256 `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; amended plan SHA-256 `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`.
- Exact-worktree GitNexus pre-edit impact: the JSON schema was not resolvable as a code symbol (`UNKNOWN`, zero indexed impacts); `_model_package` was LOW risk with exactly two direct test callers and zero affected execution processes. No HIGH or CRITICAL result occurred.
- TDD RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_model_package.py -q -p no:cacheprovider` -> collection exit `2`, `1 error in 10.69s`; expected cause was `ModuleNotFoundError: No module named 'fewsnet_partitioned_rf_pipeline.core.package'` before either Task 12 runtime module existed.
- Implementation: `write_model_package(...)` writes exactly `model.joblib`, `model_manifest.json`, `feature_contract.json`, the byte-identical approved `partition_map.csv`, horizon `threshold_report.json`, horizon `training_report.json`, and `checksums.json`; `checksums.json` is written last and contains SHA-256 identities for the prior six files. Joblib uses `compress=3, protocol=5`.
- Manifest/identity contract: the closed schema now requires the digest-pinned `container_image_uri`, matching `container_image_digest`, and copied training/validation target-month ranges. Writer and loader cross-check URI/digest equality, ranges, horizon, threshold, feature schema, approved partition digest, suite identity, optional image/source pins, and exact package membership.
- Defensive load order: exact files, every checksum, manifest schema, URI/digest, feature/partition identities, horizon reports and ranges, optional pins, and exact Python major/minor plus NumPy/pandas/scikit-learn/joblib/imbalanced-learn versions all validate before `joblib.load`; the loaded object must then be a matching `PartitionedRFPredictor`.
- Focused GREEN: the exact RED command -> `21 passed in 7.66s`.
- Related package/contract/preprocessing/partition/imputer/training/inference/parity regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_model_package.py tests/fewsnet_partitioned_rf/test_contracts.py tests/fewsnet_partitioned_rf/test_training_inference.py tests/fewsnet_partitioned_rf/test_preprocessing.py tests/fewsnet_partitioned_rf/test_partitions.py tests/fewsnet_partitioned_rf/test_imputer_thresholds.py tests/fewsnet_partitioned_rf/test_reference_parity.py -q -p no:cacheprovider` -> `117 passed in 19.08s`.
- Fresh full repository regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `503 passed, 1 skipped, 24 subtests passed in 35.07s`.
- Static/schema/dependency gates: all four touched Python files parse with `ast`; every FEWSNET JSON schema passes Draft 2020-12 metaschema validation; `.venv/bin/python -m pip check` -> `No broken requirements found.`; `git diff --check` -> exit `0` before the final ledger/staging gate.
- Scope boundary: no Task 13 file or behavior, GCP/GCS/Vertex API call, Model Registry or Batch operation, Endpoint, alias, release pointer, preserved IPCCH pipeline, external checkout, frozen design, suite-level `training-report.schema.json`, or dependency file was changed. The implementation commit subject is `feat: package Vertex-compatible FEWSNET models`; the exact hash is recorded in `.superpowers/sdd/task-12-report.md` after commit.

### Task 12 Independent-Review Fix Evidence

- Review scope: close the three Important findings only — validate exact horizon-report and nested evidence, bind the unpickled predictor to that report, fail closed when a required runtime distribution is absent, and reject directory/symlink package members before hashing. Whole-file hashing and checksum-authenticity documentation remain deferred Minor findings for final branch review.
- Pre-edit exact-worktree GitNexus impacts supplied and confirmed for this fix: `validate_horizon_training_report` HIGH with two direct internal callers confined to Task 12 package writer/loader flows; `runtime_dependency_versions` LOW; `_require_package_files` LOW; `load_model_package` MEDIUM with ten direct Task 12 test callers and zero existing runtime processes. The test fixture symbol was not resolvable (`UNKNOWN`); exact-tree search found four package-test consumers and no runtime path.
- Report/model-binding RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_model_package.py -q -p no:cacheprovider -k "training_report_extra_field or string_cluster_state or malformed_smote_result or predictor_report_mismatch"` -> `6 failed, 21 deselected in 10.62s`. Checksum-valid malformed reports reached the failing `joblib.load` sentinel, while three checksum-valid model/report mismatches loaded without rejection.
- Report/model-binding GREEN: the same command -> `6 passed, 21 deselected in 7.54s`. A follow-up status-type RED exposed three raw `TypeError` paths (`3 failed, 31 deselected in 10.41s`); the focused GREEN was `3 passed, 31 deselected in 7.01s` with every malformed status normalized to `PackageValidationError` before unpickling.
- Missing-dependency RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_model_package.py -q -p no:cacheprovider -k missing_runtime_dependency_fails_closed` -> `2 failed, 27 deselected in 10.08s`; writing emitted `not-installed`, and loading reported only a version mismatch. GREEN: `2 passed, 27 deselected in 6.84s`; both paths now raise a direct required-dependency `PackageValidationError` and never emit or accept `not-installed`.
- Member-type RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_model_package.py -q -p no:cacheprovider -k non_regular_package_member_before_hashing` -> `2 failed, 29 deselected in 9.85s`; both directory and symlink replacements reached the failing hash sentinel. GREEN: `2 passed, 29 deselected in 6.87s`; every exact package member must now be a regular, non-symlink file before hashing.
- Minimal implementation: the horizon validator enforces exact top-level and nested fields, binary non-negative class-count maps, nullable strings, Task 10 status vocabularies, per-state/SMOTE/fallback-count consistency, and sample-count totals. The loader retains the validated training report, then compares `partition_status` and the Task 10 metadata projections for `cluster_states` and `smote_results` after unpickling. Runtime version discovery raises on an absent required distribution, and the exact-member gate rejects directories, symlinks, and other non-regular file types.
- Fresh focused package verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_model_package.py -q -p no:cacheprovider` -> `34 passed in 8.29s`.
- Fresh related FEWSNET verification: package, contracts, training/inference, preprocessing, partitions, imputer/thresholds, and reference parity -> `130 passed in 18.89s`.
- Fresh full repository verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `516 passed, 1 skipped, 24 subtests passed in 34.69s`.
- Task 10 integration probe: trained a real 36-month horizon with the approved feature contract and fixed 17-cluster partition asset, validated its generated report, wrote the seven-file package, and loaded it through the hardened path -> `TASK10_PACKAGE_PROBE_OK 17 ['pooled_small_partition']`.
- Static/schema/dependency/diff gates: all three touched Python files parse with `ast`; all eight FEWSNET schemas pass Draft 2020-12 metaschema validation; exact runtime discovery returns all six required entries with no `not-installed`; `.venv/bin/python -m pip check` reports `No broken requirements found.`; `git diff --check` exits `0`.
- Preservation: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; amended plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`.
- Preliminary staged gate: exact-worktree GitNexus `detect_changes(scope="staged")` reports LOW risk, exactly four changed files, three indexed `PROGRESS.md` documentation symbols, and zero affected execution processes; the three changed Python files were not surfaced as symbols in this staged result. `git diff --cached --check` exits `0`, and staged paths are exactly `PROGRESS.md`, `core/package.py`, `core/validation.py`, and `test_model_package.py`.
- Scope boundary: only `core/validation.py`, `core/package.py`, the focused package test, and this ledger are tracked changes. The untracked Task 12 report is updated separately. No schema, Task 10 training code, contract test, design, plan, Task 13 behavior, cloud operation, registry/batch/alias/release-pointer action, or deferred Minor was entered. Planned review-fix commit subject: `fix: harden FEWSNET model package validation`.

### Task 12 Second Review Fix Evidence

- Fix base: `ba615e348859cf8a3c45f90c121b6d4c5c892698`; scope is limited to routing-evidence binding and defensive normalization in `core/package.py`, its focused package tests, this ledger, and the untracked Task 12 report.
- Pre-edit exact-worktree GitNexus impacts supplied for this wave: `_validate_predictor_reports` LOW with one internal caller; `write_model_package` LOW with four test callers and zero affected processes; `load_model_package` MEDIUM with fourteen Task 12 test callers and zero affected processes. No HIGH or CRITICAL result occurred.
- Routing RED: six writer/load cases for pooled status with a non-null model, a missing model key, and an extra model key -> `6 failed, 34 deselected in 10.43s`. GREEN after binding exact model keys and presence iff status is `partition_model` -> `6 passed, 34 deselected in 7.06s`.
- Normalization RED: writer/load cases for one- and two-element NumPy arrays in `partition_status` and `partition_metadata[*].status`, plus float keys in all three predictor report mappings -> `14 failed, 40 deselected in 11.85s`. One-element arrays were silently accepted, multi-element arrays leaked ambiguous-truth `ValueError`, and float keys were accepted.
- Minimal normalization: all predictor report mappings now require non-boolean integral cluster IDs, normalize them to `int`, reject normalized duplicates, and retain the established missing/extra-key errors. `partition_status` values must be strings before equality or routing checks. Metadata projections use the shared validation field constants and are passed through `validate_horizon_training_report` before any nested dictionary equality, with projection failures normalized to predictor-specific `PackageValidationError` paths while retaining the prior cluster-state/SMOTE mismatch anchors.
- Focused normalization GREEN: the exact 14-case RED selection -> `14 passed, 40 deselected in 7.58s`. Combined routing/normalization selection -> `20 passed, 34 deselected in 7.76s`.
- Fresh focused package verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_model_package.py -q -p no:cacheprovider` -> `54 passed in 9.45s`.
- Fresh related FEWSNET verification: package, contracts, training/inference, preprocessing, partitions, imputer/thresholds, and reference parity -> `150 passed in 20.25s`.
- Fresh full repository verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `536 passed, 1 skipped, 24 subtests passed in 35.62s`.
- Task 10 integration probe: a real 36-month horizon using the approved feature contract and fixed 17-cluster asset passed report validation plus a complete seven-file write/load round trip -> `TASK10_PACKAGE_PROBE_OK 17 ['pooled_small_partition']`.
- Static/schema/dependency/diff gates: both touched Python files parse with `ast`; all eight FEWSNET schemas pass Draft 2020-12 metaschema validation; `.venv/bin/python -m pip check` reports `No broken requirements found.`; `git diff --check` exits `0`.
- Preservation: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; amended plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`; fixed partition SHA-256 remains `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Staged GitNexus gate: `detect_changes(scope="staged")` reported HIGH for three changed files and eleven affected package write/load validation processes. Controller audit confirms the staged HIGH is line-shift over-attribution: zero-context diff changes only `_integer_keyed_mapping`, `_validate_predictor_reports`, one writer binding call, new focused tests, and `PROGRESS.md`; the reported unchanged helpers/processes have no content edits. Staged paths/check are exact and pre-edit impacts remain LOW/LOW/MEDIUM with zero runtime callers.
- Scope boundary: only `PROGRESS.md`, `core/package.py`, and `test_model_package.py` are authorized tracked changes; `.superpowers/sdd/task-12-report.md` remains untracked. `core/validation.py`, schemas, frozen design/plan, Task 10, Task 13, dependency files, cloud paths, and deferred Minors remain untouched. Planned commit subject: `fix: bind FEWSNET package routing evidence`.

### Task 12 Final Review and Controller Acceptance

- Second review-fix commit: `27742aa02de55f1876c9fd8ecc991726b3699f30` (`fix: bind FEWSNET package routing evidence`). The commit binds exact `partition_models` keys and model presence to the validated report status on both write and load, and normalizes predictor report keys/values before comparison.
- Final independent re-review: approved with no Critical or Important findings. Two non-blocking Minors remain deferred for final branch review: stream SHA-256 instead of loading whole artifacts into memory, and document or externally bind the trusted-source/authenticity boundary because package-local checksums establish consistency rather than authenticity.
- GitNexus reconciliation: the second fix staged gate reported HIGH for three files and eleven generated package flows. Zero-context diff and symbol-specific impacts confirmed line-shift over-attribution: actual production edits were `_integer_keyed_mapping`, `_validate_predictor_reports`, and one writer binding call; pre-edit impacts were LOW/LOW/MEDIUM and all direct `load_model_package` callers were Task 12 tests with zero runtime processes.
- Fresh controller focused verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_model_package.py -q -p no:cacheprovider` -> `54 passed in 9.49s`.
- Fresh controller related verification: package, contracts, training/inference, preprocessing, partitions, imputer/thresholds, and reference parity -> `150 passed in 20.26s`.
- Fresh controller full verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `536 passed, 1 skipped, 24 subtests passed in 35.54s`.
- Authority preservation: design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; amended plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`; no Task 13 or cloud write was attempted.

## Task 13 Kickoff

- Implementation base: `ecf6863d1b68e2daa718397c268987a6f9ee6efc`; branch `features/fewsnet-partitioned-rf-suite`; linked worktree `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.worktrees/fewsnet-partitioned-rf-suite`.
- Authority check: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`, and normalized plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`.
- Fresh requirements handoff: `.superpowers/sdd/task-13-brief.md`, generated directly from the approved Task 13 plan text before implementation.
- Pre-flight result: no conflict was found between Task 13, the frozen design, Task 12's seven-file package API, or the immutable storage boundary. The task creates only `cli/train.py`, `vertex/training_job.py`, and `test_training_job.py`, plus this execution ledger.
- TDD RED command: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_training_job.py -q -p no:cacheprovider`; expected initial failure is the absent Task 13 worker/job-spec modules or missing required behavior.
- GREEN/related verification: rerun the focused command, then `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_training_job.py tests/fewsnet_partitioned_rf/test_model_package.py -q -p no:cacheprovider`, followed by the complete repository suite before commit.
- Scope boundary: tests use local/fake storage and fake Vertex backends only. No real Custom Job submission, GCS object creation, Model Registry write, Batch Prediction, alias mutation, release-pointer mutation, or gated cloud smoke is authorized in Task 13.

### Task 13 Implementation Evidence

- Strict RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_training_job.py -q -p no:cacheprovider` -> collection exit `2` with the expected `ModuleNotFoundError: No module named 'fewsnet_partitioned_rf_pipeline.cli.train'`; summary `1 error in 4.44s`. Neither production module existed at this point.
- First GREEN attempt: `6 passed, 1 failed in 10.97s`; the one failure proved that GeoParquet deserializes the exact EPSG:4326 CRS as structured PROJ metadata rather than the literal string. The worker now compares semantic CRS identity, not serialization text.
- Focused GREEN: the exact RED command -> `7 passed in 10.96s`.
- Task 13 plus Task 12 package integration: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_training_job.py tests/fewsnet_partitioned_rf/test_model_package.py -q -p no:cacheprovider` -> `61 passed in 14.40s`.
- Relevant FEWSNET regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf -q -p no:cacheprovider` -> `246 passed in 29.80s`.
- Fresh full repository regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `543 passed, 1 skipped, 24 subtests passed in 40.81s`.
- Static/dependency checks: all three Task 13 Python files parse with `ast`; public imports succeed; no line exceeds 100 characters; `.venv/bin/python -m pip check` -> `No broken requirements found.` Ruff and Black are not installed in the pinned environment, so no dependency was added for formatting-only verification.
- Exact-worktree GitNexus was refreshed after the known incremental FTS inconsistency required one forced rebuild. Final indexed public-symbol impacts are LOW: `run_training_worker` has three direct callers and one new CLI process; `build_training_custom_job_spec` has three direct callers and one new Vertex process; `wait_for_training_custom_job` has two direct test callers and no affected process. No HIGH or CRITICAL result occurred.
- Staged GitNexus reconciliation: the required named-repo call with the exact `worktree` argument reports LOW risk, four changed files, three indexed `PROGRESS.md` sections, and zero affected processes, but under-attributes the three new Python files because the registry contains duplicate `IPCCH_operational` names. The exact worktree-path variant sees 120 new/touched symbols and 16 Task 13 flows and labels the additive change CRITICAL by count. Controller audit confirmed all 16 flows are newly introduced Task 13 flows, the four staged paths are exact, and the separate public upstream impacts are LOW; this is count-based over-attribution rather than an existing blast-radius break.
- Self-review: the worker verifies the manifest and every object at exact generations/checksums/sizes, revalidates normalization/row/area/month/CRS/content identity, loads the frozen feature contract without fitting it, preserves `HORIZON_MONTHS` order, uses the seven-file package and immutable-store APIs unchanged, writes identical aggregate report bytes twice, and writes `training_job_result.json` last. The Vertex module does not import the existing IPCCH client and contains no Task 18 phases or retry policy.
- Maintainability note: `cli/train.py` is 535 lines and `vertex/training_job.py` is 319 lines. The size reflects explicit validation and the mandated two-file boundary; helpers are single-purpose, but further lifecycle growth should move into Task 18 orchestration rather than expanding these modules.
- Authority/no-cloud confirmation: design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`. Tests used only `LocalArtifactStore` and a fake backend; no real GCP/GCS/Vertex/Registry/Batch/alias/release-pointer write occurred.

### Task 13 Independent-Review Fix Evidence

- Review finding: after a create-only `GenerationConflict`, `put_immutable_or_verify` and `upload_file_immutable_or_verify` trusted `ObjectRef.sha256` plus `size_bytes`. Forged or stale metadata could therefore claim the intended identity while same-size stored bytes differed.
- Authorized blast radius: `put_immutable_or_verify` was HIGH risk with six direct callers, 31 total impacts, and three process families; `upload_file_immutable_or_verify` had a degraded LOW result, while exact context showed four direct callers. The controller reviewed the shared-storage scope and authorized this narrow fix before edits.
- Strict review RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_storage.py -q -p no:cacheprovider -k 'immutable_byte_retry_rehashes or immutable_file_retry_rehashes'` -> `2 failed, 24 deselected in 1.37s`; both failures were the expected `Failed: DID NOT RAISE GenerationConflict` when forged SHA-256 metadata and same-size stored bytes differed from the intended bytes.
- Minimal fix: retain metadata and size as fail-fast gates, then read bytes at `existing.generation` for the byte helper or download that exact generation into `TemporaryDirectory` for the file helper. The byte helper recomputes SHA-256 from returned bytes; the file helper uses streaming `sha256_file`. Content mismatch and generation replacement fail closed, while byte-identical retry and missing-metadata behavior remain unchanged.
- Focused review GREEN: the exact RED command -> `2 passed, 24 deselected in 0.67s`; assertions also prove the GCS double received generation `1` for both exact-generation downloads.
- Full storage regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_storage.py -q -p no:cacheprovider` -> `26 passed in 3.68s`.
- Snapshot staging regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_snapshot_staging.py -q -p no:cacheprovider` -> `23 passed in 4.37s`.
- Task 13 plus Task 12 package regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_training_job.py tests/fewsnet_partitioned_rf/test_model_package.py -q -p no:cacheprovider` -> `61 passed in 12.88s`.
- Complete FEWSNET regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf -q -p no:cacheprovider` -> `248 passed in 29.54s`.
- Fresh full repository regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `545 passed, 1 skipped, 24 subtests passed in 39.92s`.
- Static/dependency gates: both changed Python files parse with `ast`; storage public imports succeed; no changed line exceeds 100 characters; `.venv/bin/python -m pip check` reports `No broken requirements found.`; focused `git diff --check` is clean.
- Final staged GitNexus reconciliation: the required named-repo call with the exact `worktree` argument reports LOW risk, three changed documentation symbols, and zero affected processes, but under-attributes both Python files because duplicate `IPCCH_operational` registrations select the canonical-root index. The exact worktree-path call reports MEDIUM risk, eleven changed symbols, and four processes, but hunk attribution labels unchanged adjacent bodies (`put_mutable_or_verify`, `sha256_file`, and the following colon-name test). Zero-context staged diff confirms the only production bodies changed are the two authorized immutable helpers; the four reported processes are existing `sha256_file` users reached through line-shift attribution, not unrelated behavior changes.
- Authority/scope preservation: design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`. No worker/job API, Task 14+, frozen design/plan, dependency, real cloud object, or external service was changed.

### Task 13 Final Review and Controller Acceptance

- Review-fix commit: `f0da32afa95aaecc61aacdfed8a1cdcfd0fcf3bc` (`fix: verify FEWSNET immutable retry bytes`). The complete Task 13 implementation range is `ecf6863d1b68e2daa718397c268987a6f9ee6efc..f0da32afa95aaecc61aacdfed8a1cdcfd0fcf3bc`.
- Independent re-review: spec compliant and approved with no Critical or Important findings. The prior GCS byte-identity finding is closed for both byte and file retries at the exact existing generation without weakening metadata, size, missing-metadata, or generation-race safeguards.
- Fresh controller focused verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_training_job.py tests/fewsnet_partitioned_rf/test_storage.py -q -p no:cacheprovider` -> `33 passed in 14.08s`.
- Fresh controller related verification: Task 13 worker/job, storage, snapshot staging, and Task 12 package tests -> `110 passed in 18.53s`.
- Fresh controller full repository verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `545 passed, 1 skipped, 24 subtests passed in 39.85s`.
- Authority preservation: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; normalized plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`.
- Scope/no-cloud confirmation: Task 14 was not started; no real Custom Job, GCS write, Model Registry, Batch Prediction, Endpoint, alias, release pointer, or gated cloud smoke action occurred.

## Task 14 Kickoff

- Implementation base: `9c6df4ab07a59a0260153e46b43d56d4db948b30`; branch `features/fewsnet-partitioned-rf-suite`; linked worktree `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.worktrees/fewsnet-partitioned-rf-suite`.
- Authority check: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`, and normalized plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`.
- Fresh requirements handoff: `.superpowers/sdd/task-14-brief.md`, generated directly from the approved Task 14 plan text before implementation.
- Pre-flight result: no conflict was found between Task 14, the frozen design, Task 13's shared image/trainer command, Task 12's seven-file package loader, or Task 15's future registry inputs. Task 14 creates only the predictor server, dedicated Dockerfile, two focused test files, and this ledger.
- Existing-symbol blast radius: no existing function, class, or method is scheduled for modification. The additive server composes `load_model_package`, `PartitionedRFPredictor.predict_frame`, and the existing artifact-store protocol unchanged. Any discovered need to edit an existing symbol requires a fresh exact-worktree upstream impact report before the edit; HIGH or CRITICAL risk must be reported before proceeding.
- GitNexus recovery: the first incremental refresh failed because the exact-worktree FTS index was inconsistent. A second run detected the incomplete incremental flag, forced a full rebuild, and succeeded at current HEAD with `3,480` nodes, `7,181` edges, `145` clusters, and `230` flows.
- Fresh baseline: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `545 passed, 1 skipped, 24 subtests passed in 41.51s`.
- Strict RED command: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_predictor_server.py tests/fewsnet_partitioned_rf/test_runtime_image.py -q -p no:cacheprovider`; expected initial failure is the absent Task 14 server and image contract.
- GREEN/related verification: rerun the focused command, run the import smoke from the approved plan, then run package/inference/storage-related regressions and one fresh full repository suite before commit.
- Scope boundary: tests use temporary packages, `LocalArtifactStore`, and FastAPI's local test client only. No image build/push, real GCS read/write, Model Registry upload, Batch Prediction, Endpoint, alias mutation, release-pointer mutation, or gated cloud smoke is authorized in Task 14.

## Task 14 Implementation Evidence

- Start state: exact linked worktree and branch matched the kickoff at `9c6df4ab07a59a0260153e46b43d56d4db948b30`; pre-existing user changes in `AGENTS.md`, `CLAUDE.md`, `.claude/`, and `.superpowers/` were preserved and excluded from staging.
- Existing-symbol scope: Task 14 added new symbols only. `load_model_package`, `PartitionedRFPredictor.predict_frame`, `ArtifactStore`, `LocalArtifactStore`, and `GCSArtifactStore` are consumed unchanged; no existing function, class, or method required an edit.
- Strict RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_predictor_server.py tests/fewsnet_partitioned_rf/test_runtime_image.py -q -p no:cacheprovider` -> `12 failed in 12.50s`. Eleven tests failed with the expected absent `predictor_server` module and the image contract failed with the expected absent Dockerfile.
- Minimal GREEN: `create_app` resolves the mandated Vertex environment values inside a guarded load block, localizes exactly `PACKAGE_FILES` once per app creation, validates image digest/source commit plus the package contract through `load_model_package`, stores either the predictor or startup error, and installs fail-closed health/predict routes. Requests must contain only `instances`; every instance must contain exactly `admin_code`, `feature_month`, and the package feature allowlist. The model-fixed horizon cannot be supplied by the request.
- Shared image: `docker/Dockerfile.fewsnet-partitioned-rf` matches the approved Python 3.11 image, labels the training/predictor/orchestrator entrypoints, installs only `requirements-fewsnet-partitioned-rf.txt`, records `FEWSNET_SOURCE_GIT_COMMIT`, exposes `8080`, and defaults to the predictor module. No image build, push, or registry action was performed.
- Final focused GREEN after the green-state response/test-constant refactors: the exact RED command -> `12 passed in 8.06s`.
- Approved import smoke: `.venv/bin/python -c "from fewsnet_partitioned_rf_pipeline.vertex.predictor_server import create_app; assert callable(create_app)"` -> exit `0`.
- Related regression: model-package, training/inference, storage, runtime-foundation, and training-job tests -> `104 passed in 27.29s`.
- Final fresh full repository regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `557 passed, 1 skipped, 24 subtests passed in 40.81s`.
- Static/dependency gates: all three changed Python files parse with `ast`; no changed Python line exceeds 100 characters; the only longer changed line is the mandated predictor Docker label; `.venv/bin/python -m pip check` -> `No broken requirements found.`
- GitNexus refresh: post-code incremental analysis first succeeded with `3,534` nodes, `7,334` edges, `152` clusters, and `232` flows. The ledger-only incremental refresh then hit the known FTS inconsistency; the immediate retry detected the incomplete flag, forced a full rebuild, and succeeded. The final test-constant refresh completed incrementally at `3,536` nodes, `7,336` edges, `152` clusters, and `232` flows.
- Staged GitNexus reconciliation: the duplicate-name `repo="IPCCH_operational"` lookup reports LOW risk, five changed files, three documentation symbols, and zero processes, under-attributing the new files. The exact-worktree-path lookup reports HIGH by additive count: 46 newly indexed symbols and ten flows, all starting at the new `create_app` and descending through existing package-validation/download paths. New public-symbol upstream checks are LOW (`create_app`, `_localize_package`, and `_validated_instances` have no indexed upstream production impact; `main` has one direct module-guard caller). Zero-context staged diff confirms no existing production symbol body changed.
- Self-review: missing environment or any localization/package/checksum/dependency/image-digest/source-commit failure produces health and predict `503`; a valid package produces health `200`; prediction preserves instance order and JSON-safe formal rows; missing or undeclared features and request-level horizon fields produce `400`. Tests use temporary packages, `LocalArtifactStore`, and `TestClient`; no real cloud client or backend is invoked.
- Authority preservation: design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`.
- Implementation commit: `963eea0029e47887f6b735e0984d3a994b355d9a` (`feat: serve FEWSNET models in Vertex`). Task 15 was not started.
- Scope/no-cloud confirmation: no real GCP/GCS/Vertex Custom Job/Model Registry/Batch Prediction/Endpoint, image build/push, alias mutation, release-pointer mutation, or gated cloud smoke action occurred.

### Task 14 Independent Review Fix Evidence

- Review base: `963eea0029e47887f6b735e0984d3a994b355d9a` (`feat: serve FEWSNET models in Vertex`). The review reproduced all three reported defects before production edits: module execution localized 14 rather than seven package files, configured health paths `/docs`, `/redoc`, and `/openapi.json` returned FastAPI default-route `200` responses during startup failure, and a valid falsy injected store was replaced by the default GCS factory.
- Entry-point RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_predictor_server.py -q -p no:cacheprovider -k module_entrypoint_localizes_exactly_seven_package_files` -> `1 failed, 11 deselected in 11.63s`; observed download count was 14 instead of seven.
- Entry-point GREEN: the same selector -> `1 passed, 11 deselected in 7.56s`. `main()` aliases the active `python -m` module under the canonical import name before calling the unchanged approved Uvicorn import string, preventing a second module-level `create_app()` execution.
- Health-route RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_predictor_server.py -q -p no:cacheprovider -k configured_health_route_is_not_shadowed_by_fastapi_defaults` -> `3 failed, 12 deselected in 11.06s`; all three reserved paths returned `200`.
- Health-route GREEN: the same selector -> `3 passed, 12 deselected in 7.21s`. FastAPI's default docs, ReDoc, and OpenAPI routes are disabled so the configured fail-closed health handler owns those paths.
- Injected-store RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_predictor_server.py -q -p no:cacheprovider -k falsy_injected_store_does_not_use_default_gcs_store` -> `1 failed, 15 deselected in 11.06s`; the default factory was called once.
- Injected-store GREEN: the same selector -> `1 passed, 15 deselected in 7.37s`. Store selection now distinguishes only `None`, preserving any injected `ArtifactStore` regardless of truthiness.
- Combined Task 14 verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_predictor_server.py tests/fewsnet_partitioned_rf/test_runtime_image.py -q -p no:cacheprovider` -> `17 passed in 7.98s`.
- Approved import smoke: `.venv/bin/python -c "from fewsnet_partitioned_rf_pipeline.vertex.predictor_server import create_app; assert callable(create_app)"` -> exit `0`.
- Related package/inference/storage/runtime/training regression -> `104 passed in 24.71s`.
- Fresh full repository regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `562 passed, 1 skipped, 24 subtests passed in 40.14s`.
- Static/dependency gates: both changed Python files parse with `ast`; maximum line lengths are 88 and 81; `.venv/bin/python -m pip check` -> `No broken requirements found.`; unstaged `git diff --check` is clean.
- GitNexus reconciliation: the duplicate-name staged lookup is LOW with three documentation symbols and zero processes. The incremental exact-worktree refresh hit the known inconsistent `file_fts` deletion error; the immediate retry forced a successful full rebuild at 3,548 nodes, 7,369 edges, 151 clusters, and 232 flows. The final exact-worktree staged lookup is HIGH by additive count with 22 changed/touched symbols and ten existing flows, every one marking `create_app` as the changed first step. Fresh exact-worktree upstream impact remains LOW for both edited production functions: `create_app` has zero direct callers/processes, and `main` has one direct module-guard caller and zero processes. The zero-context staged diff confirms that only `create_app`, `main`, and the focused tests changed, so the HIGH staged label reflects the number of existing package-load flows descending from the edited `create_app` entrypoint rather than a high upstream caller blast radius.
- Authority preservation: design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`.
- Review-fix commit: `fix: harden FEWSNET predictor startup` (this commit). Only the predictor server, its focused tests, and this ledger are authorized for the commit.
- Scope/no-cloud confirmation: the Dockerfile and its exact command remain unchanged; Task 15 was not started; no image build/push or real GCP/GCS/Vertex/Registry/Batch/Endpoint/alias/release-pointer action occurred.

### Task 14 Final Review and Controller Acceptance

- Review-fix commit: `6ea587343a8a31076d929a1401f47fa74b2545ce` (`fix: harden FEWSNET predictor startup`). The complete Task 14 implementation range is `9c6df4ab07a59a0260153e46b43d56d4db948b30..6ea587343a8a31076d929a1401f47fa74b2545ce`.
- Independent re-review: spec compliant and approved with no Critical, Important, or Minor findings. The reviewer confirmed exactly seven downloads under the real `python -m`/canonical-Uvicorn path, fail-closed configured health routes for `/docs`, `/redoc`, and `/openapi.json`, and correct handling of a valid falsy injected store.
- Fresh controller focused verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_predictor_server.py tests/fewsnet_partitioned_rf/test_runtime_image.py -q -p no:cacheprovider` -> `17 passed in 7.59s`.
- Fresh controller related verification: model-package, training/inference, storage, runtime-foundation, and training-job tests -> `104 passed in 25.04s`.
- Fresh controller full repository verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `562 passed, 1 skipped, 24 subtests passed in 40.14s`.
- Controller static/dependency gates: approved import smoke exits `0`; all three Task 14 Python files parse with `ast`; `.venv/bin/python -m pip check` reports `No broken requirements found.`; the complete Task 14 range passes `git diff --check`.
- Authority preservation: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; normalized plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`.
- Scope/no-cloud confirmation: the dedicated Dockerfile was not built or pushed; no real GCP/GCS/Vertex Custom Job/Model Registry/Batch Prediction/Endpoint, alias, release-pointer, or gated cloud smoke action occurred; Task 15 was not started.

## Task 15 Kickoff

- Implementation base: `680161f3e0a9f4f35ca7d1f57f1b477b2718049f`; branch `features/fewsnet-partitioned-rf-suite`; linked worktree `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.worktrees/fewsnet-partitioned-rf-suite`.
- Authority verification: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; normalized plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`.
- Fresh requirements handoff: `.superpowers/sdd/task-15-brief.md`, generated directly from the approved Task 15 plan text before implementation.
- Pre-flight result: no conflict was found between Task 15, the frozen design, Task 14's custom prediction-container contract, Task 16's exact-version Batch boundary, the existing `PARENT_MODEL_IDS`, or the existing `RegisteredModelVersion` type. Task 15 creates only `vertex/registry.py`, its focused test file, and this ledger.
- Resolved implementation detail: registry labels reserve `horizon`, `suite`, and `lifecycle`; the suite label uses the sanitized alias when it fits Vertex's 63-character label-value limit and otherwise uses a deterministic readable prefix plus hash suffix. The complete suite identity remains authoritative in the version alias, registration evidence, and later manifests.
- Run-manifest boundary: `register_candidate_version` receives a required injected updater callback, persists immutable `runs/{run_id}/registry/{horizon}.json` evidence first, then invokes the callback with the exact `RegisteredModelVersion`. Task 18 remains the sole owner of generation-guarded run-manifest serialization.
- GitNexus readiness: the exact-worktree index was refreshed successfully at `680161f` (`3,549` nodes, `7,370` edges, `151` clusters, `232` flows). No existing function, class, or method is scheduled for modification; any such discovery requires upstream impact analysis before editing.
- Fresh baseline: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider` -> `562 passed, 1 skipped, 24 subtests passed in 41.72s`; installed `google-cloud-aiplatform` version is exactly `1.161.0`.
- Strict RED command: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_registry.py -q -p no:cacheprovider`; expected initial failure is the absent Task 15 registry adapter or missing required behavior.
- Scope boundary: tests must use a complete fake/mock SDK adapter and local/fake artifact persistence only. No real model lookup/upload, GCS write, Batch Prediction, Endpoint, alias mutation, release-pointer mutation, or gated cloud smoke is authorized in Task 15.

## Task 15 Implementation Evidence

- Start state: exact linked worktree and branch matched the kickoff at `680161f3e0a9f4f35ca7d1f57f1b477b2718049f`; pre-existing user changes in `AGENTS.md`, `CLAUDE.md`, `.claude/`, and `.superpowers/` were preserved and excluded from staging.
- Existing-symbol scope: Task 15 added only `fewsnet_partitioned_rf_pipeline/vertex/registry.py` and `tests/fewsnet_partitioned_rf/test_registry.py`, then updated this ledger. It consumes `PARENT_MODEL_IDS`, `RegisteredModelVersion`, `ArtifactStore`, and `put_immutable_or_verify` unchanged; no existing function, class, or method required an edit.
- Strict RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_registry.py -q -p no:cacheprovider` -> collection exit `2` with the expected `ModuleNotFoundError: No module named 'fewsnet_partitioned_rf_pipeline.vertex.registry'` before production registry code existed (`1 error in 1.18s`).
- Focused GREEN: the exact RED command -> `26 passed in 12.35s` after adding the narrow adapter. The six horizon/parent-state upload cases assert the exact stable model IDs, artifact/image identities, `/predict` and `/health`, port `8080`, both required environment variables, candidate labels, deterministic suite alias, no `production` alias, first-parent defaults, later-parent resource names, and absence of any caller-supplied `version_id`.
- Alias and label contract: suite identities are lowercased, non-`[a-z0-9-]` characters become collapsed hyphens, leading/trailing hyphens are removed, non-letter starts receive `v-`, and empty or over-128-character results fail. Reserved labels are exactly `horizon`, `suite`, and `lifecycle`; caller conflicts fail before upload. Suite label values preserve the alias through 63 characters and otherwise use a deterministic 50-character readable prefix plus a 12-hex SHA-256 suffix.
- Parent and retry contract: `aiplatform.init(project=..., location=...)` precedes deterministic parent resolution; only `NotFound` from `ModelRegistry.list_versions()` is treated as parent absence. Existing suite aliases are loaded by exact numeric version through `Model(model_name=..., version=...)`, and reuse fails closed on artifact URI, serving image URI, digest environment, horizon label, or suite label mismatch. An exact retry may merge `lifecycle=candidate` while preserving all other labels and never uploads a duplicate.
- Evidence and failure ordering: normalized `RegisteredModelVersion` JSON is written immutably at `runs/{run_id}/registry/{horizon}.json` before the required injected run-manifest callback. Callback exceptions propagate after evidence persistence so the orchestrator can retry the same exact version. Later suite-stage cleanup loads every recorded exact version and merges only `lifecycle=abandoned`, retaining provenance labels and deleting nothing.
- Fake-only coverage: all registry tests use a complete in-memory SDK double plus `LocalArtifactStore`. The doubles mirror every SDK field consumed by production (`VersionInfo`, model resource/version/artifact identities, labels, container image, and environment entries). No authentication, real parent lookup/upload/update, GCS write, Batch Prediction, Endpoint, alias mutation, release pointer, or cloud smoke action occurred.
- Fresh full repository regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `588 passed, 1 skipped, 24 subtests passed in 52.64s`.
- Final fresh focused verification: the exact Task 15 command -> `26 passed in 11.94s`.
- Static/dependency/authority gates: both changed Python files parse with `ast`; maximum line lengths are `81` and `82`; `.venv/bin/python -m pip check` -> `No broken requirements found.`; `google-cloud-aiplatform==1.161.0` remains pinned; approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; approved plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`; partition SHA-256 remains `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- GitNexus refresh: the first exact-worktree `analyze --index-only` hit the known inconsistent `file_fts` deletion error. The immediate retry detected the incomplete incremental flag, forced a full rebuild, and succeeded with `3,646` nodes, `7,560` edges, `152` clusters, and `234` flows without rewriting agent-context files.
- Staged GitNexus reconciliation: the required duplicate-name lookup with `repo="IPCCH_operational"` and the exact worktree reports LOW risk, exactly three changed files, three documentation symbols, and zero affected processes because it resolves to the canonical-root duplicate index. The authoritative exact-worktree-path lookup reports MEDIUM risk with `100` additive/touched symbols and two affected processes; both are wholly new Task 15 internal flows (`register_candidate_version -> _required_string` and `resolve_parent_model -> _required_string`). No pre-existing production symbol body changed.
- Final staged scope: `git diff --cached --name-status` contains exactly `PROGRESS.md`, `fewsnet_partitioned_rf_pipeline/vertex/registry.py`, and `tests/fewsnet_partitioned_rf/test_registry.py`; `.superpowers/` remains untracked and unstaged; `git diff --cached --check` exits `0`.
- Self-review: all Task 15 plan statements are represented directly in tests; no existing production interface was changed; the first stable parent remains default only because Vertex requires version 1 to be default; later candidates cannot move `default` or `production`; service-assigned numeric version IDs are returned and persisted without invention; failed/retried candidates remain recoverable evidence rather than being deleted.
- Implementation commit: `feat: register FEWSNET Vertex model versions` (this commit). Independent Task 15 review remains required before controller acceptance or Task 16 implementation.
- Scope/no-cloud confirmation: no real GCP, GCS, Vertex Custom Job, Model Registry, Batch Prediction, Endpoint, alias, release-pointer, image build/push, or gated cloud smoke operation was performed.

## Task 15 Independent Review Fix Evidence

- Independent review result: `0 Critical, 2 Important, 0 Minor`. The two valid findings were that exact retry did not compare `FEWSNET_SOURCE_GIT_COMMIT`, and that retry neither rejected `production` in `VersionInfo.version_aliases` nor constrained lifecycle restoration and structural validation ordering.
- Root cause: `_validate_existing_candidate` checked artifact, image, digest, horizon, and suite identity but omitted the source commit. `register_candidate_version` ignored the resolved version aliases and changed every non-candidate lifecycle to `candidate` before constructing the structurally validated `RegisteredModelVersion`.
- Pre-edit exact-worktree GitNexus impacts were LOW: `register_candidate_version` had two direct test callers and zero affected existing processes; `_validate_existing_candidate` remained confined to the new Task 15 internal flow. No HIGH or CRITICAL warning applied.
- Review RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_registry.py -q -p no:cacheprovider` -> `8 failed, 27 passed in 19.42s`. The failures were the expected accepted source-commit mismatch, accepted `production` alias, accepted missing/unsupported lifecycle values, and lifecycle mutation before each parent/version/`@version` structural failure.
- Minimal fix: pass and exactly compare `source_git_commit`; reject only the `production` version alias while retaining `default`; allow existing lifecycle values only in `{candidate, abandoned}`; construct and structurally validate the registered version before any label update; and restore only `abandoned` to `candidate`.
- Focused GREEN: the exact review RED command -> `35 passed in 11.07s`.
- Full regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `597 passed, 1 skipped, 24 subtests passed in 50.44s`.
- Static and environment checks: both changed Python files parse with `ast`; no line exceeds 88 characters; `.venv/bin/python -m pip check` reports `No broken requirements found.`; and `git diff --check` exits `0`.
- Preliminary staged GitNexus reconciliation before completion review: `repo="IPCCH_operational"` plus the exact worktree reported LOW risk, exactly three changed files, three documentation symbols, and zero affected processes because the duplicate name resolves to the canonical-root index. The authoritative exact-worktree-path call reported MEDIUM risk, exactly three changed files, 18 touched/adjacent symbols, and one affected process: the existing Task 15 internal `register_candidate_version -> _required_string` flow.
- Exact-worktree context confirms `register_candidate_version` still has only two incoming callers, both in `test_registry.py`, and participates only in the one Task 15 internal process. Zero-context staged diff confirms the only production bodies changed are the pre-authorized `register_candidate_version` and `_validate_existing_candidate`; neighboring helper/test symbols reported by hunk attribution were not edited.
- Pre-completion-review staged scope: `git diff --cached --check` exited `0`; `git diff --cached --name-status` contained exactly `PROGRESS.md`, `fewsnet_partitioned_rf_pipeline/vertex/registry.py`, and `tests/fewsnet_partitioned_rf/test_registry.py`. Pre-existing `AGENTS.md`, `CLAUDE.md`, `.claude/`, and `.superpowers/` changes remained unstaged.
- Fix-wave self-review: mismatched source commits and production-aliased versions fail before upload, lifecycle update, evidence persistence, or callback; `default` remains allowed; `candidate` is reused without mutation; only `abandoned` is restored; missing or any other lifecycle fails closed; and structural identity validation precedes lifecycle mutation.
- Scope/no-cloud confirmation: only the Task 15 registry adapter, focused tests, and this ledger are tracked fix-wave changes. No GCP, GCS, Vertex, Model Registry, Batch Prediction, Endpoint, alias, release-pointer, image, release, or smoke operation occurred.
- Review-fix commit: `fix: harden FEWSNET registry retries` (this commit).

## Task 15 Exact-Version Lifecycle Follow-up

- Completion review found one Critical SDK-boundary defect: pinned `google-cloud-aiplatform==1.161.0` implements `Model.update()` by replacing the request name with `self.resource_name`, the unversioned parent model. Both abandoned-to-candidate retry restoration and `mark_registered_versions_abandoned` therefore risked updating parent/default labels instead of the intended numeric version.
- Installed-source verification: `Model.update` explicitly sets `copied_model_proto.name = self.resource_name`; `ModelRegistry.update_version(version, labels=...)` loads and updates the requested version resource. No network or live Vertex call was used.
- Additional exact-worktree impacts were LOW: `mark_registered_versions_abandoned` has one direct focused-test caller and zero affected processes; `FakeRegistry` has zero upstream impact. No HIGH or CRITICAL blast-radius warning applied.
- SDK-boundary RED: the focused registry command -> `2 failed, 35 passed in 21.86s`. Both failures proved `ModelRegistry.update_version` was not called and a fake parent/default sentinel received the direct `Model.update` path.
- The first GREEN attempt produced `1 failed, 36 passed in 20.15s`; the sole `NameError` was a test-placement mistake where three pre-existing assertions were left in the new test. The zero-upstream test assertions were restored without a production change.
- Minimal fix: after structural identity validation, retry restoration now calls the already-resolved registry's `update_version(version=registered.version_id, labels=...)`; abandonment creates the stable parent registry and calls `update_version(version=version.version_id, labels=...)`. Both merge the existing exact-version labels and preserve provenance.
- Exact-version focused GREEN: the registry command -> `37 passed in 10.99s`.
- Fresh full regression after the exact-version fix: `599 passed, 1 skipped, 24 subtests passed in 51.26s`.
- Static/environment rerun: both changed Python files parse with `ast`; no line exceeds 88 characters; `.venv/bin/python -m pip check` reports `No broken requirements found.`; and `git diff --check` exits `0`.
- Exact-version self-review: abandoned-to-candidate restoration and later abandonment pass the exact numeric version ID to `ModelRegistry.update_version`; candidate labels change as intended, while another/default version under the same stable parent remains unchanged.
- Completion re-review: `0 Critical, 0 Important, 0 Minor`; the prior Critical is closed at both version-specific lifecycle call sites, sentinel tests protect parent/default labels, and the staged patch is assessed ready to merge.
- Final staged GitNexus reconciliation: `repo="IPCCH_operational"` plus the exact worktree remains LOW risk with exactly three changed files, three documentation symbols, and zero affected processes. The authoritative exact-worktree-path view is MEDIUM with exactly three changed files, 22 touched/adjacent symbols, and two Task 15 internal processes: `register_candidate_version -> _required_string` and `resolve_parent_model -> _required_string`.
- Final attribution review: zero-context staged diff confirms the production edits are limited to `register_candidate_version`, `mark_registered_versions_abandoned`, and `_validate_existing_candidate`. The reported `_resolve_parent_registry`, neighboring helpers, and later test bodies are unchanged and surfaced through line-hunk adjacency.
- Final staged scope: `git diff --cached --check` exits `0`; the staged path list is exactly `PROGRESS.md`, `fewsnet_partitioned_rf_pipeline/vertex/registry.py`, and `tests/fewsnet_partitioned_rf/test_registry.py`. Pre-existing `AGENTS.md`, `CLAUDE.md`, `.claude/`, and `.superpowers/` changes remain unstaged.

## Task 15 Controller Acceptance

- Accepted implementation range: `680161f3e0a9f4f35ca7d1f57f1b477b2718049f..4d9f0099b0e995a7505f1d7e9be3463a2ddc018b`, including `2bcd227` (`feat: register FEWSNET Vertex model versions`) and `4d9f009` (`fix: harden FEWSNET registry retries`).
- Independent completion re-review: `0 Critical, 0 Important, 0 Minor`; both lifecycle mutation paths use `ModelRegistry.update_version` with the exact numeric version ID, and parent/default sentinel labels remain unchanged.
- Fresh controller focused verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_registry.py -q -p no:cacheprovider` -> `37 passed in 18.63s`.
- Fresh controller related verification: contracts, storage, model-package, training-job, predictor-server, runtime-image, and registry tests -> `177 passed in 37.02s`.
- Fresh controller full repository verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `599 passed, 1 skipped, 24 subtests passed in 52.04s`.
- Static/dependency gates: registry implementation and tests parse with `ast`; approved registry imports succeed; `.venv/bin/python -m pip check` reports `No broken requirements found.`; production `registry.py` contains no `Model.update(...)` lifecycle call; and the complete fix commit plus staged state pass `git diff --check`.
- Authority preservation: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; approved plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`.
- Post-commit GitNexus comparison remains below the warning threshold: the named duplicate index reports LOW; the authoritative exact-worktree view reports MEDIUM with only the two Task 15 internal processes. The comparison also surfaces preserved user edits in `AGENTS.md` and `CLAUDE.md`; `git show 4d9f009` confirms the accepted commit itself contains exactly `PROGRESS.md`, `vertex/registry.py`, and `test_registry.py`.
- Scope/no-cloud confirmation: no real GCP, GCS, Vertex Custom Job, Model Registry, Batch Prediction, Endpoint, alias, release-pointer, image build/push, or gated cloud smoke operation was performed.

## Task 16 Kickoff

- Implementation base: `651057e743eb87d656eefd2e040da045229ad473`; branch `features/fewsnet-partitioned-rf-suite`; linked worktree `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.worktrees/fewsnet-partitioned-rf-suite`.
- Authority verification: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; approved plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`.
- Fresh requirements handoff: `.superpowers/sdd/task-16-brief.md`, generated directly from the approved Task 16 plan text before implementation. The packaged script lacked executable bits, so the same script was invoked through `bash` with an explicit output path; the resulting brief contains the exact 71-line Task 16 block.
- Pre-flight result: no conflict was found between Task 16, the frozen design, `select_latest_inference_frame`, `FeatureContract`, `RegisteredModelVersion`, `BatchJobRef`, `ArtifactStore`, `put_immutable_or_verify`, the formal prediction schema, or Task 18's orchestration boundary. Task 16 creates only the approved Batch adapter, inference CLI, focused fixture/test, and updates this ledger.
- Pinned SDK boundary: local `google-cloud-aiplatform==1.161.0` confirms `BatchPredictionJob.submit(...)` delegates with `wait_for_completion=False`; the public `JobServiceClient` exposes exact-name `get_batch_prediction_job` and `cancel_batch_prediction_job`. Tests and implementation must preserve that asynchronous submit/poll/cancel contract and exact numeric `@version_id` model resource.
- GitNexus readiness: the exact-worktree index was refreshed at `651057e` with `3,661` nodes, `7,613` edges, `152` clusters, and `234` flows. Query/context review identified the existing latest-month, Batch reference, storage, and schema boundaries; no existing function, class, or method is scheduled for modification, and any discovered need requires upstream impact analysis before editing.
- Fresh baseline inherited from the immediately preceding controller gate: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `599 passed, 1 skipped, 24 subtests passed in 52.04s`; the only subsequent tracked commit was the Task 15 documentation ledger.
- Strict RED command: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_batch_prediction.py -q -p no:cacheprovider`; expected initial failure is the absent Task 16 test/module/fixture contract.
- Scope boundary: use fake SDK/job-service backends and `LocalArtifactStore` only. Do not submit or cancel a real Batch job, read/write real GCS, mutate Registry/Endpoint/aliases/release pointers, or run gated cloud smoke coverage.

## Task 16 Completion

- Strict minimal RED: the exact focused command failed as intended with `1 failed in 1.10s`; `test_batch_prediction_module_exposes_task_16_interfaces` raised `ModuleNotFoundError` for the absent `fewsnet_partitioned_rf_pipeline.vertex.batch_prediction` module.
- Expanded RED before production code: the same exact focused command produced `22 failed in 10.82s`; all failures were the expected absent `vertex.batch_prediction` or `cli.infer` modules, with no collection or test-design error.
- Batch input contract: `write_batch_input_jsonl` emits one UTF-8 JSON object per supplied latest-month area, preserves `FeatureContract.feature_columns` order, normalizes identity, serializes missing numeric predictors as JSON `null`, and excludes target/horizon fields.
- Exact-version submit contract: `submit_batch_prediction` derives `runs/{run_id}/batch_prediction/{horizon}/input.jsonl` and the matching `raw` prefix from the validated deployment root, rejects non-numeric or inconsistent `@version_id` identities, and calls SDK `1.161.0` `BatchPredictionJob.submit(...)` with JSONL formats, the configured machine/service account, one starting/max replica, labels, project, and region.
- Public JobService contract: `wait_batch_prediction` polls `get_batch_prediction_job` by the exact submitted resource, records `output_info.gcs_output_directory` only on success, surfaces complete failed resources, and on deadline calls `cancel_batch_prediction_job` for the exact name before waiting for terminal cancellation/failure and raising `BatchPredictionTimeoutError`.
- Output gates: normalization rejects `errors_*.jsonl`, line-level errors, invalid UTF-8/JSON, absent instance/prediction objects, malformed/duplicate/missing identities, prediction-to-instance/input mismatches, horizon/target drift, conflicting suite/model identity, and every formal-schema violation. It restores supplied input order and validates each completed `prediction-record` before returning.
- Canonical publication: `cli.infer` rebuilds the latest inference frame from the immutable snapshot, localizes only `predictions_*.jsonl`, serializes the validated formal frame once, and immutable-writes the identical byte sequence to the exact run and suite prediction URIs only after all row gates pass.
- Focused GREEN: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_batch_prediction.py -q -p no:cacheprovider` -> `22 passed in 18.75s`.
- Related regression: horizons, training inference, predictor server, registry, storage, contracts, and training-job tests -> `165 passed in 34.87s`.
- Full repository regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `621 passed, 1 skipped, 24 subtests passed in 53.69s`.
- Static/dependency gates: installed SDK signature exposes every submitted keyword; the new implementation and test files compile; no changed Python line exceeds 88 characters; `.venv/bin/python -m pip check` reports `No broken requirements found.`; and `git diff --check` exits `0`.
- Self-review: fake SDK and JobService objects carry complete documented request/resource structures; assertions verify production behavior rather than mock existence; no test-only production API was added; input/output identity and immutable-write ordering are fail closed.
- Staged GitNexus reconciliation: both `repo="IPCCH_operational"` with the exact linked worktree and the exact-worktree-path repository report LOW risk, exactly five changed files, and zero affected execution processes. Because the four Python/fixture/test paths are new relative to the indexed base, changed-symbol mapping reports only existing `PROGRESS.md` sections; their executable behavior is covered by the focused, related, and full regression gates above.
- Final staged scope: the staged path list is exactly `PROGRESS.md`, `fewsnet_partitioned_rf_pipeline/cli/infer.py`, `fewsnet_partitioned_rf_pipeline/vertex/batch_prediction.py`, `tests/fewsnet_partitioned_rf/test_batch_prediction.py`, and `tests/fixtures/fewsnet_partitioned_rf/vertex_batch_output.jsonl`. Pre-existing user `AGENTS.md`, `CLAUDE.md`, `.claude/`, and `.superpowers/` changes remain unstaged.
- Scope/no-cloud confirmation: tracked Task 16 work is limited to the approved Batch adapter, inference CLI, raw-output fixture, focused tests, and this ledger. No live cloud, network, authentication, GCS, Vertex, Registry, Endpoint, alias, release-pointer, or smoke operation occurred.
- Task commit: `feat: run FEWSNET Vertex batch prediction` (this commit).

### Task 16 Independent Review Fix Evidence

- Independent review result: `0 Critical, 4 Important, 1 Minor`. The four Important findings were reproduced and fixed; the timeout-order Minor is explicitly deferred for final whole-branch triage.
- Review-fix base: `d22c6d61e3c2d79446f3b22c3455f9c154c18a67` (`feat: run FEWSNET Vertex batch prediction`).
- Pre-edit GitNexus impact: `write_batch_input_jsonl`, `submit_batch_prediction`, `normalize_batch_output`, `_json_scalar`, and `normalize_and_publish_batch_output` were LOW risk. `_validate_model_ref` was HIGH risk because both submission and normalization call it; the controller warned on that blast radius and authorized only the narrow expected-parent binding. Both callers remain compatible.
- Strict review RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_batch_prediction.py -q -p no:cacheprovider` -> `12 failed, 24 passed in 43.96s`. The failures covered string/boolean/non-finite `float64` violations, unsupported declared dtypes, wrong project/region/stable parent, echoed-instance feature value/type drift, horizon/target/extra-field leakage, and non-nullable `cluster_id` output.
- Exact parent binding: submission now requires `RegisteredModelVersion.parent_model_resource_name` to equal `projects/{project_id}/locations/{region}/models/{parent_model_ids[horizon_key]}` before any SDK call.
- Exact instance echo: normalization now requires every echoed `instance` field and value to match the supplied input row exactly, excluding only `fews_ipc_crisis` and `target_month`; feature drift, numeric type drift, horizon/target leakage, and extra fields fail closed.
- Dtype-safe JSONL: input writing pairs every feature with `FeatureContract.feature_dtypes`, supports only declared `float64`, rejects strings, booleans, unsupported dtypes, and non-finite values, preserves missing values as JSON `null`, and emits accepted numeric values as native floats. All validation completes before creating or replacing the destination.
- Nullable integer publication: normalized `cluster_id` is explicitly pandas `Int64`, and formal records are revalidated after DataFrame construction. Canonical CSV bytes render populated IDs as `3`, not `3.0`, and missing IDs as blank.
- Focused GREEN: the exact review RED command -> `36 passed in 24.89s`.
- Related regression: horizons, training inference, predictor server, registry, storage, contracts, and training-job tests -> `165 passed in 51.34s`.
- Fresh full repository regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `635 passed, 1 skipped, 24 subtests passed in 67.16s`.
- Final fresh pre-commit rerun: focused -> `36 passed in 23.96s`; related -> `165 passed in 43.19s`; full repository -> `635 passed, 1 skipped, 24 subtests passed in 64.88s`.
- Static/dependency gates: the three Task 16 Python files parse with `ast`; `compileall` passes; no changed Python line exceeds 88 characters; `.venv/bin/python -m pip check` reports `No broken requirements found.`; and `git diff --check` exits `0`.
- Authority preservation: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; normalized plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`.
- Deferred Minor: `wait_batch_prediction` checks elapsed timeout before fetching the current job state, so a job that became terminal exactly at the deadline may receive an unnecessary cancellation request. This non-blocking ordering improvement is recorded but intentionally not changed in this fix wave.
- Scope/no-cloud confirmation: changes remain limited to the Task 16 Batch adapter, focused tests, and this ledger. No cloud, network, authentication, GCP, GCS, Vertex, Registry, Batch, Endpoint, alias, release-pointer, image, release, or smoke operation occurred.
- Review-fix commit: `fix: harden FEWSNET batch prediction contracts` (this commit). Independent re-review remains required before Task 17 starts.
- Controller GitNexus reconciliation: a later exact-worktree `detect_changes(scope="staged")` repeat returned the false-negative `No changes detected` while Git still showed the exact three staged review-fix paths. The fallback exact-worktree comparison against `d22c6d6` reported HIGH risk, five working-tree files, 41 touched/adjacent symbols, and nine Task 16 internal flows; the five-file view included preserved user `AGENTS.md` and `CLAUDE.md` edits. `git diff --cached --name-status`, `git diff --cached --check`, and commit `33b2bc1` prove the actual fix commit contains only `PROGRESS.md`, `vertex/batch_prediction.py`, and `test_batch_prediction.py`.

### Task 16 Second Independent Re-review Fix Evidence

- Second re-review result: `0 Critical, 2 Important`; the previously deferred timeout-order Minor remains open and was not changed.
- Review-fix base: `33b2bc170e7688232ed46a350429010221e5c4f9` (`fix: harden FEWSNET batch prediction contracts`).
- Verified gaps: normalization/publication did not bind the requested suite to `RegisteredModelVersion.suite_version_alias` and `artifact_uri`; prediction identity comparison used lossy canonical keys and then retained the raw drifted `admin_code` representation.
- Pre-authorized exact-worktree impact: `normalize_batch_output`, `_validate_prediction_uris`, and `_set_exact_identity` were LOW risk, each with one direct caller and two affected Task 16 CLI processes. No other existing function, class, or method was edited.
- Strict RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_batch_prediction.py -q -p no:cacheprovider` -> `6 failed, 36 passed in 32.45s`. All six failures were expected `DID NOT RAISE` results for a wrong deterministic suite alias, wrong artifact suite, wrong artifact horizon, whitespace admin drift, leading-zero admin drift, and an artifact rooted outside the exact suite publication URI.
- Suite/model binding: normalization now uses Task 15 `suite_version_alias(suite_version)` and requires the registered alias to match. It also requires the model artifact path to end exactly at `suites/{suite_version}/models/{horizon}`. Publication derives the complete expected artifact URI from `suite_csv_uri` and rejects any other bucket/root before immutable writes.
- Exact prediction identity: after canonical-key reconciliation, normalization requires the raw prediction `admin_code` and `feature_month` to equal the echoed/submitted canonical identity exactly, then writes those canonical values into the formal record. Whitespace, leading zeros, type drift, and other lossy representations fail closed.
- Focused GREEN: the exact RED command -> `42 passed in 19.60s`.
- Related regression: horizons, training inference, predictor server, registry, storage, contracts, and training-job tests -> `165 passed in 40.68s`.
- Fresh full repository regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `641 passed, 1 skipped, 24 subtests passed in 58.74s`.
- Static/environment gates: all three changed Python files parse with `ast`; production imports and the reused Task 15 alias helper succeed; installed SDK `BatchPredictionJob.submit` still exposes every required keyword; no changed Python line exceeds 88 characters; `.venv/bin/python -m pip check` reports `No broken requirements found.`; and `git diff --check` exits `0`.
- Authority preservation: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; normalized plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`.
- Scope/no-cloud confirmation: changes are limited to the Task 16 inference CLI, Batch normalization adapter, focused tests, and this ledger. No cloud, network, authentication, GCP, GCS, Vertex, Registry, Batch, Endpoint, alias, release-pointer, image, release, or smoke operation occurred; Task 17 was not started.
- Second review-fix commit: `fix: bind FEWSNET inference identities` (this commit). Independent re-review remains required before Task 16 can be controller-accepted.

### Task 16 Third and Fourth Re-review Fix Evidence

- The next independent re-review reclassified the timeout-order observation as one Important finding: `wait_batch_prediction` could cancel before refreshing a job that had already succeeded within the deadline. GitNexus upstream impact for `wait_batch_prediction` was LOW, with no indexed upstream caller or unrelated process reach.
- Strict timeout RED: the focused Task 16 command -> `1 failed, 42 passed in 34.08s`; the new deadline-success regression reproduced cancellation before the third authoritative `get()`.
- Timeout GREEN: the same command -> `43 passed in 20.51s`; current state is now refreshed and processed before timeout cancellation, while genuine timeout still cancels once and drains to terminal cancellation/failure.
- Timeout fix commit: `b33e8217a08538e3ffb528f6c5f77521d87ddc74` (`fix: poll FEWSNET batch state before timeout`). Its exact commit scope is `vertex/batch_prediction.py` plus `test_batch_prediction.py`.
- The following independent re-review confirmed the timeout fix but found one new Important URI-boundary defect: `run_csv_uri` could use another bucket/root or a nested/empty run path while the suite CSV and model artifact remained under the canonical publication root.
- GitNexus upstream impact for `_validate_prediction_uris` was LOW: one direct caller and only the existing Task 16 normalize/publish and CLI chains.
- Strict publication-root RED: the focused Task 16 command -> `3 failed, 43 passed in 32.39s`; wrong-root and nested run paths were accepted, and the empty run ID reached storage instead of failing the URI gate.
- Publication-root GREEN: the same command -> `46 passed in 19.67s`. `suite_csv_uri` now determines the exact publication root, and `run_csv_uri` must equal that root plus `runs/<one nonempty run-id segment>/predictions/{horizon}.csv`; all malformed variants reject before any write.
- Publication-root fix commit: `35b96c5f679d87574598c32424cfe54d7d648b8a` (`fix: bind FEWSNET run publication root`). Its exact commit scope is `cli/infer.py` plus `test_batch_prediction.py`.
- Final independent re-review at `35b96c5`: `0 Critical, 0 Important, 0 Minor`; spec compliance approved and task quality approved. Reviewer-focused verification was `46 passed in 21.28s`.

## Task 16 Controller Acceptance

- Accepted implementation range: `651057e743eb87d656eefd2e040da045229ad473..35b96c5f679d87574598c32424cfe54d7d648b8a`, comprising the initial implementation and four strict-TDD fix commits.
- Fresh controller focused verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_batch_prediction.py -q -p no:cacheprovider` -> `46 passed in 21.87s`.
- Fresh controller related verification: horizons, training inference, predictor server, registry, storage, contracts, and training-job tests -> `165 passed in 37.46s`.
- Fresh controller full repository verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `645 passed, 1 skipped, 24 subtests passed in 55.70s`.
- Static/dependency gates: Task 16 production/tests parse with `ast`, import successfully, compile with redirected bytecode, and preserve all required `google-cloud-aiplatform==1.161.0` `BatchPredictionJob.submit` parameters; `.venv/bin/python -m pip check` reports `No broken requirements found.`; `git diff --check 651057e..HEAD` exits `0`.
- Authority preservation: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; normalized plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`.
- GitNexus recovery and reconciliation: the first post-commit incremental refresh hit the known inconsistent `file_fts` error; the required retry detected the incomplete run and completed a full rebuild with `3,840` nodes, `8,075` edges, `166` clusters, and `253` flows. Exact-worktree compare against `651057e` reports CRITICAL over seven working-tree files and 22 Task 16 flows because it includes preserved user edits in `AGENTS.md`/`CLAUDE.md` and maps the complete new Task 16 boundary. Commit-range Git evidence proves the accepted range contains exactly the five authorized paths: `PROGRESS.md`, `cli/infer.py`, `vertex/batch_prediction.py`, `test_batch_prediction.py`, and the Batch fixture.
- Scope/no-cloud confirmation: no live cloud, network, authentication, GCP, GCS, Vertex, Registry, Batch, Endpoint, alias, release-pointer, image, release, or smoke operation occurred.

## Task 17 Kickoff

- Implementation base: `f3a02ab` (`docs: record FEWSNET task 16 review`) on branch `features/fewsnet-partitioned-rf-suite` in the existing linked worktree.
- Fresh requirements handoff: `.superpowers/sdd/task-17-brief.md`, generated directly from the approved 58-line Task 17 plan block with the script invoked through `bash` and an explicit output path.
- Authority verification: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; normalized plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`.
- Fresh inherited baseline: the immediately preceding controller gate ran `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `645 passed, 1 skipped, 24 subtests passed in 55.70s`; no tracked production change followed before this kickoff.
- Pre-flight result: no conflict was found among the Task 17 brief, authoritative two-phase promotion design, `SnapshotManifest`, `RegisteredModelVersion`, immutable `ObjectRef`, suite/model schemas, fixed-partition release gate, storage generation helpers, or Task 18 orchestration boundary.
- Validation carrier decision: each horizon's `predictions` entry must explicitly bundle the formal prediction frame, exact Batch input `ObjectRef`, the snapshot-content digest recorded for that Batch input, and the validated package manifest. This is the narrow carrier required for the approved three-argument `validate_prediction_suite(predictions, snapshot, registered_versions)` interface to enforce Batch input URI/generation/checksum plus Batch/package snapshot-digest identity without repeating them in each CSV row.
- GitNexus concept query found no existing FEWSNET promotion/rollback flow to modify. `core/validation.py` currently contains package/training validators used by package-write processes; Task 17 must add the new suite validator and helpers without changing existing function/class/method bodies. File-level impact lookup is unsupported (`UNKNOWN`); if implementation discovers a need to edit any existing symbol, it must run exact-worktree upstream impact first and stop for any HIGH/CRITICAL warning.
- Strict RED command: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_promotion.py -q -p no:cacheprovider`; expected initial failure is the absent Task 17 test/module/interfaces.
- Scope boundary: use `LocalArtifactStore` and fake alias/Vertex adapters only. Do not acquire a real lease, read/write real GCS, move a real Vertex alias, mutate a Registry/Endpoint, publish a release pointer, or start Task 18.

## Task 17 Implementation Evidence

- Strict TDD RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_promotion.py -q -p no:cacheprovider` -> collection exit `2` with the expected `ImportError` for absent `PredictionSuiteEntry`; no production file had changed (`1 error in 11.24s`).
- Focused GREEN: the same command -> `26 passed in 20.65s` after adding the explicit four-part `PredictionSuiteEntry` carrier, additive three-horizon validation, fake/local promotion coverage, the pinned Vertex alias adapter, lease serialization, alias rollback, immutable suite evidence, same-month generation replacement, and current-pointer-last publication.
- Related Task 2/3/8/10/12/15/16 regression: contracts, storage, partitions, training/inference, model packages, registry, and Batch Prediction -> `229 passed in 42.48s`.
- Full repository regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `671 passed, 1 skipped, 24 subtests passed in 57.48s`.
- Final fresh pre-commit verification: focused Task 17 -> `26 passed in 22.57s`; full repository -> `671 passed, 1 skipped, 24 subtests passed in 57.99s`.
- Validation preservation gate: AST comparison against `f3a02ab` found all `16` pre-existing functions/classes in `core/validation.py` present with body-identical ASTs; Task 17 only adds imports, constants, the carrier, the public suite validator, and new helpers.
- Static/dependency/SDK gates: all three Task 17 Python files parse with `ast`, import, and compile with redirected bytecode; maximum line lengths are `87`, `84`, and `85`; `.venv/bin/python -m pip check` reports `No broken requirements found.`; `google-cloud-aiplatform==1.161.0` exposes the required `ModelRegistry.get_version_info(self, version)`, `add_version_aliases(self, new_aliases, version)`, and `remove_version_aliases(self, target_aliases, version)` signatures.
- Authority preservation: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; normalized plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`; fixed partition SHA-256 remains `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Exact-worktree staged GitNexus gate: MEDIUM risk, `4` changed files, `14` mapped changed symbols, and `2` affected package/container validation flows. The index mapped line-shifted pre-existing `core/validation.py` symbols as touched; the independent AST comparison proves all `16` pre-existing function/class bodies are identical to `f3a02ab`. Git staging contains exactly `PROGRESS.md`, `core/validation.py`, new `vertex/promotion.py`, and new `test_promotion.py`; preserved `AGENTS.md`, `CLAUDE.md`, `.claude/`, and `.superpowers/` changes remain unstaged.
- Scope/no-cloud confirmation: tests used only `LocalArtifactStore`, fake alias/SDK backends, and injected UTC/lease identities. No real GCP, GCS, Vertex AI, Model Registry, Batch Prediction, Endpoint, alias, lease, release-pointer, image, network, or authentication operation occurred; Task 18 was not started.
- Implementation commit: `feat: promote FEWSNET model suites safely` (this commit). Independent review and controller acceptance remain required before Task 18.

### Task 17 Independent Review Fix Evidence

- Review-fix base: `200c3bc3e3e14882462043b8d97f9b5e5733b5ed` (`feat: promote FEWSNET model suites safely`). The independent review found four Critical gaps: suite validation trusted self-declared prediction provenance, an alias commit-then-raise was omitted from rollback, recovery mutated state without proving an active lease, and a current-pointer commit-then-raise could leave mixed authoritative state.
- Pre-authorized exact-worktree GitNexus impact remained within the reviewed boundary: `PredictionSuiteEntry`, `_validate_prediction_frame`, and `_rollback_aliases` were LOW; `validate_prediction_suite` and `promote_and_publish` were MEDIUM. The HIGH-risk shared `put_mutable_or_verify` helper was not modified.
- Strict review RED: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_promotion.py -q -p no:cacheprovider` -> `8 failed, 25 passed in 30.42s`. The expected failures proved the missing snapshot-admin and Batch-byte bindings, fixed-partition routing check, attempted-alias rollback, lease-safe recovery, and authoritative current-pointer reconciliation.
- Provenance fix: `PredictionSuiteEntry` now carries the generation-read `admin_universe.csv` bytes and Batch JSONL bytes. Validation checks exact SHA-256 and size against their existing `ObjectRef` values, parses normalized unique identities and the exact feature month, reconciles predictions/Batch/snapshot universes, and routes every prediction through `PartitionMap.load(PARTITION_ASSET_PATH, PARTITION_ASSET_SHA256)` while preserving the approved two-percentage-point coverage gate.
- Recovery fix: aliases are recorded before each mutation attempt; every alias or month-pointer recovery mutation first proves the same lease ID/run ID, `acquired` status, unexpired time, and generation-specific lease bytes. Lost ownership stops recovery and is surfaced through rollback failures/warnings.
- Ambiguous-write fix: Task 17 locally wraps existing mutable pointer writes and generation-reads the current object after an exception. If intended bytes committed, the write is accepted; therefore a current-pointer commit-then-raise returns `RELEASED` and keeps the candidate aliases and month pointer authoritative.
- Focused GREEN: the exact RED command -> `33 passed in 21.23s`.
- Related Task 2/3/8/10/12/15/16 regression: contracts, storage, partitions, training/inference, model packages, registry, and Batch Prediction -> `229 passed in 39.28s`.
- Fresh full repository regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `678 passed, 1 skipped, 24 subtests passed in 62.41s`.
- Static/dependency/SDK gates: all three changed Python files parse and compile with redirected bytecode; maximum line lengths are `87`, `84`, and `85`; imports pass; `.venv/bin/python -m pip check` reports `No broken requirements found.`; and the pinned `google-cloud-aiplatform==1.161.0` Model Registry signatures remain unchanged.
- Authority preservation: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; normalized plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`; fixed partition SHA-256 remains `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Exact-worktree staged GitNexus gate: LOW risk across the exact four staged files, with no mapped changed symbols or affected processes in the current index. `git diff --cached --name-status` and `git diff --cached --check` confirm the stage contains only `PROGRESS.md`, `core/validation.py`, `vertex/promotion.py`, and `test_promotion.py`; preserved `AGENTS.md`, `CLAUDE.md`, `.claude/`, and `.superpowers/` state remains unstaged.
- Scope/no-cloud confirmation: all review-fix tests used only local stores and fake backends. No cloud, network, authentication, GCP, GCS, Vertex, Registry, Batch, Endpoint, production alias, lease, release-pointer, image, release, or smoke operation occurred; Task 18 was not started.
- Review-fix commit: `fix: harden FEWSNET suite promotion` (this commit). Independent re-review remains required before Task 17 is controller-accepted.

### Task 17 Second Independent Re-review Fix Evidence

- Fix-wave base: `6a8a4bdc69520f0f4b123b3f54ab7edda3a6acdb` (`fix: harden FEWSNET suite promotion`). The second independent re-review reported three Critical gaps: self-asserted Batch provenance, forward/recovery lease TOCTOU windows, and single-read ambiguous current-pointer reconciliation.
- Pre-edit GitNexus impact recorded before this wave: `promote_and_publish` MEDIUM; carrier/validation/lease/reconciliation helpers LOW; shared `vertex/storage.py::put_mutable_or_verify` HIGH and explicitly unchanged.
- Strict second-wave RED: the exact focused command -> `19 failed, 33 passed in 29.82s`. Failures were the expected missing completed-`BatchJobRef`/canonical artifact bindings, acceptance of non-900-second leases, flat lease generation across forward mutations, unsafe alias recovery over newer ownership, absent recovery state read/fence, missing transient readback retry, and missing indeterminate no-rollback outcome.
- Additional strict TDD probes: horizon-neutral Batch bytes first failed `1 failed, 52 deselected in 27.99s` and then passed `1 passed, 52 deselected in 17.23s`; cross-horizon snapshot `ObjectRef` drift first failed `1 failed, 53 deselected in 29.28s` and then passed `1 passed, 53 deselected in 17.54s`.
- Provenance fix: `PredictionSuiteEntry` now carries the completed `BatchJobRef`, immutable run/suite prediction refs and canonical CSV bytes, plus the canonical run-level input-snapshot ref and bytes. Validation derives the publication root from each exact registered artifact path; enforces `run_id == suite_version`; reconciles numeric Batch job/model/horizon/input/destination/output identity; rejects non-canonical input and prediction URIs; requires identical horizon-neutral Batch bytes; binds snapshot evidence to the selected snapshot/package; and requires both prediction refs to match the one canonical serialization of the formal frame.
- Lease fix: acquisition rejects every duration other than exactly 900 seconds. A generation-preconditioned renewal preserves lease owner/status and extends expiry by 900 seconds immediately before every alias, immutable manifest, month pointer, and current pointer mutation. Rollback renews before reading alias state, restores only an alias still on this run's candidate, renews again immediately before restore, returns the latest lease generation, and skips all mutation after a takeover between state read and restore.
- Ambiguous-write fix: Task 17-local pointer reconciliation performs three generation-specific readback attempts. A committed current write with one transient read failure returns `RELEASED`; persistent unreadability raises `PromotionIndeterminate(indeterminate=True)` and retains candidate aliases plus the candidate month pointer without destructive rollback.
- Fresh focused GREEN: exact command -> `54 passed in 19.04s`.
- Related Task 2/3/8/10/12/15/16 regression: contracts, storage, partitions, training/inference, model packages, registry, and Batch Prediction -> `229 passed in 35.29s`.
- Fresh full repository regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `699 passed, 1 skipped, 24 subtests passed in 54.09s`.
- Static/dependency/SDK gates: all three changed Python files parse, import, and compile with redirected bytecode; maximum line lengths are validation `87`, promotion `84`, and tests `85`; `.venv/bin/python -m pip check` reports `No broken requirements found.`; pinned Model Registry method signatures remain unchanged; `git diff --check` passes.
- Authority preservation: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; normalized plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`; fixed partition SHA-256 remains `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Scope/no-cloud confirmation: all tests used `LocalArtifactStore` and fake alias/SDK backends only. No cloud, network, authentication, GCP, GCS, Vertex, Registry, Batch, Endpoint, production alias, lease, pointer, image, release, or smoke operation occurred; Task 18 was not started.
- Second-wave fix commit: `fix: close Task 17 promotion re-review findings` (this commit). Final independent re-review and controller acceptance remain required before Task 18.

### Task 17 Final Provenance Closure Evidence

- Final re-review found one remaining Critical provenance gap: a valid Batch input `ObjectRef` generation could be replaced by another positive integer, and one completed Vertex Batch job resource name could be reused across horizons.
- Exact-worktree pre-edit impact for `validate_prediction_suite` was HIGH with `15` direct upstream dependents in the FEWSNET module and no mapped execution process; the warning was reported before the controller authorized the two narrow probes. `PredictionSuiteEntry`, `_prediction_entries`, and `_with_batch_bytes` were LOW.
- Strict RED: the two narrow tests failed exactly as expected with `2 failed, 54 deselected in 28.96s`; both failures were `DID NOT RAISE`, proving generation drift and duplicate completed-job reuse were accepted before production edits.
- Provenance closure: `PredictionSuiteEntry` now carries the independently named submitted Batch input `ObjectRef`. Validation checks both refs and requires exact dataclass equality, including URI, generation, SHA-256, and size. It also requires the three completed `job_resource_name` values to be unique.
- Narrow GREEN: the exact two probes passed with `2 passed, 54 deselected in 17.63s`. The first focused rerun exposed only an existing attack-test ordering mismatch (`1 failed, 55 passed`); updating that test to mutate both attacker-controlled refs preserved its canonical-root assertion, after which focused Task 17 passed with `56 passed in 17.98s`.
- Fresh related Task 2/3/8/10/12/15/16 regression: `229 passed in 32.69s`.
- Fresh full repository regression: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider` -> `701 passed, 1 skipped, 24 subtests passed in 52.87s`.
- Static/dependency/SDK gates: all three changed Python files parse, import, and compile with redirected bytecode; maximum line lengths remain validation `87`, promotion `84`, and tests `85`; `.venv/bin/python -m pip check` reports `No broken requirements found.`; pinned Model Registry method signatures remain unchanged; `git diff --check` passes.
- Authority preservation: approved design SHA-256 remains `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`; normalized plan SHA-256 remains `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`; fixed partition SHA-256 remains `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Final independent narrow re-review: `0 Critical, 0 Important, 0 Minor`; exact input-ref equality and cross-horizon completed-job uniqueness were accepted statically. No cloud, network, authentication, GCP, GCS, Vertex, Registry, Batch, Endpoint, production alias, lease, pointer, image, release, or smoke operation occurred; Task 18 was not started.
- Final closure commit: `fix: close Task 17 promotion re-review findings` (this commit).

### Task 17 Controller Acceptance

- Fresh focused controller verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_promotion.py -q -p no:cacheprovider` -> `56 passed in 16.28s`.
- Fresh related controller verification for contracts, storage, partitions, training/inference, model packages, registry, and Batch Prediction -> `229 passed in 30.42s`.
- Fresh full repository verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `701 passed, 1 skipped, 24 subtests passed in 52.31s`.
- Static/controller gates passed: all three Task 17 Python files parse, import, and compile with redirected bytecode; `.venv/bin/python -m pip check` reports no broken requirements; pinned `ModelRegistry` alias method signatures remain compatible; `git diff --check f3a02ab..HEAD` is clean; and all `16` pre-existing function/class bodies in `core/validation.py` remain AST-identical to `f3a02ab`.
- Frozen authority remains exact: design SHA-256 `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`, plan SHA-256 `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`, and fixed-partition SHA-256 `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- GitNexus refreshed successfully at `751ad4d` to `4,096` nodes, `8,813` edges, `175` clusters, and `261` flows. Exact-worktree compare reported HIGH across six files because it also included the preserved uncommitted `AGENTS.md` and `CLAUDE.md`; the exact Git commit range `f3a02ab..751ad4d` contains only `PROGRESS.md`, `core/validation.py`, new `vertex/promotion.py`, and new `test_promotion.py`. Context inspection shows the validation callers are Task 17 tests with no mapped process, while `promote_and_publish` participates only in the intended promotion flow.
- Controller acceptance: Task 17 is complete with final review `0 Critical, 0 Important, 0 Minor`. No real cloud, network, authentication, GCP, GCS, Vertex, Registry, Batch, Endpoint, alias, lease, release-pointer, image, or smoke operation occurred.

## Task 18 Kickoff

- Implementation base: `4234084` (`docs: record FEWSNET task 17 review`) in the existing linked worktree on `features/fewsnet-partitioned-rf-suite`; the preserved `AGENTS.md`, `CLAUDE.md`, `.claude/`, and `.superpowers/` state remains outside tracked implementation commits.
- Fresh requirements handoff: `.superpowers/sdd/task-18-brief.md`, generated directly from the approved 86-line Task 18 plan block. Implementer report target: `.superpowers/sdd/task-18-report.md`.
- Frozen authority remains exact: design SHA-256 `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`, plan SHA-256 `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`, and fixed-partition SHA-256 `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Fresh baseline immediately before kickoff: focused Task 17 `56 passed`, related Tasks 2/3/8/10/12/15/16 `229 passed`, and full repository `701 passed, 1 skipped, 24 subtests`.
- Pre-flight found no conflict between Task 18 and the existing snapshot, one-job training, candidate registration, exact-version Batch, suite-validation, or generation-fenced promotion contracts. Task 18 must consume Task 17's exact generation-read snapshot/admin bytes, independently submitted Batch input ref, completed unique `BatchJobRef`, canonical run/suite prediction refs and bytes, and indeterminate-promotion semantics rather than reconstructing weaker evidence.
- GitNexus concept discovery identified the existing training, registration, Batch, validation, and promotion composition points. Fresh upstream impact is LOW for `validate_deployment`, `submit_and_persist_training_custom_job`, `register_candidate_version`, `submit_batch_prediction`, `validate_prediction_suite`, and `promote_and_publish`. No existing symbol is scheduled for edit; any discovered need to modify one requires a fresh upstream impact report before editing.
- Strict RED command: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_run_latest.py -q -p no:cacheprovider`; expected initial failure is the absent Task 18 test/module/interface.
- Scope boundary: use only `LocalArtifactStore` and injected fake training, registry, Batch, and alias backends. Do not perform any real cloud, network, authentication, GCP, GCS, Vertex, Registry, Batch, Endpoint, alias, lease, release-pointer, image, or smoke operation.

### Task 18 Implementation Evidence

- Strict TDD RED: after creating only `tests/fewsnet_partitioned_rf/test_run_latest.py`, `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_run_latest.py -q -p no:cacheprovider` failed exactly as expected with `1 failed in 1.40s` and `ModuleNotFoundError: No module named 'fewsnet_partitioned_rf_pipeline.cli.run_latest'`; the production module did not exist.
- Focused GREEN: the exact RED command now reports `17 passed in 22.06s`. Coverage includes newest schema-valid exact-generation discovery, prior-pointer NOOP, same-month revision gating, byte-identical manifest restaging at a new generation, candidate-only isolation, training/registration/Batch/output/validation failures, terminal evidence, bounded transient retries with stable identity, `PromotionBusy`, `PromotionIndeterminate`, generation-preconditioned run-manifest updates, and CLI injection.
- Related Tasks 13-18 verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_run_latest.py tests/fewsnet_partitioned_rf/test_training_job.py tests/fewsnet_partitioned_rf/test_predictor_server.py tests/fewsnet_partitioned_rf/test_registry.py tests/fewsnet_partitioned_rf/test_batch_prediction.py tests/fewsnet_partitioned_rf/test_promotion.py -q -p no:cacheprovider` -> `179 passed in 28.14s`.
- Fresh full repository verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `718 passed, 1 skipped, 24 subtests passed in 62.12s`.
- Deterministic evidence: the orchestrator preserves the selected manifest `ObjectRef` and bytes, exact snapshot-admin bytes, one immutable `input_snapshot_ref.json`, one suite identity created before retries, one training job identity, idempotent suite aliases and candidate versions, exact submitted Batch input refs, completed unique Batch job refs, and canonical run/suite prediction bytes. Every run-manifest write uses the prior exact generation as its precondition.
- Failure behavior: training failure prevents registration; registration failure abandons earlier returned candidates; Batch/output/suite-validation failures prevent all alias reads or moves and abandon all returned candidates; retries are limited to the named transient classes and `PromotionBusy`; `PromotionIndeterminate` remains an indeterminate `FAILED` terminal result without Task 18 alias/pointer recovery.
- Static/dependency gates: both new Python files pass AST parsing, built-in compilation, redirected `py_compile`, and public import. Maximum line lengths are `86` for `cli/run_latest.py` and `82` for `test_run_latest.py`. `.venv/bin/python -m pip check` reports `No broken requirements found.` and `git diff --check` exits `0`.
- Frozen authority remains exact: design SHA-256 `3ab8522823e79ef2f7085c4c4f50a34f18c1319902b3a7cdcf945ab4222eac53`, plan SHA-256 `b500910639b2d3fd6b2bbc973a80f903589cefef73e8d5e6c3a5ccb2dc0be33f`, and fixed-partition SHA-256 `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Self-review: `run_latest.py` is additive and does not edit any Task 13-17 symbol. Candidate-only skips production pointer and alias reads. Production default adapters are defined only for the CLI and were not instantiated in verification; every test used `LocalArtifactStore` plus injected fakes. The 1,207-line orchestrator and 1,739-line focused test are large because the approved task fixes both production and test scope to one file each; helpers remain single-purpose and no unrelated refactor was introduced.
- Scope/no-cloud confirmation: tracked implementation scope is only new `cli/run_latest.py`, new `test_run_latest.py`, and this ledger. Preserved `AGENTS.md`, `CLAUDE.md`, `.claude/`, and `.superpowers/` state remains outside the commit. No real cloud, network, authentication, GCP, GCS, Vertex, Registry, Batch, Endpoint, alias, lease, release-pointer, image, release, or smoke operation occurred.
- Exact-worktree staged GitNexus gate: LOW risk across exactly three changed files, eight mapped `PROGRESS.md` documentation symbols, and zero affected execution processes. The current index does not map the two additive Python files as changed symbols, so staged path review, focused/related/full runtime verification, and static import/compile evidence provide the executable-scope check.
- Planned implementation commit subject: `feat: orchestrate FEWSNET model suite releases`.

### Task 18 Independent Review Findings

- Implementation commit: `7689b73a3c1955d912751868a7e19e614616b6e3` (`feat: orchestrate FEWSNET model suite releases`). Independent task review returned spec non-compliance and `Needs fixes`: `3 Critical`, `2 Important`, `0 Minor`.
- Critical: the same-month changed-snapshot revision authorization is checked before long-running work but not rechecked inside Task 17's promotion lease, so two no-revision same-month runs can race and the later one can overwrite the first.
- Critical: real training and Batch submit boundaries have no commit-then-raise reconciliation. Outer retries can create duplicate Custom Jobs or Batch Jobs; the focused fakes currently hide that by deduplicating submissions internally.
- Critical: `PromotionIndeterminate` and failures after an authoritative `RELEASED` promotion can still mark live production versions `abandoned`.
- Important: the training job receives only the selected manifest URI, not immutable exact-generation bytes or a run-specific immutable manifest object, so a restage can change what the worker reads after discovery.
- Important: failures before `_RunState` initialization return a bare failure without terminal artifacts. This must be reconciled against the approved ordering that validates deployment/source identity before discovery and the run-manifest schema whose first normal phase is `DISCOVERED`; do not invent placeholder snapshot evidence or silently change the schema.
- Controller verification of review: the revision lease recheck lacks revision context; the pinned Vertex `CreateCustomJobRequest` and `CreateBatchPredictionJobRequest` expose no request-id field; submission helpers call create/submit directly; failure cleanup is unconditional; and the training CLI resolves the bare manifest URI later. The findings are technically grounded.
- Fresh post-review GitNexus rebuild recovered from the known incremental `file_fts` inconsistency by forcing a full rebuild to `4,291` nodes, `9,364` edges, `180` clusters, and `274` flows. Upstream impact is LOW for `run_latest`, `_VertexTrainingBackend.submit`, `promote_and_publish`, `submit_and_persist_training_custom_job`, and both Batch submit candidates. Any additional existing symbol discovered during the fix wave still requires its own upstream impact before edit.
- Fix-wave design gate: the exact-worktree impact for the required narrow `promote_and_publish` edit is HIGH with `18` upstream dependents (`16` direct tests) and `2` Task 18 orchestration processes; the warning was reported before edits. No production or test fix has yet been made.
- Pre-discovery evidence conflict: deployment/source validation must run before discovery, while `fewsnet-run-manifest-v1` requires exact snapshot evidence, feature month, suite version, and run ID. An invalid deployment may also lack a valid object-store root. Honest options are: (A) clarify that terminal run artifacts apply after successful discovery and return/log structured preflight errors before that boundary; or (B) authorize a new preflight-attempt identity/artifact contract or run-manifest v2 with a preflight phase and nullable snapshot evidence.
- Contract resolution: the user selected A on 2026-07-21. Formal run identity and required `error.json`/`run_manifest.json` begin only after successful discovery selects exact snapshot evidence. Deployment/source/discovery failures return/log a structured preflight error and exit nonzero without a preflight-attempt contract, `PREFLIGHT` phase, schema v2, nullable snapshot evidence, or fabricated run identity. The design, Task 18 plan/brief, review handoff, and both execution ledgers were synchronized before production edits resumed.
- Contract-resolution staged gate: GitNexus `detect_changes(scope="staged")` reported LOW risk across exactly three tracked documentation/ledger files, 13 mapped documentation symbols, and zero affected execution processes; staged diff/path checks were clean and preserved `AGENTS.md`, `CLAUDE.md`, `.claude/`, and `.superpowers/` outside the commit.

### Task 18 Review Fix-Wave Evidence

- Root 1, lease-protected revision gate: `promote_and_publish` was HIGH impact with `18` upstream dependents, `16` direct tests, and `2` affected orchestration processes; the warning was accepted before the narrow edit. Strict RED for the same-month changed-digest race reported `1 failed, 56 deselected in 31.57s`; GREEN reported `1 passed, 56 deselected in 18.13s`. The Task 18 forwarding RED returned `FAILED`; GREEN reported `1 passed, 16 deselected in 19.32s`. Four lease/pointer preservation cases then reported `4 passed, 53 deselected in 25.98s`.
- Root 2, real submit reconciliation: deterministic 63-character `fewsnet_operation` labels now bind the persisted Custom Job and Batch Prediction requests. The production adapters list by exact display name plus operation label, validate the complete relevant resource shape, reuse exactly one match, reject multiple or mismatched matches, and refuse a second create after an ambiguous submit returns zero matches. Training adapter RED reported `4 failed, 7 deselected in 36.55s`; GREEN reported `4 passed, 7 deselected in 20.48s`. Batch adapter RED reported `4 failed, 46 deselected in 30.20s`; GREEN reported `4 passed, 46 deselected in 18.12s`. The then-amended adapter files reported `61 passed in 20.90s`.
- Root 3, lifecycle safety: the strict two-case RED mutated real local alias/current-pointer state for `PromotionIndeterminate` and injected a `RELEASED` run-manifest write failure; it reported `2 failed, 16 deselected in 30.18s`, with all three possibly/live versions incorrectly marked `abandoned`. The narrow `run_latest` gate now abandons only definitively non-live candidates, preserves lifecycle labels for indeterminate or authoritative-release paths, and surfaces `indeterminate` or `evidence_warning`/`release_status` evidence. GREEN reported `2 passed, 16 deselected in 18.88s`; the broader abandonment-preservation selection reported `6 passed, 12 deselected in 19.77s`.
- Root 4, immutable manifest handoff: strict RED restaged the discovery URI between selection and a pre-commit training retry and reported `1 failed, 18 deselected in 29.55s` because the worker consumed the mutable source URI. The orchestrator now copies the exact-generation-read bytes to `runs/{run_id}/inputs/selected_source_manifest.json` and passes only that URI. GREEN reported `1 passed, 18 deselected in 18.51s`; happy-path/restage preservation reported `3 passed, 16 deselected in 19.44s`.
- Root 5, Resolution-A preflight boundary: four deployment/source/discovery CLI cases plus the first post-discovery evidence write produced strict RED `5 failed, 19 deselected in 29.84s`. Preflight failures now return/log nested structured errors with `preflight: true`, exit nonzero, and create no formal run identity or artifacts. `_RunState` is initialized immediately after successful discovery derives exact run identity, so the first immutable-manifest or snapshot-evidence failure writes `error.json` plus terminal `run_manifest.json`. Final GREEN reported `5 passed, 19 deselected in 17.91s`.
- Retry-fake audit: Task 18's transient training fake now fails before commit via `commit_before_transient=False`, and the Batch fake raises before creating a job. Production-adapter tests are the only commit-then-raise reconciliation coverage. The combined Roots 3-5 selection reported `9 passed, 15 deselected in 19.59s`.
- Focused Task 18 verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_run_latest.py -q -p no:cacheprovider` -> `24 passed in 21.76s`.
- Amended-file verification: Task 18, promotion, training-job, and Batch Prediction tests -> `142 passed in 27.13s`. This gate initially exposed four existing same-month Task 17 pointer/reconciliation tests that lacked the now-required explicit revision authorization; after adding `revision_id="corrected-input"` only to those intended revision scenarios, their narrow selection reported `4 passed, 53 deselected in 17.02s`.
- Related Tasks 13-18 verification: Task 18, training job, predictor server, registry, Batch Prediction, and promotion tests -> `195 passed in 28.57s`.
- Fresh full repository verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider` -> `734 passed, 1 skipped, 24 subtests passed in 55.87s`.
- Static/dependency gates: all eight amended Python files parse by AST and compile with redirected bytecode; all four production modules import successfully; `.venv/bin/python -m pip check` reports `No broken requirements found.`; `git diff --check` exits `0`. The sole line over 88 characters is unchanged pre-existing validation text in `vertex/training_job.py:278`.
- Frozen authority remains exact: design SHA-256 `71a5f93b19ee612560c31ae0f884dd762414471f9f720ad2dad6c1a95c55158a`, normalized plan SHA-256 `f80ea13e14d7dbda5f5f42ee50d9d45ede4174dbe61e269a8bad88489716628a`, and fixed-partition SHA-256 `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Scope/no-cloud confirmation: all tests used `LocalArtifactStore`, fake registry/alias boundaries, or fake low-level Vertex SDK/service clients. No network, authentication, real GCP/GCS/Vertex/Registry/Batch/alias/lease/release-pointer operation, image build, smoke run, or Task 19 work occurred. Preserved user-owned `AGENTS.md`, `CLAUDE.md`, `.claude/`, and `.superpowers/` remain outside the implementation commit.
- Final exact-worktree staged GitNexus gate reported CRITICAL aggregate risk across exactly `9` expected staged files, `67` mapped changed symbols, and `24` affected flows. Context review confirmed the executable surface is the intended `run_latest`, lease-protected `promote_and_publish`, persisted training submit, and Vertex Batch adapter boundaries; GitNexus also broadly attributed unchanged neighbors inside the large amended files. The warning was reported before commit, and the `142` amended-file, `195` related, and `734` full-suite gates directly cover the affected execution surface.
- Planned fix commit subject: `fix: harden FEWSNET release orchestration`.

### Task 18 Final Re-review Closure Evidence

- Re-review baseline at `4964da1`: full Task 18 plus promotion tests reported
  `81 passed in 23.79s`; preserved user-owned `AGENTS.md`, `CLAUDE.md`,
  `.claude/`, and `.superpowers/` remained outside implementation scope.
- Root A strict RED: the three run-manifest ambiguity probes reported
  `3 failed, 24 deselected in 30.65s`. The exact commit-then-raise regression
  escaped with `GenerationConflict: expected 0, current 1`; mismatch and
  unreadable probes proved no generation-pinned readback occurred.
- Root A GREEN: the same selection reported
  `3 passed, 24 deselected in 18.69s`. `_RunState._write` retains canonical
  bytes, reads the current exact generation after an ambiguous exception,
  advances its generation fence only when the generation advanced and bytes
  are identical, and re-raises the original exception so the top-level handler
  writes terminal `error.json` and `run_manifest.json`. Mismatched or
  unreadable state remains unreconciled.
- Root B strict RED: the real `promote_and_publish` path with an injected
  `ServiceUnavailable` during alias movement reported
  `1 failed, 27 deselected in 30.87s`; the required `RELEASED` result was
  `FAILED` because the transient root was wrapped in non-retryable
  `PromotionError`.
- Root B GREEN: the same selection reported
  `1 passed, 27 deselected in 19.21s`. Promotion now re-raises an approved
  transient root only after verifying complete alias rollback, authoritative
  month-pointer rollback, live lease ownership, and exact unchanged current
  pointer generation and bytes. Rollback failure, lost lease, pointer
  uncertainty, validation failures, and `PromotionIndeterminate` remain
  non-retryable.
- Combined new regressions: `4 passed, 81 deselected in 18.73s`.
- Full Task 18 plus promotion files: `85 passed in 22.99s`.
- Amended Task 18/training/Batch/promotion set: `146 passed in 27.15s`.
- Related Tasks 13-18 set: `199 passed in 28.74s`.
- Fresh full repository suite: `738 passed, 1 skipped, 24 subtests passed in
  56.74s`.
- Static/dependency gates: all three changed Python files passed AST parsing
  and redirected compilation; both production modules imported; `.venv/bin/python
  -m pip check` reported `No broken requirements found.`; `git diff --check`
  passed.
- Frozen authority remains exact: design SHA-256
  `71a5f93b19ee612560c31ae0f884dd762414471f9f720ad2dad6c1a95c55158a`,
  plan SHA-256
  `f80ea13e14d7dbda5f5f42ee50d9d45ede4174dbe61e269a8bad88489716628a`,
  and fixed partition SHA-256
  `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Exact-worktree staged GitNexus reported LOW risk across exactly four staged
  files, three mapped `PROGRESS.md` section symbols, and zero affected
  processes. The index under-attributed the two production files and focused
  test; the `85`, `146`, `199`, and `738` runtime gates plus static/import
  checks cover their executable surface. Staged path and whitespace checks
  confirmed only the reviewed files plus this ledger are staged.
- Scope/no-cloud confirmation: all verification used local stores and fake
  training, registry, Batch, alias, and SDK/service boundaries. No network,
  authentication, real GCP/GCS/Vertex/Registry/Batch/alias/lease/pointer
  operation, Task 19 work, image build, or smoke run occurred.
- Planned commit subject: `fix: close Task 18 terminal evidence gaps`.
- Next action after this commit: request independent Task 18 re-review; do not
  start Task 19 until that gate is clean.

### Task 18 Third Narrow Re-review Authority Synchronization

- Review baseline: `45b8db1f59ac5707ab9d296648188f8aaad54524`
  (`fix: close Task 18 terminal evidence gaps`). The independent re-review is
  `0 Critical, 2 Important, 0 Minor`.
- Formal-run contract resolution: discovery already establishes `run_id` and
  `suite_version`, so mismatched or unreadable ambiguous `run_manifest.json`
  readback must never adopt or overwrite the unknown generation and must never
  route through preflight handling. `error.json` remains required; terminal
  manifest persistence is attempted but not falsely claimed. When it cannot be
  proven, the returned result is formal-run `FAILED` with `preflight: false`,
  `evidence_indeterminate: true`, preserved run/suite identity, the original
  failure, and an explicit terminal-manifest evidence warning/error.
- Initial-release contract resolution: missing optional current, feature-month,
  and promotion-lease objects are generation zero whether the local boundary
  raises `FileNotFoundError` or production GCS raises
  `google.api_core.exceptions.NotFound`. Other storage failures remain hard
  errors.
- Pre-authorized exact-worktree impacts remain: `run_latest` LOW, CLI `main`
  LOW, `_read_current_pointer` LOW, and `_capture_optional` HIGH. The HIGH
  `_capture_optional` warning is accepted for only the missing-exception-shape
  fix. `GCSArtifactStore.get_ref` is HIGH and remains explicitly out of scope.
  Any other existing symbol requires fresh upstream impact before editing.
- Authority synchronization changed only the approved design, Task 18 plan,
  this tracked ledger, and the untracked Task 18 handoff/review/report ledgers.
  No production or test file was edited, and no network, authentication, real
  GCP/GCS/Vertex/Registry/Batch/alias/lease/pointer operation or Task 19 work
  occurred.
- Synchronized authority hashes: design
  `44ef7a355ff16fc953b663d1770312da2200ff040e9129b9e9f203082aae346a`;
  plan `981c6508f6fd182a3deca2e4186a19db4a36caa65bf6616f27232466a4fcbf3e`;
  fixed partition
  `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Next action: commit the tracked authority synchronization separately as
  `docs: resolve Task 18 indeterminate evidence contract`, then write and run
  the exact full-path RED regressions before any production edit.

### Task 18 Third Narrow Re-review Fix Evidence

- Strict formal-evidence RED:
  `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_run_latest.py -q -p no:cacheprovider -k 'formal_indeterminate_failure'`
  -> `4 failed, 30 deselected in 22.87s`. Both full-run cases escaped from
  `state.fail(exc)` with `GenerationConflict: expected 0, current 1`; both CLI
  cases were consequently misclassified as `preflight: true`.
- Strict initial-release RED:
  `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/fewsnet_partitioned_rf/test_run_latest.py tests/fewsnet_partitioned_rf/test_promotion.py -q -p no:cacheprovider -k 'gcs_not_found'`
  -> `6 failed, 89 deselected in 22.86s`. Production-style GCS `NotFound`
  escaped from `_read_current_pointer` and `_capture_optional` instead of
  representing absent optional state as generation zero.
- Minimal fix: `run_latest` guards terminal `state.fail(exc)` separately. If
  the terminal manifest cannot be proven, it returns formal-run `FAILED` with
  `preflight: false`, `evidence_indeterminate: true`, preserved run/suite
  identity and original `error`, explicit `terminal_manifest_error`, and no
  run-manifest reference. The unknown generation remains untouched and the
  CLI exits nonzero. `_read_current_pointer` and `_capture_optional` now catch
  only `(FileNotFoundError, google.api_core.exceptions.NotFound)` as absence;
  `GCSArtifactStore.get_ref` remains unchanged.
- Exact GREEN reruns: formal evidence `4 passed, 30 deselected in 12.74s`;
  GCS missing-object behavior `6 passed, 89 deselected in 13.00s`.
- Broader runtime gates: full Task 18 plus promotion `95 passed in 24.66s`;
  amended Task 18/training/Batch/promotion `156 passed in 27.81s`; related
  Tasks 13-18 `209 passed in 29.87s`; full repository
  `748 passed, 1 skipped, 24 subtests passed in 58.16s`.
- Static/dependency gates: all four changed Python files parse by AST and
  compile in memory; both production modules import; `pip check` reports
  `No broken requirements found.`; `git diff --check` passes.
- Authority hashes remain exact: design
  `44ef7a355ff16fc953b663d1770312da2200ff040e9129b9e9f203082aae346a`,
  normalized plan
  `981c6508f6fd182a3deca2e4186a19db4a36caa65bf6616f27232466a4fcbf3e`,
  and fixed partition
  `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Fresh exact-worktree upstream impact is LOW for `run_latest` (one direct,
  four total), CLI `main` (one direct, three total), `_read_current_pointer`
  (one direct, three total), and `_capture_optional` (two direct, 24 total).
  The two direct `_capture_optional` consumers are `acquire_promotion_lease`
  and `promote_and_publish`; all required runtime surfaces are covered above.
- GitNexus recovered from the interrupted incremental `file_fts` refresh by
  forcing a full rebuild: `4,373` nodes, `9,672` edges, `190` clusters, and
  `272` flows. Exact-worktree staged `detect_changes(scope="staged")` reports
  MEDIUM risk across exactly five intended tracked files, 23 mapped symbols,
  and three internal `run_latest` flows (`Load_schema`, `_canonical_json`, and
  `_timestamp`). Context confirms `main` is the sole direct production caller;
  cached path and whitespace checks are clean. Neighboring mapped test symbols
  outside the added cases are line-shift attribution inside the two amended
  focused test files.
- Scope/no-cloud confirmation: verification used local stores and fake
  training, registry, Batch, alias, and SDK/service boundaries only. No
  network, authentication, real GCP/GCS/Vertex/Registry/Batch/alias/lease/
  pointer operation, Task 19 work, image build, or smoke run occurred.
  Preserved user-owned `AGENTS.md`, `CLAUDE.md`, `.claude/`, and
  `.superpowers/` remain outside the tracked implementation commit.
- Planned commit subject: `fix: preserve Task 18 formal failure evidence`.
  Independent Task 18 re-review remains mandatory before Task 19.

---

## Prior Execution Ledger Preserved from Base Commit

The completed prediction-population-and-uncertainty ledger below is retained unchanged from `e6afd2cebde02e14501dca52e959e395c54c30b7`.

# Prediction Population and Uncertainty Progress

## Authority

- Approved design: `docs/superpowers/specs/2026-07-15-prediction-population-uncertainty-design.md`
- Approved implementation plan: `docs/superpowers/plans/2026-07-15-prediction-population-uncertainty.md`
- Plan commit: `b553890`
- Active branch: `features/prediction-population-uncertainty`
- Active worktree: `.worktrees/prediction-population-uncertainty`

`PROGRESS.md` is an execution ledger only. It does not change the approved scope.

## Task Status

- Task 1 — streaming population snapshot component: complete; review clean through `1445b30`
- Task 2 — local/cloud assembly population fields: complete; review clean through `a08c01b`
- Task 3 — core qualitative uncertainty: complete; review clean through `04ee496`
- Task 4 — Vertex/cloud prediction contract: complete; review clean through `d44c9a0`
- Task 5 — regression, docs, and immutable-run preparation: local and
  deterministic verification complete; review clean through `99b7681`; final
  fix-wave review clean through `55273f6`; live
  GCP run gated by recorded external prerequisites

## Verification Evidence

- Baseline: `231 passed, 1 skipped in 5.27s`.
- Command: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_build_monthly_ipcch_base_input.py tests/test_operational_launch_inference.py tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/cloud -q -p no:cacheprovider`
- Task 1 RED: `tests/test_population_output.py` failed during collection with `ModuleNotFoundError: No module named 'model_pipeline.ipcch_launch_runtime.population'`.
- Task 1 focused GREEN: `6 passed in 0.26s`.
- Task 1 regression GREEN: `237 passed, 1 skipped in 3.63s`.
- Task 1 command: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_population_output.py tests/test_build_monthly_ipcch_base_input.py tests/test_operational_launch_inference.py tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/cloud -q -p no:cacheprovider`
- Task 1 task review: approved with no Critical, Major, or Minor findings after the ledger-only follow-up commit `1445b30`.
- Task 2 RED: focused assembly tests failed with 5 expected failures and 13 passes: missing `population_estimate`, missing `population_selection`, and absent local/cloud population hard gates.
- Task 2 focused GREEN: `18 passed in 0.47s`.
- Task 2 regression GREEN: `239 passed, 1 skipped in 3.72s`.
- Task 2 focused command: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_build_monthly_ipcch_base_input.py tests/cloud/test_monthly_assembly_wrapper.py -q -p no:cacheprovider`.
- Task 2 regression command: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_population_output.py tests/test_build_monthly_ipcch_base_input.py tests/test_operational_launch_inference.py tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/cloud -q -p no:cacheprovider`.
- Task 2 task review: approved with no Critical or Important findings. Minor: direct failure tests do not separately cover invalid/negative population estimates, future reference periods, and inconsistent imputation methods in `base_input_validation`; retain for final whole-branch triage.
- Task 3 RED: `tests/test_prediction_uncertainty.py` failed during collection with `ModuleNotFoundError: No module named 'model_pipeline.ipcch_launch_runtime.uncertainty'`.
- Task 3 RED command: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_prediction_uncertainty.py -q -p no:cacheprovider`.
- Task 3 focused GREEN: `27 passed in 0.76s`.
- Task 3 focused command: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_prediction_uncertainty.py tests/test_operational_launch_inference.py tests/test_operational_launch_cli.py -q -p no:cacheprovider`.
- Task 3 regression GREEN: `246 passed, 1 skipped in 3.80s`.
- Task 3 regression command: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_population_output.py tests/test_build_monthly_ipcch_base_input.py tests/test_prediction_uncertainty.py tests/test_operational_launch_inference.py tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/cloud -q -p no:cacheprovider`.
- Task 3 self-review: uncertainty uses resolved per-target thresholds with fixed phase tie order; population fields are validated and propagated unchanged; existing score and prediction assertions remain unchanged; no Spec Kit sources, model packages, weights, or Outcome artifacts changed.
- Task 3 fix-review RED: the operational threshold-resolver test failed because `OperationalLaunchError` was not raised, and the malformed-threshold test failed in three cases with raw `TypeError`, `ValueError`, and `OverflowError`.
- Task 3 fix-review focused GREEN: `31 passed in 1.02s`; targeted checks separately reported `1 passed` and `3 passed`.
- Task 3 fix-review regression GREEN: `250 passed, 1 skipped in 4.44s`.
- Task 3 fix-review result: removed the operational `0.2` fallback so missing model metadata thresholds fail explicitly, and normalized malformed uncertainty thresholds to `UncertaintyError`.
- Task 3 task re-review: approved with no remaining Critical, Important, or Minor findings; reported focused and regression commands are preserved in `.superpowers/sdd/task-3-report.md`.
- Task 4 RED: focused Vertex/report contracts failed with `18 failed, 36 passed`; expected failures showed unsupported `thresholds_by_scope`, absent local run-summary threshold enforcement, and absent enriched report/validation behavior.
- Task 4 RED command: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py tests/cloud/test_report_contracts.py -q -p no:cacheprovider`.
- Task 4 focused GREEN: `54 passed in 1.06s`.
- Task 4 focused command: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/cloud/test_vertex_ai_custom_job_contract.py tests/cloud/test_report_contracts.py -q -p no:cacheprovider`.
- Task 4 first broad regression exposed the downstream release call-contract dependency: `18 failed, 238 passed, 1 skipped`; release preflight had not passed `inference_report.resolved_thresholds_by_scope` into the now-mandatory prediction validator.
- Task 4 downstream consumer regression after the narrow adaptation: `47 passed in 1.43s` for orchestrator, quickstart fake-cloud, and release tests.
- Task 4 final regression GREEN: `256 passed, 1 skipped in 4.70s`.
- Task 4 regression command: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_population_output.py tests/test_build_monthly_ipcch_base_input.py tests/test_prediction_uncertainty.py tests/test_operational_launch_inference.py tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/cloud -q -p no:cacheprovider`.
- Task 4 self-review: production thresholds come only from the passed local `run_summary.json`; synthetic predictions use the explicit test-only `0.2` mapping through `calculate_qualitative_uncertainty`; population columns match the shared base input across scopes; release revalidation consumes recorded resolved thresholds; existing release/output artifacts were not edited.
- Task 4 task review: approved with no Critical, Important, or Minor findings; reviewer focused verification reported `6 passed, 56 deselected`.
- Task 5 smoke-validator RED: `test_live_gcp_smoke_release_validator_rejects_legacy_prediction_schema` failed with `Failed: DID NOT RAISE <class 'AssertionError'>`, proving the validator did not inspect prediction CSV contents.
- Task 5 smoke-validator GREEN: `4 passed, 1 skipped in 0.57s` for `tests/cloud/test_gcp_smoke_monthly_e2e.py`.
- Task 5 deterministic regression GREEN: `257 passed, 1 skipped in 4.59s`.
- Task 5 deterministic command: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_population_output.py tests/test_prediction_uncertainty.py tests/test_build_monthly_ipcch_base_input.py tests/test_operational_launch_inference.py tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/cloud -q -p no:cacheprovider`.
- Task 5 temporary assembly first reproduced the isolated-worktree input blocker: `FAIL: Missing historical panel: Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv`.
- Task 5 temporary assembly then used the primary checkout's immutable inputs read-only and wrote only under `/tmp/ipcch-pop-uncertainty-202604`: `6227` rows, `151` columns, and `39` unmatched source joins.
- Task 5 temporary inference wrote three `6227`-row prediction CSVs plus `run_summary.json` under `/tmp`; all three contain the seven enriched fields, non-null population, allowed uncertainty labels, and `qualitative_threshold_margin_v1`.
- Task 5 initial exact-comparison attempt exposed a runtime mismatch: Windows XGBoost `3.0.0` loaded each saved vector `base_score` as `0.5`, while all `12` immutable model JSONs record version `[3, 2, 0]`. This explained the score deltas without input, code, or model drift.
- Task 5 compatibility resolution used the existing offline runtime `/home/swl007007/.venvs/ipcch-xgb/bin/python` with Python `3.12.3`, XGBoost `3.2.0`, pandas `3.0.0`, and NumPy `2.4.2`. Inference was rerun only under `/tmp/ipcch-pop-uncertainty-202604/predictions`, with bytecode and caches confined to `/tmp`.
- Task 5 exact old/new comparison PASSED with `check_exact=True`: `0m=6227`, `6m=6227`, and `12m=6227` rows; exact output was `enhanced outputs preserve all existing model results`. Old/new base row order and all `128` model features are exact for every scope.
- Task 5 immutable old-output evidence: the 0m/6m/12m prediction SHA-256 values remained `2f751622a57ae90abde2873d8059d474ffa82e84f28f2eed915914e52000a0cd`, `7d1185019f28de564d69062448dd0c22e1027577cb22cb8acf90c6d888a3813c`, and `f151608ef3cabc5dc12ea834118ad907b3fdda5434c538f0ca29d021b01a4457` before and after the temporary run.
- Task 5 live cloud run: NOT ATTEMPTED. Read-only readiness found no ADC file, all eight `IPCCH_GCP_*` smoke variables unset (including both manifest URIs and the Cloud Run Job), and no digest-pinned runtime image built from the completed Task 5 commit. Exact service accounts, bucket, job, manifest objects, and image digest therefore could not be confirmed without crossing the mandatory gate.
- Task 5 task re-review: approved with no remaining Critical, Major, or Minor findings after the untracked report was reconciled to the final exact-comparison PASS state.

## Final Whole-Branch Review Fix Wave

- Findings fixed: shared semantic population hard gate for base and prediction
  paths (including release preflight), semantically complete smoke validation
  with released-base alignment and resolved thresholds, raw-margin uncertainty
  classification/tie selection, zero-count population method summaries, and
  digest-pinned image/implementation-commit runbook guidance.
- TDD RED evidence: shared population validator initially failed collection with
  `ImportError`; four matching-invalid prediction cases and three release
  preflight cases initially reported `DID NOT RAISE`; raw-margin/tie tests
  initially failed; the invalid released-base smoke case initially reported
  `DID NOT RAISE`.
- Focused GREEN command:
  `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_population_contract.py tests/test_population_output.py tests/test_prediction_uncertainty.py tests/test_build_monthly_ipcch_base_input.py tests/test_operational_launch_inference.py tests/test_operational_launch_cli.py tests/test_operational_launch_input_contract.py tests/cloud -q -p no:cacheprovider`
  -> `274 passed, 1 skipped in 4.99s`.
- Full deterministic suite:
  `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider`
  -> `297 passed, 1 skipped in 5.78s`.
- Final fresh full-suite verification:
  `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider`
  -> `297 passed, 1 skipped in 6.02s`.
- Final compatible-runtime rerun used `/home/swl007007/.venvs/ipcch-xgb/bin/python`
  (XGBoost `3.2.0`) and wrote only to `/tmp/ipcch-pop-uncertainty-final-202604`.
  The exact unchanged-column comparison passed with `check_exact=True` for
  `0m`, `6m`, and `12m` (`6227` rows each), printing
  `enhanced outputs preserve all existing model results`; all seven enriched
  fields and semantic smoke checks also passed.
- Live smoke remains gated and was not executed; no cloud mutation or run ID
  allocation was attempted. See `.superpowers/sdd/final-fix-report.md`.
- Fix-wave implementation commit: `caa5ad8` (`fix: close final population and
  uncertainty review findings`).
- Final whole-branch re-review: Ready to merge with no Critical or Important
  findings; remaining smoke scope-set hardening is Minor/non-blocking.

## Commits

- Task 1 implementation: `b93c08e feat: add population snapshot selector`.
- Task 1 ledger correction: `1445b30 docs: record task 1 commit in progress ledger`.
- Task 2 implementation: `ec03384 feat: add output population to monthly assembly`.
- Task 2 ledger update: `a08c01b docs: record task 2 commit in progress ledger`.
- Task 3 implementation: `d510bab feat: add qualitative prediction uncertainty`.
- Task 3 review fixes: `6b6875a fix: require operational model thresholds`.
- Task 3 review-fix ledger: `04ee496 docs: record task 3 review fixes`.
- Task 4 implementation: `b4f93d8 feat: validate enriched cloud predictions`.
- Task 4 ledger update: `d44c9a0 docs: record task 4 cloud contract`.
- Task 5 test/docs/blocker record: `24b3e05 docs: document enriched inference rerun`.
- Task 5 compatibility resolution: this ledger correction (`docs: record compatible-runtime comparison pass`).
- Task 5 compatibility-resolution commit: `99b7681 docs: record compatible-runtime comparison pass`.
- Final review fix-wave implementation: `caa5ad8 fix: close final population and uncertainty review findings`.
- Final review fix-wave ledger correction: `55273f6 docs: record final review fix commit`.
- Final verification ledger: `fab795a docs: record final verification evidence`.

## Blockers

- Live GCP smoke prerequisites are absent: ADC is missing; all required `IPCCH_GCP_*` variables and manifest URIs are unset; a digest-pinned image built from the completed implementation commit is not available; exact service accounts, bucket, Cloud Run Job, and manifests are unconfirmed. No cloud mutation or run ID allocation was attempted.

## Next Step

- Final whole-branch review and verification gate passed; remaining Minor smoke
  scope-set hardening is non-blocking.
- Only after the final implementation commit has a digest-pinned runtime image and all named GCP resources, ADC, and immutable manifest URIs are confirmed should a unique live smoke run ID be allocated.
