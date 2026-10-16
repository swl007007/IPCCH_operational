"""Feature-list mapping, remote archive members and cloud-mode refusal of local paths."""
import io
import os
import tarfile
import tempfile
import unittest

from research_cloud.mlflow_migrate import feature_list_check as check
from research_cloud.mlflow_migrate import feature_list_map as fmap

ROOT = fmap.LOCAL_ROOT
RUN = "a" * 32


class Mapping(unittest.TestCase):
    def test_local_parts_map_and_everything_else_is_kept(self):
        spec = (f"compact296={ROOT}3/{RUN}/artifacts/staging/source.tar!data/f.csv.gz#name?keep=1&lead~3 ; "
                f"alpha=runs:/{'b' * 32}/features.csv#@header")
        mapped, refused = fmap.map_spec(spec)
        self.assertEqual(refused, [])
        self.assertEqual(mapped, f"compact296=runs:/{RUN}/staging/source.tar!data/f.csv.gz#name?keep=1&lead~3 ; "
                                 f"alpha=runs:/{'b' * 32}/features.csv#@header")
        self.assertEqual(fmap.map_spec(f"x=runs:/{RUN}/f.csv"), (None, []))       # nothing local: no mapped tag

    def test_other_local_roots_are_refused(self):
        mapped, refused = fmap.map_spec("x=/home/someone/elsewhere/f.csv")
        self.assertIsNone(mapped)
        self.assertEqual(len(refused), 1)

    def test_original_side_resolves_runs_refs_locally(self):
        local = check.localize(f"x=runs:/{RUN}/staging/source.tar!m.csv#c", {RUN: f"mlflow-artifacts:/3/{RUN}/artifacts"})
        self.assertEqual(local, f"x={ROOT}3/{RUN}/artifacts/staging/source.tar!m.csv#c")
        with self.assertRaises(SystemExit):
            check.localize(f"x=runs:/{RUN}/f.csv", {})


@unittest.skipUnless(__import__("importlib").util.find_spec("mlflow"), "mlflow not installed")
class Reader(unittest.TestCase):
    def setUp(self):
        from research_cloud.service import ipcch_model
        self.reader = ipcch_model
        d = tempfile.mkdtemp()
        self.tar = os.path.join(d, "source.tar")
        with tarfile.open(self.tar, "w") as t:
            data = b"name,keep\nf1,1\nf2,0\nf3,1\n"
            info = tarfile.TarInfo("data/features.csv")
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))

    def test_remote_archive_member_with_selector(self):
        data = self.reader.remote_bytes(f"file://{self.tar}!data/features.csv")
        self.assertEqual(self.reader.read_columns(data, False, "name?keep=1"), ["f1", "f3"])
        with self.assertRaises(SystemExit):
            self.reader.remote_bytes(f"file://{self.tar}!data/missing.csv")

    def test_cloud_mode_refuses_local_paths(self):
        os.environ["IPCCH_MODEL_CLOUD"] = "1"
        try:
            with self.assertRaises(SystemExit):
                self.reader.feature_blocks(f"b={self.tar}!data/features.csv#name")
        finally:
            os.environ.pop("IPCCH_MODEL_CLOUD")


if __name__ == "__main__":
    unittest.main()
