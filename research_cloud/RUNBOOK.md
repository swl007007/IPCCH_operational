# Researcher runbook: FEWS NET / IPCCH research on food-crisis-modeling-enso

Cloud: project `food-crisis-modeling-enso`, region `us-central1` (Gemini assistant: global endpoint).
MLflow: `https://research-mlflow-76571749286.us-central1.run.app`.
Every command below that touches the cloud pins the project. Never change the global gcloud configuration.

There are two roles:
- **Researcher:** works in native WSL, uses the MLflow UI and SDK with their own Basic credentials, edits code, runs local smoke tests and compares or downloads results.
- **Operator:** also builds images, reserves budget and submits Vertex jobs. These steps write to the project, so they are marked **(operator)**.

## 1. Access

- **MLflow account.** MLflow uses Basic auth with personal accounts; the existing local accounts were migrated unchanged. Ask the MLflow administrator for an account and a role:
  - `ipcch-readers`: read;
  - `ipcch-job-writers`: create runs.
- **Credentials.** Give the SDK credentials through the environment, never on a command line or in a file under the repo:
  ```sh
  read -r MLFLOW_TRACKING_USERNAME; read -rs MLFLOW_TRACKING_PASSWORD
  export MLFLOW_TRACKING_USERNAME MLFLOW_TRACKING_PASSWORD
  export MLFLOW_TRACKING_URI=https://research-mlflow-76571749286.us-central1.run.app
  ```
- **Service identities (operator only).** Job and assistant identities (`ipcch-jobwriter`, `ipcch-reader`, `ipcch-assistant`) live in Secret Manager. They are for jobs and acceptance tools, not for people.
- **GCS reads.** Application-default credentials with the quota project pinned:
  ```sh
  gcloud auth application-default login
  gcloud auth application-default set-quota-project food-crisis-modeling-enso
  ```
  Tools set `IPCCH_GCP_PROJECT=food-crisis-modeling-enso`.

## 2. Workspace

- **Repository.** Native WSL only, not under `/mnt/c`: `git clone <control-plane> && cd control-plane`. `research_cloud/` is the integration code.
- **Scientific sources.** Pinned inside the images, under `/app/sources`.
- **Environments.** Use the pinned family environments. The simplest way to get exactly the cloud runtime locally is the image filesystem:
  - `crane export <image>@sha256:… | tar -x -C <rootfs>`;
  - run inside it with `research_cloud.images.rootfs_replay.sandbox(...)` (a bubblewrap sandbox: no network, uid 65534).
- **Inputs.** Inputs are not on Dropbox; read them from GCS through a base manifest of `gs://` URIs, each with its generation and sha256. Every download is re-hashed. Examples:
  - FEWS: `fews-runs/scen-b43ef6a-v1/prepared/…`;
  - IPCCH: `inputs/ipcch.raw_panel/…`.

  The research tables are also in Cloud SQL `research-pg`, database `research`, read through the Cloud SQL Auth Proxy with your SQL role.

## 3. Change data, features or a model; local smoke test

1. Edit the adapter or the config (`research_cloud/training/…`, family `config.json`: fixed params, tuning `space`, `objective`).
2. Build a small feature snapshot:
   ```sh
   python -m research_cloud.training.fews_features --manifest BASE.json --horizon 4 --target 2019-02 --output DIR
   python -m research_cloud.training.ipcch_features --manifest BASE.json --horizon 3 --output DIR
   ```
3. Run one trial locally, with local output and no MLflow write:
   ```sh
   python -m research_cloud.training.fews_fourclass --manifest DIR/manifest.json --config C.json --output OUT [--max_depth=3 …]
   python -m research_cloud.training.ipcch_quartet  --manifest DIR/manifest.json --config C.json --output OUT [--rounds=50 …]
   ```
   `OUT/trial.json` records the status, params, metrics, input hashes, code hashes and the package path.
4. Replay the produced package:
   ```sh
   python -m research_cloud.packages.replay OUT/package --report replay.json
   ```
5. Run the unit tests for what you changed, in that family's environment. The service venv lacks the scientific packages and the PostgreSQL fixture, so a whole-suite run there is not a meaningful gate.
6. Commit. Images are built only from a committed, clean `research_cloud`.

## 4. Build an image (operator)

```sh
python -m research_cloud.images.context --image training-ipcch|training-fews --out CTX --image-uri … --build-sa …
gcloud builds submit CTX --config CTX/cloudbuild.yaml --project=food-crisis-modeling-enso --async
```

- The build runs a self-check as uid 65534 with no network, and only then pushes.
- Record the digest. Specs always reference `image@sha256:…`.
- Rebuilding is not needed for changes that only affect the spec. The per-trial cap and the launcher are in the spec, not the image.

## 5. Submit a trial or an HPT study (operator)

1. **Reserve** the job's cost on the ledger *before* submitting:
   - Use `cost.ledger.reserve(conn, "training", "<YYYY-MM>", "<operation id>", amount, detail)`, where `amount` comes from `cost.ledger.vertex_reservation(machine $/h, trials, timeout_s, 600, 100, disk $/GiB-h)`.
   - The detail records machine, trials, timeout and overhead. The training pool has its own USD 100/month envelope.
2. **Cloud copies** of the manifest and config. Upload them create-only to `gs://food-crisis-modeling-enso-research-inputs/training-jobs/`.
   ```sh
   python -m research_cloud.training.cloud_job manifest --local M.json --snapshot NAME --out CLOUD_M.json
   python -m research_cloud.training.cloud_job config --local C.json --out CLOUD_C.json
   ```
3. **Parent run (HPT only):** create one MLflow run as `ipcch-jobwriter` in the target experiment and pass `--parent-run`.
4. **Spec:**
   ```sh
   python -m research_cloud.training.cloud_job spec --adapter research_cloud.training.ipcch_quartet \
     --image …/training-ipcch@sha256:… --machine n1-highmem-4 --manifest /gcs/…/CLOUD_M.json --config /gcs/…/CLOUD_C.json \
     --family ipcch_geoxgb_pooled_quartet --timeout-s 900 [--hpt 2 --parent-run RUN] \
     --mlflow-uri https://research-mlflow-76571749286.us-central1.run.app --mlflow-experiment EXP \
     --entry /usr/local/bin/train-entry --out SPEC.json
   ```
   - `--entry` is required for training-ipcch HPT: it hands `/var/hypertune` to uid 65534, then drops root.
   - **HPT per-trial cap:** the HPT command starts with `[/usr/local/bin/train-entry] /usr/bin/timeout --kill-after=30s 900s python …`. That sends TERM at 900 s and KILL at 930 s; the 30 s grace is inside the declared 600 s overhead, so it is not a hard 900 s.
   - **Study deadline:** trials × (timeout + 600 s).
   - Every spec sets `disableRetries: true`.
5. **Submit, poll, harvest:**
   ```sh
   python -m research_cloud.training.vertex_submit submit --spec SPEC.json --kind custom|hpt --operation ID --out ledger/vertex/ID
   python -m research_cloud.training.vertex_submit poll --kind custom|hpt --operation ID --out ledger/vertex/ID
   ```
   - Admission refuses a spec outside its reservation. That includes the wrong machine or trial count, retries enabled, and an HPT command without the exact cap prefix.
   - The claim is atomic. Never resubmit the same operation: a lost acknowledgement leaves the claim held, so run `reconcile` instead.
   - The reservation is held until the provider reports a terminal state; it is not released from a list lookup.

## 6. Compare

- **MLflow UI:** the experiment's runs. HPT trials are child runs of the parent, tagged with `vertex.CLOUD_ML_JOB_ID`, `vertex.CLOUD_ML_TRIAL_ID`, `image_digest`, `source_commit` and `trial_status`. Each run's `trial.json` and `metrics.json` are artifacts.
- **HPT parent run closing (operator, after the harvest):** nothing closes the parent automatically. After the study's terminal state, harvest it: Vertex trials vs MLflow child runs vs `trial.json`, then replay of the downloaded packages. Then close the parent as `ipcch-jobwriter`:
  - `FINISHED` only after a successful harvest;
  - `FAILED` for a failed job, `KILLED` for a cancelled one;
  - end time = the job's end time;
  - tags `vertex.hpt_job`, `vertex.hpt_state`, `vertex.hpt_end`, `ledger.operation` (and `hpt.harvest_sha256` on success).

  Until then the parent shows `RUNNING`; read the study state from `ledger/vertex/<op>/final.json`.
- **Historical work:**
  - experiment `historical-packages` (one run per retained historical package);
  - registry versions carry reverse-link tags `package.run_id`, `package.name` and `package.json_sha256`;
  - the 29 `FEWS NET | …` registered models are package pointers, not pyfunc models.

## 7. Download and load a model package

```python
import mlflow
path = mlflow.artifacts.download_artifacts(run_id=RUN, artifact_path="package", dst_path="pkg")
```

- **Check:** `sha256(pkg/package/package.json)` must equal the run tag `package.json_sha256`.
- **Load:** use `pkg/package/loader/entry.py` (the package contract).
- **Replay** the frozen reference sample in the package's recorded runtime image:
  ```sh
  python -m research_cloud.images.rootfs_replay --rootfs ROOT --image NAME --digest sha256:… --manifest M --config C \
    --packages DIR --expect-packages N --out OUT
  ```
  or, for a single package, `python -m research_cloud.packages.replay`.
- **Historical exceptions:**
  - `confirm-onset-v1`: the full system arm is not replayable (7 boosters missing); the pooled/global package replays.
  - `scen-b43ef6a-v1`: incomplete history; every extant byte is preserved and downloadable.

## 8. Recover

| Situation | What to do |
|---|---|
| Job FAILED or CANCELLED | Read `ledger/vertex/<op>/final.json` and the job logs. Fix the cause, then use a **new** operation ID with a new reservation. The old reservation stays recorded. |
| Submit outcome unknown | `vertex_submit reconcile`. It binds the job if exactly one carries the claim label; otherwise the claim stays held. Do not resubmit. |
| MLflow 401 | Wrong or changed credentials. Cached credentials expire within 60 s of a password change. |
| MLflow 429 / slow | The service is one instance with concurrency 40. Retry with backoff; do not fan out wider. |
| Large downloads | Use the SDK, which streams through the artifact proxy. Avoid UI downloads of whole package trees. |

## 9. Cost

- **Platform pool** (SQL, Run, GCS, images, secrets, logging, assistant): about USD 80/month steady. The first month is about USD 92 with the one-time migration items.
- **Training pool:** each Vertex job is reserved before submission against its own USD 100/month.
- **Assistant:** the Gemini guard admits requests only within its USD 10/month allocation.
- **Ledger:** `ledger/spend.sqlite` (operator).
