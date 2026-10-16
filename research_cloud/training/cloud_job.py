"""Cloud job inputs and Vertex AI specs for the training adapters (prepared locally; submission is separate).

``manifest``: a cloud copy of a local feature-snapshot manifest. Every file's ``uri`` becomes its Vertex AI Cloud
Storage FUSE path ``/gcs/<inputs bucket>/training-snapshots/<snapshot>/<file>`` (the bucket objects were transferred
create-only with fresh hashes); every sha256 is unchanged and is re-checked by the harness before use. ``gcp_project``
is set to the target project; ``derived_from`` keeps the local manifest's own ``derived_from`` and adds the local
manifest path and sha256.

``config``: a cloud copy of a trial config without host source paths (``fews_src``/``geoxgb_src``); in the images the
sources come from ``FEWS_SRC`` / ``IPCCH_GEOXGB_SRC`` under ``/app/sources``.

``spec``: a CustomJob (or HyperparameterTuningJob) request body: image by digest, the dedicated trainer service
account, one replica of the quoted machine type, ``python -m <adapter> --manifest /gcs/... --config /gcs/...
--output gs://<artifacts>/trials/<family>`` and, for HPT, the config's tuning space with the declared objective
maximized, ``maxTrialCount``/``parallelTrialCount`` as given. Scheduling sets ``disableRetries: true`` (no retry
after internal errors once the job runs; it also overrides ``restartJobOnWorkerRestart``, which alone only concerns
restarting a whole distributed job) and the per-trial ``timeout``. With ``--mlflow-uri`` the command is the
``vertex_launch.LAUNCHER`` source (reads the job writer's credential from Secret Manager at run time) followed by the
adapter module, and the container env carries only non-secret settings (tracking URI, project, optional HPT parent
run id); ``--mlflow-experiment`` is passed to the harness.

  python -m research_cloud.training.cloud_job manifest --local M.json --snapshot NAME --out CLOUD_M.json
  python -m research_cloud.training.cloud_job config --local C.json --out CLOUD_C.json
  python -m research_cloud.training.cloud_job spec --adapter MODULE --image URI@sha256:... --machine TYPE
      --manifest /gcs/... --config /gcs/... --family NAME [--hpt TRIALS] --timeout-s N --out SPEC.json
"""
import argparse
import hashlib
import json
import os
import sys

PROJECT = "food-crisis-modeling-enso"
INPUTS = f"{PROJECT}-research-inputs"
ARTIFACTS = f"{PROJECT}-research-artifacts"
TRAINER = f"research-trainer@{PROJECT}.iam.gserviceaccount.com"
HOST_KEYS = ("fews_src", "geoxgb_src")


def sha256_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def cloud_manifest(local_path, snapshot):
    m = json.load(open(local_path))
    files = {}
    for role, e in m["files"].items():
        files[role] = {**e, "uri": f"/gcs/{INPUTS}/training-snapshots/{snapshot}/{os.path.basename(e['uri'])}"}
    derived = dict(m.get("derived_from") or {})
    derived["local_manifest"] = {"path": os.path.abspath(local_path), "sha256": sha256_file(local_path)}
    return {**m, "gcp_project": PROJECT, "files": files, "derived_from": derived}


def cloud_config(local_path):
    c = json.load(open(local_path))
    return {k: v for k, v in c.items() if k not in HOST_KEYS}


def spec(adapter, image, machine, manifest, config, family, timeout_s, hpt=None, objective=None, space=None,
         mlflow_uri=None, experiment=None, parent_run=None):
    if "@sha256:" not in image:
        raise SystemExit("the image must be given by digest")
    args = ["--manifest", manifest, "--config", config, "--output", f"gs://{ARTIFACTS}/trials/{family}"]
    container = {"imageUri": image, "command": ["python", "-m", adapter], "args": args}
    if mlflow_uri:
        # MLflow linkage: the job writer's credential is read at run time by the launcher (never in the spec)
        from research_cloud.training.vertex_launch import LAUNCHER
        container = {"imageUri": image, "command": ["python", "-c", LAUNCHER, adapter],
                     "args": args + ["--mlflow-experiment", experiment],
                     "env": [{"name": "MLFLOW_TRACKING_URI", "value": mlflow_uri},
                             {"name": "IPCCH_GCP_PROJECT", "value": PROJECT}]
                     + ([{"name": "IPCCH_PARENT_RUN_ID", "value": parent_run}] if parent_run else [])}
    job_spec = {"workerPoolSpecs": [{"machineSpec": {"machineType": machine}, "replicaCount": "1",
                                     "containerSpec": container}],
                "serviceAccount": TRAINER,
                "scheduling": {"timeout": f"{int(timeout_s)}s", "disableRetries": True,
                               "restartJobOnWorkerRestart": False}}
    labels = {"task": "gcp-research-modeling-migration", "family": family.replace("_", "-")[:63]}
    if not hpt:
        return {"displayName": f"{family}-trial", "jobSpec": job_spec, "labels": labels}
    params = []
    for name, s in sorted(space.items()):
        kind = {"int": "integerValueSpec", "float": "doubleValueSpec"}[s["type"]]
        params.append({"parameterId": name, kind: {"minValue": s["min"], "maxValue": s["max"]},
                       "scaleType": "UNIT_LINEAR_SCALE"})
    return {"displayName": f"{family}-hpt", "maxTrialCount": hpt, "parallelTrialCount": 1, "maxFailedTrialCount": 1,
            "studySpec": {"metrics": [{"metricId": objective, "goal": "MAXIMIZE"}], "parameters": params,
                          "algorithm": "RANDOM_SEARCH"},
            "trialJobSpec": job_spec, "labels": labels}


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("manifest")
    m.add_argument("--local", required=True)
    m.add_argument("--snapshot", required=True)
    m.add_argument("--out", required=True)
    c = sub.add_parser("config")
    c.add_argument("--local", required=True)
    c.add_argument("--out", required=True)
    s = sub.add_parser("spec")
    for k in ("--adapter", "--image", "--machine", "--manifest", "--config", "--family", "--out", "--local-config"):
        s.add_argument(k, required=True)
    s.add_argument("--timeout-s", type=int, required=True)
    s.add_argument("--hpt", type=int)
    s.add_argument("--mlflow-uri")
    s.add_argument("--mlflow-experiment")
    s.add_argument("--parent-run")
    args = ap.parse_args(argv)
    if args.cmd == "manifest":
        out = cloud_manifest(args.local, args.snapshot)
    elif args.cmd == "config":
        out = cloud_config(args.local)
    else:
        cfg = json.load(open(args.local_config))
        out = spec(args.adapter, args.image, args.machine, args.manifest, args.config, args.family, args.timeout_s,
                   args.hpt, cfg.get("objective"), cfg.get("space"), args.mlflow_uri, args.mlflow_experiment,
                   args.parent_run)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps({"wrote": args.out, "sha256": sha256_file(args.out)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
