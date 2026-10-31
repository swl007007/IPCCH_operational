# CP4: C transition plan and bounded cloud packet (build, compatibility, cutover)

Executor: Claude session 6a490ae1-ee00-43f9-bdfc-c887c9816c09, model claude-opus-5-5[1m], Herdr pane w1A:p8.

Source: commit 115798f. Nothing in this document has been executed. No product edit is needed for C.

The live facts below come from the Supervisor's read-only inventory in `live-preflight/`. Nothing in that inventory was re-read here.

## 0. Disposition

- **A (temporary).** One new image for `oct-delivery`, `monthly-prepare` and the Workflow, under a maintenance hold. A is a cutover state only.
- **C (final).** Existing consumers keep working on the new image:
  - the legacy v1 route, including FEWS-only runs before and after v2 activation;
  - the operator CLI.

  To get there:
  1. The unchanged FEWS packages are re-accepted for the new digest. This uses real evidence from inside the new image and from a real cloud candidate.
  2. They are initialized into a NEW destination: new config, new `work_dir`, new `initialized.json`.
  3. The existing maintenance → candidate → verify → promote → release path then makes that destination the normal one. Old state is preserved.
- **B:** stays rejected.

## 1. Why each existing step is the supported path (exact sources)

| Need | Existing mechanism | Location |
|---|---|---|
| Runtime-bound acceptance for a new digest | new `operator-baseline/v1` with runtime + acceptance reports citing in-image evidence (precedent: FEWS retrain, 487a) | `.trellis/tasks/archive/2026-10/10-21-fewsnet-fixed-map-retrain/research/p4/build_candidate_baseline.py` |
| In-image replay evidence | Cloud Build step `six-slot-evidence` running `six_slot_check.py` inside the pushed image | same dir `cloudbuild.yaml`, `six_slot_check.py`; evidence inputs `S/image-evidence/evidence/` |
| New initialized destination | `pipeline.py init --config NEW --baseline DIR --execute` (create-only `baselines/`, `models/sha256:<new>/`, `environments/`) | `cloud_pipeline/pipeline.py` `initialize` |
| Cutover of shared jobs/workflow | `maintenance hold/gate/apply`, rollback `restore`, `release` | `pipeline.py:1244-1385`; OPERATIONS.md "FEWS retrain release (2026-10-22)" |
| Real compatibility replay | legacy `run --remote-update off --infer fewsnet --prepared-manifest … --inherit ipcch=… --publication candidate`, then `download --candidate`, `verify --python <exact-lock>` | precedent argv `cloud-operations.jsonl` lines 26-28 |
| Making the new destination normal | `promote`: pointer CAS, normal config `image_uri`/`work_dir` rewritten (backup kept), fallback swap (predecessor kept) | `pipeline.py:1496-1596` |

There is no invented re-acceptance:
- The acceptance reports are written by the precedent procedure. The only changes are the runtime digest and the evidence citation.
- The new baseline's `runtime.image_uri` is set by the builder script, which writes a NEW baseline directory. That directory is the input to `init`. No `initialized.json` is hand-edited.
- No guard is touched.

## 2. How the legacy IPCCH slots are satisfied without re-enabling legacy IPCCH publication

1. **Byte-identical packages.** `init` validates all six slots, so the new baseline carries the three legacy IPCCH packages (`launch_2026_04_production_safe/scope_{0,6,12}m`) byte-identical to `b77cb29b`.
2. **What their acceptance cites.** The in-image `six_slot_check` LOADS these packages and checks their member hashes. It runs NO IPCCH inference, and the acceptance evidence string says so; this is the exact precedent wording for 487a. No IPCCH score is claimed.
3. **Legacy IPCCH is never scored during C.**
   - The only admitted run is FEWS-only (`--infer fewsnet`). Its IPCCH member is inherited from the current release (§4 step 6) and never rescored.
   - The test `test_post_activation_fews_only_publishes_a_v2_member_inheriting_the_new_ipcch_member` asserts that no legacy IPCCH package is staged.
4. **No new enablement.** Legacy IPCCH publication is enabled TODAY: the current record has no activation, and `487a` serves the v1 route. C does not newly enable it. What it changes:
   - The new image carries the R37 guards (`delivery_job.require_not_activated` / `bind_current`, `pipeline.reject_new_contract_candidate`).
   - The first real v2 current publication in CP5 sets `activation`. From then on, every legacy request that scores IPCCH, alone or mixed, is rejected before work with the MIGRATION error, on both the delivery and the remote-update path.
   - Legacy FEWS-only runs keep working and inherit the v2 IPCCH member (tests `test_post_activation_*`).
5. **Residual window (stated, not hidden).** Between the C `release` and the CP5 activation, the v1 route behaves exactly as today. A legacy IPCCH request would still be accepted.
   - Mitigation: submit CP5 immediately after release. The operator submits no legacy IPCCH request.
   - Zero-window alternative, if required: keep the hold through CP5. That needs a fresh pre-chosen v2 run ID admitted by `hold --admit`. Today `submit --run-id` refuses an ID without local state (`submit_v2.py:247-248`), so this is a small product change (a fresh, validated, pre-chosen ID) requiring Supervisor release. It is NOT part of this packet.

## 3. Artifact paths (actual)

| Item | Path / identity |
|---|---|
| Source | commit `115798f` (export with `git archive`; no checkout or branch change) |
| Accepted envelope | `/home/swl007007/projects/food-crisis-research/scratch/h2h8h14-final/envelope/ipcch-combination-envelope-v2-accepted.json` sha `03b938427391aa15d3786377151e922bfdb97cc161f312b72ebed9f596c89596` |
| Package / handoff | `…/h2h8h14-final/package-build/out-r1/package`, `…/h2h8h14-final/handoff-build/out-r5-accepted-v1` |
| Staging root S | `/home/swl007007/projects/food-crisis-research/staging/fewsnet-fixed-map-retrain-20261022` |
| Predecessor baseline | `S/baseline/fews-retrain-20261022/baseline.json` sha `b77cb29bd648c428cce6503bd10a2834bc976290115dd98b331ff67c1dd66c8b` (82 files) |
| In-image evidence inputs | `S/image-evidence/evidence/` (`six_slot_check.py` 66fb4a7e…, `reference.json` a9d7be1e…, FEWS scope inputs) |
| Local proof on current source | `research/cp4/six-slot-local-current-source.{log,exit}`: child 0; all `matches_reference` true; FEWS prediction shas 0m 6a99ec8f…, 6m 84e553eb…, 12m aacb139b… |
| Normal operator config | `/home/swl007007/ipcch-operator/food-crisis-test/project.json` (a078f0e5…; top-level image 487a…, `work_dir` `…/food-crisis-test-fews-retrain-20261022/operator-state`) |
| Current release (live read) | pointer gen `1792657760445077` → `monthly-staging/releases/fews-candidate-20261022a/release.json#1792657760321065`. Legacy v1 record, origin 2026-10, scored fewsnet, inherited ipcch. manifest `deliveries/fews-candidate-20261022a/manifest.json#1792656899775363` (54dd0f14…), archive `…/webapp_model_bundle.tar.gz#1792656963111614` (f3870914…) |
| Reusable prepared snapshot | `gs://food-crisis-test-ipcch-data/prepared/fewsnet-retrain-20261022a/prepared_manifest.json#1792650679865065` (the precedent candidate reused it across an image change) |
| Precedent candidate download (comparison reference) | `S/candidate/download/fews-candidate-20261022a/` |
| Operator interpreters | operator `/home/swl007007/.venvs/ipcch-cloud-operator/bin/python`; exact-lock replay `/home/swl007007/.venvs/fewsnet-fit-lock-20261022/bin/python` |
| Real v2 selection | `/home/swl007007/ipcch-operator/food-crisis-test/v2-inputs/real-20261031/selections.json` (2d8da49d…) |

## 4. Bounded packet

Common settings:
- `G="gcloud --configuration=food-crisis-test"`; project `feisty-flames-511718-d4`; region `us-central1`.
- `T=.trellis/tasks/10-30-ipcch-real-e2e-integration/research/cp4`.
- Every cloud command is logged to `T/cloud-operations.jsonl`. Each entry records argv, scope, intended effect, start/finish times, exit code, the stdout file and the stderr tail, in the precedent `cloudop.py` format.
- Global stop rule: any non-zero exit, or any unexpected identity, stops the sequence at that step. The Executor reports to the Supervisor and does not retry silently.

### Step 1: stage the build context (local only) — DONE 2026-10-31T13:51Z

Result:
- `build/stage-cp4-context.{log,exit}`: child 0, 16 s, peak RSS 185 MB.
- Context `/home/swl007007/ipcch-operator/food-crisis-test/v2-build/cp4-115798f-20261031T135044Z/tmp.oV5ZoayeBG`: 326 files, 2,698,661,582 bytes.
- `build/context-files.sha256`: sha 788a0030….
- `INSTALL.json` 33d19119…, identical to CP3.
- The 19 frozen product hashes (`cp3/final/SHA256SUMS`) all equal the `git archive 115798f` export.
- `build/cloudbuild.yaml` f6a40db5….

Script: `T/build/stage_cp4.sh`.
1. Export source with `git archive 115798f cloud_pipeline`.
2. Regenerate the smoke fixture.
3. Run `deploy/build_context.sh` with the accepted inputs.
4. Copy `S/image-evidence/evidence` → `$ctx/evidence`. It is used only by the build step; the Dockerfile does not COPY it into the image.
5. Copy `T/build/cloudbuild.yaml` → `$ctx/`.
6. Write `context-files.sha256`.

Limits: about 2.7 GB disk on ext4 (604 GB free); no Docker.

Stop if:
- any `install stage` re-hash fails;
- the 19 committed product hashes differ from `115798f`.

### Step 2: Cloud Build (mutation: Cloud Build source upload, new image tag)

```
$G builds submit "$ctx" --config "$ctx/cloudbuild.yaml" --project feisty-flames-511718-d4 --region us-central1 \
  --substitutions=_IMAGE=us-central1-docker.pkg.dev/feisty-flames-511718-d4/monthly-delivery/runtime:ipcch-v2-115798f,_ENVELOPE_SHA256=03b938427391aa15d3786377151e922bfdb97cc161f312b72ebed9f596c89596 \
  --async --format='value(id,status,logUrl)'
```

`cloudbuild.yaml` steps:
1. `build`: `docker build --no-cache --build-arg IPCCH_ENVELOPE_SHA256=… -t $_IMAGE .`. The Dockerfile runs `cloud.ipcch.install verify --against /opt/ipcch/INSTALL.json`.
2. `push`.
3. `digest`.
4. `install-verify`: in the pushed image, run `python3 -m cloud.ipcch.install verify … --against /opt/ipcch/INSTALL.json`.
5. `six-slot-evidence`: in the pushed image, run `python3 /workspace/evidence/six_slot_check.py /workspace/evidence`.

Resources and limits:
- Default build machine (no machine-type override) and default disk.
- `timeout: 3600s`.
- No retries.
- Cost: under about US$1 in build minutes, plus about 2.5 GB Artifact Registry storage (about US$0.25/month).
- The existing `487a` image is untouched; the tag is new.

Read back:
- `builds describe` and `builds log` → `T/build/build-record.json` and `build.log`;
- the digest → `T/build/six-slot-runtime-evidence.json`, in the precedent shape.

Stop if:
- any step fails;
- any `matches_reference` is false;
- any FEWS prediction sha differs from the local current-source evidence;
- the IPCCH load check fails;
- the timeout is reached. Then cancel the build: `$G builds cancel ID`.

Rollback: none needed. The tag stays unused.

### Step 3: runtime-identity preflight (Supervisor-owned; NOT duplicated by the Executor)

The Supervisor runs the isolated job `ipcch-v2-runtime-preflight-20261031`. Packet: `live-preflight/runtime-probe-packet.md` and `runtime-probe-job.json`.
- Image `487a`, SA `monthly-runtime`.
- 1 CPU / 512 Mi, 300 s, 1 task, 0 retries.
- Reads only: the two known han-sandbox assets, GCS permissions and current metadata.
- No export and no data write.

Dependencies and the installation of the NEW image are covered in Cloud Build (step 2) on the pushed image:
- `install-verify`;
- `runtime-imports`: `ee`, `rasterio`, `google.cloud.storage`, `google.cloud.batch` and the v2 entrypoint, producers and smoke modules, with versions printed;
- `six-slot-evidence`.

Stop if the identity probe reports a missing permission. Report the least grant on the exact resource; no broad TokenCreator.

### Step 4: smoke bucket (the proposed bucket does not exist; 404)

The same step reads `gs://food-crisis-test-ipcch-data` location and IAM:

```
$G storage buckets describe gs://food-crisis-test-ipcch-data --format=json
$G storage buckets get-iam-policy gs://food-crisis-test-ipcch-data --format=json
```

Then create the smoke bucket and mirror ONLY the runtime SA's object role from the data bucket. The SA is `monthly-runtime@feisty-flames-511718-d4.iam.gserviceaccount.com`; the role is expected to be `roles/storage.objectAdmin`. Do not copy the data bucket's role set wholesale.

```
$G storage buckets create gs://food-crisis-test-ipcch-smoke --project feisty-flames-511718-d4 --location <data-bucket-location> \
  --uniform-bucket-level-access --public-access-prevention
$G storage buckets add-iam-policy-binding gs://food-crisis-test-ipcch-smoke \
  --member serviceAccount:monthly-runtime@feisty-flames-511718-d4.iam.gserviceaccount.com --role <mirrored object role>
```

The bucket is not nested with the real roots. It is used only for smoke roots, stores and inputs, as in the committed deployment JSON, so no config change is needed.

Rollback: delete the empty bucket.

Smoke read/write under the runtime SA is first exercised by the smoke run in step 7. That smoke run fails closed before any real-root effect.

### Step 5: new baseline and new destination (local + create-only uploads)

1. **Build the new baseline.** `T/build_runtime_baseline.py OUT=S/baseline/ipcch-v2-runtime-20261031` is adapted from the precedent, with fewer changes:
   - every file of `b77cb29b` is copied byte-identically (82 files);
   - `runtime.image_uri` and each model's `environment` / `acceptance.runtime` become the new digest;
   - the lock `2f0a7251…` is unchanged;
   - the evidence string cites `T/build/six-slot-runtime-evidence.json` (sha), the build ID and source commit `115798f`;
   - IPCCH: "loaded only, no IPCCH inference".

   It asserts:
   - `changed_or_new == ["baseline.json"]`;
   - packages, assets and diagnostics are identical;
   - the `six-slot-runtime-evidence.json` digest equals the image digest.
2. **New config.** `/home/swl007007/ipcch-operator/food-crisis-test-v2-runtime-20261031/project.json` is a copy of the normal config with:
   - `image_uri` = NEW digest;
   - `work_dir` = `/home/swl007007/ipcch-operator/food-crisis-test-v2-runtime-20261031/operator-state`;
   - `v2.image_uri` = NEW digest.

   The normal config and old state are not touched.
3. **Init.** `python pipeline.py init --config NEW_CFG --baseline S/baseline/ipcch-v2-runtime-20261031 --execute`.
   - Effect: create-only `gs://food-crisis-test-ipcch-data/baselines/<id>/…`, `models/sha256:<NEW>/…`, `environments/sha256:<NEW>.json`, and the local `initialized.json`.
   - Stop if validation fails. The new `work_dir` is discarded; nothing shared has changed.

### Step 6: cutover with the C compatibility candidate (shared mutation under the hold)

```
OP=ipcch-v2-runtime-20261031 ; RUN=fews-compat-v2rt-20261031a ; P=/home/swl007007/.venvs/ipcch-cloud-operator/bin/python
$P pipeline.py maintenance --config NEW_CFG --operation-id $OP --execute hold --admit $RUN
#   functional probe (precedent): create-only requests/hold-probe-v2rt-20261031/run_manifest.json -> Workflow must FAIL
#   at hold_admission before any claim/job (read the execution)
$P pipeline.py maintenance --config NEW_CFG --operation-id $OP --execute gate
$P pipeline.py maintenance --config NEW_CFG --operation-id $OP --execute apply
#   jobs oct-delivery + monthly-prepare -> NEW image with setup args (--v2-config /opt/ipcch/deployment.json);
#   Workflow env DELIVERY_IMAGE_URI=NEW, DELIVERY_V2_CONFIG=/opt/ipcch/deployment.json; resources unchanged (8CPU/32Gi,
#   2CPU/8Gi, 14400 s, 0 retries)
$P pipeline.py run --config NEW_CFG --month 2026-10 --cutoff 2026-10-21T23:59:59Z --deadline <now+4h> --run-id $RUN \
  --acled keep --wfp keep --remote-update off --infer fewsnet \
  --prepared-manifest gs://food-crisis-test-ipcch-data/prepared/fewsnet-retrain-20261022a/prepared_manifest.json#1792650679865065 \
  --inherit ipcch=fews-candidate-20261022a \
  --inherit-manifest gs://food-crisis-test-ipcch-data/deliveries/fews-candidate-20261022a/manifest.json#1792656899775363 \
  --inherit-archive gs://food-crisis-test-ipcch-data/deliveries/fews-candidate-20261022a/webapp_model_bundle.tar.gz#1792656963111614 \
  --publication candidate --execute
$P pipeline.py status   --config NEW_CFG --run-id $RUN
$P pipeline.py download --config NEW_CFG --run-id $RUN --candidate --output S2/candidate/download/$RUN --execute
$P pipeline.py verify   --config NEW_CFG --run-id $RUN --download S2/candidate/download/$RUN \
  --python /home/swl007007/.venvs/fewsnet-fit-lock-20261022/bin/python --check T/compat-checks.json --execute
```

Here `S2 = /home/swl007007/projects/food-crisis-research/staging/ipcch-v2-runtime-20261031`.

**Inheriting IPCCH.** The current release is a legacy v1 record, so `pub.members` gives the IPCCH member as this release's own delivery (inherited in the legacy record). The inherit source therefore names `fews-candidate-20261022a`'s manifest and archive at their live generations, with the same origin 2026-10.

**`T/compat-checks.json`** is produced locally before `verify`. It is a byte comparison of the new candidate download with `S/candidate/download/fews-candidate-20261022a/`:
- every FEWS prediction/scope CSV is identical;
- the inherited IPCCH members are identical;
- frozen diagnostics are identical;
- only run/runtime identity fields differ.

This is the real cloud compatibility evidence, and it is required to pass.

**Promote** (only if verify passed and compat-checks are all true):

```
$P stage_fallback (precedent T-archive/p4/stage_fallback.py adapted)  -> S2/fallback-staged   (manifest == receipt)
$P pipeline.py promote --config NEW_CFG --operation-id $OP --run-id $RUN --receipt <local receipt> \
  --normal-config /home/swl007007/ipcch-operator/food-crisis-test/project.json \
  --fallback-staged S2/fallback-staged --fallback-active "<repo>/cloud_pipeline/fallback/october_2026" --execute
$P pipeline.py maintenance --config NEW_CFG --operation-id $OP --execute release
```

Effects of promotion:
- **Pointer CAS** from gen `1792657760445077` to the new release `releases/fews-compat-v2rt-20261031a/release.json`. The predictions are byte-identical; IPCCH is inherited unchanged.
- **Normal config:** `image_uri` and `work_dir` → new. The `v2` section is kept; the backup is in `operations/$OP/`.
- **Fallback:** `fallback/october_2026` → `october_2026.predecessor-$OP`, and staged → `october_2026`. This is a repo working-tree change for the Supervisor to review and commit.
- **Release:** re-checks pointer, config, fallback and shared runtime, then deletes the hold.

Limits:
- one candidate delivery on the existing `oct-delivery` job, unchanged at 8 CPU / 32 Gi / 14400 s / 0 retries. The precedent took about 26 min (07:51→08:17);
- no prepare job (`--remote-update off`);
- no Batch;
- no EE;
- deadline 4 h (task bound).

Stop and rollback:
- **Before `apply`:** `maintenance restore` (workflow source/env and grants back), then `release`.
- **After `apply`, if run, verify or compat-checks fail:**
  - do not promote;
  - `maintenance … restore` puts the jobs back to `487a…` with their args, the predecessor workflow source/env and grants;
  - then `release`.

  Nothing on the pointer changed, and the candidate objects are retained (no deletion).
- **After `promote`, and only before the CP5 v2 activation:** `restore` performs a pointer CAS back to gen `1792657760445077`'s body, then config, fallback and shared settings. It stops without changes on any foreign drift.
- **After the CP5 v2 activation:** this operation's restore is NOT a v2 rollback (see `step6-packet.md`, rollback scope). Use containment by a new maintenance operation and forward recovery. Pointer reversal requires a specifically reviewed procedure.

### Step 7: CP5 (mandatory this round; DA1/DA2 still deferred)

These run after `release`, on the same image. The order follows `cp3-report.md` §6, items 2-5:
1. create-only uploads of the shared envelope, the environment manifest (`requirements.lock.txt` 2f0a7251…) and the country references to the `project.json` `v2` locations;
2. `entrypoint_v2 initialise --mode real` (and smoke with an acceptor), run in the new image as a temporary job under the runtime SA, in the same pattern as step 3;
3. `pipeline.py submit --config <normal project.json> --selections …/selections.json --execute`, then `status`;
4. readback of current.

The v2 record must:
- carry `activation`;
- carry the FEWS member literally equal to the step-6 release's FEWS member (`build_record` inherited copy, `inherited` generation).

Then confirm R37 with an offline/fail-closed check only. No legacy IPCCH request is sent. The detailed CP5 resource packet follows separately once steps 1-6 are read back.

## 5. Not done / not claimed

- No retraining.
- No resource increase.
- No DA1/DA2.
- No deletion of history.
- No push, merge or Audit.
- No guard patch.
- No hand-edited initialized state.

The steps are preauthorized by the user (2026-10-31) within the goal. The Supervisor's technical gate applies before each mutation class: steps 2, 3/4, 5, 6 and 7.
