# Final preservation check (integration checkout control-plane)

- HEAD 5e94e12 equal to CP0; all 9 preserved files byte-equal to their CP0 sha256 (PROGRESS.md, RUNBOOK.md, dataset_input.py,
  ipcch_validity_features.py, ipcch_validity_pooled.py, 4 untracked CH/GPP tests); mlruns/ untouched.
- `git status --porcelain` identical to CP0 except a receipt artifact: cp0-pins.json stored the porcelain output after
  `.strip()`, which removed the leading space of its first line (" M PROGRESS.md" recorded as "M PROGRESS.md"); the file's
  hash is unchanged.
- Research worktree control-plane-origin-ablation clean at 868db9f (commits 99f3ebd, 7023d10, 868db9f).
- Operational repo: task evidence committed in ad34381 (task directory only); the preexisting AGENTS.md change left unstaged.
