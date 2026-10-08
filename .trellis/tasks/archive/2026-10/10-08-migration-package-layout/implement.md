# Implementation plan

## Gate
Await approval of the latest scope/layout summary. Then activate this task using the current authorized lifecycle; do not enroll in or launch close/spot audits. Use Windows Git for all version-control operations. Use GitNexus impact analysis before changing existing functions/classes; report HIGH/CRITICAL findings before editing.

## Steps
1. Finalize an explicit input-to-package map using research/local-inventory.md, current consumed-input references, and local paths. Confirm required fixed panel bytes without historical source tracing. Record workspace/disk availability and protect against destination collisions.
2. Implement the smallest local package builder and destination-configurable upload/request helpers beside deploy/october_delivery, reusing existing build scope, validators, and converters. Keep archived task scripts unchanged. Add focused checks for missing payloads, wrong checksums, invalid/unsafe paths, destination ref regeneration, and dry-run behavior.
3. Build the package from local data into a staging directory, verify inventory, finalize the archive, extract to a separate directory and check relative paths/dependency completeness. Preserve six accepted model scopes and include baseline comparison material. No cloud calls.
4. Record an explicit keep/delete map. Verify the final v3 archive and retained CSV/fixture bytes; stage the compact final handoff under Outcome/manual_delivery/202609_h5/20260923_country_confidence_v3. Only after migration-required inputs are durably preserved and verified, delete the three superseded September versions and redundant v3 expanded content. Do not hash or back up every obsolete file, and do not rerun accepted offline replay. Record reclaimed space and irreversibility of deleted versions. Preserve active raw/model directories and current cloud results.
5. Update live consumers (including the September v3 parity fixture), ignore rules, Outcome navigation, root README, October README, English Quickstart and affected Chinese quickstart content. Distinguish legacy EVI/Vertex instructions from current October delivery.
6. Run focused packaging/request-helper tests, relocation inventory checks, existing September output parity tests (verify they execute rather than skip), and documentation/link/whitespace checks. Run the relocated package local check without cloud credentials. Broaden testing only if changes introduce unresolved concerns.
7. Record exact artifact paths, compressed/uncompressed sizes, SHA-256, checks run, remaining destination prerequisites, and the exact retained/deleted inventory. Do not claim cloud migration completed. Keep unrelated existing edits untouched. Do not launch close/spot audit.

## Risks and rollback
- WSL/DrvFS EIO: use native Windows Python/Git for repository IO; retain staged local inputs until successful durable verification.
- Large history payload: a full operational migration package is larger than an offline prediction bundle; use one copy per required asset and avoid duplicate report archives.
- Interrupted build/cleanup: stage create-only, never merge directories, keep the keep/delete map, and perform deletion only after durable required-asset verification. Deletion of obsolete versions is intentionally irreversible; do not create a full backup that defeats the requested cleanup.
- No destination project supplied: use explicit placeholders; do not fabricate resources, generations, or accepted runtime evidence.
