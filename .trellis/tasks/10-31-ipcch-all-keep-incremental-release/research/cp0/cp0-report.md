# CP0 preflight report (read-only) and CP1/CP2 packet — task 10-31

Executor: session 6a490ae1 (claude-opus-5-5[1m]), Herdr pane w1A:p8; 2026-11-01 UTC.
- No cloud mutation, upload, EE call or submission was made.
- Local evidence steps ran under the archived `research/cp2/guarded.sh` (CHILD-EXIT recorded), except the two reads disclosed in `guard-omission-note.md`.
- Cloud reads are in `cloud-operations.jsonl`; raw outputs are in `live/`.

## 1. Live state (fresh)

| Check | Result | Evidence |
|---|---|---|
| Normal config | `project.json` sha `3be606ea`; `v2.image_uri` = `acc3e467` | `load-initialized.log` |
| `load_initialized` | baseline `f0481ca1`; destination and runtime image `acc3e467`; env manifest `#1793456025486882` (`35a4890a`) | `load-initialized.{log,exit}`, child 0 |
| Shared jobs | `oct-delivery`: 8 CPU/32 Gi, 14400 s, maxRetries 0, 1 task, SA `monthly-runtime`; argv includes `--image-uri acc3e467 --v2-config /opt/ipcch/deployment.json`. `monthly-prepare`: 2 CPU/8 Gi, `prepare --help`. Both on `acc3e467` | `live/summary.txt` |
| Workflow | `oct-delivery-trigger` rev `000005-e86`, ACTIVE; source sha `4914412c` = repo `deploy/workflow.yaml`; env `DELIVERY_IMAGE_URI=acc3e467`, `DELIVERY_V2_CONFIG` | `live/workflow.out` |
| Hold / locks | `maintenance/hold.json` 404 (no live hold); `locks/` empty | `live/hold.err`, `live/locks.err` |
| Active work | no running oct-delivery, monthly-prepare or init executions; last workflow executions all terminal; 0 active Batch jobs | `live/exec-*.out`, `live/batch-jobs.out` |
| Current | gen `1793461128385732` → `ipcch-real-522b30030f944868-ipcch`, v2 record, activation 2026-10-31T15:37:56Z; IPCCH M 2026-10 / O 2026-08; FEWS member `fews-compat-v2rt-20261031a` (`a7a631f5`) | `pre-real.json` (pinned pre-snapshot) |
| Retained store | 56 HEAD tables, 65 versions, no orphans. NO HEAD changed since the 10-30 post-CP5 inventory. Pairing: real, `ipcch-validity-h2h8h14-final-20261030`, package `18b91d45`, order `0ef1ffec`, bundle `e6e3ebc6`, roster 6226 | `inventory-pre-run-real.json` |
| Shared pins | envelope `#1793457267476070` `03b93842`; raw lock `#1793457280557418` `2f0a7251`; country ref real `#1793457294730935` `0823e418`; all match. Local selections `7ab733d8` and prepared CSV `e660c7e8` match | `pins.json`, `pins-check.log` (child 0) |
| ACLED baseline | HEAD v1 gen `1793460193863710`; 242,341 rows over 2016-12-31..2026-10-10. 12 regions with rows (East Asia and Europe were declared before but have none). 5,928 (region, week) fingerprints; 0 rows inside 2026-10-17..23; 1 coverage record (the 10-30 refresh) | `acled-baseline-pre.json` (child 0); consistency with the inventory: `acled-pre-consistency.txt` |

## 2. Demand (genuine, nonempty; product helpers, no EE)

`demand_preflight.py` (guarded, child 0, 2:40, 1.06 GB) gives `demand-preflight.json` (`05f1402d`).

- **Month:** M 2026-11 (UTC), O 2026-09, targets 2026-11/2027-05/2027-11. Season windows: 149,424 rows through 2026; no extension.
- **Climate, monthly:** all 13 bases are saved through 2026-08 and need 2026-09.
  - Raster bases go through the EE raster providers (han admin FCs and baselines plus public collections), exported to GCS `export_root`:
    - PRCP sources (chirps, persiann, era5land): prcp_anom, prcp_z, rainy_days, cdd;
    - temperature (cpc, era5land): tmean_anom, tmax_anom, hot_days_p95, gdd, edd;
    - soil (era5land, gldas21): sm_z.
  - Table bases evi_anom, spi03 and spei03 go through the producer.
- **Climate, seasonal:** 0 pending for all bases.
- **Table producer:** `demand` = monthly evi_anom/spi03/spei03 `['2026-09']`, seasonal empty. `required_tables` gives 7 jobs:
  - `S2E3_VI_CURRENT_ADMIN_AQUA_Y2026_CMG_V3` and `…_TERRA_Y2026_CMG_V3` (vi, 2026);
  - `S2C3_DROUGHT_ADMIN_PRCP_{CHIRPS,PERSIANN,ERA5LAND}_Y2020_2026_V3`;
  - `S2C3_DROUGHT_ADMIN_ET0_FAO56_Y2020_2026_V3`;
  - `S2C3_ET0_PATCH32_Y2020_2026_V2`.

  The chunks are 1990-1995 … 2014-2019 (history, never produced) and 2020-2026 (produced). Destinations follow `projects/feisty-flames-511718-d4/assets/<job.name>__M202611_<run_id>_<sha256(run_id)[:8]>`.
- **GPP:** history ends 2025-12; the ledger has 2026-01..08 unpublished. Candidates 2026-01..09 make 9 HTTPS probes (404 means unpublished; a transport or server error is a failure).
- **Nightlight:** history ends 2026-08; candidate 2026-09 goes through VIIRS discovery. If published, export and zonal statistics follow; otherwise it is recorded as an optional gap.
- **ACLED:** the refresh replaces `week in [2026-10-17, 2026-10-23] AND region in the 17 declared regions`. No saved rows match, so 0 rows are replaced, and the expected appended rows are 470 (`expected-acled-interval.json`: 12 region keys, all week 2026-10-17; guarded, child 0). Under A = O-1 = August these October rows do not enter this run's ACLED features.
- **Kept:** the other ten (wfp, history_snapshot, 8 research families) must keep HEAD generation, version and sha.

## 3. Readiness and permissions (evidence versus unproven)

**Proven by earlier live evidence:**
- runtime SA `ee.Initialize` and GCS read/write (10-30 identity probe and real run);
- han metadata reads 151/151 (2026-11-01 probe, task facts);
- public HTTPS egress (10-30 run, GPP 404s).

**UNPROVEN until the run (no probe duplicated or attempted):**
- EE export task submission and completion under the runtime SA;
- asset CREATE under `projects/feisty-flames-511718-d4/assets/`;
- the readback of produced tables;
- the actual September 2026 source-calendar completeness of each climate source.

Each base needs at least one published source at O, otherwise the run is blocked (R13). These are runtime facts, not preflight facts.

## 4. CP1 — one submission (awaiting the Supervisor's release)

```
REPO="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational"; CP="$REPO/cloud_pipeline"
T="$REPO/.trellis/tasks/10-31-ipcch-all-keep-incremental-release/research/cp0"; G="$REPO/.trellis/tasks/archive/2026-10/10-30-ipcch-real-e2e-integration/research/cp2/guarded.sh"
P=/home/swl007007/.venvs/ipcch-cloud-operator/bin/python; CFG=/home/swl007007/ipcch-operator/food-crisis-test/project.json
SEL=/home/swl007007/ipcch-operator/food-crisis-test/v2-inputs/incremental-20261101/prepared/selections.json
```

**Pre-checks.** Each is a read or local operation; stop on any difference.
1. `date -u`: the month must be 2026-11 (M is then 2026-11). Never forge M.
2. Rehash `SEL` (`7ab733d8`) and the CSV (`e660c7e8`), guarded.
3. Fresh current generation is still `1793461128385732`; the hold is 404; there is no running oct-delivery or workflow execution (cloudop reads).
4. The ACLED HEAD generation is still `1793460193863710`, and no retained HEAD has moved since `inventory-pre-run-real.json`. One guarded `store_inventory` gives `inventory-pre-cp1-real.json`. If any HEAD moved, stop and report.
5. Run `submit` WITHOUT `--execute` (preview, guarded) and check M 2026-11, image `acc3e467`, 11 choices, ACLED refresh 2026-10-17..23 with 17 regions.

**The ONE submission:**
```
cd "$CP"; python3 "$T/cloudop.py" --timeout 1800 --purpose "CP1: ONE incremental v2 submission" --scope mutation \
  --effect "uploads ACLED file create-only under inputs/v2/<run>/acled/; freezes; publishes request LAST -> Eventarc -> Workflow -> oct-delivery" \
  -- $P pipeline.py submit --config $CFG --selections $SEL --execute
```

It is submitted exactly once.
- **If cloudop times out or the response is lost:** record argv, start, end and UNKNOWN in the ledger. Reconcile with `pipeline.py status --config $CFG --run-id <id from runs-v2/*/state.json>` and the request object. Never resubmit with a new ID. A same-ID resume is only `--run-id` per `submit_v2`, after reconciliation and with Supervisor review.
- **Monitoring:** a bounded `pipeline.py status` poll (120 s; until `v2_run_status` is terminal or the 4 h deadline) plus durable-object progress reads (task records under `ipcch-v2/exports/ipcch_exports/<run>/tasks/`, retained HEAD changes). Nothing is inferred from elapsed time.

**Budget and bounds:**
- One `oct-delivery` execution at the existing 8 CPU/32 GiB, 14400 s task timeout, 0 task retries; the run deadline is 4 h with a 900 s cleanup reserve. Cloud Run compute is therefore at most 32 vCPU-hours and 128 GiB-hours.
- Earth Engine work is billed separately in the feisty project, with no amount claimed: 7 table-to-asset exports, the 13 raster-base 2026-09 computations exported to GCS, and VIIRS 2026-09 discovery and possible export.
- 9 public HTTPS GPP probes.
- GCS: the request, the ACLED upload (about 0.1 MB), exports, retained versions, the delivery and logs.
- No resource change, no second run and no deployment change.

## 5. CP2 — readback after a terminal status (all local steps guarded)

```
STATE=/home/swl007007/ipcch-operator/food-crisis-test-v2-runtime-20261031/operator-state/runs-v2/<run>/state.json
CTX=/home/swl007007/ipcch-operator/food-crisis-test/v2-build/cp4-115798f-20261031T135044Z/tmp.oV5ZoayeBG/ipcch
ENV="/usr/bin/env PYTHONPATH=$CP GOOGLE_CLOUD_PROJECT=feisty-flames-511718-d4"
1. cloudop reads: final status JSON, the execution describe, and the full logs of the oct-delivery execution
2. bash $G readback-real $T/../cp2 $ENV $P $T/readback_v2.py post real <run> $T/pre-real.json $CTX $T/../cp2/post-real.json $STATE 2026-11 2026-09 527 6226
3. bash $G inventory-post $T/../cp2 $ENV $P $T/store_inventory.py gs://food-crisis-test-ipcch-data/ipcch-v2/real $T/../cp2/inventory-post-real.json
4. bash $G acled-post $T/../cp2 $ENV $L $T/acled_baseline.py $T/../cp2/acled-baseline-post.json
5. bash $G lineage $T/../cp2 $ENV $P $T/lineage_readback.py <run> $T/../cp2/post-real.json $T/inventory-pre-cp1-real.json \
     $T/../cp2/inventory-post-real.json $T/acled-baseline-pre.json $T/../cp2/acled-baseline-post.json $T/expected-acled-interval.json $T/../cp2/lineage.json
6. (gated) da2_asset_readback.py <lineage.json> → raw property keys, PATCH32 set, VI and drought fields
```

`L` is the lock venv python. Step 6 uses the local operator's EE credentials (read-only), not the runtime SA, so it needs the Supervisor's decision; otherwise the field-shape witnesses stay pending under D2.

**What lineage checks** (`incremental_checks.py`; self-check 8 passed, guarded):
- records and production bound to the run; no duplicate task or destination;
- receipt tables equal the jobs set;
- receipts join the completed task records;
- every demanded table base appends O with a published source from this run's assets;
- unconsumed assets only with explicit `unavailable` evidence (exact-set consumption is reported separately as the strongest outcome);
- batch `retained_inputs` equal the post HEAD (version, sha, HEAD generation);
- ten keeps unchanged;
- ACLED outside the interval byte-identical, no keys outside, and interval content EXACTLY equal to the pinned export's `parse_export` fingerprint;
- ACLED source pin, interval, regions and coverage record appended.

The DA2 summarizer self-check passed 3 tests (guarded).
