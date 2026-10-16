"""Vertex job launcher for the 36bde42 training images (inline ``python -c`` in the job spec; no image rebuild).

The job writer's MLflow credential stays in Secret Manager: the launcher reads ``mlflow-jobwriter`` (pinned version)
with the job's own service-account credentials (``research-trainer`` holds secretAccessor on that secret only), sets
``MLFLOW_TRACKING_USERNAME`` / ``_PASSWORD`` in this process only (never in the job resource) and runs the adapter as
``__main__`` (so ``harness_identity`` still resolves the adapter module), passing every remaining argument through -
including Vertex HPT's ``--name=value`` trial parameters. ``LAUNCHER`` is the exact source placed in the spec.
"""
import hashlib

SECRET = "projects/food-crisis-modeling-enso/secrets/mlflow-jobwriter/versions/1"

LAUNCHER = f"""import base64, json, os, runpy, sys
import google.auth
from google.auth.transport.requests import AuthorizedSession
creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
r = AuthorizedSession(creds).get("https://secretmanager.googleapis.com/v1/{SECRET}:access", timeout=60)
r.raise_for_status()
c = json.loads(base64.b64decode(r.json()["payload"]["data"]))
os.environ["MLFLOW_TRACKING_USERNAME"], os.environ["MLFLOW_TRACKING_PASSWORD"] = c["username"], c["password"]
module, sys.argv = sys.argv[1], [sys.argv[1]] + sys.argv[2:]
runpy.run_module(module, run_name="__main__", alter_sys=True)
"""

LAUNCHER_SHA256 = hashlib.sha256(LAUNCHER.encode()).hexdigest()
