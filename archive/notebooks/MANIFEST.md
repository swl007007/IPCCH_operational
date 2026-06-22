# Archived Notebooks

These notebooks are retained as references after conversion or replacement by
operational `.py` scripts. For current handover operations, run only the
production paths listed in the tables below.

## Active Converted Workflows

These converted scripts remain the active handover paths for their source
families.

| Archived notebook | Production script | Coverage check |
| --- | --- | --- |
| `archive/notebooks/ACLED/00_add_ACLED_IPCCH.ipynb` | `ACLED/00_add_acled_features.py` | 2 notebook code cells / 2 script cell blocks. |
| `archive/notebooks/FAO_price/00_add_FAO_ipcch_update.ipynb` | `FAO_price/00_add_fao_price_features.py` | 3 notebook code cells / 3 script cell blocks. |
| `archive/notebooks/WB_indicator/00_add_WBG_ch.ipynb` | `WB_indicator/00_add_world_bank_features.py` | 32 notebook code cells / 32 script cell blocks. |
| `archive/notebooks/WFP_indicator/00_add_WFP_ch.ipynb` | `WFP_indicator/00_add_wfp_price_features.py` | 21 notebook code cells / 21 script cell blocks. |

## Legacy Final Harmonise References

The archived final harmonise notebooks document the old split CH/IPC workflow.
They are not the production path for the current unified IPCCH monthly model
input. Use `Final_harmonise/00_build_monthly_ipcch_base_input.py` for current
monthly assembly.

Converted split CH/IPC scripts are archived under
`archive/legacy_final_harmonise/` as compatibility references only:

| Archived notebook | Legacy script | Coverage check |
| --- | --- | --- |
| `archive/notebooks/Final_harmonise/00_combine_all_ch.ipynb` | `archive/legacy_final_harmonise/00_combine_all_ch.py` | 78 notebook code cells / 78 script cell blocks. |
| `archive/notebooks/Final_harmonise/00_combine_all_IPC.ipynb` | `archive/legacy_final_harmonise/00_combine_all_IPC.py` | 16 notebook code cells / 16 script cell blocks. |
| `archive/notebooks/Final_harmonise/01_CH_final_process.ipynb` | `archive/legacy_final_harmonise/01_CH_final_process.py` | 19 notebook code cells / 19 script cell blocks. |
| `archive/notebooks/Final_harmonise/01_IPC_final_process.ipynb` | `archive/legacy_final_harmonise/01_IPC_final_process.py` | 12 notebook code cells / 12 script cell blocks. |
