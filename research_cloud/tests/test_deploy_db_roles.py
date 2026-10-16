"""db_roles.run against a throwaway PostgreSQL 16 cluster (research_admin: CREATEROLE + CREATEDB, not superuser, as
cloudsqlsuperuser): scoped roles, owned databases, no PUBLIC access, verified attributes and logins; rerun is clean."""
import base64
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest

from research_cloud.deploy import db_roles, provision_secrets as ps

PG = "/home/swl007007/projects/food-crisis-research/envs/pg16/bin"


class SecretsApi:
    def __init__(self, values):
        self.values = values

    def call(self, method, url, body=None):
        name = url.split("/secrets/")[1].split("/")[0]
        return 200, {"payload": {"data": base64.b64encode(self.values[name].encode()).decode()}}


@unittest.skipUnless(os.path.exists(f"{PG}/initdb"), "PostgreSQL 16 binaries not present")
class Roles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            cls.port = s.getsockname()[1]
        subprocess.run([f"{PG}/initdb", "-D", f"{cls.dir}/data", "-U", "postgres", "-A", "md5", "--pwfile",
                        cls.pwfile("postgres-pw")], check=True, capture_output=True)
        subprocess.run([f"{PG}/pg_ctl", "-D", f"{cls.dir}/data", "-o", f"-p {cls.port} -k {cls.dir} -c listen_addresses=127.0.0.1",
                        "-l", f"{cls.dir}/log", "start", "-w"], check=True, capture_output=True)
        cls.values = {"sql-research-admin": "admin-" + "a" * 20, **{s: f"{r}-" + "b" * 20 for r, s in db_roles.ROLES.items()}}
        conn = db_roles.connect(cls.port, "postgres", "postgres-pw")
        conn.cursor().execute("CREATE ROLE research_admin LOGIN CREATEROLE CREATEDB PASSWORD %s",
                              (cls.values["sql-research-admin"],))
        conn.close()
        # Cloud SQL lets cloudsqlsuperuser create PostGIS; vanilla PostgreSQL needs a superuser, so the test cluster
        # provides it through template1 (new databases inherit it; run()'s CREATE EXTENSION IF NOT EXISTS is a no-op)
        conn = db_roles.connect(cls.port, "postgres", "postgres-pw", "template1")
        conn.cursor().execute("CREATE EXTENSION postgis")
        conn.close()

    @classmethod
    def pwfile(cls, value):
        path = os.path.join(cls.dir, "pw")
        open(path, "w").write(value)
        return path

    @classmethod
    def tearDownClass(cls):
        subprocess.run([f"{PG}/pg_ctl", "-D", f"{cls.dir}/data", "stop", "-m", "fast"], capture_output=True)
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_scoped_roles_verified_and_rerun_is_idempotent(self):
        receipt = ps.Receipt(os.path.join(self.dir, "receipt.json"))
        result = db_roles.run(SecretsApi(self.values), receipt, self.port)
        self.assertEqual(result["problems"], [])
        self.assertEqual(result["memberships"], [])
        self.assertTrue(all(not v for r in result["roles"].values() for k, v in r.items() if k != "login"))
        self.assertEqual(set(result["logins"].values()), {"ok"})
        self.assertEqual(result["databases"]["research"]["owner"], "research_import")
        self.assertFalse(any(g.startswith("PUBLIC:") for d in result["databases"].values() for g in d.get("grants", [])))
        text = open(receipt.path).read()
        for value in self.values.values():
            self.assertNotIn(value, text)
        again = db_roles.run(SecretsApi(self.values), ps.Receipt(receipt.path), self.port)   # resume: no rotation
        self.assertEqual(again["problems"], [])

    def test_a_foreign_role_is_refused(self):
        conn = db_roles.connect(self.port, "postgres", "postgres-pw")
        conn.cursor().execute("CREATE ROLE stray_check LOGIN")
        conn.close()
        original = db_roles.ROLES
        db_roles.ROLES = {"stray_check": "sql-research-read", **original}   # refused before anything is created
        try:
            with self.assertRaisesRegex(ps.ProvisionError, "did not create"):
                db_roles.run(SecretsApi(self.values), ps.Receipt(os.path.join(self.dir, "r2.json")), self.port)
        finally:
            db_roles.ROLES = original


if __name__ == "__main__":
    unittest.main()
