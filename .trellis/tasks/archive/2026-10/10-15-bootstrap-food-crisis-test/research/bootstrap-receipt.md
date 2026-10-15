# Bootstrap receipt — 2026-10-15

Project `feisty-flames-511718-d4` (display name `food-crisis-modeling-test`, number 968355701450), region `us-central1`. Executed by `weilun.shi@cgiar.org` (Owner) through gcloud configuration `food-crisis-test`; the `default` configuration (`manuel-remote-sensing`) and global ADC quota project were not changed.

## Resources

| Kind | Name | Notes |
|---|---|---|
| APIs | run, batch, compute, workflows, workflowexecutions, eventarc, pubsub, storage, artifactregistry, earthengine, iam, logging | 12/12 enabled |
| Service account | `monthly-runtime@…` | Run + Batch runtime |
| Service account | `monthly-workflow@…` | Workflow + Eventarc |
| Bucket | `gs://food-crisis-test-ipcch-data` | US-CENTRAL1, uniform access, versioning on |
| Bucket | `gs://food-crisis-test-ipcch-requests` | US-CENTRAL1, uniform access, versioning on |
| Artifact Registry | `us-central1/monthly-delivery` (docker) | |
| Image | `…/monthly-delivery/runtime:accepted-october` | digest `sha256:7e6133f32ab0b28d3f29b827d4153975e99f97d440e97a1a8cdacdfa1052f0d0` (crane v0.22.1 copy; equals source `runtime:cp5-confidence-1`) |
| Run job | `monthly-prepare` | 2 CPU / 8 GiB, 4h, digest-pinned image, runtime SA |
| Run job | `oct-delivery` | 8 CPU / 32 GiB, 4h, output `gs://food-crisis-test-ipcch-data`, namespace `monthly-staging` |
| Workflow | `oct-delivery-trigger` | ACTIVE, workflow SA |
| Eventarc | `oct-delivery-requests` | storage finalized on requests bucket -> workflow; first attempt failed on Eventarc service-agent propagation, succeeded on retry ~5 min later |

Untouched pre-existing bucket: `historical_input_data_from_dropbox`.

## IAM (read back after apply)

- runtime SA, project: `batch.jobsEditor`, `batch.agentReporter`, `logging.logWriter`, `serviceusage.serviceUsageConsumer`, `earthengine.writer`
- runtime SA, both buckets: `storage.objectAdmin`; AR repo: `artifactregistry.reader`
- runtime SA policy: `iam.serviceAccountUser` for runtime SA and workflow SA
- workflow SA, project: `eventarc.eventReceiver`, `workflows.invoker`; `oct-delivery` job: `run.developer`
- storage service agent `service-968355701450@gs-project-accounts…`: `pubsub.publisher`

**Deviation from OPERATIONS.md:** `roles/earthengine.resourceViewer` does not exist (`gcloud iam roles describe` -> not found; grant rejected). Granted `roles/earthengine.writer` instead: the runtime submits `ee.batch.Export.image.toCloudStorage` (needs `earthengine.exports.create`) and the accepted source runner `oct-delivery-runner@manuel-remote-sensing` holds exactly this role. OPERATIONS.md line 41 still names the non-existent role.

## Earth Engine

`GET earthengine.googleapis.com/v1/projects/feisty-flames-511718-d4/config` -> `REGISTERED_NOT_COMMERCIALLY` (operator registered, Contributor tier). User-credential query on the project works (MOD13A3 2026 latest = 2026-08). Runtime-SA EE access **not directly verified**: impersonation needs `iam.serviceAccounts.getAccessToken`, which Owner lacks; not granted (out of scope).

## Baseline init

- venv `~/.venvs/ipcch-cloud-operator` (Python 3.12.3) from `requirements.lock.txt` (sha256 `2f0a7251…`, equals baseline binding), `pip check` clean.
- Config `~/ipcch-operator/food-crisis-test/project.json` (copy: `project.json`), work_dir `operator-state/`.
- Preview: 74 files, 6 models, pass. Execute: 10m55s, exit 0 (`init-execute.log`).
- `baseline_id` `95111230975434f14258eac6c46a2525f527e7ee8ad8c1e14eb22033115d9884` = sha256 of `bootstrap/baseline.json`.
- Verification: 74/74 refs exist at recorded generation with size and sha256 equal to `baseline.json` (3,721,587,245 bytes); 6 models published (fewsnet `local-202604-57cb3b981198-510375f58cd8/{0,6,12}m`, ipcch `launch_2026_04_production_safe/scope_{0,6,12}m`); 15/15 diagnostics available. Copy: `initialized.json`.

No monthly run, scoring or delivery was executed.
