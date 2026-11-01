# IPCCH monthly production operations

This manual covers incremental generation, inference and publication on the **existing production deployment**. Run commands from this directory: the IFPRI repository root, or `cloud_pipeline/` in the canonical source. Bucket `food-crisis-test-ipcch-data` and namespace `monthly-staging` are production despite their names.

## 1. Production connection

| Setting | Production value |
|---|---|
| Project / Earth Engine project | `feisty-flames-511718-d4` |
| Region | `us-central1` |
| Current pointer | `gs://food-crisis-test-ipcch-data/monthly-staging/current.json` |
| Retained store | `gs://food-crisis-test-ipcch-data/ipcch-v2/real` |
| Refresh upload prefix | `gs://food-crisis-test-ipcch-data/inputs/v2/` |
| Request bucket | `food-crisis-test-ipcch-requests` |
| Runtime service account | `monthly-runtime@feisty-flames-511718-d4.iam.gserviceaccount.com` |
| Delivery job / Workflow | `oct-delivery` / `oct-delivery-trigger` |
| Writable EE output root | `projects/feisty-flames-511718-d4/assets/` |

The accepted runtime is:

```text
us-central1-docker.pkg.dev/feisty-flames-511718-d4/monthly-delivery/runtime@sha256:acc3e4673fa7c133eade6e5c74b998706788e0d1af0f92b217ae74ce7e14ccf6
```

It installs combination `ipcch-validity-h2h8h14-final-20261030` and its envelope/package/handoff under `/opt/ipcch`. Last accepted job limits: 8 CPU, 32 GiB, 14,400 seconds, zero task retries. Keep this deployment for monthly runs; bucket creation, history initialization and image builds are not submission steps.

On the operator workstation:

```bash
OPERATOR_PY=/home/swl007007/.venvs/ipcch-cloud-operator/bin/python
OPERATOR_CONFIG=/home/swl007007/ipcch-operator/food-crisis-test/project.json
SELECTIONS="$PWD/selections.example.json"
```

The config's initialized `work_dir` is `/home/swl007007/ipcch-operator/food-crisis-test-v2-runtime-20261031/operator-state`. Preserve it, including `initialized.json` and `runs-v2/<run_id>/state.json`. On another workstation, obtain the private config and matching operator state through the operator handover and use valid local paths. Credentials stay outside Git. The legacy `project.example.json` lacks the v2 block and cannot replace this config.

The private `v2` block must retain `deployment_config`, `inputs_prefix`, `image_uri`, `envelope`, `environment_manifest` and `country_reference`. The environment reference pins the raw dependency lock. `v2.image_uri` must match the deployed digest; `deployment_config` must resolve to the local production deployment JSON.

The runtime identity needs read access to han-sandbox static admins, calendars, baselines and historical assets under `projects/han-sandbox-505315/assets/`, and create/read access to the feisty output root. Both were demonstrated in November. Personal EE access is not evidence of runtime-SA access.

## 2. Prepare the eleven input choices

[selections.example.json](selections.example.json) is a complete all-keep selection: `mode: real`, `operations: [ipcch_generation, ipcch_inference]`, `publication: current`. Use it unchanged for all-keep, or copy it to a private input directory, edit the refresh choices and set `SELECTIONS` to that copy.

**Keep means the currently retained version**, including refreshes saved by earlier failed runs. It takes only `{"action":"keep"}`, without a file or dates. No choice can be omitted. All-keep still updates automatic sources.

| Choice | Refresh fields besides `"action":"refresh"` | Exact CSV header, in order |
|---|---|---|
| `acled` | `file`, `start`, `end` as days; `regions` | `week,region,country,admin1,event_type,sub_event_type,events,fatalities,population_exposure,disorder_type,centroid_latitude,centroid_longitude` |
| `wfp` | `file`, `start`, `end` as months | `admin_code,month,value` |
| `history_snapshot` | `file` only | `area_id,report_month,phase,availability_month,preparation_cutoff` |
| `nino34_anom` | `file`, `start`, `end` as months | `admin_code,month,value` |
| `bbg_staple_food` | same | `admin_code,month,value` |
| `bbg_oilgas` | same | `admin_code,month,value` |
| `bbg_soybean_oil` | same | `admin_code,month,value` |
| `bbg_global_food` | same | `admin_code,month,value` |
| `food_price_index_WB` | same | `admin_code,month,value` |
| `idp_national` | `file`, `start`, `end` as report months | `iso3,report_month,stock` |
| `idp_local` | `file`, `start`, `end` as months | `admin_code,month,value` |

Use UTF-8 CSV (BOM accepted), exact case-sensitive columns, dates `YYYY-MM-DD` and months `YYYY-MM`. A `file` is a local path (relative to the selections file), a trusted `gs://...` object or a pinned `gs://...#GENERATION`. Existing real-mode GCS inputs must be under `gs://food-crisis-test-ipcch-data/inputs/v2/`. Local files are uploaded create-only and pinned automatically.

For a monthly series, a refresh choice has this shape:

```json
{"action":"refresh","file":"inputs/series.csv","start":"2026-10","end":"2026-10"}
```

Supply the complete intended replacement for the declared interval. Refresh replaces that interval, including removal of old rows absent from the file; outside rows remain unchanged. It is not an append-only delta. Use unique keys and fixed-roster area codes. Blank series values remain missing; infinity and nonnumeric values are rejected. National IDP uses uppercase ISO3, unique `iso3,report_month` and finite nonnegative stock.

### ACLED

Supply the regional weekly aggregate export with the exact header above; the raw event-level `event_date,...` format is not this input. Week labels and `start` are Saturdays; `end` is a Friday. Every whole week must fit inside the declared interval. Provide complete coverage for the interval and declared regions, including all regions required by the fixed mapping. Overlapping saved weeks are replaced deliberately.

The accepted export used 17 region names: Caribbean; Caucasus and Central Asia; Central America; East Asia; Eastern Africa; Europe; International Waters; Middle Africa; Middle East; North America; Northern Africa; Oceania; South America; South Asia; Southeast Asia; Southern Africa; Western Africa. Declare the coverage actually exported; omitting required mapping regions is refused.

At November acceptance, ACLED v2 covered through **2026-10-23** (last weekly label 2026-10-17; 242,811 rows). Inspect the retained HEAD before preparing a later refresh. ACLED features at O use the month-lag-1 cutoff O-1: for December's O=2026-10, the latest allowed feature observation is 2026-09. Saving newer weeks does not move this cutoff.

### WFP and reported-phase history

IPCCH `wfp` is the processed research HDX `WFP_Price`: 100 plus the year-on-year percentage change in local-currency staple prices from the nearest market with data within 100 km. Supply `admin_code,month,value`, not the legacy raw WFP `Trend` export. There is no automatic WFP fetcher. The research build uses a centred outlier filter; refresh recent months explicitly when accepting revised values.

`history_snapshot` is a **complete replacement**, not a monthly append. Use one `preparation_cutoff`, unique `area_id,report_month`, phases 1..5 and no report/availability month after the cutoff. An older-than-O snapshot produces a warning.

## 3. Preview and submit once

```bash
"$OPERATOR_PY" pipeline.py submit --config "$OPERATOR_CONFIG" --selections "$SELECTIONS"
```

Preview validates selection structure, paths and request shape locally, with no cloud calls or uploads. Its references and time are provisional. It does not prove CSV content correctness, source availability or cloud permissions.

When ready, this command starts production E2E:

```bash
"$OPERATOR_PY" pipeline.py submit --config "$OPERATOR_CONFIG" --selections "$SELECTIONS" --execute
```

Save the returned `run_id` and request reference. One execution:

1. Uploads/pins refresh inputs and shared references.
2. Freezes one UTC instant after these operations: M is its UTC month, O=M-2. Upload start time and local timezone do not choose M.
3. Uploads `requests/<run_id>/run_manifest.json` last, triggering Eventarc -> Workflow -> `oct-delivery`.
4. Applies manual choices, computes automatic demand, exports/reads required EE tables and rasters, checks GPP/VIIRS, then writes the feature batch.
5. Scores H2/H8/H14 from that exact batch, verifies the delivery and publishes current. The existing FEWS NET member is inherited unchanged.

Routine submission has no month flag. A November freeze gives M=2026-11/O=2026-09 and targets 2026-11/2027-05/2027-11. The **next distinct monthly increment** requires a December UTC freeze: M=2026-12/O=2026-10 and targets 2026-12/2027-06/2027-12. Another November submission retains November's M/O.

Routine `submit` supports generation-only or generation plus inference. Generation-only writes a batch but does not publish current. Standalone inference on an explicitly pinned batch exists only in the lower-level request contract, not as a routine `submit` shortcut. Do not substitute last month's batch for a new month's generation.

## 4. Monitor and collect results

```bash
RUN_ID=ipcch-real-REPLACE_WITH_RETURNED_ID
"$OPERATOR_PY" pipeline.py status --config "$OPERATOR_CONFIG" --run-id "$RUN_ID"
```

Poll at a bounded interval, such as 60 seconds. `submitted`, `claimed` and `running` are intermediate. Success requires the durable final `status: succeeded`, IPCCH `status: succeeded`, publication `status: published`, and no unresolved `lock_release_problems`. The reservation records the deadline. Logs can be quiet while work continues; check durable state instead of resubmitting.

```bash
gcloud storage cat 'gs://food-crisis-test-ipcch-data/monthly-staging/current.json'
gcloud storage cat "gs://food-crisis-test-ipcch-data/runs/$RUN_ID/v2_run_status.json"
```

Follow the pointer's `release_record` at `release_record_generation` using `gcloud storage cat 'gs://...#GENERATION'`. The release must name publication `<run_id>-ipcch` and its pinned request. If another run has since advanced current, distinguish that from this run's own result. Follow the pinned delivery and batch manifests, not file modification times.

| Artifact | Path relative to `gs://food-crisis-test-ipcch-data/` |
|---|---|
| Feature batch | `ipcch-v2/real/feature_batches/<batch_id>/`: `manifest.json`, `h02.csv`, `h08.csv`, `h14.csv`, `feature_provenance.csv`, `summary.json` |
| Delivery manifest | `deliveries/<run_id>-ipcch/manifest.json` |
| Polygon/country predictions | `deliveries/<run_id>-ipcch/scopes/{0,6,12}m/ipcch/{polygon_predictions,country_predictions}.csv` |
| Release record | `monthly-staging/releases/<run_id>-ipcch/release.json` |
| Retained versions | Tables and their `HEAD.json`/version records under `ipcch-v2/real/` |
| EE task receipts | `ipcch-v2/exports/ipcch_exports/<run_id>/tasks/` |

Download a manifest-pinned file with `gcloud storage cp 'gs://...#GENERATION' LOCAL_FILE` and compare its SHA-256. The legacy `pipeline.py download` route is not the v2 collection procedure. Large provenance/fill-audit files need not be downloaded merely to check bucket visibility.

IPCCH should link the same batch, M/O, 527-feature order and 6,226-area roster at all three horizons. Publication verifies stored members before moving current; downloads should still use exact generations and hashes. The inherited FEWS member retains its own month. Activation records the original v2 cutover and is carried forward, so its older date is expected.

Inspect the batch manifest's generation report: `inputs`, `climate_production` (demand/jobs/skipped), `gaps`, `coverage_end` and `warnings`. Relate retained references to saved versions. Export completion alone does not establish source completeness or consumption.

## 5. Automatic sources and missing data

Unsaved EVI/SPI/SPEI periods trigger VI current, PRCP, ET0 and PATCH32 production under `projects/feisty-flames-511718-d4/assets/`. IDs are run-specific: `<table>__<version from run ID and M>`. Existing output assets are never reused or overwritten; consumers map the new IDs automatically. Job counts and year chunks follow demand; seven jobs in November are not a fixed monthly requirement.

Han-sandbox admin groups G00..G24, static baselines and historical chunks remain read-only. Raster providers, seasonal demand, GPP publication checks and VIIRS discovery are also automatic. No monthly Code Editor task submission, upstream script rerun or asset-address replacement is needed.

Incomplete source calendars can produce missing fields and unavailable consumer periods even when export succeeds. Missing values remain explicit under the feature contract. Keep does not fabricate later values for stale research inputs.

In the accepted November run, GPP 2026-01..09 returned 404 and was ledgered unpublished; history ended 2025-12. Soybean oil ended 2026-07. Their O values were optional-missing NaN. PERSIANN's incomplete September calendar left the mean wholly absent: export succeeded, but that source was unavailable. Review the next report for changes to these dated conditions.

## 6. Failure, resume and containment

After a timeout or lost response, preserve local state and reconcile status, frozen request, reservation, final record and current pointer before considering another submission.

An interrupted submission can then resume the **same frozen bytes** using its original selections and ID:

```bash
"$OPERATOR_PY" pipeline.py submit --config "$OPERATOR_CONFIG" --selections "$SELECTIONS" --run-id "$RUN_ID" --execute
```

This resumes submission; it does not rerun a terminal failed job. A new attempt needs a new submission without `--run-id`, after fixing the cause and reviewing retained changes. It freezes the then-current UTC month. Refreshes and other versions committed before failure remain saved and become the next keep baseline. A failure before publication leaves current unchanged; after publication uncertainty, inspect pointer and release before concluding that.

Preserve `work_dir`: without its v2 submission state, CLI status can fall back to legacy lookup. That does not prove the v2 request never existed.

No dedicated v2 current-rollback helper exists. Use a reviewed new maintenance operation if containment is needed. A hold pauses admission; release it before submitting a fresh routine ID, which is not pre-admitted by an existing hold. Preserve retained histories. Do not restore the old C transition, deploy the pre-v2 `487a...` image or manually replace current with a pre-activation pointer.

## 7. Accepted reference and limits

The 2026-11-01 acceptance is `ipcch-real-fe7282ef75e747fd`, execution `oct-delivery-625sk`, current generation `1793503777656101`. Eleven manual inputs stayed unchanged; thirteen climate tables appended September for exactly 6,226 areas, preserving old values. Seven table-to-asset and seven raster exports completed; nightlight appended September. The FEWS NET member from `fews-compat-v2rt-20261031a` was inherited unchanged.

DA1 production-to-current passed. DA2 remains partial under accepted D2: exact PATCH32 targets, natural null fill candidates, explicit nulls, wholly omitted fields and a three-area VI recomputation were observed. Per-row missing keys within present fields and finite-primary preservation had no natural samples. PATCH32's 93 source-level fill candidates accompanied 21 finite/11 NaN saved September SPEI values across 32 targets; this is not an independent fitted SPEI replay. No full SPEI/VI replay or model-accuracy claim follows.

Detailed evidence is in canonical archived tasks `10-31-ipcch-all-keep-incremental-release` and `10-30-ipcch-real-e2e-integration`. These records and production payloads are separate from this code-only delivery.
