# Pre-refactor source baseline and recovery

Status: source-control backup only; task remains planning. This is not a production rollback execution or a new application rollback feature.

## Pinned identities

- Accepted pre-refactor source: `422f92123932aabfc59b649b3faa90b6d4c0b6f4`.
- Remote base: `origin/feat/october-cloud-delivery`, synchronized to that commit.
- Remote annotated backup tag: `backup/ipcch-pre-refactor-20261030` (peels to the same commit).
- New work branch: `feat/ipcch-validity-feature-inference`; planning documents are separate commits above the baseline.
- Independent complete-history Git bundle: `/home/swl007007/backups/ipcch-operational-pre-refactor-20261030/repository.bundle`.
- Bundle SHA256: `a177b912b1561dda99b5897a04a0f75d2b3e5d9eeaf5446c1fbca644462d2c15`. Verified with `git bundle verify`; checksum file is adjacent.

## Non-destructive source recovery

Preserve unfinished work before any switch. To inspect or recover the old source without overwriting the refactor checkout, create a fresh directory:

```bash
git worktree add --detach /home/swl007007/backups/ipcch-recovery-422f921 backup/ipcch-pre-refactor-20261030
```

If the working repository is unavailable, restore from the bundle to a fresh directory:

```bash
git clone /home/swl007007/backups/ipcch-operational-pre-refactor-20261030/repository.bundle /home/swl007007/backups/ipcch-restored
git -C /home/swl007007/backups/ipcch-restored switch --detach 422f92123932aabfc59b649b3faa90b6d4c0b6f4
```

The bundle includes local branches and preserved refs, so keep it private. No reset, force push or deletion is needed for recovery.

## Coverage and execution boundary

Git backup covers tracked source and Git history, not ignored datasets, credentials, local runtime state, model binaries omitted from Git, or live cloud objects. Existing local artifacts are left untouched. Before any real production mutation, pin the actual deployed image digest, current release/model/input references and mutable-state recovery procedure in a separately reviewed execution packet. A source checkout alone does not roll back cloud services or retained-store changes.

No production resources were changed to establish this baseline. The existing application's no-rollback-interface decision remains unchanged; emergency operational recovery is separate from ordinary manifest functionality.

## Windows Git working-tree verification

Windows Git reported 354 modified archived research JSON files while WSL Git was clean. Every file was verified byte-identical to HEAD and parsed as JSON. Windows Git could not index their deep paths (`Filename too long`). Enabling repository-local `core.longpaths=true` removed all 354 false modifications. This setting is local Git configuration, not a tracked attribute; on another Windows checkout run `git config --local core.longpaths true`. No evidence JSON was rewritten or renormalized. Both Windows and WSL status were checked.
