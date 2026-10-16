# Cloud operations ledger

Owner: executor. One row per cloud API call or command against GCP. Target project for all operations is `food-crisis-modeling-enso` (#76571749286). The gcloud global configuration (core/project `manuel-remote-sensing`) has not been changed. No secrets are recorded here.

"Consumer" is the project charged for API quota. From O-010 on, every call pins the consumer to the target with `x-goog-user-project`/`--billing-project` and runs non-interactively.

| ID | Time (EDT, 2026-10-16; exact only where a source is cited, otherwise approximate with bounds) | Operation | Consumer | Effect | Result | Cost |
|---|---|---|---|---|---|---|
| O-001 | approx., between run start 01:15:26 and O-008 01:34:35 | `gcloud projects describe food-crisis-modeling-enso` (G1) | not pinned (gcloud default) | read | ACTIVE, number 76571749286, created 2026-08-12 | none |
| O-002 | approx., same window as O-001 | `gcloud services list --enabled --project=food-crisis-modeling-enso` (G2) | target | read | 23 services; BigQuery family, Earth Engine, Storage, Logging, Monitoring, Service Usage, sql-component, Datastore, Dataplex, Dataform, telemetry, trace. Not enabled: Run, SQL Admin, Artifact Registry, AI Platform, Secret Manager, IAM, Cloud Build, Cloud Billing, Billing Budgets | none |
| O-003 | approx., same window as O-001 | `gcloud billing projects describe food-crisis-modeling-enso` (G3) | not pinned; possibly `manuel-remote-sensing` via gcloud default | read | billingEnabled true, account `billingAccounts/01A0EF-314BAC-4D55E6` | none |
| O-004 | approx., same window as O-001 | `gcloud storage buckets list --project=food-crisis-modeling-enso` | target | read | one existing bucket `food-crisis-modeling-enso-han` (US multi-region). Not ours; will not be modified | none |
| O-005 | approx., same window as O-001 | `gcloud resource-manager org-policies list --project=…` | not pinned | read | no project-level org policies listed | none |
| O-006 | approx., same window as O-001 | `gcloud projects get-ancestors food-crisis-modeling-enso` | not pinned | read | no organization/folder ancestor returned | none |
| O-007 | approx., same window as O-001 | `cloudresourcemanager v1 projects/food-crisis-modeling-enso:testIamPermissions` (16 permissions) | not pinned (OAuth client) | read | all 16 granted, including setIamPolicy, serviceusage enable, SQL/Run/AR/Vertex/Secret/Build create, `billing.resourceCosts.get` | none |
| O-008 | 01:34:35 (services list file mtime) – 01:36:32 (last SKU file mtime) | Cloud Billing Catalog `services` and `services/{id}/skus` for SQL, Run, GCS, AR, Vertex, Secret Manager, Build, Logging | not pinned (OAuth client) | read, public price catalog | SKU lists saved to native scratch `scratch/p3/skus/*.json` | none |
| O-009 | started ≈01:39 (2-min tool timeout before backgrounding); last output write 01:41:00 (file mtime) | `gcloud billing budgets list --billing-account=01A0EF-…`, then BigQuery dataset list and billing-account describe | **wrong consumer: `manuel-remote-sensing`** (not pinned) | read attempt | Budgets call failed SERVICE_DISABLED in the consumer project. Command stopped with TaskStop; the API-enable prompt was **not** accepted and nothing was enabled. Supervisor confirmed the failure. Does not establish billing-account denial | none |
| O-010 | approx., between commits e8315b8 01:47:29 and 65c0d45 01:49:42 | BigQuery `projects/food-crisis-modeling-enso/datasets?all=true` | target | read | `[]`: no datasets, hence no billing export in this project | none |
| O-011 | approx., as O-010 | Cloud Billing `billingAccounts/01A0EF-…` get | target | read | PERMISSION_DENIED / SERVICE_DISABLED: Cloud Billing API not enabled in target. Not enabled by us | none |
| O-012 | approx., as O-010 | Billing Budgets `billingAccounts/01A0EF-…/budgets` list | target | read | SERVICE_DISABLED in target. Not enabled | none |
| O-013 | approx., as O-010 | Cloud Billing `billingAccounts/01A0EF-…:testIamPermissions` | target | read | SERVICE_DISABLED in target. Not enabled | none |
| O-014 | approx., after 65c0d45 01:49:42 and ≥45 s before O-016; ≤01:55:32 | `gcloud services enable cloudbilling.googleapis.com --project=food-crisis-modeling-enso --billing-project=food-crisis-modeling-enso --quiet` | target | **write: API enable** (supervisor-confirmed in scope for R4/R5 budget gates) | operation `operations/acat.p2-76571749286-61874aa1-…` finished successfully | none (API enable is not billed) |
| O-015 | approx., as O-014 | `gcloud services enable billingbudgets.googleapis.com --project=… --billing-project=… --quiet` | target | **write: API enable** (same authority) | operation `operations/acat.p2-76571749286-3dfc973b-…` finished successfully | none |
| O-016 | approx., after a 45 s wait following O-015; ≤01:55:32 | Cloud Billing `billingAccounts/01A0EF-314BAC-4D55E6` get | target | read | **PERMISSION_DENIED** "The caller does not have permission" (actual IAM denial, not SERVICE_DISABLED) | none |
| O-017 | approx., as O-016 | billing account `testIamPermissions`, including `billing.resourceCosts.get` | target | read | INVALID_ARGUMENT: that permission is not valid on a billing account; retried as O-020 | none |
| O-018 | approx., as O-016 | Billing Budgets list on billing account | target | read | **PERMISSION_DENIED** (actual IAM denial) | none |
| O-019 | approx., as O-016 | Cloud Billing `projects/food-crisis-modeling-enso/billingInfo` | target | read | billingEnabled true, account `01A0EF-314BAC-4D55E6` (O-003 result confirmed with pinned consumer) | none |
| O-020 | approx., shortly before O-024 | billing account `testIamPermissions` (accounts.get, budgets.get/create, getSpendingInformation, getUsageExportSpec) | target | read | `permissions: []`: the executor holds **none** of these on the billing account | none |
| O-021 | approx., shortly before O-024 (returned data point end 05:50Z) | Monitoring `storage/v2/total_bytes`, 2-day window | target | read | `food-crisis-modeling-enso-han` MULTI_REGIONAL 223,108,170 bytes (~0.21 GiB) at 05:50Z | none |
| O-022 | approx., shortly before O-024 | Monitoring `bigquery/query/scanned_bytes_billed`, month to date | target | read | no series returned. **Not evidence of zero use** | none |
| O-023 | approx., shortly before O-024 | Monitoring metricDescriptors `earthengine.googleapis.com/*` | target | read | cpu/usage_time, cpu/in_progress_usage_time, disk/used_bytes | none |
| O-024 | 01:55:32 (API-returned interval endTime 05:55:32Z = request time) | Monitoring EE `project/cpu/usage_time` ALIGN_SUM; EE `disk/used_bytes` | target | read | **3,190,660.85 EECU-seconds (~886.3 EECU-hours) over 2026-09-16T05:55Z…2026-10-16T05:55Z** (the 30-day alignment window returned, not month to date); EE disk 0 bytes | none |

## Spend visibility status (design line 42), as of O-024 (01:55:32 EDT)

Actual current-month spend for the shared project is **not visible** to the executor:
- no billing export dataset exists in the project (O-010);
- on billing account `01A0EF-314BAC-4D55E6` the executor holds none of get / budgets / spending-information / usage-export permissions (O-016, O-018, O-020). These are real IAM denials. The SERVICE_DISABLED results O-011…O-013 were resolved by enabling the support APIs in O-014/O-015.

Usage signals that are visible (usage, not billed amounts):
- legacy bucket ~0.21 GiB;
- Earth Engine: one aggregated Monitoring point of ~3.19M EECU-seconds (~886 EECU-hours). It is from a single 30-day ALIGN_SUM bucket that the API returned as 2026-09-16…10-16, even though an October start was requested. Raw points and interval semantics were not checked, so this is **not** verified October usage and not billing. It is recorded only as an observed signal;
- no BigQuery billed-bytes series, which is not proof of zero.

Whether EE compute is billed on this project, and at what rate, is unknown. It needs resolving only if the supplied current-month report or estimate leaves a material recurring cost unexplained.

**Administrator figure needed** (the supervisor is requesting it asynchronously):
1. **Required budget prerequisite:** the current-month (October 2026) actual cost for project `food-crisis-modeling-enso`, preferably broken down by service, or confirmation that the earlier "USD 3" figure refers to this project and this month.

Optional supporting evidence, not a blocker: any existing budget or alert on billing account `01A0EF-314BAC-4D55E6` that covers this project.
Conditional: Earth Engine billing detail is needed only if the supplied report or estimate leaves a material recurring cost unresolved.

Paid provisioning and job submission stay deferred until the current-month available envelope is supported by those figures.

## Update 2026-10-16: spend figure supplied (user ruling, recorded by the supervisor in e53de85)

The user stated that current-month (October 2026) actual spend for `food-crisis-modeling-enso` to date is **USD 0**. This is a user-supplied figure, not API-verified; billing-account access is still denied (O-016/O-018/O-020).

The earlier "USD 3" belongs to `manuel-remote-sensing`; it is not used here.

The required budget prerequisite above is therefore satisfied:
- In-scope provisioning and job submission may proceed once their technical gates and the per-operation cost and reservation gates pass, with no repeat permission request.
- The platform (USD 100/month) and training/HPT (USD 100/month) used-and-reserved ledgers stay separate.
- Every operation keeps its own receipt.
- The Earth Engine usage signal above stays an unverified observation. The conditional EE billing item applies only if a material recurring cost appears.

## G5 — service enablement (2026-10-16, times by `date`)

Every command pins `--project=food-crisis-modeling-enso --billing-project=food-crisis-modeling-enso --quiet`. The gcloud global core/project is still `manuel-remote-sensing` and is unchanged.

| ID | Time (EDT) | Operation | Consumer | Effect | Result | Cost |
|---|---|---|---|---|---|---|
| O-025 | 07:06:27 | `gcloud services list --enabled` (G5 precheck) | target | read | 25 services enabled. sqladmin, run, artifactregistry, cloudbuild, secretmanager, aiplatform, iam and iamcredentials were not among them | none |
| O-026 | 07:07:03 – 07:07:36 | `gcloud services enable sqladmin run artifactregistry cloudbuild secretmanager aiplatform iam iamcredentials (.googleapis.com)` | target | **write: API enable** (G5) | operation `operations/acf.p2-76571749286-61fbb5e4-…` finished successfully | none (enablement is free) |
| O-027 | 07:07:36 – 07:08:13 | `gcloud services list --enabled`; `gcloud iam service-accounts list` | target | read | 35 services. Dependencies were auto-enabled: containerregistry, pubsub. The default compute SA `76571749286-compute@developer.gserviceaccount.com` now exists | none |
| O-028 | 07:08:46 – 07:09:06 | `gcloud projects get-iam-policy` | target | read | failed: Cloud Resource Manager API not enabled in the target | none |
| O-029 | 07:09:13 – 07:09:31 | `gcloud services enable cloudresourcemanager.googleapis.com` | target | **write: API enable** (G5; needed for G6 IAM) | operation `operations/acat.p2-76571749286-0c1a9172-…` finished successfully | none |
| O-030 | ≈07:10 (after a 30 s wait) – 07:10:15 | `gcloud projects get-iam-policy` | target | read | 7 bindings. Service-account bindings: cloudbuild legacy SA `roles/cloudbuild.builds.builder`; agents for cloudbuild, containerregistry, pubsub, run; **default compute SA `roles/editor`** (granted automatically when Compute-dependent APIs were enabled) | none |

**Flag (supervisor/user):** the default compute SA now holds project Editor (automatic Google behaviour, not a grant by us). The design forbids Editor/Owner for jobs and the assistant. No workload of ours will run as this SA: Cloud Build, Cloud Run and Vertex jobs get dedicated scoped SAs in G6. Removing the automatic Editor grant is a project-level IAM change outside the planned grants, so it is not done unilaterally; it is recommended if nothing else in the shared project relies on the default SA.

## G6 — identities (2026-10-16)

| ID | Time (EDT) | Operation | Consumer | Effect | Result | Cost |
|---|---|---|---|---|---|---|
| O-031 | 07:15:58 – 07:17:12 | `gcloud iam service-accounts create research-build / research-mlflow / research-trainer` (display names: image builds, MLflow service runtime, training jobs); then list | target | **write: 3 service accounts** (no roles yet) | all three created; listed alongside the default compute SA | none |
| O-032 | 07:23:33 – 07:24:19 | `gcloud projects add-iam-policy-binding` ×3 (`--condition=None`): research-build and research-trainer `roles/logging.logWriter`; research-mlflow `roles/cloudsql.client`. Then get-iam-policy | target | **write: 3 project role bindings** (as in cloud-deployment-plan.md G6) | the policy shows exactly these research-* bindings | none |

## G7 — storage and image repository (2026-10-16)

Ledger: `/home/swl007007/projects/food-crisis-research/ledger/spend.sqlite` (operator host). Before creation, the platform pool for 2026-10 admitted:
- `G7-gcs-storage-ops-2026-10`: USD 2.27;
- `G7-gcs-initial-class-a`: USD 0.85;
- `G7-artifact-registry-2026-10`: USD 1.10.

Committed total: USD 4.22 of 100. These are reservations, not actual cost.

| ID | Time (EDT) | Operation | Consumer | Effect | Result | Cost |
|---|---|---|---|---|---|---|
| O-033 | 07:24:53 – 07:25:36 | `gcloud storage buckets create gs://food-crisis-modeling-enso-research-inputs` and `…-research-artifacts` (`--location=us-central1 --default-storage-class=STANDARD --uniform-bucket-level-access --public-access-prevention --soft-delete-duration=7d`) | target | **write: 2 buckets** | created; describe shows US-CENTRAL1, STANDARD, uniform access true, PAP enforced, soft delete 604800 s | storage by usage (reserved above) |
| O-034 | 07:25:36 – 07:26:52 | `gcloud artifacts repositories create research --repository-format=docker --location=us-central1`; describes | target | **write: AR repository** | `projects/food-crisis-modeling-enso/locations/us-central1/repositories/research`, DOCKER, STANDARD_REPOSITORY, Google-managed key | storage by usage (reserved above) |
| O-035 | 07:27:09 – 07:27:46 | `gcloud storage buckets create gs://food-crisis-modeling-enso-research-build` (same flags) + `buckets update --lifecycle-file` (Delete at age 7 days) | target | **write: build-staging bucket + lifecycle** | created; lifecycle Delete age 7 confirmed by describe | negligible (≈4.5 MB contexts) |
| O-036 | 07:27:46 – 07:30:38 | bucket IAM: artifacts → research-mlflow `objectUser`, research-trainer `objectCreator`; inputs → research-trainer `objectViewer`; build → research-build `objectViewer`. Repo `research` → research-build `artifactregistry.writer`. Then get-iam-policy of each bucket | target | **write: 5 resource-scoped bindings** | the policies show exactly these research-* bindings | none |

## G8 — Cloud SQL instance (2026-10-16)

Ledger, before creation: `G8-cloudsql-research-pg-2026-10`, USD 40.98, full-month reservation for an instance created mid-month. Platform committed USD 45.20.

| ID | Time (EDT) | Operation | Consumer | Effect | Result | Cost |
|---|---|---|---|---|---|---|
| O-037 | 07:32:11 – 07:37:24 (the supervisor backgrounded the same shell; not resubmitted) | `gcloud sql instances create research-pg --database-version=POSTGRES_16 --edition=ENTERPRISE --tier=db-g1-small --region=us-central1 --availability-type=zonal --storage-type=SSD --storage-size=30 --no-storage-auto-increase --backup-start-time=07:00 --retained-backups-count=7 --no-enable-point-in-time-recovery --ssl-mode=ENCRYPTED_ONLY --deletion-protection` | target | **write: Cloud SQL instance** | RUNNABLE; tier db-g1-small; primary address 34.123.136.49; no private address; no authorized networks (none passed) | per hour (reserved above) |

## G9 — images (2026-10-16)

Ledger: `G9-cloud-build-images`, USD 0.72 one-time (120 build-minutes); the failed pilot's minutes count against it. Every submission used `--project/--billing-project=food-crisis-modeling-enso --region=us-central1 --gcs-source-staging-dir=gs://food-crisis-modeling-enso-research-build/source`, with `serviceAccount: research-build@…` and logging CLOUD_LOGGING_ONLY in cloudbuild.yaml.

| ID | Time (EDT) | Operation | Consumer | Effect | Result | Cost |
|---|---|---|---|---|---|---|
| O-038 | ≈07:35 – 07:37:55 | `gcloud builds submit` service, context at b497503 (pilot) | target | **write: Cloud Build** | build `fd2129fa-32fb-4924-a3f8-6291b639286e` **FAILURE** at step 1 (in-image self-check, exit 78): the hook's guard refused because `MLFLOW_GATEWAY_ALLOWED_PROVIDERS` was not in the image ENV (the .pth loads before start.prepare). **Nothing was pushed.** Complete Cloud Logging saved (`g9-images-36bde42/pilot-fd2129fa-FAILED.cloud-logging.json`). Fixed in native 36bde42 | build minutes |
| O-039 | 07:42 – 07:43:12 (submissions); builds 11:42:11–11:46:50 UTC | `gcloud builds submit --async` ×5, contexts at native 36bde42 | target | **write: 5 Cloud Builds + 5 pushed images** | all SUCCESS. Each build: build → self-check as UID 65534 with no network (ok, lines in `*.selfcheck.txt`) → push. Digests: service `sha256:280013b0…`, training-fews `sha256:d7ac74a6…`, training-ipcch `sha256:7c59d674…`, replay-x320 `sha256:1e787909…`, replay-forecast-x320 `sha256:2810ab7c…` (full values in `g9-images-36bde42/*.build.json`) | build minutes; AR storage (reserved) |

## G6/G8 — credentials, admin user, scoped roles (2026-10-16)

The provisioner (native b32038d) was released by the supervisor after its fake-API regressions. The role bootstrap (native 3c8dbad) passed throwaway-PostgreSQL tests. Ledger: `G6-secret-manager-2026-10`, USD 0.84 (13 secrets + accesses); platform committed USD 46.76.

| ID | Time (EDT) | Operation | Consumer | Effect | Result | Cost |
|---|---|---|---|---|---|---|
| O-040 | 07:56:26 – 07:56:41; 07:57:05 | `provision_secrets --dry-run` (Secret Manager GET ×13), then `gcloud sql users list` | target | read | all 13 planned secrets absent (HTTP 404); instance users: only built-in `postgres` | none |
| O-041 | 07:57:05 – 07:57:35 | `provision_secrets` (Secret Manager create + addVersion + setIamPolicy ×13; Cloud SQL Admin `users.insert research_admin`) | target | **write: 13 task-labelled secrets (user-managed us-central1), secret-level accessors; 1 SQL user** | 13 secrets version 1. Accessors: research-mlflow on backend/auth URIs, flask secret, KEK, assistant credentials, guard DSN; research-trainer on mlflow-jobwriter; none (operator-only) on the SQL passwords and mlflow-reader. `users.insert` operation `fe18ef61-…` polled to DONE, errors []. Sanitized receipt: `g6-g8-credentials-roles/provision-receipt.json` (no values) | secrets (reserved) |
| O-042 | 07:57:52 – 07:58:36 | Cloud SQL Auth Proxy v2.26.2 (binary sha256 787d23b4… verified against the release notes; `--gcloud-auth --quota-project food-crisis-modeling-enso`, 127.0.0.1:5433); `db_roles` as research_admin | target | **write: 4 DB roles, 4 databases, grants, PostGIS** | research_admin login ok (stored credential proven). mlflow_app, guard_app, research_import, research_read: all attributes false except login; memberships none. Databases mlflow / mlflow_auth (owner mlflow_app), guard (guard_app), research (research_import); no PUBLIC grants; research_read CONNECT on research only; research_admin CONNECT (maintenance). PostGIS 3.6.4 (local rehearsal was 3.5.0). 4/4 app logins ok. Receipt: `db-roles-receipt.json` | instance hours (reserved) |

Registry sizes after G9 (`g9-images-36bde42/registry-images.json`): 3,307,567,088 bytes compressed for the 5 images (the quote reserved 11 GiB). The ledger notes record all six build ids, including the failed pilot (reservation kept).
| O-043 | 08:00:13 – 08:00:26 | `gcloud sql instances describe research-pg` | target | read | Observed settings (`g6-g8-credentials-roles/research-pg-settings.json`): ENTERPRISE, POSTGRES_16, db-g1-small, ZONAL (us-central1-a), PD_SSD 30 GB, storageAutoResize false, backups enabled 07:00 with 7 retained (COUNT), PITR false (transactionLogRetentionDays 7 is the API default; no logs are retained with PITR off), ipv4 enabled with **no authorized networks**, sslMode ENCRYPTED_ONLY, no private network, deletion protection true, no database flags, settingsVersion 1 | none |

## G7/G8 — data staging and MLflow stores (2026-10-16)

Transfers use the operator's own credentials through the Python storage client (target project pinned). Every object is uploaded create-only (`if_generation_match=0`) after a fresh local sha256/md5/crc32c pass equals the frozen manifest. Server md5 and crc32c are then read back. The sha256 in object metadata is declared, never cloud-computed. Stores are loaded through the Auth Proxy, PID 4174282.

| ID | Time (EDT) | Operation | Consumer | Effect | Result | Cost |
|---|---|---|---|---|---|---|
| O-044 | 08:02:07 – 08:02:08 | `transfer` pilot (native a3eb433): scen-b43ef6a-v1.actual-inputs-v1 → `gs://…-research-inputs/fews-runs/scen-b43ef6a-v1.actual-inputs-v1/` | target | **write: 6 objects** | 6/6 verified, 19,955,548 bytes; generations 1792152127189112 … 1792152128753516. Receipts: `g8-g9-data-load/transfer-pilot/` (sha256 15f957f1…). Pre-a524e51 receipts lack `bucket`, so they are subject to the final `--verify` | storage (reserved) |
| O-045 | 08:07:17 – 08:11:52 | `load_mlflow_stores` (native b97ddcd), as `mlflow_app`: MLflow 3.17 initializers created the fresh schemas, then `copy_store` and a separate `--verify-only` | target | **write: tables in DBs `mlflow`, `mlflow_auth`** | **Tracking:** source sha256 54aa6898… (= snapshot r1); revision dc11669786a5; 64 tables, 361,026 rows; copy complete 187.45 s; verify: every table's source digest equals its target digest. **Auth:** source 3797d7d0… (= r1); revision f1a2b3c4d5e6; 11 tables, 10 rows; complete and verified. Every cloud target digest also equals the local rehearsal r3 target digest. No credential appears in the reports (scrubbed; DSN without password). Reports: `g8-g9-data-load/mlflow-store-load/` | instance hours (reserved) |

## G9 — Cloud Run staging service (2026-10-16)

Ledger, before deployment: `G9-cloud-run-research-mlflow-2026-10`, USD 8.41 (recurring Cloud Run lines of the quote; the one-time package-acceptance lines, USD 1.47, are reserved at acceptance). Platform committed USD 55.17.

| ID | Time (EDT) | Operation | Consumer | Effect | Result | Cost |
|---|---|---|---|---|---|---|
| O-046 | 08:20:44 – 08:21:07 | `gcloud run deploy research-mlflow …` (design settings incl. `--allow-unauthenticated`) | target | none | **argument error before any request**: `--set-env-vars` dict syntax (comma inside the allowed-hosts value). Nothing created (`g9-service-staging/deploy-attempt1-argerror.err`) | none |
| O-047 | ≈08:21:30 | the same deploy with `^;^` env-var delimiter, still `--allow-unauthenticated` | — | **not executed** | **Rejected by the Claude Code auto-mode permission classifier** (category "TLS/Auth Weaken": the allUsers `run.invoker` binding). Not retried through any other wrapper or tool. Per supervisor: this is a permission-gate rejection for that specific IAM action, not a lack of general scoped authorization; the public-invoker step is held for explicit user approval after staging tests | none |
| O-048 | 08:22:03 – 08:23:45 | `gcloud run deploy research-mlflow` with **`--no-allow-unauthenticated`**; image `service@sha256:280013b0…`; SA research-mlflow; min 0 / max 1, concurrency 8, 1 vCPU / 2 GiB, request-based CPU, no startup boost, timeout 3600 s; Cloud SQL `research-pg`; secrets backend/auth URI `:1`, Flask secret `:1`, KEK `:1`; env artifacts destination `gs://…-research-artifacts/mlflow-artifacts`, `MLFLOW_BASIC_AUTH_FAIL_CLOSED=true`, allowed hosts `research-mlflow-76571749286.us-central1.run.app,127.0.0.1:8080,localhost:8080` | target | **write: Cloud Run service + revision 00001** | revision `research-mlflow-00001-j88` **failed to start**. Launcher ok (deny mode, hook active), then MLflow `No module named 'psycopg'`: SQLAlchemy 2.1.4 maps a bare `postgresql://` URI to psycopg v3, and the image ships psycopg2 only. The provisioner had composed the URI secrets without the driver; the local rehearsal had used `postgresql+psycopg2://`. Complete logs: `rev00001.logs.json` | instance seconds (reserved) |
| O-049 | 08:25:30 – 08:25:48 | `rebind_uri_secrets` (native 0624d03): addVersion on `mlflow-backend-uri`, `mlflow-auth-db-uri` | target | **write: secret version 2 ×2** | each new value composed in-process from `sql-mlflow-app` with the corrected template; the old value had to differ by the driver only; read-back equal. No value printed (`uri-rebind-receipt.json`). Regression a408376: `create_engine` on the generated templates resolves the installed psycopg2 | secret ops (reserved) |
| O-050 | 08:25:57 – 08:26:57 | redeploy, same settings, URI secrets pinned `:2` | target | **write: revision 00002** | `research-mlflow-00002-gbm` ready, 100% traffic. Startup probe passed at 12:26:55 UTC; deny mode; MLflow security middleware with the three allowed hosts. Service IAM policy has **no bindings** (no allUsers). URLs: `https://research-mlflow-76571749286.us-central1.run.app` (in allowed hosts) and legacy `https://research-mlflow-357xpe2jva-uc.a.run.app` (not in allowed hosts). Readback `service-describe.json`, `service-iam.json`, logs `rev00002.logs.json` | instance seconds (reserved) |
| O-051 | ≈08:28 – 08:31:15 (three runs; final report 08:31:15) | `staging_access` (native 344a857): operator identity token in `X-Serverless-Authorization` (never printed) | target | read | **19/19** (`access-iam-staging.json`): no token → 403 from Cloud Run IAM (no Basic challenge); with token and no / wrong Basic credentials → 401 with MLflow's Basic challenge on tracking, registry, artifact list, a real copied artifact (proxied and `/get-artifact`), Gateway endpoints and chat, assistant config, user creation and `/version`; `/health` 200. Legacy host: tracking 403 (host check); `/health` 200 and `/version` 401, which are exempt from the host check by design (`security_utils.HEALTH_ENDPOINTS`). **Observed upstream property:** the proxied artifact routes are a native FastAPI router (`fastapi_app.py:294`), outside the Flask host-check hook (Flask is mounted last at `/`, line 304), with their own FastAPI Basic-auth gate (`auth/__init__.py:5099`). On the legacy host they return 401 (Basic challenge), not 403: content is not exposed, but there is no DNS-rebinding host check on that router. The expectation was corrected with this evidence after the first run's 18/19; no host enforcement was added to the application. **IAM-protected staging only; this is not AC4.** Principal-positive rows (owner / reader / job writer / assistant) are pending | requests (reserved) |

## G9 — data staging, continued

| ID | Time (EDT) | Operation | Consumer | Effect | Result | Cost |
|---|---|---|---|---|---|---|
| O-052 | 08:04:23 – running | driver `ledger/transfer/run-all.sh` (PID 25168): mlflow-artifacts, packages, inputs, 28 FEWS roots | target | **write: objects (create-only)** | mlflow-artifacts 3,569/3,569 verified (08:06:44); packages 15,477/15,477 verified, 12,578,866,404 bytes (08:23:12). **inputs stage FAILED** at the builder before any upload: `fewsnet.feature_schema` has `local_status="local (non-DrvFS)"`, which the a524e51 builder rejects (it accepted only exact `"local"`). The inventory survey found 111 `local` and 12 `local (non-DrvFS)` entries, all match True or `"no_recorded_value"` (6). FEWS roots continue. **Not complete; the per-source final `--verify` is pending** | storage + Class A ops (reserved) |
| O-053 | 08:32:31 – running | inputs only, from a separate pinned worktree (`control-plane-inputs-fix`, commit 42fa33f, transfer.py blob 2b6dfc7a; the driver's checkout is untouched): explicit `LOCAL_STATUSES` and match basis (True requires recorded = actual hash and size; `"no_recorded_value"` requires no recorded hash; anything else is refused; no string truthiness); `--expect-files 122` | target | **write: objects (create-only)** | running. Expected 122 objects / 14,870,642,559 bytes. The inventory's `unique_file_count` 121 counts distinct content: two shapefile `.cpg` sidecars in different bundles hold identical 5-byte content | storage (reserved) |
| O-054 | 08:43:18 – 09:23:58 | inputs retry 2 (worktree 760e763, transfer.py blob def1f09: 16 MiB resumable requests, (60, 600) s timeouts, error-cause capture; workers 4) | target | **write: objects (create-only)** | 30/30 previously failed inputs verified (14,541,853,359 bytes, including the multi-GB files); 92 resumed after fresh identity checks. **All 122 declared inputs now hold verified receipts; the final fresh `--verify` is pending.** Root cause of the first-run RetryErrors: **hypothesis only** (per-request timeout under a shared uplink). The first receipts lack a cause; supporting evidence is the size correlation, these successful retries and the clean large-file snapshot transfers | storage (reserved) |
| O-055 | 08:50:58 – 09:01:29 | training snapshots `features-h03-v2` (6 files) and `fews-features-h4-2019-02-ff90981` (5) → `gs://…-research-inputs/training-snapshots/…`, from fresh preservation manifests whose hashes equal each manifest role's sha256 | target | **write: 11 objects** | 6/6 and 5/5 verified (192,294,655 + 175,626,598 bytes) | storage (reserved) |
| O-056 | 08:42:28 – 08:47:44 | `crane` (isolated temporary DOCKER_CONFIG with a short-lived token; removed after) for the 5 images by digest: `crane digest`, `crane manifest`, `crane config`, `crane export` → rootfs | target | read (AR egress; ledger `G9-ar-pulls-workstation` 0.84) | Every remote digest equals the build record, and every saved manifest's sha256 equals its digest. Exports exit 0 / tar 0. The rootfs identity rests on the exact-digest export chain; no filesystem digest is computed | AR egress (reserved) |
| O-057 | 08:48:34 – 09:03:35 | `images.rootfs_replay` (native 9a04ded) in a bubblewrap sandbox: image entries read-only as `/`, image Env, UID 65534, no network, only packages (ro) and output bound; the probe shows no `/mnt/c`, no host home, image loader/libc/modules | local | none (no cloud call) | **223/223**: training-ipcch 28, training-fews 53, replay-x320 86, replay-forecast-x320 56; 97,928 rows. Reconciled independently under the 4a0080c freshness gate (`reconciliation.json`): every report is fresh and binds the current package.json. Receipts are preserved in `g9-image-replays-9a04ded/` (SHA256SUMS). This is local exact-image-bits evidence, not cloud download evidence | none |
| O-058 | 09:10:56 | `temp_admin create` (native de1a116; user ruling: temporary migration admin) | target | **write: secret `mlflow-temp-admin` (v1, task labels, no accessors) + MLflow user `ipcch-migration-admin` (admin)** | Created through MLflow 3.17's auth store as mlflow_app. Diff: exactly one admin added, the 2 copied users (`admin` owner, `assistant`) unchanged; the credential authenticates. `[redacted]` in the receipt is this username (scrubbed with the JSON value). Removal after acceptance is guarded (e0a18d7) | secret version (reserved) |
| O-059 | 09:12:36 | `mlflow_identities` through the loopback IAM proxy (`deploy.iam_proxy`; `gcloud run services proxy` refused to install an SDK component, so it was not used): created `ipcch-jobwriter`, `ipcch-reader`, `ipcch-assistant` from their secrets, then `workspace_roles.apply` (rehearsed invocation, copied `assistant` as `assistant_user`) | target | **write: 3 MLflow users, roles `ipcch-readers` / `ipcch-job-writers` and assignments** | Preservation proof: copied users and roles unchanged. Added: READ on experiment/registered_model/prompt `*` for ipcch-reader, ipcch-assistant and the copied `assistant`; workspace USE for ipcch-jobwriter. **G10 open item:** the applier allows a single assistant identity, and the copied principal holds it | requests |
| O-060 | 09:13 | `cloud_access` through the loopback proxy | target | **write: acceptance experiment `cloud-acceptance-access-matrix` (id 6) + run** | 33/33 (`cloud-access-matrix.json`). Its denied delete probes targeted copied experiment 1 (all 403, no change). Later runs target the acceptance experiment only | requests |
| O-061 | 09:15 – 09:21; 09:24:49 – 09:30:21 | `feature_list_map` dry/apply/rerun (temp admin, proxy) | target | **write: 56 `card.feature_list.cloud` logged-model tags** | First attempt: `logged-models/search` HTTP 500, which Cloud Run logged as "Response size was too large" (32 MiB). Logged models carry all their metrics (84,487 rows; ~43.8 MB for experiment 4 in one page). The SDK retry loop was stopped. Fix 600a932: pages of 5. Then dry rc 0 (172/56/116, 0 refused), apply rc 0 (56 written; apply.json sha 0374bfba…), rerun rc 0 (0 written). Keyed rows equal the rehearsal | requests |
| O-062 | 09:31:07 – 09:31:24 | **user-approved single IAM change:** `gcloud run services add-iam-policy-binding research-mlflow --region=us-central1 --member=allUsers --role=roles/run.invoker` (project/billing pinned) | target | **write: service IAM binding** | Before: no bindings (etag BwZd9EUtxZc=). After: exactly `allUsers` → `roles/run.invoker` (etag BwZd9S4qhd4=). No project-level or other-service change. The earlier O-047 auto-mode rejection was disclosed before approval | none |
| O-063 | 09:33 – 09:34 | direct HTTPS checks, no Google identity, no proxy: `staging_access --direct` and `cloud_access` (native 7f09313) | target | **write: acceptance run (experiment 6)** | Anonymous **17/17**: /health 200; every content route 401 with the Basic challenge; wrong credentials 401; legacy host: tracking 403 (host check), artifact router 401 (upstream property, O-051). Principals **32/32**: job writer in the acceptance experiment and denied on copied experiment 1; reader/assistant read the copied run and artifact (sha256 = r1) with every write/escalation 403, the delete/write probes only on the acceptance experiment; admin lists users | requests |
