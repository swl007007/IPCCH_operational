"""publish_packages.copy_one against a fake bucket: receipts are never trusted alone - the source must still be the
transferred generation/hashes (copied from exactly that generation), an absent destination is (re)copied or reported
missing in verify mode, and a destination with other hashes is a conflict."""
import unittest

from research_cloud.deploy import publish_packages as pp


class Blob:
    def __init__(self, name, md5, crc, gen):
        self.name, self.md5_hash, self.crc32c, self.generation, self.size = name, md5, crc, gen, 3


class Bucket:
    def __init__(self):
        self.objects, self.copies = {}, []

    def get_blob(self, name):
        return self.objects.get(name)

    def copy_blob(self, src, bucket, dst, source_generation=None, if_generation_match=None):
        self.copies.append((src.name, dst, source_generation, if_generation_match))
        self.objects[dst] = Blob(dst, src.md5_hash, src.crc32c, 99)


REC = {"packages/p/a.bin": {"generation": 7, "local_md5": "m", "local_crc32c": "c"}}


class CopyOne(unittest.TestCase):
    def setUp(self):
        self.b = Bucket()
        self.b.objects["packages/p/a.bin"] = Blob("packages/p/a.bin", "m", "c", 7)

    def test_copy_from_the_transferred_generation(self):
        r = pp.copy_one(self.b, REC, "p", "run", "mlflow-artifacts/x/package", "a.bin")
        self.assertEqual(r["status"], "verified (copied)")
        self.assertEqual(self.b.copies, [("packages/p/a.bin", "mlflow-artifacts/x/package/a.bin", 7, 0)])
        r = pp.copy_one(self.b, REC, "p", "run", "mlflow-artifacts/x/package", "a.bin")   # rerun re-reads, no copy
        self.assertEqual((r["status"], len(self.b.copies)), ("verified (present (re-verified))", 1))

    def test_stale_source_and_missing_receipt_refused(self):
        self.b.objects["packages/p/a.bin"].generation = 8
        self.assertTrue(pp.copy_one(self.b, REC, "p", "run", "x", "a.bin")["status"].startswith("refused"))
        self.assertTrue(pp.copy_one(self.b, {}, "p", "run", "x", "a.bin")["status"].startswith("refused"))
        self.assertEqual(self.b.copies, [])

    def test_verify_mode_never_writes_and_detects_conflict(self):
        r = pp.copy_one(self.b, REC, "p", "run", "x", "a.bin", write=False)
        self.assertEqual((r["status"], self.b.copies), ("missing", []))
        self.b.objects["x/a.bin"] = Blob("x/a.bin", "other", "c", 5)
        self.assertEqual(pp.copy_one(self.b, REC, "p", "run", "x", "a.bin", write=False)["status"], "conflict")


if __name__ == "__main__":
    unittest.main()
