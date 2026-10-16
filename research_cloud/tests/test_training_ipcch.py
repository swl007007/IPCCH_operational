"""IPCCH quartet adapter boundary checks (all must fail before any model is fitted)."""
import json
import os
import tempfile
import unittest

import numpy as np
import pandas as pd

from research_cloud.training import common, ipcch_quartet

SRC = "/home/swl007007/.local/share/ipcch-mlflow/artifacts/1/bdbafe393d694439a1c35ccec4d5816a/artifacts/source_code/IPCCHGeoXGBExperiment"


@unittest.skipUnless(os.path.isdir(SRC), "P6 source_code artifact not present")
class Boundaries(unittest.TestCase):
    def bundle(self, **edit):
        d = tempfile.mkdtemp()
        names = json.load(open(f"{SRC}/config/feature-schema.json"))["ordered_names"]
        keys = pd.DataFrame({"admin_code": [1, 2], "target_ord": [24272, 24272], "origin_ord": [24269, 24269],
                             "horizon_months": [3, 3], "phase_truth": [1, 3], "q2": [.1, .5], "q3": [0, .3], "q4": [0, .1], "q5": [0, 0]})
        for k, v in edit.items():
            if v is None:
                keys = keys.drop(columns=k)
            else:
                keys[k] = v
        keys.to_csv(f"{d}/keys.csv", index=False)
        np.save(f"{d}/X.npy", np.zeros((2, 561)))
        pd.DataFrame({"name": names}).to_csv(f"{d}/order.csv", index=False)
        return {"keys": f"{d}/keys.csv", "X": f"{d}/X.npy", "feature_order": f"{d}/order.csv"}, d

    def fit(self, inputs, folds=({"origin_ord": 24269},)):
        config = {"horizon": 3, "holdout_start_ord": 24276, "folds": list(folds), "fixed": {}, "geoxgb_src": SRC}
        return ipcch_quartet.fit(inputs, {"files": {}}, config, {"rounds": 10}, common.Output(tempfile.mkdtemp()))

    def test_refusals(self):
        cases = {"no development folds": dict(folds=[]),
                 "frozen rich561": "reorder", "lack ['origin_ord']": dict(origin_ord=None),
                 "phase_truth holds non-integer": dict(phase_truth=[1, 2.5]),
                 "phase_truth outside": dict(phase_truth=[1, 7]),
                 "own origin": dict(horizon_months=[1, 1])}
        for fragment, change in cases.items():
            if change == "reorder":
                inputs, d = self.bundle()
                order = pd.read_csv(inputs["feature_order"])
                order.iloc[[0, 1]] = order.iloc[[1, 0]].to_numpy()
                order.to_csv(inputs["feature_order"], index=False)
                args = (inputs,)
            elif "folds" in change:
                args = (self.bundle()[0], change["folds"])
            else:
                args = (self.bundle(**change)[0],)
            with self.assertRaisesRegex(common.TrialError, fragment.replace("[", r"\[").replace("]", r"\]"), msg=fragment):
                self.fit(*args)


if __name__ == "__main__":
    unittest.main()
