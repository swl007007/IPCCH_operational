"""FEWS four-class trial adapter boundaries (all must fail before any model is fitted), plus a tiny fit."""
import json
import os
import tempfile
import unittest

import numpy as np
import pandas as pd

from research_cloud.training import common, fews_fourclass

SRC = "/home/swl007007/projects/food-crisis-research/sources/Food_Crisis_Cluster/FEWSNETGeoXGBExperiment"


@unittest.skipUnless(os.path.isdir(SRC), "FEWS source not present")
class Boundaries(unittest.TestCase):
    T = 2019 * 12 + 1   # 2019-02

    def bundle(self, **edit):
        d = tempfile.mkdtemp()
        rng = np.random.default_rng(0)
        n_fit = 80
        rows = pd.DataFrame({"role": ["fit_variant"] * n_fit + ["eval"] * 4 + ["target"] * 8,
                             "orig_key": list(range(n_fit)) + [0, 1, 2, 3] + [-1] * 8,
                             "area": list(range(n_fit)) + [0, 1, 2, 3] + list(range(8)),
                             "target_month": [self.T - 10] * n_fit + [self.T - 10] * 4 + [self.T] * 8,
                             "class_code": list(np.arange(n_fit) % 4) + [0, 1, 2, 3] + [0, 2, 3, 1, 2, 0, 2, 3],
                             "weight": 1.0, "variant_k": 0})
        for k, v in edit.items():
            rows[k] = v
        rows.to_csv(f"{d}/rows.csv", index=False)
        np.save(f"{d}/X.npy", rng.normal(size=(len(rows), 3)))
        pd.DataFrame({"name": ["a", "b", "c"]}).to_csv(f"{d}/order.csv", index=False)
        return {"rows": f"{d}/rows.csv", "X": f"{d}/X.npy", "feature_order": f"{d}/order.csv"}

    def config(self, **edit):
        c = {"horizon": 4, "target": "2019-02", "development_targets": ["2019-02"], "holdout_start": "2021-01",
             "n_features": 3, "fixed": {"eta": 0.3}, "space": {"max_depth": {}, "rounds": {}}, "fews_src": SRC}
        c.update(edit)
        return c

    def fit(self, inputs, config, params=None):
        return fews_fourclass.fit(inputs, {"files": {}}, config, params or {"max_depth": 2, "rounds": 5},
                                  common.Output(tempfile.mkdtemp()))

    def test_refusals(self):
        cases = [
            (self.bundle(), self.config(fixed={"objective": "binary:logistic"}), "fixed by native_xgb"),
            (self.bundle(), self.config(space={"seed": {}}), "fixed by native_xgb"),
            (self.bundle(), self.config(target="2021-02", development_targets=["2021-02"]), "development target"),
            (self.bundle(), self.config(holdout_start="2019-01"), "held-out"),
            (self.bundle(), self.config(n_features=4), "declared features"),
            (self.bundle(class_code=1.5), self.config(), "non-integer"),
            (self.bundle(class_code=4), self.config(), "outside"),
            (self.bundle(weight=0.0), self.config(), "weights"),
        ]
        for inputs, config, message in cases:
            with self.assertRaisesRegex(common.TrialError, message):
                self.fit(inputs, config)

    def test_fitting_labels_may_not_reach_the_origin(self):
        months = [self.T - 10] * 79 + [self.T - 4] + [self.T - 10] * 4 + [self.T] * 8   # one label at O = T - H
        with self.assertRaisesRegex(common.TrialError, "reach the origin"):
            self.fit(self.bundle(target_month=months), self.config())

    def test_tiny_fit_scores_only_the_target_cohort(self):
        result = self.fit(self.bundle(), self.config())
        self.assertEqual(result["metrics"]["target_rows"], 8)
        self.assertEqual(result["metrics"]["fit_rows"], 80)


if __name__ == "__main__":
    unittest.main()
