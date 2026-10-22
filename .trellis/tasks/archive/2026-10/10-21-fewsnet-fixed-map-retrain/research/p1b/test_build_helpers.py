"""Regression: builder comparisons are positional, never pandas index-aligned."""
import unittest

import numpy as np
import pandas as pd

from build_versioned_panel import diff_summary, same


class PositionalComparison(unittest.TestCase):
    def test_nonconsecutive_indexes_compare_by_position(self):
        old = pd.Series([1.0, 2.0, np.nan], index=[10, 42, 7])
        new = pd.Series([1.0, 5.0, 3.0])  # RangeIndex 0..2
        self.assertEqual(list(same(old, new)), [True, False, False])
        summary = diff_summary(old, new)
        self.assertEqual(summary["cells_both_present"], 2)
        self.assertEqual(summary["exact"], 1)
        self.assertEqual(summary["source_only_filled"], 1)
        self.assertEqual(summary["abs_diff_p90"], 2.7)

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            same(pd.Series([1.0, 2.0]), pd.Series([1.0]))


if __name__ == "__main__":
    unittest.main()
