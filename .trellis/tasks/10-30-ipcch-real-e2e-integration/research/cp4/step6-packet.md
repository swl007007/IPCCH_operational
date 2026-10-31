# CP4 step 6: exact packet (hold → gate → apply → FEWS-only C candidate → verify → promote → release)

Supervisor correction 2026-10-31: verify is guarded whole; the deadline and pointer are refreshed at submission. Steps 6a-6e are released together after the step-5 report; promotion waits for the actual compatibility results.

For Supervisor technical check. Nothing here is executed yet. Bounds:
- shared jobs unchanged at 8 CPU / 32 Gi (`oct-delivery`), 2 CPU / 8 Gi (`monthly-prepare`), 14400 s, 0 retries;
- candidate deadline now+4h;
- one candidate run;
- no automatic retry.

Every cloud/operator command goes through `cloudop.py`, which logs to `cloud-operations.jsonl`.

```
REPO="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational"; CP="$REPO/cloud_pipeline"
T="$REPO/.trellis/tasks/10-30-ipcch-real-e2e-integration/research/cp4"
P=/home/swl007007/.venvs/ipcch-cloud-operator/bin/python
NEW_CFG=/home/swl007007/ipcch-operator/food-crisis-test-v2-runtime-20261031/project.json      # sha 3be606ea
NORMAL_CFG=/home/swl007007/ipcch-operator/food-crisis-test/project.json                       # sha a078f0e5
OP=ipcch-v2-runtime-20261031 ; RUN=fews-compat-v2rt-20261031a
S2=/home/swl007007/projects/food-crisis-research/staging/ipcch-v2-runtime-20261031
REF=/home/swl007007/projects/food-crisis-research/staging/fewsnet-fixed-map-retrain-20261022/candidate/download/fews-candidate-20261022a
IMG=us-central1-docker.pkg.dev/feisty-flames-511718-d4/monthly-delivery/runtime@sha256:acc3e4673fa7c133eade6e5c74b998706788e0d1af0f92b217ae74ce7e14ccf6
```

## 6a. Hold (shared mutation: hold object only)

```
$P $CP/pipeline.py maintenance --config $NEW_CFG --operation-id $OP hold --admit $RUN            # preview
$P $CP/pipeline.py maintenance --config $NEW_CFG --operation-id $OP --execute hold --admit $RUN
```

Effects:
- records the predecessor shared runtime: jobs at `487a…`, their args, Workflow revision `000003-22c` source/env, and the grants;
- create-only `gs://food-crisis-test-ipcch-data/maintenance/hold.json`.

Stop if:
- `active_work` is non-empty;
- the hold is owned by another operation.

## 6b. Gate (Workflow source and grants; jobs unchanged)

```
$P $CP/pipeline.py maintenance --config $NEW_CFG --operation-id $OP gate                         # preview: exact commands
$P $CP/pipeline.py maintenance --config $NEW_CFG --operation-id $OP --execute gate
```

- Installs the committed `deploy/workflow.yaml` (115798f) with predecessor `DELIVERY_IMAGE_URI=487a…`, plus `DELIVERY_V2_CONFIG`.
- The gate itself verifies that the live source sha equals the file and that the job images are unchanged.

**Window.** Between gate and apply, the new Workflow passes `--v2-config` to the old 487a job. Any run reaching a job in that window would fail at argv parsing. Only `$RUN` is admitted, and it is submitted after apply.

**Functional hold probe (precedent):**
- create-only `gs://food-crisis-test-ipcch-requests/requests/hold-probe-v2rt-20261031/run_manifest.json`, body `{"run_id":"hold-probe-v2rt-20261031","purpose":"maintenance hold probe"}`;
- read the Workflow execution. It must be FAILED with "monthly admission is paused by maintenance ipcch-v2-runtime-20261031", with no `dispatch/hold-probe…/claim.json` and no job execution.

## 6c. Apply (shared jobs and Workflow → new image)

```
$P $CP/pipeline.py maintenance --config $NEW_CFG --operation-id $OP apply                        # preview: commands + active work
$P $CP/pipeline.py maintenance --config $NEW_CFG --operation-id $OP --execute apply
```

Effects:
- `oct-delivery` and `monthly-prepare` move to `$IMG`, with setup args including `--v2-config /opt/ipcch/deployment.json` and unchanged resources (the preview is inspected before execute);
- the Workflow env gets `DELIVERY_IMAGE_URI=$IMG` and `DELIVERY_V2_CONFIG=/opt/ipcch/deployment.json`;
- `operation.intended` is recorded.

Stop if:
- the preview shows any resource, timeout or retry change;
- active work is non-empty.

## 6d. FEWS-only C candidate (one delivery job execution; no prepare, no Batch, no EE)

```
# immediately before submission: a fresh live pointer read (the expected generation run binds), and the deadline
$G storage objects describe gs://food-crisis-test-ipcch-data/monthly-staging/current.json --format='value(generation)'   # must still be 1792657760445077; else stop and re-read the record
DEADLINE=$(date -u -d '+4 hours' +%Y-%m-%dT%H:%M:%SZ)   # computed at submission, recorded with the run argv
$P $CP/pipeline.py run --config $NEW_CFG --month 2026-10 --cutoff 2026-10-21T23:59:59Z --deadline $DEADLINE --run-id $RUN \
  --acled keep --wfp keep --remote-update off --infer fewsnet \
  --prepared-manifest gs://food-crisis-test-ipcch-data/prepared/fewsnet-retrain-20261022a/prepared_manifest.json#1792650679865065 \
  --inherit ipcch=fews-candidate-20261022a \
  --inherit-manifest gs://food-crisis-test-ipcch-data/deliveries/fews-candidate-20261022a/manifest.json#1792656899775363 \
  --inherit-archive gs://food-crisis-test-ipcch-data/deliveries/fews-candidate-20261022a/webapp_model_bundle.tar.gz#1792656963111614 \
  --publication candidate                                                                          # preview first
... same ... --execute
$P $CP/pipeline.py status --config $NEW_CFG --run-id $RUN      # bounded poll every ~3 min; precedent ~26 min
```

- `--month`, `--cutoff`, the snapshot and the inherit refs are identical to the precedent candidate, except that the inherit source is the CURRENT release's delivery. Current is a legacy v1 record, and its IPCCH member is that delivery.
- `expected_pointer_generation` is captured by `run` from the LIVE pointer at submission. The copied snapshot generation is only the expected value; a mismatch stops before submission.

Stop if:
- the job fails;
- the deadline passes;
- the status is anything other than candidate written.

There is no retry.

## 6e. Download, compatibility evidence, verify

```
$P $CP/pipeline.py download --config $NEW_CFG --run-id $RUN --candidate --output $S2/candidate/download/$RUN --execute
bash $T/../cp2/guarded.sh compat-check $T/step6 /home/swl007007/.venvs/fewsnet-test-lock-20261022/bin/python \
  $T/compat_check.py $S2/candidate/download/$RUN $REF $T/step6/compat-checks.json
bash $T/../cp2/guarded.sh verify-candidate $T/step6 $P $CP/pipeline.py verify --config $NEW_CFG --run-id $RUN \
  --download $S2/candidate/download/$RUN --python /home/swl007007/.venvs/fewsnet-fit-lock-20261022/bin/python \
  --check $T/step6/compat-checks.json --execute
```

`verify` launches the local relocated FEWS replay, so it runs whole inside `guarded.sh`. The pipeline process and its replay children share one unit: MemoryMax 4G, no swap, prlimit AS 3 GiB, 600 s, BLAS/OMP threads 1.
- Record the child exit and the full output: `step6/verify-candidate.{log,exit}`.
- The receipt upload, create-only to `candidates/$RUN/verification_receipt.json`, is in scope.
- Limits are not raised. If the guard stops the run, it is recorded INTERRUPTED and reported.

`compat_check` must exit 0:
- the reference is pinned to `54dd0f14…` / `f3870914…`;
- both downloads are manifest-consistent;
- `scopes/`, `inputs/`, `fewsnet/` and `ipcch/` are byte-identical;
- the three FEWS `polygon_predictions.csv` files are identical.

`verify` must return `passed` with `extra:compat-checks.json: true`. Its receipt goes create-only to `candidates/$RUN/verification_receipt.json`.

Stop if any of these fails. Then:
1. do NOT promote;
2. `maintenance … --execute restore` returns the jobs to `487a` with their args, the predecessor workflow source/env and the grants;
3. `release`.

## 6f. Stage fallback and promote (pointer CAS; normal config top-level only; fallback swap)

```
bash $T/../cp2/guarded.sh stage-fallback $T/step6 /home/swl007007/.venvs/fewsnet-test-lock-20261022/bin/python \
  $T/stage_fallback_cp4.py $S2/candidate/download/$RUN $S2/fallback-staged \
  $S2/candidate/download/$RUN.download.json <local receipt> $T/step6/compat-checks.json
$P $CP/pipeline.py promote --config $NEW_CFG --operation-id $OP --run-id $RUN --receipt <local receipt> \
  --normal-config $NORMAL_CFG --fallback-staged $S2/fallback-staged --fallback-active $CP/fallback/october_2026     # preview
... same ... --execute
```

`stage_fallback_cp4.py` has the precedent's code with only the README text changed. Promotion effects:
1. **Pointer CAS** `1792657760445077` → `releases/$RUN/release.json`. FEWS is byte-identical to before; IPCCH is inherited unchanged.
2. **Normal config:** ONLY the top-level `image_uri` and `work_dir` are rewritten to NEW_CFG's values (`pipeline.py:1537-1538`). The old `v2` section, which has no `v2.image_uri`, is preserved. The byte backup is kept in `operations/$OP/predecessor-normal-config.json`.
3. **Fallback:** `fallback/october_2026` → `october_2026.predecessor-$OP`, then staged → `october_2026`. These are repo working-tree changes for Supervisor review and commit.

Do not edit the normal config between promote and release. Release and restore classify any other content as foreign drift.

## 6g. Release

```
$P $CP/pipeline.py maintenance --config $NEW_CFG --operation-id $OP release                      # preview checks
$P $CP/pipeline.py maintenance --config $NEW_CFG --operation-id $OP --execute release
```

Release re-checks the shared runtime against the intended state:
- jobs at `$IMG`;
- pointer, config and fallback at the intended state.

It then deletes the hold at its generation.

**Old state preserved:**
- `/home/swl007007/ipcch-operator/food-crisis-test-fews-retrain-20261022/` (config 6515208d, `initialized.json` b0ec182e, tree 5f46ac65);
- baseline b77cb29b (tree 4cba2de9). The evidence is re-hashed after release.

## 6h. Normal-config v2 finish (after CP5's final current acceptance, not before; Supervisor seam)

1. Byte-back up the normal config.
2. Set `v2.image_uri = $IMG`. This is the only v2 change. NEW_CFG's reviewed `v2` section differs from the normal one only in `image_uri`.
3. Verify:
   - `pipeline.py submit --config $NORMAL_CFG --selections <real selections>` preview has no `image_uri_pending`;
   - `pipeline.py status --config $NORMAL_CFG --run-id <cp5 run>` works;
   - `load_initialized` for the normal config passes against the new work_dir, verified by a DIRECT call (`python -c "import pipeline as p; p.load_initialized(p.config(NORMAL_CFG))"`) or by `models select` preview. `maintenance status` does NOT invoke it.

Until then, CP5 uses `NEW_CFG`.

## Scope of this operation's rollback (Supervisor source review, 2026-10-31)

`maintenance restore`/`release` of `ipcch-v2-runtime-20261031` is a rollback ONLY until the CP5 v2 publication activates current. After that, and especially after the normal-config v2 finish, it is NOT a v2 rollback:
- `_inspect` classifies the later current pointer and config as foreign, so restore stops.
- Restore would put the jobs back on `487a`, which lacks the v2 guards.
- A hand CAS to the pre-activation pointer would remove activation, because the guards read only the current release.

There is no supported dedicated v2 current-rollback helper. The CP6 runbook documents instead:
- containment by a NEW maintenance operation, which snapshots the then-current guarded runtime and inspects active work;
- forward recovery with a new request.

All accepted retained writes are kept. Reversing the current pointer needs a specifically reviewed recovery procedure. No automatic rollback is advertised.
