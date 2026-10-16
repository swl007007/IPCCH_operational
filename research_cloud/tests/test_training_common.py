"""Trial harness: parameter space, fixed keys, input hashing, objective failure, HPT argument form."""
import json
import os
import tempfile
import unittest

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

    def test_undefined_objective_fails_and_is_not_reported(self):
        d = tempfile.mkdtemp()
        os.environ["CLOUD_ML_HP_METRIC_FILE"] = f"{d}/metrics"
        for value in (None, float("nan")):
            with self.assertRaises(common.TrialError):
                common.report_objective("crisis_f1", value)
        self.assertFalse(os.path.exists(f"{d}/metrics"))
        common.report_objective("crisis_f1", 0.5)
        self.assertEqual(json.loads(open(f"{d}/metrics").read())["crisis_f1"], 0.5)

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
        record = json.load(open(f"{d}/out/trial.json"))
        self.assertEqual((rc, seen["max_depth"], record["status"]), (1, 5, "failed"))
        self.assertIn("undefined", record["error"])


if __name__ == "__main__":
    unittest.main()
