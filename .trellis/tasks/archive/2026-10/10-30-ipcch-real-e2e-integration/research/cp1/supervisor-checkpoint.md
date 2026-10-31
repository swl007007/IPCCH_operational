# CP1 Supervisor acceptance

2026-10-30: accepted; AC1 passes. AC2/AC8 are partially implemented, not passed.

Inspected the complete climate_tables.py diff and new tests, then checked the
final fixes against four concrete review notes: required family fields; consumed
input-window completeness; removal of an unapproved all-baseline/all-source gate;
monthly/seasonal strictness and missing-patch-value regressions.

Verified product SHA256 6aefd477288171d87d5416c9e35a1d082363fe3fdd3507a0dbe0f0c308c0b62c
and test SHA256 781d5be1f0d6e7f563e915769783b6acfe3e718258527f59116e1410f651bc19.
Read complete-log result/exit records: focused 86 passed, exit 0; old-reader sparse
replay 7 failed/1 passed, exit 1. Produced-contract collection failure on the old
reader is not behavioral red evidence. Full-suite rerun 957 passed, exit 0,
overlapped edits; retain that qualification. git diff --check passes.

The report's permanent incomplete-source implication follows the accepted R10
source-calendar completeness rule: dependent source periods remain unavailable,
and existing origin-source rules apply. No new source override or scientific fit
policy is authorized. Other baseline/source gaps keep existing missingness behavior.

CP2 must complete producer graphs, post-2026 planning, export lifecycle, whole-run
deadline, pre-mutation replay protection and durable receipt consumption. CP3 owns
the CLI/Workflow/build wiring. No cloud calls until the concrete CP4 packet review;
live new-month incremental acceptance remains deferred.
