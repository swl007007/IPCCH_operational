"""G8: import the declared research inputs into Cloud SQL database ``research`` through the Auth Proxy.

The rehearsed loaders run unchanged against the cloud database: ``sqlimport.load_inputs`` (53 tabular inputs; every
cell compared before COMMIT; full-set reconciliation) and ``sqlimport.load_geometry load`` (3 PostGIS bundles; typed
equality and byte-equal WKB). The role is ``research_import`` (owner of ``research``); its password is read
in-process from this task's secret and handed to libpq as ``PGPASSWORD`` only (never in argv, DSN or reports).

Geometry is loaded from copies of the export directories (``export.json`` + ``rows.tsv``; the loader re-checks both
against the export record), so the client readback is written beside the copy and the rehearsal scratch is untouched.
Capacity (read-only) is recorded for ``research``, ``mlflow`` and ``mlflow_auth`` as the operator-only
``research_admin``, which has maintenance CONNECT on each and the monitoring privilege ``pg_ls_waldir`` needs.

  python -m research_cloud.deploy.load_research_inputs --port 5433 --inventory INV --keys KEYS
      --geometry-exports DIR --work DIR --reports DIR [--skip-csv] [--skip-geometry]
"""
import argparse
import json
import os
import shutil
import sys

from research_cloud.deploy.db_roles import secret_value
from research_cloud.deploy.provision_secrets import Api, scrub

BUNDLES = ("ipcch.geometry_repaired", "ipcch.geometry_source", "fewsnet.geometry")


def dsn(port, user, db=None):
    return f"host=127.0.0.1 port={port} user={user} sslmode=disable" + (f" dbname={db}" if db else "")


def call(main, argv):
    try:
        rc = main(argv)
    except SystemExit as e:
        rc = e.code
    return 0 if rc in (None, 0) else (rc if isinstance(rc, int) else 1)


def main(argv=None, api=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--keys", required=True)
    ap.add_argument("--geometry-exports", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--reports", required=True)
    ap.add_argument("--skip-csv", action="store_true")
    ap.add_argument("--skip-geometry", action="store_true")
    args = ap.parse_args(argv)
    os.makedirs(args.reports, exist_ok=True)
    api = api or Api()
    from research_cloud.sqlimport import capacity, load_geometry, load_inputs
    summary = {}
    os.environ["PGPASSWORD"] = secret_value(api, "sql-research-import")
    if not args.skip_csv:
        summary["csv_rc"] = call(load_inputs.main, ["--inventory", args.inventory, "--keys", args.keys,
                                                    "--dsn", dsn(args.port, "research_import", "research"),
                                                    "--report", os.path.join(args.reports, "csv-import-report.json")])
    if not args.skip_geometry:
        for b in BUNDLES:
            work = os.path.join(args.work, b)
            os.makedirs(work, exist_ok=True)
            for name in ("export.json", "rows.tsv"):
                shutil.copyfile(os.path.join(args.geometry_exports, b, name), os.path.join(work, name))
            summary[f"geometry_rc:{b}"] = call(load_geometry.main, [
                "load", "--export", work, "--dsn", dsn(args.port, "research_import", "research"),
                "--report", os.path.join(args.reports, "geometry-report.json")])
    # capacity as the operator-only research_admin (maintenance CONNECT on every database; pg_ls_waldir needs a
    # monitoring role, which the application roles deliberately lack); the record is read-only
    os.environ["PGPASSWORD"] = secret_value(api, "sql-research-admin")
    summary["capacity_rc"] = call(capacity.main, [
        "--dsn", dsn(args.port, "research_admin"), "--databases", "research", "mlflow", "mlflow_auth",
        "--out", os.path.join(args.reports, "capacity.json")])
    os.environ.pop("PGPASSWORD", None)
    for name in os.listdir(args.reports):                 # defence in depth: no credential persists in a report
        path = os.path.join(args.reports, name)
        if name.endswith(".json"):
            text = open(path).read()
            clean = scrub(text)
            if clean != text:
                open(path, "w").write(clean)
    print(scrub(json.dumps(summary)))
    return 0 if all(v == 0 for v in summary.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
