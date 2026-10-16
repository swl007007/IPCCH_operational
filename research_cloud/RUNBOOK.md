# Researcher runbook: FEWS NET / IPCCH research on food-crisis-modeling-enso

Cloud: project `food-crisis-modeling-enso`, region `us-central1` (Gemini assistant: global endpoint).
MLflow: `https://research-mlflow-76571749286.us-central1.run.app`.
Every command below that touches the cloud pins the project. Never change the global gcloud configuration.

There are two roles:
- **Researcher:** native WSL, MLflow UI and SDK with **their own** Basic credentials, local smoke tests, compare and download. No operator secret is needed for any researcher step.
- **Operator:** also builds images, reserves budget and submits Vertex jobs. These steps write to the project and use service identities from Secret Manager, so they are marked **(operator)**.

All examples use the existing workspace root, `W=/home/swl007007/projects/food-crisis-research`, and its saved files. Blocks marked **template** show the general form. Blocks that would create cloud objects (the parent run and submit/poll in §5) are marked **not re-run**: they are the calls used for the acceptance jobs, not repeated for this document. Every other block was run as written on 2026-10-16. Reproductions: §5 manifest/config/spec regenerate the submitted acceptance files; the §5 reservation ran on a ledger copy; §3 is the FEWS smoke; §7 download, hash and load ran on `geoxgb_reference-partitioned_gated-h01`.

Pinned images (`us-central1-docker.pkg.dev/food-crisis-modeling-enso/research/…`):

| Image | Digest | Use |
|---|---|---|
| training-fews | `sha256:d7ac74a690e72e031ac9e7fe04612c6f851c023cef03023781fc5b67ed9f0456` | FEWS features/trials; FEWS + pop-v1 historical packages |
| training-ipcch (fdbe6d1, train-entry) | `sha256:6ad7f46ce03ed3e2db9533d77de87609572dee9a632b3b7b8c431e7fdab16a91` | IPCCH features/trials/HPT |
| training-ipcch (36bde42) | `sha256:7c59d674ceb0dae7869f78c10e1751ff2d2e2217063e59626d0261c227a000fb` | GeoXGB historical packages (runtime rt-geoxgb-x300) |
| replay-x320 | `sha256:1e78790933636289e6c59c5d1863126e1558f61d8b20e4a8617e8318b9ce982f` | IPCCH-geo + AlphaEarth historical packages |
| replay-forecast-x320 | `sha256:2810ab7c1bec048dce6c24cb4968937c0461deff68c6cb10c17ecf5c59e9bef7` | forecasting historical packages |

## 1. Access

- **MLflow account.** MLflow uses Basic auth with personal accounts; the existing local accounts were migrated unchanged. Ask the MLflow administrator for an account and a role:
  - `ipcch-readers`: read;
  - `ipcch-job-writers`: create runs.
- **Credentials.** Give the SDK your credentials through the environment, never on a command line or in a file under the repo:
  ```sh
  read -r MLFLOW_TRACKING_USERNAME; read -rs MLFLOW_TRACKING_PASSWORD
  export MLFLOW_TRACKING_USERNAME MLFLOW_TRACKING_PASSWORD
  export MLFLOW_TRACKING_URI=https://research-mlflow-76571749286.us-central1.run.app
  ```
- **Google access** (GCS inputs and image pulls), with application-default credentials and the quota project pinned:
  ```sh
  gcloud auth application-default login
  gcloud auth application-default set-quota-project food-crisis-modeling-enso
  ```
  Your Google account needs read on the research buckets and on the Artifact Registry repository `research`.

## 2. Workspace and the pinned runtime

Run this once per shell. Every later block assumes it: `W`, the tooling venv (so `python` is `$W/envs/mlflow-svc/bin/python`), the repository as the working directory and `PYTHONPATH`.

```sh
W=/home/swl007007/projects/food-crisis-research
source $W/envs/mlflow-svc/bin/activate
cd $W/control-plane && export PYTHONPATH=$PWD
```

- **Repository:** `$W/control-plane`, a native WSL clone, not under `/mnt/c`. `research_cloud/` is the integration code.
- **Training runtime:** the image, run locally as an exported filesystem in a bubblewrap sandbox. There is no host venv for training: `$W/envs/rt-*` are the historical replay runtimes and `$W/envs/mlflow-svc` is the service/tooling venv.
- **Exported filesystems:** they already exist under `$W/scratch/image-pulls/<name>.rootfs`, with `<name>.manifest.json` and `<name>.config.json`. The pins are in `expected.txt`; the fdbe6d1 image is `training-ipcch-fdbe6d1.*`.
- **Exporting one yourself:** `crane` is at `~/.local/bin/crane`. This is what `$W/scratch/image-pulls/pull-fdbe6d1.sh` does:
  ```sh
  OUT=$W/scratch/image-pulls; I=us-central1-docker.pkg.dev/food-crisis-modeling-enso/research/training-ipcch@sha256:6ad7f46ce03ed3e2db9533d77de87609572dee9a632b3b7b8c431e7fdab16a91
  export DOCKER_CONFIG=$(mktemp -d); chmod 700 $DOCKER_CONFIG; trap 'rm -rf "$DOCKER_CONFIG"' EXIT
  gcloud auth print-access-token --billing-project=food-crisis-modeling-enso --quiet | crane auth login us-central1-docker.pkg.dev -u oauth2accesstoken --password-stdin
  crane manifest $I > $OUT/training-ipcch-fdbe6d1.manifest.json; crane config $I > $OUT/training-ipcch-fdbe6d1.config.json
  mkdir -p $OUT/training-ipcch-fdbe6d1.rootfs && crane export $I - | tar -x -C $OUT/training-ipcch-fdbe6d1.rootfs --no-same-owner
  ```
- **Scientific sources:**
  - **Inside the images:** `FEWS_SRC=/app/sources/FEWSNETGeoXGBExperiment` and `IPCCH_GEOXGB_SRC=/app/sources/IPCCHGeoXGBExperiment` (image Env). The sandbox below uses them.
  - **On the host, FEWS:** `--fews-src $W/sources/Food_Crisis_Cluster/FEWSNETGeoXGBExperiment`. The clone is at the pinned commit `6c1ebf72…`; check with `git -C $W/sources/Food_Crisis_Cluster rev-parse HEAD`.
  - **On the host, IPCCH:** the image's source is P6's `source_code` MLflow artifact, not the live repository. For the exact source use `--geoxgb-src $W/scratch/image-pulls/training-ipcch-fdbe6d1.rootfs/app/sources/IPCCHGeoXGBExperiment`. `$W/sources/Food_Crisis_Cluster/IPCCHGeoXGBExperiment` is the live clone and may differ.
- **Inputs:** read from GCS through saved base manifests of `gs://` URIs (generation + sha256; every download is re-hashed), with host-path-free configs:
  - FEWS: `$W/scratch/ac8/inputs-fews/{base.json,config.json}`;
  - IPCCH: `$W/scratch/ac8/inputs-ipcch/{base.json,config.json}`.

  The research tables are also in Cloud SQL `research-pg`, database `research`, read through the Cloud SQL Auth Proxy with your SQL role.

## 3. Change data, features or a model; local smoke test

Edit the adapter or config (`research_cloud/training/…`; the config holds fixed params, the tuning `space` and the `objective`). Then run the feature build and one trial **inside the pinned image**:
- your working tree is mounted read-only as the code (`PYTHONPATH`);
- inputs come from GCS with your ADC;
- there is no MLflow write, because `MLFLOW_TRACKING_URI` is not set inside.

This is the AC8 recipe (`research_cloud/deploy/clean_wsl_run.py`) without its clean clone and without the MLflow step. It takes about 3 minutes per family.

```sh
W=/home/swl007007/projects/food-crisis-research
FAM=fews; IMG=training-fews                 # IPCCH: FAM=ipcch; IMG=training-ipcch-fdbe6d1
OUT=$W/scratch/smoke-$FAM-$(date +%Y%m%dT%H%M%S)
cd $W/control-plane
PYTHONPATH=. python3 - "$W" "$FAM" "$IMG" "$OUT" <<'P'
import json, os, subprocess, sys
from research_cloud.images.rootfs_replay import sandbox
W, fam, img, out = sys.argv[1:]
os.makedirs(out)
code, inputs = os.path.realpath("."), f"{W}/scratch/ac8/inputs-{fam}"
adc = os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
b = sandbox(f"{W}/scratch/image-pulls/{img}.rootfs", json.load(open(f"{W}/scratch/image-pulls/{img}.config.json")), code, out)
i = b.index("--clearenv")
b[i:i] = ["--share-net", "--ro-bind", code, "/work/checkout", "--ro-bind", inputs, "/work/inputs",
          "--ro-bind", adc, "/work/adc.json", "--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf"]
b += ["--setenv", "PYTHONPATH", "/work/checkout", "--setenv", "GOOGLE_APPLICATION_CREDENTIALS", "/work/adc.json",
      "--setenv", "IPCCH_GCP_PROJECT", "food-crisis-modeling-enso"]
steps = {"fews": [["research_cloud.training.fews_features", "--manifest", "/work/inputs/base.json", "--horizon", "4",
                   "--target", "2019-02", "--k", "0", "--strategy", "A", "--output", "/out/features"],
                  ["research_cloud.training.fews_fourclass", "--manifest", "/out/features/manifest.json",
                   "--config", "/work/inputs/config.json", "--output", "/out/trial"]],
         "ipcch": [["research_cloud.training.ipcch_features", "--manifest", "/work/inputs/base.json", "--horizon", "3",
                    "--output", "/out/features"],
                   ["research_cloud.training.ipcch_quartet", "--manifest", "/out/features/manifest.json",
                    "--config", "/work/inputs/config.json", "--output", "/out/trial", "--param", "rounds=50"]]}[fam]
for s in steps:
    subprocess.run(b + ["/usr/local/bin/python", "-m"] + s, check=True)
P
ls $OUT/trial/*/                               # trial.json (status, params, metrics, input/code hashes), metrics.json, package/
```

- **Reference objectives** with the unchanged code and config: FEWS crisis_f1 `0.7915766738660908`; IPCCH (rounds=50) `0.8626907073509015`. A different value after your change is your change.
- **Trial parameters:** `--param name=value`, repeatable; the Vertex form `--name=value` is also accepted.
- **Replay the produced package** in the same sandbox: `/usr/local/bin/python -m research_cloud.packages.replay /out/trial/<id>/package --report /out/replay.json`.
- **Unit tests:** run only the tests for what you changed, in that family's image or environment. The service venv lacks the scientific packages and the PostgreSQL fixture, so a whole-suite run there is not a meaningful gate.
- **Commit.** Images are built only from a committed, clean `research_cloud`.

## 4. Build an image (operator)

**Template**; the image is `training-fews` or `training-ipcch`, and the build SA and URI are those in `cloud-deployment-plan.md`:
```sh
python -m research_cloud.images.context --image training-ipcch --out CTX --image-uri us-central1-docker.pkg.dev/food-crisis-modeling-enso/research/training-ipcch --build-sa BUILD_SA_EMAIL
gcloud builds submit CTX --config CTX/cloudbuild.yaml --project=food-crisis-modeling-enso --async
```

- The build runs a self-check as uid 65534 with no network, and only then pushes. Record the digest; specs always reference `image@sha256:…`.
- A rebuild is not needed for changes that only affect the spec. The per-trial cap and the launcher are in the spec, not the image.

## 5. Submit a trial or an HPT study (operator)

The examples are the acceptance jobs. Run them after the §2 setup block (`W`, venv, `PYTHONPATH`).

1. **Cloud copies** of the snapshot manifest and config. The cloud manifest uses `/gcs/...` paths, and the config has no host source paths. Upload both **create-only** to `gs://food-crisis-modeling-enso-research-inputs/training-jobs/`. The acceptance copies are `$W/scratch/vertex/jobs/{manifest,config}-{ipcch-h03,fews-h4-2019-02}.json`; these commands reproduce the IPCCH pair byte for byte. For a new run, change the local snapshot, `--snapshot` (its folder under `training-snapshots/`) and the output names.
   ```sh
   python -m research_cloud.training.cloud_job manifest --local $W/scratch/training/features-h03-v2/manifest.json --snapshot features-h03-v2 --out $W/scratch/vertex/jobs/manifest-ipcch-h03.json
   python -m research_cloud.training.cloud_job config --local $W/scratch/training/config-ipcch-h03.json --out $W/scratch/vertex/jobs/config-ipcch-h03.json
   ```
2. **Spec.** `--local-config` is the local trial config; the HPT `space` and `objective` are read from it. These exact commands regenerate the submitted acceptance specs: FEWS trial byte-identical; IPCCH HPT identical except the d9ede46 cap wrapper.
   ```sh
   I=us-central1-docker.pkg.dev/food-crisis-modeling-enso/research; G=/gcs/food-crisis-modeling-enso-research-inputs/training-jobs
   U=https://research-mlflow-76571749286.us-central1.run.app
   # FEWS single trial (CustomJob)
   python -m research_cloud.training.cloud_job spec --adapter research_cloud.training.fews_fourclass \
     --image $I/training-fews@sha256:d7ac74a690e72e031ac9e7fe04612c6f851c023cef03023781fc5b67ed9f0456 --machine n1-standard-4 \
     --manifest $G/manifest-fews-h4-2019-02.json --config $G/config-fews-h4-2019-02.json --family fewsnet_pooled_fourclass \
     --local-config $W/scratch/training/config-fews-h4-2019-02.json --timeout-s 900 \
     --mlflow-uri $U --mlflow-experiment cloud-training-acceptance --out SPEC-fews.json
   # IPCCH HPT, 2 serial trials (HyperparameterTuningJob); PARENT = the parent run of step 3
   python -m research_cloud.training.cloud_job spec --adapter research_cloud.training.ipcch_quartet \
     --image $I/training-ipcch@sha256:6ad7f46ce03ed3e2db9533d77de87609572dee9a632b3b7b8c431e7fdab16a91 --machine n1-highmem-4 \
     --manifest $G/manifest-ipcch-h03.json --config $G/config-ipcch-h03.json --family ipcch_geoxgb_pooled_quartet \
     --local-config $W/scratch/training/config-ipcch-h03.json --timeout-s 900 --hpt 2 \
     --mlflow-uri $U --mlflow-experiment cloud-training-acceptance --parent-run PARENT \
     --entry /usr/local/bin/train-entry --out SPEC-hpt.json
   ```
   - `--entry /usr/local/bin/train-entry` is required for training-ipcch HPT: it hands `/var/hypertune` to uid 65534, then drops root.
   - **HPT per-trial cap:** the command starts `/usr/local/bin/train-entry /usr/bin/timeout --kill-after=30s 900s python …`. That sends TERM at 900 s and KILL at 930 s; the 30 s grace is inside the declared 600 s overhead, so it is not a hard 900 s.
   - **Study deadline:** trials × (timeout + 600 s), 3000 s here.
   - Every spec sets `disableRetries: true`.
3. **Parent run (HPT only)**, as `ipcch-jobwriter` (Secret Manager; operator; **not re-run**):
   ```python
   import os
   from mlflow.tracking import MlflowClient
   from research_cloud.deploy import provision_secrets as ps
   from research_cloud.deploy.mlflow_identities import cred
   os.environ["MLFLOW_TRACKING_USERNAME"], os.environ["MLFLOW_TRACKING_PASSWORD"] = cred(ps.Api(), "mlflow-jobwriter")
   c = MlflowClient("https://research-mlflow-76571749286.us-central1.run.app")
   parent = c.create_run(c.get_experiment_by_name("cloud-training-acceptance").experiment_id,
                         run_name="hpt-ipcch-h03-N", tags={"hpt.kind": "ipcch_geoxgb_pooled_quartet", "hpt.attempt": "N"})
   print(parent.info.run_id)                       # -> --parent-run
   ```
4. **Reserve** the cost before submitting. This snippet was tested on a copy of the ledger; admission accepts `SPEC-hpt.json` against this detail. Use a new, unique operation ID per submission.
   ```python
   from research_cloud.cost import ledger as L
   from research_cloud.cost.quote import sku
   W = "/home/swl007007/projects/food-crisis-research"; skus = f"{W}/scratch/p3/skus"
   core = sku(skus, "vertex.json", 1576, "2A57-4214-1832")[0]
   ram = sku(skus, "vertex.json", 8176, "DE93-D712-2AE4")[0]
   rate = 4 * core + 26 * ram                      # n1-highmem-4; n1-standard-4 is 4 * core + 15 * ram
   r = L.vertex_reservation(rate, 2, 900, 600, 100, 0.000063014)   # trials, timeout_s, overhead_s, boot GiB, disk $/GiB-h
   detail = {"quote": "HPT: 2 serial trials (ipcch_quartet), parallel 1", "machine": "n1-highmem-4", "usd_per_hour": rate,
             "trials": 2, "timeout_s": 900, "overhead_s": 600, "boot_disk_gib": 100,
             "billed_seconds_per_trial": r["billed_seconds_per_trial"]}
   L.reserve(L.connect(f"{W}/ledger/spend.sqlite"), "training", "2026-10", "G11-vertex-ipcch-hpt-N", r["total_usd"], detail)
   ```
   - The month is the current `YYYY-MM`. The training pool has its own USD 100/month envelope; `reserve` refuses beyond it.
   - Admission reads `machine`, `trials`, `timeout_s`, `overhead_s` and `boot_disk_gib` from this detail.
5. **Submit, then poll** (**not re-run**; paid job).
   ```sh
   python -m research_cloud.training.vertex_submit submit --spec SPEC-hpt.json --kind hpt --operation G11-vertex-ipcch-hpt-N --out $W/ledger/vertex/ipcch-hpt-N
   python -m research_cloud.training.vertex_submit poll --kind hpt --operation G11-vertex-ipcch-hpt-N --out $W/ledger/vertex/ipcch-hpt-N
   ```
   Use `--kind custom` for `SPEC-fews.json`.
   - Admission refuses a spec outside its reservation. That includes the wrong machine or trial count, retries enabled, and an HPT command without the exact cap prefix.
   - The claim is atomic. Never resubmit the same operation: a lost acknowledgement leaves the claim held, so run `vertex_submit reconcile --kind … --operation … --out …`.
   - The reservation is held until the provider reports a terminal state; it is not released from a list lookup.
6. **Harvest, then close the parent** (operator). Compare the Vertex trials (`final.json`) with the MLflow child runs and each run's `trial.json`. Download each trial's `package` and replay it (§7). The acceptance harvest is `$W/scratch/hpt3-harvest/harvest.py`. Then close the parent as `ipcch-jobwriter`, setting `vertex.hpt_job`, `vertex.hpt_state`, `vertex.hpt_end` and `ledger.operation` first:
   - `c.set_terminated(parent_id, status="FINISHED", end_time=<job end, ms>)` only after a successful harvest;
   - `FAILED` for a failed job, `KILLED` for a cancelled one.

   Until then the parent shows `RUNNING`.

## 6. Compare

- **MLflow UI:** the experiment's runs. HPT trials are child runs of the parent, tagged with `vertex.CLOUD_ML_JOB_ID`, `vertex.CLOUD_ML_TRIAL_ID`, `image_digest`, `source_commit` and `trial_status`. Each run's `trial.json` and `metrics.json` are artifacts.
- **Historical work:**
  - experiment `historical-packages` (one run per retained historical package, tags `package.name`, `package.json_sha256`, `package.status`);
  - registry versions carry reverse-link tags `package.run_id`, `package.name` and `package.json_sha256`;
  - the 29 `FEWS NET | …` registered models are package pointers, not pyfunc models.

## 7. Download, hash and load a model package (researcher)

1. **Download and verify with your own credentials** (§1 environment, §2 setup). The trusted `package.json` hash (run tag) binds the file list. `verify_package` then re-hashes every file against it **before** any package code is imported, because `loader/entry.py` and `load()` do not check weights or dependencies themselves.
   ```python
   import hashlib, mlflow
   from mlflow.tracking import MlflowClient
   c = MlflowClient()                                   # MLFLOW_TRACKING_URI / USERNAME / PASSWORD from the environment
   exp = c.get_experiment_by_name("historical-packages")
   run = c.search_runs([exp.experiment_id], "tags.`package.name` = 'geoxgb_reference-partitioned_gated-h01'")[0]
   path = mlflow.artifacts.download_artifacts(run_id=run.info.run_id, artifact_path="package", dst_path="pkg")
   assert hashlib.sha256(open(f"{path}/package.json", "rb").read()).hexdigest() == run.data.tags["package.json_sha256"]
   from research_cloud.packages.common import verify_package   # stdlib only; needs PYTHONPATH from §2
   problems = verify_package(path)       # every listed file (weights, deps, loader, reference) re-hashed; no extra files
   assert not problems, problems         # only now is the package trusted enough to import its loader
   ```
2. **Load and predict in the package's runtime image.** The runtime comes from `package.json`, through the image table above (here `rt-geoxgb-x300` → training-ipcch 36bde42). The package is mounted read-only at `/packages/package`:
   ```sh
   PKG=$(realpath pkg); W=/home/swl007007/projects/food-crisis-research; cd $W/control-plane    # run where pkg/ was downloaded
   PYTHONPATH=. python3 - "$W" "$PKG" <<'P'
   import json, subprocess, sys
   from research_cloud.images.rootfs_replay import sandbox
   W, pkg = sys.argv[1:]
   b = sandbox(f"{W}/scratch/image-pulls/training-ipcch.rootfs", json.load(open(f"{W}/scratch/image-pulls/training-ipcch.config.json")), pkg, "/tmp")
   code = """
   import importlib.util, json, numpy as np, pandas as pd
   p = "/packages/package"
   spec = importlib.util.spec_from_file_location("entry", p + "/loader/entry.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
   model = m.load(p)
   keys = json.load(open(p + "/package.json")).get("loader", {}).get("keys", ["admin_code", "target_ord"])
   X = np.load(p + "/reference/inputs.npy", allow_pickle=False)
   ref = pd.read_csv(p + "/reference/expected.csv", dtype={"unit": str})
   print(model.predict(ref[keys], X).head())
   """
   subprocess.run(b + ["/usr/local/bin/python", "-c", code], check=True)
   P
   ```
   `predict(keys, X)` takes the key columns plus rows in the package's `deps/feature_order.csv` order (NaN = missing).
3. **Full reference replay** (contract check): `/usr/local/bin/python -m research_cloud.packages.replay /packages/package --report /out/replay.json` in the same sandbox. For many packages use `research_cloud.images.rootfs_replay` (see its docstring), as in the 223-package acceptance.
4. **Historical exceptions:**
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

- **Platform pool** (SQL, Run, GCS, images, secrets, logging, assistant): about USD 80/month steady. The first month is about USD 92 with the one-time migration items. These are gross list estimates for this migration's resources, not billed spend and not a project-wide cap.
- **Training pool:** each Vertex job is reserved (§5.4) against its own USD 100/month.
- **Assistant:** the Gemini guard admits requests only within its USD 10/month allocation.
- **Ledger:** `$W/ledger/spend.sqlite` (operator).
