"""Trial harness: parameter space, fixed keys, input hashing, objective failure, HPT argument form."""
import json
import os
import tempfile
import unittest
import uuid

from research_cloud.training import common

SPACE = {"max_depth": {"type": "int", "min": 2, "max": 6, "default": 3},
         "eta": {"type": "float", "min": 0.01, "max": 0.3, "default": 0.05}}
FIXED = {"objective": "reg:squarederror", "seed": 42}


class Harness(unittest.TestCase):
    def test_space_and_fixed_keys(self):
        self.assertEqual(common.validate_params({"max_depth": "4"}, SPACE, FIXED), {"max_depth": 4, "eta": 0.05})
        for trial in ({"objective": "reg:logistic"}, {"seed": "1"}, {"gamma": "1"}, {"max_depth": "9"},
                      {"max_depth": "3.5"}, {"eta": "nan"}):
            with self.assertRaises(common.TrialError, msg=trial):
                common.validate_params(trial, SPACE, FIXED)

    def test_input_hash_is_checked_before_use(self):
        d = tempfile.mkdtemp()
        open(f"{d}/x.bin", "wb").write(b"data")
        good = {"files": {"x": {"uri": f"{d}/x.bin", "sha256": common.sha256_file(f"{d}/x.bin")}}}
        json.dump(good, open(f"{d}/m.json", "w"))
        self.assertEqual(common.resolve_inputs(f"{d}/m.json", d)[0]["x"], f"{d}/x.bin")
        good["files"]["x"]["sha256"] = "0" * 64
        json.dump(good, open(f"{d}/m.json", "w"))
        with self.assertRaises(common.TrialError):
            common.resolve_inputs(f"{d}/m.json", d)

    def test_fixed_and_space_may_not_overlap(self):
        # regression: a space default (seed 99) must not replace a fixed seed (42)
        with self.assertRaisesRegex(common.TrialError, "both fixed and tunable"):
            common.validate_params({}, {"seed": {"type": "int", "min": 0, "max": 100, "default": 99}}, {"seed": 42})

    def test_undefined_objective_fails_and_is_not_reported(self):
        d = tempfile.mkdtemp()
        os.environ["CLOUD_ML_HP_METRIC_FILE"] = f"{d}/metrics"
        for value in (None, float("nan")):
            with self.assertRaises(common.TrialError):
                common.report_objective("crisis_f1", value)
        self.assertFalse(os.path.exists(f"{d}/metrics"))
        reporter = common.report_objective("crisis_f1", 0.5)
        record = json.loads(open(f"{d}/metrics").read().strip().splitlines()[-1])
        self.assertEqual(float(record["crisis_f1"]), 0.5)        # the official reporter writes strings
        try:
            import hypertune  # noqa: F401
            self.assertEqual(reporter, "cloudml-hypertune")    # the installed dependency is exercised
        except ImportError:
            pass

    def setUp(self):
        os.environ["CLOUD_ML_JOB_ID"], os.environ["CLOUD_ML_TRIAL_ID"] = "job-" + uuid.uuid4().hex[:6], "1"

    def tearDown(self):
        os.environ.pop("CLOUD_ML_JOB_ID", None)
        os.environ.pop("CLOUD_ML_TRIAL_ID", None)

    def trial_dir(self, d):
        return f"{d}/out/{os.environ['CLOUD_ML_JOB_ID']}/trial-1"

    def test_trial_cli_accepts_vertex_arguments_and_records_failure(self):
        d = tempfile.mkdtemp()
        open(f"{d}/x.bin", "wb").write(b"data")
        json.dump({"files": {"x": {"uri": f"{d}/x.bin", "sha256": common.sha256_file(f"{d}/x.bin")}}}, open(f"{d}/m.json", "w"))
        json.dump({"objective": "score", "fixed": FIXED, "space": SPACE}, open(f"{d}/c.json", "w"))
        os.environ["CLOUD_ML_HP_METRIC_FILE"] = f"{d}/metrics"
        seen = {}

        def fit(inputs, manifest, config, params, out):
            seen.update(params)
            return {"metrics": {"score": None}}   # undefined objective
        rc = common.run_trial(fit, ["--manifest", f"{d}/m.json", "--config", f"{d}/c.json", "--output", f"{d}/out", "--max_depth=5"])
        record = json.load(open(f"{self.trial_dir(d)}/trial.json"))
        self.assertEqual((rc, seen["max_depth"], record["status"]), (1, 5, "failed"))
        self.assertIn("undefined", record["error"])
        with self.assertRaises(SystemExit):                       # a second run never overwrites the trial record
            common.run_trial(fit, ["--manifest", f"{d}/m.json", "--config", f"{d}/c.json", "--output", f"{d}/out"])

    def test_provenance_persists_when_fit_raises_and_objective_is_enforced(self):
        d = tempfile.mkdtemp()
        open(f"{d}/x.bin", "wb").write(b"data")
        json.dump({"files": {"x": {"uri": f"{d}/x.bin", "sha256": common.sha256_file(f"{d}/x.bin")}}}, open(f"{d}/m.json", "w"))
        json.dump({"objective": "crisis_f1", "fixed": FIXED, "space": SPACE}, open(f"{d}/c.json", "w"))

        def boom(*a):
            raise RuntimeError("fit exploded")
        self.assertEqual(common.run_trial(boom, ["--manifest", f"{d}/m.json", "--config", f"{d}/c.json", "--output", f"{d}/out"],
                                          objective="crisis_f1"), 1)
        record = json.load(open(f"{self.trial_dir(d)}/trial.json"))
        self.assertEqual((record["status"], record["resolved_params"]["seed"], record["params"]["max_depth"]), ("failed", 42, 3))
        self.assertIn("x", record["input_sha256"])
        os.environ["CLOUD_ML_TRIAL_ID"] = "2"
        common.run_trial(boom, ["--manifest", f"{d}/m.json", "--config", f"{d}/c.json", "--output", f"{d}/out"], objective="other")
        self.assertIn("this adapter reports", json.load(open(f"{d}/out/{os.environ['CLOUD_ML_JOB_ID']}/trial-2/trial.json"))["error"])


class ProjectAndFailureRecords(unittest.TestCase):
    def setUp(self):
        os.environ["CLOUD_ML_JOB_ID"], os.environ["CLOUD_ML_TRIAL_ID"] = "job-" + uuid.uuid4().hex[:6], "1"

    def tearDown(self):
        os.environ.pop("CLOUD_ML_JOB_ID", None)
        os.environ.pop("CLOUD_ML_TRIAL_ID", None)

    def trial_dir(self, d):
        return f"{d}/out/{os.environ['CLOUD_ML_JOB_ID']}/trial-1"

    def test_gcs_client_is_bound_to_the_target_project_only(self):
        with self.assertRaises(common.TrialError):
            common.storage_client("some-other-project")
        os.environ.pop("IPCCH_GCP_PROJECT", None)
        with self.assertRaises(common.TrialError):     # no implicit project
            common.gcs_project({})
        self.assertEqual(common.gcs_project({"gcp_project": "food-crisis-modeling-enso"}), "food-crisis-modeling-enso")

    @unittest.skipUnless(__import__("importlib").util.find_spec("mlflow"), "mlflow not installed")
    def test_failed_trial_is_recorded_in_mlflow(self):
        import mlflow
        d = tempfile.mkdtemp()
        try:   # full mlflow: SQLite store; mlflow-skinny (no SQL stores): the file store, explicitly allowed
            import sqlalchemy  # noqa: F401
            os.environ["MLFLOW_TRACKING_URI"] = f"sqlite:///{d}/mlflow.db"
        except ImportError:
            os.environ["MLFLOW_TRACKING_URI"], os.environ["MLFLOW_ALLOW_FILE_STORE"] = f"file://{d}/mlruns", "true"
        try:
            open(f"{d}/x.bin", "wb").write(b"data")
            json.dump({"files": {"x": {"uri": f"{d}/x.bin", "sha256": "0" * 64}}}, open(f"{d}/m.json", "w"))   # wrong hash
            json.dump({"objective": "score", "fixed": FIXED, "space": SPACE}, open(f"{d}/c.json", "w"))
            rc = common.run_trial(lambda *a: {"metrics": {"score": 1.0}},
                                  ["--manifest", f"{d}/m.json", "--config", f"{d}/c.json", "--output", f"{d}/out",
                                   "--mlflow-experiment", "trial-failures", "--max_depth=4"])
            record = json.load(open(f"{self.trial_dir(d)}/trial.json"))
            run = mlflow.get_run(record["mlflow_run_id"])
            self.assertEqual((rc, run.info.status, run.data.tags["trial_status"]), (1, "FAILED", "failed"))
            self.assertIn("sha256", run.data.tags["error"])
            self.assertEqual(run.data.params["arg.max_depth"], "4")
        finally:
            os.environ.pop("MLFLOW_TRACKING_URI", None)
            os.environ.pop("MLFLOW_ALLOW_FILE_STORE", None)


if __name__ == "__main__":
    unittest.main()
