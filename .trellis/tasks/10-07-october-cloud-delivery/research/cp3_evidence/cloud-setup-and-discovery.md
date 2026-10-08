# CP3 cloud setup and live provider discovery (executor evidence)

Executor `wR:p3`, 2026-10-08 ~12:00-12:20 UTC. SDK: `gcloud` 562.0.0; project `manuel-remote-sensing` (number 645415198431); account `weilun.shi@cgiar.org`; default region `us-central1`.

## Pre-existing resources (read-only inventory before any write; all left untouched)

- Buckets: `manuel-remote-sensing-gate-b1-20260722-50e14b48` (US), `manuel-remote-sensing-rasters-645415198431` (US, versioning off).
- Service accounts: only `645415198431-compute@developer.gserviceaccount.com`.
- Artifact Registry repositories, Cloud Run jobs, Batch jobs (us-central1), Workflows (us-central1), Eventarc triggers (us-central1): none.

## Task-scoped resources created (debug namespace)

| Resource | Identity | Settings |
|---|---|---|
| Bucket | `gs://manuel-remote-sensing-oct-delivery-debug` | US-CENTRAL1, uniform bucket-level access, public access prevention, object versioning ON (old generations stay readable for pinned reads), labels task=october-cloud-delivery,purpose=debug |
| Artifact Registry | `us-central1/october-delivery` (docker) | label task=october-cloud-delivery |
| Service account | `oct-delivery-runner@manuel-remote-sensing.iam.gserviceaccount.com` | runner for Cloud Run plan / Batch extract |

IAM granted to the runner SA (task-scoped; nothing removed):
- bucket `manuel-remote-sensing-oct-delivery-debug`: `roles/storage.objectAdmin`
- repository `october-delivery`: `roles/artifactregistry.reader`
- project: `roles/earthengine.writer`, `roles/serviceusage.serviceUsageConsumer`, `roles/batch.jobsEditor`, `roles/batch.agentReporter`, `roles/logging.logWriter`
- on itself: `roles/iam.serviceAccountUser` (submit a Batch job that runs as itself)

## Live read-only provider discovery (user credentials, earthengine-api 1.7.36)

| Family | Query | Latest published month | Exact identity |
|---|---|---|---|
| EVI | `MODIS/061/MOD13A3` time_start/system:id | 2026-08 | `MODIS/061/MOD13A3/2026_08_01` |
| FLDAS | `NASA/FLDAS/NOAH01/C/GL/M/V001` | 2026-08 | `NASA/FLDAS/NOAH01/C/GL/M/V001/202608`; 28 band names equal `FLDAS_BANDS` as a set (provider order differs; selection is by name) |
| VIIRS | `NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG` | 2026-08 | `NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG/20260801` |
| GOSIF Mean/SD | HTTP HEAD (http -> 301 -> https) | **2024-12** | `.../Monthly/Mean/GOSIF_GPP_2024.M12_Mean.tif.gz` 200; every 2025-01..2026-09 Mean and SD -> 404; directory listing ends at 2024.M12 |

GOSIF disposition (supervisor, 2026-10-08): not CRITICAL; user approved no age cap. Record provider latest 2024-12 and ~22 months staleness for O=2026-10. Freshness boundary: baseline rows after the provider vintage (e.g. forward-filled panel values) are not observations; preparation re-fetches the provider latest month, excludes later history rows from the baseline and records them as `history_beyond_provider_vintage_excluded` (implemented in `cloud/orchestrator/prepare.py`, tested).

## Image build

- Cloud Build (us-central1) from a 1.7 MB staged context (`deploy/october_delivery/build_context.sh`): SUCCESS in 3m05s, `pip check` clean.
- `us-central1-docker.pkg.dev/manuel-remote-sensing/october-delivery/runtime:cp3-smoke-1` @ `sha256:c1cf7a10ca63eba154d49a066f8dce6cdae74738626a5e03264329d66a2f805b`.
- Lock: `deploy/october_delivery/requirements.lock.txt`. Numerical pins equal the frozen venv; shapely is pinned to 2.1.2. Python image 3.12.3-slim.
- This image predates the provider-inception, value-bearing-exclusion and CRS-rejection fixes; it is superseded before the Cloud Run → Batch smoke.

## Bounded live local-process smoke `smoke-local-20261008a` (in progress)

- Harness: `research/cp3_evidence/smoke_prepare_local.py`. Production `CloudSourceAcquirer` / `GCSObjectStore` / `GcsPinnedReader`, user credentials (ADC + Earth Engine), plan and extract in one local process.
- Inputs:
  - Assets `gs://manuel-remote-sensing-oct-delivery-debug/assets/smoke-20261008a/`: 12 polygons per system, histories from the accepted September panels through 2026-04.
  - origin 2026-10, cutoff `2026-06-05T00:00:00Z`, so the eligibility limit is 2026-05.
- Request `prepare_requests/smoke-local-20261008a/prepare_request.json#1791461755634045`, sha256 `bb9e4c53c64ea1c0f0301902a295b6d5d4287e23820b4ce51922f5a893f786e5`.
- Plan, written 12:15:56–12:16:02 UTC with both sentinels:
  - EVI `MODIS/061/MOD13A3/2026_05_01`
  - FLDAS `NASA/FLDAS/NOAH01/C/GL/M/V001/202605`
  - VIIRS `NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG/20260501`
  - GOSIF Mean/SD 2024-12 (re-fetch of the provider latest)
  - `history_beyond_provider_vintage` for GOSIF listed 16 empty months. The plan predates the value-bearing-only refinement.
- 12:23 UTC: Earth Engine task `ZB3Q6O5JGUCI6PPGP4KEPTEC` (`smoke_local_20261008a_evi_2026_05`) is RUNNING, 7.8 min since creation, last update 0.1 min ago. The local process is alive, waiting on the export poll (20 s interval).

## Finding: April 2026 remote values in the accepted September panels are all zero

Share of zeros/NaN by month in the accepted v3 input panels (`inputs/fewsnet_panel.csv`, `inputs/ipcch_panel.csv`). Read-only query over the full panels; values are fractions of areas.

| month | FEWS EVI=0 | FEWS nightlight=0 | IPCCH EVI_mean=0 | IPCCH nightlight_mean=0 |
|---|---|---|---|---|
| 2025-09..2026-03 | 0.005-0.013 | 0.017-0.020 | ~0.318 | ~0.40 |
| 2026-04 | **1.000** | **1.000** | **1.000** | **1.000** |

- FLDAS Rainf has no NaN.
- GPP is NaN in every month since 2025-01, consistent with the provider vintage 2024-12.
- The provider has published 2026-04 for EVI/FLDAS/VIIRS, so the April zeros are not provider observations.
- They feed FEWS `EVI_l6` (O=2026-10), the `nightlight_m12` window and IPCCH carry-forward only if no later month exists. Later prepared months supersede them for IPCCH.
- Smoke extraction of `MODIS/061/MOD13A3/2026_05_01` with the current script reducers gives normal values, e.g. FEWS area 0 mean 2289 (raw scaled), IPCCH area 0 mean 2424.

## Local live smoke `smoke-local-20261008a` (completed)

- Exit 0, wall 19:15.22, peak RSS 464,596 KiB.
- Status `succeeded` written 2026-10-08T12:34:59Z.
- Earth Engine tasks:
  - `ZB3Q6O5JGUCI6PPGP4KEPTEC` (EVI 2026-05): COMPLETED in 8.2 min.
  - `2BU27KKK4O4JXBXZZZHX6BZT` (FLDAS): COMPLETED in 3.8 min.
  - `BUTIY545KSEUM5TK7Z2YRA2T` (VIIRS): COMPLETED.
- Source objects:

| Source | Bytes | sha256 |
|---|---|---|
| `evi_2026-05.tif` | 278,550,579 | `ab98da52…` |
| `fldas_2026-05.tif` | 185,986,255 | `31946e65…`; band names from `raster_band_descriptions` |
| `viirs_2026-05.tif` | 81,504,928 | `5b85e673…` |
| `GOSIF_GPP_2024.M12_Mean.tif.gz` | 7,666,532 | `10a0bd08…` |
| `GOSIF_GPP_2024.M12_SD.tif.gz` | 7,454,668 | `a4ef4afe…` |

- All exports came back as single objects (no shards).
- Full-roster zonal throughput, measured locally on these rasters with 600 of the 6,227 IPCCH polygons and extrapolated: EVI ~12 s, VIIRS ~5 s, FLDAS ~9 s per raster; peak RSS 1.1 GB.

## Cloud Run → Batch smoke `smoke-cloud-20261008a` (ACCEPTED as bounded numerical smoke by supervisor)

- Image `us-central1-docker.pkg.dev/manuel-remote-sensing/october-delivery/runtime:cp3-smoke-3` @ `sha256:73fe81a66dd5b6b5582a0b1fdfe1c8308eb8bba117e3330afbf4db35722a19bf`.
- Request `prepare_requests/smoke-cloud-20261008a/prepare_request.json#1791463519483671`, sha256 `7ade2921035715e2ea903188dad83f73cea4d4817d5b92c7266ac2eb892cb302`.
- Cloud Run job `oct-prepare-plan` (us-central1, SA `oct-delivery-runner`, 2Gi/1 CPU, no retries):
  - Execution `oct-prepare-plan-cjbbj` succeeded and wrote `prepare_plan.json#1791463775058992` (sha256 `eb4b848e…`).
- The plan's own Batch submission `ipcch-prepare-smoke-cloud-20261008a` was created by the runner SA and went QUEUED → FAILED within 1 s, with no status detail and no logs.
  - Diagnosis: a trivial probe job `oct-batch-probe-1` with the same SA, submitted by the user account, SUCCEEDED. The identical extract spec resubmitted by the user account as `oct-extract-smoke-cloud-1` SUCCEEDED.
  - So SA-as-submitter is the remaining defect. Root cause not yet identified; this is open deployment evidence.
  - `plan_and_submit` records submit exceptions only, not asynchronous QUEUED→FAILED.
- Batch `oct-extract-smoke-cloud-1` (e2-highcpu-2 class, Batch default 2 CPU / 2000 MiB):
  - SCHEDULED 12:53, RUNNING 12:57, SUCCEEDED by 13:13:49.
  - Status `succeeded` written 13:13:22Z; no cancelled tasks.
  - Earth Engine task IDs are persisted under `provider_tasks/`.
- Parity, `research/cp3_evidence/smoke_cloud_vs_local.json` (`compare_smokes.py`), 9/9 system-family pairs:
  - provider IDs and source sha256 equal;
  - keys, columns and nulls equal; max abs diff 0.0;
  - FLDAS band identity from raster descriptions in both runs;
  - EVI/FLDAS GeoTIFFs byte-identical (equal size and MD5).

## Wind-down and authority expiry (2026-10-08)

- Read-only `wind_down.py` snapshots at 13:56:30, 13:58:29 and 14:07:07 UTC. Evidence (full raw JSON, create-only) is in `wind_down/`. `--execute` was never run.
- Final recorded state (14:07 snapshot; EE task rechecked 14:09):
  - Batch: `ipcch-prepare-full-window-20261008a` FAILED (exit 50002, e2-highcpu-2). `ipcch-prepare-full-window-20261008b` FAILED after its own deadline self-cancellation (status `failed`/`source_retrieval_failed` written 14:05:29.833Z; 31 cancellation requests; sources `evi_2025-10` and `evi_2025-11` retained).
  - Cloud Run: executions `oct-prepare-plan-vz2dq` and `oct-prepare-plan-zgclz` TERMINAL.
  - Earth Engine, all four prepare IDs: 30 CANCELLED, 8 COMPLETED, 1 CANCEL_REQUESTED, `KHVQOANYHBXYMPAUFTDIVBOP` (EVI 2025-12; cancellation already requested by the acquirer). The supervisor is tracking this task.
  - There was no active Batch or Run compute. No scoring job was ever launched. All written objects are kept.
- The scheduled 14:20 cleanup reminder fired at 14:33 UTC, after authority expired at 14:30. Per the no-new-cloud-actions rule, nothing was run then; the executor made no cloud calls after 14:19:27 UTC. That last call cached the pinned `smoke-local-20261008a` prepared objects to local disk.
- Re-checking the terminal state of `KHVQOANYHBXYMPAUFTDIVBOP` requires renewed authority.
