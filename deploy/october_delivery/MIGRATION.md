# October local migration package

This directory contains the runtime build context, six unchanged accepted model scopes,
full preparation rosters/geometries and nine remote-family histories, both consumed raw
history panels, the IPCCH April fixed panel, population references, retained WFP/ACLED
snapshots, and frozen scoring inputs/reference tables. Source object refs are historical
reference evidence only. Package construction does not establish destination acceptance.

## Local checks (no cloud credentials)

Run with Python 3.12. Keep working files and filled configuration outside the sealed package:

```sh
python deploy/migration_package.py verify .
python deploy/migration_package.py extract ../october_cloud_delivery.tar.gz ../relocated-package
cp config.env.example ../destination.env
# Fill destination.env with your destination resources, then load it:
set -a
. ../destination.env
set +a
python deploy/migration_destination.py upload --work ../upload-work
```

The last command is a dry run. Without `--execute` the destination helper verifies the
exact inventory and config, prints the proposed action, and never opens a cloud client.
No old project, repository checkout, `.trellis`, or original cache is required.
`inventory.json` records all payload paths, sizes and SHA-256; it excludes itself.
`source-map.json` records build-time sources for provenance only. Missing, extra,
modified, symlink, duplicate archive, and unsafe archive members fail verification.
Treat interrupted `.staging-*` directories as incomplete; final destinations are create-only.

## Destination steps (operator actions, not executed during packaging)

1. Create the destination buckets, Artifact Registry repository, service accounts, IAM,
   APIs and Earth Engine access. Set up provider access and Batch networking/quotas.
   The delivery script is a deployment definition, not a complete infrastructure bootstrap.
2. Build `runtime/` using its Dockerfile and locked requirements. Push the image and put
   its digest URI in IMAGE. Internet and destination credentials are required.
3. Install `runtime/requirements.lock.txt` in the operator's Python 3.12 environment for
   request generation. Upload assets/models create-only:

```sh
python deploy/migration_destination.py upload --execute --run-id migration-001 --work ../upload-work
python deploy/migration_destination.py prepare --execute --refs ../upload-work/uploaded_refs.json \
  --prepare-id prepare-001 --origin 2026-10 --cutoff 2026-10-08T23:59:59Z \
  --operator YOUR_NAME --work ../prepare-work
```

Uploads record server-returned object generations and local SHA-256. Repeated uploads
under the same prefix fail instead of replacing anything. Use a new ID after partial
failure. Preparation uploads its request but does not start a job. Run the
preparation planner in Cloud Run using the packaged runtime image. Set REQUEST_URI and
REQUEST_GENERATION from `../prepare-work/prepare_request_ref.json`, and set DEADLINE_UTC
to your authorized future UTC deadline (allow time for provider exports):

```sh
gcloud run jobs deploy oct-prepare-plan --project "$PROJECT" --region "$REGION" \
  --image "$IMAGE" --service-account "$SA" --memory 2Gi --cpu 1 \
  --max-retries 0 --tasks 1 --command python3 \
  --args="-m,cloud.orchestrator.prepare,plan,--request-uri,$REQUEST_URI,--request-generation,$REQUEST_GENERATION,--output-root,gs://$BUCKET,--earth-engine-project,$PROJECT,--batch-parent,projects/$PROJECT/locations/$REGION,--batch-image-uri,$IMAGE,--batch-service-account,$SA,--deadline-utc,$DEADLINE_UTC"
gcloud run jobs execute oct-prepare-plan --project "$PROJECT" --region "$REGION"
```

The planner submits Batch extraction. Wait for
`gs://$BUCKET/prepared/<prepare_id>/prepare_status.json` to report `succeeded`.
Download the exact generation of `prepared_manifest.json`, hash its bytes, and save
its URI/generation/SHA-256 as `../prepared_ref.json`. Keep generation as a string.
The three-field reference format matches `prepare_request_ref.json`.

4. Verify the destination image against the frozen inputs and all 30 reference scope
   tables plus diagnostic availability. Require exact IDs, discrete values and blank
   masks, with continuous atol=1e-12 and rtol=0. Record the actual check and operator,
   preserve its evidence outside the package. A changed image URI alone is not evidence.
   Write `../runtime-verification.json` only after that check passes:

```json
{
  "status": "passed",
  "image_uri": "THE_EXACT_DIGEST_PINNED_IMAGE",
  "requirements_lock_sha256": "SHA256_OF_runtime/requirements.lock.txt",
  "inventory_sha256": "SHA256_OF_inventory.json",
  "operator": "NAME_OF_PERSON_CONFIRMING_THE_CHECK",
  "evidence": "PATH_OR_URI_TO_ACTUAL_DESTINATION_VERIFICATION_REPORT"
}
```

The helper validates this receipt's identity fields; the operator is responsible for
confirming the referenced evidence. It does not perform or fabricate runtime equivalence.

```sh
python deploy/migration_destination.py delivery --execute --refs ../upload-work/uploaded_refs.json \
  --prepare-id prepare-001 --run-id delivery-001 --origin 2026-10 --operator YOUR_NAME \
  --prepared-ref ../prepared_ref.json --runtime-verification ../runtime-verification.json \
  --work ../delivery-work
```

This uploads environment/model manifests and acceptance records bottom-up using actual
new generations, then writes a validated local `run_manifest.json`. It intentionally
does not submit the delivery request. WFP/ACLED use the preserved keep snapshots; use the
existing converters and request contract for a later refresh. Use `--pointer-generation`
for a deliberate update to an existing release pointer; default zero requires a new one.

5. Deploy via `bash deploy/deploy_delivery.sh` after reviewing IAM and resource settings.
   Submit the generated request create-only to its printed REQUEST_BUCKET URI only when
   ready to trigger delivery. Verify destination job status, output inventories and release
   acceptance separately. Cloud deployment/provider access has not been tested by this package.

To submit the finished delivery request, use the URI printed by the helper:

```sh
gcloud storage cp ../delivery-work/run_manifest.json \
  "gs://$REQUEST_BUCKET/requests/delivery-001/run_manifest.json" --if-generation-match=0
```

Use the same run ID as in the generated manifest. Follow
`gs://$BUCKET/runs/delivery-001/run_status.json`; successful workflow submission alone
is not delivery completion.
