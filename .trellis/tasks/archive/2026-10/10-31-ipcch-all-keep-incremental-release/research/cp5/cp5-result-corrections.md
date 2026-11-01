# Corrections superseding parts of cp5-result.md (DA2 wording)

Executor session 6a490ae1; 2026-11-01 UTC.
- The frozen `cp5-result.md` (a773a2cd) and `SHA256SUMS.final` (2d2d3bc4) are unchanged.
- Where they conflict, this file supersedes them.
- Basis: an exact local tally of the unchanged `da2-witness.json` (d055d703) by `corrections/da2_tally.py`, guarded, child exit 0, output `corrections/da2-tally.json`.
- No helper change, no science rerun and no cloud read.

## C1: saved spei03 at O for the PATCH32 codes (supersedes cp5-result.md line 88)

**Wrong:** "The saved spei03 at 2026-09 is finite for those 31 codes and NaN for 101275."

My error: an early count treated NaN as present, and I then wrote the number without an exact recount.

**Correct tally across the 32 PATCH32 codes:**

| Saved spei03 at 2026-09 | Count | Codes |
|---|---|---|
| Finite | 21 | 76, 77, 983-987, 3422, 3423, 3427-3433, 4073, 4353, 101183, 101191, 101194 |
| NaN | 11 | 2107, 2108, 4267, 4269, 4270, 4783-4787 and 101275 |

- **Ten codes with `filled=true` still have NaN spei03 at O:** 2107, 2108, 4267, 4269, 4270, 4783, 4784, 4785, 4786 and 4787.
  - For these codes, July-September has a null primary ET0 and a finite PATCH32 ET0.
  - Nevertheless, the saved fitted SPEI is NaN.
- **101275:** both primary and patch are null (not filled), and its saved spei03 is NaN.
- **No cause is inferred.** Source-level ET0 candidates do not guarantee a finite fitted SPEI; the fit depends on more than the three input months.
- This witness does not establish a product bug, nor the absence of one.
- It remains a SOURCE-LEVEL candidate witness plus saved values, NOT an independent SPEI numerical replay.

## C2: finite-primary preservation is NOT observed (supersedes cp5-result.md line 87)

**Wrong:** "Finite primaries are preserved", which reported `finite_primary_all_preserved=true` as a result.

That flag is **vacuous**: all 96 sampled (code, month) rows have a null primary, and 0 have a finite primary. There is no natural example of a finite primary next to a patch value.

**Finite-primary preservation therefore moves to the D2 PENDING observations.** It is not an observed pass.

## C3: PERSIANN days_present wording (refines cp5-result.md line 77)

**Wrong:** "its `days_present_202609` is all finite".

The value is finite but **0** in every row; `days_present_202608` is also 0. For `prcp_202107_mean`, `days_present_202107` is 30 of 31.

Product rule, `table_producers.py:186-199`: a monthly precipitation field is masked unless every day is present. The rows are read back through `_periods` (`:412-417`), so these three months are incomplete source periods.

Classification:
- **Not an export failure.** The PERSIANN `Export.table.toAsset` task completed, the asset is readable and validated, and it has 6227 distinct rows.
- **Source-calendar unavailability or incompleteness, recorded by the producer.**
- The lineage disposition records the PERSIANN asset as produced but unconsumed for 2026-09, with spi03/spei03 evidence "S2C3 precipitation table has no published 2026-09".

## Corrected DA2 status (use in the AC matrix and handoff)

**Observed in this run** (local operator EE read; caller identity not established; not runtime-SA evidence):
- **Destinations and tasks:** 7 run-specific destination IDs with completed tasks.
- **PATCH32 set:** exactly the 32 target IDs (32 rows, 0 duplicates).
- **PATCH32 candidates:** 93 natural fill candidates (31 codes × 3 months: null primary with finite patch) and 1 code with neither.
- **Saved spei03 at O:** finite for 21 codes, NaN for 11.
- **Field shapes:**
  - explicit-null fields;
  - wholly omitted fields caused by incomplete source calendars (PERSIANN 2021-07, 2026-08 and 2026-09);
  - per-row omitted keys: none observed.
- **VI:** 3-admin recompute equals saved `evi_anom` (≤ 9e-17; a sample, not a full table); no extra scaling.

**Pending under D2 (not naturally observed):**
- finite-primary preservation beside a patch value;
- per-row omitted keys within otherwise present fields;
- any other field shapes not seen in this run.

DA2 is **partial under D2 and NOT passed as a whole.**
