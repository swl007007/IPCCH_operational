# CP4 Supervisor review — in progress

No Audit workflow; manual checkpoint review under execution-protocol.md. CP4 is not accepted.

## Verified primitives

- Locks08c7a2b: independent7tests passed but partial-acquisition transport error leaked earlier lock; original rollback test conflicted on first lock.34362d8 fixes arbitrary acquisition failure cleanup, attempt-all release, surfaced cleanup errors and ObjectStore.delete protocol. Supervisor source/regression inspection plus locked lock/store/request35passed0.95s closes these findings. GCS deletion retries are bounded and generation-conditioned; live concurrency not tested. Runtime integration must still hold locks through publication for both v1/v2 executed systems.
- Publication47d7c4c: independent7tests passed; reproduced release-record replacement during read and smoke-member activation under real mode. b684e90 adds stable release-record generation checks, member/run mode equality and required verifier before record/pointer writes. Supervisor source review plus locked publication9passed0.57s closes the two concrete defects. Mandatory callback is a seam, not evidence of actual artifact verification.
- country_reference d7c3636: inference-only input requirement, immutable reference enumeration and trusted mode admission reviewed. Existing census53uniqueISO3 covers accepted53countries; smoke fixture-only remains mandatory.

## Remaining acceptance

Actual3h artifacts and inherited member hashes/package identity validated before publication; per-system provenance on all current paths; exact current-bound inheritance including inherit-of-inherit; legacy FEWS path with new IPCCH package; old in-flight IPCCH rejected after activation; new-contract candidate promote/resume refused; full root isolation for smoke; R39 publication recheck; no CAS rebase; independent runtime success/failure; real model fixture-only CP5 E2E. No actual production publication is authorized.
