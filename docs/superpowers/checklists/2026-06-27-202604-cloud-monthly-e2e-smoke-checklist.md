# 202604 Cloud Monthly E2E Smoke Checklist

Use this checklist before running the first live `2026-04` cloud monthly E2E
smoke. It is an operator readiness checklist, not a replacement for Speckit
source-of-truth artifacts.

## Scope Lock

- [ ] Feature month is `2026-04`.
- [ ] Run id is unique and disposable, for example `smoke-202604-YYYYMMDD-HHMM`.
- [ ] This run is Cloud monthly E2E v1, not inference-only.
- [ ] Only EVI is automatically collected/extracted in v1.
- [ ] FLDAS, VIIRS/nightlight, GOSIF-GPP, ACLED API replacement, and WFP
  automation are excluded from this smoke.

## IAM and Admin Gate

- [ ] Active account is `weilun.shi@cgiar.org` or the intended deployer.
- [ ] Active project is `food-crisis-modeling`.
- [ ] Active/default smoke region is `us-central1`.
- [ ] `run.googleapis.com` is enabled.
- [ ] `batch.googleapis.com` is enabled.
- [ ] `artifactregistry.googleapis.com` is enabled.
- [ ] `cloudbuild.googleapis.com` is enabled if image build/push uses Cloud
  Build.
- [ ] `compute.googleapis.com` is enabled for Batch-managed compute resources.
- [ ] `earthengine.googleapis.com` is enabled for project-backed EVI export.
- [ ] `aiplatform.googleapis.com` is enabled.
- [ ] `storage.googleapis.com` is enabled.
- [ ] Deployer can push to the Artifact Registry runtime repository.
- [ ] Deployer can deploy or update the Cloud Run Job.
- [ ] Deployer can execute the Cloud Run Job.
- [ ] Deployer or Cloud Run service account can submit Cloud Batch jobs.
- [ ] Deployer or Cloud Run service account can submit Vertex AI custom jobs.
- [ ] Required identities have `iam.serviceAccountUser` pass permission for only
  the declared runtime service accounts.
- [ ] Operator can inspect Cloud Run, Batch, and Vertex AI logs.
- [ ] Required APIs are enabled before IAM errors are diagnosed.
- [ ] Earth Engine project access is confirmed for the Batch service account.

## Cost Guardrail

- [ ] One-month smoke only.
- [ ] Batch machine type is explicitly chosen and bounded.
- [ ] Vertex AI custom-job machine type is explicitly chosen and bounded.
- [ ] GEE export timeout is bounded.
- [ ] Batch timeout is bounded.
- [ ] Vertex AI custom-job timeout is bounded.
- [ ] Retry count follows the v1 max-retry policy.
- [ ] Budget alert or manual billing watch is in place before the full smoke.

## Input Manifest

- [ ] Manifest URI is `gs://.../input_manifest.json`.
- [ ] `feature_month` is `2026-04`.
- [ ] `run_id` matches the planned smoke run id.
- [ ] Provider is `gcp`.
- [ ] Runtime image fields use digest-pinned `@sha256:` references.
- [ ] Cloud Run, Batch, and Vertex AI service accounts are split and declared.
- [ ] Scaffold artifact for `2026-04` is declared with generation/checksum or
  approved waiver.
- [ ] Source panel artifact is declared with generation/checksum or approved
  waiver.
- [ ] Fixed/slow features artifact is declared with generation/checksum or
  approved waiver.
- [ ] Geometry artifact with canonical `area_id` is declared with
  generation/checksum or approved waiver.
- [ ] GEE EVI config covers `2026-04-01` through `2026-05-01`.
- [ ] Model package URI and immutable version/checksum/generation are declared.
- [ ] Vertex custom-job output root equals the run inference prefix.

## Image and Deployment

- [ ] Local deterministic checks have passed before image build.
- [ ] Docker image was built from the intended git commit.
- [ ] Image was pushed to Artifact Registry.
- [ ] Repo digest was captured after push.
- [ ] Manifest and deployment values use the digest, not a mutable tag.
- [ ] Cloud Run Job uses the intended image and service account.
- [ ] Cloud Run Job arguments are limited to `feature_month`, `run_id`,
  `input_manifest_uri`, and optional approved reference sample or release mode.

## Live Run

- [ ] Cloud Run Job starts successfully.
- [ ] Run prefix is acquired once under `runs/{run_id}/`.
- [ ] Cloud Batch job is submitted.
- [ ] GEE export manifest appears under `runs/{run_id}/gee_exports/`.
- [ ] EVI extraction artifacts appear under `runs/{run_id}/evi/`.
- [ ] Monthly assembly artifacts appear under `runs/{run_id}/assembly/`.
- [ ] Base input validation report appears under `runs/{run_id}/qa/`.
- [ ] Vertex AI custom-job manifest appears under `runs/{run_id}/inference/`.
- [ ] Prediction CSVs for `0m`, `6m`, and `12m` appear under
  `runs/{run_id}/inference/`.
- [ ] Release step report appears under `runs/{run_id}/release/`.
- [ ] Terminal run summary appears under `runs/{run_id}/run_summary.json`.

## Gated Smoke and Manual Review

- [ ] `IPCCH_GCP_SMOKE_ENABLED` is set only for the live smoke run.
- [ ] All required `IPCCH_GCP_*` environment variables point to the same project,
  region, run id, input manifest, Cloud Run Job, and release manifest.
- [ ] Gated smoke test passes.
- [ ] `run_summary.json.status` is `released`.
- [ ] `released/202604/release_manifest.json` is present and current.
- [ ] Release manifest references base input, summary, predictions, EVI/GEE
  evidence, Vertex AI job manifest, inference report, model package, checksums,
  and validation status.
- [ ] No unexpected FLDAS, VIIRS/nightlight, GOSIF-GPP, ACLED automation, WFP
  automation, model training, maps, sheets, delivery package, or local
  workstation scoring output is present.

## Failure Handling

- [ ] If failure occurs before run-prefix acquisition, inspect Cloud Run logs and
  confirm no run prefix was modified.
- [ ] If failure occurs after run-prefix acquisition, inspect
  `runs/{run_id}/run_summary.json` and named report artifacts.
- [ ] If Batch fails, inspect GEE/EVI reports and Batch logs before retrying.
- [ ] If Vertex fails, inspect `vertex_ai_job_manifest.json`,
  `inference_report.json`, and `inference_error.json` if present.
- [ ] If release conflicts, keep the previous release manifest authoritative and
  preserve the failed run evidence.
