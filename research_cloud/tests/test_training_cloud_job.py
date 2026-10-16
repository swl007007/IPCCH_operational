"""cloud_job: FUSE-path manifests keep every sha256 and bind the local manifest; configs lose host paths; specs pin
the image digest, the trainer SA and the declared HPT space/objective."""
import json
import os
import tempfile
import unittest

from research_cloud.training import cloud_job as cj


class CloudJob(unittest.TestCase):
    def test_manifest_config_and_spec(self):
        with tempfile.TemporaryDirectory() as d:
            local = os.path.join(d, "manifest.json")
            json.dump({"name": "n", "gcp_project": None, "derived_from": {"recipe": "r"},
                       "files": {"X": {"uri": "/host/snap/X.npy", "sha256": "a" * 64}}}, open(local, "w"))
            m = cj.cloud_manifest(local, "snap")
            self.assertEqual(m["files"]["X"], {"uri": f"/gcs/{cj.INPUTS}/training-snapshots/snap/X.npy", "sha256": "a" * 64})
            self.assertEqual(m["gcp_project"], cj.PROJECT)
            self.assertEqual(m["derived_from"]["recipe"], "r")
            self.assertEqual(m["derived_from"]["local_manifest"]["sha256"], cj.sha256_file(local))
            cfgp = os.path.join(d, "config.json")
            json.dump({"objective": "crisis_f1", "fews_src": "/host/src", "geoxgb_src": "/host/g",
                       "space": {"max_depth": {"type": "int", "min": 2, "max": 4}}, "fixed": {}}, open(cfgp, "w"))
            cfg = cj.cloud_config(cfgp)
            self.assertNotIn("fews_src", cfg)
            self.assertNotIn("geoxgb_src", cfg)
        with self.assertRaises(SystemExit):
            cj.spec("m", "repo/img:tag", "n1-standard-4", "/gcs/a", "/gcs/b", "fam", 600)
        job = cj.spec("m", "repo/img@sha256:" + "b" * 64, "n1-standard-4", "/gcs/a", "/gcs/b", "fam", 600)
        self.assertEqual(job["jobSpec"]["serviceAccount"], cj.TRAINER)
        self.assertEqual(job["jobSpec"]["scheduling"], {"timeout": "600s", "restartJobOnWorkerRestart": False})
        hpt = cj.spec("m", "repo/img@sha256:" + "b" * 64, "n1-highmem-4", "/gcs/a", "/gcs/b", "fam", 600, 2,
                      "crisis_f1", cfg["space"])
        self.assertEqual((hpt["maxTrialCount"], hpt["parallelTrialCount"]), (2, 1))
        self.assertEqual(hpt["studySpec"]["metrics"], [{"metricId": "crisis_f1", "goal": "MAXIMIZE"}])
        self.assertEqual(hpt["studySpec"]["parameters"][0]["integerValueSpec"], {"minValue": 2, "maxValue": 4})


if __name__ == "__main__":
    unittest.main()
