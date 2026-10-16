"""v1 global screen loader: explicit global keys; unknown globals and keys/X length mismatches refused."""
import json
import os
import tempfile
import types
import unittest

import numpy as np
import pandas as pd

from research_cloud.packages import fews_globals


class Loader(unittest.TestCase):
    def test_keys(self):
        import xgboost as xgb
        d = tempfile.mkdtemp()
        os.makedirs(f"{d}/deps")
        bst = xgb.train({"objective": "multi:softprob", "num_class": 4, "max_depth": 1, "nthread": 1},
                        xgb.DMatrix(np.random.default_rng(0).normal(size=(32, 162)), label=np.arange(32) % 4), 2)
        bst.save_model(f"{d}/g.ubj")
        pd.DataFrame({"name": [f"f{i}" for i in range(162)]}).to_csv(f"{d}/deps/feature_order.csv", index=False)
        json.dump({"units": {"h4/G1/O2018-06": {"file": "g.ubj", "sha256": "a" * 64}}}, open(f"{d}/package.json", "w"))
        module = types.ModuleType("entry")
        module.__file__ = f"{d}/loader/entry.py"
        exec(fews_globals.ENTRY, module.__dict__)
        model = module.load(d)
        keys = pd.DataFrame({"horizon": [4], "g_config": ["G1"], "origin_month": ["2018-06"], "area": [1], "target_month": ["2018-10"]})
        self.assertEqual(model.predict(keys, np.zeros((1, 162)))["unit"].tolist(), ["a" * 16])
        with self.assertRaisesRegex(ValueError, "1 keys but 2"):
            model.predict(keys, np.zeros((2, 162)))
        with self.assertRaises(KeyError):
            model.predict(keys.assign(g_config="G2"), np.zeros((1, 162)))
        self.assertEqual(len(model.predict(keys.assign(horizon=4.0), np.zeros((1, 162)))), 1)   # whole number accepted
        for bad in (4.9, float("nan"), float("inf"), "four"):
            with self.assertRaisesRegex(ValueError, "whole numbers"):
                model.predict(keys.assign(horizon=bad), np.zeros((1, 162)))


if __name__ == "__main__":
    unittest.main()
