import unittest

from research_cloud.inventory.model_inventory import resolve

REC = {"bytes": 10, "sha256": "aa"}


def member(*cands):
    return dict(REC, candidates=list(cands))


class ResolveAcrossCandidateRoots(unittest.TestCase):
    def test_alternate_root_supplies_weight_deleted_from_first_root(self):
        m = member({"path": "/temp/x", "status": "missing"},
                   {"path": "/preserved/x", "status": "local", "bytes_actual": 10, "sha256_actual": "aa"})
        self.assertEqual(resolve(m), ("verified", "/preserved/x"))

    def test_mismatching_first_copy_does_not_hide_matching_second(self):
        m = member({"path": "/a/x", "status": "local", "bytes_actual": 10, "sha256_actual": "bb"},
                   {"path": "/b/x", "status": "local", "bytes_actual": 10, "sha256_actual": "aa"})
        self.assertEqual(resolve(m), ("verified", "/b/x"))

    def test_same_size_different_bytes_is_mismatch(self):
        m = member({"path": "/a/x", "status": "local", "bytes_actual": 10, "sha256_actual": "bb"})
        self.assertEqual(resolve(m)[0], "hash_mismatch")

    def test_inspection_error_never_becomes_missing(self):
        m = member({"path": "/a/x", "status": "missing"}, {"path": "/b/x", "status": "inspection_error"})
        self.assertEqual(resolve(m)[0], "inspection_error")

    def test_missing_requires_every_candidate_not_found(self):
        m = member({"path": "/a/x", "status": "missing"}, {"path": "/b/x", "status": "missing"})
        self.assertEqual(resolve(m)[0], "missing")

    def test_unhashed_local_is_not_verified(self):
        m = member({"path": "/a/x", "status": "local", "bytes_actual": 10})
        self.assertEqual(resolve(m)[0], "present_unverified")

    def test_no_existing_root(self):
        self.assertEqual(resolve(member())[0], "root_unavailable")


if __name__ == "__main__":
    unittest.main()
