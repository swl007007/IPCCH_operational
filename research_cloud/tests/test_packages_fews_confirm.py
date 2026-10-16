"""confirm-onset pooled loader: keys/X length mismatch refused; the system arm stays unpackaged."""
import json
import os
import tempfile
import types
import unittest

import numpy as np
import pandas as pd

from research_cloud.packages import fews_confirm


class Loader(unittest.TestCase):
    """The shared scen loader (reused by confirm) requires X of exactly (len(keys), declared width)."""

    def package(self, width=5, declared=None):
        import xgboost as xgb
        d = tempfile.mkdtemp()
        os.makedirs(f"{d}/weights")
        os.makedirs(f"{d}/deps")
        bst = xgb.train({"objective": "multi:softprob", "num_class": 4, "max_depth": 1, "nthread": 1},
                        xgb.DMatrix(np.random.default_rng(0).normal(size=(32, width)), label=np.arange(32) % 4), 2)
        bst.save_model(f"{d}/weights/global.ubj")
        pd.DataFrame({"name": [f"f{i}" for i in range(declared or width)]}).to_csv(f"{d}/deps/feature_order.csv", index=False)
        pd.DataFrame({"area": [1, 2], "target_month": ["2026-02"] * 2, "route": ["pooled_arm"] * 2,
                      "cluster_id": [-1, -1]}).to_csv(f"{d}/deps/routing.csv", index=False)
        json.dump({"arm": "pooled", "global": {"booster_sha256": "0" * 64}}, open(f"{d}/package.json", "w"))
        return d

    def load(self, source, d):
        module = types.ModuleType("entry")
        module.__file__ = f"{d}/loader/entry.py"
        exec(source, module.__dict__)
        return module.load(d)

    def test_width_and_rows_are_exact_for_scen_and_confirm(self):
        from research_cloud.packages import fews_scen
        keys = pd.DataFrame({"area": [1, 2], "target_month": ["2026-02"] * 2})
        for source in (fews_scen.ENTRY, fews_confirm.ENTRY):
            model = self.load(source, self.package())
            self.assertEqual(model.predict(keys, np.zeros((2, 5)))["route"].tolist(), ["pooled"] * 2)
            for bad in (np.zeros((2, 4)), np.zeros((2, 6)), np.zeros((3, 5)), np.zeros((1, 5)), np.zeros(10)):
                with self.assertRaisesRegex(ValueError, "X must be"):
                    model.predict(keys, bad)
            with self.assertRaisesRegex(RuntimeError, "feature_order declares"):
                self.load(source, self.package(width=5, declared=4))


if __name__ == "__main__":
    unittest.main()
