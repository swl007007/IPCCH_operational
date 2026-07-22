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
test "${#SOURCE_GIT_COMMIT}" -eq 40
mkdir -p "$FEWSNET_LOCAL_STAGE_ROOT"

gcloud auth application-default print-access-token >/dev/null
gcloud config set project "$PROJECT_ID"
gcloud config set ai/region "$REGION"
```

The raw panel and boundary paths above are examples of operator-supplied
variables. Do not put workstation-specific source paths into code, Docker
configuration, deployment manifests, or recurring commands.

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

NORMALIZED_PANEL="$NORMALIZED_PANEL" \
NORMALIZATION_AUDIT="$NORMALIZATION_AUDIT" \
FEWSNET_BOUNDARIES_PATH="$FEWSNET_BOUNDARIES_PATH" \
CREATED_AT_UTC="$CREATED_AT_UTC" \
LOCAL_OBJECT_STORE="$LOCAL_OBJECT_STORE" \
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
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
print(json.dumps(asdict(manifest), indent=2, sort_keys=True))
PY
```

Only after local staging passes, stage the same files to the configured GCS
root. `source_manifest.json` is written last and the CLI prints its URI:

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

Grant object-level access on only the suite bucket. All three identities must
read immutable inputs; the orchestrator, training worker, and Batch worker also
write their own evidence/output prefixes:

```bash
for service_account in "$ORCHESTRATOR_SA" "$TRAINING_SA" "$BATCH_SA"; do
  gcloud storage buckets add-iam-policy-binding "gs://${ARTIFACT_BUCKET}" \
    --member="serviceAccount:${service_account}" \
    --role="roles/storage.objectUser"
done
```

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

Grant `iam.serviceAccounts.actAs` through Service Account User. The human or CI
submitter may act as the orchestrator; the orchestrator may act only as the
training and Batch runtime accounts:

```bash
gcloud iam service-accounts add-iam-policy-binding "$ORCHESTRATOR_SA" \
  --project="$PROJECT_ID" \
  --member="$SUBMITTER_MEMBER" \
  --role="roles/iam.serviceAccountUser"

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

If the image repository is in a different project, grant Artifact Registry
Reader there to the relevant Google-managed Vertex/Cloud Run service agents as
well. Do not compensate with project Owner or Editor.

## 6. Create and publish an immutable deployment manifest

The schema requires the three stable model IDs. On the first successful
registration, Vertex creates each parent and assigns the first numeric version;
later runs add versions under the same parents.

```bash
export DEPLOYMENT_VERSION="${SOURCE_GIT_COMMIT:0:12}-${IMAGE_DIGEST#sha256:}"
export DEPLOYMENT_MANIFEST_LOCAL="${FEWSNET_LOCAL_STAGE_ROOT}/deployment-${DEPLOYMENT_VERSION}.json"
export DEPLOYMENT_MANIFEST_URI="${OBJECT_STORE_ROOT_URI}/deployments/deployment-${DEPLOYMENT_VERSION}.json"

PROJECT_ID="$PROJECT_ID" \
REGION="$REGION" \
OBJECT_STORE_ROOT_URI="$OBJECT_STORE_ROOT_URI" \
ORCHESTRATOR_SA="$ORCHESTRATOR_SA" \
TRAINING_SA="$TRAINING_SA" \
BATCH_SA="$BATCH_SA" \
IMAGE_URI="$IMAGE_URI" \
IMAGE_DIGEST="$IMAGE_DIGEST" \
SOURCE_GIT_COMMIT="$SOURCE_GIT_COMMIT" \
DEPLOYMENT_MANIFEST_LOCAL="$DEPLOYMENT_MANIFEST_LOCAL" \
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
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
Path(os.environ["DEPLOYMENT_MANIFEST_LOCAL"]).write_text(
    json.dumps(deployment, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

gcloud storage cp --if-generation-match=0 \
  "$DEPLOYMENT_MANIFEST_LOCAL" "$DEPLOYMENT_MANIFEST_URI"
gcloud storage objects describe "$DEPLOYMENT_MANIFEST_URI" \
  --format='yaml(name,generation,size,updateTime)'
```

Do not overwrite a deployment manifest. Publish another versioned object when
the image, commit, IAM identity, machine type, timeout, or retry policy changes.

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

Without `FEWSNET_GCP_SMOKE_ENABLED=1` and both manifest URIs, the smoke test is
an explicit skip. Do not point this test at the production project.

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

Compare the three output row counts and unique area counts directly:

```bash
for horizon in 0m 6m 12m; do
  gcloud storage cat \
    "${OBJECT_STORE_ROOT_URI}/runs/${RUN_ID}/predictions/${horizon}.csv" \
    | HORIZON="$horizon" .venv/bin/python -c \
      'import os,sys,pandas as pd; f=pd.read_csv(sys.stdin); print(os.environ["HORIZON"], "rows", len(f), "areas", f["admin_code"].nunique()); assert len(f)==5718 and f["admin_code"].nunique()==5718'
done
```

Do not call the first production run accepted until all sixteen items are
recorded. Local implementation tests, a skipped smoke, or a successful image
build are not production acceptance.
