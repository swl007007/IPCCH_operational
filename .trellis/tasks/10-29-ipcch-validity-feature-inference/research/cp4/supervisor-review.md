# CP4 Supervisor review — in progress

No Audit workflow; manual checkpoint review under execution-protocol.md. CP4 is not accepted.

## Verified primitives

- Locks08c7a2b: independent7tests passed but partial-acquisition transport error leaked earlier lock; original rollback test conflicted on first lock.34362d8 fixes arbitrary acquisition failure cleanup, attempt-all release, surfaced cleanup errors and ObjectStore.delete protocol. Supervisor source/regression inspection plus locked lock/store/request35passed0.95s closes these findings. GCS deletion retries are bounded and generation-conditioned; live concurrency not tested. Runtime integration must still hold locks through publication for both v1/v2 executed systems.
- Publication47d7c4c: independent7tests passed; reproduced release-record replacement during read and smoke-member activation under real mode. b684e90 adds stable release-record generation checks, member/run mode equality and required verifier before record/pointer writes. Supervisor source review plus locked publication9passed0.57s closes the two concrete defects. Mandatory callback is a seam, not evidence of actual artifact verification.
- country_reference d7c3636: inference-only input requirement, immutable reference enumeration and trusted mode admission reviewed. Existing census53uniqueISO3 covers accepted53countries; smoke fixture-only remains mandatory.

## Remaining acceptance

Actual3h artifacts and inherited member hashes/package identity validated before publication; per-system provenance on all current paths; exact current-bound inheritance including inherit-of-inherit; legacy FEWS path with new IPCCH package; old in-flight IPCCH rejected after activation; new-contract candidate promote/resume refused; full root isolation for smoke; R39 publication recheck; no CAS rebase; independent runtime success/failure; real model fixture-only CP5 E2E. No actual production publication is authorized.


## Phase B review417c6d2 — pending repairs

Two read-only checks ran locked member suite6passed and targeted probes; Supervisor spot-checked implicated code. Concrete defects sent to Executor:

- delivery_member.py168-169 versus203-205: writer includes FEWS scope paths, verifier excludes them; mixed-system tree cannot verify.
- verify_member219-231: empty declared horizons plus removed scope inventory passes; require exactH2/8/14 and mandatory artifacts independently.
- copied envelope164/212-218: {} accepted; verify copied digest and package/mode/status binding.
- geometry157/225-229: empty FeatureCollection accepted; verify exact unique roster and valid geometry.
- expected identity196-201: mismatched expected package ignored without provenance digest; bind expected package identity explicitly.
- provenance.py105-127: calendar-selected season reported as actual observation even with every seasonal valueNaN; wildcard table loses actual version/hash references. Distinguish calendar selection/observation and retain concrete seasonal input refs.

Full Executor suite845passed is regression evidence only; these reproduced boundaries remain open. PhaseC/D may proceed independently, but no PhaseB/CP4 acceptance yet.

## Phase B closure and Phase C inheritance repair — 2026-10-30

The six Phase B findings above are closed at 6e57972: independent scoped member suite 8 passed, and source inspection verified mandatory horizons/files, envelope/package identity, exact geometry, shared inventory selection, and seasonal observation provenance. This supersedes the pending status above for those six findings only.

Phase C at 6e57972 had a reproduced publication blocker: a self-consistently regenerated destination inventory allowed altered inherited FEWS predictions and missing supporting artifacts to publish. The verifier checked member metadata but did not independently bind copied files to the snapshot-bound source inventory.

b98f100 closes that finding. Supervisor inspected the patch; independent read-only verification confirmed source manifest generation/hash binding, exact inherited file set and hashes, and verification before current/candidate writes. Four mutation regressions independently reran: 4 passed, 4 deselected. Executor records that all four fail against 6e57972. Recorded focused receipt: 25 passed; full suite: 855 passed (525 warnings). No additional full-suite run was required for this bounded verification.

CP4 remains unaccepted: executable entrypoint/locking, legacy compatibility, promote/resume guards, FEWS adapter and real provider route remain pending, followed by fixture-only CP5 E2E. No live cloud publication or production-current mutation was performed or accepted by this review.

## Runner integration review e3bb779

Independent read-only runner review found no confirmed defect in the scoped diff. Locked runner suite: 12 passed; additional in-memory check verified generation chaining 7 -> 8, locks held through both system callbacks, and release-error reporting. Reviewed files matched the pinned commit.

FEWS adapter integration must prove two-system publication end-to-end: the unchanged request run_id is passed after IPCCH publication, while delivery_run creates releases/{run_id}/release.json create-only. Updating expected generation alone does not prevent immutable path collisions. Executor notified to resolve this in adapter wiring and provide a fake-store test with both updates, partial failure, final member identities and no rebase. This is an outstanding integration evidence requirement; unfinished adapters and live cloud execution were outside this scoped check. CP4 remains unaccepted.

## Executable entrypoint e48ca51 — three pending findings

Independent entrypoint/delivery-job suite 32 passed, but targeted probes confirmed: entrypoint_v2.py:100 reads production current before admission even for smoke; :126 constructs EE acquisition providers even for inference-only; :137 drops outcome.report from durable/returned status, losing saved-update evidence after later generation failure. Supervisor spot-checked source and dispatched namespace-first/no-real-touch, generation-only provider construction, and durable report regressions. No entrypoint acceptance yet.

## Dual publication ec7a31b — scoped verification

No new defect found in e48ca51..ec7a31b. Per-system publication IDs separate delivery/release/candidate/conflict paths and preserve request identity. Focused publication/release/runner suite independently passed 31 tests. Both members reaching current and FEWS failure retaining IPCCH were verified. Candidate behavior inspected; dedicated dual-candidate integration evidence remains absent. Review also found pre-existing run_v2 overall status `partial` inconsistent with PRD `partial_success`; executor instructed to align literal and tests. Actual FEWS adapter remains pending.

## Entrypoint repair closure 6f07b2f

Three e48ca51 findings and the partial_success contract mismatch are closed. Independent read-only source/dataflow inspection and locked entrypoint/runner suite: 18 passed in 33.03s, including smoke zero-real-read, accepted real inference-only with forbidden acquisition initialization, and persisted saved-ACLED report after climate failure. Scoped source/test bytes matched the commit. Real current lookup follows structural validation and remains before full reference admission; no smoke production lookup remains. No consumer requiring former flattened status fields was found. Mutation replay/full-suite/live checks were not repeated. FEWS adapter and legacy integration remain pending; CP4 is not accepted.

## Phase D 6d8ea08 — pending repairs

Independent read-only checks ran locked guard/operator tests (100 passed) and byte/member tests (27 passed). Actual shipped FEWS 0/6/12 model.joblib files round-tripped byte-exactly through LocalObjectStore; binary inheritance and fake-GCS preconditions passed. No byte API defect found. Supervisor spot-checked implicated code; CP4 remains unaccepted for these reproduced or traced gaps:

1. pipeline.inherited_source:836 expects legacy provenance.run_id and :839 substitutes requested FEWS month. V2 uses top-level run_id and member feature_origin; submit_intent:814 and delivery_job._remote_intent:669 still apply same-origin admission. Fix actual operator/remote routes, not only execute.
2. Remote admission/dispatch at delivery_job:678-700 allows preparation (workflow.yaml:158) before activation rejection and shared locks in execute:494-500. Enforce R37 before collection and preserve owned locks through remote preparation, delivery and publication, with failure cleanup.
3. bind_current:613-615 rejects IPCCH scoring with inherited FEWS on every v2 record, including activation=None. This restriction is not approved: a preactivation FEWS-v2 release must not disable valid legacy IPCCH. Support inherited FEWS under its stored format until actual activation.
4. bind_current:585 calls read_current, which requires release_record_generation. Older pointers supported elsewhere now raise KeyError before work. Use a consistent compatible read preserving activation/integrity checks.
5. fews_v2.check_member:36-47 and delivery_v2.verify_delivery:214-218 omit existing FEWS structural/package validation. Local repro: corrupt country predictions, invalid headers, absent frozen inputs and packages={} still pass writer and verifier. Restore scoped existing checks and exact horizon/package identity at publication; malformed success fixtures are insufficient evidence.

Executor notified with regression requirements. The v1 archive field repeating a v2 member manifest ref is allowed as a documented compatibility convention only when exactly bound to the current member; operator source construction must implement it. No blanket preactivation rejection or validation weakening is authorized. No live cloud operations performed.

## Finding 5 follow-up 4fd6146 — original cases fixed, checksum gap remains

Independent focused tests: 16 passed, repeated against pinned module bytes. Existing FEWS content/identity/country/availability/diagnostic checks are restored at writer and publication; original corrupt-country/header/missing-frozen-input/empty-packages cases close. Default validate_delivery preserved. However delivery_bundle.py:407-410 accepts checksums.json={} because all() has no entries. Reproduction replacing every fixture package checksum map with {} before writing, using pinned modules, still publishes. Require checksum inventory coverage of content files under the existing package format, and test empty plus incomplete inventory rejection. No new full-suite run; previous 161-pass and 14-fail/2-pass mutation receipts inspected. Complete finding-5 acceptance awaits this bounded repair.

## Finding 5 checksum closure a5a107e

Independent read-only verification from isolated git archive a5a107e: test_fews_member 19 passed in 10.06s with locked interpreter. Existing package validators enforce seven regular files and exactly six content checksums, SHA256 syntax and bytes; member validator additionally binds package manifest and recorded inventory. Empty/partial/self-listing maps rejected at writer and actual publication with self-consistent external inventory; current unchanged. The checksum residual and original finding 5 are closed. Findings 1-4/R60 remain pending; no full-suite/cloud rerun implied.

Finding 2 clarification: rejecting all postactivation legacy remote-update requests is not accepted. FEWS-only legacy entrypoints remain usable; restrict their preparation to FEWS through the selected-systems seam while preserving request shape/science. Reject IPCCH-including v1 after activation. Locks cover systems actually collected/scored and carry through preparation/resolution/delivery/publication with owned cleanup. Unused IPCCH declarations in an old preparation schema do not imply authorization to collect IPCCH.

## Findings 1-4 follow-up 78a2aeb

Isolated pinned reviews: operator/legacy 57 passed; workflow/prepare/legacy 78 passed. Old-pointer consistency (finding 4), activated IPCCH rejection, FEWS-only scoped prepare, default preparation, and intended preactivation IPCCH path verified. Remaining:

- bind_current:639 uses outer v2_record to select archive semantics. Legacy both-system -> FEWS-v2 preserving legacy IPCCH -> exact-current FEWS-v1 rejects actual legacy archive. Member format must govern, not container.
- locks.acquire:79-82 reads holder then fresh generation separately. Deterministic replacement A->B between reads lets A adopt B generation and delete B on release. Bind ownership and generation consistently; changed read must refuse adoption.
- workflow.yaml prepare/resolution submission failures (e.g. definitive HTTP403) do not invoke release. Preserve locks for ambiguous submissions/timeouts; clean definitive terminal rejection.
- dispatch_step resolution RuntimeError escapes its narrow catch; execute bind_current rejection happens before cleanup; dispatch-record write failure precedes cleanup. Reproduced remaining admission locks. Cover terminal errors with owned cleanup and actual execution-path tests.

No code edits by reviewers. Finding 4 closes within reviewed scope; findings 1/3 retain the mixed-member residual, finding 2 remains open. Executor notified; CP4 not accepted.
