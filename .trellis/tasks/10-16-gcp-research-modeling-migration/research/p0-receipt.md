# P0 receipt — lifecycle start, pre-existing dirty-state preservation

Owner: executor (`gcp-research-executor`, session `228d9075-d67a-41c9-9f4c-7830cdac3b87`, pane `w14:p9`, terminal `term_65dee2e4ca9b6a`).

## Start receipt (2026-10-16)

- Command, run from the bound pane:
  `trellis-audit --repo '/mnt/c/users/swl00/ifpri dropbox/weilun shi/ipcch_monthly_operational' start gcp-research-modeling-migration` → exit 0.
- Durable controller record: run `1193a92d1b0e4118a464753e548e113f`, phase `active`, task_dir `.trellis/tasks/10-16-gcp-research-modeling-migration`, `base_sha=99d390b7df536ba8d2661b94a80f29d5abac09fd`, executor `herdr:claude` session `228d9075-…`, terminal `term_65dee2e4ca9b6a`.
- `task.json` status `in_progress`; `task.py current` resolves to this task. HEAD = base = `99d390b`.
- The unrelated active run `42ee3def…` (`ipcch-alphaearth-supervised-partition`, Food_Crisis_Cluster) was observed and not touched.

## Pre-existing dirty state (not part of this task)

At start, `git status` showed 76 entries: 73 pre-existing modified paths outside this task, plus this task's `task.json` (written by start) and the supervisor's untracked `executor-brief.md` and `supervisor-log.md`.

The 73 pre-existing paths were classified with `git diff --ignore-cr-at-eol HEAD`:

- `AGENTS.md`: content change (89 changed lines; the claude-mem context block).
- The other 72 paths (`.gitattributes`, `.gitignore`, spec indexes, two archived task directories, `PROGRESS.md`, `README.md`, `cloud_pipeline/**`, `september_manual/**`): line-ending-only differences (worktree CRLF, HEAD LF).

Preservation captured without modifying the worktree or index. Files are under `/home/swl007007/projects/food-crisis-research/preservation/predirty-20261016/`:

| Artifact | Identity |
|---|---|
| `paths.txt` | the 73 paths |
| `predirty-bytes.tar` | exact worktree bytes, sha256 `3473077cbe74deb1d76867bffb922f73dee131a1e21d8cf457c1d3c9a1e1e945` |
| `worktree-sha256.txt` | per-file sha256 of worktree bytes |
| `predirty.patch` | `git diff --binary HEAD` for those paths, sha256 `a0b24907acf4587e3256a34a7fdbbe4fab43e5f30ca20dcf2b584eb7bac859bf` |
| git ref | `refs/preserve/gcp-migration-predirty-20261016` → stash object `eaf802f38cccd5bd802f4c83a6277f9d91dc9b32` (`git stash create`; worktree untouched) |

## Final-close preservation/restore plan

The controller's `close()` (`herdr-audit-controller/trellis_audit.py:274-280`) refuses close while any non-task path is dirty. These edits belong to the user and must be neither committed nor discarded. Steps at close, after supervisor sign-off and once all task work is committed:

1. Re-verify each of the 73 files against `worktree-sha256.txt`. Any drift since capture means someone else edited them. In that case take a fresh capture the same way and report it before continuing.
2. Confirm that, other than this task's directory, the dirty set equals `paths.txt` exactly. Any other dirty path stops the close and is reported.
3. `git stash push -m "gcp-migration close preserve" -- <paths.txt>` saves the edits and restores those 73 files to HEAD bytes. Record the stash object id, and also point the preserve ref `refs/preserve/gcp-migration-close-<date>` at it so the edits survive any `git stash drop`.
4. Run `trellis-audit --repo '<exact path>' close` from the bound session. Verify the job via `status`/`show`.
5. Immediately afterwards run `git stash apply <object>`. Then re-verify every file against `worktree-sha256.txt`, which must be byte-identical. If apply conflicts or any hash mismatches, there is **no bulk tar extraction**, because a concurrent edit could be overwritten. Instead:
   - Stop only the affected restore.
   - Inspect the conflict and the current hash of each affected file.
   - Preserve both versions (current bytes copied aside, plus the stash/tar version).
   - Restore an individual file from the stash or tar only after verifying its current content is exactly the HEAD/archive bytes, so no intervening content is overwritten.
   - Report any file that cannot be restored that way to the supervisor rather than forcing it. (Supervisor correction, 2026-10-16.)
6. Keep the preserve refs and the tarball until the user says otherwise. Record the stash ids and verification result in the close evidence.

`PROGRESS.md` is one of the 72 CRLF-only paths. The task's ledger entry is staged as the HEAD (LF) blob plus the appended section, written to the index directly (`git hash-object -w` + `git update-index --cacheinfo`), which leaves the worktree line endings untouched. After commit, the same section is appended to the worktree file, so the user's CRLF state plus the new entry remains. Verified at that time; not yet done.

## Code lineage plan

Active code lives in a native-WSL clone of this repository at `/home/swl007007/projects/food-crisis-research/control-plane`, branch `gcp-research-migration`, created from `99d390b`. Integration code goes under `research_cloud/`. Before close, the clone's commits are fetched into the registered repository and merged into `feat/october-cloud-delivery`. The merge only touches `research_cloud/**` and this task directory, never the 73 preserved paths. The completion SHA is therefore a descendant of `base_sha`, and the audit snapshot contains the implementation. No other checkout is enrolled in trellis-audit and the executor is not changed.

Task evidence is written directly in this task directory in the registered repo, where the supervisor inspects it, and is committed there at checkpoints.
