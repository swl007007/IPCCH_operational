# Live read-only inventory

Supervisor, 2026-10-31. User preauthorized goal-scoped cloud operations; commands,
raw stdout/stderr and exits are alongside this note. No workload or cloud mutation
was started by these reads.

| Resource | Observed state |
|---|---|
| oct-delivery | image 487a2315…97fae; monthly-runtime SA; 8 CPU / 32 GiB; 14400 s; 0 retries |
| monthly-prepare | same image/SA; 2 CPU / 8 GiB; 14400 s; 0 retries |
| oct-delivery-trigger | ACTIVE, revision 000003-22c, monthly-workflow SA, legacy image env |
| oct-delivery-requests | request bucket finalized events target that Workflow |
| production current | generation 1792657760445077, pinned read succeeds |
| referenced release | generation 1792657760321065; fews-candidate-20261022a, origin 2026-10 |
| proposed smoke bucket | gs://food-crisis-test-ipcch-smoke returns 404 |

Pinned release SHA256:
`4bf785e8604e80007e7309f28c3176662322866bb2a981fa7c586d32c0640b3d`.
The current release records FEWS scored and legacy IPCCH inherited. Its original
bytes/references are preserved for later member readback and rollback.

Local token impersonation failed for monthly-runtime: the active operator lacks
`iam.serviceAccounts.getAccessToken`. No EE HTTP request was made, so this is
neither an EE denial nor runtime-readiness evidence. Prefer a bounded Cloud Run
preflight under the actual runtime service account; do not add broad impersonation
permissions just for a local diagnostic. Runtime EE/GCS access remains unverified.

At the inventory checkpoint, build/deploy/initialization, smoke provisioning and
full real E2E were pending. Refresh current immediately before submission; this
generation is a snapshot, never a hard-coded future publication precondition.

## Bounded runtime probe and user-access comparison

The separately recorded `runtime-probe-packet.md` was executed once: job
`ipcch-v2-runtime-preflight-20261031`, execution `...-7jq5m`, old image 487a2315,
monthly-runtime SA, 1 CPU / 512 MiB / 300 s / zero retries. Final exit **2**;
`runtime-probe-status-2.json` and `runtime-probe-logs-2.json` are the final evidence.

- EE initialization succeeds; data/request buckets grant object get/create/delete/
  list; current metadata is readable with the recorded generation.
- BOTH known han-sandbox admin and baseline assets are unreadable by the runtime
  account. This is a confirmed access gap, not an unverified readiness claim.
- Existing persistent EE user credentials can read both asset metadata records,
  but cannot read their ACLs (`user-ee-access.json`). No ACL mutation was attempted;
  upstream asset-owner sharing is required. No personal token is deployed.
- The first local user probe failed during SDK setup before cloud calls; the second
  guarded probe completed and captured metadata/ACL results. Its child exit 0 is
  not an assertion that every requested permission was granted.

Source inspection (`entrypoint_v2.py:118`, `table_producers.py:472`,
`geography.py:85`) agrees with `../cp5-han-dependency.md`: exact retained October/
August history should produce no han reads; empty demand skips before asset checks,
and source geometry comes from the installed bundle. This permits the current
retained-history acceptance to continue; its actual reports must confirm that skip.
Any real nonempty demand fails closed. DA1-DA2 future incremental execution needs
upstream sharing to monthly-runtime. Public GPP HTTPS access from Cloud Run is
still unverified and will be recorded by the actual run.

Smoke bucket provisioning completed separately under the Executor's bounded step 4;
the new image build is running. Production jobs/Workflow/current are unchanged.
