import os
import tempfile
import unittest

from research_cloud.inventory.booster_search import walk


class WalkRecordsFailures(unittest.TestCase):
    def test_unreadable_directory_is_reported_not_silently_skipped(self):
        root = tempfile.mkdtemp()
        locked = os.path.join(root, "locked")
        os.makedirs(locked)
        open(os.path.join(locked, "hidden.ubj"), "wb").close()
        open(os.path.join(root, "seen.ubj"), "wb").close()
        os.chmod(locked, 0)
        try:
            paths, errors, links = walk([root], "*.ubj")
        finally:
            os.chmod(locked, 0o755)
        self.assertEqual([os.path.basename(p) for p in paths], ["seen.ubj"])
        self.assertTrue(any(e["path"] == locked for e in errors))

    def test_symlinks_are_listed_not_followed(self):
        root, outside = tempfile.mkdtemp(), tempfile.mkdtemp()
        open(os.path.join(outside, "x.ubj"), "wb").close()
        os.symlink(os.path.join(outside, "x.ubj"), os.path.join(root, "link.ubj"))
        os.symlink(outside, os.path.join(root, "linkdir"))
        paths, errors, links = walk([root], "*.ubj")
        self.assertEqual(paths, [])
        self.assertEqual(sorted(os.path.basename(p) for p in links), ["link.ubj", "linkdir"])

    def test_missing_root_is_an_error(self):
        paths, errors, links = walk(["/nonexistent/root"], "*")
        self.assertEqual(errors[0]["path"], "/nonexistent/root")


if __name__ == "__main__":
    unittest.main()
