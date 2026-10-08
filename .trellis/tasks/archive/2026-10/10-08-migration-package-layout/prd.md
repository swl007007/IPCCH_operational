# Local migration package and delivery folder organization

## Goal
Give an operator a local, portable handoff for redeploying the accepted October FEWSNET/IPCCH cloud workflow into an independent GCP project, and separate historical manual deliveries from current cloud outputs.

## Background
The current deployment belongs to another project. Its replay bundle supports scoring but omits full history inputs required to refresh remote sensing. The missing operational inputs are available in local working caches and existing delivery directories. Four September manual versions total 485 files (~15.8 GiB), mostly repeated full panels and expanded geometry. The user confirmed existing offline replay is verified and authorized deleting redundant backups. See research/local-inventory.md for paths and evidence.

## Requirements
- R1: Build an actual local migration directory and distributable archive containing the runtime/deployment source, locked dependencies, accepted six model scopes, fixed/history inputs, full rosters/geometries, remote-family histories, configuration templates, and concise instructions. Exclude credentials, filled personal configuration, caches, failed jobs, and unrelated project content.
- R2: Support destination project/bucket/service-account/image configuration without requiring this checkout, its .trellis directory, original /tmp caches, or read access to the old cloud bucket. Reuse current converters, schemas, and package formats. Building an image and obtaining new provider data can still require internet and destination credentials.
- R3: Document and provide the minimal upload/request-building path that captures destination object generations and rebuilds dependent references/runtime bindings. Do not ship an old request as a ready-to-submit destination request or claim model acceptance solely by changing metadata.
- R4: Isolate the final September v3 handoff at Outcome/manual_delivery/202609_h5/20260923_country_confidence_v3/. Retain its verified archive, final CSVs, small metadata, and the two inputs/reports required by current parity tests. Remove superseded v1, superseded CIV-mapping, and v2 backup directories, plus redundant expanded v3 content, only after migration-required inputs are durable and checksummed. Preserve October cloud results in their current location. Update live consumers/ignore rules and record the keep/delete map. Old manifests describe the original delivery; distinguish them from the compact-folder inventory.
- R5: Keep folder cleanup bounded to delivery artifacts and navigation: introduce a clear Outcome index and migration package location. Leave raw source directories, active models, existing pipeline intermediates, archived task evidence, and historical document bodies in place.
- R6: Update the root README, October operator README, English Quickstart, and affected Chinese quickstart links/paths to explain the current cloud workflow, package use, manual archive location, and remaining destination deployment steps.
- R7: Use Windows Git and tolerate WSL/DrvFS read failures with native Windows file operations. No close/spot audits.

## Acceptance criteria
- AC1 (R1-R3): The generated directory/archive has an exact relative-path inventory, sizes and SHA-256 checksums; extraction verifies all expected bytes and detects missing/unexpected members. It contains complete local payloads rather than cloud-only pointers.
- AC2 (R1-R3): The package can be relocated outside the repository; its local validation and request-generation checks run without .trellis or /tmp dependencies. Destination refs use actual upload generations; a dry run makes no cloud mutations. No credentials or filled local account configuration are included.
- AC3 (R3): Existing models are preserved byte-for-byte. Rebinding runtime acceptance requires a documented verification gate; package construction does not claim destination deployment or provider access has been tested.
- AC4 (R4-R5): Kept manual deliverables preserve identical bytes. The compact v3 handoff is approximately 250 MiB (verified archive plus final CSVs and parity fixtures), releasing roughly 15.6 GiB of backup/expanded data. The delete list is explicit and all migration-required assets are verified in durable storage before deletion. Live September parity tests still execute instead of silently skipping. No additional full backup is created.
- AC5 (R6): Documentation links resolve and clearly separates manual deliveries, October cloud deliveries, and the migration package. The legacy cloud path is not presented as the current October workflow.

## Out of scope
Actual cloud uploads/deployment/cutover, billing/IAM changes, training, historical source tracing, provider downloads/full remote refresh, broad pipeline refactoring, deleting the final accepted delivery archive or unique operational inputs, and close/spot audits. Existing accepted offline replays will not be repeated merely for cleanup. No change to prediction or fill semantics. Initial implementation request and task-creation approval do not authorize cloud migration.

## Completion status

User approved the revised plan and backup cleanup. Implementation and local checks completed; see completion.md and research/*.json. No destination cloud migration was performed.
