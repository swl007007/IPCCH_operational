# October cloud delivery — operator runbook

Monthly FEWSNET + IPCCH predictions at origin O for horizons 0/6/12 (O, O+6, O+12), from the six
accepted packages. Fixed variables/assets are reused as they are; remote-sensing features are
refreshed with the repository's extraction code; months after a source's latest observation are
filled from the same area's own past only (never future data) and every fill is recorded. No
source/provenance tracing is part of a run. No model training.

Deployed in project `manuel-remote-sensing`, region `us-central1` (task staging names below).

| Piece | Name |
|---|---|
| Image | `us-central1-docker.pkg.dev/manuel-remote-sensing/october-delivery/runtime@sha256:41944ea048c559190b6018f30ad52695cf9bedbb7d5695abef50b1348616d034` |
| Outputs bucket | `gs://manuel-remote-sensing-oct-delivery-debug` |
| Request bucket (trigger) | `gs://manuel-remote-sensing-oct-delivery-requests` |
| Preparation job | Cloud Run job `oct-prepare-plan` (submits the Cloud Batch extraction) |
| Delivery job | Cloud Run job `oct-delivery` (32Gi, 8 CPU, 4 h, max retries 0) |
| Trigger | Eventarc `oct-delivery-requests` -> Workflows `oct-delivery-trigger` (submit only) |
| Release namespace | `oct-staging` (pointer `oct-staging/current.json`) |

## 1. Prepare remote-sensing features (EVI, FLDAS, GOSIF, VIIRS)

1. Write `prepare_requests/<prepare_id>/prepare_request.json` (pinned full-roster assets
   `assets/full-20261008a/{fewsnet,ipcch}/{geometry.geojson,roster.csv,history/*.csv}`, cutoff,
   optional `refresh_from` per family) with the request maker used for October,
   `.trellis/tasks/10-07-october-cloud-delivery/research/cp3_evidence/cloud_final_replay/oct-make-request.py`:
   `python oct-make-request.py <prepare_id> gs://manuel-remote-sensing-oct-delivery-debug/assets/full-20261008a <cutoff_utc> '{"evi": "2025-10", "fldas": "2025-10", "viirs": "2025-10"}'`.
2. Run the planner with the request URI/generation (`python -m cloud.orchestrator.prepare plan --request-uri ...
   --request-generation ... --output-root gs://manuel-remote-sensing-oct-delivery-debug --deadline-utc <UTC>`),
   e.g. by updating the args of job `oct-prepare-plan` and executing it.
3. Wait for `prepared/<prepare_id>/prepare_status.json` with `"status": "succeeded"`. Earth Engine runs
   the exports one or two at a time (about 10-17 min each); the October window (33 exports) took ~5 h.
   Provider latest months are recorded in `prepared/<prepare_id>/prepared_manifest.json`.

## 2. Choose ACLED / WFP

Per family, independently:

- `keep`: use the values already in the pinned history panels. The request names a retained snapshot
  that must equal the exact projection of those panels (`delivery_job.retained_family_rows`; the
  request builder writes and uploads it).
- `refresh`: upload the raw ACLED / WFP export; it is converted once with the existing converters in
  `tools/refresh_h5_inputs.py`.

The request builder writes `keep` for both. To refresh a family, replace that family's entry in the
generated `run_manifest.json` before uploading it (pin the uploaded raw export by its object generation
and SHA-256; `converter_contract` is unchanged):

```json
"acled": {"action": "keep", "retained_snapshot": {"uri": "gs://…/retained_acled.csv", "generation": "…", "sha256": "…"},
          "converter_contract": {"version": "september-h5-raw-converter-v1", "sha256": "…"}}
```

becomes

```json
"acled": {"action": "refresh", "raw_upload": {"uri": "gs://manuel-remote-sensing-oct-delivery-debug/uploads/<file>.csv",
                                              "generation": "<object generation>", "sha256": "<sha256 of the bytes>"},
          "converter_contract": {"version": "september-h5-raw-converter-v1", "sha256": "…"}}
```

(`gcloud storage objects describe` or the Python client gives the generation; `sha256sum` the local file.)

## 3. Upload the run manifest (this starts scoring)

Build `run_manifest.json` with the request builder used for October
(`research/cp3_evidence/cloud_final_replay/oct-make-final-request.py`):

```bash
python oct-make-final-request.py <run_id> <image_uri@sha256> manuel-remote-sensing-oct-delivery-requests <prepare_id>
```

It pins every input by URI/generation/SHA-256 (packages, panels, references, prepared snapshot,
retained ACLED/WFP), refuses a preparation that did not succeed, and validates the request. It is the
frozen October example: packages, panels and references come from the pinned inputs manifest
`delivery-inputs/v3-20261008a/manifests/debug-smoke-20261008a.json#1791476078241656` (fixed assets reused as
they are); only the prepared snapshot, run ID and image change per run. It writes the request to
`/tmp/oct-request-<run_id>/run_manifest.json`; run it from the repository with the
`/tmp/ipcch-oct-cp2`-style environment (google-cloud-storage, pandas). Upload it
create-only to

```
gs://manuel-remote-sensing-oct-delivery-requests/requests/<run_id>/run_manifest.json
```

The upload event starts the delivery job. Only that exact path triggers work.

- Re-sending the same request (same generation) returns the original status; nothing is recomputed.
- Different content under the same `run_id` is refused; a retry always uses a new `run_id`.
- A preparation whose roster/geometry/extraction contract does not match the request is rejected
  before scoring.

## 4. Results

- Status: `gs://manuel-remote-sensing-oct-delivery-debug/runs/<run_id>/run_status.json`
  (`succeeded` / `failed` with the error; `release_conflict.json` if the pointer moved).
- CSV tables: `gs://manuel-remote-sensing-oct-delivery-debug/deliveries/<run_id>/scopes/{0m,6m,12m}/{fewsnet,ipcch}/`
  (`polygon_predictions.csv`, `country_predictions.csv`, `polygon_model_mapping.csv`,
  `polygon_confidence.csv` / `polygon_training_errors.csv`, `country_confidence.csv`; September headers).
- Shared references: `deliveries/<run_id>/{fewsnet,ipcch}/{polygons.geojson,country_population_reference.csv}`.
- Disclosures: `deliveries/<run_id>/reports/` — `feature_fill_audit.csv` (observed / carry_forward /
  no_eligible_history per area, feature and month), `diagnostic_availability.csv` (unsupported
  diagnostics are blank with a reason), `*_assembly.json` (provider vintages, FEWS scoring window,
  z-score disclosure).
- Portable bundle: `deliveries/<run_id>/webapp_model_bundle.tar.gz` + `manifest.json`.
- Release: `oct-staging/releases/<run_id>/release.json`; pointer `oct-staging/current.json` (moved
  last, by generation compare-and-swap).

Offline replay of a delivered bundle (no repository, no cloud credentials):

```bash
mkdir -p bundle && tar -xzf webapp_model_bundle.tar.gz -C bundle && cd bundle
python3.12 -m venv .venv && .venv/bin/pip install --no-deps -r requirements.txt
PYTHONPATH=runtime .venv/bin/python -m cloud.orchestrator.delivery_bundle rescore --root . --output rescored
```

October final run: `run_id` `oct-final-20261008a`, prepare `full-window-20261008c`, finished 2026-10-08
19:17 UTC; replay equal on all 30 tables.

## 5. Stopping work

`deploy/october_delivery/wind_down.py --backend rest --batch-jobs ... --run-executions ...
--prepare-ids ... --evidence-dir <dir> [--execute]` snapshots the listed task-owned Batch jobs,
Cloud Run executions and Earth Engine exports, and only with `--execute` stops non-terminal ones.

## Known limitations

- GOSIF (GPP mean/SD) is published only through 2024-12; later months are carried forward and disclosed.
- Historical error/confidence diagnostics are unavailable unless evidence for the exact package and
  horizon is supplied in the request; predictions are delivered regardless.
- The workflow's service account needs `roles/run.developer` on job `oct-delivery` (granted) and acts
  as the job's service account; the workflow submits only and does not wait for completion.
- `deploy_delivery.sh` documents the deployment; the October deployment above was applied in task staging only.
