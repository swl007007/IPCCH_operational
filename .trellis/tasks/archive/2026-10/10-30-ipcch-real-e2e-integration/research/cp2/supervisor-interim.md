# CP2 Supervisor interim observations

2026-10-30; CP2 remains in progress, not accepted. No cloud calls authorized here.

Supervisor read the original 01 producer (all sections) and 02 target geometry,
monthly, reducer/export sections; their shared daily ET0 equivalence is also in
the planning evidence. Compared the initial table_producers.py graphs against
the source operations, scales, masks, reducer and geometry.

Feedback sent to the Executor:

1. Preserve 02's final monthly ET0 float cast (02:494-499), absent in 01, in the
   PATCH32 graph before reduction. Shared FAO56 arithmetic otherwise agrees.
2. Explicit empty VI composite_dates is valid source unavailability; absent or
   malformed metadata is failure. Test empty-year recovery and check the metadata
   column before indexing it.
3. Reject malformed/infinite produced means, including incomplete periods; preserve
   legitimate NaNs. A finite-value test alone misses infinity.
4. An interrupted wait must not set a live export handle done and skip cancellation.
   Ensure task ID and cancellation result remain durable.
5. One getInfo call is not by itself time-bounded. Cover producer evaluations/reads
   with deadline checks and avoid claiming a stronger timeout than implemented.

Executor CP2A report says 1-3 were applied and test-only JS/Python pixel comparisons
are exact across 696 pixel-days, monthly ET0, three precipitation sources and VI QA;
offline EE graphs serialize. These are interim reports pending final evidence
inspection. Existing transport tests (18) and subsequently related tests (78) pass
according to the Executor. Final focused logs/exit codes remain required.

The arithmetic mocks must stay limited to the compared upstream operations; Node
is test-only. Remaining: complete lifecycle tests, persisted provider/batch receipts,
deadline and pre-mutation replay reservation, and controlled-response generation
integration. No additional full-suite rerun needed before the CP4 integration gate
unless a concrete failure requires it. DA1-DA2 remain user-deferred.

## Resumed after Herdr shutdown

2026-10-31 UTC: the server log records SIGTERM at 00:08:57 and all pane children
exited. No producer pytest process survived; its last partial run is not a pass.
Live Herdr subsequently confirms the original Claude session
`6a490ae1-ee00-43f9-bdfc-c887c9816c09` at `w1A:p8`, with Supervisor at `w1A:p2`.
The same checkout and CP1 HEAD `12b1d68` remain; no replacement executor was created.

Resent the pending concrete deadline feedback: the pinned EE SDK automatically
paginates PANDAS_DATAFRAME computeFeatures and retries individual calls. One
setDeadline(remaining_budget) does not enforce a whole-read deadline. Use explicit
pages with budget checks, bounded individual RPC/retries, restore SDK settings,
and bound status/cancellation calls. Add expiry-between-pages/read tests. CP2 still
requires full logs/actual exit codes and the controlled-response generation path.
