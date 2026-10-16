"""Image definitions: the service image's baked environment lets the hook load in a fresh interpreter (deny mode)."""
import json
import os
import re
import shlex
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SERVICE_DOCKERFILE = os.path.join(HERE, "..", "images", "service", "Dockerfile")


def dockerfile_env(path):
    """ENV key=value pairs of a Dockerfile, in order (build args left as given)."""
    text = re.sub(r"\\\n\s*", " ", open(path).read())
    env = {}
    for line in text.splitlines():
        if line.startswith("ENV "):
            for item in shlex.split(line[4:]):
                k, _, v = item.partition("=")
                env[k] = v
    return env


def pth_installed():
    import site
    return any(os.path.exists(os.path.join(p, "ipcch_service_hook.pth")) for p in site.getsitepackages())


class ServiceImageEnv(unittest.TestCase):
    def test_provider_allowlist_is_baked(self):
        env = dockerfile_env(SERVICE_DOCKERFILE)
        self.assertEqual(env.get("IPCCH_SERVICE_HOOK"), "1")
        self.assertEqual(env.get("MLFLOW_GATEWAY_ALLOWED_PROVIDERS"), "vertex_ai")

    @unittest.skipUnless(pth_installed(), "ipcch_service_hook.pth not installed in this interpreter")
    def test_fresh_interpreter_with_the_image_env_loads_the_hook_in_deny_mode(self):
        from research_cloud.service.start import PROBE
        image_env = dockerfile_env(SERVICE_DOCKERFILE)
        root = os.path.abspath(os.path.join(HERE, "..", ".."))
        env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp"), **image_env, "PYTHONPATH": root}
        out = subprocess.run([sys.executable, "-c", PROBE], env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr[-500:])
        self.assertEqual(json.loads(out.stdout.strip().splitlines()[-1])["mode"], "deny")
        bad = {**env, "MLFLOW_GATEWAY_ALLOWED_PROVIDERS": ""}
        bad.pop("MLFLOW_GATEWAY_ALLOWED_PROVIDERS")
        out = subprocess.run([sys.executable, "-c", PROBE], env=bad, capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 78)   # the guard still refuses without the pin (not weakened)


if __name__ == "__main__":
    unittest.main()
