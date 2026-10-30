# IPCCH GPP v3 adapter matching the delivered history (Executor, 2026-10-30; Supervisor ruling on gpp-v3-units.md)

Finding (research/cp3/gpp-v3-units.md): the shared operational v3 contract (raw zonal mean, no fill mask, no scale)
would append values ~100x the delivered history and average fill codes 65534/65535 as data.

Fix (IPCCH only; `cloud/batch/remote_sources.py` and `cloud/orchestrator/prepare.py` unchanged, FEWS NET/legacy keep raw
statistics): `cloud/ipcch/gpp.py`
- `zonal_gpp_mean`: research formula verbatim (extract_gpp_v3.py:123-133): float64 sum of member cells not in
  {65534, 65535} / n_valid * 0.01; members = cell centres in the polygon (rasterio mask all_touched=False, one polygon
  at a time, unweighted); true zeros valid; n_valid 0 -> NaN; enforces the provider grid (uint16, EPSG:4326,
  3600x7200, 0.05 deg; nodata unset or a fill code). method_id
  `gosif-gpp-v3-mean|fills65534,65535-masked|sum/n_valid*0.01|cell-centre-unweighted|research-10-27`.
- `update_gpp`: reuses the v3 URL contract, `CloudSourceAcquirer._head` and `_acquire_http`; candidates = months after
  the last saved month through O + ledger-unpublished months; 200 -> extract, append immediately via
  `retained.append_months` (never rewrites; fills only ledger-unpublished gaps, R9), ledger `published` with the
  retained copy's uri/generation/sha256; 404 -> ledger `unpublished`, month absent (optional-missing, R65); any other
  status / exception / download / grid error -> `GppProcessingFailure` (R49) with the progress report attached;
  geometries must be exactly the roster in roster order (`geography.roster_geometries`).

Tests `tests/cloud/test_ipcch_gpp.py` (7): synthetic uint16 nodata=None raster with mixed valid/fill, true-zero, all-fill
and outside zones -> bit-equal to the research arithmetic (0.15, 0.0, NaN, 0.025, NaN); shared legacy
`rs.zonal_statistics` unchanged (raw mean incl. fill codes, FEWS mapping intact); grid/encoding enforced; ledger
published/unpublished + late fill-only-unpublished without re-download/rewrite; 503/timeout block after saved months
and are not recorded as unpublished; roster-exact geometries. With test_prepare.py: 38 passed.
