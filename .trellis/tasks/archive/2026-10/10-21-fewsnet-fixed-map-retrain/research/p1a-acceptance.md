# Supervisor acceptance of P1a

This accepts raw-label and crosswalk evidence, not AC1 as a whole, fitting readiness, or production acceptance. Executor checkpoint: `p1/p1a-checkpoint.md`. Independent verification: `supervisor-p1a-verification.json`.

## Accepted label decisions

- Use the original HDX freeze `hdx-cs-20261022T043937Z`: 22 countries, 44 files, 176548777 bytes; hashes/sizes independently rechecked. Every country's latest content month is June 2026; all collections are Published/CS, record IDs unique, and every valid phase is a Collected record. Distinguish `collection_status` from record `status`.
- Accept only the strict crosswalk: unique same-country boundary equivalence, reciprocal overlap at least 0.999999 (measured precision mode), one-to-one support, unique source records, exact country/month/fnid/value agreement, phase 1–5. No 90%/95% identity/containment rule. Preserve all unresolvable changes/gaps and the fixed 5718-area roster.
- Accept 4039 June 2026 additions, 350 October 2024 gap fills, and 351/369 October 2025/February 2026 observed replacements of proven synthetic fills: 5109 new observed targets total. Ethiopia contributes no new June labels because its redrawn geometry is not equivalent; its historical data and prediction roster remain.
- Preserve the seven documented edge-sliver cases: each has exactly one boundary-equivalent official unit; the tiny neighboring overlap is not another equivalent support. Keep conflict diagnostics and source IDs. Do not aggregate, vote or transfer the neighbor's phase.
- Independently inspected notebook cell 38 (`49ea1acc16bc8babb956faeaaa09596412b9be4917197b28ce542b92586b81c8`) and the combining notebook (`0583c74c54190236f692c9cfa0c32f52228d1a4e8085517d12104e51a1f8edad`). Independently recomputed keyed lineage: 1259/1373 unique targets absent from FEWS_2025 are exactly phase 1/crisis 0; combined panel equals the intermediate on all 5718 keys per month. Consistent duplicated intermediate keys were explicitly checked before deduplication.
- In the new versioned dataset, clear all 2632 proven synthetic targets, then attach the 720 verified replacements. The remaining 1912 stay missing and cannot be fitting targets. This enforces R4 observed-label eligibility; it is not an override of complete historical observations. Preserve raw files, old packages and all keyed changes/exclusions.
- Preserve other complete old values, including the 600/682 old name-merge labels with unverified geometric lineage and 1158 older October 2024 labels without a new strict match; disclose them. Do not replace provider revisions without separate difference review.

## Verified and remaining work

The supervisor reran all 10 unittest checks successfully. Raw content, direct source notebook logic, keyed lineage and record-check evidence were sampled independently. No model fit/evaluation occurred.

The current operator environment has certifi 2026.10.19 instead of lock pin 2026.7.22. It may continue public retrieval/data preparation, but create or verify a separate exact-lock training/runtime environment without modifying the user's existing CA-remediated environment. No silent lock substitution.

Preserve the complete supplemental June 2021 geometry and record its honest source/hash/timing evidence; its retrieval receipt was interrupted. Do not invent an HTTP result or retrieval timestamp. A bounded refetch of that one supporting object is allowed if necessary.

Continue WFP/ACLED/remote/GOSIF preparation and independent full-data runner/package implementation. Fitting remains pending the complete versioned input/fit-eligibility freeze, fixed-runtime evidence and focused software checks. Cloud operations are task-scoped preapproved until 2026-10-22T13:00:00Z; retain operation receipts and all release/maintenance gates. No Audit workflow.
