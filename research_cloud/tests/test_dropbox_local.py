import subprocess
import unittest

from research_cloud.inventory import dropbox_local as dl

PATHS = ["/mnt/c/a.bin", "/mnt/c/b.bin"]


def fake(stdout, returncode=0, stderr=b""):
    return lambda script: subprocess.CompletedProcess([], returncode, stdout.encode(), stderr)


class ClassifyFailureModes(unittest.TestCase):
    def test_parses_states(self):
        out = dl.classify(PATHS, runner=fake("R|0|ok|32|10\nR|1|ok|4198432|7\n"))
        self.assertEqual([r["status"] for r in out], ["local", "cloud_only"])

    def test_nonzero_exit_raises_not_missing(self):
        with self.assertRaises(dl.InspectionError):
            dl.classify(PATHS, runner=fake("", returncode=1, stderr=b"boom"))

    def test_absent_row_raises(self):
        with self.assertRaises(dl.InspectionError):
            dl.classify(PATHS, runner=fake("R|0|ok|32|10\n"))

    def test_duplicate_row_raises(self):
        with self.assertRaises(dl.InspectionError):
            dl.classify(PATHS, runner=fake("R|0|ok|32|10\nR|0|missing||\n"))

    def test_garbage_row_raises(self):
        with self.assertRaises(dl.InspectionError):
            dl.classify(PATHS, runner=fake("R|0|ok|notanint|10\nR|1|missing||\n"))

    def test_only_item_not_found_is_missing(self):
        out = dl.classify(PATHS, runner=fake(
            "R|0|missing||\nR|1|error||System.UnauthorizedAccessException\n"))
        self.assertEqual(out[0]["status"], "missing")
        self.assertEqual(out[1]["status"], "inspection_error")


if __name__ == "__main__":
    unittest.main()
