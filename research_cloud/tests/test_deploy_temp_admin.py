"""temp_admin against a fake auth store and the provisioner's fake API: create adds exactly the admin (secret first,
no accessors), a rerun is a no-op only with this task's receipt and a working credential, foreign users refuse,
remove deletes exactly it and destroys the secret versions; nothing secret is printed or receipted."""
import contextlib
import io
import json
import os
import tempfile
import unittest

from research_cloud.deploy import provision_secrets as ps
from research_cloud.deploy import temp_admin as ta
from research_cloud.tests.test_deploy_provision import FakeApi


class User:
    def __init__(self, name, admin):
        self.username, self.is_admin = name, admin


class FakeStore:
    def __init__(self, users):
        self.u = {n: [a, None] for n, a in users.items()}

    def list_users(self):
        return [User(n, a) for n, (a, _) in self.u.items()]

    def create_user(self, n, p, is_admin=False):
        self.u[n] = [is_admin, p]

    def delete_user(self, n):
        del self.u[n]

    def authenticate_user(self, n, p):
        return n in self.u and self.u[n][1] == p


class Api(FakeApi):
    def call(self, method, url, body=None):
        if url.endswith(f"{ta.SECRET}/versions") and method == "GET":
            return 200, {"versions": [{"name": f"projects/p/secrets/{ta.SECRET}/versions/1", "state": "ENABLED"}]}
        if url.endswith(":destroy"):
            self.calls.append((method, url))
            return 200, {}
        return super().call(method, url, body)


class TempAdmin(unittest.TestCase):
    def run_main(self, action, api, store, receipt):
        ta.store = lambda a, p: store
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = ta.main([action, "--port", "1", "--receipt", receipt], api=api)
        return rc, out.getvalue()

    def test_create_rerun_remove(self):
        api, store = Api([]), FakeStore({"admin": True, "reader": False})
        with tempfile.TemporaryDirectory() as d:
            receipt = os.path.join(d, "r.json")
            rc, out = self.run_main("create", api, store, receipt)
            self.assertEqual(rc, 0, out)
            self.assertIs(store.u[ta.USERNAME][0], True)
            pw = json.loads(api.versions[ta.SECRET])["password"]
            self.assertEqual(store.u[ta.USERNAME][1], pw)
            self.assertEqual(api.secrets[ta.SECRET], ps.LABELS)
            self.assertEqual(self.run_main("create", api, store, receipt)[0], 0)          # resumed, nothing new
            self.assertEqual(len([u for u in store.u if u == ta.USERNAME]), 1)
            rc, out2 = self.run_main("remove", api, store, receipt)
            self.assertEqual(rc, 0, out2)
            self.assertEqual(set(store.u), {"admin", "reader"})
            self.assertTrue(any(u.endswith(":destroy") for _, u in api.calls))
            self.assertNotIn(pw, open(receipt).read() + out + out2)

    def test_foreign_user_refused(self):
        api, store = Api([]), FakeStore({"admin": True, ta.USERNAME: True})
        with tempfile.TemporaryDirectory() as d:
            rc, out = self.run_main("create", api, store, os.path.join(d, "r.json"))
        self.assertEqual(rc, 1)
        self.assertIn("did not create", out)


if __name__ == "__main__":
    unittest.main()
