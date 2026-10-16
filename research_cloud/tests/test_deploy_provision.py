"""provision_secrets against a fake API: credentials are stored before use, a pending SQL operation is polled and
resumed (timeout = unknown, not failure), operation errors stop the run, and nothing secret is printed or receipted."""
import base64
import contextlib
import io
import json
import os
import tempfile
import unittest

from research_cloud.deploy import provision_secrets as ps


class FakeApi:
    def __init__(self, op_script):
        self.secrets, self.versions, self.users, self.calls = {}, {}, set(), []
        self.op_script = list(op_script)          # statuses returned by successive operation polls
        self.op_error = None

    def call(self, method, url, body=None):
        self.calls.append((method, url.split("/v1/")[-1]))
        if url.startswith(ps.SM):
            rest = url[len(ps.SM):]
            if method == "GET" and rest.endswith("/versions/latest:access"):
                name = rest[1:].split("/")[0]
                if name not in self.versions:
                    return 404, {}
                return 200, {"payload": {"data": base64.b64encode(self.versions[name].encode()).decode()}}
            if method == "GET":
                name = rest[1:]
                return (200, {"labels": self.secrets[name]}) if name in self.secrets else (404, {})
            if method == "POST" and rest.startswith("?secretId="):
                self.secrets[rest.split("=", 1)[1]] = body["labels"]
                return 200, {}
            if method == "POST" and rest.endswith(":addVersion"):
                name = rest[1:].split(":")[0]
                self.versions[name] = base64.b64decode(body["payload"]["data"]).decode()
                return 200, {"name": f"projects/p/secrets/{name}/versions/1"}
            if method == "POST" and rest.endswith(":setIamPolicy"):
                return 200, {}
        if url.endswith("/users") and method == "GET":
            return 200, {"items": [{"name": u} for u in sorted(self.users)]}
        if url.endswith("/users") and method == "POST":
            if self.op_script and self.op_script[0] == "BUSY":
                return 409, {"error": {"message": "operation in progress"}}
            self.users.add(body["name"])
            return 200, {"name": "op-1", "status": "PENDING"}
        if "/operations/" in url:
            status = self.op_script.pop(0) if self.op_script else "DONE"
            op = {"name": "op-1", "status": status}
            if status == "DONE" and self.op_error:
                op["error"] = {"errors": [{"code": self.op_error}]}
            return 200, op
        raise AssertionError(f"unexpected call {method} {url}")


class Provision(unittest.TestCase):
    def setUp(self):
        self.receipt = os.path.join(tempfile.mkdtemp(), "r.json")
        ps.POLL_WAIT_S, ps.POLL_EVERY_S = 0.05, 0.01

    def run_once(self, api):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                ps.run(api, ps.Receipt(self.receipt))
                status = "complete"
            except ps.ProvisionError as e:
                ps.Receipt(self.receipt).step("stopped", error=str(e))
                status = "stopped"
        return status, out.getvalue()

    def assert_sanitized(self, api, printed):
        """No stored value (nor any credential inside a JSON identity) appears in the receipt or the output."""
        text = open(self.receipt).read() + printed
        for value in api.versions.values():
            parts = [value]
            if value.startswith("{"):
                parts += [v for v in json.loads(value).values() if len(v) > 16]
            for part in parts:
                self.assertNotIn(part, text)

    def test_pending_operation_is_resumed_and_credentials_survive(self):
        api = FakeApi(["RUNNING"] * 50)                      # never DONE within the local wait
        status, printed = self.run_once(api)
        self.assertEqual(status, "stopped")
        r = json.load(open(self.receipt))
        self.assertEqual(r["sql_ops"]["op-1"]["status"], "unknown")
        self.assertIn("sql-research-admin", api.versions)       # stored BEFORE the user was created
        admin_password = api.versions["sql-research-admin"]
        self.assertNotIn("mlflow-backend-uri", api.versions)    # dependent secrets wait for the admin step
        api.op_script = ["RUNNING", "DONE"]                     # rerun: poll the SAME operation, no new insert
        inserts_before = sum(1 for m, u in api.calls if m == "POST" and u.endswith("/users"))
        status, printed2 = self.run_once(api)
        self.assertEqual(status, "complete")
        self.assertEqual(sum(1 for m, u in api.calls if m == "POST" and u.endswith("/users")), inserts_before)
        self.assertEqual(api.versions["sql-research-admin"], admin_password)   # not rotated
        self.assertIn(f"mlflow_app:{api.versions['sql-mlflow-app']}@", api.versions["mlflow-backend-uri"])
        self.assert_sanitized(api, printed + printed2)

    def test_operation_error_and_foreign_secret_stop_the_run(self):
        api = FakeApi(["DONE"])
        api.op_error = "INTERNAL_ERROR"
        status, _ = self.run_once(api)
        self.assertEqual(status, "stopped")
        self.assertIn("INTERNAL_ERROR", open(self.receipt).read())
        api2 = FakeApi([])
        api2.secrets["mlflow-flask-secret"] = {"owner": "someone-else"}
        self.receipt = os.path.join(tempfile.mkdtemp(), "r2.json")
        status, _ = self.run_once(api2)
        self.assertEqual(status, "stopped")
        self.assertIn("not owned by this task", open(self.receipt).read())

    def test_preflight_only_404_is_absent(self):
        class Forbidden(FakeApi):
            def call(self, method, url, body=None):
                return (403, {"error": {"message": "denied"}}) if method == "GET" and url.startswith(ps.SM) else super().call(method, url, body)
        with self.assertRaises(ps.ProvisionError):
            ps.run(Forbidden([]), ps.Receipt(self.receipt), dry_run=True)


if __name__ == "__main__":
    unittest.main()
