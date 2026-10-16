"""Package download acceptance: MLflow SDK with Basic auth only, then exact-image replay of what was downloaded.

The downloader runs in a child process whose environment holds only the ``ipcch-reader`` MLflow credential and the
tracking URI: no Google credentials (``GOOGLE_APPLICATION_CREDENTIALS`` unset, empty ``CLOUDSDK_CONFIG``, isolated
``HOME``), so every byte comes through the service's authenticated artifact proxy. For each run of experiment
``historical-packages`` (or ``--only`` names) it calls ``mlflow.artifacts.download_artifacts(run_id=…,
artifact_path="package")`` into a fresh directory ``OUT/packages/<name>/`` and checks that the downloaded
``package.json`` sha256 equals the run's ``package.json_sha256`` tag. Every file hash is then checked by the replay
itself (``packages.common.verify_package``) when ``images.rootfs_replay`` replays the downloaded directory inside each
image's sandbox.

  python -m research_cloud.deploy.package_download --url URL --out DIR --expected-packages PACKAGES_DIR
      [--only NAME ...] [--expect N]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

CHILD = r"""
import hashlib, json, os, sys, time
import mlflow
from mlflow.tracking import MlflowClient
url, out, only = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
client = MlflowClient(tracking_uri=url)
mlflow.set_tracking_uri(url)
exp = client.get_experiment_by_name("historical-packages")
runs, token = [], None
while True:
    page = client.search_runs([exp.experiment_id], max_results=500, page_token=token)
    runs += list(page)
    token = page.token
    if not token:
        break
rows = []
for run in sorted(runs, key=lambda r: r.data.tags.get("package.name", "")):
    name = run.data.tags["package.name"]
    if only and name not in only:
        continue
    if not run.info.artifact_uri.startswith("mlflow-artifacts:/"):
        raise SystemExit(f"{name}: artifact_uri {run.info.artifact_uri} is not the service's artifact proxy")
    dst = os.path.join(out, "packages", name)
    os.makedirs(dst, exist_ok=False)
    t0 = time.time()
    got = mlflow.artifacts.download_artifacts(run_id=run.info.run_id, artifact_path="package", dst_path=dst)
    for entry in os.listdir(got):                      # flatten .../<name>/package/* to .../<name>/*
        os.rename(os.path.join(got, entry), os.path.join(dst, entry))
    os.rmdir(got)
    sha = hashlib.sha256(open(os.path.join(dst, "package.json"), "rb").read()).hexdigest()
    nbytes = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(dst) for f in fs)
    rows.append({"package": name, "run_id": run.info.run_id, "files": sum(len(fs) for _, _, fs in os.walk(dst)),
                 "bytes": nbytes, "seconds": round(time.time() - t0, 1),
                 "package_json_sha256": sha, "tag_sha256": run.data.tags.get("package.json_sha256"),
                 "image": run.data.tags.get("package.replay_image"), "ok": sha == run.data.tags.get("package.json_sha256")})
    print(json.dumps(rows[-1]), flush=True)
json.dump(rows, open(os.path.join(out, "downloads.json"), "w"), indent=1)
"""


def main(argv=None, api=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--expect", type=int)
    ap.add_argument("--expected-packages", help="local frozen packages dir: the downloaded set must equal its names "
                                              "(or the --only subset) and each package.json must equal the local one")
    args = ap.parse_args(argv)
    from research_cloud.deploy import provision_secrets as ps
    from research_cloud.deploy.mlflow_identities import cred
    user, pw = cred(api or ps.Api(), "mlflow-reader")
    os.makedirs(args.out, exist_ok=False)
    home = tempfile.mkdtemp(prefix="pkg-dl-home-")
    env = {"PATH": "/usr/bin:/bin", "HOME": home, "CLOUDSDK_CONFIG": os.path.join(home, "gcloud-empty"),
           "MLFLOW_TRACKING_USERNAME": user, "MLFLOW_TRACKING_PASSWORD": pw, "MLFLOW_DISABLE_AGENT_HINT": "1",
           "PYTHONDONTWRITEBYTECODE": "1", "LANG": "C.UTF-8"}
    t0 = time.time()
    r = subprocess.run([sys.executable, "-c", CHILD, args.url, args.out, json.dumps(args.only)], env=env,
                       capture_output=True, text=True)
    sys.stdout.write(ps.scrub(r.stdout))
    if r.returncode != 0:
        sys.stderr.write(ps.scrub(r.stderr[-3000:]))
        return r.returncode
    rows = json.load(open(os.path.join(args.out, "downloads.json")))
    summary = {"packages": len(rows), "ok": sum(x["ok"] for x in rows), "bytes": sum(x["bytes"] for x in rows),
               "files": sum(x["files"] for x in rows), "seconds": round(time.time() - t0, 1),
               "identity": "ipcch-reader (MLflow Basic auth); no Google credentials in the downloader"}
    json.dump(summary, open(os.path.join(args.out, "summary.json"), "w"), indent=1)
    print(json.dumps(summary))
    if args.expected_packages:
        import hashlib
        expected = sorted(n for n in os.listdir(args.expected_packages) if not args.only or n in args.only)
        got = sorted(x["package"] for x in rows)
        local = {n: hashlib.sha256(open(os.path.join(args.expected_packages, n, "package.json"), "rb").read()).hexdigest()
                 for n in expected}
        summary["set_equal"] = got == expected
        summary["missing"], summary["extra"] = sorted(set(expected) - set(got)), sorted(set(got) - set(expected))
        summary["package_json_differs_from_local"] = sorted(x["package"] for x in rows
                                                            if local.get(x["package"]) != x["package_json_sha256"])
        json.dump(summary, open(os.path.join(args.out, "summary.json"), "w"), indent=1)
        print(json.dumps({k: summary[k] for k in ("set_equal", "missing", "extra", "package_json_differs_from_local")}))
        if not summary["set_equal"] or summary["package_json_differs_from_local"]:
            return 1
    if args.expect is not None and len(rows) != args.expect:
        return 1
    return 0 if summary["ok"] == summary["packages"] else 1


if __name__ == "__main__":
    sys.exit(main())
