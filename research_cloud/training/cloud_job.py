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
run id). Every spec sets ``IPCCH_IMAGE_DIGEST`` to the image's digest, which the baked harness records as the trial's
image identity; ``--mlflow-experiment`` is passed to the harness.

  python -m research_cloud.training.cloud_job manifest --local M.json --snapshot NAME --out CLOUD_M.json
  python -m research_cloud.training.cloud_job base-manifest --local BASE.json --receipts R.jsonl ... --out CLOUD_BASE.json
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
HPT_OVERHEAD_S = 600          # = the reservation's declared per-trial startup/termination overhead
KILL_AFTER = "30s"            # TERM at timeout_s, KILL 30 s later (inside HPT_OVERHEAD_S)


def cap_command(timeout_s):
    """Per-trial cap: coreutils timeout (present in both training images) runs the trial as its child, so the trial is
    never the container's PID 1 (PID 1 ignores signals it has no handler for, so an in-process SIGALRM is no cap).
    It sends TERM at ``timeout_s`` (900 s: TERM at 900 s) and KILL ``KILL_AFTER`` later (KILL at 930 s); the 30 s
    grace lies inside the declared 600 s per-trial overhead, so the bound is "TERM 900 s / KILL 930 s", not a hard
    900 s."""
    return ["/usr/bin/timeout", f"--kill-after={KILL_AFTER}", f"{int(timeout_s)}s"]


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


def gcs_base_manifest(local_path, receipt_paths):
    """A cloud copy of a base-input manifest: every file becomes the ``gs://`` object whose verified transfer receipt
    has exactly its sha256 (preferring the receipt for the same local path), with the object generation recorded;
    ``resolve_inputs`` re-hashes each download before use. A file without a verified object refuses."""
    m = json.load(open(local_path))
    by_sha = {}
    for path in receipt_paths:
        for line in open(path):
            r = json.loads(line)
            if r.get("status", "").startswith("verified") and r.get("bucket"):
                by_sha.setdefault(r["local_sha256"], []).append(r)
    files = {}
    for role, e in m["files"].items():
        found = sorted(by_sha.get(e["sha256"], []), key=lambda r: (r["local"] != e["uri"], r["object"]))
        if not found:
            raise SystemExit(f"{role}: no verified GCS object with sha256 {e['sha256']}")
        r = found[0]
        files[role] = {"uri": f"gs://{r['bucket']}/{r['object']}", "sha256": e["sha256"], "gcs_generation": r["generation"]}
    derived = {"local_manifest": {"path": os.path.abspath(local_path), "sha256": sha256_file(local_path)}}
    return {**{k: v for k, v in m.items() if k != "files"}, "gcp_project": PROJECT, "files": files,
            "derived_from": {**(m.get("derived_from") or {}), **derived}}


def cloud_config(local_path):
    c = json.load(open(local_path))
    return {k: v for k, v in c.items() if k not in HOST_KEYS}


def spec(adapter, image, machine, manifest, config, family, timeout_s, hpt=None, objective=None, space=None,
         mlflow_uri=None, experiment=None, parent_run=None, entry=None):
    if "@sha256:" not in image:
        raise SystemExit("the image must be given by digest")
    args = ["--manifest", manifest, "--config", config, "--output", f"gs://{ARTIFACTS}/trials/{family}"]
    # the baked harness records IPCCH_IMAGE_DIGEST as the trial's image identity (runtime_identity/adapter_identity)
    digest_env = [{"name": "IPCCH_IMAGE_DIGEST", "value": image.split("@", 1)[1]}]
    container = {"imageUri": image, "command": ["python", "-m", adapter], "args": args, "env": digest_env}
    if entry:            # the image's root-start entry (training-ipcch: hands /var/hypertune to 65534, then drops)
        container["command"] = [entry] + container["command"]
    if mlflow_uri:
        # MLflow linkage: the job writer's credential is read at run time by the launcher (never in the spec)
        from research_cloud.training.vertex_launch import LAUNCHER
        container = {"imageUri": image, "command": ([entry] if entry else []) + ["python", "-c", LAUNCHER, adapter],
                     "args": args + ["--mlflow-experiment", experiment],
                     "env": digest_env + [{"name": "MLFLOW_TRACKING_URI", "value": mlflow_uri},
                             {"name": "IPCCH_GCP_PROJECT", "value": PROJECT}]
                     + ([{"name": "IPCCH_PARENT_RUN_ID", "value": parent_run}] if parent_run else [])}
    job_spec = {"workerPoolSpecs": [{"machineSpec": {"machineType": machine}, "replicaCount": "1",
                                     "containerSpec": container}],
                "serviceAccount": TRAINER,
                "scheduling": {"timeout": f"{int(timeout_s)}s", "disableRetries": True,
                               "restartJobOnWorkerRestart": False}}
    labels = {"task": "gcp-research-modeling-migration", "family": family.replace("_", "-")[:63]}
    if hpt:
        # the observed HPT parent deadline is the trialJobSpec timeout from the study's start, so it must cover the serial
        # study (each trial's run + provisioning overhead, as reserved); each trial keeps its own hard cap through the
        # coreutils timeout wrapper in its command
        if not mlflow_uri:
            raise SystemExit("HPT specs use the launcher (it enforces the per-trial cap)")
        job_spec["scheduling"]["timeout"] = f"{int(hpt * (timeout_s + HPT_OVERHEAD_S))}s"
        cmd = container["command"]
        at = 1 if entry else 0                      # after the root-start entry, before python
        container["command"] = cmd[:at] + cap_command(timeout_s) + cmd[at:]
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
    g = sub.add_parser("base-manifest")
    g.add_argument("--local", required=True)
    g.add_argument("--receipts", nargs="+", required=True)
    g.add_argument("--out", required=True)
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
    s.add_argument("--entry", help="image entry wrapper to prefix (training-ipcch: /usr/local/bin/train-entry)")
    args = ap.parse_args(argv)
    if args.cmd == "manifest":
        out = cloud_manifest(args.local, args.snapshot)
    elif args.cmd == "base-manifest":
        out = gcs_base_manifest(args.local, args.receipts)
    elif args.cmd == "config":
        out = cloud_config(args.local)
    else:
        cfg = json.load(open(args.local_config))
        out = spec(args.adapter, args.image, args.machine, args.manifest, args.config, args.family, args.timeout_s,
                   args.hpt, cfg.get("objective"), cfg.get("space"), args.mlflow_uri, args.mlflow_experiment,
                   args.parent_run, args.entry)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps({"wrote": args.out, "sha256": sha256_file(args.out)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
