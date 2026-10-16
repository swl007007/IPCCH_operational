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
        self.assertEqual(job["jobSpec"]["scheduling"],
                         {"timeout": "600s", "disableRetries": True, "restartJobOnWorkerRestart": False})
        hpt = cj.spec("m", "repo/img@sha256:" + "b" * 64, "n1-highmem-4", "/gcs/a", "/gcs/b", "fam", 600, 2,
                      "crisis_f1", cfg["space"], mlflow_uri="https://svc.run.app", experiment="e")
        self.assertEqual((hpt["maxTrialCount"], hpt["parallelTrialCount"]), (2, 1))
        self.assertIs(hpt["trialJobSpec"]["scheduling"]["disableRetries"], True)
        linked_hpt = cj.spec("m", "repo/img@sha256:" + "b" * 64, "n1-highmem-4", "/gcs/a", "/gcs/b", "fam", 900, 2,
                             "crisis_f1", cfg["space"], mlflow_uri="https://svc.run.app", experiment="e", parent_run="p")
        self.assertEqual(linked_hpt["trialJobSpec"]["scheduling"]["timeout"], "3000s")
        env = {e["name"]: e["value"] for e in linked_hpt["trialJobSpec"]["workerPoolSpecs"][0]["containerSpec"]["env"]}
        self.assertEqual(env["IPCCH_TRIAL_TIMEOUT_S"], "900")
        with self.assertRaises(SystemExit):
            cj.spec("m", "repo/img@sha256:" + "b" * 64, "n1-highmem-4", "/gcs/a", "/gcs/b", "fam", 900, 2, "crisis_f1", cfg["space"])
        self.assertEqual(hpt["studySpec"]["metrics"], [{"metricId": "crisis_f1", "goal": "MAXIMIZE"}])
        self.assertEqual(hpt["studySpec"]["parameters"][0]["integerValueSpec"], {"minValue": 2, "maxValue": 4})
        linked = cj.spec("research_cloud.training.m", "repo/img@sha256:" + "b" * 64, "n1-standard-4", "/gcs/a", "/gcs/b",
                         "fam", 600, mlflow_uri="https://svc.run.app", experiment="exp", parent_run="r1")
        c = linked["jobSpec"]["workerPoolSpecs"][0]["containerSpec"]
        from research_cloud.training.vertex_launch import LAUNCHER
        self.assertEqual(c["command"], ["python", "-c", LAUNCHER, "research_cloud.training.m"])
        self.assertEqual(c["args"][-2:], ["--mlflow-experiment", "exp"])
        env = {e["name"]: e["value"] for e in c["env"]}
        self.assertEqual(env, {"IPCCH_IMAGE_DIGEST": "sha256:" + "b" * 64, "MLFLOW_TRACKING_URI": "https://svc.run.app",
                               "IPCCH_GCP_PROJECT": cj.PROJECT, "IPCCH_PARENT_RUN_ID": "r1"})
        self.assertEqual(job["jobSpec"]["workerPoolSpecs"][0]["containerSpec"]["env"],
                         [{"name": "IPCCH_IMAGE_DIGEST", "value": "sha256:" + "b" * 64}])
        self.assertFalse({"MLFLOW_TRACKING_USERNAME", "MLFLOW_TRACKING_PASSWORD"} & set(env))   # read at run time only
        entered = cj.spec("research_cloud.training.m", "repo/img@sha256:" + "b" * 64, "n1-standard-4", "/gcs/a", "/gcs/b",
                          "fam", 600, mlflow_uri="https://svc.run.app", experiment="exp", entry="/usr/local/bin/train-entry")
        self.assertEqual(entered["jobSpec"]["workerPoolSpecs"][0]["containerSpec"]["command"][:3],
                         ["/usr/local/bin/train-entry", "python", "-c"])


class BaseManifest(unittest.TestCase):
    def test_maps_to_verified_objects_and_refuses_missing(self):
        with tempfile.TemporaryDirectory() as d:
            local = os.path.join(d, "base.json")
            json.dump({"name": "b", "files": {"panel": {"uri": "/mnt/c/x/panel.csv", "sha256": "a" * 64}}}, open(local, "w"))
            rec = os.path.join(d, "r.jsonl")
            with open(rec, "w") as f:
                f.write(json.dumps({"status": "verified (uploaded)", "bucket": "bk", "local": "/other/panel.csv",
                                    "object": "inputs/x/panel.csv", "local_sha256": "a" * 64, "generation": 5}) + "\n")
                f.write(json.dumps({"status": "error: RetryError", "bucket": "bk", "local": "/mnt/c/x/panel.csv",
                                    "object": "inputs/y/panel.csv", "local_sha256": "a" * 64, "generation": 6}) + "\n")
            m = cj.gcs_base_manifest(local, [rec])
            self.assertEqual(m["files"]["panel"], {"uri": "gs://bk/inputs/x/panel.csv", "sha256": "a" * 64, "gcs_generation": 5})
            self.assertEqual(m["gcp_project"], cj.PROJECT)
            json.dump({"name": "b", "files": {"p": {"uri": "/z", "sha256": "b" * 64}}}, open(local, "w"))
            with self.assertRaises(SystemExit):
                cj.gcs_base_manifest(local, [rec])


if __name__ == "__main__":
    unittest.main()
