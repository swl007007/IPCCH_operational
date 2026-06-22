# Environment Setup

## Windows and ArcPy

Raster extraction and mosaicking scripts must run in the Windows ArcGIS Python environment that provides `arcpy` and Spatial Analyst.

Before running ArcPy scripts:

1. Confirm ArcGIS/ArcPy opens on Windows.
2. Confirm Spatial Analyst is licensed.
3. Confirm the operator can read local raster folders and write output CSV folders.
4. Confirm `config/paths.ini` exists and points to local data.

ArcPy-facing scripts preserve Python 2.x-compatible syntax. Do not add f-strings, `pathlib`, type annotations, or Python 3-only imports to those scripts.

## General Python

Non-ArcPy scripts use standard Python plus source-specific packages such as `pandas`, `numpy`, `requests`, `pycountry`, `polars`, `geopandas`, and `openpyxl`.

Recommended syntax-only check from WSL:

This is the intended post-refactor check after config templates, the validation utility, and the renamed IPC API script exist.

```bash
python3 -m py_compile workflow_config.py tools/validate_csv_contract.py curl_IPC/00_download_ipc_api.py
```

## Google Cloud SDK

Install Google Cloud SDK on the operator's Windows machine. Confirm these commands work after account setup:

```powershell
gcloud auth login
gsutil ls gs://operator-bucket-name
```
