# IPC-CH Monthly Operational Handover Overview

This repository contains source-specific monthly data-preparation workflows for IPCCH modelling. The handover goal is to let a new operator produce a monthly model-compatible input table without relying on Weilun's local paths, personal Google account, or notebook-only execution knowledge.

The repository does not own the final prediction step yet. Weilun will export
the trained model weights and model pipeline separately; prediction will combine
those model artifacts with the monthly compatible input produced here.

## Workflow Families

| Workflow family | Current/proposed folders | Primary operator after handover | Output contract |
| --- | --- | --- | --- |
| Core identifiers and polygons | `polygons_and_identifier/` | Weilun provides; new operator consumes | Reference scaffolds and geometry files. |
| EVI | `EVI/` | New operator | Wide monthly CSVs keyed by ArcPy zone identifier. |
| FLDAS | `FLDAS/` | New operator | Wide monthly-band CSVs split by processing part. |
| GOSIF-GPP | `GOSIF_GPP/` | New operator | Wide monthly CSVs for mean and standard deviation. |
| VIIRS nightlight | `VIIRS_nightlight/` | New operator | Wide monthly CSVs for sum and standard deviation. |
| ACLED | `ACLED/` | New operator | IPC-CH scaffold plus conflict features. |
| FAO prices | `FAO_price/` | New operator with Soonho-supported exports when needed | IPC-CH scaffold plus FAO price features. |
| World Bank indicators | `WB_indicator/` | New operator | IPC-CH scaffold plus country-year indicator features. |
| WFP prices | `WFP_indicator/` | New operator | IPC-CH scaffold plus WFP price features. |
| IPC API | `curl_IPC/` | New operator | Per-year and combined IPC areas/analyses outputs. |
| Final harmonise / model input assembly | `Final_harmonise/` and unified IPCCH assets | New operator | Monthly model-compatible IPCCH input table. |

## Production Scaffold Rule

Production only needs one target-month scaffold. The current handover keeps a
multi-month reference scaffold for QA and rebuilding, but the monthly
production input should start from a one-month scaffold such as
`Outcome/ipcch_unified/interim/ipcch_scaffold_202604.csv`.

## Operator Rule

Run a workflow only after updating `config/paths.ini` and, for EE/GCS workflows, `config/ee_gcs.ini`. The `*_template.ini` files are examples; keep local filled configs out of shared code handover when they contain workstation-specific paths.
