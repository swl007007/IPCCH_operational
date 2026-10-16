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
                             "weight": 1.0, "variant_k": 0, "horizon": 4})
        rows["origin_month"] = rows["target_month"] - 4
        for k, v in edit.items():
            rows[k] = v
        if "target_month" in edit and "origin_month" not in edit:
            rows["origin_month"] = rows["target_month"] - 4
        rows.to_csv(f"{d}/rows.csv", index=False)
        np.save(f"{d}/X.npy", rng.normal(size=(len(rows), 3)))
        pd.DataFrame({"name": ["a", "b", "c"]}).to_csv(f"{d}/order.csv", index=False)
        return {"rows": f"{d}/rows.csv", "X": f"{d}/X.npy", "feature_order": f"{d}/order.csv"}

    def config(self, **edit):
        c = {"horizon": 4, "target": "2019-02", "development_targets": ["2019-02"], "holdout_start": "2021-01",
             "n_features": 3, "fixed": {"eta": 0.3}, "space": {"max_depth": {}, "rounds": {}}, "fews_src": SRC}
        c.update(edit)
        return c

    def fit(self, inputs, config, params=None, derived=None):
        manifest = {"files": {}, "derived_from": derived if derived is not None else {"horizon": 4, "target": config["target"]}}
        return fews_fourclass.fit(inputs, manifest, config, params or {"max_depth": 2, "rounds": 5},
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
            (self.bundle(horizon=8), self.config(), "built at horizon"),
            (self.bundle(origin_month=0), self.config(), "built at horizon"),
        ] + [(self.bundle(), self.config(horizon=h), "not a FEWS horizon") for h in (1, 0, -1)] \
          + [(self.bundle(), self.config(horizon=4.5), "must be an integer")]
        for inputs, config, message in cases:
            with self.assertRaisesRegex(common.TrialError, message):
                self.fit(inputs, config)

    def test_snapshot_identity_must_match_the_config(self):
        for derived in ({"horizon": 8, "target": "2019-02"}, {"horizon": 4, "target": "2019-06"}, {}):
            with self.assertRaisesRegex(common.TrialError, "snapshot was built"):
                self.fit(self.bundle(), self.config(), derived=derived)

    def test_raw_observation_labels_are_checked_before_the_builders(self):
        from research_cloud.training import fews_features
        rx = fews_features.modules(SRC)[0]
        d = tempfile.mkdtemp()
        ok = pd.DataFrame({"area": [1, 2], "month": [24000, 24001], "country": ["A", "B"], "class_code": [0, 3]})
        ok.to_csv(f"{d}/ok.csv", index=False)
        self.assertEqual(len(fews_features.read_observations(rx, f"{d}/ok.csv")), 2)
        for bad in ({"class_code": [0, 2.5]}, {"class_code": [0, 4]}, {"class_code": [0, None]}, {"month": [24000, 24000.5]}):
            ok.assign(**bad).to_csv(f"{d}/bad.csv", index=False)
            with self.assertRaises(common.TrialError):
                fews_features.read_observations(rx, f"{d}/bad.csv")

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
