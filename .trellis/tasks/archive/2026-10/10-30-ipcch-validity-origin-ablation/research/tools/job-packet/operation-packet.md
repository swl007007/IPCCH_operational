# Origin-ablation formal-job packet r1 — task 10-30 (NOT released; prepared locally; no cloud command run)

Three fixed-parameter formal CustomJobs (H0/H6/H12) of `validity_augmented_idp_202610_acledagg_lag1_uncal_hpt` with
original-only backbone fitting labels on the CH-final panel (`origin_ablation`), on the accepted image
`training-ipcch-validity@sha256:b208b1320033473af374dc1e08fbdac36a0fbbda993f7831bb1f579f94a9d197` (build
22176002-a56f-47df-ab67-ede2ba8c68da). No HPT, no baseline refit, no retry/refit, no IAM/API/secret/MLflow configuration
change, no alias or promotion. Annual-package cleanup, MLflow readback and Dashboard UI are later packets.

`W=/home/swl007007/projects/food-crisis-research`, `P=/home/swl007007/projects/food-crisis-research/staging/ipcch-origin-ablation-20261030/job-packet`, `D="<task>/research/cp3/jobs"` (operational task dir; quoted, contains spaces),
`PY=$W/envs/mlflow-svc/bin/python`, cwd `$W/control-plane-origin-ablation` (clean, 868db9f), `PYTHONPATH=.`,
`PYTHONDONTWRITEBYTECODE=1`, `-B` everywhere; `SCI="env IPCCH_AE_SRC=$W/sources/Food_Crisis_Cluster/IPCCHAlphaEarthExperiment PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. $HOME/.venvs/ipcch-validity-idp/bin/python -B"`.
Every packet file pinned in `$P/SHA256SUMS` (`cd $W && sha256sum -c $P/SHA256SUMS`). Helpers = the task 10-28 proven
scripts with only the necessary diffs (`diffs/`); `make_packet.py` and `harvest_formal.py` adapted for the origin pins.

## Pinned identities

| Item | Value |
|---|---|
| image | `training-ipcch-validity@sha256:b208b132…` (tag gosifv3-chvalidity-originfit-20261030), read from research/cp2/build/02-digest.txt + 03-build-summary.json; lineage proof check/lineage-proof.json |
| configs (`objects/config-formal-hXX.json`) | = `candidate/final-r2/formal-origin-hXX.json` (gate-checked in check/gates-r2 on 7023d10) with EXACTLY one difference: `provenance.code_overlay` restated from this build (`objects.json` sha256 1b322b167c9af0f5ed810ca9497c105d042886012d44274c07c062e1772c403a) |
| data objects | byte-equal copies of the CH-final runs' retained predictions (size/MD5/CRC32C equal to the artifacts-bucket objects of jobs 6867303963549499392 / 3518877640599535616 / 8594997370599505920; sha256 = comparison.baseline_predictions = origin_ablation.ch_baseline.predictions_sha256) → `gs://food-crisis-modeling-enso-research-inputs/training-jobs/ipcch-validity-origin-ablation/r1/inputs/baseline-predictions-chfinal-hXX.csv.gz` |
| manifests (generated after the data uploads) | the CH-final run's uploaded manifest of the horizon (the exact object its trial read; 18 generation-pinned roles incl. ch_links) with only `baseline_predictions` replaced; pins re-checked against the inherited ch_correction inputs + the CH-final comparison pin (dry run on a copy: `manifests-render-dryrun-on-copy.json`) |
| store objects | `…/ipcch-validity-origin-ablation/r1/inputs/{manifest,config}-formal-h{00,06,12}.json` + 3 data copies (all 9 must be absent) |
| specs (`specs-check.json`) | n1-standard-16 x1, 100 GiB pd-standard, timeout 7,200 s, disableRetries, no restart, SA research-trainer@, entry train-entry, experiment `IPCCH dashboard`, displayName `ipcch-origin-ablation-formal-hXX`, labels task=ipcch-validity-origin-ablation, horizon=hXX; within_reservation [] |
| ledger plan (`reservations.json` 27ec849ca8bb6780a3628975df8af0095977234c2ac60f2f0fa9289ffdd3c2c7) | platform `ipcch-origin-ablation-r1-platform` USD 0.90 (items 0.7925); training `ipcch-origin-ablation-r1-formal-h{00,06,12}` 1.9073 each = 5.7219. Dry run on a copy: platform 99.09 → 99.99 / 100 (headroom 0.01), training 146.58 → 152.30 / 200; second run refuses; real ledger unchanged (`reserve-dryrun-on-copy.json`) |
| task cap | proposed USD 7.00 = build 0.19 (held) + platform 0.90 + training 5.7219 = 6.8119; no earlier task reservation counted |

Offline publication render (`render-draft/`, rc 0 all horizons; final render on the uploaded manifests in step 2b):
registered `IPCCH Original-label fit ablation (GOSIF v3 + CH validity 20261028) | …_hpt | H-month` (new, ≠ CH-final);
run / LoggedModel names new; code_overlay from the actual build, no CH-final image digest or old module sha in any text;
`baseline.*` = the CH-final run of the horizon; DatasetInput `IPCCH validity (gosif-v3-input-20261027+ch-validity-20261028+original-label-fit-20261030) | …_hpt | HXX | modeling panel index` with the inherited panel digest dba329f9… and fit-subset tags equal to the pins (the payload's exact saved-membership check run on the expected original-only memberships); no forbidden inherited text (copy training, GOSIF-v3 comparison).

## Order (each step needs release; receipts under $D)

1. **Reservations (local ledger write)** — `IPCCH_ORIGIN_JOB_RESERVE_CONFIRM=r1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. $PY -B $P/reserve_job.py --plan-sha256 27ec849ca8bb6780a3628975df8af0095977234c2ac60f2f0fa9289ffdd3c2c7 --out "$D/01-reservations.json" > "$D/01-reservations.log" 2>&1; echo "rc=$?" >> "$D/01-reservations.log"`
   (all four absent, own build line present, pool caps (live), task cap).
2. **Create-only uploads (writes)** — `IPCCH_ORIGIN_UPLOAD_CONFIRM=r1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. $PY -B $P/upload.py --objects-sha256 1b322b167c9af0f5ed810ca9497c105d042886012d44274c07c062e1772c403a --out "$D/02-uploads.json" > "$D/02-uploads.log" 2>&1; echo "rc=$?" >> "$D/02-uploads.log"`
   (9 existence checks; 3 data copies, then local manifests at the created generations, then 3 manifests + 3 configs;
   if_generation_match=0, retry=None, size/MD5/CRC32C readback; uncertain outcome: one metadata read, stop).
2b. **Final offline render (local)** — `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. $PY -B $P/make_packet.py render --stage final > "$D/02b-render-final.log" 2>&1; echo "rc=$?" >> "$D/02b-render-final.log"`; rc ≠ 0 stops before any job.
3. **Occupancy (read)** — `PYTHONDONTWRITEBYTECODE=1 $PY -B $P/occupancy.py --out "$D/03-occupancy-wave1.json" --planned 2` (task ≤ 2 active, region ≤ 42 vCPUs).
4. **Submit H0 and H6 (paid)** — for h in 00 06: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. $PY -B -m research_cloud.training.vertex_submit submit --spec $P/specs/spec-formal-h$h.json --kind custom --operation ipcch-origin-ablation-r1-formal-h$h --out $W/ledger/vertex/ipcch-origin-ablation-r1-formal-h$h > "$D/04-submit-h$h.log" 2>&1`
   (claim, one POST; unknown outcome → `vertex_submit reconcile` only), then background pollers `… vertex_submit poll --kind custom --operation ipcch-origin-ablation-r1-formal-h$h --out $W/ledger/vertex/… --every 120 > "$D/05-poll-h$h.log" 2>&1`.
5. **H12 gate (paid, background)** — `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. $PY -B $P/h12_gate.py` (self-test rc 0): failure-first on h00/h06; occupancy wave 2 (planned 1); two fresh provider GETs of the bound wave-1 jobs right before ONE H12 submit and its poller; lock file; never a second submit.
6. **Harvest (reads)** — per SUCCEEDED job: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. $PY -B $P/harvest_formal.py H --out "$D/06-harvest-hHH.json"` → `$W/scratch/origin-ablation-20261030/harvest/formal-hHH/trial-0` (base_X not downloaded; annual package downloaded). Checks listed in the script docstring (fits vs pinned original-only memberships and zero copies; gates incl. origin + A2 pairing; both packages verify and route holdout-only / annual-only; origin outputs; names/DatasetInput == render-final; image/source/modules). `fits()` exercised offline (`logs/harvest-fits-exercise.log`: positive pass, wrong pin and copy-in-membership refused).
7. **Package replay (local)** — `$SCI -m research_cloud.packages.replay $W/scratch/origin-ablation-20261030/harvest/formal-hHH/trial-0/package --report "$D/07-replay-hHH.json"` and `… /gcs-only/annual-package --report "$D/07-replay-annual-hHH.json"` (x3).
8. Stop and report run/model/version ids. Independent TUI/metric recompute and reconciliation with the CH-final run, annual-package cleanup (GCS + local, only after 07 replay receipts), MLflow readback and Dashboard UI follow as separate packets.

## Job behaviour

Workers read the pinned manifest/config through GCS FUSE, hash every input, run the no-fit gates (inherited CH contract on
the unfiltered plans = CH-final digests; origin gate; A2 pre-fit pairing of the prepared scored rows with the CH-final
predictions), claim `training-attempt.json`, fit every annual context once with original-only labels and the frozen
parameters (11 contexts / 44 scalar fits in total), score the full inherited cohort, write outputs to
`gs://food-crisis-modeling-enso-research-artifacts/trials/ipcch_validity_pooled/<job>/trial-0` (holdout-only retained
package; annual package under gcs-only), read the job-writer secret v1 once and publish one run, LoggedModel, new registered
model (version 1), DatasetInput, card, tags, params, metrics and artifacts into `IPCCH dashboard`. Existing runs, models,
versions and aliases are not touched.

## Cost

Reserved: training 5.7219 (7,800 s bound each), platform 0.90. Projected: CH-final trial times 20/16/11 min on ~74% copies;
original-only fits use ~26% of the fitting rows → roughly 0.3–0.5 h total x USD 0.8803/h ≈ USD 0.3–0.5. Billed actuals are
not asserted. Platform pool will have USD 0.01 headroom after step 1; any further platform need (e.g. a publication
recovery) requires a user cap decision.

## Failure behaviour

disableRetries; a provider restart never refits (attempt claim). A failed job or incomplete publication stops further
submissions (H12 gate) for review; no replacement fit, refit or resubmit. Uncertain creates use read-only reconciliation.
Reservations are never released without provider evidence that no resource exists. Any precheck failure stops before paid steps.
