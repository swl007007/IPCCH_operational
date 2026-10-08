# Design

## Layout

```text
Outcome/
  README.md
  manual_delivery/202609_h5/20260923_country_confidence_v3/  # compact final handoff
  model_delivery/october_cloud_delivery/oct-final-20261008a/  # unchanged
  migration_packages/october_cloud_delivery/
    README.md
    config.env.example
    runtime/          # current minimal Docker build context + lock
    deploy/           # preparation/delivery definitions + request helpers
    assets/           # rosters, geometry, histories, fixed panels, references
    models/           # exact accepted packages, deduplicated
    reference/        # small baseline outputs and relevant validation evidence
    inventory.json
  migration_packages/october_cloud_delivery.tar.gz
```

Generated payloads are ignored; the reusable builder/config templates/docs remain tracked under deploy/october_delivery/. No symlink/junction requirement across WSL and Windows. Do not rename existing cloud output paths solely for symmetry.

## Package construction
Use an explicit allowlist derived from the current build context and accepted consumed input map. Stage durable local copies of needed /tmp inputs before any manual move. Verify selected asset bytes against known consumed checksums, not historical provenance. Extract only required model/reference members from the accepted archive. Do not copy duplicate audit CSVs, full manual archives, or all prior cloud runs into the minimum package. Include runtime source plus Dockerfile/lock instead of requiring a local Docker daemon to export an image; destination image build may need network access.

The builder must fail rather than emit a complete-looking package if a mandatory input is missing or has different bytes. Use a unique staging directory; finalize only after inventory checks. Record source-to-member mapping for reproducibility, but package operation uses relative paths only. Archive member paths must be relative and safe to extract.

## Destination workflow
Promote the smallest reusable request-making behavior out of task-local examples into supported deploy entrypoints; preserve archived scripts unchanged. Destination config supplies project, region, request/output bucket, service accounts, namespace and digest-pinned image. Upload fixed payloads create-only and record returned generations/checksums; generate dependent manifests bottom-up. Preparation uses new observations on the destination project and the package's full local histories. A no-upload validation/dry-run mode checks inventory/config and displays actions. Cloud execution remains an explicit later operator step.

Keep model manifests and acceptance evidence honest: a new image URI must not be treated as proof of runtime equivalence. Document the fixed-input replay verification before accepting the destination binding. Reuse existing validation functions; no alternative prediction implementation.

## Relocation and authorized backup cleanup
Create a keep/delete map before changing the four September directories. Keep the final v3 verified archive (~229 MiB), the 12 top-level per-system delivery/reference CSVs, README and original metadata, inputs/ipcch_april_panel.csv, and reports/ipcch_four_target_training_replay.csv. These two small fixtures are consumed by tests/cloud/test_delivery_outputs.py:35,205,214; preserve them and update V3 at line 8. The compact handoff is about 250 MiB. Store original full-delivery manifests as historical metadata so they are not mistaken for the compact directory inventory.

After all required operational input bytes have been preserved in the migration package and checked, remove the three superseded directories and redundant expanded v3 files. User expressly authorized deleting backups after accepted offline replay. Do not create another full backup or rerun that replay. Verify kept file hashes and archive member inventory only; report exactly what was removed. The final archive can restore its packaged members, but deleted obsolete versions and raw panels excluded from that archive are not recoverable from it. Required raw history panels therefore must already exist in the verified migration payload. Roll back moves before deletion if any local check fails; do not promise rollback of deleted old versions.

Historical plans retain their original wording; a relocation index explains the compact current location. Cleanup leaves active raw datasets/model directories and October cloud results intact.

## Compatibility
Current Cloud Run/Batch behavior, source/fill semantics, model bytes, cloud output locations, and existing raw input directories remain unchanged. New package tools are local packaging/transfer aids. Folder organization is bounded to delivery outputs and documentation, not a repository-wide reshuffle.
