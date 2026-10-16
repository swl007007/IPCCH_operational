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


class InteropRetry(unittest.TestCase):
    def runner(self, failures, stderr):
        calls = []

        class R:
            def __init__(self, rc, out, err):
                self.returncode, self.stdout, self.stderr = rc, out, err

        def run(script):
            calls.append(1)
            if len(calls) <= failures:
                return R(1, b"", stderr)
            return R(0, b"R|0|missing||\n", b"")
        return run, calls

    def test_transient_interop_failure_is_retried(self):
        dl.time.sleep = lambda s: None
        run, calls = self.runner(2, b"<3>WSL (1 - ) ERROR: UtilAcceptVsock:251: accept4 failed 110")
        self.assertEqual(dl.classify(["/mnt/c/x"], runner=run)[0]["status"], "missing")
        self.assertEqual(len(calls), 3)

    def test_other_or_persistent_failures_still_raise(self):
        dl.time.sleep = lambda s: None
        run, calls = self.runner(1, b"some other error")
        with self.assertRaises(dl.InspectionError):
            dl.classify(["/mnt/c/x"], runner=run)
        self.assertEqual(len(calls), 1)
        run, calls = self.runner(9, b"UtilAcceptVsock: accept4 failed")
        with self.assertRaises(dl.InspectionError):
            dl.classify(["/mnt/c/x"], runner=run)
        self.assertEqual(len(calls), 1 + dl.INTEROP_RETRIES)


if __name__ == "__main__":
    unittest.main()
