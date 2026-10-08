# Impact and staged-change limits

GitNexus did not resolve new cloud_pipeline paths or the new operator CLI; upstream impact results were UNKNOWN. The prior indexed runtime test symbol returned LOW with no callers. Static AST/import and CLI-string checks identified the isolated old v1/debug chain; its copied files and tests were omitted while originals were preserved in the external archive.

The required detect_changes(scope=staged, repo=IPCCH_operational) returned low, three old Markdown symbols, 53 files and no affected processes. Windows Git actually reports 385 changed paths including runtime moves, so the index is stale/incomplete for this refactor. That result is not evidence of low overall risk. Verification uses Windows Git staged changes, isolated import/CLI tests, local fake-service tests and actual baseline member integrity. No graph reindex or extra task audit was launched.

Final pre-commit detect_changes attempt failed inside its WSL Git with loose-object Input/output error. Native Windows Git staged-diff and status succeed; no claim is made that the graph check passed. The source runtime had already passed isolated/archive-member checks.
