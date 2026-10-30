# CP3c-2 — IPCCH ACLED converter port + weekly store (executed evidence)

Code: `cloud_pipeline/cloud/ipcch/acled.py` (new; no existing symbol changed). Tests: `cloud_pipeline/tests/cloud/test_ipcch_acled.py` (6 passed, exact-lock env).
- Runtime uses only the delivered tables (mapping incl. override-first precedence, population, D24 neighbours, coverage start + ACLED region, unit weights, unit ISO3); unmapped admin1 of a mapped country = hard refresh failure; countries outside the table dropped and counted.
- Weekly store: one VersionedTable; a refresh replaces declared interval × declared regions and appends its coverage record in ONE commit; first refresh must complete months O-12..O for every mapped region (R44); month completeness from declared interval/region coverage of every overlapping week (R56), so covered event-free weeks are 0 and uncovered months NaN; coverage_end for R53 warnings.
- First unit-test run: 4 failed because the test fixture declared END Friday 2026-08-28, leaving the week starting Saturday 2026-08-29 (overlapping Aug 30–31) undeclared, so August was correctly incomplete; fixture END → 2026-09-04; 6 passed.

## Full-history parity vs research (`acled-parity/acled_parity.py`, result `acled_parity_result.json`, log)
Inputs: research raw exports `staging/ipcch-update-202610/sources/acled_agg/raw/aggregated_2026-10-20/*` (sha256 checked against exports_manifest.json; prefiltered to the kept f1/f2 regions as the operator would export them), one declared interval 2009-12-26..2026-10-16, the delivered work tables. Reference: research `processed/acled_agg_monthly.csv` (1,250,808 rows).
Result: exit 0 in 8.4 s; for all 18 columns the NaN pattern is identical and max |diff| ≤ 1e-9 on every reference key (2010-01..2026-09); coverage_end(2026-09) = 2026-09.
