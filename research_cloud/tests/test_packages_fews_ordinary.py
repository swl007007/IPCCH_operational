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
