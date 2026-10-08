# CP1 parallel lineage investigation

2026-10-07, read-only exploration while the Herdr executor implements independent CP1 contracts. Findings narrow T1; they do not pass it. No model, raster extraction or cloud execution. External files are historical source evidence, not an approved replacement for canonical inputs.

Path abbreviations: `D=/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data`; `S=/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/2.source_code`. Notebook cells below are zero-based; lines within cells are one-based.

## FEWS-specific evidence

- `S/Step2_combine_all_dataset_and_impute/00_combine_all_FEWSNET.ipynb`, cell 0:13–17, reads FEWS nightlight **mean** and std exports and FEWS EVI mean/std exports. Cell 1:4–7 directly renames `region_id` to `admin_code` and joins nightlight by admin/year/month. Supervisor directly checked these lines; notebook SHA256 `db79ec70c466445dee3ec0e107f1ef1df50d9a19dfa51f4172dd856d73792687`. Do not transfer the CH nightlight SUM rule to FEWS. The filename identifies the selected intermediate, not proof of its actual raster reducer.
- `S/Step1_GPP/02_extract_GPP_mean_FEWSNET.py:15–18,42,62,69` selects FEWS_Admin_LZ_v3, explicit `admin_code`, ArcPy DATA/MEAN, writes that key as `region_id` in `GOSIF_GPP_extraction_results_FEWSNET.csv`. Supervisor directly checked those lines; SHA256 `8e882e8c608b39145906d534bc0b9e6f07218ea9ae28d6286d87d635d7e9b000`. The notebook cell 1:278–280 renames and joins it by native key/month. Moving this output from Processed_Dataset to the consumed source-data directory remains unproven.
- FEWS EVI extractor `S/Step1_EVI/02_alternative_extract_EVI.py:15,17,47,51` points at FEWS geometry but uses `fid`, MEAN/STD. Its output filenames lack the consumed `_FEWSNET` suffix. A run manifest or paired keyed comparison remains necessary.
- FEWS FLDAS notebook cell 0:19–26 reads four mean/std partitions; cell 1:454–461 maps B12 to Rainf and B27 to Tair. The current `S/Step1_FEWNET_predictor/02_alternative_extract_FEWSNET.py:167,169` instead points at IPCCH geometry/admin_code. Neither the current script name nor the B-number rename proves the historical export band order.
- The notebook performs whole-column forward fill, zero fill and negative clipping (nightlight cell 0:109–113,1:2; EVI cell 1:75–95; GPP cell 1:268–278; FLDAS cell 1:180–198). These are legacy operations; preserve the approved same-area causal policy and distinguish intentional fill changes.
- Located historical output chain: combine notebook cell 1:465 writes `FEWSNET_IPC_assembled.csv`; `01_FEWSNET-final_process.ipynb` cell 14:2 writes `FEWESNET_final_v05022025.csv`; `02_add_FAO_prices_and_z_score_adjust_popdensity.ipynb` cell 0:7 reads it and cell 4:2 writes `FEWSNET_final_v06152025_with_zscores.csv`. No evidenced link yet to canonical `assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.csv` or its 2025–2026 updates.
- Scout inspected native FEWS DBF: 5,718 rows and explicit numeric `admin_code`, first values 0,1,2. This does not prove full FID identity. Repository `Outcome/fewsnet_partitioned_rf/MANIFEST.md:23` row count 1,121,120 conflicts with the normalization audit's 1,120,728 for the same listed hash; investigate rather than treating the Markdown count as acceptance.

## IPCCH-specific evidence

- `archive/legacy_final_harmonise/00_combine_all_ch.py:106,110–113` loads external `Outcome/ch_scaffold_fixed.csv` and creates `index` from the DataFrame row index. At :254,258–260 it renames both extraction `region_id` and that index to `admin_code`; :276 merges by lat/lon/year/month. This documents a historical operation, not a verified durable crosswalk.
- Git `fcaa877:FLDAS/02_alternative_extract_ch.py:167–169` and `fcaa877:VIIRS_nightlight/03_alternative_extract_nightlight_ch.py:15–17` use external `Outcome/ch_scaffold_fixed.shp` with `fid`. This differs from the current unified geometry. The matching old geometry/scaffold must be inspected before key equivalence can be accepted.
- The CH builder :906,912,918–922 creates missing IDs from coordinate groups plus max existing ID +100000. Current canonical identity must account for these generated keys.
- `archive/notebooks/Final_harmonise/00_combine_all_IPC.ipynb` cell 0:18,103–107 consumes `FEWSNET_predictors/old_methods/IPC_fldas_fewsnet_completed.csv`, drops lat/lon and joins `area_id,year,month`; its generation is still missing.
- `docs/04_output_inventory.md:51` identifies canonical IPCCH CSV as copied from `D/assembled_IPCCH/raw/IPCCH_2026_completed.csv`, hash `ae696087c3bbb280537ae269a05924133acdb51060d31290523404fa8a717673`; no canonical writer was found in the repository. The next useful evidence is external old geometries/scaffolds, canonical build records and keyed paired outputs.

## Disposition

T1 remains open, but FEWS and CH remote semantics are demonstrably not interchangeable. Continue independent CP1 contracts; do not implement a generic shared nightlight reducer or assume FID equals native ID. Future numerical/keyed verification should start from the concrete external intermediates above, preserving original artifacts.
