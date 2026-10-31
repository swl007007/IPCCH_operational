# IPCCH v2 monthly operation: operator handoff (task 10-30)

Real CP5 values come from the guarded readback (`cp4/cp5/post-real.json`), which the Supervisor accepted on 2026-10-31.

## 1. Routine monthly submission (existing CLI; no raw REQUEST JSON (the selections file is JSON), no month flag)

```bash
cd cloud_pipeline
P=/home/swl007007/.venvs/ipcch-cloud-operator/bin/python        # operator environment (ADC + gcloud configuration food-crisis-test)
CFG=/home/swl007007/ipcch-operator/food-crisis-test/project.json # normal config (v2.image_uri set 2026-10-31, 5g)
$P pipeline.py submit --config $CFG --selections SELECTIONS.json             # preview: validation, provisional refs, no upload
$P pipeline.py submit --config $CFG --selections SELECTIONS.json --execute   # uploads, freezes, publishes the request LAST
$P pipeline.py status --config $CFG --run-id ipcch-real-<id>                 # claim, reservation, durable v2_run_status
```

Since 5g, the normal config is byte-identical to `food-crisis-test-v2-runtime-20261031/project.json` (3be606ea).

**What `--execute` does:**
1. Uploads each refresh file create-only under `v2.inputs_prefix.<mode>/<run>/...`, or pins an existing `gs://…#generation`.
2. Freezes the request at ONE UTC instant: `prepared_at` and execution month M come from that instant. O = M-2; the targets are fixed.
3. Uploads `requests/<run>/run_manifest.json` last. That upload triggers Eventarc → Workflow `oct-delivery-trigger` → job `oct-delivery` → `entrypoint_v2`, which runs generation → inference → current publication with no further action.
4. Run IDs are `ipcch-<mode>-<uuid16>`. Re-running with `--run-id` resumes only that same submission. A deliberate new submission gets a new ID and a new instant.

**Failure handling:**
- An invalid selection fails before any upload.
- An admission, generation or validation failure BEFORE publication does not advance current. Retained writes saved before the failure stay saved.
- A crash or lost response AFTER the pointer CAS may have published. Before any new submission, reconcile `status` (durable `v2_run_status`) with `current.json` and its release record.
- A retry is a new submission. Never change an existing run ID.

### Selections file (`ipcch-v2-selections-v1`)

```json
{"schema": "ipcch-v2-selections-v1", "mode": "real", "operations": ["ipcch_generation", "ipcch_inference"],
 "publication": "current", "choices": { ...exactly the 11 below... }}
```

All 11 choices are explicit. `keep` is never implied, and a `keep` entry carries no other fields.

| Choice | keep | refresh fields |
|---|---|---|
| `acled` | prior accepted retained history | `file`, `start`, `end` (days), `regions`. The first refresh must cover the R44 window for O |
| `wfp` | prior accepted | `file`, `start`, `end` (months) |
| `history_snapshot` | prior accepted | `file` (a complete snapshot, replaced atomically) |
| `nino34_anom`, `bbg_staple_food`, `bbg_oilgas`, `bbg_soybean_oil`, `bbg_global_food`, `food_price_index_WB`, `idp_national`, `idp_local` | prior accepted | `file`, `start`, `end` (months) |

- `file` is a local path (uploaded create-only) or `gs://bucket/object#generation` (pinned).
- A successful refresh is the next keep baseline even if a later step fails.
- Shared pins are taken from `project.json v2`: envelope, environment manifest (the raw `requirements.lock.txt`), and the country reference for the mode.

### Horizons

| Model horizon | Public lead | Target (M=2026-10, O=2026-08) |
|---|---|---|
| H2 | 0m | 2026-10 |
| H8 | 6m | 2027-04 |
| H14 | 12m | 2027-10 |

## 2. Pins (2026-10-31)

| Item | Value |
|---|---|
| Source | `12b1d68` (CP1), `70f9d10` (CP2), `115798f` (CP3: v2 submission, installation, workflow and config) |
| Image | `us-central1-docker.pkg.dev/feisty-flames-511718-d4/monthly-delivery/runtime@sha256:acc3e4673fa7c133eade6e5c74b998706788e0d1af0f92b217ae74ce7e14ccf6` (tag `ipcch-v2-115798f`, Cloud Build `ea1cbe1c-d3fd-4e32-8a27-5e90c61e852e`) |
| Installed config | `/opt/ipcch/deployment.json` = `deploy/ipcch_v2_deployment.food-crisis-test.json` (sha `c75b1172…`); `INSTALL.json` `33d19119…` |
| IPCCH combination | `ipcch-validity-h2h8h14-final-20261030`. Envelope `03b93842…`, package `18b91d45…`, handoff bundle `e6e3ebc6…`, feature order `0ef1ffec…` (527 features), roster 6,226 |
| Retained stores | real `gs://food-crisis-test-ipcch-data/ipcch-v2/real` (pairing as above). Smoke `gs://food-crisis-test-ipcch-smoke/ipcch-v2/smoke` (fixture, roster 3) |
| Shared objects | envelope `…/inputs/v2/shared/ipcch-combination-envelope-v2-accepted.json#1793457267476070`; lock `…/inputs/v2/shared/requirements.lock.txt#1793457280557418` (`2f0a7251…`); country reference real `…/inputs/v2/reference/country_reference.csv#1793457294730935` (`0823e418…`); smoke `gs://food-crisis-test-ipcch-smoke/inputs/reference/country_reference.csv#1793457308277104` |
| Legacy destination | baseline `f0481ca1…` (runtime-only rebase of `b77cb29b…`); `initialized.json` `e0bb3e7f…`; work_dir `food-crisis-test-v2-runtime-20261031/operator-state`. FEWS packages `full-202610-ff389b11af93-02caeb861750/{0,6,12}m`, unchanged |
| Shared jobs | `oct-delivery` (8 CPU/32 Gi/14400 s/0 retries; args include `--v2-config /opt/ipcch/deployment.json`) and `monthly-prepare` (2 CPU/8 Gi; args unchanged, `prepare --help`), both on the image above. The Workflow passes `--v2-config` in the `oct-delivery` argv from env `DELIVERY_V2_CONFIG` |
| Current | `monthly-staging/current.json` gen `1793461128385732` → `releases/ipcch-real-522b30030f944868-ipcch/release.json#1793461128307577` (v2 record; activation 2026-10-31T15:37:56Z; IPCCH member M 2026-10 / O 2026-08; FEWS member inherited literally from `fews-compat-v2rt-20261031a`). Predecessor: `fews-compat-v2rt-20261031a`, gen `1793458988623055` |

## 3. Legacy FEWS NET consumers (preserved)

The legacy v1 route runs on the same image with the new destination:
- FEWS-only runs (`run --infer fewsnet --inherit ipcch=…`);
- `models register/select`.

The FEWS-only candidate `fews-compat-v2rt-20261031a` reproduced every scope, input and package byte-for-byte on the new image and was promoted.

After the v2 activation (CP5):
- a v1 request that scores IPCCH, alone or mixed, is rejected before work (R37);
- FEWS-only v1 runs inherit the v2 IPCCH member, naming it with its delivery manifest as the archive ref.

## 4. Rollback and containment (accurate as of v2 activation)

**Before the v2 activation only.** The C operation `ipcch-v2-runtime-20261031` can `restore` its own still-owned state:
- it restores the predecessor pointer CONTENT (release `fews-candidate-20261022a`) by a CAS at the observed current generation. It never restores an old generation number;
- normal config `a078f0e5`;
- fallback;
- jobs to `487a`.

This C operation's restore and release do not apply after the v2 activation.

**After the v2 activation:**
- Do NOT reuse that operation, restore to `487a`, or hand-CAS the pointer:
  - `_inspect` treats the newer pointer and config as foreign;
  - `487a` lacks the v2 guards;
  - a pre-activation pointer drops activation, because the guards read only the current release.
- There is no supported v2 current-rollback helper.
- **Containment** is a bounded, specifically reviewed procedure, because there is no dedicated post-publish rollback helper.
  - It starts with a NEW maintenance operation that actually holds: `pipeline.py maintenance --config $CFG --operation-id <new-op> --execute hold --admit <explicit run IDs>`.
  - That pauses admission, snapshots the then-current guarded runtime and reports active work.
  - The hold admits only IDs known when it is placed. Routine `submit` cannot choose an admitted ID beforehand: it generates a fresh ID, and `--run-id` only resumes an existing submission.
- **Recovery is forward,** by a new request after the hold is reviewed and released.
- Accepted retained writes are never deleted.
- Reversing the current pointer requires a specifically reviewed recovery procedure.

## 5. Deferred and known gaps (not passed)

- **DA1/DA2 (deferred).** The first natural incremental month is M=2026-11 / O=2026-09. A future real run must prove:
  - producer exports → climate reads → retained append → features → current;
  - asset IDs, PATCH32 rows, VI units, and omitted/all-null field behaviour.
- **Automatic EE outputs.** When a run has unsaved `evi_anom`/`spi03`/`spei03` periods, the table producer exports its tables to the writable root `projects/feisty-flames-511718-d4/assets/` (`producer_asset_root`). Asset IDs are run-specific, `<table name>__<version from run ID and M>`. Existing assets are never reused or overwritten, and consumers map those run-specific IDs. The han-sandbox static inputs and historical chunks are preserved as read-only inputs and are never written. Read sharing to the runtime SA remains a prerequisite.
- **Upstream access gap.** The runtime SA `monthly-runtime` is DENIED `getAsset` on the han-sandbox inputs (admin FC, STAGE2A baseline; probe `ipcch-v2-runtime-preflight-20261031-7jq5m`). The user identity's metadata reads succeed, but its ACL reads are denied. No ACL write was authorized or attempted, so whether the user can share them was not established. Read access for the runtime requires sharing by the upstream owner.
  - Any run with unsaved climate or table periods, including the first DA1 month, fails closed before export until the upstream owner shares read access with `monthly-runtime@feisty-flames-511718-d4.iam.gserviceaccount.com`, or an owner-approved copy is configured.
  - Do not deploy personal credentials.
- **Freeze timing.** M is the UTC month of the freeze instant. A run frozen after a month boundary needs that month's source readiness, so it is not a free retry of the previous month.
- **Fallback directories.** `cloud_pipeline/fallback/` is git-ignored local state:
  - active `october_2026` (`a7a631f5…`);
  - `october_2026.predecessor-ipcch-v2-runtime-20261031` (`54dd0f14…`);
  - `october_2026.predecessor-fews-retrain-20261022`.
