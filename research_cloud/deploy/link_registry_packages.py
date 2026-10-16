"""AC2 reverse links: from each registered model version and its source run to the package run that holds its package.

For every run of ``historical-packages`` whose ``registry.link_status`` is ``linked``, each listed registered model
version and each listed source run get three tags (additive; nothing else changes): ``package.run_id``,
``package.name``, ``package.json_sha256``. An existing tag with another value refuses. ``--verify`` is read-only and
checks every expected tag. Packages outside the MLflow registry (FEWS NET, pop-v1) have no MLflow source to point from;
their package runs carry ``source.run`` / ``source.run_root`` instead.

  python -m research_cloud.deploy.link_registry_packages --url URL --out REPORT.json [--verify] [--expect-versions 170]
"""
import argparse
import json
import os
import sys


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--expect-versions", type=int)
    args = ap.parse_args(argv)
    from mlflow.tracking import MlflowClient

    from research_cloud.deploy import provision_secrets as ps
    from research_cloud.deploy.mlflow_identities import cred
    user, pw = cred(ps.Api(), "mlflow-temp-admin")
    os.environ["MLFLOW_TRACKING_USERNAME"], os.environ["MLFLOW_TRACKING_PASSWORD"] = user, pw
    client = MlflowClient(tracking_uri=args.url)
    exp = client.get_experiment_by_name("historical-packages")
    if exp is None:
        raise SystemExit("experiment historical-packages does not exist")
    runs = client.search_runs([exp.experiment_id], filter_string="tags.`registry.link_status` = 'linked'",
                              max_results=1000)
    report = {"package_runs": len(runs), "versions": 0, "source_runs": 0, "written": 0, "problems": []}
    for run in sorted(runs, key=lambda r: r.data.tags["package.name"]):
        want = {"package.run_id": run.info.run_id, "package.name": run.data.tags["package.name"],
                "package.json_sha256": run.data.tags["package.json_sha256"]}
        targets = [("version", *v.rsplit("|", 1)) for v in json.loads(run.data.tags.get("registry.versions", "[]"))]
        targets += [("run", r, None) for r in json.loads(run.data.tags.get("source.run_ids", "[]"))]
        for kind, ident, version in targets:
            if kind == "version":
                have = client.get_model_version(ident, version).tags
                report["versions"] += 1
            else:
                have = client.get_run(ident).data.tags
                report["source_runs"] += 1
            for k, v in want.items():
                if have.get(k) == v:
                    continue
                if have.get(k) is not None or args.verify:
                    report["problems"].append(f"{kind} {ident} {version or ''}: {k} is {have.get(k)!r}, expected {v!r}")
                    continue
                if kind == "version":
                    client.set_model_version_tag(ident, version, k, v)
                else:
                    client.set_tag(ident, k, v)
                report["written"] += 1
    if args.expect_versions is not None and report["versions"] != args.expect_versions:
        report["problems"].append(f"{report['versions']} linked versions, expected {args.expect_versions}")
    report["ok"] = not report["problems"]
    json.dump(report, open(args.out, "w"), indent=1)
    print(json.dumps({k: (v if k != "problems" else len(v)) for k, v in report.items()}))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
