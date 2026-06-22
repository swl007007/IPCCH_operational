# FEWS NET Paper Data-Source Evidence

Reference PDF:

`C:\Users\swl00\Downloads\Forecasting_FEWS_NET_Food_Security_Crises_Using_a_Geo_Aware_Spatial_Clustering_Model.pdf`

Extraction command used locally:

```bash
pdftotext -layout "C:\Users\swl00\Downloads\Forecasting_FEWS_NET_Food_Security_Crises_Using_a_Geo_Aware_Spatial_Clustering_Model.pdf" /tmp/forecasting_fewsnet_paper.txt
```

The IPCCH handover uses the same source families and processing logic for these
fixed/slow variables. The extracted PDF text supports the following mappings:

| IPCCH G-03 family | PDF evidence location | Source/method supported by the PDF |
| --- | --- | --- |
| `aez` | Data section lines 772-777; Appendix Table A10 lines 1828-1834 | Agricultural ecological zones are spatially matched to polygons and encoded for prediction; Appendix cites Tricht et al. (2023). |
| `asap_land_cover` | Data section lines 753-777; references lines 923-927 | FAO ASAP cropland and rangeland masks are used as static agricultural background descriptors. |
| `river_distance` | Data section lines 574-582; Appendix Table A10 lines 1787-1791 | River access is constructed from global hydrographic layers and nearest-river distance from polygon centroids; source table cites World Bank and Andreadis et al. (2013). |
| `terrain` | Data section lines 557-572; Appendix Table A10 lines 1787-1791 | Elevation, slope, and ruggedness are physical geography predictors; source table cites ESA for elevation/slope and Nunn and Puga (2012) for ruggedness. |
| `isric_soilgrids` | Data section lines 753-767; Appendix Table A10 lines 1830-1834 | ISRIC SoilGrids provides soil-property layers used as fixed agricultural/biophysical descriptors. |
| `market_access` | Data section lines 650-653 and 717-726; Appendix Table A10 lines 1809 and 1814-1829 | Travel time to cities represents market accessibility; FAO price records support nearest-food-market distance. |
| `population_context` | Predictor overview lines 510-524; Appendix Table A10 lines 1814-1829 | Population density is included as an economic-condition predictor; local IPCCH source-folder provenance is recorded in the CSV manifest. |

Notes:

- The PDF is corroborating evidence for source families and methods. The
  authoritative IPCCH handover fields are the actual columns in
  `Outcome/ipcch_unified/features/ipcch_fixed_slow_features_by_area.csv`.
- Soil field names in IPCCH use `5-15cm`; the G-04 manifest follows the IPCCH
  codebook and column names for depth-specific interpretation.
