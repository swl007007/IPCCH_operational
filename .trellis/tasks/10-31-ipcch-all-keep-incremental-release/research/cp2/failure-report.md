# CP1 outcome: the one approved monthly attempt FAILED before any export (task 10-31)

Executor session 6a490ae1 (claude-opus-5-5[1m]); 2026-11-01 UTC.
- No second request was made. Nothing was created, granted, deployed or retried.
- CP0 artifacts stay frozen (`cp0/SHA256SUMS` verified).

## Identity of the attempt

| Item | Value | Evidence |
|---|---|---|
| Run | `ipcch-real-9eee4305db494a35`, submitted ONCE (guarded child 0; cloudop exit 0, 01:00:18–01:00:21Z) | `cp1/submit-execute.{log,exit}`, `cp1/cloud-operations.jsonl` |
| Freeze | M 2026-11, O 2026-09, prepared_at 01:00:20Z; expected pointer gen `1793461128385732` | `cp1/frozen-state.json` |
| Request | `requests/ipcch-real-9eee4305db494a35/run_manifest.json#1793494821542586` (`8b346d35`) | same |
| ACLED pin | `inputs/v2/ipcch-real-9eee4305db494a35/acled/…20261017_20261023.csv#1793494819786240` (`e660c7e8`); 2026-10-17..23; 17 regions | same |
| Claim / reservation | claim 01:00:22Z; reserved 01:02:09Z, deadline 05:02:09Z, timeout 14400 s | `cp1/reservation.json` |
| Execution | `oct-delivery-4jkcj` (acc3e467), 01:00:27–01:03:38Z, failedCount 1, `Container called exit(1)`; 176 log entries (1 WARNING, 1 ERROR) | `cp1/rec-execution.out`, `cp1/rec-logs.out` |
| Workflow | `44d4f44e-…` SUCCEEDED (it dispatches only; the durable status is the outcome) | `cp1/rec-wf.out` |
| Durable status | `failed`; ipcch `failed`, step `generation`, operation `climate`; `lock_release_problems: []` | `cp1/v2_run_status.json`, `cp1/cp1-final-status.json` |

**Error.** `EETransportError: cannot list projects/feisty-flames-511718-d4/assets to resolve an ambiguous asset lookup (EEException: Asset "projects/feisty-flames-511718-d4/assets" not found.); not treated as absent`.

## Where it failed (source trace; product unchanged from 115798f)

In `TableProducer.run` (`table_producers.py:465-495`), with 7 jobs demanded, the steps run in this order:
1. han admin polygon metadata check (`missing_assets(self.inputs.admins())`);
2. admin features and PATCH32 targets;
3. the PATCH32 32-row/32-code `evaluate`;
4. the "never reuse an existing destination" check: `missing_assets([new feisty id])`.

Step 4 is the one that failed. EE reports a missing child with the ambiguous "does not exist or doesn't allow" message, so `EETransport.missing_assets` resolves it by listing the parent (`ee_transport.py:122-160`). The parent is the configured `producer_asset_root` itself, and that listing raised "not found".

Steps 1-3 raise on failure and the run reached step 4, so by source order they did not fail under the runtime SA: the han admin metadata check and the evaluation of 32 unique PATCH32 targets passed. This is a SOURCE-PATH INFERENCE, not measured call telemetry; the job log does not record them.

No `Export.table.toAsset` or raster export was submitted:
- task records are reserved create-only before any submission, and none exist (`run-object-enumeration.json`);
- the failure precedes the submit loop.

## Read-only diagnosis

| Evidence | Identity | Result |
|---|---|---|
| `ee.data.getAsset(projects/feisty-flames-511718-d4/assets)` | LOCAL EE credentials (caller email NOT established, see below), read-only | HTTP 404 NOT_FOUND, "does not exist or doesn't allow this operation" |
| `ee.data.listAssets(parent=projects/feisty-flames-511718-d4/assets)` | local EE credentials | HTTP 404 NOT_FOUND, `Asset "projects/feisty-flames-511718-d4/assets" not found.`, the same text as the runtime SA's failure (`ee-root-diagnosis2-operator.json`) |
| `getAsset` of a nonexistent feisty child | local EE credentials | the ambiguous message (the product's trigger) |
| `listAssets(parent=projects/han-sandbox-505315/assets)` | local EE credentials | "Permission 'earthengine.assets.list' denied …": EE reports denial explicitly, not "not found" |
| `getAssetRoots` | local EE credentials | `Asset "projects/feisty-flames-511718-d4/assets" not found.` |
| Earth Engine API on feisty | gcloud read | ENABLED |
| Project IAM | gcloud read (gcloud account weilun.shi) | `monthly-runtime` has `roles/earthengine.writer` (plus batch, logging and serviceUsageConsumer); weilun.shi and soonho.kim are owners. This is a binding, not proof of a successful export or create |
| EE caller identity | Google tokeninfo of the EE session credentials (token never printed or stored) | HTTP 200, but no `email` field. Scopes: cloud-platform and earthengine; OAuth client `764086051850-…`. The EE caller's identity is NOT established and must not be assumed to be the gcloud owner account |

The local-credential reads are in `ee-root-diagnosis-operator.json` and `ee-root-diagnosis2-operator.json`. They are NOT runtime-SA evidence.

**Interpretation, uncertainty stated.** Two identities get HTTP 404 NOT_FOUND listing the feisty root: the runtime SA (holding `earthengine.writer`) and the local EE credentials (caller not established). Listing the han root from the local credentials is reported instead as "Permission 'earthengine.assets.list' denied … (or it may not exist)". This is CONSISTENT with an absent or uninitialised Earth Engine asset root for the feisty project. It does not exclude an identity or access cause, because the local caller's identity and its feisty permissions are unknown.
- The SDK source scout (`../supervisor-ee-root-notes.md`) shows the `projects/P/assets` parent string is supported (`data.py:586-597`), so the product's parent spelling is not the cause.
- The exact project-side condition was NOT established read-only: EE Cloud project registration, or a root created only on first asset creation.
- That `monthly-runtime` can CREATE assets there remains unproven.
- No live list or create check of the feisty asset root is recorded in the archived 10-30 evidence (its identity probe was read-only on han inputs). The 10-30 real run had empty demand, so the producer never reached this path.

## Partial work (reconciled; all preserved, nothing deleted)

**Current:** UNCHANGED at gen `1793461128385732` (`ipcch-real-522b30030f944868-ipcch`). There is no live hold and `locks/` is empty (released).

**Retained store** (`inventory-post-failure-real.json` against `cp1/inventory-pre-cp1-real.json`, guarded): exactly 2 HEADs changed and no new tables.
- `acled_agg_weekly` v1 → v2 (gen `1793494944270289`): 242,341 → 242,811 rows (+470).
- `acceptance_manifest` v3 → v4: the runtime acceptance record for the new ACLED version (`runtime_acceptance` in the status report).
- Unchanged: all 26 climate tables, GPP history and ledger, nightlight, and the ten kept histories (equality checked).

**ACLED, exact** (`failure-source-checks.json`, guarded, child 0):
- every pre (region, week) outside 2026-10-17..23 is byte-identical;
- no new keys outside the interval;
- the interval content EXACTLY equals the pinned export's `parse_export` fingerprint (12 keys, 470 rows);
- the source pin `e660c7e8`, interval, 17 regions and coverage record are appended.

This ACLED version is now the retained baseline for the next keep. There is no batch. The run status's generation report (`steps.acled`) shows `coverage_end` 2026-09; this run's features would have used A = O-1 = 2026-08.

**Absent for this run:** no feature batch, delivery, candidate, release or export task record. The only run objects are the ACLED upload, the request, the claim, the reservation and the status.

**Not reached:** GPP probes, nightlight, raster climate, assembly, inference and publication.

## Acceptance status (honest)

| AC / DA | Status |
|---|---|
| AC1 bound submission | Evidence complete: frozen request and reservation, ACLED refresh plus ten keeps, real mode, image and model refs, M/O, one run admitted |
| AC2 real production | NOT achieved: failed before export at the destination-existence check |
| AC3 consumption | NOT achieved |
| AC4 live data contract | NOT exercised (no export); DA2 unproven |
| AC5 publication | NOT achieved; current unchanged, as required on failure |
| AC6 source actions | Partial: the ACLED refresh is verified exactly and the ten keeps are unchanged. Automatic sources were not reached, so no update or reuse can be measured |
| AC7 bounded outcome | Evidence complete for the failure: status, execution, logs, partial changes and current reconciled, one attempt, no retry |
| DA1 | FAILED, not passed |
| DA2 | UNPROVEN, not passed (no export; not a D2 natural non-observation) |
