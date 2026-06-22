# G-03 Fixed and Slow-Moving Feature Asset

Source:

`Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv`

Generator:

```bash
python3 tools/build_ipcch_fixed_slow_features.py
```

## Outputs

| File | Purpose | Check |
| --- | --- | --- |
| `ipcch_fixed_slow_features_by_area.csv` | One row per unified IPCCH area, with `area_id = admin_code`, coordinates, country identifiers, source coverage, and selected G-03 feature values. | 6,227 data rows; 48 columns; SHA-256 `89bbda8680b98bc6edddea3fa19f863dadb52dbb0ad88ed09e15997d006ba482`. |
| `ipcch_fixed_slow_features_summary.csv` | Feature-level missingness, source checksum, output checksum, and within-area stability summary. | 36 data rows; SHA-256 `2ae4884a4e4cbfa5ff133f58a353d52249a5e248a1773f9e7b29527298ad8fb1`. |

## Included Feature Families

| Family | Columns | Stability in source panel |
| --- | --- | --- |
| AEZ | 21 `AEZ_*` columns | All verified static. |
| ASAP land cover / masks | `crop`, `range` | Verified static. |
| River distance | `distance_to_river` | Varies within 16 areas; output uses latest nonmissing value. |
| Terrain | `elevation`, `ruggedness`, `slope` | All verified static. |
| ISRIC SoilGrids | `sg_cec_5-15cm`, `sg_cfvo_5-15cm`, `sg_nitrogen_5-15cm`, `sg_phh2o_5-15cm`, `sg_soc_5-15cm` | Varies within 300-345 areas depending on column; output uses latest nonmissing value. |
| Market access | `market_access`, `market_distance` | `market_access` is verified static; `market_distance` varies and is missing for 141 areas. |
| Population context | `popdensity` | Verified static where present; missing for 4,919 areas. |
| Coastline distance | `coastline_dist` | Complete for all 6,227 areas by rounded lat/lon match from the coastline distance source CSV. |

The unified source panel does not expose separate `ESA_*` columns. The legacy
ESA handoff should stay superseded unless a downstream consumer requires those
source-specific files again.
