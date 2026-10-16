"""transfer_one against a fake bucket: fresh hashes vs the frozen manifest, create-only upload, server hash readback."""
import base64
import hashlib
import os
import tempfile
import unittest

from research_cloud.deploy import transfer


class PreconditionFailed(Exception):
    pass


class FakeBlob:
    def __init__(self, store, name):
        self.store, self.name, self.metadata, self.md5_hash = store, name, None, None
        self.crc32c = self.generation = None

    def upload_from_filename(self, path, if_generation_match=None, checksum=None):
        data = open(path, "rb").read()
        if self.name in self.store and if_generation_match == 0:
            raise PreconditionFailed()
        if base64.b64encode(hashlib.md5(data).digest()).decode() != self.md5_hash:
            raise ValueError("md5 mismatch")            # GCS rejects a corrupted upload
        self.store[self.name] = (data, dict(self.metadata or {}), len(self.store) + 1)

    def reload(self):
        import google_crc32c
        data, meta, gen = self.store[self.name]
        self.md5_hash = base64.b64encode(hashlib.md5(data).digest()).decode()
        c = google_crc32c.Checksum()
        c.update(data)
        self.crc32c, self.metadata, self.generation = base64.b64encode(c.digest()).decode(), meta, gen


class FakeBucket:
    def __init__(self):
        self.store = {}

    def blob(self, name):
        return FakeBlob(self.store, name)


class Transfer(unittest.TestCase):
    def setUp(self):
        import google.api_core.exceptions as gexc
        self._orig = gexc.PreconditionFailed
        gexc.PreconditionFailed = PreconditionFailed
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "a.bin")
        open(self.path, "wb").write(b"payload-1")
        self.entry = {"local": self.path, "object": "p/a.bin", "bytes": 9,
                      "sha256": hashlib.sha256(b"payload-1").hexdigest()}

    def tearDown(self):
        import google.api_core.exceptions as gexc
        gexc.PreconditionFailed = self._orig

    def test_upload_resume_conflict_and_drift(self):
        bucket = FakeBucket()
        rec = transfer.transfer_one(bucket, self.entry)
        self.assertEqual(rec["status"], "verified (uploaded)")
        self.assertEqual((rec["cloud_md5"], rec["cloud_crc32c"]), (rec["local_md5"], rec["local_crc32c"]))
        self.assertEqual(rec["generation"], 1)
        self.assertEqual(transfer.transfer_one(bucket, self.entry)["status"], "verified (already present)")
        bucket.store["p/a.bin"] = (b"payload-X", {"sha256": self.entry["sha256"]}, 7)     # same size, other bytes
        self.assertTrue(transfer.transfer_one(bucket, self.entry)["status"].startswith("conflict"))
        open(self.path, "wb").write(b"payload-2")                                       # same size local drift
        rec = transfer.transfer_one(FakeBucket(), self.entry)
        self.assertTrue(rec["status"].startswith("rejected"))
        self.assertNotIn("generation", rec)                                              # never uploaded


if __name__ == "__main__":
    unittest.main()
