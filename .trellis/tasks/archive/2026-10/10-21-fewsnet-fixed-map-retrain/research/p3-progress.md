# P3/P4 executor progress (durable checkpoint, 2026-10-22 06:40Z)

Staging `S=/home/swl007007/projects/food-crisis-research/staging/fewsnet-fixed-map-retrain-20261022`.

## Running / completed jobs

- **Production all-history fit (COMPLETED 06:40:24Z, exit 0, wall 10:28, max RSS 6.9 GB; accepted, no rerun):**
  sequential; `/usr/bin/time` launcher PID 323367, actual Python PID 323372; started 06:29:58Z from clean worktree
  `S/fit-source-ff389b1` (commit ff389b1, process-scoped `eol=crlf` map attribute), env
  `~/.venvs/fewsnet-fit-lock-20261022`, launcher `S/runtime/launch_full_fit_sequential.py`
  (sha f701265b…), log `S/runtime/full_fit.log`, output `S/fit/full-202610-ff389b11af93-02caeb861750/`
  (run_manifest sha ff026e3a…). model.joblib: 0m 69b90bf03aea…, 6m a0802145992e…, 12m 62520a04c0cb….
  Executor load receipt `S/runtime/full_fit_package_load_receipt.json` (sha f46b3f2e…, `load_local_model_package`
  with expected suite/commit/panel); supervisor receipt `supervisor-fit-package-verification.json`. 6m and 12m
  each have one single-class partition on the pooled fallback (recorded in run_manifest fallback_counts).
  First attempt (max_workers=3) failed before fitting (PartitionMap not picklable): log
  `S/runtime/full_fit.failed-pool-pickle.log`, partial output `S/fit/failed-pool-pickle-…` (fit keys only).
  Pool fix committed dbfc196 (not used by this run). Do not rerun.
- **Release snapshot (succeeded):** `gs://food-crisis-test-ipcch-data/prepared/fewsnet-retrain-20261022a/`,
  in-process `run_prepare` from worktree 38c1ccb; request `prepare_requests/fewsnet-retrain-20261022a/prepare_request.json#1792649463991739`;
  manifest generation 1792650679865065 sha a5db2c8b…; vintages evi 2026-09, fldas 2026-08, viirs 2026-08,
  gosif_mean 2025-12 (v3 from 2025-01), gosif_sd 2024-12. Overlay over v2 panel loses nothing
  (`S/sources/remote/retrain-snapshot-check/snapshot_overlay_check.json`; supervisor receipt).
- EVI 2026-09 bounded acquisition: prepare_id `fewsnet-retrain-evi202609-20261022` (EE task TEE3NHA7YUJMWU7LHH2KTKOS).

## Commits on feat/fewsnet-fixed-map-retrain (executor)

ff389b1 full-data fit path · 38c1ccb nightlight sum / GOSIF v3 boundary / contract v2 · 1dd5e70 + 82a4a0f
frozen confidence (+ raw evidence/source declarations) · 2af2a89 v2 freeze · dbfc196 pool fix ·
f9506bc execution selection / inheritance / candidate · 9e5a375 Workflow dispatch + resolve.
Tests: 511 passed (test env = lock + pytest + pyyaml).

## Remaining (in order)

1. deploy/setup.py: workflow env (PREPARE_JOB, EARTH_ENGINE_PROJECT, BATCH_*, PREPARE_POLL_SECONDS,
   PREPARE_MAX_POLLS) and scoped grants (workflow SA: run.developer on prepare job, object read on
   request/data buckets). Deploy only after maintenance checkpoint.
2. pipeline.py operator: submit intent with execution block; status shows reused/skipped preparation;
   candidate download (pinned candidate, no current.json change); maintenance hold (pause admission,
   reconcile running work, restore); promotion bound to verified receipt + expected pointer generation
   (absent pointer => generation 0); recovery record.
3. New FEWS packages -> baseline/model registration (new image digest, versioned work dir/state).
4. Image build/push, six-slot loading evidence, candidate request (remote off, FEWS only, IPCCH inherited
   from oct-confidence-20261009b archive sha ac3bfcea…, frozen confidence, v2 history panel, snapshot above),
   candidate run, download + FEWS-only relocated replay, then promotion. Cloud mutations end 13:00Z.

## P4 state (07:57Z)

- Image `runtime@sha256:487a23159b3bb151245530b6cfcef71820c8a716a189e5a2a3bbcc3074c97fae` (Cloud Build ce6e6cbf,
  source 0d60a4e clean worktree); in-image six-slot evidence `research/p4/six-slot-runtime-evidence.json` (accepted).
- Commits: 0d60a4e dispatch gates · 48d3d1e operator chain · 7e458e2 recovery concurrency · 53d5f87 grant flag.
- Candidate baseline `S/baseline/fews-retrain-20261022` sha b77cb29b (82 files; FEWS history = v2 SOURCE a83f5f4b);
  candidate operator config `/home/swl007007/ipcch-operator/food-crisis-test-fews-retrain-20261022/project.json`
  (operator-state/initialized.json). Normal config untouched: `/home/swl007007/ipcch-operator/food-crisis-test/project.json`
  sha 93293916.
- Inherited source published byte-identically: `gs://food-crisis-test-ipcch-data/inherited/oct-confidence-20261009b/`
  manifest#1792653996979392, archive#1792654027016952 (`research/p4/inherit-refs.json`).
- Maintenance `fews-retrain-20261022` (owner weilun.shi, admits fews-candidate-20261022a):
  hold gen 1792654802244430 -> gate (workflow rev 000002-c24, probe refused) -> apply (jobs + workflow on new image,
  phase shared_changed). State: `<candidate work_dir>/operations/fews-retrain-20261022/operation.json`.
  Restore: `pipeline.py maintenance --operation-id fews-retrain-20261022 --execute restore` then `release`.
- Candidate `fews-candidate-20261022a` submitted 07:50Z (request gen 1792655462447117), job execution
  oct-delivery-hfddt running. Next: download --candidate, verify (+ verify_candidate_release.py), stage fallback
  (stage_fallback.py), then promotion only when cleared.
