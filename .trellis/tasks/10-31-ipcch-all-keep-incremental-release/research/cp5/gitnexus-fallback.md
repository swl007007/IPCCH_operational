Task-local research helpers (not product code, not in the GitNexus index); callers: only CP5 readback commands in this task. Supervisor-requested readback corrections; no product symbol touched.

## 2026-11-01 03:45Z: acled_cutoff.summarize edit (actual impact request made first)
- Request: `impact(target="summarize", direction="upstream", repo="IPCCH_operational", file_path=".../cp5/acled_cutoff.py")`.
- Response: `{"error": "Target 'summarize' not found", "impactedCount": 0, "risk": "UNKNOWN"}`. The file was created after the index was built and is a task-local research script.
- Manual callers: acled_cutoff.main and test_acled_cutoff only.
- Reason: the sidecar CSV serializes source_version as "2.0", because pandas makes the column float when other sections have no version. A string comparison against 2 failed, so the comparison becomes numeric and the raw distinct values are reported. The first result is kept as acled-cutoff.INTERMEDIATE-string-version-compare.*.
