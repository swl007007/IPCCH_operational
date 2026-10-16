import os
import tempfile
import unittest

from research_cloud.inventory.fews_catalog import count


class CountExposesWalkErrors(unittest.TestCase):
    def test_unreadable_subdir_makes_count_unknown(self):
        root = tempfile.mkdtemp()
        locked = os.path.join(root, "locked")
        os.makedirs(locked)
        open(os.path.join(locked, "predictions.csv.gz"), "w").close()
        os.chmod(locked, 0)
        errors = []
        try:
            n = count(root, [r"pred.*\.csv(\.gz)?$"], errors)
        finally:
            os.chmod(locked, 0o755)
        self.assertIsNone(n)
        self.assertEqual(errors[0]["path"], locked)

    def test_readable_tree_counts(self):
        root = tempfile.mkdtemp()
        open(os.path.join(root, "predictions.csv.gz"), "w").close()
        errors = []
        self.assertEqual(count(root, [r"pred.*\.csv(\.gz)?$"], errors), 1)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
