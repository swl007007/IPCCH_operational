# CP4 local implementation plan (Executor) - Supervisor rulings 2026-10-30 applied

Rulings (binding): versioned, hash-covered per-system `system_provenance.json` (own M/O/targets/leads/mode/package
identity); content checks per member from its metadata incl. inherit-of-inherit, never the outer origin, never skip
inherited integrity checks. FEWS frozen headers preserved. New IPCCH exported predictions keep `mode` (R36) with
contract-aware exact headers for the new IPCCH member; other provenance in metadata. Inherited per-system sidecars kept
byte-for-byte; shared diagnostic_availability rebuilt by explicit merge with each system's own temporal metadata (no
identical-header concatenation). v1 FEWS-only keeps its request shape; after activation the inherited IPCCH package
comes from the current member archive (not the unused legacy IPCCH package fields); verify own hashes/identity. Smoke:
separate root for runs/deliveries/candidates/conflicts/locks/pointer; production paths unchanged. Locks: v1 and v2
share locks for the systems they EXECUTE (not untouched inherited members), held through publication, deterministic
acquisition, whole request fails if any busy, own partial acquisitions released, owner-generation conditional release,
no stale eviction. CAS: inherit snapshot bound to the expected current generation; no rebase/retry. Reject
new-contract promote/resume. Preserve activation through every FEWS publish path.

Phases (each committed with tests):
A. publication core (cloud/ipcch/publication.py): read the current snapshot bound to the expected pointer generation
   (stable read); v2 release record schema (contract version, per-system members with own provenance, activation
   marker carried forward); candidate (no pointer move, R66) vs current (CAS via delivery_run.publish, no retry, FCC3);
   R39 recheck against the bound snapshot; activation = first successful real IPCCH current publication (R37/R46);
   run outcome `publication_failed` keeps the batch.
B. v2 delivery member: IPCCH member writer from score_batch outputs (contract-aware exact headers incl. mode),
   system_provenance.json (hash-covered), per-member content checks; diagnostics (R31) from model-matched evidence.
C. inheritance: byte-for-byte member copy bound to the snapshot; inherit-of-inherit provenance; v1 FEWS-only after
   activation takes the IPCCH member from the current archive (own hashes/identity), replaced FCC9 checks.
D. legacy guards: v1 IPCCH-including requests rejected after activation (request-time + publication-time recheck in
   validate); promote/resume reject new-contract candidates; v1 runs take locks for executed systems.
E. smoke separate root; R18 all three horizons or none; isolated current replacement tests.
Done so far: 08c7a2b locks (locks/{system}, all-or-nothing, owner-generation release, ops clear) + ObjectStore.delete.
