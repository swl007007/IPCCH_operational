# IPCCH WFP contract correction (Supervisor ruling A, 2026-10-30) - implementation

Ruling: trained WFP_Price = research HDX local-currency staple YoY nearest-market (<100 km) series (definition/source
verified; the WFP `Trend` measure itself remains unverified, so no claim is made about its units). Keep the `ipcch.wfp`
block; refresh = `{action, file (immutable ref), start, end}` with the processed `admin_code, month, value` CSV from the
existing research build; R27-R29/R59 semantics via `retained.refresh_interval`; optional-missing past coverage; no
carry-forward, no new operational fetcher, no HDX port; old IPCCH raw_upload shape rejected in v2; FEWS/legacy unchanged;
initial accepted history untouched; batch tags method/provenance/coverage.

Changes:
- `cloud/orchestrator/delivery_request_v2.py` `_ipcch_wfp` (GitNexus LOW): keep | refresh {action, file, start, end}
  (canonical months, not reversed); `raw_upload`/`converter_contract` refused with a FEWS-only message;
  `iter_object_refs` yields `ipcch.wfp.file`. v1 `delivery_manifest` and FEWS NET blocks unchanged.
- `cloud/ipcch/wfp.py`: `parse_refresh` (exact columns, integral admin_code, strict numerics: blank/NaN missing,
  unparseable/inf refuse) + `apply(store, root, choice, roster, text)` (keep -> coverage report; refresh ->
  refresh_interval: declared-interval replacement, outside rows/unknown areas/duplicates refuse before any write) with
  the METHOD string and source/interval/coverage for the batch report.
- `OPERATIONS.md`: v2 IPCCH WFP_Price section.
Tests: test_delivery_request_v2.py 13 passed (new corrected-shape test, inference-only refresh fixture updated);
test_ipcch_wfp.py 8 passed (keep, interval replacement without fill, 6 refusals with history unchanged).
