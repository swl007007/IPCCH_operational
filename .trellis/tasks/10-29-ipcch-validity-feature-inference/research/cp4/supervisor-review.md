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
