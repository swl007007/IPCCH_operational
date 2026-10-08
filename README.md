# IPCCH monthly operational handover

Two supported entrypoints:

- **[September manual delivery](september_manual/README.md)** — final September CSVs and the independently replayable offline package.
- **[Cloud pipeline](cloud_pipeline/README.md)** — monthly operations, migration to your own Google Cloud project/buckets, compatible model updates and the accepted October fallback. Start with its [English quickstart](cloud_pipeline/QUICKSTART.md).

Models, fixed variables and required history are transferred once. Monthly operations choose the origin month and independent ACLED/WFP keep/refresh options; remote sensing preparation and manifest-triggered delivery use the existing cloud workflow.

Large local payloads are supplied separately from Git in the two folders. `cloud_pipeline/dist/cloud_pipeline.tar.gz` is the closed code/data handover; credentials, destination resources and the accepted container image transfer are documented prerequisites.

Unrelated research, raw inputs and old scripts were moved to the sibling `../legacy_archive/IPCCH_monthly_operational/` with original paths and a restore manifest. Git and developer controls remain here; neither public entrypoint depends on them. No accepted September/October inference was rerun for this reorganization.
