"""Service start-up contract: refusals, assistant gating and the fresh-interpreter hook check.

The hook tests need ``ipcch_service_hook.pth`` installed in the running interpreter's site-packages (skipped otherwise).
No server is started and no network is used.
"""
import json
import os
import site
import sys
import tempfile
import unittest
from pathlib import Path

from research_cloud.service import start

HOOK_INSTALLED = any((Path(p) / "ipcch_service_hook.pth").exists() for p in site.getsitepackages())


def base_env(**over):
    env = {"PORT": "8080", "MLFLOW_BACKEND_STORE_URI": "postgresql+psycopg2://u@/track",
           "MLFLOW_ARTIFACTS_DESTINATION": "gs://bucket/artifacts", "IPCCH_AUTH_DATABASE_URI": "postgresql+psycopg2://u@/auth",
           "MLFLOW_FLASK_SERVER_SECRET_KEY": "s" * 64, "MLFLOW_CRYPTO_KEK_PASSPHRASE": "k" * 64,
           "IPCCH_ALLOWED_HOSTS": "svc.example", "MLFLOW_BASIC_AUTH_FAIL_CLOSED": "true"}
    env.update(over)
    return {k: v for k, v in env.items() if v is not None}


class BaseContract(unittest.TestCase):
    def test_accepts_the_contract(self):
        start.check_base(base_env())

    def test_refusals(self):
        for over in ({"MLFLOW_BASIC_AUTH_FAIL_CLOSED": None}, {"MLFLOW_BASIC_AUTH_FAIL_CLOSED": "false"},
                     {"MLFLOW_BACKEND_STORE_URI": "sqlite:///mlflow.db"}, {"IPCCH_AUTH_DATABASE_URI": "sqlite:///auth.db"},
                     {"MLFLOW_CRYPTO_KEK_PASSPHRASE": ""}, {"MLFLOW_FLASK_SERVER_SECRET_KEY": None}, {"PORT": "http"},
                     {"MLFLOW_SQL_TRACE_ROLLUPS_ENABLED": "true"}, {"MLFLOW_GATEWAY_ALLOWED_PROVIDERS": "vertex_ai,bedrock"},
                     {"MLFLOW_GATEWAY_ALLOWED_PROVIDERS": ""}):
            with self.assertRaises(start.StartupRefused, msg=over):
                start.check_base(base_env(**over))

    def test_auth_config_is_private_and_read_by_default(self):
        path = Path(tempfile.mkdtemp()) / "auth" / "basic_auth.ini"
        start.write_auth_config(base_env(), path)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        text = path.read_text()
        self.assertIn("default_permission = READ", text)
        self.assertIn("auth_cache_ttl_seconds = 60", text)
        start.write_auth_config({**base_env(), "IPCCH_AUTH_CACHE_TTL_SECONDS": "0"}, path)
        self.assertIn("auth_cache_ttl_seconds = 0", path.read_text())
        for bad in ("-1", "301", "x"):
            with self.assertRaises(start.StartupRefused):
                start.write_auth_config({**base_env(), "IPCCH_AUTH_CACHE_TTL_SECONDS": bad}, path)
        self.assertIn("database_uri = postgresql", text)


class AssistantGate(unittest.TestCase):
    def test_not_requested_is_deny(self):
        self.assertEqual(start.assistant_mode(base_env()), ("deny", ["assistant not requested"]))

    def test_incomplete_prerequisites_deny_with_reasons(self):
        mode, reasons = start.assistant_mode(base_env(IPCCH_ASSISTANT_ENABLE="1", MLFLOW_TRACKING_USERNAME="assistant",
                                                      MLFLOW_GATEWAY_ALLOWED_PROVIDERS="vertex_ai,openai"))
        self.assertEqual(mode, "deny")
        text = " ".join(reasons)
        for fragment in ("credentials incomplete", "exactly vertex_ai", "IPCCH_ASSISTANT_ENDPOINT", "spend guard unavailable"):
            self.assertIn(fragment, text)
        self.assertNotIn("k" * 64, text)

    def test_deny_config_selects_no_provider(self):
        home = tempfile.mkdtemp()
        path = start.write_assistant_config("deny", {}, home)
        self.assertEqual(json.loads(path.read_text())["providers"], {})
        path = start.write_assistant_config("armed", {"IPCCH_ASSISTANT_ENDPOINT": "ep"}, home)
        provider = json.loads(path.read_text())["providers"]["mlflow_gateway"]
        self.assertEqual((provider["model"], provider["permissions"]["full_access"], provider["permissions"]["allow_edit_files"]),
                         ("ep", False, False))


@unittest.skipUnless(HOOK_INSTALLED, "ipcch_service_hook.pth not installed in this interpreter")
class FreshInterpreterHook(unittest.TestCase):
    def env(self, **over):
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path), IPCCH_SERVICE_HOOK="1", MLFLOW_DISABLE_AGENT_HINT="1")
        env.update(over)
        return env

    def test_deny_mode_is_verified(self):
        env = self.env(IPCCH_ASSISTANT_MODE="deny", MLFLOW_GATEWAY_ALLOWED_PROVIDERS="vertex_ai")
        self.assertEqual(start.verify_hook(env, "deny")["mode"], "deny")

    def test_deny_mode_without_provider_pin_refuses(self):
        with self.assertRaisesRegex(start.StartupRefused, "exit 78"):
            start.verify_hook(self.env(IPCCH_ASSISTANT_MODE="deny", MLFLOW_GATEWAY_ALLOWED_PROVIDERS=""), "deny")

    def test_hook_failure_refuses_start(self):
        with self.assertRaisesRegex(start.StartupRefused, "exit 78"):
            start.verify_hook(self.env(IPCCH_ASSISTANT_MODE="bogus", MLFLOW_GATEWAY_ALLOWED_PROVIDERS="vertex_ai"), "deny")
        with self.assertRaisesRegex(start.StartupRefused, "exit 78"):   # armed without a usable guard config
            start.verify_hook(self.env(IPCCH_ASSISTANT_MODE="armed", IPCCH_ASSISTANT_GUARD_CONFIG="/nonexistent.json"), "armed")

    def test_mode_mismatch_refuses_start(self):
        with self.assertRaisesRegex(start.StartupRefused, "not active in mode armed"):
            start.verify_hook(self.env(IPCCH_ASSISTANT_MODE="deny", MLFLOW_GATEWAY_ALLOWED_PROVIDERS="vertex_ai"), "armed")

    def test_hook_absent_refuses_start(self):
        with self.assertRaisesRegex(start.StartupRefused, "not active"):
            start.verify_hook(self.env(IPCCH_SERVICE_HOOK="0"), "deny")


if __name__ == "__main__":
    unittest.main()
