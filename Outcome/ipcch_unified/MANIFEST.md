# Unified IPCCH Outcome and Reference Assets

This folder is the G-02 replacement for legacy split CH/IPC `Outcome`
reference files. Treat `IPCCH` as one production input/output contract unless a
downstream consumer explicitly requires a legacy split export.

## Source

Copied from:

`C:\Users\swl00\IFPRI Dropbox\Weilun Shi\Google fund\Analysis\1.Source Data\assembled_IPCCH`

## Files

| File | Role | Rows / size | SHA-256 |
| --- | --- | --- | --- |
| `raw/IPCCH_2026_completed.csv` | Authoritative unified historical panel with keys, outcomes, and features through 2026-04. | 1,219,868 data rows; 1,782,567,753 bytes | `ae696087c3bbb280537ae269a05924133acdb51060d31290523404fa8a717673` |
| `interim/ipcch_scaffold_202604.csv` | One-month production scaffold example keyed by `admin_code`, `lat`, `lon`, `year`, `month`. | 6,227 data rows | `199882aae1151836efd159a2a3506d9183449b5b1b39047daee6dea5a21961f4` |
| `interim/ipcch_scaffold_202501_202604.csv` | Multi-month reference/batch scaffold, retained for QA and rebuilding one-month scaffolds. | 99,632 data rows; 4,110,280 bytes | `e4cda142a0b3adf2dac8e31c16a3450690e42d5d61b1e79ec6c1ede4c9a8ce2e` |
| `spatial/unique_area_id_lat_lon.csv` | `area_id` to coordinate lookup. | 6,227 data rows; 224,352 bytes | `3bf8f115ec70cd1e1c907031309b797410a8024cdc1d39265be123ae636d2862` |
| `country_area_id_lookup.csv` | `area_id` to country lookup. | 6,227 data rows; 214,996 bytes | `e2baf6ae9481b42b127db5ce81f3c53ad784bb08ae56dfa56cea74e416b44c90` |
| `country_region_mapping.csv` | Country to region mapping. | 53 data rows; 1,611 bytes | `40442e0de598511e1fe379335af0d65b33b02e25a5458b79170542f6c67d1e32` |
| `DATASET_INDEX.csv` | Source package file index from `assembled_IPCCH`. | 55 data rows; 9,473 bytes | `f2ada6ba562486995dfca9988b35d76fdf59bb4ce9fd8e6ac45edd276a6d1409` |
| `spatial/ipcch_admin_geometry.shp` and sidecars | Unified IPCCH geometry. | `.shp` is 68,930,596 bytes | See checks below. |
| `features/ipcch_fixed_slow_features_by_area.csv` | G-03 fixed/slow-moving feature handover asset derived from the historical panel plus coastline distance source. | 6,227 data rows; 48 columns | `89bbda8680b98bc6edddea3fa19f863dadb52dbb0ad88ed09e15997d006ba482` |
| `features/ipcch_fixed_slow_features_summary.csv` | Feature-level missingness and stability summary for the G-03 asset. | 36 data rows | `2ae4884a4e4cbfa5ff133f58a353d52249a5e248a1773f9e7b29527298ad8fb1` |
| `metadata/ipcch_fixed_slow_source_vintage_manifest.csv` | G-04 source/vintage/provenance manifest for G-03 feature families. | 8 data rows; 25 columns | `ee94d12de508651b93817c40304249e69caf25c1dec67aaef7bdac11fc09dcb6` |
| `metadata/variable_codebook_reorganized.csv` | Copied IPCCH codebook used by the G-05 schema contract. | 168 data rows | `4d917eee94119cf309fd66ff067262765a5c817d17d92d43343d2972f08194f6` |
| `schema/ipcch_base_panel_schema.csv` | G-05 field-level schema for the unified IPCCH base long panel. | 169 data rows; 14 columns | `c2f477162bf17ea6377ff88916f58aa8e6d32c28a53ae99c110b99edd1182b90` |
| `schema/ipcch_feature_family_contract.csv` | G-05 feature-family contract by codebook group. | 14 data rows; 8 columns | `5867106f287963f9da81b8d3043c23655f9719529474ea0f9d0ce3875d31d484` |
| `schema/ipcch_model_input_contract.md` | Human-readable unified IPCCH model input contract. | Markdown | `1e30908222895fdda77bc7e1288ff409451c0c1e7aeb5afba54452d0042fda46` |
| `schema/MANIFEST.md` | G-05 schema folder manifest. | Markdown | `63e270e038110bf7e957696edf7feb14cdd882aec43ddbd12edeb8c2aeb5d2ef` |

Geometry sidecar checks:

| File | SHA-256 |
| --- | --- |
| `spatial/ipcch_admin_geometry.shp` | `49ee44f49a2832b70f94a5df999018c4e9f3461cb96d8d79c83e308a4fbe24a0` |
| `spatial/ipcch_admin_geometry.dbf` | `eca55302f2f494a08db401202f3efdf7b120d1e3c5f741d80117b0b4b5b97fde` |
| `spatial/ipcch_admin_geometry.shx` | `a19d750a68eed012832c7c0027140543b49e85596452b85acf30eb53f073dca3` |
| `spatial/ipcch_admin_geometry.prj` | `5d3b39697820a6d6dfe49413bea38603f41331c162725fd1bd958941034a1c37` |
| `spatial/ipcch_admin_geometry.cpg` | `146d6789ffe033a5297c1ad046e6a62ee35319b86b021444f05b6ea2aa8a1f4a` |

## Validation Notes

- `raw/IPCCH_2026_completed.csv` has no duplicate
  `(admin_code, lat, lon, year, month)` keys.
- The historical panel covers 2010-01 through 2026-04.
- The production scaffold should be one target month. The current example is
  `interim/ipcch_scaffold_202604.csv`; regenerate other months with
  `tools/build_monthly_ipcch_scaffold.py`.
- Outcome columns are sparse by design because not every scaffold row has an
  observed outcome.
- `features/ipcch_fixed_slow_features_by_area.csv` is generated with
  `tools/build_ipcch_fixed_slow_features.py`. Each area uses the latest
  nonmissing source value by `year`/`month`; see the summary CSV before
  treating a column as strictly time-invariant.
- `coastline_dist` is joined from the local coastline distance source by
  rounded latitude/longitude and is complete for the current 6,227 areas.
- `metadata/ipcch_fixed_slow_source_vintage_manifest.csv` is generated with
  `tools/build_ipcch_source_vintage_manifest.py` and records local source files,
  source-family vintage, codebook evidence, PDF data-section evidence, and
  checksums.
- `schema/` is generated with `tools/build_ipcch_schema_contract.py`. It defines
  the unified IPCCH long-panel contract and the final repo output target:
  monthly model-compatible input, later combined with exported model weights and
  the model pipeline to produce predictions.
- `tools/validate_ipcch_schema.py` validates the G-05 historical panel,
  forecast scaffold, fixed/slow area asset, and future model-ready exports.
- Large raw and geometry files are excluded from GitHub via `.gitignore`; they
  are local Dropbox handover assets.
