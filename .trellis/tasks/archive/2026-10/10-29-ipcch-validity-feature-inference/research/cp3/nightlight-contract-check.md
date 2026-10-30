# Nightlight: delivered history vs operational VIIRS contract (Executor, 2026-10-30)

Check (local read-only, pandas): delivered `out-r5/history/nightlight_mean.csv` (1,244,388 rows, 2010-01..2026-08,
method `delivered:interim@b2d5d2ce6bd6`, median 0.40, max 16,702.9, 23,488 small negative values from 2012 bilinear
resampling) joined to the operational bootstrap `cloud_pipeline/bootstrap/assets/ipcch/history/viirs.csv` (current
contract output: avg_rad__sum/std/mean) on 173,703 shared (admin_code, month) keys, 2024-01..2026-04:
`avg_rad__sum / value` on 124,516 non-zero pairs: quantiles (5/50/95%) 1.0/1.0/1.0; bit-equal 97.0%. So the existing
contract (`MODEL_COLUMN_MAPPING["ipcch"]["nightlight_mean"] = avg_rad__sum`, bilinear 1/30 deg, cell-centre zonal SUM)
is the history's unit and method; no IPCCH-specific adapter is required (contrast GPP, gpp-v3-units.md). The ~3%
non-equal pairs are not investigated further (method differences are recorded, not gated, R64).

Implementation `cloud/ipcch/nightlight.py` (`update_nightlight`): months after the last saved through O; existing
`published_months` / `start_exports` / `acquire` / `zonal_statistics(family="viirs")` on `geography.roster_geometries`;
unpublished months = source-level gaps (optional-missing, R65); retrieval/extraction errors block after saved months and
cancel started exports. Tests `tests/cloud/test_ipcch_nightlight.py` (3 passed).
