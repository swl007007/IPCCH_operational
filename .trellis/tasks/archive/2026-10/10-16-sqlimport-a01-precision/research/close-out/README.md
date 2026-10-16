# Close-out: sqlimport-a01-precision (A01 repair)

- **Close audit:** job `5d2c1e92f84ad1ef0d6ffaac`, close-audit at `dbd4e06` (base `427e12d`), snapshot `40b986ba…`.
  - Result: **done**, severity **minor**, gate_open 0, verdict **findings**.
  - It resolves the originating `gcp-research-modeling-migration-A01` (cross-chunk precision), with no production-code defect and no material evidence gap.
  - Copy: `close-audit-5d2c1e92-result.json`.
- **Remaining audit debt (not waived): `sqlimport-a01-precision-A01`.** This is the disclosed lifecycle deviation: a direct native `task.py start`, then `trellis-audit resume-start`, instead of a wrapper-only start. What can be verified about the unreplayed start hooks is in `start-hook-verification.md`.
- **Close mechanics:**
  - the wrapper close only, on the first attempt;
  - the 73 pre-existing paths were stashed under a named stash (`stash-sha.txt`) for the close and restored straight after, byte-equal to the supervisor's backup (`restore-check.txt`);
  - `close-output.json` and `close-rc.txt` hold the close output and exit code.
