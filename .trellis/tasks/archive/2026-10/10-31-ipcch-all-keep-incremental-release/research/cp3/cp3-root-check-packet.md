# CP3 root-check packet (D5) — technically accepted; wording corrected (prior snapshot `cp3-root-check-packet.v1.md`)

Executor session 6a490ae1 (claude-opus-5-5[1m]); 2026-11-01 UTC.
- No cloud mutation has been made in CP3.
- Only one read was made: the job-existence check, which returned NOT_FOUND (`job-exists-check.err`).
- cp0, cp1 and cp2 stay frozen.

## Payload

**Files:**
- `root_check_payload.py`: sha256 **f1cf0b28817372e5d06dac84a3413a5fa0f50bd7c01ddad429961b8ba4432a60**. It equals `args[1]` of the job spec.
- `root-check-job.json`: sha256 **3a89b5c130a66a35aea7af06dc294f1e6b8b905cd1190b5b2f1253ba89f55ab7**.
- Superseded drafts are kept: `root-check-job.v1-superseded.json` (payload c806d3d8).

**Order of operations:**
1. **Absolute deadline.** One deadline is fixed at main entry, 240 s ahead.
2. **Identity gate.** The metadata-server email must equal `monthly-runtime@feisty-flames-511718-d4.iam.gserviceaccount.com`. A mismatch or metadata error stops (exit 2) BEFORE Earth Engine is imported or initialized.
3. **Initialization.**
   - `ee.data.setMaxRetries(0)` is called BEFORE Initialize. It sets state only; `data.initialize` keeps it, so discovery and `getAlgorithms` are built with `num_retries=0`.
   - `ee.Initialize(credentials=ADC(cloud-platform, earthengine), project=feisty, http_transport=httplib2.Http(timeout=40))`. The public `http_transport` parameter bounds every socket operation, including Initialize's discovery and `getAlgorithms`.
   - `setDeadline` is not called before init; that was the 10-31 probe's assertion cause.
4. **List the root.** `ee.data.listAssets({"parent": "projects/feisty-flames-511718-d4/assets", "pageSize": 1})`. The pinned SDK turns this into project-level `listAssets(parent=projects/feisty-flames-511718-d4)` and follows pages itself. If it succeeds, NO create.
5. **Only on HTTP 404:** exactly ONE `ee.data.createAsset({"type": "FOLDER"}, "projects/feisty-flames-511718-d4/assets/")`.
   - This is the documented `earthengine create folder projects/P/assets/` mapping. The pinned SDK sends `projects.assets.create(parent="projects/feisty-flames-511718-d4", assetId="", body={type: FOLDER})`.
   - HTTP 409 → readback only.
   - Any other result (403, 5xx, timeout) → stop.
6. **Re-list** after a create or a 409; it must succeed.
7. **Pinned product transport.** `EETransport(...).missing_assets(["projects/feisty-flames-511718-d4/assets/IPCCH_ROOT_CHECK_ABSENT_20261101"])` must return exactly that id. It uses the SAME absolute deadline (`cleanup_reserve` 1 s) and its own bounded request mechanics. It writes nothing; the receipts are in memory.
8. **Budget.** No request starts with less than 5 s left. The defensible bound is the Cloud Run hard timeout of 300 s, together with 0 SDK retries, the 40 s socket timeout and the shared deadline checks. No total duration is guaranteed beyond that hard limit.

**What it never does:** overwrite, change IAM, billing or registration, export, create a scientific asset, or touch `oct-delivery`, `monthly-prepare` or the Workflow.

**Output:** exactly one line, `IPCCH_ROOT_CHECK {json}`. It includes identity (metadata email, ADC SA email), every step with `ok`, HTTP status and body, `created`, `branch` and `passed`. Exit 0 only when `passed`.

## Offline checks (guarded: 4 GiB / 3 GiB AS / no swap / 600 s)

`test_root_check_payload.py`: **19 passed**, child 0 (`root-check-tests.{log,exit}`). The single nodes ran first (`root-check-node1`, `root-check-node2`). Coverage:
- readable root → no create;
- 404 → create exactly once → relist;
- 409 → readback only;
- create 403/500/timeout → stop with no relist or transport;
- list 403/500/timeout → stop with no create;
- relist failure → stop;
- transport not reporting the child absent → stop;
- identity mismatch, metadata error or empty identity → stop before any call;
- budget exhausted → no further call;
- HTTP status and body from `__context__`;
- **pinned SDK 1.7.36 mappings**: the create request (parent and `assetId=""`), the project-level list (SDK paging), and `setMaxRetries(0)` before `data.initialize` → resources built with `num_retries=0` and our `http_transport`.

**Intermediate logs kept:**
- `root-check-tests.INTERMEDIATE-fake-lacked-listAssets_next.*`: a test-fake gap;
- `root-check-tests.v1-before-budget.*`;
- `root-check-tests.v2-before-identity-gate.*`.

## Exact commands (on release; cloudop-logged; `G="gcloud --configuration=food-crisis-test"`, `T=research/cp3`)

```
# 0. pre: the job must NOT exist (if it exists: describe + reconcile, never replace/execute blindly)
$G run jobs describe ipcch-ee-root-check-20261101 --project feisty-flames-511718-d4 --region us-central1 --format=json   # expect NOT_FOUND
# 1. create (replace on a non-existent name creates it)
$G run jobs replace $T/root-check-job.json --project feisty-flames-511718-d4 --region us-central1 --quiet --format=json
# 2. readback of the definition: image acc3e467, SA monthly-runtime, 1 CPU/512Mi, 300 s, maxRetries 0, taskCount 1, sha256(args[1]) == f1cf0b28…
$G run jobs describe ipcch-ee-root-check-20261101 --project feisty-flames-511718-d4 --region us-central1 --format=json
# 3. ONE execution
$G run jobs execute ipcch-ee-root-check-20261101 --project feisty-flames-511718-d4 --region us-central1 --wait --format=json
# 4. readback: execution describe + full logs, then parse the IPCCH_ROOT_CHECK line
$G run jobs executions describe <execution> --project feisty-flames-511718-d4 --region us-central1 --format=json
$G logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="ipcch-ee-root-check-20261101" AND labels."run.googleapis.com/execution_name"="<execution>"' --project feisty-flames-511718-d4 --order=asc --limit=2000 --format=json
# 5. monthly jobs/Workflow untouched: oct-delivery & monthly-prepare describe (image/args/resources) + workflow revision equal to the CP0 live values
```

If `--wait` or cloudop times out, record UNKNOWN and reconcile via `executions list` and the logs. Never execute a second time.

**Acceptance of the root check:**
- the execution has `succeededCount 1` and exit 0;
- the result has `passed=true` and identity `metadata_server_email == monthly-runtime@…`;
- `branch` is one of `listable_no_create`, `created` or `already_exists_readback_only`;
- `create_root_folder` appears at most once;
- the transport step result equals `[child]`.

Anything else stops before CP4.

**Resource and cost bound:** one Cloud Run task, 1 vCPU and 512 MiB for at most 300 s (hard limit). The Earth Engine request count is NOT claimed: Initialize and SDK auto-pagination add requests, and no RPC telemetry exists. No bill amount is claimed.

**Retention:** the job definition and execution stay as evidence; no deletion.
