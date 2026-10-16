# A01 repair: carry integer precision across import chunks

Status: approved by the supervisor's relayed instruction (2026-10-16), as a narrow repair of close-audit finding **`gcp-research-modeling-migration-A01`** (job `4b7c22cfcecc2b8e8c67e36a`, minor, gate_open 0, audited `e0a3b45`). It is an ordinary task: the job has no open gate, so the lifecycle start is a normal wrapper start, not `--remediation-for`.

## Problem (A01)

`research_cloud/sqlimport/load_inputs.py` `infer_types` reads 50,000-row chunks.
1. A column whose earlier chunk holds an integer that is not exactly representable as a double (e.g. `9007199254740993`) stays `bigint`.
2. A later chunk with a fractional value promotes the column to `double precision`, and the exact-integer check sees only that later chunk.
3. The early integer is then stored rounded.
4. The verifier converts source and SQL values to the same float, so the receipt still says `verified`.

## Requirements

- **R1:** carry each column's integer-precision constraint across all chunks. If any integer literal seen in any chunk cannot safely enter a floating-point column, a later promotion to `double precision` must yield `text` (verbatim) instead.
- **R2:** pure-integer columns keep their current behaviour (`bigint` up to 18 digits, `text` beyond).
- **R3:** the safety criterion is the existing within-chunk rule: more than 15 digits, or magnitude above 2^53. It is applied to integers from every chunk, before or after the promotion.
- **R4:** regression tests across the CHUNK boundary in **both row orders** (large integer before and after the fractional value). They check that the stored value equals the **original integer text** before any float conversion, and that pure-bigint columns are unchanged.
- **R5, exposure:** a bounded, read-only scan of the actual migrated corpus.
  - Source files are only read, and hashes are re-checked against the frozen inventory.
  - The prefilter is conservative: no delimiter consumption, so adjacent fields are not missed. Any line holding a run of at least 16 digits counts as a hit.
  - Only files with hits get `csv.reader` tokenization, column mapping and exact Python-int comparison against the migrated column type.
  - "Unaffected" may be concluded only after every inventoried source byte intended for the check is covered and its hash still matches.
- **R6:** repair cloud tables **only if the scan proves them affected**, with separately logged, scoped evidence. Otherwise no cloud change.
- **R7:** the native control-plane and the registered lineage end with the same `research_cloud` code.

## Out of scope

- No general numeric-parser rewrite or new ingestion platform.
- No blind full parse of 1.2 billion cells.
- No paid jobs, deployments or broad reruns.
- Adjacent edges found by the scan (whitespace-padded or long-decimal literals) are reported, not fixed here.

## Acceptance

- **AC1:** R1–R3 implemented. The new tests fail on 6ee56f5 and pass after the change; the existing sqlimport tests still pass.
- **AC2:** exposure receipt covering all 53 inventoried CSV sources (hashes matched, byte coverage complete), with every hit classified. Any affected table is listed with its exact evidence.
- **AC3:** if a table is affected, a scoped cloud repair with before/after evidence; otherwise an explicit "no cloud repair needed", with the receipt.
- **AC4:** native and registered `research_cloud` trees are identical at close; staged `detect_changes` was run before each registered commit.
