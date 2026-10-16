# Cloud deployment plan G6-G9: exact resources, grants and secret handling (executor, 2026-10-16)

This file is the review artifact for the G6 gate ("exact grants and secret handling review"). Gates G10 (Gemini) and G11 (Vertex jobs) follow it.

## Conventions

- **Pinning.** Every command pins `--project=food-crisis-modeling-enso --billing-project=food-crisis-modeling-enso --quiet`. No global gcloud configuration is changed.
- **Receipts and ledger.** Each operation gets a receipt row in `cloud-operations.md` (O-031 onward). Each paid resource is admitted in the operator ledger (`research_cloud/cost/ledger.py`; pools `platform` / `training`) before creation, using the quote line it corresponds to (`quote-3aec3ab` as amended at native 6d4a9b6).
- **Region.** `us-central1` for everything except Gemini, which uses the `global` endpoint.
- **Shared project.** The Earth Engine workload and bucket `food-crisis-modeling-enso-han` are never touched.

## G6: identities, grants, secrets

### Service accounts

No account is project Editor/Owner, and no default service account is used. The default compute SA (Editor, auto-created at G5) is flagged in `cloud-operations.md`; none of our workloads runs as it.

| SA | Used by | Grants (exact scope) |
|---|---|---|
| `research-build@food-crisis-modeling-enso.iam.gserviceaccount.com` | Cloud Build (`serviceAccount:` in cloudbuild.yaml) | `roles/artifactregistry.writer` on repo `us-central1/research`; `roles/logging.logWriter` (project); `roles/storage.objectViewer` on the dedicated build-staging bucket `food-crisis-modeling-enso-research-build` (us-central1, 7-day delete lifecycle; used via `--gcs-source-staging-dir`) instead of the default US multi-region `_cloudbuild` bucket |
| `research-mlflow@…` | Cloud Run service runtime | `roles/cloudsql.client` (project; the project has one instance); `roles/storage.objectUser` on bucket `…-research-artifacts` only; `roles/secretmanager.secretAccessor` on each service secret listed below, secret-level. **G10 only:** custom role `researchGeminiInvoker` (`aiplatform.endpoints.predict` only) |
| `research-trainer@…` | Vertex CustomJob/HPT runtime | `roles/storage.objectViewer` on `…-research-inputs`; `roles/storage.objectCreator` on `…-research-artifacts` (create-only: trial outputs are written once, never overwritten or deleted); `roles/secretmanager.secretAccessor` on `mlflow-jobwriter` only; `roles/logging.logWriter` (project) |

Notes on the grants:
- **The operator** (the user account) submits builds and jobs, which requires `iam.serviceAccounts.actAs` on these SAs; it already holds it as project owner. It imports SQL through the Cloud SQL Auth Proxy with its own IAM identity. No authorized networks.
- **Image pulls** come from the same project's Artifact Registry: by the Cloud Run service agent (`run.serviceAgent`), and by the Vertex custom-code service agent, which gets `roles/artifactregistry.reader` on the repo at G11 (the agent is created on first Vertex use).

### Secrets

User-managed replication in `us-central1`.

- **How values are made.** Values are generated locally with `secrets.token_urlsafe(48)`, or composed from generated DB passwords. They are piped straight to `gcloud secrets versions add --data-file=-`; they are never printed, logged, or written to files or evidence.
- **Database users** are created with the same generated passwords inside one process.
- **Admin.** The admin and the existing invited users keep their migrated basic-auth credentials (copied auth store), so no new admin secret is created.

| Secret | Contents | Accessors |
|---|---|---|
| `mlflow-backend-uri` | postgresql URI for DB `mlflow`, user `mlflow_app` | research-mlflow |
| `mlflow-auth-db-uri` | postgresql URI for DB `mlflow_auth`, user `mlflow_app` | research-mlflow |
| `mlflow-flask-secret` | Flask secret (stable across revisions) | research-mlflow |
| `mlflow-kek-passphrase` | Gateway KEK passphrase (stable) | research-mlflow |
| `mlflow-assistant-credentials` | READ-only assistant basic-auth identity (used only when armed, G10) | research-mlflow |
| `guard-dsn` | DSN of DB `guard` (assistant spend/admission ledger), user `guard_app` | research-mlflow |
| `mlflow-jobwriter` | job-writer basic-auth identity (workspace USE) | research-trainer |
| `mlflow-reader` | read-only acceptance identity | operator only (no SA) |

## G7: buckets and image repository

| Resource | Settings |
|---|---|
| `gs://food-crisis-modeling-enso-research-inputs` | us-central1, Standard, uniform bucket-level access, public access prevention enforced, default soft delete (7 days), no versioning. Holds the declared inputs, the FEWS run archive (all 27 roots + top-level files) and training snapshots, under immutable names with sha256 manifests. |
| `gs://food-crisis-modeling-enso-research-artifacts` | Same settings. Holds the MLflow artifact root (`mlflow-artifacts:/` proxy destination, the copied tree with IDs preserved), packages and trial outputs. |
| Artifact Registry `us-central1/research` (docker) | Images by digest. No cleanup policy that could delete digests referenced by accepted packages or jobs. |

**Transfer verification** (amended after supervisor review):
- **Local pass.** One fresh read of every local file computes sha256, md5 and crc32c together. The sha256 must equal the frozen preservation/inventory manifest before the file is uploaded; manifest hashes reused from the exact-hash cache are not trusted here. Bytes or size that drifted from the manifest are rejected, never uploaded.
- **Upload.** Upload is per object, with `x-goog-if-generation-match=0` (never overwrite). The manifest sha256 is attached as declared metadata (`x-goog-meta-sha256`).
- **Cloud check.** The object's server-computed md5 and crc32c must then equal the locally computed values.
- **Receipt.** Each object's receipt records path, bytes, the local sha256/md5/crc32c, the cloud md5/crc32c and the object generation. The metadata sha256 is called declared, never cloud-computed. Originals and user inputs are only read.

## G8: Cloud SQL

The instance is `research-pg`:
- Enterprise, PostgreSQL 16, `db-g1-small`, zonal, us-central1;
- SSD 30 GB, storage auto-increase OFF;
- automated daily backups with 7 retained, point-in-time recovery OFF;
- public IP for the Cloud SQL connector/Auth Proxy only: **no authorized networks**, SSL mode ENCRYPTED_ONLY;
- deletion protection ON.

Databases and users:

| Database | Purpose | Users |
|---|---|---|
| `research` | inputs, PostGIS | `research_import` (operator import), `research_read` |
| `mlflow` | tracking store | `mlflow_app` |
| `mlflow_auth` | auth store | `mlflow_app` |
| `guard` | assistant ledger | `guard_app` |

Loading:
- **MLflow stores:** `research_cloud.mlflow_migrate.copy_store` from frozen snapshot r1, the same rehearsed procedure. Then workspace roles (`service/workspace_roles.py`), then the URI mapping (`feature_list_map --apply`) through the deployed service.
- **Research inputs:** `sqlimport.load_inputs` and `load_geometry` against the cloud DB through the Auth Proxy. The reconciliation and capacity record are repeated on the cloud instance (receipts; nothing is assumed from the local rehearsal).

## Historical replay images (supervisor coverage check)

The training images cover only the x300 runtimes: geoxgb 28 + fews 29 + popv1 24 = 81 of 223 packages. Two more pinned Linux replay images, built from the locally tested environments, cover the rest:

| Image | Lock | Packages |
|---|---|---|
| `replay-x320` | exact freeze of `rt-ipcchgeo-x320` (NumPy 2.4.4, pandas 3.0.3, xgboost 3.2.0, scikit-learn 1.8.0, scipy 1.18.1) | ipcchgeo 70 + AlphaEarth 16 |
| `replay-forecast-x320` | exact freeze of `rt-forecast-x320` (NumPy 2.3.5, pandas 3.0.3, xgboost 3.2.0, scikit-learn 1.9.0, scipy 1.17.1) | forecasting 56 |

- **AlphaEarth caveat.** AlphaEarth's dependency declaration omits scipy, and its original runtime had scipy 1.17.1, while the tested Linux environment has 1.18.1. Its record says "replayed in the tested Linux environment", not "identical to the original environment".
- **Pre-build verification.** Each lock is verified in a fresh venv (pip check plus sample replays of each family) before its build. Storage, pulls and builds for the five images are in the revised quote.

## G9: images, data staging, service

- **Images.** For each image, the build context is assembled at the final HEAD (`images/context.py --image-uri … --build-sa research-build@…`). Then `gcloud builds submit --config cloudbuild.yaml`: build, then the in-image self-check as UID 65534, then push. Digests are recorded, and each image is pulled to WSL with `crane` and its digest verified.
- **Data staging** follows the G7 manifests.
- **Cloud Run service.** `research-mlflow`, with the image by digest and SA `research-mlflow`:
  - min 0 / max 1 instances, concurrency 8, 1 vCPU / 2 GiB, request-based CPU;
  - Cloud SQL connection `food-crisis-modeling-enso:us-central1:research-pg`; secrets as environment variables from Secret Manager (latest pinned version);
  - assistant in deny mode until G10.

  Ingress is all, and unauthenticated invocation is allowed at IAM level so MLflow clients can reach the basic-auth challenge (design line 101). MLflow basic auth (fail-closed) authenticates every content, download and API route; only the content-free health route is anonymous.

  Acceptance is the access matrix (owner, reader, job writer, anonymous), plus artifact, dataset, logged-model and assistant routes.

## Cost admission

Before each paid resource is created, it is reserved in the platform pool at its quote line's monthly amount; one-time lines are reserved once. Training jobs are reserved per `vertex_reservation` before submission and held until the provider reports a terminal status.
