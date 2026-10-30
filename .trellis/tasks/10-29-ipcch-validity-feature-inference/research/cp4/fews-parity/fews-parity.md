# R60 FEWS NET real-deliver parity (Executor, 2026-10-30)

Question (Supervisor on 43c6d12): does the v2 FEWS NET route produce the same FEWS NET delivery as the existing
`deliver(system="fewsnet")` on identical inputs, with the REAL scorer and the existing ACLED/WFP converters?
Local only; no cloud, no EE, no retraining.

## Result

Both modes (keep with the canonical SHARED FEWS+IPCCH retained stream; refresh with format-valid raw ACLED/WFP
exports through `conflict_aggregates`/`wfp_aggregates`): the v2 run succeeded and published `parity-<mode>-fewsnet`.
Of the 31 files the existing `deliver` writes, **28 are byte-identical**, including **all 15 scope tables**
(`scopes/{0,6,12}m/fewsnet/*.csv`), and the remaining **3 are identical once their own output root is normalized**
(`all_identical_modulo_output_root: true`):

- `inputs/fewsnet_fill_sources.json` and `reports/fewsnet_normalization_audit.json` embed absolute `file://` / path
  references to the directory `deliver` wrote into (reference: `.../world-<mode>/reference`; v2: its deleted temporary
  `.../v2-delivery-parity-<mode>-fewsnet-*/delivery`).
- `reports/fewsnet_feature_fill_audit.csv` cites `fewsnet_fill_sources.json` by path and sha256; after the path
  normalization that cited digest is mapped to the reference digest (only for a file proven identical modulo the root).

Refresh changed the scores relative to keep (polygon_predictions sha differ for 0/6/12m; max |Δ probability_crisis|
0.09 at 0m), so the converter outputs reached `deliver` in both routes.

## Inputs (real October bootstrap, subset)

- areas: FEWS NET `2679-2684` (KE) and `5335-5340` (UG); IPCCH side `0, 1, 10` (only to make the prepare request's
  declared IPCCH refs and the shared retained stream real; never collected/scored).
- packages: `cloud_pipeline/bootstrap/models/fewsnet/{0,6,12}m` (accepted local packages; model.joblib sha256
  0m 63703184..., 6m aa5f80be..., 12m 47cba49d...), unchanged.
- subset files (scratch, sha256): fews_panel.csv c4ea0a8c..., fews_geometry.geojson 0321e148..., fews_roster.csv
  95bacff6..., fews_census.csv 316ea45e... (census restricted to KEN/UGA: country tables cover exactly the census
  countries), ipcch_panel.csv bc5d315e..., ipcch_geometry.geojson 5f6cf0f6..., ipcch_roster.csv b2da4a77...;
  raw exports acled_export.csv 9faf0c53..., wfp_export.csv 5d1c627b... (full digests: `parity-results.json` and
  `sha256sum` below).
- origin 2026-07 (panel and family histories end 2026-04; preparation extracts 2026-05..07).

## Method

- reference: `deliver(system="fewsnet", ...)` called directly with the legacy composition of `run_system`
  (snapshot families/features via `load_prepared_features`, raw panel, packages, census, geometry, keep -> `None`,
  refresh -> the existing converters' frames at cutoff = origin).
- v2: `run_v2.run_request` with `fews_adapter.runner`: admission (pinned prepare_request + every nested ref), FEWS
  NET-scoped `prepare.run_prepare`, the generation source binding, `publish_scored_member` with the REAL in-process
  `delivery_job.run_system` -> `deliver`, the FEWS-scoped member checks, v2 publication.
- same prepared snapshot for both (the one the v2 generation produced).

## Limitations (stated, not hidden)

- The prepared remote-sensing rasters come from a deterministic local acquirer (`GridAcquirer`), not provider data:
  the extraction path (`zonal_statistics`, outputs, manifest) is the existing one, the raster values are synthetic.
- Diagnostics are declared unavailable for every FEWS family (the parity concerns scoring/outputs, not evidence).
- A 12-area subset normalizes within itself; these are not the October production numbers. The claim is route
  equality on identical inputs, not reproduction of a delivered release.

## Readback

```
cd "<OP>/.trellis/tasks/10-29-ipcch-validity-feature-inference/research/cp4/fews-parity"
PYTHONDONTWRITEBYTECODE=1 ~/.venvs/fewsnet-test-lock-20261022/bin/python fews_parity.py ~/scratch/ipcch-fews-parity
#  -> parity-results.json (committed), parity-run5.log (on disk; *.log is gitignored)
sha256sum ~/scratch/ipcch-fews-parity/subset/* ~/scratch/ipcch-fews-parity/raw/*
#  outputs: ~/scratch/ipcch-fews-parity/world-{keep,refresh}/reference/            (existing deliver)
#           ~/scratch/ipcch-fews-parity/world-{keep,refresh}/gcs/parity-root/deliveries/parity-<mode>-fewsnet/  (v2)
```

Script: `fews_parity.py` (this directory). Results: `parity-results.json`. Runs 1-4 were the fixture census fix
(full census vs 2 scored countries -> the existing country-key check refused the member, correctly) and the
comparison-normalization fixes; run 5 is the result above.
