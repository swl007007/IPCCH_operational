# D18/D20/D21 October confidence rerun: cloud action ledger

Project `manuel-remote-sensing` (us-central1), account `weilun.shi@cgiar.org`, gcloud 562.0.0. Raw snapshots,
build records and run records are in `research/oct-confidence-cloud/`. Request build records are in
`research/oct-confidence-request/`.

Outcome: run `oct-confidence-20261009b` **succeeded** on image `runtime:cp5-confidence-1`
@ `sha256:7e6133f32ab0b28d3f29b827d4153975e99f97d440e97a1a8cdacdfa1052f0d0`. Its predictions equal the earlier smoke
run `oct-final-20261008a`, and its confidence columns are populated. The first attempt
`oct-confidence-20261009a` failed only at the release-pointer precheck (section 4).

## 1. Read-only inventory before changes (2026-10-09 ~20:00 UTC)

- Cloud Run job `oct-delivery` (generation 2): image `runtime@sha256:41944ea048c559190b6018f30ad52695cf9bedbb7d5695abef50b1348616d034`
  (cp4-final-1), 8 CPU / 32Gi, timeout 14400 s, maxRetries 0, SA `oct-delivery-runner`. Default args include
  `--image-uri <old digest>` (`job-oct-delivery.before.json`).
- Workflow `oct-delivery-trigger` revision `000002-c39`, env `DELIVERY_IMAGE_URI` = old digest (`workflow.before.json`).
- Eventarc trigger `oct-delivery-requests` (bucket `manuel-remote-sensing-oct-delivery-requests`) -> that workflow.
- Release pointer `gs://manuel-remote-sensing-oct-delivery-debug/oct-staging/current.json#1791487045444241` -> `oct-final-20261008a`.

## 2. Actions (UTC, 2026-10-09)

| Time | Action | Identity |
|---|---|---|
| 20:02 | Clean build context from `deploy/build_context.sh` (`__pycache__` removed; 81 files, `build-context.sha256.txt`); lock `2f0a7251…1e3d` = baseline lock | local |
| 20:03:11 | Create-only upload of the build source | `gs://manuel-remote-sensing-oct-delivery-debug/build-sources/cp5-confidence-1.tgz#1791576191770816`, sha256 `019cfbe8…750a` |
| 20:03:48 | `gcloud builds submit gs://…#gen` rejected client-side; no build created | — |
| 20:04:26-20:08:50 | Cloud Build via REST, pinned source generation; `pip check` clean | build `febbd244-5504-40cf-9d41-5cab5198a347` -> `runtime:cp5-confidence-1` @ `sha256:7e6133f3…f0d0` |
| 20:10:57-20:11:27 | 20 kept October request refs checked (16 hash-verified, 4 > 200 MB existence-only); 16 create-only adjuncts uploaded | `staging/oct-confidence-20261009a/` (`environment.json`, 6 acceptance reports, 9 evidence CSVs; `request-build.json`) |
| 20:16:25 | D20: job `oct-delivery` image -> new digest (image only; generation 2->3) | `job-oct-delivery.after.json`, `config-change-diff.txt` |
| 20:17:05-20:17:28 | D20: workflow redeployed from the exact deployed source (identical; sha256 `e5f14a44…`), `--update-env-vars DELIVERY_IMAGE_URI=<new>`; revision `000002-c39` -> `000003-82d`; only that env var changed | `workflow.after.json`, `config-change-diff.txt` |
| 20:19:07 | Request a submitted create-only | `requests/oct-confidence-20261009a/run_manifest.json#1791577147621782`, sha256 `56171953…5c38` |
| 20:19:08 | Workflow execution `a04856c8-0e24-45a4-9e68-f590a3b4893c` (submit-only) -> Cloud Run `oct-delivery-zhztp` | argv carries the new `--image-uri` |
| 21:03:31 | zhztp exit 1: scored, packaged and uploaded (`deliveries/oct-confidence-20261009a/`), then `ReleaseConflict` at precheck; pointer untouched | `run_status.json` (failed), `release_conflict.json`, `job-execution-zhztp.json` |
| 21:17-21:30 | run-a outputs downloaded (hash-verified vs manifest); comparison passed (18/18 prediction tables, max diff 0.0); replay rehearsal passed | local `~/work/oct-confidence-20261009/run-a` |
| 21:34:20 | The single permitted retry: request b = request a with only `run_id`, `prepared_at` and `release.expected_pointer_generation=1791487045444241` changed (`oct_confidence_retry_request.py`) | `requests/oct-confidence-20261009b/run_manifest.json#1791581660462581`, sha256 `e2a7ce3d…8d4c` |
| 21:34:22 | Workflow execution `00be8973-0432-4e63-9177-b35deb6f14da` -> Cloud Run `oct-delivery-lmt6q` | — |
| 22:16:11 | lmt6q **succeeded** (41m32s); release record `oct-staging/releases/oct-confidence-20261009b/release.json#1791584165365909`; pointer `oct-staging/current.json` -> `#1791584165565011` (task staging namespace; no consumer cutover) | `run-b-status.json`, `run-b-execution.json`, `cloud_run_b.json` |
| 22:17-22:20 | Read-only download of run b (193 manifest members + manifest + bundle + fill audit, all sha256-verified) | `manifest.json#1791584105266047` (`265a0fb9…`), `webapp_model_bundle.tar.gz#1791584164926460` (`ac3bfcea…d4b9`) |

Request a vs October final: only `run_id`, `runtime`, the six `models[i].acceptance_report` refs, the 15 `diagnostics`,
`operator` and `prepared_at` changed. Request b vs a: only `run_id`, `prepared_at` and
`release.expected_pointer_generation`. Prepared snapshot `full-window-20261008c`, origin 2026-10, ACLED/WFP keep
snapshots, assets, package manifests and contracts are the October refs unchanged.

## 3. Local verification and replacement (Phase C)

- Relocated offline replay of the run-b bundle (`oct_confidence_replay.sh`, `/tmp/oct-confidence-replay-b`, frozen venv,
  `PYTHONPATH=runtime`, empty `CLOUDSDK_CONFIG`) passed: 194/194 members, rescore `all_equal` (30 tables + availability),
  42.5 s, 1.54 GB peak, `validate_delivery` passed.
- `october_confidence_check.json` passed for run b, and the run-a/run-b scope tables are byte-identical.
- Old fallback backed up create-only to `legacy_archive/IPCCH_monthly_operational/2026-10-09-october-smoke-pre-confidence/october_2026/`
  (50 files verified). New `cloud_pipeline/fallback/october_2026/` rebuilt (52 files, inventory verified; `build_october_fallback.json`).
- Baseline runtime rebound to the new image (`rebind_baseline_runtime.py`, `new-image-acceptance.json`). G4 passed at
  15/15 available, pytest 429 passed / 1 skipped, and archive `dist/cloud_pipeline-20261009b.tar.gz` was verified
  (`handover-archive-20261009b.json`).

## 4. Attempt a failure (diagnosed; one retry used)

The run-a request copied `release.expected_pointer_generation: "0"` from the October final request. October had
already created `oct-staging/current.json`, so `publish` recorded `release_conflict.json` at precheck and failed. That
happened after scoring and uploading, and before any release record or pointer write. Run-a outputs remain under
`deliveries/oct-confidence-20261009a/` and are byte-identical to run b's scope tables.

## 5. Live configuration left in place (no rollback, per D20)

- Job `oct-delivery`: image `sha256:7e6133f3…f0d0` (generation 3). Its default container args still include
  `--image-uri <old digest>`, because D20 authorized the image change only. The workflow overrides the entire argv on
  every event, so this matters only for a manual execution without overrides.
- Workflow `oct-delivery-trigger`: revision `000003-82d`, `DELIVERY_IMAGE_URI` = new digest.
- Rollback values: image `sha256:41944ea048c559190b6018f30ad52695cf9bedbb7d5695abef50b1348616d034`, workflow revision
  `000002-c39` (same source; env var old digest).

## 6. Task-owned cloud objects/resources created (none deleted)

Bucket `gs://manuel-remote-sensing-oct-delivery-debug` (object versioning on):
- `build-sources/cp5-confidence-1.tgz`
- `staging/oct-confidence-20261009a/` (16 objects; also referenced by run b)
- `deliveries/oct-confidence-20261009a/` (202 objects, 7.9 GB; failed-release attempt) and `deliveries/oct-confidence-20261009b/` (202 objects, 7.9 GB)
- `runs/oct-confidence-20261009a/{_RUN_ACQUIRED,run_status.json,release_conflict.json}`, `runs/oct-confidence-20261009b/{_RUN_ACQUIRED,run_status.json}`
- `oct-staging/releases/oct-confidence-20261009b/release.json`; new generation of `oct-staging/current.json` (the previous generation `1791487045444241` is retained as a noncurrent version)

Bucket `gs://manuel-remote-sensing-oct-delivery-requests`:
- `requests/oct-confidence-20261009a/run_manifest.json`, `requests/oct-confidence-20261009b/run_manifest.json`

Other:
- Artifact Registry `october-delivery/runtime:cp5-confidence-1` (in use by the job/workflow)
- Cloud Build `febbd244-5504-40cf-9d41-5cab5198a347` (logs in the default Cloud Build log bucket)
- Cloud Run executions `oct-delivery-zhztp` (failed), `oct-delivery-lmt6q` (succeeded)
- Workflow executions `a04856c8-0e24-45a4-9e68-f590a3b4893c`, `00be8973-0432-4e63-9177-b35deb6f14da`

Local scratch (outside the repo): `~/work/oct-confidence-20261009/`, `/tmp/oct-confidence-replay-{a,b}`.

## Local cleanup (2026-10-09, user-authorized)

Removed: superseded archives `dist/cloud_pipeline.tar.gz` and `dist/cloud_pipeline-20261009.tar.gz` (+ .sha256), workdirs `~/work/sept-6m12m-20261009` (incl. September 0m tables and feature-fill audits; hashes remain in `september_manual/scopes/inventory.json`) and `~/work/oct-confidence-20261009`, `/tmp/{sept_bundle,ipcch-sept-test,oct-confidence-replay-a,oct-confidence-replay-b}`, `__pycache__`/`.ruff_cache`.
Kept: `september_manual/`, `cloud_pipeline/{bootstrap,fallback}`, `dist/cloud_pipeline-20261009b.tar.gz` (checksum re-verified OK before deletion of the others), external `legacy_archive/` recovery copies.
Cloud objects listed in section 4 were not deleted.
