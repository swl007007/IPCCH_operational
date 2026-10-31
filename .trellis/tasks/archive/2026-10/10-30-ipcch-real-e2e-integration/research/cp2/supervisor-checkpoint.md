# CP2 Supervisor checkpoint

2026-10-31 UTC: accepted as offline component/integration evidence. Proceed to
CP3 after the checkpoint commit. This does not accept AC2 runtime access, AC8
installed-runtime wiring, or any live E2E/publication claim. DA1-DA2 stay deferred.

## Evidence inspected

- Source/formula inspection and initial feedback are in supervisor-interim.md.
  Final inspection covered EETransport paging, RPC settings restoration, submission
  identity/cancellation, entrypoint reservation/deadline, provider mapping and the
  corrected explicit-empty versus null VI metadata boundary.
- Read-only evidence extraction confirms all 16 final logs: 226 passed, zero
  failures/skips, one CHILD-EXIT=0 each, matching .exit and time exit status.
  Maximum RSS is 492,772 KiB in test_fews_adapter.log:47 (300 rasterio warnings).
- All 20 paths in final/SHA256SUMS match current source. Source diff whitespace
  check passes. py_compile has exit evidence, but no standalone full command log.
- final/final-totals.txt and non-INTERMEDIATE logs are authoritative. The original
  runs-summary.txt is the first sweep and retains transport exit=1; its failure
  was an outdated message regex, preserved separately. Producer/E2E reruns cover
  the final VI fix and include actual Node regeneration (zero final skips).
- Supervisor confirmed PID 4905 is the original claude --resume 6a490ae1 process.
  Herdr's observer-session attribution is documented in executor-identity.md.
- GitNexus (canonical registered mixed-case path) reports HIGH, 12 expected
  climate/export processes. Its all-scope file list includes unrelated AGENTS.md
  and has incomplete indexing of new modules; final staged scope is checked
  separately. No reindex or unrelated source edit is required.
- Final staged set has 142 paths, excluding AGENTS.md; staged GitNexus still
  reports HIGH across the same 12 expected processes. Source/docs whitespace
  checks pass. Raw saved diff/pytest logs retain their original trailing spaces;
  the all-files whitespace check therefore reports those evidence files only.

## Gate dispositions

1. Accept post-2026 six-year chunks starting 2027 as the shared reader/producer
   convention. Existing historical block identities remain unchanged.
2. Accept row metadata derived in the export graph. Null/mixed/absent metadata
   fails; exact empty VI listing represents unavailable source observations.
3. Accept complete demanded VI years (including January's prior Aqua year) and
   full demanded drought chunks. Preserve and report 2020 fit-input vintage;
   no baseline splice or rewrite of saved indicators.
4. Processing failure stops the climate step before saves. Completed sibling
   assets remain unexposed; no deletion or old-asset fallback is introduced.
5. Accept 60-second individual EE RPC limit, retries disabled within each call,
   restored SDK settings, persisted <=4-hour run limit and 15-minute reserve.
   Status errors retain the existing bounded polling retry behavior.
6. Retain han-sandbox static/history inputs and feisty-flames new-output root.
   Runtime-identity accessibility remains CP5 evidence.

The original OOM PID/test link is unproven. The capped reproduction establishes
the test defect; final guarded tests verify the repair without repeating an
unbounded run. All subsequent tests retain the independent-service memory guard.
An export with a lost start response may have an unknown live operation: record
its request ID and ambiguity, refuse replay, and do not claim cancellation.

Next: CP3 under research/cp3-supervisor-seams.md. No cloud calls until the reviewed
CP4 operation packet. Keep AC2-AC9 open until their remaining evidence exists.
