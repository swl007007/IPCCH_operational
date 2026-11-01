# D5 scope extension — approved; execution pending

The sole authorized attempt ipcch-real-9eee4305db494a35 failed before EE exports
because listing projects/feisty-flames-511718-d4/assets returned NOT_FOUND.
Current is unchanged; ACLED v2 already contains the approved new week.
The user explicitly adopted this proposal on 2026-11-01 UTC:
"批准上述恢复与一次重跑". PRD D5/R8 now include this bounded extension.

## Supported operation, remaining uncertainty

Google's Earth Engine access guide, read 2026-11-01 UTC:
https://developers.google.com/earth-engine/guides/access#create-an-assets-folder-optional

The documented project-root initialization command is:

    earthengine --project feisty-flames-511718-d4 create folder projects/feisty-flames-511718-d4/assets/

The guide distinguishes API/project access from creating an asset folder for
storage. It also supports creation by adding the project in Code Editor Assets.
This supersedes the SDK-only uncertainty about whether project-root creation is a
supported operation. It does not prove this root is absent rather than inaccessible.
No creation command has been executed.

## Approved bounded recovery

1. Use a dedicated short Cloud Run job, proposed name
   ipcch-ee-root-check-20261101, in feisty-flames-511718-d4/us-central1. Pin the
   existing acc3e467 image and monthly-runtime service account. One task,
   1 CPU, 512 MiB, 300 s, zero task retries. This is a new diagnostic job, explicitly
   extending the prior no-deployment-change boundary, with no new image/build.
2. Under that confirmed runtime identity, read the root. If listing succeeds,
   skip creation. If it returns HTTP 404, make at most one documented create-folder
   operation for the exact project root, then re-read it. Other errors stop.
   The create operation must never overwrite existing assets. An already-exists
   response only permits readback reconciliation, not a destructive replacement.
   Keep SDK RPC retries at zero and calls bounded within the 300 s job budget.
3. Verify root listing and the pinned product transport's missing_assets behavior
   for a deliberately absent child. This creates no scientific data or export.
   Save the execution spec, identities, HTTP results and logs. If this fails,
   stop before monthly submission; do not grant IAM or change registration/billing.
4. If those checks pass, update selections to all eleven keep, inheriting ACLED
   v2. Re-read current and retained inventory and perform the normal preview.
   Submit exactly one additional NEW run ID. Actual UTC freeze selects M; a
   November freeze gives O=September. Existing 8 CPU/32 GiB/14400 s/zero retry
   runtime limits remain unchanged. No automatic third attempt.
5. Apply the existing DA1/DA2 acceptance and failure reconciliation. Preserve all
   prior retained versions, assets and failed-run receipts. Current publication
   still requires the complete normal pipeline and all horizons together.

This extension adds only root initialization/verification and one further
monthly attempt. No model/scientific/product code changes, new build, broad IAM,
personal credential deployment, current-pointer hand edits or history deletion.
If a different repair becomes necessary, report concrete evidence and revise scope.

## Approval boundary

The original R8 required this scope extension because it allowed one monthly
attempt only and excluded automatic deployment repair. The user has now approved
the extension, including ACLED keep because the previous refresh succeeded.
Do not request cloud permission again for these operations. Supervisor technical
payload/readback checks still apply before proceeding to the additional attempt.

No Root/DA1/DA2 success is claimed by this proposal. The risk that root creation or
the next real export fails remains until the respective live operation succeeds.
