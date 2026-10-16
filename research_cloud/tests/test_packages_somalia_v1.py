"""Somalia-oracle v1 loader: per-job routing, float32 inputs, direct q2..q5 outputs, descending crossing decode."""
import importlib.util
import json
import os
import tempfile
import unittest

import numpy as np
import pandas as pd
import xgboost as xgb

from research_cloud.packages.somalia_v1 import ENTRY


def make_package(root):
    for d in ("deps", "weights", "loader"):
        os.makedirs(f"{root}/{d}")
    open(f"{root}/loader/entry.py", "w").write(ENTRY)
    json.dump({"arm_letter": "B", "loader": {"phase_threshold": 0.2}}, open(f"{root}/package.json", "w"))
    json.dump(["f1", "f2"], open(f"{root}/deps/schema_columns.json", "w"))
    pd.DataFrame({"area_id": [1, 2], "target_ord": [10, 11], "job_id": ["jobA", "jobB"]}).to_csv(f"{root}/deps/routing.csv", index=False)
    rng = np.random.default_rng(0)
    X = rng.normal(size=(64, 2)).astype(np.float32)
    # jobA predicts a crossing quartet (q2 < 0.2 <= q5); jobB a high q2 only
    targets = {"jobA": (0.1, 0.15, 0.18, 0.3), "jobB": (0.6, 0.1, 0.05, 0.0)}
    for job, values in targets.items():
        for q, v in zip(("q2", "q3", "q4", "q5"), values):
            m = xgb.XGBRegressor(n_estimators=2, max_depth=1, base_score=v, learning_rate=1e-6)
            m.fit(X, np.full(len(X), v))
            m.save_model(f"{root}/weights/{job}_B_{q}.ubj")


def load(root):
    spec = importlib.util.spec_from_file_location("v1entry", f"{root}/loader/entry.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SomaliaV1Loader(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        make_package(self.root)
        self.mod = load(self.root)
        self.model = self.mod.load(self.root)

    def test_routes_by_job_and_decodes_highest_crossing(self):
        keys = pd.DataFrame({"area_id": [2, 1], "target_ord": [11, 10]})
        out = self.model.predict(keys, np.zeros((2, 2)))
        self.assertEqual(out["unit"].tolist(), ["jobB", "jobA"])
        self.assertEqual(out["phase"].tolist(), [2, 5])           # jobA: q5 crosses although q2..q4 do not
        np.testing.assert_allclose(out[["q2_raw", "q3_raw", "q4_raw", "q5_raw"]].to_numpy()[1], (0.1, 0.15, 0.18, 0.3), atol=1e-5)
        np.testing.assert_array_equal(out["q5_raw"].to_numpy(), out["q5_star"].to_numpy())

    def test_unserved_key_is_refused(self):
        with self.assertRaises(KeyError):
            self.model.predict(pd.DataFrame({"area_id": [3], "target_ord": [10]}), np.zeros((1, 2)))

    def test_decode_rule_and_non_finite_refusal(self):
        pred = np.array([[0.2, 0.0, 0.0, 0.0], [0.19, 0.19, 0.19, 0.19], [0.5, 0.21, 0.0, 0.2]])
        self.assertEqual(self.mod.phase_from_predictions(pred, 0.2).tolist(), [2, 1, 5])   # >= threshold, descending
        with self.assertRaises(ValueError):
            self.mod.phase_from_predictions(np.array([[np.nan, 0, 0, 0]]), 0.2)


if __name__ == "__main__":
    unittest.main()
