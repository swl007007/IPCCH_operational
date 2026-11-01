# Earth Engine runtime asset-access recheck

- Result: PASS for the enumerated read-access checks; this is not incremental E2E acceptance.
- Completed UTC: 2026-11-01T00:09:18.567400+00:00
- Verified runtime identity (Cloud Run execution and metadata server): `monthly-runtime@feisty-flames-511718-d4.iam.gserviceaccount.com`.
- Successful execution: `ipcch-v2-runtime-preflight-20261031-rpsqj`; succeededCount 1.
- 151/151 unique enumerated assets returned metadata; 0 unreadable; 0 unattempted.
- Actual EE expression evaluations: admin G00 size = 250; CHIRPS M01 bandNames = 33 bands.
- Coverage: 25 admin collections; 36 rain, 24 temperature and 24 soil baselines; 8 VI baseline tables; 18 PRCP, 6 ET0 and 6 PATCH32 historical chunks; 4 conditional VI current tables (TERRA/AQUA for 2025/2026).
- Source root: `projects/han-sandbox-505315/assets/`.

## Scope and limits

The existing isolated preflight job was used with per-execution argument overrides, 1 CPU / 512 MiB, 300 seconds, one task and zero task retries. The inherited probe image is the earlier 487a2315 digest; this recheck proves asset access by the production service-account identity, not a rerun of the deployed v2 image or pipeline. No asset exports, asset or IAM writes, monthly submission, or current publication were performed.

Incremental DA1/DA2 remain untested: real export to the feisty asset root, export readback, PATCH32/VI processing, retained append, features, inference and publication. Full asset contents and numerical outputs were not validated here. Future assets or a changed dependency set need their own access check. UTC is now November 2026; a new monthly submission freezes M=2026-11.

## Preserved unsuccessful attempt

Execution `ipcch-v2-runtime-preflight-20261031-t49gv` exited 1 before any asset read: the diagnostic called ee.data.setDeadline before ee.Initialize, triggering an SDK assertion. Runtime identity was confirmed, but this attempt is not asset-permission evidence. `probe-v2.py` removes the premature settings; the bounded recheck above succeeds. Both attempts and raw logs are retained.

## Evidence

- `summary.json`: final read/compute summary.
- `family-counts.json`: per-family totals.
- `asset-inventory.json`: exact 151-asset scope.
- `v2-logs-1.json`: raw Cloud Logging readback.
- `v2-execution-1.json`: completed execution record.
- `probe-v2.py` and `execute-v2-command.json`: exact successful code and invocation.
- `job-describe.json`: original probe job definition.

Local consistency checks matched every result to the inventory, verified the actual execution arguments and service account, and checked succeededCount and both evaluated outputs.
