# Recovery options after the failed attempt (task 10-31)

**Status.** Nothing below has been executed. The spec permitted ONE monthly attempt, and it is spent. Any project-side change, runtime diagnostic job or second submission needs a user scope decision first; the Supervisor then technically reviews the exact packet.

**Facts** (`failure-report.md`):
- the failure happened before any export, at the destination-absence check;
- HTTP 404 NOT_FOUND listing `projects/feisty-flames-511718-d4/assets`, both under the runtime SA (`roles/earthengine.writer`) and under the local EE credentials (caller identity not established);
- current is unchanged;
- the ACLED refresh is retained as v2 (exact).

**Unresolved:** whether the feisty Earth Engine asset root is absent or uninitialised, or whether this is an identity or access problem for both callers.

## Smallest next action (recommended): resolve the root, outside this spec's mutation scope

1. **Project owner (user) step: make the feisty EE asset root exist.** For example, confirm or complete the Earth Engine registration of Cloud project `feisty-flames-511718-d4` for this use, in the Cloud Console or EE Code Editor.
   - This is a project-administration action by an owner, not a code or deployment change.
   - Do NOT invent an SDK bootstrap call: the `createAssetHome` documentation and tests only cover legacy user roots (`../supervisor-ee-root-notes.md`).
   - Keep `producer_asset_root` unchanged. It is installed in the image's `/opt/ipcch/deployment.json`, so changing it to a subfolder would require a rebuild and deploy.
2. **Read-only verification, owner identity:** `ee.data.listAssets({"parent": "projects/feisty-flames-511718-d4/assets"})` must return a listing (possibly empty), not 404.
3. **Runtime-identity verification.** This is the only way to prove the runtime SA can list the root. It would be a NEW short-lived Cloud Run job, so it needs a decision; it is proposed, not launched:
   - job `ipcch-v2-root-check-<date>`, image `acc3e467`, SA `monthly-runtime`, 1 CPU/512 MiB, 300 s, 1 task, 0 retries;
   - command `python3 -c` with only:
     - `ee.Initialize(project=…)`;
     - `listAssets(root, pageSize=1)`;
     - `cloud.ipcch.ee_transport.EETransport.missing_assets([root + "/IPCCH_ROOT_CHECK_NONEXISTENT"])`, which must return that id as absent;
   - no export, no create.

   Asset CREATE by the runtime SA remains unproven until a real export.
4. **Only then, a second monthly attempt.** This needs the user's explicit scope change, because the spec allowed one attempt.
   - Same image, models, config and limits.
   - While UTC is still November, M is 2026-11 and O is 2026-09. The demand should be unchanged (the climate tables are untouched; re-run `demand_preflight.py` to confirm).
   - ACLED decision for the user: the approved refresh is ALREADY retained (v2, exact).
     - **Option a (recommended):** submit ACLED `keep`, so all 11 are keep and v2 becomes the keep baseline.
     - **Option b:** repeat the identical refresh. That replaces the same 470 rows, producing a new version with identical content.
   - Either option changes the D3 selection file, so the user must decide.

## Rejected or not recommended

- **Treating the root 404 as an empty listing in product code.** There is no evidence the SDK parent string is wrong. It would mask a missing root, the later `Export.table.toAsset` would still need the root, and it is a product change outside this spec.
- **Pointing `producer_asset_root` at another project or folder.** That is a config, image and deploy change, and possibly an IAM change; it is outside this spec.
- **Granting broader IAM or deploying personal credentials.** Prohibited.
- **Automatic same-ID resubmission or a fresh-ID retry.** Prohibited; the attempt is terminal.

## If no further attempt is authorized

Close this task as a FAILED bounded attempt:
- AC1 and AC7 evidence complete; AC6 partial (ACLED exact, ten keeps);
- AC2-AC5 not achieved; DA1 failed and DA2 unproven, with the root issue documented as the next prerequisite.

Production current and the retained store are consistent. The ACLED v2 increment stays as the retained baseline.
