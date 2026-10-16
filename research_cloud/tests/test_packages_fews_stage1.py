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
    ROOT = "h4_2018-02_G1_r80_s42"

    def sha(self, path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def build(self):
        import xgboost as xgb
        sdir = Path(tempfile.mkdtemp())
        cdir, ckpt, rdir = sdir / "candidates" / self.NAME, sdir / "checkpoints" / self.NAME, sdir / "roots" / self.ROOT
        for d in (cdir, ckpt, rdir):
            d.mkdir(parents=True)
        recorded = {}
        for i, branch in enumerate(("root", "01", "1")):
            (ckpt / f"xgb_{branch}.ubj").write_bytes(bytes(booster(i).save_raw("ubj")))
            recorded[f"xgb_{branch}.ubj"] = self.sha(ckpt / f"xgb_{branch}.ubj")
        rng = np.random.default_rng(9)
        X = rng.normal(size=(8, 3))
        areas = np.arange(8)
        pd.DataFrame({"FEWSNET_admin_code": areas[:6], "partition_id": ["01", "01", "01", "1", "1", "1"]}).to_csv(
            cdir / "correspondence_table.csv", index=False)
        branch = ["01"] * 3 + ["1"] * 3 + ["root"] * 2
        load = lambda b: xgb.Booster(model_file=str(ckpt / f"xgb_{b}.ubj"))
        proba = np.vstack([load(b).predict(xgb.DMatrix(X[i:i + 1])) for i, b in enumerate(branch)])
        truth = np.array([0, 1, 2, 3, 0, 2, 1, 0])
        pred = proba.argmax(1)
        preds = pd.DataFrame({"FEWSNET_admin_code": areas, "y_true_code": truth, "y_pred_partitioned_code": pred,
                              "y_pred_pooled_code": pred, "branch_id": branch,
                              "routing": ["terminal_branch"] * 6 + ["root_unassigned_test_area"] * 2})
        for k, l in enumerate(s1.LABELS):
            preds[f"p_partitioned_{l}"] = proba[:, k]
        preds.to_csv(cdir / "target_predictions.csv", index=False, float_format="%.17g")
        root_p = load("root").predict(xgb.DMatrix(X))
        rt = pd.DataFrame({"FEWSNET_admin_code": areas, "y_true_code": truth, "y_pred_pooled_code": root_p.argmax(1)})
        for k, l in enumerate(s1.LABELS):
            rt[f"p_pooled_{l}"] = root_p[:, k]
        rt.to_csv(rdir / "root_target_predictions.csv", index=False, float_format="%.17g")
        json.dump({"root_booster_sha256": recorded["xgb_root.ubj"]}, open(rdir / "root.json", "w"))
        per, _ = s1.recount(truth, pred)
        json.dump({"partition": {"terminal_partitions": ["01", "1"]}, "checkpoints": {"sha256": recorded},
                   "scores": {"partitioned": {"n": 8, "per_class": per}}}, open(cdir / "candidate.json", "w"))
        self.outputs = {f"checkpoints/{self.NAME}/{f}": h for f, h in recorded.items()}
        for rel in (f"candidates/{self.NAME}/candidate.json", f"candidates/{self.NAME}/correspondence_table.csv",
                    f"candidates/{self.NAME}/target_predictions.csv", f"roots/{self.ROOT}/root.json",
                    f"roots/{self.ROOT}/root_target_predictions.csv"):
            self.outputs[rel] = self.sha(sdir / rel)
        snap = pd.DataFrame(X, columns=["a", "b", "c"])
        snap["area"], snap["target_month"], snap["class_code"] = areas, s1.month_index("2018-02"), truth
        return sdir, snap.set_index(["area", "target_month"])

    def check(self, sdir, snap):
        return s1.check_candidate(sdir, self.NAME, snap, ["a", "b", "c"], self.ROOT, self.outputs)

    def rewrite(self, sdir, rel, text):
        """Change a file and re-record it, so only the content checks can refuse it."""
        (sdir / rel).write_text(text)
        self.outputs[rel] = self.sha(sdir / rel)

    def test_intact_passes_and_root_unit_has_its_own_rows(self):
        sdir, snap = self.build()
        h, units, _, _, frame, X, check = self.check(sdir, snap)
        self.assertEqual((h, sorted(units), check["rows"], check["root_target_rows"]), (4, ["01", "1", "root"], 8, 8))
        self.assertEqual((frame["route"] == "pooled_root").sum(), 8)
        self.assertEqual(len(X), 16)

    def test_unrecorded_change_is_refused(self):
        sdir, snap = self.build()
        path = sdir / "candidates" / self.NAME / "target_predictions.csv"
        path.write_text("".join(path.read_text().splitlines(True)[:-1]))
        with self.assertRaisesRegex(PackageError, "completion.json outputs"):
            self.check(sdir, snap)

    def test_duplicated_row_and_nan_probability_are_refused_even_when_recorded(self):
        rel = f"candidates/{self.NAME}/target_predictions.csv"
        sdir, snap = self.build()
        lines = (sdir / rel).read_text().splitlines(True)
        self.rewrite(sdir, rel, "".join(lines[:7] + [lines[1]] + lines[8:]))    # row 6 replaced by a copy of row 0
        with self.assertRaisesRegex(PackageError, "duplicate areas|branch/routing"):
            self.check(sdir, snap)
        sdir, snap = self.build()
        frame = pd.read_csv(sdir / rel, dtype={"branch_id": str}, keep_default_na=False)
        frame.loc[0, "p_partitioned_1"] = np.nan
        self.rewrite(sdir, rel, frame.to_csv(index=False, float_format="%.17g"))
        with self.assertRaisesRegex(PackageError, "non-finite"):
            self.check(sdir, snap)


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
