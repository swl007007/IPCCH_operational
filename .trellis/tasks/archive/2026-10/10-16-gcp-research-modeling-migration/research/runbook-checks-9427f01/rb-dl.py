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