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
    def test_length_mismatch_refused(self):
        import xgboost as xgb
        d = tempfile.mkdtemp()
        os.makedirs(f"{d}/weights")
        os.makedirs(f"{d}/deps")
        bst = xgb.train({"objective": "multi:softprob", "num_class": 4, "max_depth": 1, "nthread": 1},
                        xgb.DMatrix(np.random.default_rng(0).normal(size=(32, 4)), label=np.arange(32) % 4), 2)
        bst.save_model(f"{d}/weights/global.ubj")
        pd.DataFrame({"area": [1], "target_month": ["2026-02"], "route": ["pooled_arm"], "cluster_id": [-1]}).to_csv(
            f"{d}/deps/routing.csv", index=False)
        json.dump({"arm": "pooled", "global": {"booster_sha256": "0" * 64}}, open(f"{d}/package.json", "w"))
        module = types.ModuleType("entry")
        module.__file__ = f"{d}/loader/entry.py"
        exec(fews_confirm.ENTRY, module.__dict__)
        model = module.load(d)
        keys = pd.DataFrame({"area": [1], "target_month": ["2026-02"]})
        self.assertEqual(model.predict(keys, np.zeros((1, 4)))["route"].tolist(), ["pooled"])
        with self.assertRaisesRegex(ValueError, "1 keys but X of shape"):
            model.predict(keys, np.zeros((2, 4)))


if __name__ == "__main__":
    unittest.main()
