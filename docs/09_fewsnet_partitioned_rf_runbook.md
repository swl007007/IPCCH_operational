# FEWSNET Partitioned RF Model Suite Runbook

This is the operator contract for the three-horizon FEWSNET partitioned random
forest suite. It covers the one-time bootstrap, immutable snapshot staging,
digest-pinned image and deployment configuration, candidate validation,
production promotion, recovery, revision runs, and acceptance evidence.

The suite uses exactly one Vertex AI Custom Job, three stable parent models,
three candidate Model Versions, and three exact-version Batch Prediction Jobs.
It does not create an online Vertex Endpoint. Never mix this suite's objects
with the existing IPCCH model or release roots.

## 1. Safety rules and prerequisites

- Run commands from the repository root at the exact implementation commit.
- Never overwrite the raw assembled FEWSNET panel. Normalization must write a
  versioned CSV and a matching audit JSON to new paths.
- Runtime inputs must be immutable `gs://` objects. Local panel and shapefile
  paths are bootstrap inputs only.
- Use only `docker/Dockerfile.fewsnet-partitioned-rf` and the repository root as
  its build context.
- Use a digest-pinned image URI. Tags are build conveniences, not deployment
  identities.
- `released/current.json` is authoritative and is written only after all three
  candidate outputs and aliases validate.
- Do not manually move one production alias or overwrite one release pointer.
  The repository promotion boundary coordinates all three horizons and rolls
  back partial alias changes.
- A live smoke must use a dedicated test project. Its retained candidate
  versions must not share the production parent models.

Start with a strict shell and define environment-specific values without adding
them to the repository:

```bash
set -euo pipefail

export PROJECT_ID="your-production-project"
export REGION="us-central1"
export ARTIFACT_BUCKET="your-fewsnet-artifact-bucket"
export OBJECT_STORE_ROOT_URI="gs://${ARTIFACT_BUCKET}/fewsnet_partitioned_rf"
export AR_REPOSITORY="fewsnet"
export IMAGE_NAME="fewsnet-partitioned-rf"

export ORCHESTRATOR_SA="fewsnet-orchestrator@${PROJECT_ID}.iam.gserviceaccount.com"
export TRAINING_SA="fewsnet-training@${PROJECT_ID}.iam.gserviceaccount.com"
export BATCH_SA="fewsnet-batch@${PROJECT_ID}.iam.gserviceaccount.com"
export SUBMITTER_MEMBER="user:operator@example.org"

export FEWSNET_RAW_PANEL_PATH="/operator-selected/input/assembled_fewsnet.csv"
export FEWSNET_BOUNDARIES_PATH="/operator-selected/input/fewsnet_admin.shp"
export FEWSNET_LOCAL_STAGE_ROOT="/operator-selected/output/fewsnet-bootstrap"

export SOURCE_GIT_COMMIT="$(git rev-parse HEAD)"
[[ "$SOURCE_GIT_COMMIT" =~ ^[0-9a-f]{40}$ ]]
mkdir -p "$FEWSNET_LOCAL_STAGE_ROOT"

gcloud auth list --filter=status:ACTIVE --format='value(account)'
gcloud config set project "$PROJECT_ID"
gcloud config set ai/region "$REGION"
```

The raw panel and boundary paths above are examples of operator-supplied
variables. Do not put workstation-specific source paths into code, Docker
configuration, deployment manifests, or recurring commands.

The first IAM bootstrap and image push use the authorized human or CI
administrator named by `SUBMITTER_MEMBER`. That administrator is not the
runtime orchestration identity. Before any snapshot GCS write, Python cloud
client, candidate smoke, or production run, complete the impersonation setup
and two-principal preflight in section 5. In an already provisioned
environment, perform that preflight immediately after this section.

## 2. Build and push the shared image by digest

Preflight the Docker daemon before attempting a build:

```bash
docker version
docker info
```

If either command reports no daemon or disabled WSL integration, stop. Do not
change the Dockerfile or requirements to work around an unavailable daemon.

Build the exact implementation commit, run the training help smoke, push the
tag, and resolve the immutable registry digest:

```bash
export IMAGE_REPOSITORY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPOSITORY}/${IMAGE_NAME}"
export IMAGE_TAG="${IMAGE_REPOSITORY}:${SOURCE_GIT_COMMIT}"

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

docker build \
  --build-arg "SOURCE_GIT_COMMIT=${SOURCE_GIT_COMMIT}" \
  -f docker/Dockerfile.fewsnet-partitioned-rf \
  -t "$IMAGE_TAG" .

docker run --rm "$IMAGE_TAG" \
  python3 -m fewsnet_partitioned_rf_pipeline.cli.train --help

docker push "$IMAGE_TAG"

export IMAGE_DIGEST="$(
  gcloud artifacts docker images describe "$IMAGE_TAG" \
    --project="$PROJECT_ID" \
    --format='value(image_summary.digest)'
)"
[[ "$IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]] || {
  echo "invalid Artifact Registry digest: $IMAGE_DIGEST" >&2
  exit 1
}
export IMAGE_URI="${IMAGE_REPOSITORY}@${IMAGE_DIGEST}"
printf 'IMAGE_URI=%s\nIMAGE_DIGEST=%s\n' "$IMAGE_URI" "$IMAGE_DIGEST"
```

`SOURCE_GIT_COMMIT` is baked into `FEWSNET_SOURCE_GIT_COMMIT`. The deployment
manifest must use that same 40-character commit and the exact digest URI.

## 3. Normalize without overwriting the raw panel

Create versioned output names, preserve the raw checksum, and invoke the
repository normalization CLI:

```bash
export BOOTSTRAP_VERSION="${SOURCE_GIT_COMMIT:0:12}-$(date -u +%Y%m%dT%H%M%SZ)"
export NORMALIZED_PANEL="${FEWSNET_LOCAL_STAGE_ROOT}/assembled_fewsnet.normalized-${BOOTSTRAP_VERSION}.csv"
export NORMALIZATION_AUDIT="${FEWSNET_LOCAL_STAGE_ROOT}/assembled_fewsnet.normalized-${BOOTSTRAP_VERSION}.audit.json"

test -f "$FEWSNET_RAW_PANEL_PATH"
test -f "$FEWSNET_BOUNDARIES_PATH"
test "$FEWSNET_RAW_PANEL_PATH" != "$NORMALIZED_PANEL"
test ! -e "$NORMALIZED_PANEL"
test ! -e "$NORMALIZATION_AUDIT"

export RAW_PANEL_SHA256_BEFORE="$(sha256sum "$FEWSNET_RAW_PANEL_PATH" | awk '{print $1}')"

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m \
  fewsnet_partitioned_rf_pipeline.cli.normalize_panel \
  --input-panel "$FEWSNET_RAW_PANEL_PATH" \
  --output-panel "$NORMALIZED_PANEL" \
  --audit-output "$NORMALIZATION_AUDIT" \
  | tee "${FEWSNET_LOCAL_STAGE_ROOT}/normalize-${BOOTSTRAP_VERSION}.json"

export RAW_PANEL_SHA256_AFTER="$(sha256sum "$FEWSNET_RAW_PANEL_PATH" | awk '{print $1}')"
test "$RAW_PANEL_SHA256_BEFORE" = "$RAW_PANEL_SHA256_AFTER"

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - \
  "$NORMALIZATION_AUDIT" "$NORMALIZED_PANEL" <<'PY'
from pathlib import Path
import sys

from fewsnet_partitioned_rf_pipeline.core.normalization import (
    validate_normalization_audit,
)

audit = validate_normalization_audit(Path(sys.argv[1]), Path(sys.argv[2]))
print(audit["output_panel"]["sha256"])
PY
```

The normalization audit is part of snapshot identity. A cleaned panel without
its exact audit is not a valid runtime input.

## 4. Prove local staging, then stage the immutable GCS snapshot

First run the real `stage_snapshot` boundary against `LocalArtifactStore`.
This validates the normalized CSV, audit, local shapefile, normalized
boundaries, area universe, row counts, CRS, and content identity without a GCP
write:

```bash
export CREATED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export LOCAL_OBJECT_STORE="${FEWSNET_LOCAL_STAGE_ROOT}/local-object-store-${BOOTSTRAP_VERSION}"
export LOCAL_STAGE_EVIDENCE_JSON="${FEWSNET_LOCAL_STAGE_ROOT}/local-stage-${BOOTSTRAP_VERSION}.json"

NORMALIZED_PANEL="$NORMALIZED_PANEL" \
NORMALIZATION_AUDIT="$NORMALIZATION_AUDIT" \
FEWSNET_BOUNDARIES_PATH="$FEWSNET_BOUNDARIES_PATH" \
CREATED_AT_UTC="$CREATED_AT_UTC" \
LOCAL_OBJECT_STORE="$LOCAL_OBJECT_STORE" \
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY' \
  | tee "$LOCAL_STAGE_EVIDENCE_JSON"
from dataclasses import asdict
import json
import os
from pathlib import Path

from fewsnet_partitioned_rf_pipeline.core.data import stage_snapshot
from fewsnet_partitioned_rf_pipeline.vertex.storage import LocalArtifactStore

manifest = stage_snapshot(
    panel_path=Path(os.environ["NORMALIZED_PANEL"]),
    normalization_audit_path=Path(os.environ["NORMALIZATION_AUDIT"]),
    boundaries_path=Path(os.environ["FEWSNET_BOUNDARIES_PATH"]),
    destination_root="gs://local-preflight/fewsnet_partitioned_rf",
    store=LocalArtifactStore(os.environ["LOCAL_OBJECT_STORE"]),
    created_at_utc=os.environ["CREATED_AT_UTC"],
)
evidence = {
    "schema_version": "fewsnet-local-stage-evidence-v1",
    "store_type": "LocalArtifactStore",
    "destination_root": "gs://local-preflight/fewsnet_partitioned_rf",
    "duplicate_area_month_gate": "passed",
    "gcp_write_performed": False,
    "manifest": asdict(manifest),
}
print(json.dumps(evidence, indent=2, sort_keys=True))
PY
```

Only after local staging passes and section 5's gcloud/Python impersonation
preflight succeeds, stage the same files to the configured GCS root.
`source_manifest.json` is written last and the CLI prints its URI:

```bash
export SNAPSHOT_STAGE_RESULT="${FEWSNET_LOCAL_STAGE_ROOT}/snapshot-stage-${BOOTSTRAP_VERSION}.json"

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m \
  fewsnet_partitioned_rf_pipeline.cli.stage_snapshot \
  --panel "$NORMALIZED_PANEL" \
  --normalization-audit "$NORMALIZATION_AUDIT" \
  --boundaries "$FEWSNET_BOUNDARIES_PATH" \
  --destination-root "$OBJECT_STORE_ROOT_URI" \
  --created-at-utc "$CREATED_AT_UTC" \
  | tee "$SNAPSHOT_STAGE_RESULT"

export SNAPSHOT_MANIFEST_URI="$(
  .venv/bin/python -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["manifest_uri"])' \
    "$SNAPSHOT_STAGE_RESULT"
)"

gcloud storage objects describe "$SNAPSHOT_MANIFEST_URI" \
  --format='yaml(name,generation,size,updateTime)'
```

The immutable snapshot layout is:

```text
inputs/snapshots/{snapshot_id}/assembled_fewsnet.normalized.csv
inputs/snapshots/{snapshot_id}/panel_normalization_audit.json
inputs/snapshots/{snapshot_id}/admin_boundaries.parquet
inputs/snapshots/{snapshot_id}/admin_universe.csv
inputs/snapshots/{snapshot_id}/source_manifest.json
```

## 5. Service accounts and least-privilege IAM

Create three distinct runtime accounts if they do not already exist:

```bash
gcloud iam service-accounts create fewsnet-orchestrator \
  --project="$PROJECT_ID" --display-name="FEWSNET suite orchestrator"
gcloud iam service-accounts create fewsnet-training \
  --project="$PROJECT_ID" --display-name="FEWSNET suite training worker"
gcloud iam service-accounts create fewsnet-batch \
  --project="$PROJECT_ID" --display-name="FEWSNET suite Batch Prediction"
```

The orchestrator needs only the Vertex operations used by this repository. A
custom role avoids granting Endpoint creation or deployment:

```bash
export ORCHESTRATOR_ROLE_ID="fewsnetOrchestratorV1"
export ORCHESTRATOR_ROLE="projects/${PROJECT_ID}/roles/${ORCHESTRATOR_ROLE_ID}"
export ORCHESTRATOR_PERMISSIONS="aiplatform.batchPredictionJobs.cancel,aiplatform.batchPredictionJobs.create,aiplatform.batchPredictionJobs.get,aiplatform.batchPredictionJobs.list,aiplatform.customJobs.cancel,aiplatform.customJobs.create,aiplatform.customJobs.get,aiplatform.customJobs.list,aiplatform.endpoints.list,aiplatform.models.get,aiplatform.models.list,aiplatform.models.update,aiplatform.models.upload,aiplatform.operations.get"

gcloud iam roles create "$ORCHESTRATOR_ROLE_ID" \
  --project="$PROJECT_ID" \
  --title="FEWSNET orchestrator v1" \
  --description="Submit and reconcile FEWSNET training, model versions, aliases, and Batch jobs; list but never create Endpoints" \
  --permissions="$ORCHESTRATOR_PERMISSIONS" \
  --stage=GA

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${ORCHESTRATOR_SA}" \
  --role="$ORCHESTRATOR_ROLE"
```

Do not grant bucket-wide `roles/storage.objectUser`. Create four narrow custom
roles: exact-object reader, create-only writer, mutable object writer, and
bucket lister. Object replacement requires `storage.objects.delete`; workers
never receive that permission, so their writes remain create-only when the
repository also supplies `if_generation_match=0`.

```bash
export OBJECT_READER_ROLE_ID="fewsnetObjectReaderV1"
export OBJECT_CREATOR_ROLE_ID="fewsnetObjectCreatorV1"
export OBJECT_MUTATOR_ROLE_ID="fewsnetObjectMutatorV1"
export OBJECT_LISTER_ROLE_ID="fewsnetObjectListerV1"

gcloud iam roles create "$OBJECT_READER_ROLE_ID" \
  --project="$PROJECT_ID" \
  --title="FEWSNET exact object reader v1" \
  --permissions="storage.objects.get" \
  --stage=GA
gcloud iam roles create "$OBJECT_CREATOR_ROLE_ID" \
  --project="$PROJECT_ID" \
  --title="FEWSNET create-only object writer v1" \
  --permissions="storage.objects.create" \
  --stage=GA
gcloud iam roles create "$OBJECT_MUTATOR_ROLE_ID" \
  --project="$PROJECT_ID" \
  --title="FEWSNET generation-safe object mutator v1" \
  --permissions="storage.objects.get,storage.objects.create,storage.objects.delete" \
  --stage=GA
gcloud iam roles create "$OBJECT_LISTER_ROLE_ID" \
  --project="$PROJECT_ID" \
  --title="FEWSNET object lister v1" \
  --permissions="storage.objects.list" \
  --stage=GA

export OBJECT_READER_ROLE="projects/${PROJECT_ID}/roles/${OBJECT_READER_ROLE_ID}"
export OBJECT_CREATOR_ROLE="projects/${PROJECT_ID}/roles/${OBJECT_CREATOR_ROLE_ID}"
export OBJECT_MUTATOR_ROLE="projects/${PROJECT_ID}/roles/${OBJECT_MUTATOR_ROLE_ID}"
export OBJECT_LISTER_ROLE="projects/${PROJECT_ID}/roles/${OBJECT_LISTER_ROLE_ID}"
export OBJECT_STORE_PREFIX="${OBJECT_STORE_ROOT_URI#gs://${ARTIFACT_BUCKET}/}"
test "$OBJECT_STORE_PREFIX" != "$OBJECT_STORE_ROOT_URI"
export OBJECT_RESOURCE_BASE="projects/_/buckets/${ARTIFACT_BUCKET}/objects/${OBJECT_STORE_PREFIX}"

export TRAINING_READ_CONDITION="resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/inputs/snapshots/\") || resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/runs/\") || resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/suites/\")"
export TRAINING_CREATE_CONDITION="resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/runs/\") || resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/suites/\")"
export BATCH_RUN_CONDITION="resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/runs/\")"
export ORCHESTRATOR_READ_CONDITION="resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/\")"
export ORCHESTRATOR_MUTATE_CONDITION="resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/inputs/\") || resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/deployments/\") || resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/runs/\") || resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/suites/\") || resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/locks/\") || resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/released/\")"

gcloud storage buckets add-iam-policy-binding "gs://${ARTIFACT_BUCKET}" \
  --member="serviceAccount:${TRAINING_SA}" \
  --role="$OBJECT_READER_ROLE" \
  --condition="expression=${TRAINING_READ_CONDITION},title=fewsnet_training_read_v1,description=Read exact snapshots and retry evidence"
gcloud storage buckets add-iam-policy-binding "gs://${ARTIFACT_BUCKET}" \
  --member="serviceAccount:${TRAINING_SA}" \
  --role="$OBJECT_CREATOR_ROLE" \
  --condition="expression=${TRAINING_CREATE_CONDITION},title=fewsnet_training_create_v1,description=Create run and suite training artifacts only"

gcloud storage buckets add-iam-policy-binding "gs://${ARTIFACT_BUCKET}" \
  --member="serviceAccount:${BATCH_SA}" \
  --role="$OBJECT_READER_ROLE" \
  --condition="expression=${BATCH_RUN_CONDITION},title=fewsnet_batch_read_v1,description=Read exact Batch input objects only"
gcloud storage buckets add-iam-policy-binding "gs://${ARTIFACT_BUCKET}" \
  --member="serviceAccount:${BATCH_SA}" \
  --role="$OBJECT_CREATOR_ROLE" \
  --condition="expression=${BATCH_RUN_CONDITION},title=fewsnet_batch_create_v1,description=Create Batch raw output objects only"

gcloud storage buckets add-iam-policy-binding "gs://${ARTIFACT_BUCKET}" \
  --member="serviceAccount:${ORCHESTRATOR_SA}" \
  --role="$OBJECT_READER_ROLE" \
  --condition="expression=${ORCHESTRATOR_READ_CONDITION},title=fewsnet_orchestrator_read_v1,description=Read suite objects"
gcloud storage buckets add-iam-policy-binding "gs://${ARTIFACT_BUCKET}" \
  --member="serviceAccount:${ORCHESTRATOR_SA}" \
  --role="$OBJECT_MUTATOR_ROLE" \
  --condition="expression=${ORCHESTRATOR_MUTATE_CONDITION},title=fewsnet_orchestrator_mutate_v1,description=Generation-safe suite namespace mutation"
gcloud storage buckets add-iam-policy-binding "gs://${ARTIFACT_BUCKET}" \
  --member="serviceAccount:${ORCHESTRATOR_SA}" \
  --role="$OBJECT_LISTER_ROLE"
```

Cloud Storage evaluates `storage.objects.list` on the bucket rather than on an
individual object resource, so its permission cannot be safely narrowed by an
object-prefix condition. Only `ORCHESTRATOR_SA` receives that unavoidable list
permission; repository code still lists only configured `inputs/`, `runs/`,
and `suites/` prefixes. Training and Batch identities receive neither list nor
delete authority and have no binding covering `locks/` or `released/`.

Grant image-read access on only the runtime repository:

```bash
for service_account in "$ORCHESTRATOR_SA" "$TRAINING_SA" "$BATCH_SA"; do
  gcloud artifacts repositories add-iam-policy-binding "$AR_REPOSITORY" \
    --project="$PROJECT_ID" \
    --location="$REGION" \
    --member="serviceAccount:${service_account}" \
    --role="roles/artifactregistry.reader"
done
```

Grant the human or CI submitter Service Account Token Creator on the
orchestrator identity. This authorizes explicit short-lived impersonation; it
does not make ambient human ADC the runtime identity. Grant
`ORCHESTRATOR_SA` Service Account User on only the training and Batch accounts,
which supplies the `iam.serviceAccounts.actAs` permission required when those
Vertex jobs are submitted:

```bash
gcloud iam service-accounts add-iam-policy-binding "$ORCHESTRATOR_SA" \
  --project="$PROJECT_ID" \
  --member="$SUBMITTER_MEMBER" \
  --role="roles/iam.serviceAccountTokenCreator"

for runtime_account in "$TRAINING_SA" "$BATCH_SA"; do
  gcloud iam service-accounts add-iam-policy-binding "$runtime_account" \
    --project="$PROJECT_ID" \
    --member="serviceAccount:${ORCHESTRATOR_SA}" \
    --role="roles/iam.serviceAccountUser"
done
```

Vertex must mint credentials for the two custom runtime accounts:

```bash
export PROJECT_NUMBER="$(
  gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)'
)"
export VERTEX_SERVICE_AGENT="service-${PROJECT_NUMBER}@gcp-sa-aiplatform.iam.gserviceaccount.com"

for runtime_account in "$TRAINING_SA" "$BATCH_SA"; do
  gcloud iam service-accounts add-iam-policy-binding "$runtime_account" \
    --project="$PROJECT_ID" \
    --member="serviceAccount:${VERTEX_SERVICE_AGENT}" \
    --role="roles/iam.serviceAccountTokenCreator"
done
```

Now switch both command-line and Python default credentials to the same
orchestration principal. `gcloud` uses its impersonation configuration, while
the repository Python clients use the impersonated Application Default
Credentials file:

```bash
gcloud auth application-default login \
  --impersonate-service-account="$ORCHESTRATOR_SA" \
  --scopes="https://www.googleapis.com/auth/cloud-platform"
gcloud config set auth/impersonate_service_account "$ORCHESTRATOR_SA"

export GCLOUD_IMPERSONATION_TARGET="$(
  gcloud config get-value auth/impersonate_service_account 2>/dev/null
)"
export ADC_IMPERSONATION_TARGET="$(
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
import google.auth

credentials, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
print(getattr(credentials, "service_account_email", ""))
PY
)"

test "$GCLOUD_IMPERSONATION_TARGET" = "$ORCHESTRATOR_SA"
test "$ADC_IMPERSONATION_TARGET" = "$ORCHESTRATOR_SA"
gcloud auth print-access-token >/dev/null
gcloud auth application-default print-access-token >/dev/null
printf 'gcloud_principal=%s\nadc_principal=%s\n' \
  "$GCLOUD_IMPERSONATION_TARGET" "$ADC_IMPERSONATION_TARGET"
```

Do not continue if either target differs. All later `gcloud storage`, Vertex,
registry, Batch, alias, smoke, and production commands must run under this
preflighted impersonation state.

If the image repository is in a different project, grant Artifact Registry
Reader there to the relevant Google-managed Vertex/Cloud Run service agents as
well. Do not compensate with project Owner or Editor.

## 6. Create and publish an immutable deployment manifest

The schema requires the three stable model IDs. On the first successful
registration, Vertex creates each parent and assigns the first numeric version;
later runs add versions under the same parents.

```bash
export DEPLOYMENT_BUILD_RESULT="${FEWSNET_LOCAL_STAGE_ROOT}/deployment-build-${SOURCE_GIT_COMMIT:0:12}.json"

PROJECT_ID="$PROJECT_ID" \
REGION="$REGION" \
OBJECT_STORE_ROOT_URI="$OBJECT_STORE_ROOT_URI" \
ORCHESTRATOR_SA="$ORCHESTRATOR_SA" \
TRAINING_SA="$TRAINING_SA" \
BATCH_SA="$BATCH_SA" \
IMAGE_URI="$IMAGE_URI" \
IMAGE_DIGEST="$IMAGE_DIGEST" \
SOURCE_GIT_COMMIT="$SOURCE_GIT_COMMIT" \
FEWSNET_LOCAL_STAGE_ROOT="$FEWSNET_LOCAL_STAGE_ROOT" \
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY' \
  | tee "$DEPLOYMENT_BUILD_RESULT"
import hashlib
import json
import os
from pathlib import Path

from fewsnet_partitioned_rf_pipeline.schemas import validate_deployment

deployment = {
    "schema_version": "fewsnet-deployment-v1",
    "project_id": os.environ["PROJECT_ID"],
    "region": os.environ["REGION"],
    "object_store_root_uri": os.environ["OBJECT_STORE_ROOT_URI"],
    "orchestrator_service_account": os.environ["ORCHESTRATOR_SA"],
    "training_service_account": os.environ["TRAINING_SA"],
    "batch_prediction_service_account": os.environ["BATCH_SA"],
    "container_image_uri": os.environ["IMAGE_URI"],
    "container_image_digest": os.environ["IMAGE_DIGEST"],
    "source_git_commit": os.environ["SOURCE_GIT_COMMIT"],
    "parent_model_ids": {
        "0m": "fewsnet-partitioned-rf-0m",
        "6m": "fewsnet-partitioned-rf-6m",
        "12m": "fewsnet-partitioned-rf-12m",
    },
    "training_machine_type": "n2-highmem-8",
    "batch_machine_type": "n2-standard-4",
    "training_timeout_seconds": 21600,
    "batch_timeout_seconds": 28800,
    "max_retries": 2,
}
validate_deployment(deployment)
canonical_payload = json.dumps(
    deployment,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
config_sha256 = hashlib.sha256(canonical_payload).hexdigest()
deployment_version = (
    f"{deployment['source_git_commit'][:12]}-{config_sha256}"
)
local_path = (
    Path(os.environ["FEWSNET_LOCAL_STAGE_ROOT"])
    / f"deployment-{deployment_version}.json"
)
manifest_uri = (
    f"{deployment['object_store_root_uri'].rstrip('/')}/deployments/"
    f"deployment-{deployment_version}.json"
)
local_path.write_text(
    json.dumps(deployment, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(
    json.dumps(
        {
            "deployment_config_sha256": config_sha256,
            "deployment_version": deployment_version,
            "manifest_local": str(local_path),
            "manifest_uri": manifest_uri,
        },
        indent=2,
        sort_keys=True,
    )
)
PY

export DEPLOYMENT_VERSION="$(
  .venv/bin/python -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["deployment_version"])' \
    "$DEPLOYMENT_BUILD_RESULT"
)"
export DEPLOYMENT_CONFIG_SHA256="$(
  .venv/bin/python -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["deployment_config_sha256"])' \
    "$DEPLOYMENT_BUILD_RESULT"
)"
export DEPLOYMENT_MANIFEST_LOCAL="$(
  .venv/bin/python -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["manifest_local"])' \
    "$DEPLOYMENT_BUILD_RESULT"
)"
export DEPLOYMENT_MANIFEST_URI="$(
  .venv/bin/python -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["manifest_uri"])' \
    "$DEPLOYMENT_BUILD_RESULT"
)"
[[ "$DEPLOYMENT_CONFIG_SHA256" =~ ^[0-9a-f]{64}$ ]]

gcloud storage cp --if-generation-match=0 \
  "$DEPLOYMENT_MANIFEST_LOCAL" "$DEPLOYMENT_MANIFEST_URI"
gcloud storage objects describe "$DEPLOYMENT_MANIFEST_URI" \
  --format='yaml(name,generation,size,updateTime)'
```

`DEPLOYMENT_CONFIG_SHA256` is the canonical digest of the complete validated
deployment payload, not only the Git/image pair. Do not overwrite a deployment
manifest. Any image, commit, IAM identity, parent ID, machine type, timeout, or
retry-policy change produces a different object version and URI.

## 7. Run candidate validation and the optional live GCP smoke

For a manual candidate-only run against an explicit immutable snapshot:

```bash
FEWSNET_SOURCE_GIT_COMMIT="$SOURCE_GIT_COMMIT" \
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m \
  fewsnet_partitioned_rf_pipeline.cli.run_latest \
  --deployment-manifest-uri "$DEPLOYMENT_MANIFEST_URI" \
  --snapshot-manifest-uri "$SNAPSHOT_MANIFEST_URI" \
  --candidate-only
```

`--candidate-only` calls `run_latest(..., promote=False)`. It retains three
candidate Model Versions for diagnosis, but does not read or move production
aliases and does not write `released/current.json`.

The checked-in live smoke adds exact job/version/row/Endpoint assertions. Its
deployment manifest must point to a dedicated test project and non-production
artifact root:

```bash
export FEWSNET_GCP_SMOKE_ENABLED=1
export FEWSNET_GCP_DEPLOYMENT_MANIFEST_URI="gs://dedicated-test-bucket/fewsnet_partitioned_rf/deployments/test.json"
export FEWSNET_GCP_TEST_SNAPSHOT_MANIFEST_URI="gs://dedicated-test-bucket/fewsnet_partitioned_rf/inputs/snapshots/test/source_manifest.json"

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_gcp_smoke.py \
  -q -p no:cacheprovider -s
```

Before constructing any Google client, the smoke requires both manifest values
to be trimmed canonical `gs://bucket/nonempty-object` URIs with no query or
fragment; the snapshot must end in `/source_manifest.json`. It then validates
the deployment, resolves the checked-out repository `HEAD` as exactly forty
lowercase hexadecimal characters, requires that value to equal the deployment
`source_git_commit`, and only then sets `FEWSNET_SOURCE_GIT_COMMIT` for the
direct `run_latest` call. A malformed URI is skipped locally, and a source
identity mismatch fails before any Vertex job submission. Without
`FEWSNET_GCP_SMOKE_ENABLED=1` and both manifest URIs, the live test is an
explicit skip while its local contract tests still run. Do not point this test
at the production project.

## 8. Run the latest production suite

Only after the live smoke is approved, allow `run_latest` to discover the
latest complete `source_manifest.json` and promote all three horizons:

```bash
export RUN_RESULT="${FEWSNET_LOCAL_STAGE_ROOT}/run-latest-$(date -u +%Y%m%dT%H%M%SZ).json"

FEWSNET_SOURCE_GIT_COMMIT="$SOURCE_GIT_COMMIT" \
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m \
  fewsnet_partitioned_rf_pipeline.cli.run_latest \
  --deployment-manifest-uri "$DEPLOYMENT_MANIFEST_URI" \
  | tee "$RUN_RESULT"

export RUN_STATUS="$(
  .venv/bin/python -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["status"])' \
    "$RUN_RESULT"
)"
export RUN_ID="$(
  .venv/bin/python -c \
    'import json,sys; print(json.load(open(sys.argv[1])).get("run_id", ""))' \
    "$RUN_RESULT"
)"
printf 'status=%s\nrun_id=%s\n' "$RUN_STATUS" "$RUN_ID"
```

Expected terminal statuses are `RELEASED` for a new accepted suite or `NOOP`
for byte-identical current content. `FAILED` requires recovery before another
production attempt.

For a same-month source revision with a different snapshot content digest, use
an explicit lowercase revision ID:

```bash
export REVISION_ID="corrected-input"
FEWSNET_SOURCE_GIT_COMMIT="$SOURCE_GIT_COMMIT" \
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m \
  fewsnet_partitioned_rf_pipeline.cli.run_latest \
  --deployment-manifest-uri "$DEPLOYMENT_MANIFEST_URI" \
  --revision-id "$REVISION_ID"
```

The revision ID must match `^[a-z0-9][a-z0-9-]{0,31}$`. A byte-identical
restage is a no-op and does not need a revision ID.

## 9. Locate run, model, prediction, and release artifacts

For a successful non-noop run, the immutable paths are:

```text
runs/{run_id}/run_manifest.json
runs/{run_id}/input_snapshot_ref.json
runs/{run_id}/inputs/selected_source_manifest.json
runs/{run_id}/training/custom_job.json
runs/{run_id}/training_job_result.json
runs/{run_id}/training_threshold_report.json
runs/{run_id}/registry/{0m,6m,12m}.json
runs/{run_id}/batch_prediction/{0m,6m,12m}/input.jsonl
runs/{run_id}/batch_prediction/{0m,6m,12m}/raw/...
runs/{run_id}/predictions/{0m,6m,12m}.csv
suites/{suite_version}/models/{0m,6m,12m}/...
suites/{suite_version}/training_threshold_report.json
suites/{suite_version}/predictions/{0m,6m,12m}.csv
suites/{suite_version}/suite_manifest.json
released/{feature_month}/production_suite_manifest.json
released/current.json
```

`input_snapshot_ref.json` is the canonical generation-bound pointer containing
the selected source-manifest `ObjectRef`, snapshot ID, and snapshot content
digest. `inputs/selected_source_manifest.json` is the immutable byte-for-byte
copy of that exact source manifest placed inside the run namespace. Acceptance
must read the pointer's recorded generation and prove the copy equals those
source-manifest bytes; neither file substitutes for the other.

Inspect a run without changing cloud state:

```bash
gcloud storage ls --recursive "${OBJECT_STORE_ROOT_URI}/runs/${RUN_ID}/"
gcloud storage cat "${OBJECT_STORE_ROOT_URI}/runs/${RUN_ID}/run_manifest.json" \
  | .venv/bin/python -m json.tool
gcloud storage cat "${OBJECT_STORE_ROOT_URI}/runs/${RUN_ID}/training_threshold_report.json" \
  | .venv/bin/python -m json.tool
gcloud storage cat "${OBJECT_STORE_ROOT_URI}/released/current.json" \
  | .venv/bin/python -m json.tool
```

Vertex assigns numeric Model Version IDs such as `@1` or `@27`; the operator
must never invent them. Each `registry/{horizon}.json`, `run_manifest.json`, and
`suite_manifest.json` records the exact returned numeric resource name. The
deterministic suite alias carries the immutable suite identity across the three
parents; the manifests remain authoritative even if a low-cardinality Vertex
label is shortened.

## 10. Interpret thresholds and fallback counts

`training_threshold_report.json` contains:

- `horizon_thresholds`: threshold, precision, recall, F1, support, positive
  cases, and any threshold fallback reason for each horizon.
- `cluster_states`: the trained/fallback state of clusters `0` through `16`.
- `smote_results`: whether SMOTE was applied, skipped, or failed per cluster.
- `fallback_counts`: cluster-level counts by fallback reason.

The threshold grid is `0.05` through `0.95` at `0.01` increments. A non-null
`fallback_reason` explains use of the recorded fallback threshold, including
the permitted `0.50` default when the validation slice cannot support a normal
selection. Do not replace a recorded threshold operationally.

The formal prediction CSVs expose row-level `prediction_source`. Count those
values separately from the cluster-level training report:

```bash
gcloud storage cat "${OBJECT_STORE_ROOT_URI}/runs/${RUN_ID}/predictions/0m.csv" \
  | .venv/bin/python -c \
    'import sys,pandas as pd; f=pd.read_csv(sys.stdin); print(f["prediction_source"].value_counts(dropna=False).sort_index().to_string()); print("rows", len(f))'
```

The allowed row routes are `partition_model`, `pooled_unmapped`,
`pooled_small_partition`, `pooled_single_class`, and
`pooled_missing_partition_model`. Their counts must sum to the snapshot area
count for every horizon. Pooled fallback is expected model behavior, not an
infrastructure failure.

## 11. Recovery and rollback

Always inspect `error.json`, `run_manifest.json`, the exact Vertex resource,
and `released/current.json` before retrying.

### Training failure

- No registration should start until all three packages and the aggregate
  threshold report validate.
- Inspect `runs/{run_id}/training/custom_job.json`, the Custom Job state/logs,
  and `runs/{run_id}/error.json`.
- Fix the external cause and start a new `run_latest`. Deterministic operation
  identity reconciles an ambiguous submit and refuses duplicate matching jobs.

### Candidate registration failure

- Batch Prediction and promotion must not start.
- Versions registered earlier in the failed attempt are retained and labelled
  `abandoned` when they are definitively non-production.
- Inspect `runs/{run_id}/registry/` and the exact numeric Model Version. Never
  attach `production` manually to an abandoned version.

### Batch Prediction or output-validation failure

- No production alias may move and `released/current.json` must remain
  unchanged.
- Inspect the exact job names in `run_manifest.json`, retained raw output, and
  normalized CSV evidence. Fix the source/model/runtime cause and launch a new
  suite; do not switch a failed job to an alias or different source snapshot.

### Alias rollback or pointer conflict

- Partial alias movement is rolled back in reverse horizon order before the
  prior production pointer can change.
- `PromotionBusy` means another non-expired 900-second lease owns promotion;
  inspect `locks/production-promotion.json` and wait for or resolve that owner.
- `PromotionIndeterminate`, a rollback failure, or an unreadable pointer is a
  stop condition. Do not move aliases or overwrite pointers by hand. Preserve
  all evidence and reconcile the authoritative cloud state first.

Read-only recovery checks:

```bash
gcloud storage objects describe \
  "${OBJECT_STORE_ROOT_URI}/locks/production-promotion.json" \
  --format='yaml(name,generation,size,updateTime)'
gcloud storage objects describe \
  "${OBJECT_STORE_ROOT_URI}/released/current.json" \
  --format='yaml(name,generation,size,updateTime)'
```

Verify the current `production` alias on all three parents without moving it:

```bash
PROJECT_ID="$PROJECT_ID" REGION="$REGION" \
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
import os
from google.cloud import aiplatform

project = os.environ["PROJECT_ID"]
region = os.environ["REGION"]
aiplatform.init(project=project, location=region)
for model_id in (
    "fewsnet-partitioned-rf-0m",
    "fewsnet-partitioned-rf-6m",
    "fewsnet-partitioned-rf-12m",
):
    parent = f"projects/{project}/locations/{region}/models/{model_id}"
    info = aiplatform.ModelRegistry(parent).get_version_info("production")
    print(model_id, info.version_id, sorted(info.version_aliases or ()))
PY
```

## 12. Prove that no online Endpoint exists

This suite is Batch-only. In a dedicated FEWSNET project/region, the following
must print `endpoint_count=0` before smoke, after smoke, and after production
acceptance:

```bash
export ENDPOINT_AUDIT="${FEWSNET_LOCAL_STAGE_ROOT}/vertex-endpoints-$(date -u +%Y%m%dT%H%M%SZ).json"
gcloud ai endpoints list \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format=json >"$ENDPOINT_AUDIT"

.venv/bin/python - "$ENDPOINT_AUDIT" <<'PY'
import json
import sys

endpoints = json.load(open(sys.argv[1], encoding="utf-8"))
print(f"endpoint_count={len(endpoints)}")
assert endpoints == [], "FEWSNET project/region must contain no online Endpoint"
PY
```

The live smoke additionally snapshots the Endpoint inventory before
`run_latest` and asserts that it is unchanged afterward.

## 13. Initial production acceptance gate

Run this gate only after the candidate smoke is approved. Record immutable
URIs, generations, checksums, job/model resource names, row counts, and the
operator identity for every item.

1. The raw panel checksum before and after normalization is identical.
2. The normalized panel has exactly `1,120,728` rows and `5,718` areas; its
   audit records two duplicate groups and two removed rows.
3. The audit permits only derived-only-compatible duplicate collapse and its
   output checksum/row count match the staged panel.
4. The duplicate area-month hard gate passes and the LocalArtifactStore
   staging command completes without any GCP write.
5. The selected source manifest is the approved immutable snapshot and names
   the exact normalization-audit generation.
6. The fixed partition SHA-256 is
   `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
7. Exactly one succeeded Custom Job produces all three packages.
8. Exactly three new numeric Vertex Model Versions exist under the expected
   stable parents.
9. All three versions use the deployment image digest and exact artifact URI.
10. Exactly three exact-version Batch Prediction Jobs succeed.
11. Each `0m`, `6m`, and `12m` CSV has `5,718` unique areas.
12. Local composite-predictor, local container, and Vertex Batch predictions
    agree on the approved fixed sample.
13. Probabilities, classes, routes, threshold identity, and row-level fallback
    totals pass the suite validator.
14. No Vertex Endpoint, map, workbook, or future-target performance artifact
    exists.
15. The three `production` aliases and suite manifest name the same suite.
16. `released/current.json` points to that immutable suite manifest and has an
    update time no earlier than the suite and feature-month pointer objects.

The approved fixed-sample parity run must write
`FEWSNET_FIXED_SAMPLE_PARITY_JSON` with schema
`fewsnet-fixed-sample-parity-v1`, the suite/snapshot/image identities, a
64-character `sample_sha256`, a `probability_tolerance` no larger than
`1e-12`, and exact `0m`/`6m`/`12m` entries containing the numeric model-version
resource, compared row count, local-versus-container and local-versus-Vertex
maximum probability deltas, and both class-mismatch counts. The verifier below
rejects missing or self-inconsistent evidence.

Run this single read-only verifier under the preflighted impersonation state.
It performs no create, update, alias, job, Endpoint, or pointer operation and
exits nonzero on any missing or inconsistent acceptance item:

```bash
export FEWSNET_FIXED_SAMPLE_PARITY_JSON="/operator-selected/output/fewsnet-fixed-sample-parity.json"

: "${FEWSNET_RAW_PANEL_PATH:?}"
: "${RAW_PANEL_SHA256_BEFORE:?}"
: "${NORMALIZED_PANEL:?}"
: "${NORMALIZATION_AUDIT:?}"
: "${LOCAL_STAGE_EVIDENCE_JSON:?}"
: "${FEWSNET_FIXED_SAMPLE_PARITY_JSON:?}"
: "${DEPLOYMENT_MANIFEST_URI:?}"
: "${OBJECT_STORE_ROOT_URI:?}"
: "${RUN_RESULT:?}"
: "${RUN_ID:?}"
: "${PROJECT_ID:?}"
: "${REGION:?}"
: "${ORCHESTRATOR_SA:?}"
test "$GCLOUD_IMPERSONATION_TARGET" = "$ORCHESTRATOR_SA"
test "$ADC_IMPERSONATION_TARGET" = "$ORCHESTRATOR_SA"

# BEGIN FEWSNET_PRODUCTION_ACCEPTANCE_VERIFIER
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

import google.auth
import pandas as pd
from google.api_core.client_options import ClientOptions
from google.cloud import aiplatform, aiplatform_v1, storage

from fewsnet_partitioned_rf_pipeline.config import (
    PARTITION_ASSET_PATH,
    PARTITION_ASSET_SHA256,
)
from fewsnet_partitioned_rf_pipeline.core.normalization import (
    validate_normalization_audit,
)
from fewsnet_partitioned_rf_pipeline.core.partitions import PartitionMap
from fewsnet_partitioned_rf_pipeline.schemas import (
    validate_deployment,
    validate_payload,
)
from fewsnet_partitioned_rf_pipeline.vertex.storage import GCSArtifactStore


HORIZONS = ("0m", "6m", "12m")
HORIZON_MONTHS = {"0m": 0, "6m": 6, "12m": 12}
PREDICTION_SOURCES = (
    "partition_model",
    "pooled_unmapped",
    "pooled_small_partition",
    "pooled_single_class",
    "pooled_missing_partition_model",
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_OBJECT_TOKENS = (
    "/maps/",
    ".geojson",
    ".gpkg",
    ".shp",
    ".shx",
    ".dbf",
    ".xlsx",
    ".xlsm",
    "future_target",
    "future-target",
    "performance_artifact",
)


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"required environment variable is missing: {name}")
    if value != value.strip():
        raise ValueError(f"environment variable must be trimmed: {name}")
    return value


def load_json_file(path: str, name: str) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must be a JSON object")
    return payload


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_ref(store: GCSArtifactStore, ref: dict, name: str) -> bytes:
    required_fields = {"uri", "generation", "sha256", "size_bytes"}
    if not isinstance(ref, dict) or set(ref) != required_fields:
        raise ValueError(f"{name} ObjectRef fields differ")
    data = store.read_bytes(ref["uri"], generation=ref["generation"])
    if len(data) != ref["size_bytes"]:
        raise ValueError(f"{name} size differs from its ObjectRef")
    if hashlib.sha256(data).hexdigest() != ref["sha256"]:
        raise ValueError(f"{name} checksum differs from its ObjectRef")
    return data


def live_json(store: GCSArtifactStore, uri: str, name: str) -> tuple[dict, dict]:
    ref = vars(store.get_ref(uri))
    payload = json.loads(read_ref(store, ref, name))
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must be a JSON object")
    return payload, ref


def state_name(value: object) -> str:
    name = getattr(value, "name", None)
    return name if isinstance(name, str) and name else str(value).rsplit(".", 1)[-1]


def timestamp(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp is timezone-naive: {value}")
    return parsed.astimezone(timezone.utc)


def object_updated(client: storage.Client, ref: dict) -> datetime:
    parsed = urlsplit(ref["uri"])
    blob = client.bucket(parsed.netloc).blob(
        parsed.path[1:],
        generation=int(ref["generation"]),
    )
    blob.reload()
    if str(blob.generation) != str(ref["generation"]) or blob.updated is None:
        raise ValueError(f"cannot prove object update time: {ref['uri']}")
    return blob.updated.astimezone(timezone.utc)


raw_panel = required_env("FEWSNET_RAW_PANEL_PATH")
raw_sha256_before = required_env("RAW_PANEL_SHA256_BEFORE")
normalized_panel = required_env("NORMALIZED_PANEL")
normalization_audit_path = required_env("NORMALIZATION_AUDIT")
local_stage_path = required_env("LOCAL_STAGE_EVIDENCE_JSON")
parity_path = required_env("FEWSNET_FIXED_SAMPLE_PARITY_JSON")
deployment_uri = required_env("DEPLOYMENT_MANIFEST_URI")
root_uri = required_env("OBJECT_STORE_ROOT_URI").rstrip("/")
run_result_path = required_env("RUN_RESULT")
run_id = required_env("RUN_ID")
project_id = required_env("PROJECT_ID")
region = required_env("REGION")
orchestrator_sa = required_env("ORCHESTRATOR_SA")

credentials, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
if getattr(credentials, "service_account_email", "") != orchestrator_sa:
    raise ValueError("Python ADC does not impersonate ORCHESTRATOR_SA")

store = GCSArtifactStore.from_default()
deployment, deployment_ref = live_json(store, deployment_uri, "deployment")
validate_deployment(deployment)
assert deployment["project_id"] == project_id
assert deployment["region"] == region
assert deployment["object_store_root_uri"].rstrip("/") == root_uri
assert deployment["orchestrator_service_account"] == orchestrator_sa

run_result = load_json_file(run_result_path, "RUN_RESULT")
assert run_result["status"] == "RELEASED"
assert run_result["run_id"] == run_id
run_root = f"{root_uri}/runs/{run_id}"
run_manifest, run_manifest_ref = live_json(
    store,
    f"{run_root}/run_manifest.json",
    "run manifest",
)
validate_payload("run-manifest", run_manifest)
assert run_manifest["phase"] == "RELEASED"
assert run_manifest["status"] == "released"
assert run_manifest["hard_gates"]["outputs_validated"] is True
assert run_manifest["hard_gates"]["promotion_released"] is True

current_uri = f"{root_uri}/released/current.json"
current, current_ref = live_json(store, current_uri, "current pointer")
assert set(current) == {
    "schema_version",
    "suite_version",
    "feature_month",
    "snapshot_content_sha256",
    "suite_manifest",
    "released_at_utc",
}
assert current["schema_version"] == "fewsnet-production-suite-pointer-v1"
suite_manifest = json.loads(
    read_ref(store, current["suite_manifest"], "suite manifest")
)
validate_payload("suite-manifest", suite_manifest)
suite_version = suite_manifest["suite_version"]
assert suite_version == run_manifest["suite_version"] == run_result["suite_version"]
assert current["suite_version"] == suite_version
assert current["feature_month"] == suite_manifest["feature_month"]
assert current["released_at_utc"] == suite_manifest["released_at_utc"]
assert current["snapshot_content_sha256"] == suite_manifest["snapshot_ref"][
    "snapshot_content_sha256"
]
assert suite_manifest["source_git_commit"] == deployment["source_git_commit"]
assert suite_manifest["container_image"] == {
    "uri": deployment["container_image_uri"],
    "digest": deployment["container_image_digest"],
}

month_uri = (
    f"{root_uri}/released/{suite_manifest['feature_month']}/"
    "production_suite_manifest.json"
)
month_pointer, month_ref = live_json(store, month_uri, "month pointer")
assert month_pointer == current

snapshot_ref = suite_manifest["snapshot_ref"]["manifest"]
snapshot_bytes = read_ref(store, snapshot_ref, "source snapshot")
snapshot = json.loads(snapshot_bytes)
validate_payload("source-snapshot", snapshot)
assert snapshot["snapshot_id"] == suite_manifest["snapshot_ref"]["snapshot_id"]
assert snapshot["snapshot_content_sha256"] == current[
    "snapshot_content_sha256"
]
assert snapshot["latest_feature_month"] == suite_manifest["feature_month"]

selected_copy, selected_copy_ref = live_json(
    store,
    f"{run_root}/inputs/selected_source_manifest.json",
    "selected source manifest copy",
)
assert json.dumps(selected_copy, sort_keys=True) == json.dumps(snapshot, sort_keys=True)
assert read_ref(store, selected_copy_ref, "selected source manifest copy") == snapshot_bytes
input_snapshot, input_snapshot_ref = live_json(
    store,
    f"{run_root}/input_snapshot_ref.json",
    "input snapshot reference",
)
assert input_snapshot == {
    "manifest": snapshot_ref,
    "snapshot_id": snapshot["snapshot_id"],
    "snapshot_content_sha256": snapshot["snapshot_content_sha256"],
}

assert SHA256_PATTERN.fullmatch(raw_sha256_before)
assert sha256_file(raw_panel) == raw_sha256_before
normalization_audit = validate_normalization_audit(
    Path(normalization_audit_path),
    Path(normalized_panel),
)
assert json.loads(
    read_ref(store, snapshot["normalization_audit"], "normalization audit")
) == normalization_audit
assert normalization_audit["output_panel"]["sha256"] == snapshot["panel"]["sha256"]
assert normalization_audit["output_panel"]["row_count"] == snapshot["row_count"]
assert normalization_audit["duplicate_group_count"] == 2
assert normalization_audit["duplicate_row_count"] == 4
assert normalization_audit["removed_row_count"] == 2
assert normalization_audit["conflict_group_count"] == 0
assert all(
    group["disposition"] == "collapsed_identical_or_derived_only"
    for group in normalization_audit["duplicate_groups"]
)

normalized_rows = 0
normalized_areas: set[str] = set()
for chunk in pd.read_csv(
    normalized_panel,
    usecols=["FEWSNET_admin_code"],
    dtype={"FEWSNET_admin_code": "string"},
    chunksize=100_000,
):
    normalized_rows += len(chunk)
    normalized_areas.update(chunk["FEWSNET_admin_code"].dropna().astype(str))
assert normalized_rows == snapshot["row_count"] == 1_120_728
assert len(normalized_areas) == snapshot["area_count"] == 5_718

local_stage = load_json_file(local_stage_path, "local-stage evidence")
assert local_stage["schema_version"] == "fewsnet-local-stage-evidence-v1"
assert local_stage["store_type"] == "LocalArtifactStore"
assert local_stage["destination_root"].startswith("gs://local-preflight/")
assert local_stage["duplicate_area_month_gate"] == "passed"
assert local_stage["gcp_write_performed"] is False
local_manifest = local_stage["manifest"]
assert local_manifest["row_count"] == snapshot["row_count"]
assert local_manifest["area_count"] == snapshot["area_count"]
assert local_manifest["snapshot_content_sha256"] == snapshot[
    "snapshot_content_sha256"
]

partition_map = PartitionMap.load(PARTITION_ASSET_PATH, PARTITION_ASSET_SHA256)
assert suite_manifest["partition"]["sha256"] == PARTITION_ASSET_SHA256

client_options = ClientOptions(
    api_endpoint=f"{region}-aiplatform.googleapis.com"
)
job_service = aiplatform_v1.JobServiceClient(client_options=client_options)
model_service = aiplatform_v1.ModelServiceClient(client_options=client_options)
endpoint_service = aiplatform_v1.EndpointServiceClient(
    client_options=client_options
)
parent = f"projects/{project_id}/locations/{region}"

custom_job_evidence, _ = live_json(
    store,
    f"{run_root}/training/custom_job.json",
    "training Custom Job evidence",
)
custom_request = custom_job_evidence["request"]["custom_job"]
custom_name = custom_job_evidence["resource"]["name"]
operation_id = custom_request["labels"]["fewsnet_operation"]
matching_custom_jobs = list(
    job_service.list_custom_jobs(
        request={
            "parent": parent,
            "filter": (
                f'display_name="{custom_request["display_name"]}" '
                f"AND labels.fewsnet_operation={operation_id}"
            ),
        }
    )
)
assert len(matching_custom_jobs) == 1
custom_job = job_service.get_custom_job(request={"name": custom_name})
assert matching_custom_jobs[0].name == custom_job.name == custom_name
assert state_name(custom_job.state) == "JOB_STATE_SUCCEEDED"
assert custom_job.job_spec.service_account == deployment["training_service_account"]
worker = custom_job.job_spec.worker_pool_specs[0]
assert worker.container_spec.image_uri == deployment["container_image_uri"]

training_result, _ = live_json(
    store,
    f"{run_root}/training_job_result.json",
    "training job result",
)
assert set(training_result["packages"]) == set(HORIZONS)
assert training_result["suite_version"] == suite_version
assert training_result["snapshot_id"] == snapshot["snapshot_id"]
assert training_result["snapshot_content_sha256"] == snapshot[
    "snapshot_content_sha256"
]
assert training_result["source_git_commit"] == deployment["source_git_commit"]
assert training_result["container_image_uri"] == deployment["container_image_uri"]
assert training_result["container_image_digest"] == deployment[
    "container_image_digest"
]

training_report, training_report_ref = live_json(
    store,
    f"{run_root}/training_threshold_report.json",
    "training threshold report",
)
validate_payload("training-report", training_report)
assert training_report["suite_version"] == suite_version
suite_training_report_ref = store.get_ref(
    f"{root_uri}/suites/{suite_version}/training_threshold_report.json"
)
assert read_ref(store, vars(suite_training_report_ref), "suite training report") == read_ref(
    store,
    training_report_ref,
    "run training report",
)

aiplatform.init(project=project_id, location=region)
model_evidence: dict[str, dict] = {}
package_manifests: dict[str, dict] = {}
production_aliases: dict[str, str] = {}
for horizon in HORIZONS:
    version = suite_manifest["model_versions"][horizon]
    assert version == run_manifest["model_versions"][horizon]
    expected_parent = (
        f"{parent}/models/{deployment['parent_model_ids'][horizon]}"
    )
    assert version["parent_model_resource_name"] == expected_parent
    assert version["version_resource_name"] == (
        f"{expected_parent}@{version['version_id']}"
    )
    model = model_service.get_model(
        request={"name": version["version_resource_name"]}
    )
    observed_resource = (
        model.name if "@" in model.name else f"{model.name}@{model.version_id}"
    )
    assert observed_resource == version["version_resource_name"]
    assert model.name == expected_parent
    assert str(model.version_id) == version["version_id"]
    assert model.artifact_uri == version["artifact_uri"]
    assert model.container_spec.image_uri == deployment["container_image_uri"]
    container_env = {item.name: item.value for item in model.container_spec.env}
    assert container_env["FEWSNET_CONTAINER_IMAGE_DIGEST"] == deployment[
        "container_image_digest"
    ]
    assert container_env["FEWSNET_SOURCE_GIT_COMMIT"] == deployment[
        "source_git_commit"
    ]
    assert version["suite_version_alias"] in set(model.version_aliases)
    assert "production" in set(model.version_aliases)
    alias_info = aiplatform.ModelRegistry(expected_parent).get_version_info(
        "production"
    )
    assert alias_info.model_resource_name == expected_parent
    assert str(alias_info.version_id) == version["version_id"]
    production_aliases[horizon] = version["version_resource_name"]

    package_manifest, _ = live_json(
        store,
        f"{version['artifact_uri']}/model_manifest.json",
        f"{horizon} model package manifest",
    )
    validate_payload("model-package", package_manifest)
    assert package_manifest["horizon_key"] == horizon
    assert package_manifest["suite_version"] == suite_version
    assert package_manifest["snapshot_id"] == snapshot["snapshot_id"]
    assert package_manifest["snapshot_content_sha256"] == snapshot[
        "snapshot_content_sha256"
    ]
    assert package_manifest["partition_sha256"] == PARTITION_ASSET_SHA256
    assert package_manifest["source_git_commit"] == deployment["source_git_commit"]
    assert package_manifest["container_image_uri"] == deployment[
        "container_image_uri"
    ]
    assert package_manifest["container_image_digest"] == deployment[
        "container_image_digest"
    ]
    assert package_manifest["threshold"] == training_report[
        "horizon_thresholds"
    ][horizon]["threshold"]
    package_manifests[horizon] = package_manifest
    model_evidence[horizon] = {
        "parent": expected_parent,
        "version": version["version_resource_name"],
        "artifact_uri": model.artifact_uri,
        "image_uri": model.container_spec.image_uri,
    }
assert len(set(production_aliases.values())) == 3

batch_run_label = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:16]
listed_batch_jobs = list(
    job_service.list_batch_prediction_jobs(
        request={
            "parent": parent,
            "filter": f"labels.fewsnet_run={batch_run_label}",
        }
    )
)
expected_batch_names = {
    run_manifest["batch_jobs"][horizon]["job_resource_name"]
    for horizon in HORIZONS
}
assert len(listed_batch_jobs) == 3
assert {job.name for job in listed_batch_jobs} == expected_batch_names
batch_evidence: dict[str, dict] = {}
for horizon in HORIZONS:
    expected = run_manifest["batch_jobs"][horizon]
    job = job_service.get_batch_prediction_job(
        request={"name": expected["job_resource_name"]}
    )
    assert state_name(job.state) == "JOB_STATE_SUCCEEDED"
    assert job.model == expected["model_version_resource_name"]
    assert list(job.input_config.gcs_source.uris) == [expected["input_uri"]]
    assert (
        job.output_config.gcs_destination.output_uri_prefix
        == expected["destination_prefix"]
    )
    assert job.output_info.gcs_output_directory == expected[
        "gcs_output_directory"
    ]
    assert job.service_account == deployment["batch_prediction_service_account"]
    assert job.dedicated_resources.machine_spec.machine_type == deployment[
        "batch_machine_type"
    ]
    batch_evidence[horizon] = {
        "job": job.name,
        "model": job.model,
        "input": expected["input_uri"],
        "output": expected["gcs_output_directory"],
    }

validation = run_result["validation"]
assert set(validation) == {
    "suite_version",
    "snapshot_id",
    "snapshot_content_sha256",
    "feature_month",
    "area_count",
    "horizons",
}
assert validation["suite_version"] == suite_version
assert validation["snapshot_id"] == snapshot["snapshot_id"]
assert validation["snapshot_content_sha256"] == snapshot[
    "snapshot_content_sha256"
]
assert validation["feature_month"] == snapshot["latest_feature_month"]
assert validation["area_count"] == snapshot["area_count"]
assert set(validation["horizons"]) == set(HORIZONS)
prediction_evidence: dict[str, dict] = {}
canonical_admins: set[str] | None = None
for horizon in HORIZONS:
    suite_prediction_ref = suite_manifest["predictions"][horizon]
    prediction_bytes = read_ref(
        store,
        suite_prediction_ref,
        f"{horizon} suite prediction",
    )
    run_prediction_ref = vars(
        store.get_ref(f"{run_root}/predictions/{horizon}.csv")
    )
    assert read_ref(store, run_prediction_ref, f"{horizon} run prediction") == prediction_bytes
    frame = pd.read_csv(
        BytesIO(prediction_bytes),
        dtype={
            "admin_code": "string",
            "feature_month": "string",
            "target_month": "string",
            "horizon_months": "Int64",
            "predicted_crisis": "Int64",
            "cluster_id": "Int64",
            "prediction_source": "string",
            "suite_version": "string",
            "vertex_model_resource_name": "string",
            "vertex_model_version_id": "string",
        },
    )
    assert len(frame) == 5_718
    assert frame["admin_code"].nunique() == 5_718
    assert not frame["admin_code"].duplicated().any()
    records = json.loads(frame.to_json(orient="records"))
    for record in records:
        validate_payload("prediction-record", record)
    expected_threshold = package_manifests[horizon]["threshold"]
    assert set(frame["threshold"].astype(float)) == {expected_threshold}
    assert (
        frame["predicted_crisis"].astype(int)
        == (frame["probability_crisis"].astype(float) >= expected_threshold).astype(int)
    ).all()
    assert set(frame["suite_version"]) == {suite_version}
    assert set(frame["horizon_months"].astype(int)) == {HORIZON_MONTHS[horizon]}
    assert set(frame["vertex_model_resource_name"]) == {
        suite_manifest["model_versions"][horizon]["version_resource_name"]
    }
    assert set(frame["vertex_model_version_id"].astype(str)) == {
        suite_manifest["model_versions"][horizon]["version_id"]
    }
    routed = partition_map.route(frame["admin_code"].tolist()).tolist()
    observed_clusters = [
        None if pd.isna(value) else int(value)
        for value in frame["cluster_id"].tolist()
    ]
    assert observed_clusters == routed
    assert all(
        (cluster is None) == (source == "pooled_unmapped")
        for cluster, source in zip(
            observed_clusters,
            frame["prediction_source"].tolist(),
            strict=True,
        )
    )
    coverage = partition_map.assert_release_coverage(frame["admin_code"].tolist())
    source_counts = {
        source: int(frame["prediction_source"].eq(source).sum())
        for source in PREDICTION_SOURCES
    }
    assert sum(source_counts.values()) == 5_718
    horizon_validation = validation["horizons"][horizon]
    assert set(horizon_validation) == {
        "row_count",
        "partition_coverage_pct",
        "source_counts",
    }
    assert set(horizon_validation["source_counts"]) == set(PREDICTION_SOURCES)
    assert source_counts == horizon_validation["source_counts"]
    assert horizon_validation["row_count"] == 5_718
    assert horizon_validation["partition_coverage_pct"] == coverage
    admins = set(frame["admin_code"].astype(str))
    if canonical_admins is None:
        canonical_admins = admins
    else:
        assert admins == canonical_admins
    prediction_evidence[horizon] = {
        "rows": len(frame),
        "areas": len(admins),
        "source_counts": source_counts,
        "partition_coverage_pct": coverage,
    }

parity = load_json_file(parity_path, "fixed-sample parity evidence")
assert set(parity) == {
    "schema_version",
    "suite_version",
    "snapshot_content_sha256",
    "container_image_digest",
    "sample_sha256",
    "probability_tolerance",
    "horizons",
}
assert parity["schema_version"] == "fewsnet-fixed-sample-parity-v1"
assert SHA256_PATTERN.fullmatch(parity["sample_sha256"])
assert parity["suite_version"] == suite_version
assert parity["snapshot_content_sha256"] == snapshot["snapshot_content_sha256"]
assert parity["container_image_digest"] == deployment["container_image_digest"]
tolerance = float(parity["probability_tolerance"])
assert 0.0 <= tolerance <= 1e-12
assert set(parity["horizons"]) == set(HORIZONS)
parity_row_count: int | None = None
for horizon in HORIZONS:
    item = parity["horizons"][horizon]
    assert set(item) == {
        "model_version_resource_name",
        "row_count",
        "local_vs_container_max_abs_probability_delta",
        "local_vs_vertex_max_abs_probability_delta",
        "local_vs_container_class_mismatch_count",
        "local_vs_vertex_class_mismatch_count",
    }
    assert item["row_count"] > 0
    if parity_row_count is None:
        parity_row_count = item["row_count"]
    else:
        assert item["row_count"] == parity_row_count
    assert item["model_version_resource_name"] == suite_manifest[
        "model_versions"
    ][horizon]["version_resource_name"]
    assert item["local_vs_container_max_abs_probability_delta"] <= tolerance
    assert item["local_vs_vertex_max_abs_probability_delta"] <= tolerance
    assert item["local_vs_container_class_mismatch_count"] == 0
    assert item["local_vs_vertex_class_mismatch_count"] == 0

endpoint_names = [
    endpoint.name
    for endpoint in endpoint_service.list_endpoints(request={"parent": parent})
]
assert endpoint_names == []
object_uris = [ref.uri for ref in store.list(f"{root_uri}/")]
forbidden_uris = [
    uri
    for uri in object_uris
    if any(token in uri.lower() for token in FORBIDDEN_OBJECT_TOKENS)
]
assert forbidden_uris == []

for horizon in HORIZONS:
    alias_state = suite_manifest["alias_state"][horizon]
    assert alias_state == {
        "alias": "production",
        "version_resource_name": production_aliases[horizon],
    }

storage_client = storage.Client()
suite_updated = object_updated(storage_client, current["suite_manifest"])
month_updated = object_updated(storage_client, month_ref)
current_updated = object_updated(storage_client, current_ref)
assert suite_updated <= month_updated <= current_updated
assert timestamp(current["released_at_utc"]) <= current_updated

evidence = {
    "acceptance_01_raw_panel_unchanged": raw_sha256_before,
    "acceptance_02_normalized_panel": {
        "rows": normalized_rows,
        "areas": len(normalized_areas),
        "duplicate_groups": normalization_audit["duplicate_group_count"],
        "removed_rows": normalization_audit["removed_row_count"],
    },
    "acceptance_03_normalization_audit": normalization_audit["output_panel"],
    "acceptance_04_local_stage": local_stage,
    "acceptance_05_snapshot": {
        "manifest": snapshot_ref,
        "selected_copy": selected_copy_ref,
        "input_snapshot_ref": input_snapshot_ref,
    },
    "acceptance_06_partition_sha256": PARTITION_ASSET_SHA256,
    "acceptance_07_custom_job": custom_name,
    "acceptance_08_model_versions": production_aliases,
    "acceptance_09_model_bindings": model_evidence,
    "acceptance_10_batch_jobs": batch_evidence,
    "acceptance_11_predictions": prediction_evidence,
    "acceptance_12_fixed_sample_parity": parity,
    "acceptance_13_validator": validation,
    "acceptance_14_forbidden_artifacts": {
        "endpoint_count": len(endpoint_names),
        "forbidden_objects": forbidden_uris,
    },
    "acceptance_15_alias_suite_identity": production_aliases,
    "acceptance_16_write_order": {
        "suite_manifest_updated": suite_updated.isoformat(),
        "month_pointer_updated": month_updated.isoformat(),
        "current_pointer_updated": current_updated.isoformat(),
    },
    "deployment_ref": deployment_ref,
    "run_manifest_ref": run_manifest_ref,
}
print(json.dumps(evidence, indent=2, sort_keys=True))
print("all_16_acceptance_items=PASS")
PY
# END FEWSNET_PRODUCTION_ACCEPTANCE_VERIFIER
```

Do not call the first production run accepted until all sixteen items are
recorded. Local implementation tests, a skipped smoke, or a successful image
build are not production acceptance.
