# Local migration package

## Scope

`deploy/october_delivery/migration_package.py` builds a standalone local handoff for the
October dual-system cloud workflow. It does not deploy cloud resources or train models.
`migration_destination.py` supplies destination-specific upload and request commands.

## Package contract

- The payload includes runtime source and locked requirements, full native rosters and
  geometry, nine remote-family histories, consumed history/fixed panels, reference data,
  all six unchanged model scopes, and frozen comparison inputs/outputs.
- Build from explicit local paths. Verify consumed artifact hashes; do not reconstruct
  historical source lineage. A missing/mismatched required input is a build failure.
- `inventory.json` lists relative member paths, sizes and SHA-256. Verification requires
  exact membership and bytes. It excludes itself. Symlinks and unsafe/duplicate archive
  member paths are rejected. Extraction requires a fresh destination.
- Do not include credentials, filled local configs, temporary logs or duplicate report
  archives. Filled config and working files belong outside the sealed package.
- Old source paths/object refs may appear in reference evidence, but are not runtime
  dependencies after relocation.

## Destination behavior

- Default dry-run verifies local inventory/config without opening a cloud client.
- `--execute` explicitly authorizes helper uploads; uploaded refs use actual returned
  generations and SHA-256, with create-only writes. New attempt means new work directory
  and prefix; a partial upload is never silently overwritten.
- Preparation binds full rosters/histories. Delivery requires a successful destination
  preparation and an operator-confirmed runtime-equivalence receipt bound to image,
  requirements lock and package inventory. Receipt identity checks do not independently
  prove the operator's evidence.
- Rebuild model/environment/request references bottom-up. Never replace bucket strings
  while retaining old generations. Delivery generation writes a local request; submitting
  that final request to the trigger bucket remains a separate explicit operator action.

## Output organization

- Current cloud outputs: `Outcome/model_delivery/october_cloud_delivery/`.
- Compact manual final delivery: `Outcome/manual_delivery/202609_h5/20260923_country_confidence_v3/`.
- Generated local migration payload/archive: `Outcome/migration_packages/` (ignored by Git).
- Historical original manifests describe the original tree; the compact folder has its
  own inventory. Preserve final CSV/fixture bytes and update live references when moving.
  Remove authorized backups only after required operational inputs are durable/verified.
