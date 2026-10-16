"""Somalia-oracle loader behaviour on a hand-built minimal package with saved-constant models."""
import importlib.util
import json
import os
import tempfile
import unittest

import numpy as np
import pandas as pd

from research_cloud.packages.somalia import ENTRY


def make_package(root, job_available):
    os.makedirs(f"{root}/deps"); os.makedirs(f"{root}/weights"); os.makedirs(f"{root}/loader")
    open(f"{root}/loader/entry.py", "w").write(ENTRY)
    json.dump({"identity": {}}, open(f"{root}/package.json", "w"))
    json.dump(["f1", "hist_q3_obs1", "history_obs1_source_ord"], open(f"{root}/deps/input_columns.json", "w"))
    json.dump(["f1"], open(f"{root}/deps/schema_columns.json", "w"))
    pd.DataFrame({"area_id": [1, 2], "target_ord": [10, 10], "stem": ["J_D_residual"] * 2,
                  "map_key": ["J|D_residual"] * 2}).to_csv(f"{root}/deps/routing.csv", index=False)
    pd.DataFrame({"map_key": ["J|D_residual"] * 2, "prediction_branch": ["fallback_direct", "residual"],
                  "method": ["shift", "shift"], "status": ["ok", "unsupported"], "shift": [0.1, None],
                  "isotonic_x": [None, None], "isotonic_y": [None, None]}).to_csv(f"{root}/deps/calibration_mappings.csv", index=False)
    json.dump({"J|D_residual": {"available": job_available, "job_branches": ["fallback_direct", "residual"]}},
              open(f"{root}/deps/job_calibration.json", "w"))
    for target, value in (("q2", 0.6), ("q3_direct", 0.3), ("q4", 0.1), ("q5", 0.0), ("q3_residual_delta", 0.05)):
        json.dump({"kind": "constant", "value": value, "n_rows": 1}, open(f"{root}/weights/J_D_residual_{target}.json", "w"))


def load(root):
    spec = importlib.util.spec_from_file_location("e", f"{root}/loader/entry.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.load(root)


class JobScopedCalibration(unittest.TestCase):
    def predict(self, model, rows):
        keys = pd.DataFrame({"area_id": [r[0] for r in rows], "target_ord": [10] * len(rows)})
        X = np.array([[0.0, r[1], r[2]] for r in rows])
        return model.predict(keys, X)

    def test_result_does_not_depend_on_request_batch(self):
        root = tempfile.mkdtemp()
        make_package(root, job_available=False)       # residual mapping unsupported -> whole original job unavailable
        model = load(root)
        alone = self.predict(model, [(1, np.nan, -1)])                    # fallback_direct row only
        mixed = self.predict(model, [(1, np.nan, -1), (2, 0.4, 5)])       # plus a residual row
        self.assertTrue(np.isnan(alone.loc[0, "q3_final"]) and np.isnan(mixed.loc[0, "q3_final"]))
        self.assertEqual(alone.loc[0, "route"], "fallback_direct")
        self.assertEqual(mixed.loc[1, "route"], "residual")
        self.assertAlmostEqual(mixed.loc[1, "q3_raw"], 0.45)              # baseline 0.4 + constant delta 0.05

    def test_available_job_maps_each_branch_and_constants_are_used(self):
        root = tempfile.mkdtemp()
        make_package(root, job_available=True)
        model = load(root)
        out = self.predict(model, [(1, np.nan, -1)])
        self.assertAlmostEqual(out.loc[0, "q3_raw"], 0.3)
        self.assertAlmostEqual(out.loc[0, "q3_final"], 0.2)                # shift 0.1 on the fallback_direct branch
        self.assertAlmostEqual(out.loc[0, "q2_raw"], 0.6)
        self.assertEqual(out.loc[0, "unit"], "J_D_residual")

    def test_unknown_key_is_refused(self):
        root = tempfile.mkdtemp()
        make_package(root, job_available=True)
        with self.assertRaises(KeyError):
            self.predict(load(root), [(9, 0.1, 1)])


if __name__ == "__main__":
    unittest.main()
