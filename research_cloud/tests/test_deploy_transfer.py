"""transfer_one against a fake bucket: fresh hashes vs the frozen manifest, create-only upload, server hash readback."""
import base64
import hashlib
import json
import os
import tempfile
import unittest

from research_cloud.deploy import transfer


class PreconditionFailed(Exception):
    pass


class FakeBlob:
    requests = []

    def __init__(self, store, name):
        self.store, self.name, self.metadata, self.md5_hash = store, name, None, None
        self.crc32c = self.generation = None

    def upload_from_filename(self, path, if_generation_match=None, checksum=None, timeout=None):
        FakeBlob.requests.append((getattr(self, "chunk_size", None), timeout))
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
    def __init__(self, name="bucket-a"):
        self.store, self.name = {}, name

    def blob(self, name):
        return FakeBlob(self.store, name)

    def get_blob(self, name):
        if name not in self.store:
            return None
        b = FakeBlob(self.store, name)
        b.reload()
        return b


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


class Main(unittest.TestCase):
    def setUp(self):
        import google.api_core.exceptions as gexc
        self._orig = gexc.PreconditionFailed
        gexc.PreconditionFailed = PreconditionFailed
        self.dir = tempfile.mkdtemp()
        self.root = os.path.join(self.dir, "root")
        os.makedirs(self.root)
        open(os.path.join(self.root, "a.bin"), "wb").write(b"payload-1")
        from research_cloud.inventory import preservation_manifest as pm
        self.manifest = os.path.join(self.dir, "m.json")
        pm.main(["--root", self.root, "--out", self.manifest])
        self.receipts = os.path.join(self.dir, "r.jsonl")

    def tearDown(self):
        import google.api_core.exceptions as gexc
        gexc.PreconditionFailed = self._orig

    def run_main(self, bucket, *extra):
        import contextlib
        import io
        import json
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = transfer.main(["--bucket", bucket.name, "--receipts", self.receipts, "--from-preservation",
                                self.manifest, "--prefix", "p", "--workers", "2", *extra], bucket=bucket)
        return rc, json.loads(out.getvalue().strip().splitlines()[-1])

    def test_receipts_never_skip_without_fresh_identity_checks(self):
        bucket = FakeBucket("bucket-a")
        self.assertEqual(self.run_main(bucket)[1]["counts"], {"verified": 1})
        rc, s = self.run_main(bucket)                          # unchanged: resumed after fresh checks
        self.assertEqual((rc, s["attempted"]), (0, 0))
        rc, s = self.run_main(FakeBucket("bucket-b"))           # same receipt, new empty bucket: not skipped
        self.assertEqual((rc, s["attempted"], s["counts"]), (0, 1, {"verified": 1}))
        open(os.path.join(self.root, "a.bin"), "wb").write(b"payload-X")   # same-size local drift
        rc, s = self.run_main(bucket)
        self.assertEqual((rc, s["attempted"], s["counts"]), (1, 1, {"rejected": 1}))

    def test_verify_mode_and_coverage(self):
        bucket = FakeBucket()
        self.run_main(bucket)
        rc, s = self.run_main(bucket, "--verify", os.path.join(self.dir, "v.json"))
        self.assertEqual((rc, s["complete"], s["counts"]), (0, True, {"verified": 1}))
        rc, s = self.run_main(FakeBucket("empty"), "--verify", os.path.join(self.dir, "v2.json"))
        self.assertEqual((rc, s["complete"]), (1, False))
        with self.assertRaises(SystemExit):
            self.run_main(bucket, "--expect-files", "2")

    def test_incomplete_sources_are_refused(self):
        import json
        m = json.load(open(self.manifest))
        json.dump({**m, "complete": False}, open(self.manifest, "w"))
        with self.assertRaises(transfer.TransferError):
            self.run_main(FakeBucket())
        pkgs = os.path.join(self.dir, "packages")
        os.makedirs(os.path.join(pkgs, "no-manifest"))
        with self.assertRaises(transfer.TransferError):
            transfer.from_packages(pkgs, "packages")

    def test_uploads_use_bounded_requests_and_errors_keep_cause_type(self):
        FakeBlob.requests.clear()
        rc, s = self.run_main(FakeBucket())
        self.assertEqual(rc, 0)
        self.assertEqual(FakeBlob.requests, [(transfer.CHUNK_BYTES, transfer.REQUEST_TIMEOUT_S)])
        self.assertEqual(transfer.CHUNK_BYTES % (256 * 1024), 0)

        class Failing(FakeBucket):
            def blob(self, name):
                b = super().blob(name)

                def boom(*a, **k):
                    from google.api_core.exceptions import RetryError
                    raise RetryError("deadline", TimeoutError("remote text must not be kept"))
                b.upload_from_filename = boom
                return b
        os.remove(self.receipts)
        rc, s = self.run_main(Failing())
        rec = [json.loads(l) for l in open(self.receipts)][-1]
        self.assertEqual((rec["status"], rec["error_cause"]), ("error: RetryError", "TimeoutError"))
        self.assertNotIn("remote text", open(self.receipts).read())

    def test_inventory_statuses_explicit(self):
        import json
        path = os.path.join(self.dir, "a.bin")
        open(path, "wb").write(b"abc")
        sha = hashlib.sha256(b"abc").hexdigest()

        def entry(**kw):
            return {"id": "x.a", "path": path, "local_status": "local", "match": True, "actual_sha256": sha,
                    "recorded_sha256": sha, "actual_bytes": 3, "recorded_bytes": None, **kw}

        def build(*entries):
            inv = os.path.join(self.dir, "inv.json")
            json.dump({"namespaces": {"n": {"files": list(entries)}}}, open(inv, "w"))
            return transfer.from_inventory(inv, "inputs")

        self.assertEqual(build(entry())[0]["manifest"], "input-inventory (recorded hash matched)")
        self.assertEqual(len(build(entry(local_status="local (non-DrvFS)"))), 1)
        got = build(entry(match="no_recorded_value", recorded_sha256=None))
        self.assertEqual(got[0]["manifest"], "input-inventory (P1 fresh hash (no recorded value))")
        for bad in (entry(local_status="online-only"), entry(match=False), entry(match="mismatch"),
                    entry(match="no_recorded_value"),                       # a recorded value exists: not this case
                    entry(recorded_sha256="0" * 64), entry(recorded_bytes=4), entry(actual_sha256=None)):
            with self.assertRaises(transfer.TransferError):
                build(bad)

    def test_torn_tail_recovered_malformed_line_refused(self):
        bucket = FakeBucket()
        self.run_main(bucket)
        good = open(self.receipts).read()
        open(self.receipts, "w").write(good + '{"object": "p/a.bin", "sta')      # torn last write
        rc, s = self.run_main(bucket)
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(self.receipts + ".tail"))
        open(self.receipts, "w").write('{"broken"\n' + good)                     # malformed complete line
        with self.assertRaises(transfer.TransferError):
            self.run_main(bucket)


if __name__ == "__main__":
    unittest.main()
