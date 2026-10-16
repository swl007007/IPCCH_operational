# Itemized deployment quote (native `research_cloud/cost/quote.py`, 6d4a9b6; supersedes `quote-3aec3ab`)

Inputs:
- prices: the saved Cloud Billing catalog (`scratch/p3/skus`, effective 2026-10-15T07:00:00Z); every SKU id is verified against its saved record;
- volumes: measured;
- training: reservations from `cost/ledger.py`.

Prices are gross: free tiers and promotional credits are not subtracted. This is not a spending cap.

| Pool | Monthly | One-time | First month | Envelope |
|---|---|---|---|---|
| platform | USD 78.67 | USD 8.32 | USD 86.99 | USD 100 |
| training | — | USD 0.78 (reservations) | USD 0.78 | USD 100 |

## Platform (us-central1; Gemini on the global endpoint)

- **Cloud SQL:** Enterprise, PostgreSQL 16, zonal db-g1-small. Total USD 40.98:
  - instance, 744 h: 26.04;
  - 30 GiB SSD: 5.10 (sizing in `p2-sql-postgis-f93bfa1`);
  - backups, 30 GiB-month: 2.40;
  - public IPv4, 744 h: 7.44 (applicability unverified, so included).
- **Cloud Run MLflow service:** min 0 / max 1 instance, 1 vCPU / 2 GiB, 60 active hours. CPU 5.18, memory 1.08, requests 0.04, internet egress 20 GiB 2.10.
- **GCS:** 109 GiB-month = measured 98.8 GiB + 10% soft-delete/growth allowance; 2.18. The measured volume:

  | Component | GB |
  |---|---|
  | FEWS roots | 76.95 |
  | Inputs | 14.87 |
  | MLflow artifacts | 1.32 |
  | Packages | 12.58 |
  | Snapshots | 0.37 |

  Class A/B operations 0.09 monthly.
- **One-time acceptance network** (one path each, no double count):
  - every extant scen-b43ef6a-v1 material, 43 GiB by authorized direct GCS: 5.16;
  - all retained packages, 12 GiB through authenticated MLflow SDK downloads via the service proxy (the intended user path, including the largest-package check): egress 1.26 plus streaming CPU/memory 0.21;
  - workstation `crane` pulls of the 3 images as Artifact Registry internet egress (SKU 108E-9EAE-92D9), 8 GiB: 0.84;
  - initial GCS Class A uploads: 0.85.
- **Recurring proxy downloads, 20 GiB (2.10):** a workload allowance, separate from acceptance.
- **SQL backups:** automated daily, 7 retained, point-in-time recovery off; reserved at about 2.7x measured data and reconciled with billed usage.
- **Build-context staging:** about 4.5 MB, deleted after the build; negligible.
- **Artifact Registry:** 9 GiB-month 0.90. **Cloud Build:** 60 min 0.36. **Secret Manager:** 0.66. **Logging:** 5.10.
- **Gemini 3.8 Flash:** USD 10, the guard's hard monthly admission allocation at gross list prices of 1.50 / 7.50 per M tokens (output includes reasoning).
- **Contingency:** USD 10.

## Training (one-time reservations)

Each reservation is per-trial timeout plus a declared 600 s overhead, billed in 30 s increments, with a 100 GiB boot disk. Rates:
- n1-standard-4: 0.21849885/h;
- n1-highmem-4: 0.2720969/h (4 N1 cores + 26 GiB RAM);
- no separate management line, per `vertex-training-cost-supervisor.md`.

Jobs:
- FEWS feature snapshot: 0.150;
- IPCCH feature snapshot (highmem): 0.186;
- FEWS trial: 0.094;
- IPCCH trial: 0.116;
- two-trial HPT smoke: 0.232.

Every job is admitted through the ledger before submission. Its reservation is held until the provider reports a terminal status, with `disableRetries` set.
