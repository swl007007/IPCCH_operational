# FEWS fixed-map retrain — completion record (executor, 2026-10-22)

Final supervisor acceptance: 2026-10-22T08:43:45Z on reviewed HEAD 49ed4bb11ddccca817654bfff8e6576a469657f7 (`research/supervisor-final-acceptance.json`; AC1-AC9 accepted). Completed with the native Trellis lifecycle (task archived to `.trellis/tasks/archive/2026-10/10-21-fewsnet-fixed-map-retrain/`). No Trellis Audit was used.

## Outcome

- Production `monthly-staging/current.json#1792657760445077` -> `releases/fews-candidate-20261022a/release.json`
  (promoted 08:29Z from an absent pointer, generation 0; receipt 241e9c96; maintenance hold released 08:34Z).
- FEWS NET 0/6/12m scored with the all-history packages `full-202610-ff389b11af93-02caeb861750/{0,6,12}m`
  (fixed 17-partition map, 123 features, thresholds .48/.41/.45, model.joblib 69b90bf0/a0802145/62520a04),
  fitted on all eligible history of the v2 FEWS panel (labels through 2026-06; 273,353/264,005/254,291 rows).
- **No model evaluation, split, metric or threshold search was performed**; reports state `evaluation: none`.
- **FEWS confidence columns are old evidence**: the accepted October Stage3 proxies of the *previous* packages
  (2021-02..2024-10), copied unchanged from `oct-confidence-20261009b` as `frozen_output`. They are not error
  estimates of the new packages. Only current country outcomes (1[country probability >= 0.5]) are recomputed.
- IPCCH was not scored: tables, inputs, evidence and reports are inherited byte-for-byte from
  `oct-confidence-20261009b`, keeping that delivery's computation provenance.
- Runtime `runtime@sha256:487a23159b3bb151245530b6cfcef71820c8a716a189e5a2a3bbcc3074c97fae` (Cloud Build ce6e6cbf,
  clean source 0d60a4e); baseline b77cb29b; normal config `food-crisis-test/project.json` 8eddc1bc (work_dir =
  candidate operator state `food-crisis-test-fews-retrain-20261022/operator-state`); `fallback/october_2026/` =
  the candidate (manifest 54dd0f14, archive f3870914).

Acceptance evidence per criterion is annotated in `prd.md` (AC1-AC9) and `implement.md`.

## Rollback

Recorded in `research/p4/operation/` (and in the candidate operator state `operations/fews-retrain-20261022/`):
predecessor workflow source/env, job images/args, grants, previous normal config 93293916 (image 7e6133f3,
`food-crisis-test/operator-state`), absent previous pointer; previous fallback kept as
`fallback/october_2026.predecessor-fews-retrain-20261022/`. Steps (tested, including after a released hold):
`maintenance --operation-id fews-retrain-20261022 --execute hold --admit fews-candidate-20261022a`, then
`restore`, verify, then `release` (OPERATIONS.md "FEWS retrain release (2026-10-22)").

## Persistent cloud changes (each P4 mutation logged in `research/p4/cloud-operations.jsonl`)

Cloud Build API enabled in feisty-flames-511718-d4; image tag `runtime:fews-retrain-0d60a4e`; workflow SA grants
(run.developer on monthly-prepare, objectViewer on both buckets, objectCreator on `dispatch/`); workflow revisions
000002/000003 and both jobs on the new image; objects: baseline/models/environment uploads, inherited source copy,
candidate request/deliveries/candidate/receipt/release records, a refused hold-probe request
`requests/hold-probe-20261022/run_manifest.json`, and the noncurrent hold version (bucket versioning).

## Deviations and corrections (disclosed)

- S7: an early unit-test run (49 passed) fitted synthetic RF/SMOTE models; superseded by guarded recorder tests in
  which `RandomForestClassifier.fit`/`SMOTE.fit_resample` raise. No synthetic fit is part of the delivered evidence.
- First fit launch (pool of 3) failed before fitting (PartitionMap not picklable); the accepted fit ran
  sequentially from ff389b1; the pool fix (dbfc196) was not used for the delivered packages.
- `maintenance apply` stopped once on an unconditional bucket grant (gcloud needs `--condition=None` beside a
  conditional binding); fixed in 53d5f87 and resumed under the hold, which admitted only the candidate.
- gcloud sliced downloads stalled twice; retried single-stream (per-command env / SDK), unverified partials discarded.
- A GitNexus re-index rewrote one stats line in AGENTS.md/CLAUDE.md; reverted to the pre-index bytes.
- The release-check script first resolved a wrong task path; fixed (and its outcome check strengthened) before use.

## Pre-existing tracked changes (73 paths)

Per the supervisor's independent comparison plus this wrap-up: 68 paths are byte-identical to their pre-task
working bytes. Five differ intentionally, each staged as exact task hunks while the working copies keep their
pre-existing CRLF form: `PROGRESS.md` (task entries appended; original prefix intact),
`cloud_pipeline/QUICKSTART.md` and `cloud_pipeline/OPERATIONS.md` (operator behaviour corrections),
`cloud_pipeline/tests/cloud/test_prepare.py` (two GOSIF expectations retargeted to `gosif_sd`) and
`cloud_pipeline/tests/cloud/test_remote_sources.py` (FEWS nightlight sum).

## Test runs after activation

- Post-promotion full suite (08:40Z, exact-lock test env): **4 failed, 619 passed**. All four failures were in
  `tests/cloud/test_frozen_confidence.py` (`test_frozen_tables_are_copied_and_current_outcomes_recomputed[0/6/12]`,
  `test_frozen_outputs_reject_tampering_and_wrong_lineage`): `EvidenceIntegrityError: source declaration does not
  bind these raw evidence bytes`. Cause: the fixture read `fallback/october_2026/` as the accepted October source,
  but promotion made that directory the new release (by design) and kept the source as
  `fallback/october_2026.predecessor-fews-retrain-20261022/`.
- Fix (test-only, no runtime/data change, lineage checks unchanged): the fixture now resolves the accepted source by
  its manifest identity 265a0fb9 among `fallback/october_2026*`. Affected module plus the operator-release module
  (including the post-release re-hold/restore/release fixture): **32 passed**. Accepted suite count: 623 tests
  (619 unaffected + the 4 corrected).
