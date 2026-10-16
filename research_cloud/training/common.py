"""Shared trial harness for thin research training adapters (new Linux identities; historical locks untouched).

A trial takes: an input manifest (every file with its sha256, hashed before use), an experiment config (fixed
parameters, the allowed tuning space, declared development folds and the holdout start), trial parameters, an output
prefix (local directory or ``gs://bucket/prefix``) and an MLflow identity. GCS access is bound explicitly to
``food-crisis-modeling-enso`` (client project and quota project); any other project is refused. It records the source commit, image digest,
runtime, parameters, input digests, fitting-key digest, metrics and failure state, and reports the objective to
Vertex AI hyperparameter tuning through ``cloudml-hypertune`` when it is installed (its documented
``/tmp/hypertune/output.metrics`` file otherwise). A missing or undefined objective fails the trial.
"""
import hashlib
import json
import math
import os
import platform
import sys
import tempfile
import time
import traceback


class TrialError(Exception):
    """A trial that must fail rather than report a metric."""


TARGET_PROJECT = "food-crisis-modeling-enso"


def storage_client(project):
    """A GCS client bound explicitly to the target project (also the quota project); no default inheritance."""
    if project != TARGET_PROJECT:
        raise TrialError(f"GCS access is limited to {TARGET_PROJECT}, not {project!r}")
    from google.cloud import storage
    return storage.Client(project=project, client_options={"quota_project_id": project})


def gcs_project(manifest=None):
    project = (manifest or {}).get("gcp_project") or os.environ.get("IPCCH_GCP_PROJECT")
    if not project:
        raise TrialError("gs:// access needs an explicit project (manifest gcp_project or IPCCH_GCP_PROJECT)")
    return project


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def resolve_inputs(manifest_path, workdir):
    """{role: local path} for every manifest file, fetched from GCS when needed and hashed before use."""
    manifest = json.load(open(manifest_path))
    out = {}
    for role, entry in manifest["files"].items():
        uri, expected = entry["uri"], entry["sha256"]
        if uri.startswith("gs://"):
            bucket, _, name = uri[5:].partition("/")
            local = os.path.join(workdir, "inputs", role + "_" + os.path.basename(name))
            os.makedirs(os.path.dirname(local), exist_ok=True)
            storage_client(gcs_project(manifest)).bucket(bucket).blob(name).download_to_filename(local)
        else:
            local = uri
        actual = sha256_file(local)
        if actual != expected:
            raise TrialError(f"input {role} sha256 {actual} differs from the manifest {expected}")
        out[role] = local
    return out, manifest


def validate_params(trial, space, fixed):
    """Trial values must be inside the declared space; fixed keys can never be overridden."""
    overlap = sorted(set(space) & set(fixed))
    if overlap:   # a space default would silently replace a fixed value
        raise TrialError(f"config declares {overlap} both fixed and tunable")
    clash = sorted(set(trial) & set(fixed))
    if clash:
        raise TrialError(f"trial parameters may not override fixed keys {clash}")
    unknown = sorted(set(trial) - set(space))
    if unknown:
        raise TrialError(f"trial parameters outside the declared space: {unknown}")
    out = {}
    for name, spec in space.items():
        value = trial.get(name, spec.get("default"))
        if value is None:
            raise TrialError(f"parameter {name} has no value and no default")
        if spec["type"] == "int":
            if float(value) != int(float(value)):
                raise TrialError(f"{name} must be an integer")
            value = int(float(value))
        else:
            value = float(value)
            if not math.isfinite(value):
                raise TrialError(f"{name} must be finite")
        if not spec["min"] <= value <= spec["max"]:
            raise TrialError(f"{name}={value} outside [{spec['min']}, {spec['max']}]")
        out[name] = value
    return out


def report_objective(tag, value, step=1):
    """Vertex HPT metric report; refuses a missing/undefined objective."""
    if value is None or not math.isfinite(value):
        raise TrialError(f"objective {tag} is undefined; the trial fails instead of reporting it")
    try:
        import hypertune
        hypertune.HyperTune().report_hyperparameter_tuning_metric(
            hyperparameter_metric_tag=tag, metric_value=float(value), global_step=step)
        return "cloudml-hypertune"
    except ImportError:
        path = os.environ.get("CLOUD_ML_HP_METRIC_FILE", "/tmp/hypertune/output.metrics")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps({tag: float(value), "global_step": str(step), "timestamp": time.time(),
                                "trial": os.environ.get("CLOUD_ML_TRIAL_ID", "")}) + "\n")
        return path


class Output:
    """Write trial artifacts under a local directory or a gs:// prefix."""

    def __init__(self, prefix):
        self.prefix = prefix.rstrip("/")
        self.local = tempfile.mkdtemp(prefix="trial-") if prefix.startswith("gs://") else self.prefix
        os.makedirs(self.local, exist_ok=True)

    def path(self, name):
        p = os.path.join(self.local, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p

    def write_json(self, name, value):
        with open(self.path(name), "w") as f:
            json.dump(value, f, indent=1, default=str)

    def publish(self, project=None):
        if not self.prefix.startswith("gs://"):
            return self.prefix
        bucket, _, base = self.prefix[5:].partition("/")
        client = storage_client(project or gcs_project())
        for root, _, files in os.walk(self.local):
            for name in files:
                rel = os.path.relpath(os.path.join(root, name), self.local)
                client.bucket(bucket).blob(f"{base}/{rel}").upload_from_filename(os.path.join(root, name))
        return self.prefix


def runtime_identity():
    import importlib.metadata as md
    pkgs = {}
    for name in ("numpy", "pandas", "xgboost", "scikit-learn", "mlflow-skinny", "mlflow", "cloudml-hypertune"):
        try:
            pkgs[name] = md.version(name)
        except md.PackageNotFoundError:
            pass
    return {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine(),
            "packages": pkgs, "image_digest": os.environ.get("IPCCH_IMAGE_DIGEST"),
            "source_commit": os.environ.get("IPCCH_SOURCE_COMMIT"),
            "vertex": {k: os.environ.get(k) for k in ("CLOUD_ML_JOB_ID", "CLOUD_ML_TRIAL_ID", "AIP_MODEL_DIR") if os.environ.get(k)}}


def mlflow_log(experiment, record, artifacts_dir):
    """Log every trial, succeeded or failed, to the configured MLflow server (job identity credentials from env).
    A failed trial is a FAILED run carrying its arguments, error and trial record; metrics only when defined."""
    if not os.environ.get("MLFLOW_TRACKING_URI"):
        return None
    import mlflow
    mlflow.set_experiment(experiment)
    vertex = record["runtime"]["vertex"]
    tags = {"trial_status": record["status"], **{f"vertex.{k}": v for k, v in vertex.items()},
            "image_digest": record["runtime"].get("image_digest") or "", "source_commit": record["runtime"].get("source_commit") or ""}
    if os.environ.get("IPCCH_PARENT_RUN_ID"):
        tags["mlflow.parentRunId"] = os.environ["IPCCH_PARENT_RUN_ID"]
    if record["status"] == "failed":
        tags["error"] = record.get("error", "")[:4000]
    with mlflow.start_run(run_name=vertex.get("CLOUD_ML_TRIAL_ID") or None, tags=tags) as run:
        mlflow.log_params(record.get("params") or {f"arg.{k}": v for k, v in record["trial_arguments"].items()})
        mlflow.log_metrics({k: v for k, v in (record.get("metrics") or {}).items()
                            if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)})
        mlflow.log_artifacts(artifacts_dir)
        run_id = run.info.run_id
    if record["status"] == "failed":
        mlflow.tracking.MlflowClient().set_terminated(run_id, status="FAILED")
    return run_id


def trial_prefix(output):
    """Each job/trial writes under its own subprefix; an existing trial record is never overwritten."""
    job = os.environ.get("CLOUD_ML_JOB_ID") or "local-" + time.strftime("%Y%m%dT%H%M%S") + f"-{os.getpid()}"
    trial = os.environ.get("CLOUD_ML_TRIAL_ID") or "0"
    prefix = f"{output.rstrip('/')}/{job}/trial-{trial}"
    if not prefix.startswith("gs://") and os.path.exists(os.path.join(prefix, "trial.json")):
        raise SystemExit(f"{prefix} already holds a trial record")
    return prefix


def run_trial(fit, argv=None, objective=None):
    """CLI wrapper: --manifest --config --output [--param name=value ...] [--mlflow-experiment NAME].
    Vertex HPT passes trial values as --name=value arguments; they are accepted the same way."""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--mlflow-experiment")
    ap.add_argument("--param", action="append", default=[])
    args, extra = ap.parse_known_args(argv)
    trial = dict(p.split("=", 1) for p in args.param)
    for item in extra:   # Vertex HPT: --name=value
        if not item.startswith("--") or "=" not in item:
            raise SystemExit(f"unrecognised argument {item}")
        k, v = item[2:].split("=", 1)
        trial[k] = v
    out = Output(trial_prefix(args.output))
    record = {"status": "started", "runtime": runtime_identity(), "trial_arguments": trial, "started": time.time(),
              "output": out.prefix}
    manifest = {}
    try:
        config = json.load(open(args.config))
        record["config"] = config
        if objective is not None and config.get("objective") != objective:
            raise TrialError(f"this adapter reports {objective!r}, the config declares {config.get('objective')!r}")
        inputs, manifest = resolve_inputs(args.manifest, out.local)
        record["input_sha256"] = {r: e["sha256"] for r, e in manifest["files"].items()}
        record["input_manifest"] = {"sha256": sha256_file(args.manifest), "content": manifest}   # incl. derived_from
        params = validate_params(trial, config["space"], config["fixed"])
        record.update(params=params, resolved_params={**config["fixed"], **params})
        out.write_json("trial.json", record)   # provenance persists even if fit raises
        result = fit(inputs, manifest, config, params, out)
        record.update(status="succeeded", **result)
        record["objective_report"] = report_objective(config["objective"], result["metrics"].get(config["objective"]))
    except Exception as e:
        record.update(status="failed", error=f"{type(e).__name__}: {e}", traceback=traceback.format_exc()[-4000:])
    record["finished"] = time.time()
    out.write_json("trial.json", record)
    if args.mlflow_experiment:   # failed trials are recorded too
        try:
            record["mlflow_run_id"] = mlflow_log(args.mlflow_experiment, record, out.local)
        except Exception as e:
            record["mlflow_error"] = f"{type(e).__name__}: {e}"
            if record["status"] == "succeeded":
                record.update(status="failed", error="MLflow linkage failed: " + record["mlflow_error"])
        out.write_json("trial.json", record)
    # explicit project; the target constant applies only when the manifest itself could not be read (failure record)
    out.publish(manifest.get("gcp_project") or os.environ.get("IPCCH_GCP_PROJECT") or TARGET_PROJECT)
    print(json.dumps({k: record.get(k) for k in ("status", "error", "metrics")}, default=str))
    return 0 if record["status"] == "succeeded" else 1


if __name__ == "__main__":
    sys.exit("use an adapter module")
