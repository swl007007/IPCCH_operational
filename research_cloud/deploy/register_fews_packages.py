"""AC2: navigable FEWS NET registry entries - one registered model per FEWS package, version 1 pointing at its package.

FEWS NET runs were never in the MLflow registry. Their 29 packages are published as runs of ``historical-packages``.
Each gets a new registered model ``FEWS NET | <package name>`` whose version 1 has source ``runs:/<package run>/package``
and run_id = the package run. These are package pointers, not MLflow models: there is no MLmodel/pyfunc flavor, and
``mlflow.pyfunc.load_model("models:/...")`` is not supported. The description and tags say so and give the actual
loader: download ``package`` from the run (MLflow SDK, Basic auth) and load ``loader/entry.py`` (the package contract;
``research_cloud.packages.replay`` replays it). Tags carry the package name, package.json sha256, status (including
the accepted incomplete-history exceptions) and the FEWS run. Existing registered models and versions are not touched.
Idempotent: an existing entry must already point at the same run and package.json, else refuse. ``--verify`` is
read-only.

  python -m research_cloud.deploy.register_fews_packages --url URL --out REPORT.json [--verify] [--expect 29]
"""
import argparse
import json
import os
import sys

DESCRIPTION = ("Package pointer (not an MLflow pyfunc model). Download with mlflow.artifacts.download_artifacts("
               "run_id='{run}', artifact_path='package') and load loader/entry.py (research_cloud package contract; "
               "research_cloud.packages.replay replays the frozen reference sample). Status: {status}. "
               "package.json sha256 {sha}.")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--expect", type=int)
    ap.add_argument("--only", action="append", default=[], help="pilot: these package names only")
    args = ap.parse_args(argv)
    from mlflow.exceptions import MlflowException
    from mlflow.tracking import MlflowClient

    from research_cloud.deploy import provision_secrets as ps
    from research_cloud.deploy.mlflow_identities import cred
    user, pw = cred(ps.Api(), "mlflow-temp-admin")
    os.environ["MLFLOW_TRACKING_USERNAME"], os.environ["MLFLOW_TRACKING_PASSWORD"] = user, pw
    client = MlflowClient(tracking_uri=args.url)
    exp = client.get_experiment_by_name("historical-packages")
    if exp is None:
        raise SystemExit("experiment historical-packages does not exist")
    runs = [r for r in client.search_runs([exp.experiment_id], max_results=1000)
            if r.data.tags.get("package.family", "").startswith("fewsnet_")
            and (not args.only or r.data.tags.get("package.name") in args.only)]
    report = {"fews_package_runs": len(runs), "entries": {}, "created": 0, "problems": []}
    for run in sorted(runs, key=lambda r: r.data.tags["package.name"]):
        t = run.data.tags
        name = f"FEWS NET | {t['package.name']}"
        want = {"package.run_id": run.info.run_id, "package.name": t["package.name"],
                "package.json_sha256": t["package.json_sha256"], "package.status": t["package.status"],
                "package.loader": "loader/entry.py (research_cloud package contract); not an MLflow pyfunc model",
                "source.run": t.get("source.run", "")}
        source = f"runs:/{run.info.run_id}/package"
        try:
            versions = client.search_model_versions(f"name = '{name}'")
        except MlflowException:
            versions = []
        if versions:
            v = versions[0]
            bad = [k for k, val in want.items() if v.tags.get(k) != val]
            if len(versions) != 1 or v.run_id != run.info.run_id or bad:
                report["problems"].append(f"{name}: existing entry differs ({len(versions)} versions, tags {bad})")
            report["entries"][name] = {"version": v.version, "run_id": v.run_id, "source": v.source}
            continue
        if args.verify:
            report["problems"].append(f"{name}: no registry entry")
            continue
        client.create_registered_model(name, tags={"family": t["package.family"], "kind": "package-pointer"},
                                       description=f"FEWS NET historical package {t['package.name']} (package pointer).")
        v = client.create_model_version(name, source, run_id=run.info.run_id, tags=want,
                                        description=DESCRIPTION.format(run=run.info.run_id, status=t["package.status"],
                                                                       sha=t["package.json_sha256"]))
        report["created"] += 1
        report["entries"][name] = {"version": v.version, "run_id": v.run_id, "source": v.source}
    if args.expect is not None and len(report["entries"]) != args.expect:
        report["problems"].append(f"{len(report['entries'])} entries, expected {args.expect}")
    report["ok"] = not report["problems"]
    json.dump(report, open(args.out, "w"), indent=1)
    print(json.dumps({k: (v if k not in ("entries", "problems") else len(v)) for k, v in report.items()}))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
