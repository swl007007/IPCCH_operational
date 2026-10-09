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

- Current runtime/handover root: `cloud_pipeline/` (accepted October outputs in `cloud_pipeline/fallback/october_2026/`); the `Outcome/...` paths of the October task were moved to the external legacy archive.
- Accepted September h5 manual delivery: `september_manual/` root files plus `inventory.json` (bytes preserved).
- September-origin 6m/12m results (2026-10-09): `september_manual/scopes/{6m,12m}/{fewsnet,ipcch}/`, `scopes/shared/`, `scopes/reports/`, with their own `scopes/inventory.json`. They follow the October fallback layout, ship no portable bundle and expose no 0m scope; the run workdir keeps the 0m tables and audits by hash only.
- Historical original manifests describe the original tree; each compact folder has its
  own inventory. Preserve final CSV/fixture bytes and update live references when moving.
  Remove authorized backups only after required operational inputs are durable/verified.
