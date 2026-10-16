"""rootfs_replay counts a package only with rc 0, passed true and a fresh report binding the current package.json."""
import hashlib
import json
import os
import tempfile
import time
import unittest

from research_cloud.images import rootfs_replay as rr


class ReportGate(unittest.TestCase):
    def test_stale_foreign_and_missing_reports_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            pj = os.path.join(d, "package.json")
            open(pj, "w").write('{"x": 1}')
            current = hashlib.sha256(open(pj, "rb").read()).hexdigest()
            report = os.path.join(d, "r.json")
            self.assertFalse(rr.report_check(report, current, time.time())["fresh"])          # nothing written
            json.dump({"passed": True, "package_json_sha256": current}, open(report, "w"))
            os.utime(report, (1, 1))
            self.assertFalse(rr.report_check(report, current, time.time())["fresh"])          # stale mtime
            t0 = time.time() - 1
            json.dump({"passed": True, "package_json_sha256": "0" * 64}, open(report, "w"))
            self.assertFalse(rr.report_check(report, current, t0)["fresh"])                   # other package.json
            json.dump({"passed": True, "package_json_sha256": current}, open(report, "w"))
            self.assertTrue(rr.report_check(report, current, t0)["fresh"])


if __name__ == "__main__":
    unittest.main()
