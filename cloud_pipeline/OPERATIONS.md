# Monthly operations and migration

All commands below run from `cloud_pipeline/` (or the extracted handover root). Use one private JSON configuration copied from `project.example.json`. `work_dir` resolves relative to that config; preserve it to retain initialized refs, model versions and run attempts. Keep credentials out of JSON. Status reads cloud state; mutation commands preview unless `--execute` is supplied.

## One-time destination setup

The operator needs a billed Google Cloud project, Google Cloud CLI, Application Default Credentials, the locked Python environment and permission to create the listed resources and act as their service accounts. Use Linux/WSL or a Linux terminal for shell commands. None of the commands below has been executed for your destination.

Fill configuration with your project, `us-central1` region, two new bucket names, runtime and workflow service-account emails, accepted image URI, Earth Engine project, operator label, release namespace and prepare job. These examples assume both buckets and Eventarc are in `us-central1`; another location needs compatible bucket/Eventarc placement. Use a dedicated runtime identity shared by Run and Batch and a separate workflow identity.

Set shell variables to the same values as the private config (these are examples, not credentials):

```bash
export PROJECT='YOUR_PROJECT'
export REGION='us-central1'
export DATA_BUCKET='YOUR_UNIQUE_DATA_BUCKET'
export REQUEST_BUCKET='YOUR_UNIQUE_REQUEST_BUCKET'
export RUNTIME_SA="monthly-runtime@${PROJECT}.iam.gserviceaccount.com"
export WORKFLOW_SA="monthly-workflow@${PROJECT}.iam.gserviceaccount.com"
export IMAGE_REPO='monthly-delivery'
gcloud auth login
gcloud auth application-default login
gcloud services enable run.googleapis.com batch.googleapis.com compute.googleapis.com   workflows.googleapis.com workflowexecutions.googleapis.com eventarc.googleapis.com   pubsub.googleapis.com storage.googleapis.com artifactregistry.googleapis.com   earthengine.googleapis.com iam.googleapis.com logging.googleapis.com --project "$PROJECT"
gcloud iam service-accounts create monthly-runtime --project "$PROJECT"
gcloud iam service-accounts create monthly-workflow --project "$PROJECT"
gcloud storage buckets create "gs://${DATA_BUCKET}" --project "$PROJECT" --location "$REGION" --uniform-bucket-level-access
gcloud storage buckets create "gs://${REQUEST_BUCKET}" --project "$PROJECT" --location "$REGION" --uniform-bucket-level-access
gcloud storage buckets update "gs://${DATA_BUCKET}" --versioning
gcloud storage buckets update "gs://${REQUEST_BUCKET}" --versioning
gcloud artifacts repositories create "$IMAGE_REPO" --project "$PROJECT" --location "$REGION" --repository-format docker
```

If a resource already exists, inspect it and reuse it instead of running the corresponding create command. Keep object generations: do not apply lifecycle deletion to pinned baselines, selected models or live run inputs.

Grant the runtime the scoped storage/image access and project roles it needs:

```bash
for bucket in "$DATA_BUCKET" "$REQUEST_BUCKET"; do
  gcloud storage buckets add-iam-policy-binding "gs://${bucket}" --member "serviceAccount:${RUNTIME_SA}" --role roles/storage.objectAdmin
done
for role in roles/batch.jobsEditor roles/batch.agentReporter roles/logging.logWriter roles/serviceusage.serviceUsageConsumer roles/earthengine.resourceViewer; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:${RUNTIME_SA}" --role "$role"
done
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" --project "$PROJECT" --member "serviceAccount:${RUNTIME_SA}" --role roles/iam.serviceAccountUser
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" --project "$PROJECT" --member "serviceAccount:${WORKFLOW_SA}" --role roles/iam.serviceAccountUser
gcloud artifacts repositories add-iam-policy-binding "$IMAGE_REPO" --project "$PROJECT" --location "$REGION" --member "serviceAccount:${RUNTIME_SA}" --role roles/artifactregistry.reader
for role in roles/eventarc.eventReceiver roles/workflows.invoker; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:${WORKFLOW_SA}" --role "$role"
done
STORAGE_AGENT="$(gcloud storage service-agent --project "$PROJECT")"
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:${STORAGE_AGENT}" --role roles/pubsub.publisher
```

The deployment operator also needs service-account `actAs`, resource deployment rights, data/request bucket read-write rights for initialization and raw upload, and permission to execute the prepare job **with argument overrides** (`roles/run.developer` on that job includes the required override permission). Google-managed Batch/Run/Eventarc service agents must retain their service-agent roles; do not assign service-agent roles to ordinary users. If your organization restricts the default network, arrange Batch VM egress to Earth Engine, GCS and public GOSIF endpoints before running. The current launcher uses the project's default Batch networking.

Register the destination Earth Engine project and complete its eligibility/verification in [Earth Engine configuration](https://console.cloud.google.com/earth-engine/configuration). API enablement alone is insufficient. Set `earth_engine_project` to that registered project; if it differs from `project`, grant the runtime Earth Engine resource access and Service Usage Consumer there too. Planner and Batch use the runtime identity, not your personal Earth Engine credentials.

### Transfer the accepted runtime image

First migration reuses the accepted container digest. It does not require rebuilding or rerunning October scoring. Obtain registry-read access to the current image for this one-time transfer, or obtain an OCI image export from its owner. After transfer, operations use only your destination image and buckets.

With `crane` installed, authenticate to both registries and copy without changing bytes:

```bash
export SOURCE_IMAGE='us-central1-docker.pkg.dev/manuel-remote-sensing/october-delivery/runtime@sha256:7e6133f32ab0b28d3f29b827d4153975e99f97d440e97a1a8cdacdfa1052f0d0'
export DEST_IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${IMAGE_REPO}/runtime:accepted-october"
gcloud auth configure-docker us-central1-docker.pkg.dev,"${REGION}-docker.pkg.dev"
crane copy "$SOURCE_IMAGE" "$DEST_IMAGE"
crane digest "$DEST_IMAGE"
```

The printed digest must equal `sha256:7e6133f32ab0b28d3f29b827d4153975e99f97d440e97a1a8cdacdfa1052f0d0` (source tag `runtime:cp5-confidence-1`). This is the runtime bound by `bootstrap/baseline.json`. Its acceptance evidence is the 2026-10-09 cloud rerun `oct-confidence-20261009b`, whose predictions equal the earlier accepted run exactly and whose bundle replayed offline. The earlier image `sha256:41944ea048c559190b6018f30ad52695cf9bedbb7d5695abef50b1348616d034` rejects the bound FEWSNET proxy evidence, so do not use it with this baseline. Set config `image_uri` to the **destination URI with `@sha256:...`**, not its mutable tag. A rebuilt image is a new runtime and needs actual compatibility acceptance; old acceptance is not automatically valid. Source code and the lock are included for maintenance; the container binary is distributed by registry/OCI transfer, not embedded in the local data archive.

Preview and apply the maintained resource definitions:

```bash
bash deploy/setup.sh /private/project.json
bash deploy/setup.sh /private/project.json --execute
```

Setup deploys the prepare and delivery Run jobs, grants the workflow identity Run overrides on the delivery job, and creates Workflow/Eventarc. It does not create buckets, identities, APIs or Earth Engine registration. Eventarc trigger creation is one-time. Inspect an existing trigger before reapplying. Delivery job/Workflow/trigger names are `oct-delivery`, `oct-delivery-trigger`, `oct-delivery-requests`; `prepare_job` comes from config.

Initialize immutable destination inputs once:

```bash
python pipeline.py init --config /private/project.json --baseline bootstrap
python pipeline.py init --config /private/project.json --baseline bootstrap --execute
```

Initialization verifies all local member hashes and the six previously accepted model scopes, then uploads baseline/model files and records actual GCS generations and SHA-256 references in `work_dir/initialized.json`. It does not run prediction. Full historical panels are needed by lag/normalization calculations; they are not repeated monthly uploads. A different destination or baseline needs a separate work directory.

## Monthly run and recovery

```bash
python pipeline.py run --config /private/project.json   --month 2026-11 --cutoff 2026-11-08T00:00:00Z   --deadline 2026-11-09T00:00:00Z --run-id nov-2026-a   --acled keep --wfp keep --execute
python pipeline.py status --config /private/project.json --run-id nov-2026-a
python pipeline.py download --config /private/project.json   --run-id nov-2026-a --output /private/november-delivery --execute
```

Choose fresh UTC dates and a unique run ID. Origin O fixes targets O/O+6/O+12. `cutoff` binds discovery eligibility; extraction uses exact selected provider images. Provider delays are filled and marked using the existing contract. `deadline` bounds preparation and prevents late CLI manifest submission; reserve at least 15 minutes for preparation cleanup. It is not a cancellation timer for already-submitted delivery jobs. Delivery has a four-hour task timeout.

`keep` always means the initialized retained ACLED/WFP snapshots. A refresh never silently changes the next run's keep baseline: choose refresh again with the desired complete raw export to reuse it. Fixed variables remain unchanged. Prepared remote outputs are versioned, but this CLI currently starts each run from the initialized remote history; it may re-extract post-baseline periods. It does not upload the entire local baseline monthly.

The CLI starts remote preparation, waits, and then publishes `requests/<run_id>/run_manifest.json`. Storage finalization triggers Eventarc -> Workflows -> Cloud Run -> CSVs and portable bundle. This is the existing automation; this repository does not add a GitHub build pipeline.

`--wait-seconds` defaults to 3600 and bounds local waiting only. If the command returns `preparing`, repeat the same **complete command with `--execute`** to attach and eventually submit. A local process must remain running or be resumed until `submitted`; status alone does not advance the run. A changed intent is rejected. Never change dates/models/config for an existing run ID. If interrupted during submission, `preparation_submission_pending` deliberately prevents ambiguous relaunch: inspect the Run execution and `prepared/<run_id>/` state first. A failed attempt requires a new ID.

Only durable delivery `succeeded` is success, not workflow submission. Run evidence is under `runs/<run_id>/`, results under `deliveries/<run_id>/`, and the current release pointer under `<namespace>/current.json`. Download requires a new directory and verifies every declared member without numerical replay. Missing diagnostic evidence leaves diagnostic values blank with an unavailable reason; it does not suppress predictions.

## Compatible raw formats

Use UTF-8 CSVs with the exact case-sensitive headers below. Extra columns are tolerated. Files stay local until `run --execute`; converters validate before submission, then the CLI uploads immutable raw bytes. There is no ACLED/WFP API fetch in this interface.

**WFP** requires:

```text
Country,Admin 1,Admin 2,Market Name,Commodity,Price Type,Price Date,Price,Unit,Currency,Trend,Data Type
```

`Price Date` is `DD/MM/YYYY` (for example `01/10/2026`). `Data Type` is exactly `Aggregated` or `Forecast`; forecast rows are excluded. Price and Trend must be numeric; country names must resolve to ISO3. Do not duplicate a month for the same country/admin/market/commodity/price-type/unit/currency series. Include the preceding calendar month of each series for FEWSNET price changes; IPCCH uses the supplied Trend. Observations after origin O are excluded. Supply the existing compatible export, not a pivoted national summary.

**ACLED** requires:

```text
event_date,event_type,country,admin1,admin2,admin3,location,latitude,longitude,fatalities
```

`event_date` is `YYYY-MM-DD`; optional `year` must match it. Latitude, longitude and fatalities must be numeric. The source through O must contain the three supported event families: `Battles`, `Explosions/Remote violence`, `Violence against civilians`. Supply complete event exports for covered months, not just newly added events. Rows with missing location/admin grouping keys follow the retained converter exclusion rule. Events after O are excluded.

Choose either or both independently:

```bash
python pipeline.py run --config /private/project.json   --month 2026-11 --cutoff 2026-11-08T00:00:00Z   --deadline 2026-11-09T00:00:00Z --run-id nov-2026-refresh-a   --acled refresh --acled-raw /private/acled.csv   --wfp refresh --wfp-raw /private/wfp.csv --execute
```

## Replace compatible models

Register a complete **already-trained** package, then explicitly select it for one of FEWSNET/IPCCH x 0/6/12. Weights alone are insufficient: feature schema, thresholds, routing, imputation metadata and acceptance must match. This interface does not train models or create scientific acceptance.

FEWSNET package files: `model.joblib`, `feature_contract.json`, `partition_map.csv`, `threshold_report.json`, `training_report.json`, `local_model_manifest.json`, `checksums.json`.

IPCCH package root: `model_package_manifest.json`, `training_export_summary.json`; selected `scope_0m/`, `scope_6m/` or `scope_12m/` contains `feature_columns.json`, `feature_contract.csv`, `model_metadata.json` and `phase2_worse_model.json` through `phase5_worse_model.json`. IPCCH shared root members must remain byte-identical across selected scopes. Replacements with changed shared root metadata need coordinated six-slot/baseline preparation outside this one-slot selector; do not overwrite existing packages.

Add `operator-model.json` beside those files. Use the corresponding object from `bootstrap/baseline.json`'s `models` array as the **structure**, with genuinely new identities/evidence:

| Field | Required content |
|---|---|
| `system`, `horizon_months`, `package_id` | Scope and new immutable version identifier |
| `feature_schema_sha256` | Actual schema hash, equal to the currently selected compatible schema |
| `manifest` | `delivery-package-manifest-v1` body: scope identity and complete `files` array with relative `path` and actual `sha256` |
| `environment` | Accepted environment body with `image_uri` and `requirements_lock_sha256` |
| `acceptance` | Real `delivery-model-acceptance-v1` accepted report, matching scope/package/schema, nonempty package-specific evidence, `package_manifest_sha256` and `runtime` bindings |
| `diagnostics` | Optional complete slot-specific declarations; omit to mark every diagnostic family unavailable |

Acceptance `runtime` includes `image_uri` and `environment_manifest_sha256`. Manifest and environment hashes use `sha256(json.dumps(body, sort_keys=True).encode())` (standard separators, no newline). They bind original bodies before destination reference rebinding. New available diagnostic evidence needs pinned destination refs and valid model-specific evidence. Diagnostics bound to another package, including the baseline evidence below, cannot be reused for a new package. The baseline's existing acceptance is only for its original six models.

```bash
python pipeline.py models --config /private/project.json register   --package /private/new-package --system fewsnet --horizon 6
python pipeline.py models --config /private/project.json --execute register   --package /private/new-package --system fewsnet --horizon 6
python pipeline.py models --config /private/project.json --execute select   --system fewsnet --horizon 6 --version NEW_PACKAGE_ID
```

Registration checks package files and invokes the existing loader; only register trusted model packages. It does not select automatically. Selection preserves all six slots, immutable old versions and their diagnostics. To roll back, run select with the prior package ID. Unsubmitted runs bind their original selection; use a new run ID after changing models.

## Diagnostic evidence

`bootstrap/baseline.json` binds per-slot diagnostic evidence files in `bootstrap/evidence/`. `evidence/provenance.json` records the sources, the builders, regression checks against the accepted h5 evidence and the previous baseline hash. Current status:

| System (families) | 0m | 6m | 12m |
|---|---|---|---|
| FEWSNET (polygon and country confidence) | Stage3 proxy `h0_validation_error_proxy_stage3_fs1_lag4_2021_2024`, `2021-02..2024-10` | Stage3 proxy `h6_validation_error_proxy_stage3_fs2_lag8_2021_2024`, `2021-02..2024-10` | Stage3 proxy `h12_validation_error_proxy_stage3_fs3_lag12_2021_2024`, `2021-02..2024-10` |
| IPCCH (polygon training errors, country confidence, maximum phase) | `training_resubstitution`, `2014-01..2026-03` | `training_resubstitution`, `2014-01..2026-04` | `training_resubstitution`, `2014-01..2026-04` |

All 15 declarations are available. The FEWSNET proxies are saved errors from research runs with 4-, 8- and 12-month lags for 0m, 6m and 12m. They are not held-out errors of the delivered packages. The 0m proxy is the 4-month-lag evidence of the accepted h5 delivery, so it is more pessimistic than true 0m error. They are accepted only through the `APPROVED_PROXY_EVIDENCE` allowlist in `cloud/orchestrator/delivery_outputs.py`, which maps each horizon to one exact basis and period. Any other FEWSNET evidence must be `package_validation_split` over the package's recorded validation period. Every other basis, period or horizon is rejected, including the h5 basis and a proxy used at another horizon. IPCCH resubstitution evidence is in-sample and optimistic, and its maximum-phase file holds the four-target training residuals. Its period must end at or before the package training cutoff. Every evidence file carries `model_package_id`, `horizon_months`, `basis` and `period`, and these must match the scored package. Missing evidence still leaves values blank with an unavailable reason.

Changing any evidence file or declaration changes `baseline.json` and therefore the baseline ID. An existing work directory refuses a different baseline, so initialize a fresh `work_dir` with `init`.

## Local artifacts and maintenance

`fallback/october_2026/` contains the accepted October result from cloud run `oct-confidence-20261009b`, with populated confidence diagnostics, and its replay evidence. Its predictions equal the earlier smoke run `oct-final-20261008a`, whose confidence was blank; that copy is kept outside the package in the legacy archive. Do not rerun the fallback merely because files were relocated. Historical source paths inside frozen evidence are provenance only; all current instructions are here.

To build a future container from maintained source, use `context=$(bash deploy/build_context.sh)` then `docker build -t YOUR_NEW_IMAGE "$context"`. This excludes baseline and fallback data from the build context. A new digest needs actual compatibility evidence; it cannot reuse the accepted image claim.

To produce a portable data/code handover, run the archive commands in [README.md](README.md). The archive contains local baseline, fallback, source and instructions; destination cloud access, Python dependencies and the runtime image transfer above are explicit external prerequisites. Filled configuration, credentials, mutable state and developer files are excluded.
