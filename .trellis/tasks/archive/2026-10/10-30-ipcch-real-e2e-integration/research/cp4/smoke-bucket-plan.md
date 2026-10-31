# CP4 step 4: smoke bucket create/role plan (from observed facts; NOT executed)

## Observed (read-only, cloud-operations.jsonl entries 0-1; full outputs in `~/ipcch-operator/food-crisis-test/cloud-ops/cp4/2026-10-31T135247Z-0.out` and `…135301Z-1.out`)

`gs://food-crisis-test-ipcch-data`:
- location: `US-CENTRAL1` (region);
- storage class: STANDARD;
- uniform bucket-level access: true;
- versioning: enabled;
- soft delete: 7 days;
- public access prevention: inherited.

Its IAM, besides the legacy project bindings:
- `roles/storage.objectAdmin` for `monthly-runtime@…`;
- `roles/storage.objectViewer` for `monthly-workflow@…`;
- `roles/storage.objectCreator` for `monthly-workflow@…`, conditioned on `objects/dispatch/`.

The proposed `gs://food-crisis-test-ipcch-smoke` returns 404 (Supervisor's `live-preflight/smoke-bucket.*`).

## Plan

The settings mirror the data bucket, except public access prevention, which is enforced rather than inherited. No new location or class.

```
G="gcloud --configuration=food-crisis-test"
$G storage buckets create gs://food-crisis-test-ipcch-smoke --project=feisty-flames-511718-d4 --location=us-central1 \
  --default-storage-class=STANDARD --uniform-bucket-level-access --public-access-prevention
$G storage buckets update gs://food-crisis-test-ipcch-smoke --versioning
$G storage buckets add-iam-policy-binding gs://food-crisis-test-ipcch-smoke \
  --member=serviceAccount:monthly-runtime@feisty-flames-511718-d4.iam.gserviceaccount.com --role=roles/storage.objectAdmin
$G storage buckets describe gs://food-crisis-test-ipcch-smoke --format=json      # readback
$G storage buckets get-iam-policy gs://food-crisis-test-ipcch-smoke --format=json # readback
```

**Roles.** Only the runtime SA's object role is mirrored. The smoke root, store and inputs are read and written by the delivery job, which runs as `monthly-runtime`.
- No `monthly-workflow` role is added. The Workflow reads the request bucket and the data bucket's `maintenance/` and `dispatch/` objects, never the smoke bucket.
- If the smoke run shows otherwise, stop and report it.

**Isolation (R48).**
- `gs://food-crisis-test-ipcch-smoke/` is not nested with the real roots `gs://food-crisis-test-ipcch-data/…`.
- The committed deployment JSON already names `roots.smoke=gs://food-crisis-test-ipcch-smoke/v2`, `store_roots.smoke=…/ipcch-v2/smoke` and `trusted_prefixes.smoke=gs://food-crisis-test-ipcch-smoke/inputs/`. No config or code change is needed.

**Cost:** an empty bucket costs nothing; smoke objects are KB to MB.

**Rollback:** `$G storage buckets delete gs://food-crisis-test-ipcch-smoke`, only while it is empty. No history is deleted.

**Stop if:**
- the bucket name is taken by another project (create returns 409);
- create or binding is denied. Report it; do not choose another name silently.
