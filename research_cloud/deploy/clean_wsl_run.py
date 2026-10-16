"""AC8: a clean native-WSL checkout fetches its inputs from GCS, runs a small test, reads MLflow and downloads and loads
a historical package - with Dropbox and the original paths unavailable.

1. ``git clone`` of the control-plane repository at a given commit into a fresh directory; ``git status`` must be clean.
2. Everything else runs inside the pinned training image (bubblewrap sandbox, ``images.rootfs_replay.sandbox`` plus
   ``--share-net``): the image's own Python and libraries; ``PYTHONPATH`` = the clean checkout (read-only); only the
   checkout, an inputs directory (cloud base manifest + host-path-free config, read-only), the output directory and
   the operator's application-default credential file (read-only, for GCS reads) are bound. A probe proves
   ``/mnt/c`` and the host home are absent and ``research_cloud`` resolves to the checkout.
3. ``<family>_features`` builds the small feature snapshot from the ``gs://`` base manifest (every download is
   re-hashed); its file hashes are compared with the earlier host-built snapshot. The family's trial adapter then runs
   on it (local output, no MLflow write) and its objective is compared with the recorded value.
4. MLflow is read (experiment search) and one historical package is downloaded through the MLflow SDK, both as
   ``ipcch-reader`` (Basic auth; credential in a mode-600 file bound read-only, never on a command line, deleted
   afterwards), and replayed with the checkout's
   ``packages.replay``.

  python -m research_cloud.deploy.clean_wsl_run --family fews|ipcch --commit SHA --repo DIR --rootfs DIR
      --image-config FILE --inputs DIR --expected-snapshot MANIFEST --expected-objective X --package NAME --out DIR
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

from research_cloud.images.rootfs_replay import sandbox

FAMILY = {
    "fews": {"features": ["research_cloud.training.fews_features", "--manifest", "/work/inputs/base.json", "--horizon",
                          "4", "--target", "2019-02", "--k", "0", "--strategy", "A", "--output", "/out/features"],
             "trial": "research_cloud.training.fews_fourclass", "params": []},
    "ipcch": {"features": ["research_cloud.training.ipcch_features", "--manifest", "/work/inputs/base.json",
                           "--horizon", "3", "--output", "/out/features"],
              "trial": "research_cloud.training.ipcch_quartet", "params": ["--param", "rounds=50"]},
}
PROBE = ("import json, os, research_cloud; print(json.dumps({'mnt_c': os.path.exists('/mnt/c'), "
         "'host_home': os.path.exists(HOST_HOME), 'research_cloud': research_cloud.__file__, 'uid': os.getuid()}))")
READ = r"""
import json, os, sys
cred = json.load(open("/work/mlflow-reader.json"))      # mode 600 file, bound read-only; never on a command line
os.environ["MLFLOW_TRACKING_USERNAME"], os.environ["MLFLOW_TRACKING_PASSWORD"] = cred["username"], cred["password"]
import mlflow
from mlflow.tracking import MlflowClient
url, name = sys.argv[1], sys.argv[2]
c = MlflowClient(tracking_uri=url); mlflow.set_tracking_uri(url)
exps = [e.name for e in c.search_experiments()]
exp = c.get_experiment_by_name("historical-packages")
run = c.search_runs([exp.experiment_id], filter_string=f"tags.`package.name` = '{name}'", max_results=2)[0]
got = mlflow.artifacts.download_artifacts(run_id=run.info.run_id, artifact_path="package", dst_path="/out/pkg-dl")
print(json.dumps({"experiments": len(exps), "package_run": run.info.run_id, "downloaded": got,
                  "package_json_tag": run.data.tags.get("package.json_sha256")}))
"""


def sha256_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    return r.returncode, r.stdout, r.stderr


def main(argv=None, api=None):
    ap = argparse.ArgumentParser()
    for k in ("--family", "--commit", "--repo", "--rootfs", "--image-config", "--inputs", "--expected-snapshot",
              "--expected-objective", "--package", "--out", "--url"):
        ap.add_argument(k, required=True)
    args = ap.parse_args(argv)
    from research_cloud.deploy import provision_secrets as ps
    from research_cloud.deploy.mlflow_identities import cred
    fam = FAMILY[args.family]
    out = os.path.realpath(args.out)
    os.makedirs(out, exist_ok=False)
    report = {"family": args.family, "commit": args.commit, "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "steps": {}}
    checkout = os.path.join(out, "checkout")
    rc, _, err = run(["git", "clone", "--quiet", "--no-local", args.repo, checkout])
    rc2, _, _ = run(["git", "-C", checkout, "checkout", "--quiet", args.commit])
    rc3, status, _ = run(["git", "-C", checkout, "status", "--porcelain"])
    report["steps"]["clone"] = {"ok": rc == rc2 == rc3 == 0 and status.strip() == "",
                                "head": run(["git", "-C", checkout, "rev-parse", "HEAD"])[1].strip()}
    work = os.path.join(out, "sandbox-out")
    os.makedirs(work)
    adc = os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
    reader = cred(api or ps.Api(), "mlflow-reader")
    credfile = os.path.join(out, "mlflow-reader.json")
    fd = os.open(credfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"username": reader[0], "password": reader[1]}, f)
    base = sandbox(os.path.realpath(args.rootfs), json.load(open(args.image_config)), checkout, work)
    i = base.index("--clearenv")
    base[i:i] = ["--share-net", "--ro-bind", checkout, "/work/checkout", "--ro-bind", os.path.realpath(args.inputs),
                 "/work/inputs", "--ro-bind", adc, "/work/adc.json", "--ro-bind", credfile, "/work/mlflow-reader.json",
                 "--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf"]
    base += ["--setenv", "PYTHONPATH", "/work/checkout", "--setenv", "GOOGLE_APPLICATION_CREDENTIALS", "/work/adc.json",
             "--setenv", "IPCCH_GCP_PROJECT", "food-crisis-modeling-enso", "--setenv", "GIT_PYTHON_REFRESH", "quiet"]
    py = "/usr/local/bin/python"

    def step(name, cmd, timeout=3600):
        t0 = time.time()
        rc, so, se = run(base + [py] + cmd, timeout=timeout)
        report["steps"][name] = {"rc": rc, "seconds": round(time.time() - t0, 1), "stdout_tail": ps.scrub(so[-1500:]),
                                 "stderr_tail": ps.scrub(se[-1500:]) if rc else ""}
        print(json.dumps({"step": name, "rc": rc, "seconds": report["steps"][name]["seconds"]}), flush=True)
        return rc, so

    rc, so = step("probe", ["-c", PROBE.replace("HOST_HOME", repr(os.path.expanduser("~")))])
    probe = json.loads(so.strip().splitlines()[-1]) if rc == 0 else {}
    report["steps"]["probe"]["result"] = probe
    report["steps"]["probe"]["ok"] = probe.get("mnt_c") is False and probe.get("host_home") is False \
        and probe.get("research_cloud", "").startswith("/work/checkout/")
    rc, _ = step("features", ["-m"] + fam["features"])
    expected = json.load(open(args.expected_snapshot))["files"]
    built = json.load(open(os.path.join(work, "features", "manifest.json")))["files"] if rc == 0 else {}
    report["steps"]["features"]["hashes_equal_expected"] = {
        r: built.get(r, {}).get("sha256") == e["sha256"] for r, e in expected.items()}
    # trial on the rebuilt snapshot (its manifest's uris are the sandbox paths)
    rc, so = step("trial", ["-m", fam["trial"], "--manifest", "/out/features/manifest.json", "--config",
                            "/work/inputs/config.json", "--output", "/out/trials"] + fam["params"])
    metrics = json.loads(so.strip().splitlines()[-1]).get("metrics", {}) if rc == 0 and so.strip() else {}
    report["steps"]["trial"]["objective"] = metrics.get("crisis_f1")
    report["steps"]["trial"]["objective_equal_expected"] = metrics.get("crisis_f1") == float(args.expected_objective)
    rc, so = step("mlflow-read-and-download", ["-c", READ, args.url, args.package])
    dl = json.loads(so.strip().splitlines()[-1]) if rc == 0 else {}
    report["steps"]["mlflow-read-and-download"]["result"] = dl
    pkg = os.path.join(work, "pkg-dl", "package")
    ok_pkg = rc == 0 and os.path.exists(os.path.join(pkg, "package.json")) \
        and sha256_file(os.path.join(pkg, "package.json")) == dl.get("package_json_tag")
    report["steps"]["mlflow-read-and-download"]["package_json_equal_tag"] = ok_pkg
    rc, so = step("package-load-replay", ["-m", "research_cloud.packages.replay", "/out/pkg-dl/package", "--report",
                                          "/out/package-replay.json"])
    rep = json.load(open(os.path.join(work, "package-replay.json"))) if os.path.exists(os.path.join(work, "package-replay.json")) else {}
    report["steps"]["package-load-replay"]["passed"] = rep.get("passed")
    report["steps"]["package-load-replay"]["rows"] = rep.get("rows")
    report["ok"] = bool(report["steps"]["clone"]["ok"] and report["steps"]["probe"]["ok"]
                        and all(report["steps"]["features"]["hashes_equal_expected"].values())
                        and report["steps"]["trial"]["objective_equal_expected"] and ok_pkg and rep.get("passed") is True)
    os.remove(credfile)
    shutil.rmtree(checkout)                               # keep the evidence, not a second copy of the code
    with open(os.path.join(out, "report.json"), "w") as f:
        f.write(ps.scrub(json.dumps(report, indent=1, default=str)))
    print(json.dumps({"family": args.family, "ok": report["ok"]}))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
