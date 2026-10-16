# Existing price-catalog inputs for the deployment quote

Read-only scout plus supervisor spot checks, 2026-10-16. These are inputs to the executor's final quote, not provisioning acceptance. User supplied current-month target-project cost USD 0; Billing API visibility remains denied. No new API call occurred.

Let S = `/home/swl007007/projects/food-crisis-research/scratch/p3/skus`. Files are one-line JSON arrays; indexes below are zero-based. All listed effective times are `2026-10-15T07:00:00Z`, USD. Use tier unitPrice directly, not multiplied by displayQuantity. Free tiers can aggregate at billing-account level; do not assume availability from project cost zero.

| File[index] | SKU | Rate / unit |
|---|---|---|
| sql.json[3383] | 2A6B-45EC-D503, PostgreSQL zonal Small Americas | 0.035 / hour |
| sql.json[15396] | C18F-7FE0-0717, PostgreSQL zonal SSD Americas | 0.17 / GiB-month |
| sql.json[5732] | 46C8-DA82-DF18, backups Americas | 0.08 / GiB-month |
| sql.json[3944] | 3151-8F6A-75C1, IP reservation Americas | 0.01 / hour; applicability unverified |
| run.json[229] | 4856-B847-F1EB, request-based CPU | 0.000024 / second |
| run.json[8] | 02A2-9231-36A6, request-based memory | 0.0000025 / GiB-second |
| run.json[149] | 2DA5-55D3-E679, requests | first 2M zero, then 0.40 / million |
| run.json[646] | DDFD-AE42-E219, NA-to-NA internet | first 1 GiB zero, then 0.105 / GiB to 10,240 GiB |
| gcs.json[1124] | E5F0-6A5D-7BAD, regional standard | first 5 GiB-month zero, then 0.02 / GiB-month |
| gcs.json[392] | 4DBF-185F-A415, regional Class A | first 5,000 zero, then 0.005 / 1,000 |
| gcs.json[596] | 7870-010B-2763, regional Class B | first 50,000 zero, then 0.0004 / 1,000 |
| gcs.json[180] | 22EB-AAE8-FBCD, worldwide excluding Asia/Australia download | first 100 GiB zero, then 0.12 / GiB to 1,024 GiB |
| ar.json[14] | 8502-299A-ABAF, registry storage | first 0.5 GiB-month zero, then 0.10 / GiB-month |
| ar.json[1] | 108E-9EAE-92D9, NA-to-NA registry download | 0.105 / GiB to 10,240 GiB |
| secret.json[0] | 7756-ADEF-84F4, version replicas | first 6 replica-month zero, then 0.06 / replica-month |
| secret.json[1] | EBA7-264F-2D2C, accesses | first 10,000 zero, then 0.03 / 10,000 |
| build.json[249] | A464-9020-6404, e2-standard-2 build | first 2,500 min zero, then 0.006 / min |
| logging.json[0] | 143F-A1B0-E0BE, log storage | first 50 GiB zero, then 0.50 / GiB |
| logging.json[2] | F4AE-5A52-ACE3, retention | 0.01 / GiB-month |
| vertex.json[1576] | 2A57-4214-1832, N1 core Americas training | 0.03635265 / core-hour |
| vertex.json[8176] | DE93-D712-2AE4, N1 RAM Americas training | 0.00487255 / GiB-hour |
| vertex.json[6091] | A4CD-7C62-A250, N1 core Iowa management | 0.0047416 / core-hour |
| vertex.json[1603] | 2AFC-FA40-0543, N1 RAM Iowa management | 0.0006355 / GiB-hour |
| vertex.json[8339] | E320-80A9-21BD, training PD | 0.046 / GiB-month |
| vertex.json[9299] | FDAB-647C-5A22, Gemini 2.5 Flash GA text input | 0.30 / million tokens |
| vertex.json[6498] | AF56-1BF9-492A, Gemini 2.5 Flash GA text output | 2.50 / million tokens |
| vertex.json[6021], [7568] | A253-E8A3-DE5C, CD33-11F4-1220, GA output with thinking / thinking output | 2.50 / million tokens |

Supervisor independently checked catalog records for SQL instance/SSD/backups, Run CPU/memory/internet, GCS storage/download, all four N1 training/management rates and GA Gemini input/output. Other rows are bounded scout findings to recheck when using them in the final quote.

## Volume and path constraints

- Verified input inventory: 121 files / 14,870,642,554 bytes. Provisional FEWS cache weight volume: 59,880,198,540 bytes; historical artifacts: 1,321,950,132 bytes. Sum 70.8483 GiB before other packages, snapshots, deduplication, soft-delete and images. This is not final capacity.
- Tracking/auth rehearsal is approximately 0.197 GiB. Full research SQL import/index/WAL/temp use has not been measured. Original input bytes cannot establish that a 20 GiB SQL disk fits.
- GCS direct download, Cloud Run artifact-proxy internet traffic and local image pulls use distinct paths/SKUs. Quote the chosen actual path once, including in-region charges where applicable; do not grant all paths the GCS 100 GiB free tier.
- Model/version is not yet selected by these catalog findings. Non-GA Gemini entries have different prices; do not mix cheapest entries with the GA contract. Verify thinking/output limits and live usage before arming paid calls.
- N1 management/base-price stacking and any HPT-specific overhead need verification. No Hyperparameter-named SKU was found in this bounded catalog scan; that does not prove absence of charges.

## Illustrative envelope, not an approved quote

For a full 31-day month, using gross rates without free credits: SQL small 744h + 20GiB SSD + 20GiB backup = USD31.04; optional IP reservation allowance 7.44; Run 1CPU/2GiB active 10h + 100k requests = 1.084; GCS 120GiB = 2.40; AR10GiB = 1; 10 secret replicas +20k accesses = 0.66; build60min = 0.36; download200GiB conservatively at 0.12 =24; GCS10k A +100k B =0.09; Gemini1M input +1M total output =2.80; logging10GiB gross =5. Total **USD75.874**. It excludes a separately measured image-download allowance and is not a hard cap.

At 744 active hours the same Run CPU/memory alone is USD77.6736, making this illustrative platform total about USD152.50. Max one instance/min zero is not a spending cap. Final quote must bind realistic activity, downloads and continuing storage assumptions to monitoring/limits and contingency.

Training illustration: two serial 15-minute trials on assumed 4core/15GiB, counting both catalog base and management rates, totals USD0.123498875; assumed 100GiB PD for 0.5h adds about USD0.00309. Verify machine availability, charging rules, startup/termination overhead and actual runtime limits before reservation/submission.
