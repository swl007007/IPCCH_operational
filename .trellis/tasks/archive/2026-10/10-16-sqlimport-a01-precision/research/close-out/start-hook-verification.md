# Start-hook verification for deviation 2 (read only; nothing replayed, controller state unchanged)

The repair audit's finding `sqlimport-a01-precision-A01` asks that any required start-hook work not replayed by `resume-start` be verified from durable evidence. What can be verified:

1. **Configured native hooks: none.**
   - `.trellis/config.yaml` is identical at the run base `427e12d` (sha256 `a966e6d374e9e6ff…`) and at HEAD (`a966e6d374e9e6ff…`).
   - Its `hooks:` block is entirely commented out; no uncommented line mentions hooks or `after_start`.
   - So `run_task_hooks("after_start", …)` (`.trellis/scripts/task.py:254/268`, `common/task_utils.run_task_hooks`) had no command to run, with or without the wrapper.
2. **Wrapper start body.** Per the pinned controller source (`herdr-audit-controller/trellis_audit.py`, `start`), the wrapper:
   - inserts the run row (phase `starting`, base = HEAD);
   - invokes `task.py start <task_dir>`;
   - checks `status == in_progress`;
   - sets the phase to `active`.

   The native call that ran directly was that same command. `resume-start` then verified `in_progress` and HEAD == base `427e12d` before setting `active`.
3. **Native start effects** (`research/lifecycle/a01-start.txt`, in the archive):
   - "Current task set to: .trellis/tasks/10-16-sqlimport-a01-precision", source `session:claude_228d9075-…`;
   - status `planning → in_progress`;
   - the run then showed active, base `427e12d`, the same executor, and no error.

**Not verifiable / remaining debt:** that the native start was invoked by the wrapper process itself, as the lifecycle contract requires. It was not, and that is the recorded contract violation. It stays open as audit debt; it is not waived.
