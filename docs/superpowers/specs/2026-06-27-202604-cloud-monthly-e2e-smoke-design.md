# 202604 Cloud Monthly E2E Smoke Design

Status: approved execution design
Date: 2026-06-27

## Purpose

This design defines the first live GCP smoke for the IPCCH cloud monthly E2E
pipeline. The pilot month is `2026-04` because it is the first currently
complete model-input month. The smoke proves the cloud orchestration and release
contract before later data-source automation work expands beyond EVI.

The smoke is not an inference-only shortcut. It exercises the v1 Cloud monthly
E2E path:

1. Cloud Run Job orchestration.
2. Cloud Batch GEE EVI export and rasterio extraction.
3. Monthly base input assembly using cloud-produced EVI plus manifest-declared
   scaffold, source panel, fixed/slow features, geometry, and model package.
4. Vertex AI custom-job inference.
5. Release staging and `released/202604/release_manifest.json` publication.

## Current Scope

Current v1 automates EVI collection and extraction only. Other source families
remain manifest-provided cloud inputs.

In scope:

- one `feature_month=2026-04` smoke run
- unique run id, for example `smoke-202604-YYYYMMDD-HHMM`
- digest-pinned single repository image in Artifact Registry
- split Cloud Run, Cloud Batch, and Vertex AI service accounts
- GEE EVI export and rasterio EVI extraction
- monthly base input assembly and validation
- Vertex AI custom-job inference using the fixed launch model package
- release manifest validation and manual artifact inspection

Out of scope for this smoke:

- FLDAS automatic extraction
- VIIRS/nightlight automatic extraction
- GOSIF-GPP automatic extraction
- ACLED API replacement
- WFP upload automation
- model training
- prediction maps, sheets, or full delivery package publication
- treating a smoke pass as final production readiness

## Future Automation Direction

The intended later end state is a fuller cloud E2E pipeline where most inputs
are cloud-produced:

- FLDAS automatic collection and extraction becomes a future remote-sensing
  worker or worker step.
- VIIRS/nightlight automatic collection and extraction becomes a future
  remote-sensing worker or worker step.
- ACLED is replaced by a cloud tabular ingestion step.
- WFP remains manually uploaded unless a reliable source contract becomes
  available.

Those future steps must be added through later specs or accepted scope changes.
They do not authorize changes to the current v1 smoke.

## Deferred Post-Smoke Architecture Notes

Record these administrator discussion points for design after the live E2E
smoke, not for the current smoke implementation:

- Consider moving durable pipeline inputs and outputs from GCS object contracts
  into BigQuery tables. The current smoke still uses GCS for manifests,
  immutable run evidence, model package references, and release manifests so
  that the existing E2E contract can be tested first.
- Consider splitting the cloud pipeline into two explicit stages:
  data collection/process/assemble, then inference/model execution. The current
  smoke keeps one orchestrated E2E path to prove EVI auto-processing, monthly
  assembly, Vertex inference, and release semantics before changing stage
  boundaries.
- Treat `https://github.com/IFPRI/MTI-GOOGLE-FOOD-CRISIS-DATA.git` as the
  intended data collection/process/assemble repository and
  `https://github.com/IFPRI/MTI-GOOGLE-FOOD-CRISIS-MODEL.git` as the intended
  inference/model repository after the smoke. The current code and artifacts
  are still mixed, so the post-smoke split should replace the old mixed
  artifacts with the cloud scripts and artifacts proven by the smoke instead of
  assuming either target repo is already cleanly structured.

These changes need a follow-up spec after the E2E smoke result is available,
because they affect artifact contracts, ownership boundaries, retry semantics,
and likely repository layout.

## Execution Design

The smoke should run only after permissions and cost guardrails are ready.

1. Confirm GCP project, region, and required project APIs. For the current
   project, use `food-crisis-modeling` and `us-central1`.
2. Confirm bucket, Artifact Registry repo, and service account names.
3. Ask the administrator for missing IAM permissions before attempting the full
   run.
4. Build the repository Docker image, push it to Artifact Registry, and record
   the immutable `@sha256:` digest.
5. Create the `2026-04` input manifest in GCS. The manifest must use `gs://`
   inputs only and must record immutable checksums, generations, versions, or
   explicit waivers.
6. Execute the Cloud Run Job with `feature_month=2026-04`, the unique run id,
   and the input manifest URI.
7. Run the gated smoke validator with explicit `IPCCH_GCP_*` environment
   variables.
8. Manually inspect Cloud Run, Batch, Vertex AI, GCS run evidence, release
   evidence, and unexpected-output absence.

## Readiness Check on 2026-07-02

Initial observations from `gcloud` using account `weilun.shi@cgiar.org`:

- Project `food-crisis-modeling` is active and visible.
- Region was switched from `us-east1` to `us-central1`.
- Enabled API listing showed `aiplatform.googleapis.com` and
  `storage.googleapis.com`.
- Cloud Run Admin API returned `SERVICE_DISABLED` for `run.googleapis.com`.
- Batch API returned `SERVICE_DISABLED` for `batch.googleapis.com`.
- Artifact Registry API returned `SERVICE_DISABLED` for
  `artifactregistry.googleapis.com`.
- `gcloud config set compute/region us-central1` succeeded, but validation was
  skipped because `compute.googleapis.com` is not enabled.
- IAM policy, bucket listing, and service-account listing checks returned
  permission-denied errors, so specific resource names and pass-permission
  coverage remain unverified.

After user approval, the required project APIs were enabled successfully:
Cloud Run, Batch, Artifact Registry, Cloud Build, Compute Engine, Earth Engine,
Vertex AI, and Cloud Storage. A follow-up enabled-service check listed all
required APIs.

Current post-API status:

- Batch job listing in `us-central1` succeeds and returns no existing jobs.
- Artifact Registry repository listing in `us-central1` succeeds and returns no
  existing repositories.
- Vertex AI custom-job listing in `us-central1` succeeds and returns no
  existing jobs.
- Cloud Run Job listing now reaches the API but fails with missing
  `run.jobs.list`.
- Bucket listing still fails with missing `storage.buckets.list`.
- Service account listing still fails with missing `iam.serviceAccounts.list`.
- Project IAM policy inspection still fails with missing `getIamPolicy`.

Conclusion: the project API gate is now passed. The implementation is ready to
move into live GCP smoke preparation, but the full EVI auto-process plus Vertex
inference smoke still needs Cloud Run IAM and either exact pre-created bucket,
Artifact Registry repository, and service-account names or permission to list
and create them.

## Permission Gate

Known user-held roles are not sufficient for the full smoke unless the project
already grants equivalent permissions through service accounts or inherited IAM.

Project APIs that must be enabled before diagnosing IAM:

- Cloud Run Admin API: `run.googleapis.com`
- Batch API: `batch.googleapis.com`
- Artifact Registry API: `artifactregistry.googleapis.com`
- Cloud Build API: `cloudbuild.googleapis.com`
- Compute Engine API: `compute.googleapis.com`
- Earth Engine API: `earthengine.googleapis.com`
- Vertex AI API: `aiplatform.googleapis.com`
- Cloud Storage API: `storage.googleapis.com`

Likely deployer/admin-required permissions:

- Artifact Registry Writer on the runtime image repository.
- Batch Jobs Editor on the project or constrained Batch scope.
- IAM Service Account User on the Cloud Run, Batch, and Vertex AI service
  accounts that the user or Cloud Run Job must pass.
- Logging Viewer for Cloud Run, Batch, and Vertex AI inspection.
- Service Usage Admin only if required APIs are not already enabled.

Runtime service account boundaries:

- Cloud Run service account can read the manifest, write run/release evidence,
  submit and inspect Batch jobs, submit and inspect Vertex AI custom jobs, and
  pass only the declared Batch and Vertex service accounts.
- Batch service account can pull the digest-pinned image, use the Earth Engine
  project for EVI, read declared GCS inputs, and write declared GEE/EVI/log
  prefixes.
- Vertex AI service account can pull the digest-pinned image, read the base
  input and model package, and write declared inference/log prefixes.

## Cost Guardrail

The first smoke should use constrained runtime settings:

- one pilot month only: `2026-04`
- one unique run id
- small Cloud Batch machine type unless rasterio memory proves insufficient
- bounded GEE export timeout
- bounded Batch timeout
- bounded Vertex AI custom-job timeout
- max retry policy from the active Speckit v1 defaults
- budget alert or manual billing watch before the full smoke

If permissions are incomplete, stop at build/push or manifest/preflight steps
that do not create long-running Batch or Vertex jobs.

## Acceptance Criteria

The smoke is accepted only when all of the following are true:

- Cloud Run Job exits successfully.
- `runs/{run_id}/run_summary.json` has terminal status `released`.
- Cloud Batch EVI evidence exists and has passing reports.
- Assembly output and base input validation report exist and pass.
- Vertex AI prediction CSVs, job manifest, and inference report exist and pass.
- Forbidden side-effect scan passes.
- `released/202604/release_manifest.json` exists and is the stable entry point.
- Manual inspection finds no unexpected FLDAS, VIIRS/nightlight, GOSIF-GPP,
  ACLED automation, WFP automation, model training, maps, sheets, or local
  workstation scoring outputs.

## Open Risks

- Live Earth Engine authorization for the Batch service account is not yet
  proven.
- IAM may block Artifact Registry push, Batch submission, service account
  passing, Vertex custom-job submission, or log inspection.
- Live GCP smoke has not yet been executed.
- Cost is expected to be modest for a single month, but the first run must use
  timeout and retry limits to prevent runaway cloud usage.
