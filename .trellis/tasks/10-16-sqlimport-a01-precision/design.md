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

## Exposure scan (read only; script kept with task evidence)

1. For each of the 53 CSV inventory entries: stream the bytes once, compute sha256 (must equal the inventory), and run the over-inclusive prefilter `\d{16,}` across block boundaries (with a 15-byte overlap). Record hit counts and offsets. Total bytes covered must equal each file's size.
2. Files with hits: full `csv.reader` pass, header-mapped. Each field containing a 16+-digit run is classified as:
   - (a) a pure integer literal that is unsafe by R3;
   - (b) a signed or leading-zero literal (text by the existing rules);
   - (c) whitespace-padded;
   - (d) a decimal or exponent literal;
   - (e) other text.
3. Classes (a) and (c) are joined to the migrated column type, read from the cloud `research` catalog (`public._column_catalog`, SELECT only). A field is **affected** if the type is `double precision`. The local rehearsal catalog is used only as a cross-check.
4. Receipt: per file the sha, bytes covered, hits and classification; per affected column the rows, values and type.
   - **No affected column:** no cloud change.
   - **Affected column:** a scoped repair plan, logged separately and done only after review.
