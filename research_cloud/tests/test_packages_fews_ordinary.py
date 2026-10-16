"""FEWS ordinary packages: the D38 base margin equals the producer's own function; cells and run specs are complete."""
import os
import unittest

import numpy as np

from research_cloud.packages import fews_ordinary as fo

SRC = "/home/swl007007/projects/food-crisis-research/sources/Food_Crisis_Cluster/FEWSNETGeoXGBExperiment"


class Margin(unittest.TestCase):
    PHASE = np.array([1.0, 2.0, 3.0, 4.0, 5.0, np.nan, 2.0])

    def test_shape_dtype_and_missing_origin(self):
        m = fo.persistence_margin(self.PHASE)
        self.assertEqual((m.shape, m.dtype), ((7, 4), np.float32))
        self.assertTrue(np.all(m[5] == np.float32(0.5)))
        self.assertTrue(np.array_equal(m[3], m[4]))              # phase 5 -> code 3, like phase 4
        self.assertEqual(int(np.argmax(m[1])), 1)
        with self.assertRaises(ValueError):
            fo.persistence_margin(np.array([0.0]))

    @unittest.skipUnless(os.path.isdir(SRC), "FEWS source not present")
    def test_equals_producer_function(self):
        """Executes the producer's own function text (ast-extracted; its module imports plotting libraries)."""
        import ast
        import types

        def functions(path, names):
            tree = ast.parse(open(path).read())
            return {n.name: ast.get_source_segment(open(path).read(), n) for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name in names}

        rr = types.SimpleNamespace(GateError=ValueError)
        exec(functions(f"{SRC}/scripts/stage1_recency_root.py", {"persistence_codes"})["persistence_codes"],
             {"np": np, "GateError": ValueError}, rr.__dict__)
        ns = {"np": np, "rr": rr, "nx": types.SimpleNamespace(N_CLASSES=4), "LAMBDA": 0.5, "DEFAULT_MARGIN": 0.5}
        src = functions(f"{SRC}/scripts/stage1_persistence_margin_root.py", {"persistence_prior", "persistence_margin"})
        self.assertIn("LAMBDA = 0.5", open(f"{SRC}/scripts/stage1_persistence_margin_root.py").read())
        self.assertIn("DEFAULT_MARGIN = 0.5", open(f"{SRC}/scripts/stage1_persistence_margin_root.py").read())
        exec(src["persistence_prior"] + "\n\n" + src["persistence_margin"], ns)
        for phase in (self.PHASE, self.PHASE[:0], np.array([np.nan, np.nan])):
            mine, theirs = fo.persistence_margin(phase), ns["persistence_margin"](phase)
            self.assertEqual(mine.dtype, theirs.dtype)
            self.assertTrue(np.array_equal(mine, theirs))


class Specs(unittest.TestCase):
    def test_cells_and_runs(self):
        self.assertEqual(len(fo.cells()), 21)
        self.assertEqual(len(set(fo.cells())), 21)
        self.assertEqual(sum(1 for s in fo.RUNS.values() if s.get("margin")), 1)
        for spec in fo.RUNS.values():
            self.assertIn("C", spec["parts"])
            self.assertIn("E3", spec["parts"])


if __name__ == "__main__":
    unittest.main()


def _booster(n_features=3):
    import xgboost as xgb
    rng = np.random.default_rng(0)
    X = rng.normal(size=(64, n_features))
    y = rng.integers(0, 4, 64)
    return xgb.train({"objective": "multi:softprob", "num_class": 4, "max_depth": 1, "nthread": 1},
                     xgb.DMatrix(X, label=y), 3), X


class FrozenInputs(unittest.TestCase):
    """check_cell (the production path) refuses rows/record/weight files that differ from completion.json outputs."""

    def cell(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path

        import pandas as pd
        bst, X = _booster()
        run = Path(tempfile.mkdtemp())
        cell = "h4_2018-06_G1_r80_s42_e1pair"
        (run / cell).mkdir()
        (run / cell / "stump_root.ubj").write_bytes(bytes(bst.save_raw("ubj")))
        digest = hashlib.sha256((run / cell / "stump_root.ubj").read_bytes()).hexdigest()
        (run / cell / "stump_root.json").write_text(json.dumps({"stump_root_sha256": digest}))
        import xgboost as xgb
        p = bst.predict(xgb.DMatrix(X[:6]))
        rows = pd.DataFrame({"area": range(6), "target_month": "2017-01", "truth": 0, "y_stump": p.argmax(1)})
        for k, l in enumerate(fo.LABELS):
            rows[f"p_stump_{l}"] = p[:, k]
        for part in ("C", "E3"):
            rows.to_csv(run / cell / f"rows_{part}.csv.gz", index=False, float_format="%.17g")
        snap = pd.DataFrame(X[:6], columns=["a", "b", "c"])
        snap["area"], snap["target_month"], snap["class_code"] = range(6), fo.month_index("2017-01"), 0
        snapshots = type("S", (), {"features": ["a", "b", "c"], "get": lambda self, h: (snap.set_index(["area", "target_month"]), "s")})()
        completion = {"outputs": {f"{cell}/{f}": hashlib.sha256((run / cell / f).read_bytes()).hexdigest()
                                  for f in ("stump_root.ubj", "stump_root.json", "rows_C.csv.gz", "rows_E3.csv.gz")}}
        spec = {"unit": "stump_root", "record": "stump_root.json", "arm": "stump", "parts": ("C", "E3"), "suffix": ""}
        return run, cell, spec, snapshots, {"inputs": {cell: {"snapshot": "s"}}}, completion

    def test_intact_inputs_pass_and_truncated_or_changed_inputs_are_refused(self):
        import gzip
        run, cell, spec, snapshots, identity, completion = self.cell()
        unit, _, frame, X, check = fo.check_cell(run, spec, cell, snapshots, identity, completion)
        self.assertEqual((check["C"]["rows"], len(frame)), (6, 12))
        lines = gzip.open(run / cell / "rows_C.csv.gz", "rt").read().splitlines(True)
        with gzip.open(run / cell / "rows_C.csv.gz", "wt") as f:   # truncated, still self-consistent
            f.writelines(lines[:3])
        with self.assertRaisesRegex(fo.PackageError, "completion.json outputs"):
            fo.check_cell(run, spec, cell, snapshots, identity, completion)
        del completion["outputs"][f"{cell}/rows_C.csv.gz"]
        with self.assertRaisesRegex(fo.PackageError, "not among completion.json outputs"):
            fo.check_cell(run, spec, cell, snapshots, identity, completion)


class LoaderLengths(unittest.TestCase):
    """Generated loaders refuse a keys/X length mismatch instead of dropping the X tail."""

    def entry(self, source, package_dir):
        import types
        module = types.ModuleType("entry")
        module.__file__ = os.path.join(package_dir, "loader", "entry.py")
        exec(source, module.__dict__)
        return module.load(package_dir)

    def test_ordinary_and_map_loaders(self):
        import json
        import tempfile

        import pandas as pd
        from research_cloud.packages import fews_map
        bst, X = _booster(162)
        d = tempfile.mkdtemp()
        os.makedirs(f"{d}/deps")
        bst.save_model(f"{d}/u.ubj")
        pd.DataFrame({"name": [f"f{i}" for i in range(162)]}).to_csv(f"{d}/deps/feature_order.csv", index=False)
        pd.DataFrame({"cell": ["c"], "arm": ["a"], "area": [1], "region": [""], "reason": ["missing"]}).to_csv(
            f"{d}/deps/routing.csv", index=False)
        json.dump({"units": {"c": {"file": "u.ubj", "sha256": "0" * 64}, "c|root": {"file": "u.ubj", "sha256": "0" * 64}},
                   "cells": ["c"], "arms": {"a": "a_map_refit"}}, open(f"{d}/package.json", "w"))
        keys = pd.DataFrame({"cell": ["c"], "arm": ["a"], "area": [1], "target_month": ["2017-01"]})
        for source in (fo.ENTRY, fews_map.ENTRY):
            model = self.entry(source, d)
            self.assertEqual(len(model.predict(keys, X[:1])), 1)
            with self.assertRaisesRegex(ValueError, "1 keys but 2 feature rows"):
                model.predict(keys, X[:2])
