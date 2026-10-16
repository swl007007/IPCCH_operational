"""Preservation manifest: recorded-hash mismatches, unreadable records and the cache-hit label."""
import hashlib
import json
import os
import tempfile
import unittest

from research_cloud.inventory import preservation_manifest as pm


class Manifest(unittest.TestCase):
    def run_root(self):
        root = tempfile.mkdtemp()
        os.makedirs(f"{root}/out")
        open(f"{root}/out/a.csv", "wb").write(b"x,y\n1,2\n")
        good = hashlib.sha256(b"x,y\n1,2\n").hexdigest()
        return root, good

    def manifest(self, root, *extra):
        out = tempfile.mktemp(suffix=".json")
        code = pm.main(["--root", root, "--out", out, *extra])
        return code, json.load(open(out))

    def test_recorded_mismatch_and_unreadable_record_fail(self):
        root, good = self.run_root()
        json.dump({"outputs": {"a.csv": good}}, open(f"{root}/ok.json", "w"))
        code, m = self.manifest(root, "--recorded", "out=ok.json:outputs")
        self.assertEqual((code, m["complete"], m["totals"]["recorded_ok"]), (0, True, 1))
        json.dump({"outputs": {"a.csv": "0" * 64, "missing.csv": good}}, open(f"{root}/bad.json", "w"))
        code, m = self.manifest(root, "--recorded", "out=bad.json:outputs", "--recorded", "out=absent.json:outputs")
        self.assertEqual(code, 1)
        self.assertFalse(m["complete"])
        by = {(c["recorded_by"], c["path"]): c for c in m["recorded_checks"]}
        self.assertFalse(by[("bad.json", "out/a.csv")]["ok"])
        self.assertFalse(by[("bad.json", "out/missing.csv")]["present"])
        self.assertIn("FileNotFoundError", by[("absent.json", None)]["error"])

    def test_cache_label_only_when_the_cache_predicate_holds(self):
        root, good = self.run_root()
        path = f"{root}/out/a.csv"
        st = os.stat(path)
        cache = tempfile.mktemp(suffix=".jsonl")
        with open(cache, "w") as f:   # right digest, stale mtime: must be re-hashed and labelled fresh
            f.write(json.dumps({"path": path, "bytes": st.st_size, "mtime_ns": st.st_mtime_ns - 1, "sha256": good}) + "\n")
        _, m = self.manifest(root, "--cache", cache)
        self.assertEqual(m["files"][0]["hash_source"], "fresh")
        with open(cache, "w") as f:
            f.write(json.dumps({"path": path, "bytes": st.st_size, "mtime_ns": st.st_mtime_ns, "sha256": good}) + "\n")
        _, m = self.manifest(root, "--cache", cache)
        self.assertTrue(m["files"][0]["hash_source"].startswith("cache"))


if __name__ == "__main__":
    unittest.main()


class TopLevel(unittest.TestCase):
    def test_no_recurse_lists_loose_files_and_names_subdirectories(self):
        root = tempfile.mkdtemp()
        os.makedirs(f"{root}/run-a")
        open(f"{root}/run-a/inner.txt", "w").write("x")
        open(f"{root}/loose.log", "w").write("y")
        out = tempfile.mktemp(suffix=".json")
        self.assertEqual(pm.main(["--root", root, "--out", out, "--no-recurse"]), 0)
        m = json.load(open(out))
        self.assertEqual([f["path"] for f in m["files"]], ["loose.log"])
        self.assertEqual((m["recursive"], m["subdirectories_not_walked"]), (False, ["run-a"]))
