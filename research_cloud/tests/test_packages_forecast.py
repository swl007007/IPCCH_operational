import json
import os
import tempfile
import unittest

import numpy as np
import pandas as pd

from research_cloud.packages import forecast_batch as fb
from research_cloud.packages.common import PackageError, sha256_file
from research_cloud.packages.replay import compare


class InputChain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.parent_ds = self.write("parent_h0.csv", "area_id,year,month,f\n1,2026,1,0.5\n")
        self.other_ds = self.write("other_h0.csv", "area_id,year,month,f\n1,2026,1,9.9\n")
        self.manifest = self.write("parent_manifest.json", json.dumps({"horizons": {"0": {"arms": {
            "compact_baseline": {"dataset": {"path": self.parent_ds, "sha256": sha256_file(self.parent_ds)}},
            "compact_weather_oracle": {"appended": ["oracle_prcp_o1"]}}}}}))
        self.ext = self.write("extension_manifest.json", json.dumps({"parent": {"manifest": {"path": self.manifest}}}))

    def write(self, name, text):
        path = os.path.join(self.tmp, name)
        open(path, "w").write(text)
        return path

    def ext_meta(self, dataset_sha):
        return {"horizon": 0, "arm": "compact_baseline",
                "extension_manifest": {"path": self.ext, "sha256": sha256_file(self.ext)},
                "fingerprint_payload": {"parent_fingerprint_payload": {"manifest_sha256": sha256_file(self.manifest),
                                                                       "dataset_sha256": dataset_sha}}}

    def test_extension_resolves_through_parent_manifest_with_recorded_hashes(self):
        path, sha, chain = fb.resolve_dataset(self.ext_meta(sha256_file(self.parent_ds)), 0, "compact_baseline")
        self.assertEqual(path, self.parent_ds)
        self.assertEqual(chain["manifest_via"], "extension_manifest.parent.manifest")

    def test_recorded_dataset_hash_mismatch_is_refused(self):
        with self.assertRaises(PackageError):
            fb.resolve_dataset(self.ext_meta(sha256_file(self.other_ds)), 0, "compact_baseline")

    def test_altered_extension_manifest_is_refused(self):
        meta = self.ext_meta(sha256_file(self.parent_ds))
        meta["extension_manifest"]["sha256"] = "0" * 64
        with self.assertRaises(PackageError):
            fb.resolve_dataset(meta, 0, "compact_baseline")

    def test_information_status_from_arm_contract_not_path(self):
        ordinary = fb.information_status({"manifest": self.manifest, "horizon": 0, "arm": "compact_baseline"}, ["f"])
        oracle = fb.information_status({"manifest": self.manifest, "horizon": 0, "arm": "compact_weather_oracle"}, ["f", "oracle_prcp_o1"])
        self.assertEqual(ordinary["status"], "origin_safe_ordinary")
        self.assertEqual(oracle["status"], "oracle_realized_future_information")
        self.assertEqual(fb.information_status({"run_id": "launch"}, ["f"])["status"], "undeclared")


class HighestCrossingDecode(unittest.TestCase):
    def frame(self, scores, phase):
        return pd.DataFrame({**{f"q{k}_raw": [v] for k, v in zip(range(2, 6), scores)},
                             **{f"q{k}_star": [v] for k, v in zip(range(2, 6), scores)}, "phase": [phase]})

    def test_non_monotone_scores_use_highest_crossing_not_count(self):
        scores = np.array([[0.10, 0.30, 0.10, 0.05]])   # count rule would give 2; highest crossing gives 3
        self.assertTrue(compare(self.frame(scores[0], 3), scores, scores, np.array([3]), 0.2)["passed"])
        self.assertFalse(compare(self.frame(scores[0], 3), scores, scores, np.array([2]), 0.2)["passed"])

    def test_declared_threshold_is_used(self):
        scores = np.array([[0.25, 0.10, 0.0, 0.0]])
        self.assertTrue(compare(self.frame(scores[0], 1), scores, scores, np.array([1]), 0.3)["passed"])
        self.assertFalse(compare(self.frame(scores[0], 1), scores, scores, np.array([1]), 0.2)["passed"])


if __name__ == "__main__":
    unittest.main()
