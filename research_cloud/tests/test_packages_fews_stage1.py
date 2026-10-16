"""FEWS stage-1 candidates: check_candidate binds saved predictions by content (routing, rows, score counts)."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from research_cloud.packages import fews_stage1 as s1
from research_cloud.packages.common import PackageError


def booster(seed):
    import xgboost as xgb
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(64, 3))
    return xgb.train({"objective": "multi:softprob", "num_class": 4, "max_depth": 1, "nthread": 1},
                     xgb.DMatrix(X, label=rng.integers(0, 4, 64)), 3)


class Candidate(unittest.TestCase):
    NAME = "h4_2018-02_G1_L1_r80_s42_gt0"

    def build(self):
        import xgboost as xgb
        sdir = Path(tempfile.mkdtemp())
        cdir, ckpt = sdir / "candidates" / self.NAME, sdir / "checkpoints" / self.NAME
        cdir.mkdir(parents=True)
        ckpt.mkdir(parents=True)
        recorded = {}
        for i, branch in enumerate(("root", "01", "1")):
            (ckpt / f"xgb_{branch}.ubj").write_bytes(bytes(booster(i).save_raw("ubj")))
            recorded[f"xgb_{branch}.ubj"] = hashlib.sha256((ckpt / f"xgb_{branch}.ubj").read_bytes()).hexdigest()
        rng = np.random.default_rng(9)
        X = rng.normal(size=(8, 3))
        areas = np.arange(8)
        pd.DataFrame({"FEWSNET_admin_code": areas[:6], "partition_id": ["01", "01", "01", "1", "1", "1"]}).to_csv(
            cdir / "correspondence_table.csv", index=False)
        branch = ["01"] * 3 + ["1"] * 3 + ["root"] * 2
        proba = np.vstack([xgb.Booster(model_file=str(ckpt / f"xgb_{b}.ubj")).predict(xgb.DMatrix(X[i:i + 1]))
                           for i, b in enumerate(branch)])
        truth = np.array([0, 1, 2, 3, 0, 2, 1, 0])
        pred = proba.argmax(1)
        preds = pd.DataFrame({"FEWSNET_admin_code": areas, "y_true_code": truth, "y_pred_partitioned_code": pred,
                              "y_pred_pooled_code": pred, "branch_id": branch,
                              "routing": ["terminal_branch"] * 6 + ["root_unassigned_test_area"] * 2})
        for k, l in enumerate(s1.LABELS):
            preds[f"p_partitioned_{l}"] = proba[:, k]
        preds.to_csv(cdir / "target_predictions.csv", index=False, float_format="%.17g")
        per, crisis = s1.recount(truth, pred)
        json.dump({"partition": {"terminal_partitions": ["01", "1"]}, "checkpoints": {"sha256": recorded},
                   "scores": {"partitioned": {"n": 8, "per_class": per}, "partitioned_crisis": crisis}},
                  open(cdir / "candidate.json", "w"))
        snap = pd.DataFrame(X, columns=["a", "b", "c"])
        snap["area"], snap["target_month"], snap["class_code"] = areas, s1.month_index("2018-02"), truth
        return sdir, snap.set_index(["area", "target_month"])

    def test_intact_passes_truncated_and_edited_predictions_fail(self):
        sdir, snap = self.build()
        h, units, _, _, frame, X, check = s1.check_candidate(sdir, self.NAME, snap, ["a", "b", "c"])
        self.assertEqual((h, sorted(units), check["rows"], check["root_rows"]), (4, ["01", "1", "root"], 8, 2))
        path = sdir / "candidates" / self.NAME / "target_predictions.csv"
        text = path.read_text().splitlines(True)
        path.write_text("".join(text[:-1]))                 # truncated: still routes and predicts, counts differ
        with self.assertRaisesRegex(PackageError, "score"):
            s1.check_candidate(sdir, self.NAME, snap, ["a", "b", "c"])
        path.write_text("".join(text).replace(",01,terminal_branch", ",1,terminal_branch", 1))   # edited routing
        with self.assertRaisesRegex(PackageError, "branch/routing"):
            s1.check_candidate(sdir, self.NAME, snap, ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main()


class LoaderLength(unittest.TestCase):
    def test_keys_x_length_mismatch_is_refused(self):
        import os
        import types
        import xgboost as xgb
        d = tempfile.mkdtemp()
        os.makedirs(f"{d}/deps")
        bst = xgb.train({"objective": "multi:softprob", "num_class": 4, "max_depth": 1, "nthread": 1},
                        xgb.DMatrix(np.random.default_rng(0).normal(size=(32, 162)), label=np.arange(32) % 4), 2)
        bst.save_model(f"{d}/r.ubj")
        pd.DataFrame({"name": [f"f{i}" for i in range(162)]}).to_csv(f"{d}/deps/feature_order.csv", index=False)
        pd.DataFrame({"candidate": ["c"], "area": [5], "branch": ["01"]}).to_csv(f"{d}/deps/routing.csv", index=False)
        json.dump({"candidates": ["c"], "units": {"c|root": {"file": "r.ubj", "sha256": "0" * 64}}}, open(f"{d}/package.json", "w"))
        module = types.ModuleType("entry")
        module.__file__ = f"{d}/loader/entry.py"
        exec(s1.ENTRY, module.__dict__)
        model = module.load(d)
        keys = pd.DataFrame({"candidate": ["c"], "area": [1], "target_month": ["2018-02"]})
        X = np.zeros((2, 162))
        self.assertEqual(model.predict(keys, X[:1])["route"].tolist(), ["root_unassigned_test_area"])
        with self.assertRaisesRegex(ValueError, "1 keys but 2 feature rows"):
            model.predict(keys, X)
