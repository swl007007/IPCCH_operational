"""In-image self-check, run by Cloud Build against the BUILT image as the runtime user (UID 65534) before any push.

service: HOME is writable and ``start.write_assistant_config`` (the deny-mode start-up write) succeeds there; the
service hook ``.pth`` is installed in site-packages and a fresh interpreter loads the hook in deny mode
(``start.verify_hook``, the same check start-up runs); MLflow is the pinned 3.17.0; the ``ipcch-model`` wrapper is
executable.
training-fews / training-ipcch: HOME and /tmp are writable; the pinned scientific source imports from ``/app/sources``;
the image's control-plane commit is set and ``adapter_identity`` reports it.
replay-x320 / replay-forecast-x320: HOME is writable; every installed distribution equals ``/app/requirements.lock.txt``
(the exact freeze of the tested replay environment) and the replay entry point imports.

  python -m research_cloud.images.selfcheck --image service|training-fews|training-ipcch|replay-x320|replay-forecast-x320
Exit 0 and one JSON line on success; any failure raises (non-zero exit), which stops the build before the push.
"""
import argparse
import json
import os
import sys
import tempfile


def writable(path):
    os.makedirs(path, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path):
        pass
    return path


def service():
    import site
    from importlib.metadata import version

    from research_cloud.service import start
    home = os.environ["HOME"]
    writable(home)
    env = {**os.environ, "IPCCH_ASSISTANT_MODE": "deny", "IPCCH_SERVICE_HOOK": "1"}
    start.write_assistant_config("deny", env, home)
    pth = [p for p in site.getsitepackages() if os.path.exists(os.path.join(p, "ipcch_service_hook.pth"))]
    if not pth:
        raise RuntimeError("ipcch_service_hook.pth is not installed in site-packages")
    state = start.verify_hook(env, "deny")
    if version("mlflow") != "3.17.0":
        raise RuntimeError(f"mlflow {version('mlflow')}")
    wrapper = "/usr/local/bin/ipcch-model"
    if not os.access(wrapper, os.X_OK):
        raise RuntimeError(f"{wrapper} is not executable")
    return {"home": home, "pth": pth[0], "hook": state, "mlflow": version("mlflow")}


def training(image):
    sys.dont_write_bytecode = True
    from research_cloud.training.common import adapter_identity
    writable(os.environ["HOME"])
    writable("/tmp/hypertune")
    if image == "training-fews":
        src = os.environ["FEWS_SRC"]
        sys.path[:0] = [src, os.path.join(src, "scripts")]
        from src.experiment import plan, stage3  # noqa: F401
        from src.model import native_xgb  # noqa: F401
        import run_experiment  # noqa: F401
        from research_cloud.training import fews_features, fews_fourclass  # noqa: F401
    else:
        sys.path.insert(0, os.environ["IPCCH_GEOXGB_SRC"])
        from ipcch_geoxgb import features, prepare, projection, quartet  # noqa: F401
        from research_cloud.training import ipcch_features, ipcch_quartet  # noqa: F401
    ident = adapter_identity("research_cloud.training.common")
    if not ident["control_plane_commit"]:
        raise RuntimeError("the image does not carry its control-plane commit (IPCCH_SOURCE_COMMIT)")
    return {"home": os.environ["HOME"], "commit": ident["control_plane_commit"]}


def replay():
    from importlib.metadata import distributions

    from research_cloud.packages import replay as _replay  # noqa: F401
    writable(os.environ["HOME"])
    lock = dict(line.strip().split("==", 1) for line in open("/app/requirements.lock.txt") if "==" in line)
    installed = {d.metadata["Name"].lower().replace("_", "-"): d.version for d in distributions()}
    wrong = {k: (v, installed.get(k.lower().replace("_", "-"))) for k, v in lock.items()
             if installed.get(k.lower().replace("_", "-")) != v}
    if wrong:
        raise RuntimeError(f"installed distributions differ from the lock: {wrong}")
    return {"home": os.environ["HOME"], "lock_pins": len(lock)}


def hypertune_write():
    """Run under train-entry as Vertex HPT does: uid 65534, and the objective report must land in the metric file."""
    import hypertune
    if os.getuid() != 65534 or os.getgid() != 65534 or os.getgroups() not in ([], [65534]):
        raise RuntimeError(f"not dropped to 65534: uid {os.getuid()} gid {os.getgid()} groups {os.getgroups()}")
    hypertune.HyperTune().report_hyperparameter_tuning_metric(hyperparameter_metric_tag="probe", metric_value=1.0,
                                                              global_step=1)
    path = os.environ["CLOUD_ML_HP_METRIC_FILE"]
    rows = [json.loads(line) for line in open(path) if line.strip()]
    if not any(float(r.get("probe", "nan")) == 1.0 for r in rows):
        raise RuntimeError(f"metric not written to {path}: {rows}")
    return {"hypertune_file": path, "uid": os.getuid()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True,
                    choices=("service", "training-fews", "training-ipcch", "replay-x320", "replay-forecast-x320"))
    ap.add_argument("--hypertune", action="store_true", help="training-ipcch: check the HPT metric write under train-entry")
    args = ap.parse_args(argv)
    if args.hypertune:
        print(json.dumps({"selfcheck": "ok", "image": args.image, **hypertune_write()}))
        return 0
    result = (service() if args.image == "service" else replay() if args.image.startswith("replay-")
              else training(args.image))
    print(json.dumps({"selfcheck": "ok", "image": args.image, "uid": os.getuid(), **result}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
