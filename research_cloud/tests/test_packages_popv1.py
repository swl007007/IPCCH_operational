"""pop-v1 loader: saved-fill imputation (never refitted), score orientation, strict thresholds, routes."""
import importlib.util
import json
import os
import tempfile
import unittest

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.ensemble import RandomForestClassifier

from research_cloud.packages.popv1 import ENTRY

N_COLS = 4   # stands in for rich561


def package(arm, estimator, model=None, constant=None, t0=0.5, t1=0.5, routes=(("f1", "E_history"),)):
    root = tempfile.mkdtemp()
    for d in ("deps/imputers", "weights", "loader"):
        os.makedirs(f"{root}/{d}")
    open(f"{root}/loader/entry.py", "w").write(ENTRY)
    json.dump({"arm": arm, "decision": {"t0": t0, "t1": t1, "no_history": 0.5 if arm == "fullpool_xgb" else "+Infinity"}},
              open(f"{root}/package.json", "w"))
    json.dump([f"c{i}" for i in range(N_COLS)] + ["persistence_b"], open(f"{root}/deps/input_columns.json", "w"))
    units = {}
    for fold, _ in routes:
        units[fold] = {"estimator": estimator, "constant": constant, "route": "model", "file": None}
        if model is not None:
            name = f"{fold}__{arm}.{'joblib' if estimator == 'RandomForestClassifier' else 'ubj'}"
            (joblib.dump(model, f"{root}/weights/{name}") if estimator == "RandomForestClassifier" else model.save_model(f"{root}/weights/{name}"))
            units[fold]["file"] = name
        json.dump({str(i): 1000.0 + i for i in range(N_COLS)}, open(f"{root}/deps/imputers/{fold}.json", "w"))
    json.dump(units, open(f"{root}/deps/units.json", "w"))
    pd.DataFrame({"admin_code": [1 + i for i in range(len(routes))], "target_ord": [10] * len(routes),
                  "fold_id": [f for f, _ in routes], "support": [s for _, s in routes]}).to_csv(f"{root}/deps/routing.csv", index=False)
    spec = importlib.util.spec_from_file_location(f"pop_{arm}_{os.path.basename(root)}", f"{root}/loader/entry.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.load(root)


def keys(n=1):
    return pd.DataFrame({"admin_code": list(range(1, n + 1)), "target_ord": [10] * n})


class PopV1Loader(unittest.TestCase):
    def test_rf_uses_saved_fill_values_not_a_refit(self):
        # the forest splits only on c0 at 500: the saved fill (1000) sends a missing c0 to the high class
        X = np.array([[0.0, 0, 0, 0], [900.0, 0, 0, 0]] * 20)
        rf = RandomForestClassifier(n_estimators=3, random_state=0).fit(X, [0, 1] * 20)
        model = package("rich_rf", "RandomForestClassifier", rf)
        out = model.predict(keys(), np.array([[np.nan, 0, 0, 0, 0.0]]))
        self.assertEqual(out.loc[0, "raw_score"], 1.0)

    def test_correction_flips_by_persistence_and_constant_route(self):
        model = package("correction_xgb", "XGBClassifier", constant=0.3, routes=(("f1", "E_history"), ("f2", "E_history")))
        out = model.predict(keys(2), np.array([[0, 0, 0, 0, 0.0], [0, 0, 0, 0, 1.0]]))
        np.testing.assert_allclose(out["raw_score"], [0.3, 0.3])
        np.testing.assert_allclose(out["crisis_score"], [0.3, 0.7])

    def test_regressor_clip_and_strict_thresholds(self):
        X = np.random.default_rng(0).normal(size=(32, N_COLS)).astype(np.float32)
        reg = xgb.XGBRegressor(n_estimators=1, base_score=1.4, learning_rate=1e-6).fit(X, np.full(32, 1.4))
        model = package("share_xgb", "XGBRegressor", reg, t0=1.0, t1="-Infinity")
        out = model.predict(keys(), np.array([[0, 0, 0, 0, 0.0]]))
        self.assertAlmostEqual(out.loc[0, "raw_score"], 1.4, places=4)
        self.assertEqual((out.loc[0, "crisis_score"], out.loc[0, "decision"]), (1.0, 0))   # 1.0 > 1.0 is false
        out = model.predict(keys(), np.array([[0, 0, 0, 0, 1.0]]))
        self.assertEqual(out.loc[0, "decision"], 1)                                     # any score > -inf

    def test_no_history_threshold_and_unserved_key(self):
        model = package("fullpool_xgb", "XGBClassifier", constant=0.5, t0=0.1, t1=0.1, routes=(("f1", "E_no_history"),))
        out = model.predict(keys(), np.array([[0, 0, 0, 0, 0.0]]))
        self.assertEqual((out.loc[0, "threshold"], out.loc[0, "decision"]), (0.5, 0))
        with self.assertRaises(KeyError):
            model.predict(pd.DataFrame({"admin_code": [9], "target_ord": [10]}), np.zeros((1, N_COLS + 1)))


if __name__ == "__main__":
    unittest.main()
