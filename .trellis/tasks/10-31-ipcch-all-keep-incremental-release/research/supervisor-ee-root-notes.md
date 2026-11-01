# Read-only SDK investigation of the failed destination-root check

Source: installed earthengine-api 1.7.36 under
/home/swl007007/.venvs/fewsnet-test-lock-20261022/lib/python3.12/site-packages/.
This is source evidence, not a new runtime probe or a validated recovery.

- `ee/data.py:586-597` recognizes projects/P/assets (optional trailing slash),
  removes the assets suffix and calls projects().listAssets(parent=projects/P).
  Tests at ee/tests/data_test.py:761-799 cover both spellings. The product's input
  string is supported; changing it to bare projects/P has no established basis.
- `getAssetRootQuota` calls getAsset then checks quota fields (data.py:2070-2103).
  It is not an independent absence-versus-permission discriminator.
- getAsset(root), project configuration and independently established project
  permissions can help narrow the failure. Preserve HTTP status/body when available:
  data.py:357-377 wraps HttpError as EEException but the Python exception context
  retains the original error. Do not expose tokens or credentials in diagnostics.
- Existing local EE credentials are not automatically the current gcloud account.
  An IAM owner binding for a gcloud account alone does not prove the forensic EE
  calls used that owner identity. Label identity evidence accurately.
- `createAssetHome` documentation only specifies current-user users/joe roots
  (data.py:2228-2241); its sole test uses earthengine-legacy/users/test
  (tests/data_test.py:407-413). Generic SDK request construction for a Cloud Project
  root is traceable, but no local test proves backend acceptance of empty assetId.
  Do not call an inferred bootstrap operation without a separately reviewed scope.
- Root ACL read failure alone cannot prove absence: archived user-ee-access.json
  has a successful metadata read and failed ACL read for the same existing input.

Product path: table_producers.py:475-484 checks han admins and evaluates 32 unique
PATCH32 targets before :486-488 checks output absence. The first actual submission
loop starts at :492. This supports the pre-export location of this failure, while
actual task-prefix/object enumeration supplies durable evidence.

No cloud calls, mutations or tests were performed by the source-only scout.
