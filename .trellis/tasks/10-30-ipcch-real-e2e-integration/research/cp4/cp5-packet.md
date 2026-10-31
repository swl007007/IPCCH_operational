# CP5 packet: in-image initialisation, shared objects, smoke and real v2 submission, readback

Executor session 6a490ae1 (claude-opus-5-5[1m]); 2026-10-31. Nothing here is executed except the read-only and offline items marked DONE.

**Releases:**
- **Initialisation (5a-5c)** may be released separately while the C candidate runs.
- **Submissions (5d-5f)** wait for the C `release`; promotion of the C candidate still waits for its evidence.
- **The normal-config v2 finish (5g)** comes after CP5 acceptance.

```
REPO="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational"; CP="$REPO/cloud_pipeline"
T="$REPO/.trellis/tasks/10-30-ipcch-real-e2e-integration/research/cp4"; G="gcloud --configuration=food-crisis-test"
P=/home/swl007007/.venvs/ipcch-cloud-operator/bin/python ; L=/home/swl007007/.venvs/fewsnet-test-lock-20261022/bin/python
NEW_CFG=/home/swl007007/ipcch-operator/food-crisis-test-v2-runtime-20261031/project.json        # 3be606ea; v2.image_uri = IMG
IMG=us-central1-docker.pkg.dev/feisty-flames-511718-d4/monthly-delivery/runtime@sha256:acc3e4673fa7c133eade6e5c74b998706788e0d1af0f92b217ae74ce7e14ccf6
SA=monthly-runtime@feisty-flames-511718-d4.iam.gserviceaccount.com
CTX=/home/swl007007/ipcch-operator/food-crisis-test/v2-build/cp4-115798f-20261031T135044Z/tmp.oV5ZoayeBG/ipcch   # = image /opt/ipcch (INSTALL.json 33d19119)
SH=/home/swl007007/ipcch-operator/food-crisis-test/v2-inputs/shared-20261031
SM=/home/swl007007/ipcch-operator/food-crisis-test/v2-inputs/smoke-20261031
RS=/home/swl007007/ipcch-operator/food-crisis-test/v2-inputs/real-20261031
NEW_WORK=/home/swl007007/ipcch-operator/food-crisis-test-v2-runtime-20261031/operator-state   # NEW_CFG work_dir (submit state: $NEW_WORK/runs-v2/<run>/state.json)
```

## Facts bound

| Item | Value |
|---|---|
| Installed deployment config | `/opt/ipcch/deployment.json`, identical to committed `deploy/ipcch_v2_deployment.food-crisis-test.json` (install verify) |
| Real roots | output `gs://food-crisis-test-ipcch-data` (namespace `monthly-staging`), store `gs://food-crisis-test-ipcch-data/ipcch-v2/real` |
| Smoke roots | output `gs://food-crisis-test-ipcch-smoke/v2` (namespace `monthly-smoke`), store `gs://food-crisis-test-ipcch-smoke/ipcch-v2/smoke` |
| Trusted prefixes | real `gs://food-crisis-test-ipcch-data/inputs/v2/`, smoke `gs://food-crisis-test-ipcch-smoke/inputs/` |
| Empty-root readback (DONE) | `cp5/inventory-pre-init-{real,smoke}.json`: 0 HEAD tables, 0 version objects on both store roots (14:29Z) |
| Inventory helper | `cp5/store_inventory.py`. Guarded fixture self-check `cp5/test_store_inventory.py`: 3 passed. It checks HEAD generation and sha, refuses content that differs from the HEAD sha, and refuses a HEAD that moved after listing |
| Readback helper | `cp5/readback_v2.py` (pre/post). It uses the product `read_current`, `members`, `verify_delivery` (incl. `verify_member`), `load_batch` and raw header equality. It also checks status `succeeded` with run/mode, the reservation equal to the release request and to the frozen submit state, batch run/mode, linked batch ids, feature order and count equal to the binding, the batch and member-provenance roster equal to the bound roster, linked M/O, and the expected M/O/features/roster (real: 2026-10/2026-08/527/6226). It records the targets, `retained_inputs` and the generation report. Guarded fake-store self-check `cp5/test_readback_v2.py`: 4 passed (positive, wrong M, forged frozen request, tampered delivery file) |
| Sizing evidence | `cp5/local-initialise-measure.FAILED-AS-3GiB-cap.*`: offline real `initialise_store` hit the local 3 GiB AS guard (ArrowMemoryError, RSS 2.6 GB). The local cap is unchanged |

**Shared-object sources (DONE, local, frozen):**

| Local file | sha256 | Create-only target (generation pinned at freeze by submit) |
|---|---|---|
| `$SH/ipcch-combination-envelope-v2-accepted.json` | `03b938427391aa15d3786377151e922bfdb97cc161f312b72ebed9f596c89596` (= installed envelope) | `gs://food-crisis-test-ipcch-data/inputs/v2/shared/ipcch-combination-envelope-v2-accepted.json` |
| `$SH/requirements.lock.txt` | `2f0a7251e0436d900ddb91d0a783421b205094ffdb26ba52ccbdfb7f9bb31e3d` | `gs://food-crisis-test-ipcch-data/inputs/v2/shared/requirements.lock.txt` |
| `$SH/country_reference_real.csv` | `0823e418f0fe361db00b701f5737033ee860159e9d21ca2f6167cfe2d54e2f0b` | `gs://food-crisis-test-ipcch-data/inputs/v2/reference/country_reference.csv` |
| `$SM/country_reference_smoke_fixture.csv` | `acbd3eace7a2c8bd8dd166a83b069e4195fadf7c320d67bf84da2fbe3a999ddc` | `gs://food-crisis-test-ipcch-smoke/inputs/reference/country_reference.csv` |

- **Lock (raw-lock environment object contract):** the file is the raw `requirements.lock.txt` from commit 115798f, byte-identical to the working tree and to the image lock (`2f0a7251`).
- **Real country reference:** the current IPCCH member's `country_population_reference.csv`, from the pinned current delivery download, which is byte-identical to `fallback/october_2026/shared/ipcch/`. It has the existing column contract and covers all 6,226 roster ISO3 (offline check against handoff `fixed/area_identity.csv`; 0 missing).
- **Smoke country reference:** the fixture `COUNTRY_REFERENCE` (AAA/BBB), never the real asset (R48).

**Selections (DONE):**
- **Real:** `$RS/selections.json` (2d8da49d). ACLED refresh uses `acled_regional_aggregate_f2f3.csv` (7bcb051f, 2016-12-31..2026-10-16, 14 regions); the 10 others are keep.
- **Smoke:** `$SM/selections.json` (137b263e). ACLED refresh uses the fixture export `acled_smoke_fixture_O202608.csv` (5274ff40, BOM; R44 window 2025-07-26..2026-09-04 for O=2026-08; regions R1/R2); the 10 others are keep. Operations are generation+inference, publication current (smoke namespace).
- **Offline `submit` previews with NEW_CFG (DONE):** `cp5/submit-preview-{real,smoke}.json` both pass. Each shows M=2026-10, image `acc3e467`, operations generation+inference, and publication current in its own namespace.
- **Smoke route at M=2026-10:** passes offline with the runtime smoke providers (`cp5/smoke-at-m202610.log`, guarded, child 0).

## 5a. Create-only shared uploads (write; no runtime effect)

```
$G storage cp $SH/ipcch-combination-envelope-v2-accepted.json gs://food-crisis-test-ipcch-data/inputs/v2/shared/ipcch-combination-envelope-v2-accepted.json --if-generation-match=0
$G storage cp $SH/requirements.lock.txt gs://food-crisis-test-ipcch-data/inputs/v2/shared/requirements.lock.txt --if-generation-match=0
$G storage cp $SH/country_reference_real.csv gs://food-crisis-test-ipcch-data/inputs/v2/reference/country_reference.csv --if-generation-match=0
$G storage cp $SM/country_reference_smoke_fixture.csv gs://food-crisis-test-ipcch-smoke/inputs/reference/country_reference.csv --if-generation-match=0
# readback: generation + streamed sha256 of each object equals the local sha
for u in <4 URIs>; do $G storage objects describe $u --format='value(generation,size)'; $G storage cat $u | sha256sum; done
```

Stop if an object already exists with other bytes (412). Report it; do not overwrite.

## 5b. Dedicated initialisation job (new isolated Cloud Run job; shared jobs untouched)

```
$G run jobs create ipcch-v2-init-20261031 --project feisty-flames-511718-d4 --region us-central1 --image $IMG \
  --service-account $SA --tasks 1 --max-retries 0 --task-timeout 3600 --cpu 4 --memory 16Gi --command python3 \
  --args=-m,cloud.ipcch.entrypoint_v2,initialise,--config,/opt/ipcch/deployment.json,--mode,real
$G run jobs execute ipcch-v2-init-20261031 --project feisty-flames-511718-d4 --region us-central1 --wait
# then smoke, one mode per call, explicit acceptor (fixture records only):
$G run jobs execute ipcch-v2-init-20261031 --project feisty-flames-511718-d4 --region us-central1 --wait \
  --args=-m,cloud.ipcch.entrypoint_v2,initialise,--config,/opt/ipcch/deployment.json,--mode,smoke,--acceptor,weilun.shi
```

**Identity and inputs:**
- runtime SA `monthly-runtime`; image `acc3e467`;
- the installed envelope, package and handoff (real), or the fixture bundle (smoke), from `/opt/ipcch`, re-verified by `initialise_store`;
- no EE, no current pointer, no request.

**Writes:**
- only under the mode's store root:
  - real: acceptance records of the handoff's finalized entries;
  - smoke: fixture acceptance records with the acceptor;
- the `initial.initialise` tables;
- the binding pairing, written last.

**Limits:**
- 4 CPU / 16 GiB, 3600 s task timeout, 1 task, 0 task retries;
- client-library RPC retries are separate and not claimed to be zero;
- compute: bounded at most 8 vCPU-hours and 32 GiB-hours across the two one-hour-capped executions, plus GCS and logging. No bill amount is claimed.

The existing `oct-delivery` job (8 CPU/32 Gi/14400 s/0 retries) and `monthly-prepare` are unchanged.

**Readback per mode:**
- execution `describe`: `succeededCount=1`, exit 0;
- the job log's JSON report (`gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="ipcch-v2-init-20261031"'`);
- `cp5/store_inventory.py` for the store root → `cp5/inventory-post-init-{real,smoke}.json`. The pairing table is present with one row naming the installed combination, package manifest and feature order.

**Stop rule:**
- **Stop if** the job fails, times out or OOMs, or the pairing is absent.
- **Partial state:** acceptance or table writes may precede the final pairing. Preserve them, record the inventory, and report.
- **Not allowed:** an automatic re-run, a resource increase, or any deletion.

**Retention:** the job definition and execution records of `ipcch-v2-init-20261031` (and the Supervisor's probe job) are kept as evidence. They are inactive and add no running compute. No deletion is needed for AC1-AC9; any cleanup would need a specific justification and gate.

## 5c. Post-init check (local, read-only)

- The inventory tables match the handoff manifest's file set, with real rows equal to the bundle.
- No HEAD lies outside its own root.
- Smoke and real roots are disjoint (R48).

## 5d. Smoke submission (after C release; normal admission, no hold)

```
$P $CP/../.trellis/$T/cp5/readback_v2.py pre smoke $T/cp5/pre-smoke.json          # expected generation "0"
$P $CP/pipeline.py submit --config $NEW_CFG --selections $SM/selections.json --execute     # run id ipcch-smoke-<uuid16>
$P $CP/pipeline.py status --config $NEW_CFG --run-id <smoke run>                           # bounded poll
bash $T/../cp2/guarded.sh readback-smoke $T/cp5 /usr/bin/env PYTHONPATH="$CP" GOOGLE_CLOUD_PROJECT=feisty-flames-511718-d4 $P $T/cp5/readback_v2.py post smoke <smoke run> $T/cp5/pre-smoke.json $CTX $T/cp5/post-smoke.json \
   $NEW_WORK/runs-v2/<smoke run>/state.json 2026-10 2026-08 527 3      # smoke pairing roster_size 3 (inventory-post-init-smoke.json)
```

- The route is request → Eventarc → Workflow `run_job` → `oct-delivery` with the `--v2-config` installed config → `entrypoint_v2` smoke mode.
- Smoke providers run with no EE/GPP/nightlight access.
- Smoke publishes only to `gs://food-crisis-test-ipcch-smoke/v2/monthly-smoke/current.json`.

Stop if the smoke run fails or the readback is false. Real is then not submitted.

## 5e. Real submission (after smoke success; freeze strictly before 2026-11-01T00:00:00Z)

```
date -u   # refuse to submit at/after 23:30Z (margin): M would become 2026-11 -> O 2026-09 -> non-empty demand -> han (DENIED)
$P $T/cp5/store_inventory.py gs://food-crisis-test-ipcch-data/ipcch-v2/real $T/cp5/inventory-pre-cp5-real.json
$P $T/cp5/readback_v2.py pre real $T/cp5/pre-real.json      # the C-promoted release (legacy v1 record), pinned generation
$P $CP/pipeline.py submit --config $NEW_CFG --selections $RS/selections.json --execute
$P $CP/pipeline.py status --config $NEW_CFG --run-id <real run>                            # bounded poll <= run deadline 4 h
```

- **Freeze:** `submit` freezes M from the actual UTC instant. The expected value is M=2026-10 (O=2026-08). M is never forged.
- **Stop if:**
  - the frozen M is not 2026-10;
  - the run status is failed or rejected;
  - the generation report shows non-empty climate/table demand. The run would then fail closed at han access, which is CONFIRMED DENIED. That is reported; nothing is retried or forced.
- **Resources:** the existing `oct-delivery` at 8 CPU/32 Gi/14400 s/0 retries. The run deadline is persisted (at most 4 h).

## 5f. Real readback (local, guarded: 4G / no swap / 3 GiB AS / 600 s)

```
bash $T/../cp2/guarded.sh readback-real $T/cp5 /usr/bin/env PYTHONPATH="$CP" GOOGLE_CLOUD_PROJECT=feisty-flames-511718-d4 $P $T/cp5/readback_v2.py post real <real run> $T/cp5/pre-real.json $CTX $T/cp5/post-real.json \
   $NEW_WORK/runs-v2/<real run>/state.json 2026-10 2026-08 527 6226
$P $T/cp5/store_inventory.py gs://food-crisis-test-ipcch-data/ipcch-v2/real $T/cp5/inventory-post-cp5-real.json
$G storage cat gs://food-crisis-test-ipcch-data/runs/<real run>/v2_run_status.json > $T/cp5/run-status-real.json
gcloud logging read (oct-delivery execution of <real run>) > $T/cp5/run-logs-real.json
```

**Required:**
- the pointer moved from the pre generation;
- a v2 record of this run with `activation`;
- the FEWS member is the FULL dict equal to `pub.members(pre record)["fewsnet"]`;
- `verify_delivery` passes, including `verify_member` of the new IPCCH member (H2/H8/H14, 6,226 areas each) and the inherited FEWS source inventory;
- `load_batch` passes with every raw header equal.

**Source actions** come from:
- inventory diffs (pre-CP5 → post-CP5 HEAD versions per table);
- the GPP ledger content;
- production `demand`/`jobs`/`skipped`;
- `climate_provider_calls`;
- the job logs (including the actual GPP HTTPS results).

Public HTTPS under Cloud Run is claimed only from these actual results. Zero network calls are never inferred from unchanged coverage.

**Reference expectation, informational only:** the 10-29 local same-M/O run gave phase counts H2 {201, 2372, 3537, 111, 5}, H8 {92, 2356, 3704, 69, 5}, H14 {115, 1833, 4130, 147, 1}. Differences are explained from the actual source actions, e.g. GPP newly published. They are not forced.

**Then:**
- R37 is checked offline only (`delivery_job.require_not_activated` against the read record). No legacy IPCCH request is ever sent.
- If the readback fails, stop and report; current is not rolled back automatically.

## 5g. Normal-config v2 finish (after CP5 acceptance; Supervisor seam)

- Back up the normal `project.json` bytes.
- Set `v2.image_uri = IMG`. This is the only change: promotion already rewrote the top-level `image_uri`/`work_dir`.
- Verify:
  - `submit` preview with the normal config: no `image_uri_pending`;
  - `status --run-id <real run>` with the normal config;
  - `load_initialized` passes, verified by a DIRECT call (`python -c "import pipeline as p; p.load_initialized(p.config(NORMAL_CFG))"`) or by `models select` preview. `maintenance status` does NOT invoke it.

## Host / cloud resource summary

- **Local:** previews and readbacks only. Readback runs under the unchanged guard; if the guard stops it, it is recorded INTERRUPTED and reported.
- **Cloud:**
  - one new init job (4 CPU/16 GiB, at most 2 executions);
  - two `oct-delivery` executions (smoke, real) at existing limits;
  - about 40 MB of input uploads, plus GCS store, deliveries and logs.
- **Not used:** no EE exports in this retained round, no Batch, no prepare.

## For CP6 documentation (after CP5; Supervisor source review 2026-10-31)

The operator and rollback documentation must state the following.
- **No reuse of the C operation.** After the v2 current publication, do not reuse OP `ipcch-v2-runtime-20261031` (hold/restore/release) as a v2 rollback:
  - `_inspect` sees the later pointer and config as foreign;
  - restore targets the old `487a` runtime;
  - a hand CAS to the pre-activation pointer drops activation, because the guards read only the current release.
- **No v2 current-rollback helper exists.** None is advertised.
- **Safe containment:** a NEW maintenance operation that snapshots the then-current guarded runtime, inspects active work, then forward recovery by a new request. All accepted retained writes are kept.
- **Pointer reversal:** only by a specifically reviewed recovery procedure.
