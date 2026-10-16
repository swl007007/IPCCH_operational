# Design

## Code change (`research_cloud/sqlimport/load_inputs.py`, `infer_types` only)

- Add a per-column flag `unsafe_int[c]`: whether any integer literal (`-?\d+`, after the existing sign/leading-zero exclusion) seen so far in **any** chunk has more than 15 digits or magnitude above 2^53.
  - In the `bigint` branch, an all-integer chunk updates the flag before `continue`. The existing > 18-digit → `text` rule is unchanged.
  - When a column is (or becomes) `double precision`, it becomes `text` if the flag is set, whether the flag came from an earlier chunk or from this one. The existing within-chunk check folds into the same flag.
- Nothing else changes: chunking, `parse_column`, `copy_rows`, `compare_table` and the identifier/text rules.
- Consequences:
  - A pure-bigint column with at most 18 digits is unaffected (the flag only matters once a column turns double).
  - Columns already typed by the current code keep their type unless they meet the new condition.

Impact: `infer_types` ← `load_one` ← `load_inputs.main` (← `deploy/load_research_inputs`, which has run and is not re-run) and the tests. GitNexus cannot resolve it (index predates the merge; UNKNOWN), so impact comes from a pinned-source caller search at 6ee56f5. Assessed **LOW**.

## Tests (`research_cloud/tests/test_sqlimport.py`)

- **Pure `infer_types` tests** (no database): CSVs that cross CHUNK, in both orders:
  - 16+-digit integer in chunk 1, fraction in chunk 2;
  - fraction in chunk 1, integer in chunk 2;
  - a pure-integer column across chunks.

  Expected: `text`, `text` and `bigint`.
- **Round trip on the disposable local PostgreSQL** (`RC_TEST_PG`): `load_one` in both orders, then the stored value is read back as text and compared with the source integer literal, before any float conversion.

## Exposure scan (read only; script and self-test kept with task evidence; plan corrected after supervisor review)

1. **Stream and prefilter.** For each of the 53 CSV inventory entries, stream the file **line by line** in binary. Each physical line updates the sha256, which must equal the inventory at the end; total bytes must equal the file size. Each line is matched against the integer-field pattern:

   `(?<![^,])\s*"?\s*[+-]?\s*[0-9]{16,}\s*"?\s*(?=,|$)` (on the line, with its line ending; `\s` includes CR, so quoted padding and CRLF are covered)

   - The leading boundary is start of line or a preceding comma, via a lookbehind that consumes nothing.
   - The trailing lookahead does not consume the comma, so adjacent integer fields both match.
   - Decimal mantissas (`0.12345678901234567`) and exponent forms do not match.
   - Record per file: candidate line numbers, hit counts and byte offsets.
2. **Multi-line quoted fields (not claimed complete by the prefilter).** The line-based prefilter is exact for files whose records are all single-line, so this is checked per file rather than assumed:
   - **single-line files:** the streamed physical line count equals the imported data rows + 1 (header), allowing one trailing empty line;
   - **other files:** the multi-line records are located with a `csv.reader` pass, and **every** field of every multi-line record is tokenized and classified. The file is listed as an edge that needed record-level handling.

   Anything not covered this way is reported as an **unresolved edge**, not as unaffected.
3. **Tokenize candidates.** Only files with candidates get a `csv.reader` pass, which uses `line_num` to map records to physical lines. Only records spanning a candidate line are examined; their fields are tokenized exactly and mapped to header columns.
   - Source row number = record index, the same 1-based count `copy_rows` writes to `_source_row`.
   - Short rows are flagged, since they go to the side table.
4. **Classify each candidate field** using the migrated column type from the cloud `research` catalog (`public._column_catalog`, SELECT only; the local rehearsal catalog as a cross-check):
   - **class 1, type-change:** the value is a pure integer literal as `infer_types` sees it (`-?\d+`, not `+`, not leading-zero), unsafe by R3 (more than 15 digits or above 2^53), and the column was migrated as `double precision`.
   - **class 2, actual loss:** a class-1 value for which `int(raw) != int(float(raw))`. For a positive candidate, the stored SQL value at that `_source_row` is read (SELECT only) to confirm.
   - **class 3, lexical edge:** whitespace or quote padding, plus sign, leading zero, or a value in a text or bigint column. Reported as out of scope.
5. **Self-test before scanning** (bounded, explicit), on in-memory lines:
   - adjacent integer fields;
   - quoted, space-padded and signed fields;
   - LF, CRLF and CR line endings;
   - a decimal mantissa that must not match;
   - a field at end of line without a newline;
   - a token spanning a read boundary. Line streaming means a line is never split, which the test shows with a tiny-buffer reader;
   - a quoted field containing CR/LF around the digits, and a multi-line record (it must be detected by the line/row-count check).
6. **Decision.** Cloud updates happen only for proven class 2 with the exact scope (table, `_source_row`, column, source value, stored value) and a separately logged plan reviewed first. Class 1 alone means the import rule would type the column differently; it is reported without claiming corruption.
