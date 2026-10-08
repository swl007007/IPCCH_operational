# /tmp ledger (repo PROGRESS.md unreadable since ~16:45 UTC 2026-10-08: Dropbox folder on /mnt/c returns EIO)

- 16:37 UTC: host memory spike (swap full) -> gcloud ENOMEM; then the 9p mount returned I/O errors:
  Cloud SDK (Program Files (x86)) at ~16:38, cp3_evidence at ~16:43, then the whole repo (PROGRESS.md, cloud/*.py) by ~16:47.
  Non-Dropbox Windows paths still read. Not stopped/killed anything.
- Cleanup tool: /tmp/oct-wind-down.py (exact copy of repo wind_down.py incl. REST backend);
  evidence /tmp/oct-wind-down-evidence; selectors /tmp/oct-cleanup-selectors.txt.
  Crons: f17f58ec (20:45 UTC), 0e1552df (20:57 UTC).
- 16:42:55 report-only (REST): Batch c RUNNING; oct-prepare-plan-8bv78 TERMINAL; oct-deliver-debug-xfr48 RUNNING;
  EE c: 7 COMPLETED / 2 RUNNING / 24 READY.
- Staging deployed (16:3x): image cp4-staging-1 sha256:cdeb0f429d0fde32ae5789f0b6e8545b0ae1c6a8663843485f54f9046fa7c5f7;
  request bucket gs://manuel-remote-sensing-oct-delivery-requests; job oct-delivery (32Gi/8cpu/4h/max-retries 0);
  workflow oct-delivery-trigger rev 000001-bfd; Eventarc trigger oct-delivery-requests (create op started 16:41:34 via REST);
  compile-check workflow oct-delivery-trigger-check (executions cb6cb66a ignored, eeab386a IAM-denied).
  IAM: runner objectViewer(request bucket), eventarc agent legacyBucketReader(request bucket), GCS agent pubsub.publisher,
  runner eventarc.eventReceiver + workflows.invoker (project), runner serviceAccountUser(self), runner run.developer(job oct-delivery).
  NO staging request uploaded (builder needs repo code; blocked by EIO).
- 16:47 mount recovered intermittently (still flapping). Staging request built from the exact cp4-staging-1 build context
  (/tmp/october-delivery-ctx.MdZozs, hashes == /tmp/oct-build-7.context-sha.txt) with pinned GCS inputs.
- 16:49:28 UTC staging request uploaded create-only: gs://manuel-remote-sensing-oct-delivery-requests/requests/oct-staging-20261008a/run_manifest.json#1791478168059910
  sha256 fddaa7a13e2e352519f334919304c9d99a6bcbacc4cd90f334328178de227a84 (prepared = bounded smoke-local; expect roster rejection).
- Eventarc fired -> workflow execution db897c42-b1fa-42d4-a15d-00c0cfc3c6bf -> Cloud Run execution oct-delivery-2ll5p (created 16:49:29,
  started 16:50:33) with full argv (request uri/generation + configured output root/namespace/image). Workflow then FAILED at
  LRO polling: 403 run.operations.get (project-level permission not covered by job-scoped run.developer) -> monitoring gap, not job failure.
- CLEANUP SELECTORS now: Batch ipcch-prepare-full-window-20261008c; executions oct-prepare-plan-8bv78, oct-deliver-debug-xfr48,
  oct-delivery-2ll5p; prepare-id full-window-20261008c.
- 16:56:56 staging oct-delivery-2ll5p: readiness REJECTED as designed (AcceptanceError fewsnet prepared roster != delivery roster),
  but its run_status write then failed: GCS 503 beyond the 120 s retry deadline -> no status object.
- 17:06:27 debug oct-deliver-debug-xfr48 scored, then upload_tree hit the same GCS 503/120 s timeout after 5 objects -> outputs lost (in-memory FS).
- Fix (patch /tmp/oct-upload-retry.patch, apply to repo when the mount recovers): create-only uploads timeout=600 +
  retry deadline 1800 s; delivery uploads accept a retried create only when CRC32C of the existing object equals the local file;
  status/sentinel writes only get the longer timeout/retry (no content acceptance -> duplicate detection unchanged).
- gcloud SDK unusable (EIO) -> Cloud Build via REST: build 4df94aa8-0594-44e4-9bbb-da5d48f0b7a4, source
  gs://manuel-remote-sensing-oct-delivery-debug/build-sources/cp4-debug-2.tgz#1791480908588129,
  image cp4-debug-2 sha256:f7d5e8cbb297ef373ebfe05a475bf8221c62d31f18d2f650de80b804740d6cc0 (context hashes /tmp/oct-build-8.context-sha.txt).
- Debug rerun: job oct-deliver-debug patched to that digest, run-name smoke-20261008a-2 -> execution oct-deliver-debug-nwvkk.
- 18:15-18:25 pending changes frozen in Linux snapshot /tmp/oct-test-ctx (base = cp4-debug-2 context + edits). Focused tests there:
  test_delivery_job/test_object_store/test_deliver_job/test_delivery_manifest 81 passed exit0 (--basetemp=/tmp/oct-pytest-base);
  test_delivery_workflow 1 passed (system python3, yaml). Hashes: cloud/orchestrator/delivery_job.py=7f47c4e5302f cloud/common/object_store.py=2ecfd077a220 deploy/october_delivery/workflow.yaml=e5f14a4407ea tests/cloud/test_delivery_job.py=53a8252d3d34 tests/cloud/test_object_store.py=9c3614a25b11 tests/cloud/test_delivery_workflow.py=eafc91217ff3
  Repo reconciliation: copy these 6 files from /tmp/oct-test-ctx when the mount is stable (repo already has delivery_job/object_store/workflow/
  test_delivery_workflow edits; test_object_store.py in repo has a stray assertion in the local-store test -> take snapshot version).
  Repo test loops against /mnt/c were host I/O failures (OSError), not code results.
- 18:2x final image cp4-final-1 sha256:41944ea048c559190b6018f30ad52695cf9bedbb7d5695abef50b1348616d034 (Cloud Build c4b97e9f-61dd-412f-a94a-307effe9f066,
  source build-sources/cp4-final-1.tgz#1791483544025261, context = /tmp/oct-test-ctx minus tests, hashes /tmp/oct-build-final.context-sha.txt).
  Job oct-delivery -> that digest (maxRetries 0); workflow oct-delivery-trigger rev 000002-c39 with skip_polling + DELIVERY_IMAGE_URI = that digest.
  Final request builder /tmp/oct-make-final-request.py (submit when prepared/full-window-20261008c status == succeeded).
- 18:24:02 DEBUG cloud run oct-deliver-debug-nwvkk SUCCEEDED (image cp4-debug-2): deliveries/debug-smoke-20261008a-2/ 228 objects, 30 scope tables,
  archive; packaging validation passed. Bounded smoke debug evidence, NOT the final full remote delivery.
- IPCCH local/cloud parity: all 15 cloud IPCCH scope tables byte-identical to local run i (/tmp/oct-ipcch-parity-debug2-vs-i.json).
- Offline relocated replay (/tmp/oct-replay-cloud.sh; raw log /tmp/oct-replay-cloud-debug2.log; results /tmp/oct-cloud-debug-smoke-20261008a-2/):
  manifest#1791483766705187 sha256 2d7651864e7d5d42ef664342c9a6ec465149c8c2c8eace99c6f903ef56a7aae3,
  archive#1791483832923446 sha256 8df8d2ca93717719a0e575e3310ecc6be589f3a3aa325ed08469f43c31aeb4c0;
  member check 220/220 hashes equal, none missing/unexpected; bundled-runtime rescore RESCORE_EXIT=0, all_equal true (30 tables + availability),
  17.97 s, peak 1,517,536 KiB, empty CLOUDSDK_CONFIG, HOME kept; current snapshot validator passed (VALIDATION_EXIT=0).
- 18:30:59 full-window-20261008c prepare_status succeeded (prepare_status#1791484259757780, prepared_manifest#1791484258622845); roster/geometry/contract/families match request.
- 18:33:35 FINAL request uploaded: gs://manuel-remote-sensing-oct-delivery-requests/requests/oct-final-20261008a/run_manifest.json#1791484415757028
  sha256 0a519a265605bcefc9c6e70621d31d2f6e50542c88fc02194cab221fc9594c6a -> workflow 79d33f60-7a7f-437d-a074-45da281fc6dd SUCCEEDED (submit-only)
  -> Cloud Run execution oct-delivery-qlb42 (image cp4-final-1). CLEANUP SELECTOR added.
- 19:17:37 FINAL run oct-delivery-qlb42 SUCCEEDED: runs/oct-final-20261008a/run_status.json#1791487045559976 status succeeded;
  outputs deliveries/oct-final-20261008a/; release record oct-staging/releases/oct-final-20261008a/release.json; pointer oct-staging/current.json#1791487045444241 (task staging namespace; no consumer cutover).
- Final offline relocated replay (/tmp/oct-replay-cloud-final.log, /tmp/oct-cloud-oct-final-20261008a/): manifest#1791486960794767 sha256 d377d241...,
  archive#1791487044233595 sha256 92406388...; members 220/220; RESCORE_EXIT=0 all_equal true; 12.66 s peak 1,518,944 KiB; current validator passed (VALIDATION_EXIT=0).
- Disclosures: /tmp/oct-final-disclosures.json (vintages EVI/FLDAS/VIIRS 2026-08, GOSIF 2024-12; WFP/ACLED keep; fill counts; all historical diagnostics unavailable/missing_evidence).
- 20:00-20:04 M6 cloud checks on the live trigger path (no scoring): duplicate replay of the succeeded event (workflow 843648b8-3506-4edb-9da2-ac26c612c250)
  -> oct-delivery-hjm8q exit 0, returned existing status (status_uri runs/oct-final-20261008a/run_status.json); invalid request
  requests/oct-invalid-20261008a/run_manifest.json#1791489608112958 -> oct-delivery-hdsgp exit 1 DeliveryManifestError, no runs/ objects;
  same run id changed content requests/oct-final-20261008a/run_manifest.json#1791489658508622 -> oct-delivery-ng85q exit 1 RunConflict.
  _RUN_ACQUIRED, run_status.json and oct-staging/current.json generations unchanged (1791484608393835 / 1791487045559976 / 1791487045444241).
  Earlier staging rejection 2ll5p rejected before scoring but its status write hit GCS 503 (pre-retry-fix) -> no status object (qualified).
  CAS release conflict: local fixtures only (no second full scoring run).
- 19:59 read-only REST wind-down: Batch c SUCCEEDED; executions 8bv78/xfr48/nwvkk/2ll5p/qlb42 TERMINAL; EE 33/33 COMPLETED; no active compute.
