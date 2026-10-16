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
