import json
import os
import tempfile
import unittest

import numpy as np
import pandas as pd

from research_cloud.packages.alphaearth import ENTRY, resolve_units


def ledger(rows):
    return pd.DataFrame(rows, columns=["identity", "arm", "horizon", "block_id"])


PRED = pd.DataFrame({"block_id": ["b1", "b1", "b2"], "B1_identity": ["u1", "u1", "u2"], "B0_identity": ["v1", "v1", "v2"]})


class ResolveUnits(unittest.TestCase):
    def test_agreeing_ledger_and_predictions(self):
        units, gaps = resolve_units(ledger([("u1", "B1", 3, "b1"), ("u1", "B1", 3, "b1"), ("u2", "B1", 3, "b2")]), PRED, "G", 3)
        self.assertEqual(gaps, [])
        self.assertEqual(dict(zip(units.block_id, units.unit)), {"b1": "u1", "b2": "u2"})

    def test_conflicting_ledger_identities_are_a_gap(self):
        units, gaps = resolve_units(ledger([("u1", "B1", 3, "b1"), ("uX", "B1", 3, "b1"), ("u2", "B1", 3, "b2")]), PRED, "B1", 3)
        self.assertTrue(any("2 distinct" in g for g in gaps))
        self.assertNotIn("b1", set(units.block_id))

    def test_ledger_disagreeing_with_saved_predictions_is_a_gap(self):
        units, gaps = resolve_units(ledger([("v1", "B0", 3, "b1"), ("vZ", "B0", 3, "b2")]), PRED, "B0", 3)
        self.assertTrue(any("saved prediction B0_identity" in g for g in gaps))
        self.assertEqual(list(units.block_id), ["b1"])


class DescriptorContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "deps", "descriptors"))
        pd.DataFrame({"admin_code": [1, 2, 3], "m00": [0.1, np.nan, 0.3], "s00": [0.2, np.nan, np.nan]}).to_csv(
            os.path.join(self.tmp, "deps", "descriptors", "descriptor_table.csv.gz"), index=False)
        namespace = {}
        exec(compile(ENTRY.split("HERE = ")[0], "entry", "exec"), namespace)   # imports only
        src = ENTRY[ENTRY.index("    def row_descriptors"):ENTRY.index("    def resolve(self")]
        exec("import numpy as np\nclass M:\n" + src, namespace)
        self.m = namespace["M"]()
        self.m.descriptors = pd.read_csv(os.path.join(self.tmp, "deps", "descriptors", "descriptor_table.csv.gz")).set_index("admin_code")

    def test_routable_and_nonroutable_rows(self):
        D = self.m.row_descriptors(np.array([1, 2]))
        self.assertTrue(np.isfinite(D[0]).all() and np.isnan(D[1]).all())

    def test_partial_row_rejected(self):
        with self.assertRaises(ValueError):
            self.m.row_descriptors(np.array([3]))

    def test_absent_admin_rejected(self):
        with self.assertRaises(KeyError):
            self.m.row_descriptors(np.array([9]))


if __name__ == "__main__":
    unittest.main()
