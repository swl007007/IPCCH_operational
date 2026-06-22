# G-04 Source and Vintage Metadata

This folder records handover provenance for fixed and slow-moving IPCCH
features. It links the G-03 feature asset back to the unified source panel, local
`1.Source Data` folders, processed source files, codebook descriptions, and the
FEWS NET forecasting paper data section that uses the same source families and
methods.

## Files

| File | Purpose | Check |
| --- | --- | --- |
| `ipcch_fixed_slow_source_vintage_manifest.csv` | Family-level source/vintage/provenance manifest for the G-03 fixed and slow-moving feature asset. | 8 data rows; 25 columns; SHA-256 `ee94d12de508651b93817c40304249e69caf25c1dec67aaef7bdac11fc09dcb6`. |
| `fewsnet_paper_data_source_evidence.md` | Stable note with `pdftotext` extraction command, PDF line references, and source-family mappings used by G-04. | SHA-256 `a44609a3d3adf3091bbd75817dd64ef9206f9b5c6ddc5016df4a837187aa6ecd`. |
| `variable_codebook_reorganized.csv` | Copied IPCCH variable codebook used by the G-05 field schema and feature-family contract. | 168 data rows; SHA-256 `4d917eee94119cf309fd66ff067262765a5c817d17d92d43343d2972f08194f6`. |

## Generator

```bash
python3 tools/build_ipcch_source_vintage_manifest.py
```

Generator SHA-256:

`d0232b6cc0aeacbd1b94bad5a7146f3b44fccc5405d279e3bb81b381b17b9eaf`

## Evidence Sources

| Evidence source | Use |
| --- | --- |
| `Outcome/ipcch_unified/features/ipcch_fixed_slow_features_summary.csv` | Feature list, family assignment, output checksum, missingness, and stability summary. |
| `Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv` | Unified handover source panel used to build G-03. |
| `Outcome/ipcch_unified/metadata/variable_codebook_reorganized.csv` | Copied codebook descriptions and source hints for IPCCH columns. |
| `C:\Users\swl00\IFPRI Dropbox\Weilun Shi\Google fund\Analysis\1.Source Data\assembled_IPCCH\metadata\variable_codebook_reorganized.csv` | Original source for the copied IPCCH codebook. |
| `C:\Users\swl00\IFPRI Dropbox\Weilun Shi\Google fund\Analysis\1.Source Data\{AEZ,ASAP_land_cover,Distance_to_rivers,Elevation,ISRIC,Market_access,Populationdensity,Ruggedness,Slope,FAO,Coastline_distance_NOAA}` | Local processed source files and raster references. |
| `C:\Users\swl00\Downloads\Forecasting_FEWS_NET_Food_Security_Crises_Using_a_Geo_Aware_Spatial_Clustering_Model.pdf` | Paper data section and Appendix Table A10 corroborating source families and methods. |

## Scope Notes

- This is a handover provenance manifest, not a publication bibliography.
- The manifest records both provider/source-family vintage and local processed
  file timestamps. Local timestamps document the handover artifact state; they
  are not substitutes for provider publication dates.
- `market_access` and `market_distance` are kept in the same G-03 family but
  have different upstream sources: travel time to cities for `market_access`,
  and FAO price market matching for `market_distance`.
- Soil fields in the IPCCH codebook and column names use `5-15cm`; this
  handover follows the actual IPCCH field names even though the related FEWS NET
  paper prose describes near-surface soil extraction more generally.
