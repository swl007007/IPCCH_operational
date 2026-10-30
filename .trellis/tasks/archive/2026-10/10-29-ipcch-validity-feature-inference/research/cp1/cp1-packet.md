# CP1 concrete paid packet — H2/H8/H14 final-stage training (NOT RELEASED; prepared locally, no cloud write)

Every step needs explicit Supervisor release. Cloud reads were preauthorized; writes and paid steps are not released.
`W=/home/swl007007/projects/food-crisis-research`, `D=$W/staging/ipcch-h2h8h14-20261030`, cwd `$W/control-plane-h2h8h14` (branch `task/ipcch-h2-h8-h14-final` @ 9aa9e54), `PY=$W/envs/mlflow-svc/bin/python` (tooling, as in 10-28; the reserve step imports `research_cloud.cost.ledger`; specs import cloud_job/vertex_submit), `PYTHONPATH=.`, `PYTHONDONTWRITEBYTECODE=1`. Every packet file is pinned in `$D/SHA256SUMS` (`cd $D && sha256sum -c SHA256SUMS`).
Account: gcloud `weilun.shi@cgiar.org`; every call passes `--project=food-crisis-modeling-enso` explicitly; the default config (`manuel-remote-sensing`) is not changed. No IAM change.

## Identities
| item | value |
|---|---|
| code | worktree commit 9aa9e54 (baseline 4cb493f = 10-28 overlay; C1–C5) |
| overlaid modules | dataset_input.py c7aadb13…, ipcch_validity_features.py e56ccf41…, ipcch_validity_pooled.py 4a4dd377… |
| base image | `training-ipcch-validity@sha256:fd921dd7…ca939` (439a488; the 10-28 base) |
| new tag | `training-ipcch-validity:chvalidity-final-h2h8h14-20261030` (precheck must be NOT_FOUND) |
| context | `$D/image-overlay-final/` (9 files), record `image-overlay-final.context-record.json` sha256 c9575d08… |
| in-image check | r1 `overlay_check.py` with ONE line changed (adapter identity tests `vp.FINAL_ARM`): `$D/overlay_check-vs-r1.diff` |
| local simulation | `$D/logs/overlay_check_sim.*` (rc 0; 237 files; derived-vs-BASE exactly the 3 modules; runtime equal); `$D/logs/selfcheck_sim.*` (all code steps passed; rc 1 only at the final lock comparison, because of the local venv's certifi 2026.10.19 vs lock 2026.7.22; the image satisfies its lock) |
| store objects | `gs://food-crisis-modeling-enso-research-inputs/training-jobs/ipcch-h2h8h14-final/r1/inputs/{manifest,config}-final-h{02,08,14}.json` (6 new, create-only) |
| data objects | none uploaded: 15 existing generation-pinned objects (the 10-28 formal inputs; all BYTES-verified at CP0) + freeze-h00/h06/h12 + index |
| configs | pinned recipes from `research/cp1/recipes/config-final-h{02,08,14}.json` (byte copies in `$D/job-packet/objects/`) |
| plan | `$D/job-packet/reservations.json` sha256 9e36cb19… (build 0.19 + platform 1.00 + training 3 × 1.9073 = 6.9119) |

## Steps (receipts under `$D/receipts/`)
0. **Preflight before EVERY step (read-only)**: `bash $D/verify_packet.sh`. It checks every packet file against `SHA256SUMS`, the pinned external dependency (task 10-28 `job-packet-ch/upload.py` sha256 7199095b…, imported read-only by `upload.py`, which re-verifies the same pin itself before import), and that the imported `research_cloud` code is worktree commit 9aa9e54 with no tracked changes. Nonzero → stop.
1. **Build line (ledger write)**: `IPCCH_FINAL_RESERVE_CONFIRM=r1 $PY -B $D/job-packet/reserve.py --stage build --plan-sha256 9e36cb1979f4ffb82a185570df608031e83d9d5f3d870b66645c0474122862c2 --out $D/receipts/01-reserve-build.json`. The line must be absent, and platform committed + 0.19 ≤ 100.
2. **Build (PAID, once)**: `bash $D/build-packet/build_step.sh > $D/receipts/build/02-build.log 2>&1; echo "rc=$?" >> …`. It verifies the 9 context files against the record; tag precheck NOT_FOUND (read); ONE `gcloud builds submit` (one source tarball under `gs://food-crisis-modeling-enso-research-build/source/`, build SA research-build@, us-central1, 1,800 s, CLOUD_LOGGING_ONLY; selfcheck + overlay_check as uid 65534 without network; pushes ONE image). It polls every 30 s to a terminal state; on SUCCESS only, AR readback by digest and by tag (must equal) → `02-digest.txt`. No retry, no rebuild, no tag move.
3. **Specs (local)**: `$PY -B $D/job-packet/make_packet_final.py specs --digest $(cat $D/receipts/build/02-digest.txt)` → `specs/spec-final-h{02,08,14}.json` + `specs-check.json` (image digest equality, within_reservation, recipe card equality, labels.task exactly `ipcch-h2h8h14-final`; any failure exits nonzero and stops).
4. **Job lines (ledger write)**: `… reserve.py --stage jobs --plan-sha256 9e36cb19… --out $D/receipts/04-reserve-jobs.json`. The build line must be present, the four lines absent, each pool within its cap, and task total ≤ 8.00.
5. **Store uploads (create-only writes)**: `IPCCH_FINAL_UPLOAD_CONFIRM=r1 $PY -B $D/job-packet/upload.py --objects-sha256 $(sha256sum $D/job-packet/objects.json | cut -c1-64) --out $D/receipts/05-uploads.json` (6 objects; transport = 10-28 helpers; precheck all absent; readback size/MD5/CRC32C).
6. **Fresh occupancy before wave 1 (read; fail-closed on unknown machine types)**: `$PY -B $D/job-packet/occupancy.py --out $D/receipts/06-occupancy-wave1.json --planned 2`. ok only if this task has ≤ 2 active jobs and existing region vCPUs + 32 ≤ 42 (else `--planned 1` for H2 only, or wait).
7. **Wave 1 (PAID)**: for h in 02 08: `$PY -B -m research_cloud.training.vertex_submit submit --spec $D/job-packet/specs/spec-final-h$h.json --kind custom --operation ipcch-h2h8h14-final-r1-h$h --out $W/ledger/vertex/ipcch-h2h8h14-final-r1-h$h`, then a background `vertex_submit poll … --every 120`. Unknown outcome → `vertex_submit reconcile` only.
8. **Wave 2 (PAID)**: H14 only after both wave-1 jobs reach a terminal state, checked failure-first: any FAILED/CANCELLED/EXPIRED stops for review. A FRESH occupancy check immediately before wave 2 (`--out $D/receipts/08-occupancy-wave2.json --planned 1`) must give task jobs ≤ 2 and existing + 16 ≤ 42. Then ONE submit of `spec-final-h14.json` and its poller.
9. **Harvest (reads)**: generation-pinned download of each succeeded trial prefix (without the gcs-only base_X), then checks: trial succeeded, recipe == uploaded config, image digest == build digest, composite source identifier, gate passed, cohort 15,317, one context `hHH_supp_2026` with 4 scalar fits, package verifies, MLflow run/registered model version 1. A harvest script adapted from 10-28 `harvest_formal.py` is prepared at CP2 before this step.
10. **Package replay (local)**: `$W/envs/…/python -m research_cloud.packages.replay <trial>/package --report …` ×3. CP2 then converts to the runtime layout and builds the evidence.

## Resources and cost
- Per job: n1-standard-16 ×1, 100 GiB pd-standard, timeout 7,200 s, `disableRetries`, SA research-trainer@, MLflow job-writer secret read only inside the worker, publishing one new run + model version in experiment `IPCCH dashboard`. Existing runs, models, versions and aliases are never touched.
- Concurrency: at most TWO jobs at once (3 × 16 = 48 > 42-vCPU region quota); existing occupancy counts; H14 waits for capacity.
- Reservation estimate USD 6.9119 (10-28 per-job bound: 0.8739954 USD/h × 7,800 s + PD = 1.9073; build 0.19; platform 1.00), plus abort boundaries (timeout, no retries, no resubmit, wave gating, stop on first failure). It is not a billing-enforced cap; billed actuals are reported from billing evidence only.
- The platform line's item descriptions are the task 10-28 items carried over unchanged as a conservative estimate. They mention 10-28 data/baseline-copy writes; this packet authorizes and performs ONLY the six store-object writes (`reservations.json` `authorization_note`).
- Ledger (read from a copy, 2026-10): platform 97.71/100 → 98.90 after both lines (headroom 1.10); training 140.86/200 → 146.58. If execution slips into 2026-11 the plan month must be re-rendered (new plan sha) and re-reviewed.

## Stop rules
Any precheck, digest or tag mismatch stops before the paid steps. A failed build or job is never retried or resubmitted without a new release. An uncertain create triggers one read-only reconciliation and stops. Reservations are released only with provider evidence that no resource exists.
