# CP5 local small-area smoke - actual accepted H2/H8/H14 package, fixture-only inputs (Executor, 2026-10-30)

Local only (locked `fewsnet-test-lock-20261022`); no cloud, EE, production store/current, Audit or retraining.

## Model (actual, not synthetic)

- envelope v2 accepted `R/scratch/h2h8h14-final/envelope/ipcch-combination-envelope-v2-accepted.json`
  sha256 03b938427391aa15d3786377151e922bfdb97cc161f312b72ebed9f596c89596;
- package `R/scratch/h2h8h14-final/package-build/out-r1/package` (manifest 18b91d454163ac9f..., feature order
  0ef1ffeca07542b3..., combination `ipcch-validity-h2h8h14-final-20261030`, the real q2..q5 XGBoost weights of
  H2/H8/H14), verified by `binding.verify_combination(..., mode="smoke", fixture_root=...)` (status accepted).

## Inputs (fixture-only)

The existing smoke fixture bundle (`tests/cloud/ipcch_smoke_fixture.build_bundle`, manifest `fixture: true`) in the
declared fixture root: 3 areas 11, 12 (country AAA) and 13 (country BBB) - adjacent unit-box geometries, i.e. a
contiguous neighbour subset across two fixture countries; synthetic histories for every family, delivered calendar,
fixture ACLED tables/export (declared interval + regions), fixture climate providers, fixture population and country
references, fixture acceptance records. The fixture feature order equals the actual package's 527-name order.

## Executable route

`cloud.ipcch.entrypoint_v2.run` with a validated deployment config (smoke/real roots and stores distinct; smoke
installed = the actual envelope/package + fixture bundle/root; smoke providers = the fixture factory):

| run | request | outcome |
|---|---|---|
| 1 `cp5-gen` | generation-only, M 2027-03 | succeeded; batch written; nothing published |
| 2 `cp5-inf` | inference-only from run 1's named batch, current | succeeded; smoke current generation 1 |
| 3 `cp5-comb` | generation + inference, current | succeeded; REPLACED run 2 (previous.pointer_generation 1 -> 2) |
| 4 `cp5-stale` | gen + inf against stale expected generation 1 | publication failed (no retry/rebase); current stays run 3; batch reported |
| 5 `cp5-genfail` | gen + inf, M 2027-04, climate provider unavailable for the new origin | generation failed at climate AFTER the saved ACLED refresh (report steps kept: acled refresh, coverage 2027-02); no new batch; current unchanged |
| 6 `cp5-inffail` | inference-only from run 4's batch with its H14 file corrupted | inference refused (H14 sha256 differs from its reference); no fallback batch; current unchanged |

Checks (`cp5-results.json`, all 12 true; the script exits non-zero if any is false): runs 1-3 succeeded; generation-only not published; inference-only used the
named batch (no new batch; every horizon's `source_input` is exactly run 1's batch id); combined used its own new
batch; combined replaced current (chained generation); smoke never activates; predictions complete (3 rows per
horizon = roster), finite, `mode=smoke`, feature period 2027-01, targets 2027-03 / 2027-09 / 2028-03;
failure_preserved (stale publication), generation_failure_preserved, inference_failure_preserved; zero_real_touch
(store spy - also wrapping the route's pinned reader: no URI under the real delivery root or real store; `ReadSpy`,
the binding tests' spy for several roots: no Python-level open/stat/lstat/listdir/scandir (builtins.open, io.open,
os.open, os.stat, os.lstat, os.listdir, os.scandir; 9,712 path calls observed) under `handoff-build/` incl.
`out-r5-accepted-v1`, `R/staging` or `cp3-real-integration`; calibrated in-run - a deliberate forbidden stat is
recorded, then discarded; the real pointer never exists). NOT intercepted, stated precisely: file access performed
inside native libraries that bypass these Python entry points (e.g. GDAL/pyogrio, xgboost's native model loader) -
the route hands those only fixture and model paths; split_equals_combined_except_source_input (gen-only -> inf-only and
gen+inf predictions are identical in every column except `source_input`, the batch reference).

## Defect found and fixed by the actual package (classification: breaks required behaviour)

The actual package's evidence covers its full 6,226-area training roster; the shared rule "evidence polygon IDs must
be roster IDs" refused it against the 3-area fixture roster (run 2 of cp5 run1 failed at publication). Fix
(`cloud/ipcch/delivery_member._declarations`): SMOKE only - after the evidence bytes are verified against the bound
package manifest, the rows are restricted to the declared fixture roster and declared as a subset (own sha256, URI
`envelope:<id>/<file>#smoke-roster-subset-of-sha256:<verified source digest>`); real mode is unchanged and still
refuses evidence outside its roster. Regression `test_smoke_restricts_full_roster_package_evidence_to_the_fixture_roster`
(fails on HEAD~ with EvidenceIntegrityError).
Supervisor repair on b3b5dd2: the FULL verified evidence file's own identity is validated (`_evidence_identity` with
the real origin/training cutoff) BEFORE the restriction, so a wrong identity is never hidden; when no fixture area has
evidence the family is declared `unavailable` with reason `no_eligible_area_history` (R31), never an empty
"available" file. Regressions `test_smoke_evidence_without_any_roster_area_is_unavailable_with_reason` and
`test_smoke_validates_the_full_evidence_identity_before_restricting_it` (both fail on b3b5dd2).

## Readback

```
cd "<OP>/.trellis/tasks/10-29-ipcch-validity-feature-inference/research/cp5"
PYTHONDONTWRITEBYTECODE=1 ~/.venvs/fewsnet-test-lock-20261022/bin/python cp5_smoke.py \
    /home/swl007007/projects/food-crisis-research/scratch/h2h8h14-final/cp5-smoke/<new run dir>
#  -> <run dir>/cp5-results.json and ./cp5-results.json; artifacts: <run dir>/{fixture-root,store,work,deployment.json}
```

Run history: run1 exposed the evidence/roster defect; run2 showed run 5 needed a month whose climate was not yet
saved (the provider was correctly never called); run3 all checks; run4 = run3 + the split/combined equality check;
run5/run6 = the Supervisor's repairs (ReadSpy + spied reader, explicit batch identity, failing exit; run6 adds the
spy calibration) - run6 is the committed `cp5-results.json`. Logs `cp5-run*.log` on disk (gitignored).
