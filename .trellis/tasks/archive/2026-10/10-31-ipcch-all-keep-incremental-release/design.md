# Design: one real increment with ACLED refresh

Status: **Approved under execution-protocol.md and the user's cloud preauthorization.
D5 extends D1-D4 with bounded root recovery and one additional all-keep attempt.**

## Route and boundaries

Reuse the normal operator configuration, installed v2 image and accepted models.
No product change is proposed; D5 adds only the bounded diagnostic job. A task-scoped acceptance helper may
cross-check existing receipts after approval without changing runtime behavior.

    ACLED refresh + ten keep selections -> validation/pins -> one UTC freeze
      -> request uploaded last -> Eventarc -> Workflow -> oct-delivery
      -> validated ACLED interval replacement + other manual histories kept
      -> unsaved climate demand -> han static/history + public EE source graphs
      -> feisty run-specific exports -> wait/readback/validation -> mapped consumers
      -> monthly/seasonal retained append -> automatic GPP/nightlight
      -> 527-feature batch -> H2/H8/H14 inference
      -> validated delivery -> immutable release -> current CAS

Historical references, to be refreshed before execution:

- Config: /home/swl007007/ipcch-operator/food-crisis-test/project.json.
- Image: us-central1-docker.pkg.dev/feisty-flames-511718-d4/monthly-delivery/runtime@sha256:acc3e4673fa7c133eade6e5c74b998706788e0d1af0f92b217ae74ce7e14ccf6.
- Runtime SA: monthly-runtime@feisty-flames-511718-d4.iam.gserviceaccount.com.
- Real store: gs://food-crisis-test-ipcch-data/ipcch-v2/real.
- Current: gs://food-crisis-test-ipcch-data/monthly-staging/current.json.
- Previous accepted current generation: 1793461128385732. Never hard-code this as
  the next expected generation; submission reads current freshly.

## Demand and availability

Use existing demand(tables, origin, windows) and required_tables(need, refs) for
read-only planning. TableProducer.run submits exports and is not a preview.
The September monthly fixture has two 2026 VI and five 2020-2026 drought tables;
live seasonal/history gaps may add other years. Record actual demand at runtime.

A produced chunk replaces its mapped old chunk. Preserve the upstream full-chunk
formula/QA/scaling and current vintage, including 2020 values used in the baseline
fit. Do not splice a frozen baseline or rewrite previously saved indicators.

ACLED features use A=O-1; separate generic coverage warnings from cutoff
sufficiency. Live ACLED coverage currently ends 2026-10-16, with last weekly label
2026-10-10; the previous reported August tail was capped at O. Adding later October
weeks tests ingestion but does not place them inside this run's August cutoff.
Under D3 the copied raw export is retained byte-for-byte outside the repository.
It contains week 2026-10-10 (209 rows, overlapping old history) and week 2026-10-17
(617 rows). D4 approves refresh only for 2026-10-17..23. The separately pinned
submission CSV is prepared and preserves every selected field value; never relabel dates or replace
the old full week with a potentially partial overlapping export. The missing
2026-10-24 week does not establish an event-free or fully available source period.
See research/acled-input/ for raw-copy, prepared-file, parse and preview evidence.
GPP re-probes unpublished months: definitive 404 is unavailable,
transport/server errors are failures. Nightlight follows existing gap behavior.
At O each climate base needs a published source; historical/seasonal gaps can be
recorded. Masked areas remain NaN. Produced drought windows need the declared
completeness, including both primary ET0 and PATCH32 when produced.

## Evidence design

Reuse the archived readback_v2.py and store_inventory.py as references. Generic
readback verifies identity/publication/roster but does not establish incrementality.
A task-scoped cross-check must join:

1. nonempty demand, export task records and actual readable destination IDs;
2. batch climate_production receipts;
3. actually consumed produced_tables IDs in retained-version records;
4. batch retained version/generation/hash and inference batch identity;
5. final request/release/member/current refs and literal inherited FEWS.

Additionally verify the ACLED refresh version and source pin, its declared interval,
and byte/value preservation outside the interval and regions. Report the ten kept
histories separately. ACLED ingestion does not supply DA2's EE field witnesses.

Use existing contracts for PATCH32 IDs/sparsity, VI units and missing fields.
Record DA1 and DA2 separately, and list unobserved live shapes explicitly. Whether
those cases remain pending is settled by PRD D2: DA1/publication may pass while
DA2 remains explicitly partial. This does not waive an observed contract failure
or add a new publication gate. Do not infer numerical equality from
aggregate prediction counts, complete publication from asset existence, or zero
EE calls from empty logs. No model-accuracy or retraining gate is introduced.

## Failure and recovery

Before pointer publication, existing failures leave current unchanged, but saved
retained updates can remain. Failed production can leave completed assets;
preserve durable transport export records because a factory exception may omit
partial producer receipts from the generation report.

For an uncertain pointer response, reconcile current/release/reservation/status
before further action. Preserve the 4-hour deadline and 15-minute cleanup reserve;
do not guess cancellation or silently extend resources.

There is no supported v2 pointer rollback helper. Do not reuse the earlier C
maintenance operation, restore image 487a or hand-CAS a pre-activation pointer.
A bad publication needs a separately reviewed containment/forward-recovery plan.
The user-authorized Supervisor-Executor loop may resolve ordinary preparation and
validation errors. D5 now authorizes the root diagnostic job and one additional
all-keep attempt; other deployment repair and a third attempt remain excluded.
Native Trellis lifecycle applies; no Trellis Audit workflow.

## D5 recovery route (approved 2026-11-01 UTC)

Preserve all CP0-CP2 frozen evidence. The failed attempt wrote only ACLED v2 and
acceptance v4; no export, feature batch or publication occurred. Use the approved
runtime-SA job to read/conditionally create the exact project asset root, then
verify listing and missing_assets for an absent child. No scientific asset is
created by this check. See research/supervisor-recovery-proposal.md for limits.

After the technical root-readback gate, prepare a new all-keep selection file;
do not modify the original refresh selection/frozen state. Pin a fresh predecessor
and retained snapshot, preserve nonempty demand, and submit one new run ID.
Rebase CP2 manual-input checks to all-eleven-keep equality while retaining the
first attempt's separately accepted refresh evidence. All DA1/DA2, provenance,
roster, FEWS inheritance and publication checks are unchanged.
