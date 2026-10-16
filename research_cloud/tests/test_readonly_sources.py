"""Importing the IPCCH builders from an original artifact path must not write bytecode into it."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SRC = "/home/swl007007/.local/share/ipcch-mlflow/artifacts/1/bdbafe393d694439a1c35ccec4d5816a/artifacts/source_code/IPCCHGeoXGBExperiment"


@unittest.skipUnless(os.path.isdir(SRC), "P6 source_code artifact not present")
class ReadOnlySource(unittest.TestCase):
    def test_loader_import_writes_no_pycache(self):
        copy = os.path.join(tempfile.mkdtemp(), "IPCCHGeoXGBExperiment")
        shutil.copytree(SRC, copy, ignore=shutil.ignore_patterns("__pycache__"))
        code = ("import sys; from research_cloud.training import ipcch_quartet; "
                f"ipcch_quartet._modules({{'geoxgb_src': {copy!r}}})")
        env = {**os.environ, "PYTHONPATH": os.getcwd()}
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        env.pop("IPCCH_GEOXGB_SRC", None)
        out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr[-400:])
        written = [os.path.join(d, f) for d, _, fs in os.walk(copy) for f in fs if f.endswith(".pyc")]
        self.assertEqual(written, [])


if __name__ == "__main__":
    unittest.main()
