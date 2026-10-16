| Pool | Item | SKU | Qty | USD | One-time | Basis |
|---|---|---|---|---|---|---|
| platform | Cloud SQL db-g1-small instance, 744 h | 2A6B-45EC-D503 | 744 | 26.0400 |  | always on, full month |
| platform | Cloud SQL SSD 30 GiB | C18F-7FE0-0717 | 30 | 5.1000 |  | measured 10.98 GiB data + WAL/temp allowances 13.65 GiB; 30 GiB leaves ~16 GiB headroom |
| platform | Cloud SQL backups 30 GiB-month | 46C8-DA82-DF18 | 30 | 2.4000 |  | automated daily backups, 7 retained, point-in-time recovery (WAL archiving) OFF; one full (~11 GiB measured data) + incrementals of a mostly static research DB, reserved at ~2.7x measured data; reconcile with billed usage |
| platform | Cloud SQL public IPv4 reservation, 744 h | 3151-8F6A-75C1 | 744 | 7.4400 |  | included conservatively; applicability to an attached instance IP unverified |
| platform | Cloud SQL internet egress, input-import verification readback 16 GiB | 238B-D94B-7243 | 16 | 3.0400 | yes | one-time: the research-input import's every-cell COPY TO readback through the Auth Proxy to the workstation (~12.8 GiB CSV-equivalent + geometry/catalog reads); added before the import ran |
| platform | Cloud Run CPU, 60 active h x 1 vCPU | 4856-B847-F1EB | 216000 | 5.1840 |  | research use estimate |
| platform | Cloud Run memory, 60 active h x 2 GiB | 02A2-9231-36A6 | 432000 | 1.0800 |  | research use estimate |
| platform | Cloud Run requests, 0.1 M | 2DA5-55D3-E679 | 100000 | 0.0400 |  | gross (first 2 M are free tier) |
| platform | Cloud Run internet egress 20 GiB | DDFD-AE42-E219 | 20 | 2.1000 |  | recurring workload allowance: MLflow UI/API and proxied artifact/package downloads to the workstation |
| platform | GCS standard storage 109 GiB-month | E5F0-6A5D-7BAD | 109 | 2.1800 |  | measured 98.8 GiB (FEWS roots, inputs, MLflow artifacts, packages, snapshots) + 10% soft-delete/growth |
| platform | GCS Class A, initial upload 170k objects | 4DBF-185F-A415 | 170000 | 0.8500 | yes | operations; month 1 only |
| platform | GCS Class A, monthly 10k | 4DBF-185F-A415 | 10000 | 0.0500 |  | operations |
| platform | GCS Class B, monthly 100k | 7870-010B-2763 | 100000 | 0.0400 |  | operations |
| platform | GCS direct download, scen archive acceptance 43 GiB | 22EB-AAE8-FBCD | 43 | 5.1600 | yes | one-time: every extant scen-b43ef6a-v1 material (42.23 GiB; the exception's source archive), authorized direct GCS download; no other root is re-downloaded |
| platform | Cloud Run egress, package acceptance via MLflow SDK 12 GiB | DDFD-AE42-E219 | 12 | 1.2600 | yes | one-time: all retained packages (11.72 GiB) downloaded with authenticated MLflow SDK calls through the service's artifact proxy (the intended user path, incl. the largest-package service check) |
| platform | Cloud Run CPU, package acceptance streaming 2 h | 4856-B847-F1EB | 7200 | 0.1728 | yes | one-time: proxy time to stream the package acceptance volume (conservative) |
| platform | Cloud Run memory, package acceptance streaming 2 h x 2 GiB | 02A2-9231-36A6 | 14400 | 0.0360 | yes | one-time, as above |
| platform | Artifact Registry pulls to the workstation 11 GiB | 108E-9EAE-92D9 | 11 | 1.1550 | yes | one-time crane pulls of the 5 images (digest verification; historical replay acceptance on the workstation): measured unpacked envs 5.54 GB + base layers, x2 for one rebuild |
| platform | Artifact Registry storage 11 GiB-month | 8502-299A-ABAF | 11 | 1.1000 |  | 5 images: service + 2 training + 2 historical replay (measured unpacked envs 5.54 GB: 0.63 + 1.70 + 1.21 + 0.99 + 1.00), up to 2 retained digests each; Cloud Run/Vertex pulls are in-region |
| platform | Cloud Build e2-standard-2, 120 min | A464-9020-6404 | 120 | 0.7200 |  | 5 images x ~12 min x 2 builds; source contexts total ~4.5 MB (0.004 GiB) staged in the build source bucket, deleted after the build (negligible storage) |
| platform | Secret Manager, 16 active versions (replica-months) | 7756-ADEF-84F4 | 16 | 0.9600 |  | actual versions created: 13 initial (Flask secret, KEK, DB and identity credentials), 2 corrected MLflow URI versions (version 1 kept), 1 temporary migration admin; all assumed retained the full month; user-managed us-central1 replication |
| platform | Secret Manager accesses 20k | EBA7-264F-2D2C | 20000 | 0.0600 |  | accesses |
| platform | Logging ingestion 10 GiB | 143F-A1B0-E0BE | 10 | 5.0000 |  | gross (first 50 GiB free tier) |
| platform | Logging retention 10 GiB-month | F4AE-5A52-ACE3 | 10 | 0.1000 |  | beyond default retention |
| platform | Gemini 3.8 Flash (global) assistant, guard allocation | in/out | None | 10.0000 |  | the guard admits requests only within its USD 10 monthly allocation, reserving input + 2x max output at gross list prices (output includes reasoning); promotional credits not assumed |
| platform | Contingency | - | None | 10.0000 |  | unmetered allowances (network between services, retries, measurement error) |
| training | FEWS feature snapshot (fews_features), 1 job | n1-standard-4 |  | 0.1499 | yes | reservation held until provider terminal status; disableRetries; 600 s declared startup/termination overhead (not a provider bound); no separate management line (on-demand price) |
| training | IPCCH feature snapshot (ipcch_features), 1 job | n1-highmem-4 |  | 0.1856 | yes | reservation held until provider terminal status; disableRetries; 600 s declared startup/termination overhead (not a provider bound); no separate management line (on-demand price) |
| training | FEWS single trial (fews_fourclass), 1 job | n1-standard-4 |  | 0.0937 | yes | reservation held until provider terminal status; disableRetries; 600 s declared startup/termination overhead (not a provider bound); no separate management line (on-demand price) |
| training | IPCCH single trial (ipcch_quartet), 1 job | n1-highmem-4 |  | 0.1160 | yes | reservation held until provider terminal status; disableRetries; 600 s declared startup/termination overhead (not a provider bound); no separate management line (on-demand price) |
| training | HPT smoke: 2 serial trials (ipcch_quartet), parallel 1 | n1-highmem-4 |  | 0.2320 | yes | reservation held until provider terminal status; disableRetries; 600 s declared startup/termination overhead (not a provider bound); no separate management line (on-demand price) |
