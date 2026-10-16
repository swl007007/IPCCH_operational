"""G8/G9: load MLflow snapshot r1 (tracking + basic-auth SQLite) into the Cloud SQL databases via the Auth Proxy.

The ``mlflow_app`` password is read in-process from this task's Secret Manager secret and handed to libpq only as
``PGPASSWORD`` in this process's environment (never on a command line, in a DSN string or in a report). Steps:

1. schemas: MLflow 3.17's own initializers (``_initialize_tables`` for tracking, the auth ``migrate`` to head) create
   them as ``mlflow_app`` (the databases' owner); an existing schema must already be at the expected revision;
2. ``copy_store`` loads each store (journal bound to the snapshot sha256, one transaction per table, digest-verified);
3. ``copy_store --verify-only`` re-compares every table in a read-only session.
Reports are written next to the receipts and scrubbed of known credential values.

  python -m research_cloud.deploy.load_mlflow_stores --port 5433 --snapshot DIR --reports DIR
"""
import argparse
import contextlib
import io
import json
import os
import sys

from research_cloud.deploy.db_roles import secret_value
from research_cloud.deploy.provision_secrets import Api, scrub

EXPECTED = {"mlflow": ("alembic_version", "dc11669786a5"), "mlflow_auth": ("alembic_version_auth", None)}


def revision(port, db, table):
    import psycopg2
    with contextlib.closing(psycopg2.connect(host="127.0.0.1", port=port, user="mlflow_app", dbname=db,
                                             sslmode="disable")) as conn:
        cur = conn.cursor()
        cur.execute("SELECT to_regclass(%s)", (table,))
        if cur.fetchone()[0] is None:
            return None
        cur.execute(f"SELECT version_num FROM {table}")
        return [r[0] for r in cur.fetchall()]


def init_schema(port, db):
    import sqlalchemy as sa
    engine = sa.create_engine(f"postgresql+psycopg2://mlflow_app@127.0.0.1:{port}/{db}?sslmode=disable")
    if db == "mlflow":
        from mlflow.store.db.utils import _initialize_tables
        _initialize_tables(engine)
    else:
        from mlflow.server.auth.db import utils as au
        au.migrate(engine, "head")
    engine.dispose()


def copy(args, db, table, extra):
    from research_cloud.mlflow_migrate import copy_store
    source = os.path.join(args.snapshot, "mlflow.db" if db == "mlflow" else "basic_auth.db")
    report = os.path.join(args.reports, f"{db}{'-verify' if '--verify-only' in extra else '-copy'}.json")
    argv = ["--source", source, "--target", f"host=127.0.0.1 port={args.port} user=mlflow_app dbname={db} sslmode=disable",
            "--version-table", table, "--report", report, *extra]
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = copy_store.main(argv)
    with open(report) as f:
        text = scrub(f.read())
    with open(report, "w") as f:
        f.write(text)
    return rc, json.loads(text)


def main(argv=None, api=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--reports", required=True)
    args = ap.parse_args(argv)
    os.makedirs(args.reports, exist_ok=True)
    os.environ["PGPASSWORD"] = secret_value(api or Api(), "sql-mlflow-app")
    summary = {}
    for db, (table, expected) in EXPECTED.items():
        before = revision(args.port, db, table)
        if before is None:
            init_schema(args.port, db)
        after = revision(args.port, db, table)
        if not after or (expected and after != [expected]):
            raise SystemExit(f"{db}: schema revision {after} is not the expected {expected}")
        rc, rep = copy(args, db, table, [])
        vrc, vrep = copy(args, db, table, ["--verify-only"])
        summary[db] = {"schema_before": before, "revision": after, "copy_complete": rep.get("complete"),
                       "copy_error": rep.get("error"), "verified": vrep.get("verified"),
                       "tables": len(vrep.get("tables", {})), "rc": [rc, vrc]}
    print(scrub(json.dumps(summary)))
    return 0 if all(s["copy_complete"] and s["verified"] for s in summary.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
