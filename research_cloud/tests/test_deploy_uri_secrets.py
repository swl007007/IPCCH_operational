"""rebind_uri_secrets against the provisioner's fake API: a driver-less URI gets a corrected version, a rerun is a
no-op, any other difference refuses, and no value reaches output or receipt."""
import contextlib
import io
import json
import os
import tempfile
import unittest

from research_cloud.deploy import provision_secrets as ps
from research_cloud.deploy import rebind_uri_secrets as rb
from research_cloud.tests.test_deploy_provision import FakeApi

PW = "pw-" + "x" * 40


def seeded(uri_scheme="postgresql"):
    api = FakeApi([])
    for name in ("sql-mlflow-app", *rb.NAMES):
        api.secrets[name] = dict(ps.LABELS)
    api.versions["sql-mlflow-app"] = PW
    for name, db in (("mlflow-backend-uri", "mlflow"), ("mlflow-auth-db-uri", "mlflow_auth")):
        api.versions[name] = f"{uri_scheme}://mlflow_app:{PW}@/{db}?host={ps.SOCKET}"
    return api


class Rebind(unittest.TestCase):
    def call(self, api, receipt):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = rb.main(["--receipt", receipt], api=api)
        return rc, out.getvalue()

    def test_driver_added_then_noop_and_nothing_leaks(self):
        api = seeded()
        with tempfile.TemporaryDirectory() as d:
            receipt = os.path.join(d, "r.json")
            rc, out = self.call(api, receipt)
            self.assertEqual(rc, 0, out)
            for name in rb.NAMES:
                self.assertTrue(api.versions[name].startswith("postgresql+psycopg2://mlflow_app:"))
            adds = [c for c in api.calls if c[1].endswith(":addVersion")]
            self.assertEqual(len(adds), 2)
            rc, out2 = self.call(api, receipt)
            self.assertEqual(rc, 0)
            self.assertEqual(len([c for c in api.calls if c[1].endswith(":addVersion")]), 2)   # rerun adds nothing
            self.assertIn("already current", out2)
            text = open(receipt).read() + out + out2
            self.assertNotIn(PW, text)
            self.assertEqual(json.load(open(receipt))["uri_rebind"]["mlflow-backend-uri"]["driver"], ps.DRIVER)

    def test_other_difference_refuses(self):
        api = seeded()
        api.versions["mlflow-auth-db-uri"] = f"postgresql://mlflow_app:{PW}@/other?host={ps.SOCKET}"
        with tempfile.TemporaryDirectory() as d:
            rc, out = self.call(api, os.path.join(d, "r.json"))
        self.assertEqual(rc, 1)
        self.assertIn("more than the driver", out)
        self.assertNotIn(PW, out)


if __name__ == "__main__":
    unittest.main()
