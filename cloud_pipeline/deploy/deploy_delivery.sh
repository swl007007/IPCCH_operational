#!/usr/bin/env bash
# Deployment definition for the request-driven October delivery (NOT run automatically).
# Inputs (explicit; no defaults invented): PROJECT, REGION, BUCKET (output root), REQUEST_BUCKET
# (only requests/<run_id>/run_manifest.json uploads; the trigger watches this bucket), IMAGE (digest-pinned),
# SA (runtime service account), NAMESPACE (configured release namespace), WORKFLOW_SA.
#
# Memory budget (Cloud Run job filesystem is in-memory): inputs ~3 GB (two history panels,
# template, six packages) + outputs ~7 GB (base/extended/normalised panels, audits, scope tables)
# + archive ~0.2 GB + process peak ~4.6 GB (FEWSNET, separate process; IPCCH ~2.4 GB chunked)
# => ~15 GB; 32Gi leaves headroom for pandas transient copies. 8 vCPU, 4 h task timeout.
set -euo pipefail
: "${PROJECT:?}" "${REGION:?}" "${BUCKET:?}" "${REQUEST_BUCKET:?}" "${IMAGE:?}" "${SA:?}" "${NAMESPACE:?}" "${WORKFLOW_SA:?}"
case "$IMAGE" in *@sha256:*) ;; *) echo "IMAGE must be digest-pinned" >&2; exit 2;; esac

gcloud run jobs deploy oct-delivery --project "$PROJECT" --region "$REGION" --image "$IMAGE" \
  --service-account "$SA" --memory 32Gi --cpu 8 --task-timeout 4h --max-retries 0 --tasks 1 \
  --command python3 \
  --args="-m,cloud.orchestrator.delivery_job,run,--output-root,gs://$BUCKET,--release-namespace,$NAMESPACE,--image-uri,$IMAGE"

# The workflow SA needs run.jobs.runWithOverrides on this job (roles/run.developer on the job resource)
# and actAs on the job's runtime SA; the trigger SA needs eventarc.eventReceiver + workflows.invoker;
# the Cloud Storage service agent needs pubsub.publisher.
gcloud run jobs add-iam-policy-binding oct-delivery --project "$PROJECT" --region "$REGION" \
  --member "serviceAccount:$WORKFLOW_SA" --role roles/run.developer

gcloud workflows deploy oct-delivery-trigger --project "$PROJECT" --location "$REGION" \
  --source "$(dirname "$0")/workflow.yaml" --service-account "$WORKFLOW_SA" \
  --set-env-vars "DELIVERY_LOCATION=$REGION,DELIVERY_JOB=oct-delivery,DELIVERY_OUTPUT_ROOT=gs://$BUCKET,DELIVERY_RELEASE_NAMESPACE=$NAMESPACE,DELIVERY_IMAGE_URI=$IMAGE"

gcloud eventarc triggers create oct-delivery-requests --project "$PROJECT" --location "$REGION" \
  --destination-workflow oct-delivery-trigger --destination-workflow-location "$REGION" \
  --event-filters "type=google.cloud.storage.object.v1.finalized" --event-filters "bucket=$REQUEST_BUCKET" \
  --service-account "$WORKFLOW_SA"
