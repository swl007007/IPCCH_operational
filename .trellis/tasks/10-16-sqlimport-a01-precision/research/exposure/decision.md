# A01 exposure decision (2026-10-16, scan 13:37:20–13:50:12)

**Result: the A01 trigger is absent from the migrated corpus. No cloud repair (R6 not triggered).**

- **Coverage:**
  - All 53 inventoried CSV sources were streamed read only, 13,763,421,380 bytes in total, equal to the import report's verified source bytes.
  - Every file's sha256 equals both the inventory and the import receipt, and every byte count equals the inventory.
  - Receipt: `exposure-receipt.json` (sha256 `8d1bb0c7e233ad1e1488ff0afde4c3dfa48b8576e3879b7859677c53492d22d4`).
- **Prefilter** (CSV integer field, at least 16 digits, boundary/quote/space/sign aware, non-consuming lookahead; self-test passed): **0 candidate lines in all 53 files**.
- **Multi-line records:** 3 files are not single-line. In each, the extra physical lines account exactly for the multi-line records found:
  - `fewsnet.extension_component_2025_combined`: 392 extra lines = 196 records × 2;
  - `fewsnet.outcome`: 53 = 53 × 1;
  - `fewsnet.panel`: 360 = 180 × 2.

  Every field of every one of those 429 records was tokenized with `csv.reader`: **0 fields** holding a 16+-digit integer. No lone CR in any file.
- **Classes:**
  - class 1 (type would change under R3): 0;
  - class 2 (`int(raw) != int(float(raw))` in a double column): 0;
  - class 3 (lexical edges such as padded or signed long integers): 0.
- **Consequence:** the repaired `infer_types` changes a column's type only when an integer literal of more than 15 digits exists. None exists, so it yields the same types as the migrated catalog for all 53 tables (10,109 double columns in 45 tables, from `cloud-column-catalog.json`, sha256 `3ef25d7d737c95fd0b58df70fcf8b34dfaac7ae63cfc1b469cae6f4f73b03a04`, a read-only SELECT as `research_read`). The stored cloud values are therefore unaffected by A01.
- **Limits:**
  - This shows the absence of the A01 trigger only. It is not a general numeric re-verification.
  - Long decimal literals (no integer form) are outside A01 and were not classified.
  - The import's own cell-level verification (accepted) covers the rest.
