# Executor handoff (durable; for compaction/resume)

Identity at 2026-10-31:
- Model: Opus 5.5 (`claude-opus-5-5[1m]`).
- Pane w1A:p8. Conversation session `6a490ae1-ee00-43f9-bdfc-c887c9816c09`; Herdr reports the same session id.
- Process PID 4871 (started 09:33:39). It was launched as `claude --resume 8086f8e0…` and switched in-session to `6a490ae1` by the Supervisor's `/resume`. `8086f8e0` is the claude-mem observer session.
- Supervisor: Codex, pane w1A:p2.

## State
- **Committed:** CP0-CP2 accepted. CP2 commit is `70f9d10`.
- **CP3:** implemented and uncommitted. Report: `cp3/cp3-report.md`; frozen hashes `cp3/final/SHA256SUMS`; 285 passed in 18 guarded files.
  - Supervisor review is pending. The Supervisor commits.
- **Real selection:** prepared at `~/ipcch-operator/food-crisis-test/v2-inputs/real-20261031/` (ACLED `7bcb051f…`, selections `2d8da49d…`).
- **Staged build context:** `~/ipcch-operator/food-crisis-test/v2-build/stage-20261031T015828Z/tmp.lACWLdxwS7`. Re-stage it from the final commit before building.
- **`project.json`:**
  - backups `.bak-cp3-20261031T015130Z` and `…015945Z`;
  - `work_dir` kept (legacy-correct);
  - `v2` section added; `v2.image_uri` stays absent until the build;
  - the top-level `image_uri` stays legacy (`487a2315…`) and is NOT updated.

## Rules in force
- Every test runs through `research/cp2/guarded.sh` (MemoryMax 4G, no swap, 600 s, prlimit 3 GiB), sequentially. `.exit` = child exit.
- Cloud operations within the goal are preapproved by the user. Still run concrete bounded packets behind Supervisor technical gates.
- No resource enlargement, retraining, DA1/DA2, history deletion, push/merge or Audit. Never touch AGENTS.md or PROGRESS.md.
- **CP5 (full 6,226-area real E2E + current readback) is MANDATORY this round. Only DA1 and DA2 are deferred.**
- Compatibility:
  - disposition A (v2 image plus maintenance hold) is acceptable only as a TEMPORARY cutover;
  - B is rejected;
  - C (FEWS re-acceptance on the new runtime plus a new initialized destination) must be planned. See `cp4/compatibility-transition-plan.md`.

## Next
- Finish `cp4/compatibility-transition-plan.md` and the bounded CP4 cloud packet.
- Send ONE gate notification to the Supervisor.
