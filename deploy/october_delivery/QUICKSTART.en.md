# Cloud delivery quickstart

Generate FEWSNET and IPCCH predictions for origin month **O**, **O+6**, and **O+12**.
Reuse the accepted models and fixed variables; no model training is required.
Remote-sensing features are updated in the cloud. The operator decides independently
whether to update ACLED and WFP.

For request-building commands and JSON examples, see the [operator runbook](README.md).

## Current deployment

| Setting | Value |
|---|---|
| Google Cloud project | `manuel-remote-sensing` |
| Region | `us-central1` |
| Request bucket | `gs://manuel-remote-sensing-oct-delivery-requests` |
| Data and output bucket | `gs://manuel-remote-sensing-oct-delivery-debug` |
| Preparation job | `oct-prepare-plan` |
| Delivery job | `oct-delivery` |
| Release namespace | `oct-staging` |

These are the October staging resources. Existing production consumers have not been switched over.

## 1. Update remote-sensing inputs

Create a new `prepare_id`, build and upload a preparation request, and execute
the Cloud Run job `oct-prepare-plan` with the request URI and object generation.
The planner submits a Cloud Batch job to extract EVI, FLDAS, VIIRS, and GOSIF
features for both systems.

Before continuing, wait for:

```text
gs://manuel-remote-sensing-oct-delivery-debug/prepared/<prepare_id>/prepare_status.json
```

Its status must be `succeeded`. Check `prepared_manifest.json` in the same directory
for each source's actual latest observation month. A provider's latest release may
lag behind O; missing months are filled from the same area's past observations and disclosed.

## 2. Choose ACLED and WFP inputs

For each source, choose one action:

- **keep**: retain the existing values from the frozen history panels.
- **refresh**: upload a compatible raw export and reference it through `raw_upload`
  in the run manifest. The system converts and assembles the features automatically.

The October request builder defaults to `keep` for both sources. Every uploaded
input reference must include its URI, object generation, and SHA-256 checksum.
See the [runbook](README.md#2-choose-acled--wfp) for the replacement JSON.

## 3. Submit the prediction request

Use a new `run_id` to build `run_manifest.json`, binding the successful preparation,
model packages, fixed inputs, and ACLED/WFP choices. Upload the manifest **create-only** to:

```text
gs://manuel-remote-sensing-oct-delivery-requests/requests/<run_id>/run_manifest.json
```

The upload starts **Eventarc → Workflows → Cloud Run job `oct-delivery`**.
No separate prediction server needs to be started.

A repeated notification for the same request returns its existing status without
recomputing. Use a new `run_id` when retrying a failed run or changing inputs.

## 4. Retrieve the delivery

All paths below are relative to the data and output bucket.

| Content | Path |
|---|---|
| Run status and errors | `runs/<run_id>/run_status.json` |
| 30 delivery CSVs | `deliveries/<run_id>/scopes/{0m,6m,12m}/{fewsnet,ipcch}/` |
| Geometries and population references | `deliveries/<run_id>/{fewsnet,ipcch}/` |
| Fill records and diagnostic availability | `deliveries/<run_id>/reports/` |
| Portable bundle for offline replay | `deliveries/<run_id>/webapp_model_bundle.tar.gz` |

Wait for `run_status.json` to report `succeeded`. A successful workflow submission
does not mean scoring has finished. Unsupported diagnostics remain blank with a
reason; predictions are still delivered.

The completed October example is `oct-final-20261008a`, with targets **2026-10,
2027-04, and 2027-10**. A local copy is available at
`Outcome/model_delivery/october_cloud_delivery/oct-final-20261008a/`.
It used `keep` for ACLED and WFP, EVI/FLDAS/VIIRS through 2026-08, and GOSIF through 2024-12.

## Moving to a separate Google Cloud project

Start with the local package already built under
`Outcome/migration_packages/october_cloud_delivery/`, or transfer its sibling
`october_cloud_delivery.tar.gz`. It includes all required fixed/history inputs and models,
not just the offline prediction bundle. See [migration commands](MIGRATION.md).

After extraction, from the package root:

```sh
python deploy/migration_package.py verify .
cp config.env.example ../destination.env
# Fill destination.env; keep it outside the sealed package.
set -a; . ../destination.env; set +a
python deploy/migration_destination.py upload --work ../upload-work
```

This is a dry run and does not use cloud credentials. The migration README supplies
explicit upload/request commands and destination prerequisites. Do not reuse the old
October request JSON in a new project.


You can keep the same Google login. A separate project, service accounts, and buckets
provide the separation from the other project. No retraining is required.

1. **Create the destination resources.** Enable billing and the required APIs for
   Cloud Run, Batch, Workflows, Eventarc, Pub/Sub, Storage, Artifact Registry, and
   Earth Engine. Register the destination project for Earth Engine and authorize
   the extraction identity. Create two buckets, an Artifact Registry repository,
   and runtime/workflow service accounts. Keeping `us-central1` avoids a region change;
   use a compatible request-bucket/trigger location. Preserve output-bucket versioning,
   uniform bucket-level access, and public-access prevention.
2. **Copy reusable inputs and the runtime image.** Copy the fixed assets, model
   packages, history panels, and successful prepared data needed for the next run.
   Failed runs and debug logs are not required. Keep the image digest-pinned.
3. **Update configuration and deploy.** Replace project, bucket, service-account,
   and image references in the preparation setup and October request builders.
   Deploy the preparation job separately, then use
   [deploy_delivery.sh](deploy_delivery.sh) for the delivery job, workflow, and trigger.
   Its required variables are `PROJECT`, `REGION`, `BUCKET`, `REQUEST_BUCKET`, `IMAGE`,
   `SA`, `WORKFLOW_SA`, and `NAMESPACE`. The script does not create the prerequisite
   resources or grant all IAM permissions. Configure storage/image access, Batch/EE
   permissions, service-account impersonation, and Eventarc/Workflow invocation;
   the workflow also needs permission to run the delivery job with argument overrides.
4. **Regenerate references.** Copying an object changes its URI and generation.
   Rebuild the affected input, prepared, and run manifests from the copied objects,
   including nested references. Update runtime/acceptance bindings for the destination
   image URI. Replacing bucket names in old JSON while keeping old generations will fail.
5. **Verify and switch.** Run delivery once using the same completed inputs and compare
   all 30 CSVs. Test a small remote-sensing update in the destination project. Once both
   work, switch the operator upload/download locations and disable the old delivery
   trigger. Retain the old results for rollback and leave unrelated project resources alone.

## Limits to remember

- The request builders are frozen October examples, not a general monthly CLI.
  For another month, explicitly update origin/cutoff and confirm model applicability.
- Provider availability determines the latest observation month; a cloud refresh cannot
  produce observations that have not been published.
- Historical diagnostics require accepted evidence for the exact model package and horizon.
- This document describes migration steps; it does not perform or validate a migration.

## Historical manual results

The final September handoff is isolated at
`Outcome/manual_delivery/202609_h5/20260923_country_confidence_v3/`.
Its verified archive, final CSVs and small comparison fixtures are retained; obsolete
backups and duplicate expanded files were removed. October cloud results remain in their
existing location. See the [output index](../../Outcome/README.md).
