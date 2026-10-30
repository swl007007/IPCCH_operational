# CP2 packet steps 0–3 receipt (Executor, 2026-10-30)

Release: research/cp1/supervisor-review.md, "CP1 accepted; CP2 build release" (steps 0–3 only). Packet root `R/staging/ipcch-h2h8h14-20261030`; receipts under `receipts/`.

| step | command | result |
|---|---|---|
| 0 | `sha256sum SHA256SUMS` / `reservations.json`; `bash verify_packet.sh` | 6405b73b… / 9e36cb19… = released pins; preflight ok (34 files, external pin, worktree 9aa9e54 clean) → `receipts/00-preflight-step1.txt` |
| 1 | `IPCCH_FINAL_RESERVE_CONFIRM=r1 envs/mlflow-svc/bin/python -B job-packet/reserve.py --stage build --plan-sha256 9e36cb19… --out receipts/01-reserve-build.json` | rc 0; reserved `ipcch-h2h8h14-final-r1-build` platform 2026-10 USD 0.19; platform committed 97.71 → 97.90 |
| 2 | preflight (`receipts/00-preflight-step2.txt` ok) then `bash build-packet/build_step.sh > receipts/build/02-build.log` | rc 0. Tag precheck NOT_FOUND; ONE submit; build **108c9303-505f-4943-a6ff-e90169b6c658** (us-central1) WORKING 05:42:25Z → SUCCESS 05:43:04Z (create 05:42:17Z, finish 05:43:02Z); 3 steps SUCCESS; one pushed image |
| 2 | readback | AR by digest and by tag both = build digest **sha256:9797161afb01f44c4b169e61c7c9f3fa237bf6911e72c4da89f13b430941c689**, tag `chvalidity-final-h2h8h14-20261030` (`02-ar-readback.json`, `02-ar-tag-readback.json`, `02-digest.txt`) |
| 2 | in-image checks (read: `gcloud builds log … --region=us-central1 --project=food-crisis-modeling-enso` → `receipts/build/02-build-cloudlog.txt`) | Step #1 `selfcheck` ok as uid 65534 (includes the exact `/app/requirements.lock.txt` comparison: passes in-image); Step #2 `overlay_check` ok: 237 files, derived-vs-BASE exactly the 3 modules, runtime python 3.12.3 numpy 2.4.4 pandas 3.0.3 sklearn 1.8.0 xgboost 3.2.0 mlflow-skinny 3.17.0 cloudml-hypertune 0.1.0.dev6, composite commit 439a488+overlay(c7aadb13/e56ccf41/4a4dd377) |
| 3 | preflight (`receipts/00-preflight-step3.txt` ok) then `envs/mlflow-svc/bin/python -B job-packet/make_packet_final.py specs --digest sha256:9797161a…` | rc 0 → `job-packet/specs/spec-final-h{02,08,14}.json` (sha256 8a7dfeda… / 561f5a9c… / 6c1440bd…), `job-packet/specs-check.json` 7aea2651…: within_reservation_problems [] ×3, label task exactly `ipcch-h2h8h14-final`, env image digest equal, recipe card equal |

Spec content (H08 shown; H02/H14 identical except horizon): n1-standard-16 ×1, pd-standard 100 GiB, timeout 7200s, disableRetries, no restart, SA research-trainer@, args `--manifest /gcs/food-crisis-modeling-enso-research-inputs/training-jobs/ipcch-h2h8h14-final/r1/inputs/manifest-final-hHH.json --config …/config-final-hHH.json --output gs://food-crisis-modeling-enso-research-artifacts/trials/ipcch_validity_pooled --mlflow-experiment "IPCCH dashboard"`, env IPCCH_IMAGE_DIGEST, IPCCH_REQUIRE_REGISTRATION, IPCCH_MODEL_RECIPE (baseline/horizon/mode/model_card), MLFLOW URIs.

Not done (held): step 4 job reservations, step 5 uploads, steps 6+ occupancy/submissions. Note: the new specs/specs-check files are not in the step-0 SHA256SUMS (generated after it); their hashes are listed above for pinning.
