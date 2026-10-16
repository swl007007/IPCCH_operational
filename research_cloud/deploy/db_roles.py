"""G8 phase 2: scoped database roles and databases on research-pg, created as ``research_admin`` (resumable, verified).

Runs against the Cloud SQL Auth Proxy on 127.0.0.1 (the proxy holds the TLS/IAM connection; no authorized networks).
Credentials are read in-process from this task's Secret Manager secrets (``provision_secrets``) and never printed;
the receipt is scrubbed like the provisioner's.

1. Log in as ``research_admin`` - the proof that its stored credential is the one the instance holds (this also closes
   a lost-acknowledgement recovery in the provisioner).
2. Application and read roles ``mlflow_app``, ``guard_app``, ``research_import``, ``research_read`` are created with
   ``CREATE ROLE ... LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS``: they are members of no role
   (in particular not ``cloudsqlsuperuser``, which Admin-API users join). An existing role is accepted only when this
   task's receipt records its creation; its stored password must then log in (never rotated).
3. ``research_admin`` is granted each role ``WITH INHERIT FALSE, SET TRUE`` (needed to create databases owned by them;
   it does not inherit their privileges). Databases: ``mlflow`` and ``mlflow_auth`` owned by ``mlflow_app``, ``guard``
   by ``guard_app``, ``research`` by ``research_import``; ``CONNECT``/``TEMPORARY`` revoked from ``PUBLIC`` as each owner
   (a non-owner's REVOKE is a silent no-op); the operator-only ``research_admin`` keeps CONNECT for maintenance;
   ``research_read``
   may connect to ``research`` and, by default privileges of ``research_import``, read its tables. PostGIS is created
   in ``research``.
4. Verification from the catalogs: every app role's attributes, its memberships (must be none), each database's owner
   and ACL; and a login with each app role's stored password.

  python -m research_cloud.deploy.db_roles --port 5433 --receipt RECEIPT.json
"""
import argparse
import base64
import contextlib
import json
import sys

from research_cloud.deploy.provision_secrets import SM, Api, ProvisionError, Receipt, message, remember, scrub

ROLES = {"mlflow_app": "sql-mlflow-app", "guard_app": "sql-guard-app", "research_import": "sql-research-import",
         "research_read": "sql-research-read"}
DATABASES = {"mlflow": "mlflow_app", "mlflow_auth": "mlflow_app", "guard": "guard_app", "research": "research_import"}
ATTRS = "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT"


def secret_value(api, name):
    status, ver = api.call("GET", f"{SM}/{name}/versions/latest:access")
    if status != 200:
        raise ProvisionError(f"secret {name}: {status} {message(ver)}")
    return remember(base64.b64decode(ver["payload"]["data"]).decode())


def connect(port, user, password, dbname="postgres"):
    import psycopg2
    conn = psycopg2.connect(host="127.0.0.1", port=port, user=user, password=password, dbname=dbname,
                            sslmode="disable", connect_timeout=20)        # the Auth Proxy terminates TLS
    conn.autocommit = True
    return conn


def verify(cur):
    cur.execute("""SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolcanlogin
                   FROM pg_roles WHERE rolname = ANY(%s) ORDER BY rolname""", (list(ROLES),))
    roles = {r[0]: dict(zip(("super", "createdb", "createrole", "replication", "bypassrls", "login"), r[1:]))
             for r in cur.fetchall()}
    cur.execute("""SELECT m.rolname, g.rolname FROM pg_auth_members a JOIN pg_roles m ON m.oid = a.member
                   JOIN pg_roles g ON g.oid = a.roleid WHERE m.rolname = ANY(%s)""", (list(ROLES),))
    memberships = cur.fetchall()
    cur.execute("SELECT datname, pg_get_userbyid(datdba), datacl IS NULL FROM pg_database WHERE datname = ANY(%s)",
                (list(DATABASES),))
    dbs = {d: {"owner": o, "default_acl": n} for d, o, n in cur.fetchall()}
    cur.execute("""SELECT d.datname, CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
                          a.privilege_type
                   FROM pg_database d, aclexplode(d.datacl) a WHERE d.datname = ANY(%s) ORDER BY 1, 2, 3""",
                (list(DATABASES),))
    for d, grantee, priv in cur.fetchall():
        dbs[d].setdefault("grants", []).append(f"{grantee}:{priv}")
    problems = [f"{r}: {k}" for r, a in roles.items() for k, v in a.items() if (k == "login") != bool(v)]
    problems += [f"{m} is a member of {g}" for m, g in memberships]
    problems += [f"role {r} missing" for r in ROLES if r not in roles]
    for d, owner in DATABASES.items():
        info = dbs.get(d, {})
        if info.get("owner") != owner:
            problems.append(f"database {d} owner {info.get('owner')} != {owner}")
        if info.get("default_acl"):
            problems.append(f"database {d} has the default ACL (PUBLIC may connect)")
        problems += [f"database {d} grants {g}" for g in info.get("grants", []) if g.startswith("PUBLIC:")]
    return {"roles": roles, "memberships": memberships, "databases": dbs, "problems": problems}


def run(api, receipt, port):
    admin = secret_value(api, "sql-research-admin")
    with contextlib.closing(connect(port, "research_admin", admin)) as conn:   # closing: `with conn` opens a transaction
        receipt.step("admin-login", user="research_admin", result="ok (stored credential proven)")
        cur = conn.cursor()
        from psycopg2 import sql
        created = set(receipt.data.setdefault("roles_created", []))
        for role, secret in ROLES.items():
            password = secret_value(api, secret)
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
            if cur.fetchone():
                if role not in created:
                    raise ProvisionError(f"role {role} exists but this task did not create it; refusing")
            else:
                cur.execute(sql.SQL("CREATE ROLE {} LOGIN " + ATTRS + " PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)))
                created.add(role)
                receipt.data["roles_created"] = sorted(created)
                receipt.step("role-created", role=role, attributes=ATTRS)
            cur.execute(sql.SQL("GRANT {} TO research_admin WITH INHERIT FALSE, SET TRUE").format(sql.Identifier(role)))
        for db, owner in DATABASES.items():
            cur.execute("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s", (db,))
            row = cur.fetchone()
            if row is None:
                cur.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(db), sql.Identifier(owner)))
                receipt.step("database-created", database=db, owner=owner)
            elif row[0] != owner:
                raise ProvisionError(f"database {db} exists with owner {row[0]}; refusing")
            # as the owner: PUBLIC's default privileges were granted by the owner, so a REVOKE by any other role is a
            # silent no-op (warning only) - verify() below proves the outcome from the catalog
            cur.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(owner)))
            cur.execute(sql.SQL("REVOKE CONNECT, TEMPORARY ON DATABASE {} FROM PUBLIC").format(sql.Identifier(db)))
            cur.execute(sql.SQL("GRANT CONNECT, TEMPORARY ON DATABASE {} TO {}").format(sql.Identifier(db), sql.Identifier(owner)))
            cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO research_admin").format(sql.Identifier(db)))   # maintenance
            if db == "research":
                cur.execute("GRANT CONNECT ON DATABASE research TO research_read")
            cur.execute("RESET ROLE")
        result = verify(cur)
    with contextlib.closing(connect(port, "research_admin", admin, "research")) as conn:
        cur = conn.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'postgis'")
        result["postgis"] = cur.fetchone()[0]
        cur.execute("SET ROLE research_import")
        cur.execute("ALTER DEFAULT PRIVILEGES FOR ROLE research_import GRANT SELECT ON TABLES TO research_read")
        cur.execute("GRANT USAGE ON SCHEMA public TO research_read")
        cur.execute("RESET ROLE")
    logins = {}
    for role, secret in ROLES.items():
        db = {"mlflow_app": "mlflow", "guard_app": "guard"}.get(role, "research")
        try:
            with contextlib.closing(connect(port, role, secret_value(api, secret), db)) as conn:
                conn.cursor().execute("SELECT 1")
            logins[role] = "ok"
        except Exception as e:          # noqa: BLE001 - recorded as a code, never the driver's text
            logins[role] = type(e).__name__
    result["logins"] = logins
    result["problems"] += [f"{r} cannot log in ({v})" for r, v in logins.items() if v != "ok"]
    receipt.data["verification"] = result
    receipt.step("verified", problems=result["problems"])
    if result["problems"]:
        raise ProvisionError(f"verification failed: {result['problems']}")
    return result


def main(argv=None, api=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--receipt", required=True)
    args = ap.parse_args(argv)
    receipt = Receipt(args.receipt)
    try:
        result = run(api or Api(), receipt, args.port)
    except ProvisionError as e:
        receipt.step("stopped", error=scrub(str(e)))
        print(scrub(json.dumps({"status": "stopped", "error": str(e)})))
        return 1
    except Exception as e:              # noqa: BLE001 - driver errors as a type only (no remote free text)
        receipt.step("stopped", error=type(e).__name__)
        print(json.dumps({"status": "stopped", "error": type(e).__name__}))
        return 1
    print(scrub(json.dumps({"status": "complete", "postgis": result["postgis"], "logins": result["logins"]})))
    return 0


if __name__ == "__main__":
    sys.exit(main())
