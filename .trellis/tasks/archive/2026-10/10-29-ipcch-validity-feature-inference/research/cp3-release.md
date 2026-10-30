# CP3 local implementation release — Supervisor, 2026-10-30

CP1 accepted at operational commit 47b10f2. CP2 cloud work is released under research/cp1/supervisor-review.md; H2/H8 submitted once, H14 waits for successful wave-1 termination and fresh capacity. CP2 acceptance remains pending real artifacts.

Release independent local operational implementation, implement.md groups B–E and steps 4–11, while cloud jobs run. This ordering is explicitly allowed by implement.md line 13. Existing Executor w1A:p2 / session 6a490ae1-ee00-43f9-bdfc-c887c9816c09 remains owner. No Trellis Audit. No production deployment, live-current change or additional cloud mutation beyond the CP2 packet.

Implement the converged v2 contract, source stores and converters, shared-folder climate methods, feature assembly, inference validation/diagnostics integration and publication/compatibility boundaries with focused tests. Preserve FEWS scientific behavior. Inspect GitNexus impact before changing operational symbols; retain caller evidence, diffs, tests and checkpoints. Stage coherent sub-checkpoints for Supervisor inspection. Any fix to the known FEWS line-ending/hash issue must preserve canonical scientific asset bytes and retain the hash guard.

Keep the training worktree at clean 9aa9e54 until all submissions complete; C6/C7 uses the separate package worktree. Continue CP2 polling/harvest and report actual cloud outcomes. Unit/fixture implementation may proceed without new weights; final three-horizon E2E and acceptance cannot. The fixture conversion of an older H0 model is test evidence only, never a production substitution.
