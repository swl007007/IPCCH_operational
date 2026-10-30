# CP0 receipt — workspace, preservation, baseline pins (Executor b9db2dbb, w19:pE)

Machine-readable pins: `cp0-pins.json` (sha256 9bfd4ff2…). Commands recorded there.

- Integration checkout `control-plane` @ 5e94e12 (branch task/ipcch-acledagg-hpt) untouched: 5 modified + 4 untracked
  research files + pre-existing `mlruns/` preserved byte-for-byte (hashes in cp0-pins.json); no reset/stash/edit.
- Isolated worktree `control-plane-origin-ablation`, branch `task/ipcch-validity-origin-ablation`, from 5e94e12.
  Snapshot commit 99f3ebd = byte copies of the CH-final overlay modules (dataset_input a6d05b24, features eace18fd,
  pooled d7f78e3a — equal to the CH build 3a577f07 overlay / image 2b18cf72…) and the CH/GPP tests. Image base commit is
  439a488; 5e94e12 adds only the HPT controller (not the training path).
- Baseline (CH-final) runs: H0 298c4718… (m-698519b8…), H6 00d4e94c… (m-46beb4c7…), H12 f436da15… (m-9da8be7f…);
  registered models `IPCCH Validity-augmented pooled (GOSIF v3 + CH validity 20261028) | …_hpt | H-month` v1. Uploaded
  CH configs equal the trial configs (checked). Retained predictions/memberships/overlays/labels/fit ledgers hashed.
- GitNexus: index control-plane-native @ 5e94e12 does not include the uncommitted CH edits; impact used with pinned-source
  fallback (manual reading of the 99f3ebd sources). Risks: plan_contexts CRITICAL, check_config CRITICAL, hpt_prepare /
  check_hpt_config / check_formal_contract / hpt_fit HIGH — mitigated by default no-op policy and inherited regressions.
- Pre-change regression baseline: first attempt invalid (ran in the worktree while editing; preserved as
  tests-before-INVALID-concurrent-edits); clean rerun from an exported 99f3ebd snapshot in scratch/origin-ablation-20261030/tests-before.

## Executor identity observations (live, not a fixed claim)
- Pane w19:pE throughout; Claude Code transcript/session context b9db2dbb-7cea-4332-9733-e49ab8204e28 (prior a98cf837).
- Herdr agent_session values observed for w19:pE: d4b38847-e00a-4b73-9b83-ab0adc34c3f2 (Supervisor read) and
  74f852bb-ce05-4dbc-b41f-8c9d74e8266d (2026-10-30T17:34:38Z agent list). Herdr's value changes with sub-process
  ownership (e.g. claude-mem observer children); recorded as observed transitions.
