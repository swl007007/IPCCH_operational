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
- Checksums prove integrity and consistency, not authenticity. Establish
  authenticity through a trusted digest-pinned image and source commit, a
  least-privilege producer identity, immutable object generations, and
  restricted write authority.
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
roles: exact-object reader, create-only writer, exact mutable-object replacer,
and bucket lister. Object replacement requires both `storage.objects.create`
and `storage.objects.delete`. The orchestrator receives create-only authority
over the documented namespaces, while delete authority is a separate binding
covering only the promotion lease, release pointers, and generation-updated run
manifests. Workers never receive delete authority, so their writes remain
create-only when the repository also supplies `if_generation_match=0`.

```bash
export OBJECT_READER_ROLE_ID="fewsnetObjectReaderV1"
export OBJECT_CREATOR_ROLE_ID="fewsnetObjectCreatorV1"
export OBJECT_REPLACER_ROLE_ID="fewsnetObjectReplacerV1"
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
gcloud iam roles create "$OBJECT_REPLACER_ROLE_ID" \
  --project="$PROJECT_ID" \
  --title="FEWSNET exact mutable-object replacer v1" \
  --permissions="storage.objects.get,storage.objects.delete" \
  --stage=GA
gcloud iam roles create "$OBJECT_LISTER_ROLE_ID" \
  --project="$PROJECT_ID" \
  --title="FEWSNET object lister v1" \
  --permissions="storage.objects.list" \
  --stage=GA

export OBJECT_READER_ROLE="projects/${PROJECT_ID}/roles/${OBJECT_READER_ROLE_ID}"
export OBJECT_CREATOR_ROLE="projects/${PROJECT_ID}/roles/${OBJECT_CREATOR_ROLE_ID}"
export OBJECT_REPLACER_ROLE="projects/${PROJECT_ID}/roles/${OBJECT_REPLACER_ROLE_ID}"
export OBJECT_LISTER_ROLE="projects/${PROJECT_ID}/roles/${OBJECT_LISTER_ROLE_ID}"
export OBJECT_STORE_PREFIX="${OBJECT_STORE_ROOT_URI#gs://${ARTIFACT_BUCKET}/}"
test "$OBJECT_STORE_PREFIX" != "$OBJECT_STORE_ROOT_URI"
export OBJECT_RESOURCE_BASE="projects/_/buckets/${ARTIFACT_BUCKET}/objects/${OBJECT_STORE_PREFIX}"

export TRAINING_READ_CONDITION="resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/inputs/snapshots/\") || resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/runs/\") || resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/suites/\")"
export TRAINING_CREATE_CONDITION="resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/runs/\") || resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/suites/\")"
export BATCH_RUN_CONDITION="resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/runs/\")"
export ORCHESTRATOR_READ_CONDITION="resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/\")"
export ORCHESTRATOR_CREATE_CONDITION="resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/inputs/\") || resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/deployments/\") || resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/runs/\") || resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/suites/\") || resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/locks/\") || resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/released/\")"
export ORCHESTRATOR_REPLACE_CONDITION="resource.name == \"${OBJECT_RESOURCE_BASE}/locks/production-promotion.json\" || resource.name == \"${OBJECT_RESOURCE_BASE}/released/current.json\" || (resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/released/\") && resource.name.endsWith(\"/production_suite_manifest.json\")) || (resource.name.startsWith(\"${OBJECT_RESOURCE_BASE}/runs/\") && resource.name.endsWith(\"/run_manifest.json\"))"

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
  --role="$OBJECT_CREATOR_ROLE" \
  --condition="expression=${ORCHESTRATOR_CREATE_CONDITION},title=fewsnet_orchestrator_create_v1,description=Create immutable suite objects and initial mutable objects"
gcloud storage buckets add-iam-policy-binding "gs://${ARTIFACT_BUCKET}" \
  --member="serviceAccount:${ORCHESTRATOR_SA}" \
  --role="$OBJECT_REPLACER_ROLE" \
  --condition="expression=${ORCHESTRATOR_REPLACE_CONDITION},title=fewsnet_orchestrator_replace_v1,description=Replace only lease release pointers and run manifests"
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
`ORCHESTRATOR_SA` cannot delete or replace snapshot inputs, deployment
manifests, model packages, predictions, suite manifests, or immutable run
evidence. Its replacement binding is limited to
`locks/production-promotion.json`, `released/current.json`,
`released/{feature_month}/production_suite_manifest.json`, and
`runs/{run_id}/run_manifest.json`; every replacement still supplies the
verified prior generation.

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

For a successful non-noop run, the complete allowed object inventory is:

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

Every listed input, deployment, training, registry, Batch input/output,
prediction, model-package, and suite-manifest object is create-only. The only
generation-replaced objects are `runs/{run_id}/run_manifest.json`,
`locks/production-promotion.json`,
`released/{feature_month}/production_suite_manifest.json`, and
`released/current.json`. A failed run may additionally create the immutable
`runs/{run_id}/error.json`. No other object path or file family is approved;
in particular, maps, workbooks, and future-target performance outputs are not
part of this inventory.

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

Generate the fixed-sample evidence from the released run; do not hand-author
it. The generator reads each exact-generation Batch input and every exact
Vertex output object, requires the three input byte streams to match, and uses
the first 32 already sorted input records as the deterministic sample. It then
loads the exact package objects into the composite predictor, invokes the local
custom prediction application through its `/predict` interface, and selects the
same records from the exact Vertex Batch output. Canonical JSONL bytes, object
generations, sizes, SHA-256 values, finite nonnegative deltas, and mismatch
counts are written to `FEWSNET_FIXED_SAMPLE_PARITY_JSON`.

```bash
export FEWSNET_FIXED_SAMPLE_PARITY_JSON="/operator-selected/output/fewsnet-fixed-sample-parity.json"

: "${DEPLOYMENT_MANIFEST_URI:?}"
: "${OBJECT_STORE_ROOT_URI:?}"
: "${RUN_ID:?}"
: "${FEWSNET_FIXED_SAMPLE_PARITY_JSON:?}"

# BEGIN FEWSNET_FIXED_SAMPLE_PARITY_GENERATOR
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

import pandas as pd
from fastapi.testclient import TestClient

from fewsnet_partitioned_rf_pipeline.core.inference import (
    FORMAL_PREDICTION_COLUMNS,
)
from fewsnet_partitioned_rf_pipeline.core.package import (
    PACKAGE_FILES,
    load_model_package,
)
from fewsnet_partitioned_rf_pipeline.schemas import (
    validate_deployment,
    validate_payload,
)
from fewsnet_partitioned_rf_pipeline.vertex.predictor_server import create_app
from fewsnet_partitioned_rf_pipeline.vertex.storage import (
    GCSArtifactStore,
    LocalArtifactStore,
)


HORIZONS = ("0m", "6m", "12m")
SAMPLE_SIZE = 32
PROBABILITY_TOLERANCE = 1e-12


def require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def ref_dict(ref: object) -> dict:
    payload = {
        "uri": str(getattr(ref, "uri")),
        "generation": str(getattr(ref, "generation")),
        "sha256": str(getattr(ref, "sha256")),
        "size_bytes": int(getattr(ref, "size_bytes")),
    }
    require(len(payload["sha256"]) == 64, "ObjectRef SHA-256 is invalid")
    return payload


def read_ref(store: GCSArtifactStore, ref: dict, name: str) -> bytes:
    data = store.read_bytes(ref["uri"], generation=ref["generation"])
    require(len(data) == ref["size_bytes"], f"{name} size differs")
    require(
        hashlib.sha256(data).hexdigest() == ref["sha256"],
        f"{name} checksum differs",
    )
    return data


def object_ref_dict(ref: object) -> dict:
    return {
        "uri": str(getattr(ref, "uri")),
        "generation": str(getattr(ref, "generation")),
        "sha256": str(getattr(ref, "sha256")),
        "size_bytes": int(getattr(ref, "size_bytes")),
    }


def live_json(store: GCSArtifactStore, uri: str, name: str) -> tuple[dict, dict]:
    ref = ref_dict(store.get_ref(uri))
    payload = json.loads(read_ref(store, ref, name))
    require(isinstance(payload, dict), f"{name} must be a JSON object")
    return payload, ref


def canonical_jsonl(records: list[dict]) -> bytes:
    return (
        "\n".join(
            json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            for record in records
        )
        + "\n"
    ).encode("utf-8")


def object_fingerprint(data: bytes) -> dict:
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def parse_jsonl(data: bytes, name: str) -> list[dict]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{name} is not UTF-8 JSONL") from exc
    lines = text.splitlines()
    require(lines and all(line.strip() for line in lines), f"{name} is empty")
    records = [json.loads(line) for line in lines]
    require(all(isinstance(record, dict) for record in records), f"{name} differs")
    return records


def json_scalar(value: object) -> object:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    item = getattr(value, "item", None)
    return item() if callable(item) else value


def prediction_records(records: list[dict], name: str) -> list[dict]:
    normalized: list[dict] = []
    expected = set(FORMAL_PREDICTION_COLUMNS)
    for index, record in enumerate(records):
        require(isinstance(record, dict), f"{name}[{index}] is not an object")
        require(set(record) == expected, f"{name}[{index}] fields differ")
        normalized.append(
            {
                field: json_scalar(record[field])
                for field in FORMAL_PREDICTION_COLUMNS
            }
        )
    return normalized


def identity(record: dict) -> tuple[str, str]:
    return str(record["admin_code"]), str(record["feature_month"])


def select_vertex_predictions(
    raw_objects: list[tuple[dict, bytes]],
    sample: list[dict],
) -> list[dict]:
    expected_instances = {identity(instance): instance for instance in sample}
    selected: dict[tuple[str, str], dict] = {}
    for ref, data in raw_objects:
        for payload in parse_jsonl(data, ref["uri"]):
            require(set(payload) == {"instance", "prediction"}, "Vertex row differs")
            instance = payload["instance"]
            prediction = payload["prediction"]
            require(isinstance(instance, dict), "Vertex instance is invalid")
            require(isinstance(prediction, dict), "Vertex prediction is invalid")
            key = identity(instance)
            if key not in expected_instances:
                continue
            require(instance == expected_instances[key], "Vertex sample instance drifted")
            require(key not in selected, "Vertex sample prediction is duplicated")
            selected[key] = prediction
    missing = [identity(instance) for instance in sample if identity(instance) not in selected]
    require(not missing, f"Vertex output is missing sample identities: {missing}")
    return [selected[identity(instance)] for instance in sample]


def maximum_delta(left: list[dict], right: list[dict], name: str) -> float:
    require(len(left) == len(right) and left, f"{name} row counts differ")
    deltas = [
        abs(float(a["probability_crisis"]) - float(b["probability_crisis"]))
        for a, b in zip(left, right, strict=True)
    ]
    require(all(math.isfinite(value) and value >= 0.0 for value in deltas), name)
    return max(deltas)


def mismatch_count(left: list[dict], right: list[dict]) -> int:
    require(len(left) == len(right), "class comparison row counts differ")
    return sum(
        int(a["predicted_crisis"]) != int(b["predicted_crisis"])
        for a, b in zip(left, right, strict=True)
    )


store = GCSArtifactStore.from_default()
root_uri = os.environ["OBJECT_STORE_ROOT_URI"].rstrip("/")
run_id = os.environ["RUN_ID"]
deployment, _ = live_json(
    store,
    os.environ["DEPLOYMENT_MANIFEST_URI"],
    "deployment manifest",
)
validate_deployment(deployment)
run_manifest, _ = live_json(
    store,
    f"{root_uri}/runs/{run_id}/run_manifest.json",
    "run manifest",
)
validate_payload("run-manifest", run_manifest)
require(run_manifest["status"] == "released", "run is not released")
suite_version = run_manifest["suite_version"]
suite_manifest, _ = live_json(
    store,
    f"{root_uri}/suites/{suite_version}/suite_manifest.json",
    "suite manifest",
)
validate_payload("suite-manifest", suite_manifest)

sample_bytes: bytes | None = None
horizon_evidence: dict[str, dict] = {}
with tempfile.TemporaryDirectory(prefix="fewsnet-fixed-sample-parity-") as temp:
    temp_root = Path(temp)
    for horizon in HORIZONS:
        job = run_manifest["batch_jobs"][horizon]
        input_ref = ref_dict(store.get_ref(job["input_uri"]))
        input_bytes = read_ref(store, input_ref, f"{horizon} Batch input")
        instances = parse_jsonl(input_bytes, f"{horizon} Batch input")
        require(len(instances) >= SAMPLE_SIZE, "Batch input is smaller than sample")
        sample = instances[:SAMPLE_SIZE]
        candidate_sample_bytes = canonical_jsonl(sample)
        if sample_bytes is None:
            sample_bytes = candidate_sample_bytes
        else:
            require(candidate_sample_bytes == sample_bytes, "horizon samples differ")

        version = run_manifest["model_versions"][horizon]
        package_dir = temp_root / "packages" / horizon
        package_dir.mkdir(parents=True)
        package_refs: dict[str, dict] = {}
        for filename in PACKAGE_FILES:
            ref = ref_dict(store.get_ref(f"{version['artifact_uri']}/{filename}"))
            package_refs[filename] = ref
            (package_dir / filename).write_bytes(
                read_ref(store, ref, f"{horizon} package {filename}")
            )
        predictor = load_model_package(
            package_dir,
            expected_image_digest=deployment["container_image_digest"],
            expected_source_git_commit=deployment["source_git_commit"],
        )
        frame = pd.DataFrame(sample)
        local_records = prediction_records(
            predictor.predict_frame(frame).to_dict(orient="records"),
            f"{horizon} local predictions",
        )

        local_store = LocalArtifactStore(temp_root / "container-store" / horizon)
        local_artifact_uri = f"gs://parity-package/{horizon}"
        for filename in PACKAGE_FILES:
            local_store.upload_file(
                package_dir / filename,
                f"{local_artifact_uri}/{filename}",
            )
        app = create_app(
            environ={
                "AIP_HTTP_PORT": "8080",
                "AIP_HEALTH_ROUTE": "/health",
                "AIP_PREDICT_ROUTE": "/predict",
                "AIP_STORAGE_URI": local_artifact_uri,
                "FEWSNET_CONTAINER_IMAGE_DIGEST": deployment[
                    "container_image_digest"
                ],
                "FEWSNET_SOURCE_GIT_COMMIT": deployment["source_git_commit"],
            },
            store=local_store,
        )
        with TestClient(app) as client:
            response = client.post("/predict", json={"instances": sample})
        require(response.status_code == 200, f"{horizon} container prediction failed")
        container_payload = response.json()
        require(set(container_payload) == {"predictions"}, "container response differs")
        container_records = prediction_records(
            container_payload["predictions"],
            f"{horizon} container predictions",
        )

        output_prefix = str(job["gcs_output_directory"]).rstrip("/") + "/"
        output_refs = sorted(store.list(output_prefix), key=lambda ref: ref.uri)
        require(output_refs, f"{horizon} Vertex output objects are missing")
        require(
            all(
                Path(ref.uri).name.startswith("predictions_")
                and Path(ref.uri).suffix == ".jsonl"
                for ref in output_refs
            ),
            f"{horizon} Vertex output inventory differs",
        )
        raw_objects = [
            (
                ref_dict(ref),
                read_ref(store, ref_dict(ref), f"{horizon} Vertex output"),
            )
            for ref in output_refs
        ]
        vertex_records = prediction_records(
            select_vertex_predictions(raw_objects, sample),
            f"{horizon} Vertex predictions",
        )

        local_bytes = canonical_jsonl(local_records)
        container_bytes = canonical_jsonl(container_records)
        vertex_bytes = canonical_jsonl(vertex_records)
        local_container_delta = maximum_delta(
            local_records,
            container_records,
            f"{horizon} local/container delta",
        )
        local_vertex_delta = maximum_delta(
            local_records,
            vertex_records,
            f"{horizon} local/Vertex delta",
        )
        require(
            local_container_delta <= PROBABILITY_TOLERANCE,
            f"{horizon} local/container probability parity failed",
        )
        require(
            local_vertex_delta <= PROBABILITY_TOLERANCE,
            f"{horizon} local/Vertex probability parity failed",
        )
        local_container_mismatches = mismatch_count(local_records, container_records)
        local_vertex_mismatches = mismatch_count(local_records, vertex_records)
        require(local_container_mismatches == 0, "local/container classes differ")
        require(local_vertex_mismatches == 0, "local/Vertex classes differ")
        horizon_evidence[horizon] = {
            "model_version_resource_name": version["version_resource_name"],
            "row_count": len(sample),
            "batch_input": input_ref,
            "package_objects": package_refs,
            "vertex_output_objects": [ref for ref, _ in raw_objects],
            "local_output": object_fingerprint(local_bytes),
            "container_output": object_fingerprint(container_bytes),
            "vertex_output": object_fingerprint(vertex_bytes),
            "local_vs_container_max_abs_probability_delta": (
                local_container_delta
            ),
            "local_vs_vertex_max_abs_probability_delta": local_vertex_delta,
            "local_vs_container_class_mismatch_count": (
                local_container_mismatches
            ),
            "local_vs_vertex_class_mismatch_count": local_vertex_mismatches,
        }

require(sample_bytes is not None, "fixed sample was not generated")
report = {
    "schema_version": "fewsnet-fixed-sample-parity-v2",
    "suite_version": suite_version,
    "snapshot_content_sha256": run_manifest["snapshot_ref"][
        "snapshot_content_sha256"
    ],
    "container_image_digest": deployment["container_image_digest"],
    "sample_sha256": hashlib.sha256(sample_bytes).hexdigest(),
    "sample_size": SAMPLE_SIZE,
    "probability_tolerance": PROBABILITY_TOLERANCE,
    "horizons": horizon_evidence,
}
Path(os.environ["FEWSNET_FIXED_SAMPLE_PARITY_JSON"]).write_text(
    json.dumps(report, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(json.dumps(report, indent=2, sort_keys=True))
PY
# END FEWSNET_FIXED_SAMPLE_PARITY_GENERATOR
```

The resulting `fewsnet-fixed-sample-parity-v2` report is not accepted merely
because it reports zero deltas. The verifier below re-reads the recorded input,
package, and Vertex output generations, reconstructs the same sample, reruns the
local composite and custom prediction application, recomputes every output
fingerprint and delta, and rejects negative or nonfinite numeric evidence.

Run this single read-only verifier under the preflighted impersonation state.
It performs no create, update, alias, job, Endpoint, or pointer operation and
exits nonzero on any missing or inconsistent acceptance item:

```bash
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
env -u PYTHONOPTIMIZE PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
from __future__ import annotations

if not __debug__:
    raise RuntimeError("production acceptance verifier forbids optimized Python")

from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

import google.auth
import pandas as pd
from fastapi.testclient import TestClient
from google.api_core.client_options import ClientOptions
from google.cloud import aiplatform, aiplatform_v1, storage

from fewsnet_partitioned_rf_pipeline.config import (
    PARTITION_ASSET_PATH,
    PARTITION_ASSET_SHA256,
)
from fewsnet_partitioned_rf_pipeline.core.inference import (
    FORMAL_PREDICTION_COLUMNS,
)
from fewsnet_partitioned_rf_pipeline.core.normalization import (
    validate_normalization_audit,
)
from fewsnet_partitioned_rf_pipeline.core.package import (
    PACKAGE_FILES,
    load_model_package,
)
from fewsnet_partitioned_rf_pipeline.core.partitions import PartitionMap
from fewsnet_partitioned_rf_pipeline.schemas import (
    validate_deployment,
    validate_payload,
)
from fewsnet_partitioned_rf_pipeline.vertex.predictor_server import create_app
from fewsnet_partitioned_rf_pipeline.vertex.storage import (
    GCSArtifactStore,
    LocalArtifactStore,
)


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
PARITY_SAMPLE_SIZE = 32
ALLOWED_OBJECT_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        (
            r"inputs/snapshots/[A-Za-z0-9._-]+/"
            r"(?:assembled_fewsnet\.normalized\.csv|"
            r"panel_normalization_audit\.json|admin_boundaries\.parquet|"
            r"admin_universe\.csv|source_manifest\.json)"
        ),
        r"deployments/deployment-[0-9a-f]{12}-[0-9a-f]{64}\.json",
        (
            r"runs/[A-Za-z0-9._-]+/(?:run_manifest\.json|"
            r"input_snapshot_ref\.json|inputs/selected_source_manifest\.json|"
            r"training/custom_job\.json|training_job_result\.json|"
            r"training_threshold_report\.json|registry/(?:0m|6m|12m)\.json|"
            r"batch_prediction/(?:0m|6m|12m)/input\.jsonl|"
            r"batch_prediction/(?:0m|6m|12m)/raw/"
            r"(?:[^/]+/)*predictions_[^/]+\.jsonl|"
            r"predictions/(?:0m|6m|12m)\.csv|error\.json)"
        ),
        (
            r"suites/[A-Za-z0-9._-]+/(?:models/(?:0m|6m|12m)/"
            r"(?:model\.joblib|model_manifest\.json|feature_contract\.json|"
            r"partition_map\.csv|threshold_report\.json|training_report\.json|"
            r"checksums\.json)|training_threshold_report\.json|"
            r"predictions/(?:0m|6m|12m)\.csv|suite_manifest\.json)"
        ),
        r"locks/production-promotion\.json",
        r"released/[0-9]{4}-(?:0[1-9]|1[0-2])/production_suite_manifest\.json",
        r"released/current\.json",
    )
)


def require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


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


def object_fingerprint(data: bytes) -> dict:
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def require_fingerprint(data: bytes, expected: dict, name: str) -> None:
    require(
        isinstance(expected, dict) and set(expected) == {"sha256", "size_bytes"},
        f"{name} fingerprint fields differ",
    )
    require(expected["size_bytes"] == len(data), f"{name} size differs")
    require(
        expected["sha256"] == hashlib.sha256(data).hexdigest(),
        f"{name} checksum differs",
    )


def validate_probability_delta(value: object, tolerance: float, name: str) -> float:
    try:
        delta = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    require(math.isfinite(delta), f"{name} must be finite")
    require(0.0 <= delta <= tolerance, f"{name} is outside [0, tolerance]")
    return delta


def canonical_jsonl(records: list[dict]) -> bytes:
    return (
        "\n".join(
            json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            for record in records
        )
        + "\n"
    ).encode("utf-8")


def parse_jsonl(data: bytes, name: str) -> list[dict]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{name} is not UTF-8 JSONL") from exc
    lines = text.splitlines()
    require(lines and all(line.strip() for line in lines), f"{name} is empty")
    records = [json.loads(line) for line in lines]
    require(all(isinstance(record, dict) for record in records), f"{name} differs")
    return records


def json_scalar(value: object) -> object:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    item = getattr(value, "item", None)
    return item() if callable(item) else value


def prediction_records(records: list[dict], name: str) -> list[dict]:
    expected = set(FORMAL_PREDICTION_COLUMNS)
    normalized: list[dict] = []
    for index, record in enumerate(records):
        require(isinstance(record, dict), f"{name}[{index}] is not an object")
        require(set(record) == expected, f"{name}[{index}] fields differ")
        normalized.append(
            {
                field: json_scalar(record[field])
                for field in FORMAL_PREDICTION_COLUMNS
            }
        )
    return normalized


def identity(record: dict) -> tuple[str, str]:
    return str(record["admin_code"]), str(record["feature_month"])


def select_vertex_predictions(
    raw_objects: list[tuple[dict, bytes]],
    sample: list[dict],
) -> list[dict]:
    expected_instances = {identity(instance): instance for instance in sample}
    selected: dict[tuple[str, str], dict] = {}
    for ref, data in raw_objects:
        for payload in parse_jsonl(data, ref["uri"]):
            require(set(payload) == {"instance", "prediction"}, "Vertex row differs")
            instance = payload["instance"]
            prediction = payload["prediction"]
            require(isinstance(instance, dict), "Vertex instance is invalid")
            require(isinstance(prediction, dict), "Vertex prediction is invalid")
            key = identity(instance)
            if key not in expected_instances:
                continue
            require(instance == expected_instances[key], "Vertex sample instance drifted")
            require(key not in selected, "Vertex sample prediction is duplicated")
            selected[key] = prediction
    missing = [identity(instance) for instance in sample if identity(instance) not in selected]
    require(not missing, f"Vertex output is missing sample identities: {missing}")
    return [selected[identity(instance)] for instance in sample]


def maximum_delta(left: list[dict], right: list[dict], name: str) -> float:
    require(len(left) == len(right) and left, f"{name} row counts differ")
    deltas = [
        abs(float(a["probability_crisis"]) - float(b["probability_crisis"]))
        for a, b in zip(left, right, strict=True)
    ]
    require(all(math.isfinite(value) and value >= 0.0 for value in deltas), name)
    return max(deltas)


def mismatch_count(left: list[dict], right: list[dict]) -> int:
    require(len(left) == len(right), "class comparison row counts differ")
    return sum(
        int(a["predicted_crisis"]) != int(b["predicted_crisis"])
        for a, b in zip(left, right, strict=True)
    )


def panel_csv_dimensions(data: bytes, name: str) -> tuple[int, int]:
    try:
        frame = pd.read_csv(
            BytesIO(data),
            usecols=lambda column: column in {"admin_code", "FEWSNET_admin_code"},
            low_memory=False,
        )
    except Exception as exc:
        raise ValueError(f"{name} cannot be parsed as the normalized panel") from exc
    require(not frame.empty, f"{name} is empty")
    require(len(frame.columns) == 1, f"{name} admin-code column differs")
    return len(frame), frame.iloc[:, 0].astype(str).nunique()


def require_source_panel_identity(
    source_panel: dict,
    raw_sha256: str,
    raw_size_bytes: int,
) -> None:
    require(isinstance(source_panel, dict), "audit source_panel is invalid")
    require(
        source_panel.get("sha256") == raw_sha256,
        "raw panel checksum differs from audit source_panel",
    )
    require(
        source_panel.get("size_bytes") == raw_size_bytes,
        "raw panel size differs from audit source_panel",
    )


def allowed_object_uri(root_uri: str, uri: str) -> bool:
    prefix = root_uri.rstrip("/") + "/"
    if not isinstance(uri, str) or not uri.startswith(prefix):
        return False
    relative = uri[len(prefix):]
    if not relative or relative.startswith("/") or "//" in relative:
        return False
    return any(pattern.fullmatch(relative) for pattern in ALLOWED_OBJECT_PATTERNS)


def object_ref_dict(ref: object) -> dict:
    return {
        "uri": str(getattr(ref, "uri")),
        "generation": str(getattr(ref, "generation")),
        "sha256": str(getattr(ref, "sha256")),
        "size_bytes": int(getattr(ref, "size_bytes")),
    }


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
require(
    deployment['project_id'] == project_id,
    'acceptance condition failed at verifier source line 361',
)
require(
    deployment['region'] == region,
    'acceptance condition failed at verifier source line 362',
)
require(
    deployment['object_store_root_uri'].rstrip('/') == root_uri,
    'acceptance condition failed at verifier source line 363',
)
require(
    deployment['orchestrator_service_account'] == orchestrator_sa,
    'acceptance condition failed at verifier source line 364',
)

run_result = load_json_file(run_result_path, "RUN_RESULT")
require(
    run_result['status'] == 'RELEASED',
    'acceptance condition failed at verifier source line 367',
)
require(
    run_result['run_id'] == run_id,
    'acceptance condition failed at verifier source line 368',
)
run_root = f"{root_uri}/runs/{run_id}"
run_manifest, run_manifest_ref = live_json(
    store,
    f"{run_root}/run_manifest.json",
    "run manifest",
)
validate_payload("run-manifest", run_manifest)
require(
    run_manifest['phase'] == 'RELEASED',
    'acceptance condition failed at verifier source line 376',
)
require(
    run_manifest['status'] == 'released',
    'acceptance condition failed at verifier source line 377',
)
require(
    run_manifest['hard_gates']['outputs_validated'] is True,
    'acceptance condition failed at verifier source line 378',
)
require(
    run_manifest['hard_gates']['promotion_released'] is True,
    'acceptance condition failed at verifier source line 379',
)

current_uri = f"{root_uri}/released/current.json"
current, current_ref = live_json(store, current_uri, "current pointer")
require(
    set(current) == {'schema_version', 'suite_version', 'feature_month', 'snapshot_content_sha256', 'suite_manifest', 'released_at_utc'},
    'acceptance condition failed at verifier source line 383',
)
require(
    current['schema_version'] == 'fewsnet-production-suite-pointer-v1',
    'acceptance condition failed at verifier source line 391',
)
suite_manifest = json.loads(
    read_ref(store, current["suite_manifest"], "suite manifest")
)
validate_payload("suite-manifest", suite_manifest)
suite_version = suite_manifest["suite_version"]
require(
    suite_version == run_manifest['suite_version'] == run_result['suite_version'],
    'acceptance condition failed at verifier source line 397',
)
require(
    current['suite_version'] == suite_version,
    'acceptance condition failed at verifier source line 398',
)
require(
    current['feature_month'] == suite_manifest['feature_month'],
    'acceptance condition failed at verifier source line 399',
)
require(
    current['released_at_utc'] == suite_manifest['released_at_utc'],
    'acceptance condition failed at verifier source line 400',
)
require(
    current['snapshot_content_sha256'] == suite_manifest['snapshot_ref']['snapshot_content_sha256'],
    'acceptance condition failed at verifier source line 401',
)
require(
    suite_manifest['source_git_commit'] == deployment['source_git_commit'],
    'acceptance condition failed at verifier source line 404',
)
require(
    suite_manifest['container_image'] == {'uri': deployment['container_image_uri'], 'digest': deployment['container_image_digest']},
    'acceptance condition failed at verifier source line 405',
)

month_uri = (
    f"{root_uri}/released/{suite_manifest['feature_month']}/"
    "production_suite_manifest.json"
)
month_pointer, month_ref = live_json(store, month_uri, "month pointer")
require(
    month_pointer == current,
    'acceptance condition failed at verifier source line 415',
)

snapshot_ref = suite_manifest["snapshot_ref"]["manifest"]
snapshot_bytes = read_ref(store, snapshot_ref, "source snapshot")
snapshot = json.loads(snapshot_bytes)
validate_payload("source-snapshot", snapshot)
require(
    snapshot['snapshot_id'] == suite_manifest['snapshot_ref']['snapshot_id'],
    'acceptance condition failed at verifier source line 421',
)
require(
    snapshot['snapshot_content_sha256'] == current['snapshot_content_sha256'],
    'acceptance condition failed at verifier source line 422',
)
require(
    snapshot['latest_feature_month'] == suite_manifest['feature_month'],
    'acceptance condition failed at verifier source line 425',
)

selected_copy, selected_copy_ref = live_json(
    store,
    f"{run_root}/inputs/selected_source_manifest.json",
    "selected source manifest copy",
)
require(
    json.dumps(selected_copy, sort_keys=True) == json.dumps(snapshot, sort_keys=True),
    'acceptance condition failed at verifier source line 432',
)
require(
    read_ref(store, selected_copy_ref, 'selected source manifest copy') == snapshot_bytes,
    'acceptance condition failed at verifier source line 433',
)
input_snapshot, input_snapshot_ref = live_json(
    store,
    f"{run_root}/input_snapshot_ref.json",
    "input snapshot reference",
)
require(
    input_snapshot == {'manifest': snapshot_ref, 'snapshot_id': snapshot['snapshot_id'], 'snapshot_content_sha256': snapshot['snapshot_content_sha256']},
    'acceptance condition failed at verifier source line 439',
)

require(
    SHA256_PATTERN.fullmatch(raw_sha256_before) is not None,
    "RAW_PANEL_SHA256_BEFORE is not a SHA-256 value",
)
raw_size_bytes = Path(raw_panel).stat().st_size
require(
    sha256_file(raw_panel) == raw_sha256_before,
    "raw panel checksum changed after normalization",
)
normalization_audit = validate_normalization_audit(
    Path(normalization_audit_path),
    Path(normalized_panel),
)
require_source_panel_identity(
    normalization_audit["source_panel"],
    raw_sha256_before,
    raw_size_bytes,
)
remote_audit = json.loads(
    read_ref(store, snapshot["normalization_audit"], "normalization audit")
)
require(remote_audit == normalization_audit, "staged normalization audit differs")
normalized_bytes = Path(normalized_panel).read_bytes()
staged_panel_bytes = read_ref(store, snapshot["panel"], "staged normalized panel")
require(
    staged_panel_bytes == normalized_bytes,
    "staged normalized panel bytes differ from the validated local panel",
)
output_panel = normalization_audit["output_panel"]
require(
    output_panel["sha256"] == snapshot["panel"]["sha256"],
    "normalization audit checksum differs from staged panel",
)
require(
    output_panel["size_bytes"] == snapshot["panel"]["size_bytes"],
    "normalization audit size differs from staged panel",
)
require(
    output_panel["row_count"] == snapshot["row_count"],
    "normalization audit row count differs from snapshot",
)
require(normalization_audit["duplicate_group_count"] == 2, "duplicate groups differ")
require(normalization_audit["duplicate_row_count"] == 4, "duplicate rows differ")
require(normalization_audit["removed_row_count"] == 2, "removed rows differ")
require(normalization_audit["conflict_group_count"] == 0, "conflicts were recorded")
require(
    all(
        group["disposition"] == "collapsed_identical_or_derived_only"
        for group in normalization_audit["duplicate_groups"]
    ),
    "normalization audit contains a disallowed duplicate disposition",
)

normalized_rows, normalized_area_count = panel_csv_dimensions(
    staged_panel_bytes,
    "staged normalized panel",
)
require(
    normalized_rows == snapshot["row_count"] == 1_120_728,
    "staged normalized panel row count differs",
)
require(
    normalized_area_count == snapshot["area_count"] == 5_718,
    "staged normalized panel area count differs",
)

local_stage = load_json_file(local_stage_path, "local-stage evidence")
require(
    local_stage['schema_version'] == 'fewsnet-local-stage-evidence-v1',
    'acceptance condition failed at verifier source line 512',
)
require(
    local_stage['store_type'] == 'LocalArtifactStore',
    'acceptance condition failed at verifier source line 513',
)
require(
    local_stage['destination_root'].startswith('gs://local-preflight/'),
    'acceptance condition failed at verifier source line 514',
)
require(
    local_stage['duplicate_area_month_gate'] == 'passed',
    'acceptance condition failed at verifier source line 515',
)
require(
    local_stage['gcp_write_performed'] is False,
    'acceptance condition failed at verifier source line 516',
)
local_manifest = local_stage["manifest"]
require(
    local_manifest['row_count'] == snapshot['row_count'],
    'acceptance condition failed at verifier source line 518',
)
require(
    local_manifest['area_count'] == snapshot['area_count'],
    'acceptance condition failed at verifier source line 519',
)
require(
    local_manifest['snapshot_content_sha256'] == snapshot['snapshot_content_sha256'],
    'acceptance condition failed at verifier source line 520',
)

partition_map = PartitionMap.load(PARTITION_ASSET_PATH, PARTITION_ASSET_SHA256)
require(
    suite_manifest['partition']['sha256'] == PARTITION_ASSET_SHA256,
    'acceptance condition failed at verifier source line 525',
)

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
require(
    len(matching_custom_jobs) == 1,
    'acceptance condition failed at verifier source line 556',
)
custom_job = job_service.get_custom_job(request={"name": custom_name})
require(
    matching_custom_jobs[0].name == custom_job.name == custom_name,
    'acceptance condition failed at verifier source line 558',
)
require(
    state_name(custom_job.state) == 'JOB_STATE_SUCCEEDED',
    'acceptance condition failed at verifier source line 559',
)
require(
    custom_job.job_spec.service_account == deployment['training_service_account'],
    'acceptance condition failed at verifier source line 560',
)
worker = custom_job.job_spec.worker_pool_specs[0]
require(
    worker.container_spec.image_uri == deployment['container_image_uri'],
    'acceptance condition failed at verifier source line 562',
)

training_result, _ = live_json(
    store,
    f"{run_root}/training_job_result.json",
    "training job result",
)
require(
    set(training_result['packages']) == set(HORIZONS),
    'acceptance condition failed at verifier source line 569',
)
require(
    training_result['suite_version'] == suite_version,
    'acceptance condition failed at verifier source line 570',
)
require(
    training_result['snapshot_id'] == snapshot['snapshot_id'],
    'acceptance condition failed at verifier source line 571',
)
require(
    training_result['snapshot_content_sha256'] == snapshot['snapshot_content_sha256'],
    'acceptance condition failed at verifier source line 572',
)
require(
    training_result['source_git_commit'] == deployment['source_git_commit'],
    'acceptance condition failed at verifier source line 575',
)
require(
    training_result['container_image_uri'] == deployment['container_image_uri'],
    'acceptance condition failed at verifier source line 576',
)
require(
    training_result['container_image_digest'] == deployment['container_image_digest'],
    'acceptance condition failed at verifier source line 577',
)

training_report, training_report_ref = live_json(
    store,
    f"{run_root}/training_threshold_report.json",
    "training threshold report",
)
validate_payload("training-report", training_report)
require(
    training_report['suite_version'] == suite_version,
    'acceptance condition failed at verifier source line 587',
)
suite_training_report_ref = store.get_ref(
    f"{root_uri}/suites/{suite_version}/training_threshold_report.json"
)
require(
    read_ref(store, vars(suite_training_report_ref), 'suite training report') == read_ref(store, training_report_ref, 'run training report'),
    'acceptance condition failed at verifier source line 591',
)

aiplatform.init(project=project_id, location=region)
model_evidence: dict[str, dict] = {}
package_manifests: dict[str, dict] = {}
production_aliases: dict[str, str] = {}
for horizon in HORIZONS:
    version = suite_manifest["model_versions"][horizon]
    require(
        version == run_manifest['model_versions'][horizon],
        'acceptance condition failed at verifier source line 603',
    )
    expected_parent = (
        f"{parent}/models/{deployment['parent_model_ids'][horizon]}"
    )
    require(
        version['parent_model_resource_name'] == expected_parent,
        'acceptance condition failed at verifier source line 607',
    )
    require(
        version['version_resource_name'] == f"{expected_parent}@{version['version_id']}",
        'acceptance condition failed at verifier source line 608',
    )
    model = model_service.get_model(
        request={"name": version["version_resource_name"]}
    )
    observed_resource = (
        model.name if "@" in model.name else f"{model.name}@{model.version_id}"
    )
    require(
        observed_resource == version['version_resource_name'],
        'acceptance condition failed at verifier source line 617',
    )
    require(
        model.name == expected_parent,
        'acceptance condition failed at verifier source line 618',
    )
    require(
        str(model.version_id) == version['version_id'],
        'acceptance condition failed at verifier source line 619',
    )
    require(
        model.artifact_uri == version['artifact_uri'],
        'acceptance condition failed at verifier source line 620',
    )
    require(
        model.container_spec.image_uri == deployment['container_image_uri'],
        'acceptance condition failed at verifier source line 621',
    )
    container_env = {item.name: item.value for item in model.container_spec.env}
    require(
        container_env['FEWSNET_CONTAINER_IMAGE_DIGEST'] == deployment['container_image_digest'],
        'acceptance condition failed at verifier source line 623',
    )
    require(
        container_env['FEWSNET_SOURCE_GIT_COMMIT'] == deployment['source_git_commit'],
        'acceptance condition failed at verifier source line 626',
    )
    require(
        version['suite_version_alias'] in set(model.version_aliases),
        'acceptance condition failed at verifier source line 629',
    )
    require(
        'production' in set(model.version_aliases),
        'acceptance condition failed at verifier source line 630',
    )
    alias_info = aiplatform.ModelRegistry(expected_parent).get_version_info(
        "production"
    )
    require(
        alias_info.model_resource_name == expected_parent,
        'acceptance condition failed at verifier source line 634',
    )
    require(
        str(alias_info.version_id) == version['version_id'],
        'acceptance condition failed at verifier source line 635',
    )
    production_aliases[horizon] = version["version_resource_name"]

    package_manifest, _ = live_json(
        store,
        f"{version['artifact_uri']}/model_manifest.json",
        f"{horizon} model package manifest",
    )
    validate_payload("model-package", package_manifest)
    require(
        package_manifest['horizon_key'] == horizon,
        'acceptance condition failed at verifier source line 644',
    )
    require(
        package_manifest['suite_version'] == suite_version,
        'acceptance condition failed at verifier source line 645',
    )
    require(
        package_manifest['snapshot_id'] == snapshot['snapshot_id'],
        'acceptance condition failed at verifier source line 646',
    )
    require(
        package_manifest['snapshot_content_sha256'] == snapshot['snapshot_content_sha256'],
        'acceptance condition failed at verifier source line 647',
    )
    require(
        package_manifest['partition_sha256'] == PARTITION_ASSET_SHA256,
        'acceptance condition failed at verifier source line 650',
    )
    require(
        package_manifest['source_git_commit'] == deployment['source_git_commit'],
        'acceptance condition failed at verifier source line 651',
    )
    require(
        package_manifest['container_image_uri'] == deployment['container_image_uri'],
        'acceptance condition failed at verifier source line 652',
    )
    require(
        package_manifest['container_image_digest'] == deployment['container_image_digest'],
        'acceptance condition failed at verifier source line 655',
    )
    require(
        package_manifest['threshold'] == training_report['horizon_thresholds'][horizon]['threshold'],
        'acceptance condition failed at verifier source line 658',
    )
    package_manifests[horizon] = package_manifest
    model_evidence[horizon] = {
        "parent": expected_parent,
        "version": version["version_resource_name"],
        "artifact_uri": model.artifact_uri,
        "image_uri": model.container_spec.image_uri,
    }
require(
    len(set(production_aliases.values())) == 3,
    'acceptance condition failed at verifier source line 668',
)

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
require(
    len(listed_batch_jobs) == 3,
    'acceptance condition failed at verifier source line 683',
)
require(
    {job.name for job in listed_batch_jobs} == expected_batch_names,
    'acceptance condition failed at verifier source line 684',
)
batch_evidence: dict[str, dict] = {}
for horizon in HORIZONS:
    expected = run_manifest["batch_jobs"][horizon]
    job = job_service.get_batch_prediction_job(
        request={"name": expected["job_resource_name"]}
    )
    require(
        state_name(job.state) == 'JOB_STATE_SUCCEEDED',
        'acceptance condition failed at verifier source line 691',
    )
    require(
        job.model == expected['model_version_resource_name'],
        'acceptance condition failed at verifier source line 692',
    )
    require(
        list(job.input_config.gcs_source.uris) == [expected['input_uri']],
        'acceptance condition failed at verifier source line 693',
    )
    require(
        job.output_config.gcs_destination.output_uri_prefix == expected['destination_prefix'],
        'acceptance condition failed at verifier source line 694',
    )
    require(
        job.output_info.gcs_output_directory == expected['gcs_output_directory'],
        'acceptance condition failed at verifier source line 698',
    )
    require(
        job.service_account == deployment['batch_prediction_service_account'],
        'acceptance condition failed at verifier source line 701',
    )
    require(
        job.dedicated_resources.machine_spec.machine_type == deployment['batch_machine_type'],
        'acceptance condition failed at verifier source line 702',
    )
    batch_evidence[horizon] = {
        "job": job.name,
        "model": job.model,
        "input": expected["input_uri"],
        "output": expected["gcs_output_directory"],
    }

validation = run_result["validation"]
require(
    set(validation) == {'suite_version', 'snapshot_id', 'snapshot_content_sha256', 'feature_month', 'area_count', 'horizons'},
    'acceptance condition failed at verifier source line 713',
)
require(
    validation['suite_version'] == suite_version,
    'acceptance condition failed at verifier source line 721',
)
require(
    validation['snapshot_id'] == snapshot['snapshot_id'],
    'acceptance condition failed at verifier source line 722',
)
require(
    validation['snapshot_content_sha256'] == snapshot['snapshot_content_sha256'],
    'acceptance condition failed at verifier source line 723',
)
require(
    validation['feature_month'] == snapshot['latest_feature_month'],
    'acceptance condition failed at verifier source line 726',
)
require(
    validation['area_count'] == snapshot['area_count'],
    'acceptance condition failed at verifier source line 727',
)
require(
    set(validation['horizons']) == set(HORIZONS),
    'acceptance condition failed at verifier source line 728',
)
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
    require(
        read_ref(store, run_prediction_ref, f'{horizon} run prediction') == prediction_bytes,
        'acceptance condition failed at verifier source line 741',
    )
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
    require(
        len(frame) == 5718,
        'acceptance condition failed at verifier source line 757',
    )
    require(
        frame['admin_code'].nunique() == 5718,
        'acceptance condition failed at verifier source line 758',
    )
    require(
        not frame['admin_code'].duplicated().any(),
        'acceptance condition failed at verifier source line 759',
    )
    records = json.loads(frame.to_json(orient="records"))
    for record in records:
        validate_payload("prediction-record", record)
    expected_threshold = package_manifests[horizon]["threshold"]
    require(
        set(frame['threshold'].astype(float)) == {expected_threshold},
        'acceptance condition failed at verifier source line 764',
    )
    require(
        (frame['predicted_crisis'].astype(int) == (frame['probability_crisis'].astype(float) >= expected_threshold).astype(int)).all(),
        'acceptance condition failed at verifier source line 765',
    )
    require(
        set(frame['suite_version']) == {suite_version},
        'acceptance condition failed at verifier source line 769',
    )
    require(
        set(frame['horizon_months'].astype(int)) == {HORIZON_MONTHS[horizon]},
        'acceptance condition failed at verifier source line 770',
    )
    require(
        set(frame['vertex_model_resource_name']) == {suite_manifest['model_versions'][horizon]['version_resource_name']},
        'acceptance condition failed at verifier source line 771',
    )
    require(
        set(frame['vertex_model_version_id'].astype(str)) == {suite_manifest['model_versions'][horizon]['version_id']},
        'acceptance condition failed at verifier source line 774',
    )
    routed = partition_map.route(frame["admin_code"].tolist()).tolist()
    observed_clusters = [
        None if pd.isna(value) else int(value)
        for value in frame["cluster_id"].tolist()
    ]
    require(
        observed_clusters == routed,
        'acceptance condition failed at verifier source line 782',
    )
    require(
        all(((cluster is None) == (source == 'pooled_unmapped') for cluster, source in zip(observed_clusters, frame['prediction_source'].tolist(), strict=True))),
        'acceptance condition failed at verifier source line 783',
    )
    coverage = partition_map.assert_release_coverage(frame["admin_code"].tolist())
    source_counts = {
        source: int(frame["prediction_source"].eq(source).sum())
        for source in PREDICTION_SOURCES
    }
    require(
        sum(source_counts.values()) == 5718,
        'acceptance condition failed at verifier source line 796',
    )
    horizon_validation = validation["horizons"][horizon]
    require(
        set(horizon_validation) == {'row_count', 'partition_coverage_pct', 'source_counts'},
        'acceptance condition failed at verifier source line 798',
    )
    require(
        set(horizon_validation['source_counts']) == set(PREDICTION_SOURCES),
        'acceptance condition failed at verifier source line 803',
    )
    require(
        source_counts == horizon_validation['source_counts'],
        'acceptance condition failed at verifier source line 804',
    )
    require(
        horizon_validation['row_count'] == 5718,
        'acceptance condition failed at verifier source line 805',
    )
    require(
        horizon_validation['partition_coverage_pct'] == coverage,
        'acceptance condition failed at verifier source line 806',
    )
    admins = set(frame["admin_code"].astype(str))
    if canonical_admins is None:
        canonical_admins = admins
    else:
        require(
            admins == canonical_admins,
            'acceptance condition failed at verifier source line 811',
        )
    prediction_evidence[horizon] = {
        "rows": len(frame),
        "areas": len(admins),
        "source_counts": source_counts,
        "partition_coverage_pct": coverage,
    }

parity = load_json_file(parity_path, "fixed-sample parity evidence")
require(
    set(parity)
    == {
        "schema_version",
        "suite_version",
        "snapshot_content_sha256",
        "container_image_digest",
        "sample_sha256",
        "sample_size",
        "probability_tolerance",
        "horizons",
    },
    "fixed-sample parity report fields differ",
)
require(
    parity["schema_version"] == "fewsnet-fixed-sample-parity-v2",
    "fixed-sample parity schema differs",
)
require(
    SHA256_PATTERN.fullmatch(parity["sample_sha256"]) is not None,
    "fixed-sample SHA-256 is invalid",
)
require(parity["sample_size"] == PARITY_SAMPLE_SIZE, "fixed-sample size differs")
require(parity["suite_version"] == suite_version, "parity suite differs")
require(
    parity["snapshot_content_sha256"] == snapshot["snapshot_content_sha256"],
    "parity snapshot differs",
)
require(
    parity["container_image_digest"] == deployment["container_image_digest"],
    "parity image digest differs",
)
tolerance = float(parity["probability_tolerance"])
require(math.isfinite(tolerance), "probability tolerance must be finite")
require(0.0 <= tolerance <= 1e-12, "probability tolerance is too large")
require(set(parity["horizons"]) == set(HORIZONS), "parity horizons differ")

verified_sample_bytes: bytes | None = None
verified_parity: dict[str, dict] = {}
with tempfile.TemporaryDirectory(prefix="fewsnet-acceptance-parity-") as temp:
    temp_root = Path(temp)
    for horizon in HORIZONS:
        item = parity["horizons"][horizon]
        require(
            set(item)
            == {
                "model_version_resource_name",
                "row_count",
                "batch_input",
                "package_objects",
                "vertex_output_objects",
                "local_output",
                "container_output",
                "vertex_output",
                "local_vs_container_max_abs_probability_delta",
                "local_vs_vertex_max_abs_probability_delta",
                "local_vs_container_class_mismatch_count",
                "local_vs_vertex_class_mismatch_count",
            },
            f"{horizon} parity fields differ",
        )
        require(item["row_count"] == PARITY_SAMPLE_SIZE, f"{horizon} sample differs")
        version = suite_manifest["model_versions"][horizon]
        require(
            item["model_version_resource_name"] == version["version_resource_name"],
            f"{horizon} parity model version differs",
        )

        job = run_manifest["batch_jobs"][horizon]
        input_ref = item["batch_input"]
        require(
            input_ref["uri"] == job["input_uri"],
            f"{horizon} parity Batch input URI differs",
        )
        require(
            object_ref_dict(store.get_ref(input_ref["uri"])) == input_ref,
            f"{horizon} parity Batch input generation is not current",
        )
        input_bytes = read_ref(store, input_ref, f"{horizon} parity Batch input")
        instances = parse_jsonl(input_bytes, f"{horizon} parity Batch input")
        require(
            len(instances) >= PARITY_SAMPLE_SIZE,
            f"{horizon} Batch input is smaller than the fixed sample",
        )
        sample = instances[:PARITY_SAMPLE_SIZE]
        sample_bytes = canonical_jsonl(sample)
        if verified_sample_bytes is None:
            verified_sample_bytes = sample_bytes
        else:
            require(sample_bytes == verified_sample_bytes, "horizon samples differ")

        package_refs = item["package_objects"]
        require(
            isinstance(package_refs, dict) and set(package_refs) == set(PACKAGE_FILES),
            f"{horizon} package ObjectRefs differ",
        )
        package_dir = temp_root / "packages" / horizon
        package_dir.mkdir(parents=True)
        for filename in PACKAGE_FILES:
            package_ref = package_refs[filename]
            expected_uri = f"{version['artifact_uri']}/{filename}"
            require(
                package_ref["uri"] == expected_uri,
                f"{horizon} package URI differs for {filename}",
            )
            require(
                object_ref_dict(store.get_ref(expected_uri)) == package_ref,
                f"{horizon} package generation differs for {filename}",
            )
            (package_dir / filename).write_bytes(
                read_ref(store, package_ref, f"{horizon} package {filename}")
            )
        predictor = load_model_package(
            package_dir,
            expected_image_digest=deployment["container_image_digest"],
            expected_source_git_commit=deployment["source_git_commit"],
        )
        frame = pd.DataFrame(sample)
        local_records = prediction_records(
            predictor.predict_frame(frame).to_dict(orient="records"),
            f"{horizon} local predictions",
        )

        local_store = LocalArtifactStore(temp_root / "container-store" / horizon)
        local_artifact_uri = f"gs://parity-package/{horizon}"
        for filename in PACKAGE_FILES:
            local_store.upload_file(
                package_dir / filename,
                f"{local_artifact_uri}/{filename}",
            )
        app = create_app(
            environ={
                "AIP_HTTP_PORT": "8080",
                "AIP_HEALTH_ROUTE": "/health",
                "AIP_PREDICT_ROUTE": "/predict",
                "AIP_STORAGE_URI": local_artifact_uri,
                "FEWSNET_CONTAINER_IMAGE_DIGEST": deployment[
                    "container_image_digest"
                ],
                "FEWSNET_SOURCE_GIT_COMMIT": deployment["source_git_commit"],
            },
            store=local_store,
        )
        with TestClient(app) as client:
            response = client.post("/predict", json={"instances": sample})
        require(response.status_code == 200, f"{horizon} container prediction failed")
        response_payload = response.json()
        require(
            set(response_payload) == {"predictions"},
            f"{horizon} container response fields differ",
        )
        container_records = prediction_records(
            response_payload["predictions"],
            f"{horizon} container predictions",
        )

        output_prefix = str(job["gcs_output_directory"]).rstrip("/") + "/"
        live_output_refs = [
            object_ref_dict(ref)
            for ref in sorted(store.list(output_prefix), key=lambda ref: ref.uri)
        ]
        output_refs = item["vertex_output_objects"]
        require(
            isinstance(output_refs, list) and output_refs,
            f"{horizon} Vertex output ObjectRefs are missing",
        )
        require(
            output_refs == live_output_refs,
            f"{horizon} Vertex output inventory or generations differ",
        )
        raw_objects = [
            (ref, read_ref(store, ref, f"{horizon} Vertex output"))
            for ref in output_refs
        ]
        vertex_records = prediction_records(
            select_vertex_predictions(raw_objects, sample),
            f"{horizon} Vertex predictions",
        )

        local_bytes = canonical_jsonl(local_records)
        container_bytes = canonical_jsonl(container_records)
        vertex_bytes = canonical_jsonl(vertex_records)
        require_fingerprint(local_bytes, item["local_output"], f"{horizon} local output")
        require_fingerprint(
            container_bytes,
            item["container_output"],
            f"{horizon} container output",
        )
        require_fingerprint(
            vertex_bytes,
            item["vertex_output"],
            f"{horizon} Vertex output",
        )

        local_container_delta = maximum_delta(
            local_records,
            container_records,
            f"{horizon} local/container delta",
        )
        local_vertex_delta = maximum_delta(
            local_records,
            vertex_records,
            f"{horizon} local/Vertex delta",
        )
        reported_local_container_delta = validate_probability_delta(
            item["local_vs_container_max_abs_probability_delta"],
            tolerance,
            f"{horizon} reported local/container delta",
        )
        reported_local_vertex_delta = validate_probability_delta(
            item["local_vs_vertex_max_abs_probability_delta"],
            tolerance,
            f"{horizon} reported local/Vertex delta",
        )
        require(
            reported_local_container_delta == local_container_delta,
            f"{horizon} local/container delta was not recomputed",
        )
        require(
            reported_local_vertex_delta == local_vertex_delta,
            f"{horizon} local/Vertex delta was not recomputed",
        )
        local_container_mismatches = mismatch_count(local_records, container_records)
        local_vertex_mismatches = mismatch_count(local_records, vertex_records)
        require(
            item["local_vs_container_class_mismatch_count"]
            == local_container_mismatches
            == 0,
            f"{horizon} local/container classes differ",
        )
        require(
            item["local_vs_vertex_class_mismatch_count"]
            == local_vertex_mismatches
            == 0,
            f"{horizon} local/Vertex classes differ",
        )
        verified_parity[horizon] = {
            "batch_input": input_ref,
            "package_objects": package_refs,
            "vertex_output_objects": output_refs,
            "local_output": object_fingerprint(local_bytes),
            "container_output": object_fingerprint(container_bytes),
            "vertex_output": object_fingerprint(vertex_bytes),
            "local_vs_container_max_abs_probability_delta": (
                local_container_delta
            ),
            "local_vs_vertex_max_abs_probability_delta": local_vertex_delta,
            "local_vs_container_class_mismatch_count": local_container_mismatches,
            "local_vs_vertex_class_mismatch_count": local_vertex_mismatches,
        }

require(verified_sample_bytes is not None, "fixed sample was not verified")
require(
    hashlib.sha256(verified_sample_bytes).hexdigest() == parity["sample_sha256"],
    "fixed-sample SHA-256 was not recomputed from Batch input bytes",
)

endpoint_names = [
    endpoint.name
    for endpoint in endpoint_service.list_endpoints(request={"parent": parent})
]
require(
    endpoint_names == [],
    'acceptance condition failed at verifier source line 1081',
)
object_uris = [ref.uri for ref in store.list(f"{root_uri}/")]
unexpected_uris = [
    uri for uri in object_uris if not allowed_object_uri(root_uri, uri)
]
require(
    unexpected_uris == [],
    f"object store contains paths outside the allowed inventory: {unexpected_uris}",
)

for horizon in HORIZONS:
    alias_state = suite_manifest["alias_state"][horizon]
    require(
        alias_state == {'alias': 'production', 'version_resource_name': production_aliases[horizon]},
        'acceptance condition failed at verifier source line 1093',
    )

storage_client = storage.Client()
suite_updated = object_updated(storage_client, current["suite_manifest"])
month_updated = object_updated(storage_client, month_ref)
current_updated = object_updated(storage_client, current_ref)
require(
    suite_updated <= month_updated <= current_updated,
    'acceptance condition failed at verifier source line 1102',
)
require(
    timestamp(current['released_at_utc']) <= current_updated,
    'acceptance condition failed at verifier source line 1103',
)

evidence = {
    "acceptance_01_raw_panel_unchanged": raw_sha256_before,
    "acceptance_02_normalized_panel": {
        "rows": normalized_rows,
        "areas": normalized_area_count,
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
    "acceptance_12_fixed_sample_parity": {
        "report": parity,
        "recomputed": verified_parity,
    },
    "acceptance_13_validator": validation,
    "acceptance_14_allowed_artifact_inventory": {
        "endpoint_count": len(endpoint_names),
        "approved_object_count": len(object_uris),
        "unexpected_objects": unexpected_uris,
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

## 14. Run the local 2026-04 prediction experiment

This local-only experiment trains, reloads, and runs the approved fixed-
partition Random Forest suite for `0m`, `6m`, and `12m`. It is a workstation
reproducibility and output-contract check before any Vertex AI activity. It
does not call GCS, Vertex AI Custom Jobs, Model Registry, Batch Prediction,
online Endpoints, or the IPCCH release workflow, and it does not require a
shapefile.

### 14.1 Create or verify the Python environment

Use Python 3.12 and the already approved dependency file. The reviewed runtime
keeps `scikit-learn==1.8.0` and `imbalanced-learn==0.14.0`; do not alter those
pins or the existing compatibility bridge in `core.training`.

```bash
uv venv --python 3.12 .venv
UV_CACHE_DIR=/tmp/ipcch-fewsnet-uv-cache \
  uv pip install --python .venv/bin/python \
  -r requirements-fewsnet-partitioned-rf.txt
UV_CACHE_DIR=/tmp/ipcch-fewsnet-uv-cache \
  uv pip check --python .venv/bin/python
```

Run from a clean tracked worktree. The runner records `git rev-parse HEAD` and
rejects staged or unstaged tracked changes. The generated output root is
ignored and does not make the tracked worktree dirty.

### 14.2 Run the approved source pair

The full initial command is:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m \
  fewsnet_partitioned_rf_pipeline.cli.run_local_experiment \
  --panel "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.csv" \
  --normalization-audit "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.audit.json" \
  --feature-month 2026-04 \
  --output-root "Outcome/fewsnet_partitioned_rf"
```

Training uses the latest 36 distinct target periods with non-null labels at or
before the audited `latest_label_month`. The periods may contain calendar
gaps. The first 30 observed periods fit the temporary threshold-selection
model, the last six validate the threshold, and the final model refits on all
36. Training and validation start/end fields are bounds over those observed
period sets; they do not assert that every intervening calendar month is
labeled.

Success prints exactly one JSON object to stdout. Runtime failure prints one
JSON object to stderr and returns a nonzero exit code. The CLI intentionally
has no GCS, Vertex, registry, endpoint, Batch Prediction, or shapefile option.

### 14.3 Interpret the local artifact tree

```text
Outcome/fewsnet_partitioned_rf/
├── model_artifacts/{suite_version}/
│   ├── 0m/
│   ├── 6m/
│   └── 12m/
├── reports/{suite_version}/
│   ├── training_threshold_report.json
│   └── run_manifest.json
└── predictions/202604/
    ├── fewsnet_partitioned_rf_202604_scope_0m_predictions.csv
    ├── fewsnet_partitioned_rf_202604_scope_6m_predictions.csv
    ├── fewsnet_partitioned_rf_202604_scope_12m_predictions.csv
    └── run_summary.json
```

Each horizon directory is a seven-file
`fewsnet-local-model-package-v1` package for the local Python runtime. A local
package truthfully records local dependencies and blank Vertex identities. It
is not the digest-pinned `fewsnet-model-package-v1` used by the production
container and must not be registered or promoted as a production package.

Each prediction CSV has exactly 5,718 rows and the approved 22-column local
contract. `probability_crisis` is the continuous binary crisis probability.
`threshold` is the learned horizon-specific decision threshold, and
`predicted_crisis` is `1` exactly when `probability_crisis >= threshold`.
These files do not contain an IPC phase forecast, a categorical severity
forecast, a confidence interval, or a qualitative uncertainty label.

Population is copied from the raw last observation at or before `2026-04`; it
is not model-imputed. For the approved panel, 5,716 areas use a raw value from
`2024-10` and two areas remain null with `population_source=missing_raw`. The
run summary records that expected `5716 + 2` provenance split and the two
missing administrative codes.

The target months `2026-10` and `2027-04` are forecast horizons derived from
the `2026-04` feature frame. They are not observed evaluation labels. Do not
report future-horizon accuracy until matching observed labels exist.

### 14.4 Rerun and recover safely

Publication is no-overwrite by default. If any exact prediction CSV or
`run_summary.json` already exists, the runner fails before loading the large
panel. To replace the three prediction CSVs explicitly, rerun the full command
with `--overwrite`:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m \
  fewsnet_partitioned_rf_pipeline.cli.run_local_experiment \
  --panel "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.csv" \
  --normalization-audit "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.audit.json" \
  --feature-month 2026-04 \
  --output-root "Outcome/fewsnet_partitioned_rf" \
  --overwrite
```

Model packages and suite reports remain create-only. A fully valid existing
suite is reloaded and reused; a missing, differing, symlinked, or checksum-
invalid immutable artifact fails closed and is never overwritten.

For a new suite, the publisher atomically claims the versioned package root
first and the matching report root second before copying any member. A
concurrent publisher that loses either claim fails without altering those
roots. Cleanup recursively removes only roots that the current publisher
successfully claimed. If an owning process is hard-killed, a partial claimed
root may remain without a passed summary; that state is deliberately
fail-closed and is not accepted or reused as a complete result.

The early no-overwrite check is only an optimization. Each default-mode CSV
and the final summary is authoritatively published with exclusive creation, so
a rival file inserted after preflight is neither overwritten nor deleted by
the losing run. With `--overwrite`, `shutil.copy2` is used only when the exact
target is revalidated as an existing regular file; an absent target is still
created exclusively. A directory, symlink, junction, socket, device, or other
non-regular prediction/summary target is rejected in both modes, and the
runner never copies a CSV inside a directory target.

On an overwrite attempt, the accepted summary is removed before any CSV is
copied. The runner verifies each published CSV, stamps `completed_at_utc` only
after final packages, reports, and predictions have been published and
verified, then publishes canonical `run_summary.json` last and rechecks every
recorded package, report, and prediction checksum. Trust a run only when the
final summary has
`status: passed` and all referenced files still match those checksums. If a
run fails or the summary is absent, rerun the complete command; do not patch,
splice, or hand-edit one CSV or its checksum metadata.
