# CP3 root check: executed once, PASSED (task 10-31, D5)

- **Job:** `ipcch-ee-root-check-20261101` was created from `root-check-job.json` (3a89b5c1; payload f1cf0b28) after a fresh nonexistence check.
- **Definition readback:** all 9 fields match (`exec/2-definition-check.txt`).
- **Execution:** ONE execution, `ipcch-ee-root-check-20261101-6z5f2`, 02:17:13–02:18:51Z; succeededCount 1; Completed True (`exec/4-execution.json`). The cloudop execute call ran 02:16:53–02:19:04Z with rc 0.

**Result** (`exec/4-root-check-result.json`; the single `IPCCH_ROOT_CHECK` line from 5 log entries in `exec/4-logs.json`):
- **Runtime identity:** metadata-server email `monthly-runtime@feisty-flames-511718-d4.iam.gserviceaccount.com` (the identity gate passed). The ADC SA email is reported as `default`.
- **Steps:**
  1. `list_root`: HTTP 404, `Asset "projects/feisty-flames-511718-d4/assets" not found.` This is the pre-state that the 10-31 failure hit.
  2. `create_root_folder`, ONE call: OK. `{id/name: projects/feisty-flames-511718-d4/assets, type: FOLDER, quota: maxAssets 50000, maxSizeBytes 268435456000}`.
  3. `relist_root`: OK, `{"assets": []}`.
  4. `transport_missing_assets_absent_child` (pinned `EETransport`): `[projects/feisty-flames-511718-d4/assets/IPCCH_ROOT_CHECK_ABSENT_20261101]`, i.e. reported absent.
- **Outcome:** branch `created`, `passed` true, budget left 231 s.

**What this establishes:**
- The feisty asset root was ABSENT, which resolves the CP2 missing-root versus access uncertainty for this identity.
- The runtime SA can create the root FOLDER and list it.
- The product transport's absence resolution now works for a feisty child.

**Still unproven until CP4:**
- `Export.table.toAsset` task submission and completion, and readback of produced tables under the runtime SA;
- September 2026 source completeness.

**Monthly deployment preserved:** `oct-delivery`, `monthly-prepare` (image, args, limits, retries, SA) and Workflow rev `000005-e86` (env, source sha) equal the CP0 live values (`exec/5-preservation.txt`).

**Other changes:** no IAM, billing or registration change; no export; no scientific asset; no monthly submission. The job definition and execution are retained.
