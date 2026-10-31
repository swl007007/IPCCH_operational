# CP3 Supervisor checkpoint — local implementation accepted

2026-10-31. Source parent `70f9d10`; exact 19 product/test hashes are
`final/SHA256SUMS`, independently checked against the working tree, all OK.

## Accepted evidence

- Inspected submission/UTC freeze, literal FEWS inheritance, Workflow/setup argv,
  installed artifact verification and separate v2 image binding. Existing legacy
  operator destination is preserved; changing its top-level image is not a migration.
- Raw final logs (excluding named INTERMEDIATE runs): 18 files, 285 passed,
  0 failed/skipped, every CHILD-EXIT and paired exit file 0. Maximum RSS 489,972 KiB.
  `final/final-totals.txt` agrees. No redundant test rerun was needed.
- Actual build-context staging child exit 0, RSS 186,552 KiB. Streamed rehash of
  all 276 files / 2,370,588,224 bytes matches, no missing/extra files. INSTALL.json
  `33d1911918342e88817c367ac80f9c0a252c5486dd1f7fbb99063783bccfa3ba`.
- Context intentionally predates final submit_v2 source; re-stage from the commit.
  This proves staged payload integrity, not a successful container build/run.
- The old `final/runs-summary.txt` contains an intermediate workflow failure;
  the final workflow log records 1 passed and CHILD-EXIT=0. Retain/label that old
  summary rather than erasing the failed attempt.

## CP4 conditions

Disposition A's maintenance hold is only temporary. AC3 preserves existing
consumers; final FEWS-only rescoring must work with the new image, genuine runtime
compatibility evidence and supported acceptance/registration/initialization.
The inherited FEWS member alone is insufficient. Reject old-image publication
without v2 guards (B). Executor prepares the smallest supported C transition;
no retraining, fabricated acceptance, guard bypass or hand-edited initialized state.

The user preauthorized goal-scoped cloud operations on 2026-10-31; keep a concrete
bounded operation/evidence packet and Supervisor technical checks, without another
user permission gate. CP4 build/runtime evidence, CP5 full-roster current/readback
and CP6 closure remain mandatory. DA1-DA2 alone remain deferred. No cloud/image
success or whole-task acceptance is claimed here.
